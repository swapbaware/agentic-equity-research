"""Tier 3: Repository tests for Research Run infrastructure.

Tests repository operations with mocked AsyncSession.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import (
    FindingType,
    ResearchRunStatus,
)
from app.models.research import (
    AgentExecution,
    ResearchFinding,
    ResearchRun,
    ResearchRunStep,
)
from app.repositories.research_run import (
    AgentExecutionRepository,
    ResearchArtifactRepository,
    ResearchFindingRepository,
    ResearchRunRepository,
    ResearchRunSourceRepository,
    ResearchRunStepRepository,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# ResearchRunRepository
# ---------------------------------------------------------------------------


class TestResearchRunRepository:
    def test_init(self) -> None:
        session = _mock_session()
        repo = ResearchRunRepository(session)
        assert repo._model_class is ResearchRun

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        session = _mock_session()
        run = ResearchRun(id=uuid.uuid4(), company_id=uuid.uuid4(), initiated_by="test")
        session.get.return_value = run
        repo = ResearchRunRepository(session)

        result = await repo.get_by_id(run.id)
        assert result == run
        session.get.assert_called_once_with(ResearchRun, run.id)

    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = _mock_session()
        run = ResearchRun(company_id=uuid.uuid4(), initiated_by="test")
        repo = ResearchRunRepository(session)

        await repo.create(run)
        session.add.assert_called_once_with(run)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(run)

    @pytest.mark.asyncio
    async def test_get_by_company(self) -> None:
        session = _mock_session()
        company_id = uuid.uuid4()
        run1 = ResearchRun(id=uuid.uuid4(), company_id=company_id, initiated_by="test")
        run2 = ResearchRun(id=uuid.uuid4(), company_id=company_id, initiated_by="test")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [run1, run2]
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        results = await repo.get_by_company(company_id)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_update_status(self) -> None:
        session = _mock_session()
        run = ResearchRun(id=uuid.uuid4(), company_id=uuid.uuid4(), initiated_by="test")
        run.status = ResearchRunStatus.RUNNING
        session.get.return_value = run

        repo = ResearchRunRepository(session)
        result = await repo.update_status(
            run.id, ResearchRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        assert result is not None
        assert result.status == ResearchRunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_active_run_found(self) -> None:
        session = _mock_session()
        run = ResearchRun(
            id=uuid.uuid4(), company_id=uuid.uuid4(),
            initiated_by="test", status=ResearchRunStatus.RUNNING,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        result = await repo.get_active_run(run.company_id)
        assert result == run

    @pytest.mark.asyncio
    async def test_get_active_run_not_found(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        result = await repo.get_active_run(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_aggregates(self) -> None:
        session = _mock_session()
        run = ResearchRun(id=uuid.uuid4(), company_id=uuid.uuid4(), initiated_by="test")
        session.get.return_value = run

        repo = ResearchRunRepository(session)
        result = await repo.update_aggregates(
            run.id,
            total_input_tokens=35000,
            total_output_tokens=9000,
            total_cost_usd=Decimal("0.054600"),
        )
        assert result is not None
        assert result.total_input_tokens == 35000
        assert result.total_output_tokens == 9000
        assert result.total_cost_usd == Decimal("0.054600")


# ---------------------------------------------------------------------------
# ResearchRunStepRepository
# ---------------------------------------------------------------------------


class TestResearchRunStepRepository:
    def test_init(self) -> None:
        session = _mock_session()
        repo = ResearchRunStepRepository(session)
        assert repo._model_class is ResearchRunStep

    @pytest.mark.asyncio
    async def test_create_batch(self) -> None:
        session = _mock_session()
        repo = ResearchRunStepRepository(session)
        steps = [
            ResearchRunStep(
                research_run_id=uuid.uuid4(),
                step_name=f"step_{i}",
                step_order=i,
                step_type="AGENT",
            )
            for i in range(3)
        ]

        result = await repo.create_batch(steps)
        assert len(result) == 3
        session.add_all.assert_called_once()
        session.flush.assert_awaited_once()
        assert session.refresh.await_count == 3

    @pytest.mark.asyncio
    async def test_get_by_run(self) -> None:
        session = _mock_session()
        run_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchRunStepRepository(session)
        results = await repo.get_by_run(run_id)
        assert results == []


# ---------------------------------------------------------------------------
# AgentExecutionRepository
# ---------------------------------------------------------------------------


class TestAgentExecutionRepository:
    def test_init(self) -> None:
        session = _mock_session()
        repo = AgentExecutionRepository(session)
        assert repo._model_class is AgentExecution

    @pytest.mark.asyncio
    async def test_get_by_run(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = AgentExecutionRepository(session)
        results = await repo.get_by_run(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_step(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = AgentExecutionRepository(session)
        results = await repo.get_by_step(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_get_latest_for_agent(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = AgentExecutionRepository(session)
        result = await repo.get_latest_for_agent(uuid.uuid4(), "test_agent")
        assert result is None


# ---------------------------------------------------------------------------
# ResearchFindingRepository
# ---------------------------------------------------------------------------


class TestResearchFindingRepository:
    @pytest.mark.asyncio
    async def test_create_batch(self) -> None:
        session = _mock_session()
        repo = ResearchFindingRepository(session)
        findings = [
            ResearchFinding(
                research_run_id=uuid.uuid4(),
                agent_name="test_agent",
                finding_type=FindingType.FACT,
                category="test",
                content=f"finding {i}",
                confidence="HIGH",
            )
            for i in range(5)
        ]

        result = await repo.create_batch(findings)
        assert len(result) == 5
        session.add_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_run(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchFindingRepository(session)
        results = await repo.get_by_run(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_run_with_type_filter(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchFindingRepository(session)
        results = await repo.get_by_run(uuid.uuid4(), finding_type="FACT")
        assert results == []


# ---------------------------------------------------------------------------
# ResearchArtifactRepository
# ---------------------------------------------------------------------------


class TestResearchArtifactRepository:
    @pytest.mark.asyncio
    async def test_get_by_run(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchArtifactRepository(session)
        results = await repo.get_by_run(uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# ResearchRunSourceRepository
# ---------------------------------------------------------------------------


class TestResearchRunSourceRepository:
    @pytest.mark.asyncio
    async def test_get_by_run(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchRunSourceRepository(session)
        results = await repo.get_by_run(uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolInterfaces:
    """Verify that concrete repositories satisfy their Protocol interfaces."""

    def test_research_run_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = ResearchRunRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_by_company")
        assert hasattr(repo, "update_status")
        assert hasattr(repo, "get_active_run")

    def test_agent_execution_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = AgentExecutionRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_by_run")
        assert hasattr(repo, "get_by_step")

    def test_step_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = ResearchRunStepRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "create_batch")
        assert hasattr(repo, "get_by_run")
        assert hasattr(repo, "update_status")

    def test_finding_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = ResearchFindingRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "create_batch")
        assert hasattr(repo, "get_by_run")
        assert hasattr(repo, "get_unsupported_facts")
        assert hasattr(repo, "get_current_for_company")

    def test_artifact_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = ResearchArtifactRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "get_by_run")

    def test_source_repo_has_protocol_methods(self) -> None:
        session = _mock_session()
        repo = ResearchRunSourceRepository(session)
        assert hasattr(repo, "create")
        assert hasattr(repo, "get_by_run")
