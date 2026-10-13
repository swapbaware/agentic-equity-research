"""Tool implementations for the Future Growth & Optionality Agent.

Each public method corresponds to one of the 8 architecture-defined tools
(§21 of ``docs/architecture/phase-12-future-growth-optionality-agent.md``):

  1. load_company_context     — DB query: company + Phase 8/9/10/11 findings
  2. discover_growth_sources  — Provider: SearchProvider + NewsProvider + CorporateFilingsProvider
  3. retrieve_document        — Provider: document retrieval with content hashing
  4. persist_evidence         — DB write: evidence records
  5. persist_findings         — DB write: research findings with growth category validation
  6. persist_growth_opportunities — DB write: GrowthOpportunity + evidence junction
  7. persist_scores           — DB write: Growth Quality + Future Optionality dimension scores
  8. create_research_document — DB write: document registration (internal helper)

Provider dependencies (§22): SearchProvider, NewsProvider, CorporateFilingsProvider.
LLMProvider belongs at the agent level (Phase 12.4), not here.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.contracts import (
    GROWTH_AGENT_NAME,
    GROWTH_FINDING_CATEGORIES,
    DiscoverGrowthSourcesInput,
    DiscoverGrowthSourcesOutput,
    FindingSummary,
    LoadGrowthContextInput,
    LoadGrowthContextOutput,
    ManagementStatementSummary,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    PersistGrowthOpportunitiesInput,
    PersistGrowthOpportunitiesOutput,
    PersistGrowthScoresInput,
    PersistGrowthScoresOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
)
from app.agents.future_growth.exceptions import CompanyNotFoundForGrowthError
from app.models.analysis import GrowthOpportunity, growth_opportunity_evidence
from app.models.company import Company
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    GrowthCategory,
    GrowthMaturity,
    ManagementStatementCategory,
    ResearchRunStatus,
    ScoreDimension,
    SourceTier,
)
from app.models.research import Evidence, ManagementStatement, ResearchDocument, ResearchFinding
from app.models.thesis import CompanyScore
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

_GROWTH_RELATED_STATEMENT_CATEGORIES: frozenset[ManagementStatementCategory] = frozenset(
    {
        ManagementStatementCategory.REVENUE_GUIDANCE,
        ManagementStatementCategory.CAPEX_PLAN,
        ManagementStatementCategory.EXPANSION,
        ManagementStatementCategory.PRODUCT_LAUNCH,
    }
)


class FutureGrowthTools:
    """Implements the 8 architecture-defined tools for the Future Growth & Optionality Agent.

    Provider dependencies are limited to SearchProvider, NewsProvider, and
    CorporateFilingsProvider per architecture §22. LLMProvider belongs at the
    FutureGrowthAgent level (Phase 12.4), not here.

    Also provides the ``create_research_document`` internal helper.
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
        inp: LoadGrowthContextInput,
    ) -> LoadGrowthContextOutput:
        """Load company profile and existing Phase 8/9/10/11 findings.

        Phase 8 (company) and Phase 9 (industry) are primary inputs.
        Phase 10 (moat) and Phase 11 (management statements) are optional context.
        """
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundForGrowthError(str(inp.company_id))

        company_name = company.name
        nse_symbol = company.nse_symbol
        bse_code = company.bse_code
        industry_name: str | None = None
        if company.industry is not None:
            industry_name = company.industry.name

        company_findings: list[FindingSummary] = []
        industry_findings: list[FindingSummary] = []
        moat_context: str | None = None

        # Phase 8: Company Research findings
        company_runs = await self._run_service.get_runs_for_company(
            inp.company_id,
            limit=1,
        )
        completed_company_runs = [
            r for r in company_runs if r.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
        ]
        if completed_company_runs:
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

        # Phase 9: Industry Research findings
        industry_id = company.industry_id
        if industry_id is not None:
            industry_runs = await self._run_service.get_runs_for_industry(
                industry_id,
                limit=1,
            )
            completed_industry_runs = [
                r for r in industry_runs if r.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
            ]
            if completed_industry_runs:
                latest_industry_run = completed_industry_runs[0]
                ind_findings = await self._run_service.get_findings(latest_industry_run.id)
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

        # Phase 10: Moat context (optional — §6 says failure does not block)
        moat_findings_stmt = (
            sa.select(ResearchFinding)
            .where(
                ResearchFinding.research_run_id.in_(
                    sa.select(sa.column("id"))
                    .select_from(sa.table("research_run", schema="research"))
                    .where(sa.column("company_id") == inp.company_id)
                ),
                ResearchFinding.agent_name == "competitive_moat_agent",
            )
            .order_by(ResearchFinding.id.desc())
            .limit(5)
        )
        try:
            moat_result = await self._session.execute(moat_findings_stmt)
            moat_findings = list(moat_result.scalars().all())
            if moat_findings:
                moat_summaries = [f.content for f in moat_findings]
                moat_context = " | ".join(moat_summaries)
        except Exception:
            logger.warning("Failed to load moat context for company %s", inp.company_id)

        # Phase 11: Management statements related to growth (optional)
        management_statements: list[ManagementStatementSummary] = []
        try:
            stmt = (
                sa.select(ManagementStatement)
                .where(
                    ManagementStatement.company_id == inp.company_id,
                    ManagementStatement.category.in_(list(_GROWTH_RELATED_STATEMENT_CATEGORIES)),
                )
                .order_by(ManagementStatement.statement_date.desc())
            )
            ms_result = await self._session.execute(stmt)
            ms_records = list(ms_result.scalars().all())
            for ms in ms_records:
                management_statements.append(
                    ManagementStatementSummary(
                        id=ms.id,
                        statement_date=ms.statement_date,
                        statement=ms.statement,
                        category=ms.category,
                        expected_outcome=ms.expected_outcome,
                        expected_timeframe=None,
                        status=ms.status,
                    )
                )
        except Exception:
            logger.warning("Failed to load management statements for company %s", inp.company_id)

        # Existing growth opportunities from prior runs
        existing_opportunities: list[uuid.UUID] = []
        try:
            opp_stmt = (
                sa.select(GrowthOpportunity.id)
                .where(GrowthOpportunity.company_id == inp.company_id)
                .order_by(GrowthOpportunity.id.desc())
            )
            opp_result = await self._session.execute(opp_stmt)
            existing_opportunities = list(opp_result.scalars().all())
        except Exception:
            logger.warning("Failed to load existing opportunities for company %s", inp.company_id)

        return LoadGrowthContextOutput(
            company_name=company_name,
            industry_name=industry_name,
            nse_symbol=nse_symbol,
            bse_code=bse_code,
            company_findings=company_findings,
            industry_findings=industry_findings,
            moat_context=moat_context,
            management_statements=management_statements,
            existing_opportunities=existing_opportunities,
        )

    # -- Tool 2: discover_growth_sources ---------------------------------------

    async def discover_growth_sources(
        self,
        inp: DiscoverGrowthSourcesInput,
    ) -> DiscoverGrowthSourcesOutput:
        """Search for growth-related documents and news using SearchProvider,
        NewsProvider, and CorporateFilingsProvider.

        Temporal constraint: all queries bounded by observation_date.
        """
        candidates: list[SourceCandidate] = []
        provider_errors: list[str] = []

        # SearchProvider queries — growth-focused
        search_queries = [
            f"{inp.company_name} growth strategy expansion plans",
            f"{inp.company_name} new products new markets partnerships",
        ]
        if inp.industry_name:
            search_queries.append(f"{inp.company_name} {inp.industry_name} growth opportunities")
        for theme in inp.search_themes[:3]:
            search_queries.append(f"{inp.company_name} {theme.replace('_', ' ')}")

        for query in search_queries:
            try:
                results = await self._search.search(query, num_results=5)
                for r in results:
                    doc_type = _classify_growth_source(r.title, r.url)
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
            except ProviderError as exc:
                provider_errors.append(f"SearchProvider: {exc}")
                logger.warning("search provider failed for query: %s", query)

        # NewsProvider — growth-related news
        try:
            articles = await self._news.search_news(
                f"{inp.company_name} expansion capacity partnership launch",
                start=None,
                end=inp.observation_date,
                limit=10,
            )
            for a in articles:
                pub_date = a.published_at.date()
                if pub_date <= inp.observation_date:
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
        except ProviderError as exc:
            provider_errors.append(f"NewsProvider: {exc}")
            logger.warning("news provider failed for company: %s", inp.company_name)

        # CorporateFilingsProvider — annual reports, investor presentations
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
            except ProviderError as exc:
                provider_errors.append(f"CorporateFilingsProvider: {exc}")
                logger.warning("corporate_filings provider failed for %s", symbol)

        # Dedup by URL/source_id
        seen_keys: set[str] = set()
        unique: list[SourceCandidate] = []
        for c in candidates:
            key = c.url or c.source_id
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c.publication_date or date.min, reverse=True)

        return DiscoverGrowthSourcesOutput(
            sources=unique,
            provider_errors=provider_errors,
        )

    # -- Tool 3: retrieve_document ---------------------------------------------

    async def retrieve_document(
        self,
        inp: RetrieveDocumentInput,
    ) -> RetrieveDocumentOutput:
        """Retrieve document content with content hashing for deduplication."""
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

    # -- Tool 4: persist_evidence ----------------------------------------------

    async def persist_evidence(
        self,
        inp: PersistEvidenceInput,
    ) -> PersistEvidenceOutput:
        """Persist extracted evidence records linked to a research document."""
        evidence_ids: list[uuid.UUID] = []
        for ev in inp.evidences:
            record = Evidence(
                document_id=inp.document_id,
                evidence_type=ev.evidence_type,
                claim=ev.claim,
                context=ev.context,
                page_or_section=ev.page_or_section,
                confidence=ev.confidence,
                extracted_by=GROWTH_AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Tool 5: persist_findings ----------------------------------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        """Persist research findings with growth category validation."""
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in GROWTH_FINDING_CATEGORIES:
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

    # -- Tool 6: persist_growth_opportunities ----------------------------------

    async def persist_growth_opportunities(
        self,
        inp: PersistGrowthOpportunitiesInput,
    ) -> PersistGrowthOpportunitiesOutput:
        """Persist GrowthOpportunity records with evidence junction table linking.

        Each draft opportunity is mapped to the ORM model with enum validation.
        Evidence linking uses the ``growth_opportunity_evidence`` junction table.
        Duplicate detection by (company_id, research_run_id, opportunity_name).
        """
        opportunity_ids: list[uuid.UUID] = []

        for draft in inp.opportunities:
            # Validate enum values
            try:
                category = GrowthCategory(draft.category.upper())
            except ValueError:
                logger.warning(
                    "Invalid GrowthCategory '%s' for opportunity '%s', skipping",
                    draft.category,
                    draft.opportunity_name,
                )
                continue

            try:
                maturity = GrowthMaturity(draft.maturity.upper())
            except ValueError:
                logger.warning(
                    "Invalid GrowthMaturity '%s' for opportunity '%s', skipping",
                    draft.maturity,
                    draft.opportunity_name,
                )
                continue

            try:
                confidence = ConfidenceLevel(draft.confidence.upper())
            except ValueError:
                confidence = ConfidenceLevel.LOW

            # Duplicate check: same company + run + name
            dup_stmt = sa.select(GrowthOpportunity.id).where(
                GrowthOpportunity.company_id == inp.company_id,
                GrowthOpportunity.research_run_id == inp.research_run_id,
                GrowthOpportunity.opportunity_name == draft.opportunity_name,
            )
            dup_result = await self._session.execute(dup_stmt)
            existing = dup_result.scalar_one_or_none()
            if existing is not None:
                logger.info(
                    "Opportunity '%s' already exists for run %s, skipping duplicate",
                    draft.opportunity_name,
                    inp.research_run_id,
                )
                opportunity_ids.append(existing)
                continue

            # Build risks JSON with TAM metadata
            risks_json: dict[str, object] = {}
            if draft.risks:
                risks_json["risk_factors"] = list(draft.risks)
            if draft.tam_methodology:
                risks_json["tam_methodology"] = draft.tam_methodology
            if draft.tam_low is not None:
                risks_json["tam_low"] = str(draft.tam_low)
            if draft.tam_high is not None:
                risks_json["tam_high"] = str(draft.tam_high)

            record = GrowthOpportunity(
                company_id=inp.company_id,
                research_run_id=inp.research_run_id,
                opportunity_name=draft.opportunity_name,
                category=category,
                maturity=maturity,
                addressable_market=draft.addressable_market,
                timeline_years=draft.timeline_years,
                risks=risks_json if risks_json else None,
                confidence=confidence,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            opportunity_ids.append(record.id)

            # Link evidence via junction table
            if draft.evidence_indices and inp.evidence_ids:
                for idx in draft.evidence_indices:
                    if 0 <= idx < len(inp.evidence_ids):
                        evidence_id = inp.evidence_ids[idx]
                        await self._session.execute(
                            growth_opportunity_evidence.insert().values(
                                growth_opportunity_id=record.id,
                                evidence_id=evidence_id,
                            )
                        )
                await self._session.flush()

        return PersistGrowthOpportunitiesOutput(opportunity_ids=opportunity_ids)

    # -- Tool 7: persist_scores ------------------------------------------------

    async def persist_scores(
        self,
        inp: PersistGrowthScoresInput,
    ) -> PersistGrowthScoresOutput:
        """Persist Growth Quality and Future Optionality dimension scores.

        Scores are stored as CompanyScore records in thesis.company_score,
        with sub-score components in the JSONB sub_scores column and a
        combined rationale in the explanation column.  The table's unique
        constraint (company_id, research_run_id, dimension) prevents
        duplicate scores; on conflict the existing record is returned.
        """
        gq_record = await self._persist_single_score(
            company_id=inp.company_id,
            research_run_id=inp.research_run_id,
            dimension=ScoreDimension.GROWTH_QUALITY,
            score=inp.growth_quality_score,
            components=inp.growth_quality_components,
        )

        fo_record = await self._persist_single_score(
            company_id=inp.company_id,
            research_run_id=inp.research_run_id,
            dimension=ScoreDimension.FUTURE_OPTIONALITY,
            score=inp.future_optionality_score,
            components=inp.future_optionality_components,
        )

        return PersistGrowthScoresOutput(
            growth_quality_score_id=gq_record,
            future_optionality_score_id=fo_record,
        )

    async def _persist_single_score(
        self,
        *,
        company_id: uuid.UUID,
        research_run_id: uuid.UUID,
        dimension: ScoreDimension,
        score: int,
        components: Sequence[object],
    ) -> uuid.UUID:
        """Persist one CompanyScore, returning its id.

        If a record for the same (company, run, dimension) already exists
        (unique constraint), the existing id is returned without overwriting.
        """
        from app.agents.contracts import GrowthScoreComponent

        # Check for existing score (idempotency)
        existing_stmt = sa.select(CompanyScore.id).where(
            CompanyScore.company_id == company_id,
            CompanyScore.research_run_id == research_run_id,
            CompanyScore.dimension == dimension,
        )
        existing_result = await self._session.execute(existing_stmt)
        existing_id = existing_result.scalar_one_or_none()
        if existing_id is not None:
            return existing_id

        # Build sub_scores JSONB from components
        sub_scores: dict[str, object] | None = None
        typed_components: list[GrowthScoreComponent] = [c for c in components if isinstance(c, GrowthScoreComponent)]
        if typed_components:
            sub_scores = {
                "components": [
                    {"name": c.component_name, "score": c.score, "rationale": c.rationale} for c in typed_components
                ],
            }

        # Build explanation from component rationales
        if typed_components:
            explanation = "; ".join(f"{c.component_name}: {c.rationale}" for c in typed_components)
        else:
            explanation = f"{dimension.value} score: {score}"

        record = CompanyScore(
            company_id=company_id,
            research_run_id=research_run_id,
            dimension=dimension,
            score=score,
            sub_scores=sub_scores,
            explanation=explanation,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return record.id

    # -- Tool 8: create_research_document (internal helper) --------------------

    async def create_research_document(
        self,
        company_id: uuid.UUID,
        candidate: SourceCandidate,
        content_hash: str,
    ) -> uuid.UUID:
        """Register a document for evidence linking. Not agent-facing."""
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


def _classify_growth_source(title: str, url: str) -> DocumentType:
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
    if any(kw in lower_title for kw in ("news", "article", "expansion", "partnership", "launch")):
        return DocumentType.NEWS
    return DocumentType.RESEARCH_REPORT


def _tier_from_url(url: str) -> SourceTier:
    lower = url.lower()
    if any(domain in lower for domain in ("nse", "bse", "sebi.gov")):
        return SourceTier.TIER_1
    if any(domain in lower for domain in ("rbi.org", "ibef.org", "nasscom", "ficci")):
        return SourceTier.TIER_2
    return SourceTier.TIER_3


def _map_filing_type(filing_type: str) -> DocumentType:
    mapping: dict[str, DocumentType] = {
        "ANNUAL_REPORT": DocumentType.ANNUAL_REPORT,
        "QUARTERLY_RESULT": DocumentType.QUARTERLY_RESULT,
        "INVESTOR_PRESENTATION": DocumentType.INVESTOR_PRESENTATION,
    }
    return mapping.get(filing_type.upper(), DocumentType.FILING)
