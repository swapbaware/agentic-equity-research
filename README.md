# Agentic Equity Research Platform

An AI-agent-powered equity research platform that automates and augments fundamental analysis of public equities. The system combines financial data ingestion, quantitative analysis, and large-language-model-driven research to produce institutional-quality equity research reports.

## High-Level Architecture

```
                  ┌─────────────┐
                  │   Frontend   │  React / Next.js dashboard
                  └──────┬──────┘
                         │ REST / WebSocket
                  ┌──────┴──────┐
                  │   Backend    │  Python (FastAPI) orchestration layer
                  │  ┌────────┐  │
                  │  │ Agents │  │  LLM-powered research agents
                  │  └────────┘  │
                  └──────┬──────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────┴───┐   ┌─────┴────┐  ┌─────┴─────┐
   │ Financial │   │ Document │  │  Vector   │
   │ Data APIs │   │  Store   │  │  Store    │
   └──────────┘   └──────────┘  └───────────┘
```

## Planned Technology Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic
- **AI / Agents:** Claude API, OpenAI API, custom agent framework
- **Financial Data:** SEC EDGAR, Yahoo Finance, Alpha Vantage, Polygon.io (behind provider abstraction)
- **Frontend:** TypeScript, React, Next.js, Tailwind CSS
- **Database:** PostgreSQL, Redis (caching), pgvector or Pinecone (embeddings)
- **Infrastructure:** Docker, Docker Compose, GitHub Actions CI/CD
- **Testing:** pytest (backend), Vitest (frontend)

## Development Phases

| Phase | Name                       | Status      |
|-------|----------------------------|-------------|
| 0     | Repository Setup           | In Progress |
| 1     | Core Backend Foundation    | Not Started |
| 2     | Financial Data Pipeline    | Not Started |
| 3     | AI Agent Framework         | Not Started |
| 4     | Frontend Dashboard         | Not Started |
| 5     | Integration & Deployment   | Not Started |

## Getting Started

See `implementation-plan.md` for the full roadmap.
See `CLAUDE.md` for engineering principles and contribution guidelines.

## License

TBD
