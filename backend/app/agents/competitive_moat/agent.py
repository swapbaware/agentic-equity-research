"""Competitive Moat Agent — sequential orchestration layer (Phase 10.4).

Orchestrates a seven-step workflow to assess competitive advantages (moats)
for Indian listed companies.  Follows the Phase 8/9 agent pattern:
frozen result model, constructor with DI, execute() method,
_run_step_deterministic() / _run_step_llm() helpers, exception-based
flow control.

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
from app.agents.competitive_moat.prompts import (
    moat_analysis_prompt,
    moat_durability_challenge_prompt,
    moat_evidence_extraction_prompt,
)
from app.agents.competitive_moat.tools import CompetitiveMoatTools
from app.agents.contracts import (
    MOAT_AGENT_NAME,
    MOAT_FINDING_CATEGORIES,
    MOAT_RESEARCH_STEPS,
    DiscoverMoatSourcesInput,
    DurabilityChallengeOutput,
    EvidenceExtractionOutput,
    EvidenceItem,
    ExtractedEvidence,
    FindingItem,
    GeneratedFinding,
    GetPeerDataInput,
    LoadContextInput,
    LoadContextOutput,
    MoatAnalysisOutput,
    MoatAssessmentDraft,
    MoatAssessmentItem,
    MoatResearchConfig,
    MoatResearchRequest,
    MoatResearchResult,
    MoatValidationIssue,
    MoatValidationResult,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistMoatAssessmentsInput,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
    TokenBudget,
)
from app.models.enums import (
    ConfidenceLevel,
    MoatStrength,
    MoatType,
)
from app.models.research import ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateFilingsProvider,
    LLMProvider,
    NewsProvider,
    SearchProvider,
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

_ALL_MOAT_TYPES: frozenset[str] = frozenset(t.value for t in MoatType)


class CompetitiveMoatAgent:
    """Orchestrates a seven-step competitive moat research workflow."""

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        search: SearchProvider,
        news: NewsProvider,
        corporate_filings: CorporateFilingsProvider,
        llm: LLMProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._llm = llm

        self._tools = CompetitiveMoatTools(
            session=session,
            run_service=run_service,
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

    async def execute(
        self,
        request: MoatResearchRequest,
    ) -> MoatResearchResult:
        config = request.configuration or MoatResearchConfig()
        token_budget = TokenBudget(
            budget=config.token_budget,
            warning_threshold=config.token_warning_threshold,
        )

        run = await self._run_service.initiate_run(
            ResearchRunCreate(
                target_type="company",
                company_id=request.company_id,
                initiated_by=request.initiated_by,
                run_type="competitive_moat",
                trigger_type="manual",
                observation_date=request.observation_date,
                configuration={
                    "token_budget": config.token_budget,
                    "source_limit": config.source_limit,
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
            for sd in MOAT_RESEARCH_STEPS
        ]
        db_steps = await self._run_service.create_steps(run_id, step_defs)
        step_map = {s.step_name: s for s in db_steps}

        await self._run_service.enqueue_run(run_id)
        await self._run_service.start_run(run_id)

        context: LoadContextOutput | None = None
        peer_summary: str | None = None
        sources: list[SourceCandidate] = []
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []
        all_finding_ids: list[uuid.UUID] = []
        all_assessment_ids: list[uuid.UUID] = []
        draft_assessments: list[MoatAssessmentDraft] = []
        analysis_findings: list[GeneratedFinding] = []
        validated_assessments: list[MoatAssessmentDraft] = []
        steps_completed = 0
        error_msg: str | None = None

        try:
            # -- Step 1: company_context_load ------------------------------------
            context_result = await self._run_step_deterministic(
                step_map["company_context_load"],
                self._step_company_context_load(request),
            )
            context = context_result[0]
            peer_summary = context_result[1]
            steps_completed += 1

            # -- Step 2: moat_source_discovery -----------------------------------
            sources = await self._run_step_deterministic(
                step_map["moat_source_discovery"],
                self._step_moat_source_discovery(
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
                    sources,
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

            # -- Step 5: moat_analysis (LLM) ------------------------------------
            analysis_result = await self._run_step_llm(
                step_map["moat_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_moat_analysis(
                    context,
                    all_evidence,
                    all_evidence_ids,
                    peer_summary,
                    run_id,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.analysis_model or "default",
            )
            draft_assessments = analysis_result[0]
            analysis_findings = analysis_result[1]
            all_finding_ids.extend(analysis_result[2])
            steps_completed += 1

            # -- Step 6: moat_validation (deterministic) -------------------------
            validation_output = await self._run_step_deterministic(
                step_map["moat_validation"],
                self._step_moat_validation(
                    draft_assessments,
                    analysis_findings,
                    all_evidence,
                    all_evidence_ids,
                    request.observation_date,
                    context.company_id,
                    run_id,
                ),
            )
            validated_assessments = validation_output[0]
            # validation_output[1] is MoatValidationResult — unused here
            all_assessment_ids.extend(validation_output[2])
            steps_completed += 1

            # -- Step 7: durability_challenge (LLM) ------------------------------
            durability_finding_ids = await self._run_step_llm(
                step_map["durability_challenge"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_durability_challenge(
                    context.company_name,
                    validated_assessments,
                    all_evidence,
                    run_id,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.analysis_model or "default",
            )
            all_finding_ids.extend(durability_finding_ids)
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

        return MoatResearchResult(
            status=status,
            run_id=run_id,
            finding_ids=all_finding_ids,
            assessment_ids=all_assessment_ids,
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
        config: MoatResearchConfig,
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
                    agent_name=MOAT_AGENT_NAME,
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
        request: MoatResearchRequest,
    ) -> tuple[LoadContextOutput, str | None]:
        context = await self._tools.load_company_context(
            LoadContextInput(
                company_id=request.company_id,
                industry_id=None,
                observation_date=request.observation_date,
            ),
        )

        peer_summary: str | None = None
        if context.industry_id is not None:
            peer_output = await self._tools.get_peer_data(
                GetPeerDataInput(
                    company_id=context.company_id,
                    industry_id=context.industry_id,
                ),
            )
            if peer_output.peers:
                peer_summary = "\n".join(
                    f"- {p.name} (NSE: {p.nse_symbol}, Market Cap: {p.market_cap})" for p in peer_output.peers
                )

        return context, peer_summary

    async def _step_moat_source_discovery(
        self,
        context: LoadContextOutput,
        config: MoatResearchConfig,
        observation_date: date,
    ) -> list[SourceCandidate]:
        result = await self._tools.discover_moat_sources(
            DiscoverMoatSourcesInput(
                company_name=context.company_name,
                nse_symbol=context.nse_symbol,
                industry_name=context.industry_name,
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
        config: MoatResearchConfig,
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

        tasks = [_retrieve(c) for c in sources]
        await asyncio.gather(*tasks)
        return documents, document_ids

    async def _step_evidence_extraction(
        self,
        context: LoadContextOutput,
        documents: dict[str, RetrieveDocumentOutput],
        document_ids: dict[str, uuid.UUID],
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: MoatResearchConfig,
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

            prompt = moat_evidence_extraction_prompt(
                company_name=context.company_name,
                industry_name=context.industry_name,
                document_content=doc.content,
                source_id=source_id,
                document_title=doc.filing_id,
                observation_date=str(observation_date),
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

    async def _step_moat_analysis(
        self,
        context: LoadContextOutput,
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        peer_summary: str | None,
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: MoatResearchConfig,
        observation_date: date,
    ) -> tuple[list[MoatAssessmentDraft], list[GeneratedFinding], list[uuid.UUID]]:
        evidence_summaries = "\n\n".join(
            f"[{i}] [{ev.evidence_type}] {ev.claim} (confidence: {ev.confidence})" for i, ev in enumerate(all_evidence)
        )

        company_context = (
            "\n".join(f"[{f.finding_type}] ({f.category}) {f.content}" for f in context.company_findings)
            if context.company_findings
            else None
        )
        industry_context = (
            "\n".join(f"[{f.finding_type}] ({f.category}) {f.content}" for f in context.industry_findings)
            if context.industry_findings
            else None
        )

        prompt = moat_analysis_prompt(
            company_name=context.company_name,
            industry_name=context.industry_name,
            evidence_summaries=evidence_summaries,
            company_context=company_context,
            industry_context=industry_context,
            peer_summary=peer_summary,
        )

        schema = MoatAnalysisOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.analysis_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        output = _parse_moat_analysis_response(response)

        finding_items = [
            FindingItem(
                agent_name=MOAT_AGENT_NAME,
                finding_type=gf.finding_type,
                category=gf.category,
                content=gf.content,
                confidence=gf.confidence,
                observation_date=observation_date,
                source_publication_date=gf.source_publication_date,
            )
            for gf in output.findings
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

        return output.assessments, output.findings, finding_ids

    async def _step_moat_validation(
        self,
        draft_assessments: list[MoatAssessmentDraft],
        analysis_findings: list[GeneratedFinding],
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        observation_date: date,
        company_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> tuple[list[MoatAssessmentDraft], MoatValidationResult, list[uuid.UUID]]:
        validated, validation_result = _validate_moat_assessments(
            draft_assessments,
            analysis_findings,
            all_evidence,
            all_evidence_ids,
            observation_date,
        )

        assessment_items = _convert_assessments(validated, all_evidence_ids)

        assessment_ids: list[uuid.UUID] = []
        if assessment_items:
            persist_result = await self._tools.persist_moat_assessments(
                PersistMoatAssessmentsInput(
                    company_id=company_id,
                    research_run_id=run_id,
                    assessments=assessment_items,
                ),
            )
            assessment_ids = persist_result.assessment_ids

        return validated, validation_result, assessment_ids

    async def _step_durability_challenge(
        self,
        company_name: str,
        validated_assessments: list[MoatAssessmentDraft],
        all_evidence: list[ExtractedEvidence],
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: MoatResearchConfig,
        observation_date: date,
    ) -> list[uuid.UUID]:
        assessments_summary = "\n\n".join(
            f"[{a.moat_type}] Strength: {a.strength}, "
            f"Durability: {a.durability_years}y, "
            f"Confidence: {a.confidence}\n"
            f"Explanation: {a.explanation}"
            for a in validated_assessments
        )
        evidence_summaries = "\n\n".join(
            f"[{i}] [{ev.evidence_type}] {ev.claim} (confidence: {ev.confidence})" for i, ev in enumerate(all_evidence)
        )

        prompt = moat_durability_challenge_prompt(
            company_name=company_name,
            assessments_summary=assessments_summary,
            evidence_summaries=evidence_summaries,
        )

        schema = DurabilityChallengeOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.analysis_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        output = _parse_durability_challenge_response(response)

        finding_items = [
            FindingItem(
                agent_name=MOAT_AGENT_NAME,
                finding_type=gf.finding_type,
                category=gf.category,
                content=gf.content,
                confidence=gf.confidence,
                observation_date=observation_date,
                source_publication_date=gf.source_publication_date,
            )
            for gf in output.findings
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

        return finding_ids


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


def _parse_moat_analysis_response(
    response: LLMResponse,
) -> MoatAnalysisOutput:
    try:
        data = json.loads(response.content)
        return MoatAnalysisOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "moat_analysis",
            str(exc),
        ) from exc


def _parse_durability_challenge_response(
    response: LLMResponse,
) -> DurabilityChallengeOutput:
    try:
        data = json.loads(response.content)
        return DurabilityChallengeOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "durability_challenge",
            str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_moat_assessments(
    draft_assessments: list[MoatAssessmentDraft],
    analysis_findings: list[GeneratedFinding],
    all_evidence: list[ExtractedEvidence],
    all_evidence_ids: list[uuid.UUID],
    observation_date: date,
) -> tuple[list[MoatAssessmentDraft], MoatValidationResult]:
    """Run 9 deterministic validation checks; downgrade where required."""
    issues: list[MoatValidationIssue] = []
    downgraded_count = 0

    assessment_by_type: dict[str, MoatAssessmentDraft] = {}
    for a in draft_assessments:
        assessment_by_type[a.moat_type] = a

    # 1. coverage_completeness
    covered = set(assessment_by_type.keys())
    missing = _ALL_MOAT_TYPES - covered
    for mt in sorted(missing):
        issues.append(
            MoatValidationIssue(
                moat_type=mt,
                issue_type="missing_moat_type",
                message=f"Moat type {mt} not assessed; defaulting to NONE",
                action="added_as_none",
            ),
        )
        assessment_by_type[mt] = MoatAssessmentDraft(
            moat_type=mt,
            strength="NONE",
            explanation="Not assessed — added by validation.",
            confidence="LOW",
        )

    validated: dict[str, MoatAssessmentDraft] = dict(assessment_by_type)

    # 2. evidence_sufficiency
    _evidence_thresholds: dict[str, int] = {
        "WIDE": 3,
        "MODERATE": 2,
        "NARROW": 1,
    }
    _downgrade_ladder = ("WIDE", "MODERATE", "NARROW", "NONE")
    for mt, a in list(validated.items()):
        if a.strength == "NONE":
            continue
        ev_count = len(a.evidence_indices) if a.evidence_indices else 0
        required = _evidence_thresholds.get(a.strength, 0)
        if ev_count < required:
            new_strength = a.strength
            for target in _downgrade_ladder:
                target_req = _evidence_thresholds.get(target, 0)
                if ev_count >= target_req:
                    new_strength = target
                    break
            if new_strength != a.strength:
                action = f"downgraded_to_{new_strength.lower()}"
                issues.append(
                    MoatValidationIssue(
                        moat_type=mt,
                        issue_type="insufficient_evidence",
                        message=(f"{mt} has strength {a.strength} but only {ev_count} evidence (requires {required})"),
                        action=action,
                    ),
                )
                validated[mt] = MoatAssessmentDraft(
                    moat_type=mt,
                    strength=new_strength,
                    durability_years=a.durability_years if new_strength != "NONE" else None,
                    explanation=a.explanation,
                    threats=a.threats,
                    competitor_comparison=a.competitor_comparison,
                    confidence=a.confidence,
                    evidence_indices=a.evidence_indices,
                    counter_evidence_indices=a.counter_evidence_indices,
                )
                downgraded_count += 1

    # 3. durability_presence
    for mt, a in validated.items():
        if a.strength != "NONE" and a.durability_years is None:
            issues.append(
                MoatValidationIssue(
                    moat_type=mt,
                    issue_type="missing_durability",
                    message=(f"{mt} has strength {a.strength} but no durability estimate"),
                    action="warning",
                ),
            )

    # 4. threat_presence
    for mt, a in validated.items():
        if a.strength in ("MODERATE", "WIDE") and not a.threats:
            issues.append(
                MoatValidationIssue(
                    moat_type=mt,
                    issue_type="missing_threats",
                    message=(f"{mt} has strength {a.strength} but no threats identified"),
                    action="warning",
                ),
            )

    # 5. temporal_consistency
    for i, f in enumerate(analysis_findings):
        if f.source_publication_date and f.source_publication_date > observation_date:
            issues.append(
                MoatValidationIssue(
                    moat_type=f.category,
                    issue_type="temporal_violation",
                    message=(
                        f"Finding {i} has source_publication_date "
                        f"{f.source_publication_date} after "
                        f"observation_date {observation_date}"
                    ),
                    action="warning",
                ),
            )

    # 6. category_validity
    for i, f in enumerate(analysis_findings):
        if f.category not in MOAT_FINDING_CATEGORIES:
            issues.append(
                MoatValidationIssue(
                    moat_type=f.category,
                    issue_type="invalid_category",
                    message=f"Finding {i} has invalid category: {f.category}",
                    action="rejected",
                ),
            )

    # 7. content_non_empty
    for i, f in enumerate(analysis_findings):
        if not f.content or not f.content.strip():
            issues.append(
                MoatValidationIssue(
                    moat_type=f.category,
                    issue_type="empty_content",
                    message=f"Finding {i} has empty content",
                    action="rejected",
                ),
            )

    # 8. fact_evidence_linkage
    for i, f in enumerate(analysis_findings):
        if f.finding_type == "FACT" and not f.evidence_indices:
            issues.append(
                MoatValidationIssue(
                    moat_type=f.category,
                    issue_type="fact_without_evidence",
                    message=f"FACT finding {i} has no evidence indices",
                    action="warning",
                ),
            )

    # 9. strength_confidence_consistency
    for mt, a in list(validated.items()):
        sc_target: str | None = None
        if a.strength == "WIDE" and a.confidence != "HIGH":
            sc_target = "MODERATE"
        elif a.strength == "MODERATE" and a.confidence == "LOW":
            sc_target = "NARROW"
        if sc_target is not None:
            issues.append(
                MoatValidationIssue(
                    moat_type=mt,
                    issue_type="strength_confidence_mismatch",
                    message=(f"{mt} has {a.strength} strength but {a.confidence} confidence"),
                    action=f"downgraded_to_{sc_target.lower()}",
                ),
            )
            validated[mt] = MoatAssessmentDraft(
                moat_type=mt,
                strength=sc_target,
                durability_years=a.durability_years,
                explanation=a.explanation,
                threats=a.threats,
                competitor_comparison=a.competitor_comparison,
                confidence=a.confidence,
                evidence_indices=a.evidence_indices,
                counter_evidence_indices=a.counter_evidence_indices,
            )
            downgraded_count += 1

    validated_list = list(validated.values())
    valid_count = len(validated_list) - downgraded_count

    return validated_list, MoatValidationResult(
        total_assessments=len(validated_list),
        valid_count=valid_count,
        downgraded_count=downgraded_count,
        issues=issues,
    )


def _convert_assessments(
    validated: list[MoatAssessmentDraft],
    all_evidence_ids: list[uuid.UUID],
) -> list[MoatAssessmentItem]:
    """Convert validated MoatAssessmentDraft objects to MoatAssessmentItem."""
    items: list[MoatAssessmentItem] = []
    for a in validated:
        try:
            moat_type = MoatType(a.moat_type)
        except ValueError:
            logger.warning("Skipping unknown moat type: %s", a.moat_type)
            continue
        try:
            strength = MoatStrength(a.strength)
        except ValueError:
            strength = MoatStrength.NONE
        try:
            confidence = ConfidenceLevel(a.confidence)
        except ValueError:
            confidence = ConfidenceLevel.LOW

        evidence_ids: list[uuid.UUID] = []
        if a.evidence_indices:
            for idx in a.evidence_indices:
                if 0 <= idx < len(all_evidence_ids):
                    evidence_ids.append(all_evidence_ids[idx])

        threats: list[dict[str, object]] | None = None
        if a.threats:
            threats = [
                {
                    "description": t.description,
                    "severity": t.severity,
                    "timeframe": t.timeframe,
                    "evidence_basis": t.evidence_basis,
                }
                for t in a.threats
            ]

        competitor_comparison: dict[str, object] | None = None
        if a.competitor_comparison:
            competitor_comparison = dict(a.competitor_comparison)

        items.append(
            MoatAssessmentItem(
                moat_type=moat_type,
                strength=strength,
                durability_years=a.durability_years,
                threats=threats,
                competitor_comparison=competitor_comparison,
                confidence=confidence,
                explanation=a.explanation,
                evidence_ids=evidence_ids,
            ),
        )

    return items
