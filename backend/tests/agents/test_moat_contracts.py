"""Comprehensive tests for Phase 10.1 Competitive Moat Agent contracts."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    MOAT_AGENT_NAME,
    MOAT_AGENT_TOKEN_BUDGET,
    MOAT_AGENT_TOKEN_WARNING,
    MOAT_FINDING_CATEGORIES,
    MOAT_RESEARCH_STEPS,
    MOAT_TYPE_TO_CATEGORY,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    DiscoverMoatSourcesInput,
    DiscoverMoatSourcesOutput,
    DurabilityChallengeOutput,
    FindingSummary,
    GeneratedFinding,
    GetPeerDataInput,
    GetPeerDataOutput,
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
    PeerCompanySummary,
    PersistMoatAssessmentsInput,
    PersistMoatAssessmentsOutput,
    SourceCandidate,
    ThreatItem,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    FindingType,
    MoatStrength,
    MoatType,
    SourceTier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
INDUSTRY_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
RUN_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
EVIDENCE_UUID = uuid.UUID("fedcbafe-dcba-fedc-bafe-dcbafedcbafe")
FINDING_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")


# ===========================================================================
# Constants
# ===========================================================================


class TestMoatConstants:
    def test_moat_agent_token_budget(self) -> None:
        assert MOAT_AGENT_TOKEN_BUDGET == 25_000

    def test_moat_agent_token_warning(self) -> None:
        assert MOAT_AGENT_TOKEN_WARNING == 20_000

    def test_warning_is_80_percent(self) -> None:
        assert int(MOAT_AGENT_TOKEN_BUDGET * 0.8) == MOAT_AGENT_TOKEN_WARNING

    def test_moat_agent_name(self) -> None:
        assert MOAT_AGENT_NAME == "competitive_moat_agent"


# ===========================================================================
# MOAT_FINDING_CATEGORIES
# ===========================================================================


class TestMoatFindingCategories:
    def test_is_frozenset(self) -> None:
        assert isinstance(MOAT_FINDING_CATEGORIES, frozenset)

    def test_has_19_categories(self) -> None:
        assert len(MOAT_FINDING_CATEGORIES) == 19

    def test_per_moat_type_categories(self) -> None:
        per_type = {
            "brand_moat",
            "cost_advantage_moat",
            "network_effect_moat",
            "switching_cost_moat",
            "distribution_moat",
            "scale_moat",
            "regulatory_moat",
            "intangible_asset_moat",
            "technology_moat",
            "ecosystem_moat",
            "customer_lock_in_moat",
            "structural_moat",
            "competitive_position",
        }
        assert per_type <= MOAT_FINDING_CATEGORIES

    def test_cross_cutting_categories(self) -> None:
        cross_cutting = {
            "moat_durability",
            "moat_threat",
            "counter_evidence",
            "moat_summary",
            "research_gap",
            "contradiction",
        }
        assert cross_cutting <= MOAT_FINDING_CATEGORIES

    def test_complete_set(self) -> None:
        expected = frozenset(
            {
                "brand_moat",
                "cost_advantage_moat",
                "network_effect_moat",
                "switching_cost_moat",
                "distribution_moat",
                "scale_moat",
                "regulatory_moat",
                "intangible_asset_moat",
                "technology_moat",
                "ecosystem_moat",
                "customer_lock_in_moat",
                "structural_moat",
                "competitive_position",
                "moat_durability",
                "moat_threat",
                "counter_evidence",
                "moat_summary",
                "research_gap",
                "contradiction",
            }
        )
        assert expected == MOAT_FINDING_CATEGORIES


# ===========================================================================
# MOAT_TYPE_TO_CATEGORY
# ===========================================================================


class TestMoatTypeToCategory:
    def test_covers_all_16_moat_types(self) -> None:
        assert set(MOAT_TYPE_TO_CATEGORY.keys()) == set(MoatType)

    def test_16_entries(self) -> None:
        assert len(MOAT_TYPE_TO_CATEGORY) == 16

    def test_all_categories_in_finding_categories(self) -> None:
        for category in MOAT_TYPE_TO_CATEGORY.values():
            assert category in MOAT_FINDING_CATEGORIES

    def test_brand_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.BRAND] == "brand_moat"

    def test_cost_advantage_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.COST_ADVANTAGE] == "cost_advantage_moat"

    def test_network_effect_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.NETWORK_EFFECT] == "network_effect_moat"

    def test_switching_cost_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.SWITCHING_COST] == "switching_cost_moat"

    def test_distribution_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.DISTRIBUTION] == "distribution_moat"

    def test_scale_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.SCALE] == "scale_moat"

    def test_regulatory_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.REGULATORY] == "regulatory_moat"

    def test_ip_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.IP] == "intangible_asset_moat"

    def test_technology_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.TECHNOLOGY] == "technology_moat"

    def test_data_maps_to_technology(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.DATA] == "technology_moat"

    def test_ecosystem_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.ECOSYSTEM] == "ecosystem_moat"

    def test_customer_embeddedness_mapping(self) -> None:
        assert MOAT_TYPE_TO_CATEGORY[MoatType.CUSTOMER_EMBEDDEDNESS] == "customer_lock_in_moat"

    def test_structural_moat_group(self) -> None:
        structural_types = [
            MoatType.MANUFACTURING,
            MoatType.SUPPLY_CHAIN,
            MoatType.CAPITAL_ACCESS,
            MoatType.LOCATION,
        ]
        for mt in structural_types:
            assert MOAT_TYPE_TO_CATEGORY[mt] == "structural_moat"

    def test_maps_to_12_unique_categories(self) -> None:
        unique_categories = set(MOAT_TYPE_TO_CATEGORY.values())
        assert len(unique_categories) == 12


# ===========================================================================
# MoatResearchConfig
# ===========================================================================


class TestMoatResearchConfig:
    def test_defaults(self) -> None:
        config = MoatResearchConfig()
        assert config.token_budget == 25_000
        assert config.token_warning_threshold == 20_000
        assert config.max_llm_attempts == 2
        assert config.document_types is None
        assert config.source_limit == 20
        assert config.concurrent_retrievals == 5
        assert config.extraction_model is None
        assert config.analysis_model is None

    def test_custom_values(self) -> None:
        config = MoatResearchConfig(
            token_budget=20_000,
            token_warning_threshold=16_000,
            max_llm_attempts=1,
            document_types=[DocumentType.ANNUAL_REPORT],
            source_limit=10,
            concurrent_retrievals=3,
            extraction_model="haiku",
            analysis_model="sonnet",
        )
        assert config.token_budget == 20_000
        assert config.max_llm_attempts == 1
        assert config.document_types == [DocumentType.ANNUAL_REPORT]

    def test_frozen(self) -> None:
        config = MoatResearchConfig()
        with pytest.raises(ValidationError):
            config.token_budget = 50_000  # type: ignore[misc]

    def test_token_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            MoatResearchConfig(token_budget=0)

    def test_max_llm_attempts_max_is_3(self) -> None:
        with pytest.raises(ValidationError):
            MoatResearchConfig(max_llm_attempts=4)

    def test_source_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MoatResearchConfig(source_limit=0)
        with pytest.raises(ValidationError):
            MoatResearchConfig(source_limit=101)

    def test_concurrent_retrievals_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MoatResearchConfig(concurrent_retrievals=0)
        with pytest.raises(ValidationError):
            MoatResearchConfig(concurrent_retrievals=21)


# ===========================================================================
# MoatResearchRequest
# ===========================================================================


class TestMoatResearchRequest:
    def test_valid_request(self) -> None:
        req = MoatResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="test_user",
        )
        assert req.company_id == COMPANY_UUID
        assert req.observation_date == date(2025, 9, 30)
        assert req.initiated_by == "test_user"
        assert req.configuration is None

    def test_with_configuration(self) -> None:
        config = MoatResearchConfig(token_budget=20_000)
        req = MoatResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
            initiated_by="system",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.token_budget == 20_000

    def test_frozen(self) -> None:
        req = MoatResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        with pytest.raises(ValidationError):
            req.initiated_by = "other"  # type: ignore[misc]

    def test_empty_initiated_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="",
            )


# ===========================================================================
# MoatResearchResult
# ===========================================================================


class TestMoatResearchResult:
    def test_completed(self) -> None:
        result = MoatResearchResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            finding_ids=[FINDING_UUID],
            assessment_ids=[uuid.uuid4()],
        )
        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert len(result.finding_ids) == 1
        assert len(result.assessment_ids) == 1
        assert result.error is None

    def test_failed(self) -> None:
        result = MoatResearchResult(
            status="FAILED",
            run_id=RUN_UUID,
            error="Step 1 failed: company not found",
        )
        assert result.status == "FAILED"
        assert result.finding_ids == []
        assert result.assessment_ids == []
        assert result.error is not None

    def test_partial(self) -> None:
        result = MoatResearchResult(
            status="PARTIAL",
            run_id=RUN_UUID,
            finding_ids=[FINDING_UUID],
            error="Token budget exhausted",
        )
        assert result.status == "PARTIAL"
        assert len(result.finding_ids) == 1

    def test_frozen(self) -> None:
        result = MoatResearchResult(status="COMPLETED", run_id=RUN_UUID)
        with pytest.raises(ValidationError):
            result.status = "FAILED"  # type: ignore[misc]


# ===========================================================================
# FindingSummary
# ===========================================================================


class TestFindingSummary:
    def test_construction(self) -> None:
        fs = FindingSummary(
            finding_id=FINDING_UUID,
            category="brand_moat",
            finding_type=FindingType.FACT,
            content="Strong brand recognition in Indian market",
            confidence=ConfidenceLevel.HIGH,
        )
        assert fs.finding_id == FINDING_UUID
        assert fs.category == "brand_moat"
        assert fs.finding_type == FindingType.FACT
        assert fs.confidence == ConfidenceLevel.HIGH

    def test_frozen(self) -> None:
        fs = FindingSummary(
            finding_id=FINDING_UUID,
            category="test",
            finding_type=FindingType.FACT,
            content="Test",
            confidence=ConfidenceLevel.HIGH,
        )
        with pytest.raises(ValidationError):
            fs.category = "other"  # type: ignore[misc]

    def test_all_finding_types(self) -> None:
        for ft in FindingType:
            fs = FindingSummary(
                finding_id=FINDING_UUID,
                category="test",
                finding_type=ft,
                content="Test",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert fs.finding_type == ft


# ===========================================================================
# LoadContextInput / LoadContextOutput
# ===========================================================================


class TestLoadContextContracts:
    def test_input(self) -> None:
        inp = LoadContextInput(
            company_id=COMPANY_UUID,
            industry_id=INDUSTRY_UUID,
            observation_date=date(2025, 9, 30),
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.industry_id == INDUSTRY_UUID

    def test_input_no_industry(self) -> None:
        inp = LoadContextInput(
            company_id=COMPANY_UUID,
            industry_id=None,
            observation_date=date(2025, 9, 30),
        )
        assert inp.industry_id is None

    def test_output_with_research(self) -> None:
        findings = [
            FindingSummary(
                finding_id=FINDING_UUID,
                category="company_identity",
                finding_type=FindingType.FACT,
                content="Test company",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        out = LoadContextOutput(
            company_id=COMPANY_UUID,
            company_name="Reliance Industries Ltd",
            nse_symbol="RELIANCE",
            industry_id=INDUSTRY_UUID,
            industry_name="Oil & Gas",
            company_findings=findings,
            industry_findings=[],
            has_company_research=True,
            has_industry_research=False,
        )
        assert out.company_name == "Reliance Industries Ltd"
        assert out.has_company_research is True
        assert out.has_industry_research is False
        assert len(out.company_findings) == 1

    def test_output_no_prior_research(self) -> None:
        out = LoadContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test Co",
            nse_symbol=None,
            industry_id=None,
            industry_name=None,
            company_findings=[],
            industry_findings=[],
            has_company_research=False,
            has_industry_research=False,
        )
        assert out.nse_symbol is None
        assert out.industry_id is None
        assert not out.has_company_research

    def test_output_frozen(self) -> None:
        out = LoadContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test",
            nse_symbol=None,
            industry_id=None,
            industry_name=None,
            company_findings=[],
            industry_findings=[],
            has_company_research=False,
            has_industry_research=False,
        )
        with pytest.raises(ValidationError):
            out.company_name = "Other"  # type: ignore[misc]


# ===========================================================================
# DiscoverMoatSourcesInput / Output
# ===========================================================================


class TestDiscoverMoatSourcesContracts:
    def test_input_defaults(self) -> None:
        inp = DiscoverMoatSourcesInput(
            company_name="Reliance Industries",
            nse_symbol="RELIANCE",
            industry_name="Oil & Gas",
            observation_date=date(2025, 9, 30),
        )
        assert inp.limit == 20
        assert inp.document_types is None

    def test_input_with_types(self) -> None:
        inp = DiscoverMoatSourcesInput(
            company_name="TCS",
            nse_symbol="TCS",
            industry_name="IT Services",
            observation_date=date(2025, 9, 30),
            document_types=[DocumentType.ANNUAL_REPORT, DocumentType.NEWS],
            limit=10,
        )
        assert inp.document_types is not None
        assert len(inp.document_types) == 2
        assert inp.limit == 10

    def test_input_no_symbol(self) -> None:
        inp = DiscoverMoatSourcesInput(
            company_name="Test Co",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2025, 9, 30),
        )
        assert inp.nse_symbol is None
        assert inp.industry_name is None

    def test_input_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DiscoverMoatSourcesInput(
                company_name="Test",
                nse_symbol=None,
                industry_name=None,
                observation_date=date(2025, 9, 30),
                limit=0,
            )
        with pytest.raises(ValidationError):
            DiscoverMoatSourcesInput(
                company_name="Test",
                nse_symbol=None,
                industry_name=None,
                observation_date=date(2025, 9, 30),
                limit=101,
            )

    def test_output_empty(self) -> None:
        out = DiscoverMoatSourcesOutput(candidates=[])
        assert out.candidates == []

    def test_output_reuses_source_candidate(self) -> None:
        candidates = [
            SourceCandidate(
                source_id="filing-1",
                source_type=DocumentType.ANNUAL_REPORT,
                provider="corporate_filings",
                title="Annual Report FY2025",
                publication_date=date(2025, 5, 30),
                source_tier=SourceTier.TIER_1,
            ),
        ]
        out = DiscoverMoatSourcesOutput(candidates=candidates)
        assert len(out.candidates) == 1
        assert out.candidates[0].source_tier == SourceTier.TIER_1


# ===========================================================================
# ThreatItem
# ===========================================================================


class TestThreatItem:
    def test_full(self) -> None:
        t = ThreatItem(
            description="Digital disruption from fintech startups",
            severity="HIGH",
            timeframe="3-5 years",
            evidence_basis="Increasing fintech market share per RBI data",
        )
        assert t.description == "Digital disruption from fintech startups"
        assert t.severity == "HIGH"
        assert t.timeframe == "3-5 years"
        assert t.evidence_basis is not None

    def test_minimal(self) -> None:
        t = ThreatItem(
            description="Regulatory risk",
            severity="MEDIUM",
        )
        assert t.timeframe is None
        assert t.evidence_basis is None

    def test_frozen(self) -> None:
        t = ThreatItem(description="Test", severity="LOW")
        with pytest.raises(ValidationError):
            t.description = "Other"  # type: ignore[misc]

    def test_serialization_round_trip(self) -> None:
        t = ThreatItem(
            description="Threat 1",
            severity="HIGH",
            timeframe="2-3 years",
            evidence_basis="Source A",
        )
        data = t.model_dump(mode="json")
        t2 = ThreatItem.model_validate(data)
        assert t == t2

    def test_model_dump_produces_dict(self) -> None:
        t = ThreatItem(
            description="Test threat",
            severity="MEDIUM",
            timeframe="1 year",
        )
        dumped = t.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["description"] == "Test threat"
        assert dumped["severity"] == "MEDIUM"


# ===========================================================================
# MoatAssessmentDraft
# ===========================================================================


class TestMoatAssessmentDraft:
    def test_full(self) -> None:
        draft = MoatAssessmentDraft(
            moat_type="BRAND",
            strength="WIDE",
            durability_years=10,
            explanation="Dominant brand in Indian consumer market",
            threats=[
                ThreatItem(description="Private labels", severity="MEDIUM"),
            ],
            competitor_comparison={"HDFC": "Narrower brand moat"},
            confidence="HIGH",
            evidence_indices=[0, 1, 2],
            counter_evidence_indices=[3],
        )
        assert draft.moat_type == "BRAND"
        assert draft.strength == "WIDE"
        assert draft.durability_years == 10
        assert draft.threats is not None
        assert len(draft.threats) == 1
        assert draft.evidence_indices == [0, 1, 2]

    def test_none_moat(self) -> None:
        draft = MoatAssessmentDraft(
            moat_type="LOCATION",
            strength="NONE",
            explanation="No location-based advantage identified",
            confidence="LOW",
        )
        assert draft.strength == "NONE"
        assert draft.durability_years is None
        assert draft.threats is None
        assert draft.competitor_comparison is None
        assert draft.evidence_indices is None
        assert draft.counter_evidence_indices is None

    def test_frozen(self) -> None:
        draft = MoatAssessmentDraft(
            moat_type="BRAND",
            strength="NARROW",
            explanation="Test",
            confidence="MEDIUM",
        )
        with pytest.raises(ValidationError):
            draft.strength = "WIDE"  # type: ignore[misc]


# ===========================================================================
# MoatAnalysisOutput
# ===========================================================================


class TestMoatAnalysisOutput:
    def test_with_assessments_and_findings(self) -> None:
        out = MoatAnalysisOutput(
            assessments=[
                MoatAssessmentDraft(
                    moat_type="BRAND",
                    strength="WIDE",
                    explanation="Strong brand",
                    confidence="HIGH",
                ),
            ],
            findings=[
                GeneratedFinding(
                    finding_type=FindingType.AI_INFERENCE,
                    category="brand_moat",
                    content="Brand moat assessment",
                    confidence=ConfidenceLevel.HIGH,
                    evidence_indices=[0],
                ),
            ],
        )
        assert len(out.assessments) == 1
        assert len(out.findings) == 1

    def test_empty_assessments(self) -> None:
        out = MoatAnalysisOutput(assessments=[], findings=[])
        assert len(out.assessments) == 0

    def test_reuses_generated_finding(self) -> None:
        finding = GeneratedFinding(
            finding_type=FindingType.FACT,
            category="brand_moat",
            content="Test",
            confidence=ConfidenceLevel.HIGH,
        )
        out = MoatAnalysisOutput(assessments=[], findings=[finding])
        assert out.findings[0].finding_type == FindingType.FACT


# ===========================================================================
# MoatValidationIssue / MoatValidationResult
# ===========================================================================


class TestMoatValidationContracts:
    def test_issue(self) -> None:
        issue = MoatValidationIssue(
            moat_type="BRAND",
            issue_type="no_evidence",
            message="WIDE strength claimed without supporting evidence",
            action="DOWNGRADED_TO_NONE",
        )
        assert issue.moat_type == "BRAND"
        assert issue.action == "DOWNGRADED_TO_NONE"

    def test_result_all_valid(self) -> None:
        result = MoatValidationResult(
            total_assessments=16,
            valid_count=16,
            downgraded_count=0,
            issues=[],
        )
        assert result.total_assessments == 16
        assert len(result.issues) == 0

    def test_result_with_downgrades(self) -> None:
        result = MoatValidationResult(
            total_assessments=16,
            valid_count=14,
            downgraded_count=2,
            issues=[
                MoatValidationIssue(
                    moat_type="IP",
                    issue_type="no_evidence",
                    message="No evidence for IP moat",
                    action="DOWNGRADED_TO_NONE",
                ),
                MoatValidationIssue(
                    moat_type="SCALE",
                    issue_type="weak_evidence",
                    message="Insufficient evidence for WIDE scale moat",
                    action="DOWNGRADED_TO_NARROW",
                ),
            ],
        )
        assert result.downgraded_count == 2
        assert len(result.issues) == 2

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MoatValidationResult(
                total_assessments=-1,
                valid_count=0,
                downgraded_count=0,
                issues=[],
            )

    def test_frozen(self) -> None:
        result = MoatValidationResult(
            total_assessments=16,
            valid_count=16,
            downgraded_count=0,
            issues=[],
        )
        with pytest.raises(ValidationError):
            result.total_assessments = 0  # type: ignore[misc]


# ===========================================================================
# DurabilityChallengeOutput
# ===========================================================================


class TestDurabilityChallengeOutput:
    def test_with_findings(self) -> None:
        out = DurabilityChallengeOutput(
            findings=[
                GeneratedFinding(
                    finding_type=FindingType.AI_INFERENCE,
                    category="moat_durability",
                    content="Brand moat likely durable for 10+ years",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                GeneratedFinding(
                    finding_type=FindingType.AI_INFERENCE,
                    category="moat_threat",
                    content="Digital disruption threatens distribution moat",
                    confidence=ConfidenceLevel.HIGH,
                    evidence_indices=[2],
                ),
                GeneratedFinding(
                    finding_type=FindingType.AI_INFERENCE,
                    category="counter_evidence",
                    content="Competitor analysis suggests narrower moat",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        assert len(out.findings) == 3
        categories = {f.category for f in out.findings}
        assert categories <= MOAT_FINDING_CATEGORIES

    def test_empty_findings(self) -> None:
        out = DurabilityChallengeOutput(findings=[])
        assert len(out.findings) == 0


# ===========================================================================
# GetPeerDataInput / PeerCompanySummary / GetPeerDataOutput
# ===========================================================================


class TestGetPeerDataContracts:
    def test_input_defaults(self) -> None:
        inp = GetPeerDataInput(
            company_id=COMPANY_UUID,
            industry_id=INDUSTRY_UUID,
        )
        assert inp.limit == 5

    def test_input_custom_limit(self) -> None:
        inp = GetPeerDataInput(
            company_id=COMPANY_UUID,
            industry_id=INDUSTRY_UUID,
            limit=10,
        )
        assert inp.limit == 10

    def test_input_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GetPeerDataInput(
                company_id=COMPANY_UUID,
                industry_id=INDUSTRY_UUID,
                limit=0,
            )
        with pytest.raises(ValidationError):
            GetPeerDataInput(
                company_id=COMPANY_UUID,
                industry_id=INDUSTRY_UUID,
                limit=21,
            )

    def test_peer_summary(self) -> None:
        peer = PeerCompanySummary(
            company_id=uuid.uuid4(),
            name="TCS",
            nse_symbol="TCS",
            market_cap=Decimal("1200000.0000"),
        )
        assert peer.name == "TCS"
        assert peer.market_cap == Decimal("1200000.0000")

    def test_peer_summary_optional_fields(self) -> None:
        peer = PeerCompanySummary(
            company_id=uuid.uuid4(),
            name="Private Co",
        )
        assert peer.nse_symbol is None
        assert peer.market_cap is None

    def test_output_empty(self) -> None:
        out = GetPeerDataOutput(peers=[])
        assert out.peers == []

    def test_output_with_peers(self) -> None:
        peers = [
            PeerCompanySummary(
                company_id=uuid.uuid4(),
                name="TCS",
                nse_symbol="TCS",
                market_cap=Decimal("1200000"),
            ),
            PeerCompanySummary(
                company_id=uuid.uuid4(),
                name="Infosys",
                nse_symbol="INFY",
                market_cap=Decimal("800000"),
            ),
        ]
        out = GetPeerDataOutput(peers=peers)
        assert len(out.peers) == 2


# ===========================================================================
# MoatAssessmentItem / PersistMoatAssessmentsInput / Output
# ===========================================================================


class TestMoatAssessmentItem:
    def test_full(self) -> None:
        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.WIDE,
            durability_years=10,
            threats=[
                {"description": "Private labels", "severity": "MEDIUM", "timeframe": "5 years"},
            ],
            competitor_comparison={"TCS": "Narrower brand moat"},
            confidence=ConfidenceLevel.HIGH,
            explanation="Dominant brand recognition",
            evidence_ids=[EVIDENCE_UUID],
        )
        assert item.moat_type == MoatType.BRAND
        assert item.strength == MoatStrength.WIDE
        assert item.durability_years == 10
        assert item.threats is not None
        assert len(item.threats) == 1
        assert isinstance(item.threats[0], dict)

    def test_none_moat(self) -> None:
        item = MoatAssessmentItem(
            moat_type=MoatType.LOCATION,
            strength=MoatStrength.NONE,
            confidence=ConfidenceLevel.LOW,
        )
        assert item.strength == MoatStrength.NONE
        assert item.durability_years is None
        assert item.threats is None
        assert item.competitor_comparison is None
        assert item.explanation is None
        assert item.evidence_ids == []

    def test_uses_moat_type_enum(self) -> None:
        for mt in MoatType:
            item = MoatAssessmentItem(
                moat_type=mt,
                strength=MoatStrength.NONE,
                confidence=ConfidenceLevel.LOW,
            )
            assert item.moat_type == mt

    def test_uses_moat_strength_enum(self) -> None:
        for ms in MoatStrength:
            item = MoatAssessmentItem(
                moat_type=MoatType.BRAND,
                strength=ms,
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert item.strength == ms

    def test_uses_confidence_level_enum(self) -> None:
        for cl in ConfidenceLevel:
            item = MoatAssessmentItem(
                moat_type=MoatType.BRAND,
                strength=MoatStrength.NONE,
                confidence=cl,
            )
            assert item.confidence == cl

    def test_threats_is_list_of_dicts(self) -> None:
        threats: list[dict[str, object]] = [
            {"description": "Threat 1", "severity": "HIGH"},
            {"description": "Threat 2", "severity": "LOW", "timeframe": "2 years"},
        ]
        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.NARROW,
            threats=threats,
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert item.threats is not None
        assert len(item.threats) == 2
        assert item.threats[0]["description"] == "Threat 1"

    def test_frozen(self) -> None:
        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.NONE,
            confidence=ConfidenceLevel.LOW,
        )
        with pytest.raises(ValidationError):
            item.strength = MoatStrength.WIDE  # type: ignore[misc]


class TestPersistMoatAssessmentsContracts:
    def test_input(self) -> None:
        inp = PersistMoatAssessmentsInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.BRAND,
                    strength=MoatStrength.WIDE,
                    confidence=ConfidenceLevel.HIGH,
                    explanation="Strong brand",
                    evidence_ids=[EVIDENCE_UUID],
                ),
            ],
        )
        assert inp.company_id == COMPANY_UUID
        assert len(inp.assessments) == 1

    def test_input_empty_assessments_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistMoatAssessmentsInput(
                company_id=COMPANY_UUID,
                research_run_id=RUN_UUID,
                assessments=[],
            )

    def test_output(self) -> None:
        out = PersistMoatAssessmentsOutput(
            assessment_ids=[uuid.uuid4(), uuid.uuid4()],
        )
        assert len(out.assessment_ids) == 2


# ===========================================================================
# MOAT_RESEARCH_STEPS
# ===========================================================================


class TestMoatResearchSteps:
    def test_seven_steps(self) -> None:
        assert len(MOAT_RESEARCH_STEPS) == 7

    def test_is_tuple(self) -> None:
        assert isinstance(MOAT_RESEARCH_STEPS, tuple)

    def test_step_order_sequence(self) -> None:
        orders = [s.step_order for s in MOAT_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_step_names(self) -> None:
        names = [s.step_name for s in MOAT_RESEARCH_STEPS]
        assert names == [
            "company_context_load",
            "moat_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "moat_analysis",
            "moat_validation",
            "durability_challenge",
        ]

    def test_step_types(self) -> None:
        types = [s.step_type for s in MOAT_RESEARCH_STEPS]
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
        llm_steps = [s for s in MOAT_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        assert [s.step_name for s in llm_steps] == [
            "evidence_extraction",
            "moat_analysis",
            "durability_challenge",
        ]

    def test_deterministic_steps(self) -> None:
        det_steps = [s for s in MOAT_RESEARCH_STEPS if s.step_type == STEP_TYPE_DETERMINISTIC]
        assert len(det_steps) == 2
        assert [s.step_name for s in det_steps] == [
            "company_context_load",
            "moat_validation",
        ]

    def test_provider_steps(self) -> None:
        prov_steps = [s for s in MOAT_RESEARCH_STEPS if s.step_type == STEP_TYPE_PROVIDER_CALL]
        assert len(prov_steps) == 2
        assert [s.step_name for s in prov_steps] == [
            "moat_source_discovery",
            "document_retrieval",
        ]

    def test_timeout_values(self) -> None:
        timeouts = {s.step_name: s.timeout_seconds for s in MOAT_RESEARCH_STEPS}
        assert timeouts["company_context_load"] == 10
        assert timeouts["moat_source_discovery"] == 30
        assert timeouts["document_retrieval"] == 60
        assert timeouts["evidence_extraction"] == 120
        assert timeouts["moat_analysis"] == 120
        assert timeouts["moat_validation"] == 10
        assert timeouts["durability_challenge"] == 60


# ===========================================================================
# Serialization round-trips
# ===========================================================================


class TestMoatSerialization:
    def test_moat_research_request_round_trip(self) -> None:
        req = MoatResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
            configuration=MoatResearchConfig(token_budget=20_000),
        )
        data = req.model_dump(mode="json")
        req2 = MoatResearchRequest.model_validate(data)
        assert req == req2

    def test_load_context_output_round_trip(self) -> None:
        out = LoadContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test Co",
            nse_symbol="TEST",
            industry_id=INDUSTRY_UUID,
            industry_name="IT",
            company_findings=[
                FindingSummary(
                    finding_id=FINDING_UUID,
                    category="company_identity",
                    finding_type=FindingType.FACT,
                    content="Test",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
            industry_findings=[],
            has_company_research=True,
            has_industry_research=False,
        )
        data = out.model_dump(mode="json")
        out2 = LoadContextOutput.model_validate(data)
        assert out == out2

    def test_moat_assessment_item_round_trip(self) -> None:
        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.WIDE,
            durability_years=10,
            threats=[{"description": "Threat A", "severity": "HIGH"}],
            competitor_comparison={"peer": "weaker"},
            confidence=ConfidenceLevel.HIGH,
            explanation="Strong brand",
            evidence_ids=[EVIDENCE_UUID],
        )
        data = item.model_dump(mode="json")
        item2 = MoatAssessmentItem.model_validate(data)
        assert item2.moat_type == MoatType.BRAND
        assert item2.strength == MoatStrength.WIDE

    def test_threat_item_to_dict_for_persistence(self) -> None:
        threat = ThreatItem(
            description="Digital disruption",
            severity="HIGH",
            timeframe="3-5 years",
            evidence_basis="Market data",
        )
        dumped = threat.model_dump()
        assert isinstance(dumped, dict)
        assert set(dumped.keys()) == {"description", "severity", "timeframe", "evidence_basis"}

    def test_threat_list_serialization_path(self) -> None:
        threats = [
            ThreatItem(description="T1", severity="HIGH"),
            ThreatItem(description="T2", severity="LOW", timeframe="1 year"),
        ]
        serialized = [t.model_dump() for t in threats]
        assert isinstance(serialized, list)
        assert all(isinstance(d, dict) for d in serialized)
        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.NARROW,
            threats=serialized,
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert item.threats == serialized

    def test_peer_company_decimal_preserved(self) -> None:
        peer = PeerCompanySummary(
            company_id=COMPANY_UUID,
            name="Test",
            market_cap=Decimal("1500000.0000"),
        )
        data = peer.model_dump(mode="json")
        peer2 = PeerCompanySummary.model_validate(data)
        assert isinstance(peer2.market_cap, Decimal)

    def test_moat_validation_result_round_trip(self) -> None:
        result = MoatValidationResult(
            total_assessments=16,
            valid_count=14,
            downgraded_count=2,
            issues=[
                MoatValidationIssue(
                    moat_type="IP",
                    issue_type="no_evidence",
                    message="No evidence",
                    action="DOWNGRADED_TO_NONE",
                ),
            ],
        )
        data = result.model_dump(mode="json")
        result2 = MoatValidationResult.model_validate(data)
        assert result == result2
