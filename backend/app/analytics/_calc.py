"""Shared deterministic calculation utilities.

All division, rounding, and precision helpers live here to avoid
duplication across metric modules.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING


def safe_divide(
    numerator: Decimal | None,
    denominator: Decimal | None,
    *,
    quantize: Decimal = RATIO_QUANTIZE,
    multiplier: Decimal = Decimal("1"),
) -> tuple[Decimal | None, str | None]:
    """Divide two Decimals safely, returning (result, note).

    Returns None with an explanatory note if inputs are missing or
    the denominator is zero.
    """
    if numerator is None or denominator is None:
        return None, "missing input data"
    if denominator == Decimal("0"):
        return None, "division by zero"
    result = (numerator / denominator * multiplier).quantize(
        quantize, rounding=ROUNDING,
    )
    return result, None
