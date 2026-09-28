# ADR-005: Provider Abstraction Pattern

## Status

Accepted

## Date

2026-09-28

## Context

The platform integrates with multiple external services:
- LLM providers (Anthropic, OpenAI, future models)
- Financial data providers (NSE, BSE, Alpha Vantage, Polygon.io)
- Search providers
- Embedding providers
- Object storage providers

Hard-coding any provider creates vendor lock-in, makes testing difficult, and violates clean architecture principles.

## Decision

Define abstract provider interfaces (Python `Protocol` or `ABC`) for each external service category. Concrete implementations are injected via dependency injection. Provider selection is configuration-driven.

## Provider Interfaces

```
MarketDataProvider       — Price data, market cap, trading data
FinancialDataProvider    — Financial statements, ratios
CorporateFilingsProvider — Annual reports, filings, announcements
ShareholdingProvider     — Promoter/institutional ownership
CorporateActionsProvider — Dividends, splits, bonuses
NewsProvider             — News articles, press releases
SearchProvider           — Web search, document search
MacroDataProvider        — GDP, inflation, rates, indicators
TranscriptProvider       — Earnings call transcripts
LLMProvider              — Text generation, chat completion
EmbeddingProvider        — Text embedding generation
```

## Implementation Pattern

```python
class MarketDataProvider(Protocol):
    async def get_quote(self, symbol: str, exchange: str) -> Quote: ...
    async def get_historical_prices(self, symbol: str, exchange: str,
                                     start: date, end: date) -> list[PriceBar]: ...
    async def search_companies(self, query: str) -> list[CompanySearchResult]: ...

class AlphaVantageProvider:
    """Concrete implementation of MarketDataProvider for Alpha Vantage."""
    def __init__(self, api_key: str, rate_limiter: RateLimiter): ...
    async def get_quote(self, symbol: str, exchange: str) -> Quote: ...
    # ...
```

## Consequences

- New providers can be added without changing business logic
- Testing uses mock/stub providers — no external API calls in unit tests
- Configuration (`.env` or settings) determines which provider is active
- Providers may have different data coverage — the application layer handles provider capabilities gracefully
- Initial implementation effort is higher than direct API calls, but long-term maintenance is lower
