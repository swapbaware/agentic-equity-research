"""Domain models for the Financial Forensics / Red Flag Screening Engine.

All models are frozen Pydantic v2 BaseModels. Financial values use
decimal.Decimal exclusively — never float.
"""

from __future__ import annotations

import enum
from datetime import date, datetime  # noqa: TC003 — Pydantic needs at runtime
from decimal import Decimal  # noqa: TC003

from pydantic import BaseModel, ConfigDict

from app.analytics.models import CalculationResult  # noqa: TC002
from app.models.enums import FindingType  # noqa: TC002

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ForensicCheckStatus(enum.StrEnum):
    FLAGGED = "flagged"
    PASS = "pass"
    NOT_COMPUTABLE = "not_computable"
    INVALID_INPUT = "invalid_input"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_HISTORY = "insufficient_history"
    UNVERIFIED_TIMING = "unverified_timing"
    LOOK_AHEAD_RISK = "look_ahead_risk"


class ForensicSeverity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ForensicCategory(enum.StrEnum):
    EARNINGS_QUALITY = "earnings_quality"
    WORKING_CAPITAL = "working_capital"
    CASH_FLOW_QUALITY = "cash_flow_quality"
    LEVERAGE = "leverage"
    PROFITABILITY = "profitability"


class ThresholdDirection(enum.StrEnum):
    ABOVE = "above"
    BELOW = "below"


class ThresholdClassification(enum.StrEnum):
    PUBLISHED_MODEL = "published_model"
    ACCOUNTING_IDENTITY = "accounting_identity"
    PLATFORM_HEURISTIC = "platform_heuristic"


class CompanyType(enum.StrEnum):
    GENERAL = "general"
    FINANCIAL = "financial"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class ForensicPeriodInput(BaseModel):
    """Wraps PeriodFinancials with point-in-time timing metadata."""

    model_config = ConfigDict(frozen=True)

    financials: object  # PeriodFinancials — forward ref avoids circular import
    financial_period_end: date
    financials_available_date: date | None = None
    source_description: str | None = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ThresholdConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: Decimal | None = None
    medium: Decimal | None = None
    high: Decimal | None = None
    critical: Decimal | None = None
    direction: ThresholdDirection
    classification: ThresholdClassification
    rationale: str


class ForensicConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    thresholds: dict[str, ThresholdConfig]


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


class DataQualityDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: str
    field: str
    issue: str
    observed_values: dict[str, Decimal | None]


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------


class ForensicCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    category: ForensicCategory
    status: ForensicCheckStatus
    severity: ForensicSeverity | None = None
    observed_value: Decimal | None = None
    threshold: Decimal | None = None
    threshold_direction: ThresholdDirection | None = None
    threshold_classification: ThresholdClassification | None = None
    period: str
    finding_type: FindingType
    description: str
    calculation: CalculationResult | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Category summary
# ---------------------------------------------------------------------------


class ForensicCategorySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: ForensicCategory
    checks_total: int
    checks_evaluated: int
    checks_flagged: int
    checks_passed: int
    checks_not_computable: int
    checks_invalid_input: int
    checks_not_applicable: int
    checks_insufficient_history: int
    checks_unverified_timing: int
    checks_look_ahead_risk: int
    maximum_severity: ForensicSeverity | None = None
    data_coverage_ratio: Decimal | None = None


# ---------------------------------------------------------------------------
# Top-level result
# ---------------------------------------------------------------------------


class ForensicResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: list[ForensicCheckResult]
    category_summaries: list[ForensicCategorySummary]

    beneish_components: dict[str, Decimal | None]
    beneish_score: Decimal | None
    beneish_status: ForensicCheckStatus

    altman_components: dict[str, Decimal | None]
    altman_score: Decimal | None
    altman_zone: str | None
    altman_status: ForensicCheckStatus

    diagnostics: list[DataQualityDiagnostic]
    periods_analyzed: list[str]
    observation_date: date
    company_type: CompanyType
    calculated_at: datetime
    engine_version: str
    calculations: list[CalculationResult]
