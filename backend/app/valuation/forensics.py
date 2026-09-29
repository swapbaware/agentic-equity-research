"""Financial Forensics / Red Flag Screening Engine.

Pure deterministic engine. No database, no ORM, no network, no LLM,
no system clock, no persistence, no file I/O, no environment variables.
All arithmetic uses decimal.Decimal — never float.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.analytics._calc import safe_divide
from app.analytics.models import DAYS_QUANTIZE, RATIO_QUANTIZE, ROUNDING, CalculationResult, PeriodFinancials
from app.models.enums import FindingType
from app.valuation.forensic_models import (
    CompanyType,
    DataQualityDiagnostic,
    ForensicCategory,
    ForensicCategorySummary,
    ForensicCheckResult,
    ForensicCheckStatus,
    ForensicConfig,
    ForensicPeriodInput,
    ForensicResult,
    ForensicSeverity,
    ThresholdClassification,
    ThresholdConfig,
    ThresholdDirection,
)

ENGINE_VERSION = "1.0.0"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_D365 = Decimal("365")

# ---------------------------------------------------------------------------
# Financial-company applicable checks (exactly 3)
# ---------------------------------------------------------------------------

FINANCIAL_APPLICABLE_CHECKS: frozenset[str] = frozenset(
    {
        "eq.total_accruals_to_assets",
        "cf.negative_cfo_count",
        "pr.net_margin_decline",
    }
)

# ---------------------------------------------------------------------------
# Check → category mapping
# ---------------------------------------------------------------------------

_CHECK_CATEGORY: dict[str, ForensicCategory] = {
    "eq.cfo_to_net_income": ForensicCategory.EARNINGS_QUALITY,
    "eq.cfo_net_income_divergence": ForensicCategory.EARNINGS_QUALITY,
    "eq.total_accruals_to_assets": ForensicCategory.EARNINGS_QUALITY,
    "eq.cfo_to_ebitda": ForensicCategory.EARNINGS_QUALITY,
    "wc.receivables_vs_revenue_growth": ForensicCategory.WORKING_CAPITAL,
    "wc.inventory_vs_revenue_growth": ForensicCategory.WORKING_CAPITAL,
    "wc.dso_change": ForensicCategory.WORKING_CAPITAL,
    "wc.dio_change": ForensicCategory.WORKING_CAPITAL,
    "wc.dpo_change": ForensicCategory.WORKING_CAPITAL,
    "wc.cash_conversion_cycle_change": ForensicCategory.WORKING_CAPITAL,
    "cf.negative_cfo_count": ForensicCategory.CASH_FLOW_QUALITY,
    "cf.negative_fcf_count": ForensicCategory.CASH_FLOW_QUALITY,
    "cf.cfo_to_ebitda_level": ForensicCategory.CASH_FLOW_QUALITY,
    "cf.capex_intensity_change": ForensicCategory.CASH_FLOW_QUALITY,
    "lv.debt_to_equity": ForensicCategory.LEVERAGE,
    "lv.net_debt_to_ebitda": ForensicCategory.LEVERAGE,
    "lv.interest_coverage": ForensicCategory.LEVERAGE,
    "lv.leverage_trend": ForensicCategory.LEVERAGE,
    "pr.gross_margin_decline": ForensicCategory.PROFITABILITY,
    "pr.ebitda_margin_decline": ForensicCategory.PROFITABILITY,
    "pr.net_margin_decline": ForensicCategory.PROFITABILITY,
    "pr.profit_vs_cashflow_divergence": ForensicCategory.PROFITABILITY,
}

ALL_CHECK_IDS: list[str] = list(_CHECK_CATEGORY.keys())

# ---------------------------------------------------------------------------
# Default threshold configuration
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict[str, ThresholdConfig] = {
    "eq.cfo_to_net_income": ThresholdConfig(
        low=Decimal("0.70"),
        medium=Decimal("0.50"),
        high=Decimal("0.30"),
        critical=Decimal("0.00"),
        direction=ThresholdDirection.BELOW,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="CFO significantly below net income suggests low earnings quality",
    ),
    "eq.cfo_net_income_divergence": ThresholdConfig(
        low=Decimal("0.33"),
        medium=Decimal("0.50"),
        high=Decimal("0.67"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Frequent sign divergence between CFO and PAT",
    ),
    "eq.total_accruals_to_assets": ThresholdConfig(
        low=Decimal("0.05"),
        medium=Decimal("0.10"),
        high=Decimal("0.15"),
        critical=Decimal("0.25"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="High total accruals relative to assets",
    ),
    "eq.cfo_to_ebitda": ThresholdConfig(
        low=Decimal("0.50"),
        medium=Decimal("0.30"),
        high=Decimal("0.15"),
        critical=Decimal("0.00"),
        direction=ThresholdDirection.BELOW,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="CFO significantly below EBITDA suggests poor cash conversion",
    ),
    "wc.receivables_vs_revenue_growth": ThresholdConfig(
        low=Decimal("0.10"),
        medium=Decimal("0.20"),
        high=Decimal("0.40"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Receivables growing materially faster than revenue",
    ),
    "wc.inventory_vs_revenue_growth": ThresholdConfig(
        low=Decimal("0.10"),
        medium=Decimal("0.20"),
        high=Decimal("0.40"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Inventory growing materially faster than revenue",
    ),
    "wc.dso_change": ThresholdConfig(
        low=Decimal("15"),
        medium=Decimal("30"),
        high=Decimal("60"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Days sales outstanding increasing",
    ),
    "wc.dio_change": ThresholdConfig(
        low=Decimal("15"),
        medium=Decimal("30"),
        high=Decimal("60"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Days inventory outstanding increasing",
    ),
    "wc.dpo_change": ThresholdConfig(
        low=Decimal("-15"),
        medium=Decimal("-30"),
        high=Decimal("-60"),
        direction=ThresholdDirection.BELOW,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Days payable outstanding decreasing (paying suppliers faster)",
    ),
    "wc.cash_conversion_cycle_change": ThresholdConfig(
        low=Decimal("15"),
        medium=Decimal("30"),
        high=Decimal("60"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Cash conversion cycle lengthening",
    ),
    "cf.negative_cfo_count": ThresholdConfig(
        low=Decimal("0.33"),
        medium=Decimal("0.50"),
        high=Decimal("0.67"),
        critical=Decimal("1.00"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Proportion of periods with negative operating cash flow",
    ),
    "cf.negative_fcf_count": ThresholdConfig(
        low=Decimal("0.33"),
        medium=Decimal("0.50"),
        high=Decimal("0.67"),
        critical=Decimal("1.00"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Proportion of periods with negative free cash flow",
    ),
    "cf.cfo_to_ebitda_level": ThresholdConfig(
        low=Decimal("0.50"),
        medium=Decimal("0.30"),
        high=Decimal("0.15"),
        critical=Decimal("0.00"),
        direction=ThresholdDirection.BELOW,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="CFO well below EBITDA in latest period",
    ),
    "cf.capex_intensity_change": ThresholdConfig(
        low=Decimal("0.05"),
        medium=Decimal("0.10"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="CapEx intensity rising as share of revenue",
    ),
    "lv.debt_to_equity": ThresholdConfig(
        low=Decimal("1.50"),
        medium=Decimal("2.50"),
        high=Decimal("4.00"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="High debt relative to equity",
    ),
    "lv.net_debt_to_ebitda": ThresholdConfig(
        low=Decimal("3.00"),
        medium=Decimal("4.50"),
        high=Decimal("6.00"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Net debt high relative to EBITDA",
    ),
    "lv.interest_coverage": ThresholdConfig(
        low=Decimal("3.00"),
        medium=Decimal("2.00"),
        high=Decimal("1.50"),
        critical=Decimal("1.00"),
        direction=ThresholdDirection.BELOW,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Earnings insufficient to cover interest obligations",
    ),
    "lv.leverage_trend": ThresholdConfig(
        low=Decimal("0.50"),
        medium=Decimal("1.00"),
        high=Decimal("2.00"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Debt-to-equity ratio increasing",
    ),
    "pr.gross_margin_decline": ThresholdConfig(
        low=Decimal("2"),
        medium=Decimal("3"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Consecutive periods of gross margin decline",
    ),
    "pr.ebitda_margin_decline": ThresholdConfig(
        low=Decimal("2"),
        medium=Decimal("3"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Consecutive periods of EBITDA margin decline",
    ),
    "pr.net_margin_decline": ThresholdConfig(
        low=Decimal("2"),
        medium=Decimal("3"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Consecutive periods of net margin decline",
    ),
    "pr.profit_vs_cashflow_divergence": ThresholdConfig(
        medium=Decimal("1"),
        direction=ThresholdDirection.ABOVE,
        classification=ThresholdClassification.PLATFORM_HEURISTIC,
        rationale="Net margin improving while CFO/PAT deteriorating",
    ),
}

DEFAULT_CONFIG = ForensicConfig(
    version="1.0.0",
    thresholds=_DEFAULT_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ForensicValidationError(Exception):
    """Raised for invalid forensic engine inputs."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_severity(
    value: Decimal,
    threshold_cfg: ThresholdConfig,
) -> ForensicSeverity | None:
    if threshold_cfg.direction == ThresholdDirection.ABOVE:
        if threshold_cfg.critical is not None and value >= threshold_cfg.critical:
            return ForensicSeverity.CRITICAL
        if threshold_cfg.high is not None and value >= threshold_cfg.high:
            return ForensicSeverity.HIGH
        if threshold_cfg.medium is not None and value >= threshold_cfg.medium:
            return ForensicSeverity.MEDIUM
        if threshold_cfg.low is not None and value >= threshold_cfg.low:
            return ForensicSeverity.LOW
        return None
    # BELOW direction
    if threshold_cfg.critical is not None and value <= threshold_cfg.critical:
        return ForensicSeverity.CRITICAL
    if threshold_cfg.high is not None and value <= threshold_cfg.high:
        return ForensicSeverity.HIGH
    if threshold_cfg.medium is not None and value <= threshold_cfg.medium:
        return ForensicSeverity.MEDIUM
    if threshold_cfg.low is not None and value <= threshold_cfg.low:
        return ForensicSeverity.LOW
    return None


def _severity_to_threshold(
    severity: ForensicSeverity | None,
    cfg: ThresholdConfig,
) -> Decimal | None:
    if severity is None:
        return None
    mapping = {
        ForensicSeverity.LOW: cfg.low,
        ForensicSeverity.MEDIUM: cfg.medium,
        ForensicSeverity.HIGH: cfg.high,
        ForensicSeverity.CRITICAL: cfg.critical,
    }
    return mapping.get(severity)


def _screening_description(check_id: str) -> str:
    return f"Screening signal: {check_id} crossed configured threshold."


def _make_result(
    check_id: str,
    *,
    status: ForensicCheckStatus,
    period: str,
    severity: ForensicSeverity | None = None,
    observed_value: Decimal | None = None,
    threshold: Decimal | None = None,
    threshold_direction: ThresholdDirection | None = None,
    threshold_classification: ThresholdClassification | None = None,
    calculation: CalculationResult | None = None,
    notes: str | None = None,
    description: str | None = None,
) -> ForensicCheckResult:
    if description is None:
        if status == ForensicCheckStatus.FLAGGED:
            description = _screening_description(check_id)
        elif status == ForensicCheckStatus.PASS:
            description = f"{check_id}: within configured threshold."
        elif status == ForensicCheckStatus.NOT_COMPUTABLE:
            description = f"{check_id}: not computable — {notes or 'missing input data'}."
        elif status == ForensicCheckStatus.INVALID_INPUT:
            description = f"{check_id}: invalid input — {notes or 'economically invalid state'}."
        elif status == ForensicCheckStatus.NOT_APPLICABLE:
            description = f"{check_id}: not applicable for this company type."
        elif status == ForensicCheckStatus.INSUFFICIENT_HISTORY:
            description = f"{check_id}: insufficient history for this check."
        elif status == ForensicCheckStatus.UNVERIFIED_TIMING:
            description = f"{check_id}: unverified timing — value computed for informational purposes only."
        elif status == ForensicCheckStatus.LOOK_AHEAD_RISK:
            description = f"{check_id}: look-ahead risk — period excluded from analysis."
        else:
            description = f"{check_id}: {status.value}."

    return ForensicCheckResult(
        check_id=check_id,
        category=_CHECK_CATEGORY[check_id],
        status=status,
        severity=severity,
        observed_value=observed_value,
        threshold=threshold,
        threshold_direction=threshold_direction,
        threshold_classification=threshold_classification,
        period=period,
        finding_type=FindingType.CALCULATION,
        description=description,
        calculation=calculation,
        notes=notes,
    )


def _evaluate_ratio(
    check_id: str,
    value: Decimal,
    period: str,
    cfg: ThresholdConfig,
    calc: CalculationResult,
) -> ForensicCheckResult:
    severity = _classify_severity(value, cfg)
    if severity is not None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.FLAGGED,
            period=period,
            severity=severity,
            observed_value=value,
            threshold=_severity_to_threshold(severity, cfg),
            threshold_direction=cfg.direction,
            threshold_classification=cfg.classification,
            calculation=calc,
        )
    return _make_result(
        check_id,
        status=ForensicCheckStatus.PASS,
        period=period,
        observed_value=value,
        calculation=calc,
    )


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------


class _TimingStatus:
    VALID = "valid"
    LOOK_AHEAD_RISK = "look_ahead_risk"
    UNVERIFIED_TIMING = "unverified_timing"


def _classify_timing(period: ForensicPeriodInput, observation_date: date) -> str:
    if period.financials_available_date is None:
        return _TimingStatus.UNVERIFIED_TIMING
    if period.financials_available_date <= observation_date:
        return _TimingStatus.VALID
    return _TimingStatus.LOOK_AHEAD_RISK


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_inputs(
    periods: list[ForensicPeriodInput],
    market_cap: Decimal | None,
) -> None:
    if not periods:
        msg = "at least one period of financial data is required"
        raise ForensicValidationError(msg)

    ends = [p.financial_period_end for p in periods]
    if len(set(ends)) != len(ends):
        msg = f"duplicate financial_period_end values: {ends}"
        raise ForensicValidationError(msg)

    for i in range(1, len(ends)):
        if ends[i] <= ends[i - 1]:
            msg = f"periods must be in chronological order; {ends[i]} <= {ends[i - 1]}"
            raise ForensicValidationError(msg)

    if market_cap is not None and market_cap <= _ZERO:
        msg = f"market_cap must be positive when supplied, got {market_cap}"
        raise ForensicValidationError(msg)


# ---------------------------------------------------------------------------
# Data-quality diagnostics
# ---------------------------------------------------------------------------


def _structural_diagnostics(periods: list[ForensicPeriodInput]) -> list[DataQualityDiagnostic]:
    diags: list[DataQualityDiagnostic] = []
    for p in periods:
        f: PeriodFinancials = p.financials  # type: ignore[assignment]
        period_str = f.period

        if f.total_assets is not None and f.total_assets <= _ZERO:
            diags.append(
                DataQualityDiagnostic(
                    period=period_str,
                    field="total_assets",
                    issue="total_assets is zero or negative",
                    observed_values={"total_assets": f.total_assets},
                )
            )

        if f.current_assets is not None and f.total_assets is not None and f.current_assets > f.total_assets:
            diags.append(
                DataQualityDiagnostic(
                    period=period_str,
                    field="current_assets",
                    issue="current_assets exceeds total_assets",
                    observed_values={"current_assets": f.current_assets, "total_assets": f.total_assets},
                )
            )

        if (
            f.cash_and_equivalents is not None
            and f.total_assets is not None
            and f.cash_and_equivalents > f.total_assets
        ):
            diags.append(
                DataQualityDiagnostic(
                    period=period_str,
                    field="cash_and_equivalents",
                    issue="cash_and_equivalents exceeds total_assets",
                    observed_values={"cash_and_equivalents": f.cash_and_equivalents, "total_assets": f.total_assets},
                )
            )

        if f.current_liabilities is not None and f.total_assets is not None and f.current_liabilities > f.total_assets:
            diags.append(
                DataQualityDiagnostic(
                    period=period_str,
                    field="current_liabilities",
                    issue="current_liabilities exceeds total_assets",
                    observed_values={"current_liabilities": f.current_liabilities, "total_assets": f.total_assets},
                )
            )

        if f.revenue is not None and f.revenue < _ZERO:
            diags.append(
                DataQualityDiagnostic(
                    period=period_str,
                    field="revenue",
                    issue="revenue is negative",
                    observed_values={"revenue": f.revenue},
                )
            )

    return diags


# ---------------------------------------------------------------------------
# Individual check implementations
# ---------------------------------------------------------------------------

# ---- A. EARNINGS QUALITY ----


def _check_cfo_to_net_income(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "eq.cfo_to_net_income"
    val, note = safe_divide(fin.cfo, fin.pat)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None
    calc = CalculationResult(
        metric="forensic_cfo_to_net_income",
        value=val,
        inputs={"cfo": fin.cfo, "pat": fin.pat},
        period=period_str,
        formula="cfo / pat",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_cfo_net_income_divergence(
    valid_fins: list[PeriodFinancials],
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "eq.cfo_net_income_divergence"
    period_str = valid_fins[-1].period if valid_fins else "N/A"

    computable: list[PeriodFinancials] = [f for f in valid_fins if f.cfo is not None and f.pat is not None]

    if len(computable) < 3:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
            period=period_str,
            notes=f"need 3 computable periods, have {len(computable)}",
        ), None

    divergence_count = 0
    for f in computable:
        cfo_non_neg = f.cfo is not None and f.cfo >= _ZERO
        pat_non_neg = f.pat is not None and f.pat >= _ZERO
        if cfo_non_neg != pat_non_neg:
            divergence_count += 1
    ratio = (Decimal(divergence_count) / Decimal(len(computable))).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric="forensic_cfo_net_income_divergence",
        value=ratio,
        inputs={"divergence_count": divergence_count, "computable_periods": len(computable)},
        period=f"{computable[0].period}-{computable[-1].period}",
        formula="count(sign(cfo) != sign(pat)) / computable_periods",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, ratio, period_str, cfg, calc), calc


def _check_total_accruals_to_assets(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "eq.total_accruals_to_assets"

    if fin.total_assets is not None and fin.total_assets <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="total_assets is zero or negative",
            observed_value=fin.total_assets,
        ), None

    if fin.pat is None or fin.cfo is None or fin.total_assets is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes="missing pat, cfo, or total_assets",
        ), None

    accruals = fin.pat - fin.cfo
    val, note = safe_divide(accruals, fin.total_assets)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_total_accruals_to_assets",
        value=val,
        inputs={"pat": fin.pat, "cfo": fin.cfo, "total_assets": fin.total_assets, "accruals": accruals},
        period=period_str,
        formula="(pat - cfo) / total_assets",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_cfo_to_ebitda(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "eq.cfo_to_ebitda"

    if fin.ebitda is not None and fin.ebitda <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="ebitda is zero or negative",
            observed_value=fin.ebitda,
        ), None

    val, note = safe_divide(fin.cfo, fin.ebitda)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_cfo_to_ebitda",
        value=val,
        inputs={"cfo": fin.cfo, "ebitda": fin.ebitda},
        period=period_str,
        formula="cfo / ebitda",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


# ---- B. WORKING CAPITAL ----


def _growth_rate(current: Decimal | None, prior: Decimal | None) -> tuple[Decimal | None, str | None]:
    if current is None or prior is None:
        return None, "missing input data"
    if prior == _ZERO:
        return None, "prior value is zero; growth undefined"
    if prior < _ZERO:
        return None, "prior value is negative; growth from negative base undefined"
    diff = current - prior
    return (diff / abs(prior)).quantize(RATIO_QUANTIZE, rounding=ROUNDING), None


def _check_growth_vs_revenue(
    check_id: str,
    metric_name: str,
    field_name: str,
    current_val: Decimal | None,
    prior_val: Decimal | None,
    current_fin: PeriodFinancials,
    prior_fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    field_growth, field_note = _growth_rate(current_val, prior_val)
    rev_growth, rev_note = _growth_rate(current_fin.revenue, prior_fin.revenue)

    if field_growth is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=f"{field_name}: {field_note}",
        ), None
    if rev_growth is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=f"revenue growth: {rev_note}",
        ), None

    excess = (field_growth - rev_growth).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric=metric_name,
        value=excess,
        inputs={
            f"{field_name}_current": current_val,
            f"{field_name}_prior": prior_val,
            "revenue_current": current_fin.revenue,
            "revenue_prior": prior_fin.revenue,
            f"{field_name}_growth": field_growth,
            "revenue_growth": rev_growth,
        },
        period=period_str,
        formula=f"({field_name}_growth) - (revenue_growth)",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, excess, period_str, cfg, calc), calc


def _days_metric(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> tuple[Decimal | None, str | None]:
    if numerator is None or denominator is None:
        return None, "missing input data"
    if denominator <= _ZERO:
        return None, "denominator is zero or negative"
    return (numerator / denominator * _D365).quantize(DAYS_QUANTIZE, rounding=ROUNDING), None


def _check_days_change(
    check_id: str,
    metric_name: str,
    current_num: Decimal | None,
    current_den: Decimal | None,
    prior_num: Decimal | None,
    prior_den: Decimal | None,
    period_str: str,
    cfg: ThresholdConfig,
    num_label: str,
    den_label: str,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    current_days, current_note = _days_metric(current_num, current_den)
    if current_days is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=f"current: {current_note}",
        ), None
    prior_days, prior_note = _days_metric(prior_num, prior_den)
    if prior_days is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=f"prior: {prior_note}",
        ), None

    change = (current_days - prior_days).quantize(DAYS_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric=metric_name,
        value=change,
        inputs={
            f"{num_label}_current": current_num,
            f"{den_label}_current": current_den,
            f"{num_label}_prior": prior_num,
            f"{den_label}_prior": prior_den,
            "current_days": current_days,
            "prior_days": prior_days,
        },
        period=period_str,
        formula=f"({num_label}/{den_label}*365)_current - ({num_label}/{den_label}*365)_prior",
        version=ENGINE_VERSION,
        unit="days",
    )
    return _evaluate_ratio(check_id, change, period_str, cfg, calc), calc


def _check_ccc_change(
    current_fin: PeriodFinancials,
    prior_fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "wc.cash_conversion_cycle_change"

    dso_c, _ = _days_metric(current_fin.accounts_receivable, current_fin.revenue)
    dio_c, _ = _days_metric(current_fin.inventory, current_fin.cost_of_goods_sold)
    dpo_c, _ = _days_metric(current_fin.accounts_payable, current_fin.cost_of_goods_sold)

    dso_p, _ = _days_metric(prior_fin.accounts_receivable, prior_fin.revenue)
    dio_p, _ = _days_metric(prior_fin.inventory, prior_fin.cost_of_goods_sold)
    dpo_p, _ = _days_metric(prior_fin.accounts_payable, prior_fin.cost_of_goods_sold)

    if any(v is None for v in (dso_c, dio_c, dpo_c, dso_p, dio_p, dpo_p)):
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes="one or more day metrics not computable for CCC",
        ), None

    assert dso_c is not None and dio_c is not None and dpo_c is not None
    assert dso_p is not None and dio_p is not None and dpo_p is not None

    ccc_c = (dso_c + dio_c - dpo_c).quantize(DAYS_QUANTIZE, rounding=ROUNDING)
    ccc_p = (dso_p + dio_p - dpo_p).quantize(DAYS_QUANTIZE, rounding=ROUNDING)
    change = (ccc_c - ccc_p).quantize(DAYS_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric="forensic_ccc_change",
        value=change,
        inputs={
            "dso_current": dso_c,
            "dio_current": dio_c,
            "dpo_current": dpo_c,
            "dso_prior": dso_p,
            "dio_prior": dio_p,
            "dpo_prior": dpo_p,
            "ccc_current": ccc_c,
            "ccc_prior": ccc_p,
        },
        period=period_str,
        formula="(DSO+DIO-DPO)_current - (DSO+DIO-DPO)_prior",
        version=ENGINE_VERSION,
        unit="days",
    )
    return _evaluate_ratio(check_id, change, period_str, cfg, calc), calc


# ---- C. CASH FLOW QUALITY ----


def _check_negative_count(
    check_id: str,
    metric_name: str,
    valid_fins: list[PeriodFinancials],
    value_fn: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    period_str = valid_fins[-1].period if valid_fins else "N/A"

    computable: list[tuple[PeriodFinancials, Decimal]] = []
    for f in valid_fins:
        if value_fn == "cfo":
            v = f.cfo
        else:
            if f.cfo is None or f.capex is None:
                continue
            v = f.cfo - f.capex
        if v is not None:
            computable.append((f, v))

    if len(computable) < 3:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
            period=period_str,
            notes=f"need 3 computable periods, have {len(computable)}",
        ), None

    neg_count = sum(1 for _, v in computable if v < _ZERO)
    ratio = (Decimal(neg_count) / Decimal(len(computable))).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric=metric_name,
        value=ratio,
        inputs={"negative_count": neg_count, "computable_periods": len(computable)},
        period=f"{computable[0][0].period}-{computable[-1][0].period}",
        formula=f"count({value_fn} < 0) / computable_periods",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, ratio, period_str, cfg, calc), calc


def _check_cfo_to_ebitda_level(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "cf.cfo_to_ebitda_level"

    if fin.ebitda is not None and fin.ebitda <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="ebitda is zero or negative",
            observed_value=fin.ebitda,
        ), None

    val, note = safe_divide(fin.cfo, fin.ebitda)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_cfo_to_ebitda_level",
        value=val,
        inputs={"cfo": fin.cfo, "ebitda": fin.ebitda},
        period=period_str,
        formula="cfo / ebitda",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_capex_intensity_change(
    current_fin: PeriodFinancials,
    prior_fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "cf.capex_intensity_change"

    if current_fin.revenue is not None and current_fin.revenue <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="current revenue is zero or negative",
            observed_value=current_fin.revenue,
        ), None
    if prior_fin.revenue is not None and prior_fin.revenue <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="prior revenue is zero or negative",
            observed_value=prior_fin.revenue,
        ), None

    current_ratio, cn = safe_divide(current_fin.capex, current_fin.revenue)
    if current_ratio is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"current: {cn}"
        ), None
    prior_ratio, pn = safe_divide(prior_fin.capex, prior_fin.revenue)
    if prior_ratio is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"prior: {pn}"
        ), None

    change = (current_ratio - prior_ratio).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric="forensic_capex_intensity_change",
        value=change,
        inputs={
            "capex_current": current_fin.capex,
            "revenue_current": current_fin.revenue,
            "capex_prior": prior_fin.capex,
            "revenue_prior": prior_fin.revenue,
            "ratio_current": current_ratio,
            "ratio_prior": prior_ratio,
        },
        period=period_str,
        formula="(capex/revenue)_current - (capex/revenue)_prior",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, change, period_str, cfg, calc), calc


# ---- D. LEVERAGE ----


def _check_debt_to_equity(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "lv.debt_to_equity"

    if fin.total_equity is not None and fin.total_equity <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="total_equity is zero or negative",
            observed_value=fin.total_equity,
        ), None

    val, note = safe_divide(fin.total_debt, fin.total_equity)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_debt_to_equity",
        value=val,
        inputs={"total_debt": fin.total_debt, "total_equity": fin.total_equity},
        period=period_str,
        formula="total_debt / total_equity",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_net_debt_to_ebitda(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "lv.net_debt_to_ebitda"

    if fin.ebitda is not None and fin.ebitda <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="ebitda is zero or negative",
            observed_value=fin.ebitda,
        ), None

    if fin.total_debt is None or fin.cash_and_equivalents is None or fin.ebitda is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes="missing total_debt, cash_and_equivalents, or ebitda",
        ), None

    net_debt = fin.total_debt - fin.cash_and_equivalents
    val, note = safe_divide(net_debt, fin.ebitda)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_net_debt_to_ebitda",
        value=val,
        inputs={
            "total_debt": fin.total_debt,
            "cash_and_equivalents": fin.cash_and_equivalents,
            "net_debt": net_debt,
            "ebitda": fin.ebitda,
        },
        period=period_str,
        formula="(total_debt - cash_and_equivalents) / ebitda",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_interest_coverage(
    fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "lv.interest_coverage"

    if fin.interest_expense is None or fin.ebit is None:
        notes_parts = []
        if fin.ebit is None:
            notes_parts.append("ebit")
        if fin.interest_expense is None:
            notes_parts.append("interest_expense")
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=f"missing {', '.join(notes_parts)}",
        ), None

    if fin.interest_expense == _ZERO:
        zero_note = "Interest expense is zero; interest coverage ratio is undefined"
        if fin.total_debt is not None and fin.total_debt == _ZERO:
            zero_note += ". total_debt is also zero"
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes=zero_note,
            observed_value=fin.interest_expense,
            calculation=CalculationResult(
                metric="forensic_interest_coverage",
                value=None,
                inputs={"ebit": fin.ebit, "interest_expense": fin.interest_expense, "total_debt": fin.total_debt},
                period=period_str,
                formula="ebit / interest_expense",
                version=ENGINE_VERSION,
                unit="ratio",
                notes=zero_note,
            ),
        ), None

    if fin.interest_expense < _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="interest_expense is negative",
            observed_value=fin.interest_expense,
        ), None

    val, note = safe_divide(fin.ebit, fin.interest_expense)
    if val is None:
        return _make_result(check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=note), None

    calc = CalculationResult(
        metric="forensic_interest_coverage",
        value=val,
        inputs={"ebit": fin.ebit, "interest_expense": fin.interest_expense},
        period=period_str,
        formula="ebit / interest_expense",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_leverage_trend(
    current_fin: PeriodFinancials,
    prior_fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "lv.leverage_trend"

    if current_fin.total_equity is not None and current_fin.total_equity <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="current total_equity is zero or negative",
            observed_value=current_fin.total_equity,
        ), None

    if prior_fin.total_equity is not None and prior_fin.total_equity <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="prior total_equity is zero or negative",
            observed_value=prior_fin.total_equity,
        ), None

    current_de, cn = safe_divide(current_fin.total_debt, current_fin.total_equity)
    if current_de is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"current D/E: {cn}"
        ), None
    prior_de, pn = safe_divide(prior_fin.total_debt, prior_fin.total_equity)
    if prior_de is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"prior D/E: {pn}"
        ), None

    change = (current_de - prior_de).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

    calc = CalculationResult(
        metric="forensic_leverage_trend",
        value=change,
        inputs={
            "debt_current": current_fin.total_debt,
            "equity_current": current_fin.total_equity,
            "debt_prior": prior_fin.total_debt,
            "equity_prior": prior_fin.total_equity,
            "de_current": current_de,
            "de_prior": prior_de,
        },
        period=period_str,
        formula="(debt/equity)_current - (debt/equity)_prior",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return _evaluate_ratio(check_id, change, period_str, cfg, calc), calc


# ---- E. PROFITABILITY ----


def _margin_value(
    numerator: Decimal | None,
    revenue: Decimal | None,
) -> Decimal | None:
    if numerator is None or revenue is None or revenue <= _ZERO:
        return None
    return (numerator / revenue).quantize(RATIO_QUANTIZE, rounding=ROUNDING)


def _check_margin_decline(
    check_id: str,
    metric_name: str,
    valid_fins: list[PeriodFinancials],
    margin_fn: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    period_str = valid_fins[-1].period if valid_fins else "N/A"

    margins: list[tuple[str, Decimal]] = []
    for f in valid_fins:
        if f.revenue is not None and f.revenue <= _ZERO:
            margins.clear()
            continue

        if margin_fn == "gross":
            num = f.gross_profit
        elif margin_fn == "ebitda":
            num = f.ebitda
        else:
            num = f.pat

        m = _margin_value(num, f.revenue)
        if m is None:
            margins.clear()
            continue
        margins.append((f.period, m))

    if len(margins) < 3:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
            period=period_str,
            notes=f"need 3 valid margin periods, have {len(margins)}",
        ), None

    consec = 0
    for i in range(len(margins) - 1, 0, -1):
        if margins[i][1] < margins[i - 1][1]:
            consec += 1
        else:
            break

    val = Decimal(consec)
    calc = CalculationResult(
        metric=metric_name,
        value=val,
        inputs={p: str(m) for p, m in margins},
        period=f"{margins[0][0]}-{margins[-1][0]}",
        formula=f"consecutive periods where {margin_fn}_margin decreases (working backwards)",
        version=ENGINE_VERSION,
        unit="count",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


def _check_profit_vs_cashflow_divergence(
    current_fin: PeriodFinancials,
    prior_fin: PeriodFinancials,
    period_str: str,
    cfg: ThresholdConfig,
) -> tuple[ForensicCheckResult, CalculationResult | None]:
    check_id = "pr.profit_vs_cashflow_divergence"

    if current_fin.revenue is not None and current_fin.revenue <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="current revenue is zero or negative",
        ), None
    if prior_fin.revenue is not None and prior_fin.revenue <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="prior revenue is zero or negative",
        ), None
    if current_fin.pat is not None and current_fin.pat <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="current pat is zero or negative",
        ), None
    if prior_fin.pat is not None and prior_fin.pat <= _ZERO:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.INVALID_INPUT,
            period=period_str,
            notes="prior pat is zero or negative",
        ), None

    nm_c = _margin_value(current_fin.pat, current_fin.revenue)
    nm_p = _margin_value(prior_fin.pat, prior_fin.revenue)
    if nm_c is None or nm_p is None:
        return _make_result(
            check_id,
            status=ForensicCheckStatus.NOT_COMPUTABLE,
            period=period_str,
            notes="cannot compute net margin for current or prior period",
        ), None

    cfo_pat_c, cn = safe_divide(current_fin.cfo, current_fin.pat)
    if cfo_pat_c is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"current cfo/pat: {cn}"
        ), None
    cfo_pat_p, pn = safe_divide(prior_fin.cfo, prior_fin.pat)
    if cfo_pat_p is None:
        return _make_result(
            check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period=period_str, notes=f"prior cfo/pat: {pn}"
        ), None

    nm_improving = nm_c > nm_p
    cfo_pat_declining = cfo_pat_c < cfo_pat_p
    divergence = nm_improving and cfo_pat_declining
    val = _ONE if divergence else _ZERO

    calc = CalculationResult(
        metric="forensic_profit_vs_cashflow_divergence",
        value=val,
        inputs={
            "net_margin_current": nm_c,
            "net_margin_prior": nm_p,
            "cfo_pat_current": cfo_pat_c,
            "cfo_pat_prior": cfo_pat_p,
            "nm_improving": str(nm_improving),
            "cfo_pat_declining": str(cfo_pat_declining),
        },
        period=period_str,
        formula="1 if (net_margin increasing AND cfo/pat decreasing) else 0",
        version=ENGINE_VERSION,
        unit="flag",
    )
    return _evaluate_ratio(check_id, val, period_str, cfg, calc), calc


# ---------------------------------------------------------------------------
# Beneish components
# ---------------------------------------------------------------------------


def _beneish_dsri(
    current: PeriodFinancials,
    prior: PeriodFinancials,
    period_str: str,
) -> tuple[Decimal | None, CalculationResult | None]:
    ar_rev_c, _ = safe_divide(current.accounts_receivable, current.revenue)
    ar_rev_p, _ = safe_divide(prior.accounts_receivable, prior.revenue)
    if ar_rev_c is None or ar_rev_p is None:
        return None, None
    dsri, note = safe_divide(ar_rev_c, ar_rev_p)
    if dsri is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_beneish_dsri",
        value=dsri,
        inputs={
            "ar_current": current.accounts_receivable,
            "revenue_current": current.revenue,
            "ar_prior": prior.accounts_receivable,
            "revenue_prior": prior.revenue,
            "ar_rev_current": ar_rev_c,
            "ar_rev_prior": ar_rev_p,
        },
        period=period_str,
        formula="(AR_t/Rev_t) / (AR_{t-1}/Rev_{t-1})",
        version=ENGINE_VERSION,
        unit="index",
    )
    return dsri, calc


def _beneish_gmi(
    current: PeriodFinancials,
    prior: PeriodFinancials,
    period_str: str,
) -> tuple[Decimal | None, CalculationResult | None]:
    gm_c = _margin_value(current.gross_profit, current.revenue)
    gm_p = _margin_value(prior.gross_profit, prior.revenue)
    if gm_c is None or gm_p is None:
        return None, None
    gmi, note = safe_divide(gm_p, gm_c)
    if gmi is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_beneish_gmi",
        value=gmi,
        inputs={
            "gross_profit_current": current.gross_profit,
            "revenue_current": current.revenue,
            "gross_profit_prior": prior.gross_profit,
            "revenue_prior": prior.revenue,
            "gm_current": gm_c,
            "gm_prior": gm_p,
        },
        period=period_str,
        formula="GM_{t-1} / GM_t where GM = gross_profit / revenue",
        version=ENGINE_VERSION,
        unit="index",
    )
    return gmi, calc


def _beneish_sgi(
    current: PeriodFinancials,
    prior: PeriodFinancials,
    period_str: str,
) -> tuple[Decimal | None, CalculationResult | None]:
    sgi, note = safe_divide(current.revenue, prior.revenue)
    if sgi is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_beneish_sgi",
        value=sgi,
        inputs={"revenue_current": current.revenue, "revenue_prior": prior.revenue},
        period=period_str,
        formula="Rev_t / Rev_{t-1}",
        version=ENGINE_VERSION,
        unit="index",
    )
    return sgi, calc


def _beneish_tata(
    fin: PeriodFinancials,
    period_str: str,
) -> tuple[Decimal | None, CalculationResult | None]:
    if fin.pat is None or fin.cfo is None or fin.total_assets is None:
        return None, None
    if fin.total_assets <= _ZERO:
        return None, None
    accruals = fin.pat - fin.cfo
    tata, note = safe_divide(accruals, fin.total_assets)
    if tata is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_beneish_tata",
        value=tata,
        inputs={"pat": fin.pat, "cfo": fin.cfo, "total_assets": fin.total_assets, "accruals": accruals},
        period=period_str,
        formula="(PAT - CFO) / Total_Assets",
        version=ENGINE_VERSION,
        unit="index",
    )
    return tata, calc


# ---------------------------------------------------------------------------
# Altman components
# ---------------------------------------------------------------------------


def _altman_x1(fin: PeriodFinancials, period_str: str) -> tuple[Decimal | None, CalculationResult | None]:
    if fin.current_assets is None or fin.current_liabilities is None or fin.total_assets is None:
        return None, None
    if fin.total_assets <= _ZERO:
        return None, None
    wc = fin.current_assets - fin.current_liabilities
    x1, _ = safe_divide(wc, fin.total_assets)
    if x1 is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_altman_x1",
        value=x1,
        inputs={
            "current_assets": fin.current_assets,
            "current_liabilities": fin.current_liabilities,
            "total_assets": fin.total_assets,
            "working_capital": wc,
        },
        period=period_str,
        formula="(current_assets - current_liabilities) / total_assets",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return x1, calc


def _altman_x3(fin: PeriodFinancials, period_str: str) -> tuple[Decimal | None, CalculationResult | None]:
    if fin.ebit is None or fin.total_assets is None:
        return None, None
    if fin.total_assets <= _ZERO:
        return None, None
    x3, _ = safe_divide(fin.ebit, fin.total_assets)
    if x3 is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_altman_x3",
        value=x3,
        inputs={"ebit": fin.ebit, "total_assets": fin.total_assets},
        period=period_str,
        formula="ebit / total_assets",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return x3, calc


def _altman_x4(
    fin: PeriodFinancials,
    market_cap: Decimal | None,
    period_str: str,
) -> tuple[Decimal | None, CalculationResult | None, ForensicCheckStatus | None]:
    if market_cap is None:
        return None, None, ForensicCheckStatus.NOT_COMPUTABLE
    if fin.total_assets is None or fin.total_equity is None:
        return None, None, ForensicCheckStatus.NOT_COMPUTABLE
    if fin.total_assets <= _ZERO:
        return (
            None,
            CalculationResult(
                metric="forensic_altman_x4",
                value=None,
                inputs={"market_cap": market_cap, "total_assets": fin.total_assets, "total_equity": fin.total_equity},
                period=period_str,
                formula="market_cap / (total_assets - total_equity)",
                version=ENGINE_VERSION,
                unit="ratio",
                notes="total_assets is zero or negative",
            ),
            ForensicCheckStatus.INVALID_INPUT,
        )

    total_liabilities = fin.total_assets - fin.total_equity
    if total_liabilities <= _ZERO:
        return (
            None,
            CalculationResult(
                metric="forensic_altman_x4",
                value=None,
                inputs={
                    "market_cap": market_cap,
                    "total_assets": fin.total_assets,
                    "total_equity": fin.total_equity,
                    "total_liabilities_derived": total_liabilities,
                },
                period=period_str,
                formula="market_cap / (total_assets - total_equity)",
                version=ENGINE_VERSION,
                unit="ratio",
                notes="derived total_liabilities is zero or negative",
            ),
            ForensicCheckStatus.INVALID_INPUT,
        )

    x4, _ = safe_divide(market_cap, total_liabilities)
    if x4 is None:
        return None, None, ForensicCheckStatus.NOT_COMPUTABLE
    calc = CalculationResult(
        metric="forensic_altman_x4",
        value=x4,
        inputs={
            "market_cap": market_cap,
            "total_assets": fin.total_assets,
            "total_equity": fin.total_equity,
            "total_liabilities_derived": total_liabilities,
        },
        period=period_str,
        formula="market_cap / (total_assets - total_equity)",
        version=ENGINE_VERSION,
        unit="ratio",
        notes="total_liabilities derived as total_assets - total_equity",
    )
    return x4, calc, None


def _altman_x5(fin: PeriodFinancials, period_str: str) -> tuple[Decimal | None, CalculationResult | None]:
    if fin.revenue is None or fin.total_assets is None:
        return None, None
    if fin.total_assets <= _ZERO:
        return None, None
    x5, _ = safe_divide(fin.revenue, fin.total_assets)
    if x5 is None:
        return None, None
    calc = CalculationResult(
        metric="forensic_altman_x5",
        value=x5,
        inputs={"revenue": fin.revenue, "total_assets": fin.total_assets},
        period=period_str,
        formula="revenue / total_assets",
        version=ENGINE_VERSION,
        unit="ratio",
    )
    return x5, calc


# ---------------------------------------------------------------------------
# Category summary builder
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {
    ForensicSeverity.LOW: 1,
    ForensicSeverity.MEDIUM: 2,
    ForensicSeverity.HIGH: 3,
    ForensicSeverity.CRITICAL: 4,
}


def _build_category_summaries(
    checks: list[ForensicCheckResult],
) -> list[ForensicCategorySummary]:
    cat_checks: dict[ForensicCategory, list[ForensicCheckResult]] = {}
    for c in checks:
        cat_checks.setdefault(c.category, []).append(c)

    summaries: list[ForensicCategorySummary] = []
    for cat in ForensicCategory:
        cat_list = cat_checks.get(cat, [])
        total = len(cat_list)

        flagged = sum(1 for c in cat_list if c.status == ForensicCheckStatus.FLAGGED)
        passed = sum(1 for c in cat_list if c.status == ForensicCheckStatus.PASS)
        not_computable = sum(1 for c in cat_list if c.status == ForensicCheckStatus.NOT_COMPUTABLE)
        invalid_input = sum(1 for c in cat_list if c.status == ForensicCheckStatus.INVALID_INPUT)
        not_applicable = sum(1 for c in cat_list if c.status == ForensicCheckStatus.NOT_APPLICABLE)
        insufficient = sum(1 for c in cat_list if c.status == ForensicCheckStatus.INSUFFICIENT_HISTORY)
        unverified = sum(1 for c in cat_list if c.status == ForensicCheckStatus.UNVERIFIED_TIMING)
        look_ahead = sum(1 for c in cat_list if c.status == ForensicCheckStatus.LOOK_AHEAD_RISK)

        evaluated = flagged + passed
        applicable = total - not_applicable
        coverage: Decimal | None = None
        if applicable > 0:
            coverage = (Decimal(evaluated) / Decimal(applicable)).quantize(RATIO_QUANTIZE, rounding=ROUNDING)

        severities = [c.severity for c in cat_list if c.severity is not None]
        max_sev = max(severities, key=lambda s: _SEVERITY_ORDER[s]) if severities else None

        summaries.append(
            ForensicCategorySummary(
                category=cat,
                checks_total=total,
                checks_evaluated=evaluated,
                checks_flagged=flagged,
                checks_passed=passed,
                checks_not_computable=not_computable,
                checks_invalid_input=invalid_input,
                checks_not_applicable=not_applicable,
                checks_insufficient_history=insufficient,
                checks_unverified_timing=unverified,
                checks_look_ahead_risk=look_ahead,
                maximum_severity=max_sev,
                data_coverage_ratio=coverage,
            )
        )

    return summaries


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def forensic_analysis(
    periods: list[ForensicPeriodInput],
    *,
    observation_date: date,
    calculated_at: datetime,
    market_cap: Decimal | None = None,
    company_type: CompanyType = CompanyType.GENERAL,
    config: ForensicConfig | None = None,
) -> ForensicResult:
    """Run deterministic financial forensic analysis.

    Pure function: same inputs always produce same outputs.
    No DB, no network, no LLM, no system clock.
    """
    _validate_inputs(periods, market_cap)
    cfg = config or DEFAULT_CONFIG

    # Classify timing for each period
    timing: list[tuple[ForensicPeriodInput, str]] = [(p, _classify_timing(p, observation_date)) for p in periods]

    valid_periods = [p for p, t in timing if t == _TimingStatus.VALID]
    valid_fins: list[PeriodFinancials] = [p.financials for p in valid_periods]  # type: ignore[misc]

    diagnostics = _structural_diagnostics(periods)
    all_checks: list[ForensicCheckResult] = []
    all_calcs: list[CalculationResult] = []

    def _add(result: ForensicCheckResult, calc: CalculationResult | None) -> None:
        all_checks.append(result)
        if calc is not None:
            all_calcs.append(calc)

    def _get_threshold(check_id: str) -> ThresholdConfig:
        return cfg.thresholds[check_id]

    def _is_applicable(check_id: str) -> bool:
        if company_type == CompanyType.FINANCIAL:
            return check_id in FINANCIAL_APPLICABLE_CHECKS
        return True

    # Latest valid financials
    latest_valid: PeriodFinancials | None = valid_fins[-1] if valid_fins else None
    prior_valid: PeriodFinancials | None = valid_fins[-2] if len(valid_fins) >= 2 else None  # noqa: PLR2004
    latest_period_str = latest_valid.period if latest_valid else "N/A"

    # ---------------------------------------------------------------
    # A. EARNINGS QUALITY
    # ---------------------------------------------------------------
    for check_id in [
        "eq.cfo_to_net_income",
        "eq.cfo_net_income_divergence",
        "eq.total_accruals_to_assets",
        "eq.cfo_to_ebitda",
    ]:
        if not _is_applicable(check_id):
            _add(_make_result(check_id, status=ForensicCheckStatus.NOT_APPLICABLE, period=latest_period_str), None)
            continue

        if check_id == "eq.cfo_to_net_income":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_cfo_to_net_income(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "eq.cfo_net_income_divergence":
            if len(valid_fins) < 3:  # noqa: PLR2004
                _add(
                    _make_result(
                        check_id,
                        status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
                        period=latest_period_str,
                        notes=f"need 3 valid periods, have {len(valid_fins)}",
                    ),
                    None,
                )
            else:
                _add(*_check_cfo_net_income_divergence(valid_fins, _get_threshold(check_id)))

        elif check_id == "eq.total_accruals_to_assets":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_total_accruals_to_assets(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "eq.cfo_to_ebitda":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_cfo_to_ebitda(latest_valid, latest_period_str, _get_threshold(check_id)))

    # ---------------------------------------------------------------
    # B. WORKING CAPITAL
    # ---------------------------------------------------------------
    wc_checks_2period = [
        "wc.receivables_vs_revenue_growth",
        "wc.inventory_vs_revenue_growth",
        "wc.dso_change",
        "wc.dio_change",
        "wc.dpo_change",
        "wc.cash_conversion_cycle_change",
    ]
    for check_id in wc_checks_2period:
        if not _is_applicable(check_id):
            _add(_make_result(check_id, status=ForensicCheckStatus.NOT_APPLICABLE, period=latest_period_str), None)
            continue

        if latest_valid is None or prior_valid is None:
            _add(
                _make_result(
                    check_id,
                    status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
                    period=latest_period_str,
                    notes="need 2 valid periods",
                ),
                None,
            )
            continue

        period_str = latest_valid.period
        t = _get_threshold(check_id)

        if check_id == "wc.receivables_vs_revenue_growth":
            _add(
                *_check_growth_vs_revenue(
                    check_id,
                    "forensic_receivables_vs_revenue_growth",
                    "accounts_receivable",
                    latest_valid.accounts_receivable,
                    prior_valid.accounts_receivable,
                    latest_valid,
                    prior_valid,
                    period_str,
                    t,
                )
            )
        elif check_id == "wc.inventory_vs_revenue_growth":
            _add(
                *_check_growth_vs_revenue(
                    check_id,
                    "forensic_inventory_vs_revenue_growth",
                    "inventory",
                    latest_valid.inventory,
                    prior_valid.inventory,
                    latest_valid,
                    prior_valid,
                    period_str,
                    t,
                )
            )
        elif check_id == "wc.dso_change":
            _add(
                *_check_days_change(
                    check_id,
                    "forensic_dso_change",
                    latest_valid.accounts_receivable,
                    latest_valid.revenue,
                    prior_valid.accounts_receivable,
                    prior_valid.revenue,
                    period_str,
                    t,
                    "accounts_receivable",
                    "revenue",
                )
            )
        elif check_id == "wc.dio_change":
            _add(
                *_check_days_change(
                    check_id,
                    "forensic_dio_change",
                    latest_valid.inventory,
                    latest_valid.cost_of_goods_sold,
                    prior_valid.inventory,
                    prior_valid.cost_of_goods_sold,
                    period_str,
                    t,
                    "inventory",
                    "cogs",
                )
            )
        elif check_id == "wc.dpo_change":
            _add(
                *_check_days_change(
                    check_id,
                    "forensic_dpo_change",
                    latest_valid.accounts_payable,
                    latest_valid.cost_of_goods_sold,
                    prior_valid.accounts_payable,
                    prior_valid.cost_of_goods_sold,
                    period_str,
                    t,
                    "accounts_payable",
                    "cogs",
                )
            )
        elif check_id == "wc.cash_conversion_cycle_change":
            _add(*_check_ccc_change(latest_valid, prior_valid, period_str, t))

    # ---------------------------------------------------------------
    # C. CASH FLOW QUALITY
    # ---------------------------------------------------------------
    for check_id in [
        "cf.negative_cfo_count",
        "cf.negative_fcf_count",
        "cf.cfo_to_ebitda_level",
        "cf.capex_intensity_change",
    ]:
        if not _is_applicable(check_id):
            _add(_make_result(check_id, status=ForensicCheckStatus.NOT_APPLICABLE, period=latest_period_str), None)
            continue

        if check_id == "cf.negative_cfo_count":
            _add(
                *_check_negative_count(
                    check_id, "forensic_negative_cfo_count", valid_fins, "cfo", _get_threshold(check_id)
                )
            )

        elif check_id == "cf.negative_fcf_count":
            _add(
                *_check_negative_count(
                    check_id, "forensic_negative_fcf_count", valid_fins, "fcf", _get_threshold(check_id)
                )
            )

        elif check_id == "cf.cfo_to_ebitda_level":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_cfo_to_ebitda_level(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "cf.capex_intensity_change":
            if latest_valid is None or prior_valid is None:
                _add(
                    _make_result(
                        check_id,
                        status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
                        period=latest_period_str,
                        notes="need 2 valid periods",
                    ),
                    None,
                )
            else:
                _add(
                    *_check_capex_intensity_change(
                        latest_valid, prior_valid, latest_period_str, _get_threshold(check_id)
                    )
                )

    # ---------------------------------------------------------------
    # D. LEVERAGE
    # ---------------------------------------------------------------
    for check_id in ["lv.debt_to_equity", "lv.net_debt_to_ebitda", "lv.interest_coverage", "lv.leverage_trend"]:
        if not _is_applicable(check_id):
            _add(_make_result(check_id, status=ForensicCheckStatus.NOT_APPLICABLE, period=latest_period_str), None)
            continue

        if check_id == "lv.debt_to_equity":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_debt_to_equity(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "lv.net_debt_to_ebitda":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_net_debt_to_ebitda(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "lv.interest_coverage":
            if latest_valid is None:
                _add(
                    _make_result(
                        check_id, status=ForensicCheckStatus.NOT_COMPUTABLE, period="N/A", notes="no valid periods"
                    ),
                    None,
                )
            else:
                _add(*_check_interest_coverage(latest_valid, latest_period_str, _get_threshold(check_id)))

        elif check_id == "lv.leverage_trend":
            if latest_valid is None or prior_valid is None:
                _add(
                    _make_result(
                        check_id,
                        status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
                        period=latest_period_str,
                        notes="need 2 valid periods",
                    ),
                    None,
                )
            else:
                _add(*_check_leverage_trend(latest_valid, prior_valid, latest_period_str, _get_threshold(check_id)))

    # ---------------------------------------------------------------
    # E. PROFITABILITY
    # ---------------------------------------------------------------
    for check_id in [
        "pr.gross_margin_decline",
        "pr.ebitda_margin_decline",
        "pr.net_margin_decline",
        "pr.profit_vs_cashflow_divergence",
    ]:
        if not _is_applicable(check_id):
            _add(_make_result(check_id, status=ForensicCheckStatus.NOT_APPLICABLE, period=latest_period_str), None)
            continue

        if check_id == "pr.gross_margin_decline":
            _add(
                *_check_margin_decline(
                    check_id,
                    "forensic_gross_margin_decline",
                    valid_fins,
                    "gross",
                    _get_threshold(check_id),
                )
            )
        elif check_id == "pr.ebitda_margin_decline":
            _add(
                *_check_margin_decline(
                    check_id,
                    "forensic_ebitda_margin_decline",
                    valid_fins,
                    "ebitda",
                    _get_threshold(check_id),
                )
            )
        elif check_id == "pr.net_margin_decline":
            _add(
                *_check_margin_decline(
                    check_id,
                    "forensic_net_margin_decline",
                    valid_fins,
                    "net",
                    _get_threshold(check_id),
                )
            )
        elif check_id == "pr.profit_vs_cashflow_divergence":
            if latest_valid is None or prior_valid is None:
                _add(
                    _make_result(
                        check_id,
                        status=ForensicCheckStatus.INSUFFICIENT_HISTORY,
                        period=latest_period_str,
                        notes="need 2 valid periods",
                    ),
                    None,
                )
            else:
                _add(
                    *_check_profit_vs_cashflow_divergence(
                        latest_valid, prior_valid, latest_period_str, _get_threshold(check_id)
                    )
                )

    # ---------------------------------------------------------------
    # Beneish components
    # ---------------------------------------------------------------
    beneish_components: dict[str, Decimal | None] = {
        "dsri": None,
        "gmi": None,
        "aqi": None,
        "sgi": None,
        "tata": None,
    }
    beneish_status = ForensicCheckStatus.NOT_COMPUTABLE

    if company_type == CompanyType.FINANCIAL:
        beneish_status = ForensicCheckStatus.NOT_APPLICABLE
    elif latest_valid is not None and prior_valid is not None:
        period_str = latest_valid.period

        dsri, dsri_calc = _beneish_dsri(latest_valid, prior_valid, period_str)
        beneish_components["dsri"] = dsri
        if dsri_calc:
            all_calcs.append(dsri_calc)

        gmi, gmi_calc = _beneish_gmi(latest_valid, prior_valid, period_str)
        beneish_components["gmi"] = gmi
        if gmi_calc:
            all_calcs.append(gmi_calc)

        sgi, sgi_calc = _beneish_sgi(latest_valid, prior_valid, period_str)
        beneish_components["sgi"] = sgi
        if sgi_calc:
            all_calcs.append(sgi_calc)

        tata, tata_calc = _beneish_tata(latest_valid, period_str)
        beneish_components["tata"] = tata
        if tata_calc:
            all_calcs.append(tata_calc)

    # ---------------------------------------------------------------
    # Altman components
    # ---------------------------------------------------------------
    altman_components: dict[str, Decimal | None] = {
        "x1": None,
        "x2": None,
        "x3": None,
        "x4": None,
        "x5": None,
    }
    altman_status = ForensicCheckStatus.NOT_COMPUTABLE

    if company_type == CompanyType.FINANCIAL:
        altman_status = ForensicCheckStatus.NOT_APPLICABLE
    elif latest_valid is not None:
        period_str = latest_valid.period

        x1, x1_calc = _altman_x1(latest_valid, period_str)
        altman_components["x1"] = x1
        if x1_calc:
            all_calcs.append(x1_calc)

        x3, x3_calc = _altman_x3(latest_valid, period_str)
        altman_components["x3"] = x3
        if x3_calc:
            all_calcs.append(x3_calc)

        x4, x4_calc, x4_status = _altman_x4(latest_valid, market_cap, period_str)
        altman_components["x4"] = x4
        if x4_calc:
            all_calcs.append(x4_calc)

        x5, x5_calc = _altman_x5(latest_valid, period_str)
        altman_components["x5"] = x5
        if x5_calc:
            all_calcs.append(x5_calc)

    # ---------------------------------------------------------------
    # Category summaries
    # ---------------------------------------------------------------
    category_summaries = _build_category_summaries(all_checks)

    return ForensicResult(
        checks=all_checks,
        category_summaries=category_summaries,
        beneish_components=beneish_components,
        beneish_score=None,
        beneish_status=beneish_status,
        altman_components=altman_components,
        altman_score=None,
        altman_zone=None,
        altman_status=altman_status,
        diagnostics=diagnostics,
        periods_analyzed=[p.financials.period for p in periods],  # type: ignore[attr-defined]
        observation_date=observation_date,
        company_type=company_type,
        calculated_at=calculated_at,
        engine_version=ENGINE_VERSION,
        calculations=all_calcs,
    )
