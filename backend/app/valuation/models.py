"""Pydantic models for the Valuation Engine.

Every assumption is an explicit field — no hidden defaults. All financial
values use decimal.Decimal. Models are frozen for immutability.
"""
from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 — Pydantic needs at runtime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.analytics.models import CalculationResult
from app.models.enums import FindingType  # noqa: TC002 — Pydantic needs at runtime


class TerminalMethod(StrEnum):
    GORDON_GROWTH = "gordon_growth"
    EXIT_MULTIPLE = "exit_multiple"


class ConvergenceStatus(StrEnum):
    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    NO_SOLUTION_BELOW = "no_solution_below"
    NO_SOLUTION_ABOVE = "no_solution_above"


class ValuationMethodType(StrEnum):
    PE = "pe"
    EV_EBITDA = "ev_ebitda"
    PS = "ps"
    PB = "pb"
    PEG = "peg"
    FCF_YIELD = "fcf_yield"
    EV_FCF = "ev_fcf"


class CashFlowBasis(StrEnum):
    EQUITY_FCF = "equity_fcf"
    FCFF = "fcff"


class WACCComponents(BaseModel):
    """Components for bottom-up WACC calculation."""

    model_config = ConfigDict(frozen=True)

    risk_free_rate: Decimal
    beta: Decimal
    equity_risk_premium: Decimal
    pre_tax_cost_of_debt: Decimal
    debt_ratio: Decimal

    @field_validator("debt_ratio")
    @classmethod
    def _debt_ratio_range(cls, v: Decimal) -> Decimal:
        if v < Decimal("0") or v > Decimal("1"):
            msg = "debt_ratio must be between 0 and 1"
            raise ValueError(msg)
        return v


class DCFAssumptions(BaseModel):
    """All configurable inputs for a DCF valuation.

    Fields support either a single stable Decimal (applied uniformly)
    or a per-year list[Decimal] matching projection_years in length.
    """

    model_config = ConfigDict(frozen=True)

    projection_years: int
    revenue_growth_rates: Decimal | list[Decimal]
    ebit_margin: Decimal | list[Decimal]
    da_pct_revenue: Decimal | list[Decimal]
    tax_rate: Decimal
    capex_pct_revenue: Decimal | list[Decimal]
    nwc_pct_revenue_change: Decimal

    terminal_method: TerminalMethod
    terminal_growth_rate: Decimal
    exit_multiple: Decimal | None = None

    wacc: Decimal | None = None
    wacc_components: WACCComponents | None = None

    shares_outstanding: Decimal
    net_debt: Decimal

    @field_validator("projection_years")
    @classmethod
    def _projection_years_positive(cls, v: int) -> int:
        if v < 1 or v > 25:
            msg = "projection_years must be between 1 and 25"
            raise ValueError(msg)
        return v

    @field_validator("shares_outstanding")
    @classmethod
    def _shares_positive(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            msg = "shares_outstanding must be positive"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_assumptions(self) -> DCFAssumptions:
        if self.wacc is None and self.wacc_components is None:
            msg = "either wacc or wacc_components must be provided"
            raise ValueError(msg)

        if self.terminal_method == TerminalMethod.EXIT_MULTIPLE and self.exit_multiple is None:
            msg = "exit_multiple is required when terminal_method is exit_multiple"
            raise ValueError(msg)

        n = self.projection_years
        for field_name in ("revenue_growth_rates", "ebit_margin", "da_pct_revenue", "capex_pct_revenue"):
            val = getattr(self, field_name)
            if isinstance(val, list) and len(val) != n:
                msg = f"{field_name} list length ({len(val)}) must equal projection_years ({n})"
                raise ValueError(msg)

        return self


class ProjectedYear(BaseModel):
    """Projected financials for a single future year."""

    model_config = ConfigDict(frozen=True)

    year: int
    revenue: Decimal
    ebit: Decimal
    nopat: Decimal
    depreciation_amortization: Decimal
    capex: Decimal
    nwc_change: Decimal
    fcf: Decimal
    discount_factor: Decimal
    pv_fcf: Decimal


class TerminalValueResult(BaseModel):
    """Terminal value calculation output."""

    model_config = ConfigDict(frozen=True)

    method: TerminalMethod
    terminal_fcf: Decimal | None = None
    terminal_ebitda: Decimal | None = None
    terminal_growth_rate: Decimal
    exit_multiple_used: Decimal | None = None
    undiscounted_terminal_value: Decimal
    discount_factor: Decimal
    pv_terminal_value: Decimal


class SensitivityCell(BaseModel):
    """One cell in a WACC × terminal-growth sensitivity matrix."""

    model_config = ConfigDict(frozen=True)

    wacc: Decimal
    terminal_growth_rate: Decimal
    implied_value_per_share: Decimal | None


class DCFResult(BaseModel):
    """Complete DCF valuation output — one deterministic result for one assumption set."""

    model_config = ConfigDict(frozen=True)

    assumptions: DCFAssumptions
    wacc_used: Decimal
    projected_years: list[ProjectedYear]
    terminal_value: TerminalValueResult
    sum_pv_fcf: Decimal
    enterprise_value: Decimal
    net_debt: Decimal
    equity_value: Decimal
    shares_outstanding: Decimal
    implied_value_per_share: Decimal
    current_price: Decimal
    upside_downside_pct: Decimal
    sensitivity: list[SensitivityCell]
    calculations: list[CalculationResult]
    calculated_at: datetime
    engine_version: str


class ReverseDCFResult(BaseModel):
    """Result of a reverse DCF: the implied revenue growth rate that
    justifies a given market price, holding all other assumptions fixed."""

    model_config = ConfigDict(frozen=True)

    implied_growth_rate: Decimal
    target_price: Decimal
    implied_value_at_solution: Decimal
    residual: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    convergence_status: ConvergenceStatus
    iterations: int
    growth_rate_tolerance: Decimal
    price_tolerance: Decimal
    search_lower_bound: Decimal
    search_upper_bound: Decimal
    fixed_assumptions: DCFAssumptions
    dcf_result: DCFResult
    calculations: list[CalculationResult]
    calculated_at: datetime
    engine_version: str


class MultipleValuationResult(BaseModel):
    """Result of a multiple-based valuation — one method, one assumption set."""

    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType

    input_metric_name: str
    input_metric_value: Decimal

    target_name: str
    target_value: Decimal

    implied_enterprise_value: Decimal | None
    net_debt: Decimal | None

    implied_equity_value: Decimal
    shares_outstanding: Decimal
    implied_value_per_share: Decimal

    current_price: Decimal | None
    upside_downside_pct: Decimal | None

    earnings_growth_pct: Decimal | None
    implied_pe: Decimal | None

    cash_flow_basis: CashFlowBasis | None

    calculations: list[CalculationResult]
    calculated_at: datetime
    engine_version: str
    period: str


# ---------------------------------------------------------------------------
# Historical Valuation Bands (Phase 6e.4)
# ---------------------------------------------------------------------------


class FinancialPeriodType(StrEnum):
    ANNUAL = "annual"
    TTM = "ttm"


class ObservationStatus(StrEnum):
    VALID = "valid"
    EXCLUDED_NEGATIVE_DENOMINATOR = "excluded_negative_denominator"
    EXCLUDED_ZERO_DENOMINATOR = "excluded_zero_denominator"
    EXCLUDED_MISSING_DATA = "excluded_missing_data"
    LOOK_AHEAD_RISK = "look_ahead_risk"
    UNVERIFIED_TIMING = "unverified_timing"
    DUPLICATE_OBSERVATION = "duplicate_observation"


class DataSufficiency(StrEnum):
    INSUFFICIENT = "insufficient"
    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    ADEQUATE = "adequate"


class DataSufficiencyThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_minimal: int = 4
    min_low: int = 12
    min_moderate: int = 52


class HistoricalObservationInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_date: date
    price: Decimal
    shares_outstanding: Decimal

    financial_period: str
    financial_period_type: FinancialPeriodType
    financials_available_date: date | None = None

    eps: Decimal | None = None
    revenue: Decimal | None = None
    ebitda: Decimal | None = None
    ebit: Decimal | None = None

    total_equity: Decimal | None = None
    total_debt: Decimal | None = None
    cash_and_equivalents: Decimal | None = None

    cfo: Decimal | None = None
    capex: Decimal | None = None

    depreciation_amortization: Decimal | None = None
    effective_tax_rate: Decimal | None = None
    delta_nwc: Decimal | None = None


class HistoricalValuationObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_date: date
    method: ValuationMethodType
    status: ObservationStatus
    value: Decimal | None = None
    price: Decimal
    shares_outstanding: Decimal
    market_cap: Decimal | None = None
    enterprise_value: Decimal | None = None
    net_debt: Decimal | None = None
    financial_period: str
    financial_period_type: FinancialPeriodType
    financials_available_date: date | None = None
    cash_flow_basis: CashFlowBasis | None = None
    calculation: CalculationResult | None = None


class PercentileBand(BaseModel):
    model_config = ConfigDict(frozen=True)

    percentile: Decimal
    value: Decimal


class ValuationBandStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    valid_count: int
    unverified_count: int
    excluded_count: int
    min: Decimal
    max: Decimal
    mean: Decimal
    median: Decimal
    std_dev: Decimal | None = None
    bands: list[PercentileBand]
    data_sufficiency: DataSufficiency
    lookback_start: date | None = None
    lookback_end: date | None = None
    calculations: list[CalculationResult]


class CurrentValuationPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    current_value: Decimal
    percentile_rank: Decimal | None = None
    distance_from_median_pct: Decimal | None = None
    vs_median: Decimal | None = None
    vs_p25: Decimal | None = None
    vs_p75: Decimal | None = None


class HistoricalValuationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    observations: list[HistoricalValuationObservation]
    statistics: ValuationBandStatistics | None = None
    current_position: CurrentValuationPosition | None = None
    engine_version: str
    calculated_at: datetime


# ---------------------------------------------------------------------------
# Peer Comparison (Phase 6e.5)
# ---------------------------------------------------------------------------


class PeerSelectionMethod(StrEnum):
    MANUAL = "manual"
    SECTOR_BASED = "sector_based"
    INDUSTRY_BASED = "industry_based"
    MARKET_CAP_BASED = "market_cap_based"
    AGENT_PROPOSED = "agent_proposed"
    CUSTOM = "custom"


class PeerSetMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    peer_set_id: str | None = None
    selection_method: PeerSelectionMethod
    selection_criteria: dict[str, str | Decimal | None] | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_band: str | None = None
    geography: str | None = None
    rationale: str | None = None
    source: str | None = None


class PeerObservationInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: str
    company_name: str | None = None
    currency: str = "INR"
    observation: HistoricalObservationInput


class PeerValuationObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: str
    company_name: str | None = None
    currency: str
    observation_date: date
    method: ValuationMethodType
    status: ObservationStatus
    value: Decimal | None = None
    price: Decimal
    shares_outstanding: Decimal
    market_cap: Decimal | None = None
    enterprise_value: Decimal | None = None
    net_debt: Decimal | None = None
    financial_period: str
    financial_period_type: FinancialPeriodType
    financials_available_date: date | None = None
    cash_flow_basis: CashFlowBasis | None = None
    calculation: CalculationResult | None = None


class PeerStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    valid_count: int
    unverified_count: int
    excluded_count: int
    min: Decimal
    max: Decimal
    mean: Decimal
    median: Decimal
    std_dev: Decimal | None = None
    bands: list[PercentileBand]
    data_sufficiency: DataSufficiency
    calculations: list[CalculationResult]


class TargetVsPeerPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    target_value: Decimal
    target_company_id: str
    peer_median: Decimal
    difference_from_median: Decimal
    difference_from_median_pct: Decimal | None = None
    percentile_rank: Decimal | None = None
    rank_if_inserted: int
    peer_count: int
    vs_p25: Decimal | None = None
    vs_p75: Decimal | None = None


class PeerComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    target: PeerValuationObservation
    peers: list[PeerValuationObservation]
    statistics: PeerStatistics | None = None
    position: TargetVsPeerPosition | None = None
    peer_set_metadata: PeerSetMetadata | None = None
    engine_version: str
    calculated_at: datetime


# ---------------------------------------------------------------------------
# Scenario Engine (Phase 6e.6)
# ---------------------------------------------------------------------------


class ScenarioLabel(StrEnum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


class ScenarioExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ScenarioDiagnostic(StrEnum):
    VALUE_ORDER_UNEXPECTED = "value_order_unexpected"
    IDENTICAL_ASSUMPTIONS = "identical_assumptions"
    EXTREME_SPREAD = "extreme_spread"
    MISSING_PROVENANCE = "missing_provenance"
    SCENARIO_EXECUTION_FAILED = "scenario_execution_failed"
    INCOMPLETE_COMPARISON = "incomplete_comparison"


class AssumptionProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    parameter: str
    value_description: str
    evidence_category: FindingType
    rationale: str
    source_description: str | None = None


class MultipleScenarioAssumption(BaseModel):
    model_config = ConfigDict(frozen=True)

    method: ValuationMethodType
    target_multiple: Decimal
    target_name: str
    rationale: str
    evidence_category: FindingType

    @field_validator("target_multiple")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            msg = "target_multiple must be positive"
            raise ValueError(msg)
        return v


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: ScenarioLabel
    narrative: str
    dcf_assumptions: DCFAssumptions
    multiple_assumptions: list[MultipleScenarioAssumption] | None = None
    assumption_provenance: list[AssumptionProvenance]
    probability_weight: Decimal | None = None

    @field_validator("probability_weight")
    @classmethod
    def _weight_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < Decimal("0"):
            msg = "probability_weight must be >= 0"
            raise ValueError(msg)
        return v


class SingleScenarioOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: ScenarioLabel
    narrative: str
    execution_status: ScenarioExecutionStatus
    dcf_result: DCFResult | None
    multiple_results: list[MultipleValuationResult]
    assumption_provenance: list[AssumptionProvenance]
    probability_weight: Decimal | None
    implied_value_per_share: Decimal | None
    error_message: str | None = None
    diagnostics: list[ScenarioDiagnostic]


class ScenarioComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    value_range_low: Decimal | None
    value_range_high: Decimal | None
    value_range_midpoint: Decimal | None
    probability_weighted_value: Decimal | None
    current_price: Decimal
    bear_implied_value: Decimal | None
    base_implied_value: Decimal | None
    bull_implied_value: Decimal | None
    upside_to_bear: Decimal | None
    upside_to_base: Decimal | None
    upside_to_bull: Decimal | None
    completed_scenario_count: int
    calculations: list[CalculationResult]


class ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenarios: list[SingleScenarioOutput]
    comparison: ScenarioComparison
    calculations: list[CalculationResult]
    calculated_at: datetime
    engine_version: str
    diagnostics: list[ScenarioDiagnostic]
