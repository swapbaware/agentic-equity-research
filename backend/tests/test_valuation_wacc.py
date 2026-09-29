"""Tests for WACC calculation."""
from __future__ import annotations

from decimal import Decimal

from app.valuation.models import WACCComponents
from app.valuation.wacc import compute_wacc


class TestWACCCalculation:
    """Hand-verified WACC examples."""

    def test_basic_wacc(self) -> None:
        """Ke = 0.07 + 1.0 × 0.06 = 0.13
        Kd = 0.09 × (1 - 0.25) = 0.0675
        WACC = 0.70 × 0.13 + 0.30 × 0.0675 = 0.091 + 0.02025 = 0.11125
        """
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.0"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.30"),
        )
        wacc, calcs = compute_wacc(comp, tax_rate=Decimal("0.25"))

        assert wacc == Decimal("0.111250")
        assert len(calcs) == 3

        ke_calc = next(c for c in calcs if c.metric == "cost_of_equity")
        assert ke_calc.value == Decimal("0.130000")

        kd_calc = next(c for c in calcs if c.metric == "after_tax_cost_of_debt")
        assert kd_calc.value == Decimal("0.067500")

    def test_all_equity_wacc(self) -> None:
        """100% equity: WACC = Ke."""
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.2"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0"),
        )
        wacc, _ = compute_wacc(comp, tax_rate=Decimal("0.25"))
        # Ke = 0.07 + 1.2 × 0.06 = 0.142
        assert wacc == Decimal("0.142000")

    def test_high_beta_wacc(self) -> None:
        """High beta company."""
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.5"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.10"),
            debt_ratio=Decimal("0.40"),
        )
        wacc, _ = compute_wacc(comp, tax_rate=Decimal("0.30"))
        # Ke = 0.07 + 1.5 × 0.06 = 0.16
        # Kd = 0.10 × 0.70 = 0.07
        # WACC = 0.60 × 0.16 + 0.40 × 0.07 = 0.096 + 0.028 = 0.124
        assert wacc == Decimal("0.124000")

    def test_all_values_are_decimal(self) -> None:
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.0"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.30"),
        )
        _, calcs = compute_wacc(comp, tax_rate=Decimal("0.25"))
        for c in calcs:
            assert isinstance(c.value, Decimal), f"{c.metric} is {type(c.value)}"

    def test_audit_trail_has_formulas(self) -> None:
        comp = WACCComponents(
            risk_free_rate=Decimal("0.07"),
            beta=Decimal("1.0"),
            equity_risk_premium=Decimal("0.06"),
            pre_tax_cost_of_debt=Decimal("0.09"),
            debt_ratio=Decimal("0.30"),
        )
        _, calcs = compute_wacc(comp, tax_rate=Decimal("0.25"))
        for c in calcs:
            assert c.formula
            assert c.version
            assert c.inputs
