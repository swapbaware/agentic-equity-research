# Data Architecture

## Overview

The data architecture supports high-fidelity financial data storage, document management, semantic search, and longitudinal research tracking. All financial values use `decimal.Decimal` — no floating-point arithmetic for monetary or ratio calculations.

## Storage Topology

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
└──────┬──────────────┬───────────────┬──────────────┬────┘
       │              │               │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼─────┐
│ PostgreSQL  │ │  pgvector  │ │   Redis     │ │    S3     │
│             │ │            │ │             │ │           │
│ Relational  │ │ Embeddings │ │ Cache       │ │ Documents │
│ data, all   │ │ & semantic │ │ Sessions    │ │ PDFs      │
│ domain      │ │ search     │ │ Rate limits │ │ Reports   │
│ entities    │ │ indexes    │ │ Temp state  │ │ Filings   │
└─────────────┘ └────────────┘ └─────────────┘ └───────────┘
```

## PostgreSQL Schema Design

### Schema Organization

```
equity_research (database)
├── company        — Company, Security, Exchange, Sector, Industry
├── financial      — FinancialStatement, FinancialMetric, QuarterlyResult
├── governance     — Shareholding, PromoterPledge, CorporateAction, CorporateAnnouncement
├── research       — ResearchDocument, Evidence, ManagementStatement, ResearchRun, ResearchFinding
├── analysis       — MoatAssessment, GrowthOpportunity, Competitor, IndustryData, MacroIndicator
├── valuation      — ValuationModel, Scenario
├── thesis         — InvestmentThesis, ThesisVersion, Risk, Catalyst, CompanyScore
├── screening      — SavedScreen, ScreenResult
├── portfolio      — Watchlist, WatchlistCompany, Alert
└── auth           — User, Session, Permission
```

### Key Design Decisions

**Temporal Data**: Financial data is inherently temporal. Every financial metric is associated with a period (fiscal year + quarter). The schema supports querying across time ranges for trend analysis.

**Audit Trail**: All entities include `created_at` and `updated_at`. Research artifacts include `created_by` (user or agent). Changes to theses create new `ThesisVersion` records rather than updating in place.

**Source Linkage**: Financial data entities reference their source `ResearchDocument` via `source_document_id`, creating a verifiable chain from displayed metric to original filing.

**Decimal Storage**: PostgreSQL `NUMERIC` type (arbitrary precision) for all financial values. Application-layer uses Python `decimal.Decimal`. No `FLOAT` or `DOUBLE PRECISION` for financial data.

### Indexing Strategy

| Table | Index | Purpose |
|-------|-------|---------|
| company | (nse_symbol), (bse_code), (isin) | Lookups by exchange identifiers |
| company | (sector_id, market_cap DESC) | Sector screening |
| financial_statement | (company_id, period_type, fiscal_year) | Time-series queries |
| financial_metric | (statement_id, metric_name) | Metric lookups |
| quarterly_result | (company_id, fiscal_year, fiscal_quarter) | Quarterly data |
| research_document | (company_id, document_type, document_date) | Document retrieval |
| evidence | (document_id), (evidence_type) | Evidence queries |
| moat_assessment | (company_id, research_run_id) | Latest moat lookup |
| investment_thesis | (company_id, version DESC) | Latest thesis |
| research_run | (company_id, started_at DESC) | Research history |
| company_score | (company_id, research_run_id, dimension) | Score retrieval |

### Partitioning

- `financial_metric`: Partition by fiscal year range for large-scale historical queries
- `research_finding`: Partition by `created_at` month for growing research data
- `corporate_announcement`: Partition by year

## pgvector — Semantic Search

### Embedding Storage

```sql
CREATE TABLE document_embedding (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES research_document(id),
    chunk_index INT,
    chunk_text TEXT,
    embedding vector(1536),  -- Dimension matches embedding model
    metadata JSONB
);

CREATE INDEX ON document_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### Use Cases

| Use Case | Query Type |
|----------|-----------|
| "Find evidence of pricing power" | Semantic search across annual reports |
| Similar company discovery | Company description embeddings |
| Management commentary search | Transcript/presentation embeddings |
| Research finding retrieval | Prior research finding embeddings |

### Embedding Pipeline

```
Document Ingested
      │
      ▼
┌─────────────┐
│ Text         │  Extract text from PDF/HTML
│ Extraction   │
└──────┬──────┘
       ▼
┌─────────────┐
│ Chunking     │  Split by section/paragraph
│              │  Preserve metadata (page, section)
└──────┬──────┘
       ▼
┌─────────────┐
│ Embedding    │  EmbeddingProvider interface
│ Generation   │  (OpenAI, Cohere, etc.)
└──────┬──────┘
       ▼
┌─────────────┐
│ pgvector     │  Store with metadata
│ Storage      │
└─────────────┘
```

## Redis — Caching & Ephemeral State

### Cache Layers

| Cache | TTL | Purpose |
|-------|-----|---------|
| Company profile | 1 hour | Frequently accessed company data |
| Financial ratios | 6 hours | Pre-computed screening ratios |
| Screening results | 15 minutes | Saved screen results |
| Market data | 5 minutes | Current prices, market cap |
| Rate limit counters | Per provider | API rate limiting |
| Agent session state | 1 hour | In-progress research run state |
| User session | 24 hours | Authentication session |

### Cache Invalidation

- Financial data caches invalidate when new data is ingested
- Company profile cache invalidates on any company update
- Screen result caches invalidate on financial data refresh
- Explicit invalidation on user request ("refresh data")

## S3-Compatible Object Storage

### Bucket Structure

```
equity-research-documents/
├── annual-reports/
│   └── {company_id}/{fiscal_year}/
├── quarterly-results/
│   └── {company_id}/{fiscal_year}/Q{quarter}/
├── investor-presentations/
│   └── {company_id}/{date}/
├── corporate-filings/
│   └── {company_id}/{date}/
├── research-reports/
│   └── {research_run_id}/
└── transcripts/
    └── {company_id}/{date}/
```

### Storage Policy

- Original documents stored as-is (PDF, HTML)
- Extracted text stored alongside for search indexing
- Content hash (SHA-256) for deduplication
- Metadata stored in PostgreSQL, content in S3
- Local development uses MinIO

## Data Ingestion Architecture

### Pipeline Design

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Provider    │────▶│  Validation  │────▶│  Storage     │
│  Adapter     │     │  & Transform │     │  Layer       │
└──────────────┘     └──────────────┘     └──────────────┘
       │                     │                     │
  Rate limiting       Pydantic models        PostgreSQL
  Retry logic         Decimal conversion     S3 (documents)
  Auth handling       Deduplication          pgvector
  Error handling      Schema validation      Cache update
```

### Ingestion Scheduling

| Data Type | Frequency | Trigger |
|-----------|-----------|---------|
| Daily market data | Daily close | Scheduled (Celery beat) |
| Quarterly results | As filed | Event-driven (monitoring) |
| Annual reports | As published | Event-driven |
| Shareholding | Quarterly | Scheduled |
| Corporate announcements | Continuous | Polling |
| Macro indicators | As released | Scheduled |
| News | Continuous | Polling |

### Data Quality Checks

Every ingested record is validated:

1. **Schema validation**: Pydantic model conformance
2. **Range validation**: Financial values within reasonable bounds
3. **Consistency**: Balance sheet equation, CFO derivation
4. **Completeness**: Required fields present
5. **Freshness**: Data date is current
6. **Deduplication**: Content hash check

## Data Flow Patterns

### Research Run Data Flow

```
1. User/Schedule initiates research
2. ResearchRun record created (status: RUNNING)
3. Universe Discovery queries company + financial schemas
4. Financial Analysis reads financial schema, writes computed ratios
5. Domain agents read research documents from S3 via pgvector
6. Each agent writes ResearchFindings with evidence links
7. Valuation agent runs deterministic calculations
8. Quality gates query completeness of findings + evidence
9. Synthesis agent reads all findings, writes InvestmentThesis
10. ResearchRun updated (status: COMPLETED or INCOMPLETE)
```

### Thesis Change Detection Flow

```
1. New data ingested (quarterly result, announcement)
2. Monitoring agent detects change vs stored thesis
3. ThesisVersion created linking old → new
4. Alert generated for watchlist subscribers
5. Change summary stored with trigger reason
```

## Backup & Recovery

- PostgreSQL: Daily automated backups, point-in-time recovery
- S3: Versioning enabled, cross-region replication for production
- Redis: Ephemeral by design — cache rebuild from PostgreSQL on failure

## Data Retention

| Data Type | Retention |
|-----------|-----------|
| Financial statements | Indefinite (historical analysis requires it) |
| Source documents | Indefinite |
| Research runs | Indefinite (thesis versioning) |
| Cache | TTL-based, auto-expire |
| User sessions | 30 days |
| Audit logs | 2 years |
