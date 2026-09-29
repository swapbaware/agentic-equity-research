"""Tests for the DCF Valuation Engine.

Includes a hand-verified 5-year golden dataset, edge cases, and
validation error tests.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analytics.models import PeriodFinancials
from app.valuation.dcf import DCFValidationError, dcf_valuation
from app.valuation.models import (
    DCFAssumptions,
    DCFResult,
    TerminalMethod,
    WACCComponents,
)
from app.valuation.terminal import TerminalValueError

D = Decimal
_TS = datetime(2026, 1, 1, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Synthetic historical data (base for projections)
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
# Golden Dataset — 5 year DCF, hand-verified
#
# Base revenue = 10000, 10% growth, 20% EBIT margin, 25% tax, 3% D&A,
# 5% capex, 10% NWC change, WACC 10%, terminal growth 3%.
#
# Year 1: Rev=11000, EBIT=2200, NOPAT=1650, D&A=330, CapEx=550,
#          dNWC=100, FCF=1330
# Year 2: Rev=12100, EBIT=2420, NOPAT=1815, D&A=363, CapEx=605,
#          dNWC=110, FCF=1463
# Year 3: Rev=13310, EBIT=2662, NOPAT=1996.5, D&A=399.3, CapEx=665.5,
#          dNWC=121, FCF=1609.3
# Year 4: Rev=14641, EBIT=2928.2, NOPAT=2196.15, D&A=439.23, CapEx=732.05,
#          dNWC=133.1, FCF=1770.23
# Year 5: Rev=16105.1, EBIT=3221.02, NOPAT=2415.765, D&A=483.153,
#          CapEx=805.255, dNWC=146.41, FCF=1947.253
#
# Terminal FCF = 1947.253 × 1.03 = 2005.6706
# TV = 2005.6706 / (0.10 - 0.03) = 28652.4371
# ---------------------------------------------------------------------------


class TestGoldenDataset:
    """5-year DCF with hand-verified intermediate values."""

    def _run(self) -> DCFResult:
        return dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)

    def test_returns_dcf_result(self) -> None:
        result = self._run()
        assert isinstance(result, DCFResult)

    def test_projected_year_count(self) -> None:
        result = self._run()
        assert len(result.projected_years) == 5

    def test_year1_revenue(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.revenue == Decimal("11000.0000")

    def test_year1_ebit(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.ebit == Decimal("2200.0000")

    def test_year1_nopat(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.nopat == Decimal("1650.0000")

    def test_year1_da(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.depreciation_amortization == Decimal("330.0000")

    def test_year1_capex(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.capex == Decimal("550.0000")

    def test_year1_nwc_change(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        assert y1.nwc_change == Decimal("100.0000")

    def test_year1_fcf(self) -> None:
        result = self._run()
        y1 = result.projected_years[0]
        # 1650 + 330 - 550 - 100 = 1330
        assert y1.fcf == Decimal("1330.0000")

    def test_year5_revenue(self) -> None:
        result = self._run()
        y5 = result.projected_years[4]
        # 10000 × 1.1^5 = 16105.1
        assert y5.revenue == Decimal("16105.1000")

    def test_year5_fcf(self) -> None:
        result = self._run()
        y5 = result.projected_years[4]
        # NOPAT=2415.765 + D&A=483.153 - CapEx=805.255 - dNWC=146.41
        expected_fcf = (
            Decimal("2415.7650") + Decimal("483.1530")
            - Decimal("805.2550") - Decimal("146.4100")
        )
        assert y5.fcf == expected_fcf

    def test_terminal_value_method(self) -> None:
        result = self._run()
        assert result.terminal_value.method == TerminalMethod.GORDON_GROWTH

    def test_enterprise_value_positive(self) -> None:
        result = self._run()
        assert result.enterprise_value > Decimal("0")

    def test_equity_value(self) -> None:
        result = self._run()
        expected_equity = result.enterprise_value - Decimal("1500")
        assert result.equity_value == expected_equity

    def test_implied_value_per_share(self) -> None:
        result = self._run()
        expected = (result.equity_value / Decimal("100")).quantize(Decimal("0.0001"))
        assert result.implied_value_per_share == expected

    def test_upside_downside(self) -> None:
        result = self._run()
        expected = (
            (result.implied_value_per_share - Decimal("150")) / Decimal("150")
        ).quantize(Decimal("0.000001"))
        assert result.upside_downside_pct == expected

    def test_wacc_used(self) -> None:
        result = self._run()
        assert result.wacc_used == Decimal("0.10")

    def test_engine_version(self) -> None:
        result = self._run()
        assert result.engine_version == "1.0.0"


# ---------------------------------------------------------------------------
# WACC components integration
# ---------------------------------------------------------------------------


class TestWACCComponentsIntegration:
    def test_wacc_components_flow(self) -> None:
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.0"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.30"),
        )
        assumptions = _base_assumptions(wacc=None, wacc_components=comp)
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        # WACC = 0.70 × 0.13 + 0.30 × 0.0675 = 0.11125
        assert result.wacc_used == Decimal("0.111250")
        wacc_calcs = [c for c in result.calculations if c.metric == "cost_of_equity"]
        assert len(wacc_calcs) == 1


# ---------------------------------------------------------------------------
# Exit Multiple terminal value
# ---------------------------------------------------------------------------


class TestExitMultipleTerminal:
    def test_exit_multiple_method(self) -> None:
        assumptions = _base_assumptions(
            terminal_method=TerminalMethod.EXIT_MULTIPLE,
            exit_multiple=Decimal("12"),
        )
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.terminal_value.method == TerminalMethod.EXIT_MULTIPLE
        assert result.terminal_value.exit_multiple_used == Decimal("12")
        assert result.terminal_value.terminal_ebitda is not None
        assert result.enterprise_value > Decimal("0")


# ---------------------------------------------------------------------------
# Single-year projection
# ---------------------------------------------------------------------------


class TestSingleYearProjection:
    def test_one_year(self) -> None:
        assumptions = _base_assumptions(projection_years=1)
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert len(result.projected_years) == 1
        assert result.enterprise_value > Decimal("0")


# ---------------------------------------------------------------------------
# Per-year list assumptions
# ---------------------------------------------------------------------------


class TestPerYearAssumptions:
    def test_varying_growth_rates(self) -> None:
        rates = [
            Decimal("0.15"), Decimal("0.12"), Decimal("0.10"),
            Decimal("0.08"), Decimal("0.06"),
        ]
        assumptions = _base_assumptions(revenue_growth_rates=rates)
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        # Year 1: 10000 × 1.15 = 11500
        assert result.projected_years[0].revenue == Decimal("11500.0000")
        # Year 2: 11500 × 1.12 = 12880
        assert result.projected_years[1].revenue == Decimal("12880.0000")

    def test_varying_margins(self) -> None:
        margins = [
            Decimal("0.22"), Decimal("0.21"), Decimal("0.20"),
            Decimal("0.19"), Decimal("0.18"),
        ]
        assumptions = _base_assumptions(ebit_margin=margins)
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        # Year 1: 11000 × 0.22 = 2420
        assert result.projected_years[0].ebit == Decimal("2420.0000")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_growth(self) -> None:
        assumptions = _base_assumptions(revenue_growth_rates=Decimal("0"))
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.projected_years[0].revenue == Decimal("10000.0000")
        assert result.projected_years[4].revenue == Decimal("10000.0000")
        for y in result.projected_years:
            assert y.nwc_change == Decimal("0.0000")

    def test_negative_growth(self) -> None:
        assumptions = _base_assumptions(revenue_growth_rates=Decimal("-0.05"))
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.projected_years[0].revenue < Decimal("10000")

    def test_zero_net_debt(self) -> None:
        assumptions = _base_assumptions(net_debt=Decimal("0"))
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.equity_value == result.enterprise_value

    def test_net_cash_position(self) -> None:
        assumptions = _base_assumptions(net_debt=Decimal("-500"))
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.equity_value > result.enterprise_value

    def test_wacc_equals_terminal_growth_raises(self) -> None:
        assumptions = _base_assumptions(
            wacc=Decimal("0.03"),
            terminal_growth_rate=Decimal("0.03"),
        )
        with pytest.raises(TerminalValueError, match="must be greater"):
            dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)

    def test_wacc_below_terminal_growth_raises(self) -> None:
        assumptions = _base_assumptions(
            wacc=Decimal("0.02"),
            terminal_growth_rate=Decimal("0.03"),
        )
        with pytest.raises(TerminalValueError, match="must be greater"):
            dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)

    def test_no_financials_raises(self) -> None:
        with pytest.raises(DCFValidationError, match="at least one period"):
            dcf_valuation([], _base_assumptions(), Decimal("150"), calculated_at=_TS)

    def test_zero_price_raises(self) -> None:
        with pytest.raises(DCFValidationError, match="current_price must be positive"):
            dcf_valuation([_FY2024], _base_assumptions(), Decimal("0"), calculated_at=_TS)

    def test_negative_price_raises(self) -> None:
        with pytest.raises(DCFValidationError, match="current_price must be positive"):
            dcf_valuation([_FY2024], _base_assumptions(), Decimal("-100"), calculated_at=_TS)

    def test_missing_revenue_raises(self) -> None:
        empty = PeriodFinancials(period="FY2024")
        with pytest.raises(DCFValidationError, match="positive revenue"):
            dcf_valuation([empty], _base_assumptions(), Decimal("150"), calculated_at=_TS)


# ---------------------------------------------------------------------------
# Sensitivity matrix
# ---------------------------------------------------------------------------


class TestSensitivityMatrix:
    def test_sensitivity_grid_size(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        # 7 WACC steps × 7 TG steps = 49
        assert len(result.sensitivity) == 49

    def test_sensitivity_contains_base_case(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        base_cell = next(
            (c for c in result.sensitivity
             if c.wacc == Decimal("0.100000") and c.terminal_growth_rate == Decimal("0.030000")),
            None,
        )
        assert base_cell is not None
        assert base_cell.implied_value_per_share is not None

    def test_sensitivity_invalid_cells_are_none(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        invalid_cells = [
            c for c in result.sensitivity
            if c.wacc <= c.terminal_growth_rate
        ]
        for c in invalid_cells:
            assert c.implied_value_per_share is None

    def test_higher_wacc_lower_value(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        tg = Decimal("0.030000")
        valid = sorted(
            [c for c in result.sensitivity
             if c.terminal_growth_rate == tg and c.implied_value_per_share is not None],
            key=lambda c: c.wacc,
        )
        for a, b in zip(valid, valid[1:], strict=False):
            assert a.implied_value_per_share is not None
            assert b.implied_value_per_share is not None
            assert a.implied_value_per_share > b.implied_value_per_share


# ---------------------------------------------------------------------------
# Audit trail and classification
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_calculations_not_empty(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        assert len(result.calculations) > 0

    def test_every_calculation_has_formula(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for c in result.calculations:
            assert c.formula, f"{c.metric} missing formula"

    def test_every_calculation_has_version(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for c in result.calculations:
            assert c.version, f"{c.metric} missing version"

    def test_every_calculation_has_inputs(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for c in result.calculations:
            assert isinstance(c.inputs, dict), f"{c.metric} bad inputs"

    def test_key_metrics_present(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        metrics = {c.metric for c in result.calculations}
        assert "wacc" in metrics
        assert "enterprise_value" in metrics
        assert "equity_value" in metrics
        assert "implied_value_per_share" in metrics
        assert "upside_downside_pct" in metrics

    def test_projected_fcf_metrics_present(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        metrics = {c.metric for c in result.calculations}
        for i in range(1, 6):
            assert f"projected_fcf_Y{i}" in metrics
            assert f"pv_fcf_Y{i}" in metrics

    def test_assumptions_echo_back(self) -> None:
        assumptions = _base_assumptions()
        result = dcf_valuation([_FY2024], assumptions, Decimal("150"), calculated_at=_TS)
        assert result.assumptions == assumptions


# ---------------------------------------------------------------------------
# Reproducibility and type safety
# ---------------------------------------------------------------------------


class TestReproducibility:
    def test_repeated_execution_identical(self) -> None:
        a = _base_assumptions()
        r1 = dcf_valuation([_FY2024], a, Decimal("150"), calculated_at=_TS)
        r2 = dcf_valuation([_FY2024], a, Decimal("150"), calculated_at=_TS)
        assert r1.implied_value_per_share == r2.implied_value_per_share
        assert r1.enterprise_value == r2.enterprise_value
        assert r1.equity_value == r2.equity_value
        assert r1.upside_downside_pct == r2.upside_downside_pct
        for y1, y2 in zip(r1.projected_years, r2.projected_years, strict=True):
            assert y1.fcf == y2.fcf
            assert y1.pv_fcf == y2.pv_fcf


class TestNoFloats:
    def test_all_projected_values_decimal(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for y in result.projected_years:
            assert isinstance(y.revenue, Decimal)
            assert isinstance(y.ebit, Decimal)
            assert isinstance(y.nopat, Decimal)
            assert isinstance(y.fcf, Decimal)
            assert isinstance(y.pv_fcf, Decimal)
            assert isinstance(y.discount_factor, Decimal)

    def test_all_result_values_decimal(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        assert isinstance(result.wacc_used, Decimal)
        assert isinstance(result.enterprise_value, Decimal)
        assert isinstance(result.equity_value, Decimal)
        assert isinstance(result.implied_value_per_share, Decimal)
        assert isinstance(result.upside_downside_pct, Decimal)
        assert isinstance(result.sum_pv_fcf, Decimal)

    def test_all_calculation_values_decimal(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for c in result.calculations:
            if c.value is not None:
                assert isinstance(c.value, Decimal), f"{c.metric} is {type(c.value)}"

    def test_sensitivity_values_decimal(self) -> None:
        result = dcf_valuation([_FY2024], _base_assumptions(), Decimal("150"), calculated_at=_TS)
        for cell in result.sensitivity:
            assert isinstance(cell.wacc, Decimal)
            assert isinstance(cell.terminal_growth_rate, Decimal)
            if cell.implied_value_per_share is not None:
                assert isinstance(cell.implied_value_per_share, Decimal)
