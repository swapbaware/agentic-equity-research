# ADR-006: India Market Focus (NSE/BSE)

## Status

Accepted

## Date

2026-09-28

## Context

The platform focuses on Indian listed companies. This has specific implications for:
- Data sources (NSE, BSE, SEBI, RBI vs SEC/EDGAR)
- Currency (INR, not USD)
- Regulatory framework (SEBI, Companies Act, not SEC)
- Financial reporting standards (Ind AS, not US GAAP)
- Market structure (promoter-driven ownership, different institutional patterns)
- Fiscal year (April–March, not January–December)

## Decision

Design the data model and provider interfaces with India-specific conventions as the primary target, while keeping the architecture extensible to other markets.

## India-Specific Design Decisions

1. **Exchanges**: NSE and BSE are first-class entities, with exchange-specific symbols and codes
2. **Fiscal Year**: April–March convention. The `fiscal_year` field represents the ending year (FY2025 = April 2024 – March 2025)
3. **Currency**: INR is the default. All monetary values in INR unless explicitly specified
4. **Market Cap Tiers**: Follow Indian conventions (₹1L Cr+, ₹25K-1L Cr, ₹5K-25K Cr, <₹5K Cr)
5. **Shareholding Patterns**: Track promoter holding, promoter pledge, FII, DII, public — Indian-specific ownership categories
6. **Regulatory Sources**: SEBI filings, NSE/BSE corporate filings as Tier 1 sources
7. **Sector Classification**: Based on NSE/BSE industry classifications with custom extensions
8. **Financial Reporting**: Ind AS standards for statement parsing
9. **Macro Indicators**: RBI data, India GDP, INR/USD as primary macro factors

## Consequences

- Provider interfaces are designed for Indian market data first
- Sector/industry enumeration reflects Indian market structure
- Shareholding analysis includes India-specific patterns (promoter pledge, FII/DII)
- Financial statement parsing handles Ind AS line items
- The architecture can be extended to other markets by adding new provider implementations, but the domain model's India-specific fields (promoter holding, BSE code, etc.) would need generalization for a multi-market deployment
