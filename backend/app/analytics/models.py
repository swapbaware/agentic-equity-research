"""Core models for the Financial Analytics Engine.

All monetary and ratio calculations use decimal.Decimal — never float.
Every CalculationResult retains inputs, period, formula, version, and output.
"""
from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs at runtime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict

RATIO_QUANTIZE = Decimal("0.000001")
DAYS_QUANTIZE = Decimal("0.01")
ROUNDING = ROUND_HALF_UP
COMPUTATION_PRECISION = 50


class CalculationResult(BaseModel):
    """Immutable record of a single financial metric calculation."""

    model_config = ConfigDict(frozen=True)

    metric: str
    value: Decimal | None
    inputs: dict[str, Decimal | str | int | None]
    period: str
    formula: str
    version: str
    unit: str
    notes: str | None = None


class PeriodFinancials(BaseModel):
    """Financial data for a single reporting period."""

    model_config = ConfigDict(frozen=True)

    period: str

    # Income Statement
    revenue: Decimal | None = None
    cost_of_goods_sold: Decimal | None = None
    gross_profit: Decimal | None = None
    ebitda: Decimal | None = None
    depreciation_amortization: Decimal | None = None
    ebit: Decimal | None = None
    interest_expense: Decimal | None = None
    profit_before_tax: Decimal | None = None
    tax_expense: Decimal | None = None
    pat: Decimal | None = None

    # Balance Sheet
    total_equity: Decimal | None = None
    total_debt: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    current_assets: Decimal | None = None
    current_liabilities: Decimal | None = None
    total_assets: Decimal | None = None
    accounts_receivable: Decimal | None = None
    inventory: Decimal | None = None
    accounts_payable: Decimal | None = None
    capital_employed: Decimal | None = None

    # Cash Flow Statement
    cfo: Decimal | None = None
    capex: Decimal | None = None

    # Per Share
    eps: Decimal | None = None
    shares_outstanding: Decimal | None = None

    # Derived / Provided
    effective_tax_rate: Decimal | None = None


class AnalyticsReport(BaseModel):
    """Complete analytics output for a company across periods."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    calculations: list[CalculationResult]
    periods_analyzed: list[str]
    generated_at: datetime
