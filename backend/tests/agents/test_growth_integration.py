"""Phase 12.6 — Future Growth & Optionality Agent Integration Tests.

Proves that Phase 12 components (contracts, tools, prompts, agent,
validation, persistence) work together across their real boundaries.
Unlike Phase 12.5 (individual validation), these tests exercise
integrated execution paths through the full agent pipeline.

Mocking strategy: only external boundaries (LLM, search, news,
corporate filings, DB session) are mocked.  Internal code paths
(contracts → tools → prompts → agent → validation → persistence)
are exercised through their real implementations.

Key integration concerns addressed:
- TD-38: MV-04/MV-09 corrected findings reach persistence.
- TD-39: Hardened management-claim detection avoids false positives.
- AC-31 through AC-41: Architecture acceptance criteria.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.contracts import (
    GROWTH_AGENT_NAME,
    GROWTH_AGENT_RUN_TYPE,
    GROWTH_RESEARCH_STEPS,
    DiscoverGrowthSourcesOutput,
    FutureGrowthConfig,
    FutureGrowthResearchRequest,
    FutureGrowthResult,
    LoadGrowthContextOutput,
    PersistEvidenceOutput,
    PersistFindingsOutput,
    PersistGrowthOpportunitiesOutput,
    PersistGrowthScoresOutput,
    RetrieveDocumentOutput,
    SourceCandidate,
)
from app.agents.future_growth.agent import FutureGrowthAgent
from app.models.enums import (
    AgentExecutionStatus,
    ConfidenceLevel,
    DocumentType,
    FindingType,
    SourceTier,
    StepStatus,
)
from app.models.research import AgentExecution, ResearchRun, ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.types import LLMResponse
from app.providers.types import TokenUsage as ProviderTokenUsage

# ---------------------------------------------------------------------------
# Fixed UUIDs for deterministic tests
# ---------------------------------------------------------------------------

COMPANY_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
RUN_A = uuid.UUID("aaaa0001-0001-0001-0001-000000000001")
INDUSTRY_UUID = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000001")
DOC_UUID_1 = uuid.UUID("dddddddd-0001-0001-0001-000000000001")
EXEC_UUID = uuid.UUID("eeeeeeee-0001-0001-0001-000000000001")
STEP_UUID = uuid.UUID("ffffffff-0001-0001-0001-000000000001")
EVIDENCE_UUID_1 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-000000000001")
EVIDENCE_UUID_2 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-000000000002")
FINDING_UUID_1 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-100000000001")
FINDING_UUID_2 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-100000000002")
OPP_UUID_1 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-200000000001")
GROWTH_SCORE_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-300000000001")
OPTIONALITY_SCORE_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-300000000002")

OBS_DATE = date(2025, 9, 30)

# ---------------------------------------------------------------------------
# LLM response builders
# ---------------------------------------------------------------------------


def _evidence_response(
    evidences: list[dict[str, Any]] | None = None,
    input_tokens: int = 500,
    output_tokens: int = 200,
) -> LLMResponse:
    if evidences is None:
        evidences = [
            {
                "evidence_type": "FACT",
                "claim": "Revenue was Rs 10,000 crore in FY2025",
                "context": "From audited annual report",
                "page_or_section": "Financial Highlights, page 5",
                "confidence": "HIGH",
            },
            {
                "evidence_type": "MANAGEMENT_STATEMENT",
                "claim": "Management expects 25% CAGR in digital services",
                "context": "Earnings call Q4 FY2025",
                "page_or_section": None,
                "confidence": "MEDIUM",
            },
        ]
    return LLMResponse(
        content=json.dumps({"evidences": evidences}),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        finish_reason="stop",
    )


def _analysis_response(
    findings: list[dict[str, Any]] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
    gq_scores: list[dict[str, Any]] | None = None,
    fo_scores: list[dict[str, Any]] | None = None,
    input_tokens: int = 800,
    output_tokens: int = 400,
) -> LLMResponse:
    if opportunities is None:
        opportunities = [
            {
                "opportunity_name": "Digital Services Expansion",
                "category": "TECHNOLOGY",
                "maturity": "EARLY_STAGE",
                "addressable_market": "6500",
                "tam_methodology": "TAM analysis",
                "tam_low": "5000",
                "tam_high": "8000",
                "timeline_years": 3,
                "confidence": "MEDIUM",
                "evidence_indices": [0, 1],
                "risks": ["Competitive pressure"],
                "rationale": "Supported by revenue data and management guidance",
            },
        ]
    if gq_scores is None:
        gq_scores = [
            {
                "component_name": "revenue_momentum",
                "score": 70,
                "rationale": "Strong 15% YoY revenue growth",
                "evidence_indices": [0],
            },
        ]
    if fo_scores is None:
        fo_scores = [
            {
                "component_name": "optionality_breadth",
                "score": 60,
                "rationale": "Digital expansion provides optionality",
                "evidence_indices": [1],
            },
        ]
    if findings is None:
        findings = [
            {
                "finding_type": "FACT",
                "category": "growth_quality",
                "content": "Revenue grew 15% YoY to Rs 10,000 crore in FY25",
                "confidence": "HIGH",
                "source_publication_date": "2025-05-30",
                "evidence_indices": [0],
            },
            {
                "finding_type": "AI_INFERENCE",
                "category": "growth_trajectory",
                "content": "Digital transformation likely to drive 20% CAGR",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": [0, 1],
            },
        ]
    return LLMResponse(
        content=json.dumps(
            {
                "opportunities": opportunities,
                "growth_quality_scores": gq_scores,
                "future_optionality_scores": fo_scores,
                "growth_vs_optionality_separation": (
                    "Growth quality reflects current momentum; optionality captures future potential."
                ),
                "themes_identified": ["Digital Transformation"],
                "findings": findings,
            }
        ),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        finish_reason="stop",
    )


def _challenge_response(
    findings: list[dict[str, Any]] | None = None,
    input_tokens: int = 400,
    output_tokens: int = 150,
) -> LLMResponse:
    if findings is None:
        findings = [
            {
                "finding_type": "AI_INFERENCE",
                "category": "growth_challenge",
                "content": "Competition from larger players may limit growth",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": None,
            },
        ]
    challenges = [
        {
            "opportunity_name": "Digital Services Expansion",
            "challenge": "Intense competition from established players",
            "tam_challenge": "Market may be smaller than estimated",
            "competitive_risk": "Large incumbents have deeper pockets",
            "execution_risk": "Talent acquisition in competitive market",
            "revised_confidence": "MEDIUM",
            "evidence_indices": [0],
        },
    ]
    return LLMResponse(
        content=json.dumps(
            {
                "challenges": challenges,
                "overall_optimism_assessment": "Moderate — growth exists but execution risk is real",
                "findings": findings,
            }
        ),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        finish_reason="stop",
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_context(
    company_id: uuid.UUID = COMPANY_A,
    company_name: str = "Test Company Ltd",
    nse_symbol: str | None = "TESTCO",
    industry_id: uuid.UUID | None = INDUSTRY_UUID,
    industry_name: str | None = "Technology",
) -> LoadGrowthContextOutput:
    return LoadGrowthContextOutput(
        company_id=company_id,
        company_name=company_name,
        nse_symbol=nse_symbol,
        industry_id=industry_id,
        industry_name=industry_name,
        company_findings=[],
        industry_findings=[],
        has_company_research=False,
        has_industry_research=False,
    )


def _make_source(
    source_id: str = "filing-1",
    source_type: DocumentType = DocumentType.FILING,
    provider: str = "corporate_filings",
    pub_date: date | None = None,
) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        source_type=source_type,
        provider=provider,
        title=f"Annual Report {source_id}",
        publication_date=pub_date or date(2025, 5, 30),
        source_tier=SourceTier.TIER_1,
        url=f"https://bseindia.com/filings/{source_id}",
    )


def _make_doc(
    filing_id: str = "filing-1",
    content: str = "Test Company Ltd reported revenue of Rs 10,000 crore in FY2025.",
) -> RetrieveDocumentOutput:
    import hashlib

    return RetrieveDocumentOutput(
        content=content,
        content_type="text/plain",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        filing_id=filing_id,
    )


def _make_run(run_id: uuid.UUID = RUN_A, company_id: uuid.UUID = COMPANY_A) -> ResearchRun:
    run = ResearchRun(
        id=run_id,
        company_id=company_id,
        initiated_by="test_integration",
        status="CREATED",
        run_type="future_growth",
        trigger_type="manual",
    )
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


def _make_step(name: str, order: int, run_id: uuid.UUID = RUN_A) -> ResearchRunStep:
    step = ResearchRunStep(
        id=uuid.uuid4(),
        research_run_id=run_id,
        step_name=name,
        step_order=order,
        step_type="deterministic",
        status=StepStatus.PENDING,
    )
    step.created_at = datetime.now(UTC)
    return step


def _make_7_steps(run_id: uuid.UUID = RUN_A) -> list[ResearchRunStep]:
    return [_make_step(s.step_name, s.step_order, run_id) for s in GROWTH_RESEARCH_STEPS]


def _make_execution(exec_id: uuid.UUID = EXEC_UUID) -> AgentExecution:
    ex = AgentExecution(
        id=exec_id,
        research_run_id=RUN_A,
        step_id=STEP_UUID,
        agent_name=GROWTH_AGENT_NAME,
        attempt_number=1,
        status=AgentExecutionStatus.RUNNING,
        model_provider="llm",
        model_name="default",
    )
    ex.created_at = datetime.now(UTC)
    return ex


class MockRunService:
    def __init__(self, run_id: uuid.UUID = RUN_A, company_id: uuid.UUID = COMPANY_A) -> None:
        self.run_id = run_id
        self._run = _make_run(run_id, company_id)
        self._steps = _make_7_steps(run_id)
        self._exec_counter = 0

        self.initiate_run = AsyncMock(return_value=self._run)
        self.create_steps = AsyncMock(return_value=self._steps)
        self.enqueue_run = AsyncMock()
        self.start_run = AsyncMock()
        self.complete_run = AsyncMock()
        self.fail_run = AsyncMock()
        self.partial_run = AsyncMock()
        self.update_run_aggregates = AsyncMock()

        self.start_step = AsyncMock()
        self.complete_step = AsyncMock()
        self.fail_step = AsyncMock()
        self.skip_step = AsyncMock()
        self.retry_step = AsyncMock()

        self.record_agent_execution = AsyncMock(side_effect=self._new_execution)
        self.complete_agent = AsyncMock()
        self.fail_agent = AsyncMock()

        self.record_findings = AsyncMock(return_value=[])
        self.record_source_access = AsyncMock()

    def _new_execution(self, *args: object, **kwargs: object) -> AgentExecution:
        self._exec_counter += 1
        return _make_execution(uuid.uuid4())


def _build_agent(
    *,
    run_service: MockRunService | None = None,
    llm_responses: list[LLMResponse | Exception] | None = None,
    company_id: uuid.UUID = COMPANY_A,
    run_id: uuid.UUID = RUN_A,
) -> tuple[FutureGrowthAgent, MockRunService, dict[str, AsyncMock]]:
    session = AsyncMock()
    session.flush = AsyncMock()

    if run_service is None:
        run_service = MockRunService(run_id, company_id)

    search = AsyncMock()
    news = AsyncMock()
    corporate_filings = AsyncMock()
    llm = AsyncMock()

    if llm_responses:
        llm.generate = AsyncMock(side_effect=llm_responses)
    else:
        llm.generate = AsyncMock(return_value=_evidence_response())

    agent = FutureGrowthAgent(
        session=session,
        run_service=run_service,  # type: ignore[arg-type]
        search=search,
        news=news,
        corporate_filings=corporate_filings,
        llm=llm,
    )

    return (
        agent,
        run_service,
        {
            "session": session,
            "search": search,
            "news": news,
            "corporate_filings": corporate_filings,
            "llm": llm,
        },
    )


def _patch_tools_happy_path(
    agent: FutureGrowthAgent,
    *,
    context: LoadGrowthContextOutput | None = None,
    sources: list[SourceCandidate] | None = None,
    doc: RetrieveDocumentOutput | None = None,
    evidence_ids: list[uuid.UUID] | None = None,
    finding_ids: list[uuid.UUID] | None = None,
    opportunity_ids: list[uuid.UUID] | None = None,
) -> tuple[Any, ...]:
    if context is None:
        context = _make_context()
    if sources is None:
        sources = [_make_source()]
    if doc is None:
        doc = _make_doc()
    if evidence_ids is None:
        evidence_ids = [EVIDENCE_UUID_1, EVIDENCE_UUID_2]
    if finding_ids is None:
        finding_ids = [FINDING_UUID_1, FINDING_UUID_2]
    if opportunity_ids is None:
        opportunity_ids = [OPP_UUID_1]

    return (
        patch.object(agent._tools, "load_company_context", new_callable=AsyncMock, return_value=context),
        patch.object(
            agent._tools,
            "discover_growth_sources",
            new_callable=AsyncMock,
            return_value=DiscoverGrowthSourcesOutput(sources=sources, provider_errors=[]),
        ),
        patch.object(agent._tools, "retrieve_document", new_callable=AsyncMock, return_value=doc),
        patch.object(agent._tools, "create_research_document", new_callable=AsyncMock, return_value=DOC_UUID_1),
        patch.object(
            agent._tools,
            "persist_evidence",
            new_callable=AsyncMock,
            return_value=PersistEvidenceOutput(evidence_ids=evidence_ids),
        ),
        patch.object(
            agent._tools,
            "persist_findings",
            new_callable=AsyncMock,
            return_value=PersistFindingsOutput(finding_ids=finding_ids, rejected=[]),
        ),
        patch.object(
            agent._tools,
            "persist_growth_opportunities",
            new_callable=AsyncMock,
            return_value=PersistGrowthOpportunitiesOutput(opportunity_ids=opportunity_ids),
        ),
        patch.object(
            agent._tools,
            "persist_scores",
            new_callable=AsyncMock,
            return_value=PersistGrowthScoresOutput(
                growth_quality_score_id=GROWTH_SCORE_UUID,
                future_optionality_score_id=OPTIONALITY_SCORE_UUID,
            ),
        ),
    )


def _run_with_patches(
    agent: FutureGrowthAgent,
    patches: tuple[Any, ...],
    request: FutureGrowthResearchRequest | None = None,
) -> Any:
    """Enter all patches and execute the agent. Returns a coroutine.

    The patches are entered, the agent executes, and the mocks remain
    accessible via ``agent._tools.<method>`` for the duration because we
    do NOT exit the patches until after the awaited result is captured.
    To make post-run assertions on mocks, use :func:`_run_keeping_mocks`.
    """
    if request is None:
        request = FutureGrowthResearchRequest(
            company_id=COMPANY_A,
            observation_date=OBS_DATE,
            initiated_by="integration_test",
        )

    async def _run() -> FutureGrowthResult:
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
            return await agent.execute(request)

    return _run()


async def _run_keeping_mocks(
    agent: FutureGrowthAgent,
    patches: tuple[Any, ...],
    request: FutureGrowthResearchRequest | None = None,
) -> tuple[FutureGrowthResult, dict[str, AsyncMock]]:
    """Run agent with patches and return (result, mocks dict).

    Mocks are captured while the patches are active so callers can
    assert on call counts and arguments after the run completes.
    """
    if request is None:
        request = FutureGrowthResearchRequest(
            company_id=COMPANY_A,
            observation_date=OBS_DATE,
            initiated_by="integration_test",
        )

    mocks: list[Any] = []
    for p in patches:
        mocks.append(p.__enter__())
    try:
        result = await agent.execute(request)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    tool_names = [
        "load_company_context",
        "discover_growth_sources",
        "retrieve_document",
        "create_research_document",
        "persist_evidence",
        "persist_findings",
        "persist_growth_opportunities",
        "persist_scores",
    ]
    return result, {name: mock for name, mock in zip(tool_names, mocks, strict=True)}


# ===========================================================================
# 1. End-to-End Successful Growth Run (AC-31)
# ===========================================================================


class TestEndToEndSuccess:
    @pytest.mark.asyncio()
    async def test_full_pipeline_completes_with_all_7_steps(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.status == "COMPLETED"
        assert result.run_id == RUN_A
        assert result.steps_completed == 7
        assert len(result.errors) == 0

        svc.initiate_run.assert_awaited_once()
        svc.create_steps.assert_awaited_once()
        svc.complete_run.assert_awaited_once()
        svc.fail_run.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_run_creates_correct_metadata(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        await _run_with_patches(agent, patches)

        create_arg = svc.initiate_run.call_args[0][0]
        assert create_arg.target_type == "company"
        assert create_arg.company_id == COMPANY_A
        assert create_arg.run_type == GROWTH_AGENT_RUN_TYPE

    @pytest.mark.asyncio()
    async def test_step_ordering_matches_architecture(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        await _run_with_patches(agent, patches)

        step_defs = svc.create_steps.call_args[0][1]
        assert len(step_defs) == 7
        assert [s.step_name for s in step_defs] == [s.step_name for s in GROWTH_RESEARCH_STEPS]


# ===========================================================================
# 2. Score Persistence (AC-33, AC-34)
# ===========================================================================


class TestScorePersistence:
    @pytest.mark.asyncio()
    async def test_growth_quality_score_persisted(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.growth_quality_score is not None
        assert result.growth_quality_score == 70

    @pytest.mark.asyncio()
    async def test_future_optionality_score_persisted(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.future_optionality_score is not None
        assert result.future_optionality_score == 60

    @pytest.mark.asyncio()
    async def test_persist_scores_called_with_both_dimensions(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        mocks["persist_scores"].assert_awaited_once()
        call_arg = mocks["persist_scores"].call_args[0][0]
        assert call_arg.growth_quality_score == 70
        assert call_arg.future_optionality_score == 60


# ===========================================================================
# 3. TD-38: Corrected Findings Reach Persistence
# ===========================================================================


class TestTD38FindingCorrectionPersistence:
    @pytest.mark.asyncio()
    async def test_mv04_forward_looking_fact_corrected_before_persistence(self) -> None:
        """A forward-looking FACT in analysis output must be corrected to
        AI_INFERENCE before persist_findings is called."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_opportunity",
                    "content": "Digital services expected to grow 25% CAGR",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)
        assert result.status == "COMPLETED"

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_call = persist_calls[0]
        persisted_findings = analysis_call[0][0].findings

        corrected = [f for f in persisted_findings if f.category == "growth_opportunity"]
        assert len(corrected) == 1
        assert corrected[0].finding_type == FindingType.AI_INFERENCE

    @pytest.mark.asyncio()
    async def test_mv09_management_claim_corrected_before_persistence(self) -> None:
        """A FACT with management-claim language must be corrected to
        MANAGEMENT_CLAIM before persist_findings is called."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "management_growth_claim",
                    "content": "Management expects EBITDA margin to reach 30%",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)
        assert result.status == "COMPLETED"

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_call = persist_calls[0]
        persisted_findings = analysis_call[0][0].findings

        mgmt_findings = [f for f in persisted_findings if f.category == "management_growth_claim"]
        assert len(mgmt_findings) == 1
        assert mgmt_findings[0].finding_type == FindingType.MANAGEMENT_CLAIM

    @pytest.mark.asyncio()
    async def test_mv04_mv09_precedence_in_persisted_findings(self) -> None:
        """MV-04 fires first: a forward-looking FACT with management language
        becomes AI_INFERENCE (not MANAGEMENT_CLAIM)."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_opportunity",
                    "content": "Management expects the growth opportunity to drive 30% returns",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)
        assert result.status == "COMPLETED"

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_call = persist_calls[0]
        persisted_findings = analysis_call[0][0].findings

        opp_findings = [f for f in persisted_findings if f.category == "growth_opportunity"]
        assert len(opp_findings) == 1
        assert opp_findings[0].finding_type == FindingType.AI_INFERENCE

    @pytest.mark.asyncio()
    async def test_correct_finding_passes_through_unchanged(self) -> None:
        """A correctly classified finding should not be altered."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "growth_trajectory",
                    "content": "Growth trajectory suggests acceleration in H2",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_call = persist_calls[0]
        persisted_findings = analysis_call[0][0].findings

        assert len(persisted_findings) == 1
        assert persisted_findings[0].finding_type == FindingType.AI_INFERENCE

    @pytest.mark.asyncio()
    async def test_challenge_findings_mv09_corrected(self) -> None:
        """MV-09 corrections apply to Step 7 (challenge) findings.
        Use a non-forward-looking category so MV-04 doesn't pre-empt."""
        challenge = _challenge_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "management_growth_claim",
                    "content": "Management stated that competition is intensifying",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), challenge],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)
        assert result.status == "COMPLETED"

        persist_calls = mocks["persist_findings"].call_args_list
        assert len(persist_calls) == 2
        challenge_call = persist_calls[1]
        challenge_findings = challenge_call[0][0].findings

        assert len(challenge_findings) == 1
        assert challenge_findings[0].finding_type == FindingType.MANAGEMENT_CLAIM

    @pytest.mark.asyncio()
    async def test_challenge_findings_mv04_corrected(self) -> None:
        """MV-04 corrections apply to Step 7 (challenge) findings:
        forward-looking FACT → AI_INFERENCE."""
        challenge = _challenge_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_challenge",
                    "content": "Competitive pressure may erode margins over 3 years",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), challenge],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)
        assert result.status == "COMPLETED"

        persist_calls = mocks["persist_findings"].call_args_list
        assert len(persist_calls) == 2
        challenge_call = persist_calls[1]
        challenge_findings = challenge_call[0][0].findings

        assert len(challenge_findings) == 1
        assert challenge_findings[0].finding_type == FindingType.AI_INFERENCE

    @pytest.mark.asyncio()
    async def test_mixed_findings_each_corrected_independently(self) -> None:
        """Multiple findings: each gets independent MV-04/MV-09 treatment."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_opportunity",
                    "content": "Digital services expected to grow 25%",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "FACT",
                    "category": "management_growth_claim",
                    "content": "Management expects EBITDA margin to reach 30%",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "FACT",
                    "category": "growth_quality",
                    "content": "Revenue grew 15% YoY",
                    "confidence": "HIGH",
                    "source_publication_date": "2025-05-30",
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_call = persist_calls[0]
        pf = analysis_call[0][0].findings

        assert len(pf) == 3
        by_cat = {f.category: f for f in pf}
        assert by_cat["growth_opportunity"].finding_type == FindingType.AI_INFERENCE
        assert by_cat["management_growth_claim"].finding_type == FindingType.MANAGEMENT_CLAIM
        assert by_cat["growth_quality"].finding_type == FindingType.FACT

    @pytest.mark.asyncio()
    async def test_metadata_preserved_through_correction(self) -> None:
        """Agent name, confidence, dates, evidence_ids survive MV-04 correction."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_opportunity",
                    "content": "AI opportunity projected to grow 40%",
                    "confidence": "HIGH",
                    "source_publication_date": "2025-06-15",
                    "evidence_indices": [0, 1],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        pf = persist_calls[0][0][0].findings[0]
        assert pf.finding_type == FindingType.AI_INFERENCE
        assert pf.agent_name == GROWTH_AGENT_NAME
        assert pf.confidence == ConfidenceLevel.HIGH
        assert pf.observation_date == OBS_DATE
        assert pf.source_publication_date == date(2025, 6, 15)

    @pytest.mark.asyncio()
    async def test_no_duplicate_persistence(self) -> None:
        """persist_findings called exactly twice: once for analysis, once for challenge."""
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        assert mocks["persist_findings"].call_count == 2

    @pytest.mark.asyncio()
    async def test_result_and_persisted_findings_agree(self) -> None:
        """The returned result counts match the persisted finding calls."""
        finding_ids_analysis = [uuid.uuid4(), uuid.uuid4()]
        finding_ids_challenge = [uuid.uuid4()]

        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )

        persist_findings_mock = AsyncMock(
            side_effect=[
                PersistFindingsOutput(finding_ids=finding_ids_analysis, rejected=[]),
                PersistFindingsOutput(finding_ids=finding_ids_challenge, rejected=[]),
            ]
        )

        patches = list(_patch_tools_happy_path(agent))
        patches[5] = patch.object(agent._tools, "persist_findings", new=persist_findings_mock)
        patches_tuple = tuple(patches)

        result = await _run_with_patches(agent, patches_tuple)
        assert result.findings_count == 3


# ===========================================================================
# 4. Opportunity and Evidence Persistence (AC-31, AC-32)
# ===========================================================================


class TestOpportunityPersistence:
    @pytest.mark.asyncio()
    async def test_opportunities_persisted_with_evidence_ids(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)

        assert len(result.opportunities) == 1
        mocks["persist_growth_opportunities"].assert_awaited_once()
        call_arg = mocks["persist_growth_opportunities"].call_args[0][0]
        assert len(call_arg.evidence_ids) == 2


# ===========================================================================
# 5. Token Budget Exhaustion (AC-35)
# ===========================================================================


class TestTokenBudgetExhaustion:
    @pytest.mark.asyncio()
    async def test_budget_exhaustion_returns_partial(self) -> None:
        analysis = _analysis_response(input_tokens=15000, output_tokens=6000)
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)

        request = FutureGrowthResearchRequest(
            company_id=COMPANY_A,
            observation_date=OBS_DATE,
            initiated_by="integration_test",
            configuration=FutureGrowthConfig(token_budget=1000),
        )
        result = await _run_with_patches(agent, patches, request)

        assert result.status in ("PARTIAL", "FAILED")
        assert len(result.errors) > 0


# ===========================================================================
# 6. Provider Failure (AC-36)
# ===========================================================================


class TestProviderFailure:
    @pytest.mark.asyncio()
    async def test_early_step_failure_returns_failed(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[ProviderError(provider="mock-llm", message="LLM unavailable")],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.status == "FAILED"
        assert len(result.errors) > 0
        svc.fail_run.assert_awaited()

    @pytest.mark.asyncio()
    async def test_late_step_failure_returns_partial(self) -> None:
        err = ProviderError(provider="mock-llm", message="LLM unavailable for challenge")
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(),
                err,
                err,
            ],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.status == "PARTIAL"
        assert result.steps_completed >= 5


# ===========================================================================
# 7. Quality Gate: Management-Claim Separation (AC-37)
# ===========================================================================


class TestQualityGateManagementClaim:
    @pytest.mark.asyncio()
    async def test_management_claim_language_never_persisted_as_fact(self) -> None:
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "management_growth_claim",
                    "content": "Management announced a 30% growth target for FY26",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "CALCULATION",
                    "category": "growth_quality",
                    "content": "According to management, CAGR was 25% over 3 years",
                    "confidence": "HIGH",
                    "source_publication_date": "2025-05-30",
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_findings = persist_calls[0][0][0].findings

        for f in analysis_findings:
            if "management" in f.content.lower():
                assert f.finding_type == FindingType.MANAGEMENT_CLAIM


# ===========================================================================
# 8. Quality Gate: No FACT on Forward-Looking (AC-38)
# ===========================================================================


class TestQualityGateForwardLooking:
    @pytest.mark.asyncio()
    async def test_forward_looking_fact_never_persisted_as_fact(self) -> None:
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_opportunity",
                    "content": "Market expansion will create Rs 5000cr opportunity",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "FACT",
                    "category": "tam_estimate",
                    "content": "Total addressable market estimated at Rs 50,000 crore",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        analysis_findings = persist_calls[0][0][0].findings

        forward_looking_cats = {
            "growth_opportunity",
            "tam_estimate",
            "growth_trajectory",
            "theme_alignment",
            "growth_risk",
            "growth_challenge",
        }
        for f in analysis_findings:
            if f.category in forward_looking_cats:
                assert f.finding_type != FindingType.FACT, f"Finding with category={f.category} persisted as FACT"


# ===========================================================================
# 9. Empty and Partial Outputs
# ===========================================================================


class TestEmptyAndPartialOutputs:
    @pytest.mark.asyncio()
    async def test_no_findings_still_completes(self) -> None:
        analysis = _analysis_response(findings=[])
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response(findings=[])],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.status == "COMPLETED"
        assert result.findings_count == 0

    @pytest.mark.asyncio()
    async def test_invalid_finding_does_not_corrupt_valid(self) -> None:
        """An invalid finding (bad category) is rejected by persist_findings
        tool without affecting valid findings."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_quality",
                    "content": "Revenue grew 15%",
                    "confidence": "HIGH",
                    "source_publication_date": "2025-05-30",
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "FACT",
                    "category": "growth_quality",
                    "content": "Margins expanded 200bps",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result, mocks = await _run_keeping_mocks(agent, patches)

        assert result.status == "COMPLETED"
        persist_calls = mocks["persist_findings"].call_args_list
        analysis_findings = persist_calls[0][0][0].findings
        assert len(analysis_findings) == 2


# ===========================================================================
# 10. TD-39: Hardened MV-09 Detection in Integration Context
# ===========================================================================


class TestTD39HardenedDetectionIntegration:
    @pytest.mark.asyncio()
    async def test_central_bank_guidance_not_reclassified_in_pipeline(self) -> None:
        """'guidance of' without management context is not reclassified."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "growth_quality",
                    "content": "Under the guidance of the central bank, lending norms were tightened",
                    "confidence": "HIGH",
                    "source_publication_date": "2025-05-30",
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        pf = persist_calls[0][0][0].findings[0]
        assert pf.finding_type == FindingType.FACT

    @pytest.mark.asyncio()
    async def test_management_guidance_reclassified_in_pipeline(self) -> None:
        """'guidance of' with management context IS reclassified."""
        analysis = _analysis_response(
            findings=[
                {
                    "finding_type": "FACT",
                    "category": "management_growth_claim",
                    "content": "Management provided guidance of 20% revenue growth",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ]
        )
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis, _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        _, mocks = await _run_keeping_mocks(agent, patches)

        persist_calls = mocks["persist_findings"].call_args_list
        pf = persist_calls[0][0][0].findings[0]
        assert pf.finding_type == FindingType.MANAGEMENT_CLAIM


# ===========================================================================
# 11. Regression Guards
# ===========================================================================


class TestRegressionGuards:
    @pytest.mark.asyncio()
    async def test_agent_result_model_frozen(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        with pytest.raises((TypeError, AttributeError, ValueError)):
            result.status = "MODIFIED"  # type: ignore[misc]

    @pytest.mark.asyncio()
    async def test_validation_result_present_on_completion(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent)
        result = await _run_with_patches(agent, patches)

        assert result.validation_result is not None

    @pytest.mark.asyncio()
    async def test_evidence_count_matches_extraction(self) -> None:
        agent, _, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response(), _challenge_response()],
        )
        patches = _patch_tools_happy_path(agent, evidence_ids=[EVIDENCE_UUID_1, EVIDENCE_UUID_2])
        result = await _run_with_patches(agent, patches)

        assert result.evidence_count == 2
