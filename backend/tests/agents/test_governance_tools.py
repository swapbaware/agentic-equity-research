"""Unit tests for ManagementGovernanceTools (Phase 11.2).

Tests cover the 9 agent-facing tool methods:
  1. load_company_context
  2. discover_governance_sources
  3. retrieve_document
  4. get_shareholding_data
  5. get_corporate_actions
  6. persist_evidence
  7. persist_findings
  8. persist_management_statements
  9. persist_shareholding
  10. persist_governance_data

Plus the internal helper ``create_research_document`` and helper functions.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_FINDING_CATEGORIES,
    CorporateActionSnapshot,
    DiscoverGovernanceSourcesInput,
    EvidenceItem,
    FindingItem,
    GetCorporateActionsInput,
    GetShareholdingInput,
    LoadGovernanceContextInput,
    ManagementStatementUpdate,
    NewManagementStatement,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistGovernanceDataInput,
    PersistShareholdingInput,
    PersistStatementsInput,
    RetrieveDocumentInput,
    ShareholdingSnapshot,
    SourceCandidate,
)
from app.agents.management_governance.exceptions import (
    CompanyNotFoundForGovernanceError,
)
from app.agents.management_governance.tools import (
    ManagementGovernanceTools,
    _compute_start_date_for_quarters,
    _map_filing_type,
)
from app.models.enums import (
    ConfidenceLevel,
    CorporateActionType,
    DocumentType,
    EvidenceType,
    FindingType,
    ManagementStatementCategory,
    ManagementStatementStatus,
    ResearchRunStatus,
    SourceTier,
)
from app.providers.errors import ProviderError
from app.providers.types import (
    CorporateActionRecord,
    Filing,
    FilingDocument,
    ShareholderCategory,
    ShareholdingPattern,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockCompany:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Reliance Industries",
        nse_symbol: str | None = "RELIANCE",
        bse_code: str | None = "500325",
        isin: str = "INE002A01018",
        market_cap: Decimal | None = Decimal("16000000.0000"),
        is_active: bool = True,
        industry_id: uuid.UUID | None = None,
        industry: Any = None,
        sector: Any = None,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.name = name
        self.nse_symbol = nse_symbol
        self.bse_code = bse_code
        self.isin = isin
        self.market_cap = market_cap
        self.is_active = is_active
        self.industry_id = industry_id
        self.industry = industry
        self.sector = sector


class MockIndustry:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Oil & Gas",
    ) -> None:
        self.id = id or uuid.uuid4()
        self.name = name


class MockResearchRun:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        status: str = ResearchRunStatus.COMPLETED,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.status = status


class MockFinding:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        category: str = "management_claim",
        finding_type: str = FindingType.MANAGEMENT_CLAIM,
        content: str = "Test governance finding",
        confidence: str = ConfidenceLevel.HIGH,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.category = category
        self.finding_type = finding_type
        self.content = content
        self.confidence = confidence


class MockManagementStatement:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
        statement_date: date = date(2024, 5, 15),
        statement: str = "We expect revenue to grow 20%",
        category: ManagementStatementCategory = ManagementStatementCategory.REVENUE_GUIDANCE,
        expected_outcome: str | None = "20% revenue growth by FY25",
        status: ManagementStatementStatus = ManagementStatementStatus.PENDING,
        source_evidence_id: uuid.UUID | None = None,
        outcome_evidence_id: uuid.UUID | None = None,
        actual_outcome: str | None = None,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.company_id = company_id or uuid.uuid4()
        self.statement_date = statement_date
        self.statement = statement
        self.category = category
        self.expected_outcome = expected_outcome
        self.status = status
        self.source_evidence_id = source_evidence_id
        self.outcome_evidence_id = outcome_evidence_id
        self.actual_outcome = actual_outcome


class MockEvidence:
    def __init__(self) -> None:
        self.id = uuid.uuid4()


class MockPersistedFinding:
    def __init__(self) -> None:
        self.id = uuid.uuid4()


class MockRunService:
    def __init__(self) -> None:
        self.get_runs_for_company = AsyncMock(return_value=[])
        self.get_runs_for_industry = AsyncMock(return_value=[])
        self.get_findings = AsyncMock(return_value=[])
        self.record_findings = AsyncMock(
            return_value=[MockPersistedFinding(), MockPersistedFinding()],
        )


def _build_tools(
    session: AsyncMock | None = None,
    run_service: MockRunService | None = None,
    corporate_filings: AsyncMock | None = None,
    shareholding: AsyncMock | None = None,
    corporate_actions: AsyncMock | None = None,
) -> ManagementGovernanceTools:
    return ManagementGovernanceTools(
        session=session or AsyncMock(),
        run_service=run_service or MockRunService(),
        corporate_filings=corporate_filings or AsyncMock(),
        shareholding=shareholding or AsyncMock(),
        corporate_actions=corporate_actions or AsyncMock(),
    )


def _make_filing(
    *,
    filing_id: str = "F001",
    title: str = "Annual Report FY24",
    filing_type: str = "ANNUAL_REPORT",
    filing_date: date = date(2024, 6, 1),
    url: str = "https://bseindia.com/reports/F001.pdf",
) -> Filing:
    return Filing(
        filing_id=filing_id,
        title=title,
        filing_type=filing_type,
        filing_date=filing_date,
        url=url,
        exchange="BSE",
        symbol="500325",
    )


def _make_shareholding_pattern(
    *,
    pattern_date: date = date(2024, 6, 30),
    quarter: str = "Q1FY2025",
    promoter: Decimal = Decimal("50.49"),
    fii: Decimal = Decimal("23.34"),
    dii: Decimal = Decimal("13.12"),
    public: Decimal = Decimal("13.05"),
    pledged: Decimal | None = Decimal("0.00"),
) -> ShareholdingPattern:
    return ShareholdingPattern(
        symbol="RELIANCE",
        exchange="NSE",
        quarter=quarter,
        date=pattern_date,
        categories=[
            ShareholderCategory(category="PROMOTER", percentage=promoter, shares=3_406_000_000),
            ShareholderCategory(category="FII", percentage=fii, shares=1_575_000_000),
            ShareholderCategory(category="DII", percentage=dii, shares=885_000_000),
            ShareholderCategory(category="PUBLIC", percentage=public, shares=880_000_000),
        ],
        total_shares=6_746_000_000,
        pledged_percentage=pledged,
    )


def _make_corporate_action_record(
    *,
    action_type: str = "DIVIDEND",
    ex_date: date | None = date(2024, 7, 18),
    record_date: date | None = date(2024, 7, 19),
    details: str = "Final Dividend of INR 10 per share",
    value: Decimal | None = Decimal("10.00"),
) -> CorporateActionRecord:
    return CorporateActionRecord(
        symbol="RELIANCE",
        exchange="NSE",
        action_type=action_type,
        ex_date=ex_date,
        record_date=record_date,
        details=details,
        value=value,
    )


# ---------------------------------------------------------------------------
# Tool 1: load_company_context
# ---------------------------------------------------------------------------


class TestLoadCompanyContext:
    @pytest.mark.asyncio
    async def test_company_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        tools = _build_tools(session=session)

        inp = LoadGovernanceContextInput(
            company_id=uuid.uuid4(),
            observation_date=date(2024, 12, 31),
        )
        with pytest.raises(CompanyNotFoundForGovernanceError):
            await tools.load_company_context(inp)

    @pytest.mark.asyncio
    async def test_no_prior_research(self) -> None:
        industry = MockIndustry()
        company = MockCompany(industry=industry, industry_id=industry.id)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        run_service = MockRunService()
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadGovernanceContextInput(
            company_id=company.id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.company_id == company.id
        assert result.company_name == "Reliance Industries"
        assert result.nse_symbol == "RELIANCE"
        assert result.bse_code == "500325"
        assert result.industry_name == "Oil & Gas"
        assert result.company_findings == []
        assert result.has_company_research is False
        assert result.existing_statements == []

    @pytest.mark.asyncio
    async def test_with_prior_company_research(self) -> None:
        company = MockCompany(industry=None, industry_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        run = MockResearchRun(status=ResearchRunStatus.COMPLETED)
        findings = [MockFinding(), MockFinding(category="shareholding")]

        run_service = MockRunService()
        run_service.get_runs_for_company = AsyncMock(return_value=[run])
        run_service.get_findings = AsyncMock(return_value=findings)
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadGovernanceContextInput(
            company_id=company.id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.has_company_research is True
        assert len(result.company_findings) == 2

    @pytest.mark.asyncio
    async def test_loads_existing_management_statements(self) -> None:
        company = MockCompany(industry=None, industry_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        ms1 = MockManagementStatement(
            company_id=company.id,
            statement="Revenue guidance 20%",
            category=ManagementStatementCategory.REVENUE_GUIDANCE,
            status=ManagementStatementStatus.PENDING,
        )
        ms2 = MockManagementStatement(
            company_id=company.id,
            statement="Capex plan for FY25",
            category=ManagementStatementCategory.CAPEX_PLAN,
            status=ManagementStatementStatus.MET,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ms1, ms2]
        session.execute = AsyncMock(return_value=mock_result)

        run_service = MockRunService()
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadGovernanceContextInput(
            company_id=company.id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert len(result.existing_statements) == 2
        assert result.existing_statements[0].statement == "Revenue guidance 20%"
        assert result.existing_statements[0].category == ManagementStatementCategory.REVENUE_GUIDANCE
        assert result.existing_statements[0].status == ManagementStatementStatus.PENDING
        assert result.existing_statements[1].category == ManagementStatementCategory.CAPEX_PLAN

    @pytest.mark.asyncio
    async def test_partial_run_counts_as_prior_research(self) -> None:
        company = MockCompany(industry=None, industry_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        run = MockResearchRun(status=ResearchRunStatus.PARTIAL)
        findings = [MockFinding()]

        run_service = MockRunService()
        run_service.get_runs_for_company = AsyncMock(return_value=[run])
        run_service.get_findings = AsyncMock(return_value=findings)
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadGovernanceContextInput(
            company_id=company.id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.has_company_research is True
        assert len(result.company_findings) == 1


# ---------------------------------------------------------------------------
# Tool 2: discover_governance_sources
# ---------------------------------------------------------------------------


class TestDiscoverGovernanceSources:
    @pytest.mark.asyncio
    async def test_all_providers_successful(self) -> None:
        filings = [_make_filing()]
        patterns = [_make_shareholding_pattern()]
        ca_records = [_make_corporate_action_record()]

        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=filings)
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=patterns)
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=ca_records)

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Reliance Industries",
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert len(result.filing_candidates) == 1
        assert result.filing_candidates[0].source_id == "F001"
        assert result.filing_candidates[0].source_tier == SourceTier.TIER_1
        assert len(result.shareholding_data) == 1
        assert result.shareholding_data[0].promoter_holding_pct == Decimal("50.49")
        assert len(result.corporate_actions) == 1
        assert result.corporate_actions[0].action_type == CorporateActionType.DIVIDEND
        assert result.provider_errors == []

    @pytest.mark.asyncio
    async def test_filing_provider_failure(self) -> None:
        cf = AsyncMock()
        cf.get_filings = AsyncMock(side_effect=ProviderError(provider="corporate_filings", message="timeout"))
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert len(result.filing_candidates) == 0
        assert any("CorporateFilingsProvider" in e for e in result.provider_errors)

    @pytest.mark.asyncio
    async def test_shareholding_provider_failure(self) -> None:
        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[])
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(
            side_effect=ProviderError(provider="shareholding", message="unavailable"),
        )
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert any("ShareholdingProvider" in e for e in result.provider_errors)
        assert any("unavailable" in g.lower() for g in result.data_gaps)

    @pytest.mark.asyncio
    async def test_corporate_actions_provider_failure(self) -> None:
        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[])
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(side_effect=ProviderError(provider="corporate_actions", message="timeout"))

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert any("CorporateActionsProvider" in e for e in result.provider_errors)
        assert any("corporate actions" in g.lower() for g in result.data_gaps)

    @pytest.mark.asyncio
    async def test_temporal_filtering(self) -> None:
        future_filing = _make_filing(filing_date=date(2025, 6, 1))
        past_filing = _make_filing(filing_id="F002", filing_date=date(2024, 3, 1))

        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[future_filing, past_filing])
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert len(result.filing_candidates) == 1
        assert result.filing_candidates[0].source_id == "F002"

    @pytest.mark.asyncio
    async def test_empty_providers(self) -> None:
        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[])
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_governance_sources(inp)

        assert len(result.filing_candidates) == 0
        assert len(result.shareholding_data) == 0
        assert len(result.corporate_actions) == 0
        assert any("filings" in g.lower() for g in result.data_gaps)

    @pytest.mark.asyncio
    async def test_bse_code_fallback(self) -> None:
        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[_make_filing()])
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol=None,
            bse_code="500325",
            observation_date=date(2024, 12, 31),
        )
        await tools.discover_governance_sources(inp)

        cf.get_filings.assert_called_once()
        call_args = cf.get_filings.call_args
        assert call_args[0][0] == "500325"
        assert call_args[0][1] == "BSE"

    @pytest.mark.asyncio
    async def test_shareholding_temporal_filtering(self) -> None:
        obs_date = date(2024, 6, 30)
        future_pattern = _make_shareholding_pattern(pattern_date=date(2024, 9, 30))
        past_pattern = _make_shareholding_pattern(pattern_date=date(2024, 3, 31))

        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[future_pattern, past_pattern])
        cf = AsyncMock()
        cf.get_filings = AsyncMock(return_value=[])
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[])

        tools = _build_tools(corporate_filings=cf, shareholding=sh, corporate_actions=ca)

        inp = DiscoverGovernanceSourcesInput(
            company_id=uuid.uuid4(),
            company_name="Test Co",
            nse_symbol="TEST",
            observation_date=obs_date,
        )
        result = await tools.discover_governance_sources(inp)

        assert len(result.shareholding_data) == 1
        assert result.shareholding_data[0].as_of_date == date(2024, 3, 31)


# ---------------------------------------------------------------------------
# Tool 3: retrieve_document
# ---------------------------------------------------------------------------


class TestRetrieveDocument:
    @pytest.mark.asyncio
    async def test_successful_retrieval(self) -> None:
        content = "Annual report content for governance analysis"
        cf = AsyncMock()
        cf.get_filing_document = AsyncMock(
            return_value=FilingDocument(
                filing_id="F001",
                content=content,
                content_type="text/html",
            )
        )
        tools = _build_tools(corporate_filings=cf)

        inp = RetrieveDocumentInput(filing_id="F001")
        result = await tools.retrieve_document(inp)

        assert result.content == content
        assert result.content_type == "text/html"
        assert result.filing_id == "F001"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        assert result.content_hash == expected_hash

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self) -> None:
        cf = AsyncMock()
        cf.get_filing_document = AsyncMock(side_effect=ProviderError(provider="corporate_filings", message="not found"))
        tools = _build_tools(corporate_filings=cf)

        inp = RetrieveDocumentInput(filing_id="MISSING")
        with pytest.raises(ProviderError):
            await tools.retrieve_document(inp)


# ---------------------------------------------------------------------------
# Tool 4: get_shareholding_data
# ---------------------------------------------------------------------------


class TestGetShareholdingData:
    @pytest.mark.asyncio
    async def test_successful_retrieval(self) -> None:
        pattern = _make_shareholding_pattern()
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[pattern])
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_shareholding_data(inp)

        assert len(result.snapshots) == 1
        assert result.snapshots[0].promoter_holding_pct == Decimal("50.49")
        assert result.snapshots[0].fii_holding_pct == Decimal("23.34")
        assert result.snapshots[0].dii_holding_pct == Decimal("13.12")
        assert result.snapshots[0].public_holding_pct == Decimal("13.05")
        assert result.snapshots[0].pledged_percentage == Decimal("0.00")
        assert result.snapshots[0].quarter == "Q1FY2025"
        assert result.provider_errors == []

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(side_effect=ProviderError(provider="shareholding", message="timeout"))
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_shareholding_data(inp)

        assert result.snapshots == []
        assert len(result.provider_errors) == 1
        assert "ShareholdingProvider" in result.provider_errors[0]

    @pytest.mark.asyncio
    async def test_temporal_filtering(self) -> None:
        obs = date(2024, 6, 30)
        future = _make_shareholding_pattern(pattern_date=date(2024, 9, 30))
        past = _make_shareholding_pattern(pattern_date=date(2024, 3, 31))
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[future, past])
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=obs,
        )
        result = await tools.get_shareholding_data(inp)

        assert len(result.snapshots) == 1
        assert result.snapshots[0].as_of_date == date(2024, 3, 31)

    @pytest.mark.asyncio
    async def test_bse_code_fallback(self) -> None:
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            bse_code="500325",
            observation_date=date(2024, 12, 31),
        )
        await tools.get_shareholding_data(inp)

        call_args = sh.get_shareholding_history.call_args
        assert call_args[0][0] == "500325"
        assert call_args[0][1] == "BSE"

    @pytest.mark.asyncio
    async def test_preserves_decimal_precision(self) -> None:
        pattern = _make_shareholding_pattern(
            promoter=Decimal("56.123456"),
            fii=Decimal("22.654321"),
        )
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[pattern])
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_shareholding_data(inp)

        assert result.snapshots[0].promoter_holding_pct == Decimal("56.123456")
        assert result.snapshots[0].fii_holding_pct == Decimal("22.654321")

    @pytest.mark.asyncio
    async def test_empty_provider_response(self) -> None:
        sh = AsyncMock()
        sh.get_shareholding_history = AsyncMock(return_value=[])
        tools = _build_tools(shareholding=sh)

        inp = GetShareholdingInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_shareholding_data(inp)

        assert result.snapshots == []
        assert result.provider_errors == []


# ---------------------------------------------------------------------------
# Tool 5: get_corporate_actions
# ---------------------------------------------------------------------------


class TestGetCorporateActions:
    @pytest.mark.asyncio
    async def test_successful_retrieval(self) -> None:
        record = _make_corporate_action_record()
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[record])
        tools = _build_tools(corporate_actions=ca)

        inp = GetCorporateActionsInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_corporate_actions(inp)

        assert len(result.actions) == 1
        assert result.actions[0].action_type == CorporateActionType.DIVIDEND
        assert result.actions[0].value == Decimal("10.00")
        assert result.actions[0].details == "Final Dividend of INR 10 per share"
        assert result.provider_errors == []

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(side_effect=ProviderError(provider="corporate_actions", message="timeout"))
        tools = _build_tools(corporate_actions=ca)

        inp = GetCorporateActionsInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_corporate_actions(inp)

        assert result.actions == []
        assert any("CorporateActionsProvider" in e for e in result.provider_errors)

    @pytest.mark.asyncio
    async def test_temporal_filtering(self) -> None:
        obs = date(2024, 6, 30)
        future_action = _make_corporate_action_record(ex_date=date(2024, 9, 1))
        past_action = _make_corporate_action_record(ex_date=date(2024, 3, 1))

        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[future_action, past_action])
        tools = _build_tools(corporate_actions=ca)

        inp = GetCorporateActionsInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=obs,
        )
        result = await tools.get_corporate_actions(inp)

        assert len(result.actions) == 1
        assert result.actions[0].ex_date == date(2024, 3, 1)

    @pytest.mark.asyncio
    async def test_multiple_action_types(self) -> None:
        records = [
            _make_corporate_action_record(action_type="DIVIDEND"),
            _make_corporate_action_record(action_type="SPLIT", ex_date=date(2024, 5, 1)),
            _make_corporate_action_record(action_type="BONUS", ex_date=date(2024, 4, 1)),
        ]
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=records)
        tools = _build_tools(corporate_actions=ca)

        inp = GetCorporateActionsInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_corporate_actions(inp)

        assert len(result.actions) == 3
        types = {a.action_type for a in result.actions}
        assert CorporateActionType.DIVIDEND in types
        assert CorporateActionType.SPLIT in types
        assert CorporateActionType.BONUS in types

    @pytest.mark.asyncio
    async def test_preserves_decimal_values(self) -> None:
        record = _make_corporate_action_record(value=Decimal("25.5000"))
        ca = AsyncMock()
        ca.get_corporate_actions = AsyncMock(return_value=[record])
        tools = _build_tools(corporate_actions=ca)

        inp = GetCorporateActionsInput(
            company_id=uuid.uuid4(),
            nse_symbol="RELIANCE",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.get_corporate_actions(inp)

        assert result.actions[0].value == Decimal("25.5000")


# ---------------------------------------------------------------------------
# Tool 6: persist_evidence
# ---------------------------------------------------------------------------


class TestPersistEvidence:
    @pytest.mark.asyncio
    async def test_persist_evidence_uses_governance_agent_name(self) -> None:
        session = AsyncMock()
        mock_record = MockEvidence()
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", mock_record.id))
        tools = _build_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.REGULATORY_FILING,
                    claim="Promoter pledge at 5.2%",
                    context="Annual report page 42",
                    page_or_section="Section 5",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 1
        added_record = session.add.call_args[0][0]
        assert added_record.extracted_by == GOVERNANCE_AGENT_NAME


# ---------------------------------------------------------------------------
# Tool 7: persist_findings
# ---------------------------------------------------------------------------


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_valid_governance_finding(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=GOVERNANCE_AGENT_NAME,
                    finding_type=FindingType.MANAGEMENT_CLAIM,
                    category="management_claim",
                    content="Management guided for 20% revenue growth",
                    confidence=ConfidenceLevel.HIGH,
                    observation_date=date(2024, 12, 31),
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 2
        assert result.rejected == []

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=GOVERNANCE_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="invalid_category_xyz",
                    content="Some content",
                    confidence=ConfidenceLevel.MEDIUM,
                    observation_date=date(2024, 12, 31),
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.rejected) == 1
        assert "Invalid category" in result.rejected[0].reason

    @pytest.mark.asyncio
    async def test_all_governance_categories_accepted(self) -> None:
        run_service = MockRunService()
        run_service.record_findings = AsyncMock(
            return_value=[MockPersistedFinding() for _ in GOVERNANCE_FINDING_CATEGORIES],
        )
        tools = _build_tools(run_service=run_service)

        findings = [
            FindingItem(
                agent_name=GOVERNANCE_AGENT_NAME,
                finding_type=FindingType.FACT,
                category=cat,
                content=f"Finding for {cat}",
                confidence=ConfidenceLevel.MEDIUM,
                observation_date=date(2024, 12, 31),
            )
            for cat in GOVERNANCE_FINDING_CATEGORIES
        ]

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=findings,
        )
        result = await tools.persist_findings(inp)

        assert result.rejected == []


# ---------------------------------------------------------------------------
# Tool 8: persist_management_statements
# ---------------------------------------------------------------------------


class TestPersistManagementStatements:
    @pytest.mark.asyncio
    async def test_create_new_statement(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        evidence_id = uuid.uuid4()
        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            new_statements=[
                NewManagementStatement(
                    statement="Revenue growth of 20% expected",
                    statement_date=date(2024, 5, 15),
                    category="REVENUE_GUIDANCE",
                    expected_outcome="20% revenue growth by FY25",
                    evidence_index=0,
                ),
            ],
            evidence_ids=[evidence_id],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.created_ids) == 1
        assert result.rejected_count == 0

        added_record = session.add.call_args[0][0]
        assert added_record.status == ManagementStatementStatus.PENDING
        assert added_record.source_evidence_id == evidence_id
        assert added_record.category == ManagementStatementCategory.REVENUE_GUIDANCE

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self) -> None:
        session = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            new_statements=[
                NewManagementStatement(
                    statement="Some statement",
                    statement_date=date(2024, 5, 15),
                    category="INVALID_CATEGORY",
                    evidence_index=0,
                ),
            ],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.created_ids) == 0
        assert result.rejected_count == 1

    @pytest.mark.asyncio
    async def test_update_pending_to_met_with_evidence(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.PENDING,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        session.flush = AsyncMock()
        tools = _build_tools(session=session)

        evidence_id = uuid.uuid4()
        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="MET",
                    actual_outcome="Revenue grew 22%",
                    outcome_evidence_index=0,
                    justification="Q4 results show 22% growth",
                ),
            ],
            evidence_ids=[evidence_id],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.updated_ids) == 1
        assert result.rejected_count == 0
        assert existing.status == ManagementStatementStatus.MET
        assert existing.actual_outcome == "Revenue grew 22%"
        assert existing.outcome_evidence_id == evidence_id

    @pytest.mark.asyncio
    async def test_met_without_evidence_rejected(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.PENDING,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        tools = _build_tools(session=session)

        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="MET",
                    justification="Assumed met",
                ),
            ],
        )
        result = await tools.persist_management_statements(inp)

        assert result.updated_ids == []
        assert result.rejected_count == 1

    @pytest.mark.asyncio
    async def test_terminal_state_transition_rejected(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.MET,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        tools = _build_tools(session=session)

        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="MISSED",
                    justification="Reclassify",
                ),
            ],
        )
        result = await tools.persist_management_statements(inp)

        assert result.updated_ids == []
        assert result.rejected_count == 1

    @pytest.mark.asyncio
    async def test_statement_not_found_rejected(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        tools = _build_tools(session=session)

        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(uuid.uuid4()),
                    proposed_status="MISSED",
                    justification="Not found",
                ),
            ],
        )
        result = await tools.persist_management_statements(inp)

        assert result.updated_ids == []
        assert result.rejected_count == 1

    @pytest.mark.asyncio
    async def test_pending_to_unknown_valid(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.PENDING,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        session.flush = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="UNKNOWN",
                    justification="Insufficient evidence",
                ),
            ],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.updated_ids) == 1
        assert existing.status == ManagementStatementStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_unknown_to_met_valid(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.UNKNOWN,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        session.flush = AsyncMock()
        tools = _build_tools(session=session)

        evidence_id = uuid.uuid4()
        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="MET",
                    actual_outcome="Revenue achieved",
                    outcome_evidence_index=0,
                    justification="New evidence found",
                ),
            ],
            evidence_ids=[evidence_id],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.updated_ids) == 1
        assert existing.status == ManagementStatementStatus.MET

    @pytest.mark.asyncio
    async def test_mixed_creates_and_updates(self) -> None:
        stmt_id = uuid.uuid4()
        existing = MockManagementStatement(
            id=stmt_id,
            status=ManagementStatementStatus.PENDING,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=existing)
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        evidence_id = uuid.uuid4()
        inp = PersistStatementsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            new_statements=[
                NewManagementStatement(
                    statement="New guidance",
                    statement_date=date(2024, 8, 1),
                    category="MARGIN_GUIDANCE",
                    evidence_index=0,
                ),
            ],
            statement_updates=[
                ManagementStatementUpdate(
                    statement_id=str(stmt_id),
                    proposed_status="MISSED",
                    justification="Revenue fell short",
                ),
            ],
            evidence_ids=[evidence_id],
        )
        result = await tools.persist_management_statements(inp)

        assert len(result.created_ids) == 1
        assert len(result.updated_ids) == 1
        assert result.rejected_count == 0


# ---------------------------------------------------------------------------
# Tool 9: persist_shareholding
# ---------------------------------------------------------------------------


class TestPersistShareholding:
    @pytest.mark.asyncio
    async def test_new_shareholding_inserted(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        snapshot = ShareholdingSnapshot(
            as_of_date=date(2024, 6, 30),
            quarter="Q1FY2025",
            promoter_holding_pct=Decimal("50.49"),
            fii_holding_pct=Decimal("23.34"),
            dii_holding_pct=Decimal("13.12"),
            public_holding_pct=Decimal("13.05"),
            source_provider="shareholding",
        )

        inp = PersistShareholdingInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            snapshots=[snapshot],
        )
        result = await tools.persist_shareholding(inp)

        assert len(result.persisted_ids) == 1
        assert result.skipped_count == 0

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self) -> None:
        existing_record = MagicMock()
        existing_record.id = uuid.uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_record
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        snapshot = ShareholdingSnapshot(
            as_of_date=date(2024, 6, 30),
            quarter="Q1FY2025",
            promoter_holding_pct=Decimal("50.49"),
            fii_holding_pct=Decimal("23.34"),
            dii_holding_pct=Decimal("13.12"),
            public_holding_pct=Decimal("13.05"),
            source_provider="shareholding",
        )

        inp = PersistShareholdingInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            snapshots=[snapshot],
        )
        result = await tools.persist_shareholding(inp)

        assert result.persisted_ids == []
        assert result.skipped_count == 1

    @pytest.mark.asyncio
    async def test_mixed_new_and_duplicate(self) -> None:
        call_count = 0

        def mock_scalar(*_args: Any, **_kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return MagicMock(id=uuid.uuid4())

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = mock_scalar
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        snapshots = [
            ShareholdingSnapshot(
                as_of_date=date(2024, 6, 30),
                quarter="Q1FY2025",
                promoter_holding_pct=Decimal("50.49"),
                fii_holding_pct=Decimal("23.34"),
                dii_holding_pct=Decimal("13.12"),
                public_holding_pct=Decimal("13.05"),
                source_provider="shareholding",
            ),
            ShareholdingSnapshot(
                as_of_date=date(2024, 3, 31),
                quarter="Q4FY2024",
                promoter_holding_pct=Decimal("50.50"),
                fii_holding_pct=Decimal("23.30"),
                dii_holding_pct=Decimal("13.10"),
                public_holding_pct=Decimal("13.10"),
                source_provider="shareholding",
            ),
        ]

        inp = PersistShareholdingInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            snapshots=snapshots,
        )
        result = await tools.persist_shareholding(inp)

        assert len(result.persisted_ids) == 1
        assert result.skipped_count == 1


# ---------------------------------------------------------------------------
# Tool 10: persist_governance_data
# ---------------------------------------------------------------------------


class TestPersistGovernanceData:
    @pytest.mark.asyncio
    async def test_persist_pledge_data(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        pledge_snap = ShareholdingSnapshot(
            as_of_date=date(2024, 6, 30),
            quarter="Q1FY2025",
            promoter_holding_pct=Decimal("50.49"),
            fii_holding_pct=Decimal("23.34"),
            dii_holding_pct=Decimal("13.12"),
            public_holding_pct=Decimal("13.05"),
            pledged_percentage=Decimal("5.20"),
            source_provider="shareholding",
        )

        inp = PersistGovernanceDataInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            pledge_snapshots=[pledge_snap],
        )
        result = await tools.persist_governance_data(inp)

        assert len(result.pledge_ids) == 1
        assert result.corporate_action_ids == []

    @pytest.mark.asyncio
    async def test_persist_corporate_actions(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        action = CorporateActionSnapshot(
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2024, 7, 18),
            record_date=date(2024, 7, 19),
            details="Final Dividend of INR 10",
            value=Decimal("10.00"),
            source_provider="corporate_actions",
        )

        inp = PersistGovernanceDataInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            corporate_actions=[action],
        )
        result = await tools.persist_governance_data(inp)

        assert result.pledge_ids == []
        assert len(result.corporate_action_ids) == 1

    @pytest.mark.asyncio
    async def test_persist_both_pledge_and_actions(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        pledge_snap = ShareholdingSnapshot(
            as_of_date=date(2024, 6, 30),
            quarter="Q1FY2025",
            promoter_holding_pct=Decimal("50.49"),
            fii_holding_pct=Decimal("23.34"),
            dii_holding_pct=Decimal("13.12"),
            public_holding_pct=Decimal("13.05"),
            pledged_percentage=Decimal("5.20"),
            source_provider="shareholding",
        )

        action = CorporateActionSnapshot(
            action_type=CorporateActionType.BUYBACK,
            ex_date=date(2024, 4, 1),
            details="Buyback of shares",
            value=Decimal("500.00"),
            source_provider="corporate_actions",
        )

        inp = PersistGovernanceDataInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            pledge_snapshots=[pledge_snap],
            corporate_actions=[action],
        )
        result = await tools.persist_governance_data(inp)

        assert len(result.pledge_ids) == 1
        assert len(result.corporate_action_ids) == 1

    @pytest.mark.asyncio
    async def test_pledge_duplicate_skipped(self) -> None:
        existing_record = MagicMock()
        existing_record.id = uuid.uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_record
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        pledge_snap = ShareholdingSnapshot(
            as_of_date=date(2024, 6, 30),
            quarter="Q1FY2025",
            promoter_holding_pct=Decimal("50.49"),
            fii_holding_pct=Decimal("23.34"),
            dii_holding_pct=Decimal("13.12"),
            public_holding_pct=Decimal("13.05"),
            pledged_percentage=Decimal("5.20"),
            source_provider="shareholding",
        )

        inp = PersistGovernanceDataInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            pledge_snapshots=[pledge_snap],
        )
        result = await tools.persist_governance_data(inp)

        assert result.pledge_ids == []

    @pytest.mark.asyncio
    async def test_empty_inputs(self) -> None:
        session = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistGovernanceDataInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
        )
        result = await tools.persist_governance_data(inp)

        assert result.pledge_ids == []
        assert result.corporate_action_ids == []


# ---------------------------------------------------------------------------
# Internal helper: create_research_document
# ---------------------------------------------------------------------------


class TestCreateResearchDocument:
    @pytest.mark.asyncio
    async def test_creates_document(self) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: setattr(r, "id", uuid.uuid4()))
        tools = _build_tools(session=session)

        candidate = SourceCandidate(
            source_id="F001",
            source_type=DocumentType.ANNUAL_REPORT,
            provider="corporate_filings",
            title="Annual Report FY24",
            publication_date=date(2024, 6, 1),
            source_tier=SourceTier.TIER_1,
            url="https://bseindia.com/reports/F001.pdf",
        )
        doc_id = await tools.create_research_document(
            company_id=uuid.uuid4(),
            candidate=candidate,
            content_hash="abc123",
        )

        assert doc_id is not None
        added_record = session.add.call_args[0][0]
        assert added_record.title == "Annual Report FY24"
        assert added_record.source_tier == SourceTier.TIER_1
        assert added_record.content_hash == "abc123"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_map_filing_type_annual_report(self) -> None:
        assert _map_filing_type("ANNUAL_REPORT") == DocumentType.ANNUAL_REPORT

    def test_map_filing_type_quarterly_result(self) -> None:
        assert _map_filing_type("QUARTERLY_RESULT") == DocumentType.QUARTERLY_RESULT

    def test_map_filing_type_investor_presentation(self) -> None:
        assert _map_filing_type("INVESTOR_PRESENTATION") == DocumentType.INVESTOR_PRESENTATION

    def test_map_filing_type_unknown_defaults_to_filing(self) -> None:
        assert _map_filing_type("UNKNOWN_TYPE") == DocumentType.FILING

    def test_map_filing_type_case_insensitive(self) -> None:
        assert _map_filing_type("annual_report") == DocumentType.ANNUAL_REPORT

    def test_compute_start_date_quarters(self) -> None:
        obs = date(2024, 12, 31)
        result = _compute_start_date_for_quarters(obs, 8)
        assert result == date(2022, 12, 28)

    def test_compute_start_date_quarters_wraps_year(self) -> None:
        obs = date(2024, 3, 31)
        result = _compute_start_date_for_quarters(obs, 4)
        assert result.year == 2023

    def test_compute_start_date_single_quarter(self) -> None:
        obs = date(2024, 6, 30)
        result = _compute_start_date_for_quarters(obs, 1)
        assert result == date(2024, 3, 28)


# ---------------------------------------------------------------------------
# Tool Inventory Completeness
# ---------------------------------------------------------------------------


class TestToolInventoryCompleteness:
    def test_tools_class_has_all_9_methods(self) -> None:
        expected_methods = [
            "load_company_context",
            "discover_governance_sources",
            "retrieve_document",
            "get_shareholding_data",
            "get_corporate_actions",
            "persist_evidence",
            "persist_findings",
            "persist_management_statements",
            "persist_shareholding",
            "persist_governance_data",
        ]
        for method_name in expected_methods:
            assert hasattr(ManagementGovernanceTools, method_name), f"Missing tool method: {method_name}"

    def test_has_internal_helper(self) -> None:
        assert hasattr(ManagementGovernanceTools, "create_research_document")

    def test_constructor_accepts_required_providers(self) -> None:
        tools = _build_tools()
        assert tools._corporate_filings is not None
        assert tools._shareholding is not None
        assert tools._corporate_actions is not None

    def test_no_search_or_news_provider(self) -> None:
        import inspect

        sig = inspect.signature(ManagementGovernanceTools.__init__)
        params = list(sig.parameters.keys())
        assert "search" not in params
        assert "news" not in params


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_company_not_found_error(self) -> None:
        err = CompanyNotFoundForGovernanceError("TEST_ID")
        assert "TEST_ID" in str(err)
        assert err.identifier == "TEST_ID"

    def test_inherits_from_agent_error(self) -> None:
        from app.agents.company_research.exceptions import AgentError

        err = CompanyNotFoundForGovernanceError("X")
        assert isinstance(err, AgentError)
