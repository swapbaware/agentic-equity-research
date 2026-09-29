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
from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation._valuation_calc import (
    ZERO,
    compute_observation,
    excluded_obs,
    median_value,
    nearest_rank_index,
    percentile_rank,
    std_dev,
    sufficiency,
    timing_status,
    validate_percentiles,
)
from app.valuation.models import (
    CurrentValuationPosition,
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
            dup_obs.append(excluded_obs(first, method, ObservationStatus.DUPLICATE_OBSERVATION))

    return non_dup, dup_obs


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


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
    median_val = median_value(sorted_vals)
    sd = std_dev(valid_values, mean_val)

    bands: list[PercentileBand] = []
    for p in percentiles:
        idx = nearest_rank_index(p, n)
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
        data_sufficiency=sufficiency(n, thresholds),
        lookback_start=lookback_start,
        lookback_end=lookback_end,
        calculations=audit,
    )


# ---------------------------------------------------------------------------
# Current position
# ---------------------------------------------------------------------------


def _compute_current_position(
    current_obs: HistoricalObservationInput,
    method: ValuationMethodType,
    valid_values: list[Decimal],
    statistics: ValuationBandStatistics | None,
    percentiles: list[Decimal],
) -> CurrentValuationPosition | None:
    if current_obs.price <= ZERO or current_obs.shares_outstanding <= ZERO:
        return None

    timing = timing_status(current_obs)
    computed = compute_observation(
        current_obs, method, timing,
        engine_version=ENGINE_VERSION, metric_prefix="historical",
    )
    if computed.value is None:
        return None

    current_value = computed.value
    rank = percentile_rank(current_value, valid_values)

    vs_median: Decimal | None = None
    dist_median: Decimal | None = None
    vs_p25: Decimal | None = None
    vs_p75: Decimal | None = None

    if statistics is not None:
        vs_median = (current_value - statistics.median).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
        if statistics.median != ZERO:
            dist_median = (
                (current_value - statistics.median) / statistics.median * Decimal("100")
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
    try:
        validate_percentiles(pctls)
    except ValueError as exc:
        raise HistoricalBandError(str(exc)) from exc
    thresholds = sufficiency_thresholds or _DEFAULT_THRESHOLDS

    # --- Filter lookback window ---
    filtered = _filter_lookback(observations, lookback_start, lookback_end)

    # --- Phase 1: Structural validation ---
    structurally_valid: list[HistoricalObservationInput] = []
    result_obs: list[HistoricalValuationObservation] = []

    for obs in filtered:
        if obs.price <= ZERO or obs.shares_outstanding <= ZERO:
            result_obs.append(excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA))
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
        timing = timing_status(obs)
        computed = compute_observation(
            obs, method, timing,
            engine_version=ENGINE_VERSION, metric_prefix="historical",
        )
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
