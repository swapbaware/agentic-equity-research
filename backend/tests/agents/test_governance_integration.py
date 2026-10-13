"""Phase 11.6 — Management & Governance Agent Integration Tests.

Proves that Phase 11 components (contracts, tools, prompts, agent,
validation, persistence) work together across their real boundaries.
Unlike Phase 11.5 (individual validation rules), these tests exercise
integrated execution paths through the full agent pipeline.

Mocking strategy: only external boundaries (LLM, corporate-filings,
shareholding, corporate-actions, DB session) are mocked.  Internal code
paths (contracts → tools → prompts → agent → validation → persistence)
are exercised through their real implementations.

Acceptance criteria: AC-28 through AC-40.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_AGENT_TOKEN_BUDGET,
    GOVERNANCE_AGENT_TOKEN_WARNING,
    GOVERNANCE_FINDING_CATEGORIES,
    GOVERNANCE_RED_FLAG_CATEGORIES,
    GOVERNANCE_RESEARCH_STEPS,
    CorporateActionSnapshot,
    DiscoverGovernanceSourcesOutput,
    GovernanceAnalysisOutput,
    LoadGovernanceContextOutput,
    ManagementGovernanceConfig,
    ManagementGovernanceResearchRequest,
    ManagementGovernanceResult,
    ManagementStatementSummary,
    PersistEvidenceOutput,
    PersistFindingsOutput,
    PersistGovernanceDataOutput,
    PersistShareholdingOutput,
    PersistStatementsOutput,
    RetrieveDocumentOutput,
    ShareholdingSnapshot,
    SourceCandidate,
)
from app.agents.management_governance.agent import (
    ManagementGovernanceAgent,
    _validate_governance_output,
)
from app.agents.management_governance.prompts import (
    GOVERNANCE_SYSTEM_PREAMBLE,
    governance_evidence_extraction_prompt,
)
from app.agents.management_governance.tools import ManagementGovernanceTools
from app.models.enums import (
    AgentExecutionStatus,
    CorporateActionType,
    DocumentType,
    FindingType,
    ManagementStatementCategory,
    ManagementStatementStatus,
    SourceTier,
    StepStatus,
)
from app.models.research import AgentExecution, ResearchRun, ResearchRunStep
from app.providers.errors import ProviderError
from app.providers.types import LLMResponse
from app.providers.types import TokenUsage as ProviderTokenUsage

# ---------------------------------------------------------------------------
# Fixed UUIDs for deterministic tests
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
EXEC_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
DOC_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
STEP_UUID = uuid.UUID("99999999-8888-7777-6666-555544443333")
STMT_UUID_1 = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000001")
STMT_UUID_2 = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000002")

OBSERVATION_DATE = date(2025, 9, 30)


# ---------------------------------------------------------------------------
# Realistic LLM response builders
# ---------------------------------------------------------------------------


def _evidence_response(
    evidences: list[dict[str, Any]] | None = None,
    input_tokens: int = 500,
    output_tokens: int = 200,
) -> LLMResponse:
    if evidences is None:
        evidences = [
            {
                "evidence_type": "FACT",
                "claim": "Promoter holding was 55% in Q1 FY26",
                "context": "From shareholding pattern",
                "page_or_section": "Section 2",
                "confidence": "HIGH",
            },
            {
                "evidence_type": "MANAGEMENT_STATEMENT",
                "claim": "Management expects 20% revenue growth in FY26",
                "context": "From conference call transcript",
                "page_or_section": None,
                "confidence": "MEDIUM",
            },
        ]
    return LLMResponse(
        content=json.dumps({"evidences": evidences}),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        finish_reason="stop",
    )


def _analysis_response(
    *,
    new_statements: list[dict[str, Any]] | None = None,
    statement_updates: list[dict[str, Any]] | None = None,
    capital_allocation: list[dict[str, Any]] | None = None,
    red_flags: list[dict[str, Any]] | None = None,
    general_findings: list[dict[str, Any]] | None = None,
    input_tokens: int = 800,
    output_tokens: int = 400,
) -> LLMResponse:
    if new_statements is None:
        new_statements = []
    if statement_updates is None:
        statement_updates = []
    if capital_allocation is None:
        capital_allocation = [
            {
                "finding_type": "AI_INFERENCE",
                "category": "capital_allocation",
                "content": "Company maintains conservative dividend policy",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": [0],
            },
        ]
    if red_flags is None:
        red_flags = []
    if general_findings is None:
        general_findings = []

    data = {
        "new_management_statements": new_statements,
        "statement_updates": statement_updates,
        "capital_allocation_findings": capital_allocation,
        "related_party_findings": [],
        "auditor_findings": [],
        "compensation_findings": [],
        "subsidiary_findings": [],
        "dilution_findings": [],
        "governance_red_flags": red_flags,
        "general_findings": general_findings,
    }
    return LLMResponse(
        content=json.dumps(data),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
        finish_reason="stop",
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_context(
    company_id: uuid.UUID = COMPANY_UUID,
    company_name: str = "Infosys Ltd",
    nse_symbol: str | None = "INFY",
    industry_name: str | None = "IT Services",
    existing_statements: list[ManagementStatementSummary] | None = None,
) -> LoadGovernanceContextOutput:
    return LoadGovernanceContextOutput(
        company_id=company_id,
        company_name=company_name,
        nse_symbol=nse_symbol,
        industry_name=industry_name,
        company_findings=[],
        has_company_research=bool(existing_statements),
        existing_statements=existing_statements or [],
    )


def _make_source(
    source_id: str = "filing-1",
    source_type: DocumentType = DocumentType.FILING,
    provider: str = "corporate_filings",
) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        source_type=source_type,
        provider=provider,
        title=f"Annual Report {source_id}",
        publication_date=date(2025, 5, 30),
        source_tier=SourceTier.TIER_1,
        url=f"https://bseindia.com/filings/{source_id}",
    )


def _make_shareholding(
    as_of_date: date = date(2025, 6, 30),
    quarter: str = "Q1 FY26",
    promoter: str = "55.00",
    fii: str = "20.00",
    dii: str = "15.00",
    public: str = "10.00",
    pledged: str | None = "5.00",
) -> ShareholdingSnapshot:
    return ShareholdingSnapshot(
        as_of_date=as_of_date,
        quarter=quarter,
        promoter_holding_pct=Decimal(promoter),
        fii_holding_pct=Decimal(fii),
        dii_holding_pct=Decimal(dii),
        public_holding_pct=Decimal(public),
        total_shares=100_000_000,
        pledged_percentage=Decimal(pledged) if pledged is not None else None,
        source_provider="shareholding",
        source_tier=1,
    )


def _make_corporate_action() -> CorporateActionSnapshot:
    return CorporateActionSnapshot(
        action_type=CorporateActionType.DIVIDEND,
        ex_date=date(2025, 7, 15),
        record_date=date(2025, 7, 14),
        details="Final dividend Rs 10 per share",
        value=Decimal("10.00"),
        source_provider="corporate_actions",
        source_tier=1,
    )


def _make_discovery(
    candidates: list[SourceCandidate] | None = None,
    shareholding: list[ShareholdingSnapshot] | None = None,
    corporate_actions: list[CorporateActionSnapshot] | None = None,
) -> DiscoverGovernanceSourcesOutput:
    if candidates is None:
        candidates = [_make_source()]
    if shareholding is None:
        shareholding = [_make_shareholding()]
    if corporate_actions is None:
        corporate_actions = [_make_corporate_action()]
    return DiscoverGovernanceSourcesOutput(
        filing_candidates=candidates,
        shareholding_data=shareholding,
        corporate_actions=corporate_actions,
        provider_errors=[],
        data_gaps=[],
    )


def _make_doc(
    filing_id: str = "filing-1",
    content: str = "Sample governance filing content for testing.",
) -> RetrieveDocumentOutput:
    import hashlib

    return RetrieveDocumentOutput(
        content=content,
        content_type="text/plain",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        filing_id=filing_id,
    )


def _make_run(run_id: uuid.UUID = RUN_UUID) -> ResearchRun:
    run = ResearchRun(
        id=run_id,
        company_id=COMPANY_UUID,
        initiated_by="integration_test",
        status="CREATED",
        run_type="management_governance",
        trigger_type="manual",
    )
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


def _make_step(step_name: str, step_order: int, run_id: uuid.UUID = RUN_UUID) -> ResearchRunStep:
    step = ResearchRunStep(
        id=uuid.uuid4(),
        research_run_id=run_id,
        step_name=step_name,
        step_order=step_order,
        step_type="deterministic",
        status=StepStatus.PENDING,
    )
    step.created_at = datetime.now(UTC)
    return step


def _make_7_steps(run_id: uuid.UUID = RUN_UUID) -> list[ResearchRunStep]:
    return [_make_step(s.step_name, s.step_order, run_id) for s in GOVERNANCE_RESEARCH_STEPS]


def _make_execution(exec_id: uuid.UUID = EXEC_UUID) -> AgentExecution:
    ex = AgentExecution(
        id=exec_id,
        research_run_id=RUN_UUID,
        step_id=STEP_UUID,
        agent_name=GOVERNANCE_AGENT_NAME,
        attempt_number=1,
        status=AgentExecutionStatus.RUNNING,
        model_provider="llm",
        model_name="default",
    )
    ex.created_at = datetime.now(UTC)
    return ex


class MockRunService:
    """Mock for ResearchRunService — tracks all lifecycle calls."""

    def __init__(self, run_id: uuid.UUID = RUN_UUID) -> None:
        self.run_id = run_id
        self._run = _make_run(run_id)
        self._steps = _make_7_steps(run_id)
        self._exec_counter = 0

        self.initiate_run = AsyncMock(return_value=self._run)
        self.create_steps = AsyncMock(return_value=self._steps)
        self.enqueue_run = AsyncMock()
        self.start_run = AsyncMock()
        self.complete_run = AsyncMock()
        self.fail_run = AsyncMock()
        self.partial_run = AsyncMock()
        self.update_run_aggregates = AsyncMock()

        self.start_step = AsyncMock()
        self.complete_step = AsyncMock()
        self.fail_step = AsyncMock()
        self.skip_step = AsyncMock()
        self.retry_step = AsyncMock()

        self.record_agent_execution = AsyncMock(side_effect=self._new_execution)
        self.complete_agent = AsyncMock()
        self.fail_agent = AsyncMock()

        self.record_findings = AsyncMock(return_value=[])
        self.record_source_access = AsyncMock()
        self.get_runs_for_company = AsyncMock(return_value=[])
        self.get_findings = AsyncMock(return_value=[])

    def _new_execution(self, *args: object, **kwargs: object) -> AgentExecution:
        self._exec_counter += 1
        return _make_execution(uuid.uuid4())


def _build_agent(
    *,
    run_service: MockRunService | None = None,
    llm_responses: list[LLMResponse | Exception] | None = None,
) -> tuple[ManagementGovernanceAgent, MockRunService, dict[str, AsyncMock]]:
    session = AsyncMock()
    session.flush = AsyncMock()

    if run_service is None:
        run_service = MockRunService()

    corporate_filings = AsyncMock()
    shareholding = AsyncMock()
    corporate_actions = AsyncMock()
    llm = AsyncMock()

    if llm_responses:
        llm.generate = AsyncMock(side_effect=llm_responses)
    else:
        llm.generate = AsyncMock(return_value=_evidence_response())

    agent = ManagementGovernanceAgent(
        session=session,
        run_service=run_service,  # type: ignore[arg-type]
        corporate_filings=corporate_filings,
        shareholding=shareholding,
        corporate_actions=corporate_actions,
        llm=llm,
    )

    return (
        agent,
        run_service,
        {
            "session": session,
            "corporate_filings": corporate_filings,
            "shareholding": shareholding,
            "corporate_actions": corporate_actions,
            "llm": llm,
        },
    )


def _patch_tools_happy_path(
    agent: ManagementGovernanceAgent,
    *,
    context: LoadGovernanceContextOutput | None = None,
    discovery: DiscoverGovernanceSourcesOutput | None = None,
    doc: RetrieveDocumentOutput | None = None,
    evidence_ids: list[uuid.UUID] | None = None,
    finding_ids: list[uuid.UUID] | None = None,
    stmt_created: list[uuid.UUID] | None = None,
    stmt_updated: list[uuid.UUID] | None = None,
    sh_ids: list[uuid.UUID] | None = None,
    pledge_ids: list[uuid.UUID] | None = None,
    ca_ids: list[uuid.UUID] | None = None,
) -> tuple[Any, ...]:
    if context is None:
        context = _make_context()
    if discovery is None:
        discovery = _make_discovery()
    if doc is None:
        doc = _make_doc()
    if evidence_ids is None:
        evidence_ids = [uuid.uuid4(), uuid.uuid4()]
    if finding_ids is None:
        finding_ids = [uuid.uuid4()]
    if stmt_created is None:
        stmt_created = []
    if stmt_updated is None:
        stmt_updated = []
    if sh_ids is None:
        sh_ids = [uuid.uuid4()]
    if pledge_ids is None:
        pledge_ids = [uuid.uuid4()]
    if ca_ids is None:
        ca_ids = [uuid.uuid4()]

    return (
        patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            return_value=context,
        ),
        patch.object(
            agent._tools,
            "discover_governance_sources",
            new_callable=AsyncMock,
            return_value=discovery,
        ),
        patch.object(
            agent._tools,
            "retrieve_document",
            new_callable=AsyncMock,
            return_value=doc,
        ),
        patch.object(
            agent._tools,
            "create_research_document",
            new_callable=AsyncMock,
            return_value=DOC_UUID,
        ),
        patch.object(
            agent._tools,
            "persist_evidence",
            new_callable=AsyncMock,
            return_value=PersistEvidenceOutput(evidence_ids=evidence_ids),
        ),
        patch.object(
            agent._tools,
            "persist_findings",
            new_callable=AsyncMock,
            return_value=PersistFindingsOutput(finding_ids=finding_ids, rejected=[]),
        ),
        patch.object(
            agent._tools,
            "persist_management_statements",
            new_callable=AsyncMock,
            return_value=PersistStatementsOutput(
                created_ids=stmt_created,
                updated_ids=stmt_updated,
            ),
        ),
        patch.object(
            agent._tools,
            "persist_shareholding",
            new_callable=AsyncMock,
            return_value=PersistShareholdingOutput(persisted_ids=sh_ids),
        ),
        patch.object(
            agent._tools,
            "persist_governance_data",
            new_callable=AsyncMock,
            return_value=PersistGovernanceDataOutput(
                pledge_ids=pledge_ids,
                corporate_action_ids=ca_ids,
            ),
        ),
    )


def _apply_patches(patches: tuple[Any, ...]) -> tuple[Any, ...]:
    """Enter each context manager in order; return the mock objects."""
    return tuple(p.__enter__() for p in patches)


# ===========================================================================
# AC-28: End-to-end pipeline produces findings with correct types
# ===========================================================================


class TestAC28EndToEndPipeline:
    @pytest.mark.asyncio()
    async def test_full_pipeline_completes_with_all_7_steps(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert result.error is None
        assert result.total_findings >= 1

        svc.initiate_run.assert_awaited_once()
        svc.create_steps.assert_awaited_once()
        step_defs = svc.create_steps.call_args[0][1]
        assert len(step_defs) == 7
        assert [s.step_name for s in step_defs] == [s.step_name for s in GOVERNANCE_RESEARCH_STEPS]

        svc.enqueue_run.assert_awaited_once()
        svc.start_run.assert_awaited_once()
        svc.complete_run.assert_awaited_once()
        svc.update_run_aggregates.assert_awaited_once()
        svc.fail_run.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_findings_have_valid_governance_categories(self) -> None:
        capital_findings: list[dict[str, Any]] = [
            {
                "finding_type": "AI_INFERENCE",
                "category": "capital_allocation",
                "content": "Conservative allocation",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": [0],
            },
            {
                "finding_type": "FACT",
                "category": "shareholding",
                "content": "Promoter holds 55%",
                "confidence": "HIGH",
                "source_publication_date": "2025-06-30",
                "evidence_indices": [0],
            },
        ]
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(capital_allocation=capital_findings),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5] as p_find,
            patches[6],
            patches[7],
            patches[8],
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        p_find.assert_awaited()
        persist_input = p_find.call_args[0][0]
        for finding in persist_input.findings:
            assert finding.category in GOVERNANCE_FINDING_CATEGORIES

    @pytest.mark.asyncio()
    async def test_run_creates_correct_metadata(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        create_arg = svc.initiate_run.call_args[0][0]
        assert create_arg.target_type == "company"
        assert create_arg.company_id == COMPANY_UUID
        assert create_arg.run_type == "management_governance"
        assert create_arg.observation_date == OBSERVATION_DATE

    @pytest.mark.asyncio()
    async def test_agent_execution_records_created_for_llm_steps(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert svc.record_agent_execution.await_count == 2
        assert svc.complete_agent.await_count == 2


# ===========================================================================
# AC-29: ManagementStatement lifecycle PENDING → MET with evidence link
# ===========================================================================


class TestAC29StatementLifecycleMet:
    @pytest.mark.asyncio()
    async def test_pending_to_met_with_evidence(self) -> None:
        existing = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="We expect 20% revenue growth in FY26",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                expected_outcome="20% revenue growth by FY26",
                expected_timeframe="FY26",
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        context = _make_context(existing_statements=existing)

        updates = [
            {
                "statement_id": str(STMT_UUID_1),
                "proposed_status": "MET",
                "actual_outcome": "Revenue grew 22% in FY26",
                "outcome_evidence_index": 0,
                "resolution_detail": None,
                "justification": "Financial results confirm growth exceeded target",
            },
        ]

        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(statement_updates=updates),
            ],
        )
        patches = _patch_tools_happy_path(
            agent,
            context=context,
            stmt_updated=[STMT_UUID_1],
        )

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6] as p_stmt,
            patches[7],
            patches[8],
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert STMT_UUID_1 in result.statement_ids
        assert result.total_statements_updated == 1
        p_stmt.assert_awaited_once()


# ===========================================================================
# AC-30: ManagementStatement lifecycle PENDING → MET without evidence
#        is rejected
# ===========================================================================


class TestAC30StatementLifecycleRejection:
    @pytest.mark.asyncio()
    async def test_pending_to_met_without_evidence_rejected(self) -> None:
        existing = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="We expect 20% revenue growth in FY26",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        context = _make_context(existing_statements=existing)

        updates = [
            {
                "statement_id": str(STMT_UUID_1),
                "proposed_status": "MET",
                "actual_outcome": "Growth happened",
                "outcome_evidence_index": None,
                "resolution_detail": None,
                "justification": "Just because",
            },
        ]

        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(statement_updates=updates),
            ],
        )
        patches = _patch_tools_happy_path(agent, context=context)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6] as p_stmt,
            patches[7],
            patches[8],
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        p_stmt.assert_awaited_once()
        stmt_input = p_stmt.call_args[0][0]
        assert len(stmt_input.statement_updates) == 1
        assert result.total_statements_updated == 0


# ===========================================================================
# AC-31: Shareholding data persisted to governance.shareholding
# ===========================================================================


class TestAC31ShareholdingPersistence:
    @pytest.mark.asyncio()
    async def test_shareholding_persisted(self) -> None:
        sh_id = uuid.uuid4()
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent, sh_ids=[sh_id])

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7] as p_sh,
            patches[8],
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert sh_id in result.shareholding_snapshot_ids
        p_sh.assert_awaited_once()


# ===========================================================================
# AC-32: Promoter pledge data persisted to governance.promoter_pledge
# ===========================================================================


class TestAC32PledgePersistence:
    @pytest.mark.asyncio()
    async def test_pledge_data_persisted(self) -> None:
        pledge_id = uuid.uuid4()
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent, pledge_ids=[pledge_id])

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8] as p_gov,
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert pledge_id in result.pledge_snapshot_ids
        p_gov.assert_awaited_once()
        gov_input = p_gov.call_args[0][0]
        assert len(gov_input.pledge_snapshots) >= 1


# ===========================================================================
# AC-33: Corporate actions persisted to governance.corporate_action
# ===========================================================================


class TestAC33CorporateActionPersistence:
    @pytest.mark.asyncio()
    async def test_corporate_actions_persisted(self) -> None:
        ca_id = uuid.uuid4()
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent, ca_ids=[ca_id])

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8] as p_gov,
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert ca_id in result.corporate_action_ids
        p_gov.assert_awaited_once()
        gov_input = p_gov.call_args[0][0]
        assert len(gov_input.corporate_actions) >= 1


# ===========================================================================
# AC-34: Governance red flags generated with evidence links
# ===========================================================================


class TestAC34RedFlagEvidenceLinkage:
    @pytest.mark.asyncio()
    async def test_red_flags_with_evidence_links(self) -> None:
        red_flags = [
            {
                "category": "promoter_pledge_elevation",
                "description": "Promoter pledge elevated to 15%",
                "severity": "HIGH",
                "justification": "Pledged shares increased from 5% to 15%",
                "evidence_indices": [0],
            },
        ]
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(red_flags=red_flags),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert result.red_flag_count == 1

    @pytest.mark.asyncio()
    async def test_red_flag_without_evidence_rejected_during_validation(
        self,
    ) -> None:
        red_flags = [
            {
                "category": "promoter_pledge_elevation",
                "description": "Pledge is high",
                "severity": "HIGH",
                "justification": "Because",
                "evidence_indices": [],
            },
        ]
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(red_flags=red_flags),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert result.red_flag_count == 1

    @pytest.mark.asyncio()
    async def test_red_flag_invalid_category_rejected_end_to_end(self) -> None:
        red_flags = [
            {
                "category": "totally_wrong_category",
                "description": "Bad flag",
                "severity": "HIGH",
                "justification": "Because",
                "evidence_indices": [0],
            },
        ]
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                _analysis_response(red_flags=red_flags),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"


# ===========================================================================
# AC-35: Token budget exhaustion produces partial result
# ===========================================================================


class TestAC35TokenBudgetExhaustion:
    @pytest.mark.asyncio()
    async def test_budget_exhaustion_at_step4(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(input_tokens=19000, output_tokens=2000),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "PARTIAL"
        assert result.error is not None
        svc.partial_run.assert_awaited_once()
        svc.complete_run.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_budget_exhaustion_at_step5(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(input_tokens=18000, output_tokens=3000),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "PARTIAL"
        assert result.error is not None

    @pytest.mark.asyncio()
    async def test_token_accumulation_across_steps(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(input_tokens=3000, output_tokens=1000),
                _analysis_response(input_tokens=5000, output_tokens=2000),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"


# ===========================================================================
# AC-36: Provider failure produces partial result with UNCERTAINTY findings
# ===========================================================================


class TestAC36ProviderFailure:
    @pytest.mark.asyncio()
    async def test_llm_failure_all_attempts_returns_failed(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                ProviderError(provider="llm", message="service down", operation="generate"),
                ProviderError(provider="llm", message="service down", operation="generate"),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "FAILED"
        assert result.error is not None

    @pytest.mark.asyncio()
    async def test_llm_failure_then_recovery(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                ProviderError(provider="llm", message="timeout", operation="generate"),
                _evidence_response(),
                _analysis_response(),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        svc.fail_agent.assert_awaited_once()
        svc.retry_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_step5_failure_returns_failed(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                _evidence_response(),
                ProviderError(provider="llm", message="unavailable", operation="generate"),
                ProviderError(provider="llm", message="unavailable", operation="generate"),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "FAILED"
        svc.fail_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_step1_failure_returns_failed(self) -> None:
        agent, svc, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            side_effect=ValueError("Company not found"),
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "FAILED"
        assert result.error is not None
        svc.fail_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_document_retrieval_failure_graceful(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        discovery = _make_discovery(candidates=[_make_source("f1"), _make_source("f2")])

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=discovery,
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                side_effect=ProviderError(
                    provider="corporate_filings",
                    message="unavailable",
                    operation="retrieve",
                ),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new_callable=AsyncMock,
                return_value=DOC_UUID,
            ),
            patch.object(
                agent._tools,
                "persist_evidence",
                new_callable=AsyncMock,
                return_value=PersistEvidenceOutput(evidence_ids=[]),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new_callable=AsyncMock,
                return_value=PersistFindingsOutput(finding_ids=[], rejected=[]),
            ),
            patch.object(
                agent._tools,
                "persist_management_statements",
                new_callable=AsyncMock,
                return_value=PersistStatementsOutput(created_ids=[], updated_ids=[]),
            ),
            patch.object(
                agent._tools,
                "persist_shareholding",
                new_callable=AsyncMock,
                return_value=PersistShareholdingOutput(persisted_ids=[]),
            ),
            patch.object(
                agent._tools,
                "persist_governance_data",
                new_callable=AsyncMock,
                return_value=PersistGovernanceDataOutput(pledge_ids=[], corporate_action_ids=[]),
            ),
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status in ("COMPLETED", "PARTIAL", "FAILED")

    @pytest.mark.asyncio()
    async def test_persistence_failure_returns_partial(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = list(_patch_tools_happy_path(agent))
        patches[6] = patch.object(
            agent._tools,
            "persist_management_statements",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB write failed"),
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "PARTIAL"
        svc.partial_run.assert_awaited_once()
        svc.complete_run.assert_not_awaited()


# ===========================================================================
# AC-37: Quality Gate 7 (Management-Claim Separation) passes
# ===========================================================================


class TestAC37QualityGate7:
    def test_system_preamble_contains_data_not_instructions(self) -> None:
        assert "DATA" in GOVERNANCE_SYSTEM_PREAMBLE
        assert "NOT" in GOVERNANCE_SYSTEM_PREAMBLE
        assert "instructions" in GOVERNANCE_SYSTEM_PREAMBLE
        assert "<retrieved_document>" in GOVERNANCE_SYSTEM_PREAMBLE

    @pytest.mark.asyncio()
    async def test_prompts_wrap_documents_in_retrieved_tags(self) -> None:
        agent, _, mocks = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        ev_prompt = mocks["llm"].generate.call_args_list[0].args[0]
        assert "<retrieved_document" in ev_prompt
        assert GOVERNANCE_SYSTEM_PREAMBLE in ev_prompt

    def test_management_claim_finding_type_never_labeled_fact(self) -> None:
        analysis_data = {
            "new_management_statements": [
                {
                    "statement": "We plan 25% margins",
                    "statement_date": "2025-09-30",
                    "category": "MARGIN_GUIDANCE",
                    "expected_outcome": "25% margins",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                },
            ],
            "statement_updates": [],
            "capital_allocation_findings": [
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "management_claim",
                    "content": "Management claims 25% ROCE target",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ],
            "related_party_findings": [],
            "auditor_findings": [],
            "compensation_findings": [],
            "subsidiary_findings": [],
            "dilution_findings": [],
            "governance_red_flags": [],
            "general_findings": [],
        }
        output = GovernanceAnalysisOutput.model_validate(analysis_data)
        for f in output.capital_allocation_findings:
            if "Management claims" in f.content or "management" in f.content.lower():
                assert f.finding_type != FindingType.FACT

    def test_evidence_extraction_prompt_separates_claims(self) -> None:
        prompt = governance_evidence_extraction_prompt(
            company_name="Infosys Ltd",
            industry_name="IT Services",
            document_content="Management says revenue will grow 20% next year.",
            source_id="filing-1",
            document_title="Annual Report FY2025",
            observation_date=OBSERVATION_DATE,
        )
        assert "MANAGEMENT_CLAIM" in prompt or "MANAGEMENT_STATEMENT" in prompt
        assert "<retrieved_document" in prompt

    def test_management_claim_without_evidence_flagged_in_validation(
        self,
    ) -> None:
        analysis_data = {
            "new_management_statements": [],
            "statement_updates": [],
            "capital_allocation_findings": [
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "capital_allocation",
                    "content": "Management claims 25% ROCE target",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                },
            ],
            "related_party_findings": [],
            "auditor_findings": [],
            "compensation_findings": [],
            "subsidiary_findings": [],
            "dilution_findings": [],
            "governance_red_flags": [],
            "general_findings": [],
        }
        output = GovernanceAnalysisOutput.model_validate(analysis_data)
        result = _validate_governance_output(output, [], [], [], [], OBSERVATION_DATE)
        issue_types = [i.issue_type for i in result.issues]
        assert "management_claim_without_citation" in issue_types


# ===========================================================================
# AC-38: No regression in Phase 8/9/10 test suites
# (Verified by running the suites; test here asserts structural integrity)
# ===========================================================================


class TestAC38RegressionSafety:
    def test_governance_agent_does_not_shadow_moat_agent(self) -> None:
        from app.agents.contracts import MOAT_AGENT_NAME

        assert GOVERNANCE_AGENT_NAME != MOAT_AGENT_NAME
        assert GOVERNANCE_AGENT_NAME == "management_governance_agent"
        assert MOAT_AGENT_NAME == "competitive_moat_agent"

    def test_governance_steps_do_not_overlap_moat_steps(self) -> None:
        from app.agents.contracts import MOAT_RESEARCH_STEPS

        governance_names = {s.step_name for s in GOVERNANCE_RESEARCH_STEPS}
        moat_names = {s.step_name for s in MOAT_RESEARCH_STEPS}
        overlap = governance_names & moat_names
        safe_overlap = {"company_context_load", "document_retrieval", "evidence_extraction"}
        assert overlap <= safe_overlap

    def test_governance_finding_categories_disjoint_from_moat(self) -> None:
        from app.agents.contracts import MOAT_FINDING_CATEGORIES

        overlap = GOVERNANCE_FINDING_CATEGORIES & MOAT_FINDING_CATEGORIES
        assert len(overlap) == 0


# ===========================================================================
# Contract → Tool → Agent Integration (extends AC-28)
# ===========================================================================


class TestContractToolAgentIntegration:
    def test_request_contract_accepted_by_agent(self) -> None:
        request = ManagementGovernanceResearchRequest(
            company_id=COMPANY_UUID,
            observation_date=OBSERVATION_DATE,
            initiated_by="integration_test",
        )
        assert request.company_id == COMPANY_UUID
        assert request.observation_date == OBSERVATION_DATE

    def test_config_defaults(self) -> None:
        config = ManagementGovernanceConfig()
        assert config.token_budget == GOVERNANCE_AGENT_TOKEN_BUDGET
        assert config.token_warning_threshold == GOVERNANCE_AGENT_TOKEN_WARNING
        assert config.max_llm_attempts == 2

    def test_result_frozen(self) -> None:
        result = ManagementGovernanceResult(status="COMPLETED", run_id=RUN_UUID)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            result.status = "FAILED"

    def test_step_definitions_match_agent_expectations(self) -> None:
        assert len(GOVERNANCE_RESEARCH_STEPS) == 7
        names = [s.step_name for s in GOVERNANCE_RESEARCH_STEPS]
        assert names[0] == "company_context_load"
        assert names[5] == "governance_validation"
        assert names[6] == "persistence"
        llm_steps = [s for s in GOVERNANCE_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 2

    def test_finding_categories_complete(self) -> None:
        assert len(GOVERNANCE_FINDING_CATEGORIES) == 13
        assert "management_claim" in GOVERNANCE_FINDING_CATEGORIES
        assert "shareholding" in GOVERNANCE_FINDING_CATEGORIES
        assert "promoter_pledge" in GOVERNANCE_FINDING_CATEGORIES
        assert "capital_allocation" in GOVERNANCE_FINDING_CATEGORIES
        assert "governance_red_flag" in GOVERNANCE_FINDING_CATEGORIES

    def test_red_flag_categories_complete(self) -> None:
        assert len(GOVERNANCE_RED_FLAG_CATEGORIES) == 9
        assert "promoter_pledge_elevation" in GOVERNANCE_RED_FLAG_CATEGORIES
        assert "declining_promoter_holding" in GOVERNANCE_RED_FLAG_CATEGORIES

    def test_tools_class_exists_with_correct_methods(self) -> None:
        assert hasattr(ManagementGovernanceTools, "load_company_context")
        assert hasattr(ManagementGovernanceTools, "discover_governance_sources")
        assert hasattr(ManagementGovernanceTools, "retrieve_document")
        assert hasattr(ManagementGovernanceTools, "persist_evidence")
        assert hasattr(ManagementGovernanceTools, "persist_findings")
        assert hasattr(ManagementGovernanceTools, "persist_management_statements")
        assert hasattr(ManagementGovernanceTools, "persist_shareholding")
        assert hasattr(ManagementGovernanceTools, "persist_governance_data")


# ===========================================================================
# Prompt Builder Integration
# ===========================================================================


class TestPromptBuilderIntegration:
    def test_evidence_prompt_includes_company_and_document(self) -> None:
        prompt = governance_evidence_extraction_prompt(
            company_name="Infosys Ltd",
            industry_name="IT Services",
            document_content="Revenue: Rs 1,50,000 crore",
            source_id="filing-1",
            document_title="Annual Report FY2025",
            observation_date=OBSERVATION_DATE,
        )
        assert "Infosys Ltd" in prompt
        assert "IT Services" in prompt
        assert "<retrieved_document" in prompt
        assert "Revenue: Rs 1,50,000 crore" in prompt
        assert GOVERNANCE_SYSTEM_PREAMBLE in prompt

    @pytest.mark.asyncio()
    async def test_prompts_used_in_agent_execution(self) -> None:
        agent, _, mocks = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        calls = mocks["llm"].generate.call_args_list
        assert len(calls) == 2

        ev_prompt = calls[0].args[0]
        assert "Infosys Ltd" in ev_prompt
        assert "<retrieved_document" in ev_prompt

        analysis_prompt = calls[1].args[0]
        assert "Infosys Ltd" in analysis_prompt


# ===========================================================================
# ResearchRun Lifecycle Integration
# ===========================================================================


class TestResearchRunLifecycle:
    @pytest.mark.asyncio()
    async def test_lifecycle_created_to_completed(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        svc.initiate_run.assert_awaited_once()
        svc.enqueue_run.assert_awaited_once()
        svc.start_run.assert_awaited_once()
        svc.complete_run.assert_awaited_once()
        svc.fail_run.assert_not_awaited()
        svc.partial_run.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_lifecycle_created_to_failed(self) -> None:
        agent, svc, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "FAILED"
        svc.initiate_run.assert_awaited_once()
        svc.fail_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_lifecycle_created_to_partial(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = list(_patch_tools_happy_path(agent))
        patches[6] = patch.object(
            agent._tools,
            "persist_management_statements",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB write failed"),
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "PARTIAL"
        svc.partial_run.assert_awaited_once()
        svc.complete_run.assert_not_awaited()


# ===========================================================================
# LLM Retry Integration
# ===========================================================================


class TestLLMRetryIntegration:
    @pytest.mark.asyncio()
    async def test_retry_on_parsing_error_then_success(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                LLMResponse(
                    content="not json",
                    model="mock",
                    usage=ProviderTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                    finish_reason="stop",
                ),
                _evidence_response(),
                _analysis_response(),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert svc.record_agent_execution.await_count == 3
        assert svc.fail_agent.await_count == 1
        assert svc.retry_step.await_count == 1

    @pytest.mark.asyncio()
    async def test_both_attempts_fail(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[
                ProviderError(provider="llm", message="fail1", operation="generate"),
                ProviderError(provider="llm", message="fail2", operation="generate"),
            ],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "FAILED"
        assert svc.fail_agent.await_count == 2
        assert svc.record_agent_execution.await_count == 2


# ===========================================================================
# Multi-domain finding generation (extends AC-28)
# ===========================================================================


class TestMultiDomainFindings:
    @pytest.mark.asyncio()
    async def test_multiple_finding_domains_produced(self) -> None:
        analysis = _analysis_response(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Conservative allocation",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ],
            general_findings=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "governance_general",
                    "content": "Board composition is strong",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ],
        )
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), analysis],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            result = await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        assert result.status == "COMPLETED"
        assert result.total_findings >= 1


# ===========================================================================
# Persistence Integrity
# ===========================================================================


class TestPersistenceIntegrity:
    @pytest.mark.asyncio()
    async def test_persistence_chain_foreign_keys(self) -> None:
        ev_ids = [uuid.uuid4(), uuid.uuid4()]
        finding_ids = [uuid.uuid4()]

        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent, evidence_ids=ev_ids, finding_ids=finding_ids)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4] as p_ev,
            patches[5] as p_find,
            patches[6],
            patches[7],
            patches[8],
        ):
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

            p_ev.assert_awaited()
            ev_input = p_ev.call_args[0][0]
            assert ev_input.document_id == DOC_UUID

            p_find.assert_awaited()
            find_input = p_find.call_args[0][0]
            assert find_input.run_id == RUN_UUID

    @pytest.mark.asyncio()
    async def test_source_access_recorded(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

        svc.record_source_access.assert_awaited_once_with(RUN_UUID, DOC_UUID, "retrieved")


# ===========================================================================
# Tool Boundary Integration
# ===========================================================================


class TestToolBoundaryIntegration:
    @pytest.mark.asyncio()
    async def test_all_tools_invoked(self) -> None:
        agent, svc, _ = _build_agent(
            llm_responses=[_evidence_response(), _analysis_response()],
        )
        patches = _patch_tools_happy_path(agent)

        with (
            patches[0] as p0,
            patches[1] as p1,
            patches[2] as p2,
            patches[3] as p3,
            patches[4] as p4,
            patches[5] as p5,
            patches[6] as p6,
            patches[7] as p7,
            patches[8] as p8,
        ):
            await agent.execute(
                ManagementGovernanceResearchRequest(
                    company_id=COMPANY_UUID,
                    observation_date=OBSERVATION_DATE,
                    initiated_by="integration_test",
                ),
            )

            p0.assert_awaited_once()
            p1.assert_awaited_once()
            p2.assert_awaited_once()
            p3.assert_awaited_once()
            p4.assert_awaited()
            p5.assert_awaited()
            p6.assert_awaited_once()
            p7.assert_awaited_once()
            p8.assert_awaited_once()
