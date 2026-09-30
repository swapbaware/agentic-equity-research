"""Tool implementations for the Industry Research Agent.

Each public method corresponds to one of the 5 new industry-specific tool
contracts plus 3 adapted tool contracts (retrieve_document, persist_evidence,
persist_findings) defined in ``app.agents.contracts``.  Tools depend on
provider Protocol interfaces and the database session — never on concrete
provider implementations.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.contracts import (
    INDUSTRY_AGENT_NAME,
    INDUSTRY_FINDING_CATEGORIES,
    DiscoverIndustrySourcesInput,
    DiscoverIndustrySourcesOutput,
    GetIndustryProfileInput,
    GetIndustryProfileOutput,
    IndustryCompanySummary,
    NewsArticleResult,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    RejectedFinding,
    RetrieveIndustryDocumentInput,
    RetrieveIndustryDocumentOutput,
    SearchIndustryNewsInput,
    SearchIndustryNewsOutput,
    SourceCandidate,
    ValidateIndustryInput,
    ValidateIndustryOutput,
)
from app.agents.industry_research.exceptions import IndustryNotFoundError
from app.models.company import Classification, Company
from app.models.enums import DocumentType, SourceTier
from app.models.research import Evidence, ResearchDocument
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    LLMProvider,
    MacroDataProvider,
    NewsProvider,
    SearchProvider,
)
from app.schemas.research_run import ResearchFindingCreate
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IndustryResearchTools:
    """Implements the 8 tool contracts for the Industry Research Agent.

    5 new industry-specific tools plus 3 adapted tools (retrieve_document,
    persist_evidence, persist_findings) using industry-specific constants.

    All provider access goes through Protocol interfaces injected at
    construction time.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        search: SearchProvider,
        news: NewsProvider,
        macro_data: MacroDataProvider,
        llm: LLMProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._search = search
        self._news = news
        self._macro_data = macro_data
        self._llm = llm

    # -- Tool 1: validate_industry ---------------------------------------------

    async def validate_industry(
        self,
        inp: ValidateIndustryInput,
    ) -> ValidateIndustryOutput:
        classification = await self._session.get(Classification, inp.industry_id)

        if classification is None:
            raise IndustryNotFoundError(str(inp.industry_id))

        parent_sector_id: uuid.UUID | None = None
        parent_sector_name: str | None = None
        if classification.parent is not None:
            parent_sector_id = classification.parent.id
            parent_sector_name = classification.parent.name

        return ValidateIndustryOutput(
            industry_id=classification.id,
            name=classification.name,
            code=classification.code,
            level=classification.level.value,
            parent_sector_id=parent_sector_id,
            parent_sector_name=parent_sector_name,
        )

    # -- Tool 2: discover_industry_sources -------------------------------------

    async def discover_industry_sources(
        self,
        inp: DiscoverIndustrySourcesInput,
    ) -> DiscoverIndustrySourcesOutput:
        candidates: list[SourceCandidate] = []

        search_queries = [
            f"{inp.industry_name} industry report India",
            f"{inp.industry_name} sector analysis India market",
            f"{inp.industry_name} industry outlook India",
        ]

        for query in search_queries:
            try:
                results = await self._search.search(
                    query,
                    num_results=inp.limit,
                )
                for r in results:
                    doc_type = _classify_industry_source(r.title, r.url)
                    if inp.document_types and doc_type not in inp.document_types:
                        continue
                    candidates.append(
                        SourceCandidate(
                            source_id=r.url,
                            source_type=doc_type,
                            provider="search",
                            title=r.title,
                            publication_date=inp.observation_date,
                            source_tier=_tier_from_url(r.url),
                            url=r.url,
                        )
                    )
            except ProviderError:
                logger.warning(
                    "search provider failed for query: %s",
                    query,
                )

        try:
            articles = await self._news.search_news(
                f"{inp.industry_name} industry India",
                start=None,
                end=inp.observation_date,
                limit=inp.limit,
            )
            for a in articles:
                pub_date = a.published_at.date()
                if pub_date <= inp.observation_date:
                    if inp.document_types and DocumentType.NEWS not in inp.document_types:
                        continue
                    candidates.append(
                        SourceCandidate(
                            source_id=a.url,
                            source_type=DocumentType.NEWS,
                            provider="news",
                            title=a.title,
                            publication_date=pub_date,
                            source_tier=SourceTier.TIER_3,
                            url=a.url,
                        )
                    )
        except ProviderError:
            logger.warning(
                "news provider failed for industry: %s",
                inp.industry_name,
            )

        seen_urls: set[str] = set()
        unique: list[SourceCandidate] = []
        for c in candidates:
            key = c.url or c.source_id
            if key not in seen_urls:
                seen_urls.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c.publication_date, reverse=True)
        return DiscoverIndustrySourcesOutput(candidates=unique[: inp.limit])

    # -- Tool 3: retrieve_industry_document ------------------------------------

    async def retrieve_industry_document(
        self,
        inp: RetrieveIndustryDocumentInput,
    ) -> RetrieveIndustryDocumentOutput:
        results = await self._search.search(inp.url, num_results=1)
        content = "" if not results else results[0].snippet

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return RetrieveIndustryDocumentOutput(
            content=content,
            content_type="text/plain",
            content_hash=content_hash,
            source_id=inp.source_id,
        )

    # -- Tool 4: get_industry_profile ------------------------------------------

    async def get_industry_profile(
        self,
        inp: GetIndustryProfileInput,
    ) -> GetIndustryProfileOutput:
        classification = await self._session.get(Classification, inp.industry_id)

        if classification is None:
            raise IndustryNotFoundError(str(inp.industry_id))

        parent_sector_id: uuid.UUID | None = None
        parent_sector_name: str | None = None
        if classification.parent is not None:
            parent_sector_id = classification.parent.id
            parent_sector_name = classification.parent.name

        stmt = (
            sa.select(Company)
            .where(Company.industry_id == inp.industry_id)
            .order_by(Company.market_cap.desc().nulls_last())
        )
        result = await self._session.execute(stmt)
        companies = list(result.scalars().all())

        summaries = [
            IndustryCompanySummary(
                company_id=c.id,
                name=c.name,
                nse_symbol=c.nse_symbol,
                bse_code=c.bse_code,
                market_cap=c.market_cap,
                is_active=c.is_active,
            )
            for c in companies
        ]

        return GetIndustryProfileOutput(
            industry_id=classification.id,
            name=classification.name,
            code=classification.code,
            level=classification.level.value,
            parent_sector_id=parent_sector_id,
            parent_sector_name=parent_sector_name,
            company_count=len(summaries),
            companies=summaries,
        )

    # -- Tool 5: search_industry_news ------------------------------------------

    async def search_industry_news(
        self,
        inp: SearchIndustryNewsInput,
    ) -> SearchIndustryNewsOutput:
        articles = await self._news.search_news(
            f"{inp.industry_name} industry India",
            start=None,
            end=inp.observation_date,
            limit=inp.limit,
        )
        results: list[NewsArticleResult] = []
        for a in articles:
            if a.published_at.date() <= inp.observation_date:
                results.append(
                    NewsArticleResult(
                        title=a.title,
                        url=a.url,
                        source=a.source,
                        published_at=a.published_at,
                        summary=a.summary,
                    )
                )
        return SearchIndustryNewsOutput(articles=results)

    # -- Adapted Tool 6: persist_evidence (industry-aware) ---------------------

    async def persist_evidence(
        self,
        inp: PersistEvidenceInput,
    ) -> PersistEvidenceOutput:
        evidence_ids: list[uuid.UUID] = []
        for ev in inp.evidences:
            record = Evidence(
                document_id=inp.document_id,
                evidence_type=ev.evidence_type,
                claim=ev.claim,
                context=ev.context,
                page_or_section=ev.page_or_section,
                confidence=ev.confidence,
                extracted_by=INDUSTRY_AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Adapted Tool 7: persist_findings (industry-aware) ---------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in INDUSTRY_FINDING_CATEGORIES:
                rejected.append(
                    RejectedFinding(
                        index=i,
                        reason=f"Invalid category: {f.category}",
                    )
                )
                continue
            finding_defs.append(
                ResearchFindingCreate(
                    agent_name=f.agent_name,
                    finding_type=f.finding_type,
                    category=f.category,
                    content=f.content,
                    confidence=f.confidence,
                    observation_date=f.observation_date,
                    source_publication_date=f.source_publication_date,
                )
            )

        finding_ids: list[uuid.UUID] = []
        if finding_defs:
            persisted = await self._run_service.record_findings(
                inp.run_id,
                inp.execution_id,
                finding_defs,
            )
            finding_ids = [f.id for f in persisted]

        return PersistFindingsOutput(
            finding_ids=finding_ids,
            rejected=rejected,
        )

    # -- Adapted: create_research_document (industry-aware, company_id=None) ---

    async def create_research_document(
        self,
        candidate: SourceCandidate,
        content_hash: str,
    ) -> uuid.UUID:
        doc = ResearchDocument(
            company_id=None,
            document_type=candidate.source_type,
            title=candidate.title,
            source_tier=candidate.source_tier,
            source_name=candidate.provider,
            source_url=candidate.url,
            document_date=candidate.publication_date,
            content_hash=content_hash,
            ingested_at=datetime.now(UTC),
        )
        self._session.add(doc)
        await self._session.flush()
        await self._session.refresh(doc)
        return doc.id


def _classify_industry_source(title: str, url: str) -> DocumentType:
    lower_title = title.lower()
    lower_url = url.lower()
    if any(kw in lower_title for kw in ("annual report", "yearly report")):
        return DocumentType.ANNUAL_REPORT
    if any(kw in lower_url for kw in ("sebi.gov", "rbi.org", "nse", "bse")):
        return DocumentType.FILING
    if any(kw in lower_title for kw in ("industry report", "sector report", "market report")):
        return DocumentType.RESEARCH_REPORT
    if any(kw in lower_title for kw in ("news", "article")):
        return DocumentType.NEWS
    return DocumentType.RESEARCH_REPORT


def _tier_from_url(url: str) -> SourceTier:
    lower = url.lower()
    if any(
        domain in lower
        for domain in (
            "sebi.gov",
            "rbi.org",
            "nseindia.com",
            "bseindia.com",
        )
    ):
        return SourceTier.TIER_1
    if any(
        domain in lower
        for domain in (
            "ibef.org",
            "ficci.in",
            "nasscom.in",
            "cii.in",
        )
    ):
        return SourceTier.TIER_2
    return SourceTier.TIER_3
