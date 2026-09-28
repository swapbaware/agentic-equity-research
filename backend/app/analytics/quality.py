"""Earnings quality metrics: Return on Incremental Capital and Earnings Consistency.

ROIIC measures how effectively new capital generates new profits.
Earnings Consistency scores stability via profitable periods, growth streaks,
and coefficient-of-variation-based volatility.
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
_ONE = Decimal("1")
_THREE = Decimal("3")
_ZERO = Decimal("0")


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


def return_on_incremental_capital(
    current: PeriodFinancials,
    previous: PeriodFinancials,
) -> CalculationResult:
    nopat_curr = _nopat(current)
    nopat_prev = _nopat(previous)
    ic_curr = _invested_capital(current)
    ic_prev = _invested_capital(previous)

    value: Decimal | None = None
    notes: str | None = None

    if nopat_curr is None or nopat_prev is None or ic_curr is None or ic_prev is None:
        notes = "missing input data"
    else:
        delta_nopat = nopat_curr - nopat_prev
        delta_ic = ic_curr - ic_prev
        if delta_ic == _ZERO:
            notes = "no change in invested capital"
        else:
            value = (delta_nopat / delta_ic).quantize(
                RATIO_QUANTIZE, rounding=ROUNDING,
            )

    return CalculationResult(
        metric="return_on_incremental_capital",
        value=value,
        inputs={
            "current_nopat": nopat_curr,
            "previous_nopat": nopat_prev,
            "current_invested_capital": ic_curr,
            "previous_invested_capital": ic_prev,
        },
        period=f"{previous.period}-{current.period}",
        formula="delta_nopat / delta_invested_capital",
        version=VERSION,
        unit="ratio",
        notes=notes,
    )


def earnings_consistency(periods: list[PeriodFinancials]) -> CalculationResult:
    """Score earnings stability across multiple periods (0-1, higher = better)."""
    pat_values = [p.pat for p in periods if p.pat is not None]

    if len(pat_values) < 2:
        return CalculationResult(
            metric="earnings_consistency",
            value=None,
            inputs={"periods_with_pat": len(pat_values)},
            period=(
                f"{periods[0].period}-{periods[-1].period}" if periods else "N/A"
            ),
            formula="composite(profitable_ratio, growth_ratio, 1 - volatility)",
            version=VERSION,
            unit="score",
            notes="need at least 2 periods with PAT data",
        )

    n = len(pat_values)
    profitable = sum(1 for v in pat_values if v > _ZERO)
    profitable_ratio = Decimal(str(profitable)) / Decimal(str(n))

    growth_count = sum(
        1 for i in range(1, n) if pat_values[i] > pat_values[i - 1]
    )
    growth_ratio = Decimal(str(growth_count)) / Decimal(str(n - 1))

    with localcontext() as ctx:
        ctx.prec = COMPUTATION_PRECISION
        mean = sum(pat_values) / Decimal(str(n))
        if mean == _ZERO:
            variance = sum(v ** 2 for v in pat_values) / Decimal(str(n))
            cv = _ZERO if variance == _ZERO else _ONE
        else:
            variance = sum((v - mean) ** 2 for v in pat_values) / Decimal(str(n))
            stddev = variance.sqrt()
            cv = abs(stddev / mean)

    volatility_score = max(_ZERO, _ONE - cv)
    raw_score = (profitable_ratio + growth_ratio + volatility_score) / _THREE
    score = raw_score.quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    return CalculationResult(
        metric="earnings_consistency",
        value=score,
        inputs={
            "total_periods": n,
            "profitable_periods": profitable,
            "growth_periods": growth_count,
            "profitable_ratio": profitable_ratio.quantize(
                RATIO_QUANTIZE, rounding=ROUNDING,
            ),
            "growth_ratio": growth_ratio.quantize(
                RATIO_QUANTIZE, rounding=ROUNDING,
            ),
            "volatility_score": volatility_score.quantize(
                RATIO_QUANTIZE, rounding=ROUNDING,
            ),
        },
        period=f"{periods[0].period}-{periods[-1].period}",
        formula="composite(profitable_ratio, growth_ratio, 1 - volatility)",
        version=VERSION,
        unit="score",
        notes=None,
    )
