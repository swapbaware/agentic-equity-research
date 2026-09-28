# Agentic Equity Research Platform

An evidence-driven AI-agent-powered equity research platform for Indian listed companies (NSE/BSE). The system orchestrates 17 specialized research agents to perform deep fundamental analysis — combining financial data ingestion, quantitative analysis, moat assessment, and LLM-driven research to produce institutional-quality equity research reports with full source attribution.

This is a **research and decision-support system**, not a stock-tip generator. It systematically discovers businesses with strong economics, durable competitive advantages, and attractive structural growth opportunities while aggressively searching for evidence that could invalidate the thesis.

## High-Level Architecture

```
                  ┌─────────────┐
                  │   Frontend   │  Next.js / TypeScript dashboard
                  └──────┬──────┘
                         │ REST / WebSocket
                  ┌──────┴──────┐
                  │   Backend    │  Python (FastAPI) orchestration
                  │  ┌────────┐  │
                  │  │17 Agents│ │  LangGraph-orchestrated research
                  │  └────────┘  │
                  └──────┬──────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
┌──────┴───┐     ┌───────┴──────┐   ┌─────┴─────┐
│ Financial │     │  PostgreSQL  │   │  Object   │
│ Data APIs │     │  + pgvector  │   │  Storage  │
│ (NSE/BSE) │     │  + Redis     │   │  (S3)     │
└──────────┘     └──────────────┘   └───────────┘
```

## Research Agents

| Agent | Responsibility |
|-------|---------------|
| Universe Discovery | Company screening and filtering |
| Financial Analysis | 5-10yr quantitative analysis + forensics |
| Business Model | Revenue streams, competitive dynamics |
| Industry Analysis | TAM, Porter's Five Forces, structure |
| Competitive Moat | 16 moat types with evidence |
| Management & Governance | Ownership, capital allocation, execution |
| Future Growth | Optionality classification by maturity |
| Macro Economics | Company-specific macro factor mapping |
| Competitor Analysis | Peer comparison and positioning |
| Valuation | Multi-model valuation (DCF, multiples, bands) |
| Risk | Systematic risk identification |
| Bull Case | Optimistic scenario construction |
| Bear Case | Pessimistic scenario construction |
| Thesis Challenger | Devil's Advocate / disprove thesis |
| Evidence Verification | Source citation validation |
| Research Synthesis | Thesis generation with quality gates |
| Portfolio Monitoring | Watchlist alerts and thesis change detection |

## Technology Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0
- **AI / Agents:** LangGraph, Claude API, OpenAI API (provider-abstracted)
- **Financial Data:** NSE, BSE, Alpha Vantage, Polygon.io (provider-abstracted)
- **Frontend:** TypeScript (strict), React, Next.js, Tailwind CSS
- **Database:** PostgreSQL 16+ with pgvector, Redis 7+
- **Storage:** S3-compatible (MinIO for local dev)
- **Background Tasks:** Celery (evaluating Temporal)
- **Observability:** OpenTelemetry, structured logging, Prometheus/Grafana
- **Infrastructure:** Docker, Docker Compose, GitHub Actions CI/CD
- **Testing:** pytest, Vitest, Playwright

## Development Phases

| Phase | Name                       | Status      |
|-------|----------------------------|-------------|
| 0     | Repository Setup           | Complete    |
| 1     | Architecture & Planning    | Complete    |
| 2     | Core Backend Foundation    | Not Started |
| 3     | Domain & Data Model        | Not Started |
| 4     | Provider Framework         | Not Started |
| 5     | Evidence & Citation System | Not Started |
| 6     | Financial Calculation Engine| Not Started |
| 7     | Agent Implementation       | Not Started |
| 8     | API Layer                  | Not Started |
| 9     | Frontend Dashboard         | Not Started |
| 10    | Integration & Deployment   | Not Started |

## Documentation

| Document | Description |
|----------|-------------|
| [`CLAUDE.md`](CLAUDE.md) | Engineering principles |
| [`implementation-plan.md`](implementation-plan.md) | Full development roadmap |
| [`progress.md`](progress.md) | Phase-by-phase progress tracker |
| [`architecture/solution-architecture.md`](architecture/solution-architecture.md) | System architecture |
| [`architecture/domain-model.md`](architecture/domain-model.md) | Domain entities and relationships |
| [`architecture/agent-architecture.md`](architecture/agent-architecture.md) | Agent design and orchestration |
| [`architecture/data-architecture.md`](architecture/data-architecture.md) | Data storage and pipelines |
| [`architecture/security-architecture.md`](architecture/security-architecture.md) | Security model |
| [`architecture/deployment-architecture.md`](architecture/deployment-architecture.md) | Deployment and CI/CD |
| [`docs/api-provider-strategy.md`](docs/api-provider-strategy.md) | Provider abstraction strategy |
| [`docs/research-methodology.md`](docs/research-methodology.md) | Research methodology and quality gates |
| [`docs/testing-strategy.md`](docs/testing-strategy.md) | Testing approach |

## License

TBD
