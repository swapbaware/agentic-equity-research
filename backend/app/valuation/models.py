"""Pydantic models for the DCF Valuation Engine.

Every assumption is an explicit field — no hidden defaults. All financial
values use decimal.Decimal. Models are frozen for immutability.
"""
from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs at runtime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.analytics.models import CalculationResult


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
