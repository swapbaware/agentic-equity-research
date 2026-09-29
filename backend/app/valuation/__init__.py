"""Deterministic Valuation Engine.

All calculations use decimal.Decimal, never float. Every intermediate step
records its inputs, formula, period, and calculation version via CalculationResult.
"""
from __future__ import annotations

from app.valuation.dcf import dcf_valuation
from app.valuation.models import (
    CashFlowBasis,
    ConvergenceStatus,
    DCFAssumptions,
    DCFResult,
    MultipleValuationResult,
    ProjectedYear,
    ReverseDCFResult,
    SensitivityCell,
    TerminalValueResult,
    ValuationMethodType,
    WACCComponents,
)
from app.valuation.multiples import (
    MultipleValuationError,
    ev_ebitda_valuation,
    ev_fcf_valuation,
    fcf_yield_valuation,
    pb_valuation,
    pe_valuation,
    peg_valuation,
    ps_valuation,
)
from app.valuation.reverse_dcf import reverse_dcf

__all__ = [
    "CashFlowBasis",
    "ConvergenceStatus",
    "DCFAssumptions",
    "DCFResult",
    "MultipleValuationError",
    "MultipleValuationResult",
    "ProjectedYear",
    "ReverseDCFResult",
    "SensitivityCell",
    "TerminalValueResult",
    "ValuationMethodType",
    "WACCComponents",
    "dcf_valuation",
    "ev_ebitda_valuation",
    "ev_fcf_valuation",
    "fcf_yield_valuation",
    "pb_valuation",
    "pe_valuation",
    "peg_valuation",
    "ps_valuation",
    "reverse_dcf",
]
