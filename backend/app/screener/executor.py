"""Translates screening criteria into SQLAlchemy WHERE conditions.

Every condition targets a column on ``CompanyScreeningData``.  The mapping
from ``ScreenField`` enum values to column names is 1-to-1 by design.
"""
from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from app.models.screening import CompanyScreeningData
from app.screener.schemas import (
    STRING_FIELDS,
    FilterCriterion,
    FilterGroup,
    Operator,
    ScreenDefinition,
)


def build_conditions(
    screen: ScreenDefinition,
) -> list[sa.ColumnElement[bool]]:
    """Return a list of SQLAlchemy conditions — one per filter group."""
    return [_build_group(g) for g in screen.groups]


def _build_group(group: FilterGroup) -> sa.ColumnElement[bool]:
    parts = [_build_criterion(c) for c in group.criteria]
    combined = sa.and_(*parts) if group.logic == "AND" else sa.or_(*parts)
    if group.negate:
        combined = sa.not_(combined)
    return combined


def _build_criterion(criterion: FilterCriterion) -> sa.ColumnElement[bool]:
    # ScreenField values match CompanyScreeningData column names exactly
    col = getattr(CompanyScreeningData, criterion.field.value)

    if criterion.field in STRING_FIELDS:
        return _string_condition(col, criterion)
    return _numeric_condition(col, criterion)


def _string_condition(
    col: sa.orm.attributes.QueryableAttribute[str | None],
    criterion: FilterCriterion,
) -> sa.ColumnElement[bool]:
    op = criterion.operator
    if op == Operator.EQ:
        return col == str(criterion.value)
    if op == Operator.IN:
        return col.in_(list(criterion.values or ()))
    if op == Operator.NOT_IN:
        return ~col.in_(list(criterion.values or ()))
    msg = f"Unsupported string operator: {op}"
    raise ValueError(msg)


def _numeric_condition(
    col: sa.orm.attributes.QueryableAttribute[Decimal | None],
    criterion: FilterCriterion,
) -> sa.ColumnElement[bool]:
    val = Decimal(str(criterion.value))
    op = criterion.operator
    if op == Operator.GT:
        return col > val
    if op == Operator.GTE:
        return col >= val
    if op == Operator.LT:
        return col < val
    if op == Operator.LTE:
        return col <= val
    if op == Operator.EQ:
        return col == val
    if op == Operator.BETWEEN:
        val_high = Decimal(str(criterion.value_high))
        return col.between(val, val_high)
    msg = f"Unsupported numeric operator: {op}"
    raise ValueError(msg)
