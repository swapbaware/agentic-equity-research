"""Comprehensive tests for Phase 11.4 Management & Governance Agent.

Covers:
 1. Agent construction / dependency injection
 2. Full happy-path execution
 3. Deterministic step runner
 4. LLM step runner with retry
 5. Token budget enforcement
 6. Step 1: company context load
 7. Step 2: governance source discovery
 8. Step 3: document retrieval
 9. Step 4: evidence extraction
10. Step 5: governance analysis
11. Step 5a: deterministic shareholding/pledge finding generation
12. Step 6: governance validation (6 deterministic checks)
13. Step 7: persistence
14. Error handling / partial completion
15. LLM response parsing
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.agents.company_research.exceptions import (
    LLMParsingError,
    StepFailedError,
    TokenBudgetExhaustedError,
)
from app.agents.contracts import (
    GOVERNANCE_AGENT_NAME,
    GOVERNANCE_AGENT_TOKEN_BUDGET,
    GOVERNANCE_AGENT_TOKEN_WARNING,
    GOVERNANCE_RESEARCH_STEPS,
    CorporateActionSnapshot,
    DiscoverGovernanceSourcesOutput,
    EvidenceExtractionOutput,
    ExtractedEvidence,
    GeneratedFinding,
    GovernanceAnalysisOutput,
    GovernanceValidationResult,
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
    TokenBudget,
)
from app.agents.management_governance.agent import (
    ManagementGovernanceAgent,
    _compute_trend_direction,
    _generate_pledge_findings,
    _generate_shareholding_findings,
    _parse_evidence_extraction_response,
    _parse_governance_analysis_response,
    _validate_governance_output,
)
from app.agents.management_governance.tools import ManagementGovernanceTools
from app.models.enums import (
    AgentExecutionStatus,
    ConfidenceLevel,
    CorporateActionType,
    DocumentType,
    EvidenceType,
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
# Fixed UUIDs
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
# Helpers
# ---------------------------------------------------------------------------


def _make_context_output(
    *,
    company_id: uuid.UUID = COMPANY_UUID,
    company_name: str = "Infosys Ltd",
    nse_symbol: str | None = "INFY",
    industry_name: str | None = "IT Services",
) -> LoadGovernanceContextOutput:
    return LoadGovernanceContextOutput(
        company_id=company_id,
        company_name=company_name,
        nse_symbol=nse_symbol,
        industry_name=industry_name,
        company_findings=[],
        has_company_research=False,
        existing_statements=[],
    )


def _make_context_with_statements(
    statements: list[ManagementStatementSummary] | None = None,
) -> LoadGovernanceContextOutput:
    if statements is None:
        statements = [
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
    return LoadGovernanceContextOutput(
        company_id=COMPANY_UUID,
        company_name="Infosys Ltd",
        nse_symbol="INFY",
        industry_name="IT Services",
        company_findings=[],
        has_company_research=True,
        existing_statements=statements,
    )


def _make_source_candidate(
    source_id: str = "filing-1",
    source_type: DocumentType = DocumentType.FILING,
    provider: str = "corporate_filings",
) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        source_type=source_type,
        provider=provider,
        title=f"Test Filing {source_id}",
        publication_date=date(2025, 5, 30),
        source_tier=SourceTier.TIER_1,
        url=f"https://example.com/{source_id}",
    )


def _make_shareholding_snapshot(
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


def _make_discovery_output(
    candidates: list[SourceCandidate] | None = None,
    shareholding: list[ShareholdingSnapshot] | None = None,
    corporate_actions: list[CorporateActionSnapshot] | None = None,
) -> DiscoverGovernanceSourcesOutput:
    if candidates is None:
        candidates = [_make_source_candidate()]
    if shareholding is None:
        shareholding = [_make_shareholding_snapshot()]
    if corporate_actions is None:
        corporate_actions = [_make_corporate_action()]
    return DiscoverGovernanceSourcesOutput(
        filing_candidates=candidates,
        shareholding_data=shareholding,
        corporate_actions=corporate_actions,
        provider_errors=[],
        data_gaps=[],
    )


def _make_doc_output(
    filing_id: str = "filing-1",
    content: str = "Sample governance filing content for testing.",
) -> RetrieveDocumentOutput:
    import hashlib

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return RetrieveDocumentOutput(
        content=content,
        content_type="text/plain",
        content_hash=content_hash,
        filing_id=filing_id,
    )


def _make_llm_evidence_response(
    evidences: list[dict[str, Any]] | None = None,
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
                "context": None,
                "page_or_section": None,
                "confidence": "MEDIUM",
            },
        ]
    return LLMResponse(
        content=json.dumps({"evidences": evidences}),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
        ),
        finish_reason="stop",
    )


def _make_governance_analysis_dict(
    *,
    new_statements: list[dict[str, Any]] | None = None,
    statement_updates: list[dict[str, Any]] | None = None,
    capital_allocation: list[dict[str, Any]] | None = None,
    red_flags: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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

    return {
        "new_management_statements": new_statements,
        "statement_updates": statement_updates,
        "capital_allocation_findings": capital_allocation,
        "related_party_findings": [],
        "auditor_findings": [],
        "compensation_findings": [],
        "subsidiary_findings": [],
        "dilution_findings": [],
        "governance_red_flags": red_flags,
        "general_findings": [],
    }


def _make_llm_analysis_response(
    data: dict[str, Any] | None = None,
) -> LLMResponse:
    if data is None:
        data = _make_governance_analysis_dict()
    return LLMResponse(
        content=json.dumps(data),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=800,
            output_tokens=400,
            total_tokens=1200,
        ),
        finish_reason="stop",
    )


def _make_run(run_id: uuid.UUID = RUN_UUID) -> ResearchRun:
    run = ResearchRun(
        id=run_id,
        company_id=COMPANY_UUID,
        initiated_by="test_user",
        status="CREATED",
        run_type="management_governance",
        trigger_type="manual",
    )
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


def _make_step(
    step_name: str,
    step_order: int,
    run_id: uuid.UUID = RUN_UUID,
) -> ResearchRunStep:
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


def _make_execution(exec_id: uuid.UUID = EXEC_UUID) -> AgentExecution:
    execution = AgentExecution(
        id=exec_id,
        research_run_id=RUN_UUID,
        step_id=STEP_UUID,
        agent_name=GOVERNANCE_AGENT_NAME,
        attempt_number=1,
        status=AgentExecutionStatus.RUNNING,
        model_provider="llm",
        model_name="default",
    )
    execution.created_at = datetime.now(UTC)
    return execution


def _make_7_steps(run_id: uuid.UUID = RUN_UUID) -> list[ResearchRunStep]:
    names = [s.step_name for s in GOVERNANCE_RESEARCH_STEPS]
    return [_make_step(name, i + 1, run_id) for i, name in enumerate(names)]


class MockRunService:
    def __init__(self, run_id: uuid.UUID = RUN_UUID) -> None:
        self.run_id = run_id
        self._run = _make_run(run_id)
        self._steps = _make_7_steps(run_id)

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

        self.record_agent_execution = AsyncMock(
            return_value=_make_execution(),
        )
        self.complete_agent = AsyncMock()
        self.fail_agent = AsyncMock()

        self.record_findings = AsyncMock(return_value=[])
        self.record_source_access = AsyncMock()
        self.get_runs_for_company = AsyncMock(return_value=[])
        self.get_findings = AsyncMock(return_value=[])


def _build_agent(
    *,
    run_service: MockRunService | None = None,
    llm_responses: list[LLMResponse] | None = None,
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
        llm.generate = AsyncMock(return_value=_make_llm_evidence_response())

    agent = ManagementGovernanceAgent(
        session=session,
        run_service=run_service,  # type: ignore[arg-type]
        corporate_filings=corporate_filings,
        shareholding=shareholding,
        corporate_actions=corporate_actions,
        llm=llm,
    )

    mocks = {
        "session": session,
        "corporate_filings": corporate_filings,
        "shareholding": shareholding,
        "corporate_actions": corporate_actions,
        "llm": llm,
    }

    return agent, run_service, mocks


# ===========================================================================
# 1. Agent construction / dependency injection
# ===========================================================================


class TestAgentConstruction:
    def test_agent_creates_tools(self) -> None:
        agent, _, _ = _build_agent()
        assert isinstance(agent._tools, ManagementGovernanceTools)

    def test_agent_stores_llm_provider(self) -> None:
        agent, _, mocks = _build_agent()
        assert agent._llm is mocks["llm"]

    def test_agent_stores_run_service(self) -> None:
        agent, run_service, _ = _build_agent()
        assert agent._run_service is run_service

    def test_result_model_is_frozen(self) -> None:
        result = ManagementGovernanceResult(
            status="COMPLETED",
            run_id=RUN_UUID,
        )
        with pytest.raises(PydanticValidationError):
            result.status = "FAILED"  # type: ignore[misc]

    def test_agent_name_constant(self) -> None:
        assert GOVERNANCE_AGENT_NAME == "management_governance_agent"

    def test_token_budget_constants(self) -> None:
        assert GOVERNANCE_AGENT_TOKEN_BUDGET == 20_000
        assert GOVERNANCE_AGENT_TOKEN_WARNING == 16_000

    def test_governance_research_steps_count(self) -> None:
        assert len(GOVERNANCE_RESEARCH_STEPS) == 7

    def test_governance_research_steps_order(self) -> None:
        expected = [
            "company_context_load",
            "governance_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "governance_analysis",
            "governance_validation",
            "persistence",
        ]
        actual = [s.step_name for s in GOVERNANCE_RESEARCH_STEPS]
        assert actual == expected

    def test_step_4_and_5_use_llm(self) -> None:
        for step_def in GOVERNANCE_RESEARCH_STEPS:
            if step_def.step_name in ("evidence_extraction", "governance_analysis"):
                assert step_def.uses_llm is True
            else:
                assert step_def.uses_llm is False


# ===========================================================================
# 2. Full happy-path execution
# ===========================================================================


class TestHappyPath:
    @pytest.mark.asyncio()
    async def test_full_execution_completes(self) -> None:
        agent, run_service, mocks = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                _make_llm_analysis_response(),
            ],
        )

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=_make_discovery_output(),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
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
                return_value=PersistEvidenceOutput(
                    evidence_ids=[uuid.uuid4(), uuid.uuid4()],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new_callable=AsyncMock,
                return_value=PersistFindingsOutput(
                    finding_ids=[uuid.uuid4()],
                    rejected=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_management_statements",
                new_callable=AsyncMock,
                return_value=PersistStatementsOutput(
                    created_ids=[],
                    updated_ids=[],
                    rejected_count=0,
                ),
            ),
            patch.object(
                agent._tools,
                "persist_shareholding",
                new_callable=AsyncMock,
                return_value=PersistShareholdingOutput(
                    persisted_ids=[uuid.uuid4()],
                    skipped_count=0,
                ),
            ),
            patch.object(
                agent._tools,
                "persist_governance_data",
                new_callable=AsyncMock,
                return_value=PersistGovernanceDataOutput(
                    pledge_ids=[uuid.uuid4()],
                    corporate_action_ids=[uuid.uuid4()],
                ),
            ),
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert result.error is None

        run_service.initiate_run.assert_awaited_once()
        run_service.enqueue_run.assert_awaited_once()
        run_service.start_run.assert_awaited_once()
        run_service.complete_run.assert_awaited_once()
        run_service.update_run_aggregates.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_creates_7_steps(self) -> None:
        agent, run_service, _ = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                _make_llm_analysis_response(),
            ],
        )

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=_make_discovery_output(),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
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
                return_value=PersistEvidenceOutput(
                    evidence_ids=[uuid.uuid4(), uuid.uuid4()],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new_callable=AsyncMock,
                return_value=PersistFindingsOutput(
                    finding_ids=[uuid.uuid4()],
                    rejected=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_management_statements",
                new_callable=AsyncMock,
                return_value=PersistStatementsOutput(
                    created_ids=[],
                    updated_ids=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_shareholding",
                new_callable=AsyncMock,
                return_value=PersistShareholdingOutput(
                    persisted_ids=[uuid.uuid4()],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_governance_data",
                new_callable=AsyncMock,
                return_value=PersistGovernanceDataOutput(
                    pledge_ids=[],
                    corporate_action_ids=[],
                ),
            ),
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            await agent.execute(request)

        run_service.create_steps.assert_awaited_once()
        call_args = run_service.create_steps.call_args
        step_creates = call_args[0][1]
        assert len(step_creates) == 7

    @pytest.mark.asyncio()
    async def test_run_type_is_management_governance(self) -> None:
        agent, run_service, _ = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                _make_llm_analysis_response(),
            ],
        )

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=_make_discovery_output(),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
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
                return_value=PersistEvidenceOutput(evidence_ids=[uuid.uuid4()]),
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
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            await agent.execute(request)

        call_args = run_service.initiate_run.call_args[0][0]
        assert call_args.run_type == "management_governance"


# ===========================================================================
# 3. Deterministic step runner
# ===========================================================================


class TestDeterministicStepRunner:
    @pytest.mark.asyncio()
    async def test_step_succeeds(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("company_context_load", 1)

        async def _coro() -> str:
            return "ok"

        result = await agent._run_step_deterministic(step, _coro())
        assert result == "ok"
        run_service.start_step.assert_awaited_once()
        run_service.complete_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_step_failure_raises_step_failed(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("company_context_load", 1)

        async def _coro() -> str:
            raise ValueError("boom")

        with pytest.raises(StepFailedError):
            await agent._run_step_deterministic(step, _coro())
        run_service.fail_step.assert_awaited_once()


# ===========================================================================
# 4. LLM step runner with retry
# ===========================================================================


class TestLLMStepRunner:
    @pytest.mark.asyncio()
    async def test_succeeds_first_attempt(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=20000, warning_threshold=16000)

        async def _fn(exec_id: uuid.UUID) -> str:
            return "result"

        result = await agent._run_step_llm(
            step,
            RUN_UUID,
            token_budget,
            config,
            _fn,
        )
        assert result == "result"
        run_service.complete_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_retries_on_parsing_error(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=20000, warning_threshold=16000)

        call_count = 0

        async def _fn(exec_id: uuid.UUID) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMParsingError("evidence_extraction", "bad json")
            return "ok"

        result = await agent._run_step_llm(
            step,
            RUN_UUID,
            token_budget,
            config,
            _fn,
        )
        assert result == "ok"
        assert call_count == 2
        run_service.retry_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_fails_after_max_attempts(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        config = ManagementGovernanceConfig(max_llm_attempts=2)
        token_budget = TokenBudget(budget=20000, warning_threshold=16000)

        async def _fn(exec_id: uuid.UUID) -> str:
            raise LLMParsingError("evidence_extraction", "bad")

        with pytest.raises(StepFailedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                token_budget,
                config,
                _fn,
            )
        run_service.fail_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_skips_when_budget_exhausted_before_start(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=100, warning_threshold=80)
        token_budget.record_usage(100, 0)

        async def _fn(exec_id: uuid.UUID) -> str:
            return "unreachable"

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                token_budget,
                config,
                _fn,
            )
        run_service.skip_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_propagates_token_budget_exhausted_during_execution(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=100, warning_threshold=80)

        async def _fn(exec_id: uuid.UUID) -> str:
            raise TokenBudgetExhaustedError(101, 100)

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                token_budget,
                config,
                _fn,
            )
        run_service.fail_agent.assert_awaited_once()
        run_service.fail_step.assert_awaited_once()


# ===========================================================================
# 5. Token budget enforcement
# ===========================================================================


class TestTokenBudget:
    def test_default_budget_values(self) -> None:
        config = ManagementGovernanceConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000

    def test_budget_tracking(self) -> None:
        tb = TokenBudget(budget=20000, warning_threshold=16000)
        assert tb.remaining == 20000
        assert not tb.is_exhausted
        assert not tb.is_warning

        tb.record_usage(8000, 8000)
        assert tb.total_tokens == 16000
        assert tb.is_warning
        assert not tb.is_exhausted
        assert tb.remaining == 4000

        tb.record_usage(2000, 2000)
        assert tb.is_exhausted
        assert tb.remaining == 0

    def test_max_llm_attempts_default(self) -> None:
        config = ManagementGovernanceConfig()
        assert config.max_llm_attempts == 2


# ===========================================================================
# 6. Step 1: company context load
# ===========================================================================


class TestStep1CompanyContextLoad:
    @pytest.mark.asyncio()
    async def test_loads_context(self) -> None:
        agent, _, _ = _build_agent()
        expected = _make_context_output()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent._step_company_context_load(request)

        assert result.company_id == COMPANY_UUID
        assert result.company_name == "Infosys Ltd"

    @pytest.mark.asyncio()
    async def test_includes_existing_statements(self) -> None:
        agent, _, _ = _build_agent()
        expected = _make_context_with_statements()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent._step_company_context_load(request)

        assert len(result.existing_statements) == 1
        assert result.existing_statements[0].id == STMT_UUID_1


# ===========================================================================
# 7. Step 2: governance source discovery
# ===========================================================================


class TestStep2SourceDiscovery:
    @pytest.mark.asyncio()
    async def test_returns_candidates_and_data(self) -> None:
        agent, _, _ = _build_agent()
        context = _make_context_output()
        expected = _make_discovery_output()

        with patch.object(
            agent._tools,
            "discover_governance_sources",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            config = ManagementGovernanceConfig()
            result = await agent._step_governance_source_discovery(
                context,
                config,
                OBSERVATION_DATE,
            )

        assert len(result.filing_candidates) == 1
        assert len(result.shareholding_data) == 1
        assert len(result.corporate_actions) == 1


# ===========================================================================
# 8. Step 3: document retrieval
# ===========================================================================


class TestStep3DocumentRetrieval:
    @pytest.mark.asyncio()
    async def test_retrieves_documents(self) -> None:
        agent, run_service, _ = _build_agent()
        candidates = [_make_source_candidate("f1"), _make_source_candidate("f2")]

        with (
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new_callable=AsyncMock,
                return_value=DOC_UUID,
            ),
        ):
            config = ManagementGovernanceConfig()
            docs, doc_ids = await agent._step_document_retrieval(
                COMPANY_UUID,
                candidates,
                config,
                RUN_UUID,
            )

        assert len(docs) == 2
        assert len(doc_ids) == 2

    @pytest.mark.asyncio()
    async def test_continues_on_provider_error(self) -> None:
        agent, _, _ = _build_agent()
        candidates = [_make_source_candidate("f1"), _make_source_candidate("f2")]

        call_count = 0

        async def _side_effect(inp: Any) -> RetrieveDocumentOutput:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError(provider="corporate_filings", message="timeout")
            return _make_doc_output()

        with (
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                side_effect=_side_effect,
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new_callable=AsyncMock,
                return_value=DOC_UUID,
            ),
        ):
            config = ManagementGovernanceConfig()
            docs, _ = await agent._step_document_retrieval(
                COMPANY_UUID,
                candidates,
                config,
                RUN_UUID,
            )

        assert len(docs) == 1


# ===========================================================================
# 9. Step 4: evidence extraction
# ===========================================================================


class TestStep4EvidenceExtraction:
    @pytest.mark.asyncio()
    async def test_extracts_evidence(self) -> None:
        agent, _, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            return_value=_make_llm_evidence_response(),
        )
        context = _make_context_output()
        documents = {"f1": _make_doc_output("f1")}
        document_ids = {"f1": DOC_UUID}
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=20000, warning_threshold=16000)

        with patch.object(
            agent._tools,
            "persist_evidence",
            new_callable=AsyncMock,
            return_value=PersistEvidenceOutput(
                evidence_ids=[uuid.uuid4(), uuid.uuid4()],
            ),
        ):
            evidence, evidence_ids = await agent._step_evidence_extraction(
                context,
                documents,
                document_ids,
                EXEC_UUID,
                token_budget,
                config,
                OBSERVATION_DATE,
            )

        assert len(evidence) == 2
        assert len(evidence_ids) == 2
        assert token_budget.total_tokens == 700

    @pytest.mark.asyncio()
    async def test_stops_on_budget_exhaustion(self) -> None:
        agent, _, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            return_value=_make_llm_evidence_response(),
        )
        context = _make_context_output()
        documents = {"f1": _make_doc_output("f1"), "f2": _make_doc_output("f2")}
        document_ids = {"f1": DOC_UUID, "f2": uuid.uuid4()}
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=100, warning_threshold=80)
        token_budget.record_usage(100, 0)

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._step_evidence_extraction(
                context,
                documents,
                document_ids,
                EXEC_UUID,
                token_budget,
                config,
                OBSERVATION_DATE,
            )


# ===========================================================================
# 10. Step 5: governance analysis
# ===========================================================================


class TestStep5GovernanceAnalysis:
    @pytest.mark.asyncio()
    async def test_analyzes_governance(self) -> None:
        agent, _, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            return_value=_make_llm_analysis_response(),
        )
        context = _make_context_output()
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test claim",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        evidence_ids = [uuid.uuid4()]
        discovery = _make_discovery_output()
        config = ManagementGovernanceConfig()
        token_budget = TokenBudget(budget=20000, warning_threshold=16000)

        with patch.object(
            agent._tools,
            "persist_findings",
            new_callable=AsyncMock,
            return_value=PersistFindingsOutput(
                finding_ids=[uuid.uuid4()],
                rejected=[],
            ),
        ):
            output, finding_ids = await agent._step_governance_analysis(
                context,
                evidence,
                evidence_ids,
                discovery,
                RUN_UUID,
                EXEC_UUID,
                token_budget,
                config,
                OBSERVATION_DATE,
            )

        assert isinstance(output, GovernanceAnalysisOutput)
        assert len(finding_ids) == 1
        assert token_budget.total_tokens == 1200


# ===========================================================================
# 11. Step 5a: deterministic shareholding/pledge finding generation
# ===========================================================================


class TestStep5aShareholdingFindings:
    def test_generates_fact_findings_per_category(self) -> None:
        snapshots = [_make_shareholding_snapshot()]
        findings = _generate_shareholding_findings(snapshots, OBSERVATION_DATE)
        fact_findings = [f for f in findings if f.finding_type == FindingType.FACT]
        assert len(fact_findings) == 4
        categories_mentioned = {f.content.split(" holding")[0] for f in fact_findings}
        assert categories_mentioned == {"Promoter", "FII", "DII", "Public"}

    def test_generates_trend_findings_with_multiple_quarters(self) -> None:
        snapshots = [
            _make_shareholding_snapshot(
                as_of_date=date(2025, 3, 31),
                quarter="Q4 FY25",
                promoter="55.00",
                fii="20.00",
                dii="15.00",
                public="10.00",
            ),
            _make_shareholding_snapshot(
                as_of_date=date(2025, 6, 30),
                quarter="Q1 FY26",
                promoter="53.00",
                fii="22.00",
                dii="15.00",
                public="10.00",
            ),
        ]
        findings = _generate_shareholding_findings(snapshots, OBSERVATION_DATE)
        calc_findings = [f for f in findings if f.finding_type == FindingType.CALCULATION]
        assert len(calc_findings) == 4

    def test_no_trend_with_single_snapshot(self) -> None:
        snapshots = [_make_shareholding_snapshot()]
        findings = _generate_shareholding_findings(snapshots, OBSERVATION_DATE)
        calc_findings = [f for f in findings if f.finding_type == FindingType.CALCULATION]
        assert len(calc_findings) == 0

    def test_empty_snapshots_returns_empty(self) -> None:
        findings = _generate_shareholding_findings([], OBSERVATION_DATE)
        assert findings == []

    def test_trend_direction_increasing(self) -> None:
        direction = _compute_trend_direction(Decimal("50"), Decimal("55"))
        assert direction == "increasing"

    def test_trend_direction_decreasing(self) -> None:
        direction = _compute_trend_direction(Decimal("55"), Decimal("50"))
        assert direction == "decreasing"

    def test_trend_direction_stable(self) -> None:
        direction = _compute_trend_direction(Decimal("50"), Decimal("50.3"))
        assert direction == "stable"

    def test_all_findings_use_shareholding_category(self) -> None:
        snapshots = [
            _make_shareholding_snapshot(as_of_date=date(2025, 3, 31), quarter="Q4 FY25"),
            _make_shareholding_snapshot(as_of_date=date(2025, 6, 30), quarter="Q1 FY26"),
        ]
        findings = _generate_shareholding_findings(snapshots, OBSERVATION_DATE)
        assert all(f.category == "shareholding" for f in findings)

    def test_all_findings_have_high_confidence(self) -> None:
        snapshots = [_make_shareholding_snapshot()]
        findings = _generate_shareholding_findings(snapshots, OBSERVATION_DATE)
        assert all(f.confidence == ConfidenceLevel.HIGH for f in findings)


class TestStep5aPledgeFindings:
    def test_generates_pledge_fact_findings(self) -> None:
        snapshots = [_make_shareholding_snapshot(pledged="5.00")]
        findings = _generate_pledge_findings(snapshots, OBSERVATION_DATE)
        fact_findings = [f for f in findings if f.finding_type == FindingType.FACT]
        assert len(fact_findings) == 1
        assert "5.00%" in fact_findings[0].content

    def test_no_pledge_findings_when_pledged_is_none(self) -> None:
        snapshots = [_make_shareholding_snapshot(pledged=None)]
        findings = _generate_pledge_findings(snapshots, OBSERVATION_DATE)
        assert findings == []

    def test_pledge_trend_with_multiple_snapshots(self) -> None:
        snapshots = [
            _make_shareholding_snapshot(
                as_of_date=date(2025, 3, 31),
                quarter="Q4 FY25",
                pledged="3.00",
            ),
            _make_shareholding_snapshot(
                as_of_date=date(2025, 6, 30),
                quarter="Q1 FY26",
                pledged="5.00",
            ),
        ]
        findings = _generate_pledge_findings(snapshots, OBSERVATION_DATE)
        calc_findings = [f for f in findings if f.finding_type == FindingType.CALCULATION]
        assert len(calc_findings) == 1
        assert "increasing" in calc_findings[0].content

    def test_all_pledge_findings_use_promoter_pledge_category(self) -> None:
        snapshots = [_make_shareholding_snapshot(pledged="5.00")]
        findings = _generate_pledge_findings(snapshots, OBSERVATION_DATE)
        assert all(f.category == "promoter_pledge" for f in findings)


# ===========================================================================
# 12. Step 6: governance validation (6 checks)
# ===========================================================================


class TestStep6GovernanceValidation:
    def _make_minimal_analysis(
        self,
        **kwargs: Any,
    ) -> GovernanceAnalysisOutput:
        data = _make_governance_analysis_dict(**kwargs)
        return GovernanceAnalysisOutput.model_validate(data)

    def test_valid_output_passes_validation(self) -> None:
        analysis = self._make_minimal_analysis()
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.rejected_count == 0

    def test_invalid_statement_id_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(uuid.uuid4()),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Evidence shows target met",
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.statement_updates_rejected == 1

    def test_terminal_transition_without_evidence_rejected(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "Just because",
                }
            ],
        )
        result = _validate_governance_output(
            analysis,
            [],
            [],
            [],
            stmts,
            OBSERVATION_DATE,
        )
        assert result.statement_updates_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "missing_outcome_evidence" in issue_types

    def test_terminal_re_transition_rejected(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.MET,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Actually missed",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Oops",
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            stmts,
            OBSERVATION_DATE,
        )
        assert result.statement_updates_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "terminal_re_transition" in issue_types

    def test_unknown_transition_without_resolution_detail_rejected(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "UNKNOWN",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "No info",
                }
            ],
        )
        result = _validate_governance_output(
            analysis,
            [],
            [],
            [],
            stmts,
            OBSERVATION_DATE,
        )
        assert result.statement_updates_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "missing_resolution_detail" in issue_types

    def test_valid_statement_update_passes(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved 22% growth",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Evidence confirms",
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Revenue grew 22%",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            stmts,
            OBSERVATION_DATE,
        )
        assert result.statement_updates_valid == 1
        assert result.statement_updates_rejected == 0

    def test_new_statement_invalid_category_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            new_statements=[
                {
                    "statement": "We will grow",
                    "statement_date": "2025-09-30",
                    "category": "INVALID_CATEGORY",
                    "expected_outcome": "Growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                claim="We will grow",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.new_statements_rejected == 1

    def test_new_statement_invalid_evidence_index_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            new_statements=[
                {
                    "statement": "We plan 15% margin",
                    "statement_date": "2025-09-30",
                    "category": "MARGIN_GUIDANCE",
                    "expected_outcome": "15% margin",
                    "expected_timeframe": "FY26",
                    "evidence_index": 99,
                }
            ],
        )
        result = _validate_governance_output(
            analysis,
            [],
            [],
            [],
            [],
            OBSERVATION_DATE,
        )
        assert result.new_statements_rejected == 1

    def test_finding_invalid_category_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "totally_invalid",
                    "content": "Bad category finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.rejected_count >= 1

    def test_fact_without_evidence_warning(self) -> None:
        analysis = self._make_minimal_analysis(
            capital_allocation=[
                {
                    "finding_type": "FACT",
                    "category": "capital_allocation",
                    "content": "Fact without evidence",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        result = _validate_governance_output(
            analysis,
            [],
            [],
            [],
            [],
            OBSERVATION_DATE,
        )
        issue_types = [i.issue_type for i in result.issues]
        assert "fact_without_evidence" in issue_types

    def test_temporal_violation_warning(self) -> None:
        analysis = self._make_minimal_analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Future finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": "2025-12-31",
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        issue_types = [i.issue_type for i in result.issues]
        assert "temporal_violation" in issue_types

    def test_red_flag_invalid_category_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            red_flags=[
                {
                    "category": "totally_wrong_category",
                    "description": "Bad flag",
                    "severity": "HIGH",
                    "justification": "Because",
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.red_flags_rejected == 1

    def test_red_flag_without_evidence_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Pledge is high",
                    "severity": "HIGH",
                    "justification": "Because data shows",
                    "evidence_indices": [],
                }
            ],
        )
        result = _validate_governance_output(
            analysis,
            [],
            [],
            [],
            [],
            OBSERVATION_DATE,
        )
        assert result.red_flags_rejected == 1

    def test_valid_red_flag_passes(self) -> None:
        analysis = self._make_minimal_analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Pledge rising",
                    "severity": "MEDIUM",
                    "justification": "Pledged shares increased",
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Pledge at 15%",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(
            analysis,
            [],
            evidence,
            [uuid.uuid4()],
            [],
            OBSERVATION_DATE,
        )
        assert result.red_flags_valid == 1
        assert result.red_flags_rejected == 0

    # -- F-01: NOT_DUE with status transition ----------------------------------

    def test_not_due_with_transition_rejected(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20% by FY26",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": None,
                    "outcome_evidence_index": 0,
                    "resolution_detail": "NOT_DUE",
                    "justification": "Timeframe not elapsed but marking met",
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Revenue grew 22%",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(analysis, [], evidence, [uuid.uuid4()], stmts, OBSERVATION_DATE)
        assert result.statement_updates_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "not_due_with_transition" in issue_types

    def test_not_due_without_transition_passes(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20% by FY26",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "PENDING",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": "NOT_DUE",
                    "justification": "Timeframe not elapsed",
                }
            ],
        )
        result = _validate_governance_output(analysis, [], [], [], stmts, OBSERVATION_DATE)
        assert result.statement_updates_valid == 1
        assert result.statement_updates_rejected == 0
        issue_types = [i.issue_type for i in result.issues]
        assert "not_due_with_transition" not in issue_types

    # -- F-02: REVISED without replacement statement ----------------------------

    def test_revised_without_replacement_statement_rejected(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Revised: original target superseded",
                    "outcome_evidence_index": 0,
                    "resolution_detail": "REVISED",
                    "justification": "Management revised guidance",
                }
            ],
            new_statements=[],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Management revised growth target",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(analysis, [], evidence, [uuid.uuid4()], stmts, OBSERVATION_DATE)
        assert result.statement_updates_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "revised_without_replacement" in issue_types

    def test_revised_with_replacement_statement_passes(self) -> None:
        stmts = [
            ManagementStatementSummary(
                id=STMT_UUID_1,
                statement_date=date(2025, 4, 15),
                statement="Revenue growth 20%",
                category=ManagementStatementCategory.REVENUE_GUIDANCE,
                status=ManagementStatementStatus.PENDING,
            ),
        ]
        analysis = self._make_minimal_analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Revised: original 20% superseded by 15%",
                    "outcome_evidence_index": 0,
                    "resolution_detail": "REVISED",
                    "justification": "Management revised guidance downward",
                }
            ],
            new_statements=[
                {
                    "statement": "Revenue growth 15% revised guidance",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "15% revenue growth FY26",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                claim="Management revised growth target to 15%",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(analysis, [], evidence, [uuid.uuid4()], stmts, OBSERVATION_DATE)
        assert result.statement_updates_valid == 1
        assert result.statement_updates_rejected == 0
        issue_types = [i.issue_type for i in result.issues]
        assert "revised_without_replacement" not in issue_types

    # -- F-03: MANAGEMENT_CLAIM without source citation -------------------------

    def test_management_claim_without_evidence_warning(self) -> None:
        analysis = self._make_minimal_analysis(
            capital_allocation=[
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "capital_allocation",
                    "content": "Management claims 25% ROCE target",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        result = _validate_governance_output(analysis, [], [], [], [], OBSERVATION_DATE)
        issue_types = [i.issue_type for i in result.issues]
        assert "management_claim_without_citation" in issue_types
        matching = [i for i in result.issues if i.issue_type == "management_claim_without_citation"]
        assert matching[0].action == "warning"

    def test_management_claim_with_evidence_no_warning(self) -> None:
        analysis = self._make_minimal_analysis(
            capital_allocation=[
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "capital_allocation",
                    "content": "Management claims 25% ROCE target",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                claim="ROCE target 25%",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]
        result = _validate_governance_output(analysis, [], evidence, [uuid.uuid4()], [], OBSERVATION_DATE)
        issue_types = [i.issue_type for i in result.issues]
        assert "management_claim_without_citation" not in issue_types

    # -- F-04: Red flag empty justification -------------------------------------

    def test_red_flag_empty_justification_rejected(self) -> None:
        analysis = self._make_minimal_analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Pledge is high",
                    "severity": "HIGH",
                    "justification": "",
                    "evidence_indices": [0],
                }
            ],
        )
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Pledge at 15%",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        result = _validate_governance_output(analysis, [], evidence, [uuid.uuid4()], [], OBSERVATION_DATE)
        assert result.red_flags_rejected == 1
        issue_types = [i.issue_type for i in result.issues]
        assert "empty_justification" in issue_types

    # -- Existing shareholding tests -------------------------------------------

    def test_shareholding_sum_mismatch_warning(self) -> None:
        bad_snapshots = [
            _make_shareholding_snapshot(
                promoter="50.00",
                fii="20.00",
                dii="15.00",
                public="10.00",
            ),
        ]
        sh_findings = _generate_shareholding_findings(bad_snapshots, OBSERVATION_DATE)
        analysis = self._make_minimal_analysis()

        result = _validate_governance_output(
            analysis,
            sh_findings,
            [],
            [],
            [],
            OBSERVATION_DATE,
        )
        issue_types = [i.issue_type for i in result.issues]
        assert "sum_mismatch" in issue_types

    def test_shareholding_sum_within_tolerance_no_warning(self) -> None:
        good_snapshots = [
            _make_shareholding_snapshot(
                promoter="55.00",
                fii="20.00",
                dii="15.00",
                public="10.00",
            ),
        ]
        sh_findings = _generate_shareholding_findings(good_snapshots, OBSERVATION_DATE)
        analysis = self._make_minimal_analysis()

        result = _validate_governance_output(
            analysis,
            sh_findings,
            [],
            [],
            [],
            OBSERVATION_DATE,
        )
        issue_types = [i.issue_type for i in result.issues]
        assert "sum_mismatch" not in issue_types


# ===========================================================================
# 13. Step 7: persistence
# ===========================================================================


class TestStep7Persistence:
    @pytest.mark.asyncio()
    async def test_persists_all_data_types(self) -> None:
        agent, _, _ = _build_agent()
        context = _make_context_output()
        analysis = GovernanceAnalysisOutput.model_validate(
            _make_governance_analysis_dict(),
        )
        discovery = _make_discovery_output()
        validation = GovernanceValidationResult(
            total_findings=1,
            valid_count=1,
            rejected_count=0,
            statement_updates_valid=0,
            statement_updates_rejected=0,
            new_statements_valid=0,
            new_statements_rejected=0,
            red_flags_valid=0,
            red_flags_rejected=0,
            issues=[],
        )

        created_stmt_id = uuid.uuid4()
        sh_id = uuid.uuid4()
        pledge_id = uuid.uuid4()
        ca_id = uuid.uuid4()

        with (
            patch.object(
                agent._tools,
                "persist_findings",
                new_callable=AsyncMock,
                return_value=PersistFindingsOutput(
                    finding_ids=[uuid.uuid4()],
                    rejected=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_management_statements",
                new_callable=AsyncMock,
                return_value=PersistStatementsOutput(
                    created_ids=[created_stmt_id],
                    updated_ids=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_shareholding",
                new_callable=AsyncMock,
                return_value=PersistShareholdingOutput(
                    persisted_ids=[sh_id],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_governance_data",
                new_callable=AsyncMock,
                return_value=PersistGovernanceDataOutput(
                    pledge_ids=[pledge_id],
                    corporate_action_ids=[ca_id],
                ),
            ),
        ):
            sh_findings = [
                GeneratedFinding(
                    finding_type=FindingType.FACT,
                    category="shareholding",
                    content="Promoter holding was 55% as of Q1 FY26",
                    confidence=ConfidenceLevel.HIGH,
                    source_publication_date=date(2025, 6, 30),
                ),
            ]

            result = await agent._step_persistence(
                context,
                analysis,
                sh_findings,
                validation,
                [uuid.uuid4()],
                discovery,
                RUN_UUID,
                OBSERVATION_DATE,
            )

        sh_finding_ids, created, updated, sh_ids, p_ids, ca_ids = result
        assert len(sh_finding_ids) == 1
        assert created == [created_stmt_id]
        assert sh_ids == [sh_id]
        assert p_ids == [pledge_id]
        assert ca_ids == [ca_id]


# ===========================================================================
# 14. Error handling / partial completion
# ===========================================================================


class TestErrorHandling:
    @pytest.mark.asyncio()
    async def test_token_budget_exhaustion_returns_partial(self) -> None:
        agent, run_service, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            side_effect=TokenBudgetExhaustedError(20001, 20000),
        )

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=_make_discovery_output(),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
            ),
            patch.object(
                agent._tools,
                "create_research_document",
                new_callable=AsyncMock,
                return_value=DOC_UUID,
            ),
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"
        assert result.error is not None
        run_service.partial_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_early_step_failure_returns_failed(self) -> None:
        agent, run_service, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "FAILED"
        assert result.error is not None

    @pytest.mark.asyncio()
    async def test_late_step_failure_returns_partial(self) -> None:
        agent, run_service, mocks = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                _make_llm_analysis_response(),
            ],
        )

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "discover_governance_sources",
                new_callable=AsyncMock,
                return_value=_make_discovery_output(),
            ),
            patch.object(
                agent._tools,
                "retrieve_document",
                new_callable=AsyncMock,
                return_value=_make_doc_output(),
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
                return_value=PersistEvidenceOutput(
                    evidence_ids=[uuid.uuid4(), uuid.uuid4()],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_findings",
                new_callable=AsyncMock,
                return_value=PersistFindingsOutput(
                    finding_ids=[uuid.uuid4()],
                    rejected=[],
                ),
            ),
            patch.object(
                agent._tools,
                "persist_management_statements",
                new_callable=AsyncMock,
                side_effect=Exception("Persistence explosion"),
            ),
        ):
            request = ManagementGovernanceResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=OBSERVATION_DATE,
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"
        run_service.partial_run.assert_awaited_once()


# ===========================================================================
# 15. LLM response parsing
# ===========================================================================


class TestLLMResponseParsing:
    def test_parse_evidence_extraction_valid(self) -> None:
        response = _make_llm_evidence_response()
        output = _parse_evidence_extraction_response(response)
        assert isinstance(output, EvidenceExtractionOutput)
        assert len(output.evidences) == 2

    def test_parse_evidence_extraction_invalid_json(self) -> None:
        response = LLMResponse(
            content="not json",
            model="mock",
            usage=ProviderTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_evidence_extraction_response(response)

    def test_parse_evidence_extraction_invalid_schema(self) -> None:
        response = LLMResponse(
            content='{"wrong_field": []}',
            model="mock",
            usage=ProviderTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_evidence_extraction_response(response)

    def test_parse_governance_analysis_valid(self) -> None:
        response = _make_llm_analysis_response()
        output = _parse_governance_analysis_response(response)
        assert isinstance(output, GovernanceAnalysisOutput)
        assert len(output.capital_allocation_findings) == 1

    def test_parse_governance_analysis_invalid_json(self) -> None:
        response = LLMResponse(
            content="not json",
            model="mock",
            usage=ProviderTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_governance_analysis_response(response)

    def test_parse_governance_analysis_missing_fields(self) -> None:
        response = LLMResponse(
            content='{"only_one_field": []}',
            model="mock",
            usage=ProviderTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError):
            _parse_governance_analysis_response(response)
