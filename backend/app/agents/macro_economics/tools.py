"""Tool implementations for the Macro Economics Agent.

Each public method corresponds to one of the 8 architecture-defined tools
(§21 of ``docs/architecture/phase-13-macro-economics-agent.md``):

  1. load_macro_context          — DB + MacroDataProvider: company context + indicator snapshots
  2. discover_macro_sources      — Provider: SearchProvider + NewsProvider
  3. retrieve_document           — Provider: document retrieval with content hashing
  4. create_research_document    — DB write: document registration (internal helper)
  5. persist_evidence            — DB write: evidence records
  6. persist_findings            — DB write: research findings with macro category validation
  7. persist_macro_indicators    — DB write: MacroIndicator ORM records (NEW)
  8. compute_indicator_trends    — Pure computation: deterministic Decimal trends (NEW)

Provider dependencies (§22): MacroDataProvider, SearchProvider, NewsProvider.
LLMProvider belongs at the agent level (Phase 13.4), not here.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.contracts import (
    MACRO_AGENT_NAME,
    MACRO_DIMENSIONS,
    MACRO_FINDING_CATEGORIES,
    ComputeIndicatorTrendsInput,
    ComputeIndicatorTrendsOutput,
    DiscoverMacroSourcesInput,
    DiscoverMacroSourcesOutput,
    FindingSummary,
    IndicatorTrend,
    LoadMacroContextInput,
    LoadMacroContextOutput,
    MacroIndicatorSnapshot,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    PersistMacroIndicatorsInput,
    PersistMacroIndicatorsOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SourceCandidate,
)
from app.agents.macro_economics.exceptions import CompanyNotFoundForMacroError
from app.models.analysis import MacroIndicator
from app.models.company import Company
from app.models.enums import (
    DocumentType,
    ResearchRunStatus,
    SourceTier,
)
from app.models.research import Evidence, ResearchDocument
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    MacroDataProvider,
    NewsProvider,
    SearchProvider,
)
from app.schemas.research_run import ResearchFindingCreate
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_STABLE_THRESHOLD_RATE = Decimal("0.50")
_STABLE_THRESHOLD_LEVEL_PCT = Decimal("0.5")
_PCT_SCALE = Decimal("100")
_PCT_QUANTIZE = Decimal("0.0001")

_DIMENSION_SEARCH_TEMPLATES: dict[str, list[str]] = {
    "monetary_policy": [
        "{company} RBI repo rate monetary policy impact",
        "India monetary policy interest rate {sector}",
    ],
    "inflation": [
        "{company} inflation CPI WPI impact",
        "India inflation {sector} input cost",
    ],
    "fiscal_policy": [
        "{company} government budget fiscal policy",
        "India fiscal policy tax {sector}",
    ],
    "currency": [
        "{company} rupee exchange rate INR USD impact",
        "India currency {sector} import export",
    ],
    "gdp_growth": [
        "{company} GDP economic growth India",
        "India GDP growth {sector} outlook",
    ],
    "trade_policy": [
        "{company} trade policy tariff import duty",
        "India trade policy {sector}",
    ],
    "regulatory": [
        "{company} SEBI RBI regulation compliance",
        "India regulatory {sector} policy",
    ],
    "commodities": [
        "{company} commodity price crude oil metals",
        "India commodity {sector} raw material cost",
    ],
}


class MacroEconomicsTools:
    """Implements the 8 architecture-defined tools for the Macro Economics Agent.

    Provider dependencies are limited to MacroDataProvider, SearchProvider,
    and NewsProvider per architecture §22. LLMProvider belongs at the
    MacroEconomicsAgent level (Phase 13.4), not here.

    Also provides the ``create_research_document`` internal helper.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        macro_data: MacroDataProvider,
        search: SearchProvider,
        news: NewsProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._macro_data = macro_data
        self._search = search
        self._news = news

    # -- Tool 1: load_macro_context -------------------------------------------

    async def load_macro_context(
        self,
        inp: LoadMacroContextInput,
    ) -> LoadMacroContextOutput:
        """Load company profile, prior findings, and macro indicator snapshots.

        Queries the DB for the company record and existing findings from
        prior phases (8-12). Queries MacroDataProvider for available
        indicators and latest snapshots. Provider failure is degraded,
        not fatal — the agent proceeds with search-only data.
        """
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundForMacroError(str(inp.company_id))

        company_name = company.name
        sectors: list[str] = []
        if company.sector is not None:
            sectors.append(company.sector.name)
        if company.industry is not None and (
            company.sector is None or company.industry.name != company.sector.name
        ):
            sectors.append(company.industry.name)

        exchange = ""
        if company.nse_symbol:
            exchange = "NSE"
        elif company.bse_code:
            exchange = "BSE"

        # Prior findings from completed research runs (Phases 8-12)
        prior_findings: list[FindingSummary] = []
        prior_runs = await self._run_service.get_runs_for_company(
            inp.company_id,
            limit=5,
        )
        completed_runs = [
            r
            for r in prior_runs
            if r.status in (ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL)
        ]
        for run in completed_runs[:3]:
            findings = await self._run_service.get_findings(run.id)
            for f in findings:
                prior_findings.append(
                    FindingSummary(
                        finding_id=f.id,
                        category=f.category,
                        finding_type=f.finding_type,
                        content=f.content,
                        confidence=f.confidence,
                    )
                )

        # MacroDataProvider queries
        from app.providers.types import MacroIndicatorInfo

        available_indicators: list[MacroIndicatorInfo] = []
        indicator_snapshots: list[MacroIndicatorSnapshot] = []
        unavailable_dimensions: list[str] = []

        try:
            available_indicators = await self._macro_data.list_indicators()
        except ProviderError as exc:
            logger.warning("MacroDataProvider.list_indicators failed: %s", exc)

        for indicator in available_indicators:
            try:
                series = await self._macro_data.get_indicator(
                    indicator.indicator_id,
                    end=inp.observation_date,
                )
                valid_points = [
                    dp for dp in series.data_points if dp.date <= inp.observation_date
                ]
                if valid_points:
                    latest = max(valid_points, key=lambda dp: dp.date)
                    indicator_snapshots.append(
                        MacroIndicatorSnapshot(
                            indicator_id=series.indicator_id,
                            name=series.name,
                            value=latest.value,
                            unit=series.unit,
                            as_of_date=latest.date,
                            source=indicator.source,
                        )
                    )
            except ProviderError as exc:
                logger.warning(
                    "MacroDataProvider.get_indicator(%s) failed: %s",
                    indicator.indicator_id,
                    exc,
                )

        if not indicator_snapshots:
            unavailable_dimensions = list(MACRO_DIMENSIONS)

        return LoadMacroContextOutput(
            company_name=company_name,
            sectors=sectors,
            exchange=exchange,
            prior_findings=prior_findings,
            available_indicators=available_indicators,
            indicator_snapshots=indicator_snapshots,
            unavailable_dimensions=unavailable_dimensions,
        )

    # -- Tool 2: discover_macro_sources ---------------------------------------

    async def discover_macro_sources(
        self,
        inp: DiscoverMacroSourcesInput,
    ) -> DiscoverMacroSourcesOutput:
        """Search for macro-related documents and news.

        Generates dimension-specific search queries using SearchProvider
        and NewsProvider. Temporal constraint: all results bounded by
        observation_date.
        """
        candidates: list[SourceCandidate] = []
        provider_errors: list[str] = []
        dimensions_covered: set[str] = set()

        company = inp.company_name
        sector = inp.sectors[0] if inp.sectors else ""
        dimensions = inp.dimensions_to_search or list(MACRO_DIMENSIONS)

        for dim in dimensions:
            templates = _DIMENSION_SEARCH_TEMPLATES.get(dim, [])
            if not templates:
                templates = [
                    f"{company} {dim.replace('_', ' ')} India",
                    f"India {dim.replace('_', ' ')} {sector}",
                ]
            dim_found = False
            for template in templates:
                query = template.format(company=company, sector=sector)
                try:
                    results = await self._search.search(query, num_results=5)
                    for r in results:
                        doc_type = _classify_macro_source(r.title, r.url)
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
                        dim_found = True
                except ProviderError as exc:
                    provider_errors.append(f"SearchProvider({dim}): {exc}")
                    logger.warning("search provider failed for dim=%s query=%s", dim, query)

            if dim_found:
                dimensions_covered.add(dim)

        # NewsProvider — macro-specific news
        news_query = f"{company} macro economy monetary policy inflation India"
        try:
            articles = await self._news.search_news(
                news_query,
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
            logger.warning("news provider failed for macro query")

        # Dedup by URL/source_id
        seen_keys: set[str] = set()
        unique: list[SourceCandidate] = []
        for c in candidates:
            key = c.url or c.source_id
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c.publication_date or date.min, reverse=True)

        dimensions_still_missing = [
            d for d in dimensions if d not in dimensions_covered
        ]

        return DiscoverMacroSourcesOutput(
            sources=unique,
            dimensions_covered=sorted(dimensions_covered),
            dimensions_still_missing=dimensions_still_missing,
        )

    # -- Tool 3: retrieve_document --------------------------------------------

    async def retrieve_document(
        self,
        inp: RetrieveDocumentInput,
    ) -> RetrieveDocumentOutput:
        """Retrieve document content with content hashing for deduplication."""
        results = await self._search.search(inp.filing_id, num_results=1)
        content = "" if not results else results[0].snippet

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return RetrieveDocumentOutput(
            content=content,
            content_type="text/snippet",
            content_hash=content_hash,
            filing_id=inp.filing_id,
        )

    # -- Tool 4: create_research_document (internal helper) -------------------

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

    # -- Tool 5: persist_evidence ---------------------------------------------

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
                extracted_by=MACRO_AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Tool 6: persist_findings ---------------------------------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        """Persist research findings with macro category validation."""
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in MACRO_FINDING_CATEGORIES:
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

    # -- Tool 7: persist_macro_indicators (NEW) -------------------------------

    async def persist_macro_indicators(
        self,
        inp: PersistMacroIndicatorsInput,
    ) -> PersistMacroIndicatorsOutput:
        """Persist MacroIndicator ORM records with duplicate handling.

        Duplicate detection by (indicator_name, as_of_date, country).
        Existing duplicates are skipped; their IDs are still returned.
        """
        indicator_ids: list[uuid.UUID] = []
        persisted_count = 0

        for snap in inp.snapshots:
            # Check for existing duplicate
            dup_stmt = sa.select(MacroIndicator.id).where(
                MacroIndicator.indicator_name == snap.indicator_id,
                MacroIndicator.as_of_date == snap.as_of_date,
                MacroIndicator.country == inp.country,
            )
            dup_result = await self._session.execute(dup_stmt)
            existing_id = dup_result.scalar_one_or_none()

            if existing_id is not None:
                logger.info(
                    "MacroIndicator %s @ %s already exists, skipping",
                    snap.indicator_id,
                    snap.as_of_date,
                )
                indicator_ids.append(existing_id)
                continue

            record = MacroIndicator(
                indicator_name=snap.indicator_id,
                value=snap.value,
                unit=snap.unit,
                as_of_date=snap.as_of_date,
                source=snap.source,
                country=inp.country,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            indicator_ids.append(record.id)
            persisted_count += 1

        return PersistMacroIndicatorsOutput(
            indicator_ids=indicator_ids,
            persisted_count=persisted_count,
        )

    # -- Tool 8: compute_indicator_trends (NEW) -------------------------------

    @staticmethod
    def compute_indicator_trends(
        inp: ComputeIndicatorTrendsInput,
    ) -> ComputeIndicatorTrendsOutput:
        """Deterministic trend calculation for a time-series indicator.

        Rules (architecture §20):
        1. All calculations use decimal.Decimal, never float.
        2. Percentage changes: 4 decimal places, ROUND_HALF_UP.
        3. Direction threshold: ±0.50 pp for rates, ±0.5% for levels → STABLE.
        4. Insufficient data: < 2 data points → direction is INSUFFICIENT_DATA.
        """
        # Sort data points by date ascending, filter to <= observation_date
        valid_points = [
            (d, v) for d, v in inp.data_points if d <= inp.observation_date
        ]
        valid_points.sort(key=lambda p: p[0])

        if not valid_points:
            return ComputeIndicatorTrendsOutput(
                trend=IndicatorTrend(
                    indicator_id=inp.indicator_id,
                    current_value=Decimal("0"),
                    current_date=inp.observation_date,
                    direction="INSUFFICIENT_DATA",
                    data_points_available=0,
                ),
            )

        current_date, current_value = valid_points[-1]

        if len(valid_points) < 2:
            return ComputeIndicatorTrendsOutput(
                trend=IndicatorTrend(
                    indicator_id=inp.indicator_id,
                    current_value=current_value,
                    current_date=current_date,
                    direction="INSUFFICIENT_DATA",
                    data_points_available=1,
                ),
            )

        prior_date, prior_value = valid_points[-2]
        absolute_change = current_value - prior_value

        # Percentage change = (current - prior) / |prior| × 100
        if prior_value == Decimal("0"):
            percentage_change = None
            direction = "STABLE" if absolute_change == Decimal("0") else (
                "INCREASING" if absolute_change > Decimal("0") else "DECREASING"
            )
        else:
            percentage_change = (
                (absolute_change / abs(prior_value)) * _PCT_SCALE
            ).quantize(_PCT_QUANTIZE, rounding=ROUND_HALF_UP)

            # Direction classification using the rate threshold (§20)
            if abs(percentage_change) <= _STABLE_THRESHOLD_RATE:
                direction = "STABLE"
            elif percentage_change > Decimal("0"):
                direction = "INCREASING"
            else:
                direction = "DECREASING"

        return ComputeIndicatorTrendsOutput(
            trend=IndicatorTrend(
                indicator_id=inp.indicator_id,
                current_value=current_value,
                current_date=current_date,
                prior_value=prior_value,
                prior_date=prior_date,
                absolute_change=absolute_change,
                percentage_change=percentage_change,
                direction=direction,
                data_points_available=len(valid_points),
            ),
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _classify_macro_source(title: str, url: str) -> DocumentType:
    lower_title = title.lower()
    lower_url = url.lower()
    if any(kw in lower_url for kw in ("rbi.org", "sebi.gov", "nse", "bse")):
        return DocumentType.FILING
    if any(kw in lower_title for kw in ("monetary policy", "credit policy", "rbi bulletin")):
        return DocumentType.FILING
    if any(kw in lower_title for kw in ("annual report", "yearly report")):
        return DocumentType.ANNUAL_REPORT
    if any(kw in lower_title for kw in ("research report", "macro report", "economic outlook")):
        return DocumentType.RESEARCH_REPORT
    if any(kw in lower_title for kw in ("news", "article", "economy", "inflation", "gdp")):
        return DocumentType.NEWS
    return DocumentType.RESEARCH_REPORT


def _tier_from_url(url: str) -> SourceTier:
    lower = url.lower()
    if any(domain in lower for domain in ("rbi.org", "sebi.gov", "nse", "bse", "mospi.gov")):
        return SourceTier.TIER_1
    if any(domain in lower for domain in ("ibef.org", "nasscom", "ficci", "cii.in")):
        return SourceTier.TIER_2
    return SourceTier.TIER_3
