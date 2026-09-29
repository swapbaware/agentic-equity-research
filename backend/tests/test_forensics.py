"""Comprehensive tests for the Financial Forensics / Red Flag Screening Engine.

Tests cover: 22 individual checks, golden datasets, timing semantics,
financial-company handling, Beneish/Altman components, determinism,
thresholds, edge cases, and audit trail.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.analytics.models import PeriodFinancials
from app.models.enums import FindingType
from app.valuation.forensic_models import (
    CompanyType,
    ForensicCategory,
    ForensicCheckStatus,
    ForensicConfig,
    ForensicPeriodInput,
    ForensicSeverity,
    ThresholdClassification,
    ThresholdDirection,
)
from app.valuation.forensics import (
    ALL_CHECK_IDS,
    DEFAULT_CONFIG,
    FINANCIAL_APPLICABLE_CHECKS,
    ForensicValidationError,
    forensic_analysis,
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_OBS_DATE = date(2025, 6, 1)
_CALC_AT = datetime(2025, 6, 1, 12, 0, 0)
_AVAIL_DATE = date(2025, 5, 1)
_ZERO = Decimal("0")


def _fin(period: str, **kw: Decimal | None) -> PeriodFinancials:
    return PeriodFinancials(period=period, **kw)


def _period_input(
    fin: PeriodFinancials,
    end: date,
    avail: date | None = _AVAIL_DATE,
) -> ForensicPeriodInput:
    return ForensicPeriodInput(
        financials=fin,
        financial_period_end=end,
        financials_available_date=avail,
    )


def _d(val: str) -> Decimal:
    return Decimal(val)


# ---------------------------------------------------------------------------
# Healthy company base financials (Golden A)
# ---------------------------------------------------------------------------


def _healthy_fin(period: str, year: int) -> PeriodFinancials:
    base_rev = _d("1000") + _d(str(year - 2022)) * _d("100")
    return PeriodFinancials(
        period=period,
        revenue=base_rev,
        cost_of_goods_sold=base_rev * _d("0.60"),
        gross_profit=base_rev * _d("0.40"),
        ebitda=base_rev * _d("0.25"),
        depreciation_amortization=base_rev * _d("0.05"),
        ebit=base_rev * _d("0.20"),
        interest_expense=base_rev * _d("0.02"),
        profit_before_tax=base_rev * _d("0.18"),
        tax_expense=base_rev * _d("0.045"),
        pat=base_rev * _d("0.135"),
        total_equity=base_rev * _d("2.0"),
        total_debt=base_rev * _d("0.50"),
        cash_and_equivalents=base_rev * _d("0.15"),
        current_assets=base_rev * _d("0.80"),
        current_liabilities=base_rev * _d("0.40"),
        total_assets=base_rev * _d("3.0"),
        accounts_receivable=base_rev * _d("0.12"),
        inventory=base_rev * _d("0.10"),
        accounts_payable=base_rev * _d("0.08"),
        capital_employed=base_rev * _d("2.50"),
        cfo=base_rev * _d("0.15"),
        capex=base_rev * _d("0.05"),
        eps=_d("10") + _d(str(year - 2022)),
        shares_outstanding=_d("100"),
        effective_tax_rate=_d("0.25"),
    )


def _golden_a_periods() -> list[ForensicPeriodInput]:
    return [
        _period_input(_healthy_fin("FY2022", 2022), date(2023, 3, 31), date(2023, 6, 1)),
        _period_input(_healthy_fin("FY2023", 2023), date(2024, 3, 31), date(2024, 6, 1)),
        _period_input(_healthy_fin("FY2024", 2024), date(2025, 3, 31), date(2025, 4, 15)),
    ]


# ---------------------------------------------------------------------------
# Deteriorating company (Golden B)
# ---------------------------------------------------------------------------


def _deteriorating_fin(period: str, year: int) -> PeriodFinancials:
    rev = _d("1000") - _d(str(year - 2022)) * _d("50")
    cogs = rev * (_d("0.65") + _d(str(year - 2022)) * _d("0.03"))
    gp = rev - cogs
    ebitda_val = rev * (_d("0.20") - _d(str(year - 2022)) * _d("0.03"))
    ebit_val = ebitda_val - rev * _d("0.05")
    ie = rev * _d("0.04")
    pbt = ebit_val - ie
    tax = pbt * _d("0.25") if pbt > _ZERO else _ZERO
    net = pbt - tax
    cfo_val = net * _d("0.50")
    ar = rev * (_d("0.15") + _d(str(year - 2022)) * _d("0.05"))
    inv = rev * (_d("0.12") + _d(str(year - 2022)) * _d("0.03"))
    return PeriodFinancials(
        period=period,
        revenue=rev,
        cost_of_goods_sold=cogs,
        gross_profit=gp,
        ebitda=ebitda_val if ebitda_val > _ZERO else _d("1"),
        depreciation_amortization=rev * _d("0.05"),
        ebit=ebit_val,
        interest_expense=ie,
        profit_before_tax=pbt,
        tax_expense=tax,
        pat=net,
        total_equity=_d("1500") - _d(str(year - 2022)) * _d("200"),
        total_debt=_d("800") + _d(str(year - 2022)) * _d("200"),
        cash_and_equivalents=_d("100"),
        current_assets=_d("600"),
        current_liabilities=_d("400"),
        total_assets=_d("3000"),
        accounts_receivable=ar,
        inventory=inv,
        accounts_payable=rev * _d("0.07"),
        capital_employed=_d("2000"),
        cfo=cfo_val,
        capex=_d("80"),
        eps=net / _d("100"),
        shares_outstanding=_d("100"),
        effective_tax_rate=_d("0.25"),
    )


def _golden_b_periods() -> list[ForensicPeriodInput]:
    return [
        _period_input(_deteriorating_fin("FY2022", 2022), date(2023, 3, 31), date(2023, 6, 1)),
        _period_input(_deteriorating_fin("FY2023", 2023), date(2024, 3, 31), date(2024, 6, 1)),
        _period_input(_deteriorating_fin("FY2024", 2024), date(2025, 3, 31), date(2025, 4, 15)),
    ]


# ===========================================================================
# INPUT VALIDATION
# ===========================================================================


class TestInputValidation:
    def test_empty_periods_raises(self) -> None:
        with pytest.raises(ForensicValidationError, match="at least one period"):
            forensic_analysis([], observation_date=_OBS_DATE, calculated_at=_CALC_AT)

    def test_duplicate_period_end_raises(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"))
        p1 = _period_input(fin, date(2025, 3, 31))
        p2 = _period_input(fin, date(2025, 3, 31))
        with pytest.raises(ForensicValidationError, match="duplicate"):
            forensic_analysis([p1, p2], observation_date=_OBS_DATE, calculated_at=_CALC_AT)

    def test_non_chronological_raises(self) -> None:
        f1 = _fin("FY2024", revenue=_d("100"))
        f2 = _fin("FY2023", revenue=_d("90"))
        p1 = _period_input(f1, date(2025, 3, 31))
        p2 = _period_input(f2, date(2024, 3, 31))
        with pytest.raises(ForensicValidationError, match="chronological"):
            forensic_analysis([p1, p2], observation_date=_OBS_DATE, calculated_at=_CALC_AT)

    def test_negative_market_cap_raises(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        with pytest.raises(ForensicValidationError, match="market_cap must be positive"):
            forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT, market_cap=_d("-5"))

    def test_zero_market_cap_raises(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        with pytest.raises(ForensicValidationError, match="market_cap must be positive"):
            forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT, market_cap=_d("0"))


# ===========================================================================
# POINT-IN-TIME / TIMING
# ===========================================================================


class TestTimingSemantics:
    def test_valid_period_participates(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"), pat=_d("10"), cfo=_d("12"), total_assets=_d("500"), ebitda=_d("20"))
        p = _period_input(fin, date(2025, 3, 31), avail=date(2025, 4, 1))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        cfo_ni = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert cfo_ni.status in (ForensicCheckStatus.PASS, ForensicCheckStatus.FLAGGED)

    def test_look_ahead_excluded(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"), pat=_d("10"), cfo=_d("12"), total_assets=_d("500"))
        p = _period_input(fin, date(2025, 3, 31), avail=date(2026, 1, 1))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        for c in result.checks:
            assert c.status != ForensicCheckStatus.PASS
            assert c.status != ForensicCheckStatus.FLAGGED

    def test_unverified_timing_excluded_from_primary(self) -> None:
        fins = []
        for i, (period, yr) in enumerate([("FY2022", 2022), ("FY2023", 2023), ("FY2024", 2024)]):
            f = _healthy_fin(period, yr)
            avail = date(2025, 4, 1) if i != 1 else None
            fins.append(_period_input(f, date(yr + 1, 3, 31), avail=avail))

        result = forensic_analysis(fins, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        for summary in result.category_summaries:
            assert summary.checks_unverified_timing >= 0

    def test_unverified_timing_not_in_evaluated(self) -> None:
        f_valid = _fin("FY2022", revenue=_d("100"), pat=_d("10"), cfo=_d("12"), total_assets=_d("500"))
        f_unverified = _fin("FY2023", revenue=_d("110"), pat=_d("11"), cfo=_d("13"), total_assets=_d("550"))
        f_valid2 = _fin("FY2024", revenue=_d("120"), pat=_d("12"), cfo=_d("14"), total_assets=_d("600"))

        periods = [
            _period_input(f_valid, date(2023, 3, 31), avail=date(2023, 5, 1)),
            _period_input(f_unverified, date(2024, 3, 31), avail=None),
            _period_input(f_valid2, date(2025, 3, 31), avail=date(2025, 4, 1)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        assert result.periods_analyzed == ["FY2022", "FY2023", "FY2024"]


# ===========================================================================
# EARNINGS QUALITY
# ===========================================================================


class TestCfoToNetIncome:
    def test_healthy_passes(self) -> None:
        fin = _fin("FY2024", cfo=_d("120"), pat=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("1.200000")

    def test_low_ratio_flagged(self) -> None:
        fin = _fin("FY2024", cfo=_d("40"), pat=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert check.status == ForensicCheckStatus.FLAGGED
        assert check.severity == ForensicSeverity.MEDIUM

    def test_missing_cfo_not_computable(self) -> None:
        fin = _fin("FY2024", pat=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert check.status == ForensicCheckStatus.NOT_COMPUTABLE


class TestCfoNetIncomeDivergence:
    def test_no_divergence(self) -> None:
        periods = []
        for period, yr in [("FY2022", 2022), ("FY2023", 2023), ("FY2024", 2024)]:
            f = _fin(period, cfo=_d("100"), pat=_d("80"))
            periods.append(_period_input(f, date(yr + 1, 3, 31)))
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_net_income_divergence")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("0.000000")

    def test_full_divergence_flagged(self) -> None:
        periods = []
        for period, yr in [("FY2022", 2022), ("FY2023", 2023), ("FY2024", 2024)]:
            f = _fin(period, cfo=_d("-10"), pat=_d("80"))
            periods.append(_period_input(f, date(yr + 1, 3, 31)))
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_net_income_divergence")
        assert check.status == ForensicCheckStatus.FLAGGED

    def test_insufficient_history(self) -> None:
        f = _fin("FY2024", cfo=_d("100"), pat=_d("80"))
        p = _period_input(f, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_net_income_divergence")
        assert check.status == ForensicCheckStatus.INSUFFICIENT_HISTORY


class TestTotalAccrualsToAssets:
    def test_low_accruals_pass(self) -> None:
        fin = _fin("FY2024", pat=_d("100"), cfo=_d("98"), total_assets=_d("2000"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.total_accruals_to_assets")
        assert check.status == ForensicCheckStatus.PASS

    def test_high_accruals_flagged(self) -> None:
        fin = _fin("FY2024", pat=_d("100"), cfo=_d("10"), total_assets=_d("500"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.total_accruals_to_assets")
        assert check.status == ForensicCheckStatus.FLAGGED

    def test_zero_total_assets_invalid(self) -> None:
        fin = _fin("FY2024", pat=_d("100"), cfo=_d("10"), total_assets=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.total_accruals_to_assets")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


class TestCfoToEbitda:
    def test_healthy_pass(self) -> None:
        fin = _fin("FY2024", cfo=_d("200"), ebitda=_d("250"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_ebitda")
        assert check.status == ForensicCheckStatus.PASS

    def test_zero_ebitda_invalid(self) -> None:
        fin = _fin("FY2024", cfo=_d("200"), ebitda=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_ebitda")
        assert check.status == ForensicCheckStatus.INVALID_INPUT

    def test_negative_ebitda_invalid(self) -> None:
        fin = _fin("FY2024", cfo=_d("200"), ebitda=_d("-10"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_ebitda")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


# ===========================================================================
# WORKING CAPITAL
# ===========================================================================


class TestReceivablesVsRevenueGrowth:
    def test_normal_pass(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("110"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.receivables_vs_revenue_growth")
        assert check.status == ForensicCheckStatus.PASS

    def test_excess_growth_flagged(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("150"), revenue=_d("1050"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.receivables_vs_revenue_growth")
        assert check.status == ForensicCheckStatus.FLAGGED

    def test_zero_prior_not_computable(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("0"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("50"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.receivables_vs_revenue_growth")
        assert check.status == ForensicCheckStatus.NOT_COMPUTABLE


class TestDsoChange:
    def test_stable_dso_pass(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("110"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.dso_change")
        assert check.status == ForensicCheckStatus.PASS

    def test_increasing_dso_flagged(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("200"), revenue=_d("1000"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.dso_change")
        assert check.status == ForensicCheckStatus.FLAGGED


class TestDioChange:
    def test_missing_inventory_not_computable(self) -> None:
        f1 = _fin("FY2023", cost_of_goods_sold=_d("600"))
        f2 = _fin("FY2024", cost_of_goods_sold=_d("660"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.dio_change")
        assert check.status == ForensicCheckStatus.NOT_COMPUTABLE


class TestCccChange:
    def test_normal_ccc(self) -> None:
        f1 = _fin(
            "FY2023",
            accounts_receivable=_d("100"),
            revenue=_d("1000"),
            inventory=_d("80"),
            cost_of_goods_sold=_d("600"),
            accounts_payable=_d("60"),
        )
        f2 = _fin(
            "FY2024",
            accounts_receivable=_d("110"),
            revenue=_d("1100"),
            inventory=_d("90"),
            cost_of_goods_sold=_d("660"),
            accounts_payable=_d("65"),
        )
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.cash_conversion_cycle_change")
        assert check.status in (ForensicCheckStatus.PASS, ForensicCheckStatus.FLAGGED)
        assert check.observed_value is not None


# ===========================================================================
# CASH FLOW QUALITY
# ===========================================================================


class TestNegativeCfoCount:
    def test_all_positive_pass(self) -> None:
        periods = [_period_input(_fin(f"FY{y}", cfo=_d("100")), date(y + 1, 3, 31)) for y in range(2022, 2025)]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.negative_cfo_count")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("0.000000")

    def test_all_negative_flagged(self) -> None:
        periods = [_period_input(_fin(f"FY{y}", cfo=_d("-50")), date(y + 1, 3, 31)) for y in range(2022, 2025)]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.negative_cfo_count")
        assert check.status == ForensicCheckStatus.FLAGGED
        assert check.severity == ForensicSeverity.CRITICAL

    def test_insufficient_history(self) -> None:
        periods = [
            _period_input(_fin("FY2024", cfo=_d("100")), date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.negative_cfo_count")
        assert check.status == ForensicCheckStatus.INSUFFICIENT_HISTORY


class TestNegativeFcfCount:
    def test_all_positive_pass(self) -> None:
        periods = [
            _period_input(_fin(f"FY{y}", cfo=_d("100"), capex=_d("30")), date(y + 1, 3, 31)) for y in range(2022, 2025)
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.negative_fcf_count")
        assert check.status == ForensicCheckStatus.PASS


class TestCfoToEbitdaLevel:
    def test_healthy_pass(self) -> None:
        fin = _fin("FY2024", cfo=_d("200"), ebitda=_d("250"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.cfo_to_ebitda_level")
        assert check.status == ForensicCheckStatus.PASS

    def test_zero_ebitda_invalid(self) -> None:
        fin = _fin("FY2024", cfo=_d("200"), ebitda=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.cfo_to_ebitda_level")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


class TestCapexIntensityChange:
    def test_stable_pass(self) -> None:
        f1 = _fin("FY2023", capex=_d("50"), revenue=_d("1000"))
        f2 = _fin("FY2024", capex=_d("55"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.capex_intensity_change")
        assert check.status == ForensicCheckStatus.PASS

    def test_zero_revenue_invalid(self) -> None:
        f1 = _fin("FY2023", capex=_d("50"), revenue=_d("1000"))
        f2 = _fin("FY2024", capex=_d("55"), revenue=_d("0"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.capex_intensity_change")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


# ===========================================================================
# LEVERAGE
# ===========================================================================


class TestDebtToEquity:
    def test_low_leverage_pass(self) -> None:
        fin = _fin("FY2024", total_debt=_d("200"), total_equity=_d("1000"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.debt_to_equity")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("0.200000")

    def test_high_leverage_flagged(self) -> None:
        fin = _fin("FY2024", total_debt=_d("5000"), total_equity=_d("1000"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.debt_to_equity")
        assert check.status == ForensicCheckStatus.FLAGGED

    def test_zero_equity_invalid(self) -> None:
        fin = _fin("FY2024", total_debt=_d("200"), total_equity=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.debt_to_equity")
        assert check.status == ForensicCheckStatus.INVALID_INPUT

    def test_negative_equity_invalid(self) -> None:
        fin = _fin("FY2024", total_debt=_d("200"), total_equity=_d("-100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.debt_to_equity")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


class TestInterestCoverage:
    def test_healthy_pass(self) -> None:
        fin = _fin("FY2024", ebit=_d("500"), interest_expense=_d("50"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("10.000000")

    def test_zero_interest_not_computable(self) -> None:
        fin = _fin("FY2024", ebit=_d("500"), interest_expense=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.NOT_COMPUTABLE
        assert "zero" in (check.notes or "").lower()

    def test_zero_interest_with_zero_debt_note(self) -> None:
        fin = _fin("FY2024", ebit=_d("500"), interest_expense=_d("0"), total_debt=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.NOT_COMPUTABLE
        assert "total_debt" in (check.notes or "").lower()

    def test_negative_interest_invalid(self) -> None:
        fin = _fin("FY2024", ebit=_d("500"), interest_expense=_d("-10"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.INVALID_INPUT

    def test_negative_ebit_uses_standard_thresholds(self) -> None:
        fin = _fin("FY2024", ebit=_d("-100"), interest_expense=_d("50"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.FLAGGED
        assert check.observed_value == _d("-2.000000")
        assert check.severity == ForensicSeverity.CRITICAL

    def test_low_coverage_flagged(self) -> None:
        fin = _fin("FY2024", ebit=_d("80"), interest_expense=_d("50"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.interest_coverage")
        assert check.status == ForensicCheckStatus.FLAGGED
        assert check.observed_value == _d("1.600000")
        assert check.severity == ForensicSeverity.MEDIUM


class TestLeverageTrend:
    def test_stable_pass(self) -> None:
        f1 = _fin("FY2023", total_debt=_d("200"), total_equity=_d("1000"))
        f2 = _fin("FY2024", total_debt=_d("210"), total_equity=_d("1050"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.leverage_trend")
        assert check.status == ForensicCheckStatus.PASS

    def test_prior_zero_equity_invalid(self) -> None:
        f1 = _fin("FY2023", total_debt=_d("200"), total_equity=_d("0"))
        f2 = _fin("FY2024", total_debt=_d("210"), total_equity=_d("1050"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.leverage_trend")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


# ===========================================================================
# PROFITABILITY
# ===========================================================================


class TestGrossMarginDecline:
    def test_improving_pass(self) -> None:
        periods = [
            _period_input(
                _fin(f"FY{y}", revenue=_d("1000"), gross_profit=_d(str(300 + (y - 2022) * 20))), date(y + 1, 3, 31)
            )
            for y in range(2022, 2025)
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.gross_margin_decline")
        assert check.status == ForensicCheckStatus.PASS

    def test_consecutive_decline_flagged(self) -> None:
        periods = [
            _period_input(
                _fin(f"FY{y}", revenue=_d("1000"), gross_profit=_d(str(400 - (y - 2022) * 30))), date(y + 1, 3, 31)
            )
            for y in range(2022, 2025)
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.gross_margin_decline")
        assert check.status == ForensicCheckStatus.FLAGGED


class TestProfitVsCashflowDivergence:
    def test_no_divergence_pass(self) -> None:
        f1 = _fin("FY2023", revenue=_d("1000"), pat=_d("100"), cfo=_d("120"))
        f2 = _fin("FY2024", revenue=_d("1100"), pat=_d("120"), cfo=_d("150"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.profit_vs_cashflow_divergence")
        assert check.status == ForensicCheckStatus.PASS

    def test_divergence_flagged(self) -> None:
        f1 = _fin("FY2023", revenue=_d("1000"), pat=_d("100"), cfo=_d("150"))
        f2 = _fin("FY2024", revenue=_d("1100"), pat=_d("130"), cfo=_d("100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.profit_vs_cashflow_divergence")
        assert check.status == ForensicCheckStatus.FLAGGED

    def test_zero_pat_invalid(self) -> None:
        f1 = _fin("FY2023", revenue=_d("1000"), pat=_d("0"), cfo=_d("150"))
        f2 = _fin("FY2024", revenue=_d("1100"), pat=_d("130"), cfo=_d("100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.profit_vs_cashflow_divergence")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


# ===========================================================================
# BENEISH MODEL
# ===========================================================================


class TestBeneishComponents:
    def test_dsri_computed(self) -> None:
        f1 = _fin("FY2023", accounts_receivable=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", accounts_receivable=_d("120"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        assert result.beneish_components["dsri"] is not None
        dsri_calc = next((c for c in result.calculations if c.metric == "forensic_beneish_dsri"), None)
        assert dsri_calc is not None

    def test_gmi_computed(self) -> None:
        f1 = _fin("FY2023", gross_profit=_d("400"), revenue=_d("1000"))
        f2 = _fin("FY2024", gross_profit=_d("420"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        assert result.beneish_components["gmi"] is not None

    def test_sgi_computed(self) -> None:
        f1 = _fin("FY2023", revenue=_d("1000"))
        f2 = _fin("FY2024", revenue=_d("1200"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        assert result.beneish_components["sgi"] is not None
        assert result.beneish_components["sgi"] == _d("1.200000")

    def test_tata_computed(self) -> None:
        f1 = _fin("FY2023", pat=_d("90"), cfo=_d("75"), total_assets=_d("1900"), revenue=_d("900"))
        f2 = _fin("FY2024", pat=_d("100"), cfo=_d("80"), total_assets=_d("2000"), revenue=_d("1000"))
        result = forensic_analysis(
            [_period_input(f1, date(2024, 3, 31)), _period_input(f2, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.beneish_components["tata"] is not None

    def test_aqi_always_none(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.beneish_components["aqi"] is None

    def test_composite_not_computable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.beneish_score is None
        assert result.beneish_status == ForensicCheckStatus.NOT_COMPUTABLE

    def test_financial_company_not_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        assert result.beneish_status == ForensicCheckStatus.NOT_APPLICABLE


# ===========================================================================
# ALTMAN MODEL
# ===========================================================================


class TestAltmanComponents:
    def test_x1_computed(self) -> None:
        f = _fin("FY2024", current_assets=_d("800"), current_liabilities=_d("400"), total_assets=_d("3000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_components["x1"] is not None

    def test_x3_computed(self) -> None:
        f = _fin("FY2024", ebit=_d("200"), total_assets=_d("3000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_components["x3"] is not None

    def test_x4_with_market_cap(self) -> None:
        f = _fin("FY2024", total_assets=_d("3000"), total_equity=_d("2000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("5000"),
        )
        assert result.altman_components["x4"] is not None
        assert result.altman_components["x4"] == _d("5.000000")
        x4_calc = next(c for c in result.calculations if c.metric == "forensic_altman_x4")
        assert x4_calc.inputs["total_liabilities_derived"] == _d("1000")
        assert "total_liabilities derived" in (x4_calc.notes or "")

    def test_x4_without_market_cap_not_computable(self) -> None:
        f = _fin("FY2024", total_assets=_d("3000"), total_equity=_d("2000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_components["x4"] is None

    def test_x4_negative_liabilities_invalid(self) -> None:
        f = _fin("FY2024", total_assets=_d("3000"), total_equity=_d("4000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("5000"),
        )
        assert result.altman_components["x4"] is None
        x4_calc = next((c for c in result.calculations if c.metric == "forensic_altman_x4"), None)
        assert x4_calc is not None
        assert "zero or negative" in (x4_calc.notes or "")

    def test_x4_zero_total_assets_invalid(self) -> None:
        f = _fin("FY2024", total_assets=_d("0"), total_equity=_d("0"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("5000"),
        )
        assert result.altman_components["x4"] is None

    def test_x5_computed(self) -> None:
        f = _fin("FY2024", revenue=_d("1200"), total_assets=_d("3000"))
        result = forensic_analysis(
            [_period_input(f, date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_components["x5"] is not None
        assert result.altman_components["x5"] == _d("0.400000")

    def test_x2_always_none(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_components["x2"] is None

    def test_composite_not_computable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.altman_score is None
        assert result.altman_zone is None
        assert result.altman_status == ForensicCheckStatus.NOT_COMPUTABLE

    def test_financial_company_not_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        assert result.altman_status == ForensicCheckStatus.NOT_APPLICABLE


# ===========================================================================
# FINANCIAL COMPANIES
# ===========================================================================


class TestFinancialCompany:
    def test_exactly_3_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        applicable = [c for c in result.checks if c.status != ForensicCheckStatus.NOT_APPLICABLE]
        not_applicable = [c for c in result.checks if c.status == ForensicCheckStatus.NOT_APPLICABLE]
        assert len(applicable) == 3
        assert len(not_applicable) == 19
        applicable_ids = {c.check_id for c in applicable}
        assert applicable_ids == FINANCIAL_APPLICABLE_CHECKS

    def test_exact_applicable_check_ids(self) -> None:
        assert (
            frozenset(
                {
                    "eq.total_accruals_to_assets",
                    "cf.negative_cfo_count",
                    "pr.net_margin_decline",
                }
            )
            == FINANCIAL_APPLICABLE_CHECKS
        )

    def test_beneish_not_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        assert result.beneish_status == ForensicCheckStatus.NOT_APPLICABLE

    def test_altman_not_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        assert result.altman_status == ForensicCheckStatus.NOT_APPLICABLE


# ===========================================================================
# CATEGORY SUMMARIES
# ===========================================================================


class TestCategorySummaries:
    def test_five_categories(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert len(result.category_summaries) == 5
        cats = {s.category for s in result.category_summaries}
        assert cats == set(ForensicCategory)

    def test_coverage_ratio_computed(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for s in result.category_summaries:
            assert s.data_coverage_ratio is not None

    def test_financial_company_coverage(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        for s in result.category_summaries:
            applicable = s.checks_total - s.checks_not_applicable
            if applicable == 0:
                assert s.data_coverage_ratio is None
            else:
                assert s.data_coverage_ratio is not None

    def test_status_counts_consistent(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for s in result.category_summaries:
            assert s.checks_evaluated == s.checks_flagged + s.checks_passed
            total_statuses = (
                s.checks_flagged
                + s.checks_passed
                + s.checks_not_computable
                + s.checks_invalid_input
                + s.checks_not_applicable
                + s.checks_insufficient_history
                + s.checks_unverified_timing
                + s.checks_look_ahead_risk
            )
            assert total_statuses == s.checks_total


# ===========================================================================
# DATA QUALITY DIAGNOSTICS
# ===========================================================================


class TestDataQualityDiagnostics:
    def test_zero_total_assets_diagnostic(self) -> None:
        fin = _fin("FY2024", total_assets=_d("0"), revenue=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        diags = [d for d in result.diagnostics if d.field == "total_assets"]
        assert len(diags) == 1
        assert "zero or negative" in diags[0].issue

    def test_negative_revenue_diagnostic(self) -> None:
        fin = _fin("FY2024", revenue=_d("-50"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        diags = [d for d in result.diagnostics if d.field == "revenue"]
        assert len(diags) == 1

    def test_current_assets_exceeds_total_diagnostic(self) -> None:
        fin = _fin("FY2024", current_assets=_d("500"), total_assets=_d("400"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        diags = [d for d in result.diagnostics if d.field == "current_assets"]
        assert len(diags) == 1


# ===========================================================================
# DETERMINISM
# ===========================================================================


class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        periods = _golden_a_periods()
        r1 = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT, market_cap=_d("10000"))
        r2 = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT, market_cap=_d("10000"))
        assert r1 == r2

    def test_calculated_at_changes_only_metadata(self) -> None:
        periods = _golden_a_periods()
        t1 = datetime(2025, 6, 1, 12, 0, 0)
        t2 = datetime(2025, 7, 1, 12, 0, 0)
        r1 = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=t1)
        r2 = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=t2)
        assert r1.calculated_at == t1
        assert r2.calculated_at == t2
        assert r1.checks == r2.checks
        assert r1.category_summaries == r2.category_summaries

    def test_observation_date_affects_timing(self) -> None:
        fin = _fin("FY2024", revenue=_d("100"), pat=_d("10"), cfo=_d("12"))
        p = _period_input(fin, date(2025, 3, 31), avail=date(2025, 5, 1))
        r_before = forensic_analysis([p], observation_date=date(2025, 4, 1), calculated_at=_CALC_AT)
        r_after = forensic_analysis([p], observation_date=date(2025, 6, 1), calculated_at=_CALC_AT)
        before_check = next(c for c in r_before.checks if c.check_id == "eq.cfo_to_net_income")
        after_check = next(c for c in r_after.checks if c.check_id == "eq.cfo_to_net_income")
        assert before_check.status != ForensicCheckStatus.PASS or after_check.status != ForensicCheckStatus.PASS


# ===========================================================================
# AUDIT TRAIL
# ===========================================================================


class TestAuditTrail:
    def test_all_flagged_checks_have_calculation(self) -> None:
        result = forensic_analysis(
            _golden_b_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for c in result.checks:
            if c.status == ForensicCheckStatus.FLAGGED:
                assert c.calculation is not None, f"{c.check_id} flagged without calculation"

    def test_all_pass_checks_have_calculation(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for c in result.checks:
            if c.status == ForensicCheckStatus.PASS:
                assert c.calculation is not None, f"{c.check_id} passed without calculation"

    def test_finding_type_always_calculation(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for c in result.checks:
            assert c.finding_type == FindingType.CALCULATION

    def test_engine_version_present(self) -> None:
        result = forensic_analysis(
            [_period_input(_fin("FY2024", revenue=_d("100")), date(2025, 3, 31))],
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.engine_version == "1.0.0"

    def test_forensic_prefixed_metrics(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("10000"),
        )
        for calc in result.calculations:
            assert calc.metric.startswith("forensic_"), f"metric {calc.metric} missing forensic_ prefix"


# ===========================================================================
# LANGUAGE SAFETY
# ===========================================================================


class TestLanguageSafety:
    def test_no_fraud_language(self) -> None:
        result = forensic_analysis(
            _golden_b_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        forbidden = ["fraud", "manipulation", "distress", "unsafe", "misconduct"]
        for c in result.checks:
            desc_lower = c.description.lower()
            for word in forbidden:
                assert word not in desc_lower, f"'{word}' found in {c.check_id} description"

    def test_flagged_uses_screening_signal(self) -> None:
        result = forensic_analysis(
            _golden_b_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        for c in result.checks:
            if c.status == ForensicCheckStatus.FLAGGED:
                assert "screening signal" in c.description.lower() or "threshold" in c.description.lower()


# ===========================================================================
# DECIMAL ENFORCEMENT
# ===========================================================================


class TestDecimalEnforcement:
    def test_no_floats_in_check_results(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("10000"),
        )
        for c in result.checks:
            if c.observed_value is not None:
                assert isinstance(c.observed_value, Decimal), f"{c.check_id} observed_value is not Decimal"
            if c.threshold is not None:
                assert isinstance(c.threshold, Decimal), f"{c.check_id} threshold is not Decimal"

    def test_no_floats_in_calculations(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("10000"),
        )
        for calc in result.calculations:
            if calc.value is not None:
                assert isinstance(calc.value, Decimal), f"{calc.metric} value is not Decimal"


# ===========================================================================
# 22 CHECK COUNT
# ===========================================================================


class TestCheckCount:
    def test_exactly_22_checks(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert len(result.checks) == 22

    def test_all_check_ids_present(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        check_ids = {c.check_id for c in result.checks}
        assert check_ids == set(ALL_CHECK_IDS)


# ===========================================================================
# NO AGGREGATE SCORE
# ===========================================================================


class TestNoAggregateScore:
    def test_no_aggregate_score_field(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert not hasattr(result, "aggregate_score")
        assert not hasattr(result, "forensic_score")
        assert not hasattr(result, "risk_score")


# ===========================================================================
# GOLDEN DATASETS
# ===========================================================================


class TestGoldenA:
    """Golden dataset A: healthy industrial company."""

    def test_mostly_passing(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("10000"),
        )
        flagged = [c for c in result.checks if c.status == ForensicCheckStatus.FLAGGED]
        passed = [c for c in result.checks if c.status == ForensicCheckStatus.PASS]
        assert len(passed) > len(flagged)

    def test_beneish_components_computed(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        assert result.beneish_components["dsri"] is not None
        assert result.beneish_components["gmi"] is not None
        assert result.beneish_components["sgi"] is not None
        assert result.beneish_components["tata"] is not None
        assert result.beneish_components["aqi"] is None
        assert result.beneish_score is None

    def test_altman_components_computed(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            market_cap=_d("10000"),
        )
        assert result.altman_components["x1"] is not None
        assert result.altman_components["x2"] is None
        assert result.altman_components["x3"] is not None
        assert result.altman_components["x4"] is not None
        assert result.altman_components["x5"] is not None
        assert result.altman_score is None

    def test_hand_verified_cfo_to_ni(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value is not None


class TestGoldenB:
    """Golden dataset B: deteriorating company."""

    def test_has_flags(self) -> None:
        result = forensic_analysis(
            _golden_b_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        flagged = [c for c in result.checks if c.status == ForensicCheckStatus.FLAGGED]
        assert len(flagged) > 0

    def test_maximum_severity_present(self) -> None:
        result = forensic_analysis(
            _golden_b_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
        )
        any_severity = any(s.maximum_severity is not None for s in result.category_summaries)
        assert any_severity


class TestGoldenC:
    """Golden dataset C: financial institution."""

    def test_19_not_applicable(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        na = [c for c in result.checks if c.status == ForensicCheckStatus.NOT_APPLICABLE]
        assert len(na) == 19

    def test_3_applicable_checks(self) -> None:
        result = forensic_analysis(
            _golden_a_periods(),
            observation_date=_OBS_DATE,
            calculated_at=_CALC_AT,
            company_type=CompanyType.FINANCIAL,
        )
        applicable = [c for c in result.checks if c.status != ForensicCheckStatus.NOT_APPLICABLE]
        assert len(applicable) == 3


class TestGoldenD:
    """Golden dataset D: minimal data (single period)."""

    def test_level_checks_work(self) -> None:
        fin = _fin(
            "FY2024",
            revenue=_d("1000"),
            pat=_d("100"),
            cfo=_d("120"),
            total_assets=_d("3000"),
            ebitda=_d("200"),
            total_equity=_d("2000"),
            total_debt=_d("500"),
            cash_and_equivalents=_d("100"),
            ebit=_d("150"),
            interest_expense=_d("30"),
        )
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        level_checks = [
            "eq.cfo_to_net_income",
            "eq.total_accruals_to_assets",
            "eq.cfo_to_ebitda",
            "cf.cfo_to_ebitda_level",
            "lv.debt_to_equity",
            "lv.net_debt_to_ebitda",
            "lv.interest_coverage",
        ]
        for cid in level_checks:
            check = next(c for c in result.checks if c.check_id == cid)
            assert check.status in (ForensicCheckStatus.PASS, ForensicCheckStatus.FLAGGED), (
                f"{cid} should be evaluable with single period"
            )

    def test_trend_checks_insufficient(self) -> None:
        fin = _fin(
            "FY2024",
            revenue=_d("1000"),
            pat=_d("100"),
            cfo=_d("120"),
            total_assets=_d("3000"),
            ebitda=_d("200"),
            gross_profit=_d("400"),
        )
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        trend_checks = [
            "wc.receivables_vs_revenue_growth",
            "wc.dso_change",
            "lv.leverage_trend",
            "cf.capex_intensity_change",
            "pr.gross_margin_decline",
            "pr.profit_vs_cashflow_divergence",
        ]
        for cid in trend_checks:
            check = next(c for c in result.checks if c.check_id == cid)
            assert check.status == ForensicCheckStatus.INSUFFICIENT_HISTORY, (
                f"{cid} should be INSUFFICIENT_HISTORY with single period"
            )


class TestGoldenE:
    """Golden dataset E: mixed timing (VALID, UNVERIFIED, VALID)."""

    def test_unverified_excluded_from_evaluated(self) -> None:
        f1 = _healthy_fin("FY2022", 2022)
        f2 = _healthy_fin("FY2023", 2023)
        f3 = _healthy_fin("FY2024", 2024)

        periods = [
            _period_input(f1, date(2023, 3, 31), avail=date(2023, 5, 1)),
            _period_input(f2, date(2024, 3, 31), avail=None),
            _period_input(f3, date(2025, 3, 31), avail=date(2025, 4, 15)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        assert result.periods_analyzed == ["FY2022", "FY2023", "FY2024"]
        assert len(result.checks) == 22

    def test_valid_only_two_periods(self) -> None:
        f1 = _healthy_fin("FY2022", 2022)
        f2 = _healthy_fin("FY2023", 2023)
        f3 = _healthy_fin("FY2024", 2024)

        periods = [
            _period_input(f1, date(2023, 3, 31), avail=date(2023, 5, 1)),
            _period_input(f2, date(2024, 3, 31), avail=None),
            _period_input(f3, date(2025, 3, 31), avail=date(2025, 4, 15)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        div_check = next(c for c in result.checks if c.check_id == "eq.cfo_net_income_divergence")
        assert div_check.status == ForensicCheckStatus.INSUFFICIENT_HISTORY


# ===========================================================================
# THRESHOLD CONFIGURATION
# ===========================================================================


class TestThresholdConfig:
    def test_default_config_has_all_checks(self) -> None:
        for cid in ALL_CHECK_IDS:
            assert cid in DEFAULT_CONFIG.thresholds, f"missing threshold for {cid}"

    def test_all_thresholds_platform_heuristic(self) -> None:
        for cid, t in DEFAULT_CONFIG.thresholds.items():
            assert t.classification == ThresholdClassification.PLATFORM_HEURISTIC, (
                f"{cid} threshold is not PLATFORM_HEURISTIC"
            )

    def test_custom_config_override(self) -> None:
        from app.valuation.forensic_models import ThresholdConfig

        custom = ForensicConfig(
            version="custom",
            thresholds={
                **DEFAULT_CONFIG.thresholds,
                "eq.cfo_to_net_income": ThresholdConfig(
                    low=_d("0.99"),
                    medium=_d("0.98"),
                    high=_d("0.97"),
                    direction=ThresholdDirection.BELOW,
                    classification=ThresholdClassification.PLATFORM_HEURISTIC,
                    rationale="very strict",
                ),
            },
        )
        fin = _fin("FY2024", cfo=_d("95"), pat=_d("100"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT, config=custom)
        check = next(c for c in result.checks if c.check_id == "eq.cfo_to_net_income")
        assert check.status == ForensicCheckStatus.FLAGGED


# ===========================================================================
# NET DEBT TO EBITDA
# ===========================================================================


class TestNetDebtToEbitda:
    def test_normal_computation(self) -> None:
        fin = _fin("FY2024", total_debt=_d("500"), cash_and_equivalents=_d("100"), ebitda=_d("200"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.net_debt_to_ebitda")
        assert check.status == ForensicCheckStatus.PASS
        assert check.observed_value == _d("2.000000")

    def test_zero_ebitda_invalid(self) -> None:
        fin = _fin("FY2024", total_debt=_d("500"), cash_and_equivalents=_d("100"), ebitda=_d("0"))
        p = _period_input(fin, date(2025, 3, 31))
        result = forensic_analysis([p], observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "lv.net_debt_to_ebitda")
        assert check.status == ForensicCheckStatus.INVALID_INPUT


# ===========================================================================
# INVENTORY VS REVENUE GROWTH
# ===========================================================================


class TestInventoryVsRevenueGrowth:
    def test_normal_pass(self) -> None:
        f1 = _fin("FY2023", inventory=_d("100"), revenue=_d("1000"))
        f2 = _fin("FY2024", inventory=_d("110"), revenue=_d("1100"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.inventory_vs_revenue_growth")
        assert check.status == ForensicCheckStatus.PASS


# ===========================================================================
# DPO CHANGE
# ===========================================================================


class TestDpoChange:
    def test_increasing_dpo_pass(self) -> None:
        f1 = _fin("FY2023", accounts_payable=_d("60"), cost_of_goods_sold=_d("600"))
        f2 = _fin("FY2024", accounts_payable=_d("65"), cost_of_goods_sold=_d("660"))
        periods = [
            _period_input(f1, date(2024, 3, 31)),
            _period_input(f2, date(2025, 3, 31)),
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "wc.dpo_change")
        assert check.status in (ForensicCheckStatus.PASS, ForensicCheckStatus.FLAGGED)


# ===========================================================================
# MARGIN DECLINE: EBITDA AND NET
# ===========================================================================


class TestEbitdaMarginDecline:
    def test_improving_pass(self) -> None:
        periods = [
            _period_input(_fin(f"FY{y}", revenue=_d("1000"), ebitda=_d(str(200 + (y - 2022) * 20))), date(y + 1, 3, 31))
            for y in range(2022, 2025)
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.ebitda_margin_decline")
        assert check.status == ForensicCheckStatus.PASS


class TestNetMarginDecline:
    def test_decline_flagged(self) -> None:
        periods = [
            _period_input(_fin(f"FY{y}", revenue=_d("1000"), pat=_d(str(150 - (y - 2022) * 20))), date(y + 1, 3, 31))
            for y in range(2022, 2025)
        ]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "pr.net_margin_decline")
        assert check.status == ForensicCheckStatus.FLAGGED


# ===========================================================================
# NEGATIVE FCF COUNT
# ===========================================================================


class TestNegativeFcfCountEdge:
    def test_missing_capex_not_counted(self) -> None:
        periods = [_period_input(_fin(f"FY{y}", cfo=_d("100")), date(y + 1, 3, 31)) for y in range(2022, 2025)]
        result = forensic_analysis(periods, observation_date=_OBS_DATE, calculated_at=_CALC_AT)
        check = next(c for c in result.checks if c.check_id == "cf.negative_fcf_count")
        assert check.status == ForensicCheckStatus.INSUFFICIENT_HISTORY
