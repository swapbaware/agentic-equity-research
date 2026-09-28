"""Pydantic schemas for the Stock Screener.

Defines 20 screening fields, 8 operators, and filter validation rules.
String fields (sector/industry) accept set operators; numeric fields accept
comparison operators. All numeric values use ``decimal.Decimal``.
"""
from __future__ import annotations

from datetime import datetime  # noqa: TC003
from decimal import Decimal  # noqa: TC003
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ScreenField(StrEnum):
    """All 20 supported screening criteria."""

    SECTOR = "sector"
    INDUSTRY = "industry"
    MARKET_CAP = "market_cap"
    REVENUE_GROWTH = "revenue_growth"
    EPS_GROWTH = "eps_growth"
    ROE = "roe"
    ROCE = "roce"
    ROIC = "roic"
    DEBT_TO_EQUITY = "debt_to_equity"
    NET_DEBT_TO_EBITDA = "net_debt_to_ebitda"
    FCF_YIELD = "fcf_yield"
    PE_RATIO = "pe_ratio"
    EV_TO_EBITDA = "ev_to_ebitda"
    PEG_RATIO = "peg_ratio"
    DIVIDEND_YIELD = "dividend_yield"
    PROMOTER_HOLDING = "promoter_holding"
    PROMOTER_PLEDGE = "promoter_pledge"
    INSTITUTIONAL_OWNERSHIP = "institutional_ownership"
    EBITDA_MARGIN = "ebitda_margin"
    FCF_CONVERSION = "fcf_conversion"


class Operator(StrEnum):
    """Filter comparison operators."""

    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"


# ---------------------------------------------------------------------------
# Field / operator classification
# ---------------------------------------------------------------------------

STRING_FIELDS: frozenset[ScreenField] = frozenset({
    ScreenField.SECTOR,
    ScreenField.INDUSTRY,
})

NUMERIC_FIELDS: frozenset[ScreenField] = frozenset(ScreenField) - STRING_FIELDS

NUMERIC_OPERATORS: frozenset[Operator] = frozenset({
    Operator.GT,
    Operator.GTE,
    Operator.LT,
    Operator.LTE,
    Operator.EQ,
    Operator.BETWEEN,
})

STRING_OPERATORS: frozenset[Operator] = frozenset({
    Operator.EQ,
    Operator.IN,
    Operator.NOT_IN,
})


# ---------------------------------------------------------------------------
# Filter building blocks
# ---------------------------------------------------------------------------


class FilterCriterion(BaseModel):
    """A single filter condition: field + operator + value(s)."""

    model_config = ConfigDict(frozen=True)

    field: ScreenField
    operator: Operator
    value: Decimal | str | None = None
    value_high: Decimal | None = None
    values: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _validate_criterion(self) -> Self:
        if self.field in STRING_FIELDS:
            if self.operator not in STRING_OPERATORS:
                msg = (
                    f"Operator '{self.operator}' is not valid for "
                    f"string field '{self.field}'; use one of {sorted(STRING_OPERATORS)}"
                )
                raise ValueError(msg)
            if self.operator in {Operator.IN, Operator.NOT_IN}:
                if not self.values:
                    msg = f"Operator '{self.operator}' requires a non-empty 'values' list"
                    raise ValueError(msg)
            elif self.value is None:
                msg = f"Operator '{self.operator}' requires 'value'"
                raise ValueError(msg)
        else:
            if self.operator not in NUMERIC_OPERATORS:
                msg = (
                    f"Operator '{self.operator}' is not valid for "
                    f"numeric field '{self.field}'; use one of {sorted(NUMERIC_OPERATORS)}"
                )
                raise ValueError(msg)
            if self.value is None:
                msg = f"Operator '{self.operator}' requires 'value'"
                raise ValueError(msg)
            if self.operator == Operator.BETWEEN and self.value_high is None:
                msg = "Operator 'between' requires 'value_high'"
                raise ValueError(msg)
        return self


class FilterGroup(BaseModel):
    """A group of criteria combined by AND/OR, optionally negated (NOT)."""

    model_config = ConfigDict(frozen=True)

    logic: Literal["AND", "OR"] = "AND"
    negate: bool = False
    criteria: tuple[FilterCriterion, ...] = Field(min_length=1)


class ScreenDefinition(BaseModel):
    """Complete screen: one or more filter groups (groups are ANDed together)."""

    model_config = ConfigDict(frozen=True)

    groups: tuple[FilterGroup, ...] = Field(min_length=1)


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class CreateScreenRequest(BaseModel):
    """POST /screens request body."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    groups: list[FilterGroup] = Field(min_length=1)


class ExecuteScreenRequest(BaseModel):
    """POST /screens/{id}/execute or POST /screens/execute request body."""

    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: ScreenField | None = None
    sort_desc: bool = True


class AdHocScreenRequest(BaseModel):
    """POST /screens/execute — execute without saving."""

    groups: list[FilterGroup] = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: ScreenField | None = None
    sort_desc: bool = True


class CompanyResult(BaseModel):
    """A single company row returned from a screen execution."""

    model_config = ConfigDict(frozen=True)

    company_id: str
    symbol: str
    company_name: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    ev_to_ebitda: Decimal | None = None
    peg_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    revenue_growth: Decimal | None = None
    eps_growth: Decimal | None = None
    roe: Decimal | None = None
    roce: Decimal | None = None
    roic: Decimal | None = None
    ebitda_margin: Decimal | None = None
    debt_to_equity: Decimal | None = None
    net_debt_to_ebitda: Decimal | None = None
    fcf_yield: Decimal | None = None
    fcf_conversion: Decimal | None = None
    promoter_holding: Decimal | None = None
    promoter_pledge: Decimal | None = None
    institutional_ownership: Decimal | None = None
    data_period: str


class ScreenExecutionResult(BaseModel):
    """Result of executing a screen."""

    model_config = ConfigDict(frozen=True)

    screen_id: str | None = None
    total_matches: int
    companies: list[CompanyResult]


class SavedScreenResponse(BaseModel):
    """GET /screens response item."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str | None = None
    groups: list[FilterGroup]
    created_at: datetime
    updated_at: datetime
