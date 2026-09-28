"""Tests for profitability margin calculations."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.margins import (
    VERSION,
    ebit_margin,
    ebitda_margin,
    gross_margin,
    net_margin,
)
from app.analytics.models import PeriodFinancials


def _period(**kwargs: Decimal | str | None) -> PeriodFinancials:
    return PeriodFinancials(period=str(kwargs.pop("name", "FY2024")), **kwargs)  # type: ignore[arg-type]


class TestGrossMargin:
    def test_basic(self) -> None:
        p = _period(revenue=Decimal("1000"), gross_profit=Decimal("400"))
        result = gross_margin(p)
        assert result.value == Decimal("0.400000")
        assert result.metric == "gross_margin"

    def test_derived_from_cogs(self) -> None:
        p = _period(
            revenue=Decimal("1000"), cost_of_goods_sold=Decimal("600"),
        )
        result = gross_margin(p)
        assert result.value == Decimal("0.400000")

    def test_gross_profit_preferred_over_derivation(self) -> None:
        p = _period(
            revenue=Decimal("1000"),
            gross_profit=Decimal("350"),
            cost_of_goods_sold=Decimal("600"),
        )
        result = gross_margin(p)
        assert result.value == Decimal("0.350000")

    def test_zero_revenue(self) -> None:
        p = _period(revenue=Decimal("0"), gross_profit=Decimal("400"))
        result = gross_margin(p)
        assert result.value is None
        assert "division by zero" in str(result.notes)

    def test_negative_margin(self) -> None:
        p = _period(revenue=Decimal("1000"), gross_profit=Decimal("-100"))
        result = gross_margin(p)
        assert result.value == Decimal("-0.100000")

    def test_missing_data(self) -> None:
        p = _period(revenue=Decimal("1000"))
        result = gross_margin(p)
        assert result.value is None
        assert "missing" in str(result.notes)


class TestEbitdaMargin:
    def test_basic(self) -> None:
        p = _period(revenue=Decimal("1000"), ebitda=Decimal("250"))
        result = ebitda_margin(p)
        assert result.value == Decimal("0.250000")
        assert result.metric == "ebitda_margin"

    def test_high_margin(self) -> None:
        p = _period(revenue=Decimal("500"), ebitda=Decimal("400"))
        result = ebitda_margin(p)
        assert result.value == Decimal("0.800000")

    def test_missing_ebitda(self) -> None:
        p = _period(revenue=Decimal("1000"))
        result = ebitda_margin(p)
        assert result.value is None


class TestEbitMargin:
    def test_basic(self) -> None:
        p = _period(revenue=Decimal("2000"), ebit=Decimal("300"))
        result = ebit_margin(p)
        assert result.value == Decimal("0.150000")
        assert result.metric == "ebit_margin"

    def test_missing(self) -> None:
        p = _period(revenue=Decimal("2000"))
        result = ebit_margin(p)
        assert result.value is None


class TestNetMargin:
    def test_basic(self) -> None:
        p = _period(revenue=Decimal("1000"), pat=Decimal("150"))
        result = net_margin(p)
        assert result.value == Decimal("0.150000")
        assert result.metric == "net_margin"

    def test_loss(self) -> None:
        p = _period(revenue=Decimal("1000"), pat=Decimal("-50"))
        result = net_margin(p)
        assert result.value == Decimal("-0.050000")

    def test_missing_pat(self) -> None:
        p = _period(revenue=Decimal("1000"))
        result = net_margin(p)
        assert result.value is None


class TestMarginMetadata:
    def test_period_tracked(self) -> None:
        p = _period(
            name="FY2023", revenue=Decimal("1000"), ebitda=Decimal("250"),
        )
        result = ebitda_margin(p)
        assert result.period == "FY2023"

    def test_inputs_recorded(self) -> None:
        p = _period(revenue=Decimal("800"), ebitda=Decimal("200"))
        result = ebitda_margin(p)
        assert result.inputs["ebitda"] == Decimal("200")
        assert result.inputs["revenue"] == Decimal("800")

    def test_version_tracked(self) -> None:
        p = _period(revenue=Decimal("1000"), pat=Decimal("100"))
        result = net_margin(p)
        assert result.version == VERSION
