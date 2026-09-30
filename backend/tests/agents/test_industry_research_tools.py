"""Unit tests for IndustryResearchTools (Phase 9.3a).

Tests cover all 8 tool methods:
  1. validate_industry
  2. discover_industry_sources
  3. retrieve_industry_document
  4. get_industry_profile
  5. search_industry_news
  6. persist_evidence (industry-aware)
  7. persist_findings (industry-aware)
  8. create_research_document (industry-aware, company_id=None)

Plus helper functions _classify_industry_source and _tier_from_url.
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
    INDUSTRY_AGENT_NAME,
    INDUSTRY_FINDING_CATEGORIES,
    DiscoverIndustrySourcesInput,
    GetIndustryProfileInput,
    PersistEvidenceInput,
    PersistFindingsInput,
    RetrieveIndustryDocumentInput,
    SearchIndustryNewsInput,
    ValidateIndustryInput,
)
from app.agents.industry_research.exceptions import IndustryNotFoundError
from app.agents.industry_research.tools import (
    IndustryResearchTools,
    _classify_industry_source,
    _tier_from_url,
)
from app.models.enums import (
    ClassificationLevel,
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    SourceTier,
)
from app.providers.errors import ProviderError
from app.providers.types import NewsArticle, SearchResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class MockClassification:
    """Minimal stand-in for the Classification ORM model."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Information Technology",
        code: str = "IT",
        level: ClassificationLevel = ClassificationLevel.INDUSTRY,
        parent: MockClassification | None = None,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.name = name
        self.code = code
        self.level = level
        self.parent = parent


class MockCompany:
    """Minimal stand-in for the Company ORM model."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str = "Infosys Limited",
        nse_symbol: str | None = "INFY",
        bse_code: str | None = "500209",
        market_cap: Decimal | None = Decimal("6000000.0000"),
        is_active: bool = True,
    ) -> None:
        self.id = id or uuid.uuid4()
        self.name = name
        self.nse_symbol = nse_symbol
        self.bse_code = bse_code
        self.market_cap = market_cap
        self.is_active = is_active


class MockEvidence:
    """Stand-in for a persisted Evidence record."""

    def __init__(self) -> None:
        self.id = uuid.uuid4()


class MockFinding:
    """Stand-in for a persisted ResearchFinding record."""

    def __init__(self) -> None:
        self.id = uuid.uuid4()


class MockResearchDocument:
    """Stand-in for a persisted ResearchDocument record."""

    def __init__(self) -> None:
        self.id = uuid.uuid4()


class MockRunService:
    """Minimal mock for ResearchRunService."""

    def __init__(self) -> None:
        self.record_findings = AsyncMock(
            return_value=[MockFinding(), MockFinding()],
        )


def _build_tools(
    session: AsyncMock | None = None,
    run_service: MockRunService | None = None,
    search: AsyncMock | None = None,
    news: AsyncMock | None = None,
    macro_data: AsyncMock | None = None,
    llm: AsyncMock | None = None,
) -> IndustryResearchTools:
    return IndustryResearchTools(
        session=session or AsyncMock(),
        run_service=run_service or MockRunService(),
        search=search or AsyncMock(),
        news=news or AsyncMock(),
        macro_data=macro_data or AsyncMock(),
        llm=llm or AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tool 1: validate_industry
# ---------------------------------------------------------------------------


class TestValidateIndustry:
    @pytest.mark.asyncio
    async def test_valid_industry_no_parent(self) -> None:
        classification = MockClassification(
            level=ClassificationLevel.SECTOR,
            parent=None,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=classification)
        tools = _build_tools(session=session)

        inp = ValidateIndustryInput(industry_id=classification.id)
        result = await tools.validate_industry(inp)

        assert result.industry_id == classification.id
        assert result.name == classification.name
        assert result.code == classification.code
        assert result.level == ClassificationLevel.SECTOR.value
        assert result.parent_sector_id is None
        assert result.parent_sector_name is None

    @pytest.mark.asyncio
    async def test_valid_industry_with_parent(self) -> None:
        parent = MockClassification(
            name="Technology",
            code="TECH",
            level=ClassificationLevel.SECTOR,
        )
        classification = MockClassification(
            name="Information Technology",
            code="IT",
            level=ClassificationLevel.INDUSTRY,
            parent=parent,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=classification)
        tools = _build_tools(session=session)

        inp = ValidateIndustryInput(industry_id=classification.id)
        result = await tools.validate_industry(inp)

        assert result.industry_id == classification.id
        assert result.name == "Information Technology"
        assert result.level == ClassificationLevel.INDUSTRY.value
        assert result.parent_sector_id == parent.id
        assert result.parent_sector_name == "Technology"

    @pytest.mark.asyncio
    async def test_industry_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        tools = _build_tools(session=session)

        missing_id = uuid.uuid4()
        inp = ValidateIndustryInput(industry_id=missing_id)
        with pytest.raises(IndustryNotFoundError) as exc_info:
            await tools.validate_industry(inp)
        assert str(missing_id) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tool 2: discover_industry_sources
# ---------------------------------------------------------------------------


class TestDiscoverIndustrySources:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="IT Industry Report India 2024",
                    url="https://example.com/it-report",
                    snippet="A comprehensive report",
                ),
            ]
        )
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="IT sector grows 12%",
                    url="https://news.example.com/it-grows",
                    source="Economic Times",
                    published_at=datetime(2024, 6, 1, tzinfo=UTC),
                    summary="Strong growth",
                    symbols=[],
                ),
            ]
        )
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="Information Technology",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_industry_sources(inp)

        assert len(result.candidates) >= 2
        urls = [c.url for c in result.candidates]
        assert "https://example.com/it-report" in urls
        assert "https://news.example.com/it-grows" in urls

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
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_industry_sources(inp)

        seen_urls = [c.url for c in result.candidates]
        assert seen_urls.count("https://example.com/same-url") == 1

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
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
            limit=5,
        )
        result = await tools.discover_industry_sources(inp)
        assert len(result.candidates) <= 5

    @pytest.mark.asyncio
    async def test_search_provider_failure_graceful(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(side_effect=ProviderError(provider="search", message="Search unavailable"))
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
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_industry_sources(inp)
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
        news.search_news = AsyncMock(side_effect=ProviderError(provider="news", message="News unavailable"))
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_industry_sources(inp)
        assert len(result.candidates) >= 1

    @pytest.mark.asyncio
    async def test_filters_by_document_type(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="IT industry report for India",
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
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
            document_types=[DocumentType.NEWS],
        )
        result = await tools.discover_industry_sources(inp)
        for c in result.candidates:
            assert c.source_type == DocumentType.NEWS

    @pytest.mark.asyncio
    async def test_temporal_filtering_news(self) -> None:
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
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        tools = _build_tools(search=search, news=news)

        inp = DiscoverIndustrySourcesInput(
            industry_id=uuid.uuid4(),
            industry_name="IT",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.discover_industry_sources(inp)
        future_urls = [c.url for c in result.candidates if c.url == "https://news.example.com/future"]
        assert len(future_urls) == 0


# ---------------------------------------------------------------------------
# Tool 3: retrieve_industry_document
# ---------------------------------------------------------------------------


class TestRetrieveIndustryDocument:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(
            return_value=[
                SearchResult(
                    title="Result",
                    url="https://example.com/doc",
                    snippet="Document content from search",
                ),
            ]
        )
        tools = _build_tools(search=search)

        inp = RetrieveIndustryDocumentInput(
            url="https://example.com/doc",
            source_id="src-001",
        )
        result = await tools.retrieve_industry_document(inp)

        assert result.content == "Document content from search"
        assert result.source_id == "src-001"
        expected_hash = hashlib.sha256(b"Document content from search").hexdigest()
        assert result.content_hash == expected_hash
        assert result.content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_no_results_returns_empty(self) -> None:
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        tools = _build_tools(search=search)

        inp = RetrieveIndustryDocumentInput(
            url="https://example.com/missing",
            source_id="src-002",
        )
        result = await tools.retrieve_industry_document(inp)

        assert result.content == ""
        assert result.source_id == "src-002"
        assert result.content_hash == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# Tool 4: get_industry_profile
# ---------------------------------------------------------------------------


class TestGetIndustryProfile:
    @pytest.mark.asyncio
    async def test_happy_path_with_companies(self) -> None:
        parent = MockClassification(
            name="Technology",
            code="TECH",
            level=ClassificationLevel.SECTOR,
        )
        classification = MockClassification(
            name="IT Services",
            code="ITS",
            level=ClassificationLevel.INDUSTRY,
            parent=parent,
        )

        company1 = MockCompany(
            name="Infosys",
            nse_symbol="INFY",
            market_cap=Decimal("6000000.0000"),
        )
        company2 = MockCompany(
            name="TCS",
            nse_symbol="TCS",
            market_cap=Decimal("12000000.0000"),
        )

        session = AsyncMock()
        session.get = AsyncMock(return_value=classification)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [company1, company2]
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetIndustryProfileInput(industry_id=classification.id)
        result = await tools.get_industry_profile(inp)

        assert result.industry_id == classification.id
        assert result.name == "IT Services"
        assert result.code == "ITS"
        assert result.level == ClassificationLevel.INDUSTRY.value
        assert result.parent_sector_id == parent.id
        assert result.parent_sector_name == "Technology"
        assert result.company_count == 2
        assert len(result.companies) == 2
        assert result.companies[0].name == "Infosys"
        assert result.companies[1].name == "TCS"

    @pytest.mark.asyncio
    async def test_no_companies(self) -> None:
        classification = MockClassification(parent=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=classification)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        tools = _build_tools(session=session)

        inp = GetIndustryProfileInput(industry_id=classification.id)
        result = await tools.get_industry_profile(inp)

        assert result.company_count == 0
        assert result.companies == []

    @pytest.mark.asyncio
    async def test_industry_not_found(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        tools = _build_tools(session=session)

        missing_id = uuid.uuid4()
        inp = GetIndustryProfileInput(industry_id=missing_id)
        with pytest.raises(IndustryNotFoundError):
            await tools.get_industry_profile(inp)


# ---------------------------------------------------------------------------
# Tool 5: search_industry_news
# ---------------------------------------------------------------------------


class TestSearchIndustryNews:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Pharma industry growth",
                    url="https://news.example.com/pharma",
                    source="ET",
                    published_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
                    summary="Strong growth in pharma",
                    symbols=[],
                ),
            ]
        )
        tools = _build_tools(news=news)

        inp = SearchIndustryNewsInput(
            industry_name="Pharmaceuticals",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.search_industry_news(inp)

        assert len(result.articles) == 1
        assert result.articles[0].title == "Pharma industry growth"
        assert result.articles[0].url == "https://news.example.com/pharma"

    @pytest.mark.asyncio
    async def test_filters_future_articles(self) -> None:
        news = AsyncMock()
        news.search_news = AsyncMock(
            return_value=[
                NewsArticle(
                    title="Past article",
                    url="https://news.example.com/past",
                    source="ET",
                    published_at=datetime(2024, 3, 1, tzinfo=UTC),
                    summary="Past",
                    symbols=[],
                ),
                NewsArticle(
                    title="Future article",
                    url="https://news.example.com/future",
                    source="ET",
                    published_at=datetime(2025, 6, 1, tzinfo=UTC),
                    summary="Future",
                    symbols=[],
                ),
            ]
        )
        tools = _build_tools(news=news)

        inp = SearchIndustryNewsInput(
            industry_name="IT",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.search_industry_news(inp)

        assert len(result.articles) == 1
        assert result.articles[0].title == "Past article"

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        news = AsyncMock()
        news.search_news = AsyncMock(return_value=[])
        tools = _build_tools(news=news)

        inp = SearchIndustryNewsInput(
            industry_name="Niche Sector",
            observation_date=date(2024, 12, 31),
        )
        result = await tools.search_industry_news(inp)
        assert result.articles == []


# ---------------------------------------------------------------------------
# Adapted Tool 6: persist_evidence (industry-aware)
# ---------------------------------------------------------------------------


class TestPersistEvidence:
    @pytest.mark.asyncio
    async def test_uses_industry_agent_name(self) -> None:
        session = AsyncMock()
        created_records: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_records.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        from app.agents.contracts import EvidenceItem

        inp = PersistEvidenceInput(
            document_id=uuid.uuid4(),
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="IT industry grew 15% in FY2024",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 1
        assert len(created_records) == 1
        assert created_records[0].extracted_by == INDUSTRY_AGENT_NAME

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

        from app.agents.contracts import EvidenceItem

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
            ],
        )
        result = await tools.persist_evidence(inp)

        assert len(result.evidence_ids) == 2
        for record in created_records:
            assert record.extracted_by == INDUSTRY_AGENT_NAME


# ---------------------------------------------------------------------------
# Adapted Tool 7: persist_findings (industry-aware)
# ---------------------------------------------------------------------------


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_valid_industry_categories_accepted(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        from app.agents.contracts import FindingItem

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=INDUSTRY_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="market_size",
                    content="Indian IT market is $250B",
                    confidence=ConfidenceLevel.HIGH,
                ),
                FindingItem(
                    agent_name=INDUSTRY_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="entry_barriers",
                    content="High barriers due to talent requirements",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 2
        assert result.rejected == []
        run_service.record_findings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_company_categories_rejected(self) -> None:
        run_service = MockRunService()
        tools = _build_tools(run_service=run_service)

        from app.agents.contracts import FindingItem

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=INDUSTRY_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="company_identity",
                    content="This is a company category, not industry",
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
    async def test_mixed_valid_and_invalid_categories(self) -> None:
        run_service = MockRunService()
        run_service.record_findings = AsyncMock(
            return_value=[MockFinding()],
        )
        tools = _build_tools(run_service=run_service)

        from app.agents.contracts import FindingItem

        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=[
                FindingItem(
                    agent_name=INDUSTRY_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="growth_drivers",
                    content="Valid industry finding",
                    confidence=ConfidenceLevel.HIGH,
                ),
                FindingItem(
                    agent_name=INDUSTRY_AGENT_NAME,
                    finding_type=FindingType.FACT,
                    category="business_model",
                    content="This is a company category",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].index == 1

    @pytest.mark.asyncio
    async def test_all_14_industry_categories_accepted(self) -> None:
        run_service = MockRunService()
        findings_returned = [MockFinding() for _ in INDUSTRY_FINDING_CATEGORIES]
        run_service.record_findings = AsyncMock(return_value=findings_returned)
        tools = _build_tools(run_service=run_service)

        from app.agents.contracts import FindingItem

        findings = [
            FindingItem(
                agent_name=INDUSTRY_AGENT_NAME,
                finding_type=FindingType.FACT,
                category=cat,
                content=f"Finding for {cat}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            for cat in sorted(INDUSTRY_FINDING_CATEGORIES)
        ]
        inp = PersistFindingsInput(
            run_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            findings=findings,
        )
        result = await tools.persist_findings(inp)

        assert len(result.finding_ids) == 14
        assert result.rejected == []


# ---------------------------------------------------------------------------
# Adapted: create_research_document (industry-aware)
# ---------------------------------------------------------------------------


class TestCreateResearchDocument:
    @pytest.mark.asyncio
    async def test_company_id_is_none(self) -> None:
        session = AsyncMock()
        created_docs: list[Any] = []

        def capture_add(record: Any) -> None:
            record.id = uuid.uuid4()
            created_docs.append(record)

        session.add = capture_add
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        tools = _build_tools(session=session)

        from app.agents.contracts import SourceCandidate

        candidate = SourceCandidate(
            source_id="https://example.com/report",
            source_type=DocumentType.RESEARCH_REPORT,
            provider="search",
            title="Industry Report",
            publication_date=date(2024, 6, 1),
            source_tier=SourceTier.TIER_2,
            url="https://example.com/report",
        )
        doc_id = await tools.create_research_document(
            candidate,
            "abc123hash",
        )

        assert doc_id is not None
        assert len(created_docs) == 1
        assert created_docs[0].company_id is None
        assert created_docs[0].document_type == DocumentType.RESEARCH_REPORT
        assert created_docs[0].title == "Industry Report"
        assert created_docs[0].source_tier == SourceTier.TIER_2
        assert created_docs[0].content_hash == "abc123hash"


# ---------------------------------------------------------------------------
# Helper: _classify_industry_source
# ---------------------------------------------------------------------------


class TestClassifyIndustrySource:
    def test_annual_report(self) -> None:
        assert (
            _classify_industry_source(
                "Annual Report 2024",
                "https://example.com/ar",
            )
            == DocumentType.ANNUAL_REPORT
        )

    def test_yearly_report(self) -> None:
        assert (
            _classify_industry_source(
                "Yearly Report Summary",
                "https://example.com/yr",
            )
            == DocumentType.ANNUAL_REPORT
        )

    def test_sebi_filing(self) -> None:
        assert (
            _classify_industry_source(
                "Market regulation update",
                "https://sebi.gov.in/circular",
            )
            == DocumentType.FILING
        )

    def test_nse_source(self) -> None:
        assert (
            _classify_industry_source(
                "Data",
                "https://www.nseindia.com/data",
            )
            == DocumentType.FILING
        )

    def test_bse_source(self) -> None:
        assert (
            _classify_industry_source(
                "Data",
                "https://www.bseindia.com/data",
            )
            == DocumentType.FILING
        )

    def test_rbi_source(self) -> None:
        assert (
            _classify_industry_source(
                "Monetary policy",
                "https://rbi.org.in/scripts",
            )
            == DocumentType.FILING
        )

    def test_industry_report(self) -> None:
        assert (
            _classify_industry_source(
                "IT Industry Report 2024",
                "https://example.com/report",
            )
            == DocumentType.RESEARCH_REPORT
        )

    def test_sector_report(self) -> None:
        assert (
            _classify_industry_source(
                "Pharma Sector Report",
                "https://example.com/pharma",
            )
            == DocumentType.RESEARCH_REPORT
        )

    def test_market_report(self) -> None:
        assert (
            _classify_industry_source(
                "India Market Report",
                "https://example.com/market",
            )
            == DocumentType.RESEARCH_REPORT
        )

    def test_news_article(self) -> None:
        assert (
            _classify_industry_source(
                "Latest news on IT sector",
                "https://example.com/news",
            )
            == DocumentType.NEWS
        )

    def test_default_research_report(self) -> None:
        assert (
            _classify_industry_source(
                "Some random document",
                "https://example.com/other",
            )
            == DocumentType.RESEARCH_REPORT
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
        assert _tier_from_url("https://ficci.in/sector-report") == SourceTier.TIER_2

    def test_nasscom(self) -> None:
        assert _tier_from_url("https://nasscom.in/report") == SourceTier.TIER_2

    def test_cii(self) -> None:
        assert _tier_from_url("https://cii.in/sector") == SourceTier.TIER_2

    def test_generic_url(self) -> None:
        assert _tier_from_url("https://random-blog.com/article") == SourceTier.TIER_3


# ---------------------------------------------------------------------------
# IndustryNotFoundError
# ---------------------------------------------------------------------------


class TestIndustryNotFoundError:
    def test_message(self) -> None:
        err = IndustryNotFoundError("abc-123")
        assert "abc-123" in str(err)
        assert err.details is not None
        assert err.details["industry_id"] == "abc-123"

    def test_is_agent_error(self) -> None:
        from app.agents.company_research.exceptions import AgentError

        err = IndustryNotFoundError("test-id")
        assert isinstance(err, AgentError)


# ---------------------------------------------------------------------------
# Contract schema validation tests
# ---------------------------------------------------------------------------


class TestContractSchemaValidation:
    def test_validate_industry_input_requires_uuid(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            ValidateIndustryInput(industry_id="not-a-uuid")  # type: ignore[arg-type]

    def test_discover_sources_input_limits(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            DiscoverIndustrySourcesInput(
                industry_id=uuid.uuid4(),
                industry_name="IT",
                observation_date=date(2024, 1, 1),
                limit=0,
            )

        with pytest.raises(PydanticValidationError):
            DiscoverIndustrySourcesInput(
                industry_id=uuid.uuid4(),
                industry_name="IT",
                observation_date=date(2024, 1, 1),
                limit=101,
            )

    def test_discover_sources_input_name_length(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            DiscoverIndustrySourcesInput(
                industry_id=uuid.uuid4(),
                industry_name="",
                observation_date=date(2024, 1, 1),
            )

        with pytest.raises(PydanticValidationError):
            DiscoverIndustrySourcesInput(
                industry_id=uuid.uuid4(),
                industry_name="X" * 201,
                observation_date=date(2024, 1, 1),
            )

    def test_retrieve_doc_input_url_validation(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            RetrieveIndustryDocumentInput(
                url="",
                source_id="src-1",
            )

    def test_search_news_input_limit_bounds(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            SearchIndustryNewsInput(
                industry_name="IT",
                observation_date=date(2024, 1, 1),
                limit=0,
            )

        with pytest.raises(PydanticValidationError):
            SearchIndustryNewsInput(
                industry_name="IT",
                observation_date=date(2024, 1, 1),
                limit=51,
            )

    def test_frozen_contracts(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        inp = ValidateIndustryInput(industry_id=uuid.uuid4())
        with pytest.raises(PydanticValidationError):
            inp.industry_id = uuid.uuid4()  # type: ignore[misc]

    def test_industry_company_summary_frozen(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from app.agents.contracts import IndustryCompanySummary

        summary = IndustryCompanySummary(
            company_id=uuid.uuid4(),
            name="Test Co",
            is_active=True,
        )
        with pytest.raises(PydanticValidationError):
            summary.name = "Modified"  # type: ignore[misc]


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
        assert tools._macro_data is not None
        assert tools._llm is not None
