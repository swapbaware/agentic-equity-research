# Domain Model

## Overview

The domain model captures the core business entities of the Agentic Equity Research Platform. All entities use strong typing (Pydantic models) and `decimal.Decimal` for monetary/financial values.

## Entity Relationship Diagram (Conceptual)

```
                    ┌──────────┐
                    │ Exchange  │
                    └────┬─────┘
                         │ 1:N
                    ┌────┴─────┐          ┌──────────┐
                    │ Security │──────────│  Sector   │
                    └────┬─────┘    N:1   └────┬─────┘
                         │                     │ 1:N
                    ┌────┴─────┐          ┌────┴──────┐
                    │ Company  │──────────│ Industry   │
                    └────┬─────┘    N:1   └───────────┘
                         │
        ┌────────────────┼────────────────────┐
        │                │                    │
   ┌────┴────┐    ┌──────┴──────┐    ┌───────┴────────┐
   │Financial│    │  Research   │    │   Corporate     │
   │  Data   │    │  Artifacts  │    │   Governance    │
   └────┬────┘    └──────┬──────┘    └───────┬────────┘
        │                │                    │
   ┌────┴────┐    ┌──────┴──────┐    ┌───────┴────────┐
   │Statement│    │   Thesis    │    │  Shareholding   │
   │ Metric  │    │   Finding   │    │  Pledge         │
   │ Ratio   │    │   Evidence  │    │  RPT            │
   └─────────┘    └─────────────┘    └────────────────┘
```

## Core Entities

### Company

The central aggregate root. Represents an Indian listed company.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| name | str | Full legal name |
| nse_symbol | str | NSE trading symbol (nullable) |
| bse_code | str | BSE scrip code (nullable) |
| isin | str | ISIN code |
| sector_id | FK → Sector | Primary sector classification |
| industry_id | FK → Industry | Industry classification |
| market_cap | Decimal | Current market capitalization (INR) |
| enterprise_value | Decimal | Current enterprise value (INR) |
| incorporation_date | date | Date of incorporation |
| listing_date | date | Date of listing |
| registered_address | str | Registered office address |
| website | str | Company website |
| description | text | Business description |
| business_segments | JSON | Major business segments |
| major_products | JSON | Key products/services |
| geographies | JSON | Operating geographies |
| is_active | bool | Currently listed and trading |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### Security

Represents a tradeable security on an exchange.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| company_id | FK → Company | Issuing company |
| exchange_id | FK → Exchange | Listed exchange |
| symbol | str | Trading symbol on this exchange |
| security_type | enum | EQUITY, PREFERENCE, DEBENTURE |
| face_value | Decimal | Face value per share |
| lot_size | int | Trading lot size |
| is_active | bool | Currently trading |

### Exchange

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| code | str | NSE, BSE |
| name | str | Full exchange name |
| country | str | IN |

### Sector / Industry

Hierarchical classification. A sector contains multiple industries.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| name | str | Sector/Industry name |
| code | str | Internal code |
| parent_id | FK → Sector | (Industry → Sector) |

## Financial Data Entities

### FinancialStatement

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| company_id | FK → Company | |
| statement_type | enum | INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW |
| period_type | enum | ANNUAL, QUARTERLY |
| fiscal_year | int | Fiscal year |
| fiscal_quarter | int | Quarter (1-4, null for annual) |
| period_start | date | Period start date |
| period_end | date | Period end date |
| currency | str | INR |
| is_audited | bool | Audited vs unaudited |
| is_consolidated | bool | Consolidated vs standalone |
| source | str | Source identifier |
| source_document_id | FK → ResearchDocument | Original filing |
| created_at | datetime | Ingestion timestamp |

### FinancialMetric

Individual line items within a financial statement.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| statement_id | FK → FinancialStatement | Parent statement |
| metric_name | str | Standardized metric name (e.g. `revenue`, `ebitda`) |
| value | Decimal | Metric value |
| unit | enum | CURRENCY, PERCENTAGE, RATIO, COUNT |
| is_calculated | bool | Derived vs reported |
| calculation_formula | str | Formula if calculated |

### QuarterlyResult

Captures quarterly financial results as filed.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal identifier |
| company_id | FK → Company | |
| fiscal_year | int | |
| fiscal_quarter | int | |
| revenue | Decimal | |
| ebitda | Decimal | |
| ebit | Decimal | |
| pat | Decimal | |
| eps | Decimal | |
| source_document_id | FK → ResearchDocument | |
| filing_date | date | Date filed with exchange |

## Corporate Governance Entities

### Shareholding

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| as_of_date | date | Quarter-end date |
| promoter_holding_pct | Decimal | Promoter group % |
| fii_holding_pct | Decimal | Foreign institutional % |
| dii_holding_pct | Decimal | Domestic institutional % |
| public_holding_pct | Decimal | Public % |
| source_document_id | FK → ResearchDocument | |

### PromoterPledge

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| as_of_date | date | |
| shares_pledged | int | Number of shares pledged |
| pledge_pct | Decimal | % of promoter holding pledged |
| source_document_id | FK → ResearchDocument | |

### CorporateAction

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| action_type | enum | DIVIDEND, SPLIT, BONUS, BUYBACK, RIGHTS, MERGER |
| ex_date | date | |
| record_date | date | |
| details | JSON | Action-specific details |
| source | str | |

### CorporateAnnouncement

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| announcement_date | datetime | |
| category | str | |
| subject | str | |
| content | text | |
| source_url | str | |
| exchange | str | NSE/BSE |

## Research & Evidence Entities

### ResearchDocument

Source documents ingested by the platform.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | (nullable for macro docs) |
| document_type | enum | ANNUAL_REPORT, QUARTERLY_RESULT, INVESTOR_PRESENTATION, TRANSCRIPT, FILING, NEWS, RESEARCH_REPORT, GOVERNMENT_PUBLICATION |
| title | str | |
| source_tier | enum | TIER_1, TIER_2, TIER_3 |
| source_name | str | e.g. "NSE", "BSE", "Company Website" |
| source_url | str | |
| document_date | date | |
| storage_path | str | S3 path |
| content_hash | str | SHA-256 for dedup |
| embedding_id | str | pgvector reference |
| metadata | JSON | |
| ingested_at | datetime | |

### Evidence

An individual piece of evidence extracted from a source document.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| document_id | FK → ResearchDocument | Source document |
| evidence_type | enum | FACT, FINANCIAL_DATA, MANAGEMENT_STATEMENT, ANALYST_OPINION, REGULATORY_FILING |
| claim | text | The factual claim |
| context | text | Surrounding context |
| page_or_section | str | Location in document |
| confidence | enum | HIGH, MEDIUM, LOW |
| extracted_at | datetime | |
| extracted_by | str | Agent or pipeline that extracted it |

### ManagementStatement

Specific tracking of management promises and execution.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| statement_date | date | When the statement was made |
| statement | text | What management promised/guided |
| category | enum | REVENUE_GUIDANCE, MARGIN_GUIDANCE, CAPEX_PLAN, PRODUCT_LAUNCH, EXPANSION, OTHER |
| source_evidence_id | FK → Evidence | |
| expected_outcome | text | |
| actual_outcome | text | (filled when result known) |
| outcome_evidence_id | FK → Evidence | |
| status | enum | PENDING, MET, PARTIALLY_MET, MISSED, UNKNOWN |

## Analysis Entities

### MoatAssessment

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| moat_type | enum | BRAND, COST_ADVANTAGE, NETWORK_EFFECT, SWITCHING_COST, DISTRIBUTION, SCALE, REGULATORY, IP, TECHNOLOGY, DATA, ECOSYSTEM, CUSTOMER_EMBEDDEDNESS, MANUFACTURING, SUPPLY_CHAIN, CAPITAL_ACCESS, LOCATION |
| strength | enum | NONE, NARROW, MODERATE, WIDE |
| durability_years | int | Estimated durability |
| evidence_ids | FK[] → Evidence | Supporting evidence |
| threats | JSON | Identified threats to this moat |
| competitor_comparison | JSON | Competitor moat comparison |
| confidence | enum | HIGH, MEDIUM, LOW |
| explanation | text | |

### GrowthOpportunity

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| opportunity_name | str | |
| category | enum | NEW_PRODUCT, NEW_MARKET, ACQUISITION, PARTNERSHIP, GOVERNMENT_INCENTIVE, TECHNOLOGY, EXPANSION |
| maturity | enum | PROVEN, COMMERCIALIZING, EARLY_STAGE, EXPERIMENTAL, SPECULATIVE |
| addressable_market | Decimal | Estimated TAM in INR |
| timeline_years | int | Expected materialization |
| evidence_ids | FK[] → Evidence | |
| risks | JSON | |
| confidence | enum | HIGH, MEDIUM, LOW |

### Competitor

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | The subject company |
| competitor_company_id | FK → Company | (nullable if unlisted/foreign) |
| competitor_name | str | |
| is_domestic | bool | |
| relevance | enum | DIRECT, INDIRECT, POTENTIAL |
| comparison_metrics | JSON | Side-by-side financial comparison |

### IndustryData

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| industry_id | FK → Industry | |
| metric_name | str | TAM, growth_rate, concentration, etc. |
| value | Decimal | |
| as_of_date | date | |
| source_evidence_id | FK → Evidence | |

### MacroIndicator

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| indicator_name | str | GDP, inflation, repo_rate, etc. |
| value | Decimal | |
| unit | str | |
| as_of_date | date | |
| source | str | RBI, Government, etc. |
| country | str | IN, US, CN, GLOBAL |
| company_impact_mapping | JSON | How this affects specific sectors/companies |

## Valuation Entities

### ValuationModel

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| model_type | enum | PE, EV_EBITDA, PS, PB, PEG, FCF_YIELD, EV_FCF, DCF, REVERSE_DCF, HISTORICAL_BAND, PEER_COMPARISON |
| scenario | enum | BEAR, BASE, BULL |
| assumptions | JSON | All input assumptions (visible) |
| inputs | JSON | Model inputs |
| outputs | JSON | Model outputs |
| implied_value_per_share | Decimal | |
| current_price | Decimal | At time of calculation |
| upside_downside_pct | Decimal | |
| calculation_timestamp | datetime | |

### Scenario

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| scenario_type | enum | BEAR, BASE, BULL |
| revenue_cagr | Decimal | |
| ebitda_margin | Decimal | |
| eps_growth | Decimal | |
| fcf_growth | Decimal | |
| exit_multiple | Decimal | |
| valuation_range_low | Decimal | |
| valuation_range_high | Decimal | |
| key_assumptions | JSON | |
| what_must_go_right | text[] | |
| what_can_go_wrong | text[] | |

## Risk & Thesis Entities

### Risk

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| risk_type | enum | BUSINESS, FINANCIAL, VALUATION, GOVERNANCE, REGULATORY, TECHNOLOGY, DISRUPTION, COMMODITY, CURRENCY, GEOPOLITICAL, CUSTOMER_CONCENTRATION, SUPPLIER_CONCENTRATION, EXECUTION |
| description | text | |
| severity | enum | LOW, MEDIUM, HIGH, CRITICAL |
| likelihood | enum | LOW, MEDIUM, HIGH |
| mitigation | text | |
| evidence_ids | FK[] → Evidence | |

### Catalyst

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| description | text | |
| expected_timeline | str | |
| impact | enum | LOW, MEDIUM, HIGH |
| confidence | enum | HIGH, MEDIUM, LOW |
| evidence_ids | FK[] → Evidence | |

### InvestmentThesis

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| version | int | Thesis version number |
| one_line_thesis | str | |
| business_quality_summary | text | |
| moat_summary | text | |
| growth_summary | text | |
| management_summary | text | |
| financial_quality_summary | text | |
| valuation_summary | text | |
| catalysts | FK[] → Catalyst | |
| risks | FK[] → Risk | |
| bear_case | text | |
| bull_case | text | |
| key_monitoring_metrics | JSON | |
| thesis_invalidation_conditions | text[] | |
| overall_confidence | enum | HIGH, MEDIUM, LOW |
| fact_vs_inference_labels | JSON | Labels for each section |
| created_at | datetime | |

### ThesisVersion

Tracks longitudinal changes to a company's investment thesis.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| thesis_id | FK → InvestmentThesis | Current version |
| previous_thesis_id | FK → InvestmentThesis | Previous version |
| change_summary | text | What changed and why |
| change_trigger | str | New quarterly result, management update, etc. |
| created_at | datetime | |

## Research Execution Entities

### ResearchRun

A single execution of the research workflow for a company.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| initiated_by | str | User or scheduled |
| started_at | datetime | |
| completed_at | datetime | |
| status | enum | RUNNING, COMPLETED, FAILED, INCOMPLETE |
| quality_gate_results | JSON | Pass/fail for each gate |
| agent_execution_log | JSON | Which agents ran, duration, status |
| data_sources_used | JSON | List of sources consulted |
| research_completeness | Decimal | % of required analysis completed |
| total_input_tokens | int | LLM input tokens consumed |
| total_output_tokens | int | LLM output tokens consumed |
| total_cost_usd | Decimal | Estimated LLM cost |
| cost_by_agent | JSON | Per-agent token/cost breakdown |

### ResearchFinding

Individual findings produced by agents during a research run.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| research_run_id | FK → ResearchRun | |
| agent_name | str | Which agent produced this |
| finding_type | enum | FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, UNCERTAINTY |
| category | str | business_model, moat, valuation, etc. |
| content | text | The finding |
| evidence_ids | FK[] → Evidence | Supporting evidence |
| confidence | enum | HIGH, MEDIUM, LOW |
| created_at | datetime | |

## Scoring Entities

### CompanyScore

Transparent, evidence-backed scoring.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | |
| company_id | FK → Company | |
| research_run_id | FK → ResearchRun | |
| dimension | enum | BUSINESS_QUALITY, FINANCIAL_QUALITY, GROWTH_QUALITY, MOAT_STRENGTH, MANAGEMENT_QUALITY, FUTURE_OPTIONALITY, INDUSTRY_ATTRACTIVENESS, VALUATION_ATTRACTIVENESS, BALANCE_SHEET_STRENGTH, RISK |
| score | int | 0-100 |
| sub_scores | JSON | Breakdown with individual evidence links |
| explanation | text | Why this score |
| evidence_ids | FK[] → Evidence | |

## Value Objects

These are not persisted as separate entities but are embedded types:

- **Money**: `{amount: Decimal, currency: str}`
- **Percentage**: `{value: Decimal}`
- **FinancialRatio**: `{value: Decimal, numerator_metric: str, denominator_metric: str}`
- **DateRange**: `{start: date, end: date}`
- **SourceCitation**: `{document_id: UUID, page_or_section: str, quote: str}`
- **CAGRResult**: `{value: Decimal, start_value: Decimal, end_value: Decimal, years: int}`

## Relationship Implementation Notes

**Many-to-many relationships** (`evidence_ids` fields on MoatAssessment, GrowthOpportunity, Risk, Catalyst, CompanyScore, ResearchFinding): These are implemented as junction tables in PostgreSQL, not array columns. For example:

```
moat_assessment_evidence (moat_assessment_id, evidence_id)
research_finding_evidence (research_finding_id, evidence_id)
risk_evidence (risk_id, evidence_id)
```

**InvestmentThesis → Risks/Catalysts**: The relationship is through `research_run_id` — the thesis, its risks, and its catalysts all share the same `research_run_id`. No direct FK array from thesis to risk/catalyst.

**Company.market_cap / enterprise_value**: These are "latest snapshot" fields updated by the data ingestion pipeline. They include an implicit `as_of_date` (the `updated_at` timestamp). For historical market cap, query the price history and shares outstanding. These fields exist for fast screening queries — not as the authoritative time-series source.

**QuarterlyResult vs FinancialStatement**: `QuarterlyResult` is a denormalized convenience view for the most commonly queried quarterly metrics. The authoritative source is `FinancialStatement` + `FinancialMetric` (with `period_type = QUARTERLY`). `QuarterlyResult` is populated from `FinancialMetric` during ingestion. If there is a conflict, `FinancialStatement` + `FinancialMetric` is the source of truth.

**Sector / Industry**: Implemented as a single `classification` table with `level` field (`SECTOR` or `INDUSTRY`) and `parent_id` (Industry → Sector). This allows for future sub-industry levels without schema changes.

## Key Invariants

1. Every `ResearchFinding` with `finding_type = FACT` must have at least one `evidence_id`.
2. Every `ValuationModel` must have explicit `assumptions` — no hidden inputs.
3. `FinancialMetric.value` is always `Decimal`, never `float`.
4. Every `InvestmentThesis` must have a corresponding `Scenario` for BEAR, BASE, and BULL.
5. `ManagementStatement.status` can only transition to `MET`/`MISSED` when `outcome_evidence_id` is provided.
6. `CompanyScore.score` is always accompanied by `explanation` and `evidence_ids`.
7. No two `ResearchRun` records for the same `company_id` can have `status = RUNNING` simultaneously (enforced by Redis advisory lock — see ADR-007).

## Implementation Status

**Implemented in Phase 3** — SQLAlchemy 2.0 ORM models in `backend/app/models/`.

| Aspect | Detail |
|--------|--------|
| Models | 28 ORM classes across 8 files |
| Junction tables | 6 (evidence relationships for findings, moats, growth, risks, catalysts, scores) |
| Total tables | 34 across 7 PostgreSQL schemas |
| Enumerations | 27 `StrEnum` types |
| Migration | `backend/alembic/versions/002_domain_model.py` (explicit DDL) |
| Tests | 156 unit tests (schema introspection) + 6 integration tests (database round-trip) |

**Design decisions made during implementation:**
- `Sector`/`Industry` unified into `Classification` table with `level` discriminator and self-referential `parent_id`
- `AnnualReport`, `InvestorPresentation`, `NewsArticle` mapped to `ResearchDocument` via `document_type` enum (no separate tables)
- `InvestmentThesis` → `Risk`/`Catalyst` relationship is implicit via shared `research_run_id` (no junction table)
- All `evidence_ids` fields from the conceptual model are implemented as junction tables with CASCADE delete
- `MoatStrength` defaults to `NONE` (conservative default per CLAUDE.md rules)
