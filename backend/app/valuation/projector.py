"""Year-by-year Free Cash Flow projection.

Revenue[t] = Revenue[t-1] × (1 + growth_rate[t])
EBIT[t]    = Revenue[t] × EBIT margin[t]
NOPAT[t]   = EBIT[t] × (1 - tax_rate)
D&A[t]     = Revenue[t] × D&A %[t]
CapEx[t]   = Revenue[t] × CapEx %[t]
ΔNWC[t]    = (Revenue[t] - Revenue[t-1]) × NWC %
FCF[t]     = NOPAT[t] + D&A[t] - CapEx[t] - ΔNWC[t]

All arithmetic uses decimal.Decimal.
"""
from __future__ import annotations

from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult
from app.valuation.models import DCFAssumptions, ProjectedYear

VERSION = "1.0.0"
_ONE = Decimal("1")
_CURRENCY_QUANTIZE = Decimal("0.0001")


def _get_year_value(
    field: Decimal | list[Decimal],
    year_index: int,
) -> Decimal:
    """Extract the value for a specific projection year."""
    if isinstance(field, list):
        return field[year_index]
    return field


def project_fcf(
    base_revenue: Decimal,
    assumptions: DCFAssumptions,
    wacc: Decimal,
) -> tuple[list[ProjectedYear], list[CalculationResult]]:
    """Project free cash flows for each year of the projection period.

    Returns (projected_years, audit_trail).
    """
    results: list[CalculationResult] = []
    projected: list[ProjectedYear] = []
    prev_revenue = base_revenue

    for i in range(assumptions.projection_years):
        year_num = i + 1
        period = f"Y{year_num}"

        growth = _get_year_value(assumptions.revenue_growth_rates, i)
        margin = _get_year_value(assumptions.ebit_margin, i)
        da_pct = _get_year_value(assumptions.da_pct_revenue, i)
        capex_pct = _get_year_value(assumptions.capex_pct_revenue, i)

        revenue = (prev_revenue * (_ONE + growth)).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )
        ebit = (revenue * margin).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
        nopat = (ebit * (_ONE - assumptions.tax_rate)).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )
        da = (revenue * da_pct).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
        capex = (revenue * capex_pct).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
        delta_revenue = revenue - prev_revenue
        nwc_change = (delta_revenue * assumptions.nwc_pct_revenue_change).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        )
        fcf = nopat + da - capex - nwc_change

        discount_factor = (_ONE / (_ONE + wacc) ** year_num).quantize(
            RATIO_QUANTIZE, rounding=ROUNDING,
        )
        pv_fcf = (fcf * discount_factor).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)

        projected.append(ProjectedYear(
            year=year_num,
            revenue=revenue,
            ebit=ebit,
            nopat=nopat,
            depreciation_amortization=da,
            capex=capex,
            nwc_change=nwc_change,
            fcf=fcf,
            discount_factor=discount_factor,
            pv_fcf=pv_fcf,
        ))

        results.append(CalculationResult(
            metric=f"projected_fcf_{period}",
            value=fcf,
            inputs={
                "prior_revenue": prev_revenue,
                "revenue_growth": growth,
                "revenue": revenue,
                "ebit_margin": margin,
                "ebit": ebit,
                "tax_rate": assumptions.tax_rate,
                "nopat": nopat,
                "da_pct_revenue": da_pct,
                "depreciation_amortization": da,
                "capex_pct_revenue": capex_pct,
                "capex": capex,
                "nwc_pct_revenue_change": assumptions.nwc_pct_revenue_change,
                "nwc_change": nwc_change,
            },
            period=period,
            formula="NOPAT + D&A - CapEx - ΔNWC where NOPAT = EBIT × (1 - tax)",
            version=VERSION,
            unit="currency",
        ))

        results.append(CalculationResult(
            metric=f"pv_fcf_{period}",
            value=pv_fcf,
            inputs={"fcf": fcf, "wacc": wacc, "year": year_num, "discount_factor": discount_factor},
            period=period,
            formula="FCF / (1 + WACC) ^ year",
            version=VERSION,
            unit="currency",
        ))

        prev_revenue = revenue

    return projected, results
