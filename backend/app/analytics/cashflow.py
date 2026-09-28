"""Cash flow metric calculations.

FCF = CFO - Capex (capex stored as positive spending amount).
Conversion ratios measure cash-generation quality relative to reported profit.
"""
from __future__ import annotations

from decimal import Decimal  # noqa: TC003 — runtime use in function bodies

from app.analytics._calc import safe_divide
from app.analytics.models import CalculationResult, PeriodFinancials

VERSION = "1.0.0"


def _fcf(period: PeriodFinancials) -> Decimal | None:
    if period.cfo is None or period.capex is None:
        return None
    return period.cfo - period.capex


def operating_cash_flow(period: PeriodFinancials) -> CalculationResult:
    return CalculationResult(
        metric="cfo",
        value=period.cfo,
        inputs={"cfo": period.cfo},
        period=period.period,
        formula="cash_flow_from_operations",
        version=VERSION,
        unit="currency",
        notes=None if period.cfo is not None else "missing input data",
    )


def free_cash_flow(period: PeriodFinancials) -> CalculationResult:
    fcf_val = _fcf(period)
    return CalculationResult(
        metric="fcf",
        value=fcf_val,
        inputs={"cfo": period.cfo, "capex": period.capex},
        period=period.period,
        formula="cfo - capex",
        version=VERSION,
        unit="currency",
        notes=None if fcf_val is not None else "missing input data",
    )


def cfo_to_pat(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.cfo, period.pat)
    return CalculationResult(
        metric="cfo_to_pat",
        value=value,
        inputs={"cfo": period.cfo, "pat": period.pat},
        period=period.period,
        formula="cfo / pat",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def fcf_to_pat(period: PeriodFinancials) -> CalculationResult:
    fcf_val = _fcf(period)
    value, notes = safe_divide(fcf_val, period.pat)
    return CalculationResult(
        metric="fcf_to_pat",
        value=value,
        inputs={
            "cfo": period.cfo,
            "capex": period.capex,
            "fcf": fcf_val,
            "pat": period.pat,
        },
        period=period.period,
        formula="(cfo - capex) / pat",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def capex_to_revenue(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.capex, period.revenue)
    return CalculationResult(
        metric="capex_to_revenue",
        value=value,
        inputs={"capex": period.capex, "revenue": period.revenue},
        period=period.period,
        formula="capex / revenue",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )
