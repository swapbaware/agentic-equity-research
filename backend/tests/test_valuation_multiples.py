"""Tests for the Multiple-Based Valuation Engine.

Covers all seven methods (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF)
with golden datasets, edge cases, validation, audit trail, and Decimal enforcement.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analytics.models import PeriodFinancials
from app.valuation.models import CashFlowBasis, MultipleValuationResult, ValuationMethodType
from app.valuation.multiples import (
    MultipleValuationError,
    ev_ebitda_valuation,
    ev_fcf_valuation,
    fcf_yield_valuation,
    pb_valuation,
    pe_valuation,
    peg_valuation,
    ps_valuation,
)

_TS = datetime(2026, 1, 1, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_FY2024 = PeriodFinancials(
    period="FY2024",
    revenue=Decimal("10000"),
    ebitda=Decimal("2500"),
    ebit=Decimal("2000"),
    depreciation_amortization=Decimal("300"),
    pat=Decimal("1500"),
    total_equity=Decimal("8000"),
    total_debt=Decimal("2000"),
    cash_and_equivalents=Decimal("500"),
    current_assets=Decimal("4000"),
    current_liabilities=Decimal("2500"),
    total_assets=Decimal("12000"),
    cfo=Decimal("2000"),
    capex=Decimal("500"),
    eps=Decimal("20.00"),
    shares_outstanding=Decimal("100"),
    effective_tax_rate=Decimal("0.25"),
)

_FY2023 = PeriodFinancials(
    period="FY2023",
    revenue=Decimal("8500"),
    ebitda=Decimal("2100"),
    ebit=Decimal("1700"),
    depreciation_amortization=Decimal("250"),
    pat=Decimal("1200"),
    total_equity=Decimal("7000"),
    total_debt=Decimal("1800"),
    cash_and_equivalents=Decimal("400"),
    current_assets=Decimal("3800"),
    current_liabilities=Decimal("2300"),
    total_assets=Decimal("10500"),
    cfo=Decimal("1700"),
    capex=Decimal("400"),
    eps=Decimal("16.00"),
    shares_outstanding=Decimal("100"),
    effective_tax_rate=Decimal("0.25"),
)

# EV/FCF golden dataset — Company A (zero ΔNWC)
_EVFCF_A_PRIOR = PeriodFinancials(
    period="FY2023",
    current_assets=Decimal("3800"),
    current_liabilities=Decimal("2300"),
)

_EVFCF_A_CURRENT = PeriodFinancials(
    period="FY2024",
    ebit=Decimal("2000"),
    depreciation_amortization=Decimal("300"),
    capex=Decimal("500"),
    current_assets=Decimal("4000"),
    current_liabilities=Decimal("2500"),
    effective_tax_rate=Decimal("0.25"),
    total_debt=Decimal("2000"),
    cash_and_equivalents=Decimal("500"),
    shares_outstanding=Decimal("100"),
)

# EV/FCF golden dataset — Company B (non-zero ΔNWC)
_EVFCF_B_PRIOR = PeriodFinancials(
    period="FY2023",
    current_assets=Decimal("3500"),
    current_liabilities=Decimal("2000"),
)

_EVFCF_B_CURRENT = PeriodFinancials(
    period="FY2024",
    ebit=Decimal("2400"),
    depreciation_amortization=Decimal("360"),
    capex=Decimal("600"),
    current_assets=Decimal("4400"),
    current_liabilities=Decimal("2600"),
    effective_tax_rate=Decimal("0.25"),
    total_debt=Decimal("3000"),
    cash_and_equivalents=Decimal("1000"),
    shares_outstanding=Decimal("200"),
)


# ===================================================================
# P/E TESTS
# ===================================================================


class TestPEGolden:
    def test_pe_golden_calculation(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        # EPS=20 × P/E=25 = 500
        assert result.implied_value_per_share == Decimal("500.0000")

    def test_pe_method_type(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.method == ValuationMethodType.PE

    def test_pe_input_metric(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.input_metric_name == "eps"
        assert result.input_metric_value == Decimal("20.00")

    def test_pe_equity_based(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.implied_enterprise_value is None
        assert result.net_debt is None

    def test_pe_implied_equity_value(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        # 500 × 100 shares = 50000
        assert result.implied_equity_value == Decimal("50000.0000")

    def test_pe_with_current_price(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), current_price=Decimal("400"), calculated_at=_TS)
        assert result.current_price == Decimal("400")
        # (500 - 400) / 400 = 0.25
        assert result.upside_downside_pct == Decimal("0.250000")

    def test_pe_without_current_price(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.current_price is None
        assert result.upside_downside_pct is None

    def test_pe_cash_flow_basis_none(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_pe_period_propagated(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.period == "FY2024"


class TestPEValidation:
    def test_pe_zero_eps_raises(self) -> None:
        f = _FY2024.model_copy(update={"eps": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="eps"):
            pe_valuation(f, Decimal("25"), calculated_at=_TS)

    def test_pe_negative_eps_raises(self) -> None:
        f = _FY2024.model_copy(update={"eps": Decimal("-5")})
        with pytest.raises(MultipleValuationError, match="eps"):
            pe_valuation(f, Decimal("25"), calculated_at=_TS)

    def test_pe_missing_eps_raises(self) -> None:
        f = _FY2024.model_copy(update={"eps": None})
        with pytest.raises(MultipleValuationError, match="eps"):
            pe_valuation(f, Decimal("25"), calculated_at=_TS)

    def test_pe_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_pe"):
            pe_valuation(_FY2024, Decimal("0"), calculated_at=_TS)

    def test_pe_negative_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_pe"):
            pe_valuation(_FY2024, Decimal("-10"), calculated_at=_TS)

    def test_pe_missing_shares_raises(self) -> None:
        f = _FY2024.model_copy(update={"shares_outstanding": None})
        with pytest.raises(MultipleValuationError, match="shares_outstanding"):
            pe_valuation(f, Decimal("25"), calculated_at=_TS)

    def test_pe_zero_shares_raises(self) -> None:
        f = _FY2024.model_copy(update={"shares_outstanding": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="shares_outstanding"):
            pe_valuation(f, Decimal("25"), calculated_at=_TS)


# ===================================================================
# EV/EBITDA TESTS
# ===================================================================


class TestEVEBITDAGolden:
    def test_ev_ebitda_golden(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        # EV = 2500 × 18 = 45000
        assert result.implied_enterprise_value == Decimal("45000.0000")
        # Net Debt = 2000 - 500 = 1500
        assert result.net_debt == Decimal("1500.0000")
        # Equity = 45000 - 1500 = 43500
        assert result.implied_equity_value == Decimal("43500.0000")
        # Per share = 43500 / 100 = 435
        assert result.implied_value_per_share == Decimal("435.0000")

    def test_ev_ebitda_method_type(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        assert result.method == ValuationMethodType.EV_EBITDA

    def test_ev_ebitda_enterprise_based(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        assert result.implied_enterprise_value is not None
        assert result.net_debt is not None

    def test_ev_ebitda_net_cash(self) -> None:
        f = _FY2024.model_copy(update={
            "total_debt": Decimal("200"),
            "cash_and_equivalents": Decimal("1000"),
        })
        result = ev_ebitda_valuation(f, Decimal("18"), calculated_at=_TS)
        # Net Debt = 200 - 1000 = -800 (net cash)
        assert result.net_debt == Decimal("-800.0000")
        # Equity = 45000 - (-800) = 45800
        assert result.implied_equity_value == Decimal("45800.0000")
        assert result.implied_equity_value > result.implied_enterprise_value  # type: ignore[operator]

    def test_ev_ebitda_with_price(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), current_price=Decimal("400"), calculated_at=_TS)
        # (435 - 400) / 400 = 0.0875
        assert result.upside_downside_pct == Decimal("0.087500")

    def test_ev_ebitda_cash_flow_basis_none(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        assert result.cash_flow_basis is None


class TestEVEBITDAValidation:
    def test_ev_ebitda_zero_ebitda_raises(self) -> None:
        f = _FY2024.model_copy(update={"ebitda": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="ebitda"):
            ev_ebitda_valuation(f, Decimal("18"), calculated_at=_TS)

    def test_ev_ebitda_negative_ebitda_raises(self) -> None:
        f = _FY2024.model_copy(update={"ebitda": Decimal("-100")})
        with pytest.raises(MultipleValuationError, match="ebitda"):
            ev_ebitda_valuation(f, Decimal("18"), calculated_at=_TS)

    def test_ev_ebitda_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_ev_ebitda"):
            ev_ebitda_valuation(_FY2024, Decimal("0"), calculated_at=_TS)

    def test_ev_ebitda_missing_debt_raises(self) -> None:
        f = _FY2024.model_copy(update={"total_debt": None})
        with pytest.raises(MultipleValuationError, match="total_debt"):
            ev_ebitda_valuation(f, Decimal("18"), calculated_at=_TS)

    def test_ev_ebitda_missing_cash_raises(self) -> None:
        f = _FY2024.model_copy(update={"cash_and_equivalents": None})
        with pytest.raises(MultipleValuationError, match="cash_and_equivalents"):
            ev_ebitda_valuation(f, Decimal("18"), calculated_at=_TS)


# ===================================================================
# P/S TESTS
# ===================================================================


class TestPSGolden:
    def test_ps_golden(self) -> None:
        result = ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS)
        # Equity = 10000 × 3 = 30000
        assert result.implied_equity_value == Decimal("30000.0000")
        # Per share = 30000 / 100 = 300
        assert result.implied_value_per_share == Decimal("300.0000")

    def test_ps_method_type(self) -> None:
        result = ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS)
        assert result.method == ValuationMethodType.PS

    def test_ps_equity_based(self) -> None:
        result = ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS)
        assert result.implied_enterprise_value is None
        assert result.net_debt is None

    def test_ps_input_metric(self) -> None:
        result = ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS)
        assert result.input_metric_name == "revenue"
        assert result.input_metric_value == Decimal("10000")


class TestPSValidation:
    def test_ps_zero_revenue_raises(self) -> None:
        f = _FY2024.model_copy(update={"revenue": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="revenue"):
            ps_valuation(f, Decimal("3"), calculated_at=_TS)

    def test_ps_negative_revenue_raises(self) -> None:
        f = _FY2024.model_copy(update={"revenue": Decimal("-500")})
        with pytest.raises(MultipleValuationError, match="revenue"):
            ps_valuation(f, Decimal("3"), calculated_at=_TS)

    def test_ps_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_ps"):
            ps_valuation(_FY2024, Decimal("0"), calculated_at=_TS)

    def test_ps_negative_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_ps"):
            ps_valuation(_FY2024, Decimal("-1"), calculated_at=_TS)


# ===================================================================
# P/B TESTS
# ===================================================================


class TestPBGolden:
    def test_pb_golden(self) -> None:
        result = pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS)
        # Equity = 8000 × 2.5 = 20000
        assert result.implied_equity_value == Decimal("20000.0000")
        # Per share = 20000 / 100 = 200
        assert result.implied_value_per_share == Decimal("200.0000")

    def test_pb_method_type(self) -> None:
        result = pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS)
        assert result.method == ValuationMethodType.PB

    def test_pb_equity_based(self) -> None:
        result = pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS)
        assert result.implied_enterprise_value is None
        assert result.net_debt is None

    def test_pb_input_metric(self) -> None:
        result = pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS)
        assert result.input_metric_name == "total_equity"
        assert result.input_metric_value == Decimal("8000")


class TestPBValidation:
    def test_pb_zero_equity_raises(self) -> None:
        f = _FY2024.model_copy(update={"total_equity": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="total_equity"):
            pb_valuation(f, Decimal("2.5"), calculated_at=_TS)

    def test_pb_negative_equity_raises(self) -> None:
        f = _FY2024.model_copy(update={"total_equity": Decimal("-1000")})
        with pytest.raises(MultipleValuationError, match="total_equity"):
            pb_valuation(f, Decimal("2.5"), calculated_at=_TS)

    def test_pb_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_pb"):
            pb_valuation(_FY2024, Decimal("0"), calculated_at=_TS)

    def test_pb_missing_shares_raises(self) -> None:
        f = _FY2024.model_copy(update={"shares_outstanding": None})
        with pytest.raises(MultipleValuationError, match="shares_outstanding"):
            pb_valuation(f, Decimal("2.5"), calculated_at=_TS)


# ===================================================================
# PEG TESTS
# ===================================================================


class TestPEGGolden:
    def test_peg_golden(self) -> None:
        # PEG=1, Growth=15% → Implied P/E = 1 × 15 = 15
        # Implied Value = EPS 20 × 15 = 300
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.implied_pe == Decimal("15.000000")
        assert result.implied_value_per_share == Decimal("300.0000")

    def test_peg_growth_percentage_points(self) -> None:
        # PEG=1.2, Growth=20% → Implied P/E = 1.2 × 20 = 24
        # Implied Value = 20 × 24 = 480
        result = peg_valuation(_FY2024, Decimal("1.2"), Decimal("20"), calculated_at=_TS)
        assert result.implied_pe == Decimal("24.000000")
        assert result.implied_value_per_share == Decimal("480.0000")

    def test_peg_method_type(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.method == ValuationMethodType.PEG

    def test_peg_earnings_growth_recorded(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.earnings_growth_pct == Decimal("15")

    def test_peg_implied_pe_recorded(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.implied_pe == Decimal("15.000000")

    def test_peg_cash_flow_basis_none(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_peg_with_price(self) -> None:
        result = peg_valuation(
            _FY2024, Decimal("1"), Decimal("15"), current_price=Decimal("250"),
            calculated_at=_TS,
        )
        # (300 - 250) / 250 = 0.2
        assert result.upside_downside_pct == Decimal("0.200000")

    def test_peg_implied_equity_value(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        # 300 × 100 = 30000
        assert result.implied_equity_value == Decimal("30000.0000")


class TestPEGValidation:
    def test_peg_zero_growth_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="earnings_growth_pct"):
            peg_valuation(_FY2024, Decimal("1"), Decimal("0"), calculated_at=_TS)

    def test_peg_negative_growth_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="earnings_growth_pct"):
            peg_valuation(_FY2024, Decimal("1"), Decimal("-5"), calculated_at=_TS)

    def test_peg_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_peg"):
            peg_valuation(_FY2024, Decimal("0"), Decimal("15"), calculated_at=_TS)

    def test_peg_negative_eps_raises(self) -> None:
        f = _FY2024.model_copy(update={"eps": Decimal("-3")})
        with pytest.raises(MultipleValuationError, match="eps"):
            peg_valuation(f, Decimal("1"), Decimal("15"), calculated_at=_TS)

    def test_peg_zero_eps_raises(self) -> None:
        f = _FY2024.model_copy(update={"eps": Decimal("0")})
        with pytest.raises(MultipleValuationError, match="eps"):
            peg_valuation(f, Decimal("1"), Decimal("15"), calculated_at=_TS)


# ===================================================================
# FCF YIELD TESTS
# ===================================================================


class TestFCFYieldGolden:
    def test_fcf_yield_golden(self) -> None:
        # Equity FCF = 2000 - 500 = 1500
        # Market Cap = 1500 / 0.05 = 30000
        # Per share = 30000 / 100 = 300
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.implied_equity_value == Decimal("30000.0000")
        assert result.implied_value_per_share == Decimal("300.0000")

    def test_fcf_yield_method_type(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.method == ValuationMethodType.FCF_YIELD

    def test_fcf_yield_equity_based(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.implied_enterprise_value is None
        assert result.net_debt is None

    def test_fcf_yield_uses_equity_fcf(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.cash_flow_basis == CashFlowBasis.EQUITY_FCF
        # Verify input is CFO - CapEx, not FCFF
        assert result.input_metric_name == "equity_fcf"
        assert result.input_metric_value == Decimal("1500.0000")

    def test_fcf_yield_input_metric(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.input_metric_name == "equity_fcf"
        # CFO=2000 - CapEx=500 = 1500
        assert result.input_metric_value == Decimal("1500.0000")

    def test_fcf_yield_with_price(self) -> None:
        result = fcf_yield_valuation(
            _FY2024, Decimal("0.05"), current_price=Decimal("250"),
            calculated_at=_TS,
        )
        # (300 - 250) / 250 = 0.2
        assert result.upside_downside_pct == Decimal("0.200000")


class TestFCFYieldValidation:
    def test_fcf_yield_negative_fcf_raises(self) -> None:
        f = _FY2024.model_copy(update={"cfo": Decimal("200"), "capex": Decimal("500")})
        with pytest.raises(MultipleValuationError, match="equity FCF must be positive"):
            fcf_yield_valuation(f, Decimal("0.05"), calculated_at=_TS)

    def test_fcf_yield_zero_fcf_raises(self) -> None:
        f = _FY2024.model_copy(update={"cfo": Decimal("500"), "capex": Decimal("500")})
        with pytest.raises(MultipleValuationError, match="equity FCF must be positive"):
            fcf_yield_valuation(f, Decimal("0.05"), calculated_at=_TS)

    def test_fcf_yield_missing_cfo_raises(self) -> None:
        f = _FY2024.model_copy(update={"cfo": None})
        with pytest.raises(MultipleValuationError, match="cfo"):
            fcf_yield_valuation(f, Decimal("0.05"), calculated_at=_TS)

    def test_fcf_yield_missing_capex_raises(self) -> None:
        f = _FY2024.model_copy(update={"capex": None})
        with pytest.raises(MultipleValuationError, match="capex"):
            fcf_yield_valuation(f, Decimal("0.05"), calculated_at=_TS)

    def test_fcf_yield_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_fcf_yield"):
            fcf_yield_valuation(_FY2024, Decimal("0"), calculated_at=_TS)

    def test_fcf_yield_negative_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_fcf_yield"):
            fcf_yield_valuation(_FY2024, Decimal("-0.05"), calculated_at=_TS)


# ===================================================================
# EV/FCF TESTS (FCFF-based)
# ===================================================================


class TestEVFCFGoldenA:
    """Company A — zero ΔNWC."""

    def test_ev_fcf_golden_a_fcff(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        # NWC prior = 3800-2300 = 1500, NWC current = 4000-2500 = 1500
        # ΔNWC = 0
        # NOPAT = 2000 × 0.75 = 1500
        # FCFF = 1500 + 300 - 500 - 0 = 1300
        assert result.input_metric_value == Decimal("1300.0000")
        assert result.input_metric_name == "fcff"

    def test_ev_fcf_golden_a_ev(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        # EV = 1300 × 15 = 19500
        assert result.implied_enterprise_value == Decimal("19500.0000")

    def test_ev_fcf_golden_a_net_debt(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        # Net Debt = 2000 - 500 = 1500
        assert result.net_debt == Decimal("1500.0000")

    def test_ev_fcf_golden_a_equity_value(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        # Equity = 19500 - 1500 = 18000
        assert result.implied_equity_value == Decimal("18000.0000")

    def test_ev_fcf_golden_a_per_share(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        # Value/Share = 18000 / 100 = 180
        assert result.implied_value_per_share == Decimal("180.0000")


class TestEVFCFGoldenB:
    """Company B — non-zero ΔNWC (positive)."""

    def test_ev_fcf_golden_b_fcff(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        # NWC prior = 3500-2000 = 1500, NWC current = 4400-2600 = 1800
        # ΔNWC = 300
        # NOPAT = 2400 × 0.75 = 1800
        # FCFF = 1800 + 360 - 600 - 300 = 1260
        assert result.input_metric_value == Decimal("1260.0000")

    def test_ev_fcf_golden_b_ev(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        # EV = 1260 × 12 = 15120
        assert result.implied_enterprise_value == Decimal("15120.0000")

    def test_ev_fcf_golden_b_net_debt(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        # Net Debt = 3000 - 1000 = 2000
        assert result.net_debt == Decimal("2000.0000")

    def test_ev_fcf_golden_b_equity_value(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        # Equity = 15120 - 2000 = 13120
        assert result.implied_equity_value == Decimal("13120.0000")

    def test_ev_fcf_golden_b_per_share(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        # Value/Share = 13120 / 200 = 65.60
        assert result.implied_value_per_share == Decimal("65.6000")


class TestEVFCFNWC:
    def test_ev_fcf_zero_delta_nwc(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        delta_nwc_calc = next(
            c for c in result.calculations if c.metric == "delta_nwc"
        )
        assert delta_nwc_calc.value == Decimal("0.0000")

    def test_ev_fcf_positive_delta_nwc(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_B_CURRENT, _EVFCF_B_PRIOR, Decimal("12"),
            calculated_at=_TS,
        )
        delta_nwc_calc = next(
            c for c in result.calculations if c.metric == "delta_nwc"
        )
        assert delta_nwc_calc.value == Decimal("300.0000")

    def test_ev_fcf_negative_delta_nwc(self) -> None:
        prior = PeriodFinancials(
            period="FY2023",
            current_assets=Decimal("5000"),
            current_liabilities=Decimal("2000"),
        )
        current = _EVFCF_A_CURRENT.model_copy(update={
            "current_assets": Decimal("4000"),
            "current_liabilities": Decimal("2500"),
        })
        result = ev_fcf_valuation(current, prior, Decimal("15"), calculated_at=_TS)
        # NWC prior = 3000, NWC current = 1500 → ΔNWC = -1500
        delta_nwc_calc = next(
            c for c in result.calculations if c.metric == "delta_nwc"
        )
        assert delta_nwc_calc.value == Decimal("-1500.0000")


class TestEVFCFMetadata:
    def test_ev_fcf_method_type(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        assert result.method == ValuationMethodType.EV_FCF

    def test_ev_fcf_cash_flow_basis_fcff(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        assert result.cash_flow_basis == CashFlowBasis.FCFF

    def test_ev_fcf_enterprise_based(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        assert result.implied_enterprise_value is not None
        assert result.net_debt is not None

    def test_ev_fcf_net_cash(self) -> None:
        current = _EVFCF_A_CURRENT.model_copy(update={
            "total_debt": Decimal("200"),
            "cash_and_equivalents": Decimal("1000"),
        })
        result = ev_fcf_valuation(current, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)
        assert result.net_debt == Decimal("-800.0000")
        assert result.implied_equity_value > result.implied_enterprise_value  # type: ignore[operator]

    def test_ev_fcf_with_price(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            current_price=Decimal("150"),
            calculated_at=_TS,
        )
        # (180 - 150) / 150 = 0.2
        assert result.upside_downside_pct == Decimal("0.200000")


class TestEVFCFValidation:
    def test_ev_fcf_missing_ebit_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"ebit": None})
        with pytest.raises(MultipleValuationError, match="ebit"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_da_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"depreciation_amortization": None})
        with pytest.raises(MultipleValuationError, match="depreciation_amortization"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_capex_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"capex": None})
        with pytest.raises(MultipleValuationError, match="capex"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_tax_rate_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"effective_tax_rate": None})
        with pytest.raises(MultipleValuationError, match="effective_tax_rate"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_current_assets_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"current_assets": None})
        with pytest.raises(MultipleValuationError, match="current_assets"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_current_liabilities_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"current_liabilities": None})
        with pytest.raises(MultipleValuationError, match="current_liabilities"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_prior_current_assets_raises(self) -> None:
        prior = PeriodFinancials(period="FY2023", current_liabilities=Decimal("2300"))
        with pytest.raises(MultipleValuationError, match="prior current_assets"):
            ev_fcf_valuation(_EVFCF_A_CURRENT, prior, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_missing_prior_current_liabilities_raises(self) -> None:
        prior = PeriodFinancials(period="FY2023", current_assets=Decimal("3800"))
        with pytest.raises(MultipleValuationError, match="prior current_liabilities"):
            ev_fcf_valuation(_EVFCF_A_CURRENT, prior, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_negative_fcff_raises(self) -> None:
        # Make EBIT very small so FCFF goes negative
        f = _EVFCF_A_CURRENT.model_copy(update={
            "ebit": Decimal("100"),
            "depreciation_amortization": Decimal("10"),
            "capex": Decimal("500"),
        })
        with pytest.raises(MultipleValuationError, match="FCFF must be positive"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_zero_fcff_raises(self) -> None:
        # NOPAT = 500×0.75=375, D&A=25, CapEx=400 → FCFF = 375+25-400-0 = 0
        f = _EVFCF_A_CURRENT.model_copy(update={
            "ebit": Decimal("500"),
            "depreciation_amortization": Decimal("25"),
            "capex": Decimal("400"),
        })
        with pytest.raises(MultipleValuationError, match="FCFF must be positive"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)

    def test_ev_fcf_zero_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_ev_fcf"):
            ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("0"), calculated_at=_TS)

    def test_ev_fcf_negative_target_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="target_ev_fcf"):
            ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("-5"), calculated_at=_TS)

    def test_ev_fcf_missing_shares_raises(self) -> None:
        f = _EVFCF_A_CURRENT.model_copy(update={"shares_outstanding": None})
        with pytest.raises(MultipleValuationError, match="shares_outstanding"):
            ev_fcf_valuation(f, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)


# ===================================================================
# EV/FCF AUDIT TRAIL
# ===================================================================


class TestEVFCFAuditTrail:
    def test_ev_fcf_audit_contains_nopat(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        nopat = next(c for c in result.calculations if c.metric == "nopat")
        assert nopat.value == Decimal("1500.0000")
        assert nopat.formula == "EBIT × (1 − Tax Rate)"

    def test_ev_fcf_audit_contains_delta_nwc(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        delta = next(c for c in result.calculations if c.metric == "delta_nwc")
        assert delta.value == Decimal("0.0000")

    def test_ev_fcf_audit_contains_fcff(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        fcff = next(c for c in result.calculations if c.metric == "fcff")
        assert fcff.value == Decimal("1300.0000")
        assert fcff.formula == "NOPAT + D&A − CapEx − ΔNWC"

    def test_ev_fcf_audit_contains_nwc_current(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        nwc = next(c for c in result.calculations if c.metric == "nwc_current")
        assert nwc.value == Decimal("1500")

    def test_ev_fcf_audit_contains_nwc_prior(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        nwc = next(c for c in result.calculations if c.metric == "nwc_prior")
        assert nwc.value == Decimal("1500")


# ===================================================================
# CROSS-METHOD CONSISTENCY
# ===================================================================


class TestCrossMethodCashFlowBasis:
    def test_fcf_yield_cash_flow_basis(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        assert result.cash_flow_basis == CashFlowBasis.EQUITY_FCF

    def test_ev_fcf_cash_flow_basis(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        assert result.cash_flow_basis == CashFlowBasis.FCFF

    def test_pe_cash_flow_basis_none(self) -> None:
        result = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_ev_ebitda_cash_flow_basis_none(self) -> None:
        result = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_ps_cash_flow_basis_none(self) -> None:
        result = ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_pb_cash_flow_basis_none(self) -> None:
        result = pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS)
        assert result.cash_flow_basis is None

    def test_peg_cash_flow_basis_none(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert result.cash_flow_basis is None


class TestCrossMethodConsistency:
    def test_fcf_yield_uses_cfo_minus_capex(self) -> None:
        result = fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS)
        fcf_calc = next(c for c in result.calculations if c.metric == "equity_fcf")
        assert fcf_calc.formula == "CFO − CapEx"
        assert fcf_calc.inputs["cfo"] == Decimal("2000")
        assert fcf_calc.inputs["capex"] == Decimal("500")
        assert fcf_calc.value == Decimal("1500.0000")

    def test_ev_fcf_uses_fcff_not_equity_fcf(self) -> None:
        result = ev_fcf_valuation(
            _EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        fcff_calc = next(c for c in result.calculations if c.metric == "fcff")
        assert fcff_calc.formula == "NOPAT + D&A − CapEx − ΔNWC"
        metrics = {c.metric for c in result.calculations}
        assert "equity_fcf" not in metrics

    def test_ev_methods_use_same_net_debt(self) -> None:
        ev_ebitda = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        current_with_full = _EVFCF_A_CURRENT.model_copy(update={
            "total_debt": Decimal("2000"),
            "cash_and_equivalents": Decimal("500"),
        })
        ev_fcf = ev_fcf_valuation(
            current_with_full, _EVFCF_A_PRIOR, Decimal("15"),
            calculated_at=_TS,
        )
        assert ev_ebitda.net_debt == ev_fcf.net_debt

    def test_equity_methods_have_no_ev(self) -> None:
        results = [
            pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS),
            ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS),
            pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS),
            peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS),
            fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS),
        ]
        for r in results:
            assert r.implied_enterprise_value is None
            assert r.net_debt is None


# ===================================================================
# GENERAL AUDIT TRAIL
# ===================================================================


class TestGeneralAuditTrail:
    def _all_results(self) -> list[MultipleValuationResult]:
        return [
            pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS),
            ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS),
            ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS),
            pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS),
            peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS),
            fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS),
            ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS),
        ]

    def test_all_have_calculations(self) -> None:
        for result in self._all_results():
            assert len(result.calculations) > 0, f"{result.method} has no calculations"

    def test_all_calculations_have_formula(self) -> None:
        for result in self._all_results():
            for c in result.calculations:
                assert c.formula, f"{result.method}/{c.metric} missing formula"

    def test_all_calculations_have_version(self) -> None:
        for result in self._all_results():
            for c in result.calculations:
                assert c.version == "1.0.0", f"{result.method}/{c.metric} bad version"

    def test_all_have_engine_version(self) -> None:
        for result in self._all_results():
            assert result.engine_version == "1.0.0"


# ===================================================================
# REPRODUCIBILITY
# ===================================================================


class TestReproducibility:
    def test_pe_reproducible(self) -> None:
        r1 = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        r2 = pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS)
        assert r1.implied_value_per_share == r2.implied_value_per_share

    def test_ev_ebitda_reproducible(self) -> None:
        r1 = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        r2 = ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS)
        assert r1.implied_value_per_share == r2.implied_value_per_share
        assert r1.implied_enterprise_value == r2.implied_enterprise_value

    def test_ev_fcf_reproducible(self) -> None:
        r1 = ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)
        r2 = ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS)
        assert r1.implied_value_per_share == r2.implied_value_per_share
        assert r1.implied_enterprise_value == r2.implied_enterprise_value


# ===================================================================
# DECIMAL ENFORCEMENT
# ===================================================================


class TestDecimalEnforcement:
    def _all_results(self) -> list[MultipleValuationResult]:
        return [
            pe_valuation(_FY2024, Decimal("25"), calculated_at=_TS),
            ev_ebitda_valuation(_FY2024, Decimal("18"), calculated_at=_TS),
            ps_valuation(_FY2024, Decimal("3"), calculated_at=_TS),
            pb_valuation(_FY2024, Decimal("2.5"), calculated_at=_TS),
            peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS),
            fcf_yield_valuation(_FY2024, Decimal("0.05"), calculated_at=_TS),
            ev_fcf_valuation(_EVFCF_A_CURRENT, _EVFCF_A_PRIOR, Decimal("15"), calculated_at=_TS),
        ]

    def test_all_implied_values_decimal(self) -> None:
        for result in self._all_results():
            assert isinstance(result.implied_value_per_share, Decimal), result.method
            assert isinstance(result.implied_equity_value, Decimal), result.method
            assert isinstance(result.shares_outstanding, Decimal), result.method
            assert isinstance(result.input_metric_value, Decimal), result.method
            assert isinstance(result.target_value, Decimal), result.method

    def test_ev_fields_decimal_when_present(self) -> None:
        for result in self._all_results():
            if result.implied_enterprise_value is not None:
                assert isinstance(result.implied_enterprise_value, Decimal)
            if result.net_debt is not None:
                assert isinstance(result.net_debt, Decimal)

    def test_all_calculation_values_decimal(self) -> None:
        for result in self._all_results():
            for c in result.calculations:
                if c.value is not None:
                    assert isinstance(c.value, Decimal), f"{result.method}/{c.metric}"

    def test_peg_special_fields_decimal(self) -> None:
        result = peg_valuation(_FY2024, Decimal("1"), Decimal("15"), calculated_at=_TS)
        assert isinstance(result.earnings_growth_pct, Decimal)
        assert isinstance(result.implied_pe, Decimal)


# ===================================================================
# CURRENT PRICE EDGE CASES
# ===================================================================


class TestCurrentPriceEdgeCases:
    def test_negative_current_price_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="current_price"):
            pe_valuation(_FY2024, Decimal("25"), current_price=Decimal("-100"), calculated_at=_TS)

    def test_zero_current_price_raises(self) -> None:
        with pytest.raises(MultipleValuationError, match="current_price"):
            pe_valuation(_FY2024, Decimal("25"), current_price=Decimal("0"), calculated_at=_TS)

    def test_downside_computed_when_overvalued(self) -> None:
        # Implied = 500, current = 600 → downside
        result = pe_valuation(_FY2024, Decimal("25"), current_price=Decimal("600"), calculated_at=_TS)
        assert result.upside_downside_pct is not None
        assert result.upside_downside_pct < Decimal("0")
