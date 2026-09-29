"""DCF Valuation Engine — orchestrates the full valuation pipeline.

dcf_valuation() is a pure function: no database, no providers, no HTTP,
no LLM calls. It accepts typed inputs and produces a fully auditable
DCFResult with all intermediate calculations.

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult, PeriodFinancials
from app.valuation.models import DCFAssumptions, DCFResult
from app.valuation.projector import project_fcf
from app.valuation.sensitivity import build_sensitivity_matrix
from app.valuation.terminal import TerminalValueError, compute_terminal_value
from app.valuation.wacc import compute_wacc

ENGINE_VERSION = "1.0.0"
_CURRENCY_QUANTIZE = Decimal("0.0001")


class DCFValidationError(Exception):
    """Raised when DCF inputs fail validation."""


def dcf_valuation(
    financials: list[PeriodFinancials],
    assumptions: DCFAssumptions,
    current_price: Decimal,
) -> DCFResult:
    """Compute a deterministic DCF valuation for one explicit assumption set.

    Args:
        financials: Historical period data (earliest-first). At least one
            period is required to derive base revenue.
        assumptions: All configurable DCF inputs — no hidden defaults.
        current_price: Current market price per share for upside/downside.

    Returns:
        DCFResult with all intermediate calculations recorded.

    Raises:
        DCFValidationError: If inputs are invalid.
        TerminalValueError: If terminal value cannot be computed
            (e.g. WACC <= terminal growth for Gordon Growth).
    """
    if not financials:
        msg = "at least one period of historical financials is required"
        raise DCFValidationError(msg)

    if current_price <= Decimal("0"):
        msg = "current_price must be positive"
        raise DCFValidationError(msg)

    latest = financials[-1]
    if latest.revenue is None or latest.revenue <= Decimal("0"):
        msg = "latest period must have positive revenue for DCF projection"
        raise DCFValidationError(msg)

    audit: list[CalculationResult] = []

    # --- Step 1: Resolve WACC ---
    if assumptions.wacc is not None:
        wacc = assumptions.wacc
        audit.append(CalculationResult(
            metric="wacc",
            value=wacc,
            inputs={"wacc": wacc},
            period="assumption",
            formula="directly provided",
            version=ENGINE_VERSION,
            unit="ratio",
        ))
    else:
        assert assumptions.wacc_components is not None
        wacc, wacc_calcs = compute_wacc(assumptions.wacc_components, assumptions.tax_rate)
        audit.extend(wacc_calcs)

    # --- Step 2: Validate WACC vs terminal growth for Gordon Growth ---
    if assumptions.terminal_method.value == "gordon_growth" and wacc <= assumptions.terminal_growth_rate:
            msg = (
                f"WACC ({wacc}) must be greater than terminal_growth_rate "
                f"({assumptions.terminal_growth_rate}) for Gordon Growth Model"
            )
            raise TerminalValueError(msg)

    # --- Step 3: Project FCFs ---
    base_revenue = latest.revenue
    projected_years, projection_calcs = project_fcf(base_revenue, assumptions, wacc)
    audit.extend(projection_calcs)

    # --- Step 4: Terminal Value ---
    final_year = projected_years[-1]
    tv_result, tv_calcs = compute_terminal_value(
        final_year=final_year,
        wacc=wacc,
        terminal_growth_rate=assumptions.terminal_growth_rate,
        terminal_method=assumptions.terminal_method,
        exit_multiple=assumptions.exit_multiple,
        projection_years=assumptions.projection_years,
    )
    audit.extend(tv_calcs)

    # --- Step 5: Enterprise Value ---
    sum_pv_fcf = sum((y.pv_fcf for y in projected_years), Decimal("0"))
    enterprise_value = (sum_pv_fcf + tv_result.pv_terminal_value).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    audit.append(CalculationResult(
        metric="enterprise_value",
        value=enterprise_value,
        inputs={
            "sum_pv_fcf": sum_pv_fcf,
            "pv_terminal_value": tv_result.pv_terminal_value,
        },
        period="valuation",
        formula="Σ PV(FCF) + PV(TV)",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    # --- Step 6: Equity Value ---
    equity_value = (enterprise_value - assumptions.net_debt).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="equity_value",
        value=equity_value,
        inputs={
            "enterprise_value": enterprise_value,
            "net_debt": assumptions.net_debt,
        },
        period="valuation",
        formula="EV - Net Debt",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    # --- Step 7: Value Per Share ---
    implied_value = (equity_value / assumptions.shares_outstanding).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_value_per_share",
        value=implied_value,
        inputs={
            "equity_value": equity_value,
            "shares_outstanding": assumptions.shares_outstanding,
        },
        period="valuation",
        formula="Equity Value / Shares Outstanding",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))

    # --- Step 8: Upside/Downside ---
    upside_downside = (
        (implied_value - current_price) / current_price
    ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    audit.append(CalculationResult(
        metric="upside_downside_pct",
        value=upside_downside,
        inputs={
            "implied_value_per_share": implied_value,
            "current_price": current_price,
        },
        period="valuation",
        formula="(Implied - Current) / Current",
        version=ENGINE_VERSION,
        unit="ratio",
    ))

    # --- Step 9: Sensitivity Matrix ---
    sensitivity = build_sensitivity_matrix(projected_years, assumptions, wacc)

    return DCFResult(
        assumptions=assumptions,
        wacc_used=wacc,
        projected_years=projected_years,
        terminal_value=tv_result,
        sum_pv_fcf=sum_pv_fcf,
        enterprise_value=enterprise_value,
        net_debt=assumptions.net_debt,
        equity_value=equity_value,
        shares_outstanding=assumptions.shares_outstanding,
        implied_value_per_share=implied_value,
        current_price=current_price,
        upside_downside_pct=upside_downside,
        sensitivity=sensitivity,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
    )
