"""Reverse DCF — find the implied revenue growth rate for a target price.

Treats dcf_valuation() as a black-box oracle. Each candidate growth rate
is evaluated by calling the forward DCF engine; no DCF formulas are
duplicated here.

Solver: deterministic bisection on a monotonically increasing function.

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.analytics.models import CalculationResult, PeriodFinancials
from app.valuation.dcf import dcf_valuation
from app.valuation.models import (
    ConvergenceStatus,
    DCFAssumptions,
    DCFResult,
    ReverseDCFResult,
)

ENGINE_VERSION = "1.0.0"
_TWO = Decimal("2")
_RATIO_QUANTIZE = Decimal("0.000001")


class ReverseDCFError(Exception):
    """Raised when reverse DCF inputs are invalid."""


def _evaluate(
    financials: list[PeriodFinancials],
    base_assumptions: DCFAssumptions,
    growth_rate: Decimal,
    target_price: Decimal,
    calculated_at: datetime,
) -> DCFResult:
    candidate = base_assumptions.model_copy(
        update={"revenue_growth_rates": growth_rate},
    )
    return dcf_valuation(financials, candidate, target_price, calculated_at=calculated_at)


def reverse_dcf(
    financials: list[PeriodFinancials],
    assumptions: DCFAssumptions,
    target_price: Decimal,
    *,
    calculated_at: datetime,
    lower_bound: Decimal = Decimal("-0.50"),
    upper_bound: Decimal = Decimal("1.00"),
    growth_tolerance: Decimal = Decimal("0.0001"),
    price_tolerance: Decimal = Decimal("0.01"),
    max_iterations: int = 100,
) -> ReverseDCFResult:
    """Find the uniform revenue growth rate implied by target_price.

    Args:
        financials: Historical periods (earliest-first). At least one required.
        assumptions: DCF assumptions with all fields except revenue_growth_rates
            held constant. The revenue_growth_rates field is overridden by the solver.
        target_price: The market price (or target price) to reverse-engineer.
        lower_bound: Minimum growth rate to search.
        upper_bound: Maximum growth rate to search.
        growth_tolerance: Convergence threshold on growth rate interval width.
        price_tolerance: Convergence threshold on |implied_value - target_price|.
        max_iterations: Hard ceiling on bisection iterations.

    Returns:
        ReverseDCFResult with convergence status and the full DCF at the solution.

    Raises:
        ReverseDCFError: If inputs are structurally invalid (e.g. reversed bounds).
        DCFValidationError: If the underlying DCF engine rejects the inputs.
    """
    if lower_bound >= upper_bound:
        msg = f"lower_bound ({lower_bound}) must be less than upper_bound ({upper_bound})"
        raise ReverseDCFError(msg)

    if target_price <= Decimal("0"):
        msg = "target_price must be positive"
        raise ReverseDCFError(msg)

    audit: list[CalculationResult] = []

    lo_result = _evaluate(financials, assumptions, lower_bound, target_price, calculated_at)
    hi_result = _evaluate(financials, assumptions, upper_bound, target_price, calculated_at)

    lo_value = lo_result.implied_value_per_share
    hi_value = hi_result.implied_value_per_share

    audit.append(CalculationResult(
        metric="reverse_dcf_bounds_check",
        value=target_price,
        inputs={
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "implied_value_at_lower": lo_value,
            "implied_value_at_upper": hi_value,
            "target_price": target_price,
            "target_bracketed": str(lo_value <= target_price <= hi_value),
        },
        period="reverse_dcf",
        formula="Evaluate DCF at search bounds, verify target is bracketed",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))

    if hi_value <= lo_value:
        return _build_result(
            growth=lower_bound,
            dcf=lo_result,
            target_price=target_price,
            status=ConvergenceStatus.NO_SOLUTION_BELOW,
            iterations=0,
            growth_tolerance=growth_tolerance,
            price_tolerance=price_tolerance,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            fixed_assumptions=assumptions,
            calculated_at=calculated_at,
            audit=audit,
            notes="implied_value not monotonically increasing across bounds",
        )

    if target_price < lo_value:
        return _build_result(
            growth=lower_bound,
            dcf=lo_result,
            target_price=target_price,
            status=ConvergenceStatus.NO_SOLUTION_BELOW,
            iterations=0,
            growth_tolerance=growth_tolerance,
            price_tolerance=price_tolerance,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            fixed_assumptions=assumptions,
            calculated_at=calculated_at,
            audit=audit,
            notes=f"target_price {target_price} below minimum implied value {lo_value} at growth={lower_bound}",
        )

    if target_price > hi_value:
        return _build_result(
            growth=upper_bound,
            dcf=hi_result,
            target_price=target_price,
            status=ConvergenceStatus.NO_SOLUTION_ABOVE,
            iterations=0,
            growth_tolerance=growth_tolerance,
            price_tolerance=price_tolerance,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            fixed_assumptions=assumptions,
            calculated_at=calculated_at,
            audit=audit,
            notes=f"target_price {target_price} above maximum implied value {hi_value} at growth={upper_bound}",
        )

    lo = lower_bound
    hi = upper_bound
    mid = (lo + hi) / _TWO
    mid_result = lo_result
    iterations = 0

    for i in range(1, max_iterations + 1):
        mid = ((lo + hi) / _TWO).quantize(_RATIO_QUANTIZE)
        mid_result = _evaluate(financials, assumptions, mid, target_price, calculated_at)
        mid_value = mid_result.implied_value_per_share
        residual = mid_value - target_price
        iterations = i

        audit.append(CalculationResult(
            metric=f"reverse_dcf_iteration_{i}",
            value=mid,
            inputs={
                "lo": lo,
                "hi": hi,
                "mid": mid,
                "implied_value": mid_value,
                "residual": residual,
                "interval_width": hi - lo,
            },
            period="reverse_dcf",
            formula="bisect: mid = (lo + hi) / 2, evaluate dcf_valuation(mid)",
            version=ENGINE_VERSION,
            unit="ratio",
        ))

        growth_converged = abs(hi - lo) <= growth_tolerance
        price_converged = abs(residual) <= price_tolerance

        if growth_converged and price_converged:
            return _build_result(
                growth=mid,
                dcf=mid_result,
                target_price=target_price,
                status=ConvergenceStatus.CONVERGED,
                iterations=iterations,
                growth_tolerance=growth_tolerance,
                price_tolerance=price_tolerance,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                fixed_assumptions=assumptions,
                calculated_at=calculated_at,
                audit=audit,
            )

        if mid_value < target_price:
            lo = mid
        else:
            hi = mid

    return _build_result(
        growth=mid,
        dcf=mid_result,
        target_price=target_price,
        status=ConvergenceStatus.MAX_ITERATIONS,
        iterations=iterations,
        growth_tolerance=growth_tolerance,
        price_tolerance=price_tolerance,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        fixed_assumptions=assumptions,
        calculated_at=calculated_at,
        audit=audit,
        notes=f"did not converge after {max_iterations} iterations",
    )


def _build_result(
    *,
    growth: Decimal,
    dcf: DCFResult,
    target_price: Decimal,
    status: ConvergenceStatus,
    iterations: int,
    growth_tolerance: Decimal,
    price_tolerance: Decimal,
    lower_bound: Decimal,
    upper_bound: Decimal,
    fixed_assumptions: DCFAssumptions,
    calculated_at: datetime,
    audit: list[CalculationResult],
    notes: str | None = None,
) -> ReverseDCFResult:
    implied_value = dcf.implied_value_per_share
    residual = implied_value - target_price

    audit.append(CalculationResult(
        metric="reverse_dcf_result",
        value=growth,
        inputs={
            "implied_growth_rate": growth,
            "target_price": target_price,
            "implied_value_at_solution": implied_value,
            "residual": residual,
            "convergence_status": status.value,
            "iterations": iterations,
        },
        period="reverse_dcf",
        formula="bisection root-finding: f(g) = dcf_valuation(g).implied_value - target_price = 0",
        version=ENGINE_VERSION,
        unit="ratio",
        notes=notes,
    ))

    return ReverseDCFResult(
        implied_growth_rate=growth,
        target_price=target_price,
        implied_value_at_solution=implied_value,
        residual=residual,
        enterprise_value=dcf.enterprise_value,
        equity_value=dcf.equity_value,
        convergence_status=status,
        iterations=iterations,
        growth_rate_tolerance=growth_tolerance,
        price_tolerance=price_tolerance,
        search_lower_bound=lower_bound,
        search_upper_bound=upper_bound,
        fixed_assumptions=fixed_assumptions,
        dcf_result=dcf,
        calculations=audit,
        calculated_at=calculated_at,
        engine_version=ENGINE_VERSION,
    )
