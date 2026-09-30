"""Tool implementations for the Company Research Agent.

Each public method corresponds to one of the 8 tool contracts defined in
``app.agents.contracts``.  Tools depend on provider Protocol interfaces
and the database session — never on concrete provider implementations.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.company_research.exceptions import CompanyNotFoundError
from app.agents.contracts import (
    AGENT_NAME,
    FINDING_CATEGORIES,
    DiscoverSourcesInput,
    DiscoverSourcesOutput,
    FinancialStatementResult,
    GetCompanyProfileInput,
    GetCompanyProfileOutput,
    GetFinancialSummaryInput,
    GetFinancialSummaryOutput,
    NewsArticleResult,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SearchCompanyNewsInput,
    SearchCompanyNewsOutput,
    SourceCandidate,
    ValidateCompanyInput,
    ValidateCompanyOutput,
)
from app.models.company import Company
from app.models.enums import (
    DocumentType,
    SourceTier,
)
from app.models.research import Evidence, ResearchDocument
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateFilingsProvider,
    FinancialDataProvider,
    LLMProvider,
    NewsProvider,
    TranscriptProvider,
)
from app.schemas.research_run import ResearchFindingCreate
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CompanyResearchTools:
    """Implements the 8 tool contracts for the Company Research Agent.

    All provider access goes through Protocol interfaces injected at
    construction time.  The ``session`` is used for direct DB queries
    (company lookup, evidence persistence) that have no dedicated
    provider.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        corporate_filings: CorporateFilingsProvider,
        financial_data: FinancialDataProvider,
        news: NewsProvider,
        transcript: TranscriptProvider,
        llm: LLMProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._corporate_filings = corporate_filings
        self._financial_data = financial_data
        self._news = news
        self._transcript = transcript
        self._llm = llm

    # -- Tool 1: validate_company -----------------------------------------------

    async def validate_company(
        self, inp: ValidateCompanyInput,
    ) -> ValidateCompanyOutput:
        stmt = sa.select(Company)
        if inp.identifier_type.value == "NSE_SYMBOL":
            stmt = stmt.where(Company.nse_symbol == inp.identifier)
        elif inp.identifier_type.value == "BSE_CODE":
            stmt = stmt.where(Company.bse_code == inp.identifier)
        else:
            stmt = stmt.where(Company.isin == inp.identifier)

        result = await self._session.execute(stmt)
        company = result.scalar_one_or_none()

        if company is None:
            raise CompanyNotFoundError(inp.identifier, inp.identifier_type.value)

        sector_name: str | None = None
        industry_name: str | None = None
        if company.sector is not None:
            sector_name = company.sector.name
        if company.industry is not None:
            industry_name = company.industry.name

        return ValidateCompanyOutput(
            company_id=company.id,
            name=company.name,
            nse_symbol=company.nse_symbol,
            bse_code=company.bse_code,
            isin=company.isin,
            sector=sector_name,
            industry=industry_name,
        )

    # -- Tool 2: discover_sources -----------------------------------------------

    async def discover_sources(
        self, inp: DiscoverSourcesInput,
    ) -> DiscoverSourcesOutput:
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundError(str(inp.company_id), "UUID")

        symbol = company.nse_symbol or company.bse_code or ""
        exchange = "NSE" if company.nse_symbol else "BSE"
        candidates: list[SourceCandidate] = []

        try:
            filings = await self._corporate_filings.get_filings(
                symbol, exchange, end=inp.observation_date,
            )
            for f in filings:
                if f.filing_date <= inp.observation_date:
                    doc_type = _map_filing_type(f.filing_type)
                    if inp.document_types and doc_type not in inp.document_types:
                        continue
                    candidates.append(SourceCandidate(
                        source_id=f.filing_id,
                        source_type=doc_type,
                        provider="corporate_filings",
                        title=f.title,
                        publication_date=f.filing_date,
                        source_tier=SourceTier.TIER_1,
                        url=f.url,
                    ))
        except ProviderError:
            logger.warning("corporate_filings provider failed for %s", symbol)

        try:
            transcripts = await self._transcript.list_transcripts(symbol, exchange)
            for t in transcripts:
                if t.date <= inp.observation_date:
                    if inp.document_types and DocumentType.TRANSCRIPT not in inp.document_types:
                        continue
                    candidates.append(SourceCandidate(
                        source_id=f"{t.symbol}_{t.quarter}_{t.year}",
                        source_type=DocumentType.TRANSCRIPT,
                        provider="transcript",
                        title=t.title,
                        publication_date=t.date,
                        source_tier=SourceTier.TIER_1,
                    ))
        except ProviderError:
            logger.warning("transcript provider failed for %s", symbol)

        try:
            articles = await self._news.get_company_news(
                symbol, exchange, limit=inp.limit,
            )
            for a in articles:
                pub_date = a.published_at.date()
                if pub_date <= inp.observation_date:
                    if inp.document_types and DocumentType.NEWS not in inp.document_types:
                        continue
                    candidates.append(SourceCandidate(
                        source_id=a.url,
                        source_type=DocumentType.NEWS,
                        provider="news",
                        title=a.title,
                        publication_date=pub_date,
                        source_tier=SourceTier.TIER_3,
                        url=a.url,
                    ))
        except ProviderError:
            logger.warning("news provider failed for %s", symbol)

        candidates.sort(key=lambda c: c.publication_date, reverse=True)
        return DiscoverSourcesOutput(candidates=candidates[: inp.limit])

    # -- Tool 3: retrieve_document -----------------------------------------------

    async def retrieve_document(
        self, inp: RetrieveDocumentInput,
    ) -> RetrieveDocumentOutput:
        doc = await self._corporate_filings.get_filing_document(inp.filing_id)
        content_hash = hashlib.sha256(doc.content.encode()).hexdigest()
        return RetrieveDocumentOutput(
            content=doc.content,
            content_type=doc.content_type,
            content_hash=content_hash,
            filing_id=doc.filing_id,
        )

    # -- Tool 4: get_company_profile --------------------------------------------

    async def get_company_profile(
        self, inp: GetCompanyProfileInput,
    ) -> GetCompanyProfileOutput:
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundError(str(inp.company_id), "UUID")

        sector_name: str | None = None
        industry_name: str | None = None
        sector_id: uuid.UUID | None = None
        industry_id: uuid.UUID | None = None
        if company.sector is not None:
            sector_name = company.sector.name
            sector_id = company.sector.id
        if company.industry is not None:
            industry_name = company.industry.name
            industry_id = company.industry.id

        return GetCompanyProfileOutput(
            name=company.name,
            nse_symbol=company.nse_symbol,
            bse_code=company.bse_code,
            isin=company.isin,
            sector_id=sector_id,
            sector_name=sector_name,
            industry_id=industry_id,
            industry_name=industry_name,
            market_cap=company.market_cap,
            incorporation_date=company.incorporation_date,
            listing_date=company.listing_date,
            website=company.website,
            description=company.description,
            registered_address=company.registered_address,
            business_segments=company.business_segments,
            major_products=company.major_products,
            geographies=company.geographies,
            is_active=company.is_active,
        )

    # -- Tool 5: search_company_news --------------------------------------------

    async def search_company_news(
        self, inp: SearchCompanyNewsInput,
    ) -> SearchCompanyNewsOutput:
        articles = await self._news.get_company_news(
            inp.symbol, inp.exchange, limit=inp.limit,
        )
        results: list[NewsArticleResult] = []
        for a in articles:
            if a.published_at.date() <= inp.observation_date:
                results.append(NewsArticleResult(
                    title=a.title,
                    url=a.url,
                    source=a.source,
                    published_at=a.published_at,
                    summary=a.summary,
                ))
        return SearchCompanyNewsOutput(articles=results)

    # -- Tool 6: get_financial_summary ------------------------------------------

    async def get_financial_summary(
        self, inp: GetFinancialSummaryInput,
    ) -> GetFinancialSummaryOutput:
        statements_out: list[FinancialStatementResult] = []
        for stmt_type in ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"):
            try:
                stmts = await self._financial_data.get_financial_statements(
                    inp.symbol, inp.exchange, stmt_type, "ANNUAL",
                )
                for s in stmts[: inp.periods]:
                    statements_out.append(FinancialStatementResult(
                        symbol=s.symbol,
                        exchange=s.exchange,
                        statement_type=s.statement_type,
                        period_type=s.period_type,
                        period=s.period,
                        filing_date=s.filing_date,
                        currency=s.currency,
                        line_items=s.line_items,
                    ))
            except ProviderError:
                logger.warning(
                    "financial_data provider failed for %s/%s",
                    inp.symbol, stmt_type,
                )
        return GetFinancialSummaryOutput(statements=statements_out)

    # -- Tool 7: persist_evidence -----------------------------------------------

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
                extracted_by=AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Tool 8: persist_findings -----------------------------------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in FINDING_CATEGORIES:
                rejected.append(RejectedFinding(
                    index=i,
                    reason=f"Invalid category: {f.category}",
                ))
                continue
            finding_defs.append(ResearchFindingCreate(
                agent_name=f.agent_name,
                finding_type=f.finding_type,
                category=f.category,
                content=f.content,
                confidence=f.confidence,
                observation_date=f.observation_date,
                source_publication_date=f.source_publication_date,
            ))

        finding_ids: list[uuid.UUID] = []
        if finding_defs:
            persisted = await self._run_service.record_findings(
                inp.run_id, inp.execution_id, finding_defs,
            )
            finding_ids = [f.id for f in persisted]

        return PersistFindingsOutput(
            finding_ids=finding_ids,
            rejected=rejected,
        )

    # -- Helper: create ResearchDocument record ---------------------------------

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


def _map_filing_type(filing_type: str) -> DocumentType:
    mapping: dict[str, DocumentType] = {
        "ANNUAL_REPORT": DocumentType.ANNUAL_REPORT,
        "QUARTERLY_RESULT": DocumentType.QUARTERLY_RESULT,
        "INVESTOR_PRESENTATION": DocumentType.INVESTOR_PRESENTATION,
    }
    return mapping.get(filing_type.upper(), DocumentType.FILING)
