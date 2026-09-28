"""Tests for return on capital calculations: ROE, ROCE, ROIC."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import PeriodFinancials
from app.analytics.returns import VERSION, roce, roe, roic


def _bs(
    *,
    name: str = "FY2024",
    pat: Decimal | None = None,
    ebit: Decimal | None = None,
    total_equity: Decimal | None = None,
    total_assets: Decimal | None = None,
    current_liabilities: Decimal | None = None,
    capital_employed: Decimal | None = None,
    total_debt: Decimal | None = None,
    cash_and_equivalents: Decimal | None = None,
    effective_tax_rate: Decimal | None = None,
) -> PeriodFinancials:
    return PeriodFinancials(
        period=name, pat=pat, ebit=ebit, total_equity=total_equity,
        total_assets=total_assets, current_liabilities=current_liabilities,
        capital_employed=capital_employed, total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        effective_tax_rate=effective_tax_rate,
    )


class TestROE:
    def test_basic(self) -> None:
        curr = _bs(pat=Decimal("100"), total_equity=Decimal("500"))
        prev = _bs(total_equity=Decimal("500"), name="FY2023")
        result = roe(curr, prev)
        assert result.value == Decimal("0.200000")
        assert result.metric == "roe"

    def test_different_equities_averaged(self) -> None:
        curr = _bs(pat=Decimal("100"), total_equity=Decimal("600"))
        prev = _bs(total_equity=Decimal("400"), name="FY2023")
        # avg equity = 500, ROE = 100/500 = 0.2
        result = roe(curr, prev)
        assert result.value == Decimal("0.200000")

    def test_zero_equity(self) -> None:
        curr = _bs(pat=Decimal("100"), total_equity=Decimal("0"))
        prev = _bs(total_equity=Decimal("0"), name="FY2023")
        result = roe(curr, prev)
        assert result.value is None
        assert "division by zero" in str(result.notes)

    def test_missing_pat(self) -> None:
        curr = _bs(total_equity=Decimal("500"))
        prev = _bs(total_equity=Decimal("500"), name="FY2023")
        result = roe(curr, prev)
        assert result.value is None

    def test_negative_roe(self) -> None:
        curr = _bs(pat=Decimal("-50"), total_equity=Decimal("500"))
        prev = _bs(total_equity=Decimal("500"), name="FY2023")
        result = roe(curr, prev)
        assert result.value == Decimal("-0.100000")

    def test_inputs_record_average(self) -> None:
        curr = _bs(pat=Decimal("100"), total_equity=Decimal("600"))
        prev = _bs(total_equity=Decimal("400"), name="FY2023")
        result = roe(curr, prev)
        assert result.inputs["average_equity"] == Decimal("500")


class TestROCE:
    def test_basic_with_capital_employed(self) -> None:
        curr = _bs(ebit=Decimal("150"), capital_employed=Decimal("750"))
        prev = _bs(capital_employed=Decimal("750"), name="FY2023")
        result = roce(curr, prev)
        assert result.value == Decimal("0.200000")
        assert result.metric == "roce"

    def test_derived_from_total_assets(self) -> None:
        curr = _bs(
            ebit=Decimal("150"),
            total_assets=Decimal("1200"), current_liabilities=Decimal("400"),
        )
        prev = _bs(
            total_assets=Decimal("1100"), current_liabilities=Decimal("400"),
            name="FY2023",
        )
        # CE curr = 800, CE prev = 700, avg = 750, ROCE = 150/750 = 0.2
        result = roce(curr, prev)
        assert result.value == Decimal("0.200000")

    def test_missing_data(self) -> None:
        curr = _bs(ebit=Decimal("150"))
        prev = _bs(name="FY2023")
        result = roce(curr, prev)
        assert result.value is None


class TestROIC:
    def test_basic(self) -> None:
        curr = _bs(
            ebit=Decimal("200"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        prev = _bs(
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"), name="FY2023",
        )
        # NOPAT = 200 * 0.75 = 150, IC = 800+300-100 = 1000, avg=1000
        result = roic(curr, prev)
        assert result.value == Decimal("0.150000")
        assert result.metric == "roic"

    def test_nopat_recorded_in_inputs(self) -> None:
        curr = _bs(
            ebit=Decimal("200"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        prev = _bs(
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"), name="FY2023",
        )
        result = roic(curr, prev)
        assert result.inputs["nopat"] == Decimal("150.00")

    def test_missing_tax_rate(self) -> None:
        curr = _bs(
            ebit=Decimal("200"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        prev = _bs(
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"), name="FY2023",
        )
        result = roic(curr, prev)
        assert result.value is None

    def test_version_tracked(self) -> None:
        curr = _bs(
            ebit=Decimal("200"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("500"), total_debt=Decimal("200"),
            cash_and_equivalents=Decimal("50"),
        )
        prev = _bs(
            total_equity=Decimal("500"), total_debt=Decimal("200"),
            cash_and_equivalents=Decimal("50"), name="FY2023",
        )
        result = roic(curr, prev)
        assert result.version == VERSION
