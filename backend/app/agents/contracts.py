"""Typed contracts for the research agents.

Defines Pydantic v2 frozen models for:
- Research request and configuration
- Source candidate (generic across provider types)
- Tool I/O schemas (8 tools)
- LLM structured output schemas (evidence extraction, finding generation)
- Finding validation results
- Token budget tracking
- Step configuration
- Finding category constants
- Competitive Moat Agent contracts (Phase 10)
- Management & Governance Agent contracts (Phase 11)
- Future Growth & Optionality Agent contracts (Phase 12)
- Macro Economics Agent contracts (Phase 13)
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ConfidenceLevel,
    CorporateActionType,
    DocumentType,
    EvidenceType,
    FindingType,
    GrowthCategory,
    ManagementStatementCategory,
    ManagementStatementStatus,
    MoatStrength,
    MoatType,
    SourceTier,
)
from app.providers.types import MacroIndicatorInfo

# ---------------------------------------------------------------------------
# Company identifier type
# ---------------------------------------------------------------------------


class IdentifierType(enum.StrEnum):
    NSE_SYMBOL = "NSE_SYMBOL"
    BSE_CODE = "BSE_CODE"
    ISIN = "ISIN"


# ---------------------------------------------------------------------------
# Finding category constants
# ---------------------------------------------------------------------------

FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "company_identity",
        "business_overview",
        "business_model",
        "revenue_streams",
        "products_services",
        "revenue_drivers",
        "customer_exposure",
        "geographic_exposure",
        "management_claim",
        "growth_drivers",
        "competitive_context",
        "risk",
        "research_gap",
        "contradiction",
    }
)

# ---------------------------------------------------------------------------
# Token budget constants
# ---------------------------------------------------------------------------

AGENT_TOKEN_BUDGET: int = 30_000
AGENT_TOKEN_WARNING_THRESHOLD: int = 24_000
AGENT_NAME: str = "company_research_agent"
MAX_LLM_ATTEMPTS: int = 2

# ---------------------------------------------------------------------------
# Industry Research Agent constants
# ---------------------------------------------------------------------------

INDUSTRY_AGENT_TOKEN_BUDGET: int = 20_000
INDUSTRY_AGENT_TOKEN_WARNING: int = 16_000
INDUSTRY_AGENT_NAME: str = "industry_research_agent"

INDUSTRY_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "market_size",
        "growth_drivers",
        "entry_barriers",
        "supplier_power",
        "buyer_power",
        "substitution_risk",
        "competitive_rivalry",
        "regulatory_environment",
        "india_global_position",
        "industry_structure",
        "industry_risk",
        "cyclicality",
        "research_gap",
        "contradiction",
    }
)

# ---------------------------------------------------------------------------
# Research request and configuration
# ---------------------------------------------------------------------------


class CompanyResearchRequest(BaseModel):
    """Input contract for initiating a Company Research Agent run."""

    model_config = ConfigDict(frozen=True)

    company_identifier: str = Field(min_length=1, max_length=20)
    identifier_type: IdentifierType
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    configuration: CompanyResearchConfig | None = None


class CompanyResearchConfig(BaseModel):
    """Agent-level configuration for a Company Research Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=AGENT_TOKEN_WARNING_THRESHOLD, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    document_types: list[DocumentType] | None = None
    source_limit: int = Field(default=20, ge=1, le=100)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    generation_model: str | None = None
    analysis_model: str | None = None


# ---------------------------------------------------------------------------
# SourceCandidate — generic representation for any source type
# ---------------------------------------------------------------------------


class SourceCandidate(BaseModel):
    """A candidate source document discovered from any provider.

    Normalises Filing, TranscriptSummary, and NewsArticle into a single
    contract so downstream steps can process all source types uniformly.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=500)
    source_type: DocumentType
    provider: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=1000)
    publication_date: date | None = None
    document_date: date | None = None
    source_tier: SourceTier
    url: str | None = Field(default=None, max_length=2000)
    provider_metadata: dict[str, object] | None = None


# ---------------------------------------------------------------------------
# Tool 1: validate_company
# ---------------------------------------------------------------------------


class ValidateCompanyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    identifier: str = Field(min_length=1, max_length=20)
    identifier_type: IdentifierType


class ValidateCompanyOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    isin: str
    sector: str | None = None
    industry: str | None = None


# ---------------------------------------------------------------------------
# Tool 2: discover_sources
# ---------------------------------------------------------------------------


class DiscoverSourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class DiscoverSourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: list[SourceCandidate]


# ---------------------------------------------------------------------------
# Tool 3: retrieve_document
# ---------------------------------------------------------------------------


class RetrieveDocumentInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    filing_id: str = Field(min_length=1, max_length=500)
    provider: str | None = Field(default=None, max_length=50)


class RetrieveDocumentOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    content_type: str = Field(max_length=100)
    content_hash: str = Field(min_length=1, max_length=64)
    filing_id: str


# ---------------------------------------------------------------------------
# Tool 4: get_company_profile
# ---------------------------------------------------------------------------


class GetCompanyProfileInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID


class GetCompanyProfileOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    isin: str
    sector_id: uuid.UUID | None = None
    sector_name: str | None = None
    industry_id: uuid.UUID | None = None
    industry_name: str | None = None
    market_cap: Decimal | None = None
    incorporation_date: date | None = None
    listing_date: date | None = None
    website: str | None = None
    description: str | None = None
    registered_address: str | None = None
    business_segments: dict[str, object] | None = None
    major_products: dict[str, object] | None = None
    geographies: dict[str, object] | None = None
    is_active: bool


# ---------------------------------------------------------------------------
# Tool 5: search_company_news
# ---------------------------------------------------------------------------


class SearchCompanyNewsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=20)
    exchange: str = Field(min_length=1, max_length=10)
    observation_date: date
    limit: int = Field(default=10, ge=1, le=50)


class NewsArticleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None


class SearchCompanyNewsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    articles: list[NewsArticleResult]


# ---------------------------------------------------------------------------
# Tool 6: get_financial_summary
# ---------------------------------------------------------------------------


class GetFinancialSummaryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=20)
    exchange: str = Field(min_length=1, max_length=10)
    observation_date: date
    periods: int = Field(default=4, ge=1, le=20)


class FinancialStatementResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    statement_type: str
    period_type: str
    period: str
    filing_date: date | None = None
    currency: str
    line_items: dict[str, Decimal]


class GetFinancialSummaryOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    statements: list[FinancialStatementResult]


# ---------------------------------------------------------------------------
# Tool 7: persist_evidence
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A single evidence record to be persisted."""

    model_config = ConfigDict(frozen=True)

    evidence_type: EvidenceType
    claim: str = Field(min_length=1)
    context: str | None = None
    page_or_section: str | None = Field(default=None, max_length=200)
    confidence: ConfidenceLevel


class PersistEvidenceInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    evidences: list[EvidenceItem] = Field(min_length=1)


class PersistEvidenceOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Tool 8: persist_findings
# ---------------------------------------------------------------------------


class FindingItem(BaseModel):
    """A single research finding to be persisted."""

    model_config = ConfigDict(frozen=True)

    agent_name: str = Field(default=AGENT_NAME, max_length=100)
    finding_type: FindingType
    category: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    confidence: ConfidenceLevel
    observation_date: date | None = None
    source_publication_date: date | None = None
    evidence_ids: list[uuid.UUID] | None = None


class RejectedFinding(BaseModel):
    """Details of a finding that was rejected during persistence."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    reason: str


class PersistFindingsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: uuid.UUID
    execution_id: uuid.UUID
    findings: list[FindingItem] = Field(min_length=1)


class PersistFindingsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding_ids: list[uuid.UUID]
    rejected: list[RejectedFinding]


# ---------------------------------------------------------------------------
# LLM structured output — evidence extraction
# ---------------------------------------------------------------------------


class ExtractedEvidence(BaseModel):
    """Schema for a single evidence item extracted by the LLM."""

    model_config = ConfigDict(frozen=True)

    evidence_type: EvidenceType
    claim: str = Field(min_length=1)
    context: str | None = None
    page_or_section: str | None = Field(default=None, max_length=200)
    confidence: ConfidenceLevel


class EvidenceExtractionOutput(BaseModel):
    """Schema for LLM evidence extraction structured output."""

    model_config = ConfigDict(frozen=True)

    evidences: list[ExtractedEvidence]


# ---------------------------------------------------------------------------
# LLM structured output — finding generation
# ---------------------------------------------------------------------------


class GeneratedFinding(BaseModel):
    """Schema for a single finding generated by the LLM."""

    model_config = ConfigDict(frozen=True)

    finding_type: FindingType
    category: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    confidence: ConfidenceLevel
    source_publication_date: date | None = None
    evidence_indices: list[int] | None = None


class FindingGenerationOutput(BaseModel):
    """Schema for LLM finding generation structured output."""

    model_config = ConfigDict(frozen=True)

    findings: list[GeneratedFinding]


# ---------------------------------------------------------------------------
# Finding validation
# ---------------------------------------------------------------------------


class FindingValidationIssue(BaseModel):
    """A single validation issue found during finding validation."""

    model_config = ConfigDict(frozen=True)

    finding_index: int = Field(ge=0)
    issue_type: str = Field(min_length=1, max_length=100)
    message: str


class FindingValidationResult(BaseModel):
    """Result of finding validation (Step 6)."""

    model_config = ConfigDict(frozen=True)

    total_findings: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    issues: list[FindingValidationIssue]


# ---------------------------------------------------------------------------
# Token budget tracking
# ---------------------------------------------------------------------------


class TokenBudget(BaseModel):
    """Tracks cumulative token usage against the agent budget."""

    model_config = ConfigDict(frozen=False)

    budget: int = Field(default=AGENT_TOKEN_BUDGET, gt=0)
    warning_threshold: int = Field(default=AGENT_TOKEN_WARNING_THRESHOLD, gt=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.total_tokens)

    @property
    def is_warning(self) -> bool:
        return self.total_tokens >= self.warning_threshold

    @property
    def is_exhausted(self) -> bool:
        return self.total_tokens >= self.budget

    @property
    def utilization_pct(self) -> Decimal:
        if self.budget == 0:
            return Decimal("100.00")
        return (Decimal(self.total_tokens) / Decimal(self.budget) * 100).quantize(Decimal("0.01"))

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


# ---------------------------------------------------------------------------
# Step configuration
# ---------------------------------------------------------------------------

STEP_TYPE_DETERMINISTIC: str = "deterministic"
STEP_TYPE_PROVIDER_CALL: str = "provider_call"
STEP_TYPE_LLM_REASONING: str = "llm_reasoning"


class StepDefinition(BaseModel):
    """Definition of a single workflow step."""

    model_config = ConfigDict(frozen=True)

    step_order: int = Field(ge=1, le=7)
    step_name: str = Field(min_length=1, max_length=100)
    step_type: str = Field(min_length=1, max_length=50)
    timeout_seconds: int = Field(gt=0)
    uses_llm: bool = False


COMPANY_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="company_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=5,
    ),
    StepDefinition(
        step_order=2,
        step_name="source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="finding_generation",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="finding_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="gap_contradiction_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=60,
        uses_llm=True,
    ),
)


# ---------------------------------------------------------------------------
# Industry Research Agent — request and configuration contracts
# ---------------------------------------------------------------------------


class IndustryResearchConfig(BaseModel):
    """Agent-level configuration for an Industry Research Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=INDUSTRY_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=INDUSTRY_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    document_types: list[DocumentType] | None = None
    source_limit: int = Field(default=30, ge=1, le=100)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    generation_model: str | None = None
    analysis_model: str | None = None


class IndustryResearchRequest(BaseModel):
    """Input contract for initiating an Industry Research Agent run."""

    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    company_context_id: uuid.UUID | None = None
    configuration: IndustryResearchConfig | None = None


# ---------------------------------------------------------------------------
# Industry Tool 1: validate_industry
# ---------------------------------------------------------------------------


class ValidateIndustryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID


class ValidateIndustryOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID
    name: str
    code: str
    level: str
    parent_sector_id: uuid.UUID | None = None
    parent_sector_name: str | None = None


# ---------------------------------------------------------------------------
# Industry Tool 2: discover_industry_sources
# ---------------------------------------------------------------------------


class DiscoverIndustrySourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID
    industry_name: str = Field(min_length=1, max_length=200)
    observation_date: date
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=30, ge=1, le=100)


class DiscoverIndustrySourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: list[SourceCandidate]


# ---------------------------------------------------------------------------
# Industry Tool 3: retrieve_industry_document
# ---------------------------------------------------------------------------


class RetrieveIndustryDocumentInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = Field(min_length=1, max_length=2000)
    source_id: str = Field(min_length=1, max_length=500)
    provider: str = Field(default="search", max_length=50)


class RetrieveIndustryDocumentOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    content_type: str = Field(default="text/plain", max_length=100)
    content_hash: str = Field(min_length=1, max_length=64)
    source_id: str


# ---------------------------------------------------------------------------
# Industry Tool 4: get_industry_profile
# ---------------------------------------------------------------------------


class GetIndustryProfileInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID


class GetIndustryProfileOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID
    name: str
    code: str
    level: str
    parent_sector_id: uuid.UUID | None = None
    parent_sector_name: str | None = None
    company_count: int = Field(ge=0)
    companies: list[IndustryCompanySummary]


class IndustryCompanySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    market_cap: Decimal | None = None
    is_active: bool


# ---------------------------------------------------------------------------
# Industry Tool 5: search_industry_news
# ---------------------------------------------------------------------------


class SearchIndustryNewsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_name: str = Field(min_length=1, max_length=200)
    observation_date: date
    limit: int = Field(default=10, ge=1, le=50)


class SearchIndustryNewsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    articles: list[NewsArticleResult]


INDUSTRY_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="industry_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=5,
    ),
    StepDefinition(
        step_order=2,
        step_name="industry_source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="industry_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="finding_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="gap_contradiction_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=60,
        uses_llm=True,
    ),
)


# ===========================================================================
# Competitive Moat Agent — constants and contracts (Phase 10)
# ===========================================================================

MOAT_AGENT_TOKEN_BUDGET: int = 25_000
MOAT_AGENT_TOKEN_WARNING: int = 20_000
MOAT_AGENT_NAME: str = "competitive_moat_agent"

MOAT_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "brand_moat",
        "cost_advantage_moat",
        "network_effect_moat",
        "switching_cost_moat",
        "distribution_moat",
        "scale_moat",
        "regulatory_moat",
        "intangible_asset_moat",
        "technology_moat",
        "ecosystem_moat",
        "customer_lock_in_moat",
        "structural_moat",
        "competitive_position",
        "moat_durability",
        "moat_threat",
        "counter_evidence",
        "moat_summary",
        "research_gap",
        "contradiction",
    }
)

MOAT_TYPE_TO_CATEGORY: dict[MoatType, str] = {
    MoatType.BRAND: "brand_moat",
    MoatType.COST_ADVANTAGE: "cost_advantage_moat",
    MoatType.NETWORK_EFFECT: "network_effect_moat",
    MoatType.SWITCHING_COST: "switching_cost_moat",
    MoatType.DISTRIBUTION: "distribution_moat",
    MoatType.SCALE: "scale_moat",
    MoatType.REGULATORY: "regulatory_moat",
    MoatType.IP: "intangible_asset_moat",
    MoatType.TECHNOLOGY: "technology_moat",
    MoatType.DATA: "technology_moat",
    MoatType.ECOSYSTEM: "ecosystem_moat",
    MoatType.CUSTOMER_EMBEDDEDNESS: "customer_lock_in_moat",
    MoatType.MANUFACTURING: "structural_moat",
    MoatType.SUPPLY_CHAIN: "structural_moat",
    MoatType.CAPITAL_ACCESS: "structural_moat",
    MoatType.LOCATION: "structural_moat",
}


# ---------------------------------------------------------------------------
# Competitive Moat Agent — request / config / result contracts
# ---------------------------------------------------------------------------


class MoatResearchConfig(BaseModel):
    """Agent-level configuration for a Competitive Moat Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=MOAT_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=MOAT_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    document_types: list[DocumentType] | None = None
    source_limit: int = Field(default=20, ge=1, le=100)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    analysis_model: str | None = None


class MoatResearchRequest(BaseModel):
    """Input contract for initiating a Competitive Moat Agent run."""

    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    configuration: MoatResearchConfig | None = None


class MoatResearchResult(BaseModel):
    """Output contract returned by CompetitiveMoatAgent.execute()."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(min_length=1, max_length=20)
    run_id: uuid.UUID | None = None
    finding_ids: list[uuid.UUID] = Field(default_factory=list)
    assessment_ids: list[uuid.UUID] = Field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Step 1: Company Context Load
# ---------------------------------------------------------------------------


class FindingSummary(BaseModel):
    """Compact representation of an existing finding for context loading."""

    model_config = ConfigDict(frozen=True)

    finding_id: uuid.UUID
    category: str
    finding_type: FindingType
    content: str
    confidence: ConfidenceLevel


class LoadContextInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    industry_id: uuid.UUID | None
    observation_date: date


class LoadContextOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    company_name: str
    nse_symbol: str | None
    industry_id: uuid.UUID | None
    industry_name: str | None
    company_findings: list[FindingSummary]
    industry_findings: list[FindingSummary]
    has_company_research: bool
    has_industry_research: bool


# ---------------------------------------------------------------------------
# Step 2: Moat Source Discovery
# ---------------------------------------------------------------------------


class DiscoverMoatSourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str
    nse_symbol: str | None
    industry_name: str | None
    observation_date: date
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class DiscoverMoatSourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: list[SourceCandidate]


# ---------------------------------------------------------------------------
# Step 5: Moat Analysis — LLM output schemas
# ---------------------------------------------------------------------------


class ThreatItem(BaseModel):
    """A single threat to a competitive moat, produced by LLM."""

    model_config = ConfigDict(frozen=True)

    description: str
    severity: str
    timeframe: str | None = None
    evidence_basis: str | None = None


class MoatAssessmentDraft(BaseModel):
    """LLM-produced assessment for one moat type (Step 5 output)."""

    model_config = ConfigDict(frozen=True)

    moat_type: str
    strength: str
    durability_years: int | None = None
    explanation: str
    threats: list[ThreatItem] | None = None
    competitor_comparison: dict[str, str] | None = None
    confidence: str
    evidence_indices: list[int] | None = None
    counter_evidence_indices: list[int] | None = None


class MoatAnalysisOutput(BaseModel):
    """LLM structured output from moat analysis (Step 5)."""

    model_config = ConfigDict(frozen=True)

    assessments: list[MoatAssessmentDraft]
    findings: list[GeneratedFinding]


# ---------------------------------------------------------------------------
# Step 6: Moat Validation
# ---------------------------------------------------------------------------


class MoatValidationIssue(BaseModel):
    """A single validation issue found during moat assessment validation."""

    model_config = ConfigDict(frozen=True)

    moat_type: str
    issue_type: str
    message: str
    action: str


class MoatValidationResult(BaseModel):
    """Result of moat assessment validation (Step 6)."""

    model_config = ConfigDict(frozen=True)

    total_assessments: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    downgraded_count: int = Field(ge=0)
    issues: list[MoatValidationIssue]


# ---------------------------------------------------------------------------
# Step 7: Durability & Challenge — LLM output schema
# ---------------------------------------------------------------------------


class DurabilityChallengeOutput(BaseModel):
    """LLM structured output from durability challenge (Step 7)."""

    model_config = ConfigDict(frozen=True)

    findings: list[GeneratedFinding]


# ---------------------------------------------------------------------------
# Moat Tool: get_peer_data
# ---------------------------------------------------------------------------


class GetPeerDataInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    industry_id: uuid.UUID
    limit: int = Field(default=5, ge=1, le=20)


class PeerCompanySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    name: str
    nse_symbol: str | None = None
    market_cap: Decimal | None = None


class GetPeerDataOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    peers: list[PeerCompanySummary]


# ---------------------------------------------------------------------------
# Moat Tool: persist_moat_assessments
# ---------------------------------------------------------------------------


class MoatAssessmentItem(BaseModel):
    """A single moat assessment ready for persistence (typed enum fields)."""

    model_config = ConfigDict(frozen=True)

    moat_type: MoatType
    strength: MoatStrength
    durability_years: int | None = None
    threats: list[dict[str, object]] | None = None
    competitor_comparison: dict[str, object] | None = None
    confidence: ConfidenceLevel
    explanation: str | None = None
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class PersistMoatAssessmentsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    assessments: list[MoatAssessmentItem] = Field(min_length=1)


class PersistMoatAssessmentsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Competitive Moat Agent — step definitions
# ---------------------------------------------------------------------------

MOAT_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="company_context_load",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=2,
        step_name="moat_source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="moat_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="moat_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="durability_challenge",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=60,
        uses_llm=True,
    ),
)


# ===========================================================================
# Management & Governance Agent — constants and contracts (Phase 11)
# ===========================================================================

GOVERNANCE_AGENT_TOKEN_BUDGET: int = 20_000
GOVERNANCE_AGENT_TOKEN_WARNING: int = 16_000
GOVERNANCE_AGENT_NAME: str = "management_governance_agent"

GOVERNANCE_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "management_claim",
        "promise_tracking",
        "shareholding",
        "promoter_pledge",
        "capital_allocation",
        "related_party_transaction",
        "auditor_qualification",
        "executive_compensation",
        "subsidiary_complexity",
        "equity_dilution",
        "governance_red_flag",
        "governance_general",
        "data_gap",
    }
)

GOVERNANCE_RED_FLAG_CATEGORIES: frozenset[str] = frozenset(
    {
        "promoter_pledge_elevation",
        "declining_promoter_holding",
        "auditor_qualification",
        "auditor_change",
        "related_party_materiality",
        "executive_compensation_excess",
        "promise_track_record",
        "equity_dilution",
        "subsidiary_opacity",
    }
)


# ---------------------------------------------------------------------------
# Management & Governance Agent — request / config / result contracts
# ---------------------------------------------------------------------------


class ManagementGovernanceConfig(BaseModel):
    """Agent-level configuration for a Management & Governance Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=GOVERNANCE_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=GOVERNANCE_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    filing_types: list[str] | None = None
    shareholding_quarters: int = Field(default=8, ge=1, le=20)
    corporate_action_years: int = Field(default=5, ge=1, le=10)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    analysis_model: str | None = None


class ManagementGovernanceResearchRequest(BaseModel):
    """Input contract for initiating a Management & Governance Agent run."""

    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    configuration: ManagementGovernanceConfig | None = None


class ManagementGovernanceResult(BaseModel):
    """Output contract returned by ManagementGovernanceAgent.execute()."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(min_length=1, max_length=20)
    run_id: uuid.UUID
    finding_ids: list[uuid.UUID] = Field(default_factory=list)
    statement_ids: list[uuid.UUID] = Field(default_factory=list)
    shareholding_snapshot_ids: list[uuid.UUID] = Field(default_factory=list)
    pledge_snapshot_ids: list[uuid.UUID] = Field(default_factory=list)
    corporate_action_ids: list[uuid.UUID] = Field(default_factory=list)
    red_flag_count: int = Field(default=0, ge=0)
    total_findings: int = Field(default=0, ge=0)
    total_statements_created: int = Field(default=0, ge=0)
    total_statements_updated: int = Field(default=0, ge=0)
    error: str | None = None


# ---------------------------------------------------------------------------
# Step 1: Company Context Load
# ---------------------------------------------------------------------------


class ManagementStatementSummary(BaseModel):
    """Compact representation of an existing ManagementStatement for context loading."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    statement_date: date
    statement: str
    category: ManagementStatementCategory
    expected_outcome: str | None = None
    expected_timeframe: str | None = None
    status: ManagementStatementStatus


class LoadGovernanceContextInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date


class LoadGovernanceContextOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    company_name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    industry_name: str | None = None
    company_findings: list[FindingSummary]
    has_company_research: bool
    existing_statements: list[ManagementStatementSummary]


# ---------------------------------------------------------------------------
# Step 2: Governance Source Discovery
# ---------------------------------------------------------------------------


class ShareholdingSnapshot(BaseModel):
    """Normalized shareholding data from ShareholdingProvider."""

    model_config = ConfigDict(frozen=True)

    as_of_date: date
    quarter: str
    promoter_holding_pct: Decimal
    fii_holding_pct: Decimal
    dii_holding_pct: Decimal
    public_holding_pct: Decimal
    total_shares: int | None = None
    pledged_percentage: Decimal | None = None
    source_provider: str
    source_tier: int = 1


class CorporateActionSnapshot(BaseModel):
    """Normalized corporate action data from CorporateActionsProvider."""

    model_config = ConfigDict(frozen=True)

    action_type: CorporateActionType
    ex_date: date | None = None
    record_date: date | None = None
    details: str
    value: Decimal | None = None
    source_provider: str
    source_tier: int = 1


class DiscoverGovernanceSourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    company_name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    observation_date: date
    filing_types: list[str] | None = None
    shareholding_quarters: int = Field(default=8, ge=1, le=20)
    corporate_action_years: int = Field(default=5, ge=1, le=10)


class DiscoverGovernanceSourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    filing_candidates: list[SourceCandidate]
    shareholding_data: list[ShareholdingSnapshot]
    corporate_actions: list[CorporateActionSnapshot]
    provider_errors: list[str]
    data_gaps: list[str]


# ---------------------------------------------------------------------------
# Step 3: Document Retrieval
# ---------------------------------------------------------------------------


class RetrievedDocument(BaseModel):
    """A single retrieved governance document with metadata."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    title: str
    content: str
    document_date: date | None = None
    filing_date: date | None = None
    source_url: str | None = None
    source_tier: int
    content_hash: str


class RetrieveGovernanceDocumentsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    filing_candidates: list[SourceCandidate]


class RetrieveGovernanceDocumentsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: list[RetrievedDocument]
    retrieval_errors: list[str]
    total_attempted: int = Field(ge=0)
    total_retrieved: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Step 5: Governance Analysis — LLM output schemas
# ---------------------------------------------------------------------------


class NewManagementStatement(BaseModel):
    """A new management statement extracted by the LLM."""

    model_config = ConfigDict(frozen=True)

    statement: str
    statement_date: date
    category: str
    expected_outcome: str | None = None
    expected_timeframe: str | None = None
    evidence_index: int


class ManagementStatementUpdate(BaseModel):
    """A proposed update to an existing ManagementStatement."""

    model_config = ConfigDict(frozen=True)

    statement_id: str
    proposed_status: str
    actual_outcome: str | None = None
    outcome_evidence_index: int | None = None
    resolution_detail: str | None = None
    justification: str


class GovernanceRedFlag(BaseModel):
    """A governance red flag identified by the LLM."""

    model_config = ConfigDict(frozen=True)

    category: str
    description: str
    severity: str
    justification: str
    evidence_indices: list[int]


class GovernanceAnalysisOutput(BaseModel):
    """LLM structured output from governance analysis (Step 5)."""

    model_config = ConfigDict(frozen=True)

    new_management_statements: list[NewManagementStatement]
    statement_updates: list[ManagementStatementUpdate]
    capital_allocation_findings: list[GeneratedFinding]
    related_party_findings: list[GeneratedFinding]
    auditor_findings: list[GeneratedFinding]
    compensation_findings: list[GeneratedFinding]
    subsidiary_findings: list[GeneratedFinding]
    dilution_findings: list[GeneratedFinding]
    governance_red_flags: list[GovernanceRedFlag]
    general_findings: list[GeneratedFinding]


# ---------------------------------------------------------------------------
# Step 6: Governance Validation
# ---------------------------------------------------------------------------


class GovernanceValidationIssue(BaseModel):
    """A single validation issue found during governance validation."""

    model_config = ConfigDict(frozen=True)

    domain: str
    issue_type: str
    message: str
    action: str


class GovernanceValidationResult(BaseModel):
    """Result of governance validation (Step 6)."""

    model_config = ConfigDict(frozen=True)

    total_findings: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    statement_updates_valid: int = Field(ge=0)
    statement_updates_rejected: int = Field(ge=0)
    new_statements_valid: int = Field(ge=0)
    new_statements_rejected: int = Field(ge=0)
    red_flags_valid: int = Field(ge=0)
    red_flags_rejected: int = Field(ge=0)
    issues: list[GovernanceValidationIssue]
    rejected_statement_update_indices: frozenset[int] = Field(default_factory=frozenset)
    rejected_new_statement_indices: frozenset[int] = Field(default_factory=frozenset)
    rejected_red_flag_indices: frozenset[int] = Field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# Management & Governance Agent — tool I/O contracts
# ---------------------------------------------------------------------------


class GetShareholdingInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    nse_symbol: str | None = None
    bse_code: str | None = None
    observation_date: date
    quarters: int = Field(default=8, ge=1, le=20)


class GetShareholdingOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshots: list[ShareholdingSnapshot]
    provider_errors: list[str]


class GetCorporateActionsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    nse_symbol: str | None = None
    bse_code: str | None = None
    observation_date: date
    years: int = Field(default=5, ge=1, le=10)


class GetCorporateActionsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    actions: list[CorporateActionSnapshot]
    provider_errors: list[str]


class PersistStatementsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    new_statements: list[NewManagementStatement] = Field(default_factory=list)
    statement_updates: list[ManagementStatementUpdate] = Field(default_factory=list)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class PersistStatementsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    created_ids: list[uuid.UUID]
    updated_ids: list[uuid.UUID]
    rejected_count: int = Field(default=0, ge=0)


class PersistShareholdingInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    snapshots: list[ShareholdingSnapshot] = Field(min_length=1)


class PersistShareholdingOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    persisted_ids: list[uuid.UUID]
    skipped_count: int = Field(default=0, ge=0)


class PersistGovernanceDataInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    pledge_snapshots: list[ShareholdingSnapshot] = Field(default_factory=list)
    corporate_actions: list[CorporateActionSnapshot] = Field(default_factory=list)


class PersistGovernanceDataOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    pledge_ids: list[uuid.UUID]
    corporate_action_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Management & Governance Agent — step definitions
# ---------------------------------------------------------------------------

GOVERNANCE_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="company_context_load",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=2,
        step_name="governance_source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="governance_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="governance_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="persistence",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=30,
    ),
)


# ===========================================================================
# Future Growth & Optionality Agent — constants and contracts (Phase 12)
# ===========================================================================

GROWTH_AGENT_TOKEN_BUDGET: int = 20_000
GROWTH_AGENT_TOKEN_WARNING: int = 16_000
GROWTH_AGENT_NAME: str = "future_growth_agent"
GROWTH_AGENT_RUN_TYPE: str = "future_growth"

GROWTH_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "growth_opportunity",
        "growth_quality",
        "future_optionality",
        "tam_estimate",
        "growth_trajectory",
        "theme_alignment",
        "management_growth_claim",
        "growth_risk",
        "growth_challenge",
        "maturity_classification",
        "growth_score_rationale",
        "optionality_score_rationale",
        "research_gap",
        "contradiction",
    }
)

INDIA_STRUCTURAL_THEMES: tuple[str, ...] = (
    "artificial_intelligence",
    "data_centres",
    "semiconductors",
    "defence_indigenisation",
    "electric_vehicles",
    "renewable_energy",
    "pharma_innovation",
    "digital_payments",
    "manufacturing_pli",
    "infrastructure",
)

GROWTH_CATEGORY_TO_FINDING_CATEGORY: dict[GrowthCategory, str] = {
    GrowthCategory.NEW_PRODUCT: "growth_opportunity",
    GrowthCategory.NEW_MARKET: "growth_opportunity",
    GrowthCategory.ACQUISITION: "growth_opportunity",
    GrowthCategory.PARTNERSHIP: "growth_opportunity",
    GrowthCategory.GOVERNMENT_INCENTIVE: "growth_opportunity",
    GrowthCategory.TECHNOLOGY: "growth_opportunity",
    GrowthCategory.EXPANSION: "growth_opportunity",
}


# ---------------------------------------------------------------------------
# Future Growth Agent — request / config / result contracts
# ---------------------------------------------------------------------------


class FutureGrowthConfig(BaseModel):
    """Agent-level configuration for a Future Growth & Optionality Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=GROWTH_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=GROWTH_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    source_limit: int = Field(default=20, ge=1, le=100)
    max_documents: int = Field(default=8, ge=1, le=30)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    max_opportunities: int = Field(default=15, ge=1, le=50)
    extraction_model: str | None = None
    analysis_model: str | None = None
    challenge_model: str | None = None


class FutureGrowthResearchRequest(BaseModel):
    """Input contract for initiating a Future Growth & Optionality Agent run."""

    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    configuration: FutureGrowthConfig | None = None


class FutureGrowthResult(BaseModel):
    """Output contract returned by FutureGrowthAgent.execute()."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(min_length=1, max_length=20)
    run_id: uuid.UUID
    opportunities: list[uuid.UUID] = Field(default_factory=list)
    findings_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    growth_quality_score: int | None = None
    future_optionality_score: int | None = None
    validation_result: GrowthValidationResult | None = None
    steps_completed: int = Field(default=0, ge=0)
    steps_total: int = Field(default=7, ge=1)
    token_usage: TokenBudget | None = None
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: Company Context Load
# ---------------------------------------------------------------------------


class LoadGrowthContextInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    observation_date: date


class LoadGrowthContextOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str
    industry_name: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    company_findings: list[FindingSummary] = Field(default_factory=list)
    industry_findings: list[FindingSummary] = Field(default_factory=list)
    moat_context: str | None = None
    management_statements: list[ManagementStatementSummary] = Field(default_factory=list)
    existing_opportunities: list[uuid.UUID] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 2: Growth Source Discovery
# ---------------------------------------------------------------------------


class DiscoverGrowthSourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str
    industry_name: str | None = None
    nse_symbol: str | None = None
    observation_date: date
    search_themes: list[str] = Field(default_factory=list)


class DiscoverGrowthSourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: list[SourceCandidate] = Field(default_factory=list)
    provider_errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 5: Growth Analysis — LLM output schemas
# ---------------------------------------------------------------------------


class GrowthOpportunityDraft(BaseModel):
    """LLM-produced draft of a single growth opportunity (Step 5 output)."""

    model_config = ConfigDict(frozen=True)

    opportunity_name: str = Field(max_length=500)
    category: str
    maturity: str
    addressable_market: Decimal | None = None
    tam_methodology: str | None = None
    tam_low: Decimal | None = None
    tam_high: Decimal | None = None
    timeline_years: int | None = None
    confidence: str
    evidence_indices: list[int] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rationale: str


class GrowthScoreComponent(BaseModel):
    """A single sub-score component for Growth Quality or Future Optionality."""

    model_config = ConfigDict(frozen=True)

    component_name: str
    score: int = Field(ge=0, le=100)
    rationale: str
    evidence_indices: list[int] = Field(default_factory=list)


class GrowthAnalysisOutput(BaseModel):
    """LLM structured output from growth analysis (Step 5)."""

    model_config = ConfigDict(frozen=True)

    opportunities: list[GrowthOpportunityDraft] = Field(default_factory=list)
    growth_quality_scores: list[GrowthScoreComponent] = Field(default_factory=list)
    future_optionality_scores: list[GrowthScoreComponent] = Field(default_factory=list)
    growth_vs_optionality_separation: str
    themes_identified: list[str] = Field(default_factory=list)
    findings: list[FindingItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 6: Growth Validation
# ---------------------------------------------------------------------------


class GrowthValidationIssue(BaseModel):
    """A single validation issue found during growth validation."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    severity: str
    opportunity_name: str | None = None
    message: str


class GrowthValidationResult(BaseModel):
    """Result of growth validation (Step 6)."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    issues: list[GrowthValidationIssue] = Field(default_factory=list)
    downgraded_maturities: list[tuple[str, str, str]] = Field(default_factory=list)
    nullified_tams: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 7: Growth Challenge — LLM output schema
# ---------------------------------------------------------------------------


class GrowthChallengeItem(BaseModel):
    """LLM-produced challenge for a single growth opportunity (Step 7 output)."""

    model_config = ConfigDict(frozen=True)

    opportunity_name: str
    challenge: str
    tam_challenge: str | None = None
    competitive_risk: str | None = None
    execution_risk: str | None = None
    revised_confidence: str | None = None
    evidence_indices: list[int] = Field(default_factory=list)


class GrowthChallengeOutput(BaseModel):
    """LLM structured output from growth challenge (Step 7)."""

    model_config = ConfigDict(frozen=True)

    challenges: list[GrowthChallengeItem] = Field(default_factory=list)
    overall_optimism_assessment: str
    findings: list[FindingItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Growth Agent — tool I/O contracts
# ---------------------------------------------------------------------------


class PersistGrowthOpportunitiesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    opportunities: list[GrowthOpportunityDraft] = Field(min_length=1)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class PersistGrowthOpportunitiesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    opportunity_ids: list[uuid.UUID]


class PersistGrowthScoresInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    growth_quality_score: int = Field(ge=0, le=100)
    future_optionality_score: int = Field(ge=0, le=100)
    growth_quality_components: list[GrowthScoreComponent] = Field(default_factory=list)
    future_optionality_components: list[GrowthScoreComponent] = Field(default_factory=list)


class PersistGrowthScoresOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    growth_quality_score_id: uuid.UUID
    future_optionality_score_id: uuid.UUID


# ---------------------------------------------------------------------------
# Future Growth Agent — step definitions
# ---------------------------------------------------------------------------

GROWTH_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="context_load",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=2,
        step_name="source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="growth_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="growth_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="growth_challenge",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
)


# ===========================================================================
# Macro Economics Agent — constants and contracts (Phase 13)
# ===========================================================================

MACRO_AGENT_TOKEN_BUDGET: int = 20_000
MACRO_AGENT_TOKEN_WARNING: int = 16_000
MACRO_AGENT_NAME: str = "macro_economics_agent"
MACRO_AGENT_RUN_TYPE: str = "macro_economics"

MACRO_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        # Dimensional assessments
        "monetary_policy_assessment",
        "inflation_assessment",
        "growth_assessment",
        "fiscal_policy_assessment",
        "external_sector_assessment",
        "commodity_exposure",
        "credit_banking_assessment",
        "global_macro_assessment",
        # Transmission and impact
        "macro_transmission_channel",
        "sector_sensitivity",
        # Forward-looking
        "macro_risk",
        "macro_catalyst",
        "macro_scenario",
        # Data quality
        "data_gap",
        "data_contradiction",
    }
)

MACRO_DIMENSIONS: tuple[str, ...] = (
    "monetary_policy",
    "inflation",
    "growth",
    "fiscal_policy",
    "external_sector",
    "commodities",
    "credit_banking",
    "global",
)

REGIME_LABELS: dict[int, str] = {
    1: "VERY_RESTRICTIVE",
    2: "RESTRICTIVE",
    3: "NEUTRAL",
    4: "SUPPORTIVE",
    5: "VERY_SUPPORTIVE",
}


# ---------------------------------------------------------------------------
# Macro Economics Agent — request / config / result contracts
# ---------------------------------------------------------------------------


class MacroConfig(BaseModel):
    """Agent-level configuration for a Macro Economics Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=MACRO_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=MACRO_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    source_limit: int = Field(default=30, ge=1, le=100)
    max_documents: int = Field(default=10, ge=1, le=30)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    analysis_model: str | None = None
    challenge_model: str | None = None


class MacroResearchRequest(BaseModel):
    """Input contract for initiating a Macro Economics Agent run."""

    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    configuration: MacroConfig | None = None


class MacroEconomicsResult(BaseModel):
    """Output contract returned by MacroEconomicsAgent.execute()."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(min_length=1, max_length=20)
    run_id: uuid.UUID
    findings_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    indicators_persisted: int = Field(default=0, ge=0)
    regime_assessments_count: int = Field(default=0, ge=0)
    transmission_channels_count: int = Field(default=0, ge=0)
    macro_data_provider_available: bool = True
    validation_result: MacroValidationResult | None = None
    steps_completed: int = Field(default=0, ge=0)
    steps_total: int = Field(default=7, ge=1)
    token_usage: TokenBudget | None = None
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: Macro Context Load
# ---------------------------------------------------------------------------


class MacroIndicatorSnapshot(BaseModel):
    """A point-in-time snapshot of a single macro indicator value."""

    model_config = ConfigDict(frozen=True)

    indicator_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: Decimal
    unit: str = Field(min_length=1)
    as_of_date: date
    source: str = Field(min_length=1)


class LoadMacroContextInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: uuid.UUID
    research_run_id: uuid.UUID
    observation_date: date


class LoadMacroContextOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str
    sectors: list[str] = Field(default_factory=list)
    exchange: str = ""
    prior_findings: list[FindingSummary] = Field(default_factory=list)
    available_indicators: list[MacroIndicatorInfo] = Field(default_factory=list)
    indicator_snapshots: list[MacroIndicatorSnapshot] = Field(default_factory=list)
    unavailable_dimensions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 2: Macro Source Discovery
# ---------------------------------------------------------------------------


class DiscoverMacroSourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str = Field(min_length=1)
    sectors: list[str] = Field(default_factory=list)
    dimensions_to_search: list[str] = Field(default_factory=list)
    observation_date: date


class DiscoverMacroSourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: list[SourceCandidate] = Field(default_factory=list)
    dimensions_covered: list[str] = Field(default_factory=list)
    dimensions_still_missing: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 4: Evidence Extraction — LLM output schema
# ---------------------------------------------------------------------------


class MacroEvidenceExtractionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidences: list[ExtractedEvidence] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 5: Macro Analysis — LLM output schemas
# ---------------------------------------------------------------------------


class MacroRegimeAssessment(BaseModel):
    """Dimensional regime classification for one macro dimension."""

    model_config = ConfigDict(frozen=True)

    dimension: str = Field(min_length=1)
    regime_level: int = Field(ge=1, le=5)
    regime_label: str = Field(min_length=1)
    confidence: ConfidenceLevel
    rationale: str = Field(min_length=1)
    supporting_indicators: list[str] = Field(default_factory=list)
    evidence_indices: list[int] = Field(default_factory=list)


class MacroTransmissionChannel(BaseModel):
    """Describes how a macro condition affects a sector or company."""

    model_config = ConfigDict(frozen=True)

    macro_dimension: str = Field(min_length=1)
    indicator_name: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    affected_sector: str = Field(min_length=1)
    impact_direction: str = Field(min_length=1)
    impact_magnitude: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    confidence: ConfidenceLevel


class SectorMacroSensitivity(BaseModel):
    """Sector-level macro sensitivity profile."""

    model_config = ConfigDict(frozen=True)

    sector: str = Field(min_length=1)
    dimension_sensitivities: dict[str, str] = Field(default_factory=dict)
    key_transmission_channels: list[str] = Field(default_factory=list)
    overall_macro_exposure: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class MacroAnalysisOutput(BaseModel):
    """LLM structured output from macro analysis (Step 5)."""

    model_config = ConfigDict(frozen=True)

    regime_assessments: list[MacroRegimeAssessment] = Field(default_factory=list)
    transmission_channels: list[MacroTransmissionChannel] = Field(default_factory=list)
    sector_sensitivity: SectorMacroSensitivity | None = None
    findings: list[GeneratedFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 6: Macro Validation
# ---------------------------------------------------------------------------


class MacroValidationIssue(BaseModel):
    """A single validation issue found during macro validation."""

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(min_length=1, max_length=10)
    severity: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MacroValidationResult(BaseModel):
    """Result of macro validation (Step 6)."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    issues: list[MacroValidationIssue] = Field(default_factory=list)
    findings_corrected: int = Field(default=0, ge=0)
    findings_rejected: int = Field(default=0, ge=0)
    regimes_clamped: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Step 7: Macro Challenge — LLM output schemas
# ---------------------------------------------------------------------------


class MacroChallengeItem(BaseModel):
    """A single challenge raised against a macro assessment."""

    model_config = ConfigDict(frozen=True)

    dimension: str = Field(min_length=1)
    challenge: str = Field(min_length=1)
    alternative_interpretation: str | None = None
    risk: str | None = None
    catalyst: str | None = None
    evidence_indices: list[int] = Field(default_factory=list)


class MacroChallengeOutput(BaseModel):
    """LLM structured output from macro challenge (Step 7)."""

    model_config = ConfigDict(frozen=True)

    challenges: list[MacroChallengeItem] = Field(default_factory=list)
    findings: list[GeneratedFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Macro Economics Agent — deterministic calculation contracts
# ---------------------------------------------------------------------------


class IndicatorTrend(BaseModel):
    """Deterministic trend calculation for a time-series indicator."""

    model_config = ConfigDict(frozen=True)

    indicator_id: str = Field(min_length=1)
    current_value: Decimal
    current_date: date
    prior_value: Decimal | None = None
    prior_date: date | None = None
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None
    direction: str = Field(min_length=1)
    data_points_available: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Macro Economics Agent — tool I/O contracts
# ---------------------------------------------------------------------------


class PersistMacroIndicatorsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    research_run_id: uuid.UUID
    snapshots: list[MacroIndicatorSnapshot] = Field(min_length=1)
    country: str = Field(default="IN", min_length=1, max_length=10)


class PersistMacroIndicatorsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator_ids: list[uuid.UUID]
    persisted_count: int = Field(ge=0)


class ComputeIndicatorTrendsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator_id: str = Field(min_length=1)
    data_points: list[tuple[date, Decimal]] = Field(min_length=1)
    observation_date: date


class ComputeIndicatorTrendsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    trend: IndicatorTrend


# ---------------------------------------------------------------------------
# Macro Economics Agent — step definitions
# ---------------------------------------------------------------------------

MACRO_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="context_load",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=2,
        step_name="macro_source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="macro_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="macro_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="macro_challenge",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
)
