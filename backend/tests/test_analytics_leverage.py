"""Tests for leverage and solvency ratio calculations."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.leverage import (
    VERSION,
    current_ratio,
    debt_to_equity,
    interest_coverage,
    net_debt_to_ebitda,
)
from app.analytics.models import PeriodFinancials


def _period(**kwargs: Decimal | str | None) -> PeriodFinancials:
    return PeriodFinancials(period=str(kwargs.pop("name", "FY2024")), **kwargs)  # type: ignore[arg-type]


class TestDebtToEquity:
    def test_basic(self) -> None:
        p = _period(total_debt=Decimal("500"), total_equity=Decimal("1000"))
        result = debt_to_equity(p)
        assert result.value == Decimal("0.500000")
        assert result.metric == "debt_to_equity"

    def test_zero_equity(self) -> None:
        p = _period(total_debt=Decimal("500"), total_equity=Decimal("0"))
        result = debt_to_equity(p)
        assert result.value is None

    def test_no_debt(self) -> None:
        p = _period(total_debt=Decimal("0"), total_equity=Decimal("1000"))
        result = debt_to_equity(p)
        assert result.value == Decimal("0.000000")

    def test_missing(self) -> None:
        p = _period(total_debt=Decimal("500"))
        result = debt_to_equity(p)
        assert result.value is None


class TestNetDebtToEbitda:
    def test_basic(self) -> None:
        p = _period(
            total_debt=Decimal("500"),
            cash_and_equivalents=Decimal("100"),
            ebitda=Decimal("200"),
        )
        # net debt = 400, ratio = 400/200 = 2.0
        result = net_debt_to_ebitda(p)
        assert result.value == Decimal("2.000000")
        assert result.metric == "net_debt_to_ebitda"

    def test_negative_net_debt(self) -> None:
        p = _period(
            total_debt=Decimal("100"),
            cash_and_equivalents=Decimal("500"),
            ebitda=Decimal("200"),
        )
        # net debt = -400, ratio = -400/200 = -2.0
        result = net_debt_to_ebitda(p)
        assert result.value == Decimal("-2.000000")

    def test_zero_ebitda(self) -> None:
        p = _period(
            total_debt=Decimal("500"),
            cash_and_equivalents=Decimal("100"),
            ebitda=Decimal("0"),
        )
        result = net_debt_to_ebitda(p)
        assert result.value is None

    def test_net_debt_in_inputs(self) -> None:
        p = _period(
            total_debt=Decimal("500"),
            cash_and_equivalents=Decimal("100"),
            ebitda=Decimal("200"),
        )
        result = net_debt_to_ebitda(p)
        assert result.inputs["net_debt"] == Decimal("400")


class TestInterestCoverage:
    def test_basic(self) -> None:
        p = _period(ebit=Decimal("200"), interest_expense=Decimal("40"))
        result = interest_coverage(p)
        assert result.value == Decimal("5.000000")
        assert result.metric == "interest_coverage"

    def test_zero_interest(self) -> None:
        p = _period(ebit=Decimal("200"), interest_expense=Decimal("0"))
        result = interest_coverage(p)
        assert result.value is None

    def test_missing(self) -> None:
        p = _period(ebit=Decimal("200"))
        result = interest_coverage(p)
        assert result.value is None

    def test_low_coverage(self) -> None:
        p = _period(ebit=Decimal("50"), interest_expense=Decimal("100"))
        result = interest_coverage(p)
        assert result.value == Decimal("0.500000")


class TestCurrentRatio:
    def test_basic(self) -> None:
        p = _period(
            current_assets=Decimal("500"),
            current_liabilities=Decimal("250"),
        )
        result = current_ratio(p)
        assert result.value == Decimal("2.000000")
        assert result.metric == "current_ratio"

    def test_below_one(self) -> None:
        p = _period(
            current_assets=Decimal("200"),
            current_liabilities=Decimal("400"),
        )
        result = current_ratio(p)
        assert result.value == Decimal("0.500000")

    def test_zero_liabilities(self) -> None:
        p = _period(
            current_assets=Decimal("500"),
            current_liabilities=Decimal("0"),
        )
        result = current_ratio(p)
        assert result.value is None


class TestLeverageMetadata:
    def test_version_and_unit(self) -> None:
        p = _period(total_debt=Decimal("500"), total_equity=Decimal("1000"))
        result = debt_to_equity(p)
        assert result.version == VERSION
        assert result.unit == "ratio"
