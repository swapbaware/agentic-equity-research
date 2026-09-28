"""Tests for working capital and efficiency calculations."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.efficiency import (
    VERSION,
    cash_conversion_cycle,
    inventory_days,
    payable_days,
    receivable_days,
    working_capital,
)
from app.analytics.models import PeriodFinancials


def _period(**kwargs: Decimal | str | None) -> PeriodFinancials:
    return PeriodFinancials(period=str(kwargs.pop("name", "FY2024")), **kwargs)  # type: ignore[arg-type]


class TestWorkingCapital:
    def test_basic(self) -> None:
        p = _period(
            current_assets=Decimal("500"),
            current_liabilities=Decimal("300"),
        )
        result = working_capital(p)
        assert result.value == Decimal("200")
        assert result.metric == "working_capital"
        assert result.unit == "currency"

    def test_negative(self) -> None:
        p = _period(
            current_assets=Decimal("200"),
            current_liabilities=Decimal("400"),
        )
        result = working_capital(p)
        assert result.value == Decimal("-200")

    def test_missing(self) -> None:
        p = _period(current_assets=Decimal("500"))
        result = working_capital(p)
        assert result.value is None


class TestReceivableDays:
    def test_basic(self) -> None:
        # (100 / 1000) * 365 = 36.50
        p = _period(
            accounts_receivable=Decimal("100"), revenue=Decimal("1000"),
        )
        result = receivable_days(p)
        assert result.value == Decimal("36.50")
        assert result.unit == "days"

    def test_zero_revenue(self) -> None:
        p = _period(
            accounts_receivable=Decimal("100"), revenue=Decimal("0"),
        )
        result = receivable_days(p)
        assert result.value is None

    def test_missing(self) -> None:
        p = _period(revenue=Decimal("1000"))
        result = receivable_days(p)
        assert result.value is None


class TestInventoryDays:
    def test_basic(self) -> None:
        # (150 / 600) * 365 = 91.25
        p = _period(
            inventory=Decimal("150"), cost_of_goods_sold=Decimal("600"),
        )
        result = inventory_days(p)
        assert result.value == Decimal("91.25")

    def test_zero_cogs(self) -> None:
        p = _period(
            inventory=Decimal("150"), cost_of_goods_sold=Decimal("0"),
        )
        result = inventory_days(p)
        assert result.value is None


class TestPayableDays:
    def test_basic(self) -> None:
        # (80 / 600) * 365 = 48.6666... → 48.67
        p = _period(
            accounts_payable=Decimal("80"),
            cost_of_goods_sold=Decimal("600"),
        )
        result = payable_days(p)
        assert result.value == Decimal("48.67")

    def test_missing(self) -> None:
        p = _period(cost_of_goods_sold=Decimal("600"))
        result = payable_days(p)
        assert result.value is None


class TestCashConversionCycle:
    def test_basic(self) -> None:
        # recv=36.50, inv=91.25, pay=48.67 → CCC = 79.08
        p = _period(
            accounts_receivable=Decimal("100"),
            revenue=Decimal("1000"),
            inventory=Decimal("150"),
            cost_of_goods_sold=Decimal("600"),
            accounts_payable=Decimal("80"),
        )
        result = cash_conversion_cycle(p)
        assert result.value == Decimal("79.08")
        assert result.metric == "cash_conversion_cycle"

    def test_negative_cycle(self) -> None:
        # Large payable days: AP=300, COGS=600 → pay=182.50
        # recv=36.50, inv=91.25, pay=182.50 → CCC = -54.75
        p = _period(
            accounts_receivable=Decimal("100"),
            revenue=Decimal("1000"),
            inventory=Decimal("150"),
            cost_of_goods_sold=Decimal("600"),
            accounts_payable=Decimal("300"),
        )
        result = cash_conversion_cycle(p)
        assert result.value == Decimal("-54.75")

    def test_partial_missing(self) -> None:
        p = _period(
            accounts_receivable=Decimal("100"),
            revenue=Decimal("1000"),
        )
        result = cash_conversion_cycle(p)
        assert result.value is None
        assert "inventory_days" in str(result.notes)

    def test_inputs_contain_component_days(self) -> None:
        p = _period(
            accounts_receivable=Decimal("100"),
            revenue=Decimal("1000"),
            inventory=Decimal("150"),
            cost_of_goods_sold=Decimal("600"),
            accounts_payable=Decimal("80"),
        )
        result = cash_conversion_cycle(p)
        assert result.inputs["receivable_days"] == Decimal("36.50")
        assert result.inputs["inventory_days"] == Decimal("91.25")
        assert result.inputs["payable_days"] == Decimal("48.67")


class TestEfficiencyMetadata:
    def test_version_tracked(self) -> None:
        p = _period(
            current_assets=Decimal("500"),
            current_liabilities=Decimal("300"),
        )
        result = working_capital(p)
        assert result.version == VERSION

    def test_period_tracked(self) -> None:
        p = _period(
            name="FY2023",
            current_assets=Decimal("500"),
            current_liabilities=Decimal("300"),
        )
        result = working_capital(p)
        assert result.period == "FY2023"
