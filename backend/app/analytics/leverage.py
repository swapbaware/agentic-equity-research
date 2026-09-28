"""Leverage and solvency ratio calculations.

Net Debt = Total Debt - Cash and Equivalents.
All ratios return None with a note when denominators are zero or data is missing.
"""
from __future__ import annotations

from decimal import Decimal  # noqa: TC003 — runtime use in function bodies

from app.analytics._calc import safe_divide
from app.analytics.models import CalculationResult, PeriodFinancials

VERSION = "1.0.0"


def debt_to_equity(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.total_debt, period.total_equity)
    return CalculationResult(
        metric="debt_to_equity",
        value=value,
        inputs={
            "total_debt": period.total_debt,
            "total_equity": period.total_equity,
        },
        period=period.period,
        formula="total_debt / total_equity",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def net_debt_to_ebitda(period: PeriodFinancials) -> CalculationResult:
    net_debt: Decimal | None = None
    if period.total_debt is not None and period.cash_and_equivalents is not None:
        net_debt = period.total_debt - period.cash_and_equivalents
    value, notes = safe_divide(net_debt, period.ebitda)
    return CalculationResult(
        metric="net_debt_to_ebitda",
        value=value,
        inputs={
            "total_debt": period.total_debt,
            "cash_and_equivalents": period.cash_and_equivalents,
            "net_debt": net_debt,
            "ebitda": period.ebitda,
        },
        period=period.period,
        formula="(total_debt - cash) / ebitda",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def interest_coverage(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.ebit, period.interest_expense)
    return CalculationResult(
        metric="interest_coverage",
        value=value,
        inputs={
            "ebit": period.ebit,
            "interest_expense": period.interest_expense,
        },
        period=period.period,
        formula="ebit / interest_expense",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def current_ratio(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(period.current_assets, period.current_liabilities)
    return CalculationResult(
        metric="current_ratio",
        value=value,
        inputs={
            "current_assets": period.current_assets,
            "current_liabilities": period.current_liabilities,
        },
        period=period.period,
        formula="current_assets / current_liabilities",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )
