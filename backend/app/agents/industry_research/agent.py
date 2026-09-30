"""Industry Research Agent — seven-step sequential orchestrator.

Implements Phase 9.3b.1 of the Agentic Equity Research Platform.  The agent
runs a fixed seven-step workflow (no LangGraph), tracks token budgets,
enforces retry limits, and persists all outputs through the
``ResearchRunService`` (Phase 7).

LLM reasoning steps (4, 5, 7) are stub boundaries in this phase — they
record agent executions but perform no actual LLM calls and produce no
findings.  Deterministic steps (1, 6) and provider-call steps (2, 3) are
fully functional.

Dependencies are injected via Protocol interfaces — the agent never
imports a concrete provider.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.agents.company_research.exceptions import (
    LLMParsingError,
    StepFailedError,
    TokenBudgetExhaustedError,
)
from app.agents.contracts import (
    INDUSTRY_AGENT_NAME,
    INDUSTRY_FINDING_CATEGORIES,
    INDUSTRY_RESEARCH_STEPS,
    DiscoverIndustrySourcesInput,
    FindingValidationIssue,
    FindingValidationResult,
    IndustryResearchConfig,
    IndustryResearchRequest,
    RetrieveIndustryDocumentInput,
    RetrieveIndustryDocumentOutput,
    SourceCandidate,
    TokenBudget,
    ValidateIndustryInput,
    ValidateIndustryOutput,
)
from app.agents.industry_research.tools import IndustryResearchTools
from app.models.research import ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    NewsProvider,
    SearchProvider,
)
from app.schemas.research_run import (
    AgentExecutionCreate,
    ResearchRunCreate,
    ResearchRunStepCreate,
    TokenUsage,
)
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class IndustryResearchResult(BaseModel):
    """Result returned by the Industry Research Agent."""

    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    status: str
    industry_id: uuid.UUID
    industry_name: str
    findings_count: int = 0
    evidence_count: int = 0
    steps_completed: int = 0
    steps_total: int = Field(default=len(INDUSTRY_RESEARCH_STEPS))
    token_budget: TokenBudget
    validation_result: FindingValidationResult | None = None
    error: str | None = None


class IndustryResearchAgent:
    """Orchestrates a seven-step industry research workflow.

    Construction requires Protocol-typed providers and a database session.
    Call :meth:`execute` with an :class:`IndustryResearchRequest` to run the
    full pipeline.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        search: SearchProvider,
        news: NewsProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service

        self._tools = IndustryResearchTools(
            session=session,
            run_service=run_service,
            search=search,
            news=news,
        )

    async def execute(
        self, request: IndustryResearchRequest,
    ) -> IndustryResearchResult:
        config = request.configuration or IndustryResearchConfig()
        token_budget = TokenBudget(
            budget=config.token_budget,
            warning_threshold=config.token_warning_threshold,
        )

        run = await self._run_service.initiate_run(ResearchRunCreate(
            target_type="industry",
            industry_id=request.industry_id,
            initiated_by=request.initiated_by,
            run_type="industry_research",
            trigger_type="manual",
            observation_date=request.observation_date,
            configuration={
                "token_budget": config.token_budget,
                "source_limit": config.source_limit,
            },
        ))
        run_id = run.id

        step_defs = [
            ResearchRunStepCreate(
                step_name=sd.step_name,
                step_order=sd.step_order,
                step_type=sd.step_type,
            )
            for sd in INDUSTRY_RESEARCH_STEPS
        ]
        db_steps = await self._run_service.create_steps(run_id, step_defs)
        step_map = {s.step_name: s for s in db_steps}

        await self._run_service.enqueue_run(run_id)
        await self._run_service.start_run(run_id)

        industry_info: ValidateIndustryOutput | None = None
        sources: list[SourceCandidate] = []
        all_evidence_ids: list[uuid.UUID] = []
        all_findings: list[object] = []
        validation_result: FindingValidationResult | None = None
        steps_completed = 0
        error_msg: str | None = None

        try:
            # -- Step 1: industry_validation ------------------------------------
            industry_info = await self._run_step_deterministic(
                step_map["industry_validation"],
                self._step_industry_validation(request),
            )
            steps_completed += 1

            # -- Step 2: industry_source_discovery ------------------------------
            sources = await self._run_step_deterministic(
                step_map["industry_source_discovery"],
                self._step_source_discovery(
                    industry_info.industry_id,
                    industry_info.name,
                    request.observation_date,
                    config,
                ),
            )
            steps_completed += 1

            # -- Step 3: document_retrieval -------------------------------------
            await self._run_step_deterministic(
                step_map["document_retrieval"],
                self._step_document_retrieval(
                    sources, config, run_id=run_id,
                ),
            )
            steps_completed += 1

            # -- Step 4: evidence_extraction (LLM stub) -------------------------
            all_evidence_ids = await self._run_step_llm(
                step_map["evidence_extraction"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_evidence_extraction_stub(
                    exec_id,
                ),
            )
            steps_completed += 1

            # -- Step 5: industry_analysis (LLM stub) ---------------------------
            analysis_findings = await self._run_step_llm(
                step_map["industry_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_industry_analysis_stub(
                    exec_id,
                ),
            )
            all_findings.extend(analysis_findings)
            steps_completed += 1

            # -- Step 6: finding_validation (deterministic) ---------------------
            validation_result = await self._run_step_deterministic(
                step_map["finding_validation"],
                self._step_finding_validation(all_findings),
            )
            steps_completed += 1

            # -- Step 7: gap_contradiction_analysis (LLM stub) ------------------
            gap_findings = await self._run_step_llm(
                step_map["gap_contradiction_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_gap_contradiction_stub(
                    exec_id,
                ),
            )
            all_findings.extend(gap_findings)
            steps_completed += 1

            await self._run_service.update_run_aggregates(run_id)
            await self._run_service.complete_run(run_id)
            status = "COMPLETED"

        except TokenBudgetExhaustedError as exc:
            error_msg = str(exc)
            logger.warning("Token budget exhausted: %s", exc)
            await self._run_service.update_run_aggregates(run_id)
            await self._run_service.partial_run(run_id, error_msg)
            status = "PARTIAL"

        except StepFailedError as exc:
            error_msg = str(exc)
            logger.error("Step failed: %s", exc)
            if steps_completed >= 5:
                await self._run_service.update_run_aggregates(run_id)
                await self._run_service.partial_run(run_id, error_msg)
                status = "PARTIAL"
            else:
                await self._run_service.update_run_aggregates(run_id)
                await self._run_service.fail_run(run_id, error_msg)
                status = "FAILED"

        except Exception as exc:
            error_msg = f"Unexpected error: {type(exc).__name__}: {exc}"
            logger.exception("Agent execution failed")
            try:
                await self._run_service.update_run_aggregates(run_id)
                await self._run_service.fail_run(run_id, error_msg)
            except Exception:
                logger.exception("Failed to record run failure")
            status = "FAILED"

        return IndustryResearchResult(
            run_id=run_id,
            status=status,
            industry_id=industry_info.industry_id if industry_info else uuid.UUID(int=0),
            industry_name=industry_info.name if industry_info else "",
            findings_count=len(all_findings),
            evidence_count=len(all_evidence_ids),
            steps_completed=steps_completed,
            token_budget=token_budget,
            validation_result=validation_result,
            error=error_msg,
        )

    # -----------------------------------------------------------------------
    # Step runner helpers
    # -----------------------------------------------------------------------

    async def _run_step_deterministic(
        self,
        step: ResearchRunStep,
        coro: Awaitable[_T],
    ) -> _T:
        step_id = step.id
        step_name = step.step_name
        await self._run_service.start_step(step_id)
        try:
            result = await coro
            await self._run_service.complete_step(step_id)
            return result
        except Exception as exc:
            await self._run_service.fail_step(step_id, str(exc))
            raise StepFailedError(step_name, str(exc)) from exc

    async def _run_step_llm(
        self,
        step: ResearchRunStep,
        run_id: uuid.UUID,
        token_budget: TokenBudget,
        config: IndustryResearchConfig,
        fn: Callable[[uuid.UUID], Awaitable[_T]],
    ) -> _T:
        step_id = step.id
        step_name = step.step_name
        max_attempts = config.max_llm_attempts

        if token_budget.is_exhausted:
            await self._run_service.skip_step(step_id)
            raise TokenBudgetExhaustedError(
                token_budget.total_tokens, token_budget.budget,
            )

        await self._run_service.start_step(step_id)

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            execution = await self._run_service.record_agent_execution(
                run_id, step_id,
                AgentExecutionCreate(
                    agent_name=INDUSTRY_AGENT_NAME,
                    attempt_number=attempt,
                    model_provider="llm",
                    model_name=config.extraction_model or "default",
                ),
            )
            start_time = time.monotonic()
            try:
                result = await fn(execution.id)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                await self._run_service.complete_agent(
                    execution.id,
                    token_usage=TokenUsage(
                        input_tokens=token_budget.input_tokens,
                        output_tokens=token_budget.output_tokens,
                    ),
                    cost_usd=Decimal("0"),
                    findings_count=0,
                    duration_ms=duration_ms,
                )
                await self._run_service.complete_step(step_id)
                return result
            except (LLMParsingError, ProviderError) as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                last_error = exc
                logger.warning(
                    "LLM attempt %d/%d failed for %s: %s",
                    attempt, max_attempts, step_name, exc,
                )
                await self._run_service.fail_agent(
                    execution.id,
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                    duration_ms=duration_ms,
                )
                if attempt < max_attempts:
                    await self._run_service.retry_step(step_id)
                continue
            except TokenBudgetExhaustedError:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                await self._run_service.fail_agent(
                    execution.id,
                    error_message="Token budget exhausted",
                    error_type="TokenBudgetExhaustedError",
                    duration_ms=duration_ms,
                )
                await self._run_service.fail_step(step_id, "Token budget exhausted")
                raise

        await self._run_service.fail_step(step_id, str(last_error))
        raise StepFailedError(step_name, str(last_error))

    # -----------------------------------------------------------------------
    # Step implementations
    # -----------------------------------------------------------------------

    async def _step_industry_validation(
        self, request: IndustryResearchRequest,
    ) -> ValidateIndustryOutput:
        return await self._tools.validate_industry(
            ValidateIndustryInput(
                industry_id=request.industry_id,
            ),
        )

    async def _step_source_discovery(
        self,
        industry_id: uuid.UUID,
        industry_name: str,
        observation_date: date,
        config: IndustryResearchConfig,
    ) -> list[SourceCandidate]:
        result = await self._tools.discover_industry_sources(
            DiscoverIndustrySourcesInput(
                industry_id=industry_id,
                industry_name=industry_name,
                observation_date=observation_date,
                document_types=config.document_types,
                limit=config.source_limit,
            ),
        )
        return result.candidates

    async def _step_document_retrieval(
        self,
        sources: list[SourceCandidate],
        config: IndustryResearchConfig,
        run_id: uuid.UUID | None = None,
    ) -> tuple[dict[str, RetrieveIndustryDocumentOutput], dict[str, uuid.UUID]]:
        documents: dict[str, RetrieveIndustryDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        sem = asyncio.Semaphore(config.concurrent_retrievals)

        async def _retrieve(candidate: SourceCandidate) -> None:
            async with sem:
                try:
                    doc = await self._tools.retrieve_industry_document(
                        RetrieveIndustryDocumentInput(
                            source_id=candidate.source_id,
                            url=candidate.url or candidate.source_id,
                        ),
                    )
                    documents[candidate.source_id] = doc
                    doc_id = await self._tools.create_research_document(
                        candidate, doc.content_hash,
                    )
                    document_ids[candidate.source_id] = doc_id
                    if run_id is not None:
                        await self._run_service.record_source_access(
                            run_id, doc_id, "retrieved",
                        )
                except ProviderError:
                    logger.warning(
                        "Failed to retrieve document %s", candidate.source_id,
                    )

        tasks = [_retrieve(c) for c in sources]
        await asyncio.gather(*tasks)
        return documents, document_ids

    async def _step_evidence_extraction_stub(
        self,
        execution_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """LLM stub — returns empty evidence list. Phase 9.3b.2 adds real extraction."""
        return []

    async def _step_industry_analysis_stub(
        self,
        execution_id: uuid.UUID,
    ) -> list[object]:
        """LLM stub — returns empty findings list. Phase 9.3b.2 adds real analysis."""
        return []

    async def _step_finding_validation(
        self,
        findings: list[object],
    ) -> FindingValidationResult:
        issues: list[FindingValidationIssue] = []
        valid_count = 0
        rejected_count = 0

        for i, f in enumerate(findings):
            if not hasattr(f, "category"):
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="missing_category",
                    message="Finding lacks a category attribute",
                ))
                rejected_count += 1
                continue

            category = f.category
            if category not in INDUSTRY_FINDING_CATEGORIES:
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="invalid_category",
                    message=f"Category '{category}' not in allowed industry categories",
                ))
                rejected_count += 1
                continue

            valid_count += 1

        return FindingValidationResult(
            total_findings=len(findings),
            valid_count=valid_count,
            rejected_count=rejected_count,
            issues=issues,
        )

    async def _step_gap_contradiction_stub(
        self,
        execution_id: uuid.UUID,
    ) -> list[object]:
        """LLM stub — returns empty gap/contradiction list. Phase 9.3b.2 adds real analysis."""
        return []
