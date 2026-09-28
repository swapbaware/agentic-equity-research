"""Tests for cash flow metric calculations."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.cashflow import (
    VERSION,
    capex_to_revenue,
    cfo_to_pat,
    fcf_to_pat,
    free_cash_flow,
    operating_cash_flow,
)
from app.analytics.models import PeriodFinancials


def _period(**kwargs: Decimal | str | None) -> PeriodFinancials:
    return PeriodFinancials(period=str(kwargs.pop("name", "FY2024")), **kwargs)  # type: ignore[arg-type]


class TestOperatingCashFlow:
    def test_basic(self) -> None:
        p = _period(cfo=Decimal("200"))
        result = operating_cash_flow(p)
        assert result.value == Decimal("200")
        assert result.metric == "cfo"
        assert result.unit == "currency"

    def test_missing(self) -> None:
        p = _period()
        result = operating_cash_flow(p)
        assert result.value is None
        assert result.notes is not None

    def test_negative_cfo(self) -> None:
        p = _period(cfo=Decimal("-50"))
        result = operating_cash_flow(p)
        assert result.value == Decimal("-50")


class TestFreeCashFlow:
    def test_basic(self) -> None:
        p = _period(cfo=Decimal("200"), capex=Decimal("80"))
        result = free_cash_flow(p)
        assert result.value == Decimal("120")
        assert result.metric == "fcf"

    def test_negative_fcf(self) -> None:
        p = _period(cfo=Decimal("50"), capex=Decimal("100"))
        result = free_cash_flow(p)
        assert result.value == Decimal("-50")

    def test_missing_capex(self) -> None:
        p = _period(cfo=Decimal("200"))
        result = free_cash_flow(p)
        assert result.value is None

    def test_inputs_recorded(self) -> None:
        p = _period(cfo=Decimal("200"), capex=Decimal("80"))
        result = free_cash_flow(p)
        assert result.inputs["cfo"] == Decimal("200")
        assert result.inputs["capex"] == Decimal("80")


class TestCfoToPat:
    def test_basic(self) -> None:
        p = _period(cfo=Decimal("200"), pat=Decimal("100"))
        result = cfo_to_pat(p)
        assert result.value == Decimal("2.000000")
        assert result.metric == "cfo_to_pat"

    def test_zero_pat(self) -> None:
        p = _period(cfo=Decimal("200"), pat=Decimal("0"))
        result = cfo_to_pat(p)
        assert result.value is None

    def test_missing(self) -> None:
        p = _period(cfo=Decimal("200"))
        result = cfo_to_pat(p)
        assert result.value is None


class TestFcfToPat:
    def test_basic(self) -> None:
        p = _period(
            cfo=Decimal("200"), capex=Decimal("80"), pat=Decimal("100"),
        )
        # FCF = 120, ratio = 120/100 = 1.2
        result = fcf_to_pat(p)
        assert result.value == Decimal("1.200000")
        assert result.metric == "fcf_to_pat"

    def test_loss_period(self) -> None:
        p = _period(
            cfo=Decimal("50"), capex=Decimal("30"), pat=Decimal("-20"),
        )
        # FCF = 20, ratio = 20 / -20 = -1.0
        result = fcf_to_pat(p)
        assert result.value == Decimal("-1.000000")

    def test_fcf_recorded_in_inputs(self) -> None:
        p = _period(
            cfo=Decimal("200"), capex=Decimal("80"), pat=Decimal("100"),
        )
        result = fcf_to_pat(p)
        assert result.inputs["fcf"] == Decimal("120")


class TestCapexToRevenue:
    def test_basic(self) -> None:
        p = _period(capex=Decimal("80"), revenue=Decimal("1000"))
        result = capex_to_revenue(p)
        assert result.value == Decimal("0.080000")
        assert result.metric == "capex_to_revenue"

    def test_missing(self) -> None:
        p = _period(revenue=Decimal("1000"))
        result = capex_to_revenue(p)
        assert result.value is None


class TestCashflowMetadata:
    def test_version_tracked(self) -> None:
        p = _period(cfo=Decimal("200"), capex=Decimal("80"))
        result = free_cash_flow(p)
        assert result.version == VERSION

    def test_period_tracked(self) -> None:
        p = _period(name="FY2023", cfo=Decimal("100"))
        result = operating_cash_flow(p)
        assert result.period == "FY2023"
