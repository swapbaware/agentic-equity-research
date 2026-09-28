"""Tests for CAGR calculations — growth module."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.analytics.growth import (
    VERSION,
    _cagr,
    ebit_cagr,
    ebitda_cagr,
    eps_cagr,
    pat_cagr,
    revenue_cagr,
)
from app.analytics.models import PeriodFinancials


def _period(*, revenue: Decimal | None = None, ebitda: Decimal | None = None,
            ebit: Decimal | None = None, pat: Decimal | None = None,
            eps: Decimal | None = None, name: str = "FY2024") -> PeriodFinancials:
    return PeriodFinancials(
        period=name, revenue=revenue, ebitda=ebitda, ebit=ebit, pat=pat, eps=eps,
    )


class TestCoreCagr:
    """Verify the core CAGR formula with hand-computed values."""

    def test_exact_10_percent_over_2_years(self) -> None:
        # 1.1^2 = 1.21, so (121/100)^(1/2) - 1 = 0.1
        val, note = _cagr(Decimal("100"), Decimal("121"), 2)
        assert val == Decimal("0.100000")
        assert note is None

    def test_exact_10_percent_over_3_years(self) -> None:
        # 1.1^3 = 1.331
        val, note = _cagr(Decimal("1000"), Decimal("1331"), 3)
        assert val == Decimal("0.100000")
        assert note is None

    def test_approximate_cagr_5_years(self) -> None:
        # 2^(1/5) - 1 ≈ 0.148698
        val, note = _cagr(Decimal("100"), Decimal("200"), 5)
        assert val is not None
        assert val == Decimal("0.148698")
        assert note is None

    def test_zero_growth(self) -> None:
        val, note = _cagr(Decimal("100"), Decimal("100"), 3)
        assert val == Decimal("0.000000")
        assert note is None

    def test_one_year_is_simple_growth(self) -> None:
        # (120/100) - 1 = 0.2
        val, note = _cagr(Decimal("100"), Decimal("120"), 1)
        assert val == Decimal("0.200000")

    def test_decline(self) -> None:
        # 80/100 over 1 year = -0.2
        val, note = _cagr(Decimal("100"), Decimal("80"), 1)
        assert val == Decimal("-0.200000")

    def test_negative_start_returns_none(self) -> None:
        val, note = _cagr(Decimal("-100"), Decimal("200"), 2)
        assert val is None
        assert note is not None

    def test_negative_end_returns_none(self) -> None:
        val, note = _cagr(Decimal("100"), Decimal("-50"), 2)
        assert val is None

    def test_zero_start_returns_none(self) -> None:
        val, note = _cagr(Decimal("0"), Decimal("200"), 2)
        assert val is None

    def test_zero_end_returns_none(self) -> None:
        val, note = _cagr(Decimal("100"), Decimal("0"), 2)
        assert val is None

    def test_zero_years_returns_none(self) -> None:
        val, note = _cagr(Decimal("100"), Decimal("200"), 0)
        assert val is None
        assert "years must be positive" in str(note)

    def test_none_inputs_returns_none(self) -> None:
        val, note = _cagr(None, Decimal("200"), 2)
        assert val is None
        assert "missing" in str(note)


class TestRevenueCagr:
    def test_basic(self) -> None:
        start = _period(revenue=Decimal("1000"), name="FY2020")
        end = _period(revenue=Decimal("1210"), name="FY2022")
        result = revenue_cagr(start, end, 2)
        assert result.metric == "revenue_cagr"
        assert result.value == Decimal("0.100000")
        assert result.period == "FY2020-FY2022"

    def test_missing_revenue(self) -> None:
        start = _period(name="FY2020")
        end = _period(revenue=Decimal("1210"), name="FY2022")
        result = revenue_cagr(start, end, 2)
        assert result.value is None
        assert result.notes is not None

    def test_inputs_recorded(self) -> None:
        start = _period(revenue=Decimal("500"), name="FY2021")
        end = _period(revenue=Decimal("800"), name="FY2024")
        result = revenue_cagr(start, end, 3)
        assert result.inputs["start_value"] == Decimal("500")
        assert result.inputs["end_value"] == Decimal("800")
        assert result.inputs["years"] == 3

    def test_formula_documented(self) -> None:
        start = _period(revenue=Decimal("100"), name="FY2020")
        end = _period(revenue=Decimal("200"), name="FY2023")
        result = revenue_cagr(start, end, 3)
        assert "revenue" in result.formula
        assert result.version == VERSION

    def test_unit_is_ratio(self) -> None:
        start = _period(revenue=Decimal("100"), name="FY2020")
        end = _period(revenue=Decimal("200"), name="FY2023")
        result = revenue_cagr(start, end, 3)
        assert result.unit == "ratio"


class TestOtherCagrs:
    def test_ebitda_cagr(self) -> None:
        start = _period(ebitda=Decimal("100"), name="FY2020")
        end = _period(ebitda=Decimal("121"), name="FY2022")
        result = ebitda_cagr(start, end, 2)
        assert result.metric == "ebitda_cagr"
        assert result.value == Decimal("0.100000")

    def test_ebit_cagr(self) -> None:
        start = _period(ebit=Decimal("200"), name="FY2021")
        end = _period(ebit=Decimal("242"), name="FY2023")
        result = ebit_cagr(start, end, 2)
        assert result.metric == "ebit_cagr"
        assert result.value == Decimal("0.100000")

    def test_pat_cagr(self) -> None:
        start = _period(pat=Decimal("1000"), name="FY2020")
        end = _period(pat=Decimal("1331"), name="FY2023")
        result = pat_cagr(start, end, 3)
        assert result.metric == "pat_cagr"
        assert result.value == Decimal("0.100000")

    def test_eps_cagr(self) -> None:
        start = _period(eps=Decimal("10"), name="FY2020")
        end = _period(eps=Decimal("12.1"), name="FY2022")
        result = eps_cagr(start, end, 2)
        assert result.metric == "eps_cagr"
        assert result.value == Decimal("0.100000")


class TestCagrResultImmutability:
    def test_result_is_frozen(self) -> None:
        start = _period(revenue=Decimal("100"), name="FY2020")
        end = _period(revenue=Decimal("200"), name="FY2023")
        result = revenue_cagr(start, end, 3)
        with pytest.raises(ValidationError):
            result.value = Decimal("0")  # type: ignore[misc]
