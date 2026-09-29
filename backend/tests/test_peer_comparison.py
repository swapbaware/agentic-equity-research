"""Comprehensive tests for the Peer Comparison Engine.

Covers: all six methods, target timing, rank_if_inserted semantics,
duplicate handling, target-as-peer exclusion, mixed currencies,
data sufficiency, invalid data, statistics, determinism, provenance,
golden datasets, and cross-engine formula consistency.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
import pytest

from app.valuation.historical_bands import (
    historical_valuation_bands,
)
from app.valuation.models import (
    CashFlowBasis,
    DataSufficiency,
    DataSufficiencyThresholds,
    FinancialPeriodType,
    HistoricalObservationInput,
    ObservationStatus,
    PeerComparisonResult,
    PeerObservationInput,
    PeerSelectionMethod,
    PeerSetMetadata,
    ValuationMethodType,
)
from app.valuation.peer_comparison import (
    ENGINE_VERSION,
    PeerComparisonError,
    compare_peers,
)

D = Decimal
CALC_AT = datetime(2025, 6, 15, 10, 0, 0)

_DEFAULT_PRICE = D("100")
_DEFAULT_SHARES = D("1000000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hist_obs(
    obs_date: date = date(2024, 6, 1),
    price: Decimal = _DEFAULT_PRICE,
    shares: Decimal = _DEFAULT_SHARES,
    *,
    fin_period: str = "FY2024",
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
        financial_period=fin_period,
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


def _peer(
    company_id: str,
    *,
    price: Decimal = _DEFAULT_PRICE,
    shares: Decimal = _DEFAULT_SHARES,
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
    currency: str = "INR",
    avail_date: date | None = date(2024, 3, 15),
    company_name: str | None = None,
) -> PeerObservationInput:
    return PeerObservationInput(
        company_id=company_id,
        company_name=company_name,
        currency=currency,
        observation=_hist_obs(
            price=price,
            shares=shares,
            eps=eps,
            revenue=revenue,
            ebitda=ebitda,
            total_equity=total_equity,
            total_debt=total_debt,
            cash=cash,
            cfo=cfo,
            capex=capex,
            ebit=ebit,
            tax_rate=tax_rate,
            da=da,
            delta_nwc=delta_nwc,
            avail_date=avail_date,
        ),
    )


# ---------------------------------------------------------------------------
# A. Per-method invocation
# ---------------------------------------------------------------------------


class TestPEMethod:
    def test_basic_pe_comparison(self) -> None:
        target = _peer("TARGET", price=D("200"), eps=D("10"))
        peers = [
            _peer("A", price=D("150"), eps=D("10")),
            _peer("B", price=D("100"), eps=D("5")),
            _peer("C", price=D("120"), eps=D("8")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.method == ValuationMethodType.PE
        assert result.target.value == D("20.000000")
        assert result.statistics is not None
        assert result.statistics.valid_count == 3
        assert result.position is not None

    def test_pe_negative_eps_excluded(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("-5")),
            _peer("B", price=D("100"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 1
        excluded = [p for p in result.peers if p.status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR]
        assert len(excluded) == 1

    def test_pe_zero_eps_excluded(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("100"), eps=D("0"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is None


class TestEVEBITDAMethod:
    def test_basic(self) -> None:
        target = _peer("T", price=D("100"), total_debt=D("200"), cash=D("50"), ebitda=D("80"))
        peers = [
            _peer("A", price=D("80"), total_debt=D("100"), cash=D("20"), ebitda=D("60")),
            _peer("B", price=D("120"), total_debt=D("300"), cash=D("100"), ebitda=D("90")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.target.value is not None
        assert result.target.enterprise_value is not None
        assert result.target.net_debt is not None
        assert result.statistics is not None
        assert result.statistics.valid_count == 2


class TestPSMethod:
    def test_basic(self) -> None:
        target = _peer("T", price=D("100"), revenue=D("500000"))
        peers = [
            _peer("A", price=D("80"), revenue=D("400000")),
            _peer("B", price=D("120"), revenue=D("600000")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PS, calculated_at=CALC_AT)
        assert result.target.value is not None
        assert result.statistics is not None


class TestPBMethod:
    def test_basic(self) -> None:
        target = _peer("T", price=D("100"), total_equity=D("800000"))
        peers = [
            _peer("A", price=D("80"), total_equity=D("600000")),
            _peer("B", price=D("120"), total_equity=D("1000000")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PB, calculated_at=CALC_AT)
        assert result.target.value is not None
        assert result.statistics is not None


class TestFCFYieldMethod:
    def test_basic(self) -> None:
        target = _peer("T", price=D("100"), cfo=D("80000"), capex=D("20000"))
        peers = [
            _peer("A", price=D("80"), cfo=D("60000"), capex=D("15000")),
            _peer("B", price=D("120"), cfo=D("100000"), capex=D("30000")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        assert result.target.value is not None
        assert result.target.cash_flow_basis == CashFlowBasis.EQUITY_FCF
        assert result.statistics is not None


class TestEVFCFMethod:
    def test_basic(self) -> None:
        target = _peer(
            "T", price=D("100"), total_debt=D("200"), cash=D("50"),
            ebit=D("100"), tax_rate=D("0.25"), da=D("20"), capex=D("30"), delta_nwc=D("10"),
        )
        peers = [
            _peer(
                "A", price=D("80"), total_debt=D("100"), cash=D("20"),
                ebit=D("80"), tax_rate=D("0.25"), da=D("15"), capex=D("25"), delta_nwc=D("5"),
            ),
        ]
        result = compare_peers(target, peers, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        assert result.target.value is not None
        assert result.target.cash_flow_basis == CashFlowBasis.FCFF
        assert result.statistics is not None

    def test_fcff_chain_in_calculation(self) -> None:
        target = _peer(
            "T", price=D("100"), total_debt=D("200"), cash=D("50"),
            ebit=D("100"), tax_rate=D("0.25"), da=D("20"), capex=D("30"), delta_nwc=D("10"),
        )
        peers = [
            _peer(
                "A", price=D("80"), total_debt=D("100"), cash=D("20"),
                ebit=D("80"), tax_rate=D("0.25"), da=D("15"), capex=D("25"), delta_nwc=D("5"),
            ),
        ]
        result = compare_peers(target, peers, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        calc = result.target.calculation
        assert calc is not None
        inputs = calc.inputs
        assert "ebit" in inputs
        assert "effective_tax_rate" in inputs
        assert "nopat" in inputs
        assert "depreciation_amortization" in inputs
        assert "capex" in inputs
        assert "delta_nwc" in inputs
        assert "fcff" in inputs
        assert "enterprise_value" in inputs


class TestPEGRejected:
    def test_peg_raises(self) -> None:
        target = _peer("T", eps=D("10"))
        with pytest.raises(PeerComparisonError, match="PEG"):
            compare_peers(target, [], ValuationMethodType.PEG, calculated_at=CALC_AT)


# ---------------------------------------------------------------------------
# B. Target timing
# ---------------------------------------------------------------------------


class TestTargetTiming:
    def test_valid_target_has_position(self) -> None:
        target = _peer("T", price=D("160"), eps=D("10"), avail_date=date(2024, 3, 15))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.status == ObservationStatus.VALID
        assert result.position is not None

    def test_look_ahead_target_no_position(self) -> None:
        target = _peer("T", price=D("160"), eps=D("10"), avail_date=date(2025, 6, 1))
        target = PeerObservationInput(
            company_id="T",
            currency="INR",
            observation=HistoricalObservationInput(
                observation_date=date(2024, 6, 1),
                price=D("160"),
                shares_outstanding=D("1000000"),
                financial_period="FY2024",
                financial_period_type=FinancialPeriodType.ANNUAL,
                financials_available_date=date(2025, 6, 1),
                eps=D("10"),
            ),
        )
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.status == ObservationStatus.LOOK_AHEAD_RISK
        assert result.target.value is not None
        assert result.position is None

    def test_unverified_target_no_position(self) -> None:
        target = _peer("T", price=D("160"), eps=D("10"), avail_date=None)
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.status == ObservationStatus.UNVERIFIED_TIMING
        assert result.target.value is not None
        assert result.position is None

    def test_peer_look_ahead_excluded_from_stats(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("100"), eps=D("10"), avail_date=date(2025, 6, 1)),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 1

    def test_peer_unverified_excluded_from_stats(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("100"), eps=D("10"), avail_date=None),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 1


# ---------------------------------------------------------------------------
# C. Rank semantics
# ---------------------------------------------------------------------------


class TestRankIfInserted:
    def _peers_10_15_20(self) -> list[PeerObservationInput]:
        return [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]

    def test_below_all(self) -> None:
        target = _peer("T", price=D("50"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 1

    def test_equal_to_lowest(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 2

    def test_between_low_mid(self) -> None:
        target = _peer("T", price=D("120"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 2

    def test_equal_to_middle(self) -> None:
        target = _peer("T", price=D("150"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 3

    def test_between_mid_high(self) -> None:
        target = _peer("T", price=D("170"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 3

    def test_equal_to_highest(self) -> None:
        target = _peer("T", price=D("200"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 4

    def test_above_all(self) -> None:
        target = _peer("T", price=D("250"), eps=D("10"))
        result = compare_peers(target, self._peers_10_15_20(), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.rank_if_inserted == 4


# ---------------------------------------------------------------------------
# D. Percentile rank
# ---------------------------------------------------------------------------


class TestPercentileRankInResult:
    def test_below_all(self) -> None:
        target = _peer("T", price=D("50"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.percentile_rank == D("0.000000")

    def test_above_all(self) -> None:
        target = _peer("T", price=D("250"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.percentile_rank == D("100.000000")


# ---------------------------------------------------------------------------
# E. Mixed currencies
# ---------------------------------------------------------------------------


class TestMixedCurrencies:
    def test_mixed_currencies_allowed(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"), currency="INR")
        peers = [
            _peer("A", price=D("50"), eps=D("5"), currency="USD"),
            _peer("B", price=D("80"), eps=D("4"), currency="EUR"),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.currency == "INR"
        assert result.statistics is not None
        assert result.statistics.valid_count == 2
        currencies = {p.currency for p in result.peers if p.status == ObservationStatus.VALID}
        assert currencies == {"USD", "EUR"}

    def test_currencies_preserved_in_output(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"), currency="INR")
        peers = [_peer("A", price=D("50"), eps=D("5"), currency="USD")]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.peers[0].currency == "USD"

    def test_no_fx_conversion(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"), currency="INR")
        peers = [_peer("A", price=D("50"), eps=D("5"), currency="USD")]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.value == D("10.000000")
        assert result.peers[0].value == D("10.000000")


# ---------------------------------------------------------------------------
# F. Duplicate peers
# ---------------------------------------------------------------------------


class TestDuplicatePeers:
    def test_identical_dedup(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        p = _peer("A", price=D("50"), eps=D("5"))
        result = compare_peers(target, [p, p], ValuationMethodType.PE, calculated_at=CALC_AT)
        valid = [pp for pp in result.peers if pp.status == ObservationStatus.VALID]
        dups = [pp for pp in result.peers if pp.status == ObservationStatus.DUPLICATE_OBSERVATION]
        assert len(valid) == 1
        assert len(dups) == 1
        assert result.statistics is not None
        assert result.statistics.valid_count == 1

    def test_contradictory_raises(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        p1 = _peer("A", price=D("50"), eps=D("5"))
        p2 = _peer("A", price=D("60"), eps=D("5"))
        with pytest.raises(PeerComparisonError, match="Contradictory"):
            compare_peers(target, [p1, p2], ValuationMethodType.PE, calculated_at=CALC_AT)

    def test_multiple_duplicates(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        p = _peer("A", price=D("50"), eps=D("5"))
        result = compare_peers(target, [p, p, p], ValuationMethodType.PE, calculated_at=CALC_AT)
        dups = [pp for pp in result.peers if pp.status == ObservationStatus.DUPLICATE_OBSERVATION]
        assert len(dups) == 2


# ---------------------------------------------------------------------------
# G. Target-as-peer
# ---------------------------------------------------------------------------


class TestTargetAsPeer:
    def test_target_excluded_from_peers(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("T", price=D("100"), eps=D("10")),
            _peer("A", price=D("50"), eps=D("5")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.valid_count == 1
        target_in_peers = [p for p in result.peers if p.company_id == "T"]
        assert len(target_in_peers) == 1
        assert target_in_peers[0].status == ObservationStatus.DUPLICATE_OBSERVATION

    def test_target_as_peer_does_not_affect_statistics(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers_without = [_peer("A", price=D("50"), eps=D("5"))]
        peers_with = [_peer("T", price=D("100"), eps=D("10")), _peer("A", price=D("50"), eps=D("5"))]

        r1 = compare_peers(target, peers_without, ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = compare_peers(target, peers_with, ValuationMethodType.PE, calculated_at=CALC_AT)

        assert r1.statistics is not None
        assert r2.statistics is not None
        assert r1.statistics.median == r2.statistics.median
        assert r1.statistics.mean == r2.statistics.mean


# ---------------------------------------------------------------------------
# H. Input ordering
# ---------------------------------------------------------------------------


class TestInputOrdering:
    def test_different_order_same_statistics(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        a = _peer("A", price=D("50"), eps=D("5"))
        b = _peer("B", price=D("150"), eps=D("10"))
        c = _peer("C", price=D("200"), eps=D("8"))

        r1 = compare_peers(target, [a, b, c], ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = compare_peers(target, [c, a, b], ValuationMethodType.PE, calculated_at=CALC_AT)
        r3 = compare_peers(target, [b, c, a], ValuationMethodType.PE, calculated_at=CALC_AT)

        assert r1.statistics is not None
        assert r1.statistics.median == r2.statistics.median == r3.statistics.median
        assert r1.statistics.mean == r2.statistics.mean == r3.statistics.mean
        assert r1.statistics.min == r2.statistics.min == r3.statistics.min
        assert r1.statistics.max == r2.statistics.max == r3.statistics.max

    def test_different_order_same_rank(self) -> None:
        target = _peer("T", price=D("120"), eps=D("10"))
        a = _peer("A", price=D("100"), eps=D("10"))
        b = _peer("B", price=D("150"), eps=D("10"))
        c = _peer("C", price=D("200"), eps=D("10"))

        r1 = compare_peers(target, [a, b, c], ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = compare_peers(target, [c, a, b], ValuationMethodType.PE, calculated_at=CALC_AT)

        assert r1.position is not None
        assert r2.position is not None
        assert r1.position.rank_if_inserted == r2.position.rank_if_inserted


# ---------------------------------------------------------------------------
# I. Data sufficiency
# ---------------------------------------------------------------------------


class TestDataSufficiency:
    def _make_peers(self, n: int) -> list[PeerObservationInput]:
        return [
            _peer(f"P{i}", price=D(str(50 + i * 10)), eps=D("10"))
            for i in range(n)
        ]

    def test_zero_insufficient(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, [], ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is None

    def test_1_minimal(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(1), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.MINIMAL

    def test_2_minimal(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(2), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.MINIMAL

    def test_3_low(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(3), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.LOW

    def test_4_low(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(4), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.LOW

    def test_5_moderate(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(5), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.MODERATE

    def test_9_moderate(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(9), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.MODERATE

    def test_10_adequate(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, self._make_peers(10), ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.ADEQUATE

    def test_custom_thresholds(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        custom = DataSufficiencyThresholds(min_minimal=2, min_low=4, min_moderate=8)
        result = compare_peers(
            target, self._make_peers(3), ValuationMethodType.PE,
            calculated_at=CALC_AT, sufficiency_thresholds=custom,
        )
        assert result.statistics is not None
        assert result.statistics.data_sufficiency == DataSufficiency.LOW


# ---------------------------------------------------------------------------
# J. Invalid data
# ---------------------------------------------------------------------------


class TestInvalidData:
    def test_missing_eps(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_negative_revenue(self) -> None:
        target = _peer("T", price=D("100"), revenue=D("500000"))
        peers = [_peer("A", price=D("50"), revenue=D("-100"))]
        result = compare_peers(target, peers, ValuationMethodType.PS, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR

    def test_zero_book_value(self) -> None:
        target = _peer("T", price=D("100"), total_equity=D("500000"))
        peers = [_peer("A", price=D("50"), total_equity=D("0"))]
        result = compare_peers(target, peers, ValuationMethodType.PB, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_ZERO_DENOMINATOR

    def test_missing_debt_for_ev(self) -> None:
        target = _peer("T", price=D("100"), total_debt=D("200"), cash=D("50"), ebitda=D("80"))
        peers = [_peer("A", price=D("50"), ebitda=D("60"))]
        result = compare_peers(target, peers, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_negative_equity_fcf(self) -> None:
        target = _peer("T", price=D("100"), cfo=D("80000"), capex=D("20000"))
        peers = [_peer("A", price=D("50"), cfo=D("10000"), capex=D("50000"))]
        result = compare_peers(target, peers, ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT)
        excluded = [p for p in result.peers if p.status != ObservationStatus.VALID]
        assert len(excluded) == 1

    def test_missing_delta_nwc_for_ev_fcf(self) -> None:
        target = _peer(
            "T", price=D("100"), total_debt=D("200"), cash=D("50"),
            ebit=D("100"), tax_rate=D("0.25"), da=D("20"), capex=D("30"), delta_nwc=D("10"),
        )
        peers = [_peer(
            "A", price=D("80"), total_debt=D("100"), cash=D("20"),
            ebit=D("80"), tax_rate=D("0.25"), da=D("15"), capex=D("25"),
        )]
        result = compare_peers(target, peers, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_zero_price_excluded(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("0"), eps=D("10"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_MISSING_DATA

    def test_zero_shares_excluded(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), shares=D("0"), eps=D("10"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.peers[0].status == ObservationStatus.EXCLUDED_MISSING_DATA


# ---------------------------------------------------------------------------
# K. Net cash
# ---------------------------------------------------------------------------


class TestNetCash:
    def test_negative_net_debt(self) -> None:
        target = _peer("T", price=D("100"), total_debt=D("50"), cash=D("500"), ebitda=D("80"))
        peers = [_peer("A", price=D("80"), total_debt=D("30"), cash=D("300"), ebitda=D("60"))]
        result = compare_peers(target, peers, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)
        assert result.target.net_debt is not None
        assert result.target.net_debt < D("0")
        assert result.target.enterprise_value is not None
        assert result.target.market_cap is not None
        assert result.target.enterprise_value < result.target.market_cap


# ---------------------------------------------------------------------------
# L. Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_single_peer(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        s = result.statistics
        assert s.min == s.max == s.mean == s.median
        assert s.std_dev is None

    def test_std_dev_present(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("50"), eps=D("5")),
            _peer("B", price=D("150"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.std_dev is not None
        assert result.statistics.std_dev > D("0")

    def test_custom_percentiles(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer(f"P{i}", price=D(str(50 + i * 10)), eps=D("10"))
            for i in range(10)
        ]
        result = compare_peers(
            target, peers, ValuationMethodType.PE,
            calculated_at=CALC_AT, percentiles=[D("20"), D("80")],
        )
        assert result.statistics is not None
        pctls = {b.percentile for b in result.statistics.bands}
        assert pctls == {D("20"), D("80")}

    def test_invalid_percentile_raises(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        with pytest.raises(PeerComparisonError, match="percentile"):
            compare_peers(
                target, [], ValuationMethodType.PE,
                calculated_at=CALC_AT, percentiles=[D("110")],
            )

    def test_median_odd(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.median == D("15.000000")

    def test_median_even(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("120"), eps=D("10")),
            _peer("C", price=D("180"), eps=D("10")),
            _peer("D", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        assert result.statistics.median == D("15.000000")


# ---------------------------------------------------------------------------
# M. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_inputs_same_output(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        r1 = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert r1 == r2

    def test_different_calculated_at(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        r1 = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        r2 = compare_peers(
            target, peers, ValuationMethodType.PE,
            calculated_at=datetime(2025, 7, 1, 10, 0, 0),
        )
        assert r1.calculated_at != r2.calculated_at
        assert r1.target.value == r2.target.value


# ---------------------------------------------------------------------------
# N. Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_engine_version(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.engine_version == ENGINE_VERSION

    def test_calculated_at_passthrough(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, [], ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.calculated_at == CALC_AT

    def test_peer_set_metadata_preserved(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        meta = PeerSetMetadata(
            peer_set_id="ps-001",
            selection_method=PeerSelectionMethod.SECTOR_BASED,
            sector="IT",
            rationale="Same sector",
        )
        result = compare_peers(
            target, [], ValuationMethodType.PE,
            calculated_at=CALC_AT, peer_set_metadata=meta,
        )
        assert result.peer_set_metadata is not None
        assert result.peer_set_metadata.peer_set_id == "ps-001"
        assert result.peer_set_metadata.selection_method == PeerSelectionMethod.SECTOR_BASED

    def test_calculation_result_on_peer(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        valid_peers = [p for p in result.peers if p.status == ObservationStatus.VALID]
        assert len(valid_peers) == 1
        assert valid_peers[0].calculation is not None
        assert valid_peers[0].calculation.metric == "peer_pe"
        assert valid_peers[0].calculation.version == ENGINE_VERSION

    def test_company_identity_preserved(self) -> None:
        target = _peer("TARGET-CO", price=D("100"), eps=D("10"), company_name="Target Corp")
        peers = [_peer("PEER-A", price=D("50"), eps=D("5"), company_name="Peer A")]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.company_id == "TARGET-CO"
        assert result.target.company_name == "Target Corp"
        valid_peers = [p for p in result.peers if p.status == ObservationStatus.VALID]
        assert valid_peers[0].company_id == "PEER-A"
        assert valid_peers[0].company_name == "Peer A"

    def test_excluded_obs_status_recorded(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("-5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert len(result.peers) == 1
        assert result.peers[0].status == ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR


# ---------------------------------------------------------------------------
# O. Target positioning details
# ---------------------------------------------------------------------------


class TestTargetPositioning:
    def test_difference_from_median(self) -> None:
        target = _peer("T", price=D("200"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.difference_from_median == D("20.000000") - D("15.000000")

    def test_difference_from_median_pct(self) -> None:
        target = _peer("T", price=D("200"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),
            _peer("B", price=D("150"), eps=D("10")),
            _peer("C", price=D("200"), eps=D("10")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.difference_from_median_pct is not None
        expected = (D("20") - D("15")) / D("15") * D("100")
        assert result.position.difference_from_median_pct == expected.quantize(D("0.000001"))

    def test_zero_median_pct_none(self) -> None:
        target = _peer("T", price=D("100"), revenue=D("500000"))
        peers = [_peer("A", price=D("0.001"), revenue=D("500000"))]
        result = compare_peers(target, peers, ValuationMethodType.PS, calculated_at=CALC_AT)
        if result.statistics is not None and result.statistics.median == D("0"):
            assert result.position is not None
            assert result.position.difference_from_median_pct is None

    def test_vs_p25_and_p75(self) -> None:
        target = _peer("T", price=D("120"), eps=D("10"))
        peers = [
            _peer(f"P{i}", price=D(str(50 + i * 20)), eps=D("10"))
            for i in range(10)
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is not None
        assert result.position.vs_p25 is not None
        assert result.position.vs_p75 is not None

    def test_no_position_when_no_valid_peers(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("-5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.position is None

    def test_no_position_when_target_invalid(self) -> None:
        target = _peer("T", price=D("100"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.target.status == ObservationStatus.EXCLUDED_MISSING_DATA
        assert result.position is None


# ---------------------------------------------------------------------------
# P. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_peers(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        result = compare_peers(target, [], ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is None
        assert result.position is None
        assert result.peers == []

    def test_all_peers_invalid(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [
            _peer("A", price=D("50"), eps=D("-5")),
            _peer("B", price=D("50")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is None
        assert result.position is None

    def test_single_peer(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        assert result.statistics is not None
        s = result.statistics
        assert s.min == s.max == s.mean == s.median
        assert result.position is not None


# ---------------------------------------------------------------------------
# Q. Golden datasets
# ---------------------------------------------------------------------------


class TestGoldenPE:
    """5-peer P/E golden dataset with hand-calculated values."""

    @pytest.fixture()
    def golden_result(self) -> PeerComparisonResult:
        target = _peer("TARGET", price=D("160"), eps=D("10"))
        peers = [
            _peer("A", price=D("100"), eps=D("10")),   # P/E = 10
            _peer("B", price=D("120"), eps=D("10")),   # P/E = 12
            _peer("C", price=D("150"), eps=D("10")),   # P/E = 15
            _peer("D", price=D("180"), eps=D("10")),   # P/E = 18
            _peer("E", price=D("200"), eps=D("10")),   # P/E = 20
        ]
        return compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)

    def test_target_pe(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.target.value == D("16.000000")

    def test_min(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.statistics is not None
        assert golden_result.statistics.min == D("10.000000")

    def test_max(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.statistics is not None
        assert golden_result.statistics.max == D("20.000000")

    def test_mean(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.statistics is not None
        expected = (D("10") + D("12") + D("15") + D("18") + D("20")) / D("5")
        assert golden_result.statistics.mean == expected.quantize(D("0.000001"))

    def test_median(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.statistics is not None
        assert golden_result.statistics.median == D("15.000000")

    def test_rank_if_inserted(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.position is not None
        assert golden_result.position.rank_if_inserted == 4

    def test_difference_from_median(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.position is not None
        assert golden_result.position.difference_from_median == D("1.000000")

    def test_valid_count(self, golden_result: PeerComparisonResult) -> None:
        assert golden_result.statistics is not None
        assert golden_result.statistics.valid_count == 5


class TestGoldenEVEBITDA:
    """3-peer EV/EBITDA with hand-verified EV derivation."""

    def test_golden(self) -> None:
        target = _peer("T", price=D("100"), total_debt=D("500000"), cash=D("100000"), ebitda=D("200000"))
        peers = [
            _peer("A", price=D("80"), total_debt=D("400000"), cash=D("50000"), ebitda=D("150000")),
            _peer("B", price=D("120"), total_debt=D("600000"), cash=D("200000"), ebitda=D("250000")),
            _peer("C", price=D("90"), total_debt=D("300000"), cash=D("80000"), ebitda=D("180000")),
        ]
        result = compare_peers(target, peers, ValuationMethodType.EV_EBITDA, calculated_at=CALC_AT)

        assert result.target.net_debt is not None
        assert result.target.net_debt == D("400000.0000")
        assert result.target.enterprise_value is not None
        mcap = D("100") * D("1000000")
        assert result.target.enterprise_value == (mcap + D("400000")).quantize(D("0.0001"))

        assert result.statistics is not None
        assert result.statistics.valid_count == 3


class TestGoldenEVFCF:
    """EV/FCF with hand-verified FCFF chain."""

    def test_fcff_chain(self) -> None:
        target = _peer(
            "T", price=D("100"), total_debt=D("200000"), cash=D("50000"),
            ebit=D("100000"), tax_rate=D("0.25"), da=D("20000"),
            capex=D("30000"), delta_nwc=D("10000"),
        )
        peers = [
            _peer(
                "A", price=D("80"), total_debt=D("100000"), cash=D("20000"),
                ebit=D("80000"), tax_rate=D("0.30"), da=D("15000"),
                capex=D("25000"), delta_nwc=D("5000"),
            ),
        ]
        result = compare_peers(target, peers, ValuationMethodType.EV_FCF, calculated_at=CALC_AT)

        nopat_target = D("100000") * (D("1") - D("0.25"))
        fcff_target = (nopat_target + D("20000") - D("30000") - D("10000")).quantize(D("0.0001"))
        mcap_target = D("100") * D("1000000")
        nd_target = (D("200000") - D("50000")).quantize(D("0.0001"))
        ev_target = (mcap_target + nd_target).quantize(D("0.0001"))
        expected_ratio = (ev_target / fcff_target).quantize(D("0.000001"))

        assert result.target.value == expected_ratio
        assert result.target.cash_flow_basis == CashFlowBasis.FCFF
        assert result.statistics is not None


# ---------------------------------------------------------------------------
# R. Cross-engine consistency
# ---------------------------------------------------------------------------


class TestCrossEngineConsistency:
    def test_pe_matches_historical_bands(self) -> None:
        obs = _hist_obs(price=D("100"), eps=D("10"))
        hist_result = historical_valuation_bands(
            [obs], ValuationMethodType.PE,
            calculated_at=CALC_AT,
        )
        peer_input = PeerObservationInput(
            company_id="X",
            currency="INR",
            observation=obs,
        )
        peer_result = compare_peers(
            peer_input, [_peer("A", price=D("50"), eps=D("5"))],
            ValuationMethodType.PE, calculated_at=CALC_AT,
        )
        hist_val = hist_result.observations[0].value
        peer_val = peer_result.target.value
        assert hist_val is not None
        assert peer_val is not None
        assert hist_val == peer_val

    def test_ev_fcf_matches_historical_bands(self) -> None:
        obs = _hist_obs(
            price=D("100"), total_debt=D("200000"), cash=D("50000"),
            ebit=D("100000"), tax_rate=D("0.25"), da=D("20000"),
            capex=D("30000"), delta_nwc=D("10000"),
        )
        hist_result = historical_valuation_bands(
            [obs], ValuationMethodType.EV_FCF,
            calculated_at=CALC_AT,
        )
        peer_input = PeerObservationInput(
            company_id="X",
            currency="INR",
            observation=obs,
        )
        peer_result = compare_peers(
            peer_input,
            [_peer("A", price=D("80"), total_debt=D("100000"), cash=D("20000"),
                   ebit=D("80000"), tax_rate=D("0.30"), da=D("15000"),
                   capex=D("25000"), delta_nwc=D("5000"))],
            ValuationMethodType.EV_FCF, calculated_at=CALC_AT,
        )
        hist_val = hist_result.observations[0].value
        peer_val = peer_result.target.value
        assert hist_val is not None
        assert peer_val is not None
        assert hist_val == peer_val

    def test_fcf_yield_matches_historical_bands(self) -> None:
        obs = _hist_obs(price=D("100"), cfo=D("80000"), capex=D("20000"))
        hist_result = historical_valuation_bands(
            [obs], ValuationMethodType.FCF_YIELD,
            calculated_at=CALC_AT,
        )
        peer_input = PeerObservationInput(
            company_id="X",
            currency="INR",
            observation=obs,
        )
        peer_result = compare_peers(
            peer_input,
            [_peer("A", price=D("80"), cfo=D("60000"), capex=D("15000"))],
            ValuationMethodType.FCF_YIELD, calculated_at=CALC_AT,
        )
        hist_val = hist_result.observations[0].value
        peer_val = peer_result.target.value
        assert hist_val is not None
        assert peer_val is not None
        assert hist_val == peer_val


# ---------------------------------------------------------------------------
# S. Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_result_frozen(self) -> None:
        target = _peer("T", price=D("100"), eps=D("10"))
        peers = [_peer("A", price=D("50"), eps=D("5"))]
        result = compare_peers(target, peers, ValuationMethodType.PE, calculated_at=CALC_AT)
        with pytest.raises(pydantic.ValidationError):
            result.method = ValuationMethodType.PS  # type: ignore[misc]
