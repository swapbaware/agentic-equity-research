"""WACC × terminal-growth sensitivity analysis.

Generates a grid of implied values per share by varying WACC and
terminal growth rate around the base assumptions.

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING
from app.valuation.models import DCFAssumptions, ProjectedYear, SensitivityCell, TerminalMethod

VERSION = "1.0.0"
_ONE = Decimal("1")
_CURRENCY_QUANTIZE = Decimal("0.0001")
_STEP = Decimal("0.01")
_STEPS = 3


def _implied_value(
    projected: list[ProjectedYear],
    wacc: Decimal,
    terminal_growth: Decimal,
    terminal_method: TerminalMethod,
    exit_multiple: Decimal | None,
    projection_years: int,
    net_debt: Decimal,
    shares: Decimal,
) -> Decimal | None:
    """Compute implied value per share for one (WACC, terminal_growth) pair."""
    if terminal_method == TerminalMethod.GORDON_GROWTH:
        spread = wacc - terminal_growth
        if spread <= Decimal("0"):
            return None
        terminal_fcf = projected[-1].fcf * (_ONE + terminal_growth)
        undiscounted_tv = terminal_fcf / spread
    else:
        if exit_multiple is None:
            return None
        terminal_ebitda = projected[-1].ebit + projected[-1].depreciation_amortization
        undiscounted_tv = terminal_ebitda * exit_multiple

    sum_pv = Decimal("0")
    for yr in projected:
        df = _ONE / (_ONE + wacc) ** yr.year
        sum_pv += yr.fcf * df

    tv_df = _ONE / (_ONE + wacc) ** projection_years
    pv_tv = undiscounted_tv * tv_df

    ev = sum_pv + pv_tv
    equity = ev - net_debt
    return (equity / shares).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)


def build_sensitivity_matrix(
    projected: list[ProjectedYear],
    assumptions: DCFAssumptions,
    base_wacc: Decimal,
) -> list[SensitivityCell]:
    """Build a WACC × terminal-growth sensitivity grid.

    Varies each dimension by ±3 steps of 1 percentage point around the base.
    """
    cells: list[SensitivityCell] = []

    wacc_values = [
        (base_wacc + _STEP * Decimal(str(offset))).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
        for offset in range(-_STEPS, _STEPS + 1)
    ]
    tg_values = [
        (assumptions.terminal_growth_rate + _STEP * Decimal(str(offset))).quantize(
            RATIO_QUANTIZE, rounding=ROUNDING,
        )
        for offset in range(-_STEPS, _STEPS + 1)
    ]

    for w in wacc_values:
        for tg in tg_values:
            value = _implied_value(
                projected=projected,
                wacc=w,
                terminal_growth=tg,
                terminal_method=assumptions.terminal_method,
                exit_multiple=assumptions.exit_multiple,
                projection_years=assumptions.projection_years,
                net_debt=assumptions.net_debt,
                shares=assumptions.shares_outstanding,
            )
            cells.append(SensitivityCell(
                wacc=w,
                terminal_growth_rate=tg,
                implied_value_per_share=value,
            ))

    return cells
