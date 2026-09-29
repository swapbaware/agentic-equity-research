"""Tests for shared valuation calculation helpers (_valuation_calc.py).

Verifies that the extracted pure functions produce correct results
independently of any engine. These tests complement — not replace —
the integration tests in test_valuation_bands.py.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.valuation._valuation_calc import (
    CURRENCY_QUANTIZE,
    HALF,
    HUNDRED,
    ONE,
    TWO,
    ZERO,
    compute_observation,
    denom_status,
    ev_components,
    median_value,
    nearest_rank_index,
    percentile_rank,
    std_dev,
    sufficiency,
    timing_status,
    validate_percentiles,
)
from app.valuation.models import (
    CashFlowBasis,
    DataSufficiency,
    DataSufficiencyThresholds,
    FinancialPeriodType,
    HistoricalObservationInput,
    ObservationStatus,
    ValuationMethodType,
)

D = Decimal

_DEFAULT_PRICE = D("100")
_DEFAULT_SHARES = D("1000000")


def _obs(
    obs_date: date = date(2024, 6, 1),
    price: Decimal = _DEFAULT_PRICE,
    shares: Decimal = _DEFAULT_SHARES,
    *,
    avail_date: date | None = date(2024, 3, 15),
    eps: Decimal | None = None,
    revenue: Decimal | None = None,
    ebitda: Decimal | None = None,
    total_equity: Decimal | None = None,
    total_debt: Decimal | None = None,
    cash: Decimal | None = None,
    cfo: Decimal | None = None,
    capex: Decimal | None = None,
    ebit: Decimal | None = None,
    tax_rate: Decimal | None = None,
    da: Decimal | None = None,
    delta_nwc: Decimal | None = None,
) -> HistoricalObservationInput:
    return HistoricalObservationInput(
        observation_date=obs_date,
        price=price,
        shares_outstanding=shares,
        financial_period="FY2024",
        financial_period_type=FinancialPeriodType.ANNUAL,
        financials_available_date=avail_date,
        eps=eps,
        revenue=revenue,
        ebitda=ebitda,
        total_equity=total_equity,
        total_debt=total_debt,
        cash_and_equivalents=cash,
        cfo=cfo,
        capex=capex,
        ebit=ebit,
        effective_tax_rate=tax_rate,
        depreciation_amortization=da,
        delta_nwc=delta_nwc,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_zero(self) -> None:
        assert D("0") == ZERO

    def test_one(self) -> None:
        assert D("1") == ONE

    def test_two(self) -> None:
        assert D("2") == TWO

    def test_hundred(self) -> None:
        assert D("100") == HUNDRED

    def test_half(self) -> None:
        assert D("0.5") == HALF

    def test_currency_quantize(self) -> None:
        assert D("0.0001") == CURRENCY_QUANTIZE


# ---------------------------------------------------------------------------
# validate_percentiles
# ---------------------------------------------------------------------------


class TestValidatePercentiles:
    def test_valid(self) -> None:
        validate_percentiles([D("0"), D("25"), D("50"), D("75"), D("100")])

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="percentile must be in"):
            validate_percentiles([D("-1")])

    def test_over_100_raises(self) -> None:
        with pytest.raises(ValueError, match="percentile must be in"):
            validate_percentiles([D("101")])

    def test_empty_is_valid(self) -> None:
        validate_percentiles([])


# ---------------------------------------------------------------------------
# timing_status
# ---------------------------------------------------------------------------


class TestTimingStatus:
    def test_valid(self) -> None:
        obs = _obs(avail_date=date(2024, 3, 15))
        assert timing_status(obs) == ObservationStatus.VALID

    def test_valid_same_day(self) -> None:
        obs = _obs(obs_date=date(2024, 6, 1), avail_date=date(2024, 6, 1))
        assert timing_status(obs) == ObservationStatus.VALID

    def test_look_ahead_risk(self) -> None:
        obs = _obs(obs_date=date(2024, 1, 1), avail_date=date(2024, 6, 1))
        assert timing_status(obs) == ObservationStatus.LOOK_AHEAD_RISK

    def test_unverified(self) -> None:
        obs = _obs(avail_date=None)
        assert timing_status(obs) == ObservationStatus.UNVERIFIED_TIMING


# ---------------------------------------------------------------------------
# denom_status
# ---------------------------------------------------------------------------


class TestDenomStatus:
    def test_positive(self) -> None:
        assert denom_status(D("10")) is None

    def test_zero(self) -> None:
        assert denom_status(D("0")) == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR

    def test_negative(self) -> None:
        assert denom_status(D("-5")) == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR


# ---------------------------------------------------------------------------
# ev_components
# ---------------------------------------------------------------------------


class TestEvComponents:
    def test_valid(self) -> None:
        obs = _obs(total_debt=D("500"), cash=D("200"))
        mcap = D("1000")
        result = ev_components(obs, mcap)
        assert result is not None
        net_debt, ev = result
        assert net_debt == D("300.0000")
        assert ev == D("1300.0000")

    def test_net_cash(self) -> None:
        obs = _obs(total_debt=D("100"), cash=D("500"))
        mcap = D("1000")
        result = ev_components(obs, mcap)
        assert result is not None
        net_debt, ev = result
        assert net_debt == D("-400.0000")
        assert ev == D("600.0000")

    def test_missing_debt(self) -> None:
        obs = _obs(total_debt=None, cash=D("200"))
        assert ev_components(obs, D("1000")) is None

    def test_missing_cash(self) -> None:
        obs = _obs(total_debt=D("500"), cash=None)
        assert ev_components(obs, D("1000")) is None


# ---------------------------------------------------------------------------
# compute_observation — basic per-method smoke tests
# ---------------------------------------------------------------------------


class TestComputeObservation:
    def test_pe(self) -> None:
        obs = _obs(eps=D("10"))
        result = compute_observation(
            obs, ValuationMethodType.PE, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.value == D("10.000000")
        assert result.calculation is not None
        assert result.calculation.metric == "test_pe"
        assert result.calculation.version == "1.0.0"

    def test_ev_ebitda(self) -> None:
        obs = _obs(ebitda=D("50"), total_debt=D("200"), cash=D("50"))
        result = compute_observation(
            obs, ValuationMethodType.EV_EBITDA, ObservationStatus.VALID,
            engine_version="2.0.0", metric_prefix="custom",
        )
        assert result.value is not None
        assert result.calculation is not None
        assert result.calculation.metric == "custom_ev_ebitda"
        assert result.calculation.version == "2.0.0"

    def test_ps(self) -> None:
        obs = _obs(revenue=D("500000"))
        result = compute_observation(
            obs, ValuationMethodType.PS, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.value is not None
        assert result.calculation is not None
        assert result.calculation.metric == "test_ps"

    def test_pb(self) -> None:
        obs = _obs(total_equity=D("800000"))
        result = compute_observation(
            obs, ValuationMethodType.PB, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.value is not None

    def test_fcf_yield(self) -> None:
        obs = _obs(cfo=D("100000"), capex=D("30000"))
        result = compute_observation(
            obs, ValuationMethodType.FCF_YIELD, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.value is not None
        assert result.cash_flow_basis == CashFlowBasis.EQUITY_FCF

    def test_ev_fcf(self) -> None:
        obs = _obs(
            total_debt=D("200"), cash=D("50"),
            ebit=D("100"), tax_rate=D("0.25"),
            da=D("20"), capex=D("30"), delta_nwc=D("10"),
        )
        result = compute_observation(
            obs, ValuationMethodType.EV_FCF, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.value is not None
        assert result.cash_flow_basis == CashFlowBasis.FCFF

    def test_missing_data(self) -> None:
        obs = _obs()
        result = compute_observation(
            obs, ValuationMethodType.PE, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.status == ObservationStatus.EXCLUDED_MISSING_DATA
        assert result.value is None

    def test_negative_denominator(self) -> None:
        obs = _obs(eps=D("-5"))
        result = compute_observation(
            obs, ValuationMethodType.PE, ObservationStatus.VALID,
            engine_version="1.0.0", metric_prefix="test",
        )
        assert result.status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR

    def test_unsupported_method(self) -> None:
        obs = _obs(eps=D("10"))
        with pytest.raises(ValueError, match="Unsupported method"):
            compute_observation(
                obs, ValuationMethodType.PEG, ObservationStatus.VALID,
                engine_version="1.0.0", metric_prefix="test",
            )


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


class TestNearestRankIndex:
    def test_p0(self) -> None:
        assert nearest_rank_index(D("0"), 5) == 0

    def test_p100(self) -> None:
        assert nearest_rank_index(D("100"), 5) == 4

    def test_p50_odd(self) -> None:
        assert nearest_rank_index(D("50"), 5) == 2

    def test_p25_even(self) -> None:
        assert nearest_rank_index(D("25"), 4) == 0

    def test_p75_even(self) -> None:
        assert nearest_rank_index(D("75"), 4) == 2


class TestMedianValue:
    def test_odd(self) -> None:
        assert median_value([D("1"), D("2"), D("3")]) == D("2")

    def test_even(self) -> None:
        assert median_value([D("1"), D("2"), D("3"), D("4")]) == D("2.500000")

    def test_single(self) -> None:
        assert median_value([D("42")]) == D("42")


class TestStdDev:
    def test_single_returns_none(self) -> None:
        assert std_dev([D("10")], D("10")) is None

    def test_two_values(self) -> None:
        result = std_dev([D("10"), D("20")], D("15"))
        assert result is not None
        assert result > D("0")

    def test_all_same(self) -> None:
        result = std_dev([D("5"), D("5"), D("5")], D("5"))
        assert result == D("0.000000")


class TestSufficiency:
    def test_zero_insufficient(self) -> None:
        t = DataSufficiencyThresholds(min_minimal=3, min_low=5, min_moderate=10)
        assert sufficiency(0, t) == DataSufficiency.INSUFFICIENT

    def test_minimal(self) -> None:
        t = DataSufficiencyThresholds(min_minimal=3, min_low=5, min_moderate=10)
        assert sufficiency(1, t) == DataSufficiency.MINIMAL
        assert sufficiency(2, t) == DataSufficiency.MINIMAL

    def test_low(self) -> None:
        t = DataSufficiencyThresholds(min_minimal=3, min_low=5, min_moderate=10)
        assert sufficiency(3, t) == DataSufficiency.LOW
        assert sufficiency(4, t) == DataSufficiency.LOW

    def test_moderate(self) -> None:
        t = DataSufficiencyThresholds(min_minimal=3, min_low=5, min_moderate=10)
        assert sufficiency(5, t) == DataSufficiency.MODERATE
        assert sufficiency(9, t) == DataSufficiency.MODERATE

    def test_adequate(self) -> None:
        t = DataSufficiencyThresholds(min_minimal=3, min_low=5, min_moderate=10)
        assert sufficiency(10, t) == DataSufficiency.ADEQUATE
        assert sufficiency(50, t) == DataSufficiency.ADEQUATE


class TestPercentileRank:
    def test_below_all(self) -> None:
        rank = percentile_rank(D("1"), [D("10"), D("20"), D("30")])
        assert rank is not None
        assert rank == D("0.000000")

    def test_above_all(self) -> None:
        rank = percentile_rank(D("100"), [D("10"), D("20"), D("30")])
        assert rank is not None
        assert rank == D("100.000000")

    def test_at_median(self) -> None:
        rank = percentile_rank(D("20"), [D("10"), D("20"), D("30")])
        assert rank is not None
        expected = (D("1") + D("0.5") * D("1")) / D("3") * D("100")
        assert rank == expected.quantize(D("0.000001"))

    def test_empty_returns_none(self) -> None:
        assert percentile_rank(D("10"), []) is None

    def test_all_equal(self) -> None:
        rank = percentile_rank(D("10"), [D("10"), D("10"), D("10")])
        assert rank is not None
        assert rank == D("50.000000")
