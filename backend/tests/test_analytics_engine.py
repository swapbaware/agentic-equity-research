"""Tests for the Financial Analytics Engine orchestrator."""
from __future__ import annotations

from decimal import Decimal

from app.analytics.engine import compute_all
from app.analytics.models import PeriodFinancials

# ---------------------------------------------------------------------------
# Synthetic 3-year dataset with clean hand-verifiable numbers
# ---------------------------------------------------------------------------

_FY2022 = PeriodFinancials(
    period="FY2022",
    revenue=Decimal("10000"), cost_of_goods_sold=Decimal("6000"),
    gross_profit=Decimal("4000"),
    ebitda=Decimal("3000"), depreciation_amortization=Decimal("500"),
    ebit=Decimal("2500"), interest_expense=Decimal("200"),
    profit_before_tax=Decimal("2300"), tax_expense=Decimal("575"),
    pat=Decimal("1725"), effective_tax_rate=Decimal("0.25"),
    total_equity=Decimal("8000"), total_debt=Decimal("3000"),
    cash_and_equivalents=Decimal("500"),
    current_assets=Decimal("4000"), current_liabilities=Decimal("2500"),
    total_assets=Decimal("12000"),
    accounts_receivable=Decimal("1500"), inventory=Decimal("1200"),
    accounts_payable=Decimal("800"),
    cfo=Decimal("2000"), capex=Decimal("800"),
    eps=Decimal("17.25"), shares_outstanding=Decimal("100"),
)

_FY2023 = PeriodFinancials(
    period="FY2023",
    revenue=Decimal("11000"), cost_of_goods_sold=Decimal("6500"),
    gross_profit=Decimal("4500"),
    ebitda=Decimal("3400"), depreciation_amortization=Decimal("550"),
    ebit=Decimal("2850"), interest_expense=Decimal("180"),
    profit_before_tax=Decimal("2670"), tax_expense=Decimal("668"),
    pat=Decimal("2002"), effective_tax_rate=Decimal("0.25"),
    total_equity=Decimal("9000"), total_debt=Decimal("2800"),
    cash_and_equivalents=Decimal("600"),
    current_assets=Decimal("4500"), current_liabilities=Decimal("2700"),
    total_assets=Decimal("13000"),
    accounts_receivable=Decimal("1600"), inventory=Decimal("1300"),
    accounts_payable=Decimal("850"),
    cfo=Decimal("2300"), capex=Decimal("900"),
    eps=Decimal("20.02"), shares_outstanding=Decimal("100"),
)

_FY2024 = PeriodFinancials(
    period="FY2024",
    revenue=Decimal("12100"), cost_of_goods_sold=Decimal("7000"),
    gross_profit=Decimal("5100"),
    ebitda=Decimal("3993"), depreciation_amortization=Decimal("600"),
    ebit=Decimal("3393"), interest_expense=Decimal("150"),
    profit_before_tax=Decimal("3243"), tax_expense=Decimal("811"),
    pat=Decimal("2432"), effective_tax_rate=Decimal("0.25"),
    total_equity=Decimal("10000"), total_debt=Decimal("2500"),
    cash_and_equivalents=Decimal("700"),
    current_assets=Decimal("5000"), current_liabilities=Decimal("2800"),
    total_assets=Decimal("14000"),
    accounts_receivable=Decimal("1800"), inventory=Decimal("1400"),
    accounts_payable=Decimal("900"),
    cfo=Decimal("2800"), capex=Decimal("1000"),
    eps=Decimal("24.32"), shares_outstanding=Decimal("100"),
)

_PERIODS = [_FY2022, _FY2023, _FY2024]


class TestComputeAllFull:
    """Full 3-year dataset produces all 28 metrics."""

    def test_total_metric_count(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        assert len(report.calculations) == 28

    def test_periods_tracked(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        assert report.periods_analyzed == ["FY2022", "FY2023", "FY2024"]

    def test_symbol_and_exchange(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        assert report.symbol == "TESTCO"
        assert report.exchange == "NSE"

    def test_all_have_version(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        for calc in report.calculations:
            assert calc.version, f"{calc.metric} missing version"

    def test_all_have_formula(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        for calc in report.calculations:
            assert calc.formula, f"{calc.metric} missing formula"

    def test_all_have_inputs(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        for calc in report.calculations:
            assert isinstance(calc.inputs, dict), f"{calc.metric} bad inputs"

    def test_all_decimal_values(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        for calc in report.calculations:
            if calc.value is not None:
                assert isinstance(calc.value, Decimal), (
                    f"{calc.metric} value is {type(calc.value)}"
                )


class TestComputeAllGoldenValues:
    """Verify selected metrics against hand-computed expected values."""

    def test_gross_margin_fy2024(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        gm = next(c for c in report.calculations if c.metric == "gross_margin")
        # 5100 / 12100 = 0.421488...
        assert gm.value is not None
        assert abs(gm.value - Decimal("0.421488")) < Decimal("0.000001")

    def test_revenue_cagr_2_years(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        rc = next(c for c in report.calculations if c.metric == "revenue_cagr")
        # (12100/10000)^(1/2) - 1 = sqrt(1.21) - 1 = 0.1
        assert rc.value == Decimal("0.100000")

    def test_current_ratio_fy2024(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        cr = next(c for c in report.calculations if c.metric == "current_ratio")
        # 5000 / 2800 = 1.785714
        assert cr.value is not None
        assert abs(cr.value - Decimal("1.785714")) < Decimal("0.000001")

    def test_fcf_fy2024(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        fcf = next(c for c in report.calculations if c.metric == "fcf")
        # 2800 - 1000 = 1800
        assert fcf.value == Decimal("1800")

    def test_working_capital_fy2024(self) -> None:
        report = compute_all("TESTCO", "NSE", _PERIODS)
        wc = next(c for c in report.calculations if c.metric == "working_capital")
        # 5000 - 2800 = 2200
        assert wc.value == Decimal("2200")


class TestComputeAllEdgeCases:
    def test_single_period(self) -> None:
        report = compute_all("TESTCO", "NSE", [_FY2024])
        metrics = {c.metric for c in report.calculations}
        # Only single-period metrics (18 of them)
        assert "gross_margin" in metrics
        assert "revenue_cagr" not in metrics
        assert "roe" not in metrics
        assert len(report.calculations) == 18

    def test_empty_periods(self) -> None:
        report = compute_all("TESTCO", "NSE", [])
        assert report.calculations == []
        assert report.periods_analyzed == []

    def test_two_periods(self) -> None:
        report = compute_all("TESTCO", "NSE", [_FY2023, _FY2024])
        metrics = {c.metric for c in report.calculations}
        assert "revenue_cagr" in metrics
        assert "roe" in metrics
        assert "earnings_consistency" in metrics
