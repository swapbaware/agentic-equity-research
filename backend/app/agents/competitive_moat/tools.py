"""Tool implementations for the Competitive Moat Agent.

Each public method corresponds to one of the 7 agent-facing tool contracts
defined in ``app.agents.contracts``:

  1. load_company_context
  2. discover_moat_sources
  3. retrieve_document
  4. get_peer_data
  5. persist_evidence
  6. persist_findings
  7. persist_moat_assessments

Internal helper (NOT agent-facing): create_research_document.

Tools depend on provider Protocol interfaces and the database session —
never on concrete provider implementations.

Note on temporal semantics: The canonical filtering rule is
``information_available_date <= observation_date``. Where a provider
(e.g. NewsProvider) exposes only ``published_at``, the agent treats it as
the best available proxy but does NOT relabel it as
``information_available_date``. When availability date is unknown, the
field is preserved as-is (None) — never fabricated.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.competitive_moat.exceptions import CompanyNotFoundForMoatError
from app.agents.contracts import (
    MOAT_AGENT_NAME,
    MOAT_FINDING_CATEGORIES,
    DiscoverMoatSourcesInput,
    DiscoverMoatSourcesOutput,
    FindingSummary,
    GetPeerDataInput,
    GetPeerDataOutput,
    LoadContextInput,
    LoadContextOutput,
    PeerCompanySummary,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    PersistMoatAssessmentsInput,
    PersistMoatAssessmentsOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
)
from app.models.analysis import MoatAssessment, moat_assessment_evidence
from app.models.company import Company
from app.models.enums import (
    DocumentType,
    ResearchRunStatus,
    SourceTier,
)
from app.models.research import Evidence, ResearchDocument
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateFilingsProvider,
    NewsProvider,
    SearchProvider,
)
from app.schemas.research_run import ResearchFindingCreate
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CompetitiveMoatTools:
    """Implements the 7 agent-facing tool contracts for the Competitive Moat Agent.

    Provider dependencies are limited to SearchProvider, NewsProvider, and
    CorporateFilingsProvider per architecture §21. LLMProvider belongs at the
    CompetitiveMoatAgent level, not here.

    Also provides the ``create_research_document`` internal helper (not
    agent-facing).
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        search: SearchProvider,
        news: NewsProvider,
        corporate_filings: CorporateFilingsProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._search = search
        self._news = news
        self._corporate_filings = corporate_filings

    # -- Tool 1: load_company_context ------------------------------------------

    async def load_company_context(
        self,
        inp: LoadContextInput,
    ) -> LoadContextOutput:
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundForMoatError(str(inp.company_id))

        company_name = company.name
        nse_symbol = company.nse_symbol
        industry_id = inp.industry_id or company.industry_id
        industry_name: str | None = None
        if company.industry is not None:
            industry_name = company.industry.name

        company_findings: list[FindingSummary] = []
        industry_findings: list[FindingSummary] = []
        has_company_research = False
        has_industry_research = False

        company_runs = await self._run_service.get_runs_for_company(
            inp.company_id,
            limit=1,
        )
        completed_company_runs = [
            r for r in company_runs if r.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
        ]
        if completed_company_runs:
            has_company_research = True
            latest_run = completed_company_runs[0]
            findings = await self._run_service.get_findings(latest_run.id)
            for f in findings:
                company_findings.append(
                    FindingSummary(
                        finding_id=f.id,
                        category=f.category,
                        finding_type=f.finding_type,
                        content=f.content,
                        confidence=f.confidence,
                    )
                )

        if industry_id is not None:
            industry_runs = await self._run_service.get_runs_for_industry(
                industry_id,
                limit=1,
            )
            completed_industry_runs = [
                r for r in industry_runs if r.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
            ]
            if completed_industry_runs:
                has_industry_research = True
                latest_industry_run = completed_industry_runs[0]
                ind_findings = await self._run_service.get_findings(
                    latest_industry_run.id,
                )
                for f in ind_findings:
                    industry_findings.append(
                        FindingSummary(
                            finding_id=f.id,
                            category=f.category,
                            finding_type=f.finding_type,
                            content=f.content,
                            confidence=f.confidence,
                        )
                    )

        return LoadContextOutput(
            company_id=inp.company_id,
            company_name=company_name,
            nse_symbol=nse_symbol,
            industry_id=industry_id,
            industry_name=industry_name,
            company_findings=company_findings,
            industry_findings=industry_findings,
            has_company_research=has_company_research,
            has_industry_research=has_industry_research,
        )

    # -- Tool 2: discover_moat_sources -----------------------------------------

    async def discover_moat_sources(
        self,
        inp: DiscoverMoatSourcesInput,
    ) -> DiscoverMoatSourcesOutput:
        candidates: list[SourceCandidate] = []

        search_queries = [
            f"{inp.company_name} competitive advantage moat",
            f"{inp.company_name} market position competitive landscape",
        ]
        if inp.industry_name:
            search_queries.append(f"{inp.company_name} {inp.industry_name} industry competitive position")

        for query in search_queries:
            try:
                results = await self._search.search(
                    query,
                    num_results=inp.limit,
                )
                for r in results:
                    doc_type = _classify_moat_source(r.title, r.url)
                    if inp.document_types and doc_type not in inp.document_types:
                        continue
                    candidates.append(
                        SourceCandidate(
                            source_id=r.url,
                            source_type=doc_type,
                            provider="search",
                            title=r.title,
                            publication_date=None,
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
                f"{inp.company_name} competitive advantage market position",
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
                "news provider failed for company: %s",
                inp.company_name,
            )

        symbol = inp.nse_symbol
        if symbol:
            exchange = "NSE"
            try:
                filings = await self._corporate_filings.get_filings(
                    symbol,
                    exchange,
                    end=inp.observation_date,
                )
                for f in filings:
                    if f.filing_date <= inp.observation_date:
                        doc_type = _map_filing_type(f.filing_type)
                        if inp.document_types and doc_type not in inp.document_types:
                            continue
                        candidates.append(
                            SourceCandidate(
                                source_id=f.filing_id,
                                source_type=doc_type,
                                provider="corporate_filings",
                                title=f.title,
                                publication_date=f.filing_date,
                                source_tier=SourceTier.TIER_1,
                                url=f.url,
                            )
                        )
            except ProviderError:
                logger.warning(
                    "corporate_filings provider failed for %s",
                    symbol,
                )

        seen_keys: set[str] = set()
        unique: list[SourceCandidate] = []
        for c in candidates:
            key = c.url or c.source_id
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c.publication_date or date.min, reverse=True)
        return DiscoverMoatSourcesOutput(candidates=unique[: inp.limit])

    # -- Tool 3: retrieve_document ---------------------------------------------

    async def retrieve_document(
        self,
        inp: RetrieveDocumentInput,
    ) -> RetrieveDocumentOutput:
        if inp.provider == "corporate_filings":
            doc = await self._corporate_filings.get_filing_document(inp.filing_id)
            content_hash = hashlib.sha256(doc.content.encode()).hexdigest()
            return RetrieveDocumentOutput(
                content=doc.content,
                content_type=doc.content_type,
                content_hash=content_hash,
                filing_id=doc.filing_id,
            )

        results = await self._search.search(inp.filing_id, num_results=1)
        content = "" if not results else results[0].snippet

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return RetrieveDocumentOutput(
            content=content,
            content_type="text/snippet",
            content_hash=content_hash,
            filing_id=inp.filing_id,
        )

    # -- Tool 4: get_peer_data -------------------------------------------------

    async def get_peer_data(
        self,
        inp: GetPeerDataInput,
    ) -> GetPeerDataOutput:
        stmt = (
            sa.select(Company)
            .where(
                Company.industry_id == inp.industry_id,
                Company.id != inp.company_id,
                Company.is_active == sa.true(),
            )
            .order_by(Company.market_cap.desc().nulls_last())
            .limit(inp.limit)
        )
        result = await self._session.execute(stmt)
        companies = list(result.scalars().all())

        peers = [
            PeerCompanySummary(
                company_id=c.id,
                name=c.name,
                nse_symbol=c.nse_symbol,
                market_cap=c.market_cap,
            )
            for c in companies
        ]

        return GetPeerDataOutput(peers=peers)

    # -- Tool 5: persist_evidence ----------------------------------------------

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
                extracted_by=MOAT_AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Tool 6: persist_findings ----------------------------------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in MOAT_FINDING_CATEGORIES:
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

    # -- Tool 7: persist_moat_assessments --------------------------------------

    async def persist_moat_assessments(
        self,
        inp: PersistMoatAssessmentsInput,
    ) -> PersistMoatAssessmentsOutput:
        assessment_ids: list[uuid.UUID] = []
        for item in inp.assessments:
            assessment = MoatAssessment(
                company_id=inp.company_id,
                research_run_id=inp.research_run_id,
                moat_type=item.moat_type,
                strength=item.strength,
                durability_years=item.durability_years,
                threats=item.threats,
                competitor_comparison=item.competitor_comparison,
                confidence=item.confidence,
                explanation=item.explanation,
            )
            self._session.add(assessment)
            await self._session.flush()
            await self._session.refresh(assessment)
            assessment_ids.append(assessment.id)

            if item.evidence_ids:
                for evidence_id in item.evidence_ids:
                    await self._session.execute(
                        moat_assessment_evidence.insert().values(
                            moat_assessment_id=assessment.id,
                            evidence_id=evidence_id,
                        )
                    )
                await self._session.flush()

        return PersistMoatAssessmentsOutput(assessment_ids=assessment_ids)

    # -- Internal helper (NOT an agent-facing tool) ----------------------------

    async def create_research_document(
        self,
        company_id: uuid.UUID,
        candidate: SourceCandidate,
        content_hash: str,
    ) -> uuid.UUID:
        doc = ResearchDocument(
            company_id=company_id,
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


def _classify_moat_source(title: str, url: str) -> DocumentType:
    lower_title = title.lower()
    lower_url = url.lower()
    if any(kw in lower_title for kw in ("annual report", "yearly report")):
        return DocumentType.ANNUAL_REPORT
    if any(kw in lower_url for kw in ("sebi.gov", "rbi.org", "nse", "bse")):
        return DocumentType.FILING
    if any(kw in lower_title for kw in ("investor presentation", "investor deck")):
        return DocumentType.INVESTOR_PRESENTATION
    if any(kw in lower_title for kw in ("research report", "equity report", "sector report", "industry report")):
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


def _map_filing_type(filing_type: str) -> DocumentType:
    mapping: dict[str, DocumentType] = {
        "ANNUAL_REPORT": DocumentType.ANNUAL_REPORT,
        "QUARTERLY_RESULT": DocumentType.QUARTERLY_RESULT,
        "INVESTOR_PRESENTATION": DocumentType.INVESTOR_PRESENTATION,
    }
    return mapping.get(filing_type.upper(), DocumentType.FILING)
