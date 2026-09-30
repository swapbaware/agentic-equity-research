"""Research Run domain service — lifecycle management, state machine enforcement, temporal validation."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, ValidationError
from app.models.enums import (
    AgentExecutionStatus,
    ResearchRunStatus,
    StepStatus,
)
from app.models.research import (
    AgentExecution,
    ResearchArtifact,
    ResearchFinding,
    ResearchRun,
    ResearchRunSource,
    ResearchRunStep,
)
from app.models.state_machines import (
    TERMINAL_RUN_STATUSES,
    validate_execution_transition,
    validate_run_transition,
    validate_step_transition,
)
from app.repositories.research_run import (
    AgentExecutionRepository,
    ResearchArtifactRepository,
    ResearchFindingRepository,
    ResearchRunRepository,
    ResearchRunSourceRepository,
    ResearchRunStepRepository,
)
from app.schemas.research_run import (
    AgentExecutionCreate,
    ResearchArtifactCreate,
    ResearchFindingCreate,
    ResearchRunCreate,
    ResearchRunStepCreate,
    RunProgress,
    TokenUsage,
)

MAX_AGENT_RETRIES = 3


class ResearchRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = ResearchRunRepository(session)
        self._steps = ResearchRunStepRepository(session)
        self._executions = AgentExecutionRepository(session)
        self._findings = ResearchFindingRepository(session)
        self._artifacts = ResearchArtifactRepository(session)
        self._sources = ResearchRunSourceRepository(session)

    # -- Run lifecycle (AC-1, AC-3, AC-6, AC-13) -----------------------------

    async def initiate_run(self, data: ResearchRunCreate) -> ResearchRun:
        active = await self._runs.get_active_run(data.company_id)
        if active is not None:
            raise ValidationError(
                message="A research run is already active for this company",
                details={
                    "company_id": str(data.company_id),
                    "active_run_id": str(active.id),
                    "active_status": active.status,
                },
            )

        if data.parent_run_id is not None:
            parent = await self._runs.get_by_id(data.parent_run_id)
            if parent is None:
                raise NotFoundError(
                    message="Parent run not found",
                    details={"parent_run_id": str(data.parent_run_id)},
                )
            if parent.status not in TERMINAL_RUN_STATUSES:
                raise ValidationError(
                    message="Parent run must be in a terminal state",
                    details={
                        "parent_run_id": str(data.parent_run_id),
                        "parent_status": parent.status,
                    },
                )

        run = ResearchRun(
            company_id=data.company_id,
            initiated_by=data.initiated_by,
            run_type=data.run_type,
            trigger_type=data.trigger_type,
            parent_run_id=data.parent_run_id,
            observation_date=data.observation_date,
            configuration=data.configuration,
            status=ResearchRunStatus.CREATED,
        )
        return await self._runs.create(run)

    async def enqueue_run(self, run_id: uuid.UUID) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.QUEUED)
        result = await self._runs.update_status(run_id, ResearchRunStatus.QUEUED)
        assert result is not None
        return result

    async def start_run(self, run_id: uuid.UUID) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.RUNNING)
        result = await self._runs.update_status(
            run_id, ResearchRunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        assert result is not None
        return result

    async def complete_run(
        self,
        run_id: uuid.UUID,
        quality_gates: dict[str, object] | None = None,
    ) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.COMPLETED)
        result = await self._runs.update_status(
            run_id, ResearchRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            quality_gate_results=quality_gates,
        )
        assert result is not None
        return result

    async def fail_run(
        self, run_id: uuid.UUID, error_summary: str,
    ) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.FAILED)
        result = await self._runs.update_status(
            run_id, ResearchRunStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_summary=error_summary,
        )
        assert result is not None
        return result

    async def partial_run(
        self,
        run_id: uuid.UUID,
        error_summary: str,
        quality_gates: dict[str, object] | None = None,
    ) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.PARTIAL)
        result = await self._runs.update_status(
            run_id, ResearchRunStatus.PARTIAL,
            completed_at=datetime.now(UTC),
            error_summary=error_summary,
            quality_gate_results=quality_gates,
        )
        assert result is not None
        return result

    async def cancel_run(self, run_id: uuid.UUID) -> ResearchRun:
        run = await self._get_run(run_id)
        validate_run_transition(run.status, ResearchRunStatus.CANCELLED)
        result = await self._runs.update_status(
            run_id, ResearchRunStatus.CANCELLED,
            completed_at=datetime.now(UTC),
        )
        assert result is not None
        return result

    async def get_run(self, run_id: uuid.UUID) -> ResearchRun:
        return await self._get_run(run_id)

    async def get_runs_for_company(
        self, company_id: uuid.UUID, *, limit: int = 10,
    ) -> list[ResearchRun]:
        return await self._runs.get_by_company(company_id, limit=limit)

    async def get_run_progress(self, run_id: uuid.UUID) -> RunProgress:
        run = await self._get_run(run_id)
        steps = await self._steps.get_by_run(run_id)
        findings = await self._findings.get_by_run(run_id)

        steps_completed = sum(
            1 for s in steps if s.status == StepStatus.COMPLETED
        )
        current_step: str | None = None
        current_agent: str | None = None
        for s in steps:
            if s.status == StepStatus.RUNNING:
                current_step = s.step_name
                break

        if current_step:
            for s in steps:
                if s.step_name == current_step:
                    execs = await self._executions.get_by_step(s.id)
                    running = [
                        e for e in execs
                        if e.status == AgentExecutionStatus.RUNNING
                    ]
                    if running:
                        current_agent = running[0].agent_name
                    break

        elapsed = 0
        if run.started_at:
            elapsed = int((datetime.now(UTC) - run.started_at).total_seconds())

        return RunProgress(
            run_id=run_id,
            status=run.status,
            steps_total=len(steps),
            steps_completed=steps_completed,
            current_step=current_step,
            current_agent=current_agent,
            findings_count=len(findings),
            elapsed_seconds=elapsed,
        )

    # -- Step management (AC-1) -----------------------------------------------

    async def create_steps(
        self,
        run_id: uuid.UUID,
        step_defs: list[ResearchRunStepCreate],
    ) -> list[ResearchRunStep]:
        await self._get_run(run_id)
        steps = [
            ResearchRunStep(
                research_run_id=run_id,
                step_name=s.step_name,
                step_order=s.step_order,
                step_type=s.step_type,
                status=StepStatus.PENDING,
            )
            for s in step_defs
        ]
        return await self._steps.create_batch(steps)

    async def start_step(self, step_id: uuid.UUID) -> ResearchRunStep:
        step = await self._get_step(step_id)
        validate_step_transition(step.status, StepStatus.RUNNING)
        result = await self._steps.update_status(
            step_id,
            StepStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        assert result is not None
        return result

    async def complete_step(
        self,
        step_id: uuid.UUID,
        *,
        output_state_hash: str | None = None,
    ) -> ResearchRunStep:
        step = await self._get_step(step_id)
        validate_step_transition(step.status, StepStatus.COMPLETED)
        result = await self._steps.update_status(
            step_id,
            StepStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        assert result is not None
        if output_state_hash is not None:
            result.output_state_hash = output_state_hash
            await self._session.flush()
            await self._session.refresh(result)
        return result

    async def fail_step(
        self, step_id: uuid.UUID, error_message: str,
    ) -> ResearchRunStep:
        step = await self._get_step(step_id)
        validate_step_transition(step.status, StepStatus.FAILED)
        result = await self._steps.update_status(
            step_id,
            StepStatus.FAILED,
            completed_at=datetime.now(UTC),
            error_message=error_message,
        )
        assert result is not None
        return result

    async def skip_step(self, step_id: uuid.UUID) -> ResearchRunStep:
        step = await self._get_step(step_id)
        validate_step_transition(step.status, StepStatus.SKIPPED)
        result = await self._steps.update_status(step_id, StepStatus.SKIPPED)
        assert result is not None
        return result

    async def retry_step(self, step_id: uuid.UUID) -> ResearchRunStep:
        step = await self._get_step(step_id)
        validate_step_transition(step.status, StepStatus.RUNNING)
        result = await self._steps.update_status(
            step_id,
            StepStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        assert result is not None
        return result

    # -- Agent execution (AC-4, AC-5, AC-21, AC-22) --------------------------

    async def record_agent_execution(
        self,
        run_id: uuid.UUID,
        step_id: uuid.UUID | None,
        data: AgentExecutionCreate,
    ) -> AgentExecution:
        await self._get_run(run_id)
        if step_id is not None:
            await self._get_step(step_id)

        if data.attempt_number > MAX_AGENT_RETRIES:
            raise ValidationError(
                message=f"Attempt number {data.attempt_number} exceeds max retries ({MAX_AGENT_RETRIES})",
                details={
                    "attempt_number": data.attempt_number,
                    "max_retries": MAX_AGENT_RETRIES,
                },
            )

        execution = AgentExecution(
            research_run_id=run_id,
            step_id=step_id,
            agent_name=data.agent_name,
            attempt_number=data.attempt_number,
            status=AgentExecutionStatus.RUNNING,
            model_provider=data.model_provider,
            model_name=data.model_name,
            model_config=data.llm_config,
            prompt_version=data.prompt_version,
            tool_versions=data.tool_versions,
        )
        return await self._executions.create(execution)

    async def complete_agent(
        self,
        execution_id: uuid.UUID,
        *,
        token_usage: TokenUsage,
        cost_usd: Decimal,
        findings_count: int,
        duration_ms: int | None = None,
    ) -> AgentExecution:
        execution = await self._get_execution(execution_id)
        validate_execution_transition(
            execution.status, AgentExecutionStatus.COMPLETED,
        )
        execution.status = AgentExecutionStatus.COMPLETED
        execution.completed_at = datetime.now(UTC)
        execution.input_tokens = token_usage.input_tokens
        execution.output_tokens = token_usage.output_tokens
        execution.cost_usd = cost_usd
        execution.findings_produced = findings_count
        if duration_ms is not None:
            execution.duration_ms = duration_ms
        await self._session.flush()
        await self._session.refresh(execution)
        return execution

    async def fail_agent(
        self,
        execution_id: uuid.UUID,
        *,
        error_message: str,
        error_type: str,
        status: str = AgentExecutionStatus.FAILED,
        token_usage: TokenUsage | None = None,
        cost_usd: Decimal | None = None,
        duration_ms: int | None = None,
    ) -> AgentExecution:
        if status not in (
            AgentExecutionStatus.FAILED,
            AgentExecutionStatus.TIMEOUT,
            AgentExecutionStatus.TRUNCATED,
        ):
            raise ValidationError(
                message=f"Invalid failure status: {status}",
                details={"status": status},
            )
        execution = await self._get_execution(execution_id)
        validate_execution_transition(execution.status, status)
        execution.status = status
        execution.completed_at = datetime.now(UTC)
        execution.error_message = error_message
        execution.error_type = error_type
        if token_usage is not None:
            execution.input_tokens = token_usage.input_tokens
            execution.output_tokens = token_usage.output_tokens
        if cost_usd is not None:
            execution.cost_usd = cost_usd
        if duration_ms is not None:
            execution.duration_ms = duration_ms
        await self._session.flush()
        await self._session.refresh(execution)
        return execution

    # -- Findings (AC-8, AC-9, AC-10, AC-11, AC-12) --------------------------

    async def record_findings(
        self,
        run_id: uuid.UUID,
        execution_id: uuid.UUID | None,
        finding_defs: list[ResearchFindingCreate],
    ) -> list[ResearchFinding]:
        run = await self._get_run(run_id)

        findings: list[ResearchFinding] = []
        for fd in finding_defs:
            self._validate_temporal_consistency(fd, run)

            finding = ResearchFinding(
                research_run_id=run_id,
                agent_execution_id=execution_id,
                agent_name=fd.agent_name,
                finding_type=fd.finding_type,
                category=fd.category,
                content=fd.content,
                confidence=fd.confidence,
                observation_date=fd.observation_date,
                source_publication_date=fd.source_publication_date,
                calculation_version=fd.calculation_version,
                supersedes_finding_id=fd.supersedes_finding_id,
            )
            findings.append(finding)

        persisted = await self._findings.create_batch(findings)
        self._validate_publication_date_against_created_at(persisted)
        return persisted

    async def get_findings(
        self,
        run_id: uuid.UUID,
        *,
        finding_type: str | None = None,
    ) -> list[ResearchFinding]:
        return await self._findings.get_by_run(run_id, finding_type=finding_type)

    async def get_unsupported_facts(
        self, run_id: uuid.UUID,
    ) -> list[ResearchFinding]:
        return await self._findings.get_unsupported_facts(run_id)

    # -- Artifacts (AC-23) ----------------------------------------------------

    async def record_artifact(
        self,
        run_id: uuid.UUID,
        execution_id: uuid.UUID | None,
        data: ResearchArtifactCreate,
    ) -> ResearchArtifact:
        await self._get_run(run_id)
        artifact = ResearchArtifact(
            research_run_id=run_id,
            agent_execution_id=execution_id,
            artifact_type=data.artifact_type,
            title=data.title,
            content_type=data.content_type,
            content_hash=data.content_hash,
            storage_path=data.storage_path,
            inline_content=data.inline_content,
            metadata_=data.metadata,
        )
        return await self._artifacts.create(artifact)

    async def get_artifacts(
        self,
        run_id: uuid.UUID,
        *,
        artifact_type: str | None = None,
    ) -> list[ResearchArtifact]:
        return await self._artifacts.get_by_run(
            run_id, artifact_type=artifact_type,
        )

    # -- Sources (AC-23) ------------------------------------------------------

    async def record_source_access(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        access_type: str,
    ) -> ResearchRunSource:
        await self._get_run(run_id)
        source = ResearchRunSource(
            research_run_id=run_id,
            document_id=document_id,
            access_type=access_type,
        )
        return await self._sources.create(source)

    # -- Aggregate updates (AC-22) --------------------------------------------

    async def update_run_aggregates(
        self, run_id: uuid.UUID,
    ) -> ResearchRun:
        await self._get_run(run_id)
        executions = await self._executions.get_by_run(run_id)

        total_input = sum(e.input_tokens for e in executions)
        total_output = sum(e.output_tokens for e in executions)
        total_cost = sum((e.cost_usd for e in executions), Decimal(0))

        result = await self._runs.update_aggregates(
            run_id,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=total_cost,
        )
        assert result is not None
        return result

    # -- Private helpers -------------------------------------------------------

    async def _get_run(self, run_id: uuid.UUID) -> ResearchRun:
        run = await self._runs.get_by_id(run_id)
        if run is None:
            raise NotFoundError(
                message="Research run not found",
                details={"run_id": str(run_id)},
            )
        return run

    async def _get_step(self, step_id: uuid.UUID) -> ResearchRunStep:
        step = await self._steps.get_by_id(step_id)
        if step is None:
            raise NotFoundError(
                message="Research run step not found",
                details={"step_id": str(step_id)},
            )
        return step

    async def _get_execution(
        self, execution_id: uuid.UUID,
    ) -> AgentExecution:
        execution = await self._executions.get_by_id(execution_id)
        if execution is None:
            raise NotFoundError(
                message="Agent execution not found",
                details={"execution_id": str(execution_id)},
            )
        return execution

    @staticmethod
    def _validate_temporal_consistency(
        finding: ResearchFindingCreate,
        run: ResearchRun,
    ) -> None:
        if (
            finding.observation_date is not None
            and run.observation_date is not None
            and finding.observation_date > run.observation_date
        ):
            raise ValidationError(
                message="Finding observation_date cannot be after run observation_date",
                details={
                    "finding_observation_date": str(finding.observation_date),
                    "run_observation_date": str(run.observation_date),
                },
            )
        if (
            finding.source_publication_date is not None
            and finding.observation_date is not None
            and finding.source_publication_date > finding.observation_date
        ):
            raise ValidationError(
                message="source_publication_date cannot be after observation_date",
                details={
                    "source_publication_date": str(finding.source_publication_date),
                    "observation_date": str(finding.observation_date),
                },
            )

    @staticmethod
    def _validate_publication_date_against_created_at(
        findings: list[ResearchFinding],
    ) -> None:
        for finding in findings:
            if (
                finding.source_publication_date is not None
                and finding.created_at is not None
                and finding.source_publication_date > finding.created_at.date()
            ):
                raise ValidationError(
                    message="source_publication_date cannot be after finding created_at",
                    details={
                        "finding_id": str(finding.id),
                        "source_publication_date": str(finding.source_publication_date),
                        "created_at": str(finding.created_at),
                    },
                )
