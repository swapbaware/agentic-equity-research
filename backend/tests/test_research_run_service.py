"""Tier 4: Service layer tests for ResearchRunService.

Tests lifecycle management, state machine enforcement, temporal validation,
finding immutability, concurrent run prevention, retry semantics, and
thesis versioning support.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import NotFoundError, ValidationError
from app.models.enums import (
    AgentExecutionStatus,
    FindingType,
    ResearchRunStatus,
    StepStatus,
)
from app.models.research import (
    AgentExecution,
    ResearchFinding,
    ResearchRun,
    ResearchRunStep,
)
from app.schemas.research_run import (
    AgentExecutionCreate,
    ResearchArtifactCreate,
    ResearchFindingCreate,
    ResearchRunCreate,
    ResearchRunStepCreate,
    TokenUsage,
)
from app.services.research_run import MAX_AGENT_RETRIES, ResearchRunService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    *,
    status: str = ResearchRunStatus.CREATED,
    company_id: uuid.UUID | None = None,
    observation_date: date | None = None,
    parent_run_id: uuid.UUID | None = None,
) -> ResearchRun:
    run = ResearchRun(
        id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        initiated_by="test_user",
        status=status,
        run_type="FULL",
        trigger_type="USER_INITIATED",
        observation_date=observation_date,
        parent_run_id=parent_run_id,
    )
    run.started_at = datetime.now(UTC)
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


def _make_step(
    *,
    run_id: uuid.UUID | None = None,
    status: str = StepStatus.PENDING,
) -> ResearchRunStep:
    step = ResearchRunStep(
        id=uuid.uuid4(),
        research_run_id=run_id or uuid.uuid4(),
        step_name="financial_analysis",
        step_order=1,
        step_type="AGENT",
        status=status,
    )
    step.created_at = datetime.now(UTC)
    step.updated_at = datetime.now(UTC)
    return step


def _make_execution(
    *,
    run_id: uuid.UUID | None = None,
    status: str = AgentExecutionStatus.RUNNING,
    attempt_number: int = 1,
) -> AgentExecution:
    execution = AgentExecution(
        id=uuid.uuid4(),
        research_run_id=run_id or uuid.uuid4(),
        agent_name="financial_analysis_agent",
        attempt_number=attempt_number,
        status=status,
        model_provider="anthropic",
        model_name="claude-sonnet-5",
    )
    execution.started_at = datetime.now(UTC)
    execution.created_at = datetime.now(UTC)
    execution.input_tokens = 0
    execution.output_tokens = 0
    execution.cost_usd = Decimal("0")
    execution.findings_produced = 0
    return execution


def _simulate_create_batch(findings: list[ResearchFinding]) -> list[ResearchFinding]:
    for f in findings:
        if f.created_at is None:
            f.created_at = datetime.now(UTC)
    return findings


def _make_service() -> tuple[ResearchRunService, MagicMock]:
    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    service = ResearchRunService(mock_session)
    return service, mock_session


# ---------------------------------------------------------------------------
# Run lifecycle (AC-1, AC-3, AC-13)
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_initiate_run(self) -> None:
        service, session = _make_service()
        data = ResearchRunCreate(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            observation_date=date(2026, 9, 30),
        )

        with (
            patch.object(service._runs, "get_active_run", new_callable=AsyncMock, return_value=None),
            patch.object(service._runs, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda run: run
            result = await service.initiate_run(data)

        assert result.status == ResearchRunStatus.CREATED
        assert result.run_type == "FULL"
        assert result.trigger_type == "USER_INITIATED"
        assert result.observation_date == date(2026, 9, 30)

    @pytest.mark.asyncio
    async def test_initiate_run_blocked_by_concurrent(self) -> None:
        service, _ = _make_service()
        existing = _make_run(status=ResearchRunStatus.RUNNING)
        data = ResearchRunCreate(
            company_id=existing.company_id,
            initiated_by="test_user",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )

        with (
            patch.object(service._runs, "get_active_run", new_callable=AsyncMock, return_value=existing),
            pytest.raises(ValidationError, match="already active"),
        ):
            await service.initiate_run(data)

    @pytest.mark.asyncio
    async def test_full_lifecycle_created_to_completed(self) -> None:
        service, session = _make_service()
        run = _make_run(status=ResearchRunStatus.CREATED)

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            mock_update.return_value = run
            await service.enqueue_run(run.id)

        run.status = ResearchRunStatus.QUEUED
        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            started_run = _make_run(status=ResearchRunStatus.RUNNING)
            mock_update.return_value = started_run
            result = await service.start_run(run.id)
            mock_update.assert_called_once()

        run.status = ResearchRunStatus.RUNNING
        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            completed_run = _make_run(status=ResearchRunStatus.COMPLETED)
            completed_run.completed_at = datetime.now(UTC)
            mock_update.return_value = completed_run
            result = await service.complete_run(run.id, quality_gates={"gate_1": True})
            mock_update.assert_called_once()

        assert result.status == ResearchRunStatus.COMPLETED
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_running_to_partial(self) -> None:
        service, session = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        partial = _make_run(status=ResearchRunStatus.PARTIAL)
        partial.completed_at = datetime.now(UTC)
        partial.error_summary = "Quality gates failed after 2 iterations"

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock, return_value=partial) as mock_update,
        ):
            result = await service.partial_run(
                run.id,
                error_summary="Quality gates failed after 2 iterations",
                quality_gates={"citation_completeness": False},
            )
            mock_update.assert_called_once()

        assert result.status == ResearchRunStatus.PARTIAL
        assert result.error_summary == "Quality gates failed after 2 iterations"

    @pytest.mark.asyncio
    async def test_running_to_failed(self) -> None:
        service, session = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        failed = _make_run(status=ResearchRunStatus.FAILED)
        failed.completed_at = datetime.now(UTC)
        failed.error_summary = "Database connection failed"

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock, return_value=failed) as mock_update,
        ):
            result = await service.fail_run(run.id, "Database connection failed")
            mock_update.assert_called_once()

        assert result.status == ResearchRunStatus.FAILED
        assert result.error_summary == "Database connection failed"

    @pytest.mark.asyncio
    async def test_running_to_cancelled(self) -> None:
        service, session = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        cancelled = _make_run(status=ResearchRunStatus.CANCELLED)
        cancelled.completed_at = datetime.now(UTC)

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock, return_value=cancelled) as mock_update,
        ):
            result = await service.cancel_run(run.id)
            mock_update.assert_called_once()

        assert result.status == ResearchRunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.CREATED)

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._runs, "update_status", new_callable=AsyncMock),
            pytest.raises(ValidationError, match="Invalid run transition"),
        ):
            await service.complete_run(run.id)


# ---------------------------------------------------------------------------
# Resume with parent_run_id (AC-6)
# ---------------------------------------------------------------------------


class TestResume:
    @pytest.mark.asyncio
    async def test_resume_with_parent_run_id(self) -> None:
        service, _ = _make_service()
        parent = _make_run(status=ResearchRunStatus.PARTIAL)

        data = ResearchRunCreate(
            company_id=parent.company_id,
            initiated_by="test_user",
            run_type="INCREMENTAL",
            trigger_type="RERUN",
            parent_run_id=parent.id,
        )

        with (
            patch.object(service._runs, "get_active_run", new_callable=AsyncMock, return_value=None),
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=parent),
            patch.object(service._runs, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda run: run
            result = await service.initiate_run(data)

        assert result.parent_run_id == parent.id
        assert result.run_type == "INCREMENTAL"
        assert result.trigger_type == "RERUN"

    @pytest.mark.asyncio
    async def test_resume_parent_must_be_terminal(self) -> None:
        service, _ = _make_service()
        parent = _make_run(status=ResearchRunStatus.RUNNING)

        data = ResearchRunCreate(
            company_id=parent.company_id,
            initiated_by="test_user",
            run_type="INCREMENTAL",
            trigger_type="RERUN",
            parent_run_id=parent.id,
        )

        with (
            patch.object(service._runs, "get_active_run", new_callable=AsyncMock, return_value=None),
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=parent),
            pytest.raises(ValidationError, match="terminal state"),
        ):
            await service.initiate_run(data)

    @pytest.mark.asyncio
    async def test_resume_parent_not_found(self) -> None:
        service, _ = _make_service()

        data = ResearchRunCreate(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            run_type="INCREMENTAL",
            trigger_type="RERUN",
            parent_run_id=uuid.uuid4(),
        )

        with (
            patch.object(service._runs, "get_active_run", new_callable=AsyncMock, return_value=None),
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Parent run not found"),
        ):
            await service.initiate_run(data)


# ---------------------------------------------------------------------------
# Agent execution (AC-4, AC-5, AC-21, AC-22)
# ---------------------------------------------------------------------------


class TestAgentExecution:
    @pytest.mark.asyncio
    async def test_record_execution(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        data = AgentExecutionCreate(
            agent_name="financial_analysis_agent",
            attempt_number=1,
            model_provider="anthropic",
            model_name="claude-sonnet-5",
            prompt_version="v1.0.0",
            tool_versions={"ratio_calc": "1.0.0"},
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._executions, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda e: e
            result = await service.record_agent_execution(run.id, None, data)

        assert result.agent_name == "financial_analysis_agent"
        assert result.status == AgentExecutionStatus.RUNNING
        assert result.model_provider == "anthropic"
        assert result.model_name == "claude-sonnet-5"
        assert result.prompt_version == "v1.0.0"

    @pytest.mark.asyncio
    async def test_complete_execution(self) -> None:
        service, _ = _make_service()
        execution = _make_execution(status=AgentExecutionStatus.RUNNING)

        with patch.object(service._executions, "get_by_id", new_callable=AsyncMock, return_value=execution):
            result = await service.complete_agent(
                execution.id,
                token_usage=TokenUsage(input_tokens=15000, output_tokens=4000),
                cost_usd=Decimal("0.023400"),
                findings_count=8,
                duration_ms=12340,
            )

        assert result.status == AgentExecutionStatus.COMPLETED
        assert result.input_tokens == 15000
        assert result.output_tokens == 4000
        assert result.cost_usd == Decimal("0.023400")
        assert result.findings_produced == 8
        assert result.duration_ms == 12340
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_execution(self) -> None:
        service, _ = _make_service()
        execution = _make_execution(status=AgentExecutionStatus.RUNNING)

        with patch.object(service._executions, "get_by_id", new_callable=AsyncMock, return_value=execution):
            result = await service.fail_agent(
                execution.id,
                error_message="Provider rate limit exceeded",
                error_type="RATE_LIMIT",
            )

        assert result.status == AgentExecutionStatus.FAILED
        assert result.error_message == "Provider rate limit exceeded"
        assert result.error_type == "RATE_LIMIT"

    @pytest.mark.asyncio
    async def test_timeout_execution(self) -> None:
        service, _ = _make_service()
        execution = _make_execution(status=AgentExecutionStatus.RUNNING)

        with patch.object(service._executions, "get_by_id", new_callable=AsyncMock, return_value=execution):
            result = await service.fail_agent(
                execution.id,
                error_message="Agent exceeded 180s timeout",
                error_type="TIMEOUT",
                status=AgentExecutionStatus.TIMEOUT,
            )

        assert result.status == AgentExecutionStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_truncated_execution(self) -> None:
        service, _ = _make_service()
        execution = _make_execution(status=AgentExecutionStatus.RUNNING)

        with patch.object(service._executions, "get_by_id", new_callable=AsyncMock, return_value=execution):
            result = await service.fail_agent(
                execution.id,
                error_message="Token budget exhausted",
                error_type="TOKEN_BUDGET",
                status=AgentExecutionStatus.TRUNCATED,
                token_usage=TokenUsage(input_tokens=50000, output_tokens=25000),
                cost_usd=Decimal("0.150000"),
            )

        assert result.status == AgentExecutionStatus.TRUNCATED
        assert result.input_tokens == 50000

    @pytest.mark.asyncio
    async def test_max_retry_limit_enforced(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        data = AgentExecutionCreate(
            agent_name="test_agent",
            attempt_number=MAX_AGENT_RETRIES + 1,
            model_provider="anthropic",
            model_name="claude-sonnet-5",
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            pytest.raises(ValidationError, match="exceeds max retries"),
        ):
            await service.record_agent_execution(run.id, None, data)

    @pytest.mark.asyncio
    async def test_retry_preserves_history(self) -> None:
        """AC-5: Verify retry creates new record with incremented attempt_number."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)

        created_executions: list[AgentExecution] = []

        async def capture_create(e: AgentExecution) -> AgentExecution:
            created_executions.append(e)
            return e

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._executions, "create", new_callable=AsyncMock, side_effect=capture_create),
        ):
            for attempt in range(1, 4):
                data = AgentExecutionCreate(
                    agent_name="test_agent",
                    attempt_number=attempt,
                    model_provider="anthropic",
                    model_name="claude-sonnet-5",
                )
                await service.record_agent_execution(run.id, None, data)

        assert len(created_executions) == 3
        assert [e.attempt_number for e in created_executions] == [1, 2, 3]
        for e in created_executions:
            assert e.agent_name == "test_agent"


# ---------------------------------------------------------------------------
# Findings (AC-8, AC-9, AC-10, AC-11, AC-12)
# ---------------------------------------------------------------------------


class TestFindings:
    @pytest.mark.asyncio
    async def test_record_finding_with_temporal_fields(self) -> None:
        service, _ = _make_service()
        run = _make_run(
            status=ResearchRunStatus.RUNNING,
            observation_date=date(2026, 9, 30),
        )
        finding_data = ResearchFindingCreate(
            agent_name="financial_analysis_agent",
            finding_type=FindingType.FACT,
            category="revenue",
            content="Revenue was INR 1000 Cr",
            confidence="HIGH",
            observation_date=date(2026, 9, 30),
            source_publication_date=date(2026, 9, 15),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = _simulate_create_batch
            results = await service.record_findings(run.id, None, [finding_data])

        assert len(results) == 1
        assert results[0].observation_date == date(2026, 9, 30)
        assert results[0].source_publication_date == date(2026, 9, 15)

    @pytest.mark.asyncio
    async def test_finding_observation_date_after_run_raises(self) -> None:
        """AC-11: Temporal validation — finding cannot observe the future."""
        service, _ = _make_service()
        run = _make_run(
            status=ResearchRunStatus.RUNNING,
            observation_date=date(2026, 9, 30),
        )
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            observation_date=date(2026, 10, 15),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            pytest.raises(ValidationError, match="cannot be after run observation_date"),
        ):
            await service.record_findings(run.id, None, [finding_data])

    @pytest.mark.asyncio
    async def test_source_publication_after_observation_raises(self) -> None:
        """AC-11: source_publication_date must be <= observation_date."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            observation_date=date(2026, 6, 30),
            source_publication_date=date(2026, 7, 15),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            pytest.raises(ValidationError, match="source_publication_date cannot be after"),
        ):
            await service.record_findings(run.id, None, [finding_data])

    @pytest.mark.asyncio
    async def test_supersession_chain(self) -> None:
        """AC-9: Finding supersession via supersedes_finding_id."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        old_finding_id = uuid.uuid4()

        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="revenue",
            content="Updated revenue figure",
            confidence="HIGH",
            supersedes_finding_id=old_finding_id,
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = _simulate_create_batch
            results = await service.record_findings(run.id, None, [finding_data])

        assert results[0].supersedes_finding_id == old_finding_id

    @pytest.mark.asyncio
    async def test_publication_date_before_created_at_accepted(self) -> None:
        """§12.2.2: source_publication_date before created_at is valid."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            source_publication_date=date(2026, 9, 1),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = _simulate_create_batch
            results = await service.record_findings(run.id, None, [finding_data])

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_publication_date_equal_to_created_at_accepted(self) -> None:
        """§12.2.2: source_publication_date equal to created_at date is valid."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        today = date.today()
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            source_publication_date=today,
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = _simulate_create_batch
            results = await service.record_findings(run.id, None, [finding_data])

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_publication_date_after_created_at_rejected(self) -> None:
        """§12.2.2: source_publication_date after created_at must raise."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        future_date = date(2099, 12, 31)
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            source_publication_date=future_date,
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
            pytest.raises(ValidationError, match="source_publication_date cannot be after finding created_at"),
        ):
            mock_batch.side_effect = _simulate_create_batch
            await service.record_findings(run.id, None, [finding_data])

    @pytest.mark.asyncio
    async def test_observation_date_validation_still_works_with_new_rule(self) -> None:
        """Existing observation_date rules still apply alongside §12.2.2."""
        service, _ = _make_service()
        run = _make_run(
            status=ResearchRunStatus.RUNNING,
            observation_date=date(2026, 9, 30),
        )
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            observation_date=date(2026, 10, 15),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            pytest.raises(ValidationError, match="cannot be after run observation_date"),
        ):
            await service.record_findings(run.id, None, [finding_data])

    @pytest.mark.asyncio
    async def test_invalid_finding_not_persisted_after_post_insert_check(self) -> None:
        """Invalid findings raise before transaction commits."""
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        future_date = date(2099, 12, 31)
        finding_data = ResearchFindingCreate(
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="test",
            confidence="HIGH",
            source_publication_date=future_date,
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
            pytest.raises(ValidationError),
        ):
            mock_batch.side_effect = _simulate_create_batch
            await service.record_findings(run.id, None, [finding_data])


# ---------------------------------------------------------------------------
# Artifacts (AC-23)
# ---------------------------------------------------------------------------


class TestArtifacts:
    @pytest.mark.asyncio
    async def test_record_artifact(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        data = ResearchArtifactCreate(
            artifact_type="REPORT",
            title="Financial Analysis Report",
            content_type="text/markdown",
            content_hash="abcdef1234567890" * 4,
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._artifacts, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda a: a
            result = await service.record_artifact(run.id, None, data)

        assert result.artifact_type == "REPORT"
        assert result.title == "Financial Analysis Report"


# ---------------------------------------------------------------------------
# Run aggregates (AC-22)
# ---------------------------------------------------------------------------


class TestAggregates:
    @pytest.mark.asyncio
    async def test_update_run_aggregates(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)

        exec1 = _make_execution()
        exec1.input_tokens = 15000
        exec1.output_tokens = 4000
        exec1.cost_usd = Decimal("0.023400")

        exec2 = _make_execution()
        exec2.input_tokens = 20000
        exec2.output_tokens = 5000
        exec2.cost_usd = Decimal("0.031200")

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._executions, "get_by_run", new_callable=AsyncMock, return_value=[exec1, exec2]),
            patch.object(service._runs, "update_aggregates", new_callable=AsyncMock) as mock_update,
        ):
            mock_update.return_value = run
            await service.update_run_aggregates(run.id)

        mock_update.assert_called_once_with(
            run.id,
            total_input_tokens=35000,
            total_output_tokens=9000,
            total_cost_usd=Decimal("0.054600"),
        )


# ---------------------------------------------------------------------------
# Step management
# ---------------------------------------------------------------------------


class TestStepManagement:
    @pytest.mark.asyncio
    async def test_create_steps(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        step_defs = [
            ResearchRunStepCreate(step_name="financial_analysis", step_order=1, step_type="AGENT"),
            ResearchRunStepCreate(step_name="moat_assessment", step_order=2, step_type="AGENT"),
        ]

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._steps, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = lambda steps: steps
            results = await service.create_steps(run.id, step_defs)

        assert len(results) == 2
        assert results[0].step_name == "financial_analysis"
        assert results[0].status == StepStatus.PENDING

    @pytest.mark.asyncio
    async def test_step_lifecycle(self) -> None:
        service, session = _make_service()
        step = _make_step(status=StepStatus.PENDING)

        with (
            patch.object(service._steps, "get_by_id", new_callable=AsyncMock, return_value=step),
            patch.object(service._steps, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            mock_update.return_value = step
            await service.start_step(step.id)

        step.status = StepStatus.RUNNING
        completed_step = _make_step(status=StepStatus.COMPLETED)
        with (
            patch.object(service._steps, "get_by_id", new_callable=AsyncMock, return_value=step),
            patch.object(
                service._steps, "update_status",
                new_callable=AsyncMock, return_value=completed_step,
            ) as mock_complete,
        ):
            result = await service.complete_step(step.id, output_state_hash="abc123")
            mock_complete.assert_called_once()

        assert result.output_state_hash == "abc123"

    @pytest.mark.asyncio
    async def test_step_retry(self) -> None:
        service, _ = _make_service()
        step = _make_step(status=StepStatus.FAILED)

        with (
            patch.object(service._steps, "get_by_id", new_callable=AsyncMock, return_value=step),
            patch.object(service._steps, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            mock_update.return_value = step
            await service.retry_step(step.id)

    @pytest.mark.asyncio
    async def test_skip_step(self) -> None:
        service, _ = _make_service()
        step = _make_step(status=StepStatus.PENDING)

        with (
            patch.object(service._steps, "get_by_id", new_callable=AsyncMock, return_value=step),
            patch.object(service._steps, "update_status", new_callable=AsyncMock) as mock_update,
        ):
            mock_update.return_value = step
            await service.skip_step(step.id)

    @pytest.mark.asyncio
    async def test_invalid_step_transition_raises(self) -> None:
        service, _ = _make_service()
        step = _make_step(status=StepStatus.COMPLETED)

        with (
            patch.object(service._steps, "get_by_id", new_callable=AsyncMock, return_value=step),
            pytest.raises(ValidationError, match="Invalid step transition"),
        ):
            await service.start_step(step.id)


# ---------------------------------------------------------------------------
# Not found errors
# ---------------------------------------------------------------------------


class TestNotFound:
    @pytest.mark.asyncio
    async def test_get_run_not_found(self) -> None:
        service, _ = _make_service()
        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Research run not found"),
        ):
            await service.get_run(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_complete_agent_not_found(self) -> None:
        service, _ = _make_service()
        with (
            patch.object(service._executions, "get_by_id", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Agent execution not found"),
        ):
            await service.complete_agent(
                uuid.uuid4(),
                token_usage=TokenUsage(input_tokens=0, output_tokens=0),
                cost_usd=Decimal("0"),
                findings_count=0,
            )


# ---------------------------------------------------------------------------
# Service/repository boundary (Issue #1 audit fix)
# ---------------------------------------------------------------------------


class TestServiceUsesRepository:
    """Verify that lifecycle methods delegate to repository.update_status()."""

    @pytest.mark.asyncio
    async def test_start_run_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.QUEUED)
        result_run = _make_run(status=ResearchRunStatus.RUNNING)

        with (
            patch.object(
                service._runs, "get_by_id",
                new_callable=AsyncMock, return_value=run,
            ),
            patch.object(
                service._runs, "update_status",
                new_callable=AsyncMock, return_value=result_run,
            ) as mock_update,
        ):
            await service.start_run(run.id)
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args
            assert call_kwargs[0][1] == ResearchRunStatus.RUNNING
            assert "started_at" in call_kwargs[1]

    @pytest.mark.asyncio
    async def test_complete_run_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        result_run = _make_run(status=ResearchRunStatus.COMPLETED)

        with (
            patch.object(
                service._runs, "get_by_id",
                new_callable=AsyncMock, return_value=run,
            ),
            patch.object(
                service._runs, "update_status",
                new_callable=AsyncMock, return_value=result_run,
            ) as mock_update,
        ):
            await service.complete_run(run.id, quality_gates={"g1": True})
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args
            assert call_kwargs[0][1] == ResearchRunStatus.COMPLETED
            assert call_kwargs[1]["quality_gate_results"] == {"g1": True}
            assert "completed_at" in call_kwargs[1]

    @pytest.mark.asyncio
    async def test_fail_run_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        result_run = _make_run(status=ResearchRunStatus.FAILED)

        with (
            patch.object(
                service._runs, "get_by_id",
                new_callable=AsyncMock, return_value=run,
            ),
            patch.object(
                service._runs, "update_status",
                new_callable=AsyncMock, return_value=result_run,
            ) as mock_update,
        ):
            await service.fail_run(run.id, "error")
            mock_update.assert_called_once()
            assert mock_update.call_args[1]["error_summary"] == "error"

    @pytest.mark.asyncio
    async def test_partial_run_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        result_run = _make_run(status=ResearchRunStatus.PARTIAL)

        with (
            patch.object(
                service._runs, "get_by_id",
                new_callable=AsyncMock, return_value=run,
            ),
            patch.object(
                service._runs, "update_status",
                new_callable=AsyncMock, return_value=result_run,
            ) as mock_update,
        ):
            await service.partial_run(run.id, "partial error")
            mock_update.assert_called_once()
            assert mock_update.call_args[1]["error_summary"] == "partial error"

    @pytest.mark.asyncio
    async def test_cancel_run_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        run = _make_run(status=ResearchRunStatus.RUNNING)
        result_run = _make_run(status=ResearchRunStatus.CANCELLED)

        with (
            patch.object(
                service._runs, "get_by_id",
                new_callable=AsyncMock, return_value=run,
            ),
            patch.object(
                service._runs, "update_status",
                new_callable=AsyncMock, return_value=result_run,
            ) as mock_update,
        ):
            await service.cancel_run(run.id)
            mock_update.assert_called_once()
            assert mock_update.call_args[0][1] == ResearchRunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_complete_step_delegates_to_repo(self) -> None:
        service, _ = _make_service()
        step = _make_step(status=StepStatus.RUNNING)
        result_step = _make_step(status=StepStatus.COMPLETED)

        with (
            patch.object(
                service._steps, "get_by_id",
                new_callable=AsyncMock, return_value=step,
            ),
            patch.object(
                service._steps, "update_status",
                new_callable=AsyncMock, return_value=result_step,
            ) as mock_update,
        ):
            await service.complete_step(step.id)
            mock_update.assert_called_once()
            assert mock_update.call_args[0][1] == StepStatus.COMPLETED
