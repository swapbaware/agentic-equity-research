# ADR-009: NSE/BSE Data Access Strategy

## Status

Open — requires research in Phase 4

## Date

2026-09-28

## Context

The architecture review identified a critical dependency: NSE and BSE do not offer free, open REST APIs for financial data. Access methods include:

1. **NSE website data feeds**: Semi-structured data accessible via HTTP requests, but terms of service may restrict automated access and redistribution.
2. **BSE API**: BSE provides some data endpoints, but coverage and terms vary.
3. **Commercial data vendors**: Providers like Capital Market, Ace Equity, Bloomberg, Refinitiv offer comprehensive Indian market data but at significant cost.
4. **SEBI XBRL filings**: Structured financial data in XBRL format filed with SEBI.
5. **Third-party aggregators**: Free or low-cost APIs that aggregate public Indian market data (e.g., Yahoo Finance India, Google Finance).

This is a **critical path blocker** for Phase 4 (Provider Framework). The platform cannot function without reliable Indian financial data.

## Options Under Evaluation

| Source | Data Coverage | Cost | Legal Risk | Reliability |
|--------|-------------|------|-----------|-------------|
| NSE HTTP feeds | Comprehensive (prices, filings, shareholding) | Free | **High** (ToS may prohibit scraping) | **Medium** (changes without notice) |
| BSE API | Good (prices, some filings) | Free | Medium | Medium |
| Yahoo Finance (India) | Prices, basic financials | Free | Medium (redistribution limits) | Medium |
| SEBI XBRL | Financial statements only | Free | **Low** (public regulatory data) | High |
| Commercial vendor (TBD) | Comprehensive | $$$ | Low | High |
| Alpha Vantage | Limited India coverage | Free/Paid | Low | High |

## Recommended Strategy

1. **Start with SEBI XBRL** for financial statements — this is public regulatory data with minimal legal risk.
2. **Use BSE API** for price data and basic company information where terms permit.
3. **Evaluate Yahoo Finance** for price history and basic data as a supplementary source.
4. **Design the provider abstraction** so that a commercial vendor can be swapped in without changing business logic — this is already covered by ADR-005.
5. **Document terms of service** for every data source before implementation.
6. **Do NOT build a web scraper for NSE** as a primary data strategy — it's fragile and likely violates terms of service.

## Decision

Deferred to Phase 4. The provider abstraction layer (ADR-005) ensures that data source selection does not affect application architecture. The MVP may launch with limited data coverage from free sources, with commercial vendor integration planned as an upgrade path.

## Consequences

- MVP data coverage will be narrower than the full specification envisions
- Financial data quality and completeness may vary by source
- Some companies may have incomplete financial histories
- The testing strategy must account for data gaps (quality gates allow INCOMPLETE results)
- Budget planning must include potential commercial data vendor costs
