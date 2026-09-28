"""Financial Analytics Engine — orchestrates all metric calculations.

Takes a chronologically sorted list of PeriodFinancials and produces
a complete AnalyticsReport with all applicable metrics.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.analytics import (
    cashflow,
    efficiency,
    growth,
    leverage,
    margins,
    quality,
    returns,
)
from app.analytics.models import AnalyticsReport, CalculationResult, PeriodFinancials


def compute_all(
    symbol: str,
    exchange: str,
    periods: list[PeriodFinancials],
) -> AnalyticsReport:
    """Run all analytics on the provided periods (earliest-first order)."""
    if not periods:
        return AnalyticsReport(
            symbol=symbol,
            exchange=exchange,
            calculations=[],
            periods_analyzed=[],
            generated_at=datetime.now(UTC),
        )

    results: list[CalculationResult] = []
    latest = periods[-1]

    # --- Profitability Margins (latest period) ---
    results.append(margins.gross_margin(latest))
    results.append(margins.ebitda_margin(latest))
    results.append(margins.ebit_margin(latest))
    results.append(margins.net_margin(latest))

    # --- Leverage (latest period) ---
    results.append(leverage.debt_to_equity(latest))
    results.append(leverage.net_debt_to_ebitda(latest))
    results.append(leverage.interest_coverage(latest))
    results.append(leverage.current_ratio(latest))

    # --- Cash Flow (latest period) ---
    results.append(cashflow.operating_cash_flow(latest))
    results.append(cashflow.free_cash_flow(latest))
    results.append(cashflow.cfo_to_pat(latest))
    results.append(cashflow.fcf_to_pat(latest))
    results.append(cashflow.capex_to_revenue(latest))

    # --- Efficiency (latest period) ---
    results.append(efficiency.working_capital(latest))
    results.append(efficiency.receivable_days(latest))
    results.append(efficiency.inventory_days(latest))
    results.append(efficiency.payable_days(latest))
    results.append(efficiency.cash_conversion_cycle(latest))

    if len(periods) >= 2:
        earliest = periods[0]
        prev = periods[-2]
        years = len(periods) - 1

        # --- Growth (earliest → latest) ---
        results.append(growth.revenue_cagr(earliest, latest, years))
        results.append(growth.ebitda_cagr(earliest, latest, years))
        results.append(growth.ebit_cagr(earliest, latest, years))
        results.append(growth.pat_cagr(earliest, latest, years))
        results.append(growth.eps_cagr(earliest, latest, years))

        # --- Returns (latest vs previous) ---
        results.append(returns.roe(latest, prev))
        results.append(returns.roce(latest, prev))
        results.append(returns.roic(latest, prev))

        # --- Quality ---
        results.append(
            quality.return_on_incremental_capital(latest, prev),
        )
        results.append(quality.earnings_consistency(periods))

    return AnalyticsReport(
        symbol=symbol,
        exchange=exchange,
        calculations=results,
        periods_analyzed=[p.period for p in periods],
        generated_at=datetime.now(UTC),
    )
