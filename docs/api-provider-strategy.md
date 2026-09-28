# API & Provider Strategy

## Overview

The platform accesses external services through abstract provider interfaces. This document defines the provider strategy, data source priorities, rate limiting approach, and implementation guidelines.

## Provider Interface Catalog

### LLM Providers

| Interface | Method | Description |
|-----------|--------|-------------|
| `LLMProvider` | `generate(prompt, schema)` | Structured text generation with output schema |
| `LLMProvider` | `chat(messages, tools)` | Multi-turn conversation with tool use |
| `EmbeddingProvider` | `embed(texts)` | Generate text embeddings |

**Initial Implementations**: Anthropic (Claude), OpenAI (GPT)

**Selection**: Configured via `LLM_PROVIDER` environment variable. Different agents can use different providers/models based on task requirements (e.g., stronger model for Thesis Synthesis, faster model for data extraction).

### Financial Data Providers

| Interface | Purpose | Initial Sources |
|-----------|---------|-----------------|
| `MarketDataProvider` | Price, volume, market cap, trading data | NSE, BSE, Alpha Vantage, Polygon.io |
| `FinancialDataProvider` | Financial statements (IS, BS, CF) | NSE filings, BSE filings |
| `CorporateFilingsProvider` | Annual reports, quarterly results, filings | NSE, BSE, SEBI |
| `ShareholdingProvider` | Promoter, FII, DII, public ownership | NSE, BSE |
| `CorporateActionsProvider` | Dividends, splits, bonuses, buybacks | NSE, BSE |
| `NewsProvider` | Company and sector news | Web search, news APIs |
| `MacroDataProvider` | GDP, inflation, rates, commodity prices | RBI, government sources |
| `TranscriptProvider` | Earnings call transcripts | Provider-specific |
| `SearchProvider` | Web search, document retrieval | Web search APIs |

## Data Source Tiering

### Tier 1 — Primary Sources (Authoritative)

- **NSE** — Corporate filings, financial results, shareholding patterns, price data
- **BSE** — Corporate filings, financial results, shareholding patterns, price data
- **SEBI** — Regulatory filings, insider trading disclosures
- **Company websites** — Annual reports, investor presentations
- **RBI** — Monetary policy, economic data
- **Government sources** — Ministry publications, economic surveys

### Tier 2 — Secondary Sources (Reliable)

- **Industry bodies** — NASSCOM, CII, FICCI industry reports
- **Government economic reports** — Economic Survey, Budget documents

### Tier 3 — Tertiary Sources (Supplementary)

- **Financial publications** — Business newspapers, financial websites
- **Research reports** — Brokerage research (with attribution)
- **Conference transcripts** — Earnings calls, investor days

### Usage Rules

1. Financial data (revenue, profit, ratios) must come from Tier 1 sources
2. Tier 2 sources are acceptable for industry data and macro indicators
3. Tier 3 sources can be used for discovery and sentiment but are not authoritative
4. Source tier is recorded with every `Evidence` record
5. Quality gates validate source tier appropriateness

## Rate Limiting Strategy

### Per-Provider Rate Limits

| Provider | Rate Limit | Implementation |
|----------|-----------|----------------|
| NSE/BSE | Respect published limits | Token bucket in Redis |
| Alpha Vantage (free) | 5 calls/minute, 500/day | Token bucket in Redis |
| Alpha Vantage (premium) | 75 calls/minute | Token bucket in Redis |
| Polygon.io | Plan-dependent | Token bucket in Redis |
| Anthropic | Plan-dependent | Token bucket in Redis |
| OpenAI | Plan-dependent | Token bucket in Redis |

### Rate Limiter Design

```python
class RateLimiter:
    """Redis-backed token bucket rate limiter."""
    async def acquire(self, provider: str, tokens: int = 1) -> bool: ...
    async def wait_and_acquire(self, provider: str, tokens: int = 1) -> None: ...
    def remaining(self, provider: str) -> int: ...
```

### Retry Strategy

| Scenario | Strategy |
|----------|----------|
| Rate limited (429) | Exponential backoff, respect Retry-After header |
| Server error (5xx) | Retry 3 times with exponential backoff |
| Timeout | Retry once with increased timeout |
| Auth error (401/403) | Fail immediately, log alert |
| Client error (4xx) | Fail immediately, log for investigation |

## Provider Implementation Guidelines

### Every Provider Implementation Must

1. Accept configuration via constructor (API key, base URL, timeout)
2. Use the shared `RateLimiter` for its provider key
3. Implement retry logic with the shared retry strategy
4. Log all API calls (provider, endpoint, latency, status) via structured logging
5. Validate responses against expected Pydantic schemas
6. Convert all financial values to `Decimal` at the provider boundary
7. Handle pagination for list endpoints
8. Support async operations (`async/await`)
9. Raise provider-specific exceptions that map to a common error hierarchy
10. Include provider name and request ID in error context

### Error Hierarchy

```
ProviderError
├── ProviderAuthError          # 401/403
├── ProviderRateLimitError     # 429
├── ProviderNotFoundError      # 404 (company not found, etc.)
├── ProviderTimeoutError       # Timeout
├── ProviderUnavailableError   # 5xx
└── ProviderDataError          # Response doesn't match expected schema
```

### Testing Providers

- Unit tests use mock HTTP responses (no real API calls)
- Integration tests (optional, CI-skipped by default) hit real APIs with test keys
- Each provider has a test fixture with sample response payloads
- Provider interface compliance tested with a shared conformance test suite

## Data Licensing & Terms

- Review each provider's terms of service before implementation
- Document redistribution restrictions
- Display required attributions in the UI
- Do not cache or redistribute data beyond what terms allow
- Log data access for audit purposes

## Provider Switching

Switching a provider requires:
1. Implementing the relevant interface
2. Adding configuration for the new provider's API key and settings
3. Updating the provider factory to include the new implementation
4. Running the conformance test suite against the new provider
5. Updating `.env.example` with new provider configuration

No changes to business logic, agents, or UI are required.
