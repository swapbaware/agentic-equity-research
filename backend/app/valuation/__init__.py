"""Deterministic Valuation Engine.

All calculations use decimal.Decimal, never float. Every intermediate step
records its inputs, formula, period, and calculation version via CalculationResult.
"""
from __future__ import annotations

from app.valuation.dcf import dcf_valuation
from app.valuation.historical_bands import (
    HistoricalBandError,
    historical_valuation_bands,
)
from app.valuation.models import (
    CashFlowBasis,
    ConvergenceStatus,
    CurrentValuationPosition,
    DataSufficiency,
    DataSufficiencyThresholds,
    DCFAssumptions,
    DCFResult,
    FinancialPeriodType,
    HistoricalObservationInput,
    HistoricalValuationObservation,
    HistoricalValuationResult,
    MultipleValuationResult,
    ObservationStatus,
    PeerComparisonResult,
    PeerObservationInput,
    PeerSelectionMethod,
    PeerSetMetadata,
    PeerStatistics,
    PeerValuationObservation,
    PercentileBand,
    ProjectedYear,
    ReverseDCFResult,
    SensitivityCell,
    TargetVsPeerPosition,
    TerminalValueResult,
    ValuationBandStatistics,
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
from app.valuation.peer_comparison import (
    PeerComparisonError,
    compare_peers,
)
from app.valuation.reverse_dcf import reverse_dcf

__all__ = [
    "CashFlowBasis",
    "ConvergenceStatus",
    "CurrentValuationPosition",
    "DCFAssumptions",
    "DCFResult",
    "DataSufficiency",
    "DataSufficiencyThresholds",
    "FinancialPeriodType",
    "HistoricalBandError",
    "HistoricalObservationInput",
    "HistoricalValuationObservation",
    "HistoricalValuationResult",
    "MultipleValuationError",
    "MultipleValuationResult",
    "ObservationStatus",
    "PeerComparisonError",
    "PeerComparisonResult",
    "PeerObservationInput",
    "PeerSelectionMethod",
    "PeerSetMetadata",
    "PeerStatistics",
    "PeerValuationObservation",
    "PercentileBand",
    "ProjectedYear",
    "ReverseDCFResult",
    "SensitivityCell",
    "TargetVsPeerPosition",
    "TerminalValueResult",
    "ValuationBandStatistics",
    "ValuationMethodType",
    "WACCComponents",
    "compare_peers",
    "dcf_valuation",
    "ev_ebitda_valuation",
    "ev_fcf_valuation",
    "fcf_yield_valuation",
    "historical_valuation_bands",
    "pb_valuation",
    "pe_valuation",
    "peg_valuation",
    "ps_valuation",
    "reverse_dcf",
]
