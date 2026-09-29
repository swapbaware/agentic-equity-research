"""Tests for DCF valuation Pydantic models and validation."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.valuation.models import (
    DCFAssumptions,
    TerminalMethod,
    WACCComponents,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        "net_debt": Decimal("500"),
    }
    defaults.update(overrides)
    return DCFAssumptions(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------

class TestDCFAssumptionsValid:
    def test_stable_decimal_construction(self) -> None:
        a = _base_assumptions()
        assert a.projection_years == 5
        assert a.revenue_growth_rates == Decimal("0.10")
        assert a.wacc == Decimal("0.10")

    def test_per_year_list_construction(self) -> None:
        rates = [Decimal("0.12"), Decimal("0.11"), Decimal("0.10"), Decimal("0.09"), Decimal("0.08")]
        a = _base_assumptions(revenue_growth_rates=rates)
        assert a.revenue_growth_rates == rates

    def test_wacc_components_instead_of_wacc(self) -> None:
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.0"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.30"),
        )
        a = _base_assumptions(wacc=None, wacc_components=comp)
        assert a.wacc_components is not None
        assert a.wacc is None

    def test_exit_multiple_method(self) -> None:
        a = _base_assumptions(
            terminal_method=TerminalMethod.EXIT_MULTIPLE,
            exit_multiple=Decimal("12"),
        )
        assert a.terminal_method == TerminalMethod.EXIT_MULTIPLE
        assert a.exit_multiple == Decimal("12")

    def test_frozen_immutability(self) -> None:
        a = _base_assumptions()
        with pytest.raises(ValidationError):
            a.projection_years = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestDCFAssumptionsValidation:
    def test_projection_years_zero(self) -> None:
        with pytest.raises(ValueError, match="projection_years"):
            _base_assumptions(projection_years=0)

    def test_projection_years_too_large(self) -> None:
        with pytest.raises(ValueError, match="projection_years"):
            _base_assumptions(projection_years=26)

    def test_shares_outstanding_zero(self) -> None:
        with pytest.raises(ValueError, match="shares_outstanding"):
            _base_assumptions(shares_outstanding=Decimal("0"))

    def test_shares_outstanding_negative(self) -> None:
        with pytest.raises(ValueError, match="shares_outstanding"):
            _base_assumptions(shares_outstanding=Decimal("-10"))

    def test_no_wacc_and_no_components(self) -> None:
        with pytest.raises(ValueError, match="either wacc or wacc_components"):
            _base_assumptions(wacc=None, wacc_components=None)

    def test_exit_multiple_missing_for_exit_method(self) -> None:
        with pytest.raises(ValueError, match="exit_multiple is required"):
            _base_assumptions(
                terminal_method=TerminalMethod.EXIT_MULTIPLE,
                exit_multiple=None,
            )

    def test_per_year_list_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="revenue_growth_rates list length"):
            _base_assumptions(
                projection_years=5,
                revenue_growth_rates=[Decimal("0.10"), Decimal("0.09")],
            )


# ---------------------------------------------------------------------------
# WACCComponents validation
# ---------------------------------------------------------------------------

class TestWACCComponentsValidation:
    def test_debt_ratio_above_one(self) -> None:
        with pytest.raises(ValueError, match="debt_ratio"):
            WACCComponents(
                risk_free_rate=Decimal("0.07"),
                beta=Decimal("1.0"),
                equity_risk_premium=Decimal("0.06"),
                pre_tax_cost_of_debt=Decimal("0.09"),
                debt_ratio=Decimal("1.5"),
            )

    def test_debt_ratio_negative(self) -> None:
        with pytest.raises(ValueError, match="debt_ratio"):
            WACCComponents(
                risk_free_rate=Decimal("0.07"),
                beta=Decimal("1.0"),
                equity_risk_premium=Decimal("0.06"),
                pre_tax_cost_of_debt=Decimal("0.09"),
                debt_ratio=Decimal("-0.1"),
            )

    def test_valid_construction(self) -> None:
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.2"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.40"),
        )
        assert comp.beta == Decimal("1.2")
