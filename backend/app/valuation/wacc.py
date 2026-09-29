"""WACC (Weighted Average Cost of Capital) calculation.

Ke = Rf + Beta × ERP
Kd = PreTaxCostOfDebt × (1 - TaxRate)
WACC = (E/(D+E)) × Ke + (D/(D+E)) × Kd

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation.models import WACCComponents

VERSION = "1.0.0"
_ONE = Decimal("1")


def compute_wacc(
    components: WACCComponents,
    tax_rate: Decimal,
) -> tuple[Decimal, list[CalculationResult]]:
    """Compute WACC from its components. Returns (wacc, audit_trail)."""
    results: list[CalculationResult] = []

    ke = (
        components.risk_free_rate
        + components.beta * components.equity_risk_premium
    ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
    results.append(CalculationResult(
        metric="cost_of_equity",
        value=ke,
        inputs={
            "risk_free_rate": components.risk_free_rate,
            "beta": components.beta,
            "equity_risk_premium": components.equity_risk_premium,
        },
        period="assumption",
        formula="Rf + Beta × ERP",
        version=VERSION,
        unit="ratio",
    ))

    kd = (
        components.pre_tax_cost_of_debt * (_ONE - tax_rate)
    ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
    results.append(CalculationResult(
        metric="after_tax_cost_of_debt",
        value=kd,
        inputs={
            "pre_tax_cost_of_debt": components.pre_tax_cost_of_debt,
            "tax_rate": tax_rate,
        },
        period="assumption",
        formula="PreTaxKd × (1 - TaxRate)",
        version=VERSION,
        unit="ratio",
    ))

    equity_weight = _ONE - components.debt_ratio
    wacc_value = (
        equity_weight * ke + components.debt_ratio * kd
    ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    results.append(CalculationResult(
        metric="wacc",
        value=wacc_value,
        inputs={
            "cost_of_equity": ke,
            "after_tax_cost_of_debt": kd,
            "equity_weight": equity_weight,
            "debt_weight": components.debt_ratio,
        },
        period="assumption",
        formula="(E/(D+E)) × Ke + (D/(D+E)) × Kd",
        version=VERSION,
        unit="ratio",
    ))

    return wacc_value, results
