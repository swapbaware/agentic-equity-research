"""Future Growth & Optionality Agent — sequential orchestration layer (Phase 12.4).

Orchestrates a seven-step workflow to assess future growth drivers and
strategic optionality for Indian listed companies.  Follows the Phase 10.4
competitive moat agent pattern: frozen result model, constructor with DI,
execute() method, _run_step_deterministic() / _run_step_llm() helpers,
exception-based flow control.

Steps:
  1. context_load        (deterministic)
  2. source_discovery     (provider call)
  3. document_retrieval   (provider call)
  4. evidence_extraction  (LLM)
  5. growth_analysis      (LLM)
  6. growth_validation    (deterministic)
  7. growth_challenge     (LLM)
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
    GROWTH_AGENT_NAME,
    GROWTH_AGENT_RUN_TYPE,
    GROWTH_RESEARCH_STEPS,
    INDIA_STRUCTURAL_THEMES,
    DiscoverGrowthSourcesInput,
    EvidenceExtractionOutput,
    EvidenceItem,
    ExtractedEvidence,
    FindingItem,
    FutureGrowthConfig,
    FutureGrowthResearchRequest,
    FutureGrowthResult,
    GrowthAnalysisOutput,
    GrowthChallengeOutput,
    GrowthOpportunityDraft,
    GrowthScoreComponent,
    GrowthValidationIssue,
    GrowthValidationResult,
    LoadGrowthContextInput,
    LoadGrowthContextOutput,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistGrowthOpportunitiesInput,
    PersistGrowthScoresInput,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
    TokenBudget,
)
from app.agents.future_growth.prompts import (
    growth_analysis_prompt,
    growth_challenge_prompt,
    growth_evidence_extraction_prompt,
)
from app.agents.future_growth.tools import FutureGrowthTools
from app.models.enums import (
    FindingType,
    GrowthCategory,
    GrowthMaturity,
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

_ALL_GROWTH_CATEGORIES: frozenset[str] = frozenset(c.value for c in GrowthCategory)
_ALL_GROWTH_MATURITIES: frozenset[str] = frozenset(m.value for m in GrowthMaturity)
_INDIA_THEMES_SET: frozenset[str] = frozenset(INDIA_STRUCTURAL_THEMES)


class FutureGrowthAgent:
    """Orchestrates a seven-step future growth & optionality research workflow."""

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

        self._tools = FutureGrowthTools(
            session=session,
            run_service=run_service,
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

    async def execute(
        self,
        request: FutureGrowthResearchRequest,
    ) -> FutureGrowthResult:
        config = request.configuration or FutureGrowthConfig()
        token_budget = TokenBudget(
            budget=config.token_budget,
            warning_threshold=config.token_warning_threshold,
        )

        run = await self._run_service.initiate_run(
            ResearchRunCreate(
                target_type="company",
                company_id=request.company_id,
                initiated_by=request.initiated_by,
                run_type=GROWTH_AGENT_RUN_TYPE,
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
            for sd in GROWTH_RESEARCH_STEPS
        ]
        db_steps = await self._run_service.create_steps(run_id, step_defs)
        step_map = {s.step_name: s for s in db_steps}

        await self._run_service.enqueue_run(run_id)
        await self._run_service.start_run(run_id)

        context: LoadGrowthContextOutput | None = None
        sources: list[SourceCandidate] = []
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        all_evidence: list[ExtractedEvidence] = []
        all_evidence_ids: list[uuid.UUID] = []
        all_finding_ids: list[uuid.UUID] = []
        all_opportunity_ids: list[uuid.UUID] = []
        draft_opportunities: list[GrowthOpportunityDraft] = []
        gq_scores: list[GrowthScoreComponent] = []
        fo_scores: list[GrowthScoreComponent] = []
        growth_quality_score: int | None = None
        future_optionality_score: int | None = None
        validation_result: GrowthValidationResult | None = None
        steps_completed = 0
        error_msg: str | None = None

        try:
            # -- Step 1: context_load -----------------------------------------------
            context = await self._run_step_deterministic(
                step_map["context_load"],
                self._step_context_load(request, run_id),
            )
            steps_completed += 1

            # -- Step 2: source_discovery -------------------------------------------
            sources = await self._run_step_deterministic(
                step_map["source_discovery"],
                self._step_source_discovery(
                    context,
                    config,
                    request.observation_date,
                ),
            )
            steps_completed += 1

            # -- Step 3: document_retrieval -----------------------------------------
            doc_result = await self._run_step_deterministic(
                step_map["document_retrieval"],
                self._step_document_retrieval(
                    request.company_id,
                    sources,
                    config,
                    run_id,
                ),
            )
            documents = doc_result[0]
            document_ids = doc_result[1]
            steps_completed += 1

            # -- Step 4: evidence_extraction (LLM) ----------------------------------
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

            # -- Step 5: growth_analysis (LLM) --------------------------------------
            analysis_result = await self._run_step_llm(
                step_map["growth_analysis"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_growth_analysis(
                    context,
                    all_evidence,
                    all_evidence_ids,
                    run_id,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.analysis_model or "default",
            )
            draft_opportunities = analysis_result[0]
            gq_scores = analysis_result[1]
            fo_scores = analysis_result[2]
            all_finding_ids.extend(analysis_result[3])
            steps_completed += 1

            # -- Step 6: growth_validation (deterministic) --------------------------
            validation_output = await self._run_step_deterministic(
                step_map["growth_validation"],
                self._step_growth_validation(
                    draft_opportunities,
                    gq_scores,
                    fo_scores,
                    all_evidence,
                    all_evidence_ids,
                    request.company_id,
                    run_id,
                    request.observation_date,
                ),
            )
            draft_opportunities = validation_output[0]
            gq_scores = validation_output[1]
            fo_scores = validation_output[2]
            validation_result = validation_output[3]
            all_opportunity_ids = validation_output[4]
            growth_quality_score = validation_output[5]
            future_optionality_score = validation_output[6]
            steps_completed += 1

            # -- Step 7: growth_challenge (LLM) -------------------------------------
            challenge_finding_ids = await self._run_step_llm(
                step_map["growth_challenge"],
                run_id,
                token_budget,
                config,
                lambda exec_id: self._step_growth_challenge(
                    context.company_name,
                    draft_opportunities,
                    all_evidence,
                    run_id,
                    exec_id,
                    token_budget,
                    config,
                    request.observation_date,
                ),
                model_name=config.challenge_model or "default",
            )
            all_finding_ids.extend(challenge_finding_ids)
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

        return FutureGrowthResult(
            status=status,
            run_id=run_id,
            opportunities=all_opportunity_ids,
            findings_count=len(all_finding_ids),
            evidence_count=len(all_evidence_ids),
            growth_quality_score=growth_quality_score,
            future_optionality_score=future_optionality_score,
            validation_result=validation_result,
            steps_completed=steps_completed,
            token_usage=token_budget,
            errors=[error_msg] if error_msg else [],
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
        config: FutureGrowthConfig,
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
                    agent_name=GROWTH_AGENT_NAME,
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

    async def _step_context_load(
        self,
        request: FutureGrowthResearchRequest,
        run_id: uuid.UUID,
    ) -> LoadGrowthContextOutput:
        return await self._tools.load_company_context(
            LoadGrowthContextInput(
                company_id=request.company_id,
                research_run_id=run_id,
                observation_date=request.observation_date,
            ),
        )

    async def _step_source_discovery(
        self,
        context: LoadGrowthContextOutput,
        config: FutureGrowthConfig,
        observation_date: date,
    ) -> list[SourceCandidate]:
        result = await self._tools.discover_growth_sources(
            DiscoverGrowthSourcesInput(
                company_name=context.company_name,
                industry_name=context.industry_name,
                nse_symbol=context.nse_symbol,
                observation_date=observation_date,
                search_themes=list(INDIA_STRUCTURAL_THEMES[:3]),
            ),
        )
        sources = result.sources[: config.source_limit]
        if result.provider_errors:
            for err in result.provider_errors:
                logger.warning("Source discovery provider error: %s", err)
        return sources

    async def _step_document_retrieval(
        self,
        company_id: uuid.UUID,
        sources: list[SourceCandidate],
        config: FutureGrowthConfig,
        run_id: uuid.UUID,
    ) -> tuple[dict[str, RetrieveDocumentOutput], dict[str, uuid.UUID]]:
        documents: dict[str, RetrieveDocumentOutput] = {}
        document_ids: dict[str, uuid.UUID] = {}
        sem = asyncio.Semaphore(config.concurrent_retrievals)
        limited_sources = sources[: config.max_documents]

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

        tasks = [_retrieve(c) for c in limited_sources]
        await asyncio.gather(*tasks)
        return documents, document_ids

    async def _step_evidence_extraction(
        self,
        context: LoadGrowthContextOutput,
        documents: dict[str, RetrieveDocumentOutput],
        document_ids: dict[str, uuid.UUID],
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: FutureGrowthConfig,
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

            prompt = growth_evidence_extraction_prompt(
                company_name=context.company_name,
                industry_name=context.industry_name,
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

    async def _step_growth_analysis(
        self,
        context: LoadGrowthContextOutput,
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: FutureGrowthConfig,
        observation_date: date,
    ) -> tuple[
        list[GrowthOpportunityDraft],
        list[GrowthScoreComponent],
        list[GrowthScoreComponent],
        list[uuid.UUID],
    ]:
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

        prompt = growth_analysis_prompt(
            company_name=context.company_name,
            industry_name=context.industry_name,
            evidence_summaries=evidence_summaries,
            company_context=company_context,
            industry_context=industry_context,
            observation_date=observation_date,
        )

        schema = GrowthAnalysisOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.analysis_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        output = _parse_growth_analysis_response(response)

        finding_items = [
            FindingItem(
                agent_name=GROWTH_AGENT_NAME,
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

        return (
            list(output.opportunities),
            list(output.growth_quality_scores),
            list(output.future_optionality_scores),
            finding_ids,
        )

    async def _step_growth_validation(
        self,
        draft_opportunities: list[GrowthOpportunityDraft],
        gq_scores: list[GrowthScoreComponent],
        fo_scores: list[GrowthScoreComponent],
        all_evidence: list[ExtractedEvidence],
        all_evidence_ids: list[uuid.UUID],
        company_id: uuid.UUID,
        run_id: uuid.UUID,
        observation_date: date,
    ) -> tuple[
        list[GrowthOpportunityDraft],
        list[GrowthScoreComponent],
        list[GrowthScoreComponent],
        GrowthValidationResult,
        list[uuid.UUID],
        int | None,
        int | None,
    ]:
        validated_opps, clamped_gq, clamped_fo, val_result, _ = _validate_growth(
            draft_opportunities,
            gq_scores,
            fo_scores,
            all_evidence,
            all_evidence_ids,
        )

        growth_quality_score = _compute_dimension_score(clamped_gq)
        future_optionality_score = _compute_dimension_score(clamped_fo)

        opportunity_ids: list[uuid.UUID] = []
        if validated_opps:
            persist_result = await self._tools.persist_growth_opportunities(
                PersistGrowthOpportunitiesInput(
                    company_id=company_id,
                    research_run_id=run_id,
                    opportunities=validated_opps,
                    evidence_ids=all_evidence_ids,
                ),
            )
            opportunity_ids = persist_result.opportunity_ids

        if growth_quality_score is not None and future_optionality_score is not None:
            await self._tools.persist_scores(
                PersistGrowthScoresInput(
                    company_id=company_id,
                    research_run_id=run_id,
                    growth_quality_score=growth_quality_score,
                    future_optionality_score=future_optionality_score,
                    growth_quality_components=clamped_gq,
                    future_optionality_components=clamped_fo,
                ),
            )

        return (
            validated_opps,
            clamped_gq,
            clamped_fo,
            val_result,
            opportunity_ids,
            growth_quality_score,
            future_optionality_score,
        )

    async def _step_growth_challenge(
        self,
        company_name: str,
        validated_opportunities: list[GrowthOpportunityDraft],
        all_evidence: list[ExtractedEvidence],
        run_id: uuid.UUID,
        execution_id: uuid.UUID,
        token_budget: TokenBudget,
        config: FutureGrowthConfig,
        observation_date: date,
    ) -> list[uuid.UUID]:
        opportunities_summary = "\n\n".join(
            f"[{o.opportunity_name}] Category: {o.category}, "
            f"Maturity: {o.maturity}, "
            f"TAM: {o.addressable_market or 'N/A'}, "
            f"Confidence: {o.confidence}\n"
            f"Rationale: {o.rationale}"
            for o in validated_opportunities
        )
        evidence_summaries = "\n\n".join(
            f"[{i}] [{ev.evidence_type}] {ev.claim} (confidence: {ev.confidence})" for i, ev in enumerate(all_evidence)
        )

        prompt = growth_challenge_prompt(
            company_name=company_name,
            opportunities_summary=opportunities_summary,
            evidence_summaries=evidence_summaries,
        )

        schema = GrowthChallengeOutput.model_json_schema()
        response = await self._llm.generate(
            prompt,
            model=config.challenge_model,
            response_schema=schema,
        )
        token_budget.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        output = _parse_growth_challenge_response(response)

        finding_items = [
            FindingItem(
                agent_name=GROWTH_AGENT_NAME,
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


def _parse_growth_analysis_response(
    response: LLMResponse,
) -> GrowthAnalysisOutput:
    try:
        data = json.loads(response.content)
        return GrowthAnalysisOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "growth_analysis",
            str(exc),
        ) from exc


def _parse_growth_challenge_response(
    response: LLMResponse,
) -> GrowthChallengeOutput:
    try:
        data = json.loads(response.content)
        return GrowthChallengeOutput.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParsingError(
            "growth_challenge",
            str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Deterministic validation (MV-01 through MV-10, §20)
# ---------------------------------------------------------------------------

_MATURITY_DOWNGRADE_LADDER: tuple[str, ...] = (
    "PROVEN",
    "COMMERCIALIZING",
    "EARLY_STAGE",
    "EXPERIMENTAL",
    "SPECULATIVE",
)


def _validate_growth(
    draft_opportunities: list[GrowthOpportunityDraft],
    gq_scores: list[GrowthScoreComponent],
    fo_scores: list[GrowthScoreComponent],
    all_evidence: list[ExtractedEvidence],
    all_evidence_ids: list[uuid.UUID],
    findings: list[FindingItem] | None = None,
) -> tuple[
    list[GrowthOpportunityDraft],
    list[GrowthScoreComponent],
    list[GrowthScoreComponent],
    GrowthValidationResult,
    list[FindingItem],
]:
    issues: list[GrowthValidationIssue] = []
    downgraded_maturities: list[tuple[str, str, str]] = []
    nullified_tams: list[str] = []

    validated: list[GrowthOpportunityDraft] = []

    for opp in draft_opportunities:
        current = opp
        opp_name = current.opportunity_name

        # MV-06: GrowthCategory is valid enum value
        if current.category.upper() not in _ALL_GROWTH_CATEGORIES:
            issues.append(
                GrowthValidationIssue(
                    check_id="MV-06",
                    severity="ERROR",
                    opportunity_name=opp_name,
                    message=f"Invalid GrowthCategory: {current.category}",
                ),
            )
            continue

        # MV-07: GrowthMaturity is valid enum value
        if current.maturity.upper() not in _ALL_GROWTH_MATURITIES:
            issues.append(
                GrowthValidationIssue(
                    check_id="MV-07",
                    severity="ERROR",
                    opportunity_name=opp_name,
                    message=f"Invalid GrowthMaturity: {current.maturity}",
                ),
            )
            continue

        # MV-01: Every opportunity has >= 1 evidence_id
        ev_count = len(current.evidence_indices) if current.evidence_indices else 0
        if ev_count == 0:
            old_maturity = current.maturity.upper()
            if old_maturity != "SPECULATIVE":
                downgraded_maturities.append((opp_name, old_maturity, "SPECULATIVE"))
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-01",
                        severity="ERROR",
                        opportunity_name=opp_name,
                        message=(f"No evidence for opportunity; downgrading {old_maturity} to SPECULATIVE"),
                    ),
                )
                current = GrowthOpportunityDraft(
                    opportunity_name=current.opportunity_name,
                    category=current.category,
                    maturity="SPECULATIVE",
                    addressable_market=current.addressable_market,
                    tam_methodology=current.tam_methodology,
                    tam_low=current.tam_low,
                    tam_high=current.tam_high,
                    timeline_years=current.timeline_years,
                    confidence=current.confidence,
                    evidence_indices=current.evidence_indices,
                    risks=current.risks,
                    rationale=current.rationale,
                )

        # MV-02: PROVEN requires FACT-type evidence with revenue data
        if current.maturity.upper() == "PROVEN":
            has_fact_revenue = _has_fact_revenue_evidence(current.evidence_indices, all_evidence)
            if not has_fact_revenue:
                new_maturity = "COMMERCIALIZING"
                downgraded_maturities.append((opp_name, "PROVEN", new_maturity))
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-02",
                        severity="ERROR",
                        opportunity_name=opp_name,
                        message=(
                            f"PROVEN requires FACT-type evidence with revenue data; downgrading to {new_maturity}"
                        ),
                    ),
                )
                current = _replace_maturity(current, new_maturity)

        # MV-03: COMMERCIALIZING requires evidence of revenue generation
        if current.maturity.upper() == "COMMERCIALIZING":
            has_revenue_evidence = _has_revenue_evidence(current.evidence_indices, all_evidence)
            if not has_revenue_evidence:
                new_maturity = "EARLY_STAGE"
                downgraded_maturities.append((opp_name, "COMMERCIALIZING", new_maturity))
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-03",
                        severity="ERROR",
                        opportunity_name=opp_name,
                        message=(
                            f"COMMERCIALIZING requires evidence of revenue generation; downgrading to {new_maturity}"
                        ),
                    ),
                )
                current = _replace_maturity(current, new_maturity)

        # MV-05: TAM validation
        if current.addressable_market is not None:
            tam_valid = True

            if not current.tam_methodology:
                tam_valid = False
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-05",
                        severity="ERROR",
                        opportunity_name=opp_name,
                        message="TAM without methodology; nullifying addressable_market",
                    ),
                )

            if current.tam_low is not None and current.tam_high is not None and current.tam_low > current.tam_high:
                tam_valid = False
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-05",
                        severity="ERROR",
                        opportunity_name=opp_name,
                        message="tam_low > tam_high; nullifying addressable_market",
                    ),
                )

            if not tam_valid:
                nullified_tams.append(opp_name)
                current = GrowthOpportunityDraft(
                    opportunity_name=current.opportunity_name,
                    category=current.category,
                    maturity=current.maturity,
                    addressable_market=None,
                    tam_methodology=None,
                    tam_low=None,
                    tam_high=None,
                    timeline_years=current.timeline_years,
                    confidence=current.confidence,
                    evidence_indices=current.evidence_indices,
                    risks=current.risks,
                    rationale=current.rationale,
                )

        # MV-10: addressable_market is non-negative when present
        if current.addressable_market is not None and current.addressable_market < Decimal("0"):
            nullified_tams.append(opp_name)
            issues.append(
                GrowthValidationIssue(
                    check_id="MV-10",
                    severity="ERROR",
                    opportunity_name=opp_name,
                    message="Negative addressable_market; nullifying",
                ),
            )
            current = GrowthOpportunityDraft(
                opportunity_name=current.opportunity_name,
                category=current.category,
                maturity=current.maturity,
                addressable_market=None,
                tam_methodology=current.tam_methodology,
                tam_low=current.tam_low,
                tam_high=current.tam_high,
                timeline_years=current.timeline_years,
                confidence=current.confidence,
                evidence_indices=current.evidence_indices,
                risks=current.risks,
                rationale=current.rationale,
            )

        validated.append(current)

    # MV-04 / MV-09: Finding type validation
    corrected_findings = _validate_findings(findings or [], issues)

    # MV-08: Scores in [0, 100] — clamp
    clamped_gq = _clamp_scores(gq_scores, issues, "growth_quality")
    clamped_fo = _clamp_scores(fo_scores, issues, "future_optionality")

    passed = len(issues) == 0
    result = GrowthValidationResult(
        passed=passed,
        issues=issues,
        downgraded_maturities=downgraded_maturities,
        nullified_tams=nullified_tams,
    )
    return validated, clamped_gq, clamped_fo, result, corrected_findings


def _has_fact_revenue_evidence(
    evidence_indices: list[int],
    all_evidence: list[ExtractedEvidence],
) -> bool:
    revenue_keywords = ("revenue", "sales", "turnover", "income")
    for idx in evidence_indices:
        if 0 <= idx < len(all_evidence):
            ev = all_evidence[idx]
            if ev.evidence_type.value == "FACT" or ev.evidence_type.value == "FINANCIAL_DATA":
                claim_lower = ev.claim.lower()
                if any(kw in claim_lower for kw in revenue_keywords):
                    return True
    return False


def _has_revenue_evidence(
    evidence_indices: list[int],
    all_evidence: list[ExtractedEvidence],
) -> bool:
    revenue_keywords = ("revenue", "sales", "turnover", "income", "commerciali")
    for idx in evidence_indices:
        if 0 <= idx < len(all_evidence):
            ev = all_evidence[idx]
            claim_lower = ev.claim.lower()
            if any(kw in claim_lower for kw in revenue_keywords):
                return True
    return False


def _replace_maturity(
    opp: GrowthOpportunityDraft,
    new_maturity: str,
) -> GrowthOpportunityDraft:
    return GrowthOpportunityDraft(
        opportunity_name=opp.opportunity_name,
        category=opp.category,
        maturity=new_maturity,
        addressable_market=opp.addressable_market,
        tam_methodology=opp.tam_methodology,
        tam_low=opp.tam_low,
        tam_high=opp.tam_high,
        timeline_years=opp.timeline_years,
        confidence=opp.confidence,
        evidence_indices=opp.evidence_indices,
        risks=opp.risks,
        rationale=opp.rationale,
    )


def _clamp_scores(
    scores: list[GrowthScoreComponent],
    issues: list[GrowthValidationIssue],
    dimension_label: str,
) -> list[GrowthScoreComponent]:
    clamped: list[GrowthScoreComponent] = []
    for sc in scores:
        if sc.score < 0 or sc.score > 100:
            issues.append(
                GrowthValidationIssue(
                    check_id="MV-08",
                    severity="ERROR",
                    opportunity_name=None,
                    message=(
                        f"{dimension_label} component '{sc.component_name}' score {sc.score} out of [0,100]; clamping"
                    ),
                ),
            )
            clamped.append(
                GrowthScoreComponent(
                    component_name=sc.component_name,
                    score=max(0, min(100, sc.score)),
                    rationale=sc.rationale,
                    evidence_indices=sc.evidence_indices,
                ),
            )
        else:
            clamped.append(sc)
    return clamped


_FORWARD_LOOKING_CATEGORIES: frozenset[str] = frozenset(
    {
        "growth_opportunity",
        "tam_estimate",
        "growth_trajectory",
        "theme_alignment",
        "growth_risk",
        "growth_challenge",
    }
)


def _validate_findings(
    findings: list[FindingItem],
    issues: list[GrowthValidationIssue],
) -> list[FindingItem]:
    corrected: list[FindingItem] = []
    for f in findings:
        current = f

        # MV-04: forward-looking finding must not have FindingType.FACT
        if current.finding_type == FindingType.FACT and current.category in _FORWARD_LOOKING_CATEGORIES:
            issues.append(
                GrowthValidationIssue(
                    check_id="MV-04",
                    severity="ERROR",
                    opportunity_name=None,
                    message=(
                        f"Forward-looking finding (category={current.category}) "
                        f"classified as FACT; reclassifying to AI_INFERENCE"
                    ),
                ),
            )
            current = FindingItem(
                agent_name=current.agent_name,
                finding_type=FindingType.AI_INFERENCE,
                category=current.category,
                content=current.content,
                confidence=current.confidence,
                observation_date=current.observation_date,
                source_publication_date=current.source_publication_date,
                evidence_ids=current.evidence_ids,
            )

        # MV-09: MANAGEMENT_CLAIM must not be classified as FACT or CALCULATION
        if current.finding_type in (FindingType.FACT, FindingType.CALCULATION):
            content_lower = current.content.lower()
            mgmt_indicators = (
                "management guided",
                "management expects",
                "management stated",
                "management announced",
                "management plans",
                "according to management",
                "management indicated",
                "management projected",
                "management commentary",
                "guidance of",
                "guided for",
                "management believes",
            )
            if any(indicator in content_lower for indicator in mgmt_indicators):
                issues.append(
                    GrowthValidationIssue(
                        check_id="MV-09",
                        severity="ERROR",
                        opportunity_name=None,
                        message=(
                            f"Finding contains management-claim language but classified "
                            f"as {current.finding_type.value}; reclassifying to MANAGEMENT_CLAIM"
                        ),
                    ),
                )
                current = FindingItem(
                    agent_name=current.agent_name,
                    finding_type=FindingType.MANAGEMENT_CLAIM,
                    category=current.category,
                    content=current.content,
                    confidence=current.confidence,
                    observation_date=current.observation_date,
                    source_publication_date=current.source_publication_date,
                    evidence_ids=current.evidence_ids,
                )

        corrected.append(current)
    return corrected


def _compute_dimension_score(
    components: list[GrowthScoreComponent],
) -> int | None:
    if not components:
        return None
    total = sum(c.score for c in components)
    return total // len(components)
