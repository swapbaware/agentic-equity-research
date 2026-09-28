"""Financial Analytics Engine — deterministic financial metric calculations.

All calculations use decimal.Decimal, never float. Every result records
its inputs, formula, period, and calculation version.
"""
from __future__ import annotations

from app.analytics import (
    cashflow,
    efficiency,
    growth,
    leverage,
    margins,
    quality,
    returns,
)
from app.analytics.engine import compute_all
from app.analytics.models import AnalyticsReport, CalculationResult, PeriodFinancials

__all__ = [
    "AnalyticsReport",
    "CalculationResult",
    "PeriodFinancials",
    "cashflow",
    "compute_all",
    "efficiency",
    "growth",
    "leverage",
    "margins",
    "quality",
    "returns",
]
