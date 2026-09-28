"""Provider Protocol interfaces.

Each Protocol defines the structural contract for one external service category.
Business logic depends on these Protocols, never on concrete implementations.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from app.providers.types import (
    ChatMessage,
    CompanySearchResult,
    CorporateActionRecord,
    EmbeddingResult,
    Filing,
    FilingDocument,
    FinancialStatement,
    LLMResponse,
    MacroIndicatorInfo,
    MacroSeries,
    NewsArticle,
    PriceBar,
    ProviderHealth,
    Quote,
    SearchResult,
    ShareholdingPattern,
    ToolDefinition,
    Transcript,
    TranscriptSummary,
)


@runtime_checkable
class MarketDataProvider(Protocol):
    async def get_quote(self, symbol: str, exchange: str) -> Quote: ...
    async def get_historical_prices(
        self, symbol: str, exchange: str, start: date, end: date
    ) -> list[PriceBar]: ...
    async def search_companies(self, query: str) -> list[CompanySearchResult]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class FinancialDataProvider(Protocol):
    async def get_financial_statements(
        self,
        symbol: str,
        exchange: str,
        statement_type: str,
        period_type: str,
    ) -> list[FinancialStatement]: ...
    async def get_financial_ratios(
        self, symbol: str, exchange: str
    ) -> dict[str, object]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class CorporateFilingsProvider(Protocol):
    async def get_filings(
        self,
        symbol: str,
        exchange: str,
        *,
        filing_type: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Filing]: ...
    async def get_filing_document(self, filing_id: str) -> FilingDocument: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class ShareholdingProvider(Protocol):
    async def get_shareholding_pattern(
        self, symbol: str, exchange: str, quarter: str
    ) -> ShareholdingPattern: ...
    async def get_shareholding_history(
        self, symbol: str, exchange: str, *, start: date | None = None, end: date | None = None
    ) -> list[ShareholdingPattern]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class CorporateActionsProvider(Protocol):
    async def get_corporate_actions(
        self,
        symbol: str,
        exchange: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateActionRecord]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class NewsProvider(Protocol):
    async def search_news(
        self, query: str, *, start: date | None = None, end: date | None = None, limit: int = 10
    ) -> list[NewsArticle]: ...
    async def get_company_news(
        self, symbol: str, exchange: str, *, limit: int = 10
    ) -> list[NewsArticle]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class SearchProvider(Protocol):
    async def search(self, query: str, *, num_results: int = 10) -> list[SearchResult]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class MacroDataProvider(Protocol):
    async def get_indicator(
        self, indicator_id: str, *, start: date | None = None, end: date | None = None
    ) -> MacroSeries: ...
    async def list_indicators(self) -> list[MacroIndicatorInfo]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class TranscriptProvider(Protocol):
    async def get_transcript(
        self, symbol: str, exchange: str, quarter: str, year: int
    ) -> Transcript: ...
    async def list_transcripts(self, symbol: str, exchange: str) -> list[TranscriptSummary]: ...
    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        response_schema: dict[str, object] | None = None,
    ) -> LLMResponse: ...

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse: ...

    async def check_health(self) -> ProviderHealth: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> EmbeddingResult: ...
    async def embed_single(
        self, text: str, *, model: str | None = None
    ) -> list[float]: ...
    async def check_health(self) -> ProviderHealth: ...
