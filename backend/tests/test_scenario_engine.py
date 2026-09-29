"""Tests for the Scenario Engine (Bear/Base/Bull).

Verifies orchestration, validation, delegation, failure handling,
provenance, determinism, and golden-dataset outputs.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import pydantic
import pytest

from app.analytics.models import PeriodFinancials
from app.models.enums import FindingType
from app.valuation.models import (
    AssumptionProvenance,
    CashFlowBasis,
    DCFAssumptions,
    MultipleScenarioAssumption,
    ScenarioDefinition,
    ScenarioDiagnostic,
    ScenarioExecutionStatus,
    ScenarioLabel,
    TerminalMethod,
    ValuationMethodType,
)
from app.valuation.scenario import (
    ENGINE_VERSION,
    ScenarioEngineError,
    ScenarioExecutionError,
    ScenarioValidationError,
    run_scenarios,
)

D = Decimal

_TS = datetime(2026, 1, 1, tzinfo=UTC)
_PRICE = D("200")

_FY2024 = PeriodFinancials(
    period="FY2024",
    revenue=D("10000"),
    ebitda=D("2300"),
    ebit=D("2000"),
    pat=D("1500"),
    total_equity=D("8000"),
    total_debt=D("2000"),
    cash_and_equivalents=D("500"),
    current_assets=D("4000"),
    current_liabilities=D("2500"),
    total_assets=D("12000"),
    cfo=D("1800"),
    capex=D("500"),
    eps=D("15.00"),
    shares_outstanding=D("100"),
    effective_tax_rate=D("0.25"),
    depreciation_amortization=D("300"),
)

_FY2023 = PeriodFinancials(
    period="FY2023",
    revenue=D("9000"),
    ebitda=D("2000"),
    ebit=D("1800"),
    pat=D("1350"),
    total_equity=D("7000"),
    total_debt=D("2200"),
    cash_and_equivalents=D("400"),
    current_assets=D("3500"),
    current_liabilities=D("2200"),
    total_assets=D("11000"),
    cfo=D("1600"),
    capex=D("450"),
    eps=D("13.50"),
    shares_outstanding=D("100"),
    effective_tax_rate=D("0.25"),
    depreciation_amortization=D("200"),
)

_PROVENANCE = [
    AssumptionProvenance(
        parameter="revenue_growth_rates",
        value_description="test assumption",
        evidence_category=FindingType.ASSUMPTION,
        rationale="test",
    ),
]


_DEFAULT_GROWTH = D("0.10")
_DEFAULT_MARGIN = D("0.20")
_DEFAULT_WACC = D("0.10")
_DEFAULT_TERMINAL_GROWTH = D("0.03")
_BEAR_GROWTH = D("0.05")
_BEAR_MARGIN = D("0.15")
_BEAR_WACC = D("0.12")
_BULL_GROWTH = D("0.15")
_BULL_MARGIN = D("0.25")


def _assumptions(
    growth: Decimal = _DEFAULT_GROWTH,
    margin: Decimal = _DEFAULT_MARGIN,
    wacc: Decimal = _DEFAULT_WACC,
    terminal_growth: Decimal = _DEFAULT_TERMINAL_GROWTH,
) -> DCFAssumptions:
    return DCFAssumptions(
        projection_years=5,
        revenue_growth_rates=growth,
        ebit_margin=margin,
        da_pct_revenue=D("0.03"),
        tax_rate=D("0.25"),
        capex_pct_revenue=D("0.05"),
        nwc_pct_revenue_change=D("0.10"),
        terminal_method=TerminalMethod.GORDON_GROWTH,
        terminal_growth_rate=terminal_growth,
        wacc=wacc,
        shares_outstanding=D("100"),
        net_debt=D("1500"),
    )


def _bear_def(
    growth: Decimal = _BEAR_GROWTH,
    margin: Decimal = _BEAR_MARGIN,
    wacc: Decimal = _BEAR_WACC,
    **kw: object,
) -> ScenarioDefinition:
    return ScenarioDefinition(
        label=ScenarioLabel.BEAR,
        narrative="Bear case",
        dcf_assumptions=_assumptions(growth=growth, margin=margin, wacc=wacc),
        assumption_provenance=_PROVENANCE,
        **kw,  # type: ignore[arg-type]
    )


def _base_def(
    growth: Decimal = _DEFAULT_GROWTH,
    margin: Decimal = _DEFAULT_MARGIN,
    wacc: Decimal = _DEFAULT_WACC,
    **kw: object,
) -> ScenarioDefinition:
    return ScenarioDefinition(
        label=ScenarioLabel.BASE,
        narrative="Base case",
        dcf_assumptions=_assumptions(growth=growth, margin=margin, wacc=wacc),
        assumption_provenance=_PROVENANCE,
        **kw,  # type: ignore[arg-type]
    )


def _bull_def(
    growth: Decimal = _BULL_GROWTH,
    margin: Decimal = _BULL_MARGIN,
    wacc: Decimal = _DEFAULT_WACC,
    **kw: object,
) -> ScenarioDefinition:
    return ScenarioDefinition(
        label=ScenarioLabel.BULL,
        narrative="Bull case",
        dcf_assumptions=_assumptions(growth=growth, margin=margin, wacc=wacc),
        assumption_provenance=_PROVENANCE,
        **kw,  # type: ignore[arg-type]
    )


def _standard_scenarios() -> list[ScenarioDefinition]:
    return [_bear_def(), _base_def(), _bull_def()]


# ---------------------------------------------------------------------------
# Scenario Model Tests
# ---------------------------------------------------------------------------


class TestScenarioModels:
    def test_scenario_label_values(self) -> None:
        assert ScenarioLabel.BEAR == "bear"
        assert ScenarioLabel.BASE == "base"
        assert ScenarioLabel.BULL == "bull"

    def test_scenario_execution_status(self) -> None:
        assert ScenarioExecutionStatus.COMPLETED == "completed"
        assert ScenarioExecutionStatus.FAILED == "failed"

    def test_scenario_diagnostic_values(self) -> None:
        assert len(ScenarioDiagnostic) == 6

    def test_assumption_provenance_frozen(self) -> None:
        p = _PROVENANCE[0]
        with pytest.raises(pydantic.ValidationError):
            p.parameter = "x"  # type: ignore[misc]

    def test_multiple_scenario_assumption_positive(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="positive"):
            MultipleScenarioAssumption(
                method=ValuationMethodType.PE,
                target_multiple=D("-1"),
                target_name="test",
                rationale="test",
                evidence_category=FindingType.ASSUMPTION,
            )

    def test_scenario_definition_frozen(self) -> None:
        s = _bear_def()
        with pytest.raises(pydantic.ValidationError):
            s.label = ScenarioLabel.BULL  # type: ignore[misc]

    def test_scenario_definition_negative_weight(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="probability_weight"):
            _bear_def(probability_weight=D("-0.1"))

    def test_single_scenario_output_frozen(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        with pytest.raises(pydantic.ValidationError):
            result.scenarios[0].label = ScenarioLabel.BULL  # type: ignore[misc]

    def test_scenario_result_frozen(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        with pytest.raises(pydantic.ValidationError):
            result.engine_version = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


class TestExactlyThreeScenarios:
    def test_zero_scenarios(self) -> None:
        with pytest.raises(ScenarioValidationError, match="exactly 3"):
            run_scenarios([_FY2024], [], _PRICE, _TS)

    def test_one_scenario(self) -> None:
        with pytest.raises(ScenarioValidationError, match="exactly 3"):
            run_scenarios([_FY2024], [_bear_def()], _PRICE, _TS)

    def test_two_scenarios(self) -> None:
        with pytest.raises(ScenarioValidationError, match="exactly 3"):
            run_scenarios([_FY2024], [_bear_def(), _base_def()], _PRICE, _TS)

    def test_four_scenarios(self) -> None:
        with pytest.raises(ScenarioValidationError, match="exactly 3"):
            run_scenarios(
                [_FY2024],
                [_bear_def(), _base_def(), _bull_def(), _bear_def()],
                _PRICE, _TS,
            )


class TestDuplicateMissingLabels:
    def test_duplicate_bear(self) -> None:
        bear2 = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="Bear 2",
            dcf_assumptions=_assumptions(),
            assumption_provenance=_PROVENANCE,
        )
        with pytest.raises(ScenarioValidationError, match="duplicate"):
            run_scenarios([_FY2024], [_bear_def(), bear2, _bull_def()], _PRICE, _TS)

    def test_missing_bull(self) -> None:
        bear2 = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="Bear 2",
            dcf_assumptions=_assumptions(),
            assumption_provenance=_PROVENANCE,
        )
        with pytest.raises(ScenarioValidationError):
            run_scenarios([_FY2024], [_bear_def(), _base_def(), bear2], _PRICE, _TS)


class TestInputValidation:
    def test_empty_financials(self) -> None:
        with pytest.raises(ScenarioValidationError, match="financials"):
            run_scenarios([], _standard_scenarios(), _PRICE, _TS)

    def test_zero_price(self) -> None:
        with pytest.raises(ScenarioValidationError, match="current_price"):
            run_scenarios([_FY2024], _standard_scenarios(), D("0"), _TS)

    def test_negative_price(self) -> None:
        with pytest.raises(ScenarioValidationError, match="current_price"):
            run_scenarios([_FY2024], _standard_scenarios(), D("-100"), _TS)


class TestProbabilityWeights:
    def test_valid_weights(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(probability_weight=D("0.50")),
            _bull_def(probability_weight=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.comparison.probability_weighted_value is not None

    def test_partial_weights_rejected(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(),
            _bull_def(probability_weight=D("0.25")),
        ]
        with pytest.raises(ScenarioValidationError, match="probability_weight"):
            run_scenarios([_FY2024], scenarios, _PRICE, _TS)

    def test_weights_not_sum_to_one(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.30")),
            _base_def(probability_weight=D("0.50")),
            _bull_def(probability_weight=D("0.30")),
        ]
        with pytest.raises(ScenarioValidationError, match="sum"):
            run_scenarios([_FY2024], scenarios, _PRICE, _TS)

    def test_no_weights_no_pwv(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.probability_weighted_value is None

    def test_no_default_probabilities(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert s.probability_weight is None

    def test_pwv_calculation(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(probability_weight=D("0.50")),
            _bull_def(probability_weight=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        bear_iv = result.comparison.bear_implied_value
        base_iv = result.comparison.base_implied_value
        bull_iv = result.comparison.bull_implied_value
        assert bear_iv is not None and base_iv is not None and bull_iv is not None
        expected = (
            D("0.25") * bear_iv + D("0.50") * base_iv + D("0.25") * bull_iv
        ).quantize(D("0.0001"))
        assert result.comparison.probability_weighted_value == expected


# ---------------------------------------------------------------------------
# DCF Delegation Tests
# ---------------------------------------------------------------------------


class TestDCFDelegation:
    def test_basic_execution(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert len(result.scenarios) == 3
        for s in result.scenarios:
            assert s.execution_status == ScenarioExecutionStatus.COMPLETED
            assert s.dcf_result is not None
            assert s.implied_value_per_share is not None

    def test_bear_base_bull_order(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.scenarios[0].label == ScenarioLabel.BEAR
        assert result.scenarios[1].label == ScenarioLabel.BASE
        assert result.scenarios[2].label == ScenarioLabel.BULL

    def test_dcf_result_matches_direct_call(self) -> None:
        from app.valuation.dcf import dcf_valuation

        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        base_output = result.scenarios[1]
        direct = dcf_valuation(
            [_FY2024], _assumptions(), _PRICE, calculated_at=_TS,
        )
        assert base_output.dcf_result is not None
        assert base_output.dcf_result.implied_value_per_share == direct.implied_value_per_share
        assert base_output.dcf_result.enterprise_value == direct.enterprise_value

    def test_scenarios_not_reordered(self) -> None:
        scenarios = [_bull_def(), _bear_def(), _base_def()]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.scenarios[0].label == ScenarioLabel.BEAR
        assert result.scenarios[1].label == ScenarioLabel.BASE
        assert result.scenarios[2].label == ScenarioLabel.BULL

    def test_calculated_at_propagated(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.calculated_at == _TS
        for s in result.scenarios:
            if s.dcf_result is not None:
                assert s.dcf_result.calculated_at == _TS

    def test_engine_version(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.engine_version == ENGINE_VERSION


# ---------------------------------------------------------------------------
# Multiple Delegation Tests
# ---------------------------------------------------------------------------


class TestMultipleDelegation:
    def test_pe_multiple(self) -> None:
        from app.valuation.multiples import pe_valuation

        pe_assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.PE,
            target_multiple=D("18"),
            target_name="Base PE",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(),
            _base_def(multiple_assumptions=[pe_assumption]),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        base = result.scenarios[1]
        assert len(base.multiple_results) == 1
        mr = base.multiple_results[0]
        assert mr.method == ValuationMethodType.PE
        direct = pe_valuation(_FY2024, D("18"), _PRICE, calculated_at=_TS)
        assert mr.implied_value_per_share == direct.implied_value_per_share

    def test_ev_ebitda_multiple(self) -> None:
        assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.EV_EBITDA,
            target_multiple=D("10"),
            target_name="Bear EV/EBITDA",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[assumption]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert len(result.scenarios[0].multiple_results) == 1
        assert result.scenarios[0].multiple_results[0].method == ValuationMethodType.EV_EBITDA

    def test_no_multiples_by_default(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert s.multiple_results == []

    def test_multiple_calculated_at(self) -> None:
        pe_assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.PE,
            target_multiple=D("15"),
            target_name="test",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[pe_assumption]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        mr = result.scenarios[0].multiple_results[0]
        assert mr.calculated_at == _TS

    def test_failed_multiple_does_not_fail_scenario(self) -> None:
        bad_assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.PEG,
            target_multiple=D("1.5"),
            target_name="PEG",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[bad_assumption]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.scenarios[0].execution_status == ScenarioExecutionStatus.COMPLETED
        assert result.scenarios[0].multiple_results == []

    def test_ev_fcf_uses_two_periods(self) -> None:
        assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.EV_FCF,
            target_multiple=D("15"),
            target_name="EV/FCF",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[assumption]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2023, _FY2024], scenarios, _PRICE, _TS)
        assert len(result.scenarios[0].multiple_results) == 1
        mr = result.scenarios[0].multiple_results[0]
        assert mr.cash_flow_basis == CashFlowBasis.FCFF


# ---------------------------------------------------------------------------
# Scenario Execution Failure
# ---------------------------------------------------------------------------


class TestScenarioFailure:
    def test_one_scenario_fails(self) -> None:
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL,
            narrative="Bull with bad WACC",
            dcf_assumptions=_assumptions(
                wacc=D("0.02"), terminal_growth=D("0.03"),
            ),
            assumption_provenance=_PROVENANCE,
        )
        scenarios = [_bear_def(), _base_def(), bad_bull]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.scenarios[2].execution_status == ScenarioExecutionStatus.FAILED
        assert result.scenarios[2].dcf_result is None
        assert result.scenarios[2].implied_value_per_share is None
        assert result.scenarios[2].error_message is not None
        assert result.scenarios[0].execution_status == ScenarioExecutionStatus.COMPLETED
        assert result.scenarios[1].execution_status == ScenarioExecutionStatus.COMPLETED

    def test_all_scenarios_fail(self) -> None:
        bad = _assumptions(wacc=D("0.02"), terminal_growth=D("0.03"))
        scenarios = [
            ScenarioDefinition(
                label=ScenarioLabel.BEAR, narrative="bad",
                dcf_assumptions=bad, assumption_provenance=_PROVENANCE,
            ),
            ScenarioDefinition(
                label=ScenarioLabel.BASE, narrative="bad",
                dcf_assumptions=bad, assumption_provenance=_PROVENANCE,
            ),
            ScenarioDefinition(
                label=ScenarioLabel.BULL, narrative="bad",
                dcf_assumptions=bad, assumption_provenance=_PROVENANCE,
            ),
        ]
        with pytest.raises(ScenarioExecutionError, match="all three"):
            run_scenarios([_FY2024], scenarios, _PRICE, _TS)

    def test_failed_scenario_no_fabrication(self) -> None:
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="bad bear",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        scenarios = [bad_bear, _base_def(), _bull_def()]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        bear = result.scenarios[0]
        assert bear.dcf_result is None
        assert bear.implied_value_per_share is None

    def test_failed_scenario_preserves_label(self) -> None:
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="bad bear",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        scenarios = [bad_bear, _base_def(), _bull_def()]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.scenarios[0].label == ScenarioLabel.BEAR

    def test_bear_fails_base_bull_succeed(self) -> None:
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [bad_bear, _base_def(), _bull_def()], _PRICE, _TS)
        assert result.scenarios[0].execution_status == ScenarioExecutionStatus.FAILED
        assert result.scenarios[1].execution_status == ScenarioExecutionStatus.COMPLETED
        assert result.scenarios[2].execution_status == ScenarioExecutionStatus.COMPLETED

    def test_base_fails_bear_bull_succeed(self) -> None:
        bad_base = ScenarioDefinition(
            label=ScenarioLabel.BASE,
            narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [_bear_def(), bad_base, _bull_def()], _PRICE, _TS)
        assert result.scenarios[1].execution_status == ScenarioExecutionStatus.FAILED
        assert result.scenarios[0].execution_status == ScenarioExecutionStatus.COMPLETED
        assert result.scenarios[2].execution_status == ScenarioExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Scenario Comparison
# ---------------------------------------------------------------------------


class TestScenarioComparison:
    def test_value_range(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        c = result.comparison
        assert c.value_range_low is not None
        assert c.value_range_high is not None
        assert c.value_range_low <= c.value_range_high

    def test_midpoint(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        c = result.comparison
        assert c.value_range_midpoint is not None
        assert c.value_range_low is not None
        assert c.value_range_high is not None
        expected = (c.value_range_low + c.value_range_high) / D("2")
        assert c.value_range_midpoint == expected.quantize(D("0.0001"))

    def test_completed_count(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.completed_scenario_count == 3

    def test_completed_count_with_failure(self) -> None:
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL,
            narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [_bear_def(), _base_def(), bad_bull], _PRICE, _TS)
        assert result.comparison.completed_scenario_count == 2

    def test_individual_implied_values(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        c = result.comparison
        assert c.bear_implied_value is not None
        assert c.base_implied_value is not None
        assert c.bull_implied_value is not None

    def test_failed_scenario_implied_none(self) -> None:
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [bad_bear, _base_def(), _bull_def()], _PRICE, _TS)
        assert result.comparison.bear_implied_value is None
        assert result.comparison.base_implied_value is not None
        assert result.comparison.bull_implied_value is not None

    def test_upside_downside(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        c = result.comparison
        assert c.upside_to_bear is not None
        assert c.upside_to_base is not None
        assert c.upside_to_bull is not None
        assert c.bear_implied_value is not None
        expected = (c.bear_implied_value - _PRICE) / _PRICE
        assert c.upside_to_bear == expected.quantize(D("0.000001"))

    def test_upside_none_when_failed(self) -> None:
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR,
            narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [bad_bear, _base_def(), _bull_def()], _PRICE, _TS)
        assert result.comparison.upside_to_bear is None

    def test_range_none_with_one_completed(self) -> None:
        bad = _assumptions(wacc=D("0.02"), terminal_growth=D("0.03"))
        bad_bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR, narrative="bad",
            dcf_assumptions=bad, assumption_provenance=_PROVENANCE,
        )
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL, narrative="bad",
            dcf_assumptions=bad, assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [bad_bear, _base_def(), bad_bull], _PRICE, _TS)
        assert result.comparison.completed_scenario_count == 1
        assert result.comparison.value_range_low is None
        assert result.comparison.value_range_high is None
        assert result.comparison.value_range_midpoint is None

    def test_no_recommendation_fields(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert not hasattr(result.comparison, "recommendation")
        assert not hasattr(result.comparison, "score")
        assert not hasattr(result.comparison, "buy")
        assert not hasattr(result.comparison, "sell")

    def test_pwv_none_when_scenario_failed(self) -> None:
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL, narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
            probability_weight=D("0.25"),
        )
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(probability_weight=D("0.50")),
            bad_bull,
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert result.comparison.probability_weighted_value is None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_value_order_unexpected(self) -> None:
        scenarios = [
            _bear_def(growth=D("0.15"), margin=D("0.25"), wacc=D("0.08")),
            _base_def(growth=D("0.05"), margin=D("0.15")),
            _bull_def(growth=D("0.12"), margin=D("0.22")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED in result.diagnostics

    def test_identical_assumptions(self) -> None:
        same = _assumptions()
        scenarios = [
            ScenarioDefinition(
                label=ScenarioLabel.BEAR, narrative="same",
                dcf_assumptions=same, assumption_provenance=_PROVENANCE,
            ),
            ScenarioDefinition(
                label=ScenarioLabel.BASE, narrative="same",
                dcf_assumptions=same, assumption_provenance=_PROVENANCE,
            ),
            ScenarioDefinition(
                label=ScenarioLabel.BULL, narrative="same",
                dcf_assumptions=same, assumption_provenance=_PROVENANCE,
            ),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert ScenarioDiagnostic.IDENTICAL_ASSUMPTIONS in result.diagnostics

    def test_no_spurious_diagnostics(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert ScenarioDiagnostic.IDENTICAL_ASSUMPTIONS not in result.diagnostics
        assert ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED not in result.diagnostics

    def test_scenario_execution_failed_diagnostic(self) -> None:
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL, narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [_bear_def(), _base_def(), bad_bull], _PRICE, _TS)
        assert ScenarioDiagnostic.SCENARIO_EXECUTION_FAILED in result.scenarios[2].diagnostics

    def test_incomplete_comparison_diagnostic(self) -> None:
        bad_bull = ScenarioDefinition(
            label=ScenarioLabel.BULL, narrative="bad",
            dcf_assumptions=_assumptions(wacc=D("0.02"), terminal_growth=D("0.03")),
            assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [_bear_def(), _base_def(), bad_bull], _PRICE, _TS)
        assert ScenarioDiagnostic.INCOMPLETE_COMPARISON in result.diagnostics


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_provenance_preserved(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert len(s.assumption_provenance) > 0
            assert s.assumption_provenance[0].parameter == "revenue_growth_rates"

    def test_finding_type_preserved(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert s.assumption_provenance[0].evidence_category == FindingType.ASSUMPTION


# ---------------------------------------------------------------------------
# CalculationResult Audit Trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_scenario_level_calculations(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        metrics = [c.metric for c in result.calculations]
        assert "scenario_value_range" in metrics
        assert any(m.startswith("upside_to_") for m in metrics)

    def test_dcf_calculations_present(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert s.dcf_result is not None
            assert len(s.dcf_result.calculations) > 0

    def test_pwv_audit_when_weighted(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(probability_weight=D("0.50")),
            _bull_def(probability_weight=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        metrics = [c.metric for c in result.calculations]
        assert "probability_weighted_value" in metrics


# ---------------------------------------------------------------------------
# Decimal & Determinism
# ---------------------------------------------------------------------------


class TestDecimalArithmetic:
    def test_no_float_in_result(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        c = result.comparison
        for field in [c.value_range_low, c.value_range_high, c.value_range_midpoint,
                      c.bear_implied_value, c.base_implied_value, c.bull_implied_value,
                      c.upside_to_bear, c.upside_to_base, c.upside_to_bull]:
            if field is not None:
                assert isinstance(field, Decimal)


class TestDeterminism:
    def test_same_inputs_same_outputs(self) -> None:
        r1 = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        r2 = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert r1.comparison.bear_implied_value == r2.comparison.bear_implied_value
        assert r1.comparison.base_implied_value == r2.comparison.base_implied_value
        assert r1.comparison.bull_implied_value == r2.comparison.bull_implied_value
        assert r1.comparison.value_range_midpoint == r2.comparison.value_range_midpoint
        assert r1.calculated_at == r2.calculated_at

    def test_different_calculated_at_different_result(self) -> None:
        ts2 = datetime(2026, 6, 1, tzinfo=UTC)
        r1 = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        r2 = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, ts2)
        assert r1.calculated_at != r2.calculated_at
        assert r1.comparison.bear_implied_value == r2.comparison.bear_implied_value


# ---------------------------------------------------------------------------
# DCF calculated_at Propagation
# ---------------------------------------------------------------------------


class TestDCFCalculatedAt:
    def test_dcf_respects_calculated_at(self) -> None:
        from app.valuation.dcf import dcf_valuation

        ts1 = datetime(2026, 1, 1, tzinfo=UTC)
        ts2 = datetime(2026, 6, 15, tzinfo=UTC)
        r1 = dcf_valuation([_FY2024], _assumptions(), _PRICE, calculated_at=ts1)
        r2 = dcf_valuation([_FY2024], _assumptions(), _PRICE, calculated_at=ts2)
        assert r1.calculated_at == ts1
        assert r2.calculated_at == ts2
        assert r1.implied_value_per_share == r2.implied_value_per_share

    def test_dcf_none_calculated_at_uses_now(self) -> None:
        from app.valuation.dcf import dcf_valuation

        r = dcf_valuation([_FY2024], _assumptions(), _PRICE)
        assert r.calculated_at is not None


# ---------------------------------------------------------------------------
# Multiple calculated_at Propagation
# ---------------------------------------------------------------------------


class TestMultipleCalculatedAt:
    def test_pe_respects_calculated_at(self) -> None:
        from app.valuation.multiples import pe_valuation

        ts = datetime(2026, 3, 1, tzinfo=UTC)
        r = pe_valuation(_FY2024, D("15"), _PRICE, calculated_at=ts)
        assert r.calculated_at == ts

    def test_ev_ebitda_respects_calculated_at(self) -> None:
        from app.valuation.multiples import ev_ebitda_valuation

        ts = datetime(2026, 3, 1, tzinfo=UTC)
        r = ev_ebitda_valuation(_FY2024, D("10"), _PRICE, calculated_at=ts)
        assert r.calculated_at == ts


# ---------------------------------------------------------------------------
# Sensitivity Boundary
# ---------------------------------------------------------------------------


class TestSensitivityBoundary:
    def test_no_merged_sensitivity(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert not hasattr(result, "merged_sensitivity")

    def test_dcf_sensitivities_preserved(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        for s in result.scenarios:
            assert s.dcf_result is not None
            assert len(s.dcf_result.sensitivity) > 0


# ---------------------------------------------------------------------------
# Boundary Tests — No Historical/Peer/Reverse invocation
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_result_has_no_historical_band_data(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert not hasattr(result, "historical_bands")

    def test_result_has_no_peer_data(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert not hasattr(result, "peer_comparison")

    def test_result_has_no_reverse_dcf(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert not hasattr(result, "reverse_dcf")


# ---------------------------------------------------------------------------
# Value Ordering — Diagnostic Only
# ---------------------------------------------------------------------------


class TestValueOrdering:
    def test_normal_ordering_no_diagnostic(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED not in result.diagnostics

    def test_bear_greater_than_base_diagnostic(self) -> None:
        scenarios = [
            _bear_def(growth=D("0.20"), margin=D("0.30"), wacc=D("0.08")),
            _base_def(growth=D("0.05"), margin=D("0.12")),
            _bull_def(growth=D("0.15"), margin=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED in result.diagnostics
        bear_iv = result.comparison.bear_implied_value
        base_iv = result.comparison.base_implied_value
        assert bear_iv is not None and base_iv is not None
        assert bear_iv > base_iv

    def test_unusual_ordering_not_rejected(self) -> None:
        scenarios = [
            _bear_def(growth=D("0.20"), margin=D("0.30"), wacc=D("0.08")),
            _base_def(growth=D("0.05"), margin=D("0.12")),
            _bull_def(growth=D("0.15"), margin=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        assert len(result.scenarios) == 3
        for s in result.scenarios:
            assert s.execution_status == ScenarioExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# FCFF / Equity FCF Consistency
# ---------------------------------------------------------------------------


class TestFCFFConsistency:
    def test_fcf_yield_equity_basis(self) -> None:
        assumption = MultipleScenarioAssumption(
            method=ValuationMethodType.FCF_YIELD,
            target_multiple=D("0.05"),
            target_name="FCF Yield",
            rationale="test",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[assumption]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        mr = result.scenarios[0].multiple_results[0]
        assert mr.cash_flow_basis == CashFlowBasis.EQUITY_FCF


# ---------------------------------------------------------------------------
# Projection Validation
# ---------------------------------------------------------------------------


class TestProjectionValidation:
    def test_per_year_assumptions(self) -> None:
        bear_a = DCFAssumptions(
            projection_years=3,
            revenue_growth_rates=[D("0.03"), D("0.02"), D("0.01")],
            ebit_margin=[D("0.12"), D("0.11"), D("0.10")],
            da_pct_revenue=D("0.03"),
            tax_rate=D("0.25"),
            capex_pct_revenue=D("0.05"),
            nwc_pct_revenue_change=D("0.10"),
            terminal_method=TerminalMethod.GORDON_GROWTH,
            terminal_growth_rate=D("0.02"),
            wacc=D("0.12"),
            shares_outstanding=D("100"),
            net_debt=D("1500"),
        )
        bear = ScenarioDefinition(
            label=ScenarioLabel.BEAR, narrative="Declining",
            dcf_assumptions=bear_a, assumption_provenance=_PROVENANCE,
        )
        base_a = DCFAssumptions(
            projection_years=3,
            revenue_growth_rates=D("0.08"),
            ebit_margin=D("0.18"),
            da_pct_revenue=D("0.03"),
            tax_rate=D("0.25"),
            capex_pct_revenue=D("0.05"),
            nwc_pct_revenue_change=D("0.10"),
            terminal_method=TerminalMethod.GORDON_GROWTH,
            terminal_growth_rate=D("0.03"),
            wacc=D("0.10"),
            shares_outstanding=D("100"),
            net_debt=D("1500"),
        )
        base = ScenarioDefinition(
            label=ScenarioLabel.BASE, narrative="Stable",
            dcf_assumptions=base_a, assumption_provenance=_PROVENANCE,
        )
        bull_a = DCFAssumptions(
            projection_years=3,
            revenue_growth_rates=[D("0.12"), D("0.15"), D("0.18")],
            ebit_margin=[D("0.20"), D("0.22"), D("0.25")],
            da_pct_revenue=D("0.03"),
            tax_rate=D("0.25"),
            capex_pct_revenue=D("0.05"),
            nwc_pct_revenue_change=D("0.10"),
            terminal_method=TerminalMethod.GORDON_GROWTH,
            terminal_growth_rate=D("0.04"),
            wacc=D("0.10"),
            shares_outstanding=D("100"),
            net_debt=D("1500"),
        )
        bull = ScenarioDefinition(
            label=ScenarioLabel.BULL, narrative="Accelerating",
            dcf_assumptions=bull_a, assumption_provenance=_PROVENANCE,
        )
        result = run_scenarios([_FY2024], [bear, base, bull], _PRICE, _TS)
        assert result.scenarios[0].dcf_result is not None
        assert len(result.scenarios[0].dcf_result.projected_years) == 3

    def test_mismatched_list_length_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="list length"):
            DCFAssumptions(
                projection_years=5,
                revenue_growth_rates=[D("0.05"), D("0.04"), D("0.03")],
                ebit_margin=D("0.15"),
                da_pct_revenue=D("0.03"),
                tax_rate=D("0.25"),
                capex_pct_revenue=D("0.05"),
                nwc_pct_revenue_change=D("0.10"),
                terminal_method=TerminalMethod.GORDON_GROWTH,
                terminal_growth_rate=D("0.03"),
                wacc=D("0.10"),
                shares_outstanding=D("100"),
                net_debt=D("1500"),
            )


# ---------------------------------------------------------------------------
# Error Hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_validation_is_engine_error(self) -> None:
        assert issubclass(ScenarioValidationError, ScenarioEngineError)

    def test_execution_is_engine_error(self) -> None:
        assert issubclass(ScenarioExecutionError, ScenarioEngineError)


# ---------------------------------------------------------------------------
# Golden Dataset — Company A (Stable Compounder)
# ---------------------------------------------------------------------------


class TestGoldenCompanyA:
    """Hand-verified Bear/Base/Bull scenario for synthetic Company A.

    Financials: FY2024 revenue=10000, EPS=15.00, shares=100, net_debt=1500
    Bear: 5% growth, 15% margin, 12% WACC → implied 94.0153
    Base: 10% growth, 20% margin, 10% WACC → implied 223.3635
    Bull: 15% growth, 25% margin, 10% WACC → implied 357.2581
    """

    def test_bear_implied_value(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.bear_implied_value == D("94.0153")

    def test_base_implied_value(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.base_implied_value == D("223.3635")

    def test_bull_implied_value(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.bull_implied_value == D("357.2581")

    def test_value_range(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        assert result.comparison.value_range_low == D("94.0153")
        assert result.comparison.value_range_high == D("357.2581")

    def test_upside_to_bear(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        expected = (D("94.0153") - D("200")) / D("200")
        assert result.comparison.upside_to_bear == expected.quantize(
            D("0.000001"), rounding=ROUND_HALF_UP,
        )

    def test_upside_to_base(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        expected = (D("223.3635") - D("200")) / D("200")
        assert result.comparison.upside_to_base == expected.quantize(
            D("0.000001"), rounding=ROUND_HALF_UP,
        )

    def test_upside_to_bull(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        expected = (D("357.2581") - D("200")) / D("200")
        assert result.comparison.upside_to_bull == expected.quantize(
            D("0.000001"), rounding=ROUND_HALF_UP,
        )

    def test_midpoint(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        expected = (D("94.0153") + D("357.2581")) / D("2")
        assert result.comparison.value_range_midpoint == expected.quantize(D("0.0001"))

    def test_probability_weighted(self) -> None:
        scenarios = [
            _bear_def(probability_weight=D("0.25")),
            _base_def(probability_weight=D("0.50")),
            _bull_def(probability_weight=D("0.25")),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        expected = (
            D("0.25") * D("94.0153")
            + D("0.50") * D("223.3635")
            + D("0.25") * D("357.2581")
        ).quantize(D("0.0001"))
        assert result.comparison.probability_weighted_value == expected


# ---------------------------------------------------------------------------
# Golden Dataset — Company B (with PE multiples)
# ---------------------------------------------------------------------------


class TestGoldenCompanyB:
    """Same Company A but with PE multiple scenarios.

    Bear PE 12x: 15 * 12 = 180.0000
    Base PE 18x: 15 * 18 = 270.0000
    Bull PE 25x: 15 * 25 = 375.0000
    """

    def test_pe_bear(self) -> None:
        pe_bear = MultipleScenarioAssumption(
            method=ValuationMethodType.PE, target_multiple=D("12"),
            target_name="Bear PE", rationale="sector trough",
            evidence_category=FindingType.ASSUMPTION,
        )
        scenarios = [
            _bear_def(multiple_assumptions=[pe_bear]),
            _base_def(),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        mr = result.scenarios[0].multiple_results[0]
        assert mr.implied_value_per_share == D("180.0000")

    def test_pe_base(self) -> None:
        pe_base = MultipleScenarioAssumption(
            method=ValuationMethodType.PE, target_multiple=D("18"),
            target_name="Base PE", rationale="historical mean",
            evidence_category=FindingType.FACT,
        )
        scenarios = [
            _bear_def(),
            _base_def(multiple_assumptions=[pe_base]),
            _bull_def(),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        mr = result.scenarios[1].multiple_results[0]
        assert mr.implied_value_per_share == D("270.0000")

    def test_pe_bull(self) -> None:
        pe_bull = MultipleScenarioAssumption(
            method=ValuationMethodType.PE, target_multiple=D("25"),
            target_name="Bull PE", rationale="re-rating",
            evidence_category=FindingType.AI_INFERENCE,
        )
        scenarios = [
            _bear_def(),
            _base_def(),
            _bull_def(multiple_assumptions=[pe_bull]),
        ]
        result = run_scenarios([_FY2024], scenarios, _PRICE, _TS)
        mr = result.scenarios[2].multiple_results[0]
        assert mr.implied_value_per_share == D("375.0000")


# ---------------------------------------------------------------------------
# Reverse DCF Regression
# ---------------------------------------------------------------------------


class TestReverseDCFRegression:
    def test_reverse_dcf_still_works(self) -> None:
        from app.valuation.reverse_dcf import reverse_dcf

        r = reverse_dcf([_FY2024], _assumptions(), D("223"))
        assert r.convergence_status.value in {"converged", "max_iterations"}
        assert r.dcf_result is not None


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_scenario_result_frozen(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        with pytest.raises(pydantic.ValidationError):
            result.engine_version = "x"  # type: ignore[misc]

    def test_comparison_frozen(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        with pytest.raises(pydantic.ValidationError):
            result.comparison.current_price = D("999")  # type: ignore[misc]

    def test_single_output_frozen(self) -> None:
        result = run_scenarios([_FY2024], _standard_scenarios(), _PRICE, _TS)
        with pytest.raises(pydantic.ValidationError):
            result.scenarios[0].label = ScenarioLabel.BULL  # type: ignore[misc]
