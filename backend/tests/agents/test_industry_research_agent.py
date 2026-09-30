"""Comprehensive tests for Phase 9.3b.1 Industry Research Agent skeleton.

Covers:
 1. Agent construction / dependency injection
 2. Full happy-path execution (with LLM stubs)
 3. Step-level deterministic runner
 4. Step-level LLM runner with retry
 5. Token budget enforcement
 6. Finding validation logic (deterministic step 6)
 7. Error handling / partial completion (≥5 steps → PARTIAL, <5 → FAILED)
 8. Unexpected exception handling
 9. Industry validation step
10. Source discovery step
11. Document retrieval step
12. LLM stub boundary verification (no fabricated findings)
13. IndustryResearchResult contract
14. Step map construction from INDUSTRY_RESEARCH_STEPS
15. Configuration defaults
16. Agent attribution
17. Tool registry verification (canonical 8 agent-facing tools)
18. Temporal semantics (information_available_date vs publication_date)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agents.company_research.exceptions import (
    StepFailedError,
    TokenBudgetExhaustedError,
)
from app.agents.contracts import (
    INDUSTRY_AGENT_NAME,
    INDUSTRY_AGENT_TOKEN_BUDGET,
    INDUSTRY_AGENT_TOKEN_WARNING,
    INDUSTRY_RESEARCH_STEPS,
    MAX_LLM_ATTEMPTS,
    FindingValidationResult,
    IndustryResearchConfig,
    IndustryResearchRequest,
    NewsArticleResult,
    RetrieveIndustryDocumentOutput,
    SearchIndustryNewsInput,
    SourceCandidate,
    TokenBudget,
    ValidateIndustryOutput,
)
from app.agents.industry_research.agent import (
    IndustryResearchAgent,
    IndustryResearchResult,
)
from app.agents.industry_research.exceptions import IndustryNotFoundError
from app.agents.industry_research.tools import IndustryResearchTools
from app.models.enums import (
    AgentExecutionStatus,
    DocumentType,
    SourceTier,
    StepStatus,
)
from app.models.research import AgentExecution, ResearchRun, ResearchRunStep
from app.providers.errors import ProviderError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INDUSTRY_UUID = uuid.UUID("aabbccdd-1122-3344-5566-778899aabbcc")
RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
EXEC_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
DOC_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
STEP_UUID = uuid.UUID("99999999-8888-7777-6666-555544443333")
OBS_DATE = date(2025, 6, 15)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_validate_output(
    *,
    industry_id: uuid.UUID = INDUSTRY_UUID,
    name: str = "Information Technology",
    code: str = "IT",
    level: str = "INDUSTRY",
) -> ValidateIndustryOutput:
    return ValidateIndustryOutput(
        industry_id=industry_id,
        name=name,
        code=code,
        level=level,
    )


def _make_source_candidate(
    source_id: str = "report-1",
    source_type: DocumentType = DocumentType.RESEARCH_REPORT,
    provider: str = "search",
) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        source_type=source_type,
        provider=provider,
        title=f"Test Industry Report {source_id}",
        publication_date=date(2025, 5, 30),
        source_tier=SourceTier.TIER_2,
        url=f"https://example.com/{source_id}",
    )


def _make_doc_output(
    source_id: str = "report-1",
    content: str = "Sample industry report content.",
) -> RetrieveIndustryDocumentOutput:
    import hashlib

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return RetrieveIndustryDocumentOutput(
        content=content,
        content_type="text/snippet",
        content_hash=content_hash,
        source_id=source_id,
    )


def _make_run(run_id: uuid.UUID = RUN_UUID) -> ResearchRun:
    run = ResearchRun(
        id=run_id,
        target_type="industry",
        industry_id=INDUSTRY_UUID,
        initiated_by="test_user",
        status="CREATED",
        run_type="industry_research",
        trigger_type="manual",
        observation_date=OBS_DATE,
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


def _make_7_steps(run_id: uuid.UUID = RUN_UUID) -> list[ResearchRunStep]:
    names = [s.step_name for s in INDUSTRY_RESEARCH_STEPS]
    return [_make_step(name, i + 1, run_id) for i, name in enumerate(names)]


def _make_execution(exec_id: uuid.UUID = EXEC_UUID) -> AgentExecution:
    execution = AgentExecution(
        id=exec_id,
        research_run_id=RUN_UUID,
        step_id=STEP_UUID,
        agent_name=INDUSTRY_AGENT_NAME,
        attempt_number=1,
        status=AgentExecutionStatus.RUNNING,
        model_provider="llm",
        model_name="default",
    )
    execution.created_at = datetime.now(UTC)
    return execution


class MockRunService:
    """A mock ResearchRunService with all methods as AsyncMocks."""

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


def _build_agent(
    *,
    run_service: MockRunService | None = None,
) -> tuple[IndustryResearchAgent, MockRunService, dict[str, AsyncMock]]:
    session = AsyncMock()
    session.flush = AsyncMock()

    if run_service is None:
        run_service = MockRunService()

    search = AsyncMock()
    news = AsyncMock()

    agent = IndustryResearchAgent(
        session=session,
        run_service=run_service,  # type: ignore[arg-type]
        search=search,
        news=news,
    )

    mocks = {
        "session": session,
        "search": search,
        "news": news,
    }
    return agent, run_service, mocks


def _make_request(
    industry_id: uuid.UUID = INDUSTRY_UUID,
    observation_date: date = OBS_DATE,
    configuration: IndustryResearchConfig | None = None,
) -> IndustryResearchRequest:
    return IndustryResearchRequest(
        industry_id=industry_id,
        observation_date=observation_date,
        initiated_by="test_user",
        configuration=configuration,
    )


# ---------------------------------------------------------------------------
# 1. Agent construction
# ---------------------------------------------------------------------------


class TestAgentConstruction:
    def test_agent_construction(self) -> None:
        agent, _, _ = _build_agent()
        assert agent is not None
        assert isinstance(agent, IndustryResearchAgent)

    def test_agent_has_tools(self) -> None:
        agent, _, _ = _build_agent()
        assert hasattr(agent, "_tools")

    def test_agent_has_run_service(self) -> None:
        agent, svc, _ = _build_agent()
        assert agent._run_service is svc


# ---------------------------------------------------------------------------
# 2. Full happy-path execution
# ---------------------------------------------------------------------------


class TestHappyPathExecution:
    @pytest.mark.asyncio
    async def test_happy_path_completes(self) -> None:
        agent, svc, _ = _build_agent()

        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        result = await agent.execute(_make_request())

        assert result.status == "COMPLETED"
        assert result.steps_completed == 7
        assert result.industry_id == INDUSTRY_UUID
        assert result.industry_name == "Information Technology"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_happy_path_creates_run(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        await agent.execute(_make_request())

        svc.initiate_run.assert_called_once()
        call_args = svc.initiate_run.call_args[0][0]
        assert call_args.target_type == "industry"
        assert call_args.industry_id == INDUSTRY_UUID
        assert call_args.run_type == "industry_research"

    @pytest.mark.asyncio
    async def test_happy_path_creates_steps(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        await agent.execute(_make_request())

        svc.create_steps.assert_called_once()
        step_defs = svc.create_steps.call_args[0][1]
        assert len(step_defs) == 7

    @pytest.mark.asyncio
    async def test_happy_path_enqueues_and_starts(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        await agent.execute(_make_request())

        svc.enqueue_run.assert_called_once()
        svc.start_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_happy_path_completes_run(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        await agent.execute(_make_request())

        svc.complete_run.assert_called_once()
        svc.update_run_aggregates.assert_called_once()

    @pytest.mark.asyncio
    async def test_happy_path_no_findings_from_stubs(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        result = await agent.execute(_make_request())

        assert result.findings_count == 0
        assert result.evidence_count == 0


# ---------------------------------------------------------------------------
# 3. Step-level deterministic runner
# ---------------------------------------------------------------------------


class TestDeterministicStepRunner:
    @pytest.mark.asyncio
    async def test_deterministic_step_starts_and_completes(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("industry_validation", 1)

        result = await agent._run_step_deterministic(
            step,
            _async_return(_make_validate_output()),
        )

        svc.start_step.assert_called_once_with(step.id)
        svc.complete_step.assert_called_once_with(step.id)
        assert result.industry_id == INDUSTRY_UUID

    @pytest.mark.asyncio
    async def test_deterministic_step_fails_on_exception(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("industry_validation", 1)

        with pytest.raises(StepFailedError):
            await agent._run_step_deterministic(
                step,
                _async_raise(ValueError("test error")),
            )

        svc.start_step.assert_called_once()
        svc.fail_step.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Step-level LLM runner
# ---------------------------------------------------------------------------


class TestLLMStepRunner:
    @pytest.mark.asyncio
    async def test_llm_step_creates_execution(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        token_budget = TokenBudget()
        config = IndustryResearchConfig()

        await agent._run_step_llm(
            step,
            RUN_UUID,
            token_budget,
            config,
            lambda exec_id: _async_return_val([]),
        )

        svc.record_agent_execution.assert_called_once()
        call_data = svc.record_agent_execution.call_args[0][2]
        assert call_data.agent_name == INDUSTRY_AGENT_NAME

    @pytest.mark.asyncio
    async def test_llm_step_skipped_when_budget_exhausted(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        token_budget = TokenBudget(budget=100, input_tokens=100)

        with pytest.raises(TokenBudgetExhaustedError):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                token_budget,
                IndustryResearchConfig(),
                lambda exec_id: _async_return_val([]),
            )

        svc.skip_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_step_retries_on_provider_error(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        token_budget = TokenBudget()
        config = IndustryResearchConfig()

        call_count = 0

        async def _failing_then_success(exec_id: uuid.UUID) -> list[object]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError(provider="search", message="transient")
            return []

        await agent._run_step_llm(
            step,
            RUN_UUID,
            token_budget,
            config,
            _failing_then_success,
        )

        assert call_count == 2
        svc.fail_agent.assert_called_once()
        svc.retry_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_step_fails_after_max_retries(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        token_budget = TokenBudget()
        config = IndustryResearchConfig()

        async def _always_fails(exec_id: uuid.UUID) -> list[object]:
            raise ProviderError(provider="search", message="persistent failure")

        with pytest.raises(StepFailedError, match="persistent failure"):
            await agent._run_step_llm(
                step,
                RUN_UUID,
                token_budget,
                config,
                _always_fails,
            )

        assert svc.fail_agent.call_count == MAX_LLM_ATTEMPTS


# ---------------------------------------------------------------------------
# 5. Token budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_token_budget_defaults(self) -> None:
        config = IndustryResearchConfig()
        assert config.token_budget == INDUSTRY_AGENT_TOKEN_BUDGET
        assert config.token_warning_threshold == INDUSTRY_AGENT_TOKEN_WARNING

    def test_token_budget_tracking(self) -> None:
        tb = TokenBudget(budget=20_000, warning_threshold=16_000)
        assert tb.remaining == 20_000
        assert not tb.is_warning
        assert not tb.is_exhausted

        tb.record_usage(8_000, 8_000)
        assert tb.remaining == 4_000
        assert tb.is_warning

        tb.record_usage(2_000, 2_000)
        assert tb.remaining == 0
        assert tb.is_exhausted


# ---------------------------------------------------------------------------
# 6. Finding validation (step 6)
# ---------------------------------------------------------------------------


class TestFindingValidation:
    @pytest.mark.asyncio
    async def test_empty_findings_valid(self) -> None:
        agent, _, _ = _build_agent()
        result = await agent._step_finding_validation([])

        assert result.total_findings == 0
        assert result.valid_count == 0
        assert result.rejected_count == 0
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_finding_missing_category(self) -> None:
        agent, _, _ = _build_agent()

        class BadFinding:
            pass

        result = await agent._step_finding_validation([BadFinding()])

        assert result.rejected_count == 1
        assert result.issues[0].issue_type == "missing_category"

    @pytest.mark.asyncio
    async def test_finding_invalid_category(self) -> None:
        agent, _, _ = _build_agent()

        class BadCatFinding:
            category = "not_a_real_category"

        result = await agent._step_finding_validation([BadCatFinding()])

        assert result.rejected_count == 1
        assert result.issues[0].issue_type == "invalid_category"

    @pytest.mark.asyncio
    async def test_finding_valid_categories(self) -> None:
        agent, _, _ = _build_agent()

        class GoodFinding:
            def __init__(self, cat: str) -> None:
                self.category = cat

        findings = [GoodFinding(cat) for cat in ["market_size", "growth_drivers"]]
        result = await agent._step_finding_validation(findings)

        assert result.total_findings == 2
        assert result.valid_count == 2
        assert result.rejected_count == 0


# ---------------------------------------------------------------------------
# 7. Error handling — partial completion
# ---------------------------------------------------------------------------


class TestErrorHandlingPartial:
    @pytest.mark.asyncio
    async def test_step_failure_after_5_steps_yields_partial(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        async def _fail_validation(findings: list[object]) -> FindingValidationResult:
            raise ValueError("validation step forced failure")

        agent._step_finding_validation = _fail_validation  # type: ignore[assignment]

        result = await agent.execute(_make_request())

        assert result.status == "PARTIAL"
        assert result.steps_completed == 5
        svc.partial_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_failure_before_5_steps_yields_failed(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            side_effect=IndustryNotFoundError(str(INDUSTRY_UUID)),
        )

        result = await agent.execute(_make_request())

        assert result.status == "FAILED"
        assert result.steps_completed == 0
        svc.fail_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_exhaustion_yields_partial(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        async def _raise_token_exhausted(exec_id: uuid.UUID) -> list[uuid.UUID]:
            raise TokenBudgetExhaustedError(20_000, 20_000)

        agent._step_evidence_extraction_stub = _raise_token_exhausted  # type: ignore[assignment]

        result = await agent.execute(_make_request())

        assert result.status == "PARTIAL"
        svc.partial_run.assert_called_once()


# ---------------------------------------------------------------------------
# 8. Unexpected exception
# ---------------------------------------------------------------------------


class TestUnexpectedException:
    @pytest.mark.asyncio
    async def test_unexpected_error_yields_failed(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        async def _raise_unexpected(exec_id: uuid.UUID) -> list[uuid.UUID]:
            raise RuntimeError("something unexpected")

        agent._step_evidence_extraction_stub = _raise_unexpected  # type: ignore[assignment]

        result = await agent.execute(_make_request())

        assert result.status == "FAILED"
        assert "something unexpected" in (result.error or "")
        svc.fail_run.assert_called_once()


# ---------------------------------------------------------------------------
# 9. Industry validation step
# ---------------------------------------------------------------------------


class TestIndustryValidationStep:
    @pytest.mark.asyncio
    async def test_calls_validate_industry_tool(self) -> None:
        agent, _, _ = _build_agent()
        agent._tools.validate_industry = AsyncMock(
            return_value=_make_validate_output(),
        )

        request = _make_request()
        result = await agent._step_industry_validation(request)

        agent._tools.validate_industry.assert_called_once()
        assert result.industry_id == INDUSTRY_UUID
        assert result.name == "Information Technology"


# ---------------------------------------------------------------------------
# 10. Source discovery step
# ---------------------------------------------------------------------------


class TestSourceDiscoveryStep:
    @pytest.mark.asyncio
    async def test_calls_discover_industry_sources_tool(self) -> None:
        agent, _, _ = _build_agent()
        mock_output = AsyncMock()
        mock_output.candidates = [_make_source_candidate()]
        agent._tools.discover_industry_sources = AsyncMock(
            return_value=mock_output,
        )

        config = IndustryResearchConfig()
        result = await agent._step_source_discovery(
            INDUSTRY_UUID,
            "Information Technology",
            OBS_DATE,
            config,
        )

        agent._tools.discover_industry_sources.assert_called_once()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 11. Document retrieval step
# ---------------------------------------------------------------------------


class TestDocumentRetrievalStep:
    @pytest.mark.asyncio
    async def test_retrieves_documents_and_creates_records(self) -> None:
        agent, svc, _ = _build_agent()
        candidate = _make_source_candidate()
        doc_output = _make_doc_output()

        agent._tools.retrieve_industry_document = AsyncMock(
            return_value=doc_output,
        )
        agent._tools.create_research_document = AsyncMock(
            return_value=DOC_UUID,
        )

        config = IndustryResearchConfig()
        docs, doc_ids = await agent._step_document_retrieval(
            [candidate],
            config,
            run_id=RUN_UUID,
        )

        assert candidate.source_id in docs
        assert candidate.source_id in doc_ids
        svc.record_source_access.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_provider_error_during_retrieval(self) -> None:
        agent, svc, _ = _build_agent()
        candidate = _make_source_candidate()

        agent._tools.retrieve_industry_document = AsyncMock(
            side_effect=ProviderError(provider="search", message="timeout"),
        )

        config = IndustryResearchConfig()
        docs, doc_ids = await agent._step_document_retrieval(
            [candidate],
            config,
            run_id=RUN_UUID,
        )

        assert len(docs) == 0
        assert len(doc_ids) == 0

    @pytest.mark.asyncio
    async def test_empty_sources_returns_empty(self) -> None:
        agent, _, _ = _build_agent()
        config = IndustryResearchConfig()
        docs, doc_ids = await agent._step_document_retrieval(
            [],
            config,
            run_id=RUN_UUID,
        )
        assert docs == {}
        assert doc_ids == {}


# ---------------------------------------------------------------------------
# 12. LLM stub boundary verification
# ---------------------------------------------------------------------------


class TestLLMStubBoundaries:
    @pytest.mark.asyncio
    async def test_evidence_extraction_stub_returns_empty(self) -> None:
        agent, _, _ = _build_agent()
        result = await agent._step_evidence_extraction_stub(EXEC_UUID)
        assert result == []

    @pytest.mark.asyncio
    async def test_industry_analysis_stub_returns_empty(self) -> None:
        agent, _, _ = _build_agent()
        result = await agent._step_industry_analysis_stub(EXEC_UUID)
        assert result == []

    @pytest.mark.asyncio
    async def test_gap_contradiction_stub_returns_empty(self) -> None:
        agent, _, _ = _build_agent()
        result = await agent._step_gap_contradiction_stub(EXEC_UUID)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_fabricated_findings_in_full_run(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        result = await agent.execute(_make_request())

        assert result.findings_count == 0
        assert result.evidence_count == 0

    @pytest.mark.asyncio
    async def test_no_fabricated_token_usage(self) -> None:
        agent, svc, _ = _build_agent()
        agent._step_industry_validation = AsyncMock(
            return_value=_make_validate_output(),
        )
        agent._step_source_discovery = AsyncMock(return_value=[])
        agent._step_document_retrieval = AsyncMock(return_value=({}, {}))

        result = await agent.execute(_make_request())

        assert result.token_budget.input_tokens == 0
        assert result.token_budget.output_tokens == 0
        assert result.token_budget.total_tokens == 0


# ---------------------------------------------------------------------------
# 13. IndustryResearchResult contract
# ---------------------------------------------------------------------------


class TestResultContract:
    def test_result_has_required_fields(self) -> None:
        result = IndustryResearchResult(
            run_id=RUN_UUID,
            status="COMPLETED",
            industry_id=INDUSTRY_UUID,
            industry_name="IT",
            token_budget=TokenBudget(),
        )
        assert result.run_id == RUN_UUID
        assert result.status == "COMPLETED"
        assert result.industry_id == INDUSTRY_UUID
        assert result.steps_total == 7

    def test_result_is_frozen(self) -> None:
        result = IndustryResearchResult(
            run_id=RUN_UUID,
            status="COMPLETED",
            industry_id=INDUSTRY_UUID,
            industry_name="IT",
            token_budget=TokenBudget(),
        )
        with pytest.raises(ValidationError):
            result.status = "FAILED"  # type: ignore[misc]

    def test_result_defaults(self) -> None:
        result = IndustryResearchResult(
            run_id=RUN_UUID,
            status="COMPLETED",
            industry_id=INDUSTRY_UUID,
            industry_name="IT",
            token_budget=TokenBudget(),
        )
        assert result.findings_count == 0
        assert result.evidence_count == 0
        assert result.steps_completed == 0
        assert result.validation_result is None
        assert result.error is None


# ---------------------------------------------------------------------------
# 14. Step map from INDUSTRY_RESEARCH_STEPS
# ---------------------------------------------------------------------------


class TestStepDefinitions:
    def test_seven_steps_defined(self) -> None:
        assert len(INDUSTRY_RESEARCH_STEPS) == 7

    def test_step_names(self) -> None:
        names = [s.step_name for s in INDUSTRY_RESEARCH_STEPS]
        assert names == [
            "industry_validation",
            "industry_source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "industry_analysis",
            "finding_validation",
            "gap_contradiction_analysis",
        ]

    def test_step_orders(self) -> None:
        orders = [s.step_order for s in INDUSTRY_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_llm_steps_flagged(self) -> None:
        llm_steps = [s.step_name for s in INDUSTRY_RESEARCH_STEPS if s.uses_llm]
        assert llm_steps == [
            "evidence_extraction",
            "industry_analysis",
            "gap_contradiction_analysis",
        ]


# ---------------------------------------------------------------------------
# 15. Configuration defaults
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_default_config(self) -> None:
        config = IndustryResearchConfig()
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == MAX_LLM_ATTEMPTS
        assert config.source_limit == 30

    def test_request_requires_industry_id(self) -> None:
        request = _make_request()
        assert request.industry_id == INDUSTRY_UUID
        assert request.observation_date == OBS_DATE


# ---------------------------------------------------------------------------
# 16. Agent attribution
# ---------------------------------------------------------------------------


class TestAgentAttribution:
    def test_agent_name_constant(self) -> None:
        assert INDUSTRY_AGENT_NAME == "industry_research_agent"

    @pytest.mark.asyncio
    async def test_agent_execution_uses_correct_name(self) -> None:
        agent, svc, _ = _build_agent()
        step = _make_step("evidence_extraction", 4)
        token_budget = TokenBudget()
        config = IndustryResearchConfig()

        await agent._run_step_llm(
            step,
            RUN_UUID,
            token_budget,
            config,
            lambda exec_id: _async_return_val([]),
        )

        call_data = svc.record_agent_execution.call_args[0][2]
        assert call_data.agent_name == INDUSTRY_AGENT_NAME


# ---------------------------------------------------------------------------
# 17. Tool registry verification
# ---------------------------------------------------------------------------

CANONICAL_AGENT_TOOLS = frozenset(
    {
        "validate_industry",
        "discover_industry_sources",
        "retrieve_industry_document",
        "get_industry_profile",
        "search_industry_news",
        "retrieve_document",
        "persist_evidence",
        "persist_findings",
    }
)


class TestToolRegistry:
    def test_exactly_8_agent_facing_tools(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        public_methods = {name for name in dir(tools) if not name.startswith("_") and callable(getattr(tools, name))}
        internal_helpers = {"create_research_document"}
        agent_facing = public_methods - internal_helpers
        assert agent_facing == CANONICAL_AGENT_TOOLS
        assert len(agent_facing) == 8

    def test_retrieve_document_present(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        assert hasattr(tools, "retrieve_document")
        assert callable(tools.retrieve_document)

    def test_create_research_document_is_internal(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        assert hasattr(tools, "create_research_document")
        assert "create_research_document" not in CANONICAL_AGENT_TOOLS

    def test_no_company_only_tools_exposed(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        company_only_tools = {
            "get_company_profile",
            "get_financial_data",
            "search_filings",
            "get_transcript",
        }
        public_methods = {name for name in dir(tools) if not name.startswith("_") and callable(getattr(tools, name))}
        assert company_only_tools.isdisjoint(public_methods)

    def test_unknown_tools_not_present(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        public_methods = {name for name in dir(tools) if not name.startswith("_") and callable(getattr(tools, name))}
        internal_helpers = {"create_research_document"}
        agent_facing = public_methods - internal_helpers
        unexpected = agent_facing - CANONICAL_AGENT_TOOLS
        assert unexpected == set(), f"Unexpected tools: {unexpected}"


# ---------------------------------------------------------------------------
# 18. Temporal semantics
# ---------------------------------------------------------------------------


class TestTemporalSemantics:
    def test_source_candidate_stores_publication_date_not_relabeled(self) -> None:
        candidate = _make_source_candidate()
        assert hasattr(candidate, "publication_date")
        assert candidate.publication_date == date(2025, 5, 30)

    def test_source_candidate_publication_date_can_be_none(self) -> None:
        candidate = SourceCandidate(
            source_id="search-result-1",
            source_type=DocumentType.RESEARCH_REPORT,
            provider="search",
            title="Industry Report",
            publication_date=None,
            source_tier=SourceTier.TIER_2,
            url="https://example.com/report",
        )
        assert candidate.publication_date is None

    @pytest.mark.asyncio
    async def test_news_filtering_uses_observation_date(self) -> None:
        tools = IndustryResearchTools(
            session=AsyncMock(),
            run_service=AsyncMock(),
            search=AsyncMock(),
            news=AsyncMock(),
        )
        future_article = AsyncMock()
        future_article.published_at = datetime(2025, 7, 1, tzinfo=UTC)
        future_article.url = "https://example.com/future"
        future_article.title = "Future Article"
        future_article.source = "news"
        future_article.summary = "Summary"

        past_article = AsyncMock()
        past_article.published_at = datetime(2025, 6, 1, tzinfo=UTC)
        past_article.url = "https://example.com/past"
        past_article.title = "Past Article"
        past_article.source = "news"
        past_article.summary = "Summary"

        tools._news.search_news = AsyncMock(
            return_value=[future_article, past_article],
        )

        result = await tools.search_industry_news(
            SearchIndustryNewsInput(
                industry_name="IT",
                observation_date=OBS_DATE,
                limit=10,
            ),
        )
        assert len(result.articles) == 1
        assert result.articles[0].title == "Past Article"

    def test_news_article_result_preserves_published_at(self) -> None:
        article = NewsArticleResult(
            title="Test",
            url="https://example.com",
            source="test",
            published_at=datetime(2025, 6, 1, tzinfo=UTC),
            summary="test",
        )
        assert article.published_at == datetime(2025, 6, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _async_return(val: Any) -> Any:
    return val


async def _async_return_val(val: Any) -> Any:
    return val


async def _async_raise(exc: Exception) -> None:
    raise exc
