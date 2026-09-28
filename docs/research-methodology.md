# Research Methodology

## Overview

This document describes the systematic research methodology implemented by the platform. The methodology is designed to produce evidence-backed equity research that is reproducible, transparent, and intellectually honest.

## Core Research Question

> "What businesses in India are building durable competitive advantages in industries with long-term structural growth, and does the current valuation provide an attractive risk/reward relative to the company's future earning potential?"

## Research Principles

1. **Evidence before inference.** Every factual claim requires a source.
2. **Separation of concerns.** Facts, calculations, management claims, analyst opinions, AI inference, assumptions, and uncertainty are never mixed.
3. **No fabricated data.** If data is unavailable, the system says so. It never invents financial figures.
4. **Reproducibility.** Every conclusion can be re-derived from stored evidence and deterministic calculations.
5. **Adversarial testing.** Every thesis is challenged by a Devil's Advocate agent. Every research output includes a bear case.
6. **No certainty manufacturing.** The system does not predict future returns. It identifies characteristics associated with business quality and value creation.

## Research Dimensions

### A. Business Quality

- What does the company do?
- How does it make money?
- Revenue stream composition, concentration, and quality
- Recurring vs transactional revenue
- Pricing power, operating leverage, capital intensity

### B. Industry Attractiveness

- Total addressable market (TAM) and serviceable market (SAM)
- Growth rate and drivers
- Competitive structure (Porter's Five Forces)
- Entry barriers, cyclicality, regulatory environment
- India's competitive position in the global industry

### C. Competitive Moat

16 moat types evaluated individually with evidence:
Brand, Cost Advantage, Network Effects, Switching Costs, Distribution, Scale, Regulatory Barriers, IP, Technology, Data, Ecosystem, Customer Embeddedness, Manufacturing, Supply Chain, Capital Access, Location

Each moat assessed for: strength, durability, threats, competitive comparison.

Default assessment is **no moat** — evidence is required to upgrade.

### D. Management Quality

- Ownership and alignment (promoter holding, pledge)
- Capital allocation track record
- Promise vs execution history
- Governance (related-party transactions, auditor history)
- Compensation and dilution

### E. Financial Quality (5-10 Year Analysis)

**Growth**: Revenue, EBITDA, EBIT, PAT, EPS, FCF CAGR
**Profitability**: Gross/EBITDA/EBIT/Net margin, ROE, ROCE, ROIC
**Balance Sheet**: Debt/Equity, Net Debt/EBITDA, interest coverage, current ratio
**Cash Flow**: CFO, FCF, CFO/PAT, FCF/PAT, capex, working capital
**Quality**: Earnings consistency, cash conversion, margin stability, return on incremental capital

**Financial Forensics**: Receivables vs revenue growth, inventory build-up, CFO vs PAT, capitalized expenses, related-party transactions, auditor qualifications → Financial Red Flag Score.

### F. Growth Quality

Current business growth trajectory distinguished from future optionality.

### G. Future Optionality

Future initiatives classified by maturity:
- **Proven**: Revenue-generating, scaled
- **Commercializing**: Product/market fit, early revenue
- **Early Stage**: Pilot/prototype
- **Experimental**: R&D phase
- **Speculative**: Announced intent only

Management announcements are NOT treated as guaranteed future revenue.

### H. Macroeconomic Exposure

Company-specific macro factor mapping. Example: Oil ↑ → airline margins ↓ but upstream energy revenue ↑. Macro factors include GDP, inflation, RBI policy, INR/USD, commodities, government capex, global growth, geopolitics.

### I. Valuation

Multiple models (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF, DCF, Reverse DCF, Historical Bands, Peer Comparison).

Always produces a **range**, never a single false-precision value. All assumptions are visible and configurable. Business Quality vs Valuation matrix output.

### J. Risks

Systematic identification across categories: Business, Financial, Valuation, Governance, Regulatory, Technology, Disruption, Commodity, Currency, Geopolitical, Concentration (customer/supplier), Execution.

Top 5 risks and thesis invalidation conditions.

### K. Catalysts

Identified positive catalysts with expected timeline, impact, confidence, and supporting evidence.

### L. Bear Case

Pessimistic scenario with: revenue CAGR, margin trajectory, EPS path, valuation range, key assumptions, "What Can Go Wrong."

### M. Bull Case

Optimistic scenario with: revenue CAGR, margin trajectory, EPS path, valuation range, key assumptions, "What Must Go Right."

### N. Investment Thesis

Structured synthesis:
- One-line thesis
- Business quality, moat, growth engine, future optionality
- Management, financial quality, valuation
- Catalysts, risks, bear case, bull case
- Key monitoring metrics
- Thesis invalidation conditions

Every statement labeled: FACT / CALCULATION / MANAGEMENT CLAIM / ANALYST OPINION / AI INFERENCE / ASSUMPTION / UNCERTAINTY.

### O. Thesis Invalidation

Specific, measurable conditions under which the investment thesis would be invalidated. These conditions are monitored by the Portfolio Monitoring Agent.

## Quality Gates

Every research run must pass 12 gates before publication:

| # | Gate | Check |
|---|------|-------|
| 1 | Data Completeness | All required financial data collected (5yr minimum) |
| 2 | Source Verification | All Tier 1 data sourced from authoritative providers |
| 3 | Financial Consistency | Balance sheet balances, cross-statement consistency |
| 4 | Calculation Validation | All computed ratios reproducible from stored data |
| 5 | Valuation Assumption Validation | All DCF/model inputs explicitly stated |
| 6 | Current-Source Validation | Source documents are current (not stale) |
| 7 | Management-Claim Separation | Management statements labeled, not presented as fact |
| 8 | Risk Coverage | All major risk categories assessed |
| 9 | Bear-Case Coverage | Bear case present with specific assumptions |
| 10 | Thesis-Challenger Review | Devil's Advocate analysis completed |
| 11 | Citation Completeness | All FACT-type findings have evidence citations |
| 12 | Output Schema Validation | Research output conforms to schema |

**If any gate fails**: The research output is marked RESEARCH INCOMPLETE with a list of missing evidence. The system does NOT fabricate information to pass gates.

## Scoring Methodology

10 independent dimensions, each scored 0-100 with underlying sub-scores and evidence links:

1. Business Quality
2. Financial Quality
3. Growth Quality
4. Moat Strength
5. Management Quality
6. Future Optionality
7. Industry Attractiveness
8. Valuation Attractiveness
9. Balance Sheet Strength
10. Risk (lower = more risk)

**No opaque composite score.** Every score is explainable — users can drill down from score → sub-scores → evidence.

## Screening Methodology

The screening engine supports multi-criteria filtering:

- Financial metrics (ROCE, ROE, ROIC, margins, growth rates)
- Balance sheet metrics (Debt/Equity, interest coverage)
- Cash flow metrics (FCF yield, CFO/PAT)
- Ownership metrics (promoter holding, pledge, institutional)
- Valuation metrics (P/E, EV/EBITDA, PEG)
- Quality scores (from research runs)
- AND/OR logic, saved screens

Screening identifies candidates for deep research — it does not constitute a buy/sell recommendation.

## Longitudinal Research

The system maintains thesis versions over time. When new data arrives:

1. Compare with stored thesis assumptions
2. Detect material changes
3. Flag: THESIS CHANGE DETECTED
4. Generate change summary
5. Alert watchlist subscribers

Example:
```
Previous: Revenue guidance 20% growth
New:      Revenue guidance reduced to 12%
Alert:    THESIS CHANGE — Revenue growth assumption weakened
```

## Disclaimers

- The platform is a research and decision-support system
- It does NOT provide personalized investment advice
- AI-generated analysis is labeled as such
- Past performance indicators do not guarantee future results
- Users should perform their own due diligence
- If commercialized, SEBI Research Analyst / Investment Adviser requirements must be assessed with legal counsel
