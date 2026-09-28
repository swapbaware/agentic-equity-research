"""Profitability margin calculations.

All margins are expressed as ratios (0.25 = 25%).
Gross profit is derived from revenue - COGS when not provided directly.
"""
from __future__ import annotations

from app.analytics._calc import safe_divide
from app.analytics.models import CalculationResult, PeriodFinancials

VERSION = "1.0.0"


def gross_margin(period: PeriodFinancials) -> CalculationResult:
    gp = period.gross_profit
    if gp is None and period.revenue is not None and period.cost_of_goods_sold is not None:
        gp = period.revenue - period.cost_of_goods_sold
    value, notes = safe_divide(gp, period.revenue)
    return CalculationResult(
        metric="gross_margin",
        value=value,
        inputs={"gross_profit": gp, "revenue": period.revenue},
        period=period.period,
        formula="gross_profit / revenue",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def ebitda_margin(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.ebitda, period.revenue)
    return CalculationResult(
        metric="ebitda_margin",
        value=value,
        inputs={"ebitda": period.ebitda, "revenue": period.revenue},
        period=period.period,
        formula="ebitda / revenue",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def ebit_margin(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.ebit, period.revenue)
    return CalculationResult(
        metric="ebit_margin",
        value=value,
        inputs={"ebit": period.ebit, "revenue": period.revenue},
        period=period.period,
        formula="ebit / revenue",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def net_margin(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.pat, period.revenue)
    return CalculationResult(
        metric="net_margin",
        value=value,
        inputs={"pat": period.pat, "revenue": period.revenue},
        period=period.period,
        formula="pat / revenue",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )
