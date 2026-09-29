"""Historical Valuation Bands Engine — deterministic, frequency-agnostic.

All calculations use decimal.Decimal, never float. The engine operates on
whatever observation set the caller supplies. It never calls date.today() or
datetime.now(); calculated_at is caller-supplied.

The caller is responsible for providing prices and per-share financial data
on a consistent split-adjusted basis. The engine does not perform
corporate-action adjustments.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal

from app.analytics._calc import safe_divide
from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation.models import (
    CashFlowBasis,
    CurrentValuationPosition,
    DataSufficiency,
    DataSufficiencyThresholds,
    HistoricalObservationInput,
    HistoricalValuationObservation,
    HistoricalValuationResult,
    ObservationStatus,
    PercentileBand,
    ValuationBandStatistics,
    ValuationMethodType,
)

ENGINE_VERSION = "1.0.0"
_CURRENCY_QUANTIZE = Decimal("0.0001")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_HUNDRED = Decimal("100")
_HALF = Decimal("0.5")

_DEFAULT_PERCENTILES = [
    Decimal("10"),
    Decimal("25"),
    Decimal("50"),
    Decimal("75"),
    Decimal("90"),
]
_DEFAULT_THRESHOLDS = DataSufficiencyThresholds()


class HistoricalBandError(Exception):
    """Raised when historical band inputs have irreconcilable conflicts."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_percentiles(percentiles: list[Decimal]) -> None:
    for p in percentiles:
        if p < _ZERO or p > _HUNDRED:
            msg = f"percentile must be in [0, 100], got {p}"
            raise HistoricalBandError(msg)


def _filter_lookback(
    observations: list[HistoricalObservationInput],
    start: date | None,
    end: date | None,
) -> list[HistoricalObservationInput]:
    result = observations
    if start is not None:
        result = [o for o in result if o.observation_date >= start]
    if end is not None:
        result = [o for o in result if o.observation_date <= end]
    return result


def _timing_status(obs: HistoricalObservationInput) -> ObservationStatus:
    if obs.financials_available_date is None:
        return ObservationStatus.UNVERIFIED_TIMING
    if obs.financials_available_date > obs.observation_date:
        return ObservationStatus.LOOK_AHEAD_RISK
    return ObservationStatus.VALID


def _excluded_obs(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    status: ObservationStatus,
    market_cap: Decimal | None = None,
    enterprise_value: Decimal | None = None,
    net_debt: Decimal | None = None,
    cash_flow_basis: CashFlowBasis | None = None,
) -> HistoricalValuationObservation:
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=status,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        net_debt=net_debt,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        cash_flow_basis=cash_flow_basis,
    )


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _detect_duplicates(
    observations: list[HistoricalObservationInput],
    method: ValuationMethodType,
) -> tuple[list[HistoricalObservationInput], list[HistoricalValuationObservation]]:
    by_date: dict[date, list[HistoricalObservationInput]] = {}
    for obs in observations:
        by_date.setdefault(obs.observation_date, []).append(obs)

    non_dup: list[HistoricalObservationInput] = []
    dup_obs: list[HistoricalValuationObservation] = []

    for d in sorted(by_date):
        group = by_date[d]
        if len(group) == 1:
            non_dup.append(group[0])
            continue

        first = group[0]
        if not all(obs == first for obs in group[1:]):
            msg = f"Contradictory observations for date {d}"
            raise HistoricalBandError(msg)

        non_dup.append(first)
        for _ in group[1:]:
            dup_obs.append(_excluded_obs(first, method, ObservationStatus.DUPLICATE_OBSERVATION))

    return non_dup, dup_obs


# ---------------------------------------------------------------------------
# Per-method computation
# ---------------------------------------------------------------------------


def _missing(status: ObservationStatus = ObservationStatus.EXCLUDED_MISSING_DATA) -> ObservationStatus:
    return status


def _denom_status(value: Decimal) -> ObservationStatus | None:
    if value < _ZERO:
        return ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR
    if value == _ZERO:
        return ObservationStatus.EXCLUDED_ZERO_DENOMINATOR
    return None


def _compute_observation(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
) -> HistoricalValuationObservation:
    market_cap = (obs.price * obs.shares_outstanding).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    if method == ValuationMethodType.PE:
        return _compute_pe(obs, method, timing, market_cap)
    if method == ValuationMethodType.EV_EBITDA:
        return _compute_ev_ebitda(obs, method, timing, market_cap)
    if method == ValuationMethodType.PS:
        return _compute_ps(obs, method, timing, market_cap)
    if method == ValuationMethodType.PB:
        return _compute_pb(obs, method, timing, market_cap)
    if method == ValuationMethodType.FCF_YIELD:
        return _compute_fcf_yield(obs, method, timing, market_cap)
    if method == ValuationMethodType.EV_FCF:
        return _compute_ev_fcf(obs, method, timing, market_cap)

    msg = f"Unsupported method: {method}"
    raise HistoricalBandError(msg)


def _compute_pe(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    if obs.eps is None:
        return _excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = _denom_status(obs.eps)
    if bad is not None:
        return _excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(obs.price, obs.eps)
    assert value is not None  # noqa: S101 — eps > 0 guaranteed above

    calc = CalculationResult(
        metric="historical_pe",
        value=value,
        inputs={"price": obs.price, "eps": obs.eps},
        period=obs.financial_period,
        formula="Price / EPS",
        version=ENGINE_VERSION,
        unit="multiple",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        calculation=calc,
    )


def _ev_components(
    obs: HistoricalObservationInput,
    market_cap: Decimal,
) -> tuple[Decimal, Decimal] | None:
    if obs.total_debt is None or obs.cash_and_equivalents is None:
        return None
    net_debt = (obs.total_debt - obs.cash_and_equivalents).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    ev = (market_cap + net_debt).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
    return net_debt, ev


def _compute_ev_ebitda(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    ev_parts = _ev_components(obs, market_cap)
    if ev_parts is None:
        return _excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    net_debt, ev = ev_parts

    if obs.ebitda is None:
        return _excluded_obs(
            obs, method, ObservationStatus.EXCLUDED_MISSING_DATA,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
        )

    bad = _denom_status(obs.ebitda)
    if bad is not None:
        return _excluded_obs(
            obs, method, bad,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
        )

    value, _ = safe_divide(ev, obs.ebitda)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric="historical_ev_ebitda",
        value=value,
        inputs={
            "price": obs.price,
            "shares_outstanding": obs.shares_outstanding,
            "market_cap": market_cap,
            "total_debt": obs.total_debt,
            "cash_and_equivalents": obs.cash_and_equivalents,
            "net_debt": net_debt,
            "enterprise_value": ev,
            "ebitda": obs.ebitda,
        },
        period=obs.financial_period,
        formula="Enterprise Value / EBITDA",
        version=ENGINE_VERSION,
        unit="multiple",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        enterprise_value=ev,
        net_debt=net_debt,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        calculation=calc,
    )


def _compute_ps(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    if obs.revenue is None:
        return _excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = _denom_status(obs.revenue)
    if bad is not None:
        return _excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(market_cap, obs.revenue)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric="historical_ps",
        value=value,
        inputs={
            "market_cap": market_cap,
            "revenue": obs.revenue,
        },
        period=obs.financial_period,
        formula="Market Cap / Revenue",
        version=ENGINE_VERSION,
        unit="multiple",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        calculation=calc,
    )


def _compute_pb(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    if obs.total_equity is None:
        return _excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = _denom_status(obs.total_equity)
    if bad is not None:
        return _excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(market_cap, obs.total_equity)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric="historical_pb",
        value=value,
        inputs={
            "market_cap": market_cap,
            "total_equity": obs.total_equity,
        },
        period=obs.financial_period,
        formula="Market Cap / Total Equity",
        version=ENGINE_VERSION,
        unit="multiple",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        calculation=calc,
    )


def _compute_fcf_yield(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    if obs.cfo is None or obs.capex is None:
        return _excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    equity_fcf = (obs.cfo - obs.capex).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)

    bad = _denom_status(equity_fcf)
    if bad is not None:
        return _excluded_obs(
            obs, method, bad, market_cap=market_cap,
            cash_flow_basis=CashFlowBasis.EQUITY_FCF,
        )

    value, _ = safe_divide(equity_fcf, market_cap)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric="historical_fcf_yield",
        value=value,
        inputs={
            "cfo": obs.cfo,
            "capex": obs.capex,
            "equity_fcf": equity_fcf,
            "market_cap": market_cap,
        },
        period=obs.financial_period,
        formula="(CFO − CapEx) / Market Cap",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        cash_flow_basis=CashFlowBasis.EQUITY_FCF,
        calculation=calc,
    )


def _compute_ev_fcf(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
) -> HistoricalValuationObservation:
    ev_parts = _ev_components(obs, market_cap)
    if ev_parts is None:
        return _excluded_obs(
            obs, method, ObservationStatus.EXCLUDED_MISSING_DATA,
            market_cap=market_cap, cash_flow_basis=CashFlowBasis.FCFF,
        )
    net_debt, ev = ev_parts

    missing_fcff = (
        obs.ebit is None
        or obs.effective_tax_rate is None
        or obs.depreciation_amortization is None
        or obs.capex is None
        or obs.delta_nwc is None
    )
    if missing_fcff:
        return _excluded_obs(
            obs, method, ObservationStatus.EXCLUDED_MISSING_DATA,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
            cash_flow_basis=CashFlowBasis.FCFF,
        )

    assert obs.ebit is not None  # noqa: S101 — guaranteed by check above
    assert obs.effective_tax_rate is not None  # noqa: S101
    assert obs.depreciation_amortization is not None  # noqa: S101
    assert obs.capex is not None  # noqa: S101
    assert obs.delta_nwc is not None  # noqa: S101

    nopat = (obs.ebit * (_ONE - obs.effective_tax_rate)).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    fcff = (nopat + obs.depreciation_amortization - obs.capex - obs.delta_nwc).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    bad = _denom_status(fcff)
    if bad is not None:
        return _excluded_obs(
            obs, method, bad,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
            cash_flow_basis=CashFlowBasis.FCFF,
        )

    value, _ = safe_divide(ev, fcff)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric="historical_ev_fcf",
        value=value,
        inputs={
            "enterprise_value": ev,
            "ebit": obs.ebit,
            "effective_tax_rate": obs.effective_tax_rate,
            "nopat": nopat,
            "depreciation_amortization": obs.depreciation_amortization,
            "capex": obs.capex,
            "delta_nwc": obs.delta_nwc,
            "fcff": fcff,
        },
        period=obs.financial_period,
        formula="Enterprise Value / FCFF",
        version=ENGINE_VERSION,
        unit="multiple",
    )
    return HistoricalValuationObservation(
        observation_date=obs.observation_date,
        method=method,
        status=timing,
        value=value,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        market_cap=market_cap,
        enterprise_value=ev,
        net_debt=net_debt,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
        cash_flow_basis=CashFlowBasis.FCFF,
        calculation=calc,
    )


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _nearest_rank_index(p: Decimal, n: int) -> int:
    if p == _ZERO:
        return 0
    if p == _HUNDRED:
        return n - 1
    raw = p * Decimal(n) / _HUNDRED
    return int(raw.to_integral_value(rounding=ROUND_CEILING)) - 1


def _median(sorted_values: list[Decimal]) -> Decimal:
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return ((sorted_values[mid - 1] + sorted_values[mid]) / _TWO).quantize(
        RATIO_QUANTIZE, rounding=ROUNDING,
    )


def _std_dev(values: list[Decimal], mean: Decimal) -> Decimal | None:
    n = len(values)
    if n < 2:
        return None
    sum_sq = sum((v - mean) ** 2 for v in values)
    variance = sum_sq / Decimal(n - 1)
    return variance.sqrt().quantize(RATIO_QUANTIZE, rounding=ROUNDING)


def _sufficiency(count: int, thresholds: DataSufficiencyThresholds) -> DataSufficiency:
    if count == 0:
        return DataSufficiency.INSUFFICIENT
    if count < thresholds.min_minimal:
        return DataSufficiency.MINIMAL
    if count < thresholds.min_low:
        return DataSufficiency.LOW
    if count < thresholds.min_moderate:
        return DataSufficiency.MODERATE
    return DataSufficiency.ADEQUATE


def _compute_statistics(
    valid_values: list[Decimal],
    method: ValuationMethodType,
    percentiles: list[Decimal],
    thresholds: DataSufficiencyThresholds,
    unverified_count: int,
    excluded_count: int,
    lookback_start: date | None,
    lookback_end: date | None,
) -> ValuationBandStatistics:
    n = len(valid_values)
    sorted_vals = sorted(valid_values)

    mean_val = (sum(sorted_vals) / Decimal(n)).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
    median_val = _median(sorted_vals)
    sd = _std_dev(valid_values, mean_val)

    bands: list[PercentileBand] = []
    for p in percentiles:
        idx = _nearest_rank_index(p, n)
        bands.append(PercentileBand(percentile=p, value=sorted_vals[idx]))

    audit: list[CalculationResult] = []
    stat_inputs: dict[str, Decimal | str | int | None] = {
        "valid_count": n,
        "lookback_start": str(lookback_start) if lookback_start else None,
        "lookback_end": str(lookback_end) if lookback_end else None,
    }

    for name, val in [("min", sorted_vals[0]), ("max", sorted_vals[-1]),
                      ("mean", mean_val), ("median", median_val)]:
        audit.append(CalculationResult(
            metric=f"historical_{method.value}_{name}",
            value=val,
            inputs=stat_inputs,
            period="historical",
            formula=f"{name.capitalize()} of valid historical {method.value} observations",
            version=ENGINE_VERSION,
            unit="multiple" if method != ValuationMethodType.FCF_YIELD else "ratio",
        ))

    for band in bands:
        audit.append(CalculationResult(
            metric=f"historical_{method.value}_p{int(band.percentile)}",
            value=band.value,
            inputs=stat_inputs,
            period="historical",
            formula=f"Nearest-rank P{int(band.percentile)} of valid historical {method.value} observations",
            version=ENGINE_VERSION,
            unit="multiple" if method != ValuationMethodType.FCF_YIELD else "ratio",
        ))

    return ValuationBandStatistics(
        method=method,
        valid_count=n,
        unverified_count=unverified_count,
        excluded_count=excluded_count,
        min=sorted_vals[0],
        max=sorted_vals[-1],
        mean=mean_val,
        median=median_val,
        std_dev=sd,
        bands=bands,
        data_sufficiency=_sufficiency(n, thresholds),
        lookback_start=lookback_start,
        lookback_end=lookback_end,
        calculations=audit,
    )


# ---------------------------------------------------------------------------
# Current position
# ---------------------------------------------------------------------------


def _percentile_rank(current: Decimal, valid_values: list[Decimal]) -> Decimal | None:
    n = len(valid_values)
    if n == 0:
        return None
    below = sum(1 for v in valid_values if v < current)
    equal = sum(1 for v in valid_values if v == current)
    rank = (Decimal(below) + _HALF * Decimal(equal)) / Decimal(n) * _HUNDRED
    return rank.quantize(RATIO_QUANTIZE, rounding=ROUNDING)


def _compute_current_position(
    current_obs: HistoricalObservationInput,
    method: ValuationMethodType,
    valid_values: list[Decimal],
    statistics: ValuationBandStatistics | None,
    percentiles: list[Decimal],
) -> CurrentValuationPosition | None:
    if current_obs.price <= _ZERO or current_obs.shares_outstanding <= _ZERO:
        return None

    timing = _timing_status(current_obs)
    computed = _compute_observation(current_obs, method, timing)
    if computed.value is None:
        return None

    current_value = computed.value
    rank = _percentile_rank(current_value, valid_values)

    vs_median: Decimal | None = None
    dist_median: Decimal | None = None
    vs_p25: Decimal | None = None
    vs_p75: Decimal | None = None

    if statistics is not None:
        vs_median = (current_value - statistics.median).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
        if statistics.median != _ZERO:
            dist_median = (
                (current_value - statistics.median) / statistics.median * _HUNDRED
            ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

        p25_band = next((b for b in statistics.bands if b.percentile == Decimal("25")), None)
        p75_band = next((b for b in statistics.bands if b.percentile == Decimal("75")), None)
        if p25_band is not None:
            vs_p25 = (current_value - p25_band.value).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
        if p75_band is not None:
            vs_p75 = (current_value - p75_band.value).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    return CurrentValuationPosition(
        method=method,
        current_value=current_value,
        percentile_rank=rank,
        distance_from_median_pct=dist_median,
        vs_median=vs_median,
        vs_p25=vs_p25,
        vs_p75=vs_p75,
    )


# ---------------------------------------------------------------------------
# Main engine function
# ---------------------------------------------------------------------------


def historical_valuation_bands(
    observations: list[HistoricalObservationInput],
    method: ValuationMethodType,
    *,
    calculated_at: datetime,
    current_observation: HistoricalObservationInput | None = None,
    percentiles: list[Decimal] | None = None,
    lookback_start: date | None = None,
    lookback_end: date | None = None,
    sufficiency_thresholds: DataSufficiencyThresholds | None = None,
) -> HistoricalValuationResult:
    """Compute historical valuation bands for one method.

    The caller is responsible for providing prices and per-share financial data
    on a consistent split-adjusted basis. The engine does not perform
    corporate-action adjustments.

    Args:
        observations: Historical observation inputs (any frequency).
        method: Which valuation method to compute.
        calculated_at: Caller-supplied timestamp (engine never generates one).
        current_observation: Optional current-period observation for positioning.
        percentiles: Percentile bands to compute (default P10/P25/P50/P75/P90).
        lookback_start: Inclusive start of historical window (None = no bound).
        lookback_end: Inclusive end of historical window (None = no bound).
        sufficiency_thresholds: Data-sufficiency heuristic thresholds.

    Returns:
        HistoricalValuationResult with observations, statistics, and positioning.
    """
    pctls = percentiles if percentiles is not None else list(_DEFAULT_PERCENTILES)
    _validate_percentiles(pctls)
    thresholds = sufficiency_thresholds or _DEFAULT_THRESHOLDS

    # --- Filter lookback window ---
    filtered = _filter_lookback(observations, lookback_start, lookback_end)

    # --- Phase 1: Structural validation ---
    structurally_valid: list[HistoricalObservationInput] = []
    result_obs: list[HistoricalValuationObservation] = []

    for obs in filtered:
        if obs.price <= _ZERO or obs.shares_outstanding <= _ZERO:
            result_obs.append(_excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA))
        else:
            structurally_valid.append(obs)

    # --- Phase 2: Duplicate detection ---
    non_dup, dup_obs = _detect_duplicates(structurally_valid, method)
    result_obs.extend(dup_obs)

    # --- Phase 3-4: Timing + method computation ---
    valid_values: list[Decimal] = []
    unverified_count = 0
    excluded_count = len(result_obs)

    for obs in non_dup:
        timing = _timing_status(obs)
        computed = _compute_observation(obs, method, timing)
        result_obs.append(computed)

        if computed.status == ObservationStatus.VALID and computed.value is not None:
            valid_values.append(computed.value)
        elif computed.status == ObservationStatus.UNVERIFIED_TIMING:
            unverified_count += 1
        else:
            excluded_count += 1

    # --- Statistics ---
    statistics: ValuationBandStatistics | None = None
    if valid_values:
        statistics = _compute_statistics(
            valid_values, method, pctls, thresholds,
            unverified_count, excluded_count,
            lookback_start, lookback_end,
        )

    # --- Current position ---
    current_position: CurrentValuationPosition | None = None
    if current_observation is not None and statistics is not None:
        current_position = _compute_current_position(
            current_observation, method, valid_values, statistics, pctls,
        )

    # Sort observations by date for deterministic output
    result_obs.sort(key=lambda o: o.observation_date)

    return HistoricalValuationResult(
        method=method,
        observations=result_obs,
        statistics=statistics,
        current_position=current_position,
        engine_version=ENGINE_VERSION,
        calculated_at=calculated_at,
    )
