# Solution Architecture

## System Overview

The Agentic Equity Research Platform is an evidence-driven research and decision-support system for Indian listed companies (NSE/BSE). It orchestrates a team of specialized AI agents to perform deep fundamental research, producing institutional-quality equity research with full source attribution.

The platform is NOT a stock-tip generator. It is a systematic research operating system that discovers, analyzes, and monitors companies while maintaining strict separation between facts, calculations, management claims, analyst opinions, AI inference, and uncertainty.

## Architecture Principles

- **Clean Architecture**: Domain logic at the center, dependencies point inward. No framework or infrastructure concerns leak into business logic.
- **Provider Abstraction**: Every external dependency (LLM, financial data, search) accessed through interfaces. Providers are swappable via configuration.
- **Evidence-First**: Every factual claim must be traceable to a source document. No LLM-fabricated financial data enters the system as fact.
- **Deterministic Computations**: Financial calculations performed by code, never by LLM arithmetic. `decimal.Decimal` for all monetary values.
- **Structured Agent Communication**: Agents exchange typed state objects, not free-text.

## Architecture Layers

```
┌──────────────────────────────────────────────────────┐
│                   Presentation Layer                  │
│  Next.js Dashboard  │  API Gateway  │  Research Chat  │
└──────────────┬───────────────────────┬───────────────┘
               │                       │
┌──────────────┴───────────────────────┴───────────────┐
│                   Application Layer                   │
│  Research Workflow  │  Screening  │  Portfolio Mgmt   │
│  Agent Orchestration (LangGraph)                      │
└──────────────┬───────────────────────┬───────────────┘
               │                       │
┌──────────────┴───────────────────────┴───────────────┐
│                    Domain Layer                       │
│  Company  │  Financial  │  Valuation  │  Research     │
│  Moat     │  Industry   │  Evidence   │  Thesis       │
│  Risk     │  Macro      │  Scoring    │  Agent Tools  │
└──────────────┬───────────────────────┬───────────────┘
               │                       │
┌──────────────┴───────────────────────┴───────────────┐
│                 Infrastructure Layer                  │
│  PostgreSQL/pgvector  │  Redis  │  S3  │  Celery      │
│  LLM Providers  │  Data Providers  │  Search          │
│  OpenTelemetry  │  Auth (OAuth/JWT)                   │
└──────────────────────────────────────────────────────┘
```

## Component Architecture

### Frontend (Next.js)

| Component | Responsibility |
|-----------|---------------|
| Dashboard | Market overview, sector heatmap, research candidates, alerts |
| Stock Screener | Interactive multi-filter screening with AND/OR conditions |
| Company Detail | Full research view — financials, moat, valuation, thesis |
| Research Chat | Interactive AI research assistant per company |
| Portfolio / Watchlist | User-created lists with monitoring and alerts |
| Report Viewer | Rendered research reports with evidence drill-down |
| Scorecard | Multi-dimensional quality scores with evidence links |

### Backend (FastAPI)

| Service | Responsibility |
|---------|---------------|
| API Layer | REST endpoints, WebSocket for real-time updates, auth middleware |
| Research Engine | Orchestrates agent workflows via LangGraph |
| Screening Engine | Configurable financial screening with saved screens |
| Valuation Engine | Deterministic multi-model valuation (DCF, multiples, reverse DCF) |
| Scoring Engine | Evidence-backed multi-dimensional company scoring |
| Evidence Engine | Source tracking, citation management, provenance metadata |
| Data Ingestion | Provider-abstracted financial data pipelines |
| Quality Gate Engine | Pre-publication research validation (12 gates) |

### Agent Layer (LangGraph)

17 specialized agents with structured state passing. See `agent-architecture.md`.

### Data Layer

| Store | Purpose |
|-------|---------|
| PostgreSQL | Relational data — companies, financials, research, users |
| pgvector | Document embeddings for semantic search |
| Redis | Caching, rate limiting, session state |
| S3-compatible | Annual reports, presentations, filing PDFs |

## Data Flow

### Research Workflow

```
User Request (company/screen)
        │
        ▼
┌─────────────────┐
│ Universe         │──── Market Data Provider
│ Discovery Agent  │──── Financial Data Provider
└────────┬────────┘
         ▼
┌─────────────────┐
│ Financial        │──── Financial Statements (5-10yr)
│ Analysis Agent   │──── Quarterly Results
└────────┬────────┘
         ▼
┌─────────────────┐
│ Business Model / │──── Annual Reports
│ Industry / Moat  │──── Investor Presentations
│ Agents           │──── Corporate Filings
└────────┬────────┘
         ▼
┌─────────────────┐
│ Management /     │──── Shareholding Data
│ Macro / Growth   │──── Corporate Actions
│ Agents           │──── Macro Indicators
└────────┬────────┘
         ▼
┌─────────────────┐
│ Valuation Agent  │──── Deterministic Calculation Engine
└────────┬────────┘
         ▼
┌─────────────────┐
│ Risk / Bull /    │
│ Bear / Thesis    │
│ Challenger       │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Evidence         │──── Citation Verification
│ Verification     │──── Source Validation
└────────┬────────┘
         ▼
┌─────────────────┐
│ Research         │──── Quality Gates (12 checks)
│ Synthesis        │──── Report Generation
└────────┬────────┘
         ▼
    Research Report
    (with full provenance)
```

### Data Ingestion Flow

```
External Provider APIs
        │
        ▼
┌─────────────────┐
│ Provider         │  Abstracted interfaces
│ Adapters         │  Rate limiting, retry, auth
└────────┬────────┘
         ▼
┌─────────────────┐
│ Validation &     │  Schema validation (Pydantic)
│ Normalization    │  decimal.Decimal for financials
└────────┬────────┘
         ▼
┌─────────────────┐
│ Storage Layer    │  PostgreSQL (structured)
│                  │  S3 (documents)
│                  │  pgvector (embeddings)
└─────────────────┘
```

## Integration Points

| External System | Integration Method | Provider Interface |
|----------------|-------------------|-------------------|
| NSE | API / Web scraping | MarketDataProvider, CorporateFilingsProvider |
| BSE | API / Web scraping | MarketDataProvider, CorporateFilingsProvider |
| SEBI | API / Web scraping | CorporateFilingsProvider |
| SEC EDGAR | API | CorporateFilingsProvider |
| Alpha Vantage | REST API | MarketDataProvider |
| Polygon.io | REST API | MarketDataProvider |
| Anthropic Claude | REST API | LLMProvider |
| OpenAI | REST API | LLMProvider |
| S3-compatible | SDK | Object Storage |

## Non-Functional Requirements

| Requirement | Target |
|------------|--------|
| Research latency (single company) | < 5 minutes for full analysis |
| Screening response | < 3 seconds for pre-computed screens |
| Concurrent research runs | Support 5+ simultaneous |
| Data freshness | Daily price data, quarterly financials within 24h of filing |
| Availability | 99.5% uptime for dashboard |
| Evidence traceability | 100% of factual claims linked to source |
| Financial calculation accuracy | Zero floating-point errors (decimal.Decimal) |
| Test coverage | 80%+ line coverage for new modules |

## Technology Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript (strict), Tailwind CSS, Recharts/Tremor |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 |
| Agent Orchestration | LangGraph |
| Database | PostgreSQL 16+, pgvector |
| Cache | Redis 7+ |
| Object Storage | S3-compatible (MinIO for local dev) |
| Background Tasks | Celery or Temporal (ADR pending) |
| Observability | OpenTelemetry, structured logging, Prometheus/Grafana |
| LLM | Provider abstraction — Claude, OpenAI initially |
| Auth | OAuth 2.0 / JWT |
| Deployment | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Testing | pytest, Vitest, Playwright |
