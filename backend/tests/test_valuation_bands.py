"""Comprehensive tests for the Historical Valuation Bands engine.

Covers: all six methods, point-in-time validation, duplicate detection,
structural validation, missing/zero/negative data, statistics, percentile
bands (nearest-rank), percentile rank (midpoint), data sufficiency,
current position, lookback filtering, determinism, edge cases, and a
golden dataset.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.valuation.historical_bands import (
    ENGINE_VERSION,
    HistoricalBandError,
    _detect_duplicates,
    _median,
    _nearest_rank_index,
    _percentile_rank,
    _std_dev,
    _sufficiency,
    _timing_status,
    historical_valuation_bands,
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
CALC_AT = datetime(2025, 6, 15, 10, 0, 0)
_DEFAULT_PRICE = D("100")
_DEFAULT_SHARES = D("1000000")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _obs(
    obs_date: date,
    price: Decimal = _DEFAULT_PRICE,
    shares: Decimal = _DEFAULT_SHARES,
    *,
    fin_period: str = "FY2024",
    fin_type: FinancialPeriodType = FinancialPeriodType.ANNUAL,
    avail_date: date | None = None,
    eps: Decimal | None = None,
    revenue: Decimal | None = None,
    ebitda: Decimal | None = None,
    ebit: Decimal | None = None,
    total_equity: Decimal | None = None,
    total_debt: Decimal | None = None,
    cash: Decimal | None = None,
    cfo: Decimal | None = None,
    capex: Decimal | None = None,
    da: Decimal | None = None,
    tax_rate: Decimal | None = None,
    delta_nwc: Decimal | None = None,
) -> HistoricalObservationInput:
    return HistoricalObservationInput(
        observation_date=obs_date,
        price=price,
        shares_outstanding=shares,
        financial_period=fin_period,
        financial_period_type=fin_type,
        financials_available_date=avail_date,
        eps=eps,
        revenue=revenue,
        ebitda=ebitda,
        ebit=ebit,
        total_equity=total_equity,
        total_debt=total_debt,
        cash_and_equivalents=cash,
        cfo=cfo,
        capex=capex,
        depreciation_amortization=da,
        effective_tax_rate=tax_rate,
        delta_nwc=delta_nwc,
    )


def _pe_obs(obs_date: date, price: Decimal, eps: Decimal, avail: date | None = None) -> HistoricalObservationInput:
    avail = avail if avail is not None else date(obs_date.year, 1, 1)
    return _obs(obs_date, price, eps=eps, avail_date=avail)


# ---------------------------------------------------------------------------
# 1. P/E method
# ---------------------------------------------------------------------------


class TestPEMethod:
    def test_basic_pe(self) -> None:
        obs = [
            _pe_obs(date(2024, 3, 1), D("200"), D("10")),
            _pe_obs(date(2024, 6, 1), D("250"), D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.method == ValuationMethodType.PE
        assert result.engine_version == ENGINE_VERSION
        assert result.calculated_at == CALC_AT

        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 2
        assert valid[0].value == D("200") / D("10")
        assert valid[1].value == D("250") / D("10")
        assert all(o.calculation is not None for o in valid)
        assert all(o.calculation.formula == "Price / EPS" for o in valid)

    def test_pe_negative_eps(self) -> None:
        obs = [_pe_obs(date(2024, 3, 1), D("200"), D("-5"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR
        assert result.statistics is None

    def test_pe_zero_eps(self) -> None:
        obs = [_pe_obs(date(2024, 3, 1), D("200"), D("0"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR

    def test_pe_missing_eps(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA


# ---------------------------------------------------------------------------
# 2. EV/EBITDA method
# ---------------------------------------------------------------------------


class TestEVEBITDAMethod:
    def test_basic_ev_ebitda(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), D("100"), D("1000000"),
            avail_date=date(2024, 1, 1),
            ebitda=D("20000000"),
            total_debt=D("50000000"),
            cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 1
        o = valid[0]
        assert o.value is not None
        assert o.enterprise_value is not None
        assert o.net_debt is not None
        assert o.calculation is not None
        assert o.calculation.formula == "Enterprise Value / EBITDA"

    def test_ev_ebitda_missing_debt(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1), ebitda=D("20000000"))]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_ev_ebitda_zero_ebitda(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            ebitda=D("0"), total_debt=D("50000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR

    def test_ev_ebitda_negative_ebitda(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            ebitda=D("-1000"), total_debt=D("50000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR


# ---------------------------------------------------------------------------
# 3. P/S method
# ---------------------------------------------------------------------------


class TestPSMethod:
    def test_basic_ps(self) -> None:
        obs = [_obs(date(2024, 3, 1), D("50"), avail_date=date(2024, 1, 1), revenue=D("100000000"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PS, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 1
        market_cap = D("50") * D("1000000")
        expected_ps = market_cap / D("100000000")
        assert valid[0].value == expected_ps.quantize(D("0.000001"))
        assert valid[0].calculation is not None
        assert valid[0].calculation.formula == "Market Cap / Revenue"

    def test_ps_missing_revenue(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1))]
        result = historical_valuation_bands(obs, ValuationMethodType.PS, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_ps_zero_revenue(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1), revenue=D("0"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PS, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR


# ---------------------------------------------------------------------------
# 4. P/B method
# ---------------------------------------------------------------------------


class TestPBMethod:
    def test_basic_pb(self) -> None:
        obs = [_obs(date(2024, 3, 1), D("100"), avail_date=date(2024, 1, 1), total_equity=D("50000000"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PB, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 1
        market_cap = D("100") * D("1000000")
        assert valid[0].value == (market_cap / D("50000000")).quantize(D("0.000001"))
        assert valid[0].calculation is not None
        assert valid[0].calculation.formula == "Market Cap / Total Equity"

    def test_pb_negative_equity(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1), total_equity=D("-10000000"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PB, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR


# ---------------------------------------------------------------------------
# 5. FCF Yield method
# ---------------------------------------------------------------------------


class TestFCFYieldMethod:
    def test_basic_fcf_yield(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), D("100"), avail_date=date(2024, 1, 1),
            cfo=D("15000000"), capex=D("5000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 1
        equity_fcf = D("15000000") - D("5000000")
        market_cap = D("100") * D("1000000")
        expected = (equity_fcf / market_cap).quantize(D("0.000001"))
        assert valid[0].value == expected
        assert valid[0].cash_flow_basis == CashFlowBasis.EQUITY_FCF
        assert valid[0].calculation is not None
        assert valid[0].calculation.formula == "(CFO − CapEx) / Market Cap"

    def test_fcf_yield_missing_cfo(self) -> None:
        obs = [_obs(date(2024, 3, 1), avail_date=date(2024, 1, 1), capex=D("5000000"))]
        result = historical_valuation_bands(obs, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_fcf_yield_negative_fcf(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            cfo=D("3000000"), capex=D("5000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR

    def test_fcf_yield_zero_fcf(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            cfo=D("5000000"), capex=D("5000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR


# ---------------------------------------------------------------------------
# 6. EV/FCF method (FCFF)
# ---------------------------------------------------------------------------


class TestEVFCFMethod:
    def test_basic_ev_fcf(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), D("100"), avail_date=date(2024, 1, 1),
            ebit=D("30000000"),
            tax_rate=D("0.25"),
            da=D("5000000"),
            capex=D("8000000"),
            delta_nwc=D("2000000"),
            total_debt=D("40000000"),
            cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert len(valid) == 1
        o = valid[0]
        assert o.cash_flow_basis == CashFlowBasis.FCFF

        assert o.value is not None
        assert o.calculation is not None
        assert o.calculation.formula == "Enterprise Value / FCFF"
        assert o.calculation.inputs["fcff"] is not None

    def test_ev_fcf_missing_ebit(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            tax_rate=D("0.25"), da=D("5000000"),
            capex=D("8000000"), delta_nwc=D("2000000"),
            total_debt=D("40000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA
        assert result.observations[0].cash_flow_basis == CashFlowBasis.FCFF

    def test_ev_fcf_missing_delta_nwc(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            ebit=D("30000000"), tax_rate=D("0.25"), da=D("5000000"),
            capex=D("8000000"),
            total_debt=D("40000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_ev_fcf_zero_fcff(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), avail_date=date(2024, 1, 1),
            ebit=D("10000000"), tax_rate=D("0.25"),
            da=D("2500000"), capex=D("10000000"),
            delta_nwc=D("0"),
            total_debt=D("40000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        nopat = D("10000000") * D("0.75")
        fcff = nopat + D("2500000") - D("10000000") - D("0")
        assert result.observations[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR if fcff == D("0") else True


# ---------------------------------------------------------------------------
# 7. Point-in-time validation
# ---------------------------------------------------------------------------


class TestPointInTimeValidation:
    def test_valid_timing(self) -> None:
        obs = _obs(date(2024, 6, 1), avail_date=date(2024, 5, 1), eps=D("10"))
        assert _timing_status(obs) == ObservationStatus.VALID

    def test_same_day_is_valid(self) -> None:
        obs = _obs(date(2024, 6, 1), avail_date=date(2024, 6, 1), eps=D("10"))
        assert _timing_status(obs) == ObservationStatus.VALID

    def test_look_ahead_risk(self) -> None:
        obs = _obs(date(2024, 6, 1), avail_date=date(2024, 7, 1), eps=D("10"))
        assert _timing_status(obs) == ObservationStatus.LOOK_AHEAD_RISK

    def test_unverified_timing(self) -> None:
        obs = _obs(date(2024, 6, 1), eps=D("10"))
        assert _timing_status(obs) == ObservationStatus.UNVERIFIED_TIMING

    def test_look_ahead_excluded_from_statistics(self) -> None:
        obs = [
            _pe_obs(date(2024, 3, 1), D("100"), D("10"), avail=date(2024, 2, 1)),
            _pe_obs(date(2024, 6, 1), D("200"), D("10"), avail=date(2024, 2, 1)),
            _obs(date(2024, 9, 1), D("300"), eps=D("10"), avail_date=date(2024, 12, 1)),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        look_ahead = [o for o in result.observations if o.status == ObservationStatus.LOOK_AHEAD_RISK]
        assert len(look_ahead) == 1
        assert look_ahead[0].value is not None
        assert result.statistics is not None
        assert result.statistics.valid_count == 2

    def test_unverified_excluded_from_statistics(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _obs(date(2024, 6, 1), D("300"), eps=D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        unverified = [o for o in result.observations if o.status == ObservationStatus.UNVERIFIED_TIMING]
        assert len(unverified) == 1
        assert unverified[0].value is not None
        assert result.statistics is not None
        assert result.statistics.valid_count == 1
        assert result.statistics.unverified_count == 1


# ---------------------------------------------------------------------------
# 8. Duplicate detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    def test_identical_duplicates_deduped(self) -> None:
        obs1 = _pe_obs(date(2024, 3, 1), D("100"), D("10"))
        obs2 = _pe_obs(date(2024, 3, 1), D("100"), D("10"))
        non_dup, dup_obs = _detect_duplicates([obs1, obs2], ValuationMethodType.PE)
        assert len(non_dup) == 1
        assert len(dup_obs) == 1
        assert dup_obs[0].status == ObservationStatus.DUPLICATE_OBSERVATION

    def test_contradictory_duplicates_raise(self) -> None:
        obs1 = _pe_obs(date(2024, 3, 1), D("100"), D("10"))
        obs2 = _pe_obs(date(2024, 3, 1), D("200"), D("10"))
        with pytest.raises(HistoricalBandError, match="Contradictory"):
            _detect_duplicates([obs1, obs2], ValuationMethodType.PE)

    def test_triple_identical_dedup(self) -> None:
        obs = _pe_obs(date(2024, 3, 1), D("100"), D("10"))
        non_dup, dup_obs = _detect_duplicates([obs, obs, obs], ValuationMethodType.PE)
        assert len(non_dup) == 1
        assert len(dup_obs) == 2

    def test_no_duplicates(self) -> None:
        obs = [
            _pe_obs(date(2024, 3, 1), D("100"), D("10")),
            _pe_obs(date(2024, 6, 1), D("200"), D("10")),
        ]
        non_dup, dup_obs = _detect_duplicates(obs, ValuationMethodType.PE)
        assert len(non_dup) == 2
        assert len(dup_obs) == 0


# ---------------------------------------------------------------------------
# 9. Structural validation
# ---------------------------------------------------------------------------


class TestStructuralValidation:
    def test_zero_price_excluded(self) -> None:
        obs = [_obs(date(2024, 3, 1), D("0"), avail_date=date(2024, 1, 1), eps=D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA
        assert result.statistics is None

    def test_negative_price_excluded(self) -> None:
        obs = [_obs(date(2024, 3, 1), D("-50"), avail_date=date(2024, 1, 1), eps=D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_zero_shares_excluded(self) -> None:
        obs = [_obs(date(2024, 3, 1), D("100"), D("0"), avail_date=date(2024, 1, 1), eps=D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.EXCLUDED_MISSING_DATA


# ---------------------------------------------------------------------------
# 10. Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    @pytest.fixture()
    def five_pe_obs(self) -> list[HistoricalObservationInput]:
        return [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 4, 1), D("150"), D("10")),
            _pe_obs(date(2024, 7, 1), D("120"), D("10")),
            _pe_obs(date(2024, 10, 1), D("180"), D("10")),
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
        ]

    def test_min_max(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.min == D("10") / D("1")
        assert result.statistics.max == D("20") / D("1")

    def test_mean(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        values = sorted([D("10"), D("15"), D("12"), D("18"), D("20")])
        expected_mean = sum(values) / D("5")
        assert result.statistics.mean == expected_mean.quantize(D("0.000001"))

    def test_median_odd_count(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.median == D("15")

    def test_median_even_count(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 4, 1), D("150"), D("10")),
            _pe_obs(date(2024, 7, 1), D("120"), D("10")),
            _pe_obs(date(2024, 10, 1), D("180"), D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        expected = (D("12") + D("15")) / D("2")
        assert result.statistics.median == expected.quantize(D("0.000001"))

    def test_std_dev_present(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.std_dev is not None
        assert result.statistics.std_dev > D("0")

    def test_std_dev_none_for_single(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.std_dev is None

    def test_valid_count(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 5

    def test_calculation_audit_trail(self, five_pe_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(five_pe_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        metrics = {c.metric for c in result.statistics.calculations}
        assert "historical_pe_min" in metrics
        assert "historical_pe_max" in metrics
        assert "historical_pe_mean" in metrics
        assert "historical_pe_median" in metrics


# ---------------------------------------------------------------------------
# 11. Nearest-rank percentile
# ---------------------------------------------------------------------------


class TestNearestRankPercentile:
    def test_p0_returns_first(self) -> None:
        assert _nearest_rank_index(D("0"), 5) == 0

    def test_p100_returns_last(self) -> None:
        assert _nearest_rank_index(D("100"), 5) == 4

    def test_p50_of_5(self) -> None:
        idx = _nearest_rank_index(D("50"), 5)
        assert idx == 2

    def test_p25_of_4(self) -> None:
        idx = _nearest_rank_index(D("25"), 4)
        assert idx == 0

    def test_p75_of_4(self) -> None:
        idx = _nearest_rank_index(D("75"), 4)
        assert idx == 2

    def test_p10_of_10(self) -> None:
        idx = _nearest_rank_index(D("10"), 10)
        assert idx == 0

    def test_p90_of_10(self) -> None:
        idx = _nearest_rank_index(D("90"), 10)
        assert idx == 8

    def test_bands_in_result(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 2, 1), D("120"), D("10")),
            _pe_obs(date(2024, 3, 1), D("140"), D("10")),
            _pe_obs(date(2024, 4, 1), D("160"), D("10")),
            _pe_obs(date(2024, 5, 1), D("180"), D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        band_pcts = {b.percentile for b in result.statistics.bands}
        assert D("10") in band_pcts
        assert D("25") in band_pcts
        assert D("50") in band_pcts
        assert D("75") in band_pcts
        assert D("90") in band_pcts

    def test_custom_percentiles(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 2, 1), D("120"), D("10")),
            _pe_obs(date(2024, 3, 1), D("140"), D("10")),
            _pe_obs(date(2024, 4, 1), D("160"), D("10")),
        ]
        result = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            percentiles=[D("20"), D("80")],
        )
        assert result.statistics is not None
        assert len(result.statistics.bands) == 2
        assert result.statistics.bands[0].percentile == D("20")
        assert result.statistics.bands[1].percentile == D("80")

    def test_invalid_percentile_raises(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        with pytest.raises(HistoricalBandError, match="percentile"):
            historical_valuation_bands(
                obs, ValuationMethodType.PE,
                calculated_at=CALC_AT,
                percentiles=[D("150")],
            )


# ---------------------------------------------------------------------------
# 12. Percentile rank (midpoint)
# ---------------------------------------------------------------------------


class TestPercentileRank:
    def test_below_all(self) -> None:
        rank = _percentile_rank(D("1"), [D("10"), D("20"), D("30")])
        assert rank is not None
        assert rank == D("0")

    def test_above_all(self) -> None:
        rank = _percentile_rank(D("100"), [D("10"), D("20"), D("30")])
        assert rank is not None
        assert rank == D("100")

    def test_at_median(self) -> None:
        rank = _percentile_rank(D("20"), [D("10"), D("20"), D("30")])
        assert rank is not None
        expected = (D("1") + D("0.5") * D("1")) / D("3") * D("100")
        assert rank == expected.quantize(D("0.000001"))

    def test_empty_returns_none(self) -> None:
        assert _percentile_rank(D("10"), []) is None

    def test_all_equal(self) -> None:
        rank = _percentile_rank(D("10"), [D("10"), D("10"), D("10")])
        assert rank is not None
        expected = (D("0") + D("0.5") * D("3")) / D("3") * D("100")
        assert rank == expected.quantize(D("0.000001"))


# ---------------------------------------------------------------------------
# 13. Data sufficiency
# ---------------------------------------------------------------------------


class TestDataSufficiency:
    def test_insufficient(self) -> None:
        assert _sufficiency(0, _DEFAULT_THRESHOLDS) == DataSufficiency.INSUFFICIENT

    def test_minimal(self) -> None:
        assert _sufficiency(1, _DEFAULT_THRESHOLDS) == DataSufficiency.MINIMAL
        assert _sufficiency(3, _DEFAULT_THRESHOLDS) == DataSufficiency.MINIMAL

    def test_low(self) -> None:
        assert _sufficiency(4, _DEFAULT_THRESHOLDS) == DataSufficiency.LOW
        assert _sufficiency(11, _DEFAULT_THRESHOLDS) == DataSufficiency.LOW

    def test_moderate(self) -> None:
        assert _sufficiency(12, _DEFAULT_THRESHOLDS) == DataSufficiency.MODERATE
        assert _sufficiency(51, _DEFAULT_THRESHOLDS) == DataSufficiency.MODERATE

    def test_adequate(self) -> None:
        assert _sufficiency(52, _DEFAULT_THRESHOLDS) == DataSufficiency.ADEQUATE
        assert _sufficiency(200, _DEFAULT_THRESHOLDS) == DataSufficiency.ADEQUATE

    def test_custom_thresholds(self) -> None:
        custom = DataSufficiencyThresholds(min_minimal=2, min_low=5, min_moderate=20)
        assert _sufficiency(1, custom) == DataSufficiency.MINIMAL
        assert _sufficiency(2, custom) == DataSufficiency.LOW
        assert _sufficiency(5, custom) == DataSufficiency.MODERATE
        assert _sufficiency(20, custom) == DataSufficiency.ADEQUATE

    def test_sufficiency_in_result(self) -> None:
        obs = [_pe_obs(date(2024, m, 1), D(str(100 + m * 10)), D("10")) for m in range(1, 6)]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.LOW


_DEFAULT_THRESHOLDS = DataSufficiencyThresholds()


# ---------------------------------------------------------------------------
# 14. Current position
# ---------------------------------------------------------------------------


class TestCurrentPosition:
    @pytest.fixture()
    def obs_with_current(self) -> tuple[list[HistoricalObservationInput], HistoricalObservationInput]:
        historical = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 4, 1), D("150"), D("10")),
            _pe_obs(date(2024, 7, 1), D("120"), D("10")),
            _pe_obs(date(2024, 10, 1), D("180"), D("10")),
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
        ]
        current = _pe_obs(date(2025, 6, 1), D("160"), D("10"))
        return historical, current

    def test_current_position_present(
        self,
        obs_with_current: tuple[list[HistoricalObservationInput], HistoricalObservationInput],
    ) -> None:
        historical, current = obs_with_current
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is not None
        assert result.current_position.current_value == D("16")
        assert result.current_position.percentile_rank is not None

    def test_current_position_vs_median(
        self,
        obs_with_current: tuple[list[HistoricalObservationInput], HistoricalObservationInput],
    ) -> None:
        historical, current = obs_with_current
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is not None
        assert result.current_position.vs_median is not None
        assert result.current_position.vs_median == D("16") - D("15")

    def test_current_position_distance_from_median_pct(
        self,
        obs_with_current: tuple[list[HistoricalObservationInput], HistoricalObservationInput],
    ) -> None:
        historical, current = obs_with_current
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is not None
        assert result.current_position.distance_from_median_pct is not None
        expected = (D("16") - D("15")) / D("15") * D("100")
        assert result.current_position.distance_from_median_pct == expected.quantize(D("0.000001"))

    def test_no_current_without_obs(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.current_position is None

    def test_current_position_zero_price_excluded(self) -> None:
        historical = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        current = _obs(date(2025, 1, 1), D("0"), eps=D("10"), avail_date=date(2025, 1, 1))
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is None

    def test_current_position_missing_data(self) -> None:
        historical = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        current = _obs(date(2025, 1, 1), D("100"), avail_date=date(2025, 1, 1))
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is None


# ---------------------------------------------------------------------------
# 15. Lookback filtering
# ---------------------------------------------------------------------------


class TestLookbackFiltering:
    def test_lookback_start(self) -> None:
        obs = [
            _pe_obs(date(2023, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 1, 1), D("150"), D("10")),
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
        ]
        result = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            lookback_start=date(2024, 1, 1),
        )
        assert result.statistics is not None
        assert result.statistics.valid_count == 2

    def test_lookback_end(self) -> None:
        obs = [
            _pe_obs(date(2023, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 1, 1), D("150"), D("10")),
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
        ]
        result = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            lookback_end=date(2024, 6, 1),
        )
        assert result.statistics is not None
        assert result.statistics.valid_count == 2

    def test_lookback_both(self) -> None:
        obs = [
            _pe_obs(date(2023, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 1, 1), D("150"), D("10")),
            _pe_obs(date(2024, 6, 1), D("180"), D("10")),
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
        ]
        result = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            lookback_start=date(2024, 1, 1),
            lookback_end=date(2024, 12, 31),
        )
        assert result.statistics is not None
        assert result.statistics.valid_count == 2


# ---------------------------------------------------------------------------
# 16. Empty / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_observations(self) -> None:
        result = historical_valuation_bands([], ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations == []
        assert result.statistics is None
        assert result.current_position is None

    def test_all_excluded(self) -> None:
        obs = [
            _obs(date(2024, 1, 1), D("0"), avail_date=date(2024, 1, 1), eps=D("10")),
            _obs(date(2024, 2, 1), D("100"), avail_date=date(2024, 1, 1), eps=D("0")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is None

    def test_single_observation(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 1
        assert result.statistics.min == result.statistics.max
        assert result.statistics.mean == result.statistics.median

    def test_observations_sorted_by_date(self) -> None:
        obs = [
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 7, 1), D("150"), D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        dates = [o.observation_date for o in result.observations]
        assert dates == sorted(dates)

    def test_lookback_excludes_all(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            lookback_start=date(2025, 1, 1),
        )
        assert result.statistics is None
        assert result.observations == []


# ---------------------------------------------------------------------------
# 17. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_inputs_same_output(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 4, 1), D("150"), D("10")),
            _pe_obs(date(2024, 7, 1), D("120"), D("10")),
        ]
        r1 = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert r1 == r2

    def test_different_calculated_at_different_output(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        r1 = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = historical_valuation_bands(
            obs, ValuationMethodType.PE,
            calculated_at=datetime(2025, 7, 1, 12, 0, 0),
        )
        assert r1.calculated_at != r2.calculated_at
        assert r1.statistics == r2.statistics

    def test_calculated_at_is_passthrough(self) -> None:
        ts = datetime(2099, 12, 31, 23, 59, 59)
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=ts)
        assert result.calculated_at == ts


# ---------------------------------------------------------------------------
# 18. Median helper
# ---------------------------------------------------------------------------


class TestMedianHelper:
    def test_odd(self) -> None:
        assert _median([D("1"), D("2"), D("3")]) == D("2")

    def test_even(self) -> None:
        assert _median([D("1"), D("2"), D("3"), D("4")]) == D("2.500000")

    def test_single(self) -> None:
        assert _median([D("42")]) == D("42")

    def test_two(self) -> None:
        assert _median([D("10"), D("20")]) == D("15.000000")


# ---------------------------------------------------------------------------
# 19. Std dev helper
# ---------------------------------------------------------------------------


class TestStdDevHelper:
    def test_single_returns_none(self) -> None:
        assert _std_dev([D("10")], D("10")) is None

    def test_two_values(self) -> None:
        result = _std_dev([D("10"), D("20")], D("15"))
        assert result is not None
        assert result > D("0")

    def test_all_same_returns_zero(self) -> None:
        result = _std_dev([D("5"), D("5"), D("5")], D("5"))
        assert result is not None
        assert result == D("0")


# ---------------------------------------------------------------------------
# 20. Model immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_result_frozen(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        with pytest.raises(Exception):  # noqa: B017, PT011
            result.engine_version = "2.0.0"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 21. Golden dataset — cross-verified P/E
# ---------------------------------------------------------------------------


class TestGoldenDataset:
    """Hand-verified P/E calculations for a 5-observation dataset.

    Values: [10, 12, 15, 18, 20] (sorted)
    Mean: 75 / 5 = 15.0
    Median: 15 (3rd value, odd count)
    P25: index = ceil(25/100 * 5) - 1 = ceil(1.25) - 1 = 2 - 1 = 1 → 12
    P75: index = ceil(75/100 * 5) - 1 = ceil(3.75) - 1 = 4 - 1 = 3 → 18
    P10: index = ceil(10/100 * 5) - 1 = ceil(0.5) - 1 = 1 - 1 = 0 → 10
    P90: index = ceil(90/100 * 5) - 1 = ceil(4.5) - 1 = 5 - 1 = 4 → 20
    """

    @pytest.fixture()
    def golden_obs(self) -> list[HistoricalObservationInput]:
        return [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),   # PE = 10
            _pe_obs(date(2024, 4, 1), D("120"), D("10")),   # PE = 12
            _pe_obs(date(2024, 7, 1), D("150"), D("10")),   # PE = 15
            _pe_obs(date(2024, 10, 1), D("180"), D("10")),  # PE = 18
            _pe_obs(date(2025, 1, 1), D("200"), D("10")),   # PE = 20
        ]

    def test_golden_min(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.min == D("10")

    def test_golden_max(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.max == D("20")

    def test_golden_mean(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.mean == D("15")

    def test_golden_median(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.median == D("15")

    def test_golden_p10(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        p10 = next(b for b in result.statistics.bands if b.percentile == D("10"))
        assert p10.value == D("10")

    def test_golden_p25(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        p25 = next(b for b in result.statistics.bands if b.percentile == D("25"))
        assert p25.value == D("12")

    def test_golden_p50(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        p50 = next(b for b in result.statistics.bands if b.percentile == D("50"))
        assert p50.value == D("15")

    def test_golden_p75(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        p75 = next(b for b in result.statistics.bands if b.percentile == D("75"))
        assert p75.value == D("18")

    def test_golden_p90(self, golden_obs: list[HistoricalObservationInput]) -> None:
        result = historical_valuation_bands(golden_obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        p90 = next(b for b in result.statistics.bands if b.percentile == D("90"))
        assert p90.value == D("20")

    def test_golden_current_position(self, golden_obs: list[HistoricalObservationInput]) -> None:
        current = _pe_obs(date(2025, 6, 1), D("160"), D("10"))  # PE = 16
        result = historical_valuation_bands(
            golden_obs, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is not None
        assert result.current_position.current_value == D("16")

        # Midpoint rank: below=3 (10,12,15), equal=0, total=5
        # rank = (3 + 0.5*0) / 5 * 100 = 60
        assert result.current_position.percentile_rank == D("60")

        # vs_median = 16 - 15 = 1
        assert result.current_position.vs_median == D("1")

        # distance_from_median_pct = (16-15)/15 * 100 = 6.666...%
        expected_dist = ((D("16") - D("15")) / D("15") * D("100")).quantize(D("0.000001"))
        assert result.current_position.distance_from_median_pct == expected_dist

    def test_golden_ev_ebitda(self) -> None:
        """Hand-verified EV/EBITDA with 3 observations.

        Obs1: price=100, shares=1M → MCap=100M; debt=30M, cash=10M → ND=20M, EV=120M; EBITDA=40M → EV/EBITDA=3
        Obs2: price=200, shares=1M → MCap=200M; debt=30M, cash=10M → ND=20M, EV=220M; EBITDA=40M → EV/EBITDA=5.5
        Obs3: price=150, shares=1M → MCap=150M; debt=30M, cash=10M → ND=20M, EV=170M; EBITDA=40M → EV/EBITDA=4.25
        """
        obs = [
            _obs(date(2024, 1, 1), D("100"), avail_date=date(2024, 1, 1),
                 ebitda=D("40000000"), total_debt=D("30000000"), cash=D("10000000")),
            _obs(date(2024, 4, 1), D("200"), avail_date=date(2024, 1, 1),
                 ebitda=D("40000000"), total_debt=D("30000000"), cash=D("10000000")),
            _obs(date(2024, 7, 1), D("150"), avail_date=date(2024, 1, 1),
                 ebitda=D("40000000"), total_debt=D("30000000"), cash=D("10000000")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 3

        sorted_vals = sorted([D("3"), D("5.5"), D("4.25")])
        assert result.statistics.min == sorted_vals[0]
        assert result.statistics.max == sorted_vals[-1]

    def test_golden_fcf_yield(self) -> None:
        """Hand-verified FCF Yield.

        price=100, shares=1M → MCap=100M
        CFO=20M, CapEx=5M → equity FCF=15M
        FCF Yield = 15M / 100M = 0.15
        """
        obs = [_obs(
            date(2024, 3, 1), D("100"), avail_date=date(2024, 1, 1),
            cfo=D("20000000"), capex=D("5000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.min == D("0.150000")

    def test_golden_ev_fcf_fcff(self) -> None:
        """Hand-verified EV/FCF with FCFF.

        price=100, shares=1M → MCap=100M
        debt=40M, cash=10M → ND=30M, EV=130M
        EBIT=50M, tax=25% → NOPAT=37.5M
        D&A=10M, CapEx=15M, ΔNWC=2.5M
        FCFF = 37.5 + 10 - 15 - 2.5 = 30M
        EV/FCFF = 130M / 30M ≈ 4.333333
        """
        obs = [_obs(
            date(2024, 3, 1), D("100"), avail_date=date(2024, 1, 1),
            ebit=D("50000000"), tax_rate=D("0.25"),
            da=D("10000000"), capex=D("15000000"), delta_nwc=D("2500000"),
            total_debt=D("40000000"), cash=D("10000000"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        assert result.statistics is not None
        v = result.observations[0]
        assert v.status == ObservationStatus.VALID
        assert v.value is not None
        assert v.cash_flow_basis == CashFlowBasis.FCFF

        nopat = D("50000000") * D("0.75")
        fcff = nopat + D("10000000") - D("15000000") - D("2500000")
        ev = D("100") * D("1000000") + D("40000000") - D("10000000")
        expected = (ev / fcff).quantize(D("0.000001"))
        assert v.value == expected


# ---------------------------------------------------------------------------
# 22. TTM period type
# ---------------------------------------------------------------------------


class TestTTMPeriodType:
    def test_ttm_accepted(self) -> None:
        obs = [_obs(
            date(2024, 3, 1), D("100"),
            fin_period="TTM-2024Q1",
            fin_type=FinancialPeriodType.TTM,
            avail_date=date(2024, 2, 1),
            eps=D("10"),
        )]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.observations[0].status == ObservationStatus.VALID
        assert result.observations[0].financial_period_type == FinancialPeriodType.TTM


# ---------------------------------------------------------------------------
# 23. Mixed statuses
# ---------------------------------------------------------------------------


class TestMixedStatuses:
    def test_mixed_valid_excluded_unverified(self) -> None:
        obs = [
            _pe_obs(date(2024, 1, 1), D("100"), D("10")),
            _pe_obs(date(2024, 2, 1), D("200"), D("-5")),
            _obs(date(2024, 3, 1), D("150"), eps=D("10")),
            _pe_obs(date(2024, 4, 1), D("120"), D("10")),
        ]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        statuses = {o.status for o in result.observations}
        assert ObservationStatus.VALID in statuses
        assert ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR in statuses
        assert ObservationStatus.UNVERIFIED_TIMING in statuses

        assert result.statistics is not None
        assert result.statistics.valid_count == 2
        assert result.statistics.unverified_count == 1
        assert result.statistics.excluded_count == 1


# ---------------------------------------------------------------------------
# 24. Engine version
# ---------------------------------------------------------------------------


class TestEngineVersion:
    def test_version_in_result(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.engine_version == "1.0.0"

    def test_version_in_calculations(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        valid = [o for o in result.observations if o.status == ObservationStatus.VALID]
        assert valid[0].calculation is not None
        assert valid[0].calculation.version == "1.0.0"


# ---------------------------------------------------------------------------
# 25. Method field propagation
# ---------------------------------------------------------------------------


class TestMethodFieldPropagation:
    def test_method_in_statistics(self) -> None:
        obs = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        result = historical_valuation_bands(obs, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.method == ValuationMethodType.PE

    def test_method_in_current_position(self) -> None:
        historical = [_pe_obs(date(2024, 1, 1), D("100"), D("10"))]
        current = _pe_obs(date(2025, 1, 1), D("120"), D("10"))
        result = historical_valuation_bands(
            historical, ValuationMethodType.PE,
            calculated_at=CALC_AT,
            current_observation=current,
        )
        assert result.current_position is not None
        assert result.current_position.method == ValuationMethodType.PE
