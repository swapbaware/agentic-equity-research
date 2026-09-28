"""Return on capital calculations: ROE, ROCE, ROIC.

All use average of current and previous period balance-sheet values.
Capital Employed = Total Assets - Current Liabilities (if not provided).
Invested Capital = Total Equity + Total Debt - Cash.
NOPAT = EBIT × (1 - effective_tax_rate).
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics._calc import safe_divide
from app.analytics.models import CalculationResult, PeriodFinancials

VERSION = "1.0.0"
_TWO = Decimal("2")
_ONE = Decimal("1")


def _avg(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None:
        return None
    return (a + b) / _TWO


def _capital_employed(period: PeriodFinancials) -> Decimal | None:
    if period.capital_employed is not None:
        return period.capital_employed
    if period.total_assets is not None and period.current_liabilities is not None:
        return period.total_assets - period.current_liabilities
    return None


def _invested_capital(period: PeriodFinancials) -> Decimal | None:
    if (
        period.total_equity is not None
        and period.total_debt is not None
        and period.cash_and_equivalents is not None
    ):
        return period.total_equity + period.total_debt - period.cash_and_equivalents
    return None


def _nopat(period: PeriodFinancials) -> Decimal | None:
    if period.ebit is None or period.effective_tax_rate is None:
        return None
    return period.ebit * (_ONE - period.effective_tax_rate)


def roe(
    current: PeriodFinancials, previous: PeriodFinancials,
) -> CalculationResult:
    avg_equity = _avg(current.total_equity, previous.total_equity)
    value, notes = safe_divide(current.pat, avg_equity)
    return CalculationResult(
        metric="roe",
        value=value,
        inputs={
            "pat": current.pat,
            "current_equity": current.total_equity,
            "previous_equity": previous.total_equity,
            "average_equity": avg_equity,
        },
        period=current.period,
        formula="pat / average(current_equity, previous_equity)",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def roce(
    current: PeriodFinancials, previous: PeriodFinancials,
) -> CalculationResult:
    ce_curr = _capital_employed(current)
    ce_prev = _capital_employed(previous)
    avg_ce = _avg(ce_curr, ce_prev)
    value, notes = safe_divide(current.ebit, avg_ce)
    return CalculationResult(
        metric="roce",
        value=value,
        inputs={
            "ebit": current.ebit,
            "current_capital_employed": ce_curr,
            "previous_capital_employed": ce_prev,
            "average_capital_employed": avg_ce,
        },
        period=current.period,
        formula="ebit / average(capital_employed_current, capital_employed_previous)",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def roic(
    current: PeriodFinancials, previous: PeriodFinancials,
) -> CalculationResult:
    nopat_val = _nopat(current)
    ic_curr = _invested_capital(current)
    ic_prev = _invested_capital(previous)
    avg_ic = _avg(ic_curr, ic_prev)
    value, notes = safe_divide(nopat_val, avg_ic)
    return CalculationResult(
        metric="roic",
        value=value,
        inputs={
            "ebit": current.ebit,
            "effective_tax_rate": current.effective_tax_rate,
            "nopat": nopat_val,
            "current_invested_capital": ic_curr,
            "previous_invested_capital": ic_prev,
            "average_invested_capital": avg_ic,
        },
        period=current.period,
        formula="nopat / average(invested_capital) where nopat = ebit * (1 - tax_rate)",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )
