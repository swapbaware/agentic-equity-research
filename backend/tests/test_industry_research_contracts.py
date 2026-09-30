"""Tests for Phase 9.2: Industry Research Contracts & ResearchRun Integration.

Tests cover:
- ResearchRunCreate XOR target validation (Parts 1, 7)
- ResearchRunRead / RunSummary industry fields (Part 1)
- IndustryResearchRequest / IndustryResearchConfig contracts (Part 2)
- INDUSTRY_FINDING_CATEGORIES (Part 2)
- INDUSTRY_RESEARCH_STEPS (Part 3)
- Repository contracts — get_by_industry, get_active_industry_run (Part 4)
- Service — industry run initiation, concurrent industry run prevention (Part 5)
- Company Research backward compatibility (Part 6)
- State machine compatibility (Part 8)
- Temporal validation for industry runs (Part 9)
- Findings/Evidence compatibility (Part 10)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.agents.contracts import (
    INDUSTRY_AGENT_NAME,
    INDUSTRY_AGENT_TOKEN_BUDGET,
    INDUSTRY_AGENT_TOKEN_WARNING,
    INDUSTRY_FINDING_CATEGORIES,
    INDUSTRY_RESEARCH_STEPS,
    MAX_LLM_ATTEMPTS,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    IndustryResearchConfig,
    IndustryResearchRequest,
    TokenBudget,
)
from app.exceptions import ValidationError
from app.models.enums import FindingType, ResearchRunStatus
from app.models.research import ResearchFinding, ResearchRun
from app.repositories.research_run import ResearchRunRepository
from app.schemas.research_run import (
    ResearchFindingCreate,
    ResearchRunCreate,
    ResearchRunRead,
    RunSummary,
)
from app.services.research_run import ResearchRunService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> tuple[ResearchRunService, MagicMock]:
    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    service = ResearchRunService(mock_session)
    return service, mock_session


def _make_run(
    *,
    status: str = ResearchRunStatus.CREATED,
    company_id: uuid.UUID | None = None,
    industry_id: uuid.UUID | None = None,
    target_type: str = "company",
    observation_date: date | None = None,
) -> ResearchRun:
    run = ResearchRun(
        id=uuid.uuid4(),
        target_type=target_type,
        company_id=company_id or (uuid.uuid4() if target_type == "company" else None),
        industry_id=industry_id or (uuid.uuid4() if target_type == "industry" else None),
        initiated_by="test_user",
        status=status,
        run_type="FULL",
        trigger_type="USER_INITIATED",
        observation_date=observation_date,
    )
    run.started_at = datetime.now(UTC)
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


# ===========================================================================
# PART 1: ResearchRunCreate XOR target validation
# ===========================================================================


class TestResearchRunCreateXOR:
    def test_company_target_valid(self) -> None:
        data = ResearchRunCreate(
            target_type="company",
            company_id=uuid.uuid4(),
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )
        assert data.target_type == "company"
        assert data.company_id is not None
        assert data.industry_id is None

    def test_industry_target_valid(self) -> None:
        data = ResearchRunCreate(
            target_type="industry",
            industry_id=uuid.uuid4(),
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )
        assert data.target_type == "industry"
        assert data.industry_id is not None
        assert data.company_id is None

    def test_default_target_type_is_company(self) -> None:
        data = ResearchRunCreate(
            company_id=uuid.uuid4(),
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )
        assert data.target_type == "company"

    def test_company_target_without_company_id_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="company_id is required"):
            ResearchRunCreate(
                target_type="company",
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_company_target_with_industry_id_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="industry_id must be None"):
            ResearchRunCreate(
                target_type="company",
                company_id=uuid.uuid4(),
                industry_id=uuid.uuid4(),
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_industry_target_without_industry_id_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="industry_id is required"):
            ResearchRunCreate(
                target_type="industry",
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_industry_target_with_company_id_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="company_id must be None"):
            ResearchRunCreate(
                target_type="industry",
                company_id=uuid.uuid4(),
                industry_id=uuid.uuid4(),
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_invalid_target_type_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="target_type must be"):
            ResearchRunCreate(
                target_type="macro",
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_both_ids_none_raises(self) -> None:
        with pytest.raises(PydanticValidationError, match="company_id is required"):
            ResearchRunCreate(
                target_type="company",
                initiated_by="test",
                run_type="FULL",
                trigger_type="USER_INITIATED",
            )

    def test_run_type_preserved_for_company(self) -> None:
        """run_type retains execution-mode semantics, not target semantics."""
        data = ResearchRunCreate(
            target_type="company",
            company_id=uuid.uuid4(),
            initiated_by="test",
            run_type="INCREMENTAL",
            trigger_type="RERUN",
        )
        assert data.run_type == "INCREMENTAL"
        assert data.target_type == "company"

    def test_run_type_preserved_for_industry(self) -> None:
        """run_type retains execution-mode semantics for industry runs too."""
        data = ResearchRunCreate(
            target_type="industry",
            industry_id=uuid.uuid4(),
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )
        assert data.run_type == "FULL"
        assert data.target_type == "industry"


# ===========================================================================
# PART 1: ResearchRunRead / RunSummary with industry fields
# ===========================================================================


class TestResearchRunReadIndustry:
    def test_read_company_run(self) -> None:
        cid = uuid.uuid4()
        data = ResearchRunRead(
            id=uuid.uuid4(),
            target_type="company",
            company_id=cid,
            industry_id=None,
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            parent_run_id=None,
            status="CREATED",
            started_at=datetime.now(UTC),
            completed_at=None,
            observation_date=None,
            configuration=None,
            quality_gate_results=None,
            research_completeness=None,
            total_input_tokens=None,
            total_output_tokens=None,
            total_cost_usd=None,
            error_summary=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert data.target_type == "company"
        assert data.company_id == cid
        assert data.industry_id is None

    def test_read_industry_run(self) -> None:
        iid = uuid.uuid4()
        data = ResearchRunRead(
            id=uuid.uuid4(),
            target_type="industry",
            company_id=None,
            industry_id=iid,
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            parent_run_id=None,
            status="CREATED",
            started_at=datetime.now(UTC),
            completed_at=None,
            observation_date=None,
            configuration=None,
            quality_gate_results=None,
            research_completeness=None,
            total_input_tokens=None,
            total_output_tokens=None,
            total_cost_usd=None,
            error_summary=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert data.target_type == "industry"
        assert data.industry_id == iid
        assert data.company_id is None


class TestRunSummaryIndustry:
    def test_summary_company_run(self) -> None:
        cid = uuid.uuid4()
        summary = RunSummary(
            id=uuid.uuid4(),
            target_type="company",
            company_id=cid,
            industry_id=None,
            status="COMPLETED",
            run_type="FULL",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            observation_date=date(2026, 9, 30),
            research_completeness=None,
            total_cost_usd=None,
        )
        assert summary.target_type == "company"
        assert summary.company_id == cid

    def test_summary_industry_run(self) -> None:
        iid = uuid.uuid4()
        summary = RunSummary(
            id=uuid.uuid4(),
            target_type="industry",
            company_id=None,
            industry_id=iid,
            status="COMPLETED",
            run_type="FULL",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            observation_date=date(2026, 9, 30),
            research_completeness=None,
            total_cost_usd=None,
        )
        assert summary.target_type == "industry"
        assert summary.industry_id == iid


# ===========================================================================
# PART 2: IndustryResearchRequest / IndustryResearchConfig
# ===========================================================================


class TestIndustryResearchRequest:
    def test_valid_request(self) -> None:
        req = IndustryResearchRequest(
            industry_id=uuid.uuid4(),
            observation_date=date(2026, 9, 30),
            initiated_by="test_user",
        )
        assert req.industry_id is not None
        assert req.observation_date == date(2026, 9, 30)
        assert req.company_context_id is None
        assert req.configuration is None

    def test_request_with_company_context(self) -> None:
        cid = uuid.uuid4()
        req = IndustryResearchRequest(
            industry_id=uuid.uuid4(),
            observation_date=date(2026, 9, 30),
            initiated_by="langgraph_workflow",
            company_context_id=cid,
        )
        assert req.company_context_id == cid

    def test_request_with_configuration(self) -> None:
        config = IndustryResearchConfig(source_limit=15)
        req = IndustryResearchRequest(
            industry_id=uuid.uuid4(),
            observation_date=date(2026, 9, 30),
            initiated_by="test",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.source_limit == 15

    def test_request_is_frozen(self) -> None:
        req = IndustryResearchRequest(
            industry_id=uuid.uuid4(),
            observation_date=date(2026, 9, 30),
            initiated_by="test",
        )
        with pytest.raises(PydanticValidationError):
            req.industry_id = uuid.uuid4()  # type: ignore[misc]

    def test_empty_initiated_by_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            IndustryResearchRequest(
                industry_id=uuid.uuid4(),
                observation_date=date(2026, 9, 30),
                initiated_by="",
            )


class TestIndustryResearchConfig:
    def test_defaults(self) -> None:
        config = IndustryResearchConfig()
        assert config.token_budget == INDUSTRY_AGENT_TOKEN_BUDGET
        assert config.token_budget == 20_000
        assert config.token_warning_threshold == INDUSTRY_AGENT_TOKEN_WARNING
        assert config.token_warning_threshold == 16_000
        assert config.max_llm_attempts == MAX_LLM_ATTEMPTS
        assert config.source_limit == 20
        assert config.concurrent_retrievals == 5
        assert config.extraction_model is None
        assert config.generation_model is None
        assert config.analysis_model is None

    def test_custom_values(self) -> None:
        config = IndustryResearchConfig(
            token_budget=25_000,
            source_limit=30,
            extraction_model="haiku",
        )
        assert config.token_budget == 25_000
        assert config.source_limit == 30
        assert config.extraction_model == "haiku"

    def test_config_is_frozen(self) -> None:
        config = IndustryResearchConfig()
        with pytest.raises(PydanticValidationError):
            config.token_budget = 50_000  # type: ignore[misc]

    def test_budget_must_be_positive(self) -> None:
        with pytest.raises(PydanticValidationError):
            IndustryResearchConfig(token_budget=0)


# ===========================================================================
# PART 2: INDUSTRY_FINDING_CATEGORIES
# ===========================================================================


class TestIndustryFindingCategories:
    def test_has_14_categories(self) -> None:
        assert len(INDUSTRY_FINDING_CATEGORIES) == 14

    def test_five_forces_categories_present(self) -> None:
        five_forces = {
            "entry_barriers",
            "supplier_power",
            "buyer_power",
            "substitution_risk",
            "competitive_rivalry",
        }
        assert five_forces.issubset(INDUSTRY_FINDING_CATEGORIES)

    def test_market_and_structure_categories_present(self) -> None:
        expected = {
            "market_size",
            "growth_drivers",
            "regulatory_environment",
            "technology_trends",
            "industry_structure",
            "value_chain",
            "cyclicality",
        }
        assert expected.issubset(INDUSTRY_FINDING_CATEGORIES)

    def test_meta_categories_present(self) -> None:
        assert "research_gap" in INDUSTRY_FINDING_CATEGORIES
        assert "contradiction" in INDUSTRY_FINDING_CATEGORIES

    def test_disjoint_from_company_except_growth_drivers(self) -> None:
        from app.agents.contracts import FINDING_CATEGORIES

        overlap = INDUSTRY_FINDING_CATEGORIES & FINDING_CATEGORIES
        assert overlap == {"growth_drivers", "research_gap", "contradiction"}


# ===========================================================================
# PART 2/3: INDUSTRY_RESEARCH_STEPS
# ===========================================================================


class TestIndustryResearchSteps:
    def test_has_7_steps(self) -> None:
        assert len(INDUSTRY_RESEARCH_STEPS) == 7

    def test_step_order_sequential(self) -> None:
        orders = [s.step_order for s in INDUSTRY_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_step_names(self) -> None:
        names = [s.step_name for s in INDUSTRY_RESEARCH_STEPS]
        assert names == [
            "industry_validation",
            "source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "finding_generation",
            "finding_validation",
            "gap_contradiction_analysis",
        ]

    def test_step_types(self) -> None:
        types = [s.step_type for s in INDUSTRY_RESEARCH_STEPS]
        assert types == [
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_PROVIDER_CALL,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_LLM_REASONING,
            STEP_TYPE_DETERMINISTIC,
            STEP_TYPE_LLM_REASONING,
        ]

    def test_llm_steps_flagged(self) -> None:
        llm_steps = [s for s in INDUSTRY_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        assert {s.step_name for s in llm_steps} == {
            "evidence_extraction",
            "finding_generation",
            "gap_contradiction_analysis",
        }


# ===========================================================================
# PART 2: Industry agent constants
# ===========================================================================


class TestIndustryAgentConstants:
    def test_token_budget_is_20k(self) -> None:
        assert INDUSTRY_AGENT_TOKEN_BUDGET == 20_000

    def test_token_warning_is_16k(self) -> None:
        assert INDUSTRY_AGENT_TOKEN_WARNING == 16_000

    def test_agent_name(self) -> None:
        assert INDUSTRY_AGENT_NAME == "industry_research_agent"

    def test_token_budget_reuse_with_industry_default(self) -> None:
        budget = TokenBudget(
            budget=INDUSTRY_AGENT_TOKEN_BUDGET,
            warning_threshold=INDUSTRY_AGENT_TOKEN_WARNING,
        )
        assert budget.budget == 20_000
        assert budget.warning_threshold == 16_000
        assert budget.remaining == 20_000
        assert not budget.is_warning
        assert not budget.is_exhausted


# ===========================================================================
# PART 4: Repository — get_by_industry, get_active_industry_run
# ===========================================================================


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


class TestResearchRunRepositoryIndustry:
    @pytest.mark.asyncio
    async def test_get_by_industry(self) -> None:
        session = _mock_session()
        industry_id = uuid.uuid4()
        run1 = _make_run(target_type="industry", industry_id=industry_id)
        run2 = _make_run(target_type="industry", industry_id=industry_id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [run1, run2]
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        results = await repo.get_by_industry(industry_id)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_by_industry_empty(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        results = await repo.get_by_industry(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_get_active_industry_run_found(self) -> None:
        session = _mock_session()
        industry_id = uuid.uuid4()
        run = _make_run(
            target_type="industry",
            industry_id=industry_id,
            status=ResearchRunStatus.RUNNING,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        result = await repo.get_active_industry_run(industry_id)
        assert result == run

    @pytest.mark.asyncio
    async def test_get_active_industry_run_not_found(self) -> None:
        session = _mock_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = ResearchRunRepository(session)
        result = await repo.get_active_industry_run(uuid.uuid4())
        assert result is None

    def test_protocol_has_industry_methods(self) -> None:
        session = _mock_session()
        repo = ResearchRunRepository(session)
        assert hasattr(repo, "get_by_industry")
        assert hasattr(repo, "get_active_industry_run")


# ===========================================================================
# PART 5: Service — industry run initiation
# ===========================================================================


class TestServiceIndustryRunInitiation:
    @pytest.mark.asyncio
    async def test_initiate_industry_run(self) -> None:
        service, _ = _make_service()
        industry_id = uuid.uuid4()
        data = ResearchRunCreate(
            target_type="industry",
            industry_id=industry_id,
            initiated_by="test_user",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            observation_date=date(2026, 9, 30),
        )

        with (
            patch.object(
                service._runs,
                "get_active_industry_run",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(service._runs, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda run: run
            result = await service.initiate_run(data)

        assert result.status == ResearchRunStatus.CREATED
        assert result.target_type == "industry"
        assert result.industry_id == industry_id
        assert result.company_id is None
        assert result.run_type == "FULL"

    @pytest.mark.asyncio
    async def test_initiate_industry_run_blocked_by_active(self) -> None:
        service, _ = _make_service()
        industry_id = uuid.uuid4()
        existing = _make_run(
            target_type="industry",
            industry_id=industry_id,
            status=ResearchRunStatus.RUNNING,
        )
        data = ResearchRunCreate(
            target_type="industry",
            industry_id=industry_id,
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )

        with (
            patch.object(
                service._runs,
                "get_active_industry_run",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            pytest.raises(ValidationError, match="already active for this industry"),
        ):
            await service.initiate_run(data)

    @pytest.mark.asyncio
    async def test_company_run_still_uses_company_active_check(self) -> None:
        """Backward compatibility: company runs still check company active runs."""
        service, _ = _make_service()
        company_id = uuid.uuid4()
        data = ResearchRunCreate(
            company_id=company_id,
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )

        with (
            patch.object(
                service._runs,
                "get_active_run",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_company_check,
            patch.object(service._runs, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda run: run
            result = await service.initiate_run(data)

        mock_company_check.assert_called_once_with(company_id)
        assert result.target_type == "company"
        assert result.company_id == company_id

    @pytest.mark.asyncio
    async def test_get_runs_for_industry(self) -> None:
        service, _ = _make_service()
        industry_id = uuid.uuid4()
        runs = [_make_run(target_type="industry", industry_id=industry_id)]

        with patch.object(
            service._runs,
            "get_by_industry",
            new_callable=AsyncMock,
            return_value=runs,
        ):
            results = await service.get_runs_for_industry(industry_id)

        assert len(results) == 1


# ===========================================================================
# PART 6: Company Research backward compatibility
# ===========================================================================


class TestCompanyBackwardCompatibility:
    def test_existing_create_pattern_works(self) -> None:
        """Existing code passing company_id to ResearchRunCreate still works."""
        data = ResearchRunCreate(
            company_id=uuid.uuid4(),
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
            observation_date=date(2026, 9, 30),
        )
        assert data.target_type == "company"
        assert data.company_id is not None

    def test_existing_run_summary_pattern_works(self) -> None:
        """RunSummary with just company_id still works (backward compat)."""
        summary = RunSummary(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            status="COMPLETED",
            run_type="FULL",
            started_at=datetime.now(UTC),
            completed_at=None,
            observation_date=None,
            research_completeness=None,
            total_cost_usd=None,
        )
        assert summary.target_type == "company"

    @pytest.mark.asyncio
    async def test_company_initiate_run_unchanged(self) -> None:
        """initiate_run with company target works identically to Phase 8."""
        service, _ = _make_service()
        data = ResearchRunCreate(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )

        with (
            patch.object(
                service._runs,
                "get_active_run",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(service._runs, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda run: run
            result = await service.initiate_run(data)

        assert result.status == ResearchRunStatus.CREATED
        assert result.target_type == "company"

    @pytest.mark.asyncio
    async def test_company_concurrent_run_prevention_unchanged(self) -> None:
        """Company concurrent run prevention is unchanged."""
        service, _ = _make_service()
        existing = _make_run(status=ResearchRunStatus.RUNNING)
        data = ResearchRunCreate(
            company_id=existing.company_id,
            initiated_by="test",
            run_type="FULL",
            trigger_type="USER_INITIATED",
        )

        with (
            patch.object(
                service._runs,
                "get_active_run",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            pytest.raises(ValidationError, match="already active for this company"),
        ):
            await service.initiate_run(data)


# ===========================================================================
# PART 8: State machine compatibility — same lifecycle for both target types
# ===========================================================================


class TestStateMachineCompatibility:
    @pytest.mark.asyncio
    async def test_industry_run_lifecycle(self) -> None:
        """Industry runs follow the same CREATED→QUEUED→RUNNING→COMPLETED lifecycle."""
        from app.models.state_machines import validate_run_transition

        validate_run_transition(ResearchRunStatus.CREATED, ResearchRunStatus.QUEUED)
        validate_run_transition(ResearchRunStatus.QUEUED, ResearchRunStatus.RUNNING)
        validate_run_transition(ResearchRunStatus.RUNNING, ResearchRunStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_industry_run_can_be_partial(self) -> None:
        from app.models.state_machines import validate_run_transition

        validate_run_transition(ResearchRunStatus.RUNNING, ResearchRunStatus.PARTIAL)

    @pytest.mark.asyncio
    async def test_industry_run_can_fail(self) -> None:
        from app.models.state_machines import validate_run_transition

        validate_run_transition(ResearchRunStatus.RUNNING, ResearchRunStatus.FAILED)


# ===========================================================================
# PART 9: Temporal validation for industry runs
# ===========================================================================


class TestTemporalValidationIndustry:
    @pytest.mark.asyncio
    async def test_industry_finding_temporal_validation(self) -> None:
        """Temporal validation applies equally to industry runs."""
        service, _ = _make_service()
        run = _make_run(
            target_type="industry",
            observation_date=date(2026, 9, 30),
        )
        finding_data = ResearchFindingCreate(
            agent_name=INDUSTRY_AGENT_NAME,
            finding_type=FindingType.FACT,
            category="market_size",
            content="Market size is INR 50,000 Cr",
            confidence="HIGH",
            observation_date=date(2026, 10, 15),
        )

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            pytest.raises(ValidationError, match="cannot be after run observation_date"),
        ):
            await service.record_findings(run.id, None, [finding_data])

    @pytest.mark.asyncio
    async def test_industry_finding_valid_temporal(self) -> None:
        service, _ = _make_service()
        run = _make_run(
            target_type="industry",
            observation_date=date(2026, 9, 30),
        )
        finding_data = ResearchFindingCreate(
            agent_name=INDUSTRY_AGENT_NAME,
            finding_type=FindingType.AI_INFERENCE,
            category="entry_barriers",
            content="High capital requirements create significant barriers",
            confidence="MEDIUM",
            observation_date=date(2026, 9, 30),
            source_publication_date=date(2026, 8, 15),
        )

        def _simulate_batch(findings: list[ResearchFinding]) -> list[ResearchFinding]:
            for f in findings:
                if f.created_at is None:
                    f.created_at = datetime.now(UTC)
            return findings

        with (
            patch.object(service._runs, "get_by_id", new_callable=AsyncMock, return_value=run),
            patch.object(service._findings, "create_batch", new_callable=AsyncMock) as mock_batch,
        ):
            mock_batch.side_effect = _simulate_batch
            results = await service.record_findings(run.id, None, [finding_data])

        assert len(results) == 1
        assert results[0].agent_name == INDUSTRY_AGENT_NAME


# ===========================================================================
# PART 10: Findings/Evidence compatibility
# ===========================================================================


class TestFindingsCompatibility:
    def test_industry_finding_uses_existing_finding_type(self) -> None:
        """Industry findings use the same FindingType enum values."""
        finding = ResearchFindingCreate(
            agent_name=INDUSTRY_AGENT_NAME,
            finding_type=FindingType.AI_INFERENCE,
            category="competitive_rivalry",
            content="Industry is moderately concentrated",
            confidence="MEDIUM",
        )
        assert finding.finding_type == FindingType.AI_INFERENCE

    def test_industry_finding_all_types_valid(self) -> None:
        """All FindingType values work for industry findings."""
        for ft in FindingType:
            finding = ResearchFindingCreate(
                agent_name=INDUSTRY_AGENT_NAME,
                finding_type=ft,
                category="market_size",
                content="test content",
                confidence="HIGH",
            )
            assert finding.finding_type == ft

    def test_no_industry_finding_model_exists(self) -> None:
        """Verify no IndustryFinding model was created — reuse ResearchFinding."""
        import app.models.research as research_module

        assert not hasattr(research_module, "IndustryFinding")
