"""Company Research Agent — seven-step sequential orchestrator.

Implements Phase 8 of the Agentic Equity Research Platform.  The agent
runs a fixed seven-step workflow (no LangGraph), tracks token budgets,
enforces retry limits, and persists all outputs through the
``ResearchRunService`` (Phase 7).

Dependencies are injected via Protocol interfaces — the agent never
imports a concrete provider.
"""
from __future__ import annotations

import asyncio
import json
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
from app.agents.company_research.prompts import (
    evidence_extraction_prompt,
    finding_generation_prompt,
    gap_contradiction_prompt,
)
from app.agents.company_research.tools import CompanyResearchTools
from app.agents.contracts import (
    AGENT_NAME,
    COMPANY_RESEARCH_STEPS,
    FINDING_CATEGORIES,
    CompanyResearchConfig,
    CompanyResearchRequest,
    DiscoverSourcesInput,
    EvidenceExtractionOutput,
    EvidenceItem,
    ExtractedEvidence,
    FindingGenerationOutput,
    FindingItem,
    FindingValidationIssue,
    FindingValidationResult,
    PersistEvidenceInput,
    PersistFindingsInput,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
    TokenBudget,
    ValidateCompanyInput,
    ValidateCompanyOutput,
)
from app.models.enums import FindingType
from app.models.research import ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateFilingsProvider,
    FinancialDataProvider,
    LLMProvider,
    NewsProvider,
    TranscriptProvider,
)
from app.providers.types import LLMResponse
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


class CompanyResearchResult(BaseModel):
    """Result returned by the Company Research Agent."""

    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    status: str
    company_id: uuid.UUID
    company_name: str
    findings_count: int = 0
    evidence_count: int = 0
    steps_completed: int = 0
    steps_total: int = Field(default=len(COMPANY_RESEARCH_STEPS))
    token_budget: TokenBudget
    validation_result: FindingValidationResult | None = None
    error: str | None = None


class CompanyResearchAgent:
    """Orchestrates a seven-step company research workflow.

    Construction requires Protocol-typed providers and a database session.
    Call :meth:`execute` with a :class:`CompanyResearchRequest` to run the
    full pipeline.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        corporate_filings: CorporateFilingsProvider,
        financial_data: FinancialDataProvider,
        news: NewsProvider,
        transcript: TranscriptProvider,
        llm: LLMProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._llm = llm

        self._tools = CompanyResearchTools(
            session=session,
            run_service=run_service,
            corporate_filings=corporate_filings,
            financial_data=financial_data,
            news=news,
            transcript=transcript,
            llm=llm,
        )

    async def execute(
        self, request: CompanyResearchRequest,
    ) -> CompanyResearchResult:
        config = request.configuration or CompanyResearchConfig()
        token_budget = TokenBudget(
            budget=config.token_budget,
            warning_threshold=config.token_warning_threshold,
        )

        run = await self._run_service.initiate_run(ResearchRunCreate(
            company_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            initiated_by=request.initiated_by,
            run_type="company_research",
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
            for sd in COMPANY_RESEARCH_STEPS
        ]
        db_steps = await self._run_service.create_steps(run_id, step_defs)
        step_map = {s.step_name: s for s in db_steps}

        await self._run_service.enqueue_run(run_id)
        await self._run_service.start_run(run_id)

        company_info: ValidateCompanyOutput | None = None
        sources: list[SourceCandidate] = []
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []
        all_findings: list[FindingItem] = []
        validation_result: FindingValidationResult | None = None
        steps_completed = 0
        error_msg: str | None = None

        try:
            # -- Step 1: company_validation ------------------------------------
            company_info = await self._run_step_deterministic(
                step_map["company_validation"],
                self._step_company_validation(request),
            )
            steps_completed += 1

            # Update run with real company_id via service layer
            await self._run_service.update_run_company(
                run_id, company_info.company_id,
            )

            # -- Step 2: source_discovery --------------------------------------
            sources = await self._run_step_deterministic(
                step_map["source_discovery"],
                self._step_source_discovery(
                    company_info.company_id,
                    request.observation_date,
                    config,
                ),
            )
            steps_completed += 1

            # -- Step 3: document_retrieval ------------------------------------
            doc_retrieval_result = await self._run_step_deterministic(
                step_map["document_retrieval"],
                self._step_document_retrieval(
                    company_info.company_id, sources, config,
                    run_id=run_id,
                ),
            )
            documents = doc_retrieval_result[0]
            document_ids = doc_retrieval_result[1]
            steps_completed += 1

            # -- Step 4: evidence_extraction (LLM) -----------------------------
            ev_result = await self._run_step_llm(
                step_map["evidence_extraction"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_evidence_extraction(
                    company_info, documents, document_ids, exec_id,
                    token_budget, config,
                ),
            )
            all_evidence = ev_result[0]
            all_evidence_ids = ev_result[1]
            steps_completed += 1

            # -- Step 5: finding_generation (LLM) ------------------------------
            all_findings = await self._run_step_llm(
                step_map["finding_generation"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_finding_generation(
                    company_info, all_evidence, all_evidence_ids,
                    run_id, exec_id, token_budget, config,
                    observation_date=request.observation_date,
                ),
            )
            steps_completed += 1

            # -- Step 6: finding_validation (deterministic) --------------------
            validation_result = await self._run_step_deterministic(
                step_map["finding_validation"],
                self._step_finding_validation(
                    all_findings, all_evidence_ids,
                ),
            )
            steps_completed += 1

            # -- Step 7: gap_contradiction_analysis (LLM) ----------------------
            gap_findings: list[FindingItem] = await self._run_step_llm(
                step_map["gap_contradiction_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_gap_contradiction(
                    company_info, all_findings, run_id, exec_id,
                    token_budget, config,
                    observation_date=request.observation_date,
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

        return CompanyResearchResult(
            run_id=run_id,
            status=status,
            company_id=company_info.company_id if company_info else uuid.UUID(int=0),
            company_name=company_info.name if company_info else "",
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
        config: CompanyResearchConfig,
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
                    agent_name=AGENT_NAME,
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

    async def _step_company_validation(
        self, request: CompanyResearchRequest,
    ) -> ValidateCompanyOutput:
        return await self._tools.validate_company(
            ValidateCompanyInput(
                identifier=request.company_identifier,
                identifier_type=request.identifier_type,
            ),
        )

    async def _step_source_discovery(
        self,
        company_id: uuid.UUID,
        observation_date: date,
        config: CompanyResearchConfig,
    ) -> list[SourceCandidate]:
        result = await self._tools.discover_sources(
            DiscoverSourcesInput(
                company_id=company_id,
                observation_date=observation_date,
                document_types=config.document_types,
                limit=config.source_limit,
            ),
        )
        return result.candidates

    async def _step_document_retrieval(
        self,
        company_id: uuid.UUID,
        sources: list[SourceCandidate],
        config: CompanyResearchConfig,
        run_id: uuid.UUID | None = None,
    ) -> tuple[dict[str, RetrieveDocumentOutput], dict[str, uuid.UUID]]:
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        sem = asyncio.Semaphore(config.concurrent_retrievals)

        async def _retrieve(candidate: SourceCandidate) -> None:
            async with sem:
                try:
                    doc = await self._tools.retrieve_document(
                        RetrieveDocumentInput(
                            filing_id=candidate.source_id,
                            provider=candidate.provider,
                        ),
                    )
                    documents[candidate.source_id] = doc
                    doc_id = await self._tools.create_research_document(
                        company_id, candidate, doc.content_hash,
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

    async def _step_evidence_extraction(
        self,
        company_info: ValidateCompanyOutput,
        documents: dict[str, RetrieveDocumentOutput],
        document_ids: dict[str, uuid.UUID],
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: CompanyResearchConfig,
    ) -> tuple[list[ExtractedEvidence], list[uuid.UUID]]:
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []

        for source_id, doc in documents.items():
            if token_budget.is_exhausted:
                raise TokenBudgetExhaustedError(
                    token_budget.total_tokens, token_budget.budget,
                )

            prompt = evidence_extraction_prompt(
                company_name=company_info.name,
                document_content=doc.content,
                source_id=source_id,
                document_title=doc.filing_id,
            )

            schema = EvidenceExtractionOutput.model_json_schema()
            response = await self._llm.generate(
                prompt,
                model=config.extraction_model,
                response_schema=schema,
            )
            token_budget.record_usage(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            extracted = _parse_evidence_response(response)
            all_evidence.extend(extracted.evidences)

            if source_id in document_ids:
                evidence_items = [
                    EvidenceItem(
                        evidence_type=ev.evidence_type,
                        claim=ev.claim,
                        context=ev.context,
                        page_or_section=ev.page_or_section,
                        confidence=ev.confidence,
                    )
                    for ev in extracted.evidences
                ]
                if evidence_items:
                    persist_result = await self._tools.persist_evidence(
                        PersistEvidenceInput(
                            document_id=document_ids[source_id],
                            evidences=evidence_items,
                        ),
                    )
                    all_evidence_ids.extend(persist_result.evidence_ids)

        return all_evidence, all_evidence_ids

    async def _step_finding_generation(
        self,
        company_info: ValidateCompanyOutput,
        evidence: list[ExtractedEvidence],
        evidence_ids: list[uuid.UUID],
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: CompanyResearchConfig,
        observation_date: date | None = None,
    ) -> list[FindingItem]:
        if token_budget.is_exhausted:
            raise TokenBudgetExhaustedError(
                token_budget.total_tokens, token_budget.budget,
            )

        evidence_summaries = "\n".join(
            f"[{i}] ({ev.evidence_type}) {ev.claim}"
            for i, ev in enumerate(evidence)
        )

        prompt = finding_generation_prompt(
            company_name=company_info.name,
            evidence_summaries=evidence_summaries,
        )

        schema = FindingGenerationOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.generation_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        generated = _parse_finding_response(response)

        findings: list[FindingItem] = []
        for gf in generated.findings:
            linked_evidence: list[uuid.UUID] = []
            if gf.evidence_indices:
                for idx in gf.evidence_indices:
                    if 0 <= idx < len(evidence_ids):
                        linked_evidence.append(evidence_ids[idx])

            findings.append(FindingItem(
                finding_type=gf.finding_type,
                category=gf.category,
                content=gf.content,
                confidence=gf.confidence,
                observation_date=observation_date,
                source_publication_date=gf.source_publication_date,
                evidence_ids=linked_evidence or None,
            ))

        if findings:
            await self._tools.persist_findings(PersistFindingsInput(
                run_id=run_id,
                execution_id=execution_id,
                findings=findings,
            ))

        return findings

    async def _step_finding_validation(
        self,
        findings: list[FindingItem],
        evidence_ids: list[uuid.UUID],
    ) -> FindingValidationResult:
        issues: list[FindingValidationIssue] = []

        for i, f in enumerate(findings):
            if f.category not in FINDING_CATEGORIES:
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="invalid_category",
                    message=f"Category '{f.category}' not in allowed set",
                ))

            if not f.content or not f.content.strip():
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="empty_content",
                    message="Finding content is empty",
                ))

            if f.finding_type == FindingType.FACT and not f.evidence_ids:
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="fact_without_evidence",
                    message="FACT-type finding must have linked evidence",
                ))

            if (
                f.source_publication_date is not None
                and f.observation_date is not None
                and f.source_publication_date > f.observation_date
            ):
                issues.append(FindingValidationIssue(
                    finding_index=i,
                    issue_type="temporal_inconsistency",
                    message=(
                        f"source_publication_date ({f.source_publication_date})"
                        f" is after observation_date ({f.observation_date})"
                    ),
                ))

        rejected_indices = {iss.finding_index for iss in issues}
        valid_count = len(findings) - len(rejected_indices)

        return FindingValidationResult(
            total_findings=len(findings),
            valid_count=valid_count,
            rejected_count=len(rejected_indices),
            issues=issues,
        )

    async def _step_gap_contradiction(
        self,
        company_info: ValidateCompanyOutput,
        existing_findings: list[FindingItem],
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: CompanyResearchConfig,
        observation_date: date | None = None,
    ) -> list[FindingItem]:
        if token_budget.is_exhausted:
            raise TokenBudgetExhaustedError(
                token_budget.total_tokens, token_budget.budget,
            )

        findings_summary = "\n".join(
            f"[{i}] ({f.finding_type}/{f.category}) {f.content}"
            for i, f in enumerate(existing_findings)
        )

        prompt = gap_contradiction_prompt(
            company_name=company_info.name,
            findings_summary=findings_summary,
        )

        schema = FindingGenerationOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.analysis_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        generated = _parse_finding_response(response)

        gap_findings: list[FindingItem] = []
        for gf in generated.findings:
            if gf.category not in ("research_gap", "contradiction"):
                continue
            gap_findings.append(FindingItem(
                finding_type=gf.finding_type,
                category=gf.category,
                content=gf.content,
                confidence=gf.confidence,
                observation_date=observation_date,
                source_publication_date=None,
                evidence_ids=None,
            ))

        if gap_findings:
            await self._tools.persist_findings(PersistFindingsInput(
                run_id=run_id,
                execution_id=execution_id,
                findings=gap_findings,
            ))

        return gap_findings


# ---------------------------------------------------------------------------
# LLM response parsing helpers
# ---------------------------------------------------------------------------


def _parse_evidence_response(response: LLMResponse) -> EvidenceExtractionOutput:
    try:
        data = json.loads(response.content)
        return EvidenceExtractionOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "evidence_extraction", str(exc),
        ) from exc


def _parse_finding_response(response: LLMResponse) -> FindingGenerationOutput:
    try:
        data = json.loads(response.content)
        return FindingGenerationOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "finding_generation", str(exc),
        ) from exc
