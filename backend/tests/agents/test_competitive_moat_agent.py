"""Comprehensive tests for Phase 10.4 Competitive Moat Agent.

Covers:
 1. Agent construction / dependency injection
 2. Full happy-path execution
 3. Deterministic step runner
 4. LLM step runner with retry
 5. Token budget enforcement
 6. Step 1: company context load
 7. Step 2: moat source discovery
 8. Step 3: document retrieval
 9. Step 4: evidence extraction
10. Step 5: moat analysis
11. Step 6: moat validation (9 deterministic checks)
12. Step 7: durability challenge
13. Error handling / partial completion
14. LLM response parsing
15. Assessment conversion
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
from app.agents.competitive_moat.agent import (
    CompetitiveMoatAgent,
    _convert_assessments,
    _parse_durability_challenge_response,
    _parse_evidence_extraction_response,
    _parse_moat_analysis_response,
    _validate_moat_assessments,
)
from app.agents.competitive_moat.tools import CompetitiveMoatTools
from app.agents.contracts import (
    MOAT_AGENT_NAME,
    MOAT_AGENT_TOKEN_BUDGET,
    MOAT_AGENT_TOKEN_WARNING,
    MOAT_FINDING_CATEGORIES,
    MOAT_RESEARCH_STEPS,
    DiscoverMoatSourcesOutput,
    DurabilityChallengeOutput,
    EvidenceExtractionOutput,
    ExtractedEvidence,
    GeneratedFinding,
    GetPeerDataOutput,
    LoadContextOutput,
    MoatAssessmentDraft,
    MoatResearchConfig,
    MoatResearchRequest,
    MoatResearchResult,
    PeerCompanySummary,
    PersistEvidenceOutput,
    PersistFindingsOutput,
    PersistMoatAssessmentsOutput,
    RetrieveDocumentOutput,
    SourceCandidate,
    TokenBudget,
)
from app.models.enums import (
    AgentExecutionStatus,
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    MoatStrength,
    MoatType,
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
INDUSTRY_UUID = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000001")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_16_MOAT_TYPES = [
    "BRAND",
    "COST_ADVANTAGE",
    "NETWORK_EFFECT",
    "SWITCHING_COST",
    "DISTRIBUTION",
    "SCALE",
    "REGULATORY",
    "IP",
    "TECHNOLOGY",
    "DATA",
    "ECOSYSTEM",
    "CUSTOMER_EMBEDDEDNESS",
    "MANUFACTURING",
    "SUPPLY_CHAIN",
    "CAPITAL_ACCESS",
    "LOCATION",
]


def _make_context_output(
    *,
    company_id: uuid.UUID = COMPANY_UUID,
    company_name: str = "Reliance Industries Ltd",
    nse_symbol: str | None = "RELIANCE",
    industry_id: uuid.UUID | None = INDUSTRY_UUID,
    industry_name: str | None = "Oil & Gas",
) -> LoadContextOutput:
    return LoadContextOutput(
        company_id=company_id,
        company_name=company_name,
        nse_symbol=nse_symbol,
        industry_id=industry_id,
        industry_name=industry_name,
        company_findings=[],
        industry_findings=[],
        has_company_research=False,
        has_industry_research=False,
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


def _make_doc_output(
    filing_id: str = "filing-1",
    content: str = "Sample filing content for testing.",
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
                "claim": "Revenue was Rs 950,000 crore in FY2025",
                "context": "From audited financials",
                "page_or_section": "Section 3",
                "confidence": "HIGH",
            },
            {
                "evidence_type": "MANAGEMENT_STATEMENT",
                "claim": "Management expects 20% growth in FY2026",
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


def _make_16_assessment_dicts(
    *,
    strength: str = "NONE",
    confidence: str = "LOW",
) -> list[dict[str, Any]]:
    return [
        {
            "moat_type": mt,
            "strength": strength,
            "durability_years": None,
            "explanation": f"Assessment for {mt}",
            "threats": None,
            "competitor_comparison": None,
            "confidence": confidence,
            "evidence_indices": None,
            "counter_evidence_indices": None,
        }
        for mt in _ALL_16_MOAT_TYPES
    ]


def _make_llm_analysis_response(
    assessments: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> LLMResponse:
    if assessments is None:
        assessments = _make_16_assessment_dicts()
    if findings is None:
        findings = [
            {
                "finding_type": "AI_INFERENCE",
                "category": "brand_moat",
                "content": "Brand recognition is moderate in the market",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": None,
            },
        ]
    return LLMResponse(
        content=json.dumps({"assessments": assessments, "findings": findings}),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=800,
            output_tokens=400,
            total_tokens=1200,
        ),
        finish_reason="stop",
    )


def _make_llm_durability_response(
    findings: list[dict[str, Any]] | None = None,
) -> LLMResponse:
    if findings is None:
        findings = [
            {
                "finding_type": "AI_INFERENCE",
                "category": "moat_durability",
                "content": "Brand moat is durable for 5-10 years",
                "confidence": "MEDIUM",
                "source_publication_date": None,
                "evidence_indices": None,
            },
        ]
    return LLMResponse(
        content=json.dumps({"findings": findings}),
        model="mock-llm",
        usage=ProviderTokenUsage(
            input_tokens=400,
            output_tokens=150,
            total_tokens=550,
        ),
        finish_reason="stop",
    )


def _make_run(run_id: uuid.UUID = RUN_UUID) -> ResearchRun:
    run = ResearchRun(
        id=run_id,
        company_id=COMPANY_UUID,
        initiated_by="test_user",
        status="CREATED",
        run_type="competitive_moat",
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
        agent_name=MOAT_AGENT_NAME,
        attempt_number=1,
        status=AgentExecutionStatus.RUNNING,
        model_provider="llm",
        model_name="default",
    )
    execution.created_at = datetime.now(UTC)
    return execution


def _make_7_steps(run_id: uuid.UUID = RUN_UUID) -> list[ResearchRunStep]:
    names = [s.step_name for s in MOAT_RESEARCH_STEPS]
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
        self.get_runs_for_industry = AsyncMock(return_value=[])
        self.get_findings = AsyncMock(return_value=[])


def _build_agent(
    *,
    run_service: MockRunService | None = None,
    llm_responses: list[LLMResponse] | None = None,
) -> tuple[CompetitiveMoatAgent, MockRunService, dict[str, AsyncMock]]:
    session = AsyncMock()
    session.flush = AsyncMock()

    if run_service is None:
        run_service = MockRunService()

    search = AsyncMock()
    news = AsyncMock()
    corporate_filings = AsyncMock()
    llm = AsyncMock()

    if llm_responses:
        llm.generate = AsyncMock(side_effect=llm_responses)
    else:
        llm.generate = AsyncMock(return_value=_make_llm_evidence_response())

    agent = CompetitiveMoatAgent(
        session=session,
        run_service=run_service,  # type: ignore[arg-type]
        search=search,
        news=news,
        corporate_filings=corporate_filings,
        llm=llm,
    )

    mocks = {
        "session": session,
        "search": search,
        "news": news,
        "corporate_filings": corporate_filings,
        "llm": llm,
    }

    return agent, run_service, mocks


def _make_peer_data_output() -> GetPeerDataOutput:
    return GetPeerDataOutput(
        peers=[
            PeerCompanySummary(
                company_id=uuid.uuid4(),
                name="ONGC Ltd",
                nse_symbol="ONGC",
                market_cap=Decimal("150000"),
            ),
        ],
    )


# ===========================================================================
# 1. Agent construction / dependency injection
# ===========================================================================


class TestAgentConstruction:
    def test_agent_creates_tools(self) -> None:
        agent, _, _ = _build_agent()
        assert isinstance(agent._tools, CompetitiveMoatTools)

    def test_agent_stores_llm_provider(self) -> None:
        agent, _, mocks = _build_agent()
        assert agent._llm is mocks["llm"]

    def test_agent_stores_run_service(self) -> None:
        agent, run_service, _ = _build_agent()
        assert agent._run_service is run_service

    def test_result_model_is_frozen(self) -> None:
        result = MoatResearchResult(
            status="COMPLETED",
            run_id=RUN_UUID,
        )
        with pytest.raises(PydanticValidationError):
            result.status = "FAILED"  # type: ignore[misc]


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
                _make_llm_durability_response(),
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
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
            patch.object(
                agent._tools,
                "discover_moat_sources",
                new_callable=AsyncMock,
                return_value=DiscoverMoatSourcesOutput(
                    candidates=[_make_source_candidate()],
                ),
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
                "persist_moat_assessments",
                new_callable=AsyncMock,
                return_value=PersistMoatAssessmentsOutput(
                    assessment_ids=[uuid.uuid4() for _ in range(16)],
                ),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "COMPLETED"
        assert result.run_id == RUN_UUID
        assert result.error is None
        assert len(result.assessment_ids) == 16

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
                _make_llm_durability_response(),
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
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
            patch.object(
                agent._tools,
                "discover_moat_sources",
                new_callable=AsyncMock,
                return_value=DiscoverMoatSourcesOutput(
                    candidates=[_make_source_candidate()],
                ),
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
                "persist_moat_assessments",
                new_callable=AsyncMock,
                return_value=PersistMoatAssessmentsOutput(
                    assessment_ids=[uuid.uuid4() for _ in range(16)],
                ),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            await agent.execute(request)

        run_service.create_steps.assert_awaited_once()
        step_defs = run_service.create_steps.call_args[0][1]
        assert len(step_defs) == 7
        assert step_defs[0].step_name == "company_context_load"
        assert step_defs[6].step_name == "durability_challenge"


# ===========================================================================
# 3. Deterministic step runner
# ===========================================================================


class TestDeterministicStepRunner:
    @pytest.mark.asyncio()
    async def test_runs_coroutine_and_completes_step(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("test_step", 1)

        async def _coro() -> str:
            return "result"

        result = await agent._run_step_deterministic(step, _coro())
        assert result == "result"
        run_service.start_step.assert_awaited_once_with(step.id)
        run_service.complete_step.assert_awaited_once_with(step.id)

    @pytest.mark.asyncio()
    async def test_fails_step_on_exception(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("test_step", 1)

        async def _coro() -> str:
            msg = "boom"
            raise ValueError(msg)

        with pytest.raises(StepFailedError, match="test_step"):
            await agent._run_step_deterministic(step, _coro())

        run_service.fail_step.assert_awaited_once()


# ===========================================================================
# 4. LLM step runner with retry
# ===========================================================================


class TestLLMStepRunner:
    @pytest.mark.asyncio()
    async def test_succeeds_on_first_attempt(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=25000, warning_threshold=20000)
        config = MoatResearchConfig()

        async def _fn(exec_id: uuid.UUID) -> str:
            return "ok"

        result = await agent._run_step_llm(
            step,
            RUN_UUID,
            budget,
            config,
            _fn,
        )
        assert result == "ok"
        run_service.record_agent_execution.assert_awaited_once()
        run_service.complete_agent.assert_awaited_once()
        run_service.complete_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_retries_on_parsing_error(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=25000, warning_threshold=20000)
        config = MoatResearchConfig()

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
            budget,
            config,
            _fn,
        )
        assert result == "ok"
        assert call_count == 2
        assert run_service.record_agent_execution.await_count == 2
        run_service.fail_agent.assert_awaited_once()
        run_service.retry_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_retries_on_provider_error(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=25000, warning_threshold=20000)
        config = MoatResearchConfig()

        call_count = 0

        async def _fn(exec_id: uuid.UUID) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError(
                    provider="llm",
                    message="timeout",
                    operation="generate",
                )
            return "ok"

        result = await agent._run_step_llm(
            step,
            RUN_UUID,
            budget,
            config,
            _fn,
        )
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio()
    async def test_fails_after_max_attempts(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=25000, warning_threshold=20000)
        config = MoatResearchConfig()

        async def _fn(exec_id: uuid.UUID) -> str:
            raise LLMParsingError("evidence_extraction", "bad json")

        with pytest.raises(StepFailedError, match="evidence_extraction"):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                budget,
                config,
                _fn,
            )

        assert run_service.record_agent_execution.await_count == 2
        assert run_service.fail_agent.await_count == 2
        run_service.fail_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_max_attempts_default_is_2(self) -> None:
        config = MoatResearchConfig()
        assert config.max_llm_attempts == 2

    @pytest.mark.asyncio()
    async def test_skips_step_when_budget_exhausted_before_start(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=100, warning_threshold=80)
        budget.record_usage(100, 0)
        config = MoatResearchConfig()

        async def _fn(exec_id: uuid.UUID) -> str:
            return "should not run"

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                budget,
                config,
                _fn,
            )

        run_service.skip_step.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_token_budget_exhausted_mid_step(self) -> None:
        agent, run_service, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        budget = TokenBudget(budget=100, warning_threshold=80)
        config = MoatResearchConfig()

        async def _fn(exec_id: uuid.UUID) -> str:
            raise TokenBudgetExhaustedError(200, 100)

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                budget,
                config,
                _fn,
            )

        run_service.fail_agent.assert_awaited_once()
        run_service.fail_step.assert_awaited_once()


# ===========================================================================
# 5. Token budget enforcement
# ===========================================================================


class TestTokenBudgetEnforcement:
    def test_moat_budget_defaults(self) -> None:
        assert MOAT_AGENT_TOKEN_BUDGET == 25000
        assert MOAT_AGENT_TOKEN_WARNING == 20000

    def test_config_defaults(self) -> None:
        config = MoatResearchConfig()
        assert config.token_budget == 25000
        assert config.token_warning_threshold == 20000

    @pytest.mark.asyncio()
    async def test_agent_returns_partial_on_exhaustion(self) -> None:
        ev_response = _make_llm_evidence_response()
        ev_response = LLMResponse(
            content=ev_response.content,
            model="mock",
            usage=ProviderTokenUsage(
                input_tokens=400,
                output_tokens=200,
                total_tokens=600,
            ),
            finish_reason="stop",
        )
        agent, run_service, _ = _build_agent(
            llm_responses=[ev_response],
        )
        small_config = MoatResearchConfig(
            token_budget=500,
            token_warning_threshold=400,
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
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
            patch.object(
                agent._tools,
                "discover_moat_sources",
                new_callable=AsyncMock,
                return_value=DiscoverMoatSourcesOutput(
                    candidates=[_make_source_candidate()],
                ),
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
                    evidence_ids=[uuid.uuid4()],
                ),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
                configuration=small_config,
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"
        assert result.error is not None


# ===========================================================================
# 6. Step 1: company context load
# ===========================================================================


class TestStep1CompanyContextLoad:
    @pytest.mark.asyncio()
    async def test_loads_context_and_peers(self) -> None:
        agent, _, _ = _build_agent()

        with (
            patch.object(
                agent._tools,
                "load_company_context",
                new_callable=AsyncMock,
                return_value=_make_context_output(),
            ),
            patch.object(
                agent._tools,
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            context, peer_summary = await agent._step_company_context_load(
                request,
            )

        assert context.company_name == "Reliance Industries Ltd"
        assert peer_summary is not None
        assert "ONGC" in peer_summary

    @pytest.mark.asyncio()
    async def test_no_peers_without_industry(self) -> None:
        agent, _, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            return_value=_make_context_output(industry_id=None),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            context, peer_summary = await agent._step_company_context_load(
                request,
            )

        assert peer_summary is None


# ===========================================================================
# 7. Step 2: moat source discovery
# ===========================================================================


class TestStep2SourceDiscovery:
    @pytest.mark.asyncio()
    async def test_returns_candidates(self) -> None:
        agent, _, _ = _build_agent()
        candidates = [
            _make_source_candidate("f-1"),
            _make_source_candidate("f-2"),
        ]

        with patch.object(
            agent._tools,
            "discover_moat_sources",
            new_callable=AsyncMock,
            return_value=DiscoverMoatSourcesOutput(candidates=candidates),
        ):
            result = await agent._step_moat_source_discovery(
                _make_context_output(),
                MoatResearchConfig(),
                date(2025, 9, 30),
            )

        assert len(result) == 2


# ===========================================================================
# 8. Step 3: document retrieval
# ===========================================================================


class TestStep3DocumentRetrieval:
    @pytest.mark.asyncio()
    async def test_retrieves_documents(self) -> None:
        agent, run_service, _ = _build_agent()
        sources = [_make_source_candidate("filing-1")]

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
            docs, doc_ids = await agent._step_document_retrieval(
                COMPANY_UUID,
                sources,
                MoatResearchConfig(),
                RUN_UUID,
            )

        assert len(docs) == 1
        assert "filing-1" in docs
        assert doc_ids["filing-1"] == DOC_UUID
        run_service.record_source_access.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_skips_failed_retrieval(self) -> None:
        agent, run_service, _ = _build_agent()
        sources = [_make_source_candidate("filing-1")]

        with patch.object(
            agent._tools,
            "retrieve_document",
            new_callable=AsyncMock,
            side_effect=ProviderError(
                message="network error",
                provider="search",
            ),
        ):
            docs, doc_ids = await agent._step_document_retrieval(
                COMPANY_UUID,
                sources,
                MoatResearchConfig(),
                RUN_UUID,
            )

        assert len(docs) == 0
        assert len(doc_ids) == 0
        run_service.record_source_access.assert_not_awaited()


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
        doc = _make_doc_output()
        documents = {"filing-1": doc}
        document_ids = {"filing-1": DOC_UUID}

        with patch.object(
            agent._tools,
            "persist_evidence",
            new_callable=AsyncMock,
            return_value=PersistEvidenceOutput(
                evidence_ids=[uuid.uuid4(), uuid.uuid4()],
            ),
        ):
            budget = TokenBudget(budget=25000, warning_threshold=20000)
            config = MoatResearchConfig()
            all_evidence, all_evidence_ids = await agent._step_evidence_extraction(
                context,
                documents,
                document_ids,
                EXEC_UUID,
                budget,
                config,
                date(2025, 9, 30),
            )

        assert len(all_evidence) == 2
        assert len(all_evidence_ids) == 2
        assert budget.total_tokens > 0

    @pytest.mark.asyncio()
    async def test_raises_on_budget_exhaustion(self) -> None:
        agent, _, _ = _build_agent()

        context = _make_context_output()
        documents = {"filing-1": _make_doc_output()}
        document_ids = {"filing-1": DOC_UUID}

        budget = TokenBudget(budget=10, warning_threshold=5)
        budget.record_usage(10, 0)
        config = MoatResearchConfig()

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._step_evidence_extraction(
                context,
                documents,
                document_ids,
                EXEC_UUID,
                budget,
                config,
                date(2025, 9, 30),
            )


# ===========================================================================
# 10. Step 5: moat analysis
# ===========================================================================


class TestStep5MoatAnalysis:
    @pytest.mark.asyncio()
    async def test_produces_assessments_and_findings(self) -> None:
        agent, _, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            return_value=_make_llm_analysis_response(),
        )

        context = _make_context_output()
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Revenue was 950,000 crore",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
        evidence_ids = [uuid.uuid4()]

        with patch.object(
            agent._tools,
            "persist_findings",
            new_callable=AsyncMock,
            return_value=PersistFindingsOutput(
                finding_ids=[uuid.uuid4()],
                rejected=[],
            ),
        ):
            budget = TokenBudget(budget=25000, warning_threshold=20000)
            config = MoatResearchConfig()
            assessments, findings, finding_ids = await agent._step_moat_analysis(
                context,
                evidence,
                evidence_ids,
                None,
                RUN_UUID,
                EXEC_UUID,
                budget,
                config,
                date(2025, 9, 30),
            )

        assert len(assessments) == 16
        assert len(findings) >= 1
        assert budget.total_tokens > 0


# ===========================================================================
# 11. Step 6: moat validation (9 deterministic checks)
# ===========================================================================


class TestStep6MoatValidation:
    def test_coverage_completeness_adds_missing(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NONE",
                explanation="No evidence",
                confidence="LOW",
            ),
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        assert result.total_assessments == 16
        types = {a.moat_type for a in validated}
        for mt in _ALL_16_MOAT_TYPES:
            assert mt in types
        missing_issues = [i for i in result.issues if i.issue_type == "missing_moat_type"]
        assert len(missing_issues) == 15

    def test_evidence_sufficiency_downgrades_to_none(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="NARROW" if mt == "BRAND" else "NONE",
                explanation=f"Assessment for {mt}",
                confidence="MEDIUM",
                evidence_indices=None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand_assessment = next(a for a in validated if a.moat_type == "BRAND")
        assert brand_assessment.strength == "NONE"
        assert result.downgraded_count >= 1
        ev_issues = [i for i in result.issues if i.issue_type == "insufficient_evidence"]
        assert len(ev_issues) == 1

    def test_durability_presence_warns(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="NARROW" if mt == "BRAND" else "NONE",
                durability_years=None,
                explanation=f"Assessment for {mt}",
                confidence="MEDIUM",
                evidence_indices=[0] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        _, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        dur_issues = [i for i in result.issues if i.issue_type == "missing_durability"]
        assert len(dur_issues) >= 1

    def test_threat_presence_warns(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="WIDE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="HIGH" if mt == "BRAND" else "LOW",
                evidence_indices=[0, 1, 2] if mt == "BRAND" else None,
                threats=None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        _, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        threat_issues = [i for i in result.issues if i.issue_type == "missing_threats"]
        assert len(threat_issues) >= 1

    def test_temporal_consistency_flags_future_dates(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.AI_INFERENCE,
                category="brand_moat",
                content="Some finding",
                confidence=ConfidenceLevel.MEDIUM,
                source_publication_date=date(2025, 10, 15),
            ),
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        temporal = [i for i in result.issues if i.issue_type == "temporal_violation"]
        assert len(temporal) == 1

    def test_temporal_consistency_allows_past_dates(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.AI_INFERENCE,
                category="brand_moat",
                content="Some finding",
                confidence=ConfidenceLevel.MEDIUM,
                source_publication_date=date(2025, 5, 30),
            ),
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        temporal = [i for i in result.issues if i.issue_type == "temporal_violation"]
        assert len(temporal) == 0

    def test_category_validity_flags_invalid(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.AI_INFERENCE,
                category="nonexistent_category",
                content="Finding with bad category",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        cat_issues = [i for i in result.issues if i.issue_type == "invalid_category"]
        assert len(cat_issues) == 1

    def test_all_moat_finding_categories_accepted(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.AI_INFERENCE,
                category=cat,
                content=f"Finding for {cat}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            for cat in MOAT_FINDING_CATEGORIES
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        cat_issues = [i for i in result.issues if i.issue_type == "invalid_category"]
        assert len(cat_issues) == 0

    def test_content_non_empty_flags_blank(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.AI_INFERENCE,
                category="brand_moat",
                content="   ",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        empty_issues = [i for i in result.issues if i.issue_type == "empty_content"]
        assert len(empty_issues) == 1

    def test_fact_evidence_linkage_warns(self) -> None:
        findings = [
            GeneratedFinding(
                finding_type=FindingType.FACT,
                category="brand_moat",
                content="A fact with no evidence links",
                confidence=ConfidenceLevel.HIGH,
                evidence_indices=None,
            ),
        ]
        _, result = _validate_moat_assessments(
            [],
            findings,
            [],
            [],
            date(2025, 9, 30),
        )
        link_issues = [i for i in result.issues if i.issue_type == "fact_without_evidence"]
        assert len(link_issues) == 1

    def test_strength_confidence_consistency_downgrades_wide_low(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="WIDE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="LOW",
                evidence_indices=[0, 1, 2] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand_assessment = next(a for a in validated if a.moat_type == "BRAND")
        assert brand_assessment.strength == "MODERATE"
        sc_issues = [i for i in result.issues if i.issue_type == "strength_confidence_mismatch"]
        assert len(sc_issues) == 1

    def test_wide_with_2_evidence_downgrades_to_moderate(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="WIDE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="HIGH",
                evidence_indices=[0, 1] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand = next(a for a in validated if a.moat_type == "BRAND")
        assert brand.strength == "MODERATE"
        ev_issues = [i for i in result.issues if i.issue_type == "insufficient_evidence"]
        assert len(ev_issues) == 1
        assert ev_issues[0].action == "downgraded_to_moderate"

    def test_wide_with_1_evidence_downgrades_to_narrow(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="WIDE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="HIGH",
                evidence_indices=[0] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand = next(a for a in validated if a.moat_type == "BRAND")
        assert brand.strength == "NARROW"
        ev_issues = [i for i in result.issues if i.issue_type == "insufficient_evidence"]
        assert len(ev_issues) == 1
        assert ev_issues[0].action == "downgraded_to_narrow"

    def test_moderate_with_1_evidence_downgrades_to_narrow(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="MODERATE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="MEDIUM",
                evidence_indices=[0] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand = next(a for a in validated if a.moat_type == "BRAND")
        assert brand.strength == "NARROW"
        ev_issues = [i for i in result.issues if i.issue_type == "insufficient_evidence"]
        assert len(ev_issues) == 1
        assert ev_issues[0].action == "downgraded_to_narrow"

    def test_wide_medium_confidence_downgrades_to_moderate(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="WIDE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="MEDIUM" if mt == "BRAND" else "LOW",
                evidence_indices=[0, 1, 2] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand = next(a for a in validated if a.moat_type == "BRAND")
        assert brand.strength == "MODERATE"
        sc_issues = [i for i in result.issues if i.issue_type == "strength_confidence_mismatch"]
        assert len(sc_issues) == 1
        assert sc_issues[0].action == "downgraded_to_moderate"

    def test_moderate_low_confidence_downgrades_to_narrow(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="MODERATE" if mt == "BRAND" else "NONE",
                durability_years=10 if mt == "BRAND" else None,
                explanation=f"Assessment for {mt}",
                confidence="LOW",
                evidence_indices=[0, 1] if mt == "BRAND" else None,
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        brand = next(a for a in validated if a.moat_type == "BRAND")
        assert brand.strength == "NARROW"
        sc_issues = [i for i in result.issues if i.issue_type == "strength_confidence_mismatch"]
        assert len(sc_issues) == 1
        assert sc_issues[0].action == "downgraded_to_narrow"

    def test_all_none_passes_cleanly(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="NONE",
                explanation=f"No evidence for {mt}",
                confidence="LOW",
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        validated, result = _validate_moat_assessments(
            drafts,
            [],
            [],
            [],
            date(2025, 9, 30),
        )
        assert result.total_assessments == 16
        assert result.downgraded_count == 0
        assert len(result.issues) == 0


# ===========================================================================
# 12. Step 7: durability challenge
# ===========================================================================


class TestStep7DurabilityChallenge:
    @pytest.mark.asyncio()
    async def test_generates_durability_findings(self) -> None:
        agent, _, mocks = _build_agent()
        mocks["llm"].generate = AsyncMock(
            return_value=_make_llm_durability_response(),
        )

        assessments = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NARROW",
                durability_years=5,
                explanation="Moderate brand",
                confidence="MEDIUM",
                evidence_indices=[0],
            ),
        ]
        evidence = [
            ExtractedEvidence(
                evidence_type=EvidenceType.FACT,
                claim="Strong brand presence",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]

        with patch.object(
            agent._tools,
            "persist_findings",
            new_callable=AsyncMock,
            return_value=PersistFindingsOutput(
                finding_ids=[uuid.uuid4()],
                rejected=[],
            ),
        ):
            budget = TokenBudget(budget=25000, warning_threshold=20000)
            config = MoatResearchConfig()
            finding_ids = await agent._step_durability_challenge(
                "Reliance Industries Ltd",
                assessments,
                evidence,
                RUN_UUID,
                EXEC_UUID,
                budget,
                config,
                date(2025, 9, 30),
            )

        assert len(finding_ids) == 1
        assert budget.total_tokens > 0


# ===========================================================================
# 13. Error handling / partial completion
# ===========================================================================


class TestErrorHandling:
    @pytest.mark.asyncio()
    async def test_early_step_failure_returns_failed(self) -> None:
        agent, run_service, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            side_effect=ValueError("company not found"),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "FAILED"
        assert result.error is not None
        run_service.fail_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_step5_failure_returns_failed(self) -> None:
        agent, run_service, mocks = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                ProviderError(
                    provider="llm",
                    message="service down",
                    operation="generate",
                ),
                ProviderError(
                    provider="llm",
                    message="service down",
                    operation="generate",
                ),
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
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
            patch.object(
                agent._tools,
                "discover_moat_sources",
                new_callable=AsyncMock,
                return_value=DiscoverMoatSourcesOutput(
                    candidates=[_make_source_candidate()],
                ),
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
                    evidence_ids=[uuid.uuid4()],
                ),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "FAILED"
        run_service.fail_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_step7_failure_returns_partial(self) -> None:
        agent, run_service, mocks = _build_agent(
            llm_responses=[
                _make_llm_evidence_response(),
                _make_llm_analysis_response(),
                ProviderError(
                    provider="llm",
                    message="service down",
                    operation="generate",
                ),
                ProviderError(
                    provider="llm",
                    message="service down",
                    operation="generate",
                ),
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
                "get_peer_data",
                new_callable=AsyncMock,
                return_value=_make_peer_data_output(),
            ),
            patch.object(
                agent._tools,
                "discover_moat_sources",
                new_callable=AsyncMock,
                return_value=DiscoverMoatSourcesOutput(
                    candidates=[_make_source_candidate()],
                ),
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
                "persist_moat_assessments",
                new_callable=AsyncMock,
                return_value=PersistMoatAssessmentsOutput(
                    assessment_ids=[uuid.uuid4() for _ in range(16)],
                ),
            ),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "PARTIAL"
        run_service.partial_run.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_unexpected_exception_returns_failed(self) -> None:
        agent, run_service, _ = _build_agent()

        with patch.object(
            agent._tools,
            "load_company_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            request = MoatResearchRequest(
                company_id=COMPANY_UUID,
                observation_date=date(2025, 9, 30),
                initiated_by="test_user",
            )
            result = await agent.execute(request)

        assert result.status == "FAILED"
        assert "unexpected" in result.error.lower()  # type: ignore[union-attr]
        run_service.fail_run.assert_awaited_once()


# ===========================================================================
# 14. LLM response parsing
# ===========================================================================


class TestResponseParsing:
    def test_parse_valid_evidence_response(self) -> None:
        response = _make_llm_evidence_response()
        result = _parse_evidence_extraction_response(response)
        assert isinstance(result, EvidenceExtractionOutput)
        assert len(result.evidences) == 2

    def test_parse_valid_analysis_response(self) -> None:
        response = _make_llm_analysis_response()
        result = _parse_moat_analysis_response(response)
        assert len(result.assessments) == 16
        assert len(result.findings) >= 1

    def test_parse_valid_durability_response(self) -> None:
        response = _make_llm_durability_response()
        result = _parse_durability_challenge_response(response)
        assert isinstance(result, DurabilityChallengeOutput)
        assert len(result.findings) == 1

    def test_parse_invalid_json_raises(self) -> None:
        response = LLMResponse(
            content="not valid json",
            model="mock",
            usage=ProviderTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            ),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError, match="evidence_extraction"):
            _parse_evidence_extraction_response(response)

    def test_parse_wrong_schema_raises_analysis(self) -> None:
        response = LLMResponse(
            content=json.dumps({"wrong_key": []}),
            model="mock",
            usage=ProviderTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            ),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError, match="moat_analysis"):
            _parse_moat_analysis_response(response)

    def test_parse_wrong_schema_raises_durability(self) -> None:
        response = LLMResponse(
            content=json.dumps({"wrong_key": []}),
            model="mock",
            usage=ProviderTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            ),
            finish_reason="stop",
        )
        with pytest.raises(LLMParsingError, match="durability_challenge"):
            _parse_durability_challenge_response(response)

    def test_parse_empty_evidences(self) -> None:
        response = LLMResponse(
            content=json.dumps({"evidences": []}),
            model="mock",
            usage=ProviderTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            ),
            finish_reason="stop",
        )
        result = _parse_evidence_extraction_response(response)
        assert result.evidences == []


# ===========================================================================
# 15. Assessment conversion
# ===========================================================================


class TestAssessmentConversion:
    def test_converts_valid_assessments(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NARROW",
                durability_years=5,
                explanation="Strong brand",
                confidence="MEDIUM",
                evidence_indices=[0],
            ),
        ]
        ev_ids = [uuid.uuid4()]
        items = _convert_assessments(drafts, ev_ids)
        assert len(items) == 1
        assert items[0].moat_type == MoatType.BRAND
        assert items[0].strength == MoatStrength.NARROW
        assert items[0].confidence == ConfidenceLevel.MEDIUM
        assert items[0].evidence_ids == [ev_ids[0]]

    def test_skips_unknown_moat_type(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="IMAGINARY",
                strength="NONE",
                explanation="Not real",
                confidence="LOW",
            ),
        ]
        items = _convert_assessments(drafts, [])
        assert len(items) == 0

    def test_defaults_invalid_strength_to_none(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="SUPER_WIDE",
                explanation="Invalid strength",
                confidence="MEDIUM",
            ),
        ]
        items = _convert_assessments(drafts, [])
        assert items[0].strength == MoatStrength.NONE

    def test_defaults_invalid_confidence_to_low(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NONE",
                explanation="Invalid confidence",
                confidence="SUPER_HIGH",
            ),
        ]
        items = _convert_assessments(drafts, [])
        assert items[0].confidence == ConfidenceLevel.LOW

    def test_out_of_range_evidence_index_skipped(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NARROW",
                explanation="Test",
                confidence="MEDIUM",
                evidence_indices=[0, 99],
            ),
        ]
        ev_id = uuid.uuid4()
        items = _convert_assessments(drafts, [ev_id])
        assert items[0].evidence_ids == [ev_id]

    def test_converts_threats(self) -> None:
        from app.agents.contracts import ThreatItem

        drafts = [
            MoatAssessmentDraft(
                moat_type="BRAND",
                strength="NARROW",
                explanation="Brand",
                confidence="MEDIUM",
                threats=[
                    ThreatItem(
                        description="New entrant",
                        severity="HIGH",
                        timeframe="2-3 years",
                    ),
                ],
            ),
        ]
        items = _convert_assessments(drafts, [])
        assert items[0].threats is not None
        assert len(items[0].threats) == 1
        assert items[0].threats[0]["description"] == "New entrant"

    def test_converts_all_16_types(self) -> None:
        drafts = [
            MoatAssessmentDraft(
                moat_type=mt,
                strength="NONE",
                explanation=f"Assessment for {mt}",
                confidence="LOW",
            )
            for mt in _ALL_16_MOAT_TYPES
        ]
        items = _convert_assessments(drafts, [])
        assert len(items) == 16
        converted_types = {i.moat_type for i in items}
        for mt in MoatType:
            assert mt in converted_types


# ===========================================================================
# 16. Step definitions
# ===========================================================================


class TestStepDefinitions:
    def test_7_steps_defined(self) -> None:
        assert len(MOAT_RESEARCH_STEPS) == 7

    def test_step_names(self) -> None:
        names = [s.step_name for s in MOAT_RESEARCH_STEPS]
        assert names == [
            "company_context_load",
            "moat_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "moat_analysis",
            "moat_validation",
            "durability_challenge",
        ]

    def test_llm_steps_flagged(self) -> None:
        llm_steps = [s for s in MOAT_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        llm_names = {s.step_name for s in llm_steps}
        assert llm_names == {
            "evidence_extraction",
            "moat_analysis",
            "durability_challenge",
        }

    def test_step_order_sequential(self) -> None:
        orders = [s.step_order for s in MOAT_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]
