"""Tool implementations for the Management & Governance Agent.

Each public method corresponds to one of the 9 agent-facing tool contracts
defined in ``app.agents.contracts`` (see architecture §27):

  1. load_company_context
  2. discover_governance_sources
  3. retrieve_document
  4. get_shareholding_data
  5. get_corporate_actions
  6. persist_evidence
  7. persist_findings
  8. persist_management_statements
  9. persist_shareholding
  10. persist_governance_data (tool 9 in the count; listed as the 5th new tool)

Internal helper (NOT agent-facing): create_research_document.

Provider dependencies (§28): ShareholdingProvider, CorporateFilingsProvider,
CorporateActionsProvider only. SearchProvider and NewsProvider are NOT used.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa

from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_FINDING_CATEGORIES,
    CorporateActionSnapshot,
    DiscoverGovernanceSourcesInput,
    DiscoverGovernanceSourcesOutput,
    FindingSummary,
    GetCorporateActionsInput,
    GetCorporateActionsOutput,
    GetShareholdingInput,
    GetShareholdingOutput,
    LoadGovernanceContextInput,
    LoadGovernanceContextOutput,
    ManagementStatementSummary,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    PersistGovernanceDataInput,
    PersistGovernanceDataOutput,
    PersistShareholdingInput,
    PersistShareholdingOutput,
    PersistStatementsInput,
    PersistStatementsOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    ShareholdingSnapshot,
    SourceCandidate,
)
from app.agents.management_governance.exceptions import (
    CompanyNotFoundForGovernanceError,
)
from app.models.company import Company
from app.models.enums import (
    CorporateActionType,
    DocumentType,
    ManagementStatementCategory,
    ManagementStatementStatus,
    ResearchRunStatus,
    SourceTier,
)
from app.models.governance import CorporateAction, PromoterPledge, Shareholding
from app.models.research import Evidence, ManagementStatement, ResearchDocument
from app.providers.errors import ProviderError
from app.providers.interfaces import (
    CorporateActionsProvider,
    CorporateFilingsProvider,
    ShareholdingProvider,
)
from app.schemas.research_run import ResearchFindingCreate
from app.services.research_run import ResearchRunService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Valid status transitions per §10 ManagementStatement lifecycle
_VALID_TRANSITIONS: dict[ManagementStatementStatus, frozenset[ManagementStatementStatus]] = {
    ManagementStatementStatus.PENDING: frozenset(
        {
            ManagementStatementStatus.MET,
            ManagementStatementStatus.PARTIALLY_MET,
            ManagementStatementStatus.MISSED,
            ManagementStatementStatus.UNKNOWN,
        }
    ),
    ManagementStatementStatus.UNKNOWN: frozenset(
        {
            ManagementStatementStatus.MET,
            ManagementStatementStatus.PARTIALLY_MET,
            ManagementStatementStatus.MISSED,
        }
    ),
    ManagementStatementStatus.MET: frozenset(),
    ManagementStatementStatus.PARTIALLY_MET: frozenset(),
    ManagementStatementStatus.MISSED: frozenset(),
}


class ManagementGovernanceTools:
    """Implements the 9 agent-facing tool contracts for the Management & Governance Agent.

    Provider dependencies are limited to ShareholdingProvider,
    CorporateFilingsProvider, and CorporateActionsProvider per architecture §28.
    LLMProvider belongs at the agent level, not here.

    Also provides the ``create_research_document`` internal helper.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_service: ResearchRunService,
        corporate_filings: CorporateFilingsProvider,
        shareholding: ShareholdingProvider,
        corporate_actions: CorporateActionsProvider,
    ) -> None:
        self._session = session
        self._run_service = run_service
        self._corporate_filings = corporate_filings
        self._shareholding = shareholding
        self._corporate_actions = corporate_actions

    # -- Tool 1: load_company_context ------------------------------------------

    async def load_company_context(
        self,
        inp: LoadGovernanceContextInput,
    ) -> LoadGovernanceContextOutput:
        company = await self._session.get(Company, inp.company_id)
        if company is None:
            raise CompanyNotFoundForGovernanceError(str(inp.company_id))

        company_name = company.name
        nse_symbol = company.nse_symbol
        bse_code = company.bse_code
        industry_name: str | None = None
        if company.industry is not None:
            industry_name = company.industry.name

        company_findings: list[FindingSummary] = []
        has_company_research = False

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

        stmt = (
            sa.select(ManagementStatement)
            .where(ManagementStatement.company_id == inp.company_id)
            .order_by(ManagementStatement.statement_date.desc())
        )
        result = await self._session.execute(stmt)
        ms_records = list(result.scalars().all())

        existing_statements: list[ManagementStatementSummary] = []
        for ms in ms_records:
            existing_statements.append(
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

        return LoadGovernanceContextOutput(
            company_id=inp.company_id,
            company_name=company_name,
            nse_symbol=nse_symbol,
            bse_code=bse_code,
            industry_name=industry_name,
            company_findings=company_findings,
            has_company_research=has_company_research,
            existing_statements=existing_statements,
        )

    # -- Tool 2: discover_governance_sources -----------------------------------

    async def discover_governance_sources(
        self,
        inp: DiscoverGovernanceSourcesInput,
    ) -> DiscoverGovernanceSourcesOutput:
        filing_candidates: list[SourceCandidate] = []
        shareholding_data: list[ShareholdingSnapshot] = []
        corporate_actions: list[CorporateActionSnapshot] = []
        provider_errors: list[str] = []
        data_gaps: list[str] = []

        symbol = inp.nse_symbol or inp.bse_code or ""
        exchange = "NSE" if inp.nse_symbol else "BSE"

        # Filings via CorporateFilingsProvider
        try:
            filings = await self._corporate_filings.get_filings(
                symbol,
                exchange,
                end=inp.observation_date,
            )
            for f in filings:
                if f.filing_date <= inp.observation_date:
                    doc_type = _map_filing_type(f.filing_type)
                    if inp.filing_types and f.filing_type.upper() not in [ft.upper() for ft in inp.filing_types]:
                        continue
                    filing_candidates.append(
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
            if not filings:
                data_gaps.append("No corporate filings found for this company")
        except ProviderError as exc:
            provider_errors.append(f"CorporateFilingsProvider: {exc}")
            logger.warning("corporate_filings provider failed for %s", symbol)

        # Shareholding via ShareholdingProvider
        start_date = _compute_start_date_for_quarters(
            inp.observation_date,
            inp.shareholding_quarters,
        )
        try:
            patterns = await self._shareholding.get_shareholding_history(
                symbol,
                exchange,
                start=start_date,
                end=inp.observation_date,
            )
            for p in patterns:
                if p.date <= inp.observation_date:
                    promoter_pct = Decimal("0")
                    fii_pct = Decimal("0")
                    dii_pct = Decimal("0")
                    public_pct = Decimal("0")
                    for cat in p.categories:
                        cat_upper = cat.category.upper()
                        if cat_upper == "PROMOTER":
                            promoter_pct = cat.percentage
                        elif cat_upper == "FII":
                            fii_pct = cat.percentage
                        elif cat_upper == "DII":
                            dii_pct = cat.percentage
                        elif cat_upper == "PUBLIC":
                            public_pct = cat.percentage

                    shareholding_data.append(
                        ShareholdingSnapshot(
                            as_of_date=p.date,
                            quarter=p.quarter,
                            promoter_holding_pct=promoter_pct,
                            fii_holding_pct=fii_pct,
                            dii_holding_pct=dii_pct,
                            public_holding_pct=public_pct,
                            total_shares=p.total_shares,
                            pledged_percentage=p.pledged_percentage,
                            source_provider="shareholding",
                            source_tier=1,
                        )
                    )
            if not patterns:
                data_gaps.append("No shareholding data available from provider")
        except ProviderError as exc:
            provider_errors.append(f"ShareholdingProvider: {exc}")
            data_gaps.append("Shareholding data unavailable due to provider error")
            logger.warning("shareholding provider failed for %s", symbol)

        # Corporate actions via CorporateActionsProvider
        ca_start = date(
            inp.observation_date.year - inp.corporate_action_years,
            inp.observation_date.month,
            inp.observation_date.day,
        )
        try:
            actions = await self._corporate_actions.get_corporate_actions(
                symbol,
                exchange,
                start=ca_start,
                end=inp.observation_date,
            )
            for a in actions:
                action_date = a.ex_date or a.record_date
                if action_date is not None and action_date > inp.observation_date:
                    continue
                try:
                    action_type = CorporateActionType(a.action_type.upper())
                except ValueError:
                    action_type = CorporateActionType.DIVIDEND

                corporate_actions.append(
                    CorporateActionSnapshot(
                        action_type=action_type,
                        ex_date=a.ex_date,
                        record_date=a.record_date,
                        details=a.details,
                        value=a.value,
                        source_provider="corporate_actions",
                        source_tier=1,
                    )
                )
            if not actions:
                data_gaps.append("No corporate actions found for the specified period")
        except ProviderError as exc:
            provider_errors.append(f"CorporateActionsProvider: {exc}")
            data_gaps.append("Corporate actions data unavailable due to provider error")
            logger.warning("corporate_actions provider failed for %s", symbol)

        filing_candidates.sort(
            key=lambda c: c.publication_date or date.min,
            reverse=True,
        )

        return DiscoverGovernanceSourcesOutput(
            filing_candidates=filing_candidates,
            shareholding_data=shareholding_data,
            corporate_actions=corporate_actions,
            provider_errors=provider_errors,
            data_gaps=data_gaps,
        )

    # -- Tool 3: retrieve_document ---------------------------------------------

    async def retrieve_document(
        self,
        inp: RetrieveDocumentInput,
    ) -> RetrieveDocumentOutput:
        doc = await self._corporate_filings.get_filing_document(inp.filing_id)
        content_hash = hashlib.sha256(doc.content.encode()).hexdigest()
        return RetrieveDocumentOutput(
            content=doc.content,
            content_type=doc.content_type,
            content_hash=content_hash,
            filing_id=doc.filing_id,
        )

    # -- Tool 4: get_shareholding_data -----------------------------------------

    async def get_shareholding_data(
        self,
        inp: GetShareholdingInput,
    ) -> GetShareholdingOutput:
        symbol = inp.nse_symbol or inp.bse_code or ""
        exchange = "NSE" if inp.nse_symbol else "BSE"

        start_date = _compute_start_date_for_quarters(
            inp.observation_date,
            inp.quarters,
        )

        snapshots: list[ShareholdingSnapshot] = []
        provider_errors: list[str] = []

        try:
            patterns = await self._shareholding.get_shareholding_history(
                symbol,
                exchange,
                start=start_date,
                end=inp.observation_date,
            )
            for p in patterns:
                if p.date <= inp.observation_date:
                    promoter_pct = Decimal("0")
                    fii_pct = Decimal("0")
                    dii_pct = Decimal("0")
                    public_pct = Decimal("0")
                    for cat in p.categories:
                        cat_upper = cat.category.upper()
                        if cat_upper == "PROMOTER":
                            promoter_pct = cat.percentage
                        elif cat_upper == "FII":
                            fii_pct = cat.percentage
                        elif cat_upper == "DII":
                            dii_pct = cat.percentage
                        elif cat_upper == "PUBLIC":
                            public_pct = cat.percentage

                    snapshots.append(
                        ShareholdingSnapshot(
                            as_of_date=p.date,
                            quarter=p.quarter,
                            promoter_holding_pct=promoter_pct,
                            fii_holding_pct=fii_pct,
                            dii_holding_pct=dii_pct,
                            public_holding_pct=public_pct,
                            total_shares=p.total_shares,
                            pledged_percentage=p.pledged_percentage,
                            source_provider="shareholding",
                            source_tier=1,
                        )
                    )
        except ProviderError as exc:
            provider_errors.append(f"ShareholdingProvider: {exc}")
            logger.warning("shareholding provider failed for %s", symbol)

        return GetShareholdingOutput(
            snapshots=snapshots,
            provider_errors=provider_errors,
        )

    # -- Tool 5: get_corporate_actions -----------------------------------------

    async def get_corporate_actions(
        self,
        inp: GetCorporateActionsInput,
    ) -> GetCorporateActionsOutput:
        symbol = inp.nse_symbol or inp.bse_code or ""
        exchange = "NSE" if inp.nse_symbol else "BSE"

        ca_start = date(
            inp.observation_date.year - inp.years,
            inp.observation_date.month,
            inp.observation_date.day,
        )

        actions: list[CorporateActionSnapshot] = []
        provider_errors: list[str] = []

        try:
            records = await self._corporate_actions.get_corporate_actions(
                symbol,
                exchange,
                start=ca_start,
                end=inp.observation_date,
            )
            for r in records:
                action_date = r.ex_date or r.record_date
                if action_date is not None and action_date > inp.observation_date:
                    continue
                try:
                    action_type = CorporateActionType(r.action_type.upper())
                except ValueError:
                    action_type = CorporateActionType.DIVIDEND

                actions.append(
                    CorporateActionSnapshot(
                        action_type=action_type,
                        ex_date=r.ex_date,
                        record_date=r.record_date,
                        details=r.details,
                        value=r.value,
                        source_provider="corporate_actions",
                        source_tier=1,
                    )
                )
        except ProviderError as exc:
            provider_errors.append(f"CorporateActionsProvider: {exc}")
            logger.warning("corporate_actions provider failed for %s", symbol)

        return GetCorporateActionsOutput(
            actions=actions,
            provider_errors=provider_errors,
        )

    # -- Tool 6: persist_evidence ----------------------------------------------

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
                extracted_by=GOVERNANCE_AGENT_NAME,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            evidence_ids.append(record.id)
        return PersistEvidenceOutput(evidence_ids=evidence_ids)

    # -- Tool 7: persist_findings ----------------------------------------------

    async def persist_findings(
        self,
        inp: PersistFindingsInput,
    ) -> PersistFindingsOutput:
        finding_defs: list[ResearchFindingCreate] = []
        rejected: list[RejectedFinding] = []

        for i, f in enumerate(inp.findings):
            if f.category not in GOVERNANCE_FINDING_CATEGORIES:
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

    # -- Tool 8: persist_management_statements ---------------------------------

    async def persist_management_statements(
        self,
        inp: PersistStatementsInput,
    ) -> PersistStatementsOutput:
        created_ids: list[uuid.UUID] = []
        updated_ids: list[uuid.UUID] = []
        rejected_count = 0

        # INSERT new statements
        for new_stmt in inp.new_statements:
            try:
                category = ManagementStatementCategory(new_stmt.category.upper())
            except ValueError:
                rejected_count += 1
                logger.warning("Invalid ManagementStatement category: %s", new_stmt.category)
                continue

            evidence_id: uuid.UUID | None = None
            if inp.evidence_ids and 0 <= new_stmt.evidence_index < len(inp.evidence_ids):
                evidence_id = inp.evidence_ids[new_stmt.evidence_index]

            record = ManagementStatement(
                company_id=inp.company_id,
                statement_date=new_stmt.statement_date,
                statement=new_stmt.statement,
                category=category,
                expected_outcome=new_stmt.expected_outcome,
                source_evidence_id=evidence_id,
                status=ManagementStatementStatus.PENDING,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            created_ids.append(record.id)

        # UPDATE existing statements
        for update in inp.statement_updates:
            try:
                stmt_id = uuid.UUID(update.statement_id)
            except ValueError:
                rejected_count += 1
                logger.warning("Invalid statement_id format: %s", update.statement_id)
                continue

            existing = await self._session.get(ManagementStatement, stmt_id)
            if existing is None:
                rejected_count += 1
                logger.warning("ManagementStatement not found: %s", update.statement_id)
                continue

            try:
                proposed_status = ManagementStatementStatus(update.proposed_status.upper())
            except ValueError:
                rejected_count += 1
                logger.warning("Invalid proposed status: %s", update.proposed_status)
                continue

            current_status = existing.status
            if proposed_status not in _VALID_TRANSITIONS.get(current_status, frozenset()):
                rejected_count += 1
                logger.warning(
                    "Invalid transition %s -> %s for statement %s",
                    current_status,
                    proposed_status,
                    update.statement_id,
                )
                continue

            # Per §10: MET requires outcome_evidence_id
            if proposed_status == ManagementStatementStatus.MET and update.outcome_evidence_index is None:
                rejected_count += 1
                logger.warning(
                    "MET transition requires outcome_evidence_index for statement %s",
                    update.statement_id,
                )
                continue

            outcome_evidence_id: uuid.UUID | None = None
            if (
                update.outcome_evidence_index is not None
                and inp.evidence_ids
                and 0 <= update.outcome_evidence_index < len(inp.evidence_ids)
            ):
                outcome_evidence_id = inp.evidence_ids[update.outcome_evidence_index]

            existing.status = proposed_status
            if update.actual_outcome is not None:
                existing.actual_outcome = update.actual_outcome
            if outcome_evidence_id is not None:
                existing.outcome_evidence_id = outcome_evidence_id
            await self._session.flush()
            updated_ids.append(stmt_id)

        return PersistStatementsOutput(
            created_ids=created_ids,
            updated_ids=updated_ids,
            rejected_count=rejected_count,
        )

    # -- Tool 9: persist_shareholding ------------------------------------------

    async def persist_shareholding(
        self,
        inp: PersistShareholdingInput,
    ) -> PersistShareholdingOutput:
        persisted_ids: list[uuid.UUID] = []
        skipped_count = 0

        for snapshot in inp.snapshots:
            # Check for existing row (upsert semantics per §30)
            existing_stmt = sa.select(Shareholding).where(
                Shareholding.company_id == inp.company_id,
                Shareholding.as_of_date == snapshot.as_of_date,
            )
            result = await self._session.execute(existing_stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                skipped_count += 1
                logger.info(
                    "Shareholding already exists for company %s on %s, skipping (first-write-wins)",
                    inp.company_id,
                    snapshot.as_of_date,
                )
                continue

            record = Shareholding(
                company_id=inp.company_id,
                as_of_date=snapshot.as_of_date,
                promoter_holding_pct=snapshot.promoter_holding_pct,
                fii_holding_pct=snapshot.fii_holding_pct,
                dii_holding_pct=snapshot.dii_holding_pct,
                public_holding_pct=snapshot.public_holding_pct,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            persisted_ids.append(record.id)

        return PersistShareholdingOutput(
            persisted_ids=persisted_ids,
            skipped_count=skipped_count,
        )

    # -- Tool 10: persist_governance_data --------------------------------------

    async def persist_governance_data(
        self,
        inp: PersistGovernanceDataInput,
    ) -> PersistGovernanceDataOutput:
        pledge_ids: list[uuid.UUID] = []
        corporate_action_ids: list[uuid.UUID] = []

        # Persist pledge snapshots to governance.promoter_pledge
        for snap in inp.pledge_snapshots:
            # Upsert semantics: skip if (company_id, as_of_date) exists
            existing_stmt = sa.select(PromoterPledge).where(
                PromoterPledge.company_id == inp.company_id,
                PromoterPledge.as_of_date == snap.as_of_date,
            )
            result = await self._session.execute(existing_stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                logger.info(
                    "PromoterPledge already exists for company %s on %s, skipping",
                    inp.company_id,
                    snap.as_of_date,
                )
                continue

            pledge_pct = snap.pledged_percentage if snap.pledged_percentage is not None else Decimal("0")
            record = PromoterPledge(
                company_id=inp.company_id,
                as_of_date=snap.as_of_date,
                shares_pledged=0,
                pledge_pct=pledge_pct,
            )
            self._session.add(record)
            await self._session.flush()
            await self._session.refresh(record)
            pledge_ids.append(record.id)

        # Persist corporate actions to governance.corporate_action
        for action in inp.corporate_actions:
            action_record = CorporateAction(
                company_id=inp.company_id,
                action_type=action.action_type,
                ex_date=action.ex_date,
                record_date=action.record_date,
                details={"description": action.details, "value": str(action.value) if action.value else None},
                source=action.source_provider,
            )
            self._session.add(action_record)
            await self._session.flush()
            await self._session.refresh(action_record)
            corporate_action_ids.append(action_record.id)

        return PersistGovernanceDataOutput(
            pledge_ids=pledge_ids,
            corporate_action_ids=corporate_action_ids,
        )

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


def _map_filing_type(filing_type: str) -> DocumentType:
    mapping: dict[str, DocumentType] = {
        "ANNUAL_REPORT": DocumentType.ANNUAL_REPORT,
        "QUARTERLY_RESULT": DocumentType.QUARTERLY_RESULT,
        "INVESTOR_PRESENTATION": DocumentType.INVESTOR_PRESENTATION,
    }
    return mapping.get(filing_type.upper(), DocumentType.FILING)


def _compute_start_date_for_quarters(observation_date: date, quarters: int) -> date:
    months_back = quarters * 3
    year = observation_date.year
    month = observation_date.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    day = min(observation_date.day, 28)
    return date(year, month, day)
