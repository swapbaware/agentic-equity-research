"""Unit tests for FutureGrowthTools (Phase 12.2).

Tests cover the 8 architecture-defined tool methods:
  1. load_company_context
  2. discover_growth_sources
  3. retrieve_document
  4. persist_evidence
  5. persist_findings
  6. persist_growth_opportunities
  7. persist_scores
  8. create_research_document (internal helper)

Plus helper functions _classify_growth_source, _tier_from_url, _map_filing_type.

Architecture reference: docs/architecture/phase-12-future-growth-optionality-agent.md §21
Acceptance criteria: AC-03, AC-04, AC-05, AC-06, AC-07
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.contracts import (
    GROWTH_AGENT_NAME,
    GROWTH_FINDING_CATEGORIES,
    DiscoverGrowthSourcesInput,
    EvidenceItem,
    FindingItem,
    GrowthOpportunityDraft,
    GrowthScoreComponent,
    LoadGrowthContextInput,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistGrowthOpportunitiesInput,
    PersistGrowthScoresInput,
    RetrieveDocumentInput,
    SourceCandidate,
)
from app.agents.future_growth.exceptions import CompanyNotFoundForGrowthError
from app.agents.future_growth.tools import (
    FutureGrowthTools,
    _classify_growth_source,
    _map_filing_type,
    _tier_from_url,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    GrowthCategory,
    GrowthMaturity,
    ManagementStatementCategory,
    ManagementStatementStatus,
    ResearchRunStatus,
    ScoreDimension,
    SourceTier,
)
from app.providers.errors import ProviderError
from app.providers.types import Filing, FilingDocument, NewsArticle, SearchResult

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockCompany:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Infosys Limited",
        nse_symbol: str | None = "INFY",
        bse_code: str | None = "500209",
        isin: str = "INE009A01021",
        market_cap: Decimal | None = Decimal("6500000.0000"),
        is_active: bool = True,
        industry_id: uuid.UUID | None = None,
        industry: Any = None,
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


class MockIndustry:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Information Technology",
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
        category: str = "growth_opportunity",
        finding_type: str = FindingType.AI_INFERENCE,
        content: str = "Test growth finding",
        confidence: str = ConfidenceLevel.MEDIUM,
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
        statement_date: date = date(2025, 1, 15),
        statement: str = "We plan to expand to 3 new markets",
        category: ManagementStatementCategory = ManagementStatementCategory.EXPANSION,
        expected_outcome: str | None = "Market entry by FY26",
        status: ManagementStatementStatus = ManagementStatementStatus.PENDING,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.company_id = company_id or uuid.uuid4()
        self.statement_date = statement_date
        self.statement = statement
        self.category = category
        self.expected_outcome = expected_outcome
        self.status = status


class MockEvidence:
    def __init__(self, *, id: uuid.UUID | None = None) -> None:
        self.id = id or uuid.uuid4()


class MockPersistedFinding:
    def __init__(self, *, id: uuid.UUID | None = None) -> None:
        self.id = id or uuid.uuid4()


class MockMoatFinding:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        content: str = "Network effects moat: WIDE",
        agent_name: str = "competitive_moat_agent",
    ) -> None:
        self.id = id or uuid.uuid4()
        self.content = content
        self.agent_name = agent_name


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
EXECUTION_ID = uuid.uuid4()
INDUSTRY_ID = uuid.uuid4()
OBSERVATION_DATE = date(2025, 6, 30)


def _make_session_mock() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_run_service_mock() -> AsyncMock:
    return AsyncMock()


def _make_tools(
    session: AsyncMock | None = None,
    run_service: AsyncMock | None = None,
    search: AsyncMock | None = None,
    news: AsyncMock | None = None,
    corporate_filings: AsyncMock | None = None,
) -> FutureGrowthTools:
    return FutureGrowthTools(
        session=session or _make_session_mock(),
        run_service=run_service or _make_run_service_mock(),
        search=search or AsyncMock(),
        news=news or AsyncMock(),
        corporate_filings=corporate_filings or AsyncMock(),
    )


# ===========================================================================
# Tool 1: load_company_context
# ===========================================================================


class TestLoadCompanyContext:
    """AC-04: load_company_context loads Phase 8/9/10/11 findings."""

    @pytest.mark.asyncio
    async def test_company_not_found_raises(self) -> None:
        session = _make_session_mock()
        session.get = AsyncMock(return_value=None)
        tools = _make_tools(session=session)

        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        with pytest.raises(CompanyNotFoundForGrowthError):
            await tools.load_company_context(inp)

    @pytest.mark.asyncio
    async def test_happy_path_with_all_context(self) -> None:
        industry = MockIndustry(id=INDUSTRY_ID)
        company = MockCompany(
            id=COMPANY_ID,
            industry_id=INDUSTRY_ID,
            industry=industry,
        )

        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        # Mock moat findings query
        moat_findings = [MockMoatFinding()]
        moat_result_mock = MagicMock()
        moat_result_mock.scalars.return_value.all.return_value = moat_findings

        # Mock management statements query
        ms = MockManagementStatement(company_id=COMPANY_ID)
        ms_result_mock = MagicMock()
        ms_result_mock.scalars.return_value.all.return_value = [ms]

        # Mock existing opportunities query
        opp_id = uuid.uuid4()
        opp_result_mock = MagicMock()
        opp_result_mock.scalars.return_value.all.return_value = [opp_id]

        session.execute = AsyncMock(side_effect=[moat_result_mock, ms_result_mock, opp_result_mock])

        run_service = _make_run_service_mock()

        company_run = MockResearchRun()
        industry_run = MockResearchRun()
        company_finding = MockFinding(category="business_model")
        industry_finding = MockFinding(category="industry_growth_drivers")

        run_service.get_runs_for_company = AsyncMock(return_value=[company_run])
        run_service.get_findings = AsyncMock(side_effect=[[company_finding], [industry_finding]])
        run_service.get_runs_for_industry = AsyncMock(return_value=[industry_run])

        tools = _make_tools(session=session, run_service=run_service)
        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_company_context(inp)

        assert result.company_name == "Infosys Limited"
        assert result.industry_name == "Information Technology"
        assert result.nse_symbol == "INFY"
        assert result.bse_code == "500209"
        assert len(result.company_findings) == 1
        assert len(result.industry_findings) == 1
        assert result.moat_context is not None
        assert "Network effects moat" in result.moat_context
        assert len(result.management_statements) == 1
        assert result.management_statements[0].category == ManagementStatementCategory.EXPANSION
        assert len(result.existing_opportunities) == 1

    @pytest.mark.asyncio
    async def test_no_upstream_findings(self) -> None:
        """When Phase 8/9 findings are absent, output is empty lists (not errors)."""
        company = MockCompany(id=COMPANY_ID, industry=None, industry_id=None)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        # No moat, statements, or existing opportunities
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)
        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_company_context(inp)

        assert result.company_name == "Infosys Limited"
        assert result.industry_name is None
        assert result.company_findings == []
        assert result.industry_findings == []
        assert result.moat_context is None
        assert result.management_statements == []
        assert result.existing_opportunities == []

    @pytest.mark.asyncio
    async def test_optional_context_failure_does_not_block(self) -> None:
        """Phase 10/11 failures are caught and logged — do not raise."""
        company = MockCompany(id=COMPANY_ID, industry=None, industry_id=None)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)
        session.execute = AsyncMock(side_effect=Exception("DB error"))

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)
        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_company_context(inp)

        assert result.company_name == "Infosys Limited"
        assert result.moat_context is None
        assert result.management_statements == []

    @pytest.mark.asyncio
    async def test_correct_agent_name_filters(self) -> None:
        """Verifies company runs are loaded via run_service (AC-04)."""
        company = MockCompany(id=COMPANY_ID, industry=None, industry_id=None)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)
        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        await tools.load_company_context(inp)

        run_service.get_runs_for_company.assert_called_once_with(COMPANY_ID, limit=1)

    @pytest.mark.asyncio
    async def test_output_contract_shape(self) -> None:
        company = MockCompany(id=COMPANY_ID, industry=None, industry_id=None)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)
        inp = LoadGrowthContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_company_context(inp)

        from app.agents.contracts import LoadGrowthContextOutput

        assert isinstance(result, LoadGrowthContextOutput)
        assert result.model_config.get("frozen") is True


# ===========================================================================
# Tool 2: discover_growth_sources
# ===========================================================================


class TestDiscoverGrowthSources:
    """AC-05: discover_growth_sources queries SearchProvider + NewsProvider +
    CorporateFilingsProvider."""

    @pytest.mark.asyncio
    async def test_happy_path_all_providers(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Infosys AI strategy expansion",
                    url="https://example.com/infy-ai",
                    snippet="Infosys investing in AI capabilities",
                ),
            ]
        )

        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Infosys launches new cloud platform",
                    url="https://news.example.com/infy-cloud",
                    source="ET",
                    published_at=datetime(2025, 5, 1, tzinfo=UTC),
                ),
            ]
        )

        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL001",
                    symbol="INFY",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Annual Report FY25",
                    filing_date=date(2025, 6, 1),
                    url="https://nse.example.com/filing/001",
                ),
            ]
        )

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            industry_name="Information Technology",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
            search_themes=["artificial_intelligence"],
        )
        result = await tools.discover_growth_sources(inp)

        assert len(result.sources) >= 3
        assert result.provider_errors == []

        providers = {s.provider for s in result.sources}
        assert "search" in providers
        assert "news" in providers
        assert "corporate_filings" in providers

    @pytest.mark.asyncio
    async def test_temporal_filtering(self) -> None:
        """News published after observation_date must be excluded."""
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Future news",
                    url="https://news.example.com/future",
                    source="ET",
                    published_at=datetime(2025, 7, 15, tzinfo=UTC),
                ),
                NewsArticle(
                    title="Past news",
                    url="https://news.example.com/past",
                    source="ET",
                    published_at=datetime(2025, 5, 1, tzinfo=UTC),
                ),
            ]
        )

        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        urls = [s.url for s in result.sources]
        assert "https://news.example.com/past" in urls
        assert "https://news.example.com/future" not in urls

    @pytest.mark.asyncio
    async def test_deduplication(self) -> None:
        """Duplicate URLs are removed."""
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(title="Page 1", url="https://example.com/page", snippet="x"),
            ]
        )

        tools = _make_tools(search=search)
        tools._news.search_news = AsyncMock(return_value=[])
        tools._corporate_filings.get_filings = AsyncMock(return_value=[])

        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        url_counts: dict[str, int] = {}
        for s in result.sources:
            key = s.url or s.source_id
            url_counts[key] = url_counts.get(key, 0) + 1
        for count in url_counts.values():
            assert count == 1

    @pytest.mark.asyncio
    async def test_search_provider_failure(self) -> None:
        """Provider failure produces error message, not exception."""
        search = AsyncMock()
        search.search = AsyncMock(side_effect=ProviderError(provider="search", message="Search unavailable"))

        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert any("SearchProvider" in e for e in result.provider_errors)
        # Sources may be empty or partial, but no exception
        assert isinstance(result.sources, list)

    @pytest.mark.asyncio
    async def test_news_provider_failure(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(side_effect=ProviderError(provider="news", message="News unavailable"))
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert any("NewsProvider" in e for e in result.provider_errors)

    @pytest.mark.asyncio
    async def test_corporate_filings_failure(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            side_effect=ProviderError(provider="corporate_filings", message="Filings unavailable")
        )

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert any("CorporateFilingsProvider" in e for e in result.provider_errors)

    @pytest.mark.asyncio
    async def test_all_providers_fail(self) -> None:
        """When all providers fail, result has errors but no exception."""
        search = AsyncMock()
        search.search = AsyncMock(side_effect=ProviderError(provider="search", message="Search down"))
        news = AsyncMock()
        news.search_news = AsyncMock(side_effect=ProviderError(provider="news", message="News down"))
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            side_effect=ProviderError(provider="corporate_filings", message="Filings down")
        )

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
            search_themes=["artificial_intelligence"],
        )
        result = await tools.discover_growth_sources(inp)

        assert result.sources == []
        assert len(result.provider_errors) >= 3

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        """All providers return empty → empty sources, no errors."""
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert result.sources == []
        assert result.provider_errors == []

    @pytest.mark.asyncio
    async def test_filing_date_after_observation_excluded(self) -> None:
        """Filings with filing_date after observation_date excluded."""
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL_FUTURE",
                    symbol="INFY",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Future Filing",
                    filing_date=date(2025, 7, 15),
                ),
            ]
        )

        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert all(s.source_id != "FIL_FUTURE" for s in result.sources)

    @pytest.mark.asyncio
    async def test_output_contract_shape(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        from app.agents.contracts import DiscoverGrowthSourcesOutput

        assert isinstance(result, DiscoverGrowthSourcesOutput)
        assert result.model_config.get("frozen") is True

    @pytest.mark.asyncio
    async def test_theme_search_queries_generated(self) -> None:
        """Themes produce additional search queries."""
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            observation_date=OBSERVATION_DATE,
            search_themes=["artificial_intelligence", "data_centres"],
        )
        await tools.discover_growth_sources(inp)

        # Base queries (2) + industry (0, no industry_name) + themes (2)
        assert search.search.call_count == 4

    @pytest.mark.asyncio
    async def test_no_nse_symbol_skips_filings(self) -> None:
        """When nse_symbol is None, corporate filings are not queried."""
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            nse_symbol=None,
            observation_date=OBSERVATION_DATE,
        )
        await tools.discover_growth_sources(inp)

        corporate_filings.get_filings.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_tier_assignment(self) -> None:
        """Filings get TIER_1, news gets TIER_3."""
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL001",
                    symbol="INFY",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Annual Report",
                    filing_date=date(2025, 5, 1),
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Infosys news",
                    url="https://news.example.com/infy",
                    source="ET",
                    published_at=datetime(2025, 4, 1, tzinfo=UTC),
                ),
            ]
        )
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys Limited",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        filing_sources = [s for s in result.sources if s.provider == "corporate_filings"]
        news_sources = [s for s in result.sources if s.provider == "news"]
        assert all(s.source_tier == SourceTier.TIER_1 for s in filing_sources)
        assert all(s.source_tier == SourceTier.TIER_3 for s in news_sources)


# ===========================================================================
# Tool 3: retrieve_document
# ===========================================================================


class TestRetrieveDocument:
    @pytest.mark.asyncio
    async def test_corporate_filings_retrieval(self) -> None:
        corporate_filings = AsyncMock()
        filing_doc = FilingDocument(
            filing_id="FIL001",
            content="Growth strategy: expanding into AI services",
            content_type="text/plain",
        )
        corporate_filings.get_filing_document = AsyncMock(return_value=filing_doc)

        tools = _make_tools(corporate_filings=corporate_filings)
        inp = RetrieveDocumentInput(filing_id="FIL001", provider="corporate_filings")
        result = await tools.retrieve_document(inp)

        expected_hash = hashlib.sha256(b"Growth strategy: expanding into AI services").hexdigest()
        assert result.content == "Growth strategy: expanding into AI services"
        assert result.content_hash == expected_hash
        assert result.filing_id == "FIL001"
        assert result.content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_search_provider_retrieval(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(title="AI Growth", url="https://example.com", snippet="AI expansion plans"),
            ]
        )

        tools = _make_tools(search=search)
        inp = RetrieveDocumentInput(filing_id="https://example.com", provider="search")
        result = await tools.retrieve_document(inp)

        assert result.content == "AI expansion plans"
        assert result.content_type == "text/snippet"
        assert result.content_hash == hashlib.sha256(b"AI expansion plans").hexdigest()

    @pytest.mark.asyncio
    async def test_search_empty_result(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        tools = _make_tools(search=search)
        inp = RetrieveDocumentInput(filing_id="https://example.com/missing", provider="search")
        result = await tools.retrieve_document(inp)

        assert result.content == ""
        assert result.content_hash == hashlib.sha256(b"").hexdigest()

    @pytest.mark.asyncio
    async def test_output_contract_shape(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        tools = _make_tools(search=search)
        inp = RetrieveDocumentInput(filing_id="test", provider="search")
        result = await tools.retrieve_document(inp)

        from app.agents.contracts import RetrieveDocumentOutput

        assert isinstance(result, RetrieveDocumentOutput)
        assert result.model_config.get("frozen") is True


# ===========================================================================
# Tool 4: persist_evidence
# ===========================================================================


class TestPersistEvidence:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        session = _make_session_mock()
        evidence_id = uuid.uuid4()

        async def mock_refresh(record: Any) -> None:
            record.id = evidence_id

        session.refresh = mock_refresh

        tools = _make_tools(session=session)
        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                    claim="Company plans AI expansion",
                    context="Annual report FY25, page 42",
                    page_or_section="42",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 1
        assert result.evidence_ids[0] == evidence_id
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_extracted_by_is_growth_agent(self) -> None:
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh
        tools = _make_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="test",
                    context="test",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        await tools.persist_evidence(inp)

        added_record = session.add.call_args[0][0]
        assert added_record.extracted_by == GROWTH_AGENT_NAME

    @pytest.mark.asyncio
    async def test_multiple_evidences(self) -> None:
        session = _make_session_mock()
        ids = [uuid.uuid4(), uuid.uuid4()]
        call_idx = 0

        async def mock_refresh(record: Any) -> None:
            nonlocal call_idx
            record.id = ids[call_idx]
            call_idx += 1

        session.refresh = mock_refresh
        tools = _make_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="claim1",
                    context="ctx1",
                    confidence=ConfidenceLevel.HIGH,
                ),
                EvidenceItem(
                    evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                    claim="claim2",
                    context="ctx2",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)
        assert result.evidence_ids == ids

    def test_empty_evidences_rejected_by_contract(self) -> None:
        """Contract enforces min_length=1 on evidences."""
        with pytest.raises(ValueError):
            PersistEvidenceInput(
                document_id=uuid.uuid4(),
                evidences=[],
            )


# ===========================================================================
# Tool 5: persist_findings
# ===========================================================================


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        run_service = _make_run_service_mock()
        persisted = [MockPersistedFinding()]
        run_service.record_findings = AsyncMock(return_value=persisted)

        tools = _make_tools(run_service=run_service)
        inp = PersistFindingsInput(
            run_id=RUN_ID,
            execution_id=EXECUTION_ID,
            findings=[
                FindingItem(
                    agent_name=GROWTH_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="growth_opportunity",
                    content="AI services expansion opportunity identified",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 1
        assert result.rejected == []

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self) -> None:
        run_service = _make_run_service_mock()
        run_service.record_findings = AsyncMock(return_value=[])

        tools = _make_tools(run_service=run_service)
        inp = PersistFindingsInput(
            run_id=RUN_ID,
            execution_id=EXECUTION_ID,
            findings=[
                FindingItem(
                    agent_name=GROWTH_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="invalid_category_xyz",
                    content="Bad category",
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert result.finding_ids == []
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 0
        assert "Invalid category" in result.rejected[0].reason

    @pytest.mark.asyncio
    async def test_valid_growth_categories_accepted(self) -> None:
        """All 14 growth finding categories are accepted."""
        run_service = _make_run_service_mock()
        persisted = [MockPersistedFinding() for _ in GROWTH_FINDING_CATEGORIES]
        run_service.record_findings = AsyncMock(return_value=persisted)

        findings = [
            FindingItem(
                agent_name=GROWTH_AGENT_NAME,
                finding_type=FindingType.AI_INFERENCE,
                category=cat,
                content=f"Finding for {cat}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            for cat in sorted(GROWTH_FINDING_CATEGORIES)
        ]

        tools = _make_tools(run_service=run_service)
        inp = PersistFindingsInput(
            run_id=RUN_ID,
            execution_id=EXECUTION_ID,
            findings=findings,
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == len(GROWTH_FINDING_CATEGORIES)
        assert result.rejected == []

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid(self) -> None:
        run_service = _make_run_service_mock()
        persisted = [MockPersistedFinding()]
        run_service.record_findings = AsyncMock(return_value=persisted)

        tools = _make_tools(run_service=run_service)
        inp = PersistFindingsInput(
            run_id=RUN_ID,
            execution_id=EXECUTION_ID,
            findings=[
                FindingItem(
                    agent_name=GROWTH_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="growth_opportunity",
                    content="Valid",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                FindingItem(
                    agent_name=GROWTH_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="bogus",
                    content="Invalid",
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 1

    def test_empty_findings_rejected_by_contract(self) -> None:
        """Contract enforces min_length=1 on findings."""
        with pytest.raises(ValueError):
            PersistFindingsInput(
                run_id=RUN_ID,
                execution_id=EXECUTION_ID,
                findings=[],
            )


# ===========================================================================
# Tool 6: persist_growth_opportunities
# ===========================================================================


class TestPersistGrowthOpportunities:
    """AC-06: persist_growth_opportunities handles INSERT with evidence junction."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        session = _make_session_mock()
        opp_id = uuid.uuid4()

        async def mock_refresh(record: Any) -> None:
            record.id = opp_id

        session.refresh = mock_refresh

        # Duplicate check returns nothing
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        evidence_ids = [uuid.uuid4(), uuid.uuid4()]

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="AI Services Platform",
                    category="TECHNOLOGY",
                    maturity="EARLY_STAGE",
                    addressable_market=Decimal("50000.0000"),
                    tam_methodology="Top-down from industry TAM",
                    tam_low=Decimal("30000.0000"),
                    tam_high=Decimal("80000.0000"),
                    timeline_years=3,
                    confidence="MEDIUM",
                    evidence_indices=[0, 1],
                    risks=["Competition from global players"],
                    rationale="Infosys investing in AI capabilities",
                ),
            ],
            evidence_ids=evidence_ids,
        )
        result = await tools.persist_growth_opportunities(inp)

        assert len(result.opportunity_ids) == 1
        assert result.opportunity_ids[0] == opp_id
        session.add.assert_called_once()

        added_record = session.add.call_args[0][0]
        assert added_record.category == GrowthCategory.TECHNOLOGY
        assert added_record.maturity == GrowthMaturity.EARLY_STAGE
        assert added_record.addressable_market == Decimal("50000.0000")
        assert added_record.confidence == ConfidenceLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_evidence_junction_linking(self) -> None:
        """Evidence indices are resolved and linked via junction table."""
        session = _make_session_mock()
        opp_id = uuid.uuid4()

        async def mock_refresh(record: Any) -> None:
            record.id = opp_id

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        execute_calls: list[Any] = []

        async def track_execute(stmt: Any) -> Any:
            execute_calls.append(stmt)
            return dup_result

        session.execute = track_execute

        ev_ids = [uuid.uuid4(), uuid.uuid4()]
        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Test Opp",
                    category="NEW_PRODUCT",
                    maturity="SPECULATIVE",
                    confidence="LOW",
                    evidence_indices=[0, 1],
                    rationale="test",
                ),
            ],
            evidence_ids=ev_ids,
        )
        await tools.persist_growth_opportunities(inp)

        # Dup check (1) + junction inserts (2) = at least 3 execute calls
        assert len(execute_calls) >= 3

    @pytest.mark.asyncio
    async def test_invalid_category_skipped(self) -> None:
        session = _make_session_mock()
        tools = _make_tools(session=session)

        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Bad Category Opp",
                    category="INVALID_CATEGORY",
                    maturity="SPECULATIVE",
                    confidence="LOW",
                    rationale="test",
                ),
            ],
        )
        result = await tools.persist_growth_opportunities(inp)

        assert result.opportunity_ids == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_maturity_skipped(self) -> None:
        session = _make_session_mock()
        tools = _make_tools(session=session)

        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Bad Maturity Opp",
                    category="TECHNOLOGY",
                    maturity="INVALID_MATURITY",
                    confidence="LOW",
                    rationale="test",
                ),
            ],
        )
        result = await tools.persist_growth_opportunities(inp)

        assert result.opportunity_ids == []

    @pytest.mark.asyncio
    async def test_duplicate_detection(self) -> None:
        """Existing opportunity with same name is not re-inserted."""
        session = _make_session_mock()
        existing_id = uuid.uuid4()

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = existing_id
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Existing Opp",
                    category="TECHNOLOGY",
                    maturity="PROVEN",
                    confidence="HIGH",
                    rationale="test",
                ),
            ],
        )
        result = await tools.persist_growth_opportunities(inp)

        assert result.opportunity_ids == [existing_id]
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_risks_json_structure(self) -> None:
        """TAM metadata and risks stored in risks JSON column."""
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="TAM Test Opp",
                    category="NEW_MARKET",
                    maturity="COMMERCIALIZING",
                    addressable_market=Decimal("100000"),
                    tam_methodology="Top-down",
                    tam_low=Decimal("70000"),
                    tam_high=Decimal("150000"),
                    confidence="MEDIUM",
                    risks=["Market competition", "Regulatory risk"],
                    rationale="test",
                ),
            ],
        )
        await tools.persist_growth_opportunities(inp)

        added_record = session.add.call_args[0][0]
        risks = added_record.risks
        assert risks is not None
        assert risks["tam_methodology"] == "Top-down"
        assert risks["tam_low"] == "70000"
        assert risks["tam_high"] == "150000"
        assert "Market competition" in risks["risk_factors"]

    @pytest.mark.asyncio
    async def test_invalid_confidence_defaults_to_low(self) -> None:
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Bad Confidence Opp",
                    category="EXPANSION",
                    maturity="SPECULATIVE",
                    confidence="INVALID_CONF",
                    rationale="test",
                ),
            ],
        )
        await tools.persist_growth_opportunities(inp)

        added_record = session.add.call_args[0][0]
        assert added_record.confidence == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_evidence_index_out_of_range_ignored(self) -> None:
        """Out-of-range evidence indices silently skipped."""
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        ev_ids = [uuid.uuid4()]
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Out of range Opp",
                    category="TECHNOLOGY",
                    maturity="SPECULATIVE",
                    confidence="LOW",
                    evidence_indices=[0, 99],
                    rationale="test",
                ),
            ],
            evidence_ids=ev_ids,
        )
        result = await tools.persist_growth_opportunities(inp)

        # Should succeed without error for the out-of-range index
        assert len(result.opportunity_ids) == 1

    @pytest.mark.asyncio
    async def test_addressable_market_decimal_preserved(self) -> None:
        """AC-08: Financial values use Decimal."""
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Decimal Test",
                    category="EXPANSION",
                    maturity="PROVEN",
                    addressable_market=Decimal("123456.7890"),
                    confidence="HIGH",
                    rationale="test",
                ),
            ],
        )
        await tools.persist_growth_opportunities(inp)

        added_record = session.add.call_args[0][0]
        assert isinstance(added_record.addressable_market, Decimal)
        assert added_record.addressable_market == Decimal("123456.7890")

    @pytest.mark.asyncio
    async def test_output_contract_shape(self) -> None:
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=dup_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthOpportunitiesInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            opportunities=[
                GrowthOpportunityDraft(
                    opportunity_name="Shape Test",
                    category="TECHNOLOGY",
                    maturity="SPECULATIVE",
                    confidence="LOW",
                    rationale="test",
                ),
            ],
        )
        result = await tools.persist_growth_opportunities(inp)

        from app.agents.contracts import PersistGrowthOpportunitiesOutput

        assert isinstance(result, PersistGrowthOpportunitiesOutput)
        assert result.model_config.get("frozen") is True


# ===========================================================================
# Tool 7: persist_scores
# ===========================================================================


class TestPersistScores:
    """AC-07: persist_scores writes Growth Quality and Future Optionality
    dimension scores as CompanyScore records in thesis.company_score."""

    def _setup_session_for_scores(self) -> tuple[AsyncMock, list[Any]]:
        """Return a session mock that tracks added CompanyScore records."""
        session = _make_session_mock()
        added_records: list[Any] = []

        gq_id = uuid.uuid4()
        fo_id = uuid.uuid4()
        refresh_ids = iter([gq_id, fo_id])

        def track_add(record: Any) -> None:
            added_records.append(record)

        async def mock_refresh(record: Any) -> None:
            record.id = next(refresh_ids)

        session.add = track_add
        session.refresh = mock_refresh

        # Default: no existing score (idempotency check returns None)
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=no_existing)

        return session, added_records

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=65,
            future_optionality_score=42,
            growth_quality_components=[
                GrowthScoreComponent(
                    component_name="Revenue CAGR",
                    score=70,
                    rationale="Strong 3-year CAGR",
                ),
            ],
            future_optionality_components=[
                GrowthScoreComponent(
                    component_name="Opportunity Count",
                    score=50,
                    rationale="3 identified opportunities",
                ),
            ],
        )
        result = await tools.persist_scores(inp)

        assert result.growth_quality_score_id is not None
        assert result.future_optionality_score_id is not None
        assert result.growth_quality_score_id != result.future_optionality_score_id
        assert len(added) == 2

    @pytest.mark.asyncio
    async def test_two_company_score_records_created(self) -> None:
        """Exactly 2 CompanyScore records — one for GQ, one for FO."""
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        await tools.persist_scores(inp)

        from app.models.thesis import CompanyScore

        assert len(added) == 2
        assert all(isinstance(r, CompanyScore) for r in added)

        dimensions = {r.dimension for r in added}
        assert dimensions == {ScoreDimension.GROWTH_QUALITY, ScoreDimension.FUTURE_OPTIONALITY}

    @pytest.mark.asyncio
    async def test_correct_company_and_run_associations(self) -> None:
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        await tools.persist_scores(inp)

        for record in added:
            assert record.company_id == COMPANY_ID
            assert record.research_run_id == RUN_ID

    @pytest.mark.asyncio
    async def test_correct_score_values(self) -> None:
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=65,
            future_optionality_score=42,
        )
        await tools.persist_scores(inp)

        gq = next(r for r in added if r.dimension == ScoreDimension.GROWTH_QUALITY)
        fo = next(r for r in added if r.dimension == ScoreDimension.FUTURE_OPTIONALITY)
        assert gq.score == 65
        assert fo.score == 42

    @pytest.mark.asyncio
    async def test_components_in_sub_scores(self) -> None:
        """Component scores stored in CompanyScore.sub_scores JSONB."""
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=65,
            future_optionality_score=42,
            growth_quality_components=[
                GrowthScoreComponent(component_name="Revenue CAGR", score=70, rationale="Good"),
                GrowthScoreComponent(component_name="Profit CAGR", score=60, rationale="OK"),
            ],
        )
        await tools.persist_scores(inp)

        gq = next(r for r in added if r.dimension == ScoreDimension.GROWTH_QUALITY)
        assert gq.sub_scores is not None
        assert len(gq.sub_scores["components"]) == 2
        assert gq.sub_scores["components"][0]["name"] == "Revenue CAGR"
        assert gq.sub_scores["components"][0]["score"] == 70
        assert gq.sub_scores["components"][0]["rationale"] == "Good"

    @pytest.mark.asyncio
    async def test_explanation_from_rationale(self) -> None:
        """CompanyScore.explanation built from component rationales."""
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=65,
            future_optionality_score=42,
            growth_quality_components=[
                GrowthScoreComponent(component_name="Revenue CAGR", score=70, rationale="Strong"),
            ],
            future_optionality_components=[
                GrowthScoreComponent(component_name="Opportunity Count", score=50, rationale="3 identified"),
            ],
        )
        await tools.persist_scores(inp)

        gq = next(r for r in added if r.dimension == ScoreDimension.GROWTH_QUALITY)
        fo = next(r for r in added if r.dimension == ScoreDimension.FUTURE_OPTIONALITY)
        assert "Revenue CAGR" in gq.explanation
        assert "Strong" in gq.explanation
        assert "Opportunity Count" in fo.explanation

    @pytest.mark.asyncio
    async def test_explanation_fallback_without_components(self) -> None:
        """When no components are provided, a default explanation is generated."""
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        await tools.persist_scores(inp)

        gq = next(r for r in added if r.dimension == ScoreDimension.GROWTH_QUALITY)
        fo = next(r for r in added if r.dimension == ScoreDimension.FUTURE_OPTIONALITY)
        assert gq.explanation != ""
        assert fo.explanation != ""
        assert "50" in gq.explanation
        assert "30" in fo.explanation

    @pytest.mark.asyncio
    async def test_score_bounds_zero_and_hundred(self) -> None:
        """Boundary values 0 and 100 are accepted by contract and persisted."""
        session, added = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=0,
            future_optionality_score=100,
        )
        await tools.persist_scores(inp)

        gq = next(r for r in added if r.dimension == ScoreDimension.GROWTH_QUALITY)
        fo = next(r for r in added if r.dimension == ScoreDimension.FUTURE_OPTIONALITY)
        assert gq.score == 0
        assert fo.score == 100

    def test_score_out_of_range_rejected_by_contract(self) -> None:
        """Contract Field(ge=0, le=100) rejects out-of-range scores."""
        with pytest.raises(ValueError):
            PersistGrowthScoresInput(
                company_id=COMPANY_ID,
                research_run_id=RUN_ID,
                growth_quality_score=-1,
                future_optionality_score=50,
            )
        with pytest.raises(ValueError):
            PersistGrowthScoresInput(
                company_id=COMPANY_ID,
                research_run_id=RUN_ID,
                growth_quality_score=50,
                future_optionality_score=101,
            )

    @pytest.mark.asyncio
    async def test_idempotency_existing_scores_returned(self) -> None:
        """When scores already exist for (company, run, dimension), return existing IDs."""
        session = _make_session_mock()
        existing_gq_id = uuid.uuid4()
        existing_fo_id = uuid.uuid4()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.side_effect = [existing_gq_id, existing_fo_id]
        session.execute = AsyncMock(return_value=existing_result)

        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        result = await tools.persist_scores(inp)

        assert result.growth_quality_score_id == existing_gq_id
        assert result.future_optionality_score_id == existing_fo_id
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_dimension_not_persisted_when_first_fails(self) -> None:
        """If the first score write raises, the second is not attempted."""
        session = _make_session_mock()

        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=no_existing)
        session.flush = AsyncMock(side_effect=Exception("DB write failed"))
        session.add = MagicMock()

        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        with pytest.raises(Exception, match="DB write failed"):
            await tools.persist_scores(inp)

        # Only 1 add call — the second dimension was not attempted
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_no_research_finding_records_created(self) -> None:
        """Scores must use CompanyScore, not ResearchFinding via record_findings."""
        session, added = self._setup_session_for_scores()
        run_service = _make_run_service_mock()
        tools = _make_tools(session=session, run_service=run_service)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        await tools.persist_scores(inp)

        run_service.record_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_output_contract_shape(self) -> None:
        session, _ = self._setup_session_for_scores()
        tools = _make_tools(session=session)
        inp = PersistGrowthScoresInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            growth_quality_score=50,
            future_optionality_score=30,
        )
        result = await tools.persist_scores(inp)

        from app.agents.contracts import PersistGrowthScoresOutput

        assert isinstance(result, PersistGrowthScoresOutput)
        assert result.model_config.get("frozen") is True


# ===========================================================================
# Tool 8: create_research_document (internal helper)
# ===========================================================================


class TestCreateResearchDocument:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        session = _make_session_mock()
        doc_id = uuid.uuid4()

        async def mock_refresh(record: Any) -> None:
            record.id = doc_id

        session.refresh = mock_refresh

        tools = _make_tools(session=session)
        candidate = SourceCandidate(
            source_id="FIL001",
            source_type=DocumentType.ANNUAL_REPORT,
            provider="corporate_filings",
            title="Annual Report FY25",
            publication_date=date(2025, 6, 1),
            source_tier=SourceTier.TIER_1,
            url="https://nse.example.com/filing/001",
        )
        result = await tools.create_research_document(COMPANY_ID, candidate, "abc123hash")

        assert result == doc_id
        session.add.assert_called_once()

        added_doc = session.add.call_args[0][0]
        assert added_doc.company_id == COMPANY_ID
        assert added_doc.document_type == DocumentType.ANNUAL_REPORT
        assert added_doc.source_tier == SourceTier.TIER_1
        assert added_doc.content_hash == "abc123hash"
        assert added_doc.source_url == "https://nse.example.com/filing/001"

    @pytest.mark.asyncio
    async def test_preserves_publication_date(self) -> None:
        session = _make_session_mock()

        async def mock_refresh(record: Any) -> None:
            record.id = uuid.uuid4()

        session.refresh = mock_refresh

        tools = _make_tools(session=session)
        pub_date = date(2025, 3, 15)
        candidate = SourceCandidate(
            source_id="news_001",
            source_type=DocumentType.NEWS,
            provider="news",
            title="Growth news",
            publication_date=pub_date,
            source_tier=SourceTier.TIER_3,
            url="https://news.example.com/growth",
        )
        await tools.create_research_document(COMPANY_ID, candidate, "hash123")

        added_doc = session.add.call_args[0][0]
        assert added_doc.document_date == pub_date


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestClassifyGrowthSource:
    def test_annual_report(self) -> None:
        assert _classify_growth_source("Annual Report 2025", "https://example.com") == DocumentType.ANNUAL_REPORT

    def test_yearly_report(self) -> None:
        assert _classify_growth_source("Yearly Report", "https://example.com") == DocumentType.ANNUAL_REPORT

    def test_sebi_filing(self) -> None:
        assert _classify_growth_source("Some Filing", "https://sebi.gov.in/filings") == DocumentType.FILING

    def test_nse_filing(self) -> None:
        assert _classify_growth_source("NSE Disclosure", "https://nse.example.com") == DocumentType.FILING

    def test_investor_presentation(self) -> None:
        assert (
            _classify_growth_source("Investor Presentation Q3", "https://example.com")
            == DocumentType.INVESTOR_PRESENTATION
        )

    def test_research_report(self) -> None:
        assert _classify_growth_source("Industry Report on IT", "https://example.com") == DocumentType.RESEARCH_REPORT

    def test_news_article(self) -> None:
        assert _classify_growth_source("News: Infosys expansion", "https://example.com") == DocumentType.NEWS

    def test_expansion_keyword(self) -> None:
        assert _classify_growth_source("Infosys expansion in Europe", "https://example.com") == DocumentType.NEWS

    def test_partnership_keyword(self) -> None:
        assert _classify_growth_source("New partnership announced", "https://example.com") == DocumentType.NEWS

    def test_fallback(self) -> None:
        assert _classify_growth_source("Generic page", "https://example.com") == DocumentType.RESEARCH_REPORT


class TestTierFromUrl:
    def test_nse_tier1(self) -> None:
        assert _tier_from_url("https://www.nseindia.com/listing") == SourceTier.TIER_1

    def test_bse_tier1(self) -> None:
        assert _tier_from_url("https://www.bseindia.com/stock") == SourceTier.TIER_1

    def test_sebi_tier1(self) -> None:
        assert _tier_from_url("https://www.sebi.gov.in/order") == SourceTier.TIER_1

    def test_ibef_tier2(self) -> None:
        assert _tier_from_url("https://www.ibef.org/industry") == SourceTier.TIER_2

    def test_nasscom_tier2(self) -> None:
        assert _tier_from_url("https://nasscom.in/report") == SourceTier.TIER_2

    def test_ficci_tier2(self) -> None:
        assert _tier_from_url("https://ficci.in/sector") == SourceTier.TIER_2

    def test_generic_tier3(self) -> None:
        assert _tier_from_url("https://example.com/article") == SourceTier.TIER_3


class TestMapFilingType:
    def test_annual_report(self) -> None:
        assert _map_filing_type("ANNUAL_REPORT") == DocumentType.ANNUAL_REPORT

    def test_quarterly_result(self) -> None:
        assert _map_filing_type("QUARTERLY_RESULT") == DocumentType.QUARTERLY_RESULT

    def test_investor_presentation(self) -> None:
        assert _map_filing_type("INVESTOR_PRESENTATION") == DocumentType.INVESTOR_PRESENTATION

    def test_unknown_type(self) -> None:
        assert _map_filing_type("UNKNOWN_TYPE") == DocumentType.FILING

    def test_case_insensitive(self) -> None:
        assert _map_filing_type("annual_report") == DocumentType.ANNUAL_REPORT


# ===========================================================================
# Constructor and DI
# ===========================================================================


class TestFutureGrowthToolsConstructor:
    """AC-03: 8 tools implemented with typed I/O contracts."""

    def test_constructor_accepts_required_providers(self) -> None:
        tools = _make_tools()
        assert isinstance(tools, FutureGrowthTools)

    def test_all_tool_methods_exist(self) -> None:
        tools = _make_tools()
        assert callable(getattr(tools, "load_company_context", None))
        assert callable(getattr(tools, "discover_growth_sources", None))
        assert callable(getattr(tools, "retrieve_document", None))
        assert callable(getattr(tools, "persist_evidence", None))
        assert callable(getattr(tools, "persist_findings", None))
        assert callable(getattr(tools, "persist_growth_opportunities", None))
        assert callable(getattr(tools, "persist_scores", None))
        assert callable(getattr(tools, "create_research_document", None))

    def test_tool_count(self) -> None:
        """Architecture §21 defines exactly 8 tools."""
        tools = _make_tools()
        public_methods = [m for m in dir(tools) if not m.startswith("_") and callable(getattr(tools, m))]
        assert len(public_methods) == 8


# ===========================================================================
# Provenance and observation-date integrity
# ===========================================================================


class TestProvenanceIntegrity:
    """Source IDs, URLs, publication dates, and evidence references preserved."""

    @pytest.mark.asyncio
    async def test_source_candidate_preserves_metadata(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Growth article",
                    url="https://specific-source.com/article/123",
                    snippet="Content about growth",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Test Company",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        assert len(result.sources) >= 1
        source = result.sources[0]
        assert source.url == "https://specific-source.com/article/123"
        assert source.source_id == "https://specific-source.com/article/123"
        assert source.provider == "search"

    @pytest.mark.asyncio
    async def test_filing_provenance_preserved(self) -> None:
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="UNIQUE_FILING_ID_789",
                    symbol="INFY",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Annual Report FY25",
                    filing_date=date(2025, 4, 30),
                    url="https://nse.example.com/filings/789",
                ),
            ]
        )
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Infosys",
            nse_symbol="INFY",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_growth_sources(inp)

        filing_sources = [s for s in result.sources if s.provider == "corporate_filings"]
        assert len(filing_sources) == 1
        assert filing_sources[0].source_id == "UNIQUE_FILING_ID_789"
        assert filing_sources[0].publication_date == date(2025, 4, 30)
        assert filing_sources[0].url == "https://nse.example.com/filings/789"
        assert filing_sources[0].source_tier == SourceTier.TIER_1

    @pytest.mark.asyncio
    async def test_observation_date_passed_to_news(self) -> None:
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Test",
            observation_date=OBSERVATION_DATE,
        )
        await tools.discover_growth_sources(inp)

        news.search_news.assert_called_once()
        call_kwargs = news.search_news.call_args
        assert call_kwargs.kwargs.get("end") == OBSERVATION_DATE or call_kwargs[1].get("end") == OBSERVATION_DATE

    @pytest.mark.asyncio
    async def test_observation_date_passed_to_filings(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news, corporate_filings=corporate_filings)
        inp = DiscoverGrowthSourcesInput(
            company_name="Test",
            nse_symbol="TEST",
            observation_date=OBSERVATION_DATE,
        )
        await tools.discover_growth_sources(inp)

        corporate_filings.get_filings.assert_called_once()
        call_kwargs = corporate_filings.get_filings.call_args
        assert call_kwargs.kwargs.get("end") == OBSERVATION_DATE or call_kwargs[1].get("end") == OBSERVATION_DATE
