"""Tests for Stock Screener Pydantic schemas — validation, field/operator rules."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.screener.schemas import (
    NUMERIC_FIELDS,
    NUMERIC_OPERATORS,
    STRING_FIELDS,
    STRING_OPERATORS,
    AdHocScreenRequest,
    CompanyResult,
    CreateScreenRequest,
    ExecuteScreenRequest,
    FilterCriterion,
    FilterGroup,
    Operator,
    ScreenDefinition,
    ScreenField,
)


class TestScreenFieldEnum:
    def test_has_20_members(self) -> None:
        assert len(ScreenField) == 20

    def test_string_fields(self) -> None:
        assert {ScreenField.SECTOR, ScreenField.INDUSTRY} == STRING_FIELDS

    def test_numeric_fields_count(self) -> None:
        assert len(NUMERIC_FIELDS) == 18


class TestOperatorEnum:
    def test_has_8_members(self) -> None:
        assert len(Operator) == 8

    def test_numeric_operators(self) -> None:
        expected = {Operator.GT, Operator.GTE, Operator.LT, Operator.LTE, Operator.EQ, Operator.BETWEEN}
        assert expected == NUMERIC_OPERATORS

    def test_string_operators(self) -> None:
        expected = {Operator.EQ, Operator.IN, Operator.NOT_IN}
        assert expected == STRING_OPERATORS


class TestFilterCriterion:
    def test_numeric_gt(self) -> None:
        c = FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15"))
        assert c.field == ScreenField.ROE
        assert c.value == Decimal("0.15")

    def test_numeric_between(self) -> None:
        c = FilterCriterion(
            field=ScreenField.PE_RATIO, operator=Operator.BETWEEN,
            value=Decimal("10"), value_high=Decimal("25"),
        )
        assert c.value == Decimal("10")
        assert c.value_high == Decimal("25")

    def test_numeric_between_missing_high_raises(self) -> None:
        with pytest.raises(ValidationError, match="value_high"):
            FilterCriterion(
                field=ScreenField.PE_RATIO, operator=Operator.BETWEEN,
                value=Decimal("10"),
            )

    def test_numeric_missing_value_raises(self) -> None:
        with pytest.raises(ValidationError, match="requires 'value'"):
            FilterCriterion(field=ScreenField.ROE, operator=Operator.GT)

    def test_numeric_field_with_in_operator_raises(self) -> None:
        with pytest.raises(ValidationError, match="not valid for numeric"):
            FilterCriterion(
                field=ScreenField.ROE, operator=Operator.IN,
                values=("high",),
            )

    def test_numeric_field_with_not_in_raises(self) -> None:
        with pytest.raises(ValidationError, match="not valid for numeric"):
            FilterCriterion(
                field=ScreenField.MARKET_CAP, operator=Operator.NOT_IN,
                values=("large",),
            )

    def test_string_eq(self) -> None:
        c = FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="IT")
        assert c.value == "IT"

    def test_string_in(self) -> None:
        c = FilterCriterion(
            field=ScreenField.SECTOR, operator=Operator.IN,
            values=("IT", "Pharma", "Banking"),
        )
        assert c.values == ("IT", "Pharma", "Banking")

    def test_string_not_in(self) -> None:
        c = FilterCriterion(
            field=ScreenField.INDUSTRY, operator=Operator.NOT_IN,
            values=("Real Estate",),
        )
        assert c.operator == Operator.NOT_IN

    def test_string_in_empty_values_raises(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            FilterCriterion(
                field=ScreenField.SECTOR, operator=Operator.IN,
                values=(),
            )

    def test_string_field_with_gt_raises(self) -> None:
        with pytest.raises(ValidationError, match="not valid for string"):
            FilterCriterion(
                field=ScreenField.SECTOR, operator=Operator.GT,
                value="IT",
            )

    def test_string_field_with_between_raises(self) -> None:
        with pytest.raises(ValidationError, match="not valid for string"):
            FilterCriterion(
                field=ScreenField.INDUSTRY, operator=Operator.BETWEEN,
                value="A", value_high=Decimal("10"),
            )

    def test_string_eq_missing_value_raises(self) -> None:
        with pytest.raises(ValidationError, match="requires 'value'"):
            FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ)

    def test_frozen(self) -> None:
        c = FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.1"))
        with pytest.raises(ValidationError):
            c.value = Decimal("0.2")  # type: ignore[misc]

    def test_all_numeric_fields_accept_gt(self) -> None:
        for field in NUMERIC_FIELDS:
            c = FilterCriterion(field=field, operator=Operator.GT, value=Decimal("1"))
            assert c.field == field

    def test_all_string_fields_accept_in(self) -> None:
        for field in STRING_FIELDS:
            c = FilterCriterion(field=field, operator=Operator.IN, values=("x",))
            assert c.field == field


class TestFilterGroup:
    def test_and_group(self) -> None:
        g = FilterGroup(criteria=(
            FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
            FilterCriterion(field=ScreenField.DEBT_TO_EQUITY, operator=Operator.LT, value=Decimal("1.0")),
        ))
        assert g.logic == "AND"
        assert len(g.criteria) == 2
        assert g.negate is False

    def test_or_group(self) -> None:
        g = FilterGroup(
            logic="OR",
            criteria=(
                FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="IT"),
                FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="Pharma"),
            ),
        )
        assert g.logic == "OR"

    def test_negate(self) -> None:
        g = FilterGroup(
            negate=True,
            criteria=(
                FilterCriterion(field=ScreenField.PROMOTER_PLEDGE, operator=Operator.GT, value=Decimal("10")),
            ),
        )
        assert g.negate is True

    def test_empty_criteria_raises(self) -> None:
        with pytest.raises(ValidationError):
            FilterGroup(criteria=())


class TestScreenDefinition:
    def test_single_group(self) -> None:
        sd = ScreenDefinition(groups=(
            FilterGroup(criteria=(
                FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
            )),
        ))
        assert len(sd.groups) == 1

    def test_multiple_groups(self) -> None:
        g1 = FilterGroup(criteria=(
            FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
        ))
        g2 = FilterGroup(
            logic="OR",
            criteria=(
                FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="IT"),
                FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="Banking"),
            ),
        )
        sd = ScreenDefinition(groups=(g1, g2))
        assert len(sd.groups) == 2

    def test_empty_groups_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScreenDefinition(groups=())


class TestCreateScreenRequest:
    def test_valid(self) -> None:
        req = CreateScreenRequest(
            name="High ROE",
            description="Companies with ROE > 15%",
            groups=[FilterGroup(criteria=(
                FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
            ))],
        )
        assert req.name == "High ROE"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreateScreenRequest(
                name="",
                groups=[FilterGroup(criteria=(
                    FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
                ))],
            )

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreateScreenRequest(
                name="x" * 201,
                groups=[FilterGroup(criteria=(
                    FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
                ))],
            )


class TestExecuteScreenRequest:
    def test_defaults(self) -> None:
        req = ExecuteScreenRequest()
        assert req.limit == 50
        assert req.offset == 0
        assert req.sort_by is None
        assert req.sort_desc is True

    def test_custom_sort(self) -> None:
        req = ExecuteScreenRequest(sort_by=ScreenField.MARKET_CAP, sort_desc=False)
        assert req.sort_by == ScreenField.MARKET_CAP

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ExecuteScreenRequest(limit=0)
        with pytest.raises(ValidationError):
            ExecuteScreenRequest(limit=501)


class TestAdHocScreenRequest:
    def test_valid(self) -> None:
        req = AdHocScreenRequest(
            groups=[FilterGroup(criteria=(
                FilterCriterion(field=ScreenField.PE_RATIO, operator=Operator.LT, value=Decimal("20")),
            ))],
            sort_by=ScreenField.PE_RATIO,
        )
        assert req.sort_by == ScreenField.PE_RATIO


class TestCompanyResult:
    def test_frozen(self) -> None:
        cr = CompanyResult(
            company_id="abc", symbol="TCS", company_name="TCS Ltd",
            exchange="NSE", data_period="FY2025",
        )
        with pytest.raises(ValidationError):
            cr.symbol = "INFY"  # type: ignore[misc]


class TestSerializationRoundTrip:
    def test_filter_criterion_json(self) -> None:
        c = FilterCriterion(
            field=ScreenField.ROE, operator=Operator.BETWEEN,
            value=Decimal("0.10"), value_high=Decimal("0.25"),
        )
        data = c.model_dump(mode="json")
        restored = FilterCriterion(**data)
        assert restored.field == c.field
        assert restored.operator == c.operator
        assert Decimal(str(restored.value)) == Decimal(str(c.value))
        assert restored.value_high == c.value_high

    def test_filter_group_json(self) -> None:
        g = FilterGroup(
            logic="OR", negate=True,
            criteria=(
                FilterCriterion(field=ScreenField.SECTOR, operator=Operator.IN, values=("IT", "Pharma")),
            ),
        )
        data = g.model_dump(mode="json")
        restored = FilterGroup(**data)
        assert restored == g

    def test_screen_definition_json(self) -> None:
        sd = ScreenDefinition(groups=(
            FilterGroup(criteria=(
                FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
                FilterCriterion(field=ScreenField.DEBT_TO_EQUITY, operator=Operator.LT, value=Decimal("1")),
            )),
        ))
        data = sd.model_dump(mode="json")
        restored = ScreenDefinition(**data)
        assert len(restored.groups) == 1
        assert len(restored.groups[0].criteria) == 2
