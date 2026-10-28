"""Unit tests for MacroEconomicsTools (Phase 13.2).

Tests cover the 8 architecture-defined tool methods:
  1. load_macro_context
  2. discover_macro_sources
  3. retrieve_document
  4. create_research_document (internal helper)
  5. persist_evidence
  6. persist_findings
  7. persist_macro_indicators (NEW)
  8. compute_indicator_trends (NEW)

Plus helper functions _classify_macro_source, _tier_from_url.

Architecture reference: docs/architecture/phase-13-macro-economics-agent.md §21
Acceptance criteria: AC-03, AC-04, AC-05, AC-06, AC-07
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.contracts import (
    MACRO_AGENT_NAME,
    ComputeIndicatorTrendsInput,
    DiscoverMacroSourcesInput,
    EvidenceItem,
    FindingItem,
    LoadMacroContextInput,
    LoadMacroContextOutput,
    MacroIndicatorSnapshot,
    PersistEvidenceInput,
    PersistFindingsInput,
    PersistMacroIndicatorsInput,
    RetrieveDocumentInput,
    SourceCandidate,
)
from app.agents.macro_economics.exceptions import CompanyNotFoundForMacroError
from app.agents.macro_economics.tools import (
    MacroEconomicsTools,
    _classify_macro_source,
    _tier_from_url,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    ResearchRunStatus,
    SourceTier,
)
from app.providers.errors import ProviderError
from app.providers.types import (
    MacroDataPoint,
    MacroIndicatorInfo,
    MacroSeries,
    NewsArticle,
    SearchResult,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockCompany:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "HDFC Bank Limited",
        nse_symbol: str | None = "HDFCBANK",
        bse_code: str | None = "500180",
        isin: str = "INE040A01034",
        market_cap: Decimal | None = Decimal("12000000.0000"),
        is_active: bool = True,
        sector_id: uuid.UUID | None = None,
        sector: Any = None,
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
        self.sector_id = sector_id
        self.sector = sector
        self.industry_id = industry_id
        self.industry = industry


class MockClassification:
    def __init__(self, *, name: str = "Banking") -> None:
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
        category: str = "monetary_policy_assessment",
        finding_type: str = FindingType.AI_INFERENCE,
        content: str = "Test macro finding",
        confidence: str = ConfidenceLevel.MEDIUM,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.category = category
        self.finding_type = finding_type
        self.content = content
        self.confidence = confidence


class MockEvidence:
    def __init__(self, *, id: uuid.UUID | None = None) -> None:
        self.id = id or uuid.uuid4()


class MockPersistedFinding:
    def __init__(self, *, id: uuid.UUID | None = None) -> None:
        self.id = id or uuid.uuid4()


class MockMacroIndicator:
    def __init__(self, *, id: uuid.UUID | None = None) -> None:
        self.id = id or uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
EXECUTION_ID = uuid.uuid4()
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


def _make_macro_data_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.list_indicators = AsyncMock(
        return_value=[
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
        ]
    )
    mock.get_indicator = AsyncMock(
        side_effect=_default_get_indicator,
    )
    return mock


async def _default_get_indicator(
    indicator_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> MacroSeries:
    if indicator_id == "REPO_RATE":
        return MacroSeries(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            unit="PERCENTAGE",
            data_points=[
                MacroDataPoint(date=date(2024, 1, 1), value=Decimal("6.50")),
                MacroDataPoint(date=date(2024, 4, 1), value=Decimal("6.50")),
                MacroDataPoint(date=date(2024, 7, 1), value=Decimal("6.25")),
            ],
        )
    if indicator_id == "CPI_INFLATION":
        return MacroSeries(
            indicator_id="CPI_INFLATION",
            name="CPI Inflation",
            unit="PERCENTAGE",
            data_points=[
                MacroDataPoint(date=date(2024, 1, 1), value=Decimal("5.10")),
                MacroDataPoint(date=date(2024, 4, 1), value=Decimal("4.83")),
                MacroDataPoint(date=date(2024, 7, 1), value=Decimal("3.54")),
            ],
        )
    raise ProviderError(provider="mock_macro_data", message=f"Unknown: {indicator_id}", operation="get_indicator")


def _make_tools(
    session: AsyncMock | None = None,
    run_service: AsyncMock | None = None,
    macro_data: AsyncMock | None = None,
    search: AsyncMock | None = None,
    news: AsyncMock | None = None,
) -> MacroEconomicsTools:
    return MacroEconomicsTools(
        session=session or _make_session_mock(),
        run_service=run_service or _make_run_service_mock(),
        macro_data=macro_data or _make_macro_data_mock(),
        search=search or AsyncMock(),
        news=news or AsyncMock(),
    )


# ===========================================================================
# Tool 1: load_macro_context
# ===========================================================================


class TestLoadMacroContext:
    @pytest.mark.asyncio
    async def test_company_not_found(self) -> None:
        session = _make_session_mock()
        session.get = AsyncMock(return_value=None)
        tools = _make_tools(session=session)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        with pytest.raises(CompanyNotFoundForMacroError):
            await tools.load_macro_context(inp)

    @pytest.mark.asyncio
    async def test_basic_company_load(self) -> None:
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        assert result.company_name == "HDFC Bank Limited"
        assert result.exchange == "NSE"
        assert isinstance(result, LoadMacroContextOutput)

    @pytest.mark.asyncio
    async def test_sectors_populated(self) -> None:
        sector = MockClassification(name="Financial Services")
        industry = MockClassification(name="Banking")
        company = MockCompany(id=COMPANY_ID, sector=sector, industry=industry)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        assert "Financial Services" in result.sectors
        assert "Banking" in result.sectors

    @pytest.mark.asyncio
    async def test_duplicate_sector_industry_name(self) -> None:
        """When sector and industry have the same name, only include once."""
        classification = MockClassification(name="Banking")
        company = MockCompany(id=COMPANY_ID, sector=classification, industry=classification)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)
        assert result.sectors == ["Banking"]

    @pytest.mark.asyncio
    async def test_bse_exchange_when_no_nse(self) -> None:
        company = MockCompany(id=COMPANY_ID, nse_symbol=None, bse_code="500180")
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        tools = _make_tools(session=session, run_service=run_service)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)
        assert result.exchange == "BSE"

    @pytest.mark.asyncio
    async def test_indicator_snapshots_from_provider(self) -> None:
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        macro_data = _make_macro_data_mock()
        tools = _make_tools(session=session, run_service=run_service, macro_data=macro_data)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        assert len(result.indicator_snapshots) == 2
        assert len(result.available_indicators) == 2
        assert result.unavailable_dimensions == []

        repo_snap = next(s for s in result.indicator_snapshots if s.indicator_id == "REPO_RATE")
        assert repo_snap.value == Decimal("6.25")
        assert repo_snap.as_of_date == date(2024, 7, 1)
        assert isinstance(repo_snap.value, Decimal)

    @pytest.mark.asyncio
    async def test_available_indicators_are_macro_indicator_info(self) -> None:
        """F-01 regression test: available_indicators must be list[MacroIndicatorInfo]."""
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        macro_data = _make_macro_data_mock()
        tools = _make_tools(session=session, run_service=run_service, macro_data=macro_data)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        for ind in result.available_indicators:
            assert isinstance(ind, MacroIndicatorInfo)
            assert ind.indicator_id
            assert ind.name
            assert ind.source

    @pytest.mark.asyncio
    async def test_provider_failure_degrades_gracefully(self) -> None:
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        macro_data = AsyncMock()
        macro_data.list_indicators = AsyncMock(
            side_effect=ProviderError(provider="mock", message="down", operation="list"),
        )

        tools = _make_tools(session=session, run_service=run_service, macro_data=macro_data)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        assert result.available_indicators == []
        assert result.indicator_snapshots == []
        assert len(result.unavailable_dimensions) > 0

    @pytest.mark.asyncio
    async def test_prior_findings_loaded(self) -> None:
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run = MockResearchRun(status=ResearchRunStatus.COMPLETED)
        run_service.get_runs_for_company = AsyncMock(return_value=[run])
        finding = MockFinding()
        run_service.get_findings = AsyncMock(return_value=[finding])

        tools = _make_tools(session=session, run_service=run_service)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)

        assert len(result.prior_findings) == 1
        assert result.prior_findings[0].category == "monetary_policy_assessment"

    @pytest.mark.asyncio
    async def test_observation_date_filters_snapshots(self) -> None:
        """Snapshots with as_of_date > observation_date are excluded."""
        company = MockCompany(id=COMPANY_ID)
        session = _make_session_mock()
        session.get = AsyncMock(return_value=company)

        run_service = _make_run_service_mock()
        run_service.get_runs_for_company = AsyncMock(return_value=[])

        macro_data = AsyncMock()
        macro_data.list_indicators = AsyncMock(
            return_value=[
                MacroIndicatorInfo(
                    indicator_id="FUTURE_RATE",
                    name="Future Rate",
                    source="RBI",
                    frequency="quarterly",
                    unit="PERCENTAGE",
                ),
            ]
        )
        macro_data.get_indicator = AsyncMock(
            return_value=MacroSeries(
                indicator_id="FUTURE_RATE",
                name="Future Rate",
                unit="PERCENTAGE",
                data_points=[
                    MacroDataPoint(date=date(2026, 1, 1), value=Decimal("7.00")),
                ],
            )
        )

        tools = _make_tools(session=session, run_service=run_service, macro_data=macro_data)

        inp = LoadMacroContextInput(
            company_id=COMPANY_ID,
            research_run_id=RUN_ID,
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.load_macro_context(inp)
        assert result.indicator_snapshots == []


# ===========================================================================
# Tool 2: discover_macro_sources
# ===========================================================================


class TestDiscoverMacroSources:
    @pytest.mark.asyncio
    async def test_basic_discovery(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="India Monetary Policy Impact on Banking",
                    url="https://rbi.org/policy/2025",
                    snippet="RBI monetary policy...",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            sectors=["Banking"],
            dimensions_to_search=["monetary_policy"],
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        assert len(result.sources) >= 1
        assert "monetary_policy" in result.dimensions_covered

    @pytest.mark.asyncio
    async def test_news_articles_included(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="RBI cuts repo rate by 25bps",
                    url="https://economictimes.com/rbi-rate-cut",
                    source="Economic Times",
                    published_at=datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC),
                ),
            ]
        )

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            sectors=["Banking"],
            dimensions_to_search=["monetary_policy"],
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        news_sources = [s for s in result.sources if s.provider == "news"]
        assert len(news_sources) == 1
        assert news_sources[0].source_type == DocumentType.NEWS

    @pytest.mark.asyncio
    async def test_future_news_filtered_out(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Future macro event",
                    url="https://example.com/future",
                    source="Future News",
                    published_at=datetime(2025, 12, 1, 10, 0, 0, tzinfo=UTC),
                ),
            ]
        )

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        assert len(result.sources) == 0

    @pytest.mark.asyncio
    async def test_dedup_by_url(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(title="Dup 1", url="https://rbi.org/policy", snippet="..."),
                SearchResult(title="Dup 2", url="https://rbi.org/policy", snippet="..."),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            dimensions_to_search=["monetary_policy"],
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        urls = [s.url for s in result.sources]
        assert len(urls) == len(set(urls))

    @pytest.mark.asyncio
    async def test_provider_error_captured(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            side_effect=ProviderError(provider="search", message="down", operation="search"),
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            side_effect=ProviderError(provider="news", message="down", operation="search_news"),
        )

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            dimensions_to_search=["monetary_policy"],
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        assert result.sources == []
        assert "monetary_policy" in result.dimensions_still_missing

    @pytest.mark.asyncio
    async def test_all_dimensions_searched_when_none_specified(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(title="Result", url="https://example.com/1", snippet="..."),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])

        tools = _make_tools(search=search, news=news)

        inp = DiscoverMacroSourcesInput(
            company_name="HDFC Bank",
            observation_date=OBSERVATION_DATE,
        )
        result = await tools.discover_macro_sources(inp)

        # All 8 dimensions should be covered when results exist
        assert len(result.dimensions_covered) > 0


# ===========================================================================
# Tool 3: retrieve_document
# ===========================================================================


class TestRetrieveDocument:
    @pytest.mark.asyncio
    async def test_basic_retrieval(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(title="Policy doc", url="https://rbi.org/doc", snippet="Policy content here"),
            ]
        )

        tools = _make_tools(search=search)

        inp = RetrieveDocumentInput(filing_id="https://rbi.org/doc")
        result = await tools.retrieve_document(inp)

        assert result.content == "Policy content here"
        assert result.content_hash == hashlib.sha256(b"Policy content here").hexdigest()
        assert result.content_type == "text/snippet"

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        tools = _make_tools(search=search)

        inp = RetrieveDocumentInput(filing_id="nonexistent")
        result = await tools.retrieve_document(inp)

        assert result.content == ""
        assert result.content_hash == hashlib.sha256(b"").hexdigest()


# ===========================================================================
# Tool 4: create_research_document
# ===========================================================================


class TestCreateResearchDocument:
    @pytest.mark.asyncio
    async def test_creates_document(self) -> None:
        session = _make_session_mock()
        doc_id = uuid.uuid4()

        async def refresh_with_id(obj: Any) -> None:
            obj.id = doc_id

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        candidate = SourceCandidate(
            source_id="https://rbi.org/policy",
            source_type=DocumentType.FILING,
            provider="search",
            title="RBI Monetary Policy",
            publication_date=date(2025, 6, 1),
            source_tier=SourceTier.TIER_1,
            url="https://rbi.org/policy",
        )
        content_hash = hashlib.sha256(b"content").hexdigest()

        result = await tools.create_research_document(COMPANY_ID, candidate, content_hash)

        assert result == doc_id
        session.add.assert_called_once()
        session.flush.assert_awaited_once()


# ===========================================================================
# Tool 5: persist_evidence
# ===========================================================================


class TestPersistEvidence:
    @pytest.mark.asyncio
    async def test_persist_single_evidence(self) -> None:
        session = _make_session_mock()
        evidence_id = uuid.uuid4()

        async def refresh_with_id(obj: Any) -> None:
            obj.id = evidence_id

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        doc_id = uuid.uuid4()
        inp = PersistEvidenceInput(
            document_id=doc_id,
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="RBI repo rate is 6.25%",
                    context="As of Q2 2024",
                    page_or_section="Section 1",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 1
        assert result.evidence_ids[0] == evidence_id
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_extracted_by_macro_agent(self) -> None:
        session = _make_session_mock()

        async def refresh_with_id(obj: Any) -> None:
            obj.id = uuid.uuid4()

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="Test claim",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        await tools.persist_evidence(inp)

        added_record = session.add.call_args[0][0]
        assert added_record.extracted_by == MACRO_AGENT_NAME


# ===========================================================================
# Tool 6: persist_findings
# ===========================================================================


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_valid_findings_persisted(self) -> None:
        run_service = _make_run_service_mock()
        persisted = [MockPersistedFinding(), MockPersistedFinding()]
        run_service.record_findings = AsyncMock(return_value=persisted)

        tools = _make_tools(run_service=run_service)

        inp = PersistFindingsInput(
            run_id=RUN_ID,
            execution_id=EXECUTION_ID,
            findings=[
                FindingItem(
                    agent_name=MACRO_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="monetary_policy_assessment",
                    content="RBI's accommodative stance benefits banking sector",
                    confidence=ConfidenceLevel.MEDIUM,
                    observation_date=OBSERVATION_DATE,
                ),
                FindingItem(
                    agent_name=MACRO_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="inflation_assessment",
                    content="CPI inflation at 3.54% in Jul 2024",
                    confidence=ConfidenceLevel.HIGH,
                    observation_date=OBSERVATION_DATE,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 2
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
                    agent_name=MACRO_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="not_a_valid_macro_category",
                    content="Invalid",
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert result.finding_ids == []
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 0

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
                    agent_name=MACRO_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="monetary_policy_assessment",
                    content="Valid finding",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                FindingItem(
                    agent_name=MACRO_AGENT_NAME,
                    finding_type=FindingType.AI_INFERENCE,
                    category="completely_bogus",
                    content="Invalid finding",
                    confidence=ConfidenceLevel.LOW,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 1


# ===========================================================================
# Tool 7: persist_macro_indicators (NEW)
# ===========================================================================


class TestPersistMacroIndicators:
    @pytest.mark.asyncio
    async def test_persist_new_indicators(self) -> None:
        session = _make_session_mock()
        indicator_ids = [uuid.uuid4(), uuid.uuid4()]
        call_count = 0

        async def refresh_with_id(obj: Any) -> None:
            nonlocal call_count
            obj.id = indicator_ids[call_count]
            call_count += 1

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        # No duplicates
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        tools = _make_tools(session=session)

        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_ID,
            snapshots=[
                MacroIndicatorSnapshot(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    value=Decimal("6.25"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="RBI",
                ),
                MacroIndicatorSnapshot(
                    indicator_id="CPI_INFLATION",
                    name="CPI Inflation",
                    value=Decimal("3.54"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="MOSPI",
                ),
            ],
        )
        result = await tools.persist_macro_indicators(inp)

        assert len(result.indicator_ids) == 2
        assert result.persisted_count == 2
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self) -> None:
        session = _make_session_mock()
        existing_id = uuid.uuid4()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_id)
        session.execute = AsyncMock(return_value=mock_result)

        tools = _make_tools(session=session)

        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_ID,
            snapshots=[
                MacroIndicatorSnapshot(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    value=Decimal("6.25"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="RBI",
                ),
            ],
        )
        result = await tools.persist_macro_indicators(inp)

        assert len(result.indicator_ids) == 1
        assert result.indicator_ids[0] == existing_id
        assert result.persisted_count == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_decimal_fidelity(self) -> None:
        """All indicator values must remain Decimal, never float."""
        session = _make_session_mock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        async def refresh_with_id(obj: Any) -> None:
            obj.id = uuid.uuid4()

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        val = Decimal("6.25000000")
        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_ID,
            snapshots=[
                MacroIndicatorSnapshot(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    value=val,
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="RBI",
                ),
            ],
        )
        await tools.persist_macro_indicators(inp)

        added_record = session.add.call_args[0][0]
        assert isinstance(added_record.value, Decimal)
        assert added_record.value == val

    @pytest.mark.asyncio
    async def test_country_default_india(self) -> None:
        session = _make_session_mock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        async def refresh_with_id(obj: Any) -> None:
            obj.id = uuid.uuid4()

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_ID,
            snapshots=[
                MacroIndicatorSnapshot(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    value=Decimal("6.25"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="RBI",
                ),
            ],
        )
        await tools.persist_macro_indicators(inp)

        added_record = session.add.call_args[0][0]
        assert added_record.country == "IN"

    @pytest.mark.asyncio
    async def test_mixed_new_and_duplicate(self) -> None:
        session = _make_session_mock()
        existing_id = uuid.uuid4()
        new_id = uuid.uuid4()

        call_idx = [0]

        async def execute_side_effect(stmt: Any) -> Any:
            mock_r = AsyncMock()
            if call_idx[0] == 0:
                mock_r.scalar_one_or_none = MagicMock(return_value=existing_id)
            else:
                mock_r.scalar_one_or_none = MagicMock(return_value=None)
            call_idx[0] += 1
            return mock_r

        session.execute = AsyncMock(side_effect=execute_side_effect)

        async def refresh_with_id(obj: Any) -> None:
            obj.id = new_id

        session.refresh = AsyncMock(side_effect=refresh_with_id)

        tools = _make_tools(session=session)

        inp = PersistMacroIndicatorsInput(
            research_run_id=RUN_ID,
            snapshots=[
                MacroIndicatorSnapshot(
                    indicator_id="REPO_RATE",
                    name="RBI Repo Rate",
                    value=Decimal("6.25"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="RBI",
                ),
                MacroIndicatorSnapshot(
                    indicator_id="CPI_INFLATION",
                    name="CPI Inflation",
                    value=Decimal("3.54"),
                    unit="PERCENTAGE",
                    as_of_date=date(2024, 7, 1),
                    source="MOSPI",
                ),
            ],
        )
        result = await tools.persist_macro_indicators(inp)

        assert result.indicator_ids == [existing_id, new_id]
        assert result.persisted_count == 1


# ===========================================================================
# Tool 8: compute_indicator_trends (NEW)
# ===========================================================================


class TestComputeIndicatorTrends:
    def test_increasing_trend(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="CPI_INFLATION",
            data_points=[
                (date(2024, 1, 1), Decimal("4.00")),
                (date(2024, 4, 1), Decimal("5.00")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "INCREASING"
        assert trend.current_value == Decimal("5.00")
        assert trend.prior_value == Decimal("4.00")
        assert trend.absolute_change == Decimal("1.00")
        # (5 - 4) / 4 × 100 = 25.0000
        assert trend.percentage_change == Decimal("25.0000")
        assert trend.data_points_available == 2

    def test_decreasing_trend(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("6.50")),
                (date(2024, 4, 1), Decimal("6.25")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "DECREASING"
        assert trend.absolute_change == Decimal("-0.25")
        # (-0.25 / 6.50) × 100 = -3.8462
        expected_pct = (Decimal("-0.25") / Decimal("6.50") * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        assert trend.percentage_change == expected_pct

    def test_stable_within_threshold(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("100.00")),
                (date(2024, 4, 1), Decimal("100.40")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        # 0.40 / 100 × 100 = 0.4000 → within ±0.50 → STABLE
        assert trend.direction == "STABLE"
        assert trend.percentage_change == Decimal("0.4000")

    def test_insufficient_data_zero_points(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2026, 1, 1), Decimal("6.50")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "INSUFFICIENT_DATA"
        assert trend.data_points_available == 0

    def test_insufficient_data_one_point(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("6.50")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "INSUFFICIENT_DATA"
        assert trend.current_value == Decimal("6.50")
        assert trend.prior_value is None
        assert trend.absolute_change is None
        assert trend.percentage_change is None
        assert trend.data_points_available == 1

    def test_decimal_precision_round_half_up(self) -> None:
        """Verify 4-decimal-place ROUND_HALF_UP for percentage_change."""
        inp = ComputeIndicatorTrendsInput(
            indicator_id="TEST",
            data_points=[
                (date(2024, 1, 1), Decimal("3")),
                (date(2024, 4, 1), Decimal("4")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        # (4-3)/3 × 100 = 33.3333... → ROUND_HALF_UP → 33.3333
        assert trend.percentage_change == Decimal("33.3333")
        assert isinstance(trend.percentage_change, Decimal)

    def test_all_values_decimal(self) -> None:
        """Every numeric field in IndicatorTrend must be Decimal, never float."""
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("6.50")),
                (date(2024, 4, 1), Decimal("6.25")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert isinstance(trend.current_value, Decimal)
        assert isinstance(trend.prior_value, Decimal)
        assert isinstance(trend.absolute_change, Decimal)
        assert isinstance(trend.percentage_change, Decimal)

    def test_prior_value_zero(self) -> None:
        """When prior_value is 0, percentage_change is None."""
        inp = ComputeIndicatorTrendsInput(
            indicator_id="TEST",
            data_points=[
                (date(2024, 1, 1), Decimal("0")),
                (date(2024, 4, 1), Decimal("5")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.percentage_change is None
        assert trend.direction == "INCREASING"
        assert trend.absolute_change == Decimal("5")

    def test_both_zero(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="TEST",
            data_points=[
                (date(2024, 1, 1), Decimal("0")),
                (date(2024, 4, 1), Decimal("0")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "STABLE"
        assert trend.absolute_change == Decimal("0")

    def test_observation_date_filters_future_points(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("6.50")),
                (date(2024, 7, 1), Decimal("6.25")),
                (date(2026, 1, 1), Decimal("5.00")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.current_value == Decimal("6.25")
        assert trend.current_date == date(2024, 7, 1)
        assert trend.data_points_available == 2

    def test_multiple_data_points_uses_last_two(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2023, 1, 1), Decimal("6.00")),
                (date(2023, 7, 1), Decimal("6.25")),
                (date(2024, 1, 1), Decimal("6.50")),
                (date(2024, 7, 1), Decimal("6.25")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.current_value == Decimal("6.25")
        assert trend.prior_value == Decimal("6.50")
        assert trend.data_points_available == 4

    def test_negative_values(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="TRADE_BALANCE",
            data_points=[
                (date(2024, 1, 1), Decimal("-20.00")),
                (date(2024, 4, 1), Decimal("-15.00")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.direction == "INCREASING"
        assert trend.absolute_change == Decimal("5.00")
        # (-15 - (-20)) / |-20| × 100 = 25.0000
        assert trend.percentage_change == Decimal("25.0000")

    def test_unsorted_input_sorted_correctly(self) -> None:
        inp = ComputeIndicatorTrendsInput(
            indicator_id="REPO_RATE",
            data_points=[
                (date(2024, 7, 1), Decimal("6.25")),
                (date(2024, 1, 1), Decimal("6.50")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        trend = result.trend

        assert trend.current_value == Decimal("6.25")
        assert trend.prior_value == Decimal("6.50")
        assert trend.current_date == date(2024, 7, 1)
        assert trend.prior_date == date(2024, 1, 1)

    def test_exactly_at_threshold_is_stable(self) -> None:
        """±0.50 exactly → STABLE."""
        inp = ComputeIndicatorTrendsInput(
            indicator_id="RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("100")),
                (date(2024, 4, 1), Decimal("100.50")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        assert result.trend.direction == "STABLE"

    def test_just_above_threshold_is_increasing(self) -> None:
        """Just above ±0.50 → INCREASING."""
        inp = ComputeIndicatorTrendsInput(
            indicator_id="RATE",
            data_points=[
                (date(2024, 1, 1), Decimal("100")),
                (date(2024, 4, 1), Decimal("100.51")),
            ],
            observation_date=OBSERVATION_DATE,
        )
        result = MacroEconomicsTools.compute_indicator_trends(inp)
        assert result.trend.direction == "INCREASING"


# ===========================================================================
# Helper functions
# ===========================================================================


class TestClassifyMacroSource:
    def test_rbi_url(self) -> None:
        assert _classify_macro_source("Policy", "https://rbi.org/doc") == DocumentType.FILING

    def test_sebi_url(self) -> None:
        assert _classify_macro_source("Reg", "https://sebi.gov.in/doc") == DocumentType.FILING

    def test_monetary_policy_title(self) -> None:
        assert _classify_macro_source("Monetary Policy Statement", "https://example.com") == DocumentType.FILING

    def test_news_title(self) -> None:
        assert _classify_macro_source("Economy slows down in Q2", "https://example.com") == DocumentType.NEWS

    def test_research_report_title(self) -> None:
        assert _classify_macro_source("Economic outlook 2025", "https://example.com") == DocumentType.RESEARCH_REPORT

    def test_default(self) -> None:
        assert _classify_macro_source("Unknown document", "https://example.com/xyz") == DocumentType.RESEARCH_REPORT


class TestTierFromUrl:
    def test_rbi_tier1(self) -> None:
        assert _tier_from_url("https://rbi.org/monetary") == SourceTier.TIER_1

    def test_sebi_tier1(self) -> None:
        assert _tier_from_url("https://sebi.gov.in/circular") == SourceTier.TIER_1

    def test_mospi_tier1(self) -> None:
        assert _tier_from_url("https://mospi.gov.in/data") == SourceTier.TIER_1

    def test_ibef_tier2(self) -> None:
        assert _tier_from_url("https://ibef.org/industry") == SourceTier.TIER_2

    def test_nasscom_tier2(self) -> None:
        assert _tier_from_url("https://nasscom.in/report") == SourceTier.TIER_2

    def test_generic_tier3(self) -> None:
        assert _tier_from_url("https://example.com/article") == SourceTier.TIER_3


# ===========================================================================
# F-01 regression: LoadMacroContextOutput serialization
# ===========================================================================


class TestF01Regression:
    def test_available_indicators_accepts_macro_indicator_info(self) -> None:
        """Confirm the contract accepts MacroIndicatorInfo, not plain str."""
        indicator = MacroIndicatorInfo(
            indicator_id="REPO_RATE",
            name="RBI Repo Rate",
            source="RBI",
            frequency="quarterly",
            unit="PERCENTAGE",
        )
        out = LoadMacroContextOutput(
            company_name="Test",
            available_indicators=[indicator],
        )
        assert len(out.available_indicators) == 1
        assert isinstance(out.available_indicators[0], MacroIndicatorInfo)

    def test_available_indicators_rejects_plain_str(self) -> None:
        """Plain strings must no longer be accepted for available_indicators."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LoadMacroContextOutput(
                company_name="Test",
                available_indicators=["REPO_RATE"],  # type: ignore[list-item]
            )

    def test_roundtrip_serialization(self) -> None:
        """Verify JSON roundtrip preserves MacroIndicatorInfo structure."""
        indicator = MacroIndicatorInfo(
            indicator_id="CPI_INFLATION",
            name="CPI Inflation",
            description="Consumer Price Index",
            source="MOSPI",
            frequency="monthly",
            unit="PERCENTAGE",
        )
        out = LoadMacroContextOutput(
            company_name="Test",
            available_indicators=[indicator],
        )
        json_str = out.model_dump_json()
        restored = LoadMacroContextOutput.model_validate_json(json_str)
        assert restored.available_indicators[0].indicator_id == "CPI_INFLATION"
        assert restored.available_indicators[0].source == "MOSPI"


# ===========================================================================
# Exception tests
# ===========================================================================


class TestCompanyNotFoundForMacroError:
    def test_message(self) -> None:
        err = CompanyNotFoundForMacroError("abc-123")
        assert "abc-123" in str(err)
        assert "macro analysis" in err.message.lower()

    def test_details(self) -> None:
        err = CompanyNotFoundForMacroError("xyz")
        assert err.details is not None
        assert err.details["company_id"] == "xyz"
