"""Compound Annual Growth Rate (CAGR) calculations.

CAGR = (end / start) ^ (1 / years) - 1

Computed via decimal ln/exp to keep the full chain in Decimal arithmetic.
CAGR is defined only when both start and end are strictly positive.
"""
from __future__ import annotations

from decimal import Decimal, localcontext

from app.analytics.models import (
    COMPUTATION_PRECISION,
    RATIO_QUANTIZE,
    ROUNDING,
    CalculationResult,
    PeriodFinancials,
)

VERSION = "1.0.0"


def _cagr(
    start_value: Decimal | None,
    end_value: Decimal | None,
    years: int,
) -> tuple[Decimal | None, str | None]:
    if start_value is None or end_value is None:
        return None, "missing input data"
    if years <= 0:
        return None, "years must be positive"
    if start_value <= Decimal("0") or end_value <= Decimal("0"):
        return None, "CAGR undefined for non-positive values"
    if start_value == end_value:
        return Decimal("0").quantize(RATIO_QUANTIZE, rounding=ROUNDING), None

    with localcontext() as ctx:
        ctx.prec = COMPUTATION_PRECISION
        ratio = end_value / start_value
        ln_ratio = ctx.ln(ratio)
        exponent = ln_ratio / Decimal(str(years))
        result = ctx.exp(exponent) - Decimal("1")
        return result.quantize(RATIO_QUANTIZE, rounding=ROUNDING), None


def _cagr_result(
    metric: str,
    field: str,
    start: PeriodFinancials,
    end: PeriodFinancials,
    years: int,
) -> CalculationResult:
    start_val: Decimal | None = getattr(start, field)
    end_val: Decimal | None = getattr(end, field)
    value, notes = _cagr(start_val, end_val, years)
    return CalculationResult(
        metric=metric,
        value=value,
        inputs={
            "start_value": start_val,
            "end_value": end_val,
            "years": years,
        },
        period=f"{start.period}-{end.period}",
        formula=f"({field}_end / {field}_start) ^ (1 / years) - 1",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def revenue_cagr(
    start: PeriodFinancials, end: PeriodFinancials, years: int,
) -> CalculationResult:
    return _cagr_result("revenue_cagr", "revenue", start, end, years)


def ebitda_cagr(
    start: PeriodFinancials, end: PeriodFinancials, years: int,
) -> CalculationResult:
    return _cagr_result("ebitda_cagr", "ebitda", start, end, years)


def ebit_cagr(
    start: PeriodFinancials, end: PeriodFinancials, years: int,
) -> CalculationResult:
    return _cagr_result("ebit_cagr", "ebit", start, end, years)


def pat_cagr(
    start: PeriodFinancials, end: PeriodFinancials, years: int,
) -> CalculationResult:
    return _cagr_result("pat_cagr", "pat", start, end, years)


def eps_cagr(
    start: PeriodFinancials, end: PeriodFinancials, years: int,
) -> CalculationResult:
    return _cagr_result("eps_cagr", "eps", start, end, years)
