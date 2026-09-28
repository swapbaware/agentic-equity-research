"""Working capital and efficiency calculations.

Days metrics use a 365-day year. All use end-of-period balances.
Cash Conversion Cycle = Receivable Days + Inventory Days - Payable Days.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics._calc import safe_divide
from app.analytics.models import (
    DAYS_QUANTIZE,
    ROUNDING,
    CalculationResult,
    PeriodFinancials,
)

VERSION = "1.0.0"
_DAYS_IN_YEAR = Decimal("365")


def working_capital(period: PeriodFinancials) -> CalculationResult:
    value: Decimal | None = None
    notes: str | None = None
    if period.current_assets is not None and period.current_liabilities is not None:
        value = period.current_assets - period.current_liabilities
    else:
        notes = "missing input data"
    return CalculationResult(
        metric="working_capital",
        value=value,
        inputs={
            "current_assets": period.current_assets,
            "current_liabilities": period.current_liabilities,
        },
        period=period.period,
        formula="current_assets - current_liabilities",
        version=VERSION,
        unit="currency",
        notes=notes,
    )


def receivable_days(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(
        period.accounts_receivable, period.revenue,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )
    return CalculationResult(
        metric="receivable_days",
        value=value,
        inputs={
            "accounts_receivable": period.accounts_receivable,
            "revenue": period.revenue,
        },
        period=period.period,
        formula="(accounts_receivable / revenue) * 365",
        version=VERSION,
        unit="days",
        notes=notes,
    )


def inventory_days(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(
        period.inventory, period.cost_of_goods_sold,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )
    return CalculationResult(
        metric="inventory_days",
        value=value,
        inputs={
            "inventory": period.inventory,
            "cost_of_goods_sold": period.cost_of_goods_sold,
        },
        period=period.period,
        formula="(inventory / cost_of_goods_sold) * 365",
        version=VERSION,
        unit="days",
        notes=notes,
    )


def payable_days(period: PeriodFinancials) -> CalculationResult:
    value, notes = safe_divide(
        period.accounts_payable, period.cost_of_goods_sold,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )
    return CalculationResult(
        metric="payable_days",
        value=value,
        inputs={
            "accounts_payable": period.accounts_payable,
            "cost_of_goods_sold": period.cost_of_goods_sold,
        },
        period=period.period,
        formula="(accounts_payable / cost_of_goods_sold) * 365",
        version=VERSION,
        unit="days",
        notes=notes,
    )


def cash_conversion_cycle(period: PeriodFinancials) -> CalculationResult:
    recv = safe_divide(
        period.accounts_receivable, period.revenue,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )
    inv = safe_divide(
        period.inventory, period.cost_of_goods_sold,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )
    pay = safe_divide(
        period.accounts_payable, period.cost_of_goods_sold,
        quantize=DAYS_QUANTIZE, multiplier=_DAYS_IN_YEAR,
    )

    value: Decimal | None = None
    notes: str | None = None

    if recv[0] is not None and inv[0] is not None and pay[0] is not None:
        value = (recv[0] + inv[0] - pay[0]).quantize(DAYS_QUANTIZE, rounding=ROUNDING)
    else:
        missing = []
        if recv[0] is None:
            missing.append("receivable_days")
        if inv[0] is None:
            missing.append("inventory_days")
        if pay[0] is None:
            missing.append("payable_days")
        notes = f"cannot compute: {', '.join(missing)} unavailable"

    return CalculationResult(
        metric="cash_conversion_cycle",
        value=value,
        inputs={
            "receivable_days": recv[0],
            "inventory_days": inv[0],
            "payable_days": pay[0],
        },
        period=period.period,
        formula="receivable_days + inventory_days - payable_days",
        version=VERSION,
        unit="days",
        notes=notes,
    )
