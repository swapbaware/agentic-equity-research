"""Multiple-Based Valuation Engine — seven deterministic methods.

All calculations use decimal.Decimal, never float. Every intermediate step
records its inputs, formula, period, and calculation version via CalculationResult.

Methods:
    pe_valuation        — P/E (equity-based)
    ev_ebitda_valuation — EV/EBITDA (enterprise-based)
    ps_valuation        — P/S (equity-based)
    pb_valuation        — P/B (equity-based)
    peg_valuation       — PEG (equity-based)
    fcf_yield_valuation — FCF Yield (equity-based, equity FCF = CFO − CapEx)
    ev_fcf_valuation    — EV/FCF (enterprise-based, FCFF = NOPAT + D&A − CapEx − ΔNWC)
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.analytics.models import RATIO_QUANTIZE, ROUNDING, CalculationResult, PeriodFinancials
from app.valuation.models import (
    CashFlowBasis,
    MultipleValuationResult,
    ValuationMethodType,
)

ENGINE_VERSION = "1.0.0"
_CURRENCY_QUANTIZE = Decimal("0.0001")
_ONE = Decimal("1")
_ZERO = Decimal("0")


class MultipleValuationError(Exception):
    """Raised when multiple-based valuation inputs are invalid."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _require_positive(
    value: Decimal | None,
    field_name: str,
) -> Decimal:
    if value is None:
        msg = f"{field_name} is required but missing"
        raise MultipleValuationError(msg)
    if value <= _ZERO:
        msg = f"{field_name} must be positive, got {value}"
        raise MultipleValuationError(msg)
    return value


def _require_present(
    value: Decimal | None,
    field_name: str,
) -> Decimal:
    if value is None:
        msg = f"{field_name} is required but missing"
        raise MultipleValuationError(msg)
    return value


def _derive_net_debt(
    total_debt: Decimal | None,
    cash_and_equivalents: Decimal | None,
    audit: list[CalculationResult],
    period: str,
) -> Decimal:
    debt = _require_present(total_debt, "total_debt")
    cash = _require_present(cash_and_equivalents, "cash_and_equivalents")
    net_debt = (debt - cash).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)
    audit.append(CalculationResult(
        metric="net_debt",
        value=net_debt,
        inputs={"total_debt": debt, "cash_and_equivalents": cash},
        period=period,
        formula="Total Debt − Cash and Equivalents",
        version=ENGINE_VERSION,
        unit="currency",
    ))
    return net_debt


def _compute_upside(
    implied_value: Decimal,
    current_price: Decimal | None,
    audit: list[CalculationResult],
    period: str,
) -> Decimal | None:
    if current_price is None:
        return None
    if current_price <= _ZERO:
        msg = f"current_price must be positive, got {current_price}"
        raise MultipleValuationError(msg)
    upside = (
        (implied_value - current_price) / current_price
    ).quantize(RATIO_QUANTIZE, rounding=ROUNDING)
    audit.append(CalculationResult(
        metric="upside_downside_pct",
        value=upside,
        inputs={
            "implied_value_per_share": implied_value,
            "current_price": current_price,
        },
        period=period,
        formula="(Implied − Current) / Current",
        version=ENGINE_VERSION,
        unit="ratio",
    ))
    return upside


def _ev_to_per_share(
    implied_ev: Decimal,
    net_debt: Decimal,
    shares: Decimal,
    audit: list[CalculationResult],
    period: str,
) -> tuple[Decimal, Decimal]:
    equity_value = (implied_ev - net_debt).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_equity_value",
        value=equity_value,
        inputs={"implied_enterprise_value": implied_ev, "net_debt": net_debt},
        period=period,
        formula="Implied EV − Net Debt",
        version=ENGINE_VERSION,
        unit="currency",
    ))
    value_per_share = (equity_value / shares).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_value_per_share",
        value=value_per_share,
        inputs={"implied_equity_value": equity_value, "shares_outstanding": shares},
        period=period,
        formula="Implied Equity Value / Shares Outstanding",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))
    return equity_value, value_per_share


def _equity_to_per_share(
    equity_value: Decimal,
    shares: Decimal,
    audit: list[CalculationResult],
    period: str,
) -> Decimal:
    value_per_share = (equity_value / shares).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_value_per_share",
        value=value_per_share,
        inputs={"implied_equity_value": equity_value, "shares_outstanding": shares},
        period=period,
        formula="Implied Equity Value / Shares Outstanding",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))
    return value_per_share


# ---------------------------------------------------------------------------
# 1. P/E Valuation
# ---------------------------------------------------------------------------


def pe_valuation(
    financials: PeriodFinancials,
    target_pe: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Implied value per share = EPS × Target P/E."""
    eps = _require_positive(financials.eps, "eps")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_pe, "target_pe")

    audit: list[CalculationResult] = []
    period = financials.period

    implied_value = (eps * target_pe).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_value_per_share",
        value=implied_value,
        inputs={"eps": eps, "target_pe": target_pe},
        period=period,
        formula="EPS × Target P/E",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))

    upside = _compute_upside(implied_value, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.PE,
        input_metric_name="eps",
        input_metric_value=eps,
        target_name="target_pe",
        target_value=target_pe,
        implied_enterprise_value=None,
        net_debt=None,
        implied_equity_value=(implied_value * shares).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        ),
        shares_outstanding=shares,
        implied_value_per_share=implied_value,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=None,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 2. EV/EBITDA Valuation
# ---------------------------------------------------------------------------


def ev_ebitda_valuation(
    financials: PeriodFinancials,
    target_ev_ebitda: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Implied EV = EBITDA × Target EV/EBITDA, then EV → equity → per share."""
    ebitda = _require_positive(financials.ebitda, "ebitda")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_ev_ebitda, "target_ev_ebitda")

    audit: list[CalculationResult] = []
    period = financials.period

    net_debt = _derive_net_debt(
        financials.total_debt, financials.cash_and_equivalents, audit, period,
    )

    implied_ev = (ebitda * target_ev_ebitda).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_enterprise_value",
        value=implied_ev,
        inputs={"ebitda": ebitda, "target_ev_ebitda": target_ev_ebitda},
        period=period,
        formula="EBITDA × Target EV/EBITDA",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    equity_value, value_per_share = _ev_to_per_share(
        implied_ev, net_debt, shares, audit, period,
    )

    upside = _compute_upside(value_per_share, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.EV_EBITDA,
        input_metric_name="ebitda",
        input_metric_value=ebitda,
        target_name="target_ev_ebitda",
        target_value=target_ev_ebitda,
        implied_enterprise_value=implied_ev,
        net_debt=net_debt,
        implied_equity_value=equity_value,
        shares_outstanding=shares,
        implied_value_per_share=value_per_share,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=None,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 3. P/S Valuation
# ---------------------------------------------------------------------------


def ps_valuation(
    financials: PeriodFinancials,
    target_ps: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Implied equity value = Revenue × Target P/S, then per share."""
    revenue = _require_positive(financials.revenue, "revenue")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_ps, "target_ps")

    audit: list[CalculationResult] = []
    period = financials.period

    implied_equity = (revenue * target_ps).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_equity_value",
        value=implied_equity,
        inputs={"revenue": revenue, "target_ps": target_ps},
        period=period,
        formula="Revenue × Target P/S",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    value_per_share = _equity_to_per_share(implied_equity, shares, audit, period)
    upside = _compute_upside(value_per_share, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.PS,
        input_metric_name="revenue",
        input_metric_value=revenue,
        target_name="target_ps",
        target_value=target_ps,
        implied_enterprise_value=None,
        net_debt=None,
        implied_equity_value=implied_equity,
        shares_outstanding=shares,
        implied_value_per_share=value_per_share,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=None,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 4. P/B Valuation
# ---------------------------------------------------------------------------


def pb_valuation(
    financials: PeriodFinancials,
    target_pb: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Implied equity value = Book Value (total_equity) × Target P/B, then per share."""
    book_value = _require_positive(financials.total_equity, "total_equity")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_pb, "target_pb")

    audit: list[CalculationResult] = []
    period = financials.period

    implied_equity = (book_value * target_pb).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_equity_value",
        value=implied_equity,
        inputs={"total_equity": book_value, "target_pb": target_pb},
        period=period,
        formula="Book Value (Total Equity) × Target P/B",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    value_per_share = _equity_to_per_share(implied_equity, shares, audit, period)
    upside = _compute_upside(value_per_share, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.PB,
        input_metric_name="total_equity",
        input_metric_value=book_value,
        target_name="target_pb",
        target_value=target_pb,
        implied_enterprise_value=None,
        net_debt=None,
        implied_equity_value=implied_equity,
        shares_outstanding=shares,
        implied_value_per_share=value_per_share,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=None,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 5. PEG Valuation
# ---------------------------------------------------------------------------


def peg_valuation(
    financials: PeriodFinancials,
    target_peg: Decimal,
    earnings_growth_pct: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Implied P/E = PEG × Growth%, Implied Value = EPS × Implied P/E.

    earnings_growth_pct is in percentage points (15 means 15%, not 0.15).
    """
    eps = _require_positive(financials.eps, "eps")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_peg, "target_peg")
    _require_positive(earnings_growth_pct, "earnings_growth_pct")

    audit: list[CalculationResult] = []
    period = financials.period

    implied_pe = (target_peg * earnings_growth_pct).quantize(
        RATIO_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_pe",
        value=implied_pe,
        inputs={
            "target_peg": target_peg,
            "earnings_growth_pct": earnings_growth_pct,
        },
        period=period,
        formula="PEG × Earnings Growth %",
        version=ENGINE_VERSION,
        unit="multiple",
    ))

    implied_value = (eps * implied_pe).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_value_per_share",
        value=implied_value,
        inputs={"eps": eps, "implied_pe": implied_pe},
        period=period,
        formula="EPS × Implied P/E",
        version=ENGINE_VERSION,
        unit="currency_per_share",
    ))

    upside = _compute_upside(implied_value, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.PEG,
        input_metric_name="eps",
        input_metric_value=eps,
        target_name="target_peg",
        target_value=target_peg,
        implied_enterprise_value=None,
        net_debt=None,
        implied_equity_value=(implied_value * shares).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUNDING,
        ),
        shares_outstanding=shares,
        implied_value_per_share=implied_value,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=earnings_growth_pct,
        implied_pe=implied_pe,
        cash_flow_basis=None,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 6. FCF Yield Valuation
# ---------------------------------------------------------------------------


def fcf_yield_valuation(
    financials: PeriodFinancials,
    target_fcf_yield: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """Equity FCF = CFO − CapEx. Implied Market Cap = Equity FCF / Target Yield."""
    cfo = _require_present(financials.cfo, "cfo")
    capex = _require_present(financials.capex, "capex")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_fcf_yield, "target_fcf_yield")

    equity_fcf = (cfo - capex).quantize(_CURRENCY_QUANTIZE, rounding=ROUNDING)

    audit: list[CalculationResult] = []
    period = financials.period

    audit.append(CalculationResult(
        metric="equity_fcf",
        value=equity_fcf,
        inputs={"cfo": cfo, "capex": capex},
        period=period,
        formula="CFO − CapEx",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    if equity_fcf <= _ZERO:
        msg = f"equity FCF must be positive for FCF Yield valuation, got {equity_fcf}"
        raise MultipleValuationError(msg)

    implied_market_cap = (equity_fcf / target_fcf_yield).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_market_cap",
        value=implied_market_cap,
        inputs={"equity_fcf": equity_fcf, "target_fcf_yield": target_fcf_yield},
        period=period,
        formula="Equity FCF / Target FCF Yield",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    value_per_share = _equity_to_per_share(implied_market_cap, shares, audit, period)
    upside = _compute_upside(value_per_share, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.FCF_YIELD,
        input_metric_name="equity_fcf",
        input_metric_value=equity_fcf,
        target_name="target_fcf_yield",
        target_value=target_fcf_yield,
        implied_enterprise_value=None,
        net_debt=None,
        implied_equity_value=implied_market_cap,
        shares_outstanding=shares,
        implied_value_per_share=value_per_share,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=CashFlowBasis.EQUITY_FCF,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )


# ---------------------------------------------------------------------------
# 7. EV/FCF Valuation (FCFF-based)
# ---------------------------------------------------------------------------


def ev_fcf_valuation(
    financials: PeriodFinancials,
    prior_financials: PeriodFinancials,
    target_ev_fcf: Decimal,
    current_price: Decimal | None = None,
) -> MultipleValuationResult:
    """EV/FCF using FCFF = EBIT×(1−t) + D&A − CapEx − ΔNWC.

    Requires two periods to derive ΔNWC deterministically.
    """
    ebit = _require_present(financials.ebit, "ebit")
    da = _require_present(financials.depreciation_amortization, "depreciation_amortization")
    capex = _require_present(financials.capex, "capex")
    tax_rate = _require_present(financials.effective_tax_rate, "effective_tax_rate")
    cur_ca = _require_present(financials.current_assets, "current_assets")
    cur_cl = _require_present(financials.current_liabilities, "current_liabilities")
    shares = _require_positive(financials.shares_outstanding, "shares_outstanding")
    _require_positive(target_ev_fcf, "target_ev_fcf")

    prior_ca = _require_present(prior_financials.current_assets, "prior current_assets")
    prior_cl = _require_present(prior_financials.current_liabilities, "prior current_liabilities")

    audit: list[CalculationResult] = []
    period = financials.period

    nwc_current = cur_ca - cur_cl
    nwc_prior = prior_ca - prior_cl
    delta_nwc = (nwc_current - nwc_prior).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )

    audit.append(CalculationResult(
        metric="nwc_current",
        value=nwc_current,
        inputs={"current_assets": cur_ca, "current_liabilities": cur_cl},
        period=period,
        formula="Current Assets − Current Liabilities",
        version=ENGINE_VERSION,
        unit="currency",
    ))
    audit.append(CalculationResult(
        metric="nwc_prior",
        value=nwc_prior,
        inputs={
            "prior_current_assets": prior_ca,
            "prior_current_liabilities": prior_cl,
        },
        period=prior_financials.period,
        formula="Current Assets − Current Liabilities",
        version=ENGINE_VERSION,
        unit="currency",
    ))
    audit.append(CalculationResult(
        metric="delta_nwc",
        value=delta_nwc,
        inputs={"nwc_current": nwc_current, "nwc_prior": nwc_prior},
        period=period,
        formula="NWC Current − NWC Prior",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    nopat = (ebit * (_ONE - tax_rate)).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="nopat",
        value=nopat,
        inputs={"ebit": ebit, "effective_tax_rate": tax_rate},
        period=period,
        formula="EBIT × (1 − Tax Rate)",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    fcff = (nopat + da - capex - delta_nwc).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="fcff",
        value=fcff,
        inputs={
            "nopat": nopat,
            "depreciation_amortization": da,
            "capex": capex,
            "delta_nwc": delta_nwc,
        },
        period=period,
        formula="NOPAT + D&A − CapEx − ΔNWC",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    if fcff <= _ZERO:
        msg = f"FCFF must be positive for EV/FCF valuation, got {fcff}"
        raise MultipleValuationError(msg)

    net_debt = _derive_net_debt(
        financials.total_debt, financials.cash_and_equivalents, audit, period,
    )

    implied_ev = (fcff * target_ev_fcf).quantize(
        _CURRENCY_QUANTIZE, rounding=ROUNDING,
    )
    audit.append(CalculationResult(
        metric="implied_enterprise_value",
        value=implied_ev,
        inputs={"fcff": fcff, "target_ev_fcf": target_ev_fcf},
        period=period,
        formula="FCFF × Target EV/FCF",
        version=ENGINE_VERSION,
        unit="currency",
    ))

    equity_value, value_per_share = _ev_to_per_share(
        implied_ev, net_debt, shares, audit, period,
    )

    upside = _compute_upside(value_per_share, current_price, audit, period)

    return MultipleValuationResult(
        method=ValuationMethodType.EV_FCF,
        input_metric_name="fcff",
        input_metric_value=fcff,
        target_name="target_ev_fcf",
        target_value=target_ev_fcf,
        implied_enterprise_value=implied_ev,
        net_debt=net_debt,
        implied_equity_value=equity_value,
        shares_outstanding=shares,
        implied_value_per_share=value_per_share,
        current_price=current_price,
        upside_downside_pct=upside,
        earnings_growth_pct=None,
        implied_pe=None,
        cash_flow_basis=CashFlowBasis.FCFF,
        calculations=audit,
        calculated_at=datetime.now(UTC),
        engine_version=ENGINE_VERSION,
        period=period,
    )
