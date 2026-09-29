"""Terminal value calculation.

Gordon Growth: TV = FCF_n × (1 + g) / (WACC - g)
Exit Multiple: TV = EBITDA_n × exit_multiple

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation.models import ProjectedYear, TerminalMethod, TerminalValueResult

VERSION = "1.0.0"
_ONE = Decimal("1")
_CURRENCY_QUANTIZE = Decimal("0.0001")


class TerminalValueError(Exception):
    """Raised when terminal value cannot be computed."""


def compute_terminal_value(
    final_year: ProjectedYear,
    wacc: Decimal,
    terminal_growth_rate: Decimal,
    terminal_method: TerminalMethod,
    exit_multiple: Decimal | None,
    projection_years: int,
) -> tuple[TerminalValueResult, list[CalculationResult]]:
    """Compute terminal value using the specified method.

    Raises TerminalValueError if WACC <= terminal_growth_rate for Gordon Growth.
    """
    results: list[CalculationResult] = []

    if terminal_method == TerminalMethod.GORDON_GROWTH:
        spread = wacc - terminal_growth_rate
        if spread <= Decimal("0"):
            msg = (
                f"WACC ({wacc}) must be greater than terminal_growth_rate "
                f"({terminal_growth_rate}) for Gordon Growth Model"
            )
            raise TerminalValueError(msg)

        terminal_fcf = (final_year.fcf * (_ONE + terminal_growth_rate)).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )
        undiscounted_tv = (terminal_fcf / spread).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )

        results.append(CalculationResult(
            metric="terminal_value_gordon",
            value=undiscounted_tv,
            inputs={
                "final_year_fcf": final_year.fcf,
                "terminal_growth_rate": terminal_growth_rate,
                "terminal_fcf": terminal_fcf,
                "wacc": wacc,
                "spread": spread,
            },
            period=f"terminal_Y{projection_years}",
            formula="FCF_n × (1 + g) / (WACC - g)",
            version=VERSION,
            unit="currency",
        ))

        tv_result = TerminalValueResult(
            method=TerminalMethod.GORDON_GROWTH,
            terminal_fcf=terminal_fcf,
            terminal_growth_rate=terminal_growth_rate,
            undiscounted_terminal_value=undiscounted_tv,
            discount_factor=Decimal("0"),
            pv_terminal_value=Decimal("0"),
        )

    else:
        if exit_multiple is None:
            msg = "exit_multiple is required for Exit Multiple method"
            raise TerminalValueError(msg)

        terminal_ebitda = (
            final_year.ebit + final_year.depreciation_amortization
        )
        undiscounted_tv = (terminal_ebitda * exit_multiple).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )

        results.append(CalculationResult(
            metric="terminal_value_exit_multiple",
            value=undiscounted_tv,
            inputs={
                "final_year_ebit": final_year.ebit,
                "final_year_da": final_year.depreciation_amortization,
                "terminal_ebitda": terminal_ebitda,
                "exit_multiple": exit_multiple,
            },
            period=f"terminal_Y{projection_years}",
            formula="EBITDA_n × exit_multiple",
            version=VERSION,
            unit="currency",
        ))

        tv_result = TerminalValueResult(
            method=TerminalMethod.EXIT_MULTIPLE,
            terminal_ebitda=terminal_ebitda,
            terminal_growth_rate=terminal_growth_rate,
            exit_multiple_used=exit_multiple,
            undiscounted_terminal_value=undiscounted_tv,
            discount_factor=Decimal("0"),
            pv_terminal_value=Decimal("0"),
        )

    discount_factor = (_ONE / (_ONE + wacc) ** projection_years).quantize(
        RATIO_QUANTIZE, rounding=ROUNDING,
    )
    pv_tv = (undiscounted_tv * discount_factor).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    results.append(CalculationResult(
        metric="pv_terminal_value",
        value=pv_tv,
        inputs={
            "undiscounted_terminal_value": undiscounted_tv,
            "wacc": wacc,
            "projection_years": projection_years,
            "discount_factor": discount_factor,
        },
        period=f"terminal_Y{projection_years}",
        formula="TV / (1 + WACC) ^ n",
        version=VERSION,
        unit="currency",
    ))

    tv_result = tv_result.model_copy(update={
        "discount_factor": discount_factor,
        "pv_terminal_value": pv_tv,
    })

    return tv_result, results
