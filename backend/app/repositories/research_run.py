"""Repositories for Research Run infrastructure entities."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import FindingType, ResearchRunStatus
from app.models.research import (
    AgentExecution,
    ResearchArtifact,
    ResearchFinding,
    ResearchRun,
    ResearchRunSource,
    ResearchRunStep,
)
from app.repositories.base import BaseRepository

# ---------------------------------------------------------------------------
# Protocol interfaces (AC-20)
# ---------------------------------------------------------------------------


class ResearchRunRepositoryProtocol(Protocol):
    async def create(self, run: ResearchRun) -> ResearchRun: ...
    async def get_by_id(self, run_id: uuid.UUID) -> ResearchRun | None: ...
    async def get_by_company(
        self, company_id: uuid.UUID, *, limit: int = 10,
    ) -> list[ResearchRun]: ...
    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        *,
        error_summary: str | None = None,
        completed_at: datetime | None = None,
        started_at: datetime | None = None,
        quality_gate_results: dict[str, object] | None = None,
    ) -> ResearchRun | None: ...
    async def update_company_id(
        self, run_id: uuid.UUID, company_id: uuid.UUID,
    ) -> ResearchRun | None: ...
    async def get_active_run(self, company_id: uuid.UUID) -> ResearchRun | None: ...


class AgentExecutionRepositoryProtocol(Protocol):
    async def create(self, execution: AgentExecution) -> AgentExecution: ...
    async def get_by_id(self, execution_id: uuid.UUID) -> AgentExecution | None: ...
    async def get_by_run(self, run_id: uuid.UUID) -> list[AgentExecution]: ...
    async def get_by_step(self, step_id: uuid.UUID) -> list[AgentExecution]: ...


class ResearchRunStepRepositoryProtocol(Protocol):
    async def create(self, step: ResearchRunStep) -> ResearchRunStep: ...
    async def create_batch(
        self, steps: list[ResearchRunStep],
    ) -> list[ResearchRunStep]: ...
    async def get_by_run(self, run_id: uuid.UUID) -> list[ResearchRunStep]: ...
    async def update_status(
        self,
        step_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> ResearchRunStep | None: ...


class ResearchFindingRepositoryProtocol(Protocol):
    async def create(self, finding: ResearchFinding) -> ResearchFinding: ...
    async def create_batch(
        self, findings: list[ResearchFinding],
    ) -> list[ResearchFinding]: ...
    async def get_by_run(
        self, run_id: uuid.UUID, *, finding_type: str | None = None,
    ) -> list[ResearchFinding]: ...
    async def get_unsupported_facts(
        self, run_id: uuid.UUID,
    ) -> list[ResearchFinding]: ...
    async def get_current_for_company(
        self, company_id: uuid.UUID,
    ) -> list[ResearchFinding]: ...


class ResearchArtifactRepositoryProtocol(Protocol):
    async def create(self, artifact: ResearchArtifact) -> ResearchArtifact: ...
    async def get_by_run(
        self, run_id: uuid.UUID, *, artifact_type: str | None = None,
    ) -> list[ResearchArtifact]: ...


class ResearchRunSourceRepositoryProtocol(Protocol):
    async def create(self, source: ResearchRunSource) -> ResearchRunSource: ...
    async def get_by_run(self, run_id: uuid.UUID) -> list[ResearchRunSource]: ...


# ---------------------------------------------------------------------------
# SQLAlchemy implementations
# ---------------------------------------------------------------------------


class ResearchRunRepository(BaseRepository[ResearchRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchRun)

    async def get_with_relations(
        self, run_id: uuid.UUID,
    ) -> ResearchRun | None:
        stmt = (
            sa.select(ResearchRun)
            .options(
                selectinload(ResearchRun.steps),
                selectinload(ResearchRun.agent_executions),
            )
            .where(ResearchRun.id == run_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_company(
        self, company_id: uuid.UUID, *, limit: int = 10,
    ) -> list[ResearchRun]:
        stmt = (
            sa.select(ResearchRun)
            .where(ResearchRun.company_id == company_id)
            .order_by(ResearchRun.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        *,
        error_summary: str | None = None,
        completed_at: datetime | None = None,
        started_at: datetime | None = None,
        quality_gate_results: dict[str, object] | None = None,
    ) -> ResearchRun | None:
        run = await self.get_by_id(run_id)
        if run is None:
            return None
        run.status = status
        if error_summary is not None:
            run.error_summary = error_summary
        if completed_at is not None:
            run.completed_at = completed_at
        if started_at is not None:
            run.started_at = started_at
        if quality_gate_results is not None:
            run.quality_gate_results = quality_gate_results
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def update_company_id(
        self, run_id: uuid.UUID, company_id: uuid.UUID,
    ) -> ResearchRun | None:
        run = await self.get_by_id(run_id)
        if run is None:
            return None
        run.company_id = company_id
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def get_active_run(
        self, company_id: uuid.UUID,
    ) -> ResearchRun | None:
        active_statuses = [
            ResearchRunStatus.CREATED,
            ResearchRunStatus.QUEUED,
            ResearchRunStatus.RUNNING,
        ]
        stmt = (
            sa.select(ResearchRun)
            .where(
                ResearchRun.company_id == company_id,
                ResearchRun.status.in_(active_statuses),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_aggregates(
        self,
        run_id: uuid.UUID,
        *,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost_usd: Decimal,
        research_completeness: Decimal | None = None,
    ) -> ResearchRun | None:
        run = await self.get_by_id(run_id)
        if run is None:
            return None
        run.total_input_tokens = total_input_tokens
        run.total_output_tokens = total_output_tokens
        run.total_cost_usd = total_cost_usd
        if research_completeness is not None:
            run.research_completeness = research_completeness
        await self._session.flush()
        await self._session.refresh(run)
        return run


class ResearchRunStepRepository(BaseRepository[ResearchRunStep]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchRunStep)

    async def create_batch(
        self, steps: list[ResearchRunStep],
    ) -> list[ResearchRunStep]:
        self._session.add_all(steps)
        await self._session.flush()
        for step in steps:
            await self._session.refresh(step)
        return steps

    async def get_by_run(
        self, run_id: uuid.UUID,
    ) -> list[ResearchRunStep]:
        stmt = (
            sa.select(ResearchRunStep)
            .where(ResearchRunStep.research_run_id == run_id)
            .order_by(ResearchRunStep.step_order)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        step_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> ResearchRunStep | None:
        step = await self.get_by_id(step_id)
        if step is None:
            return None
        step.status = status
        if started_at is not None:
            step.started_at = started_at
        if completed_at is not None:
            step.completed_at = completed_at
        if error_message is not None:
            step.error_message = error_message
        await self._session.flush()
        await self._session.refresh(step)
        return step


class AgentExecutionRepository(BaseRepository[AgentExecution]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AgentExecution)

    async def get_by_run(
        self, run_id: uuid.UUID,
    ) -> list[AgentExecution]:
        stmt = (
            sa.select(AgentExecution)
            .where(AgentExecution.research_run_id == run_id)
            .order_by(AgentExecution.started_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_step(
        self, step_id: uuid.UUID,
    ) -> list[AgentExecution]:
        stmt = (
            sa.select(AgentExecution)
            .where(AgentExecution.step_id == step_id)
            .order_by(AgentExecution.attempt_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_agent(
        self, run_id: uuid.UUID, agent_name: str,
    ) -> AgentExecution | None:
        stmt = (
            sa.select(AgentExecution)
            .where(
                AgentExecution.research_run_id == run_id,
                AgentExecution.agent_name == agent_name,
            )
            .order_by(AgentExecution.attempt_number.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class ResearchFindingRepository(BaseRepository[ResearchFinding]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchFinding)

    async def create_batch(
        self, findings: list[ResearchFinding],
    ) -> list[ResearchFinding]:
        self._session.add_all(findings)
        await self._session.flush()
        for finding in findings:
            await self._session.refresh(finding)
        return findings

    async def get_by_run(
        self,
        run_id: uuid.UUID,
        *,
        finding_type: str | None = None,
    ) -> list[ResearchFinding]:
        stmt = sa.select(ResearchFinding).where(
            ResearchFinding.research_run_id == run_id,
        )
        if finding_type is not None:
            stmt = stmt.where(ResearchFinding.finding_type == finding_type)
        stmt = stmt.order_by(ResearchFinding.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_unsupported_facts(
        self, run_id: uuid.UUID,
    ) -> list[ResearchFinding]:
        from app.models.research import research_finding_evidence

        subq = (
            sa.select(research_finding_evidence.c.research_finding_id)
            .where(research_finding_evidence.c.research_finding_id == ResearchFinding.id)
            .correlate(ResearchFinding)
            .exists()
        )
        stmt = (
            sa.select(ResearchFinding)
            .where(
                ResearchFinding.research_run_id == run_id,
                ResearchFinding.finding_type == FindingType.FACT,
                ~subq,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current_for_company(
        self, company_id: uuid.UUID,
    ) -> list[ResearchFinding]:
        superseded_ids = (
            sa.select(ResearchFinding.supersedes_finding_id)
            .where(ResearchFinding.supersedes_finding_id.isnot(None))
            .scalar_subquery()
        )
        stmt = (
            sa.select(ResearchFinding)
            .join(ResearchRun, ResearchRun.id == ResearchFinding.research_run_id)
            .where(
                ResearchRun.company_id == company_id,
                ResearchFinding.id.notin_(superseded_ids),
            )
            .order_by(ResearchFinding.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ResearchArtifactRepository(BaseRepository[ResearchArtifact]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchArtifact)

    async def get_by_run(
        self,
        run_id: uuid.UUID,
        *,
        artifact_type: str | None = None,
    ) -> list[ResearchArtifact]:
        stmt = sa.select(ResearchArtifact).where(
            ResearchArtifact.research_run_id == run_id,
        )
        if artifact_type is not None:
            stmt = stmt.where(ResearchArtifact.artifact_type == artifact_type)
        stmt = stmt.order_by(ResearchArtifact.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ResearchRunSourceRepository(BaseRepository[ResearchRunSource]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchRunSource)

    async def get_by_run(
        self, run_id: uuid.UUID,
    ) -> list[ResearchRunSource]:
        stmt = (
            sa.select(ResearchRunSource)
            .where(ResearchRunSource.research_run_id == run_id)
            .order_by(ResearchRunSource.accessed_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
