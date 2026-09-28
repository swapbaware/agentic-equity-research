"""Tests for earnings quality metrics: ROIIC and Earnings Consistency."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import PeriodFinancials
from app.analytics.quality import (
    VERSION,
    earnings_consistency,
    return_on_incremental_capital,
)


def _bs(
    *,
    name: str = "FY2024",
    ebit: Decimal | None = None,
    effective_tax_rate: Decimal | None = None,
    total_equity: Decimal | None = None,
    total_debt: Decimal | None = None,
    cash_and_equivalents: Decimal | None = None,
    pat: Decimal | None = None,
) -> PeriodFinancials:
    return PeriodFinancials(
        period=name, ebit=ebit, effective_tax_rate=effective_tax_rate,
        total_equity=total_equity, total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents, pat=pat,
    )


class TestReturnOnIncrementalCapital:
    def test_basic(self) -> None:
        prev = _bs(
            name="FY2023", ebit=Decimal("180"),
            effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("350"),
            cash_and_equivalents=Decimal("100"),
        )
        curr = _bs(
            ebit=Decimal("200"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("900"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        # NOPAT prev = 180*0.75 = 135, curr = 200*0.75 = 150
        # IC prev = 800+350-100 = 1050, curr = 900+300-100 = 1100
        # ROIIC = (150-135)/(1100-1050) = 15/50 = 0.3
        result = return_on_incremental_capital(curr, prev)
        assert result.value == Decimal("0.300000")
        assert result.metric == "return_on_incremental_capital"

    def test_no_change_in_invested_capital(self) -> None:
        prev = _bs(
            name="FY2023", ebit=Decimal("180"),
            effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        curr = _bs(
            ebit=Decimal("200"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        result = return_on_incremental_capital(curr, prev)
        assert result.value is None
        assert "no change" in str(result.notes)

    def test_missing_data(self) -> None:
        prev = _bs(name="FY2023", ebit=Decimal("180"))
        curr = _bs(ebit=Decimal("200"))
        result = return_on_incremental_capital(curr, prev)
        assert result.value is None

    def test_negative_roiic(self) -> None:
        prev = _bs(
            name="FY2023", ebit=Decimal("200"),
            effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        curr = _bs(
            ebit=Decimal("180"), effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("900"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        # NOPAT declined while IC increased → negative
        result = return_on_incremental_capital(curr, prev)
        assert result.value is not None
        assert result.value < Decimal("0")

    def test_period_spans_both(self) -> None:
        prev = _bs(
            name="FY2023", ebit=Decimal("180"),
            effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("800"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        curr = _bs(
            name="FY2024", ebit=Decimal("200"),
            effective_tax_rate=Decimal("0.25"),
            total_equity=Decimal("900"), total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("100"),
        )
        result = return_on_incremental_capital(curr, prev)
        assert result.period == "FY2023-FY2024"


class TestEarningsConsistency:
    def test_all_constant(self) -> None:
        periods = [
            _bs(name=f"FY{y}", pat=Decimal("100")) for y in range(2021, 2024)
        ]
        result = earnings_consistency(periods)
        # profitable=3/3=1, growth=0/2=0, vol_score=1 (cv=0)
        # score = (1+0+1)/3 = 0.666667
        assert result.value == Decimal("0.666667")
        assert result.metric == "earnings_consistency"

    def test_steady_growth(self) -> None:
        periods = [
            _bs(name="FY2021", pat=Decimal("100")),
            _bs(name="FY2022", pat=Decimal("110")),
            _bs(name="FY2023", pat=Decimal("121")),
        ]
        result = earnings_consistency(periods)
        assert result.value is not None
        # All profitable, all growing → score > 0.85
        assert result.value > Decimal("0.85")

    def test_mixed_with_loss(self) -> None:
        periods = [
            _bs(name="FY2021", pat=Decimal("100")),
            _bs(name="FY2022", pat=Decimal("-50")),
            _bs(name="FY2023", pat=Decimal("80")),
            _bs(name="FY2024", pat=Decimal("120")),
        ]
        result = earnings_consistency(periods)
        assert result.value is not None
        assert result.value < Decimal("0.5")

    def test_all_losses(self) -> None:
        periods = [
            _bs(name="FY2021", pat=Decimal("-100")),
            _bs(name="FY2022", pat=Decimal("-80")),
            _bs(name="FY2023", pat=Decimal("-120")),
        ]
        result = earnings_consistency(periods)
        assert result.value is not None
        # profitable_ratio=0, growth_ratio=0.5 (-80>-100), volatility low
        assert result.inputs["profitable_periods"] == 0
        assert result.value < Decimal("0.5")

    def test_insufficient_periods(self) -> None:
        periods = [_bs(name="FY2024", pat=Decimal("100"))]
        result = earnings_consistency(periods)
        assert result.value is None
        assert "at least 2" in str(result.notes)

    def test_two_periods_minimum(self) -> None:
        periods = [
            _bs(name="FY2023", pat=Decimal("100")),
            _bs(name="FY2024", pat=Decimal("120")),
        ]
        result = earnings_consistency(periods)
        assert result.value is not None

    def test_inputs_contain_components(self) -> None:
        periods = [
            _bs(name=f"FY{y}", pat=Decimal("100")) for y in range(2021, 2024)
        ]
        result = earnings_consistency(periods)
        assert result.inputs["total_periods"] == 3
        assert result.inputs["profitable_periods"] == 3
        assert result.inputs["growth_periods"] == 0

    def test_version_tracked(self) -> None:
        periods = [
            _bs(name="FY2023", pat=Decimal("100")),
            _bs(name="FY2024", pat=Decimal("120")),
        ]
        result = earnings_consistency(periods)
        assert result.version == VERSION
