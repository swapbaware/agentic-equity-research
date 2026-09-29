"""Tests for Reverse DCF — implied revenue growth from market price.

Covers golden-dataset round-trip, convergence, no-solution cases,
boundary conditions, Decimal enforcement, and audit trail.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.analytics.models import PeriodFinancials
from app.valuation.dcf import dcf_valuation
from app.valuation.models import (
    ConvergenceStatus,
    DCFAssumptions,
    ReverseDCFResult,
    TerminalMethod,
)
from app.valuation.reverse_dcf import ReverseDCFError, reverse_dcf

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FY2024 = PeriodFinancials(
    period="FY2024",
    revenue=Decimal("10000"),
    ebitda=Decimal("2300"),
    ebit=Decimal("2000"),
    pat=Decimal("1500"),
    total_equity=Decimal("8000"),
    total_debt=Decimal("2000"),
    cash_and_equivalents=Decimal("500"),
    current_assets=Decimal("4000"),
    current_liabilities=Decimal("2500"),
    total_assets=Decimal("12000"),
    cfo=Decimal("1800"),
    capex=Decimal("500"),
    eps=Decimal("15.00"),
    shares_outstanding=Decimal("100"),
    effective_tax_rate=Decimal("0.25"),
)


def _base_assumptions(**overrides: object) -> DCFAssumptions:
    defaults: dict[str, object] = {
        "projection_years": 5,
        "revenue_growth_rates": Decimal("0.10"),
        "ebit_margin": Decimal("0.20"),
        "da_pct_revenue": Decimal("0.03"),
        "tax_rate": Decimal("0.25"),
        "capex_pct_revenue": Decimal("0.05"),
        "nwc_pct_revenue_change": Decimal("0.10"),
        "terminal_method": TerminalMethod.GORDON_GROWTH,
        "terminal_growth_rate": Decimal("0.03"),
        "wacc": Decimal("0.10"),
        "shares_outstanding": Decimal("100"),
        "net_debt": Decimal("1500"),
    }
    defaults.update(overrides)
    return DCFAssumptions(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Golden dataset forward → reverse round-trip
# ---------------------------------------------------------------------------


class TestGoldenRoundTrip:
    """Forward DCF at 10% growth → implied=223.3635 → reverse → growth≈10%."""

    def test_round_trip_growth_10pct(self) -> None:
        assumptions = _base_assumptions()
        fwd = dcf_valuation([_FY2024], assumptions, Decimal("150"))
        assert fwd.implied_value_per_share == Decimal("223.3635")

        result = reverse_dcf([_FY2024], assumptions, fwd.implied_value_per_share)

        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0.10")) <= Decimal("0.0001")
        assert abs(result.residual) <= Decimal("0.01")

    def test_round_trip_growth_0pct(self) -> None:
        assumptions = _base_assumptions(revenue_growth_rates=Decimal("0"))
        fwd = dcf_valuation([_FY2024], assumptions, Decimal("150"))

        result = reverse_dcf([_FY2024], assumptions, fwd.implied_value_per_share)

        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0")) <= Decimal("0.0001")

    def test_round_trip_growth_5pct(self) -> None:
        assumptions = _base_assumptions(revenue_growth_rates=Decimal("0.05"))
        fwd = dcf_valuation([_FY2024], assumptions, Decimal("150"))

        result = reverse_dcf([_FY2024], assumptions, fwd.implied_value_per_share)

        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0.05")) <= Decimal("0.0001")


# ---------------------------------------------------------------------------
# 2. Convergence status and dual-condition check
# ---------------------------------------------------------------------------


class TestConvergence:
    def test_converged_status(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED

    def test_both_tolerances_satisfied(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.residual) <= result.price_tolerance

    def test_iterations_reasonable(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.iterations <= 20

    def test_max_iterations_not_converged(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
            max_iterations=1,
        )
        assert result.convergence_status == ConvergenceStatus.MAX_ITERATIONS
        assert result.iterations == 1

    def test_max_iterations_2_not_converged(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
            max_iterations=2,
        )
        assert result.convergence_status == ConvergenceStatus.MAX_ITERATIONS
        assert result.iterations == 2


# ---------------------------------------------------------------------------
# 3. No-solution cases
# ---------------------------------------------------------------------------


class TestNoSolution:
    def test_no_solution_below(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("5.00"),
        )
        assert result.convergence_status == ConvergenceStatus.NO_SOLUTION_BELOW
        assert result.iterations == 0

    def test_no_solution_above(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("100000.00"),
        )
        assert result.convergence_status == ConvergenceStatus.NO_SOLUTION_ABOVE
        assert result.iterations == 0

    def test_no_solution_returns_structured_result(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("5.00"),
        )
        assert isinstance(result, ReverseDCFResult)
        assert result.implied_growth_rate is not None
        assert result.dcf_result is not None
        assert len(result.calculations) > 0

    def test_no_solution_above_returns_structured_result(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("100000.00"),
        )
        assert isinstance(result, ReverseDCFResult)
        assert result.dcf_result is not None
        notes = [c.notes for c in result.calculations if c.notes]
        assert any("above" in n for n in notes)


# ---------------------------------------------------------------------------
# 4. Boundary targets
# ---------------------------------------------------------------------------


class TestBoundaryTargets:
    def test_target_at_lower_bound_value(self) -> None:
        lo_fwd = dcf_valuation(
            [_FY2024],
            _base_assumptions(revenue_growth_rates=Decimal("-0.50")),
            Decimal("150"),
        )
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), lo_fwd.implied_value_per_share,
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("-0.50")) <= Decimal("0.001")

    def test_target_at_upper_bound_value(self) -> None:
        hi_fwd = dcf_valuation(
            [_FY2024],
            _base_assumptions(revenue_growth_rates=Decimal("1.00")),
            Decimal("150"),
        )
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), hi_fwd.implied_value_per_share,
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("1.00")) <= Decimal("0.001")

    def test_near_lower_bound(self) -> None:
        lo_fwd = dcf_valuation(
            [_FY2024],
            _base_assumptions(revenue_growth_rates=Decimal("-0.45")),
            Decimal("150"),
        )
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), lo_fwd.implied_value_per_share,
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("-0.45")) <= Decimal("0.001")

    def test_near_upper_bound(self) -> None:
        hi_fwd = dcf_valuation(
            [_FY2024],
            _base_assumptions(revenue_growth_rates=Decimal("0.95")),
            Decimal("150"),
        )
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), hi_fwd.implied_value_per_share,
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0.95")) <= Decimal("0.001")


# ---------------------------------------------------------------------------
# 5. Custom search bounds
# ---------------------------------------------------------------------------


class TestCustomBounds:
    def test_narrower_bounds(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
            lower_bound=Decimal("0.00"),
            upper_bound=Decimal("0.30"),
        )
        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0.10")) <= Decimal("0.0001")

    def test_custom_bounds_target_outside(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
            lower_bound=Decimal("0.20"),
            upper_bound=Decimal("0.50"),
        )
        assert result.convergence_status == ConvergenceStatus.NO_SOLUTION_BELOW


# ---------------------------------------------------------------------------
# 6. Exit Multiple terminal method
# ---------------------------------------------------------------------------


class TestExitMultiple:
    def test_exit_multiple_round_trip(self) -> None:
        assumptions = _base_assumptions(
            terminal_method=TerminalMethod.EXIT_MULTIPLE,
            exit_multiple=Decimal("12"),
            revenue_growth_rates=Decimal("0.10"),
        )
        fwd = dcf_valuation([_FY2024], assumptions, Decimal("150"))

        result = reverse_dcf([_FY2024], assumptions, fwd.implied_value_per_share)

        assert result.convergence_status == ConvergenceStatus.CONVERGED
        assert abs(result.implied_growth_rate - Decimal("0.10")) <= Decimal("0.0001")


# ---------------------------------------------------------------------------
# 7. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_reversed_bounds_raises(self) -> None:
        with pytest.raises(ReverseDCFError, match="lower_bound"):
            reverse_dcf(
                [_FY2024], _base_assumptions(), Decimal("150"),
                lower_bound=Decimal("0.50"),
                upper_bound=Decimal("-0.50"),
            )

    def test_equal_bounds_raises(self) -> None:
        with pytest.raises(ReverseDCFError, match="lower_bound"):
            reverse_dcf(
                [_FY2024], _base_assumptions(), Decimal("150"),
                lower_bound=Decimal("0.10"),
                upper_bound=Decimal("0.10"),
            )

    def test_zero_target_price_raises(self) -> None:
        with pytest.raises(ReverseDCFError, match="target_price must be positive"):
            reverse_dcf([_FY2024], _base_assumptions(), Decimal("0"))

    def test_negative_target_price_raises(self) -> None:
        with pytest.raises(ReverseDCFError, match="target_price must be positive"):
            reverse_dcf([_FY2024], _base_assumptions(), Decimal("-100"))


# ---------------------------------------------------------------------------
# 8. Decimal-only enforcement
# ---------------------------------------------------------------------------


class TestDecimalEnforcement:
    def test_all_result_fields_decimal(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert isinstance(result.implied_growth_rate, Decimal)
        assert isinstance(result.target_price, Decimal)
        assert isinstance(result.implied_value_at_solution, Decimal)
        assert isinstance(result.residual, Decimal)
        assert isinstance(result.enterprise_value, Decimal)
        assert isinstance(result.equity_value, Decimal)
        assert isinstance(result.growth_rate_tolerance, Decimal)
        assert isinstance(result.price_tolerance, Decimal)
        assert isinstance(result.search_lower_bound, Decimal)
        assert isinstance(result.search_upper_bound, Decimal)

    def test_calculation_values_decimal(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        for c in result.calculations:
            if c.value is not None:
                assert isinstance(c.value, Decimal), f"{c.metric} is {type(c.value)}"


# ---------------------------------------------------------------------------
# 9. Reproducibility
# ---------------------------------------------------------------------------


class TestReproducibility:
    def test_identical_inputs_identical_outputs(self) -> None:
        a = _base_assumptions()
        r1 = reverse_dcf([_FY2024], a, Decimal("223.3635"))
        r2 = reverse_dcf([_FY2024], a, Decimal("223.3635"))
        assert r1.implied_growth_rate == r2.implied_growth_rate
        assert r1.iterations == r2.iterations
        assert r1.residual == r2.residual
        assert r1.enterprise_value == r2.enterprise_value


# ---------------------------------------------------------------------------
# 10. Audit trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_calculations_not_empty(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert len(result.calculations) > 0

    def test_has_bounds_check(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        bounds = [c for c in result.calculations if c.metric == "reverse_dcf_bounds_check"]
        assert len(bounds) == 1

    def test_has_iteration_records(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        iters = [c for c in result.calculations if c.metric.startswith("reverse_dcf_iteration_")]
        assert len(iters) == result.iterations

    def test_has_result_record(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        final = [c for c in result.calculations if c.metric == "reverse_dcf_result"]
        assert len(final) == 1

    def test_every_calculation_has_formula(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        for c in result.calculations:
            assert c.formula, f"{c.metric} missing formula"

    def test_every_calculation_has_version(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        for c in result.calculations:
            assert c.version, f"{c.metric} missing version"


# ---------------------------------------------------------------------------
# 11. DCF result consistency
# ---------------------------------------------------------------------------


class TestDCFResultConsistency:
    def test_implied_value_matches_dcf(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.dcf_result.implied_value_per_share == result.implied_value_at_solution

    def test_dcf_assumptions_use_implied_growth(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.dcf_result.assumptions.revenue_growth_rates == result.implied_growth_rate

    def test_fixed_assumptions_echo_original(self) -> None:
        original = _base_assumptions()
        result = reverse_dcf([_FY2024], original, Decimal("223.3635"))
        assert result.fixed_assumptions.ebit_margin == original.ebit_margin
        assert result.fixed_assumptions.tax_rate == original.tax_rate
        assert result.fixed_assumptions.wacc == original.wacc
        assert result.fixed_assumptions.terminal_growth_rate == original.terminal_growth_rate

    def test_enterprise_and_equity_from_dcf(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("223.3635"),
        )
        assert result.enterprise_value == result.dcf_result.enterprise_value
        assert result.equity_value == result.dcf_result.equity_value


# ---------------------------------------------------------------------------
# 12. Purity — no DB/provider/HTTP/LLM dependency
# ---------------------------------------------------------------------------


class TestPurity:
    def test_runs_without_external_deps(self) -> None:
        result = reverse_dcf(
            [_FY2024], _base_assumptions(), Decimal("200"),
        )
        assert isinstance(result, ReverseDCFResult)
        assert result.convergence_status == ConvergenceStatus.CONVERGED
