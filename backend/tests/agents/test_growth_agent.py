"""Comprehensive tests for Phase 12.4 Future Growth & Optionality Agent.

Covers:
 1. Agent construction / dependency injection
 2. Full happy-path execution
 3. Deterministic step runner
 4. LLM step runner with retry
 5. Token budget enforcement
 6. Step 1: context load
 7. Step 2: source discovery
 8. Step 3: document retrieval
 9. Step 4: evidence extraction (LLM)
10. Step 5: growth analysis (LLM)
11. Step 6: growth validation (MV-01 through MV-10)
12. Step 7: growth challenge (LLM)
13. Error handling / partial completion
14. LLM response parsing
15. Scoring and dimension computation
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.company_research.exceptions import (
    LLMParsingError,
    StepFailedError,
    TokenBudgetExhaustedError,
)
from app.agents.contracts import (
    GROWTH_AGENT_NAME,
    GROWTH_AGENT_RUN_TYPE,
    GROWTH_AGENT_TOKEN_BUDGET,
    GROWTH_AGENT_TOKEN_WARNING,
    GROWTH_FINDING_CATEGORIES,
    GROWTH_RESEARCH_STEPS,
    INDIA_STRUCTURAL_THEMES,
    DiscoverGrowthSourcesOutput,
    ExtractedEvidence,
    FindingItem,
    FutureGrowthConfig,
    FutureGrowthResearchRequest,
    FutureGrowthResult,
    GrowthOpportunityDraft,
    GrowthScoreComponent,
    GrowthValidationIssue,
    GrowthValidationResult,
    LoadGrowthContextOutput,
    PersistEvidenceOutput,
    PersistFindingsOutput,
    PersistGrowthOpportunitiesOutput,
    PersistGrowthScoresInput,
    PersistGrowthScoresOutput,
    RetrieveDocumentOutput,
    SourceCandidate,
    TokenBudget,
)
from app.agents.future_growth.agent import (
    _FORWARD_LOOKING_CATEGORIES,
    FutureGrowthAgent,
    _clamp_scores,
    _compute_dimension_score,
    _has_fact_revenue_evidence,
    _has_management_claim_language,
    _has_revenue_evidence,
    _parse_evidence_extraction_response,
    _parse_growth_analysis_response,
    _parse_growth_challenge_response,
    _replace_maturity,
    _validate_findings,
    _validate_growth,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    SourceTier,
)
from app.models.research import AgentExecution, ResearchRun, ResearchRunStep
from app.providers.types import LLMResponse
from app.providers.types import TokenUsage as ProviderTokenUsage

# ---------------------------------------------------------------------------
# Fixed UUIDs
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
EXEC_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
DOC_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
STEP_UUID = uuid.UUID("99999999-8888-7777-6666-555544443333")
EVIDENCE_UUID_1 = uuid.UUID("ee000001-0000-0000-0000-000000000001")
EVIDENCE_UUID_2 = uuid.UUID("ee000002-0000-0000-0000-000000000002")
OPP_UUID_1 = uuid.UUID("00000001-0001-0001-0001-000000000001")
SCORE_UUID_1 = uuid.UUID("55000001-0000-0000-0000-000000000001")
SCORE_UUID_2 = uuid.UUID("55000002-0000-0000-0000-000000000002")

OBS_DATE = date(2025, 3, 31)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context_output(
    *,
    company_name: str = "Infosys Ltd",
    industry_name: str | None = "IT Services",
    nse_symbol: str | None = "INFY",
) -> LoadGrowthContextOutput:
    return LoadGrowthContextOutput(
        company_name=company_name,
        industry_name=industry_name,
        nse_symbol=nse_symbol,
        bse_code=None,
        company_findings=[],
        industry_findings=[],
        moat_context=None,
        management_statements=[],
        existing_opportunities=[],
    )


def _make_source_candidate(
    source_id: str = "filing-1",
    source_type: DocumentType = DocumentType.FILING,
    provider: str = "corporate_filings",
) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        source_type=source_type,
        provider=provider,
        title="Test Document",
        publication_date=OBS_DATE,
        source_tier=SourceTier.TIER_1,
        url=f"https://example.com/{source_id}",
    )


def _make_doc_output(content: str = "test content") -> RetrieveDocumentOutput:
    return RetrieveDocumentOutput(
        content=content,
        content_type="text/plain",
        content_hash="abc123hash",
        filing_id="filing-1",
    )


def _make_evidence(
    claim: str = "Revenue grew 15% YoY",
    evidence_type: EvidenceType = EvidenceType.FACT,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> ExtractedEvidence:
    return ExtractedEvidence(
        evidence_type=evidence_type,
        claim=claim,
        context=None,
        page_or_section=None,
        confidence=confidence,
    )


def _make_opportunity_draft(
    name: str = "Cloud Expansion",
    category: str = "NEW_PRODUCT",
    maturity: str = "EARLY_STAGE",
    addressable_market: Decimal | None = Decimal("5000"),
    tam_methodology: str | None = "Top-down industry sizing",
    evidence_indices: list[int] | None = None,
) -> GrowthOpportunityDraft:
    return GrowthOpportunityDraft(
        opportunity_name=name,
        category=category,
        maturity=maturity,
        addressable_market=addressable_market,
        tam_methodology=tam_methodology,
        tam_low=Decimal("3000") if addressable_market else None,
        tam_high=Decimal("7000") if addressable_market else None,
        timeline_years=3,
        confidence="MEDIUM",
        evidence_indices=evidence_indices if evidence_indices is not None else [0],
        risks=["Execution risk"],
        rationale="Strong growth potential based on evidence",
    )


def _make_score_component(
    name: str = "Revenue growth",
    score: int = 65,
) -> GrowthScoreComponent:
    return GrowthScoreComponent(
        component_name=name,
        score=score,
        rationale="Based on evidence",
        evidence_indices=[0],
    )


def _make_finding(
    content: str = "Revenue grew 15% YoY",
    finding_type: FindingType = FindingType.FACT,
    category: str = "growth_opportunity",
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> FindingItem:
    return FindingItem(
        agent_name=GROWTH_AGENT_NAME,
        finding_type=finding_type,
        category=category,
        content=content,
        confidence=confidence,
    )


def _make_llm_response(data: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        content=json.dumps(data),
        model="test-model",
        usage=ProviderTokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        finish_reason="stop",
    )


def _make_run_mock() -> ResearchRun:
    run = MagicMock(spec=ResearchRun)
    run.id = RUN_UUID
    return run


def _make_step_mock(step_name: str = "context_load") -> ResearchRunStep:
    step = MagicMock(spec=ResearchRunStep)
    step.id = STEP_UUID
    step.step_name = step_name
    return step


def _make_exec_mock() -> AgentExecution:
    ex = MagicMock(spec=AgentExecution)
    ex.id = EXEC_UUID
    return ex


def _build_agent() -> tuple[FutureGrowthAgent, dict[str, AsyncMock]]:
    session = AsyncMock()
    run_service = AsyncMock()
    search = AsyncMock()
    news = AsyncMock()
    corporate_filings = AsyncMock()
    llm = AsyncMock()

    agent = FutureGrowthAgent(
        session=session,
        run_service=run_service,
        search=search,
        news=news,
        corporate_filings=corporate_filings,
        llm=llm,
    )

    return agent, {
        "session": session,
        "run_service": run_service,
        "search": search,
        "news": news,
        "corporate_filings": corporate_filings,
        "llm": llm,
    }


# ===========================================================================
# 1. Agent construction / dependency injection
# ===========================================================================


class TestAgentConstruction:
    def test_constructor_accepts_all_providers(self) -> None:
        agent, _ = _build_agent()
        assert isinstance(agent, FutureGrowthAgent)

    def test_agent_has_tools(self) -> None:
        agent, _ = _build_agent()
        assert hasattr(agent, "_tools")

    def test_agent_has_llm(self) -> None:
        agent, _ = _build_agent()
        assert hasattr(agent, "_llm")

    def test_agent_has_run_service(self) -> None:
        agent, _ = _build_agent()
        assert hasattr(agent, "_run_service")


# ===========================================================================
# 2. Constants and contracts
# ===========================================================================


class TestConstants:
    def test_agent_name(self) -> None:
        assert GROWTH_AGENT_NAME == "future_growth_agent"

    def test_run_type(self) -> None:
        assert GROWTH_AGENT_RUN_TYPE == "future_growth"

    def test_token_budget(self) -> None:
        assert GROWTH_AGENT_TOKEN_BUDGET == 20_000

    def test_token_warning(self) -> None:
        assert GROWTH_AGENT_TOKEN_WARNING == 16_000

    def test_research_steps_count(self) -> None:
        assert len(GROWTH_RESEARCH_STEPS) == 7

    def test_research_steps_order(self) -> None:
        for i, step in enumerate(GROWTH_RESEARCH_STEPS, start=1):
            assert step.step_order == i

    def test_step_names(self) -> None:
        names = [s.step_name for s in GROWTH_RESEARCH_STEPS]
        assert names == [
            "context_load",
            "source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "growth_analysis",
            "growth_validation",
            "growth_challenge",
        ]

    def test_llm_steps(self) -> None:
        llm_steps = [s for s in GROWTH_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        assert {s.step_name for s in llm_steps} == {
            "evidence_extraction",
            "growth_analysis",
            "growth_challenge",
        }

    def test_india_themes(self) -> None:
        assert len(INDIA_STRUCTURAL_THEMES) == 10
        assert "artificial_intelligence" in INDIA_STRUCTURAL_THEMES

    def test_default_config(self) -> None:
        config = FutureGrowthConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == 2

    def test_result_model_frozen(self) -> None:
        result = FutureGrowthResult(
            status="COMPLETED",
            run_id=RUN_UUID,
        )
        assert result.model_config.get("frozen") is True


# ===========================================================================
# 3. LLM response parsing
# ===========================================================================


class TestParsing:
    def test_parse_evidence_extraction_valid(self) -> None:
        data = {
            "evidences": [
                {
                    "evidence_type": "FACT",
                    "claim": "Revenue was 100cr",
                    "context": None,
                    "page_or_section": None,
                    "confidence": "HIGH",
                },
            ],
        }
        response = _make_llm_response(data)
        result = _parse_evidence_extraction_response(response)
        assert len(result.evidences) == 1
        assert result.evidences[0].claim == "Revenue was 100cr"

    def test_parse_evidence_extraction_invalid_json(self) -> None:
        response = LLMResponse(
            content="not json",
            model="test",
            usage=ProviderTokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_evidence_extraction_response(response)

    def test_parse_growth_analysis_valid(self) -> None:
        data = {
            "opportunities": [],
            "growth_quality_scores": [],
            "future_optionality_scores": [],
            "growth_vs_optionality_separation": "test",
            "themes_identified": [],
            "findings": [],
        }
        response = _make_llm_response(data)
        result = _parse_growth_analysis_response(response)
        assert result.growth_vs_optionality_separation == "test"

    def test_parse_growth_analysis_invalid(self) -> None:
        response = LLMResponse(
            content="{}",
            model="test",
            usage=ProviderTokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_growth_analysis_response(response)

    def test_parse_growth_challenge_valid(self) -> None:
        data = {
            "challenges": [],
            "overall_optimism_assessment": "balanced",
            "findings": [],
        }
        response = _make_llm_response(data)
        result = _parse_growth_challenge_response(response)
        assert result.overall_optimism_assessment == "balanced"

    def test_parse_growth_challenge_invalid(self) -> None:
        response = LLMResponse(
            content='{"bad": true}',
            model="test",
            usage=ProviderTokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_growth_challenge_response(response)


# ===========================================================================
# 4. Deterministic validation (MV-01 through MV-10)
# ===========================================================================


class TestValidation:
    """Tests for _validate_growth and its sub-functions."""

    def test_mv01_no_evidence_downgrades_to_speculative(self) -> None:
        opp = _make_opportunity_draft(maturity="EARLY_STAGE", evidence_indices=[])
        validated, _, _, result, _ = _validate_growth([opp], [], [], [], [])
        assert validated[0].maturity == "SPECULATIVE"
        assert not result.passed
        mv01 = [i for i in result.issues if i.check_id == "MV-01"]
        assert len(mv01) == 1
        assert len(result.downgraded_maturities) == 1

    def test_mv01_speculative_stays_speculative(self) -> None:
        opp = _make_opportunity_draft(maturity="SPECULATIVE", evidence_indices=[])
        validated, _, _, result, _ = _validate_growth([opp], [], [], [], [])
        assert validated[0].maturity == "SPECULATIVE"
        mv01 = [i for i in result.issues if i.check_id == "MV-01"]
        assert len(mv01) == 0

    def test_mv02_proven_without_fact_revenue_downgrades(self) -> None:
        evidence = [
            _make_evidence(
                claim="Revenue grew to 500cr according to management",
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
            ),
        ]
        opp = _make_opportunity_draft(maturity="PROVEN", evidence_indices=[0])
        validated, _, _, result, _ = _validate_growth([opp], [], [], evidence, [EVIDENCE_UUID_1])
        assert validated[0].maturity == "COMMERCIALIZING"
        mv02 = [i for i in result.issues if i.check_id == "MV-02"]
        assert len(mv02) == 1

    def test_mv02_proven_with_fact_revenue_passes(self) -> None:
        evidence = [
            _make_evidence(
                claim="Revenue from cloud services was 500cr",
                evidence_type=EvidenceType.FACT,
            ),
        ]
        opp = _make_opportunity_draft(maturity="PROVEN", evidence_indices=[0])
        validated, _, _, result, _ = _validate_growth([opp], [], [], evidence, [EVIDENCE_UUID_1])
        assert validated[0].maturity == "PROVEN"

    def test_mv03_commercializing_without_revenue_downgrades(self) -> None:
        evidence = [
            _make_evidence(
                claim="New plant commissioned",
                evidence_type=EvidenceType.FACT,
            ),
        ]
        opp = _make_opportunity_draft(maturity="COMMERCIALIZING", evidence_indices=[0])
        validated, _, _, result, _ = _validate_growth([opp], [], [], evidence, [EVIDENCE_UUID_1])
        assert validated[0].maturity == "EARLY_STAGE"
        mv03 = [i for i in result.issues if i.check_id == "MV-03"]
        assert len(mv03) == 1

    def test_mv03_commercializing_with_revenue_passes(self) -> None:
        evidence = [
            _make_evidence(
                claim="Initial sales revenue of 50cr from new product",
                evidence_type=EvidenceType.FACT,
            ),
        ]
        opp = _make_opportunity_draft(maturity="COMMERCIALIZING", evidence_indices=[0])
        validated, _, _, result, _ = _validate_growth([opp], [], [], evidence, [EVIDENCE_UUID_1])
        assert validated[0].maturity == "COMMERCIALIZING"

    def test_mv05_tam_without_methodology_nullifies(self) -> None:
        opp = _make_opportunity_draft(
            addressable_market=Decimal("5000"),
            tam_methodology=None,
            evidence_indices=[0],
        )
        validated, _, _, result, _ = _validate_growth([opp], [], [], [_make_evidence()], [EVIDENCE_UUID_1])
        assert validated[0].addressable_market is None
        assert validated[0].tam_methodology is None
        mv05 = [i for i in result.issues if i.check_id == "MV-05"]
        assert len(mv05) >= 1
        assert len(result.nullified_tams) == 1

    def test_mv05_tam_low_greater_than_high_nullifies(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="NEW_PRODUCT",
            maturity="EARLY_STAGE",
            addressable_market=Decimal("5000"),
            tam_methodology="Top-down",
            tam_low=Decimal("8000"),
            tam_high=Decimal("3000"),
            timeline_years=3,
            confidence="MEDIUM",
            evidence_indices=[0],
            risks=[],
            rationale="Test",
        )
        validated, _, _, result, _ = _validate_growth([opp], [], [], [_make_evidence()], [EVIDENCE_UUID_1])
        assert validated[0].addressable_market is None
        mv05 = [i for i in result.issues if i.check_id == "MV-05"]
        assert len(mv05) == 1

    def test_mv06_invalid_category_rejected(self) -> None:
        opp = _make_opportunity_draft(evidence_indices=[0])
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="INVALID_CATEGORY",
            maturity="EARLY_STAGE",
            confidence="MEDIUM",
            evidence_indices=[0],
            risks=[],
            rationale="Test",
        )
        validated, _, _, result, _ = _validate_growth([opp], [], [], [_make_evidence()], [EVIDENCE_UUID_1])
        assert len(validated) == 0
        mv06 = [i for i in result.issues if i.check_id == "MV-06"]
        assert len(mv06) == 1

    def test_mv07_invalid_maturity_rejected(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="NEW_PRODUCT",
            maturity="INVALID_MATURITY",
            confidence="MEDIUM",
            evidence_indices=[0],
            risks=[],
            rationale="Test",
        )
        validated, _, _, result, _ = _validate_growth([opp], [], [], [_make_evidence()], [EVIDENCE_UUID_1])
        assert len(validated) == 0
        mv07 = [i for i in result.issues if i.check_id == "MV-07"]
        assert len(mv07) == 1

    def test_mv08_score_clamped_to_range(self) -> None:
        score_over = GrowthScoreComponent.model_construct(
            component_name="Revenue growth",
            score=150,
            rationale="Based on evidence",
            evidence_indices=[0],
        )
        score_under = GrowthScoreComponent.model_construct(
            component_name="Under",
            score=-10,
            rationale="Based on evidence",
            evidence_indices=[0],
        )
        issues: list[GrowthValidationIssue] = []

        clamped = _clamp_scores([score_over, score_under], issues, "test")
        assert clamped[0].score == 100
        assert clamped[1].score == 0
        assert len(issues) == 2
        assert all(i.check_id == "MV-08" for i in issues)

    def test_mv08_valid_score_unchanged(self) -> None:
        score = _make_score_component(score=75)
        issues: list[GrowthValidationIssue] = []
        clamped = _clamp_scores([score], issues, "test")
        assert clamped[0].score == 75
        assert len(issues) == 0

    def test_mv10_negative_tam_nullified(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="NEW_PRODUCT",
            maturity="EARLY_STAGE",
            addressable_market=Decimal("-100"),
            tam_methodology="Test method",
            tam_low=None,
            tam_high=None,
            timeline_years=3,
            confidence="MEDIUM",
            evidence_indices=[0],
            risks=[],
            rationale="Test",
        )
        validated, _, _, result, _ = _validate_growth([opp], [], [], [_make_evidence()], [EVIDENCE_UUID_1])
        assert validated[0].addressable_market is None
        mv10 = [i for i in result.issues if i.check_id == "MV-10"]
        assert len(mv10) == 1

    def test_validation_passes_clean_data(self) -> None:
        evidence = [
            _make_evidence(claim="Revenue grew 15%", evidence_type=EvidenceType.FACT),
        ]
        opp = _make_opportunity_draft(evidence_indices=[0])
        gq = [_make_score_component(score=65)]
        fo = [_make_score_component(name="Optionality", score=50)]

        validated, clamped_gq, clamped_fo, result, _ = _validate_growth([opp], gq, fo, evidence, [EVIDENCE_UUID_1])
        assert result.passed is True
        assert len(validated) == 1
        assert len(clamped_gq) == 1
        assert len(clamped_fo) == 1


# ===========================================================================
# 5. Helper functions
# ===========================================================================


class TestHelpers:
    def test_has_fact_revenue_evidence_true(self) -> None:
        evidence = [
            _make_evidence(claim="Revenue was 500cr", evidence_type=EvidenceType.FACT),
        ]
        assert _has_fact_revenue_evidence([0], evidence) is True

    def test_has_fact_revenue_evidence_false_no_revenue_keyword(self) -> None:
        evidence = [
            _make_evidence(claim="New plant built", evidence_type=EvidenceType.FACT),
        ]
        assert _has_fact_revenue_evidence([0], evidence) is False

    def test_has_fact_revenue_evidence_false_wrong_type(self) -> None:
        evidence = [
            _make_evidence(
                claim="Revenue guidance of 1000cr",
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
            ),
        ]
        assert _has_fact_revenue_evidence([0], evidence) is False

    def test_has_fact_revenue_with_financial_data_type(self) -> None:
        evidence = [
            _make_evidence(
                claim="Sales turnover increased to 800cr",
                evidence_type=EvidenceType.FINANCIAL_DATA,
            ),
        ]
        assert _has_fact_revenue_evidence([0], evidence) is True

    def test_has_revenue_evidence_true(self) -> None:
        evidence = [
            _make_evidence(claim="Initial sales of 10cr"),
        ]
        assert _has_revenue_evidence([0], evidence) is True

    def test_has_revenue_evidence_false(self) -> None:
        evidence = [
            _make_evidence(claim="Capacity addition planned"),
        ]
        assert _has_revenue_evidence([0], evidence) is False

    def test_has_revenue_evidence_commercializing_keyword(self) -> None:
        evidence = [
            _make_evidence(claim="Product commercialisation has begun"),
        ]
        assert _has_revenue_evidence([0], evidence) is True

    def test_replace_maturity(self) -> None:
        opp = _make_opportunity_draft(maturity="PROVEN")
        replaced = _replace_maturity(opp, "SPECULATIVE")
        assert replaced.maturity == "SPECULATIVE"
        assert replaced.opportunity_name == opp.opportunity_name
        assert replaced.category == opp.category

    def test_compute_dimension_score(self) -> None:
        components = [
            _make_score_component(score=60),
            _make_score_component(name="B", score=80),
        ]
        assert _compute_dimension_score(components) == 70

    def test_compute_dimension_score_empty(self) -> None:
        assert _compute_dimension_score([]) is None

    def test_compute_dimension_score_single(self) -> None:
        assert _compute_dimension_score([_make_score_component(score=55)]) == 55


# ===========================================================================
# 6. Step runner unit tests
# ===========================================================================


class TestStepRunnerDeterministic:
    @pytest.mark.asyncio
    async def test_deterministic_step_success(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock()
        rs = mocks["run_service"]
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()

        async def _coro() -> str:
            return "ok"

        result = await agent._run_step_deterministic(step, _coro())
        assert result == "ok"
        rs.start_step.assert_awaited_once_with(STEP_UUID)
        rs.complete_step.assert_awaited_once_with(STEP_UUID)

    @pytest.mark.asyncio
    async def test_deterministic_step_failure(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock()
        rs = mocks["run_service"]
        rs.start_step = AsyncMock()
        rs.fail_step = AsyncMock()

        async def _failing() -> str:
            raise ValueError("boom")

        with pytest.raises(StepFailedError):
            await agent._run_step_deterministic(step, _failing())
        rs.fail_step.assert_awaited_once()


class TestStepRunnerLLM:
    @pytest.mark.asyncio
    async def test_llm_step_success_first_attempt(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock("evidence_extraction")
        rs = mocks["run_service"]
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.complete_agent = AsyncMock()

        config = FutureGrowthConfig()
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)

        call_count = 0

        async def fn(exec_id: uuid.UUID) -> str:
            nonlocal call_count
            call_count += 1
            return "result"

        result = await agent._run_step_llm(step, RUN_UUID, budget, config, fn)
        assert result == "result"
        assert call_count == 1
        rs.complete_agent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_step_retries_on_parsing_error(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock("growth_analysis")
        rs = mocks["run_service"]
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.retry_step = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.complete_agent = AsyncMock()
        rs.fail_agent = AsyncMock()

        config = FutureGrowthConfig()
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)

        call_count = 0

        async def fn(exec_id: uuid.UUID) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMParsingError("test", "bad json")
            return "ok"

        result = await agent._run_step_llm(step, RUN_UUID, budget, config, fn)
        assert result == "ok"
        assert call_count == 2
        rs.retry_step.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_step_fails_after_max_attempts(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock("growth_analysis")
        rs = mocks["run_service"]
        rs.start_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.retry_step = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.fail_agent = AsyncMock()

        config = FutureGrowthConfig()
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)

        async def fn(exec_id: uuid.UUID) -> str:
            raise LLMParsingError("test", "always fails")

        with pytest.raises(StepFailedError):
            await agent._run_step_llm(step, RUN_UUID, budget, config, fn)

    @pytest.mark.asyncio
    async def test_llm_step_skips_when_budget_exhausted(self) -> None:
        agent, mocks = _build_agent()
        step = _make_step_mock("growth_challenge")
        rs = mocks["run_service"]
        rs.skip_step = AsyncMock()

        config = FutureGrowthConfig()
        budget = TokenBudget(budget=100, warning_threshold=80)
        budget.record_usage(60, 60)

        async def fn(exec_id: uuid.UUID) -> str:
            return "nope"

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(step, RUN_UUID, budget, config, fn)
        rs.skip_step.assert_awaited_once()


# ===========================================================================
# 7. Full happy-path execution
# ===========================================================================


class TestFullExecution:
    @pytest.mark.asyncio
    async def test_happy_path_returns_completed(self) -> None:
        agent, mocks = _build_agent()
        rs = mocks["run_service"]
        llm = mocks["llm"]

        rs.initiate_run = AsyncMock(return_value=_make_run_mock())
        rs.create_steps = AsyncMock(
            return_value=[
                _make_step_mock("context_load"),
                _make_step_mock("source_discovery"),
                _make_step_mock("document_retrieval"),
                _make_step_mock("evidence_extraction"),
                _make_step_mock("growth_analysis"),
                _make_step_mock("growth_validation"),
                _make_step_mock("growth_challenge"),
            ]
        )
        rs.enqueue_run = AsyncMock()
        rs.start_run = AsyncMock()
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.complete_run = AsyncMock()
        rs.update_run_aggregates = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.complete_agent = AsyncMock()
        rs.record_source_access = AsyncMock()

        context = _make_context_output()
        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new=AsyncMock(return_value=context),
            ),
            patch.object(
                agent._tools,
                "discover_growth_sources",
                new=AsyncMock(
                    return_value=DiscoverGrowthSourcesOutput(
                        sources=[_make_source_candidate()],
                        provider_errors=[],
                    )
                ),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new=AsyncMock(return_value=_make_doc_output()),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new=AsyncMock(return_value=DOC_UUID),
            ),
            patch.object(
                agent._tools,
                "persist_evidence",
                new=AsyncMock(return_value=PersistEvidenceOutput(evidence_ids=[EVIDENCE_UUID_1])),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new=AsyncMock(
                    return_value=PersistFindingsOutput(
                        finding_ids=[uuid.uuid4()],
                        rejected=[],
                    )
                ),
            ),
            patch.object(
                agent._tools,
                "persist_growth_opportunities",
                new=AsyncMock(return_value=PersistGrowthOpportunitiesOutput(opportunity_ids=[OPP_UUID_1])),
            ),
            patch.object(
                agent._tools,
                "persist_scores",
                new=AsyncMock(
                    return_value=PersistGrowthScoresOutput(
                        growth_quality_score_id=SCORE_UUID_1,
                        future_optionality_score_id=SCORE_UUID_2,
                    )
                ),
            ),
        ):
            evidence_data = {
                "evidences": [
                    {
                        "evidence_type": "FACT",
                        "claim": "Revenue grew 15% to 500cr",
                        "context": None,
                        "page_or_section": None,
                        "confidence": "HIGH",
                    },
                ],
            }
            analysis_data = {
                "opportunities": [
                    {
                        "opportunity_name": "Cloud Expansion",
                        "category": "NEW_PRODUCT",
                        "maturity": "EARLY_STAGE",
                        "addressable_market": "5000",
                        "tam_methodology": "Top-down",
                        "tam_low": "3000",
                        "tam_high": "7000",
                        "timeline_years": 3,
                        "confidence": "MEDIUM",
                        "evidence_indices": [0],
                        "risks": ["Execution risk"],
                        "rationale": "Strong potential",
                    },
                ],
                "growth_quality_scores": [
                    {
                        "component_name": "Revenue growth",
                        "score": 65,
                        "rationale": "Good track record",
                        "evidence_indices": [0],
                    },
                ],
                "future_optionality_scores": [
                    {
                        "component_name": "Platform potential",
                        "score": 55,
                        "rationale": "Emerging",
                        "evidence_indices": [0],
                    },
                ],
                "growth_vs_optionality_separation": "Quality vs upside",
                "themes_identified": ["artificial_intelligence"],
                "findings": [
                    {
                        "finding_type": "AI_INFERENCE",
                        "category": "growth_opportunity",
                        "content": "Growth is real",
                        "confidence": "MEDIUM",
                        "source_publication_date": None,
                    },
                ],
            }
            challenge_data = {
                "challenges": [],
                "overall_optimism_assessment": "balanced",
                "findings": [
                    {
                        "finding_type": "AI_INFERENCE",
                        "category": "growth_challenge",
                        "content": "Execution risk",
                        "confidence": "MEDIUM",
                        "source_publication_date": None,
                    },
                ],
            }

            llm.generate = AsyncMock(
                side_effect=[
                    _make_llm_response(evidence_data),
                    _make_llm_response(analysis_data),
                    _make_llm_response(challenge_data),
                ]
            )

            request = FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBS_DATE,
                initiated_by="test",
            )
            result = await agent.execute(request)

        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert result.steps_completed == 7
        assert result.steps_total == 7
        assert len(result.opportunities) == 1
        assert result.growth_quality_score == 65
        assert result.future_optionality_score == 55
        assert result.findings_count > 0
        assert result.evidence_count > 0
        rs.complete_run.assert_awaited_once()


# ===========================================================================
# 8. Error handling and partial completion
# ===========================================================================


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_step_failure_early_returns_failed(self) -> None:
        agent, mocks = _build_agent()
        rs = mocks["run_service"]

        rs.initiate_run = AsyncMock(return_value=_make_run_mock())
        rs.create_steps = AsyncMock(
            return_value=[
                _make_step_mock(n)
                for n in [
                    "context_load",
                    "source_discovery",
                    "document_retrieval",
                    "evidence_extraction",
                    "growth_analysis",
                    "growth_validation",
                    "growth_challenge",
                ]
            ]
        )
        rs.enqueue_run = AsyncMock()
        rs.start_run = AsyncMock()
        rs.start_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.fail_run = AsyncMock()
        rs.update_run_aggregates = AsyncMock()

        with patch.object(
            agent._tools,
            "load_company_context",
            new=AsyncMock(side_effect=ValueError("company not found")),
        ):
            request = FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBS_DATE,
                initiated_by="test",
            )
            result = await agent.execute(request)

        assert result.status == "FAILED"
        assert result.steps_completed == 0

    @pytest.mark.asyncio
    async def test_step_failure_late_returns_partial(self) -> None:
        agent, mocks = _build_agent()
        rs = mocks["run_service"]

        rs.initiate_run = AsyncMock(return_value=_make_run_mock())
        steps = [
            _make_step_mock(n)
            for n in [
                "context_load",
                "source_discovery",
                "document_retrieval",
                "evidence_extraction",
                "growth_analysis",
                "growth_validation",
                "growth_challenge",
            ]
        ]
        rs.create_steps = AsyncMock(return_value=steps)
        rs.enqueue_run = AsyncMock()
        rs.start_run = AsyncMock()
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.partial_run = AsyncMock()
        rs.update_run_aggregates = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.complete_agent = AsyncMock()
        rs.fail_agent = AsyncMock()
        rs.retry_step = AsyncMock()
        rs.record_source_access = AsyncMock()

        context = _make_context_output()
        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new=AsyncMock(return_value=context),
            ),
            patch.object(
                agent._tools,
                "discover_growth_sources",
                new=AsyncMock(
                    return_value=DiscoverGrowthSourcesOutput(
                        sources=[_make_source_candidate()],
                        provider_errors=[],
                    )
                ),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new=AsyncMock(return_value=_make_doc_output()),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new=AsyncMock(return_value=DOC_UUID),
            ),
            patch.object(
                agent._tools,
                "persist_evidence",
                new=AsyncMock(return_value=PersistEvidenceOutput(evidence_ids=[EVIDENCE_UUID_1])),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new=AsyncMock(return_value=PersistFindingsOutput(finding_ids=[], rejected=[])),
            ),
            patch.object(
                agent._tools,
                "persist_growth_opportunities",
                new=AsyncMock(return_value=PersistGrowthOpportunitiesOutput(opportunity_ids=[OPP_UUID_1])),
            ),
            patch.object(
                agent._tools,
                "persist_scores",
                new=AsyncMock(
                    return_value=PersistGrowthScoresOutput(
                        growth_quality_score_id=SCORE_UUID_1,
                        future_optionality_score_id=SCORE_UUID_2,
                    )
                ),
            ),
        ):
            evidence_data = {
                "evidences": [
                    {
                        "evidence_type": "FACT",
                        "claim": "Revenue was 100cr",
                        "context": None,
                        "page_or_section": None,
                        "confidence": "HIGH",
                    }
                ],
            }
            analysis_data = {
                "opportunities": [
                    {
                        "opportunity_name": "Test",
                        "category": "NEW_PRODUCT",
                        "maturity": "EARLY_STAGE",
                        "addressable_market": "5000",
                        "tam_methodology": "Top-down",
                        "tam_low": "3000",
                        "tam_high": "7000",
                        "timeline_years": 3,
                        "confidence": "MEDIUM",
                        "evidence_indices": [0],
                        "risks": [],
                        "rationale": "Test",
                    }
                ],
                "growth_quality_scores": [
                    {"component_name": "G", "score": 50, "rationale": "ok", "evidence_indices": [0]}
                ],
                "future_optionality_scores": [
                    {"component_name": "F", "score": 40, "rationale": "ok", "evidence_indices": [0]}
                ],
                "growth_vs_optionality_separation": "test",
                "themes_identified": [],
                "findings": [],
            }

            mocks["llm"].generate = AsyncMock(
                side_effect=[
                    _make_llm_response(evidence_data),
                    _make_llm_response(analysis_data),
                    LLMParsingError("growth_challenge", "fail"),
                    LLMParsingError("growth_challenge", "fail"),
                ]
            )

            request = FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBS_DATE,
                initiated_by="test",
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"
        assert result.steps_completed >= 5

    @pytest.mark.asyncio
    async def test_token_budget_exhaustion_returns_partial(self) -> None:
        agent, mocks = _build_agent()
        rs = mocks["run_service"]

        rs.initiate_run = AsyncMock(return_value=_make_run_mock())
        steps = [
            _make_step_mock(n)
            for n in [
                "context_load",
                "source_discovery",
                "document_retrieval",
                "evidence_extraction",
                "growth_analysis",
                "growth_validation",
                "growth_challenge",
            ]
        ]
        rs.create_steps = AsyncMock(return_value=steps)
        rs.enqueue_run = AsyncMock()
        rs.start_run = AsyncMock()
        rs.start_step = AsyncMock()
        rs.complete_step = AsyncMock()
        rs.fail_step = AsyncMock()
        rs.skip_step = AsyncMock()
        rs.partial_run = AsyncMock()
        rs.update_run_aggregates = AsyncMock()
        rs.record_agent_execution = AsyncMock(return_value=_make_exec_mock())
        rs.complete_agent = AsyncMock()
        rs.fail_agent = AsyncMock()
        rs.record_source_access = AsyncMock()

        context = _make_context_output()

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new=AsyncMock(return_value=context),
            ),
            patch.object(
                agent._tools,
                "discover_growth_sources",
                new=AsyncMock(
                    return_value=DiscoverGrowthSourcesOutput(
                        sources=[_make_source_candidate()],
                        provider_errors=[],
                    )
                ),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new=AsyncMock(return_value=_make_doc_output()),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new=AsyncMock(return_value=DOC_UUID),
            ),
            patch.object(
                agent._tools,
                "persist_evidence",
                new=AsyncMock(return_value=PersistEvidenceOutput(evidence_ids=[EVIDENCE_UUID_1])),
            ),
        ):
            evidence_data = {
                "evidences": [
                    {
                        "evidence_type": "FACT",
                        "claim": "Revenue 100cr",
                        "context": None,
                        "page_or_section": None,
                        "confidence": "HIGH",
                    }
                ],
            }

            async def _generate_exhaust(*args: Any, **kwargs: Any) -> LLMResponse:
                return LLMResponse(
                    content=json.dumps(evidence_data),
                    model="test",
                    usage=ProviderTokenUsage(input_tokens=15000, output_tokens=10000, total_tokens=25000),
                    finish_reason="stop",
                )

            mocks["llm"].generate = AsyncMock(side_effect=_generate_exhaust)

            request = FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBS_DATE,
                initiated_by="test",
                configuration=FutureGrowthConfig(
                    token_budget=100,
                    token_warning_threshold=80,
                ),
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"


# ===========================================================================
# 9. Token budget
# ===========================================================================


class TestTokenBudget:
    def test_budget_initialization(self) -> None:
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)
        assert budget.budget == 20_000
        assert budget.warning_threshold == 16_000
        assert budget.total_tokens == 0
        assert budget.is_exhausted is False
        assert budget.is_warning is False

    def test_budget_warning(self) -> None:
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)
        budget.record_usage(10_000, 7_000)
        assert budget.is_warning is True
        assert budget.is_exhausted is False

    def test_budget_exhaustion(self) -> None:
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)
        budget.record_usage(12_000, 10_000)
        assert budget.is_exhausted is True


# ===========================================================================
# 10. Validation result model
# ===========================================================================


class TestValidationResult:
    def test_result_frozen(self) -> None:
        result = GrowthValidationResult(passed=True)
        assert result.model_config.get("frozen") is True

    def test_result_with_issues(self) -> None:
        issue = GrowthValidationIssue(
            check_id="MV-01",
            severity="ERROR",
            opportunity_name="Test",
            message="No evidence",
        )
        result = GrowthValidationResult(
            passed=False,
            issues=[issue],
            downgraded_maturities=[("Test", "EARLY_STAGE", "SPECULATIVE")],
            nullified_tams=["Test"],
        )
        assert len(result.issues) == 1
        assert len(result.downgraded_maturities) == 1
        assert len(result.nullified_tams) == 1


# ===========================================================================
# 11. MV-04 and MV-09 (finding type validation)
# ===========================================================================


class TestFindingTypeValidation:
    """MV-04 and MV-09 are enforced at the prompt level and by
    persist_findings category validation. The validation step
    focuses on opportunities and scores. These tests verify
    that the agent's prompts instruct correct classification
    and the persist layer rejects invalid categories.
    """

    def test_finding_item_accepts_valid_types(self) -> None:
        for ft in ("FACT", "AI_INFERENCE", "MANAGEMENT_CLAIM", "ASSUMPTION"):
            item = FindingItem(
                agent_name=GROWTH_AGENT_NAME,
                finding_type=FindingType(ft),
                category="growth_opportunity",
                content="Test",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert item.finding_type.value == ft


# ===========================================================================
# 12. Dual scoring
# ===========================================================================


class TestDualScoring:
    def test_both_dimensions_computed(self) -> None:
        gq = [_make_score_component(score=60), _make_score_component(name="B", score=80)]
        fo = [_make_score_component(name="C", score=40)]
        gq_score = _compute_dimension_score(gq)
        fo_score = _compute_dimension_score(fo)
        assert gq_score == 70
        assert fo_score == 40

    def test_score_output_contract(self) -> None:
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=65,
            future_optionality_score=55,
            growth_quality_components=[_make_score_component(score=65)],
            future_optionality_components=[_make_score_component(name="Opt", score=55)],
        )
        assert inp.growth_quality_score == 65
        assert inp.future_optionality_score == 55


# ===========================================================================
# 13. Multiple validation issues
# ===========================================================================


class TestMultipleValidationIssues:
    def test_multiple_opportunities_validated(self) -> None:
        evidence = [_make_evidence(claim="Revenue was 100cr", evidence_type=EvidenceType.FACT)]
        opp_good = _make_opportunity_draft(name="Good", evidence_indices=[0])
        opp_bad_category = GrowthOpportunityDraft(
            opportunity_name="Bad Category",
            category="INVALID",
            maturity="EARLY_STAGE",
            confidence="MEDIUM",
            evidence_indices=[0],
            risks=[],
            rationale="Test",
        )
        opp_no_evidence = _make_opportunity_draft(
            name="No Evidence",
            maturity="PROVEN",
            evidence_indices=[],
        )

        validated, _, _, result, _ = _validate_growth(
            [opp_good, opp_bad_category, opp_no_evidence],
            [],
            [],
            evidence,
            [EVIDENCE_UUID_1],
        )
        assert len(validated) == 2
        assert validated[0].opportunity_name == "Good"
        assert validated[1].opportunity_name == "No Evidence"
        assert validated[1].maturity == "SPECULATIVE"
        assert not result.passed

    def test_cascading_maturity_downgrade(self) -> None:
        evidence = [
            _make_evidence(
                claim="Management announced expansion",
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
            )
        ]
        opp = _make_opportunity_draft(name="Cascade", maturity="PROVEN", evidence_indices=[0])
        validated, _, _, result, _ = _validate_growth([opp], [], [], evidence, [EVIDENCE_UUID_1])
        # MV-02: PROVEN → COMMERCIALIZING (no FACT-type revenue evidence)
        # MV-03: COMMERCIALIZING → EARLY_STAGE (no revenue keyword in claim)
        assert validated[0].maturity == "EARLY_STAGE"
        assert len(result.downgraded_maturities) == 2
        assert result.downgraded_maturities[0] == ("Cascade", "PROVEN", "COMMERCIALIZING")
        assert result.downgraded_maturities[1] == ("Cascade", "COMMERCIALIZING", "EARLY_STAGE")


# ===========================================================================
# 14. MV-04 — Forward-looking FACT → AI_INFERENCE reclassification
# ===========================================================================


class TestMV04ForwardLookingFactReclassification:
    """MV-04: No forward-looking finding may have FindingType.FACT.
    Forward-looking categories must be reclassified to AI_INFERENCE."""

    def test_forward_looking_fact_reclassified_to_ai_inference(self) -> None:
        for cat in _FORWARD_LOOKING_CATEGORIES:
            finding = _make_finding(
                content="TAM estimated at 5000cr",
                finding_type=FindingType.FACT,
                category=cat,
            )
            issues: list[GrowthValidationIssue] = []
            result = _validate_findings([finding], issues)
            assert len(result) == 1
            assert result[0].finding_type == FindingType.AI_INFERENCE
            assert len(issues) == 1
            assert issues[0].check_id == "MV-04"
            assert issues[0].severity == "ERROR"

    def test_non_forward_looking_fact_unchanged(self) -> None:
        non_forward = [c for c in GROWTH_FINDING_CATEGORIES if c not in _FORWARD_LOOKING_CATEGORIES]
        for cat in non_forward:
            finding = _make_finding(
                content="Revenue was 1000cr in FY24",
                finding_type=FindingType.FACT,
                category=cat,
            )
            issues: list[GrowthValidationIssue] = []
            result = _validate_findings([finding], issues)
            assert result[0].finding_type == FindingType.FACT
            assert len(issues) == 0

    def test_forward_looking_ai_inference_unchanged(self) -> None:
        finding = _make_finding(
            content="Growth trajectory looks strong",
            finding_type=FindingType.AI_INFERENCE,
            category="growth_trajectory",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.AI_INFERENCE
        assert len(issues) == 0

    def test_forward_looking_assumption_unchanged(self) -> None:
        finding = _make_finding(
            content="Assuming TAM grows at 10% CAGR",
            finding_type=FindingType.ASSUMPTION,
            category="tam_estimate",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.ASSUMPTION
        assert len(issues) == 0

    def test_mv04_issue_records_category(self) -> None:
        finding = _make_finding(
            content="Theme alignment expected",
            finding_type=FindingType.FACT,
            category="theme_alignment",
        )
        issues: list[GrowthValidationIssue] = []
        _validate_findings([finding], issues)
        assert "theme_alignment" in issues[0].message

    def test_mv04_preserves_all_fields(self) -> None:
        finding = FindingItem(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="growth_risk",
            content="Risk assessment content",
            confidence=ConfidenceLevel.HIGH,
            observation_date=OBS_DATE,
            source_publication_date=OBS_DATE,
            evidence_ids=[EVIDENCE_UUID_1],
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        corrected = result[0]
        assert corrected.finding_type == FindingType.AI_INFERENCE
        assert corrected.agent_name == "test_agent"
        assert corrected.category == "growth_risk"
        assert corrected.content == "Risk assessment content"
        assert corrected.confidence == ConfidenceLevel.HIGH
        assert corrected.observation_date == OBS_DATE
        assert corrected.evidence_ids == [EVIDENCE_UUID_1]

    def test_multiple_forward_looking_facts_all_reclassified(self) -> None:
        findings = [
            _make_finding(finding_type=FindingType.FACT, category="growth_opportunity"),
            _make_finding(finding_type=FindingType.FACT, category="tam_estimate"),
            _make_finding(finding_type=FindingType.FACT, category="growth_challenge"),
        ]
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings(findings, issues)
        assert all(f.finding_type == FindingType.AI_INFERENCE for f in result)
        assert len(issues) == 3
        assert all(i.check_id == "MV-04" for i in issues)


# ===========================================================================
# 15. MV-09 — Management-claim language reclassification
# ===========================================================================


class TestMV09ManagementClaimReclassification:
    """MV-09: Findings containing management-claim language must not be
    classified as FACT or CALCULATION. Reclassify to MANAGEMENT_CLAIM."""

    def test_management_guided_in_fact_reclassified(self) -> None:
        finding = _make_finding(
            content="Management guided for 20% revenue growth in FY25",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM
        assert len(issues) == 1
        assert issues[0].check_id == "MV-09"

    def test_management_expects_in_calculation_reclassified(self) -> None:
        finding = _make_finding(
            content="Management expects EBITDA margin to expand 200bps",
            finding_type=FindingType.CALCULATION,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM
        assert len(issues) == 1
        assert issues[0].check_id == "MV-09"

    def test_according_to_management_reclassified(self) -> None:
        finding = _make_finding(
            content="According to management, capex will be Rs 500cr",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_all_management_indicators_detected(self) -> None:
        indicators = [
            "management guided",
            "management expects",
            "management stated",
            "management announced",
            "management plans",
            "according to management",
            "management indicated",
            "management projected",
            "management commentary",
            "management believes",
        ]
        for indicator in indicators:
            finding = _make_finding(
                content=f"The company: {indicator} a 15% growth target",
                finding_type=FindingType.FACT,
                category="management_growth_claim",
            )
            issues: list[GrowthValidationIssue] = []
            result = _validate_findings([finding], issues)
            assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM, f"Indicator '{indicator}' not detected"

    def test_contextual_guidance_of_with_management(self) -> None:
        finding = _make_finding(
            content="Management provided guidance of 20% revenue growth for FY26",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_contextual_guided_for_with_management(self) -> None:
        finding = _make_finding(
            content="Management guided for a 15% increase in EBITDA margins",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_no_management_language_fact_unchanged(self) -> None:
        finding = _make_finding(
            content="Revenue grew 15% YoY to Rs 1000cr in FY24",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.FACT
        assert len(issues) == 0

    def test_management_language_in_ai_inference_unchanged(self) -> None:
        finding = _make_finding(
            content="Management guided for 20% growth, which seems aggressive",
            finding_type=FindingType.AI_INFERENCE,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.AI_INFERENCE
        assert len(issues) == 0

    def test_management_language_in_management_claim_unchanged(self) -> None:
        finding = _make_finding(
            content="Management guided for 20% growth",
            finding_type=FindingType.MANAGEMENT_CLAIM,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM
        assert len(issues) == 0

    def test_case_insensitive_detection(self) -> None:
        finding = _make_finding(
            content="MANAGEMENT GUIDED for 20% revenue growth",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_mv09_preserves_all_fields(self) -> None:
        finding = FindingItem(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
            content="Management guided for expansion",
            confidence=ConfidenceLevel.LOW,
            observation_date=OBS_DATE,
            source_publication_date=OBS_DATE,
            evidence_ids=[EVIDENCE_UUID_1, EVIDENCE_UUID_2],
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        corrected = result[0]
        assert corrected.finding_type == FindingType.MANAGEMENT_CLAIM
        assert corrected.agent_name == "test_agent"
        assert corrected.category == "management_growth_claim"
        assert corrected.content == "Management guided for expansion"
        assert corrected.confidence == ConfidenceLevel.LOW
        assert corrected.evidence_ids == [EVIDENCE_UUID_1, EVIDENCE_UUID_2]


# ===========================================================================
# 16. MV-04 + MV-09 interaction
# ===========================================================================


class TestMV04MV09Interaction:
    """When a forward-looking finding with FACT type also contains
    management-claim language, MV-04 fires first (FACT → AI_INFERENCE),
    then MV-09 should NOT fire because AI_INFERENCE is not FACT/CALCULATION."""

    def test_mv04_fires_first_prevents_mv09(self) -> None:
        finding = _make_finding(
            content="Management guided for growth in new markets",
            finding_type=FindingType.FACT,
            category="growth_trajectory",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.AI_INFERENCE
        assert len(issues) == 1
        assert issues[0].check_id == "MV-04"

    def test_non_forward_looking_management_claim_gets_mv09(self) -> None:
        finding = _make_finding(
            content="Management expects revenue to grow 20%",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM
        assert len(issues) == 1
        assert issues[0].check_id == "MV-09"

    def test_mixed_findings_independent_rules(self) -> None:
        findings = [
            _make_finding(
                content="TAM is large",
                finding_type=FindingType.FACT,
                category="tam_estimate",
            ),
            _make_finding(
                content="Management guided for 30% capex increase",
                finding_type=FindingType.CALCULATION,
                category="management_growth_claim",
            ),
            _make_finding(
                content="Revenue was Rs 500cr in FY24",
                finding_type=FindingType.FACT,
                category="management_growth_claim",
            ),
        ]
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings(findings, issues)
        assert result[0].finding_type == FindingType.AI_INFERENCE  # MV-04
        assert result[1].finding_type == FindingType.MANAGEMENT_CLAIM  # MV-09
        assert result[2].finding_type == FindingType.FACT  # unchanged
        assert len(issues) == 2


# ===========================================================================
# 17. _validate_findings edge cases
# ===========================================================================


class TestValidateFindingsEdgeCases:
    def test_empty_findings_returns_empty(self) -> None:
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([], issues)
        assert result == []
        assert len(issues) == 0

    def test_findings_without_issues_pass_through(self) -> None:
        findings = [
            _make_finding(finding_type=FindingType.AI_INFERENCE, category="growth_opportunity"),
            _make_finding(finding_type=FindingType.ASSUMPTION, category="tam_estimate"),
            _make_finding(finding_type=FindingType.MANAGEMENT_CLAIM, category="management_growth_claim"),
        ]
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings(findings, issues)
        assert len(result) == 3
        assert result[0].finding_type == FindingType.AI_INFERENCE
        assert result[1].finding_type == FindingType.ASSUMPTION
        assert result[2].finding_type == FindingType.MANAGEMENT_CLAIM
        assert len(issues) == 0

    def test_issues_list_accumulates_across_findings(self) -> None:
        findings = [
            _make_finding(finding_type=FindingType.FACT, category="growth_opportunity"),
            _make_finding(finding_type=FindingType.FACT, category="tam_estimate"),
        ]
        issues: list[GrowthValidationIssue] = []
        _validate_findings(findings, issues)
        assert len(issues) == 2

    def test_pre_existing_issues_preserved(self) -> None:
        issues: list[GrowthValidationIssue] = [
            GrowthValidationIssue(
                check_id="MV-01",
                severity="ERROR",
                opportunity_name="Test",
                message="Pre-existing issue",
            ),
        ]
        finding = _make_finding(finding_type=FindingType.FACT, category="growth_opportunity")
        _validate_findings([finding], issues)
        assert len(issues) == 2
        assert issues[0].check_id == "MV-01"
        assert issues[1].check_id == "MV-04"

    def test_uncertainty_type_passes_through(self) -> None:
        finding = _make_finding(
            content="Uncertain outlook for growth",
            finding_type=FindingType.UNCERTAINTY,
            category="growth_risk",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.UNCERTAINTY
        assert len(issues) == 0


# ===========================================================================
# 18. _validate_growth integration with findings parameter
# ===========================================================================


class TestValidateGrowthWithFindings:
    def test_validate_growth_accepts_findings_parameter(self) -> None:
        evidence = [_make_evidence()]
        opp = _make_opportunity_draft(evidence_indices=[0])
        findings = [
            _make_finding(finding_type=FindingType.FACT, category="growth_opportunity"),
        ]
        validated, _, _, result, corrected_findings = _validate_growth(
            [opp],
            [],
            [],
            evidence,
            [EVIDENCE_UUID_1],
            findings=findings,
        )
        assert len(validated) == 1
        assert len(corrected_findings) == 1
        assert corrected_findings[0].finding_type == FindingType.AI_INFERENCE

    def test_validate_growth_no_findings_returns_empty(self) -> None:
        evidence = [_make_evidence()]
        opp = _make_opportunity_draft(evidence_indices=[0])
        validated, _, _, result, corrected_findings = _validate_growth(
            [opp],
            [],
            [],
            evidence,
            [EVIDENCE_UUID_1],
        )
        assert corrected_findings == []

    def test_validate_growth_finding_issues_in_result(self) -> None:
        evidence = [_make_evidence()]
        opp = _make_opportunity_draft(evidence_indices=[0])
        findings = [
            _make_finding(finding_type=FindingType.FACT, category="tam_estimate"),
        ]
        _, _, _, result, _ = _validate_growth(
            [opp],
            [],
            [],
            evidence,
            [EVIDENCE_UUID_1],
            findings=findings,
        )
        mv04_issues = [i for i in result.issues if i.check_id == "MV-04"]
        assert len(mv04_issues) == 1


# ===========================================================================
# 19. _FORWARD_LOOKING_CATEGORIES constant
# ===========================================================================


class TestForwardLookingCategories:
    def test_forward_looking_categories_are_subset_of_growth_finding_categories(self) -> None:
        assert _FORWARD_LOOKING_CATEGORIES <= GROWTH_FINDING_CATEGORIES

    def test_forward_looking_categories_non_empty(self) -> None:
        assert len(_FORWARD_LOOKING_CATEGORIES) >= 4

    def test_expected_categories_present(self) -> None:
        expected = {"growth_opportunity", "tam_estimate", "growth_trajectory", "growth_challenge"}
        assert expected <= _FORWARD_LOOKING_CATEGORIES


# ===========================================================================
# 20. TD-39 — MV-09 false-positive regression tests
# ===========================================================================


class TestMV09FalsePositiveRegression:
    """Verify TD-39 hardening: 'guidance of' and 'guided for' no longer
    produce false positives without management context."""

    def test_central_bank_guidance_not_reclassified(self) -> None:
        finding = _make_finding(
            content="Under the guidance of the central bank, interest rates were kept stable",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.FACT
        assert len(issues) == 0

    def test_analyst_guided_for_not_reclassified(self) -> None:
        finding = _make_finding(
            content="The analyst guided for a P/E of 25x based on peer comparison",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.FACT
        assert len(issues) == 0

    def test_regulatory_guidance_not_reclassified(self) -> None:
        finding = _make_finding(
            content="SEBI issued guidance of stricter disclosure norms",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.FACT
        assert len(issues) == 0

    def test_rbi_guided_for_not_reclassified(self) -> None:
        finding = _make_finding(
            content="RBI guided for a cautious approach to lending growth",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.FACT
        assert len(issues) == 0

    def test_management_guidance_of_reclassified(self) -> None:
        finding = _make_finding(
            content="The management gave guidance of 18-20% growth for next fiscal year",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_management_guided_for_reclassified(self) -> None:
        finding = _make_finding(
            content="Management guided for margin expansion of 200bps in H2",
            finding_type=FindingType.FACT,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_management_guidance_case_insensitive(self) -> None:
        finding = _make_finding(
            content="MANAGEMENT provided GUIDANCE OF 25% revenue growth",
            finding_type=FindingType.CALCULATION,
            category="management_growth_claim",
        )
        issues: list[GrowthValidationIssue] = []
        result = _validate_findings([finding], issues)
        assert result[0].finding_type == FindingType.MANAGEMENT_CLAIM

    def test_has_management_claim_language_direct_positive(self) -> None:
        assert _has_management_claim_language("Management expects 20% growth")
        assert _has_management_claim_language("according to management, revenue will grow")

    def test_has_management_claim_language_direct_negative(self) -> None:
        assert not _has_management_claim_language("Revenue grew 20% in FY24")
        assert not _has_management_claim_language("Under the guidance of RBI")

    def test_has_management_claim_language_contextual_positive(self) -> None:
        assert _has_management_claim_language("Management provided guidance of 20% growth")
        assert _has_management_claim_language("The management team guided for 15% CAGR")

    def test_has_management_claim_language_contextual_negative(self) -> None:
        assert not _has_management_claim_language("The analyst guided for a P/E of 25x")
        assert not _has_management_claim_language("Under the guidance of central bank norms")
