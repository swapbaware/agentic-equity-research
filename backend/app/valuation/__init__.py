"""Deterministic DCF Valuation Engine.

All calculations use decimal.Decimal, never float. Every intermediate step
records its inputs, formula, period, and calculation version via CalculationResult.
"""
from __future__ import annotations

from app.valuation.dcf import dcf_valuation
from app.valuation.models import (
    DCFAssumptions,
    DCFResult,
    ProjectedYear,
    SensitivityCell,
    TerminalValueResult,
    WACCComponents,
)

__all__ = [
    "DCFAssumptions",
    "DCFResult",
    "ProjectedYear",
    "SensitivityCell",
    "TerminalValueResult",
    "WACCComponents",
    "dcf_valuation",
]
