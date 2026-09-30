"""Domain enumerations for the equity research platform."""
import enum

# ---------------------------------------------------------------------------
# Company domain
# ---------------------------------------------------------------------------

class ClassificationLevel(enum.StrEnum):
    SECTOR = "SECTOR"
    INDUSTRY = "INDUSTRY"


class SecurityType(enum.StrEnum):
    EQUITY = "EQUITY"
    PREFERENCE = "PREFERENCE"
    DEBENTURE = "DEBENTURE"


# ---------------------------------------------------------------------------
# Financial domain
# ---------------------------------------------------------------------------

class StatementType(enum.StrEnum):
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    CASH_FLOW = "CASH_FLOW"


class PeriodType(enum.StrEnum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"


class MetricUnit(enum.StrEnum):
    CURRENCY = "CURRENCY"
    PERCENTAGE = "PERCENTAGE"
    RATIO = "RATIO"
    COUNT = "COUNT"


# ---------------------------------------------------------------------------
# Governance domain
# ---------------------------------------------------------------------------

class CorporateActionType(enum.StrEnum):
    DIVIDEND = "DIVIDEND"
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    BUYBACK = "BUYBACK"
    RIGHTS = "RIGHTS"
    MERGER = "MERGER"


# ---------------------------------------------------------------------------
# Research domain
# ---------------------------------------------------------------------------

class DocumentType(enum.StrEnum):
    ANNUAL_REPORT = "ANNUAL_REPORT"
    QUARTERLY_RESULT = "QUARTERLY_RESULT"
    INVESTOR_PRESENTATION = "INVESTOR_PRESENTATION"
    TRANSCRIPT = "TRANSCRIPT"
    FILING = "FILING"
    NEWS = "NEWS"
    RESEARCH_REPORT = "RESEARCH_REPORT"
    GOVERNMENT_PUBLICATION = "GOVERNMENT_PUBLICATION"


class SourceTier(enum.StrEnum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


class EvidenceType(enum.StrEnum):
    FACT = "FACT"
    FINANCIAL_DATA = "FINANCIAL_DATA"
    MANAGEMENT_STATEMENT = "MANAGEMENT_STATEMENT"
    ANALYST_OPINION = "ANALYST_OPINION"
    REGULATORY_FILING = "REGULATORY_FILING"


class ConfidenceLevel(enum.StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ManagementStatementCategory(enum.StrEnum):
    REVENUE_GUIDANCE = "REVENUE_GUIDANCE"
    MARGIN_GUIDANCE = "MARGIN_GUIDANCE"
    CAPEX_PLAN = "CAPEX_PLAN"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    EXPANSION = "EXPANSION"
    OTHER = "OTHER"


class ManagementStatementStatus(enum.StrEnum):
    PENDING = "PENDING"
    MET = "MET"
    PARTIALLY_MET = "PARTIALLY_MET"
    MISSED = "MISSED"
    UNKNOWN = "UNKNOWN"


class ResearchRunStatus(enum.StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class StepStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentExecutionStatus(enum.StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    TRUNCATED = "TRUNCATED"


class ArtifactType(enum.StrEnum):
    REPORT = "REPORT"
    ANALYSIS = "ANALYSIS"
    CHART_DATA = "CHART_DATA"
    CALCULATION_RESULT = "CALCULATION_RESULT"
    INTERMEDIATE_STATE = "INTERMEDIATE_STATE"


class FindingType(enum.StrEnum):
    FACT = "FACT"
    CALCULATION = "CALCULATION"
    MANAGEMENT_CLAIM = "MANAGEMENT_CLAIM"
    ANALYST_OPINION = "ANALYST_OPINION"
    AI_INFERENCE = "AI_INFERENCE"
    ASSUMPTION = "ASSUMPTION"
    UNCERTAINTY = "UNCERTAINTY"


class ClaimType(enum.StrEnum):
    FACT = "FACT"
    CALCULATION = "CALCULATION"
    MANAGEMENT_CLAIM = "MANAGEMENT_CLAIM"
    EXTERNAL_ANALYST_VIEW = "EXTERNAL_ANALYST_VIEW"
    AI_INFERENCE = "AI_INFERENCE"
    ASSUMPTION = "ASSUMPTION"


class SourceType(enum.StrEnum):
    EXCHANGE = "EXCHANGE"
    REGULATOR = "REGULATOR"
    COMPANY = "COMPANY"
    NEWS = "NEWS"
    RESEARCH_FIRM = "RESEARCH_FIRM"
    GOVERNMENT = "GOVERNMENT"
    INDUSTRY_BODY = "INDUSTRY_BODY"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Analysis domain
# ---------------------------------------------------------------------------

class MoatType(enum.StrEnum):
    BRAND = "BRAND"
    COST_ADVANTAGE = "COST_ADVANTAGE"
    NETWORK_EFFECT = "NETWORK_EFFECT"
    SWITCHING_COST = "SWITCHING_COST"
    DISTRIBUTION = "DISTRIBUTION"
    SCALE = "SCALE"
    REGULATORY = "REGULATORY"
    IP = "IP"
    TECHNOLOGY = "TECHNOLOGY"
    DATA = "DATA"
    ECOSYSTEM = "ECOSYSTEM"
    CUSTOMER_EMBEDDEDNESS = "CUSTOMER_EMBEDDEDNESS"
    MANUFACTURING = "MANUFACTURING"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    CAPITAL_ACCESS = "CAPITAL_ACCESS"
    LOCATION = "LOCATION"


class MoatStrength(enum.StrEnum):
    NONE = "NONE"
    NARROW = "NARROW"
    MODERATE = "MODERATE"
    WIDE = "WIDE"


class GrowthCategory(enum.StrEnum):
    NEW_PRODUCT = "NEW_PRODUCT"
    NEW_MARKET = "NEW_MARKET"
    ACQUISITION = "ACQUISITION"
    PARTNERSHIP = "PARTNERSHIP"
    GOVERNMENT_INCENTIVE = "GOVERNMENT_INCENTIVE"
    TECHNOLOGY = "TECHNOLOGY"
    EXPANSION = "EXPANSION"


class GrowthMaturity(enum.StrEnum):
    PROVEN = "PROVEN"
    COMMERCIALIZING = "COMMERCIALIZING"
    EARLY_STAGE = "EARLY_STAGE"
    EXPERIMENTAL = "EXPERIMENTAL"
    SPECULATIVE = "SPECULATIVE"


class CompetitorRelevance(enum.StrEnum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    POTENTIAL = "POTENTIAL"


# ---------------------------------------------------------------------------
# Valuation domain
# ---------------------------------------------------------------------------

class ValuationModelType(enum.StrEnum):
    PE = "PE"
    EV_EBITDA = "EV_EBITDA"
    PS = "PS"
    PB = "PB"
    PEG = "PEG"
    FCF_YIELD = "FCF_YIELD"
    EV_FCF = "EV_FCF"
    DCF = "DCF"
    REVERSE_DCF = "REVERSE_DCF"
    HISTORICAL_BAND = "HISTORICAL_BAND"
    PEER_COMPARISON = "PEER_COMPARISON"


class ScenarioType(enum.StrEnum):
    BEAR = "BEAR"
    BASE = "BASE"
    BULL = "BULL"


# ---------------------------------------------------------------------------
# Thesis domain
# ---------------------------------------------------------------------------

class RiskType(enum.StrEnum):
    BUSINESS = "BUSINESS"
    FINANCIAL = "FINANCIAL"
    VALUATION = "VALUATION"
    GOVERNANCE = "GOVERNANCE"
    REGULATORY = "REGULATORY"
    TECHNOLOGY = "TECHNOLOGY"
    DISRUPTION = "DISRUPTION"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"
    GEOPOLITICAL = "GEOPOLITICAL"
    CUSTOMER_CONCENTRATION = "CUSTOMER_CONCENTRATION"
    SUPPLIER_CONCENTRATION = "SUPPLIER_CONCENTRATION"
    EXECUTION = "EXECUTION"


class Severity(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Likelihood(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CatalystImpact(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ScoreDimension(enum.StrEnum):
    BUSINESS_QUALITY = "BUSINESS_QUALITY"
    FINANCIAL_QUALITY = "FINANCIAL_QUALITY"
    GROWTH_QUALITY = "GROWTH_QUALITY"
    MOAT_STRENGTH = "MOAT_STRENGTH"
    MANAGEMENT_QUALITY = "MANAGEMENT_QUALITY"
    FUTURE_OPTIONALITY = "FUTURE_OPTIONALITY"
    INDUSTRY_ATTRACTIVENESS = "INDUSTRY_ATTRACTIVENESS"
    VALUATION_ATTRACTIVENESS = "VALUATION_ATTRACTIVENESS"
    BALANCE_SHEET_STRENGTH = "BALANCE_SHEET_STRENGTH"
    RISK = "RISK"
