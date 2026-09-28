"""Tests for the screening executor — criteria → SQL condition translation."""
from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.screening import CompanyScreeningData
from app.screener.executor import build_conditions
from app.screener.schemas import (
    FilterCriterion,
    FilterGroup,
    Operator,
    ScreenDefinition,
    ScreenField,
)


def _compile(conditions: list[sa.ColumnElement[bool]]) -> str:
    """Build a SELECT with the given conditions and compile to PostgreSQL SQL."""
    query = sa.select(CompanyScreeningData)
    for cond in conditions:
        query = query.where(cond)
    compiled = query.compile(dialect=postgresql.dialect())
    return str(compiled)


def _make_screen(*groups: FilterGroup) -> ScreenDefinition:
    return ScreenDefinition(groups=tuple(groups))


def _num_criterion(
    field: ScreenField, op: Operator, value: Decimal,
    value_high: Decimal | None = None,
) -> FilterCriterion:
    return FilterCriterion(field=field, operator=op, value=value, value_high=value_high)


def _str_criterion(
    field: ScreenField, op: Operator,
    value: str | None = None, values: tuple[str, ...] | None = None,
) -> FilterCriterion:
    return FilterCriterion(field=field, operator=op, value=value, values=values)


class TestBuildConditions:
    def test_returns_list(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(_num_criterion(ScreenField.ROE, Operator.GT, Decimal("0.15")),)),
        )
        conds = build_conditions(screen)
        assert isinstance(conds, list)
        assert len(conds) == 1

    def test_multiple_groups_produce_multiple_conditions(self) -> None:
        g1 = FilterGroup(criteria=(_num_criterion(ScreenField.ROE, Operator.GT, Decimal("0.15")),))
        g2 = FilterGroup(criteria=(_num_criterion(ScreenField.PE_RATIO, Operator.LT, Decimal("20")),))
        conds = build_conditions(_make_screen(g1, g2))
        assert len(conds) == 2


class TestNumericConditions:
    def test_gt(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(_num_criterion(ScreenField.ROE, Operator.GT, Decimal("0.15")),)),
        )
        sql = _compile(build_conditions(screen))
        assert "roe >" in sql.lower()

    def test_gte(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(_num_criterion(ScreenField.ROCE, Operator.GTE, Decimal("0.12")),)),
        )
        sql = _compile(build_conditions(screen))
        assert "roce >=" in sql.lower()

    def test_lt(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(_num_criterion(ScreenField.PE_RATIO, Operator.LT, Decimal("20")),)),
        )
        sql = _compile(build_conditions(screen))
        assert "pe_ratio <" in sql.lower()

    def test_lte(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _num_criterion(ScreenField.DEBT_TO_EQUITY, Operator.LTE, Decimal("1.5")),
            )),
        )
        sql = _compile(build_conditions(screen))
        assert "debt_to_equity <=" in sql.lower()

    def test_eq(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _num_criterion(ScreenField.DIVIDEND_YIELD, Operator.EQ, Decimal("0.03")),
            )),
        )
        sql = _compile(build_conditions(screen))
        assert "dividend_yield =" in sql.lower()

    def test_between(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _num_criterion(
                    ScreenField.MARKET_CAP, Operator.BETWEEN,
                    Decimal("100000"), value_high=Decimal("500000"),
                ),
            )),
        )
        sql = _compile(build_conditions(screen))
        assert "between" in sql.lower()


class TestStringConditions:
    def test_eq(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _str_criterion(ScreenField.SECTOR, Operator.EQ, value="IT"),
            )),
        )
        sql = _compile(build_conditions(screen))
        assert "sector" in sql.lower()

    def test_in(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _str_criterion(ScreenField.SECTOR, Operator.IN, values=("IT", "Pharma")),
            )),
        )
        sql = _compile(build_conditions(screen))
        assert "in" in sql.lower()

    def test_not_in(self) -> None:
        screen = _make_screen(
            FilterGroup(criteria=(
                _str_criterion(ScreenField.INDUSTRY, Operator.NOT_IN, values=("Real Estate",)),
            )),
        )
        sql = _compile(build_conditions(screen))
        lower = sql.lower()
        assert "not" in lower or "NOT" in sql


class TestLogicOperators:
    def test_and_group(self) -> None:
        screen = _make_screen(
            FilterGroup(
                logic="AND",
                criteria=(
                    _num_criterion(ScreenField.ROE, Operator.GT, Decimal("0.15")),
                    _num_criterion(ScreenField.DEBT_TO_EQUITY, Operator.LT, Decimal("1")),
                ),
            ),
        )
        sql = _compile(build_conditions(screen))
        assert "and" in sql.lower()

    def test_or_group(self) -> None:
        screen = _make_screen(
            FilterGroup(
                logic="OR",
                criteria=(
                    _str_criterion(ScreenField.SECTOR, Operator.EQ, value="IT"),
                    _str_criterion(ScreenField.SECTOR, Operator.EQ, value="Pharma"),
                ),
            ),
        )
        sql = _compile(build_conditions(screen))
        assert "or" in sql.lower()

    def test_not_group(self) -> None:
        screen = _make_screen(
            FilterGroup(
                negate=True,
                criteria=(
                    _num_criterion(ScreenField.PROMOTER_PLEDGE, Operator.GT, Decimal("10")),
                    _num_criterion(ScreenField.PROMOTER_HOLDING, Operator.LT, Decimal("50")),
                ),
            ),
        )
        sql = _compile(build_conditions(screen))
        assert "not" in sql.lower()

    def test_combined_and_or_not(self) -> None:
        g1 = FilterGroup(
            logic="AND",
            criteria=(
                _num_criterion(ScreenField.ROE, Operator.GT, Decimal("0.15")),
                _num_criterion(ScreenField.ROCE, Operator.GT, Decimal("0.12")),
            ),
        )
        g2 = FilterGroup(
            logic="OR",
            negate=True,
            criteria=(
                _str_criterion(ScreenField.SECTOR, Operator.EQ, value="Real Estate"),
                _num_criterion(ScreenField.PROMOTER_PLEDGE, Operator.GT, Decimal("50")),
            ),
        )
        screen = _make_screen(g1, g2)
        conds = build_conditions(screen)
        assert len(conds) == 2
        sql = _compile(conds)
        assert "and" in sql.lower()
        assert "not" in sql.lower()


class TestAllFieldsCompile:
    """Verify every ScreenField produces valid SQL when used in a condition."""

    @pytest.mark.parametrize("field", list(ScreenField))
    def test_field_compiles(self, field: ScreenField) -> None:
        from app.screener.schemas import STRING_FIELDS

        if field in STRING_FIELDS:
            criterion = _str_criterion(field, Operator.EQ, value="test")
        else:
            criterion = _num_criterion(field, Operator.GT, Decimal("0"))

        screen = _make_screen(FilterGroup(criteria=(criterion,)))
        conds = build_conditions(screen)
        sql = _compile(conds)
        assert field.value in sql.lower()
