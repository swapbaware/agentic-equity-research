"""Comprehensive tests for Phase 11.1 Management & Governance Agent contracts."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_AGENT_TOKEN_BUDGET,
    GOVERNANCE_AGENT_TOKEN_WARNING,
    GOVERNANCE_FINDING_CATEGORIES,
    GOVERNANCE_RED_FLAG_CATEGORIES,
    GOVERNANCE_RESEARCH_STEPS,
    MAX_LLM_ATTEMPTS,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    CorporateActionSnapshot,
    DiscoverGovernanceSourcesInput,
    DiscoverGovernanceSourcesOutput,
    FindingSummary,
    GeneratedFinding,
    GetCorporateActionsInput,
    GetCorporateActionsOutput,
    GetShareholdingInput,
    GetShareholdingOutput,
    GovernanceAnalysisOutput,
    GovernanceRedFlag,
    GovernanceValidationIssue,
    GovernanceValidationResult,
    LoadGovernanceContextInput,
    LoadGovernanceContextOutput,
    ManagementGovernanceConfig,
    ManagementGovernanceResearchRequest,
    ManagementGovernanceResult,
    ManagementStatementSummary,
    ManagementStatementUpdate,
    NewManagementStatement,
    PersistGovernanceDataInput,
    PersistGovernanceDataOutput,
    PersistShareholdingInput,
    PersistShareholdingOutput,
    PersistStatementsInput,
    PersistStatementsOutput,
    RetrievedDocument,
    RetrieveGovernanceDocumentsInput,
    RetrieveGovernanceDocumentsOutput,
    ShareholdingSnapshot,
    SourceCandidate,
)
from app.models.enums import (
    ConfidenceLevel,
    CorporateActionType,
    DocumentType,
    FindingType,
    ManagementStatementCategory,
    ManagementStatementStatus,
    SourceTier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STATEMENT_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
FINDING_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
EVIDENCE_UUID = uuid.UUID("fedcbafe-dcba-fedc-bafe-dcbafedcbafe")


# ===========================================================================
# Constants
# ===========================================================================


class TestGovernanceConstants:
    def test_agent_token_budget(self) -> None:
        assert GOVERNANCE_AGENT_TOKEN_BUDGET == 20_000

    def test_agent_token_warning(self) -> None:
        assert GOVERNANCE_AGENT_TOKEN_WARNING == 16_000

    def test_warning_is_80_percent(self) -> None:
        assert int(GOVERNANCE_AGENT_TOKEN_BUDGET * 0.8) == GOVERNANCE_AGENT_TOKEN_WARNING

    def test_agent_name(self) -> None:
        assert GOVERNANCE_AGENT_NAME == "management_governance_agent"

    def test_max_llm_attempts_shared(self) -> None:
        assert MAX_LLM_ATTEMPTS == 2


# ===========================================================================
# GOVERNANCE_FINDING_CATEGORIES
# ===========================================================================


class TestGovernanceFindingCategories:
    def test_is_frozenset(self) -> None:
        assert isinstance(GOVERNANCE_FINDING_CATEGORIES, frozenset)

    def test_has_13_categories(self) -> None:
        assert len(GOVERNANCE_FINDING_CATEGORIES) == 13

    def test_complete_set(self) -> None:
        expected = frozenset(
            {
                "management_claim",
                "promise_tracking",
                "shareholding",
                "promoter_pledge",
                "capital_allocation",
                "related_party_transaction",
                "auditor_qualification",
                "executive_compensation",
                "subsidiary_complexity",
                "equity_dilution",
                "governance_red_flag",
                "governance_general",
                "data_gap",
            }
        )
        assert expected == GOVERNANCE_FINDING_CATEGORIES

    def test_domain_categories_present(self) -> None:
        domain = {
            "management_claim",
            "promise_tracking",
            "shareholding",
            "promoter_pledge",
            "capital_allocation",
            "related_party_transaction",
            "auditor_qualification",
            "executive_compensation",
            "subsidiary_complexity",
            "equity_dilution",
        }
        assert domain <= GOVERNANCE_FINDING_CATEGORIES

    def test_cross_cutting_categories_present(self) -> None:
        cross_cutting = {
            "governance_red_flag",
            "governance_general",
            "data_gap",
        }
        assert cross_cutting <= GOVERNANCE_FINDING_CATEGORIES


# ===========================================================================
# GOVERNANCE_RED_FLAG_CATEGORIES
# ===========================================================================


class TestGovernanceRedFlagCategories:
    def test_is_frozenset(self) -> None:
        assert isinstance(GOVERNANCE_RED_FLAG_CATEGORIES, frozenset)

    def test_has_9_categories(self) -> None:
        assert len(GOVERNANCE_RED_FLAG_CATEGORIES) == 9

    def test_complete_set(self) -> None:
        expected = frozenset(
            {
                "promoter_pledge_elevation",
                "declining_promoter_holding",
                "auditor_qualification",
                "auditor_change",
                "related_party_materiality",
                "executive_compensation_excess",
                "promise_track_record",
                "equity_dilution",
                "subsidiary_opacity",
            }
        )
        assert expected == GOVERNANCE_RED_FLAG_CATEGORIES

    def test_no_overlap_with_finding_categories(self) -> None:
        overlap = GOVERNANCE_RED_FLAG_CATEGORIES & GOVERNANCE_FINDING_CATEGORIES
        assert overlap == {"auditor_qualification", "equity_dilution"}


# ===========================================================================
# ManagementGovernanceConfig
# ===========================================================================


class TestManagementGovernanceConfig:
    def test_defaults(self) -> None:
        config = ManagementGovernanceConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == 2
        assert config.filing_types is None
        assert config.shareholding_quarters == 8
        assert config.corporate_action_years == 5
        assert config.concurrent_retrievals == 5
        assert config.extraction_model is None
        assert config.analysis_model is None

    def test_custom_values(self) -> None:
        config = ManagementGovernanceConfig(
            token_budget=15_000,
            token_warning_threshold=12_000,
            max_llm_attempts=1,
            filing_types=["annual_report", "quarterly_result"],
            shareholding_quarters=12,
            corporate_action_years=3,
            concurrent_retrievals=3,
            extraction_model="haiku",
            analysis_model="sonnet",
        )
        assert config.token_budget == 15_000
        assert config.max_llm_attempts == 1
        assert config.filing_types == ["annual_report", "quarterly_result"]
        assert config.shareholding_quarters == 12

    def test_frozen(self) -> None:
        config = ManagementGovernanceConfig()
        with pytest.raises(ValidationError):
            config.token_budget = 50_000

    def test_token_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(token_budget=0)

    def test_max_llm_attempts_max_is_3(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(max_llm_attempts=4)

    def test_shareholding_quarters_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(shareholding_quarters=0)
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(shareholding_quarters=21)

    def test_corporate_action_years_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(corporate_action_years=0)
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(corporate_action_years=11)

    def test_concurrent_retrievals_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(concurrent_retrievals=0)
        with pytest.raises(ValidationError):
            ManagementGovernanceConfig(concurrent_retrievals=21)


# ===========================================================================
# ManagementGovernanceResearchRequest
# ===========================================================================


class TestManagementGovernanceResearchRequest:
    def test_valid_request(self) -> None:
        req = ManagementGovernanceResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="test_user",
        )
        assert req.company_id == COMPANY_UUID
        assert req.observation_date == date(2025, 9, 30)
        assert req.initiated_by == "test_user"
        assert req.configuration is None

    def test_with_configuration(self) -> None:
        config = ManagementGovernanceConfig(token_budget=15_000)
        req = ManagementGovernanceResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
            initiated_by="system",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.token_budget == 15_000

    def test_frozen(self) -> None:
        req = ManagementGovernanceResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        with pytest.raises(ValidationError):
            req.initiated_by = "other"

    def test_empty_initiated_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="",
            )


# ===========================================================================
# ManagementGovernanceResult
# ===========================================================================


class TestManagementGovernanceResult:
    def test_completed(self) -> None:
        result = ManagementGovernanceResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            finding_ids=[FINDING_UUID],
            statement_ids=[STATEMENT_UUID],
            red_flag_count=2,
            total_findings=5,
            total_statements_created=3,
            total_statements_updated=1,
        )
        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert len(result.finding_ids) == 1
        assert len(result.statement_ids) == 1
        assert result.red_flag_count == 2
        assert result.total_findings == 5
        assert result.error is None

    def test_failed(self) -> None:
        result = ManagementGovernanceResult(
            status="FAILED",
            run_id=RUN_UUID,
            error="Step 1 failed: company not found",
        )
        assert result.status == "FAILED"
        assert result.finding_ids == []
        assert result.statement_ids == []
        assert result.shareholding_snapshot_ids == []
        assert result.pledge_snapshot_ids == []
        assert result.corporate_action_ids == []
        assert result.red_flag_count == 0
        assert result.total_findings == 0
        assert result.total_statements_created == 0
        assert result.total_statements_updated == 0
        assert result.error is not None

    def test_partial(self) -> None:
        result = ManagementGovernanceResult(
            status="PARTIAL",
            run_id=RUN_UUID,
            finding_ids=[FINDING_UUID],
            error="Token budget exhausted",
        )
        assert result.status == "PARTIAL"
        assert len(result.finding_ids) == 1

    def test_frozen(self) -> None:
        result = ManagementGovernanceResult(status="COMPLETED", run_id=RUN_UUID)
        with pytest.raises(ValidationError):
            result.status = "FAILED"

    def test_red_flag_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ManagementGovernanceResult(
                status="COMPLETED",
                run_id=RUN_UUID,
                red_flag_count=-1,
            )

    def test_with_all_id_lists(self) -> None:
        result = ManagementGovernanceResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            finding_ids=[uuid.uuid4(), uuid.uuid4()],
            statement_ids=[uuid.uuid4()],
            shareholding_snapshot_ids=[uuid.uuid4(), uuid.uuid4(), uuid.uuid4()],
            pledge_snapshot_ids=[uuid.uuid4()],
            corporate_action_ids=[uuid.uuid4(), uuid.uuid4()],
            red_flag_count=1,
            total_findings=10,
            total_statements_created=4,
            total_statements_updated=2,
        )
        assert len(result.finding_ids) == 2
        assert len(result.shareholding_snapshot_ids) == 3
        assert len(result.pledge_snapshot_ids) == 1
        assert len(result.corporate_action_ids) == 2


# ===========================================================================
# ManagementStatementSummary
# ===========================================================================


class TestManagementStatementSummary:
    def test_full(self) -> None:
        summary = ManagementStatementSummary(
            id=STATEMENT_UUID,
            statement_date=date(2025, 1, 25),
            statement="Management expects 20% revenue growth in FY2026",
            category=ManagementStatementCategory.REVENUE_GUIDANCE,
            expected_outcome="20% revenue growth by March 2026",
            expected_timeframe="FY2026",
            status=ManagementStatementStatus.PENDING,
        )
        assert summary.id == STATEMENT_UUID
        assert summary.category == ManagementStatementCategory.REVENUE_GUIDANCE
        assert summary.status == ManagementStatementStatus.PENDING
        assert summary.expected_timeframe == "FY2026"

    def test_minimal(self) -> None:
        summary = ManagementStatementSummary(
            id=STATEMENT_UUID,
            statement_date=date(2025, 1, 25),
            statement="Plans to expand to 5 new cities",
            category=ManagementStatementCategory.EXPANSION,
            status=ManagementStatementStatus.PENDING,
        )
        assert summary.expected_outcome is None
        assert summary.expected_timeframe is None

    def test_frozen(self) -> None:
        summary = ManagementStatementSummary(
            id=STATEMENT_UUID,
            statement_date=date(2025, 1, 25),
            statement="Test",
            category=ManagementStatementCategory.OTHER,
            status=ManagementStatementStatus.PENDING,
        )
        with pytest.raises(ValidationError):
            summary.status = ManagementStatementStatus.MET

    def test_all_statuses(self) -> None:
        for status in ManagementStatementStatus:
            summary = ManagementStatementSummary(
                id=STATEMENT_UUID,
                statement_date=date(2025, 1, 1),
                statement="Test",
                category=ManagementStatementCategory.OTHER,
                status=status,
            )
            assert summary.status == status

    def test_all_categories(self) -> None:
        for category in ManagementStatementCategory:
            summary = ManagementStatementSummary(
                id=STATEMENT_UUID,
                statement_date=date(2025, 1, 1),
                statement="Test",
                category=category,
                status=ManagementStatementStatus.PENDING,
            )
            assert summary.category == category


# ===========================================================================
# LoadGovernanceContextInput / Output
# ===========================================================================


class TestLoadGovernanceContextContracts:
    def test_input(self) -> None:
        inp = LoadGovernanceContextInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.observation_date == date(2025, 9, 30)

    def test_input_frozen(self) -> None:
        inp = LoadGovernanceContextInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
        )
        with pytest.raises(ValidationError):
            inp.company_id = uuid.uuid4()

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
        statements = [
            ManagementStatementSummary(
                id=STATEMENT_UUID,
                statement_date=date(2025, 1, 25),
                statement="Revenue target 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        out = LoadGovernanceContextOutput(
            company_id=COMPANY_UUID,
            company_name="Reliance Industries Ltd",
            nse_symbol="RELIANCE",
            bse_code="500325",
            industry_name="Oil & Gas",
            company_findings=findings,
            has_company_research=True,
            existing_statements=statements,
        )
        assert out.company_name == "Reliance Industries Ltd"
        assert out.has_company_research is True
        assert len(out.company_findings) == 1
        assert len(out.existing_statements) == 1

    def test_output_no_prior_research(self) -> None:
        out = LoadGovernanceContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test Co",
            company_findings=[],
            has_company_research=False,
            existing_statements=[],
        )
        assert out.nse_symbol is None
        assert out.bse_code is None
        assert out.industry_name is None
        assert not out.has_company_research

    def test_output_frozen(self) -> None:
        out = LoadGovernanceContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test",
            company_findings=[],
            has_company_research=False,
            existing_statements=[],
        )
        with pytest.raises(ValidationError):
            out.company_name = "Other"


# ===========================================================================
# ShareholdingSnapshot
# ===========================================================================


class TestShareholdingSnapshot:
    def test_full(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 6, 30),
            quarter="Q1FY2026",
            promoter_holding_pct=Decimal("50.25"),
            fii_holding_pct=Decimal("22.30"),
            dii_holding_pct=Decimal("15.45"),
            public_holding_pct=Decimal("12.00"),
            total_shares=500_000_000,
            pledged_percentage=Decimal("5.50"),
            source_provider="ShareholdingProvider",
            source_tier=1,
        )
        assert snap.promoter_holding_pct == Decimal("50.25")
        assert snap.total_shares == 500_000_000
        assert snap.pledged_percentage == Decimal("5.50")
        assert snap.source_tier == 1

    def test_minimal(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY2025",
            promoter_holding_pct=Decimal("60.00"),
            fii_holding_pct=Decimal("15.00"),
            dii_holding_pct=Decimal("10.00"),
            public_holding_pct=Decimal("15.00"),
            source_provider="ShareholdingProvider",
        )
        assert snap.total_shares is None
        assert snap.pledged_percentage is None
        assert snap.source_tier == 1

    def test_frozen(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY2025",
            promoter_holding_pct=Decimal("60.00"),
            fii_holding_pct=Decimal("15.00"),
            dii_holding_pct=Decimal("10.00"),
            public_holding_pct=Decimal("15.00"),
            source_provider="ShareholdingProvider",
        )
        with pytest.raises(ValidationError):
            snap.promoter_holding_pct = Decimal("70.00")

    def test_decimal_types(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4",
            promoter_holding_pct=Decimal("50.25"),
            fii_holding_pct=Decimal("22.30"),
            dii_holding_pct=Decimal("15.45"),
            public_holding_pct=Decimal("12.00"),
            source_provider="test",
        )
        assert isinstance(snap.promoter_holding_pct, Decimal)
        assert isinstance(snap.fii_holding_pct, Decimal)
        assert isinstance(snap.dii_holding_pct, Decimal)
        assert isinstance(snap.public_holding_pct, Decimal)


# ===========================================================================
# CorporateActionSnapshot
# ===========================================================================


class TestCorporateActionSnapshot:
    def test_dividend(self) -> None:
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2025, 7, 15),
            record_date=date(2025, 7, 18),
            details="Interim dividend of Rs 10 per share",
            value=Decimal("10.00"),
            source_provider="CorporateActionsProvider",
        )
        assert action.action_type == CorporateActionType.DIVIDEND
        assert action.value == Decimal("10.00")

    def test_split(self) -> None:
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2025, 8, 1),
            details="Stock split 1:5",
            source_provider="CorporateActionsProvider",
        )
        assert action.action_type == CorporateActionType.SPLIT
        assert action.record_date is None
        assert action.value is None

    def test_all_action_types(self) -> None:
        for at in CorporateActionType:
            action = CorporateActionSnapshot(
                action_type=at,
                details=f"Test {at.value}",
                source_provider="test",
            )
            assert action.action_type == at

    def test_frozen(self) -> None:
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.BUYBACK,
            details="Buyback at Rs 500",
            source_provider="test",
        )
        with pytest.raises(ValidationError):
            action.details = "Other"


# ===========================================================================
# DiscoverGovernanceSourcesInput / Output
# ===========================================================================


class TestDiscoverGovernanceSourcesContracts:
    def test_input_defaults(self) -> None:
        inp = DiscoverGovernanceSourcesInput(
            company_id=COMPANY_UUID,
            company_name="Reliance Industries",
            observation_date=date(2025, 9, 30),
        )
        assert inp.shareholding_quarters == 8
        assert inp.corporate_action_years == 5
        assert inp.filing_types is None

    def test_input_custom(self) -> None:
        inp = DiscoverGovernanceSourcesInput(
            company_id=COMPANY_UUID,
            company_name="TCS",
            nse_symbol="TCS",
            bse_code="532540",
            observation_date=date(2025, 9, 30),
            filing_types=["annual_report", "corporate_governance"],
            shareholding_quarters=12,
            corporate_action_years=3,
        )
        assert inp.filing_types is not None
        assert len(inp.filing_types) == 2
        assert inp.shareholding_quarters == 12
        assert inp.corporate_action_years == 3

    def test_input_shareholding_quarters_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DiscoverGovernanceSourcesInput(
                company_id=COMPANY_UUID,
                company_name="Test",
                observation_date=date(2025, 9, 30),
                shareholding_quarters=0,
            )
        with pytest.raises(ValidationError):
            DiscoverGovernanceSourcesInput(
                company_id=COMPANY_UUID,
                company_name="Test",
                observation_date=date(2025, 9, 30),
                shareholding_quarters=21,
            )

    def test_input_corporate_action_years_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DiscoverGovernanceSourcesInput(
                company_id=COMPANY_UUID,
                company_name="Test",
                observation_date=date(2025, 9, 30),
                corporate_action_years=0,
            )
        with pytest.raises(ValidationError):
            DiscoverGovernanceSourcesInput(
                company_id=COMPANY_UUID,
                company_name="Test",
                observation_date=date(2025, 9, 30),
                corporate_action_years=11,
            )

    def test_output_empty(self) -> None:
        out = DiscoverGovernanceSourcesOutput(
            filing_candidates=[],
            shareholding_data=[],
            corporate_actions=[],
            provider_errors=[],
            data_gaps=[],
        )
        assert out.filing_candidates == []
        assert out.shareholding_data == []

    def test_output_with_data(self) -> None:
        candidates = [
            SourceCandidate(
                source_id="BSE-12345",
                source_type=DocumentType.ANNUAL_REPORT,
                provider="corporate_filings",
                title="Annual Report FY2025",
                publication_date=date(2025, 5, 30),
                source_tier=SourceTier.TIER_1,
            ),
        ]
        shareholding = [
            ShareholdingSnapshot(
                as_of_date=date(2025, 6, 30),
                quarter="Q1FY2026",
                promoter_holding_pct=Decimal("50.25"),
                fii_holding_pct=Decimal("22.30"),
                dii_holding_pct=Decimal("15.45"),
                public_holding_pct=Decimal("12.00"),
                source_provider="ShareholdingProvider",
            ),
        ]
        actions = [
            CorporateActionSnapshot(
                action_type=CorporateActionType.DIVIDEND,
                ex_date=date(2025, 7, 15),
                details="Rs 10 dividend",
                value=Decimal("10.00"),
                source_provider="CorporateActionsProvider",
            ),
        ]
        out = DiscoverGovernanceSourcesOutput(
            filing_candidates=candidates,
            shareholding_data=shareholding,
            corporate_actions=actions,
            provider_errors=["ShareholdingProvider: timeout on second call"],
            data_gaps=["No quarterly results for Q2FY2026 yet"],
        )
        assert len(out.filing_candidates) == 1
        assert len(out.shareholding_data) == 1
        assert len(out.corporate_actions) == 1
        assert len(out.provider_errors) == 1
        assert len(out.data_gaps) == 1


# ===========================================================================
# RetrievedDocument
# ===========================================================================


class TestRetrievedDocument:
    def test_full(self) -> None:
        doc = RetrievedDocument(
            source_id="BSE-12345",
            title="Annual Report FY2025",
            content="Full text of annual report...",
            document_date=date(2025, 3, 31),
            filing_date=date(2025, 5, 30),
            source_url="https://bseindia.com/filing/12345",
            source_tier=1,
            content_hash="abc123def456789",
        )
        assert doc.source_id == "BSE-12345"
        assert doc.source_tier == 1
        assert doc.content_hash == "abc123def456789"

    def test_minimal(self) -> None:
        doc = RetrievedDocument(
            source_id="f1",
            title="Filing",
            content="Content",
            source_tier=1,
            content_hash="hash123",
        )
        assert doc.document_date is None
        assert doc.filing_date is None
        assert doc.source_url is None

    def test_frozen(self) -> None:
        doc = RetrievedDocument(
            source_id="f1",
            title="Test",
            content="Content",
            source_tier=1,
            content_hash="hash",
        )
        with pytest.raises(ValidationError):
            doc.content = "New"


# ===========================================================================
# RetrieveGovernanceDocumentsInput / Output
# ===========================================================================


class TestRetrieveGovernanceDocumentsContracts:
    def test_input(self) -> None:
        candidates = [
            SourceCandidate(
                source_id="f1",
                source_type=DocumentType.FILING,
                provider="bse",
                title="Test Filing",
                publication_date=date(2025, 5, 1),
                source_tier=SourceTier.TIER_1,
            ),
        ]
        inp = RetrieveGovernanceDocumentsInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            filing_candidates=candidates,
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.research_run_id == RUN_UUID
        assert len(inp.filing_candidates) == 1

    def test_output(self) -> None:
        docs = [
            RetrievedDocument(
                source_id="f1",
                title="Filing 1",
                content="Content 1",
                source_tier=1,
                content_hash="hash1",
            ),
        ]
        out = RetrieveGovernanceDocumentsOutput(
            documents=docs,
            retrieval_errors=["f2: timeout"],
            total_attempted=2,
            total_retrieved=1,
        )
        assert len(out.documents) == 1
        assert out.total_attempted == 2
        assert out.total_retrieved == 1
        assert len(out.retrieval_errors) == 1

    def test_output_empty(self) -> None:
        out = RetrieveGovernanceDocumentsOutput(
            documents=[],
            retrieval_errors=[],
            total_attempted=0,
            total_retrieved=0,
        )
        assert out.documents == []

    def test_total_attempted_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            RetrieveGovernanceDocumentsOutput(
                documents=[],
                retrieval_errors=[],
                total_attempted=-1,
                total_retrieved=0,
            )


# ===========================================================================
# NewManagementStatement
# ===========================================================================


class TestNewManagementStatement:
    def test_full(self) -> None:
        stmt = NewManagementStatement(
            statement="Management expects 20% revenue growth in FY2026",
            statement_date=date(2025, 1, 25),
            category="REVENUE_GUIDANCE",
            expected_outcome="20% revenue growth by March 2026",
            expected_timeframe="FY2026",
            evidence_index=0,
        )
        assert stmt.statement == "Management expects 20% revenue growth in FY2026"
        assert stmt.category == "REVENUE_GUIDANCE"
        assert stmt.expected_timeframe == "FY2026"

    def test_minimal(self) -> None:
        stmt = NewManagementStatement(
            statement="Plans to expand",
            statement_date=date(2025, 5, 15),
            category="EXPANSION",
            evidence_index=3,
        )
        assert stmt.expected_outcome is None
        assert stmt.expected_timeframe is None

    def test_frozen(self) -> None:
        stmt = NewManagementStatement(
            statement="Test",
            statement_date=date(2025, 1, 1),
            category="OTHER",
            evidence_index=0,
        )
        with pytest.raises(ValidationError):
            stmt.statement = "Other"


# ===========================================================================
# ManagementStatementUpdate
# ===========================================================================


class TestManagementStatementUpdate:
    def test_met_transition(self) -> None:
        update = ManagementStatementUpdate(
            statement_id=str(STATEMENT_UUID),
            proposed_status="MET",
            actual_outcome="Revenue grew 22%, exceeding 20% target",
            outcome_evidence_index=5,
            justification="Annual report FY2026 confirms 22% revenue growth",
        )
        assert update.proposed_status == "MET"
        assert update.outcome_evidence_index == 5
        assert update.resolution_detail is None

    def test_unknown_with_resolution_detail(self) -> None:
        update = ManagementStatementUpdate(
            statement_id=str(STATEMENT_UUID),
            proposed_status="UNKNOWN",
            resolution_detail="INSUFFICIENT_EVIDENCE",
            justification="No outcome data available for this promise",
        )
        assert update.proposed_status == "UNKNOWN"
        assert update.resolution_detail == "INSUFFICIENT_EVIDENCE"
        assert update.outcome_evidence_index is None

    def test_not_due(self) -> None:
        update = ManagementStatementUpdate(
            statement_id=str(STATEMENT_UUID),
            proposed_status="PENDING",
            resolution_detail="NOT_DUE",
            justification="Expected timeframe FY2027 has not yet elapsed",
        )
        assert update.resolution_detail == "NOT_DUE"

    def test_frozen(self) -> None:
        update = ManagementStatementUpdate(
            statement_id=str(STATEMENT_UUID),
            proposed_status="MET",
            justification="Test",
        )
        with pytest.raises(ValidationError):
            update.proposed_status = "MISSED"


# ===========================================================================
# GovernanceRedFlag
# ===========================================================================


class TestGovernanceRedFlag:
    def test_full(self) -> None:
        flag = GovernanceRedFlag(
            category="promoter_pledge_elevation",
            description="Promoter pledge increased from 5% to 25% in 2 quarters",
            severity="HIGH",
            justification="Rapid pledge increase indicates potential financial stress",
            evidence_indices=[0, 1, 2],
        )
        assert flag.category == "promoter_pledge_elevation"
        assert flag.severity == "HIGH"
        assert len(flag.evidence_indices) == 3

    def test_frozen(self) -> None:
        flag = GovernanceRedFlag(
            category="auditor_change",
            description="Auditor changed twice in 3 years",
            severity="MEDIUM",
            justification="Frequent auditor changes are a governance concern",
            evidence_indices=[4],
        )
        with pytest.raises(ValidationError):
            flag.severity = "LOW"

    def test_all_red_flag_categories(self) -> None:
        for cat in GOVERNANCE_RED_FLAG_CATEGORIES:
            flag = GovernanceRedFlag(
                category=cat,
                description=f"Test {cat}",
                severity="MEDIUM",
                justification="Test justification",
                evidence_indices=[0],
            )
            assert flag.category == cat


# ===========================================================================
# GovernanceAnalysisOutput
# ===========================================================================


class TestGovernanceAnalysisOutput:
    def test_full(self) -> None:
        out = GovernanceAnalysisOutput(
            new_management_statements=[
                NewManagementStatement(
                    statement="Revenue target 20%",
                    statement_date=date(2025, 1, 25),
                    category="REVENUE_GUIDANCE",
                    evidence_index=0,
                ),
            ],
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(STATEMENT_UUID),
                    proposed_status="MET",
                    actual_outcome="Revenue grew 22%",
                    outcome_evidence_index=5,
                    justification="Annual report confirms",
                ),
            ],
            capital_allocation_findings=[
                GeneratedFinding(
                    finding_type=FindingType.CALCULATION,
                    category="capital_allocation",
                    content="Dividend payout ratio was 35.24%",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
            related_party_findings=[],
            auditor_findings=[],
            compensation_findings=[],
            subsidiary_findings=[],
            dilution_findings=[],
            governance_red_flags=[
                GovernanceRedFlag(
                    category="promoter_pledge_elevation",
                    description="Pledge increased significantly",
                    severity="HIGH",
                    justification="Pledge up from 5% to 25%",
                    evidence_indices=[1, 2],
                ),
            ],
            general_findings=[],
        )
        assert len(out.new_management_statements) == 1
        assert len(out.statement_updates) == 1
        assert len(out.capital_allocation_findings) == 1
        assert len(out.governance_red_flags) == 1

    def test_empty(self) -> None:
        out = GovernanceAnalysisOutput(
            new_management_statements=[],
            statement_updates=[],
            capital_allocation_findings=[],
            related_party_findings=[],
            auditor_findings=[],
            compensation_findings=[],
            subsidiary_findings=[],
            dilution_findings=[],
            governance_red_flags=[],
            general_findings=[],
        )
        assert len(out.new_management_statements) == 0
        assert len(out.governance_red_flags) == 0

    def test_frozen(self) -> None:
        out = GovernanceAnalysisOutput(
            new_management_statements=[],
            statement_updates=[],
            capital_allocation_findings=[],
            related_party_findings=[],
            auditor_findings=[],
            compensation_findings=[],
            subsidiary_findings=[],
            dilution_findings=[],
            governance_red_flags=[],
            general_findings=[],
        )
        with pytest.raises(ValidationError):
            out.general_findings = []


# ===========================================================================
# GovernanceValidationIssue / GovernanceValidationResult
# ===========================================================================


class TestGovernanceValidationContracts:
    def test_issue(self) -> None:
        issue = GovernanceValidationIssue(
            domain="management_statement",
            issue_type="missing_outcome_evidence",
            message="MET transition without outcome_evidence_index",
            action="rejected",
        )
        assert issue.domain == "management_statement"
        assert issue.action == "rejected"

    def test_result_all_valid(self) -> None:
        result = GovernanceValidationResult(
            total_findings=10,
            valid_count=10,
            rejected_count=0,
            statement_updates_valid=3,
            statement_updates_rejected=0,
            new_statements_valid=5,
            new_statements_rejected=0,
            red_flags_valid=2,
            red_flags_rejected=0,
            issues=[],
        )
        assert result.total_findings == 10
        assert result.rejected_count == 0
        assert len(result.issues) == 0

    def test_result_with_rejections(self) -> None:
        result = GovernanceValidationResult(
            total_findings=15,
            valid_count=12,
            rejected_count=3,
            statement_updates_valid=2,
            statement_updates_rejected=1,
            new_statements_valid=4,
            new_statements_rejected=1,
            red_flags_valid=1,
            red_flags_rejected=1,
            issues=[
                GovernanceValidationIssue(
                    domain="management_statement",
                    issue_type="missing_outcome_evidence",
                    message="No evidence for MET transition",
                    action="rejected",
                ),
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="invalid_category",
                    message="Category 'unknown' not in GOVERNANCE_FINDING_CATEGORIES",
                    action="rejected",
                ),
                GovernanceValidationIssue(
                    domain="red_flag",
                    issue_type="no_evidence_indices",
                    message="Red flag without evidence indices",
                    action="rejected",
                ),
            ],
        )
        assert result.rejected_count == 3
        assert len(result.issues) == 3
        assert result.issues[0].domain == "management_statement"
        assert result.issues[1].domain == "finding"
        assert result.issues[2].domain == "red_flag"

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GovernanceValidationResult(
                total_findings=-1,
                valid_count=0,
                rejected_count=0,
                statement_updates_valid=0,
                statement_updates_rejected=0,
                new_statements_valid=0,
                new_statements_rejected=0,
                red_flags_valid=0,
                red_flags_rejected=0,
                issues=[],
            )

    def test_frozen(self) -> None:
        result = GovernanceValidationResult(
            total_findings=10,
            valid_count=10,
            rejected_count=0,
            statement_updates_valid=0,
            statement_updates_rejected=0,
            new_statements_valid=0,
            new_statements_rejected=0,
            red_flags_valid=0,
            red_flags_rejected=0,
            issues=[],
        )
        with pytest.raises(ValidationError):
            result.total_findings = 0


# ===========================================================================
# GOVERNANCE_RESEARCH_STEPS
# ===========================================================================


class TestGovernanceResearchSteps:
    def test_seven_steps(self) -> None:
        assert len(GOVERNANCE_RESEARCH_STEPS) == 7

    def test_is_tuple(self) -> None:
        assert isinstance(GOVERNANCE_RESEARCH_STEPS, tuple)

    def test_step_order_sequence(self) -> None:
        orders = [s.step_order for s in GOVERNANCE_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_step_names(self) -> None:
        names = [s.step_name for s in GOVERNANCE_RESEARCH_STEPS]
        assert names == [
            "company_context_load",
            "governance_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "governance_analysis",
            "governance_validation",
            "persistence",
        ]

    def test_step_types(self) -> None:
        types = [s.step_type for s in GOVERNANCE_RESEARCH_STEPS]
        assert types == [
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_DETERMINISTIC,
        ]

    def test_llm_steps(self) -> None:
        llm_steps = [s for s in GOVERNANCE_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 2
        assert [s.step_name for s in llm_steps] == [
            "evidence_extraction",
            "governance_analysis",
        ]

    def test_deterministic_steps(self) -> None:
        det_steps = [
            s for s in GOVERNANCE_RESEARCH_STEPS if s.step_type == STEP_TYPE_DETERMINISTIC
        ]
        assert len(det_steps) == 3
        assert [s.step_name for s in det_steps] == [
            "company_context_load",
            "governance_validation",
            "persistence",
        ]

    def test_provider_steps(self) -> None:
        prov_steps = [
            s for s in GOVERNANCE_RESEARCH_STEPS if s.step_type == STEP_TYPE_PROVIDER_CALL
        ]
        assert len(prov_steps) == 2
        assert [s.step_name for s in prov_steps] == [
            "governance_source_discovery",
            "document_retrieval",
        ]

    def test_timeout_values(self) -> None:
        timeouts = {s.step_name: s.timeout_seconds for s in GOVERNANCE_RESEARCH_STEPS}
        assert timeouts["company_context_load"] == 10
        assert timeouts["governance_source_discovery"] == 30
        assert timeouts["document_retrieval"] == 60
        assert timeouts["evidence_extraction"] == 120
        assert timeouts["governance_analysis"] == 120
        assert timeouts["governance_validation"] == 10
        assert timeouts["persistence"] == 30


# ===========================================================================
# Serialization round-trips
# ===========================================================================


class TestGovernanceSerialization:
    def test_research_request_round_trip(self) -> None:
        req = ManagementGovernanceResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
            configuration=ManagementGovernanceConfig(token_budget=15_000),
        )
        data = req.model_dump(mode="json")
        req2 = ManagementGovernanceResearchRequest.model_validate(data)
        assert req == req2

    def test_result_round_trip(self) -> None:
        result = ManagementGovernanceResult(
            status="COMPLETED",
            run_id=RUN_UUID,
            finding_ids=[FINDING_UUID],
            statement_ids=[STATEMENT_UUID],
            red_flag_count=2,
            total_findings=5,
            total_statements_created=3,
            total_statements_updated=1,
        )
        data = result.model_dump(mode="json")
        result2 = ManagementGovernanceResult.model_validate(data)
        assert result == result2

    def test_shareholding_snapshot_decimal_preserved(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 6, 30),
            quarter="Q1FY2026",
            promoter_holding_pct=Decimal("50.2500"),
            fii_holding_pct=Decimal("22.3000"),
            dii_holding_pct=Decimal("15.4500"),
            public_holding_pct=Decimal("12.0000"),
            source_provider="ShareholdingProvider",
        )
        data = snap.model_dump(mode="json")
        snap2 = ShareholdingSnapshot.model_validate(data)
        assert isinstance(snap2.promoter_holding_pct, Decimal)
        assert isinstance(snap2.fii_holding_pct, Decimal)

    def test_corporate_action_round_trip(self) -> None:
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2025, 7, 15),
            details="Rs 10 dividend",
            value=Decimal("10.00"),
            source_provider="CorporateActionsProvider",
        )
        data = action.model_dump(mode="json")
        action2 = CorporateActionSnapshot.model_validate(data)
        assert action2.action_type == CorporateActionType.DIVIDEND
        assert isinstance(action2.value, Decimal)

    def test_management_statement_summary_round_trip(self) -> None:
        summary = ManagementStatementSummary(
            id=STATEMENT_UUID,
            statement_date=date(2025, 1, 25),
            statement="Revenue target 20%",
            category=ManagementStatementCategory.REVENUE_GUIDANCE,
            expected_outcome="20% growth by FY26",
            expected_timeframe="FY2026",
            status=ManagementStatementStatus.PENDING,
        )
        data = summary.model_dump(mode="json")
        summary2 = ManagementStatementSummary.model_validate(data)
        assert summary == summary2

    def test_governance_validation_result_round_trip(self) -> None:
        result = GovernanceValidationResult(
            total_findings=10,
            valid_count=8,
            rejected_count=2,
            statement_updates_valid=3,
            statement_updates_rejected=0,
            new_statements_valid=2,
            new_statements_rejected=1,
            red_flags_valid=1,
            red_flags_rejected=1,
            issues=[
                GovernanceValidationIssue(
                    domain="finding",
                    issue_type="invalid_category",
                    message="Bad category",
                    action="rejected",
                ),
            ],
        )
        data = result.model_dump(mode="json")
        result2 = GovernanceValidationResult.model_validate(data)
        assert result == result2

    def test_governance_red_flag_round_trip(self) -> None:
        flag = GovernanceRedFlag(
            category="promoter_pledge_elevation",
            description="Pledge increased",
            severity="HIGH",
            justification="Rapid increase",
            evidence_indices=[0, 1],
        )
        data = flag.model_dump(mode="json")
        flag2 = GovernanceRedFlag.model_validate(data)
        assert flag == flag2


# ===========================================================================
# Cross-cutting: enum reuse
# ===========================================================================


class TestGovernanceEnumReuse:
    """Verify governance contracts reuse existing enums."""

    def test_statement_summary_uses_management_statement_category(self) -> None:
        for cat in ManagementStatementCategory:
            summary = ManagementStatementSummary(
                id=STATEMENT_UUID,
                statement_date=date(2025, 1, 1),
                statement="Test",
                category=cat,
                status=ManagementStatementStatus.PENDING,
            )
            assert summary.category == cat

    def test_statement_summary_uses_management_statement_status(self) -> None:
        for status in ManagementStatementStatus:
            summary = ManagementStatementSummary(
                id=STATEMENT_UUID,
                statement_date=date(2025, 1, 1),
                statement="Test",
                category=ManagementStatementCategory.OTHER,
                status=status,
            )
            assert summary.status == status

    def test_corporate_action_uses_corporate_action_type(self) -> None:
        for at in CorporateActionType:
            action = CorporateActionSnapshot(
                action_type=at,
                details=f"Test {at.value}",
                source_provider="test",
            )
            assert action.action_type == at

    def test_governance_analysis_reuses_generated_finding(self) -> None:
        finding = GeneratedFinding(
            finding_type=FindingType.FACT,
            category="capital_allocation",
            content="Dividend payout ratio 35%",
            confidence=ConfidenceLevel.HIGH,
            evidence_indices=[0],
        )
        out = GovernanceAnalysisOutput(
            new_management_statements=[],
            statement_updates=[],
            capital_allocation_findings=[finding],
            related_party_findings=[],
            auditor_findings=[],
            compensation_findings=[],
            subsidiary_findings=[],
            dilution_findings=[],
            governance_red_flags=[],
            general_findings=[],
        )
        assert out.capital_allocation_findings[0].finding_type == FindingType.FACT

    def test_context_output_reuses_finding_summary(self) -> None:
        fs = FindingSummary(
            finding_id=FINDING_UUID,
            category="company_identity",
            finding_type=FindingType.FACT,
            content="Test company",
            confidence=ConfidenceLevel.HIGH,
        )
        out = LoadGovernanceContextOutput(
            company_id=COMPANY_UUID,
            company_name="Test",
            company_findings=[fs],
            has_company_research=True,
            existing_statements=[],
        )
        assert out.company_findings[0].finding_type == FindingType.FACT

    def test_source_discovery_reuses_source_candidate(self) -> None:
        sc = SourceCandidate(
            source_id="BSE-1",
            source_type=DocumentType.FILING,
            provider="bse",
            title="Filing",
            publication_date=date(2025, 5, 1),
            source_tier=SourceTier.TIER_1,
        )
        out = DiscoverGovernanceSourcesOutput(
            filing_candidates=[sc],
            shareholding_data=[],
            corporate_actions=[],
            provider_errors=[],
            data_gaps=[],
        )
        assert out.filing_candidates[0].source_tier == SourceTier.TIER_1


# ===========================================================================
# Tool I/O Contract Tests (Remediation for FINDING-01)
# ===========================================================================


class TestGetShareholdingContracts:

    def test_input_valid(self) -> None:
        inp = GetShareholdingInput(
            company_id=COMPANY_UUID,
            nse_symbol="RELIANCE",
            bse_code="500325",
            observation_date=date(2025, 6, 30),
            quarters=8,
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.nse_symbol == "RELIANCE"
        assert inp.bse_code == "500325"
        assert inp.observation_date == date(2025, 6, 30)
        assert inp.quarters == 8

    def test_input_defaults(self) -> None:
        inp = GetShareholdingInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
        )
        assert inp.nse_symbol is None
        assert inp.bse_code is None
        assert inp.quarters == 8

    def test_input_frozen(self) -> None:
        inp = GetShareholdingInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
        )
        with pytest.raises(ValidationError):
            inp.quarters = 4

    def test_input_quarters_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GetShareholdingInput(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 6, 30),
                quarters=0,
            )
        with pytest.raises(ValidationError):
            GetShareholdingInput(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 6, 30),
                quarters=21,
            )

    def test_output_valid(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY25",
            promoter_holding_pct=Decimal("50.30"),
            fii_holding_pct=Decimal("20.00"),
            dii_holding_pct=Decimal("15.00"),
            public_holding_pct=Decimal("14.70"),
            source_provider="nse",
        )
        out = GetShareholdingOutput(
            snapshots=[snap],
            provider_errors=[],
        )
        assert len(out.snapshots) == 1
        assert out.snapshots[0].promoter_holding_pct == Decimal("50.30")
        assert out.provider_errors == []

    def test_output_with_errors(self) -> None:
        out = GetShareholdingOutput(
            snapshots=[],
            provider_errors=["Provider timeout"],
        )
        assert len(out.snapshots) == 0
        assert out.provider_errors == ["Provider timeout"]

    def test_output_frozen(self) -> None:
        out = GetShareholdingOutput(snapshots=[], provider_errors=[])
        with pytest.raises(ValidationError):
            out.snapshots = []


class TestGetCorporateActionsContracts:

    def test_input_valid(self) -> None:
        inp = GetCorporateActionsInput(
            company_id=COMPANY_UUID,
            nse_symbol="RELIANCE",
            observation_date=date(2025, 6, 30),
            years=5,
        )
        assert inp.company_id == COMPANY_UUID
        assert inp.years == 5

    def test_input_defaults(self) -> None:
        inp = GetCorporateActionsInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
        )
        assert inp.nse_symbol is None
        assert inp.bse_code is None
        assert inp.years == 5

    def test_input_frozen(self) -> None:
        inp = GetCorporateActionsInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 6, 30),
        )
        with pytest.raises(ValidationError):
            inp.years = 3

    def test_input_years_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GetCorporateActionsInput(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 6, 30),
                years=0,
            )
        with pytest.raises(ValidationError):
            GetCorporateActionsInput(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 6, 30),
                years=11,
            )

    def test_output_valid(self) -> None:
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2025, 5, 15),
            details="Interim dividend Rs 10",
            value=Decimal("10.00"),
            source_provider="bse",
        )
        out = GetCorporateActionsOutput(
            actions=[action],
            provider_errors=[],
        )
        assert len(out.actions) == 1
        assert out.actions[0].action_type == CorporateActionType.DIVIDEND

    def test_output_frozen(self) -> None:
        out = GetCorporateActionsOutput(actions=[], provider_errors=[])
        with pytest.raises(ValidationError):
            out.actions = []


class TestPersistStatementsContracts:

    def test_input_with_new_statements(self) -> None:
        stmt = NewManagementStatement(
            statement="Revenue will grow 20%",
            statement_date=date(2025, 1, 15),
            category="revenue_guidance",
            evidence_index=0,
        )
        inp = PersistStatementsInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            new_statements=[stmt],
        )
        assert len(inp.new_statements) == 1
        assert inp.statement_updates == []
        assert inp.evidence_ids == []

    def test_input_with_updates(self) -> None:
        upd = ManagementStatementUpdate(
            statement_id=str(STATEMENT_UUID),
            proposed_status="MET",
            actual_outcome="Revenue grew 22%",
            outcome_evidence_index=0,
            justification="Annual report confirms",
        )
        inp = PersistStatementsInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            statement_updates=[upd],
            evidence_ids=[EVIDENCE_UUID],
        )
        assert len(inp.statement_updates) == 1
        assert len(inp.evidence_ids) == 1

    def test_input_frozen(self) -> None:
        inp = PersistStatementsInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
        )
        with pytest.raises(ValidationError):
            inp.company_id = COMPANY_UUID

    def test_output_valid(self) -> None:
        out = PersistStatementsOutput(
            created_ids=[STATEMENT_UUID],
            updated_ids=[],
            rejected_count=0,
        )
        assert len(out.created_ids) == 1
        assert out.rejected_count == 0

    def test_output_with_rejections(self) -> None:
        out = PersistStatementsOutput(
            created_ids=[],
            updated_ids=[],
            rejected_count=2,
        )
        assert out.rejected_count == 2

    def test_output_frozen(self) -> None:
        out = PersistStatementsOutput(
            created_ids=[], updated_ids=[], rejected_count=0,
        )
        with pytest.raises(ValidationError):
            out.rejected_count = 1

    def test_output_rejected_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            PersistStatementsOutput(
                created_ids=[], updated_ids=[], rejected_count=-1,
            )


class TestPersistShareholdingContracts:

    def test_input_valid(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY25",
            promoter_holding_pct=Decimal("50.30"),
            fii_holding_pct=Decimal("20.00"),
            dii_holding_pct=Decimal("15.00"),
            public_holding_pct=Decimal("14.70"),
            source_provider="nse",
        )
        inp = PersistShareholdingInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            snapshots=[snap],
        )
        assert len(inp.snapshots) == 1

    def test_input_requires_at_least_one_snapshot(self) -> None:
        with pytest.raises(ValidationError):
            PersistShareholdingInput(
                company_id=COMPANY_UUID,
                research_run_id=RUN_UUID,
                snapshots=[],
            )

    def test_input_frozen(self) -> None:
        snap = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY25",
            promoter_holding_pct=Decimal("50.30"),
            fii_holding_pct=Decimal("20.00"),
            dii_holding_pct=Decimal("15.00"),
            public_holding_pct=Decimal("14.70"),
            source_provider="nse",
        )
        inp = PersistShareholdingInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            snapshots=[snap],
        )
        with pytest.raises(ValidationError):
            inp.company_id = COMPANY_UUID

    def test_output_valid(self) -> None:
        out = PersistShareholdingOutput(
            persisted_ids=[COMPANY_UUID],
            skipped_count=0,
        )
        assert len(out.persisted_ids) == 1
        assert out.skipped_count == 0

    def test_output_skipped_count_default(self) -> None:
        out = PersistShareholdingOutput(persisted_ids=[])
        assert out.skipped_count == 0

    def test_output_skipped_count_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            PersistShareholdingOutput(persisted_ids=[], skipped_count=-1)

    def test_output_frozen(self) -> None:
        out = PersistShareholdingOutput(persisted_ids=[])
        with pytest.raises(ValidationError):
            out.skipped_count = 1


class TestPersistGovernanceDataContracts:

    def test_input_with_both(self) -> None:
        pledge = ShareholdingSnapshot(
            as_of_date=date(2025, 3, 31),
            quarter="Q4FY25",
            promoter_holding_pct=Decimal("50.30"),
            fii_holding_pct=Decimal("20.00"),
            dii_holding_pct=Decimal("15.00"),
            public_holding_pct=Decimal("14.70"),
            pledged_percentage=Decimal("5.00"),
            source_provider="nse",
        )
        action = CorporateActionSnapshot(
            action_type=CorporateActionType.DIVIDEND,
            details="Final dividend Rs 5",
            value=Decimal("5.00"),
            source_provider="bse",
        )
        inp = PersistGovernanceDataInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
            pledge_snapshots=[pledge],
            corporate_actions=[action],
        )
        assert len(inp.pledge_snapshots) == 1
        assert len(inp.corporate_actions) == 1
        assert inp.pledge_snapshots[0].pledged_percentage == Decimal("5.00")

    def test_input_defaults_empty_lists(self) -> None:
        inp = PersistGovernanceDataInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
        )
        assert inp.pledge_snapshots == []
        assert inp.corporate_actions == []

    def test_input_frozen(self) -> None:
        inp = PersistGovernanceDataInput(
            company_id=COMPANY_UUID,
            research_run_id=RUN_UUID,
        )
        with pytest.raises(ValidationError):
            inp.company_id = COMPANY_UUID

    def test_output_valid(self) -> None:
        out = PersistGovernanceDataOutput(
            pledge_ids=[COMPANY_UUID],
            corporate_action_ids=[RUN_UUID],
        )
        assert len(out.pledge_ids) == 1
        assert len(out.corporate_action_ids) == 1

    def test_output_frozen(self) -> None:
        out = PersistGovernanceDataOutput(
            pledge_ids=[], corporate_action_ids=[],
        )
        with pytest.raises(ValidationError):
            out.pledge_ids = []


class TestToolContractCompleteness:
    """Verify all 6 tool I/O contract pairs required by Architecture §40 exist."""

    REQUIRED_TOOL_CONTRACTS: list[tuple[str, str]] = [
        ("LoadGovernanceContextInput", "LoadGovernanceContextOutput"),
        ("GetShareholdingInput", "GetShareholdingOutput"),
        ("GetCorporateActionsInput", "GetCorporateActionsOutput"),
        ("PersistStatementsInput", "PersistStatementsOutput"),
        ("PersistShareholdingInput", "PersistShareholdingOutput"),
        ("PersistGovernanceDataInput", "PersistGovernanceDataOutput"),
    ]

    def test_all_tool_contract_pairs_importable(self) -> None:
        import app.agents.contracts as mod
        for input_name, output_name in self.REQUIRED_TOOL_CONTRACTS:
            assert hasattr(mod, input_name), f"Missing: {input_name}"
            assert hasattr(mod, output_name), f"Missing: {output_name}"

    def test_all_tool_contracts_are_frozen(self) -> None:
        import app.agents.contracts as mod
        for input_name, output_name in self.REQUIRED_TOOL_CONTRACTS:
            input_cls = getattr(mod, input_name)
            output_cls = getattr(mod, output_name)
            assert input_cls.model_config.get("frozen") is True, f"{input_name} not frozen"
            assert output_cls.model_config.get("frozen") is True, f"{output_name} not frozen"

    def test_required_count(self) -> None:
        assert len(self.REQUIRED_TOOL_CONTRACTS) == 6
