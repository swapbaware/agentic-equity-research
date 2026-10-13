"""Management & Governance Agent — sequential orchestration layer (Phase 11.4).

Orchestrates a seven-step workflow to assess management quality, corporate
governance, and capital allocation for Indian listed companies.  Follows the
Phase 10.4 CompetitiveMoatAgent pattern: frozen result model, constructor
with DI, execute() method, _run_step_deterministic() / _run_step_llm()
helpers, exception-based flow control.

Reuses shared exceptions from ``app.agents.company_research.exceptions``
per TD-17 (exception consolidation deferred).
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

from app.agents.company_research.exceptions import (
    LLMParsingError,
    StepFailedError,
    TokenBudgetExhaustedError,
)
from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_FINDING_CATEGORIES,
    GOVERNANCE_RED_FLAG_CATEGORIES,
    GOVERNANCE_RESEARCH_STEPS,
    DiscoverGovernanceSourcesInput,
    DiscoverGovernanceSourcesOutput,
    EvidenceExtractionOutput,
    EvidenceItem,
    ExtractedEvidence,
    FindingItem,
    GeneratedFinding,
    GovernanceAnalysisOutput,
    GovernanceValidationIssue,
    GovernanceValidationResult,
    LoadGovernanceContextInput,
    LoadGovernanceContextOutput,
    ManagementGovernanceConfig,
    ManagementGovernanceResearchRequest,
    ManagementGovernanceResult,
    ManagementStatementSummary,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistGovernanceDataInput,
    PersistShareholdingInput,
    PersistStatementsInput,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    ShareholdingSnapshot,
    SourceCandidate,
    TokenBudget,
)
from app.agents.management_governance.prompts import (
    governance_analysis_prompt,
    governance_evidence_extraction_prompt,
)
from app.agents.management_governance.tools import ManagementGovernanceTools
from app.models.enums import (
    ConfidenceLevel,
    FindingType,
    ManagementStatementCategory,
)
from app.models.research import ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateActionsProvider,
    CorporateFilingsProvider,
    LLMProvider,
    ShareholdingProvider,
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

_VALID_MANAGEMENT_STATEMENT_CATEGORIES: frozenset[str] = frozenset(c.value for c in ManagementStatementCategory)

_TERMINAL_STATUSES: frozenset[str] = frozenset({"MET", "PARTIALLY_MET", "MISSED"})

_VALID_RED_FLAG_SEVERITIES: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW"})


class ManagementGovernanceAgent:
    """Orchestrates a seven-step management & governance research workflow."""

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        corporate_filings: CorporateFilingsProvider,
        shareholding: ShareholdingProvider,
        corporate_actions: CorporateActionsProvider,
        llm: LLMProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._llm = llm

        self._tools = ManagementGovernanceTools(
            session=session,
            run_service=run_service,
            corporate_filings=corporate_filings,
            shareholding=shareholding,
            corporate_actions=corporate_actions,
        )

    async def execute(
        self,
        request: ManagementGovernanceResearchRequest,
    ) -> ManagementGovernanceResult:
        config = request.configuration or ManagementGovernanceConfig()
        token_budget = TokenBudget(
            budget=config.token_budget,
            warning_threshold=config.token_warning_threshold,
        )

        run = await self._run_service.initiate_run(
            ResearchRunCreate(
                target_type="company",
                company_id=request.company_id,
                initiated_by=request.initiated_by,
                run_type="management_governance",
                trigger_type="manual",
                observation_date=request.observation_date,
                configuration={
                    "token_budget": config.token_budget,
                    "filing_types": config.filing_types,
                    "shareholding_quarters": config.shareholding_quarters,
                    "corporate_action_years": config.corporate_action_years,
                },
            ),
        )
        run_id = run.id

        step_defs = [
            ResearchRunStepCreate(
                step_name=sd.step_name,
                step_order=sd.step_order,
                step_type=sd.step_type,
            )
            for sd in GOVERNANCE_RESEARCH_STEPS
        ]
        db_steps = await self._run_service.create_steps(run_id, step_defs)
        step_map = {s.step_name: s for s in db_steps}

        await self._run_service.enqueue_run(run_id)
        await self._run_service.start_run(run_id)

        context: LoadGovernanceContextOutput | None = None
        discovery: DiscoverGovernanceSourcesOutput | None = None
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []
        all_finding_ids: list[uuid.UUID] = []
        analysis_output: GovernanceAnalysisOutput | None = None
        validation_result: GovernanceValidationResult | None = None
        shareholding_findings: list[GeneratedFinding] = []
        all_statement_created_ids: list[uuid.UUID] = []
        all_statement_updated_ids: list[uuid.UUID] = []
        all_shareholding_ids: list[uuid.UUID] = []
        all_pledge_ids: list[uuid.UUID] = []
        all_corporate_action_ids: list[uuid.UUID] = []
        steps_completed = 0
        error_msg: str | None = None

        try:
            # -- Step 1: company_context_load ------------------------------------
            context = await self._run_step_deterministic(
                step_map["company_context_load"],
                self._step_company_context_load(request),
            )
            steps_completed += 1

            # -- Step 2: governance_source_discovery -----------------------------
            discovery = await self._run_step_deterministic(
                step_map["governance_source_discovery"],
                self._step_governance_source_discovery(
                    context,
                    config,
                    request.observation_date,
                ),
            )
            steps_completed += 1

            # -- Step 3: document_retrieval --------------------------------------
            doc_result = await self._run_step_deterministic(
                step_map["document_retrieval"],
                self._step_document_retrieval(
                    context.company_id,
                    discovery.filing_candidates,
                    config,
                    run_id,
                ),
            )
            documents = doc_result[0]
            document_ids = doc_result[1]
            steps_completed += 1

            # -- Step 4: evidence_extraction (LLM) -------------------------------
            ev_result = await self._run_step_llm(
                step_map["evidence_extraction"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_evidence_extraction(
                    context,
                    documents,
                    document_ids,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.extraction_model or "default",
            )
            all_evidence = ev_result[0]
            all_evidence_ids = ev_result[1]
            steps_completed += 1

            # -- Step 5: governance_analysis (LLM) -------------------------------
            analysis_result = await self._run_step_llm(
                step_map["governance_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_governance_analysis(
                    context,
                    all_evidence,
                    all_evidence_ids,
                    discovery,
                    run_id,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.analysis_model or "default",
            )
            analysis_output = analysis_result[0]
            all_finding_ids.extend(analysis_result[1])
            steps_completed += 1

            # -- Step 5a: deterministic shareholding/pledge findings -------------
            shareholding_findings = _generate_shareholding_findings(
                discovery.shareholding_data,
                request.observation_date,
            )
            pledge_findings = _generate_pledge_findings(
                discovery.shareholding_data,
                request.observation_date,
            )
            shareholding_findings.extend(pledge_findings)

            # -- Step 5b: deterministic data-gap UNCERTAINTY findings ------------
            data_gap_findings = _generate_data_gap_findings(
                discovery.data_gaps,
                request.observation_date,
            )
            shareholding_findings.extend(data_gap_findings)

            # -- Step 6: governance_validation (deterministic) -------------------
            validation_result = await self._run_step_deterministic(
                step_map["governance_validation"],
                self._step_governance_validation(
                    analysis_output,
                    shareholding_findings,
                    all_evidence,
                    all_evidence_ids,
                    context.existing_statements,
                    request.observation_date,
                    shareholding_snapshots=discovery.shareholding_data,
                ),
            )
            steps_completed += 1

            # -- Step 7: persistence (deterministic) ----------------------------
            persist_result = await self._run_step_deterministic(
                step_map["persistence"],
                self._step_persistence(
                    context,
                    analysis_output,
                    shareholding_findings,
                    validation_result,
                    all_evidence_ids,
                    discovery,
                    run_id,
                    request.observation_date,
                ),
            )
            all_finding_ids.extend(persist_result[0])
            all_statement_created_ids = persist_result[1]
            all_statement_updated_ids = persist_result[2]
            all_shareholding_ids = persist_result[3]
            all_pledge_ids = persist_result[4]
            all_corporate_action_ids = persist_result[5]
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

        red_flag_count = 0
        if validation_result is not None:
            red_flag_count = validation_result.red_flags_valid
        elif analysis_output is not None:
            red_flag_count = len(analysis_output.governance_red_flags)

        return ManagementGovernanceResult(
            status=status,
            run_id=run_id,
            finding_ids=all_finding_ids,
            statement_ids=all_statement_created_ids + all_statement_updated_ids,
            shareholding_snapshot_ids=all_shareholding_ids,
            pledge_snapshot_ids=all_pledge_ids,
            corporate_action_ids=all_corporate_action_ids,
            red_flag_count=red_flag_count,
            total_findings=len(all_finding_ids),
            total_statements_created=len(all_statement_created_ids),
            total_statements_updated=len(all_statement_updated_ids),
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
        config: ManagementGovernanceConfig,
        fn: Callable[[uuid.UUID], Awaitable[_T]],
        *,
        model_name: str = "default",
    ) -> _T:
        step_id = step.id
        step_name = step.step_name
        max_attempts = config.max_llm_attempts

        if token_budget.is_exhausted:
            await self._run_service.skip_step(step_id)
            raise TokenBudgetExhaustedError(
                token_budget.total_tokens,
                token_budget.budget,
            )

        await self._run_service.start_step(step_id)

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            execution = await self._run_service.record_agent_execution(
                run_id,
                step_id,
                AgentExecutionCreate(
                    agent_name=GOVERNANCE_AGENT_NAME,
                    attempt_number=attempt,
                    model_provider="llm",
                    model_name=model_name,
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
                    attempt,
                    max_attempts,
                    step_name,
                    exc,
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
                await self._run_service.fail_step(
                    step_id,
                    "Token budget exhausted",
                )
                raise

        await self._run_service.fail_step(step_id, str(last_error))
        raise StepFailedError(step_name, str(last_error))

    # -----------------------------------------------------------------------
    # Step implementations
    # -----------------------------------------------------------------------

    async def _step_company_context_load(
        self,
        request: ManagementGovernanceResearchRequest,
    ) -> LoadGovernanceContextOutput:
        return await self._tools.load_company_context(
            LoadGovernanceContextInput(
                company_id=request.company_id,
                observation_date=request.observation_date,
            ),
        )

    async def _step_governance_source_discovery(
        self,
        context: LoadGovernanceContextOutput,
        config: ManagementGovernanceConfig,
        observation_date: date,
    ) -> DiscoverGovernanceSourcesOutput:
        return await self._tools.discover_governance_sources(
            DiscoverGovernanceSourcesInput(
                company_id=context.company_id,
                company_name=context.company_name,
                nse_symbol=context.nse_symbol,
                bse_code=context.bse_code,
                observation_date=observation_date,
                filing_types=config.filing_types,
                shareholding_quarters=config.shareholding_quarters,
                corporate_action_years=config.corporate_action_years,
            ),
        )

    async def _step_document_retrieval(
        self,
        company_id: uuid.UUID,
        filing_candidates: list[SourceCandidate],
        config: ManagementGovernanceConfig,
        run_id: uuid.UUID,
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
                        company_id,
                        candidate,
                        doc.content_hash,
                    )
                    document_ids[candidate.source_id] = doc_id
                    await self._run_service.record_source_access(
                        run_id,
                        doc_id,
                        "retrieved",
                    )
                except ProviderError:
                    logger.warning(
                        "Failed to retrieve document %s",
                        candidate.source_id,
                    )

        tasks = [_retrieve(c) for c in filing_candidates]
        await asyncio.gather(*tasks)
        return documents, document_ids

    async def _step_evidence_extraction(
        self,
        context: LoadGovernanceContextOutput,
        documents: dict[str, RetrieveDocumentOutput],
        document_ids: dict[str, uuid.UUID],
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: ManagementGovernanceConfig,
        observation_date: date,
    ) -> tuple[list[ExtractedEvidence], list[uuid.UUID]]:
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []

        for source_id, doc in documents.items():
            if token_budget.is_exhausted:
                raise TokenBudgetExhaustedError(
                    token_budget.total_tokens,
                    token_budget.budget,
                )

            prompt = governance_evidence_extraction_prompt(
                company_name=context.company_name,
                industry_name=context.industry_name or "Unknown",
                document_content=doc.content,
                source_id=source_id,
                document_title=doc.filing_id,
                observation_date=observation_date,
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

            extracted = _parse_evidence_extraction_response(response)
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

    async def _step_governance_analysis(
        self,
        context: LoadGovernanceContextOutput,
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        discovery: DiscoverGovernanceSourcesOutput,
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: ManagementGovernanceConfig,
        observation_date: date,
    ) -> tuple[GovernanceAnalysisOutput, list[uuid.UUID]]:
        evidence_summaries = "\n\n".join(
            f"[{i}] [{ev.evidence_type}] {ev.claim} (confidence: {ev.confidence})" for i, ev in enumerate(all_evidence)
        )

        existing_statements_text = (
            "\n\n".join(
                f"- ID: {ms.id}\n  Statement: {ms.statement}\n"
                f"  Category: {ms.category}\n  Status: {ms.status}\n"
                f"  Date: {ms.statement_date}\n"
                f"  Expected: {ms.expected_outcome or 'N/A'}"
                for ms in context.existing_statements
            )
            if context.existing_statements
            else "No existing management statements."
        )

        shareholding_text = (
            "\n".join(
                f"- {s.quarter or s.as_of_date}: Promoter={s.promoter_holding_pct}%, "
                f"FII={s.fii_holding_pct}%, DII={s.dii_holding_pct}%, "
                f"Public={s.public_holding_pct}%"
                f"{f', Pledged={s.pledged_percentage}%' if s.pledged_percentage else ''}"
                for s in discovery.shareholding_data
            )
            if discovery.shareholding_data
            else "No shareholding data available."
        )

        corporate_actions_text = (
            "\n".join(
                f"- {a.action_type.value}: {a.details or 'N/A'}"
                f" (ex-date: {a.ex_date or 'N/A'}, value: {a.value or 'N/A'})"
                for a in discovery.corporate_actions
            )
            if discovery.corporate_actions
            else "No corporate actions data available."
        )

        prompt = governance_analysis_prompt(
            company_name=context.company_name,
            industry_name=context.industry_name or "Unknown",
            evidence_summaries=evidence_summaries,
            existing_statements=existing_statements_text,
            shareholding_context=shareholding_text,
            corporate_actions_context=corporate_actions_text,
            observation_date=observation_date,
        )

        schema = GovernanceAnalysisOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.analysis_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        output = _parse_governance_analysis_response(response)

        all_domain_findings: list[GeneratedFinding] = []
        all_domain_findings.extend(output.capital_allocation_findings)
        all_domain_findings.extend(output.related_party_findings)
        all_domain_findings.extend(output.auditor_findings)
        all_domain_findings.extend(output.compensation_findings)
        all_domain_findings.extend(output.subsidiary_findings)
        all_domain_findings.extend(output.dilution_findings)
        all_domain_findings.extend(output.general_findings)

        finding_items = [
            FindingItem(
                agent_name=GOVERNANCE_AGENT_NAME,
                finding_type=gf.finding_type,
                category=gf.category,
                content=gf.content,
                confidence=gf.confidence,
                observation_date=observation_date,
                source_publication_date=gf.source_publication_date,
            )
            for gf in all_domain_findings
        ]
        finding_ids: list[uuid.UUID] = []
        if finding_items:
            persist_result = await self._tools.persist_findings(
                PersistFindingsInput(
                    run_id=run_id,
                    execution_id=execution_id,
                    findings=finding_items,
                ),
            )
            finding_ids = persist_result.finding_ids

        return output, finding_ids

    async def _step_governance_validation(
        self,
        analysis_output: GovernanceAnalysisOutput,
        shareholding_findings: list[GeneratedFinding],
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        existing_statements: list[ManagementStatementSummary],
        observation_date: date,
        shareholding_snapshots: list[ShareholdingSnapshot] | None = None,
    ) -> GovernanceValidationResult:
        return _validate_governance_output(
            analysis_output,
            shareholding_findings,
            all_evidence,
            all_evidence_ids,
            existing_statements,
            observation_date,
            shareholding_snapshots=shareholding_snapshots or [],
        )

    async def _step_persistence(
        self,
        context: LoadGovernanceContextOutput,
        analysis_output: GovernanceAnalysisOutput,
        shareholding_findings: list[GeneratedFinding],
        validation_result: GovernanceValidationResult,
        all_evidence_ids: list[uuid.UUID],
        discovery: DiscoverGovernanceSourcesOutput,
        run_id: uuid.UUID,
        observation_date: date,
    ) -> tuple[
        list[uuid.UUID],
        list[uuid.UUID],
        list[uuid.UUID],
        list[uuid.UUID],
        list[uuid.UUID],
        list[uuid.UUID],
    ]:
        # Persist Step 5a findings (shareholding + pledge)
        sh_finding_ids: list[uuid.UUID] = []
        if shareholding_findings:
            sh_finding_items = [
                FindingItem(
                    agent_name=GOVERNANCE_AGENT_NAME,
                    finding_type=gf.finding_type,
                    category=gf.category,
                    content=gf.content,
                    confidence=gf.confidence,
                    observation_date=observation_date,
                    source_publication_date=gf.source_publication_date,
                )
                for gf in shareholding_findings
            ]
            sh_persist = await self._tools.persist_findings(
                PersistFindingsInput(
                    run_id=run_id,
                    execution_id=uuid.uuid4(),
                    findings=sh_finding_items,
                ),
            )
            sh_finding_ids = sh_persist.finding_ids

        # Filter rejected items using validation result indices
        valid_updates = [
            u
            for i, u in enumerate(analysis_output.statement_updates)
            if i not in validation_result.rejected_statement_update_indices
        ]
        valid_new_stmts = [
            s
            for i, s in enumerate(analysis_output.new_management_statements)
            if i not in validation_result.rejected_new_statement_indices
        ]

        # Persist management statements (new + updates) — rejected items excluded
        stmt_result = await self._tools.persist_management_statements(
            PersistStatementsInput(
                company_id=context.company_id,
                research_run_id=run_id,
                new_statements=valid_new_stmts,
                statement_updates=valid_updates,
                evidence_ids=all_evidence_ids,
            ),
        )

        # Persist shareholding snapshots
        sh_snapshot_ids: list[uuid.UUID] = []
        if discovery.shareholding_data:
            sh_snap_result = await self._tools.persist_shareholding(
                PersistShareholdingInput(
                    company_id=context.company_id,
                    research_run_id=run_id,
                    snapshots=discovery.shareholding_data,
                ),
            )
            sh_snapshot_ids = sh_snap_result.persisted_ids

        # Persist governance data (pledges + corporate actions)
        pledge_snapshots = [s for s in discovery.shareholding_data if s.pledged_percentage is not None]
        gov_data_result = await self._tools.persist_governance_data(
            PersistGovernanceDataInput(
                company_id=context.company_id,
                research_run_id=run_id,
                pledge_snapshots=pledge_snapshots,
                corporate_actions=discovery.corporate_actions,
            ),
        )

        return (
            sh_finding_ids,
            stmt_result.created_ids,
            stmt_result.updated_ids,
            sh_snapshot_ids,
            gov_data_result.pledge_ids,
            gov_data_result.corporate_action_ids,
        )


# ---------------------------------------------------------------------------
# LLM response parsing helpers
# ---------------------------------------------------------------------------


def _parse_evidence_extraction_response(
    response: LLMResponse,
) -> EvidenceExtractionOutput:
    try:
        data = json.loads(response.content)
        return EvidenceExtractionOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "evidence_extraction",
            str(exc),
        ) from exc


def _parse_governance_analysis_response(
    response: LLMResponse,
) -> GovernanceAnalysisOutput:
    try:
        data = json.loads(response.content)
        return GovernanceAnalysisOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "governance_analysis",
            str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Step 5a: Deterministic shareholding & pledge finding generation
# ---------------------------------------------------------------------------


def _compute_trend_direction(start: Decimal, end: Decimal) -> str:
    diff = end - start
    if diff > Decimal("0.5"):
        return "increasing"
    if diff < Decimal("-0.5"):
        return "decreasing"
    return "stable"


def _generate_shareholding_findings(
    snapshots: list[ShareholdingSnapshot],
    observation_date: date,
) -> list[GeneratedFinding]:
    findings: list[GeneratedFinding] = []
    if not snapshots:
        return findings

    sorted_snaps = sorted(snapshots, key=lambda s: s.as_of_date)

    for snap in sorted_snaps:
        label = snap.quarter or str(snap.as_of_date)
        for category_name, pct in [
            ("Promoter", snap.promoter_holding_pct),
            ("FII", snap.fii_holding_pct),
            ("DII", snap.dii_holding_pct),
            ("Public", snap.public_holding_pct),
        ]:
            findings.append(
                GeneratedFinding(
                    finding_type=FindingType.FACT,
                    category="shareholding",
                    content=f"{category_name} holding was {pct}% as of {label}",
                    confidence=ConfidenceLevel.HIGH,
                    source_publication_date=snap.as_of_date,
                ),
            )

    if len(sorted_snaps) >= 2:
        first = sorted_snaps[0]
        last = sorted_snaps[-1]
        n_quarters = len(sorted_snaps)
        for category_name, start_pct, end_pct in [
            ("Promoter", first.promoter_holding_pct, last.promoter_holding_pct),
            ("FII", first.fii_holding_pct, last.fii_holding_pct),
            ("DII", first.dii_holding_pct, last.dii_holding_pct),
            ("Public", first.public_holding_pct, last.public_holding_pct),
        ]:
            direction = _compute_trend_direction(start_pct, end_pct)
            findings.append(
                GeneratedFinding(
                    finding_type=FindingType.CALCULATION,
                    category="shareholding",
                    content=(
                        f"{category_name} holding trend: {direction} "
                        f"from {start_pct}% to {end_pct}% "
                        f"over {n_quarters} quarters"
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    source_publication_date=last.as_of_date,
                ),
            )

    return findings


def _generate_pledge_findings(
    snapshots: list[ShareholdingSnapshot],
    observation_date: date,
) -> list[GeneratedFinding]:
    findings: list[GeneratedFinding] = []
    pledge_snaps = [s for s in snapshots if s.pledged_percentage is not None]
    if not pledge_snaps:
        return findings

    sorted_snaps = sorted(pledge_snaps, key=lambda s: s.as_of_date)

    for snap in sorted_snaps:
        label = snap.quarter or str(snap.as_of_date)
        findings.append(
            GeneratedFinding(
                finding_type=FindingType.FACT,
                category="promoter_pledge",
                content=f"Promoter pledge was {snap.pledged_percentage}% as of {label}",
                confidence=ConfidenceLevel.HIGH,
                source_publication_date=snap.as_of_date,
            ),
        )

    if len(sorted_snaps) >= 2:
        first = sorted_snaps[0]
        last = sorted_snaps[-1]
        n_quarters = len(sorted_snaps)
        start_pct = first.pledged_percentage or Decimal("0")
        end_pct = last.pledged_percentage or Decimal("0")
        direction = _compute_trend_direction(start_pct, end_pct)
        findings.append(
            GeneratedFinding(
                finding_type=FindingType.CALCULATION,
                category="promoter_pledge",
                content=(
                    f"Promoter pledge trend: {direction} from {start_pct}% to {end_pct}% over {n_quarters} quarters"
                ),
                confidence=ConfidenceLevel.HIGH,
                source_publication_date=last.as_of_date,
            ),
        )

    return findings


def _generate_data_gap_findings(
    data_gaps: list[str],
    observation_date: date,
) -> list[GeneratedFinding]:
    findings: list[GeneratedFinding] = []
    for gap in data_gaps:
        findings.append(
            GeneratedFinding(
                finding_type=FindingType.UNCERTAINTY,
                category="data_gap",
                content=gap,
                confidence=ConfidenceLevel.LOW,
                source_publication_date=observation_date,
            ),
        )
    return findings


# ---------------------------------------------------------------------------
# Step 6: Governance validation
# ---------------------------------------------------------------------------


def _validate_governance_output(
    analysis_output: GovernanceAnalysisOutput,
    shareholding_findings: list[GeneratedFinding],
    all_evidence: list[ExtractedEvidence],
    all_evidence_ids: list[uuid.UUID],
    existing_statements: list[ManagementStatementSummary],
    observation_date: date,
    *,
    shareholding_snapshots: list[ShareholdingSnapshot] | None = None,
) -> GovernanceValidationResult:
    issues: list[GovernanceValidationIssue] = []
    existing_by_id: dict[str, ManagementStatementSummary] = {str(ms.id): ms for ms in existing_statements}

    # -- 1. ManagementStatement transition validation -------------------------
    stmt_updates_valid = 0
    stmt_updates_rejected = 0
    rejected_stmt_update_idxs: set[int] = set()
    for upd_idx, update in enumerate(analysis_output.statement_updates):
        rejected = False
        sid = update.statement_id

        if sid not in existing_by_id:
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="invalid_statement_id",
                    message=f"Statement ID {sid} not found in existing statements",
                    action="rejected",
                )
            )
            rejected = True
        else:
            existing_ms = existing_by_id[sid]
            current_status = existing_ms.status.value

            if current_status in _TERMINAL_STATUSES:
                issues.append(
                    GovernanceValidationIssue(
                        domain="management_statement",
                        issue_type="terminal_re_transition",
                        message=(
                            f"Statement {sid} is in terminal status {current_status}; no further transitions allowed"
                        ),
                        action="rejected",
                    )
                )
                rejected = True

        proposed = update.proposed_status.upper()
        if proposed in _TERMINAL_STATUSES:
            if update.outcome_evidence_index is None:
                issues.append(
                    GovernanceValidationIssue(
                        domain="management_statement",
                        issue_type="missing_outcome_evidence",
                        message=(f"Transition to {proposed} requires outcome_evidence_index for statement {sid}"),
                        action="rejected",
                    )
                )
                rejected = True
            elif update.outcome_evidence_index >= len(all_evidence):
                issues.append(
                    GovernanceValidationIssue(
                        domain="management_statement",
                        issue_type="invalid_evidence_index",
                        message=(
                            f"outcome_evidence_index {update.outcome_evidence_index} out of range for statement {sid}"
                        ),
                        action="rejected",
                    )
                )
                rejected = True

        if proposed == "UNKNOWN" and not update.resolution_detail:
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="missing_resolution_detail",
                    message=f"UNKNOWN transition requires resolution_detail for statement {sid}",
                    action="rejected",
                )
            )
            rejected = True

        if update.resolution_detail == "NOT_DUE" and sid in existing_by_id:
            existing_ms_status = existing_by_id[sid].status.value
            if proposed != existing_ms_status:
                issues.append(
                    GovernanceValidationIssue(
                        domain="management_statement",
                        issue_type="not_due_with_transition",
                        message=(
                            f"NOT_DUE update for statement {sid} must not propose "
                            f"a status transition (proposed: {proposed})"
                        ),
                        action="rejected",
                    )
                )
                rejected = True

        # Architecture §24 Step 6 rule 1.8: REVISED updates require a
        # corresponding NewManagementStatement.  The contract has no
        # linking field (e.g. replaces_statement_id), so 1:1 matching
        # cannot be verified — only the existence of at least one new
        # statement is checked.  See architecture §10 handling rule 4.
        if update.resolution_detail == "REVISED" and not analysis_output.new_management_statements:
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="revised_without_replacement",
                    message=(
                        f"REVISED update for statement {sid} requires a "
                        f"corresponding NewManagementStatement for the "
                        f"revised guidance, but none exist"
                    ),
                    action="rejected",
                )
            )
            rejected = True

        if rejected:
            stmt_updates_rejected += 1
            rejected_stmt_update_idxs.add(upd_idx)
        else:
            stmt_updates_valid += 1

    # -- 2. New ManagementStatement validation --------------------------------
    new_stmts_valid = 0
    new_stmts_rejected = 0
    rejected_new_stmt_idxs: set[int] = set()
    for ns_idx, new_stmt in enumerate(analysis_output.new_management_statements):
        rejected = False

        if new_stmt.category.upper() not in _VALID_MANAGEMENT_STATEMENT_CATEGORIES:
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="invalid_category",
                    message=f"Invalid category: {new_stmt.category}",
                    action="rejected",
                )
            )
            rejected = True

        if new_stmt.evidence_index >= len(all_evidence):
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="invalid_evidence_index",
                    message=f"evidence_index {new_stmt.evidence_index} out of range",
                    action="rejected",
                )
            )
            rejected = True

        if not new_stmt.statement or not new_stmt.statement.strip():
            issues.append(
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="empty_statement",
                    message="New statement has empty text",
                    action="rejected",
                )
            )
            rejected = True

        if rejected:
            new_stmts_rejected += 1
            rejected_new_stmt_idxs.add(ns_idx)
        else:
            new_stmts_valid += 1

    # -- 3 & 4. Finding type and category validation --------------------------
    all_analysis_findings: list[GeneratedFinding] = []
    all_analysis_findings.extend(analysis_output.capital_allocation_findings)
    all_analysis_findings.extend(analysis_output.related_party_findings)
    all_analysis_findings.extend(analysis_output.auditor_findings)
    all_analysis_findings.extend(analysis_output.compensation_findings)
    all_analysis_findings.extend(analysis_output.subsidiary_findings)
    all_analysis_findings.extend(analysis_output.dilution_findings)
    all_analysis_findings.extend(analysis_output.general_findings)
    all_analysis_findings.extend(shareholding_findings)

    total_findings = len(all_analysis_findings)
    findings_rejected = 0

    for i, f in enumerate(all_analysis_findings):
        if f.category not in GOVERNANCE_FINDING_CATEGORIES:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="invalid_category",
                    message=f"Finding {i} has invalid category: {f.category}",
                    action="rejected",
                )
            )
            findings_rejected += 1
            continue

        if f.finding_type == FindingType.FACT and not f.evidence_indices:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="fact_without_evidence",
                    message=f"FACT finding {i} has no evidence indices",
                    action="warning",
                )
            )

        if f.finding_type == FindingType.MANAGEMENT_CLAIM and not f.evidence_indices:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="management_claim_without_citation",
                    message=f"MANAGEMENT_CLAIM finding {i} has no source citation (evidence_indices)",
                    action="warning",
                )
            )

        if f.finding_type == FindingType.CALCULATION and not f.evidence_indices:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="calculation_without_evidence",
                    message=f"CALCULATION finding {i} has no evidence indices",
                    action="warning",
                )
            )

        if (
            f.finding_type == FindingType.AI_INFERENCE
            and f.category == "governance_red_flag"
            and not f.evidence_indices
        ):
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="ai_inference_red_flag_without_evidence",
                    message=f"AI_INFERENCE finding {i} for governance_red_flag requires evidence indices",
                    action="rejected",
                )
            )
            findings_rejected += 1
            continue

        if f.finding_type == FindingType.ANALYST_OPINION:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="analyst_opinion_not_allowed",
                    message=f"Finding {i} uses ANALYST_OPINION which is not applicable to this agent",
                    action="rejected",
                )
            )
            findings_rejected += 1
            continue

        if f.source_publication_date and f.source_publication_date > observation_date:
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="temporal_violation",
                    message=(
                        f"Finding {i} has source_publication_date "
                        f"{f.source_publication_date} after "
                        f"observation_date {observation_date}"
                    ),
                    action="warning",
                )
            )

        if not f.content or not f.content.strip():
            issues.append(
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="empty_content",
                    message=f"Finding {i} has empty content",
                    action="rejected",
                )
            )
            findings_rejected += 1

    # -- 5. Red flag validation -----------------------------------------------
    red_flags_valid = 0
    red_flags_rejected = 0
    rejected_red_flag_idxs: set[int] = set()
    for rf_idx, rf in enumerate(analysis_output.governance_red_flags):
        rejected = False

        if rf.category not in GOVERNANCE_RED_FLAG_CATEGORIES:
            issues.append(
                GovernanceValidationIssue(
                    domain="red_flag",
                    issue_type="invalid_category",
                    message=f"Red flag has invalid category: {rf.category}",
                    action="rejected",
                )
            )
            rejected = True

        if rf.severity.upper() not in _VALID_RED_FLAG_SEVERITIES:
            issues.append(
                GovernanceValidationIssue(
                    domain="red_flag",
                    issue_type="invalid_severity",
                    message=f"Red flag has invalid severity: {rf.severity}",
                    action="rejected",
                )
            )
            rejected = True

        if not rf.evidence_indices:
            issues.append(
                GovernanceValidationIssue(
                    domain="red_flag",
                    issue_type="missing_evidence",
                    message=f"Red flag '{rf.category}' has no evidence indices",
                    action="rejected",
                )
            )
            rejected = True

        if not rf.justification or not rf.justification.strip():
            issues.append(
                GovernanceValidationIssue(
                    domain="red_flag",
                    issue_type="empty_justification",
                    message=f"Red flag '{rf.category}' has empty justification",
                    action="rejected",
                )
            )
            rejected = True

        for idx in rf.evidence_indices:
            if idx < 0 or idx >= len(all_evidence):
                issues.append(
                    GovernanceValidationIssue(
                        domain="red_flag",
                        issue_type="invalid_evidence_index",
                        message=f"Red flag '{rf.category}' references invalid evidence index {idx}",
                        action="rejected",
                    )
                )
                rejected = True
                break

        if rejected:
            red_flags_rejected += 1
            rejected_red_flag_idxs.add(rf_idx)
        else:
            red_flags_valid += 1

    # -- 6. Shareholding consistency ------------------------------------------
    _validate_shareholding_consistency(shareholding_findings, issues)

    # -- 7. Shareholding snapshot validation (SV-02, SV-03, SV-04) -----------
    for snap in shareholding_snapshots or []:
        pcts = [
            snap.promoter_holding_pct,
            snap.fii_holding_pct,
            snap.dii_holding_pct,
            snap.public_holding_pct,
        ]
        if any(p < 0 for p in pcts):
            issues.append(
                GovernanceValidationIssue(
                    domain="shareholding",
                    issue_type="negative_percentage",
                    message=(f"Shareholding snapshot {snap.quarter} has negative percentage"),
                    action="rejected",
                )
            )
        if snap.pledged_percentage is not None and snap.pledged_percentage > Decimal("100"):
            issues.append(
                GovernanceValidationIssue(
                    domain="shareholding",
                    issue_type="pledge_exceeds_100",
                    message=(f"Shareholding snapshot {snap.quarter} has pledge {snap.pledged_percentage}% > 100%"),
                    action="rejected",
                )
            )
        if snap.as_of_date > observation_date:
            issues.append(
                GovernanceValidationIssue(
                    domain="shareholding",
                    issue_type="future_snapshot",
                    message=(
                        f"Shareholding snapshot {snap.quarter} "
                        f"as_of_date {snap.as_of_date} is after "
                        f"observation_date {observation_date}"
                    ),
                    action="rejected",
                )
            )

    valid_count = total_findings - findings_rejected

    return GovernanceValidationResult(
        total_findings=total_findings,
        valid_count=valid_count,
        rejected_count=findings_rejected,
        statement_updates_valid=stmt_updates_valid,
        statement_updates_rejected=stmt_updates_rejected,
        new_statements_valid=new_stmts_valid,
        new_statements_rejected=new_stmts_rejected,
        red_flags_valid=red_flags_valid,
        red_flags_rejected=red_flags_rejected,
        issues=issues,
        rejected_statement_update_indices=frozenset(rejected_stmt_update_idxs),
        rejected_new_statement_indices=frozenset(rejected_new_stmt_idxs),
        rejected_red_flag_indices=frozenset(rejected_red_flag_idxs),
    )


def _validate_shareholding_consistency(
    shareholding_findings: list[GeneratedFinding],
    issues: list[GovernanceValidationIssue],
) -> None:
    """Check that shareholding FACT findings for any given quarter sum ~100%."""
    quarter_totals: dict[str, Decimal] = {}
    for f in shareholding_findings:
        if f.finding_type != FindingType.FACT or f.category != "shareholding":
            continue
        content = f.content
        # Extract quarter label and percentage from content pattern:
        # "{Category} holding was {pct}% as of {label}"
        if "holding was" not in content or "% as of" not in content:
            continue
        try:
            pct_str = content.split("holding was ")[1].split("% as of")[0]
            label = content.split("% as of ")[1]
            pct = Decimal(pct_str)
            quarter_totals[label] = quarter_totals.get(label, Decimal("0")) + pct
        except (IndexError, ValueError):
            continue

    for label, total in quarter_totals.items():
        diff = abs(total - Decimal("100"))
        if diff > Decimal("0.5"):
            issues.append(
                GovernanceValidationIssue(
                    domain="shareholding",
                    issue_type="sum_mismatch",
                    message=(f"Shareholding percentages for {label} sum to {total}% (expected ~100%, tolerance 0.5%)"),
                    action="warning",
                )
            )
