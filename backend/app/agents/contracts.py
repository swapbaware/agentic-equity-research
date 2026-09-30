"""Typed contracts for the Company Research Agent.

Defines Pydantic v2 frozen models for:
- Research request and configuration
- Source candidate (generic across provider types)
- Tool I/O schemas (8 tools)
- LLM structured output schemas (evidence extraction, finding generation)
- Finding validation results
- Token budget tracking
- Step configuration
- Finding category constants
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    SourceTier,
)

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
    publication_date: date
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
