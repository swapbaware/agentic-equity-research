"""Data types returned by provider interfaces.

These are the boundary types between the provider layer and the application.
All financial values use Decimal. No vendor-specific types leak past this layer.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.providers.provenance import DataProvenance

# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    price: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None
    market_cap: Decimal | None = None
    timestamp: datetime
    currency: str = "INR"
    provenance: DataProvenance | None = None


class PriceBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal | None = None
    provenance: DataProvenance | None = None


class CompanySearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    name: str
    isin: str | None = None


# ---------------------------------------------------------------------------
# Financial data
# ---------------------------------------------------------------------------


class FinancialStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    statement_type: str
    period_type: str
    period: str
    filing_date: date | None = None
    currency: str = "INR"
    line_items: dict[str, Decimal]
    provenance: DataProvenance | None = None


# ---------------------------------------------------------------------------
# Corporate filings
# ---------------------------------------------------------------------------


class Filing(BaseModel):
    model_config = ConfigDict(frozen=True)

    filing_id: str
    symbol: str
    exchange: str
    filing_type: str
    title: str
    filing_date: date
    url: str | None = None
    provenance: DataProvenance | None = None


class FilingDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    filing_id: str
    content: str
    content_type: str
    url: str | None = None


# ---------------------------------------------------------------------------
# Shareholding
# ---------------------------------------------------------------------------


class ShareholderCategory(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    percentage: Decimal
    shares: int | None = None


class ShareholdingPattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    quarter: str
    date: date
    categories: list[ShareholderCategory]
    total_shares: int | None = None
    pledged_percentage: Decimal | None = None


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------


class CorporateActionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    action_type: str
    ex_date: date | None = None
    record_date: date | None = None
    details: str
    value: Decimal | None = None
    provenance: DataProvenance | None = None


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


class NewsArticle(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    source: str
    published_at: datetime
    summary: str | None = None
    symbols: list[str] = []


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str


# ---------------------------------------------------------------------------
# Macro data
# ---------------------------------------------------------------------------


class MacroIndicatorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator_id: str
    name: str
    description: str | None = None
    source: str
    frequency: str
    unit: str


class MacroDataPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    value: Decimal


class MacroSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator_id: str
    name: str
    unit: str
    data_points: list[MacroDataPoint]


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker: str | None = None
    role: str | None = None
    text: str


class TranscriptSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    quarter: str
    year: int
    date: date
    title: str


class Transcript(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    quarter: str
    year: int
    date: date
    title: str
    segments: list[TranscriptSegment]
    raw_text: str | None = None


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int
    output_tokens: int
    total_tokens: int


class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, object]


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, object]
    result: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: list[ToolCall] | None = None


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    model: str
    usage: TokenUsage
    finish_reason: str
    tool_calls: list[ToolCall] = []
    response_id: str | None = None
    cost_usd: Decimal | None = None


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class EmbeddingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    embeddings: list[list[float]]
    model: str
    usage: TokenUsage


# ---------------------------------------------------------------------------
# Provider health
# ---------------------------------------------------------------------------


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_name: str
    is_healthy: bool
    latency_ms: float | None = None
    message: str | None = None
    checked_at: datetime
