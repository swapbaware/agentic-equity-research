"""Peer Comparison Engine — deterministic, cross-sectional.

Compares a target company's valuation multiple against an explicitly
supplied peer set. One valuation method per invocation.

All calculations use decimal.Decimal, never float. The engine never calls
date.today() or datetime.now(); calculated_at is caller-supplied. No
database, no network, no LLM, no system clock, no mutable global state.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation._valuation_calc import (
    HUNDRED,
    ZERO,
    compute_observation,
    median_value,
    nearest_rank_index,
    percentile_rank,
    std_dev,
    sufficiency,
    timing_status,
    validate_percentiles,
)
from app.valuation.models import (
    DataSufficiencyThresholds,
    HistoricalValuationObservation,
    ObservationStatus,
    PeerComparisonResult,
    PeerObservationInput,
    PeerSetMetadata,
    PeerStatistics,
    PeerValuationObservation,
    PercentileBand,
    TargetVsPeerPosition,
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

PEER_DEFAULT_THRESHOLDS = DataSufficiencyThresholds(
    min_minimal=3,
    min_low=5,
    min_moderate=10,
)


class PeerComparisonError(Exception):
    """Raised for irreconcilable peer-set conflicts."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_peer_obs(
    peer_input: PeerObservationInput,
    computed: HistoricalValuationObservation,
) -> PeerValuationObservation:
    return PeerValuationObservation(
        company_id=peer_input.company_id,
        company_name=peer_input.company_name,
        currency=peer_input.currency,
        observation_date=computed.observation_date,
        method=computed.method,
        status=computed.status,
        value=computed.value,
        price=computed.price,
        shares_outstanding=computed.shares_outstanding,
        market_cap=computed.market_cap,
        enterprise_value=computed.enterprise_value,
        net_debt=computed.net_debt,
        financial_period=computed.financial_period,
        financial_period_type=computed.financial_period_type,
        financials_available_date=computed.financials_available_date,
        cash_flow_basis=computed.cash_flow_basis,
        calculation=computed.calculation,
    )


def _excluded_peer(
    peer_input: PeerObservationInput,
    method: ValuationMethodType,
    status: ObservationStatus,
) -> PeerValuationObservation:
    obs = peer_input.observation
    return PeerValuationObservation(
        company_id=peer_input.company_id,
        company_name=peer_input.company_name,
        currency=peer_input.currency,
        observation_date=obs.observation_date,
        method=method,
        status=status,
        price=obs.price,
        shares_outstanding=obs.shares_outstanding,
        financial_period=obs.financial_period,
        financial_period_type=obs.financial_period_type,
        financials_available_date=obs.financials_available_date,
    )


def _compute_peer(
    peer_input: PeerObservationInput,
    method: ValuationMethodType,
) -> PeerValuationObservation:
    obs = peer_input.observation

    if obs.price <= ZERO or obs.shares_outstanding <= ZERO:
        return _excluded_peer(peer_input, method, ObservationStatus.EXCLUDED_MISSING_DATA)

    timing = timing_status(obs)
    computed = compute_observation(
        obs, method, timing,
        engine_version=ENGINE_VERSION, metric_prefix="peer",
    )
    return _to_peer_obs(peer_input, computed)


def _detect_peer_duplicates(
    peers: list[PeerObservationInput],
    method: ValuationMethodType,
) -> tuple[list[PeerObservationInput], list[PeerValuationObservation]]:
    by_id: dict[str, list[PeerObservationInput]] = {}
    for p in peers:
        by_id.setdefault(p.company_id, []).append(p)

    deduped: list[PeerObservationInput] = []
    dup_obs: list[PeerValuationObservation] = []

    for cid in sorted(by_id):
        group = by_id[cid]
        if len(group) == 1:
            deduped.append(group[0])
            continue

        first = group[0]
        if not all(p.observation == first.observation for p in group[1:]):
            msg = f"Contradictory observations for company_id '{cid}'"
            raise PeerComparisonError(msg)

        deduped.append(first)
        for _ in group[1:]:
            dup_obs.append(_excluded_peer(first, method, ObservationStatus.DUPLICATE_OBSERVATION))

    return deduped, dup_obs


def _rank_if_inserted(target_value: Decimal, peer_values: list[Decimal]) -> int:
    return sum(1 for v in peer_values if v <= target_value) + 1


def _compute_peer_statistics(
    valid_values: list[Decimal],
    method: ValuationMethodType,
    percentiles: list[Decimal],
    thresholds: DataSufficiencyThresholds,
    unverified_count: int,
    excluded_count: int,
) -> PeerStatistics:
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
    stat_inputs: dict[str, Decimal | str | int | None] = {"valid_count": n}

    for name, val in [("min", sorted_vals[0]), ("max", sorted_vals[-1]),
                      ("mean", mean_val), ("median", median_val)]:
        audit.append(CalculationResult(
            metric=f"peer_{method.value}_{name}",
            value=val,
            inputs=stat_inputs,
            period="peer_comparison",
            formula=f"{name.capitalize()} of valid peer {method.value} observations",
            version=ENGINE_VERSION,
            unit="multiple" if method != ValuationMethodType.FCF_YIELD else "ratio",
        ))

    for band in bands:
        audit.append(CalculationResult(
            metric=f"peer_{method.value}_p{int(band.percentile)}",
            value=band.value,
            inputs=stat_inputs,
            period="peer_comparison",
            formula=f"Nearest-rank P{int(band.percentile)} of valid peer {method.value} observations",
            version=ENGINE_VERSION,
            unit="multiple" if method != ValuationMethodType.FCF_YIELD else "ratio",
        ))

    return PeerStatistics(
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
        calculations=audit,
    )


def _compute_position(
    target_value: Decimal,
    target_company_id: str,
    method: ValuationMethodType,
    valid_values: list[Decimal],
    stats: PeerStatistics,
) -> TargetVsPeerPosition:
    diff = (target_value - stats.median).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    diff_pct: Decimal | None = None
    if stats.median != ZERO:
        diff_pct = (
            (target_value - stats.median) / stats.median * HUNDRED
        ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    rank = percentile_rank(target_value, valid_values)
    inserted = _rank_if_inserted(target_value, valid_values)

    vs_p25: Decimal | None = None
    vs_p75: Decimal | None = None
    p25_band = next((b for b in stats.bands if b.percentile == Decimal("25")), None)
    p75_band = next((b for b in stats.bands if b.percentile == Decimal("75")), None)
    if p25_band is not None:
        vs_p25 = (target_value - p25_band.value).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
    if p75_band is not None:
        vs_p75 = (target_value - p75_band.value).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    return TargetVsPeerPosition(
        method=method,
        target_value=target_value,
        target_company_id=target_company_id,
        peer_median=stats.median,
        difference_from_median=diff,
        difference_from_median_pct=diff_pct,
        percentile_rank=rank,
        rank_if_inserted=inserted,
        peer_count=stats.valid_count,
        vs_p25=vs_p25,
        vs_p75=vs_p75,
    )


# ---------------------------------------------------------------------------
# Main engine function
# ---------------------------------------------------------------------------


def compare_peers(
    target: PeerObservationInput,
    peers: list[PeerObservationInput],
    method: ValuationMethodType,
    *,
    calculated_at: datetime,
    peer_set_metadata: PeerSetMetadata | None = None,
    percentiles: list[Decimal] | None = None,
    sufficiency_thresholds: DataSufficiencyThresholds | None = None,
) -> PeerComparisonResult:
    """Compare a target company against its peers for one valuation method.

    Args:
        target: Target company observation.
        peers: Explicitly supplied peer observations.
        method: Which valuation method to compute.
        calculated_at: Caller-supplied timestamp (engine never generates one).
        peer_set_metadata: Optional provenance for the peer set.
        percentiles: Percentile bands to compute (default P10/P25/P50/P75/P90).
        sufficiency_thresholds: Data-sufficiency heuristic thresholds.

    Returns:
        PeerComparisonResult with per-peer observations, statistics,
        and target positioning.
    """
    if method == ValuationMethodType.PEG:
        msg = "PEG is not supported for peer comparison"
        raise PeerComparisonError(msg)

    pctls = percentiles if percentiles is not None else list(_DEFAULT_PERCENTILES)
    try:
        validate_percentiles(pctls)
    except ValueError as exc:
        raise PeerComparisonError(str(exc)) from exc
    thresholds = sufficiency_thresholds or PEER_DEFAULT_THRESHOLDS

    # --- Exclude target from peer list ---
    filtered_peers: list[PeerObservationInput] = []
    target_as_peer_obs: list[PeerValuationObservation] = []
    for p in peers:
        if p.company_id == target.company_id:
            target_as_peer_obs.append(
                _excluded_peer(p, method, ObservationStatus.DUPLICATE_OBSERVATION),
            )
        else:
            filtered_peers.append(p)

    # --- Duplicate detection by company_id ---
    deduped, dup_obs = _detect_peer_duplicates(filtered_peers, method)

    # --- Compute target ---
    target_computed = _compute_peer(target, method)

    # --- Compute peers ---
    peer_results: list[PeerValuationObservation] = []
    valid_values: list[Decimal] = []
    unverified_count = 0
    excluded_count = len(dup_obs) + len(target_as_peer_obs)

    for p in deduped:
        result = _compute_peer(p, method)
        peer_results.append(result)

        if result.status == ObservationStatus.VALID and result.value is not None:
            valid_values.append(result.value)
        elif result.status == ObservationStatus.UNVERIFIED_TIMING:
            unverified_count += 1
        else:
            excluded_count += 1

    all_peer_obs = peer_results + dup_obs + target_as_peer_obs

    # --- Statistics ---
    statistics: PeerStatistics | None = None
    if valid_values:
        statistics = _compute_peer_statistics(
            valid_values, method, pctls, thresholds,
            unverified_count, excluded_count,
        )

    # --- Target positioning ---
    position: TargetVsPeerPosition | None = None
    if (
        statistics is not None
        and target_computed.status == ObservationStatus.VALID
        and target_computed.value is not None
    ):
        position = _compute_position(
            target_computed.value,
            target.company_id,
            method,
            valid_values,
            statistics,
        )

    return PeerComparisonResult(
        method=method,
        target=target_computed,
        peers=all_peer_obs,
        statistics=statistics,
        position=position,
        peer_set_metadata=peer_set_metadata,
        engine_version=ENGINE_VERSION,
        calculated_at=calculated_at,
    )
