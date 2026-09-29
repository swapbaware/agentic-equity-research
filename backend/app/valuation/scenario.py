"""Scenario Engine — Bear/Base/Bull orchestration layer.

Constructs per-scenario assumption sets and delegates to existing
deterministic valuation engines. No financial formulas are duplicated.
All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult, PeriodFinancials
from app.valuation.dcf import DCFValidationError, dcf_valuation
from app.valuation.models import (
    DCFResult,
    MultipleValuationResult,
    ScenarioComparison,
    ScenarioDefinition,
    ScenarioDiagnostic,
    ScenarioExecutionStatus,
    ScenarioLabel,
    ScenarioResult,
    SingleScenarioOutput,
    ValuationMethodType,
)
from app.valuation.multiples import (
    MultipleValuationError,
    ev_ebitda_valuation,
    ev_fcf_valuation,
    fcf_yield_valuation,
    pb_valuation,
    pe_valuation,
    ps_valuation,
)
from app.valuation.terminal import TerminalValueError

ENGINE_VERSION = "1.0.0"
_CURRENCY_QUANTIZE = Decimal("0.0001")
_ONE = Decimal("1")
_TEN = Decimal("10")
_ZERO = Decimal("0")

_REQUIRED_LABELS = frozenset(ScenarioLabel)

_MULTIPLE_DISPATCH: dict[
    ValuationMethodType,
    str,
] = {
    ValuationMethodType.PE: "pe",
    ValuationMethodType.EV_EBITDA: "ev_ebitda",
    ValuationMethodType.PS: "ps",
    ValuationMethodType.PB: "pb",
    ValuationMethodType.PEG: "peg",
    ValuationMethodType.FCF_YIELD: "fcf_yield",
    ValuationMethodType.EV_FCF: "ev_fcf",
}


class ScenarioEngineError(Exception):
    """Base error for scenario engine failures."""


class ScenarioValidationError(ScenarioEngineError):
    """Raised for invalid scenario inputs (pre-execution)."""


class ScenarioExecutionError(ScenarioEngineError):
    """Raised when all scenarios fail."""


def _validate_scenarios(
    scenarios: list[ScenarioDefinition],
    financials: list[PeriodFinancials],
    current_price: Decimal,
) -> None:
    if not financials:
        msg = "at least one period of historical financials is required"
        raise ScenarioValidationError(msg)

    if current_price <= _ZERO:
        msg = "current_price must be positive"
        raise ScenarioValidationError(msg)

    if len(scenarios) != 3:  # noqa: PLR2004
        msg = f"exactly 3 scenarios required (BEAR, BASE, BULL), got {len(scenarios)}"
        raise ScenarioValidationError(msg)

    labels = [s.label for s in scenarios]
    label_set = set(labels)

    if len(label_set) != len(labels):
        msg = f"duplicate scenario labels: {labels}"
        raise ScenarioValidationError(msg)

    missing = _REQUIRED_LABELS - label_set
    if missing:
        msg = f"missing required scenario labels: {sorted(missing)}"
        raise ScenarioValidationError(msg)

    weights = [s.probability_weight for s in scenarios]
    has_weights = [w is not None for w in weights]
    if any(has_weights) and not all(has_weights):
        msg = "probability_weight must be supplied for all three scenarios or none"
        raise ScenarioValidationError(msg)

    if all(has_weights):
        total = sum(w for w in weights if w is not None)
        if total != _ONE:
            msg = f"probability weights must sum to exactly 1, got {total}"
            raise ScenarioValidationError(msg)


def _execute_multiples(
    scenario: ScenarioDefinition,
    financials: list[PeriodFinancials],
    current_price: Decimal,
    calculated_at: datetime,
) -> list[MultipleValuationResult]:
    if not scenario.multiple_assumptions:
        return []

    results: list[MultipleValuationResult] = []
    latest = financials[-1]

    for assumption in scenario.multiple_assumptions:
        try:
            result = _dispatch_multiple(
                assumption.method,
                latest,
                financials[-2] if len(financials) >= 2 else latest,  # noqa: PLR2004
                assumption.target_multiple,
                current_price,
                calculated_at,
            )
            results.append(result)
        except (MultipleValuationError, ValueError):
            pass

    return results


def _dispatch_multiple(
    method: ValuationMethodType,
    financials: PeriodFinancials,
    prior_financials: PeriodFinancials,
    target_multiple: Decimal,
    current_price: Decimal,
    calculated_at: datetime,
) -> MultipleValuationResult:
    if method == ValuationMethodType.PE:
        return pe_valuation(
            financials, target_multiple, current_price, calculated_at=calculated_at,
        )
    if method == ValuationMethodType.EV_EBITDA:
        return ev_ebitda_valuation(
            financials, target_multiple, current_price, calculated_at=calculated_at,
        )
    if method == ValuationMethodType.PS:
        return ps_valuation(
            financials, target_multiple, current_price, calculated_at=calculated_at,
        )
    if method == ValuationMethodType.PB:
        return pb_valuation(
            financials, target_multiple, current_price, calculated_at=calculated_at,
        )
    if method == ValuationMethodType.PEG:
        msg = "PEG requires earnings_growth_pct; not supported in scenario multiple dispatch"
        raise MultipleValuationError(msg)
    if method == ValuationMethodType.FCF_YIELD:
        return fcf_yield_valuation(
            financials, target_multiple, current_price, calculated_at=calculated_at,
        )
    if method == ValuationMethodType.EV_FCF:
        return ev_fcf_valuation(
            financials, prior_financials, target_multiple,
            current_price, calculated_at=calculated_at,
        )
    msg = f"unsupported multiple method: {method}"
    raise MultipleValuationError(msg)


def _execute_scenario(
    scenario: ScenarioDefinition,
    financials: list[PeriodFinancials],
    current_price: Decimal,
    calculated_at: datetime,
) -> SingleScenarioOutput:
    diagnostics: list[ScenarioDiagnostic] = []

    try:
        dcf_ok = dcf_valuation(
            financials,
            scenario.dcf_assumptions,
            current_price,
            calculated_at=calculated_at,
        )
        dcf_result: DCFResult | None = dcf_ok
        implied: Decimal | None = dcf_ok.implied_value_per_share
        status = ScenarioExecutionStatus.COMPLETED
        error_msg: str | None = None
    except (DCFValidationError, TerminalValueError, ValueError) as exc:
        dcf_result = None
        implied = None
        status = ScenarioExecutionStatus.FAILED
        error_msg = str(exc)
        diagnostics.append(ScenarioDiagnostic.SCENARIO_EXECUTION_FAILED)

    multiple_results = _execute_multiples(
        scenario, financials, current_price, calculated_at,
    )

    return SingleScenarioOutput(
        label=scenario.label,
        narrative=scenario.narrative,
        execution_status=status,
        dcf_result=dcf_result,
        multiple_results=multiple_results,
        assumption_provenance=scenario.assumption_provenance,
        probability_weight=scenario.probability_weight,
        implied_value_per_share=implied,
        error_message=error_msg,
        diagnostics=diagnostics,
    )


def _upside(implied: Decimal | None, current: Decimal) -> Decimal | None:
    if implied is None:
        return None
    return ((implied - current) / current).quantize(RATIO_QUANTIZE, rounding=ROUNDING)


def _build_comparison(
    outputs: dict[ScenarioLabel, SingleScenarioOutput],
    current_price: Decimal,
    audit: list[CalculationResult],
) -> ScenarioComparison:
    bear = outputs[ScenarioLabel.BEAR]
    base = outputs[ScenarioLabel.BASE]
    bull = outputs[ScenarioLabel.BULL]

    bear_iv = bear.implied_value_per_share
    base_iv = base.implied_value_per_share
    bull_iv = bull.implied_value_per_share

    completed = [v for v in (bear_iv, base_iv, bull_iv) if v is not None]
    count = len(completed)

    if count >= 2:  # noqa: PLR2004
        low = min(completed)
        high = max(completed)
        mid = ((low + high) / Decimal("2")).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
        audit.append(CalculationResult(
            metric="scenario_value_range",
            value=mid,
            inputs={"low": low, "high": high},
            period="scenario",
            formula="(low + high) / 2",
            version=ENGINE_VERSION,
            unit="currency_per_share",
        ))
    else:
        low = None
        high = None
        mid = None

    pwv: Decimal | None = None
    w_bear = bear.probability_weight
    w_base = base.probability_weight
    w_bull = bull.probability_weight
    if (
        count == 3  # noqa: PLR2004
        and w_bear is not None
        and w_base is not None
        and w_bull is not None
        and bear_iv is not None
        and base_iv is not None
        and bull_iv is not None
    ):
        pwv = (
            w_bear * bear_iv + w_base * base_iv + w_bull * bull_iv
        ).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
        audit.append(CalculationResult(
            metric="probability_weighted_value",
            value=pwv,
            inputs={
                "bear_weight": w_bear,
                "base_weight": w_base,
                "bull_weight": w_bull,
                "bear_value": bear_iv,
                "base_value": base_iv,
                "bull_value": bull_iv,
            },
            period="scenario",
            formula="Σ(weight_i × implied_value_i)",
            version=ENGINE_VERSION,
            unit="currency_per_share",
        ))

    upside_bear = _upside(bear_iv, current_price)
    upside_base = _upside(base_iv, current_price)
    upside_bull = _upside(bull_iv, current_price)

    for label_str, up in [("bear", upside_bear), ("base", upside_base), ("bull", upside_bull)]:
        if up is not None:
            audit.append(CalculationResult(
                metric=f"upside_to_{label_str}",
                value=up,
                inputs={
                    "implied_value": outputs[ScenarioLabel(label_str)].implied_value_per_share,
                    "current_price": current_price,
                },
                period="scenario",
                formula="(implied - current) / current",
                version=ENGINE_VERSION,
                unit="ratio",
            ))

    return ScenarioComparison(
        value_range_low=low,
        value_range_high=high,
        value_range_midpoint=mid,
        probability_weighted_value=pwv,
        current_price=current_price,
        bear_implied_value=bear_iv,
        base_implied_value=base_iv,
        bull_implied_value=bull_iv,
        upside_to_bear=upside_bear,
        upside_to_base=upside_base,
        upside_to_bull=upside_bull,
        completed_scenario_count=count,
        calculations=audit,
    )


def _collect_diagnostics(
    outputs: dict[ScenarioLabel, SingleScenarioOutput],
    scenarios: list[ScenarioDefinition],
) -> list[ScenarioDiagnostic]:
    diags: list[ScenarioDiagnostic] = []
    bear = outputs[ScenarioLabel.BEAR]
    base = outputs[ScenarioLabel.BASE]
    bull = outputs[ScenarioLabel.BULL]

    bear_iv = bear.implied_value_per_share
    base_iv = base.implied_value_per_share
    bull_iv = bull.implied_value_per_share

    if bear_iv is not None and base_iv is not None and bear_iv > base_iv:
        diags.append(ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED)
    if base_iv is not None and bull_iv is not None and base_iv > bull_iv:
        diags.append(ScenarioDiagnostic.VALUE_ORDER_UNEXPECTED)

    dcf_keys = [s.dcf_assumptions for s in scenarios]
    if dcf_keys[0] == dcf_keys[1] == dcf_keys[2]:
        diags.append(ScenarioDiagnostic.IDENTICAL_ASSUMPTIONS)

    completed_vals = [v for v in (bear_iv, base_iv, bull_iv) if v is not None]
    if len(completed_vals) >= 2:  # noqa: PLR2004
        lo = min(completed_vals)
        hi = max(completed_vals)
        if lo > _ZERO and hi / lo > _TEN:
            diags.append(ScenarioDiagnostic.EXTREME_SPREAD)

    failed_count = sum(
        1 for o in (bear, base, bull) if o.execution_status == ScenarioExecutionStatus.FAILED
    )
    if 0 < failed_count < 3:  # noqa: PLR2004
        diags.append(ScenarioDiagnostic.INCOMPLETE_COMPARISON)

    if any(not s.assumption_provenance for s in scenarios):
        diags.append(ScenarioDiagnostic.MISSING_PROVENANCE)

    return diags


def run_scenarios(
    financials: list[PeriodFinancials],
    scenarios: list[ScenarioDefinition],
    current_price: Decimal,
    calculated_at: datetime,
) -> ScenarioResult:
    """Execute Bear/Base/Bull scenario analysis.

    Delegates to existing DCF and multiple-valuation engines.
    No financial formulas are duplicated.
    """
    _validate_scenarios(scenarios, financials, current_price)

    label_order = [ScenarioLabel.BEAR, ScenarioLabel.BASE, ScenarioLabel.BULL]
    by_label = {s.label: s for s in scenarios}

    outputs: dict[ScenarioLabel, SingleScenarioOutput] = {}
    for label in label_order:
        outputs[label] = _execute_scenario(
            by_label[label], financials, current_price, calculated_at,
        )

    all_failed = all(
        o.execution_status == ScenarioExecutionStatus.FAILED for o in outputs.values()
    )
    if all_failed:
        errors = {
            label.value: outputs[label].error_message for label in label_order
        }
        msg = f"all three scenarios failed: {errors}"
        raise ScenarioExecutionError(msg)

    audit: list[CalculationResult] = []
    comparison = _build_comparison(outputs, current_price, audit)
    diags = _collect_diagnostics(outputs, [by_label[lbl] for lbl in label_order])

    scenario_list = [outputs[label] for label in label_order]

    return ScenarioResult(
        scenarios=scenario_list,
        comparison=comparison,
        calculations=audit,
        calculated_at=calculated_at,
        engine_version=ENGINE_VERSION,
        diagnostics=diags,
    )
