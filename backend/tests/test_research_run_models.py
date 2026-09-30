"""Tier 2: Model and enum tests for Phase 7 research run infrastructure.

Tests model field definitions, CHECK constraints, enum values,
relationship declarations, and immutability contracts.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.enums import (
    AgentExecutionStatus,
    ArtifactType,
    ConfidenceLevel,
    FindingType,
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

# ---------------------------------------------------------------------------
# Enum tests (AC-2)
# ---------------------------------------------------------------------------


class TestResearchRunStatusEnum:
    def test_has_seven_values(self) -> None:
        assert len(ResearchRunStatus) == 7

    def test_values(self) -> None:
        expected = {
            "CREATED", "QUEUED", "RUNNING",
            "COMPLETED", "FAILED", "PARTIAL", "CANCELLED",
        }
        assert {s.value for s in ResearchRunStatus} == expected

    def test_no_incomplete(self) -> None:
        assert not hasattr(ResearchRunStatus, "INCOMPLETE")
        assert "INCOMPLETE" not in {s.value for s in ResearchRunStatus}

    def test_is_str_enum(self) -> None:
        assert isinstance(ResearchRunStatus.CREATED, str)
        assert ResearchRunStatus.CREATED == "CREATED"


class TestStepStatusEnum:
    def test_has_five_values(self) -> None:
        assert len(StepStatus) == 5

    def test_values(self) -> None:
        expected = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"}
        assert {s.value for s in StepStatus} == expected


class TestAgentExecutionStatusEnum:
    def test_has_five_values(self) -> None:
        assert len(AgentExecutionStatus) == 5

    def test_values(self) -> None:
        expected = {"RUNNING", "COMPLETED", "FAILED", "TIMEOUT", "TRUNCATED"}
        assert {s.value for s in AgentExecutionStatus} == expected


class TestArtifactTypeEnum:
    def test_has_five_values(self) -> None:
        assert len(ArtifactType) == 5

    def test_values(self) -> None:
        expected = {
            "REPORT", "ANALYSIS", "CHART_DATA",
            "CALCULATION_RESULT", "INTERMEDIATE_STATE",
        }
        assert {s.value for s in ArtifactType} == expected


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------


class TestResearchRunModel:
    def test_create_with_defaults(self) -> None:
        run = ResearchRun(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            status=ResearchRunStatus.CREATED,
        )
        assert run.status == "CREATED"
        assert run.run_type is None
        assert run.parent_run_id is None
        assert run.observation_date is None
        assert run.configuration is None
        assert run.error_summary is None

    def test_create_with_all_fields(self) -> None:
        parent_id = uuid.uuid4()
        config = {"agents": ["financial_analysis"], "budget": 100000}
        run = ResearchRun(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            parent_run_id=parent_id,
            status=ResearchRunStatus.CREATED,
            observation_date=date(2026, 9, 30),
            configuration=config,
        )
        assert run.run_type == "FULL"
        assert run.trigger_type == "USER_INITIATED"
        assert run.parent_run_id == parent_id
        assert run.observation_date == date(2026, 9, 30)
        assert run.configuration == config

    def test_deprecated_jsonb_fields_exist(self) -> None:
        run = ResearchRun(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
        )
        assert hasattr(run, "agent_execution_log")
        assert hasattr(run, "data_sources_used")
        assert hasattr(run, "cost_by_agent")

    def test_tablename(self) -> None:
        assert ResearchRun.__tablename__ == "research_run"

    def test_schema(self) -> None:
        assert ResearchRun.__table_args__[-1]["schema"] == "research"


class TestResearchRunStepModel:
    def test_create(self) -> None:
        step = ResearchRunStep(
            research_run_id=uuid.uuid4(),
            step_name="financial_analysis",
            step_order=1,
            step_type="AGENT",
            status=StepStatus.PENDING,
        )
        assert step.status == "PENDING"
        assert step.started_at is None
        assert step.completed_at is None
        assert step.error_message is None

    def test_tablename(self) -> None:
        assert ResearchRunStep.__tablename__ == "research_run_step"

    def test_has_timestamp_mixin_fields(self) -> None:
        assert hasattr(ResearchRunStep, "created_at")
        assert hasattr(ResearchRunStep, "updated_at")


class TestAgentExecutionModel:
    def test_create_with_required_fields(self) -> None:
        execution = AgentExecution(
            research_run_id=uuid.uuid4(),
            agent_name="financial_analysis_agent",
            attempt_number=1,
            status=AgentExecutionStatus.RUNNING,
            model_provider="anthropic",
            model_name="claude-sonnet-5",
        )
        assert execution.attempt_number == 1
        assert execution.status == "RUNNING"
        assert execution.error_message is None
        assert execution.error_type is None

    def test_create_with_all_fields(self) -> None:
        execution = AgentExecution(
            research_run_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            agent_name="moat_assessment_agent",
            attempt_number=2,
            status=AgentExecutionStatus.RUNNING,
            model_provider="openai",
            model_name="gpt-4o",
            model_config={"temperature": 0.1, "max_tokens": 4096},
            prompt_version="v1.2.0",
            tool_versions={"ratio_calculator": "1.0.0"},
        )
        assert execution.attempt_number == 2
        assert execution.model_config == {"temperature": 0.1, "max_tokens": 4096}
        assert execution.prompt_version == "v1.2.0"

    def test_tablename(self) -> None:
        assert AgentExecution.__tablename__ == "agent_execution"


class TestResearchFindingModel:
    def test_new_fields_exist(self) -> None:
        finding = ResearchFinding(
            research_run_id=uuid.uuid4(),
            agent_name="financial_analysis_agent",
            finding_type=FindingType.FACT,
            category="revenue",
            content="Revenue was INR 1000 Cr",
            confidence=ConfidenceLevel.HIGH,
            observation_date=date(2026, 9, 30),
            source_publication_date=date(2026, 9, 15),
            calculation_version="1.0.0",
        )
        assert finding.observation_date == date(2026, 9, 30)
        assert finding.source_publication_date == date(2026, 9, 15)
        assert finding.calculation_version == "1.0.0"
        assert finding.supersedes_finding_id is None
        assert finding.agent_execution_id is None

    def test_supersession_field(self) -> None:
        old_id = uuid.uuid4()
        finding = ResearchFinding(
            research_run_id=uuid.uuid4(),
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="test",
            content="Updated revenue figure",
            confidence=ConfidenceLevel.HIGH,
            supersedes_finding_id=old_id,
        )
        assert finding.supersedes_finding_id == old_id


class TestResearchArtifactModel:
    def test_create(self) -> None:
        artifact = ResearchArtifact(
            research_run_id=uuid.uuid4(),
            artifact_type=ArtifactType.REPORT,
            title="Financial Analysis Report",
            content_type="text/markdown",
            content_hash="abc123" * 10 + "abcd",
        )
        assert artifact.storage_path is None
        assert artifact.inline_content is None

    def test_tablename(self) -> None:
        assert ResearchArtifact.__tablename__ == "research_artifact"


class TestResearchRunSourceModel:
    def test_create(self) -> None:
        source = ResearchRunSource(
            research_run_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            access_type="FULL_READ",
        )
        assert source.access_type == "FULL_READ"

    def test_tablename(self) -> None:
        assert ResearchRunSource.__tablename__ == "research_run_source"


# ---------------------------------------------------------------------------
# CHECK constraint verification (AC-2)
# ---------------------------------------------------------------------------


class TestCheckConstraints:
    """Verify CHECK constraints are declared in __table_args__."""

    def _get_check_constraints(self, model: type) -> list[str]:
        constraints = []
        for arg in model.__table_args__:
            if hasattr(arg, "sqltext"):
                constraints.append(str(arg.sqltext))
        return constraints

    def test_research_run_status_check(self) -> None:
        checks = self._get_check_constraints(ResearchRun)
        status_checks = [c for c in checks if "status" in c.lower()]
        assert len(status_checks) == 1
        check = status_checks[0]
        for status in ResearchRunStatus:
            assert status.value in check
        assert "INCOMPLETE" not in check

    def test_research_run_step_status_check(self) -> None:
        checks = self._get_check_constraints(ResearchRunStep)
        status_checks = [c for c in checks if "status" in c.lower()]
        assert len(status_checks) == 1
        check = status_checks[0]
        for status in StepStatus:
            assert status.value in check

    def test_agent_execution_status_check(self) -> None:
        checks = self._get_check_constraints(AgentExecution)
        status_checks = [c for c in checks if "status" in c.lower()]
        assert len(status_checks) == 1
        check = status_checks[0]
        for status in AgentExecutionStatus:
            assert status.value in check


# ---------------------------------------------------------------------------
# No LangGraph / No processor dependency (AC-15, AC-16)
# ---------------------------------------------------------------------------


class TestNoDependencies:
    def test_no_langgraph_in_research_models(self) -> None:
        import inspect

        import app.models.research as module
        source = inspect.getsource(module)
        assert "langgraph" not in source.lower()

    def test_no_langgraph_in_state_machines(self) -> None:
        import inspect

        import app.models.state_machines as module
        source = inspect.getsource(module)
        assert "langgraph" not in source.lower()

    def test_no_celery_in_service(self) -> None:
        import inspect

        import app.services.research_run as module
        source = inspect.getsource(module)
        assert "celery" not in source.lower()
        assert "import temporal" not in source.lower()
        assert "from temporal" not in source.lower()
