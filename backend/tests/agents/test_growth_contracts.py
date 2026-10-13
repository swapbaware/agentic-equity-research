"""Comprehensive tests for Phase 12.1 Future Growth & Optionality Agent contracts."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.agents.contracts import (
    GROWTH_AGENT_NAME,
    GROWTH_AGENT_RUN_TYPE,
    GROWTH_AGENT_TOKEN_BUDGET,
    GROWTH_AGENT_TOKEN_WARNING,
    GROWTH_CATEGORY_TO_FINDING_CATEGORY,
    GROWTH_FINDING_CATEGORIES,
    GROWTH_RESEARCH_STEPS,
    INDIA_STRUCTURAL_THEMES,
    MAX_LLM_ATTEMPTS,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    DiscoverGrowthSourcesInput,
    DiscoverGrowthSourcesOutput,
    FindingItem,
    FindingSummary,
    FutureGrowthConfig,
    FutureGrowthResearchRequest,
    FutureGrowthResult,
    GrowthAnalysisOutput,
    GrowthChallengeItem,
    GrowthChallengeOutput,
    GrowthOpportunityDraft,
    GrowthScoreComponent,
    GrowthValidationIssue,
    GrowthValidationResult,
    LoadGrowthContextInput,
    LoadGrowthContextOutput,
    ManagementStatementSummary,
    PersistGrowthOpportunitiesInput,
    PersistGrowthOpportunitiesOutput,
    PersistGrowthScoresInput,
    PersistGrowthScoresOutput,
    SourceCandidate,
    TokenBudget,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    FindingType,
    GrowthCategory,
    GrowthMaturity,
    ManagementStatementCategory,
    ManagementStatementStatus,
    SourceTier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
EVIDENCE_UUID = uuid.UUID("fedcbafe-dcba-fedc-bafe-dcbafedcbafe")
FINDING_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
OPP_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SCORE_UUID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
SCORE_UUID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ===========================================================================
# Constants
# ===========================================================================


class TestGrowthConstants:
    def test_growth_agent_token_budget(self) -> None:
        assert GROWTH_AGENT_TOKEN_BUDGET == 20_000

    def test_growth_agent_token_warning(self) -> None:
        assert GROWTH_AGENT_TOKEN_WARNING == 16_000

    def test_warning_is_80_percent(self) -> None:
        assert int(GROWTH_AGENT_TOKEN_BUDGET * 0.8) == GROWTH_AGENT_TOKEN_WARNING

    def test_growth_agent_name(self) -> None:
        assert GROWTH_AGENT_NAME == "future_growth_agent"

    def test_growth_agent_run_type(self) -> None:
        assert GROWTH_AGENT_RUN_TYPE == "future_growth"

    def test_max_llm_attempts_shared(self) -> None:
        assert MAX_LLM_ATTEMPTS == 2


# ===========================================================================
# GROWTH_FINDING_CATEGORIES
# ===========================================================================


class TestGrowthFindingCategories:
    def test_is_frozenset(self) -> None:
        assert isinstance(GROWTH_FINDING_CATEGORIES, frozenset)

    def test_has_14_categories(self) -> None:
        assert len(GROWTH_FINDING_CATEGORIES) == 14

    def test_growth_specific_categories(self) -> None:
        growth_specific = {
            "growth_opportunity",
            "growth_quality",
            "future_optionality",
            "tam_estimate",
            "growth_trajectory",
            "theme_alignment",
            "management_growth_claim",
            "growth_risk",
            "growth_challenge",
            "maturity_classification",
            "growth_score_rationale",
            "optionality_score_rationale",
        }
        assert growth_specific <= GROWTH_FINDING_CATEGORIES

    def test_cross_cutting_categories(self) -> None:
        cross_cutting = {"research_gap", "contradiction"}
        assert cross_cutting <= GROWTH_FINDING_CATEGORIES

    def test_complete_set(self) -> None:
        expected = frozenset(
            {
                "growth_opportunity",
                "growth_quality",
                "future_optionality",
                "tam_estimate",
                "growth_trajectory",
                "theme_alignment",
                "management_growth_claim",
                "growth_risk",
                "growth_challenge",
                "maturity_classification",
                "growth_score_rationale",
                "optionality_score_rationale",
                "research_gap",
                "contradiction",
            }
        )
        assert expected == GROWTH_FINDING_CATEGORIES


# ===========================================================================
# INDIA_STRUCTURAL_THEMES
# ===========================================================================


class TestIndiaStructuralThemes:
    def test_is_tuple(self) -> None:
        assert isinstance(INDIA_STRUCTURAL_THEMES, tuple)

    def test_has_10_themes(self) -> None:
        assert len(INDIA_STRUCTURAL_THEMES) == 10

    def test_contains_key_themes(self) -> None:
        assert "artificial_intelligence" in INDIA_STRUCTURAL_THEMES
        assert "data_centres" in INDIA_STRUCTURAL_THEMES
        assert "semiconductors" in INDIA_STRUCTURAL_THEMES
        assert "defence_indigenisation" in INDIA_STRUCTURAL_THEMES
        assert "electric_vehicles" in INDIA_STRUCTURAL_THEMES
        assert "renewable_energy" in INDIA_STRUCTURAL_THEMES
        assert "pharma_innovation" in INDIA_STRUCTURAL_THEMES
        assert "digital_payments" in INDIA_STRUCTURAL_THEMES
        assert "manufacturing_pli" in INDIA_STRUCTURAL_THEMES
        assert "infrastructure" in INDIA_STRUCTURAL_THEMES

    def test_no_duplicates(self) -> None:
        assert len(INDIA_STRUCTURAL_THEMES) == len(set(INDIA_STRUCTURAL_THEMES))

    def test_all_snake_case(self) -> None:
        for theme in INDIA_STRUCTURAL_THEMES:
            assert theme == theme.lower()
            assert " " not in theme


# ===========================================================================
# GROWTH_CATEGORY_TO_FINDING_CATEGORY
# ===========================================================================


class TestGrowthCategoryToFindingCategory:
    def test_covers_all_7_growth_categories(self) -> None:
        assert set(GROWTH_CATEGORY_TO_FINDING_CATEGORY.keys()) == set(GrowthCategory)

    def test_7_entries(self) -> None:
        assert len(GROWTH_CATEGORY_TO_FINDING_CATEGORY) == 7

    def test_all_map_to_growth_opportunity(self) -> None:
        for category in GROWTH_CATEGORY_TO_FINDING_CATEGORY.values():
            assert category == "growth_opportunity"

    def test_all_values_in_finding_categories(self) -> None:
        for category in GROWTH_CATEGORY_TO_FINDING_CATEGORY.values():
            assert category in GROWTH_FINDING_CATEGORIES


# ===========================================================================
# FutureGrowthConfig
# ===========================================================================


class TestFutureGrowthConfig:
    def test_defaults(self) -> None:
        config = FutureGrowthConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == 2
        assert config.source_limit == 20
        assert config.max_documents == 8
        assert config.concurrent_retrievals == 5
        assert config.max_opportunities == 15
        assert config.extraction_model is None
        assert config.analysis_model is None
        assert config.challenge_model is None

    def test_custom_values(self) -> None:
        config = FutureGrowthConfig(
            token_budget=15_000,
            token_warning_threshold=12_000,
            max_llm_attempts=1,
            source_limit=10,
            max_documents=5,
            concurrent_retrievals=3,
            max_opportunities=10,
            extraction_model="haiku",
            analysis_model="sonnet",
            challenge_model="opus",
        )
        assert config.token_budget == 15_000
        assert config.max_llm_attempts == 1
        assert config.max_documents == 5
        assert config.max_opportunities == 10
        assert config.challenge_model == "opus"

    def test_frozen(self) -> None:
        config = FutureGrowthConfig()
        with pytest.raises(ValidationError):
            config.token_budget = 50_000  # type: ignore[misc]

    def test_token_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(token_budget=0)

    def test_max_llm_attempts_max_is_3(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(max_llm_attempts=4)

    def test_source_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(source_limit=0)
        with pytest.raises(ValidationError):
            FutureGrowthConfig(source_limit=101)

    def test_concurrent_retrievals_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(concurrent_retrievals=0)
        with pytest.raises(ValidationError):
            FutureGrowthConfig(concurrent_retrievals=21)

    def test_max_opportunities_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(max_opportunities=0)
        with pytest.raises(ValidationError):
            FutureGrowthConfig(max_opportunities=51)

    def test_max_documents_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthConfig(max_documents=0)
        with pytest.raises(ValidationError):
            FutureGrowthConfig(max_documents=31)


# ===========================================================================
# FutureGrowthResearchRequest
# ===========================================================================


class TestFutureGrowthResearchRequest:
    def test_valid_request(self) -> None:
        req = FutureGrowthResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="test_user",
        )
        assert req.company_id == COMPANY_UUID
        assert req.observation_date == date(2025, 9, 30)
        assert req.initiated_by == "test_user"
        assert req.configuration is None

    def test_with_configuration(self) -> None:
        config = FutureGrowthConfig(token_budget=15_000)
        req = FutureGrowthResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
            initiated_by="system",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.token_budget == 15_000

    def test_frozen(self) -> None:
        req = FutureGrowthResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        with pytest.raises(ValidationError):
            req.initiated_by = "other"  # type: ignore[misc]

    def test_empty_initiated_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="",
            )

    def test_long_initiated_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FutureGrowthResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="x" * 201,
            )


# ===========================================================================
# FutureGrowthResult
# ===========================================================================


class TestFutureGrowthResult:
    def test_completed(self) -> None:
        result = FutureGrowthResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            opportunities=[OPP_UUID],
            findings_count=25,
            evidence_count=15,
            growth_quality_score=72,
            future_optionality_score=65,
            steps_completed=7,
        )
        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert len(result.opportunities) == 1
        assert result.growth_quality_score == 72
        assert result.future_optionality_score == 65
        assert result.steps_completed == 7
        assert result.steps_total == 7
        assert result.errors == []

    def test_partial(self) -> None:
        result = FutureGrowthResult(
            status="PARTIAL",
            run_id=RUN_UUID,
            opportunities=[OPP_UUID],
            findings_count=10,
            evidence_count=5,
            steps_completed=5,
            errors=["Token budget exhausted"],
        )
        assert result.status == "PARTIAL"
        assert result.growth_quality_score is None
        assert result.future_optionality_score is None
        assert len(result.errors) == 1

    def test_failed(self) -> None:
        result = FutureGrowthResult(
            status="FAILED",
            run_id=RUN_UUID,
            errors=["Step 1 failed: company not found"],
        )
        assert result.status == "FAILED"
        assert result.opportunities == []
        assert result.findings_count == 0
        assert result.evidence_count == 0

    def test_frozen(self) -> None:
        result = FutureGrowthResult(status="COMPLETED", run_id=RUN_UUID)
        with pytest.raises(ValidationError):
            result.status = "FAILED"  # type: ignore[misc]

    def test_defaults(self) -> None:
        result = FutureGrowthResult(status="COMPLETED", run_id=RUN_UUID)
        assert result.opportunities == []
        assert result.findings_count == 0
        assert result.evidence_count == 0
        assert result.growth_quality_score is None
        assert result.future_optionality_score is None
        assert result.validation_result is None
        assert result.steps_completed == 0
        assert result.steps_total == 7
        assert result.token_usage is None
        assert result.errors == []

    def test_with_validation_result(self) -> None:
        validation = GrowthValidationResult(passed=True)
        result = FutureGrowthResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            validation_result=validation,
        )
        assert result.validation_result is not None
        assert result.validation_result.passed is True

    def test_with_token_usage(self) -> None:
        budget = TokenBudget(
            budget=GROWTH_AGENT_TOKEN_BUDGET,
            warning_threshold=GROWTH_AGENT_TOKEN_WARNING,
            input_tokens=10_000,
            output_tokens=5_000,
        )
        result = FutureGrowthResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            token_usage=budget,
        )
        assert result.token_usage is not None
        assert result.token_usage.total_tokens == 15_000


# ===========================================================================
# LoadGrowthContextInput / Output
# ===========================================================================


class TestLoadGrowthContextInput:
    def test_valid(self) -> None:
        inp = LoadGrowthContextInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            observation_date=date(2025, 9, 30),
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.research_run_id == RUN_UUID
        assert inp.observation_date == date(2025, 9, 30)

    def test_frozen(self) -> None:
        inp = LoadGrowthContextInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            observation_date=date(2025, 9, 30),
        )
        with pytest.raises(ValidationError):
            inp.company_id = uuid.uuid4()  # type: ignore[misc]


class TestLoadGrowthContextOutput:
    def test_minimal(self) -> None:
        out = LoadGrowthContextOutput(company_name="Infosys Ltd")
        assert out.company_name == "Infosys Ltd"
        assert out.industry_name is None
        assert out.nse_symbol is None
        assert out.bse_code is None
        assert out.company_findings == []
        assert out.industry_findings == []
        assert out.moat_context is None
        assert out.management_statements == []
        assert out.existing_opportunities == []

    def test_full(self) -> None:
        finding = FindingSummary(
            finding_id=FINDING_UUID,
            category="business_model",
            finding_type=FindingType.FACT,
            content="IT services company",
            confidence=ConfidenceLevel.HIGH,
        )
        stmt = ManagementStatementSummary(
            id=uuid.uuid4(),
            statement_date=date(2025, 6, 1),
            statement="We will invest in AI capabilities",
            category=ManagementStatementCategory.EXPANSION,
            status=ManagementStatementStatus.PENDING,
        )
        out = LoadGrowthContextOutput(
            company_name="Infosys Ltd",
            industry_name="IT Services",
            nse_symbol="INFY",
            bse_code="500209",
            company_findings=[finding],
            industry_findings=[finding],
            moat_context="Strong brand moat with MODERATE strength",
            management_statements=[stmt],
            existing_opportunities=[OPP_UUID],
        )
        assert out.nse_symbol == "INFY"
        assert len(out.company_findings) == 1
        assert len(out.management_statements) == 1
        assert len(out.existing_opportunities) == 1

    def test_frozen(self) -> None:
        out = LoadGrowthContextOutput(company_name="Test")
        with pytest.raises(ValidationError):
            out.company_name = "Other"  # type: ignore[misc]


# ===========================================================================
# DiscoverGrowthSourcesInput / Output
# ===========================================================================


class TestDiscoverGrowthSourcesInput:
    def test_valid(self) -> None:
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Ltd",
            industry_name="IT Services",
            nse_symbol="INFY",
            observation_date=date(2025, 9, 30),
            search_themes=["artificial_intelligence", "digital_payments"],
        )
        assert inp.company_name == "Infosys Ltd"
        assert len(inp.search_themes) == 2

    def test_defaults(self) -> None:
        inp = DiscoverGrowthSourcesInput(
            company_name="Test Corp",
            observation_date=date(2025, 9, 30),
        )
        assert inp.industry_name is None
        assert inp.nse_symbol is None
        assert inp.search_themes == []

    def test_frozen(self) -> None:
        inp = DiscoverGrowthSourcesInput(
            company_name="Test",
            observation_date=date(2025, 9, 30),
        )
        with pytest.raises(ValidationError):
            inp.company_name = "Other"  # type: ignore[misc]


class TestDiscoverGrowthSourcesOutput:
    def test_empty(self) -> None:
        out = DiscoverGrowthSourcesOutput()
        assert out.sources == []
        assert out.provider_errors == []

    def test_with_sources(self) -> None:
        source = SourceCandidate(
            source_id="annual-report-2025",
            source_type=DocumentType.ANNUAL_REPORT,
            provider="corporate_filings",
            title="Annual Report FY2025",
            publication_date=date(2025, 6, 15),
            source_tier=SourceTier.TIER_1,
        )
        out = DiscoverGrowthSourcesOutput(sources=[source])
        assert len(out.sources) == 1
        assert out.sources[0].source_id == "annual-report-2025"

    def test_with_provider_errors(self) -> None:
        out = DiscoverGrowthSourcesOutput(
            provider_errors=["SearchProvider: timeout", "NewsProvider: 503"],
        )
        assert len(out.provider_errors) == 2

    def test_frozen(self) -> None:
        out = DiscoverGrowthSourcesOutput()
        with pytest.raises(ValidationError):
            out.sources = []  # type: ignore[misc]


# ===========================================================================
# GrowthOpportunityDraft
# ===========================================================================


class TestGrowthOpportunityDraft:
    def test_valid(self) -> None:
        draft = GrowthOpportunityDraft(
            opportunity_name="AI Services Expansion",
            category="NEW_PRODUCT",
            maturity="EARLY_STAGE",
            addressable_market=Decimal("50000.0000"),
            tam_methodology="Top-down from global AI services market",
            tam_low=Decimal("30000.0000"),
            tam_high=Decimal("80000.0000"),
            timeline_years=3,
            confidence="MEDIUM",
            evidence_indices=[0, 1, 3],
            risks=["Competitive pressure from large tech companies"],
            rationale="Company has invested in AI R&D and signed pilot customers",
        )
        assert draft.opportunity_name == "AI Services Expansion"
        assert draft.category == "NEW_PRODUCT"
        assert draft.maturity == "EARLY_STAGE"
        assert draft.addressable_market == Decimal("50000.0000")
        assert draft.tam_low == Decimal("30000.0000")
        assert draft.tam_high == Decimal("80000.0000")
        assert draft.timeline_years == 3
        assert len(draft.evidence_indices) == 3
        assert len(draft.risks) == 1

    def test_minimal(self) -> None:
        draft = GrowthOpportunityDraft(
            opportunity_name="Basic expansion",
            category="EXPANSION",
            maturity="SPECULATIVE",
            confidence="LOW",
            evidence_indices=[0],
            rationale="Speculative assessment based on limited evidence",
        )
        assert draft.addressable_market is None
        assert draft.tam_methodology is None
        assert draft.tam_low is None
        assert draft.tam_high is None
        assert draft.timeline_years is None
        assert draft.risks == []

    def test_frozen(self) -> None:
        draft = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="EXPANSION",
            maturity="SPECULATIVE",
            confidence="LOW",
            rationale="Test",
        )
        with pytest.raises(ValidationError):
            draft.maturity = "PROVEN"  # type: ignore[misc]

    def test_opportunity_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            GrowthOpportunityDraft(
                opportunity_name="x" * 501,
                category="EXPANSION",
                maturity="SPECULATIVE",
                confidence="LOW",
                rationale="Test",
            )

    def test_addressable_market_uses_decimal(self) -> None:
        draft = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="EXPANSION",
            maturity="SPECULATIVE",
            addressable_market=Decimal("12345.6789"),
            confidence="LOW",
            rationale="Test",
        )
        assert isinstance(draft.addressable_market, Decimal)
        assert draft.addressable_market == Decimal("12345.6789")

    def test_all_growth_categories_accepted(self) -> None:
        for cat in GrowthCategory:
            draft = GrowthOpportunityDraft(
                opportunity_name="Test",
                category=cat.value,
                maturity="SPECULATIVE",
                confidence="LOW",
                rationale="Test",
            )
            assert draft.category == cat.value

    def test_all_growth_maturities_accepted(self) -> None:
        for mat in GrowthMaturity:
            draft = GrowthOpportunityDraft(
                opportunity_name="Test",
                category="EXPANSION",
                maturity=mat.value,
                confidence="LOW",
                rationale="Test",
            )
            assert draft.maturity == mat.value


# ===========================================================================
# GrowthScoreComponent
# ===========================================================================


class TestGrowthScoreComponent:
    def test_valid(self) -> None:
        comp = GrowthScoreComponent(
            component_name="Revenue CAGR",
            score=75,
            rationale="3-year CAGR of 25% indicates strong growth",
            evidence_indices=[0, 2],
        )
        assert comp.component_name == "Revenue CAGR"
        assert comp.score == 75
        assert len(comp.evidence_indices) == 2

    def test_score_min_boundary(self) -> None:
        comp = GrowthScoreComponent(component_name="Test", score=0, rationale="No data")
        assert comp.score == 0

    def test_score_max_boundary(self) -> None:
        comp = GrowthScoreComponent(component_name="Test", score=100, rationale="Perfect")
        assert comp.score == 100

    def test_score_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthScoreComponent(component_name="Test", score=-1, rationale="Invalid")

    def test_score_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GrowthScoreComponent(component_name="Test", score=101, rationale="Invalid")

    def test_frozen(self) -> None:
        comp = GrowthScoreComponent(component_name="Test", score=50, rationale="Test")
        with pytest.raises(ValidationError):
            comp.score = 99  # type: ignore[misc]

    def test_default_evidence_indices(self) -> None:
        comp = GrowthScoreComponent(component_name="Test", score=50, rationale="Test")
        assert comp.evidence_indices == []


# ===========================================================================
# GrowthAnalysisOutput
# ===========================================================================


class TestGrowthAnalysisOutput:
    def test_valid(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="AI Expansion",
            category="NEW_PRODUCT",
            maturity="EARLY_STAGE",
            confidence="MEDIUM",
            rationale="Evidence supports early-stage AI initiative",
        )
        gq = GrowthScoreComponent(component_name="Revenue CAGR", score=70, rationale="Strong")
        fo = GrowthScoreComponent(component_name="Maturity Distribution", score=60, rationale="Decent")
        finding = FindingItem(
            agent_name=GROWTH_AGENT_NAME,
            finding_type=FindingType.AI_INFERENCE,
            category="growth_opportunity",
            content="AI services opportunity identified",
            confidence=ConfidenceLevel.MEDIUM,
        )
        output = GrowthAnalysisOutput(
            opportunities=[opp],
            growth_quality_scores=[gq],
            future_optionality_scores=[fo],
            growth_vs_optionality_separation="Current growth driven by IT services; optionality in AI",
            themes_identified=["artificial_intelligence"],
            findings=[finding],
        )
        assert len(output.opportunities) == 1
        assert len(output.growth_quality_scores) == 1
        assert len(output.future_optionality_scores) == 1
        assert output.growth_vs_optionality_separation != ""
        assert "artificial_intelligence" in output.themes_identified

    def test_empty_lists(self) -> None:
        output = GrowthAnalysisOutput(
            growth_vs_optionality_separation="No opportunities found",
        )
        assert output.opportunities == []
        assert output.growth_quality_scores == []
        assert output.future_optionality_scores == []
        assert output.themes_identified == []
        assert output.findings == []

    def test_frozen(self) -> None:
        output = GrowthAnalysisOutput(
            growth_vs_optionality_separation="Test",
        )
        with pytest.raises(ValidationError):
            output.growth_vs_optionality_separation = "Other"  # type: ignore[misc]


# ===========================================================================
# GrowthValidationIssue / GrowthValidationResult
# ===========================================================================


class TestGrowthValidationIssue:
    def test_valid(self) -> None:
        issue = GrowthValidationIssue(
            check_id="MV-01",
            severity="ERROR",
            opportunity_name="AI Expansion",
            message="No evidence linked to opportunity",
        )
        assert issue.check_id == "MV-01"
        assert issue.severity == "ERROR"
        assert issue.opportunity_name == "AI Expansion"
        assert issue.message != ""

    def test_without_opportunity_name(self) -> None:
        issue = GrowthValidationIssue(
            check_id="MV-08",
            severity="ERROR",
            message="Score out of range",
        )
        assert issue.opportunity_name is None

    def test_frozen(self) -> None:
        issue = GrowthValidationIssue(check_id="MV-01", severity="ERROR", message="Test")
        with pytest.raises(ValidationError):
            issue.check_id = "MV-02"  # type: ignore[misc]


class TestGrowthValidationResult:
    def test_passed(self) -> None:
        result = GrowthValidationResult(passed=True)
        assert result.passed is True
        assert result.issues == []
        assert result.downgraded_maturities == []
        assert result.nullified_tams == []

    def test_failed_with_issues(self) -> None:
        issues = [
            GrowthValidationIssue(
                check_id="MV-01",
                severity="ERROR",
                opportunity_name="AI Expansion",
                message="No evidence",
            ),
            GrowthValidationIssue(
                check_id="MV-04",
                severity="ERROR",
                message="Forward-looking FACT found",
            ),
        ]
        result = GrowthValidationResult(
            passed=False,
            issues=issues,
            downgraded_maturities=[("AI Expansion", "PROVEN", "SPECULATIVE")],
            nullified_tams=["Semiconductor Play"],
        )
        assert result.passed is False
        assert len(result.issues) == 2
        assert len(result.downgraded_maturities) == 1
        assert result.downgraded_maturities[0] == (
            "AI Expansion",
            "PROVEN",
            "SPECULATIVE",
        )
        assert "Semiconductor Play" in result.nullified_tams

    def test_frozen(self) -> None:
        result = GrowthValidationResult(passed=True)
        with pytest.raises(ValidationError):
            result.passed = False  # type: ignore[misc]


# ===========================================================================
# GrowthChallengeItem / GrowthChallengeOutput
# ===========================================================================


class TestGrowthChallengeItem:
    def test_valid(self) -> None:
        item = GrowthChallengeItem(
            opportunity_name="AI Expansion",
            challenge="Intense competition from global tech giants",
            tam_challenge="Global AI market estimates are highly speculative",
            competitive_risk="Google, Microsoft already dominant",
            execution_risk="Company lacks deep AI talent pool",
            revised_confidence="LOW",
            evidence_indices=[0, 2],
        )
        assert item.opportunity_name == "AI Expansion"
        assert item.challenge != ""
        assert item.tam_challenge is not None
        assert item.competitive_risk is not None
        assert item.execution_risk is not None
        assert item.revised_confidence == "LOW"

    def test_minimal(self) -> None:
        item = GrowthChallengeItem(
            opportunity_name="Test",
            challenge="Basic challenge",
        )
        assert item.tam_challenge is None
        assert item.competitive_risk is None
        assert item.execution_risk is None
        assert item.revised_confidence is None
        assert item.evidence_indices == []

    def test_frozen(self) -> None:
        item = GrowthChallengeItem(
            opportunity_name="Test",
            challenge="Test",
        )
        with pytest.raises(ValidationError):
            item.challenge = "Other"  # type: ignore[misc]


class TestGrowthChallengeOutput:
    def test_valid(self) -> None:
        challenge = GrowthChallengeItem(
            opportunity_name="AI Expansion",
            challenge="Competition is fierce",
        )
        finding = FindingItem(
            agent_name=GROWTH_AGENT_NAME,
            finding_type=FindingType.AI_INFERENCE,
            category="growth_challenge",
            content="AI expansion faces competitive headwinds",
            confidence=ConfidenceLevel.MEDIUM,
        )
        output = GrowthChallengeOutput(
            challenges=[challenge],
            overall_optimism_assessment="Analysis is moderately optimistic",
            findings=[finding],
        )
        assert len(output.challenges) == 1
        assert output.overall_optimism_assessment != ""
        assert len(output.findings) == 1

    def test_empty_challenges(self) -> None:
        output = GrowthChallengeOutput(
            overall_optimism_assessment="No non-SPECULATIVE opportunities to challenge",
        )
        assert output.challenges == []
        assert output.findings == []

    def test_frozen(self) -> None:
        output = GrowthChallengeOutput(
            overall_optimism_assessment="Test",
        )
        with pytest.raises(ValidationError):
            output.overall_optimism_assessment = "Other"  # type: ignore[misc]


# ===========================================================================
# PersistGrowthOpportunitiesInput / Output
# ===========================================================================


class TestPersistGrowthOpportunitiesInput:
    def test_valid(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="EXPANSION",
            maturity="SPECULATIVE",
            confidence="LOW",
            rationale="Test",
        )
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            opportunities=[opp],
            evidence_ids=[EVIDENCE_UUID],
        )
        assert inp.company_id == COMPANY_UUID
        assert len(inp.opportunities) == 1
        assert len(inp.evidence_ids) == 1

    def test_empty_opportunities_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistGrowthOpportunitiesInput(
                company_id=COMPANY_UUID,
                research_run_id=RUN_UUID,
                opportunities=[],
            )

    def test_frozen(self) -> None:
        opp = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="EXPANSION",
            maturity="SPECULATIVE",
            confidence="LOW",
            rationale="Test",
        )
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            opportunities=[opp],
        )
        with pytest.raises(ValidationError):
            inp.company_id = uuid.uuid4()  # type: ignore[misc]


class TestPersistGrowthOpportunitiesOutput:
    def test_valid(self) -> None:
        out = PersistGrowthOpportunitiesOutput(opportunity_ids=[OPP_UUID])
        assert len(out.opportunity_ids) == 1

    def test_frozen(self) -> None:
        out = PersistGrowthOpportunitiesOutput(opportunity_ids=[OPP_UUID])
        with pytest.raises(ValidationError):
            out.opportunity_ids = []  # type: ignore[misc]


# ===========================================================================
# PersistGrowthScoresInput / Output
# ===========================================================================


class TestPersistGrowthScoresInput:
    def test_valid(self) -> None:
        comp = GrowthScoreComponent(component_name="Revenue CAGR", score=70, rationale="Strong")
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=72,
            future_optionality_score=65,
            growth_quality_components=[comp],
            future_optionality_components=[comp],
        )
        assert inp.growth_quality_score == 72
        assert inp.future_optionality_score == 65
        assert len(inp.growth_quality_components) == 1

    def test_score_boundaries(self) -> None:
        inp_min = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=0,
            future_optionality_score=0,
        )
        assert inp_min.growth_quality_score == 0

        inp_max = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=100,
            future_optionality_score=100,
        )
        assert inp_max.growth_quality_score == 100

    def test_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistGrowthScoresInput(
                company_id=COMPANY_UUID,
                research_run_id=RUN_UUID,
                growth_quality_score=-1,
                future_optionality_score=50,
            )
        with pytest.raises(ValidationError):
            PersistGrowthScoresInput(
                company_id=COMPANY_UUID,
                research_run_id=RUN_UUID,
                growth_quality_score=50,
                future_optionality_score=101,
            )

    def test_frozen(self) -> None:
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=50,
            future_optionality_score=50,
        )
        with pytest.raises(ValidationError):
            inp.growth_quality_score = 99  # type: ignore[misc]

    def test_default_empty_components(self) -> None:
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            growth_quality_score=50,
            future_optionality_score=50,
        )
        assert inp.growth_quality_components == []
        assert inp.future_optionality_components == []


class TestPersistGrowthScoresOutput:
    def test_valid(self) -> None:
        out = PersistGrowthScoresOutput(
            growth_quality_score_id=SCORE_UUID_1,
            future_optionality_score_id=SCORE_UUID_2,
        )
        assert out.growth_quality_score_id == SCORE_UUID_1
        assert out.future_optionality_score_id == SCORE_UUID_2

    def test_frozen(self) -> None:
        out = PersistGrowthScoresOutput(
            growth_quality_score_id=SCORE_UUID_1,
            future_optionality_score_id=SCORE_UUID_2,
        )
        with pytest.raises(ValidationError):
            out.growth_quality_score_id = uuid.uuid4()  # type: ignore[misc]


# ===========================================================================
# GROWTH_RESEARCH_STEPS
# ===========================================================================


class TestGrowthResearchSteps:
    def test_is_tuple(self) -> None:
        assert isinstance(GROWTH_RESEARCH_STEPS, tuple)

    def test_has_7_steps(self) -> None:
        assert len(GROWTH_RESEARCH_STEPS) == 7

    def test_step_order_sequential(self) -> None:
        for i, step in enumerate(GROWTH_RESEARCH_STEPS, start=1):
            assert step.step_order == i

    def test_step_1_context_load(self) -> None:
        step = GROWTH_RESEARCH_STEPS[0]
        assert step.step_name == "context_load"
        assert step.step_type == STEP_TYPE_DETERMINISTIC
        assert step.timeout_seconds == 10
        assert step.uses_llm is False

    def test_step_2_source_discovery(self) -> None:
        step = GROWTH_RESEARCH_STEPS[1]
        assert step.step_name == "source_discovery"
        assert step.step_type == STEP_TYPE_PROVIDER_CALL
        assert step.timeout_seconds == 30
        assert step.uses_llm is False

    def test_step_3_document_retrieval(self) -> None:
        step = GROWTH_RESEARCH_STEPS[2]
        assert step.step_name == "document_retrieval"
        assert step.step_type == STEP_TYPE_PROVIDER_CALL
        assert step.timeout_seconds == 60
        assert step.uses_llm is False

    def test_step_4_evidence_extraction(self) -> None:
        step = GROWTH_RESEARCH_STEPS[3]
        assert step.step_name == "evidence_extraction"
        assert step.step_type == STEP_TYPE_LLM_REASONING
        assert step.timeout_seconds == 120
        assert step.uses_llm is True

    def test_step_5_growth_analysis(self) -> None:
        step = GROWTH_RESEARCH_STEPS[4]
        assert step.step_name == "growth_analysis"
        assert step.step_type == STEP_TYPE_LLM_REASONING
        assert step.timeout_seconds == 120
        assert step.uses_llm is True

    def test_step_6_growth_validation(self) -> None:
        step = GROWTH_RESEARCH_STEPS[5]
        assert step.step_name == "growth_validation"
        assert step.step_type == STEP_TYPE_DETERMINISTIC
        assert step.timeout_seconds == 10
        assert step.uses_llm is False

    def test_step_7_growth_challenge(self) -> None:
        step = GROWTH_RESEARCH_STEPS[6]
        assert step.step_name == "growth_challenge"
        assert step.step_type == STEP_TYPE_LLM_REASONING
        assert step.timeout_seconds == 120
        assert step.uses_llm is True

    def test_3_llm_steps(self) -> None:
        llm_steps = [s for s in GROWTH_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3

    def test_2_deterministic_steps(self) -> None:
        det_steps = [s for s in GROWTH_RESEARCH_STEPS if s.step_type == STEP_TYPE_DETERMINISTIC]
        assert len(det_steps) == 2

    def test_2_provider_call_steps(self) -> None:
        prov_steps = [s for s in GROWTH_RESEARCH_STEPS if s.step_type == STEP_TYPE_PROVIDER_CALL]
        assert len(prov_steps) == 2

    def test_all_steps_frozen(self) -> None:
        for step in GROWTH_RESEARCH_STEPS:
            with pytest.raises(ValidationError):
                step.step_name = "hacked"  # type: ignore[misc]


# ===========================================================================
# Acceptance Criteria verification
# ===========================================================================


class TestAcceptanceCriteria:
    """Verify Phase 12.1 acceptance criteria AC-01, AC-08, AC-16, AC-17."""

    def test_ac01_all_contracts_frozen(self) -> None:
        """AC-01: All new Pydantic contracts are frozen (immutable)."""
        frozen_models: list[type[BaseModel]] = [
            FutureGrowthConfig,
            FutureGrowthResearchRequest,
            FutureGrowthResult,
            LoadGrowthContextInput,
            LoadGrowthContextOutput,
            DiscoverGrowthSourcesInput,
            DiscoverGrowthSourcesOutput,
            GrowthOpportunityDraft,
            GrowthScoreComponent,
            GrowthAnalysisOutput,
            GrowthValidationIssue,
            GrowthValidationResult,
            GrowthChallengeItem,
            GrowthChallengeOutput,
            PersistGrowthOpportunitiesInput,
            PersistGrowthOpportunitiesOutput,
            PersistGrowthScoresInput,
            PersistGrowthScoresOutput,
        ]
        for model_cls in frozen_models:
            config = getattr(model_cls, "model_config", {})
            assert config.get("frozen") is True, f"{model_cls.__name__} is not frozen"

    def test_ac08_addressable_market_is_decimal(self) -> None:
        """AC-08: All financial values use Decimal (never float)."""
        draft = GrowthOpportunityDraft(
            opportunity_name="Test",
            category="EXPANSION",
            maturity="SPECULATIVE",
            addressable_market=Decimal("12345.6789"),
            tam_low=Decimal("10000.0000"),
            tam_high=Decimal("20000.0000"),
            confidence="LOW",
            rationale="Test",
        )
        assert isinstance(draft.addressable_market, Decimal)
        assert isinstance(draft.tam_low, Decimal)
        assert isinstance(draft.tam_high, Decimal)

    def test_ac16_token_budget_20000(self) -> None:
        """AC-16: Token budget initialized at 20,000."""
        assert GROWTH_AGENT_TOKEN_BUDGET == 20_000
        config = FutureGrowthConfig()
        assert config.token_budget == 20_000

    def test_ac17_agent_name(self) -> None:
        """AC-17: Agent name is 'future_growth_agent'."""
        assert GROWTH_AGENT_NAME == "future_growth_agent"


# ===========================================================================
# Serialization round-trip tests
# ===========================================================================


class TestSerialization:
    def test_growth_opportunity_draft_round_trip(self) -> None:
        draft = GrowthOpportunityDraft(
            opportunity_name="Test Opportunity",
            category="NEW_PRODUCT",
            maturity="EARLY_STAGE",
            addressable_market=Decimal("50000.0000"),
            tam_methodology="Bottom-up estimation",
            tam_low=Decimal("30000.0000"),
            tam_high=Decimal("80000.0000"),
            timeline_years=3,
            confidence="MEDIUM",
            evidence_indices=[0, 1],
            risks=["Competition"],
            rationale="Test rationale",
        )
        data = draft.model_dump()
        restored = GrowthOpportunityDraft.model_validate(data)
        assert restored == draft
        assert isinstance(restored.addressable_market, Decimal)

    def test_growth_validation_result_round_trip(self) -> None:
        result = GrowthValidationResult(
            passed=False,
            issues=[
                GrowthValidationIssue(
                    check_id="MV-01",
                    severity="ERROR",
                    opportunity_name="Test",
                    message="No evidence",
                ),
            ],
            downgraded_maturities=[("Test", "PROVEN", "SPECULATIVE")],
            nullified_tams=["Test"],
        )
        data = result.model_dump()
        restored = GrowthValidationResult.model_validate(data)
        assert restored == result

    def test_future_growth_result_round_trip(self) -> None:
        result = FutureGrowthResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            opportunities=[OPP_UUID],
            findings_count=20,
            evidence_count=10,
            growth_quality_score=72,
            future_optionality_score=65,
            steps_completed=7,
            errors=[],
        )
        data = result.model_dump()
        restored = FutureGrowthResult.model_validate(data)
        assert restored == result

    def test_growth_analysis_output_json_round_trip(self) -> None:
        output = GrowthAnalysisOutput(
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Test",
                    category="EXPANSION",
                    maturity="SPECULATIVE",
                    confidence="LOW",
                    rationale="Test",
                ),
            ],
            growth_quality_scores=[
                GrowthScoreComponent(component_name="Revenue CAGR", score=50, rationale="Moderate"),
            ],
            future_optionality_scores=[
                GrowthScoreComponent(
                    component_name="Maturity Distribution",
                    score=40,
                    rationale="Low",
                ),
            ],
            growth_vs_optionality_separation="Test separation",
            themes_identified=["artificial_intelligence"],
        )
        json_str = output.model_dump_json()
        restored = GrowthAnalysisOutput.model_validate_json(json_str)
        assert restored == output

    def test_growth_challenge_output_round_trip(self) -> None:
        output = GrowthChallengeOutput(
            challenges=[
                GrowthChallengeItem(
                    opportunity_name="Test",
                    challenge="Competition",
                    tam_challenge="Overestimated",
                ),
            ],
            overall_optimism_assessment="Moderately optimistic",
        )
        data = output.model_dump()
        restored = GrowthChallengeOutput.model_validate(data)
        assert restored == output
