"""Unit tests for CompetitiveMoatTools (Phase 10.2).

Tests cover the 7 agent-facing tool methods:
  1. load_company_context
  2. discover_moat_sources
  3. retrieve_document
  4. get_peer_data
  5. persist_evidence
  6. persist_findings
  7. persist_moat_assessments

Plus the internal helper ``create_research_document`` (NOT agent-facing),
and helper functions _classify_moat_source, _tier_from_url, _map_filing_type.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.competitive_moat.exceptions import CompanyNotFoundForMoatError
from app.agents.competitive_moat.tools import (
    CompetitiveMoatTools,
    _classify_moat_source,
    _map_filing_type,
    _tier_from_url,
)
from app.agents.contracts import (
    MOAT_AGENT_NAME,
    MOAT_FINDING_CATEGORIES,
    DiscoverMoatSourcesInput,
    EvidenceItem,
    FindingItem,
    GetPeerDataInput,
    LoadContextInput,
    MoatAssessmentItem,
    PeerCompanySummary,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistMoatAssessmentsInput,
    RetrieveDocumentInput,
    SourceCandidate,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    MoatStrength,
    MoatType,
    ResearchRunStatus,
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
        name: str = "Reliance Industries",
        nse_symbol: str | None = "RELIANCE",
        bse_code: str | None = "500325",
        isin: str = "INE002A01018",
        market_cap: Decimal | None = Decimal("16000000.0000"),
        is_active: bool = True,
        industry_id: uuid.UUID | None = None,
        industry: Any = None,
        sector: Any = None,
        sector_id: uuid.UUID | None = None,
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
        self.sector_id = sector_id


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
        observation_date: date | None = date(2024, 12, 31),
    ) -> None:
        self.id = id or uuid.uuid4()
        self.status = status
        self.observation_date = observation_date


class MockFinding:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        category: str = "business_model",
        finding_type: str = FindingType.FACT,
        content: str = "Test finding content",
        confidence: str = ConfidenceLevel.HIGH,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.category = category
        self.finding_type = finding_type
        self.content = content
        self.confidence = confidence


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
    search: AsyncMock | None = None,
    news: AsyncMock | None = None,
    corporate_filings: AsyncMock | None = None,
) -> CompetitiveMoatTools:
    return CompetitiveMoatTools(
        session=session or AsyncMock(),
        run_service=run_service or MockRunService(),
        search=search or AsyncMock(),
        news=news or AsyncMock(),
        corporate_filings=corporate_filings or AsyncMock(),
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

        inp = LoadContextInput(
            company_id=uuid.uuid4(),
            industry_id=None,
            observation_date=date(2024, 12, 31),
        )
        with pytest.raises(CompanyNotFoundForMoatError):
            await tools.load_company_context(inp)

    @pytest.mark.asyncio
    async def test_no_prior_research(self) -> None:
        industry = MockIndustry()
        company = MockCompany(industry=industry, industry_id=industry.id)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)
        run_service = MockRunService()
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadContextInput(
            company_id=company.id,
            industry_id=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.company_id == company.id
        assert result.company_name == "Reliance Industries"
        assert result.nse_symbol == "RELIANCE"
        assert result.industry_id == industry.id
        assert result.industry_name == "Oil & Gas"
        assert result.company_findings == []
        assert result.industry_findings == []
        assert result.has_company_research is False
        assert result.has_industry_research is False

    @pytest.mark.asyncio
    async def test_with_prior_company_research(self) -> None:
        company = MockCompany(industry=None, industry_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        run = MockResearchRun(status=ResearchRunStatus.COMPLETED)
        findings = [
            MockFinding(category="business_model"),
            MockFinding(category="revenue_breakdown"),
        ]

        run_service = MockRunService()
        run_service.get_runs_for_company = AsyncMock(return_value=[run])
        run_service.get_findings = AsyncMock(return_value=findings)
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadContextInput(
            company_id=company.id,
            industry_id=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.has_company_research is True
        assert len(result.company_findings) == 2
        assert result.company_findings[0].category == "business_model"

    @pytest.mark.asyncio
    async def test_with_prior_industry_research(self) -> None:
        industry_id = uuid.uuid4()
        industry = MockIndustry(id=industry_id)
        company = MockCompany(industry=industry, industry_id=industry_id)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        company_run = MockResearchRun(status=ResearchRunStatus.FAILED)
        industry_run = MockResearchRun(status=ResearchRunStatus.COMPLETED)
        industry_findings = [MockFinding(category="market_size")]

        run_service = MockRunService()
        run_service.get_runs_for_company = AsyncMock(return_value=[company_run])
        run_service.get_runs_for_industry = AsyncMock(return_value=[industry_run])
        run_service.get_findings = AsyncMock(return_value=industry_findings)
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadContextInput(
            company_id=company.id,
            industry_id=industry_id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.has_company_research is False
        assert result.has_industry_research is True
        assert len(result.industry_findings) == 1

    @pytest.mark.asyncio
    async def test_uses_input_industry_id_over_company(self) -> None:
        company_industry_id = uuid.uuid4()
        input_industry_id = uuid.uuid4()
        industry = MockIndustry(id=company_industry_id)
        company = MockCompany(industry=industry, industry_id=company_industry_id)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)
        run_service = MockRunService()
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadContextInput(
            company_id=company.id,
            industry_id=input_industry_id,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.industry_id == input_industry_id

    @pytest.mark.asyncio
    async def test_partial_run_counts_as_prior_research(self) -> None:
        company = MockCompany(industry=None, industry_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=company)

        run = MockResearchRun(status=ResearchRunStatus.PARTIAL)
        findings = [MockFinding()]

        run_service = MockRunService()
        run_service.get_runs_for_company = AsyncMock(return_value=[run])
        run_service.get_findings = AsyncMock(return_value=findings)
        tools = _build_tools(session=session, run_service=run_service)

        inp = LoadContextInput(
            company_id=company.id,
            industry_id=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.load_company_context(inp)

        assert result.has_company_research is True
        assert len(result.company_findings) == 1


# ---------------------------------------------------------------------------
# Tool 2: discover_moat_sources
# ---------------------------------------------------------------------------


class TestDiscoverMoatSources:
    @pytest.mark.asyncio
    async def test_happy_path_all_providers(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Reliance competitive advantage analysis",
                    url="https://example.com/reliance-moat",
                    snippet="Analysis of RIL moat",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Reliance strengthens market position",
                    url="https://news.example.com/reliance-position",
                    source="Economic Times",
                    published_at=datetime(2024, 6, 1, tzinfo=UTC),
                    summary="Strong position",
                    symbols=[],
                ),
            ]
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL001",
                    symbol="RELIANCE",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Reliance Annual Report 2024",
                    filing_date=date(2024, 7, 15),
                    url="https://nseindia.com/filing/001",
                ),
            ]
        )
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Reliance Industries",
            nse_symbol="RELIANCE",
            industry_name="Oil & Gas",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)

        assert len(result.candidates) >= 3
        providers = {c.provider for c in result.candidates}
        assert "search" in providers
        assert "news" in providers
        assert "corporate_filings" in providers

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Same report",
                    url="https://example.com/same-url",
                    snippet="Snippet",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Same article",
                    url="https://example.com/same-url",
                    source="Source",
                    published_at=datetime(2024, 6, 1, tzinfo=UTC),
                    summary="Summary",
                    symbols=[],
                ),
            ]
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test Co",
            nse_symbol="TEST",
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)

        urls = [c.url for c in result.candidates]
        assert urls.count("https://example.com/same-url") == 1

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title=f"Report {i}",
                    url=f"https://example.com/report-{i}",
                    snippet=f"Snippet {i}",
                )
                for i in range(20)
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
            limit=5,
        )
        result = await tools.discover_moat_sources(inp)
        assert len(result.candidates) <= 5

    @pytest.mark.asyncio
    async def test_search_provider_failure_graceful(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            side_effect=ProviderError(
                provider="search",
                message="Search unavailable",
            )
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="News article",
                    url="https://news.example.com/article",
                    source="Source",
                    published_at=datetime(2024, 6, 1, tzinfo=UTC),
                    summary="Summary",
                    symbols=[],
                ),
            ]
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)
        assert len(result.candidates) >= 1

    @pytest.mark.asyncio
    async def test_news_provider_failure_graceful(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Report",
                    url="https://example.com/report",
                    snippet="Snippet",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            side_effect=ProviderError(
                provider="news",
                message="News unavailable",
            )
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol="TEST",
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)
        assert len(result.candidates) >= 1

    @pytest.mark.asyncio
    async def test_corporate_filings_failure_graceful(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            side_effect=ProviderError(
                provider="corporate_filings",
                message="Filings unavailable",
            )
        )
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol="TEST",
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)
        assert result.candidates == []

    @pytest.mark.asyncio
    async def test_temporal_filtering_news(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Future article",
                    url="https://news.example.com/future",
                    source="Source",
                    published_at=datetime(2025, 6, 1, tzinfo=UTC),
                    summary="Summary",
                    symbols=[],
                ),
            ]
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)
        future_urls = [c.url for c in result.candidates if c.url == "https://news.example.com/future"]
        assert len(future_urls) == 0

    @pytest.mark.asyncio
    async def test_temporal_filtering_filings(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL_FUTURE",
                    symbol="TEST",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Future Report",
                    filing_date=date(2025, 3, 1),
                    url="https://nseindia.com/future",
                ),
            ]
        )
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol="TEST",
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)
        assert all(c.source_id != "FIL_FUTURE" for c in result.candidates)

    @pytest.mark.asyncio
    async def test_no_filings_without_nse_symbol(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        await tools.discover_moat_sources(inp)

        corporate_filings.get_filings.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_includes_industry_query_when_present(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Reliance",
            nse_symbol=None,
            industry_name="Oil & Gas",
            observation_date=date(2024, 12, 31),
        )
        await tools.discover_moat_sources(inp)

        assert search.search.await_count == 3

    @pytest.mark.asyncio
    async def test_two_queries_without_industry(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Reliance",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        await tools.discover_moat_sources(inp)

        assert search.search.await_count == 2

    @pytest.mark.asyncio
    async def test_filters_by_document_type(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Research report on moats",
                    url="https://example.com/report",
                    snippet="Report",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="News",
                    url="https://news.example.com/news",
                    source="Source",
                    published_at=datetime(2024, 6, 1, tzinfo=UTC),
                    summary="Summary",
                    symbols=[],
                ),
            ]
        )
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
            document_types=[DocumentType.NEWS],
        )
        result = await tools.discover_moat_sources(inp)
        for c in result.candidates:
            assert c.source_type == DocumentType.NEWS

    @pytest.mark.asyncio
    async def test_search_results_have_null_publication_date(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Moat analysis report",
                    url="https://example.com/moat",
                    snippet="Moat report",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(return_value=[])
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol=None,
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)

        for c in result.candidates:
            if c.provider == "search":
                assert c.publication_date is None

    @pytest.mark.asyncio
    async def test_filings_get_tier_1(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        corporate_filings = AsyncMock()
        corporate_filings.get_filings = AsyncMock(
            return_value=[
                Filing(
                    filing_id="FIL001",
                    symbol="TEST",
                    exchange="NSE",
                    filing_type="ANNUAL_REPORT",
                    title="Annual Report",
                    filing_date=date(2024, 7, 15),
                    url="https://nseindia.com/filing/001",
                ),
            ]
        )
        tools = _build_tools(
            search=search,
            news=news,
            corporate_filings=corporate_filings,
        )

        inp = DiscoverMoatSourcesInput(
            company_name="Test",
            nse_symbol="TEST",
            industry_name=None,
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_moat_sources(inp)

        filing_candidates = [c for c in result.candidates if c.provider == "corporate_filings"]
        assert len(filing_candidates) == 1
        assert filing_candidates[0].source_tier == SourceTier.TIER_1


# ---------------------------------------------------------------------------
# Tool 3: retrieve_document
# ---------------------------------------------------------------------------


class TestRetrieveDocument:
    @pytest.mark.asyncio
    async def test_corporate_filings_provider(self) -> None:
        corporate_filings = AsyncMock()
        corporate_filings.get_filing_document = AsyncMock(
            return_value=FilingDocument(
                filing_id="FIL001",
                content="Annual report content here",
                content_type="text/plain",
            )
        )
        tools = _build_tools(corporate_filings=corporate_filings)

        inp = RetrieveDocumentInput(
            filing_id="FIL001",
            provider="corporate_filings",
        )
        result = await tools.retrieve_document(inp)

        assert result.content == "Annual report content here"
        assert result.content_type == "text/plain"
        assert result.filing_id == "FIL001"
        expected_hash = hashlib.sha256(b"Annual report content here").hexdigest()
        assert result.content_hash == expected_hash

    @pytest.mark.asyncio
    async def test_search_provider_fallback(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Result",
                    url="https://example.com/doc",
                    snippet="Search snippet content",
                ),
            ]
        )
        tools = _build_tools(search=search)

        inp = RetrieveDocumentInput(
            filing_id="https://example.com/doc",
            provider="search",
        )
        result = await tools.retrieve_document(inp)

        assert result.content == "Search snippet content"
        assert result.content_type == "text/snippet"
        expected_hash = hashlib.sha256(b"Search snippet content").hexdigest()
        assert result.content_hash == expected_hash

    @pytest.mark.asyncio
    async def test_no_provider_defaults_to_search(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Result",
                    url="https://example.com/doc",
                    snippet="Default search snippet",
                ),
            ]
        )
        tools = _build_tools(search=search)

        inp = RetrieveDocumentInput(filing_id="https://example.com/doc")
        result = await tools.retrieve_document(inp)

        assert result.content == "Default search snippet"
        assert result.content_type == "text/snippet"

    @pytest.mark.asyncio
    async def test_search_no_results_returns_empty(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        tools = _build_tools(search=search)

        inp = RetrieveDocumentInput(filing_id="https://example.com/missing")
        result = await tools.retrieve_document(inp)

        assert result.content == ""
        assert result.content_hash == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# Tool 4: get_peer_data
# ---------------------------------------------------------------------------


class TestGetPeerData:
    @pytest.mark.asyncio
    async def test_returns_peers_from_same_industry(self) -> None:
        company_id = uuid.uuid4()
        industry_id = uuid.uuid4()
        peer1 = MockCompany(
            name="Peer Company 1",
            nse_symbol="PEER1",
            market_cap=Decimal("5000000.0000"),
        )
        peer2 = MockCompany(
            name="Peer Company 2",
            nse_symbol="PEER2",
            market_cap=Decimal("3000000.0000"),
        )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [peer1, peer2]
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetPeerDataInput(
            company_id=company_id,
            industry_id=industry_id,
        )
        result = await tools.get_peer_data(inp)

        assert len(result.peers) == 2
        assert result.peers[0].name == "Peer Company 1"
        assert result.peers[1].name == "Peer Company 2"

    @pytest.mark.asyncio
    async def test_empty_peers(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetPeerDataInput(
            company_id=uuid.uuid4(),
            industry_id=uuid.uuid4(),
        )
        result = await tools.get_peer_data(inp)

        assert result.peers == []

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MockCompany(name=f"Peer {i}") for i in range(3)]
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetPeerDataInput(
            company_id=uuid.uuid4(),
            industry_id=uuid.uuid4(),
            limit=3,
        )
        result = await tools.get_peer_data(inp)
        assert len(result.peers) == 3

    @pytest.mark.asyncio
    async def test_peer_summary_fields(self) -> None:
        peer = MockCompany(
            name="InfoEdge",
            nse_symbol="NAUKRI",
            market_cap=Decimal("80000.5000"),
        )
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [peer]
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetPeerDataInput(
            company_id=uuid.uuid4(),
            industry_id=uuid.uuid4(),
        )
        result = await tools.get_peer_data(inp)

        assert len(result.peers) == 1
        assert result.peers[0].company_id == peer.id
        assert result.peers[0].name == "InfoEdge"
        assert result.peers[0].nse_symbol == "NAUKRI"
        assert result.peers[0].market_cap == Decimal("80000.5000")


# ---------------------------------------------------------------------------
# Tool 5: persist_evidence
# ---------------------------------------------------------------------------


class TestPersistEvidence:
    @pytest.mark.asyncio
    async def test_uses_moat_agent_name(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="Company has strong brand recognition in India",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 1
        assert len(created_records) == 1
        assert created_records[0].extracted_by == MOAT_AGENT_NAME

    @pytest.mark.asyncio
    async def test_multiple_evidences(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="Claim 1",
                    confidence=ConfidenceLevel.HIGH,
                ),
                EvidenceItem(
                    evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                    claim="Claim 2",
                    context="Context for claim 2",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    evidence_type=EvidenceType.ANALYST_OPINION,
                    claim="Claim 3",
                    page_or_section="Section 5",
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 3
        for record in created_records:
            assert record.extracted_by == MOAT_AGENT_NAME


# ---------------------------------------------------------------------------
# Tool 6: persist_findings
# ---------------------------------------------------------------------------


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_valid_moat_categories_accepted(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=MOAT_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="brand_moat",
                    content="Strong brand moat identified",
                    confidence=ConfidenceLevel.HIGH,
                ),
                FindingItem(
                    agent_name=MOAT_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="moat_durability",
                    content="Moat expected to persist for 10+ years",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 2
        assert result.rejected == []
        run_service.record_findings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_moat_categories_rejected(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=MOAT_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="company_identity",
                    content="This is a company research category",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert result.finding_ids == []
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 0
        assert "Invalid category" in result.rejected[0].reason

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid(self) -> None:
        run_service = MockRunService()
        run_service.record_findings = AsyncMock(
            return_value=[MockPersistedFinding()],
        )
        tools = _build_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=MOAT_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="network_effect_moat",
                    content="Valid moat finding",
                    confidence=ConfidenceLevel.HIGH,
                ),
                FindingItem(
                    agent_name=MOAT_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="market_size",
                    content="Industry category, not moat",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 1

    @pytest.mark.asyncio
    async def test_all_19_moat_categories_accepted(self) -> None:
        run_service = MockRunService()
        findings_returned = [MockPersistedFinding() for _ in MOAT_FINDING_CATEGORIES]
        run_service.record_findings = AsyncMock(return_value=findings_returned)
        tools = _build_tools(run_service=run_service)

        findings = [
            FindingItem(
                agent_name=MOAT_AGENT_NAME,
                finding_type=FindingType.FACT,
                category=cat,
                content=f"Finding for {cat}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            for cat in sorted(MOAT_FINDING_CATEGORIES)
        ]
        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=findings,
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 19
        assert result.rejected == []


# ---------------------------------------------------------------------------
# Tool 7: persist_moat_assessments
# ---------------------------------------------------------------------------


class TestPersistMoatAssessments:
    @pytest.mark.asyncio
    async def test_single_assessment_no_evidence(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistMoatAssessmentsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.BRAND,
                    strength=MoatStrength.WIDE,
                    durability_years=15,
                    confidence=ConfidenceLevel.HIGH,
                    explanation="Strong brand with decades of trust",
                ),
            ],
        )
        result = await tools.persist_moat_assessments(inp)

        assert len(result.assessment_ids) == 1
        assert len(created_records) == 1
        assert created_records[0].moat_type == MoatType.BRAND
        assert created_records[0].strength == MoatStrength.WIDE
        assert created_records[0].durability_years == 15
        assert created_records[0].confidence == ConfidenceLevel.HIGH

    @pytest.mark.asyncio
    async def test_assessment_with_evidence_junction(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        tools = _build_tools(session=session)

        ev_id_1 = uuid.uuid4()
        ev_id_2 = uuid.uuid4()

        inp = PersistMoatAssessmentsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.NETWORK_EFFECT,
                    strength=MoatStrength.MODERATE,
                    confidence=ConfidenceLevel.MEDIUM,
                    evidence_ids=[ev_id_1, ev_id_2],
                ),
            ],
        )
        result = await tools.persist_moat_assessments(inp)

        assert len(result.assessment_ids) == 1
        assert session.execute.await_count >= 2

    @pytest.mark.asyncio
    async def test_multiple_assessments(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistMoatAssessmentsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.BRAND,
                    strength=MoatStrength.WIDE,
                    confidence=ConfidenceLevel.HIGH,
                ),
                MoatAssessmentItem(
                    moat_type=MoatType.COST_ADVANTAGE,
                    strength=MoatStrength.NARROW,
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                MoatAssessmentItem(
                    moat_type=MoatType.SCALE,
                    strength=MoatStrength.NONE,
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_moat_assessments(inp)

        assert len(result.assessment_ids) == 3
        moat_types = [r.moat_type for r in created_records]
        assert MoatType.BRAND in moat_types
        assert MoatType.COST_ADVANTAGE in moat_types
        assert MoatType.SCALE in moat_types

    @pytest.mark.asyncio
    async def test_preserves_threats_and_competitor_comparison(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        tools = _build_tools(session=session)

        threats: list[dict[str, object]] = [
            {
                "description": "New entrant with lower cost",
                "severity": "HIGH",
                "timeframe": "2-3 years",
            },
        ]
        competitor_comparison: dict[str, object] = {
            "TCS": "slightly weaker brand",
            "Wipro": "significantly weaker brand",
        }

        inp = PersistMoatAssessmentsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.BRAND,
                    strength=MoatStrength.WIDE,
                    confidence=ConfidenceLevel.HIGH,
                    threats=threats,
                    competitor_comparison=competitor_comparison,
                ),
            ],
        )
        result = await tools.persist_moat_assessments(inp)

        assert len(result.assessment_ids) == 1
        assert created_records[0].threats == threats
        assert created_records[0].competitor_comparison == competitor_comparison

    @pytest.mark.asyncio
    async def test_none_optional_fields(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        tools = _build_tools(session=session)

        inp = PersistMoatAssessmentsInput(
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            assessments=[
                MoatAssessmentItem(
                    moat_type=MoatType.IP,
                    strength=MoatStrength.NARROW,
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_moat_assessments(inp)

        assert len(result.assessment_ids) == 1
        assert created_records[0].durability_years is None
        assert created_records[0].threats is None
        assert created_records[0].competitor_comparison is None
        assert created_records[0].explanation is None


# ---------------------------------------------------------------------------
# Internal helper: create_research_document (NOT agent-facing)
# ---------------------------------------------------------------------------


class TestCreateResearchDocument:
    @pytest.mark.asyncio
    async def test_creates_with_company_id(self) -> None:
        session = AsyncMock()
        created_docs: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_docs.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        company_id = uuid.uuid4()
        candidate = SourceCandidate(
            source_id="FIL001",
            source_type=DocumentType.ANNUAL_REPORT,
            provider="corporate_filings",
            title="Annual Report 2024",
            publication_date=date(2024, 7, 15),
            source_tier=SourceTier.TIER_1,
            url="https://nseindia.com/filing/001",
        )
        doc_id = await tools.create_research_document(
            company_id,
            candidate,
            "abc123hash",
        )

        assert doc_id is not None
        assert len(created_docs) == 1
        assert created_docs[0].company_id == company_id
        assert created_docs[0].document_type == DocumentType.ANNUAL_REPORT
        assert created_docs[0].title == "Annual Report 2024"
        assert created_docs[0].source_tier == SourceTier.TIER_1
        assert created_docs[0].content_hash == "abc123hash"
        assert created_docs[0].source_name == "corporate_filings"
        assert created_docs[0].source_url == "https://nseindia.com/filing/001"

    @pytest.mark.asyncio
    async def test_handles_null_url(self) -> None:
        session = AsyncMock()
        created_docs: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_docs.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        candidate = SourceCandidate(
            source_id="src-no-url",
            source_type=DocumentType.RESEARCH_REPORT,
            provider="search",
            title="Report",
            source_tier=SourceTier.TIER_3,
        )
        doc_id = await tools.create_research_document(
            uuid.uuid4(),
            candidate,
            "hash456",
        )

        assert doc_id is not None
        assert created_docs[0].source_url is None


# ---------------------------------------------------------------------------
# Helper: _classify_moat_source
# ---------------------------------------------------------------------------


class TestClassifyMoatSource:
    def test_annual_report(self) -> None:
        assert _classify_moat_source("Annual Report 2024", "https://example.com/ar") == DocumentType.ANNUAL_REPORT

    def test_yearly_report(self) -> None:
        assert _classify_moat_source("Yearly Report Summary", "https://example.com/yr") == DocumentType.ANNUAL_REPORT

    def test_sebi_filing(self) -> None:
        assert _classify_moat_source("Market circular", "https://sebi.gov.in/circular") == DocumentType.FILING

    def test_nse_source(self) -> None:
        assert _classify_moat_source("Data", "https://www.nseindia.com/data") == DocumentType.FILING

    def test_investor_presentation(self) -> None:
        assert (
            _classify_moat_source(
                "Q3 Investor Presentation",
                "https://example.com/pres",
            )
            == DocumentType.INVESTOR_PRESENTATION
        )

    def test_investor_deck(self) -> None:
        assert (
            _classify_moat_source(
                "Reliance Investor Deck 2024",
                "https://example.com/deck",
            )
            == DocumentType.INVESTOR_PRESENTATION
        )

    def test_research_report(self) -> None:
        assert (
            _classify_moat_source(
                "Equity Report on Reliance",
                "https://example.com/report",
            )
            == DocumentType.RESEARCH_REPORT
        )

    def test_sector_report(self) -> None:
        assert (
            _classify_moat_source(
                "Oil & Gas Sector Report",
                "https://example.com/sector",
            )
            == DocumentType.RESEARCH_REPORT
        )

    def test_news(self) -> None:
        assert (
            _classify_moat_source(
                "Latest news on competitive landscape",
                "https://example.com/news",
            )
            == DocumentType.NEWS
        )

    def test_default_research_report(self) -> None:
        assert (
            _classify_moat_source("Some random document", "https://example.com/other") == DocumentType.RESEARCH_REPORT
        )


# ---------------------------------------------------------------------------
# Helper: _tier_from_url
# ---------------------------------------------------------------------------


class TestTierFromUrl:
    def test_sebi(self) -> None:
        assert _tier_from_url("https://sebi.gov.in/data") == SourceTier.TIER_1

    def test_rbi(self) -> None:
        assert _tier_from_url("https://rbi.org.in/scripts") == SourceTier.TIER_1

    def test_nse(self) -> None:
        assert _tier_from_url("https://nseindia.com/data") == SourceTier.TIER_1

    def test_bse(self) -> None:
        assert _tier_from_url("https://bseindia.com/data") == SourceTier.TIER_1

    def test_ibef(self) -> None:
        assert _tier_from_url("https://ibef.org/industry") == SourceTier.TIER_2

    def test_ficci(self) -> None:
        assert _tier_from_url("https://ficci.in/sector") == SourceTier.TIER_2

    def test_nasscom(self) -> None:
        assert _tier_from_url("https://nasscom.in/report") == SourceTier.TIER_2

    def test_cii(self) -> None:
        assert _tier_from_url("https://cii.in/sector") == SourceTier.TIER_2

    def test_generic(self) -> None:
        assert _tier_from_url("https://random-blog.com/article") == SourceTier.TIER_3


# ---------------------------------------------------------------------------
# Helper: _map_filing_type
# ---------------------------------------------------------------------------


class TestMapFilingType:
    def test_annual_report(self) -> None:
        assert _map_filing_type("ANNUAL_REPORT") == DocumentType.ANNUAL_REPORT

    def test_quarterly_result(self) -> None:
        assert _map_filing_type("QUARTERLY_RESULT") == DocumentType.QUARTERLY_RESULT

    def test_investor_presentation(self) -> None:
        assert _map_filing_type("INVESTOR_PRESENTATION") == DocumentType.INVESTOR_PRESENTATION

    def test_unknown_defaults_to_filing(self) -> None:
        assert _map_filing_type("SOME_UNKNOWN_TYPE") == DocumentType.FILING

    def test_case_insensitive(self) -> None:
        assert _map_filing_type("annual_report") == DocumentType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestToolsConstructor:
    def test_accepts_protocol_providers(self) -> None:
        tools = _build_tools()
        assert tools is not None
        assert tools._session is not None
        assert tools._run_service is not None
        assert tools._search is not None
        assert tools._news is not None
        assert tools._corporate_filings is not None

    def test_no_llm_dependency(self) -> None:
        tools = _build_tools()
        assert not hasattr(tools, "_llm")

    def test_no_macro_data_dependency(self) -> None:
        tools = _build_tools()
        assert not hasattr(tools, "_macro_data")

    def test_no_financial_data_dependency(self) -> None:
        tools = _build_tools()
        assert not hasattr(tools, "_financial_data")


# ---------------------------------------------------------------------------
# Tool inventory verification
# ---------------------------------------------------------------------------


class TestToolInventory:
    AGENT_FACING_TOOLS = [
        "load_company_context",
        "discover_moat_sources",
        "retrieve_document",
        "get_peer_data",
        "persist_evidence",
        "persist_findings",
        "persist_moat_assessments",
    ]

    def test_all_agent_facing_tools_exist(self) -> None:
        tools = _build_tools()
        for name in self.AGENT_FACING_TOOLS:
            assert hasattr(tools, name), f"Missing agent-facing tool: {name}"
            assert callable(getattr(tools, name))

    def test_create_research_document_is_internal_helper(self) -> None:
        tools = _build_tools()
        assert hasattr(tools, "create_research_document")
        assert callable(tools.create_research_document)

    def test_exactly_7_agent_facing_tools(self) -> None:
        assert len(self.AGENT_FACING_TOOLS) == 7


# ---------------------------------------------------------------------------
# CompanyNotFoundForMoatError
# ---------------------------------------------------------------------------


class TestCompanyNotFoundForMoatError:
    def test_message(self) -> None:
        err = CompanyNotFoundForMoatError("abc-123")
        assert "abc-123" in str(err)
        assert err.details is not None
        assert err.details["company_id"] == "abc-123"

    def test_is_agent_error(self) -> None:
        from app.agents.company_research.exceptions import AgentError

        err = CompanyNotFoundForMoatError("test-id")
        assert isinstance(err, AgentError)


# ---------------------------------------------------------------------------
# Contract schema validation — moat-specific contracts
# ---------------------------------------------------------------------------


class TestMoatContractValidation:
    def test_load_context_input_frozen(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        inp = LoadContextInput(
            company_id=uuid.uuid4(),
            industry_id=None,
            observation_date=date(2024, 1, 1),
        )
        with pytest.raises(PydanticValidationError):
            inp.company_id = uuid.uuid4()  # type: ignore[misc]

    def test_discover_moat_sources_limit_bounds(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            DiscoverMoatSourcesInput(
                company_name="Test",
                nse_symbol=None,
                industry_name=None,
                observation_date=date(2024, 1, 1),
                limit=0,
            )

        with pytest.raises(PydanticValidationError):
            DiscoverMoatSourcesInput(
                company_name="Test",
                nse_symbol=None,
                industry_name=None,
                observation_date=date(2024, 1, 1),
                limit=101,
            )

    def test_get_peer_data_input_limit_bounds(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            GetPeerDataInput(
                company_id=uuid.uuid4(),
                industry_id=uuid.uuid4(),
                limit=0,
            )

        with pytest.raises(PydanticValidationError):
            GetPeerDataInput(
                company_id=uuid.uuid4(),
                industry_id=uuid.uuid4(),
                limit=21,
            )

    def test_persist_moat_assessments_requires_at_least_one(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            PersistMoatAssessmentsInput(
                company_id=uuid.uuid4(),
                research_run_id=uuid.uuid4(),
                assessments=[],
            )

    def test_moat_assessment_item_frozen(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        item = MoatAssessmentItem(
            moat_type=MoatType.BRAND,
            strength=MoatStrength.WIDE,
            confidence=ConfidenceLevel.HIGH,
        )
        with pytest.raises(PydanticValidationError):
            item.strength = MoatStrength.NONE  # type: ignore[misc]

    def test_peer_company_summary_frozen(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        summary = PeerCompanySummary(
            company_id=uuid.uuid4(),
            name="Test Co",
        )
        with pytest.raises(PydanticValidationError):
            summary.name = "Modified"  # type: ignore[misc]
