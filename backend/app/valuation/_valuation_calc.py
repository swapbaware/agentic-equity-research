"""Shared deterministic valuation calculation helpers.

Pure functions used by both historical_bands.py and peer_comparison.py.
All arithmetic uses decimal.Decimal. No database, no network, no LLM,
no system clock.

Dependency direction:
    analytics/models.py, analytics/_calc.py
        ↓
    valuation/models.py
        ↓
    valuation/_valuation_calc.py  (this module)
        ↓           ↓
    historical_bands.py   peer_comparison.py
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from app.analytics._calc import safe_divide
from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation.models import (
    CashFlowBasis,
    DataSufficiency,
    DataSufficiencyThresholds,
    HistoricalObservationInput,
    HistoricalValuationObservation,
    ObservationStatus,
    ValuationMethodType,
)

CURRENCY_QUANTIZE = Decimal("0.0001")
ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
HUNDRED = Decimal("100")
HALF = Decimal("0.5")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_percentiles(percentiles: list[Decimal]) -> None:
    for p in percentiles:
        if p < ZERO or p > HUNDRED:
            msg = f"percentile must be in [0, 100], got {p}"
            raise ValueError(msg)


def timing_status(obs: HistoricalObservationInput) -> ObservationStatus:
    if obs.financials_available_date is None:
        return ObservationStatus.UNVERIFIED_TIMING
    if obs.financials_available_date > obs.observation_date:
        return ObservationStatus.LOOK_AHEAD_RISK
    return ObservationStatus.VALID


def denom_status(value: Decimal) -> ObservationStatus | None:
    if value < ZERO:
        return ObservationStatus.EXCLUDED_NEGATIVE_DENOMINATOR
    if value == ZERO:
        return ObservationStatus.EXCLUDED_ZERO_DENOMINATOR
    return None


# ---------------------------------------------------------------------------
# Financial component helpers
# ---------------------------------------------------------------------------


def ev_components(
    obs: HistoricalObservationInput,
    market_cap: Decimal,
) -> tuple[Decimal, Decimal] | None:
    if obs.total_debt is None or obs.cash_and_equivalents is None:
        return None
    net_debt = (obs.total_debt - obs.cash_and_equivalents).quantize(
        CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    ev = (market_cap + net_debt).quantize(CURRENCY_QUANTIZE, rounding=ROUNDING)
    return net_debt, ev


def excluded_obs(
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
# Per-method ratio computation
# ---------------------------------------------------------------------------


def compute_observation(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    market_cap = (obs.price * obs.shares_outstanding).quantize(
        CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    kw = {"engine_version": engine_version, "metric_prefix": metric_prefix}

    if method == ValuationMethodType.PE:
        return _compute_pe(obs, method, timing, market_cap, **kw)
    if method == ValuationMethodType.EV_EBITDA:
        return _compute_ev_ebitda(obs, method, timing, market_cap, **kw)
    if method == ValuationMethodType.PS:
        return _compute_ps(obs, method, timing, market_cap, **kw)
    if method == ValuationMethodType.PB:
        return _compute_pb(obs, method, timing, market_cap, **kw)
    if method == ValuationMethodType.FCF_YIELD:
        return _compute_fcf_yield(obs, method, timing, market_cap, **kw)
    if method == ValuationMethodType.EV_FCF:
        return _compute_ev_fcf(obs, method, timing, market_cap, **kw)

    msg = f"Unsupported method: {method}"
    raise ValueError(msg)


def _compute_pe(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    if obs.eps is None:
        return excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = denom_status(obs.eps)
    if bad is not None:
        return excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(obs.price, obs.eps)
    assert value is not None  # noqa: S101 — eps > 0 guaranteed above

    calc = CalculationResult(
        metric=f"{metric_prefix}_pe",
        value=value,
        inputs={"price": obs.price, "eps": obs.eps},
        period=obs.financial_period,
        formula="Price / EPS",
        version=engine_version,
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


def _compute_ev_ebitda(
    obs: HistoricalObservationInput,
    method: ValuationMethodType,
    timing: ObservationStatus,
    market_cap: Decimal,
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    ev_parts = ev_components(obs, market_cap)
    if ev_parts is None:
        return excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    net_debt, ev = ev_parts

    if obs.ebitda is None:
        return excluded_obs(
            obs, method, ObservationStatus.EXCLUDED_MISSING_DATA,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
        )

    bad = denom_status(obs.ebitda)
    if bad is not None:
        return excluded_obs(
            obs, method, bad,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
        )

    value, _ = safe_divide(ev, obs.ebitda)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric=f"{metric_prefix}_ev_ebitda",
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
        version=engine_version,
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
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    if obs.revenue is None:
        return excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = denom_status(obs.revenue)
    if bad is not None:
        return excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(market_cap, obs.revenue)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric=f"{metric_prefix}_ps",
        value=value,
        inputs={
            "market_cap": market_cap,
            "revenue": obs.revenue,
        },
        period=obs.financial_period,
        formula="Market Cap / Revenue",
        version=engine_version,
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
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    if obs.total_equity is None:
        return excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    bad = denom_status(obs.total_equity)
    if bad is not None:
        return excluded_obs(obs, method, bad, market_cap=market_cap)

    value, _ = safe_divide(market_cap, obs.total_equity)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric=f"{metric_prefix}_pb",
        value=value,
        inputs={
            "market_cap": market_cap,
            "total_equity": obs.total_equity,
        },
        period=obs.financial_period,
        formula="Market Cap / Total Equity",
        version=engine_version,
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
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    if obs.cfo is None or obs.capex is None:
        return excluded_obs(obs, method, ObservationStatus.EXCLUDED_MISSING_DATA, market_cap=market_cap)

    equity_fcf = (obs.cfo - obs.capex).quantize(CURRENCY_QUANTIZE, rounding=ROUNDING)

    bad = denom_status(equity_fcf)
    if bad is not None:
        return excluded_obs(
            obs, method, bad, market_cap=market_cap,
            cash_flow_basis=CashFlowBasis.EQUITY_FCF,
        )

    value, _ = safe_divide(equity_fcf, market_cap)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric=f"{metric_prefix}_fcf_yield",
        value=value,
        inputs={
            "cfo": obs.cfo,
            "capex": obs.capex,
            "equity_fcf": equity_fcf,
            "market_cap": market_cap,
        },
        period=obs.financial_period,
        formula="(CFO − CapEx) / Market Cap",
        version=engine_version,
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
    *,
    engine_version: str,
    metric_prefix: str,
) -> HistoricalValuationObservation:
    ev_parts = ev_components(obs, market_cap)
    if ev_parts is None:
        return excluded_obs(
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
        return excluded_obs(
            obs, method, ObservationStatus.EXCLUDED_MISSING_DATA,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
            cash_flow_basis=CashFlowBasis.FCFF,
        )

    assert obs.ebit is not None  # noqa: S101 — guaranteed by check above
    assert obs.effective_tax_rate is not None  # noqa: S101
    assert obs.depreciation_amortization is not None  # noqa: S101
    assert obs.capex is not None  # noqa: S101
    assert obs.delta_nwc is not None  # noqa: S101

    nopat = (obs.ebit * (ONE - obs.effective_tax_rate)).quantize(
        CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    fcff = (nopat + obs.depreciation_amortization - obs.capex - obs.delta_nwc).quantize(
        CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    bad = denom_status(fcff)
    if bad is not None:
        return excluded_obs(
            obs, method, bad,
            market_cap=market_cap, enterprise_value=ev, net_debt=net_debt,
            cash_flow_basis=CashFlowBasis.FCFF,
        )

    value, _ = safe_divide(ev, fcff)
    assert value is not None  # noqa: S101

    calc = CalculationResult(
        metric=f"{metric_prefix}_ev_fcf",
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
        version=engine_version,
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
# Statistical helpers
# ---------------------------------------------------------------------------


def nearest_rank_index(p: Decimal, n: int) -> int:
    if p == ZERO:
        return 0
    if p == HUNDRED:
        return n - 1
    raw = p * Decimal(n) / HUNDRED
    return int(raw.to_integral_value(rounding=ROUND_CEILING)) - 1


def median_value(sorted_values: list[Decimal]) -> Decimal:
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return ((sorted_values[mid - 1] + sorted_values[mid]) / TWO).quantize(
        RATIO_QUANTIZE, rounding=ROUNDING,
    )


def std_dev(values: list[Decimal], mean: Decimal) -> Decimal | None:
    n = len(values)
    if n < 2:
        return None
    sum_sq = sum((v - mean) ** 2 for v in values)
    variance = sum_sq / Decimal(n - 1)
    return variance.sqrt().quantize(RATIO_QUANTIZE, rounding=ROUNDING)


def sufficiency(count: int, thresholds: DataSufficiencyThresholds) -> DataSufficiency:
    if count == 0:
        return DataSufficiency.INSUFFICIENT
    if count < thresholds.min_minimal:
        return DataSufficiency.MINIMAL
    if count < thresholds.min_low:
        return DataSufficiency.LOW
    if count < thresholds.min_moderate:
        return DataSufficiency.MODERATE
    return DataSufficiency.ADEQUATE


def percentile_rank(current: Decimal, valid_values: list[Decimal]) -> Decimal | None:
    n = len(valid_values)
    if n == 0:
        return None
    below = sum(1 for v in valid_values if v < current)
    equal = sum(1 for v in valid_values if v == current)
    rank = (Decimal(below) + HALF * Decimal(equal)) / Decimal(n) * HUNDRED
    return rank.quantize(RATIO_QUANTIZE, rounding=ROUNDING)
