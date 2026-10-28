"""Comprehensive tests for Phase 13.1 Macro Economics Agent contracts."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    MACRO_AGENT_NAME,
    MACRO_AGENT_RUN_TYPE,
    MACRO_AGENT_TOKEN_BUDGET,
    MACRO_AGENT_TOKEN_WARNING,
    MACRO_DIMENSIONS,
    MACRO_FINDING_CATEGORIES,
    MACRO_RESEARCH_STEPS,
    MAX_LLM_ATTEMPTS,
    REGIME_LABELS,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    ComputeIndicatorTrendsInput,
    ComputeIndicatorTrendsOutput,
    DiscoverMacroSourcesInput,
    DiscoverMacroSourcesOutput,
    ExtractedEvidence,
    FindingSummary,
    GeneratedFinding,
    IndicatorTrend,
    LoadMacroContextInput,
    LoadMacroContextOutput,
    MacroAnalysisOutput,
    MacroChallengeItem,
    MacroChallengeOutput,
    MacroConfig,
    MacroEconomicsResult,
    MacroEvidenceExtractionOutput,
    MacroIndicatorSnapshot,
    MacroRegimeAssessment,
    MacroResearchRequest,
    MacroTransmissionChannel,
    MacroValidationIssue,
    MacroValidationResult,
    PersistMacroIndicatorsInput,
    PersistMacroIndicatorsOutput,
    SectorMacroSensitivity,
    SourceCandidate,
    TokenBudget,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    SourceTier,
)
from app.providers.types import MacroIndicatorInfo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
INDICATOR_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
FINDING_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")


# ===========================================================================
# Constants
# ===========================================================================


class TestMacroConstants:
    def test_macro_agent_token_budget(self) -> None:
        assert MACRO_AGENT_TOKEN_BUDGET == 20_000

    def test_macro_agent_token_warning(self) -> None:
        assert MACRO_AGENT_TOKEN_WARNING == 16_000

    def test_warning_is_80_percent(self) -> None:
        assert int(MACRO_AGENT_TOKEN_BUDGET * 0.8) == MACRO_AGENT_TOKEN_WARNING

    def test_macro_agent_name(self) -> None:
        assert MACRO_AGENT_NAME == "macro_economics_agent"

    def test_macro_agent_run_type(self) -> None:
        assert MACRO_AGENT_RUN_TYPE == "macro_economics"

    def test_max_llm_attempts_shared(self) -> None:
        assert MAX_LLM_ATTEMPTS == 2


# ===========================================================================
# MACRO_FINDING_CATEGORIES
# ===========================================================================


class TestMacroFindingCategories:
    def test_is_frozenset(self) -> None:
        assert isinstance(MACRO_FINDING_CATEGORIES, frozenset)

    def test_has_15_categories(self) -> None:
        assert len(MACRO_FINDING_CATEGORIES) == 15

    def test_dimensional_assessment_categories(self) -> None:
        dimensional = {
            "monetary_policy_assessment",
            "inflation_assessment",
            "growth_assessment",
            "fiscal_policy_assessment",
            "external_sector_assessment",
            "commodity_exposure",
            "credit_banking_assessment",
            "global_macro_assessment",
        }
        assert dimensional <= MACRO_FINDING_CATEGORIES

    def test_transmission_impact_categories(self) -> None:
        transmission = {"macro_transmission_channel", "sector_sensitivity"}
        assert transmission <= MACRO_FINDING_CATEGORIES

    def test_forward_looking_categories(self) -> None:
        forward = {"macro_risk", "macro_catalyst", "macro_scenario"}
        assert forward <= MACRO_FINDING_CATEGORIES

    def test_data_quality_categories(self) -> None:
        data_quality = {"data_gap", "data_contradiction"}
        assert data_quality <= MACRO_FINDING_CATEGORIES

    def test_complete_set(self) -> None:
        expected = frozenset(
            {
                "monetary_policy_assessment",
                "inflation_assessment",
                "growth_assessment",
                "fiscal_policy_assessment",
                "external_sector_assessment",
                "commodity_exposure",
                "credit_banking_assessment",
                "global_macro_assessment",
                "macro_transmission_channel",
                "sector_sensitivity",
                "macro_risk",
                "macro_catalyst",
                "macro_scenario",
                "data_gap",
                "data_contradiction",
            }
        )
        assert expected == MACRO_FINDING_CATEGORIES

    def test_no_overlap_with_growth_categories(self) -> None:
        from app.agents.contracts import GROWTH_FINDING_CATEGORIES

        overlap = MACRO_FINDING_CATEGORIES & GROWTH_FINDING_CATEGORIES
        assert overlap == set(), f"Unexpected overlap: {overlap}"


# ===========================================================================
# MACRO_DIMENSIONS
# ===========================================================================


class TestMacroDimensions:
    def test_is_tuple(self) -> None:
        assert isinstance(MACRO_DIMENSIONS, tuple)

    def test_has_8_dimensions(self) -> None:
        assert len(MACRO_DIMENSIONS) == 8

    def test_contains_all_dimensions(self) -> None:
        assert "monetary_policy" in MACRO_DIMENSIONS
        assert "inflation" in MACRO_DIMENSIONS
        assert "growth" in MACRO_DIMENSIONS
        assert "fiscal_policy" in MACRO_DIMENSIONS
        assert "external_sector" in MACRO_DIMENSIONS
        assert "commodities" in MACRO_DIMENSIONS
        assert "credit_banking" in MACRO_DIMENSIONS
        assert "global" in MACRO_DIMENSIONS

    def test_no_duplicates(self) -> None:
        assert len(MACRO_DIMENSIONS) == len(set(MACRO_DIMENSIONS))

    def test_all_snake_case(self) -> None:
        for dim in MACRO_DIMENSIONS:
            assert dim == dim.lower()
            assert " " not in dim


# ===========================================================================
# REGIME_LABELS
# ===========================================================================


class TestRegimeLabels:
    def test_is_dict(self) -> None:
        assert isinstance(REGIME_LABELS, dict)

    def test_has_5_levels(self) -> None:
        assert len(REGIME_LABELS) == 5

    def test_keys_are_1_through_5(self) -> None:
        assert set(REGIME_LABELS.keys()) == {1, 2, 3, 4, 5}

    def test_labels(self) -> None:
        assert REGIME_LABELS[1] == "VERY_RESTRICTIVE"
        assert REGIME_LABELS[2] == "RESTRICTIVE"
        assert REGIME_LABELS[3] == "NEUTRAL"
        assert REGIME_LABELS[4] == "SUPPORTIVE"
        assert REGIME_LABELS[5] == "VERY_SUPPORTIVE"

    def test_all_uppercase(self) -> None:
        for label in REGIME_LABELS.values():
            assert label == label.upper()


# ===========================================================================
# MACRO_RESEARCH_STEPS
# ===========================================================================


class TestMacroResearchSteps:
    def test_is_tuple(self) -> None:
        assert isinstance(MACRO_RESEARCH_STEPS, tuple)

    def test_has_7_steps(self) -> None:
        assert len(MACRO_RESEARCH_STEPS) == 7

    def test_step_order_sequential(self) -> None:
        orders = [s.step_order for s in MACRO_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_step_names(self) -> None:
        names = [s.step_name for s in MACRO_RESEARCH_STEPS]
        assert names == [
            "context_load",
            "macro_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "macro_analysis",
            "macro_validation",
            "macro_challenge",
        ]

    def test_step_types(self) -> None:
        types = [s.step_type for s in MACRO_RESEARCH_STEPS]
        assert types == [
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_LLM_REASONING,
        ]

    def test_llm_steps(self) -> None:
        llm_steps = [s for s in MACRO_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        assert [s.step_name for s in llm_steps] == [
            "evidence_extraction",
            "macro_analysis",
            "macro_challenge",
        ]

    def test_deterministic_steps_no_llm(self) -> None:
        for step in MACRO_RESEARCH_STEPS:
            if step.step_type == STEP_TYPE_DETERMINISTIC:
                assert not step.uses_llm

    def test_timeouts(self) -> None:
        timeouts = {s.step_name: s.timeout_seconds for s in MACRO_RESEARCH_STEPS}
        assert timeouts["context_load"] == 10
        assert timeouts["macro_source_discovery"] == 30
        assert timeouts["document_retrieval"] == 60
        assert timeouts["evidence_extraction"] == 120
        assert timeouts["macro_analysis"] == 120
        assert timeouts["macro_validation"] == 10
        assert timeouts["macro_challenge"] == 120

    def test_all_steps_frozen(self) -> None:
        for step in MACRO_RESEARCH_STEPS:
            assert step.model_config.get("frozen") is True


# ===========================================================================
# MacroConfig
# ===========================================================================


class TestMacroConfig:
    def test_defaults(self) -> None:
        config = MacroConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == 2
        assert config.source_limit == 30
        assert config.max_documents == 10
        assert config.concurrent_retrievals == 5
        assert config.extraction_model is None
        assert config.analysis_model is None
        assert config.challenge_model is None

    def test_custom_values(self) -> None:
        config = MacroConfig(
            token_budget=15_000,
            token_warning_threshold=12_000,
            max_llm_attempts=1,
            source_limit=20,
            max_documents=5,
            concurrent_retrievals=3,
            extraction_model="haiku",
            analysis_model="sonnet",
            challenge_model="opus",
        )
        assert config.token_budget == 15_000
        assert config.max_llm_attempts == 1
        assert config.max_documents == 5
        assert config.challenge_model == "opus"

    def test_frozen(self) -> None:
        config = MacroConfig()
        with pytest.raises(ValidationError):
            config.token_budget = 50_000  # type: ignore[misc]

    def test_token_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            MacroConfig(token_budget=0)

    def test_max_llm_attempts_max_is_3(self) -> None:
        with pytest.raises(ValidationError):
            MacroConfig(max_llm_attempts=4)

    def test_source_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MacroConfig(source_limit=0)
        with pytest.raises(ValidationError):
            MacroConfig(source_limit=101)

    def test_concurrent_retrievals_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MacroConfig(concurrent_retrievals=0)
        with pytest.raises(ValidationError):
            MacroConfig(concurrent_retrievals=21)

    def test_max_documents_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MacroConfig(max_documents=0)
        with pytest.raises(ValidationError):
            MacroConfig(max_documents=31)


# ===========================================================================
# MacroResearchRequest
# ===========================================================================


class TestMacroResearchRequest:
    def test_valid_request(self) -> None:
        req = MacroResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="test_user",
        )
        assert req.company_id == COMPANY_UUID
        assert req.observation_date == date(2025, 9, 30)
        assert req.initiated_by == "test_user"
        assert req.configuration is None

    def test_with_configuration(self) -> None:
        config = MacroConfig(token_budget=15_000)
        req = MacroResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
            initiated_by="system",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.token_budget == 15_000

    def test_frozen(self) -> None:
        req = MacroResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        with pytest.raises(ValidationError):
            req.initiated_by = "other"  # type: ignore[misc]

    def test_initiated_by_not_empty(self) -> None:
        with pytest.raises(ValidationError):
            MacroResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="",
            )

    def test_initiated_by_max_length(self) -> None:
        with pytest.raises(ValidationError):
            MacroResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="x" * 201,
            )

    def test_ignores_extra_fields(self) -> None:
        req = MacroResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
            extra_field="ignored",  # type: ignore[call-arg]
        )
        assert req.company_id == COMPANY_UUID
        assert not hasattr(req, "extra_field")


# ===========================================================================
# MacroEconomicsResult
# ===========================================================================


class TestMacroEconomicsResult:
    def test_minimal(self) -> None:
        result = MacroEconomicsResult(status="COMPLETED", run_id=RUN_UUID)
        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert result.findings_count == 0
        assert result.evidence_count == 0
        assert result.indicators_persisted == 0
        assert result.regime_assessments_count == 0
        assert result.transmission_channels_count == 0
        assert result.macro_data_provider_available is True
        assert result.validation_result is None
        assert result.steps_completed == 0
        assert result.steps_total == 7
        assert result.token_usage is None
        assert result.errors == []

    def test_full(self) -> None:
        vr = MacroValidationResult(passed=True)
        tb = TokenBudget(budget=20_000, warning_threshold=16_000)
        result = MacroEconomicsResult(
            status="PARTIAL",
            run_id=RUN_UUID,
            findings_count=10,
            evidence_count=5,
            indicators_persisted=3,
            regime_assessments_count=6,
            transmission_channels_count=4,
            macro_data_provider_available=False,
            validation_result=vr,
            steps_completed=5,
            steps_total=7,
            token_usage=tb,
            errors=["provider timeout"],
        )
        assert result.status == "PARTIAL"
        assert result.findings_count == 10
        assert result.indicators_persisted == 3
        assert result.macro_data_provider_available is False
        assert result.steps_completed == 5

    def test_frozen(self) -> None:
        result = MacroEconomicsResult(status="COMPLETED", run_id=RUN_UUID)
        with pytest.raises(ValidationError):
            result.status = "FAILED"  # type: ignore[misc]

    def test_negative_findings_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroEconomicsResult(status="COMPLETED", run_id=RUN_UUID, findings_count=-1)

    def test_empty_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroEconomicsResult(status="", run_id=RUN_UUID)


# ===========================================================================
# MacroIndicatorSnapshot
# ===========================================================================


class TestMacroIndicatorSnapshot:
    def test_valid_snapshot(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            value=Decimal("6.50"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="RBI",
        )
        assert snap.indicator_id == "REPO_RATE"
        assert snap.value == Decimal("6.50")
        assert isinstance(snap.value, Decimal)
        assert snap.as_of_date == date(2025, 6, 1)
        assert snap.source == "RBI"

    def test_frozen(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="CPI",
            name="CPI Inflation",
            value=Decimal("5.20"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 5, 1),
            source="MOSPI",
        )
        with pytest.raises(ValidationError):
            snap.value = Decimal("6.00")  # type: ignore[misc]

    def test_decimal_precision_preserved(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="GDP_GROWTH",
            name="GDP Growth",
            value=Decimal("7.12345678"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 3, 31),
            source="MOSPI",
        )
        assert snap.value == Decimal("7.12345678")

    def test_empty_indicator_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroIndicatorSnapshot(
                indicator_id="",
                name="Test",
                value=Decimal("1.0"),
                unit="PERCENTAGE",
                as_of_date=date(2025, 1, 1),
                source="RBI",
            )

    def test_empty_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroIndicatorSnapshot(
                indicator_id="REPO_RATE",
                name="Test",
                value=Decimal("6.50"),
                unit="PERCENTAGE",
                as_of_date=date(2025, 1, 1),
                source="",
            )

    def test_serialization_round_trip(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            value=Decimal("6.50"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="RBI",
        )
        data = snap.model_dump()
        rebuilt = MacroIndicatorSnapshot.model_validate(data)
        assert rebuilt == snap


# ===========================================================================
# LoadMacroContextInput / Output
# ===========================================================================


class TestLoadMacroContextInput:
    def test_valid(self) -> None:
        inp = LoadMacroContextInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            observation_date=date(2025, 9, 30),
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.research_run_id == RUN_UUID
        assert inp.observation_date == date(2025, 9, 30)

    def test_frozen(self) -> None:
        inp = LoadMacroContextInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            observation_date=date(2025, 9, 30),
        )
        with pytest.raises(ValidationError):
            inp.company_id = COMPANY_UUID  # type: ignore[misc]


class TestLoadMacroContextOutput:
    def test_minimal(self) -> None:
        out = LoadMacroContextOutput(company_name="HDFC Bank")
        assert out.company_name == "HDFC Bank"
        assert out.sectors == []
        assert out.exchange == ""
        assert out.prior_findings == []
        assert out.available_indicators == []
        assert out.indicator_snapshots == []
        assert out.unavailable_dimensions == []

    def test_full(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            value=Decimal("6.50"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="RBI",
        )
        finding = FindingSummary(
            finding_id=FINDING_UUID,
            category="company_identity",
            finding_type=FindingType.FACT,
            content="HDFC Bank is a private sector bank",
            confidence=ConfidenceLevel.HIGH,
        )
        out = LoadMacroContextOutput(
            company_name="HDFC Bank",
            sectors=["Banking", "Financial Services"],
            exchange="NSE",
            prior_findings=[finding],
            available_indicators=[
                MacroIndicatorInfo(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    source="RBI",
                    frequency="quarterly",
                    unit="PERCENTAGE",
                ),
                MacroIndicatorInfo(
                    indicator_id="CPI_INFLATION",
                    name="CPI Inflation",
                    source="MOSPI",
                    frequency="monthly",
                    unit="PERCENTAGE",
                ),
            ],
            indicator_snapshots=[snap],
            unavailable_dimensions=["fiscal_policy", "commodities"],
        )
        assert len(out.sectors) == 2
        assert len(out.prior_findings) == 1
        assert len(out.indicator_snapshots) == 1
        assert len(out.unavailable_dimensions) == 2

    def test_frozen(self) -> None:
        out = LoadMacroContextOutput(company_name="Test")
        with pytest.raises(ValidationError):
            out.company_name = "Other"  # type: ignore[misc]


# ===========================================================================
# DiscoverMacroSourcesInput / Output
# ===========================================================================


class TestDiscoverMacroSourcesInput:
    def test_valid(self) -> None:
        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            sectors=["Banking"],
            dimensions_to_search=["fiscal_policy", "commodities"],
            observation_date=date(2025, 9, 30),
        )
        assert inp.company_name == "HDFC Bank"
        assert len(inp.dimensions_to_search) == 2

    def test_empty_company_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiscoverMacroSourcesInput(
                company_name="",
                observation_date=date(2025, 9, 30),
            )

    def test_frozen(self) -> None:
        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            observation_date=date(2025, 9, 30),
        )
        with pytest.raises(ValidationError):
            inp.company_name = "SBI"  # type: ignore[misc]


class TestDiscoverMacroSourcesOutput:
    def test_minimal(self) -> None:
        out = DiscoverMacroSourcesOutput()
        assert out.sources == []
        assert out.dimensions_covered == []
        assert out.dimensions_still_missing == []

    def test_frozen(self) -> None:
        out = DiscoverMacroSourcesOutput()
        with pytest.raises(ValidationError):
            out.dimensions_covered = ["test"]  # type: ignore[misc]


# ===========================================================================
# MacroEvidenceExtractionOutput
# ===========================================================================


class TestMacroEvidenceExtractionOutput:
    def test_empty(self) -> None:
        out = MacroEvidenceExtractionOutput()
        assert out.evidences == []

    def test_with_evidences(self) -> None:
        ev = ExtractedEvidence(
            evidence_type=EvidenceType.FACT,
            claim="RBI repo rate is 6.50%",
            confidence=ConfidenceLevel.HIGH,
        )
        out = MacroEvidenceExtractionOutput(evidences=[ev])
        assert len(out.evidences) == 1
        assert out.evidences[0].claim == "RBI repo rate is 6.50%"

    def test_frozen(self) -> None:
        out = MacroEvidenceExtractionOutput()
        with pytest.raises(ValidationError):
            out.evidences = []  # type: ignore[misc]


# ===========================================================================
# MacroRegimeAssessment
# ===========================================================================


class TestMacroRegimeAssessment:
    def test_valid(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="monetary_policy",
            regime_level=4,
            regime_label="SUPPORTIVE",
            confidence=ConfidenceLevel.HIGH,
            rationale="RBI has cut rates and maintained accommodative stance",
            supporting_indicators=["REPO_RATE"],
            evidence_indices=[0, 1],
        )
        assert ra.dimension == "monetary_policy"
        assert ra.regime_level == 4
        assert ra.regime_label == "SUPPORTIVE"
        assert ra.confidence == ConfidenceLevel.HIGH

    def test_frozen(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="inflation",
            regime_level=3,
            regime_label="NEUTRAL",
            confidence=ConfidenceLevel.MEDIUM,
            rationale="CPI within target band",
        )
        with pytest.raises(ValidationError):
            ra.regime_level = 5  # type: ignore[misc]

    def test_regime_level_below_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegimeAssessment(
                dimension="growth",
                regime_level=0,
                regime_label="INVALID",
                confidence=ConfidenceLevel.LOW,
                rationale="test",
            )

    def test_regime_level_above_5_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegimeAssessment(
                dimension="growth",
                regime_level=6,
                regime_label="INVALID",
                confidence=ConfidenceLevel.LOW,
                rationale="test",
            )

    def test_regime_level_1_accepted(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="monetary_policy",
            regime_level=1,
            regime_label="VERY_RESTRICTIVE",
            confidence=ConfidenceLevel.HIGH,
            rationale="Aggressive tightening",
        )
        assert ra.regime_level == 1

    def test_regime_level_5_accepted(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="fiscal_policy",
            regime_level=5,
            regime_label="VERY_SUPPORTIVE",
            confidence=ConfidenceLevel.HIGH,
            rationale="Massive fiscal stimulus",
        )
        assert ra.regime_level == 5

    def test_empty_dimension_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegimeAssessment(
                dimension="",
                regime_level=3,
                regime_label="NEUTRAL",
                confidence=ConfidenceLevel.LOW,
                rationale="test",
            )

    def test_empty_rationale_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroRegimeAssessment(
                dimension="growth",
                regime_level=3,
                regime_label="NEUTRAL",
                confidence=ConfidenceLevel.LOW,
                rationale="",
            )

    def test_serialization_round_trip(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="inflation",
            regime_level=2,
            regime_label="RESTRICTIVE",
            confidence=ConfidenceLevel.MEDIUM,
            rationale="High inflation eroding purchasing power",
            supporting_indicators=["CPI_INFLATION"],
            evidence_indices=[0],
        )
        data = ra.model_dump()
        rebuilt = MacroRegimeAssessment.model_validate(data)
        assert rebuilt == ra


# ===========================================================================
# MacroTransmissionChannel
# ===========================================================================


class TestMacroTransmissionChannel:
    def test_valid(self) -> None:
        tc = MacroTransmissionChannel(
            macro_dimension="monetary_policy",
            indicator_name="RBI Repo Rate",
            direction="INCREASE",
            affected_sector="Banking",
            impact_direction="POSITIVE",
            impact_magnitude="HIGH",
            mechanism="Higher repo rate increases NIMs for banks with MCLR-linked loans",
            confidence=ConfidenceLevel.HIGH,
        )
        assert tc.macro_dimension == "monetary_policy"
        assert tc.direction == "INCREASE"
        assert tc.impact_direction == "POSITIVE"

    def test_frozen(self) -> None:
        tc = MacroTransmissionChannel(
            macro_dimension="inflation",
            indicator_name="CPI",
            direction="INCREASE",
            affected_sector="FMCG",
            impact_direction="NEGATIVE",
            impact_magnitude="MEDIUM",
            mechanism="Input cost pressure",
            confidence=ConfidenceLevel.MEDIUM,
        )
        with pytest.raises(ValidationError):
            tc.direction = "DECREASE"  # type: ignore[misc]

    def test_empty_mechanism_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroTransmissionChannel(
                macro_dimension="growth",
                indicator_name="GDP",
                direction="INCREASE",
                affected_sector="Infra",
                impact_direction="POSITIVE",
                impact_magnitude="HIGH",
                mechanism="",
                confidence=ConfidenceLevel.LOW,
            )

    def test_serialization_round_trip(self) -> None:
        tc = MacroTransmissionChannel(
            macro_dimension="external_sector",
            indicator_name="INR/USD",
            direction="DECREASE",
            affected_sector="IT Services",
            impact_direction="POSITIVE",
            impact_magnitude="HIGH",
            mechanism="INR depreciation boosts export revenue in INR terms",
            confidence=ConfidenceLevel.HIGH,
        )
        data = tc.model_dump()
        rebuilt = MacroTransmissionChannel.model_validate(data)
        assert rebuilt == tc


# ===========================================================================
# SectorMacroSensitivity
# ===========================================================================


class TestSectorMacroSensitivity:
    def test_valid(self) -> None:
        sms = SectorMacroSensitivity(
            sector="Banking",
            dimension_sensitivities={
                "monetary_policy": "HIGH_POSITIVE",
                "inflation": "MODERATE_NEGATIVE",
            },
            key_transmission_channels=["rate_impact_on_nims"],
            overall_macro_exposure="FAVORABLE",
            rationale="Banking benefits from rate cycle expansion",
        )
        assert sms.sector == "Banking"
        assert sms.overall_macro_exposure == "FAVORABLE"
        assert len(sms.dimension_sensitivities) == 2

    def test_frozen(self) -> None:
        sms = SectorMacroSensitivity(
            sector="IT",
            overall_macro_exposure="NEUTRAL",
            rationale="Mixed exposure",
        )
        with pytest.raises(ValidationError):
            sms.sector = "Banking"  # type: ignore[misc]

    def test_empty_sector_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SectorMacroSensitivity(
                sector="",
                overall_macro_exposure="NEUTRAL",
                rationale="test",
            )


# ===========================================================================
# MacroAnalysisOutput
# ===========================================================================


class TestMacroAnalysisOutput:
    def test_minimal(self) -> None:
        out = MacroAnalysisOutput()
        assert out.regime_assessments == []
        assert out.transmission_channels == []
        assert out.sector_sensitivity is None
        assert out.findings == []

    def test_full(self) -> None:
        ra = MacroRegimeAssessment(
            dimension="monetary_policy",
            regime_level=4,
            regime_label="SUPPORTIVE",
            confidence=ConfidenceLevel.HIGH,
            rationale="Accommodative stance",
        )
        tc = MacroTransmissionChannel(
            macro_dimension="monetary_policy",
            indicator_name="Repo Rate",
            direction="DECREASE",
            affected_sector="Real Estate",
            impact_direction="POSITIVE",
            impact_magnitude="HIGH",
            mechanism="Lower EMIs boost demand",
            confidence=ConfidenceLevel.HIGH,
        )
        sms = SectorMacroSensitivity(
            sector="Real Estate",
            overall_macro_exposure="FAVORABLE",
            rationale="Rate sensitive sector",
        )
        finding = GeneratedFinding(
            finding_type=FindingType.AI_INFERENCE,
            category="monetary_policy_assessment",
            content="Accommodative monetary policy supports real estate",
            confidence=ConfidenceLevel.HIGH,
        )
        out = MacroAnalysisOutput(
            regime_assessments=[ra],
            transmission_channels=[tc],
            sector_sensitivity=sms,
            findings=[finding],
        )
        assert len(out.regime_assessments) == 1
        assert len(out.transmission_channels) == 1
        assert out.sector_sensitivity is not None

    def test_frozen(self) -> None:
        out = MacroAnalysisOutput()
        with pytest.raises(ValidationError):
            out.sector_sensitivity = None  # type: ignore[misc]


# ===========================================================================
# MacroValidationIssue / MacroValidationResult
# ===========================================================================


class TestMacroValidationIssue:
    def test_valid(self) -> None:
        issue = MacroValidationIssue(
            check_id="MV-01",
            severity="WARNING",
            message="FACT finding without evidence downgraded to AI_INFERENCE",
        )
        assert issue.check_id == "MV-01"
        assert issue.severity == "WARNING"

    def test_frozen(self) -> None:
        issue = MacroValidationIssue(
            check_id="MV-02",
            severity="ERROR",
            message="Forward-looking FACT reclassified",
        )
        with pytest.raises(ValidationError):
            issue.check_id = "MV-03"  # type: ignore[misc]

    def test_empty_check_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroValidationIssue(check_id="", severity="WARNING", message="test")

    def test_check_id_max_length(self) -> None:
        with pytest.raises(ValidationError):
            MacroValidationIssue(check_id="X" * 11, severity="WARNING", message="test")


class TestMacroValidationResult:
    def test_passed(self) -> None:
        vr = MacroValidationResult(passed=True)
        assert vr.passed is True
        assert vr.issues == []
        assert vr.findings_corrected == 0
        assert vr.findings_rejected == 0
        assert vr.regimes_clamped == 0

    def test_failed_with_issues(self) -> None:
        issue = MacroValidationIssue(
            check_id="MV-01",
            severity="WARNING",
            message="FACT without evidence",
        )
        vr = MacroValidationResult(
            passed=False,
            issues=[issue],
            findings_corrected=3,
            findings_rejected=1,
            regimes_clamped=0,
        )
        assert not vr.passed
        assert len(vr.issues) == 1
        assert vr.findings_corrected == 3
        assert vr.findings_rejected == 1

    def test_frozen(self) -> None:
        vr = MacroValidationResult(passed=True)
        with pytest.raises(ValidationError):
            vr.passed = False  # type: ignore[misc]

    def test_negative_corrected_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroValidationResult(passed=True, findings_corrected=-1)


# ===========================================================================
# MacroChallengeItem / MacroChallengeOutput
# ===========================================================================


class TestMacroChallengeItem:
    def test_valid(self) -> None:
        item = MacroChallengeItem(
            dimension="monetary_policy",
            challenge="Rate cuts may be delayed due to sticky core inflation",
            alternative_interpretation="RBI may prioritize growth over inflation",
            risk="Prolonged high rates could stress corporate balance sheets",
            catalyst="Faster disinflation could accelerate rate cuts",
            evidence_indices=[0, 2],
        )
        assert item.dimension == "monetary_policy"
        assert item.alternative_interpretation is not None
        assert item.risk is not None
        assert item.catalyst is not None

    def test_minimal(self) -> None:
        item = MacroChallengeItem(
            dimension="growth",
            challenge="GDP growth may not translate to corporate earnings growth",
        )
        assert item.alternative_interpretation is None
        assert item.risk is None
        assert item.catalyst is None
        assert item.evidence_indices == []

    def test_frozen(self) -> None:
        item = MacroChallengeItem(
            dimension="inflation",
            challenge="test challenge",
        )
        with pytest.raises(ValidationError):
            item.challenge = "other"  # type: ignore[misc]

    def test_empty_dimension_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroChallengeItem(dimension="", challenge="test")

    def test_empty_challenge_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroChallengeItem(dimension="growth", challenge="")


class TestMacroChallengeOutput:
    def test_minimal(self) -> None:
        out = MacroChallengeOutput()
        assert out.challenges == []
        assert out.findings == []

    def test_with_data(self) -> None:
        item = MacroChallengeItem(
            dimension="growth",
            challenge="GDP growth may slow",
        )
        finding = GeneratedFinding(
            finding_type=FindingType.AI_INFERENCE,
            category="macro_risk",
            content="Risk of growth slowdown",
            confidence=ConfidenceLevel.MEDIUM,
        )
        out = MacroChallengeOutput(challenges=[item], findings=[finding])
        assert len(out.challenges) == 1
        assert len(out.findings) == 1

    def test_frozen(self) -> None:
        out = MacroChallengeOutput()
        with pytest.raises(ValidationError):
            out.challenges = []  # type: ignore[misc]


# ===========================================================================
# IndicatorTrend
# ===========================================================================


class TestIndicatorTrend:
    def test_full_trend(self) -> None:
        trend = IndicatorTrend(
            indicator_id="REPO_RATE",
            current_value=Decimal("6.50"),
            current_date=date(2025, 6, 1),
            prior_value=Decimal("6.25"),
            prior_date=date(2024, 12, 1),
            absolute_change=Decimal("0.25"),
            percentage_change=Decimal("4.0000"),
            direction="INCREASING",
            data_points_available=5,
        )
        assert trend.current_value == Decimal("6.50")
        assert trend.prior_value == Decimal("6.25")
        assert trend.absolute_change == Decimal("0.25")
        assert trend.direction == "INCREASING"
        assert isinstance(trend.current_value, Decimal)
        assert isinstance(trend.absolute_change, Decimal)

    def test_insufficient_data(self) -> None:
        trend = IndicatorTrend(
            indicator_id="NEW_INDICATOR",
            current_value=Decimal("100.00"),
            current_date=date(2025, 6, 1),
            prior_value=None,
            prior_date=None,
            absolute_change=None,
            percentage_change=None,
            direction="INSUFFICIENT_DATA",
            data_points_available=1,
        )
        assert trend.prior_value is None
        assert trend.absolute_change is None
        assert trend.percentage_change is None
        assert trend.direction == "INSUFFICIENT_DATA"

    def test_stable_direction(self) -> None:
        trend = IndicatorTrend(
            indicator_id="REPO_RATE",
            current_value=Decimal("6.50"),
            current_date=date(2025, 6, 1),
            prior_value=Decimal("6.50"),
            prior_date=date(2024, 12, 1),
            absolute_change=Decimal("0.00"),
            percentage_change=Decimal("0.0000"),
            direction="STABLE",
            data_points_available=3,
        )
        assert trend.direction == "STABLE"

    def test_frozen(self) -> None:
        trend = IndicatorTrend(
            indicator_id="CPI",
            current_value=Decimal("5.0"),
            current_date=date(2025, 1, 1),
            direction="INCREASING",
            data_points_available=2,
        )
        with pytest.raises(ValidationError):
            trend.direction = "DECREASING"  # type: ignore[misc]

    def test_empty_indicator_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndicatorTrend(
                indicator_id="",
                current_value=Decimal("1.0"),
                current_date=date(2025, 1, 1),
                direction="STABLE",
                data_points_available=1,
            )

    def test_negative_data_points_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IndicatorTrend(
                indicator_id="CPI",
                current_value=Decimal("5.0"),
                current_date=date(2025, 1, 1),
                direction="STABLE",
                data_points_available=-1,
            )

    def test_decimal_precision(self) -> None:
        trend = IndicatorTrend(
            indicator_id="CPI_INFLATION",
            current_value=Decimal("5.12345678"),
            current_date=date(2025, 6, 1),
            prior_value=Decimal("4.98765432"),
            prior_date=date(2024, 12, 1),
            absolute_change=Decimal("0.13580246"),
            percentage_change=Decimal("2.7228"),
            direction="INCREASING",
            data_points_available=12,
        )
        assert trend.current_value == Decimal("5.12345678")
        assert trend.percentage_change == Decimal("2.7228")

    def test_serialization_round_trip(self) -> None:
        trend = IndicatorTrend(
            indicator_id="REPO_RATE",
            current_value=Decimal("6.50"),
            current_date=date(2025, 6, 1),
            prior_value=Decimal("6.25"),
            prior_date=date(2024, 12, 1),
            absolute_change=Decimal("0.25"),
            percentage_change=Decimal("4.0000"),
            direction="INCREASING",
            data_points_available=5,
        )
        data = trend.model_dump()
        rebuilt = IndicatorTrend.model_validate(data)
        assert rebuilt == trend


# ===========================================================================
# PersistMacroIndicatorsInput / Output
# ===========================================================================


class TestPersistMacroIndicatorsInput:
    def test_valid(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            value=Decimal("6.50"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="RBI",
        )
        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_UUID,
            snapshots=[snap],
        )
        assert inp.research_run_id == RUN_UUID
        assert len(inp.snapshots) == 1
        assert inp.country == "IN"

    def test_custom_country(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="FED_RATE",
            name="Fed Funds Rate",
            value=Decimal("5.25"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="Fed",
        )
        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_UUID,
            snapshots=[snap],
            country="US",
        )
        assert inp.country == "US"

    def test_empty_snapshots_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistMacroIndicatorsInput(
                research_run_id=RUN_UUID,
                snapshots=[],
            )

    def test_frozen(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="CPI",
            name="CPI",
            value=Decimal("5.0"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 1, 1),
            source="MOSPI",
        )
        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_UUID,
            snapshots=[snap],
        )
        with pytest.raises(ValidationError):
            inp.country = "US"  # type: ignore[misc]

    def test_country_max_length(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="CPI",
            name="CPI",
            value=Decimal("5.0"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 1, 1),
            source="MOSPI",
        )
        with pytest.raises(ValidationError):
            PersistMacroIndicatorsInput(
                research_run_id=RUN_UUID,
                snapshots=[snap],
                country="X" * 11,
            )


class TestPersistMacroIndicatorsOutput:
    def test_valid(self) -> None:
        out = PersistMacroIndicatorsOutput(
            indicator_ids=[INDICATOR_UUID],
            persisted_count=1,
        )
        assert len(out.indicator_ids) == 1
        assert out.persisted_count == 1

    def test_frozen(self) -> None:
        out = PersistMacroIndicatorsOutput(
            indicator_ids=[],
            persisted_count=0,
        )
        with pytest.raises(ValidationError):
            out.persisted_count = 1  # type: ignore[misc]


# ===========================================================================
# ComputeIndicatorTrendsInput / Output
# ===========================================================================


class TestComputeIndicatorTrendsInput:
    def test_valid(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 6, 1), Decimal("6.50")),
                (date(2025, 1, 1), Decimal("6.25")),
            ],
            observation_date=date(2025, 6, 30),
        )
        assert inp.indicator_id == "REPO_RATE"
        assert len(inp.data_points) == 2
        assert inp.observation_date == date(2025, 6, 30)

    def test_empty_data_points_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ComputeIndicatorTrendsInput(
                indicator_id="CPI",
                data_points=[],
                observation_date=date(2025, 6, 30),
            )

    def test_frozen(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="CPI",
            data_points=[(date(2025, 1, 1), Decimal("5.0"))],
            observation_date=date(2025, 6, 30),
        )
        with pytest.raises(ValidationError):
            inp.indicator_id = "WPI"  # type: ignore[misc]

    def test_decimal_values_in_data_points(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="GDP_GROWTH",
            data_points=[
                (date(2024, 3, 31), Decimal("7.12345678")),
            ],
            observation_date=date(2025, 3, 31),
        )
        _, val = inp.data_points[0]
        assert isinstance(val, Decimal)
        assert val == Decimal("7.12345678")


class TestComputeIndicatorTrendsOutput:
    def test_valid(self) -> None:
        trend = IndicatorTrend(
            indicator_id="REPO_RATE",
            current_value=Decimal("6.50"),
            current_date=date(2025, 6, 1),
            direction="STABLE",
            data_points_available=3,
        )
        out = ComputeIndicatorTrendsOutput(trend=trend)
        assert out.trend.indicator_id == "REPO_RATE"

    def test_frozen(self) -> None:
        trend = IndicatorTrend(
            indicator_id="CPI",
            current_value=Decimal("5.0"),
            current_date=date(2025, 1, 1),
            direction="STABLE",
            data_points_available=1,
        )
        out = ComputeIndicatorTrendsOutput(trend=trend)
        with pytest.raises(ValidationError):
            out.trend = trend  # type: ignore[misc]


# ===========================================================================
# AC-01: All new contracts are frozen
# ===========================================================================


class TestAllContractsFrozen:
    """AC-01: All new Pydantic contracts are frozen (immutable)."""

    FROZEN_CONTRACTS = [
        MacroConfig,
        MacroResearchRequest,
        MacroEconomicsResult,
        MacroIndicatorSnapshot,
        LoadMacroContextInput,
        LoadMacroContextOutput,
        DiscoverMacroSourcesInput,
        DiscoverMacroSourcesOutput,
        MacroEvidenceExtractionOutput,
        MacroRegimeAssessment,
        MacroTransmissionChannel,
        SectorMacroSensitivity,
        MacroAnalysisOutput,
        MacroValidationIssue,
        MacroValidationResult,
        MacroChallengeItem,
        MacroChallengeOutput,
        IndicatorTrend,
        PersistMacroIndicatorsInput,
        PersistMacroIndicatorsOutput,
        ComputeIndicatorTrendsInput,
        ComputeIndicatorTrendsOutput,
    ]

    @pytest.mark.parametrize("contract", FROZEN_CONTRACTS, ids=lambda c: c.__name__)
    def test_frozen(self, contract: type) -> None:
        assert issubclass(contract, object)
        assert contract.model_config.get("frozen") is True


# ===========================================================================
# AC-08: All numeric fields use Decimal
# ===========================================================================


class TestDecimalFidelity:
    """AC-08: All financial values use Decimal (never float)."""

    def test_macro_indicator_snapshot_value_is_decimal(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            value=Decimal("6.50"),
            unit="PERCENTAGE",
            as_of_date=date(2025, 6, 1),
            source="RBI",
        )
        assert isinstance(snap.value, Decimal)

    def test_indicator_trend_values_are_decimal(self) -> None:
        trend = IndicatorTrend(
            indicator_id="CPI",
            current_value=Decimal("5.20"),
            current_date=date(2025, 6, 1),
            prior_value=Decimal("4.80"),
            prior_date=date(2024, 12, 1),
            absolute_change=Decimal("0.40"),
            percentage_change=Decimal("8.3333"),
            direction="INCREASING",
            data_points_available=6,
        )
        assert isinstance(trend.current_value, Decimal)
        assert isinstance(trend.prior_value, Decimal)
        assert isinstance(trend.absolute_change, Decimal)
        assert isinstance(trend.percentage_change, Decimal)

    def test_float_coerced_to_decimal_snapshot(self) -> None:
        snap = MacroIndicatorSnapshot(
            indicator_id="GDP",
            name="GDP Growth",
            value=6.5,  # type: ignore[arg-type]
            unit="PERCENTAGE",
            as_of_date=date(2025, 1, 1),
            source="MOSPI",
        )
        assert isinstance(snap.value, Decimal)

    def test_float_coerced_to_decimal_trend(self) -> None:
        trend = IndicatorTrend(
            indicator_id="GDP",
            current_value=7.2,  # type: ignore[arg-type]
            current_date=date(2025, 1, 1),
            direction="INCREASING",
            data_points_available=2,
        )
        assert isinstance(trend.current_value, Decimal)


# ===========================================================================
# Regression: shared types compatibility
# ===========================================================================


class TestSharedTypeCompatibility:
    """Verify macro contracts work with shared types from existing agents."""

    def test_finding_item_with_macro_category(self) -> None:
        for category in MACRO_FINDING_CATEGORIES:
            item = FindingSummary(
                finding_id=FINDING_UUID,
                category=category,
                finding_type=FindingType.AI_INFERENCE,
                content=f"Test {category}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert item.category == category

    def test_generated_finding_with_macro_category(self) -> None:
        gf = GeneratedFinding(
            finding_type=FindingType.AI_INFERENCE,
            category="monetary_policy_assessment",
            content="RBI is in accommodative mode",
            confidence=ConfidenceLevel.HIGH,
        )
        assert gf.category in MACRO_FINDING_CATEGORIES

    def test_token_budget_with_macro_defaults(self) -> None:
        tb = TokenBudget(
            budget=MACRO_AGENT_TOKEN_BUDGET,
            warning_threshold=MACRO_AGENT_TOKEN_WARNING,
        )
        assert tb.budget == 20_000
        assert tb.warning_threshold == 16_000
        assert not tb.is_exhausted
        assert not tb.is_warning

    def test_source_candidate_in_discover_output(self) -> None:
        sc = SourceCandidate(
            source_id="rbi-mp-2025",
            url="https://rbi.org.in/monetary-policy",
            title="RBI Monetary Policy Statement",
            source_type=DocumentType.GOVERNMENT_PUBLICATION,
            provider="rbi",
            source_tier=SourceTier.TIER_1,
        )
        out = DiscoverMacroSourcesOutput(
            sources=[sc],
            dimensions_covered=["monetary_policy"],
        )
        assert len(out.sources) == 1
        assert out.sources[0].source_tier == SourceTier.TIER_1
