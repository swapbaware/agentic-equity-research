# Implementation Plan

## Overview

This document describes the implementation roadmap for the Agentic Equity Research Platform — an evidence-driven research system for Indian listed companies (NSE/BSE). Each phase builds on the previous one, ending with a working, tested increment. The platform is NOT a stock-tip generator; it is a systematic research operating system.

## Guiding Principles for Sequencing

1. **Foundation before features:** Infrastructure and abstractions before business logic.
2. **Data before agents:** Reliable financial data pipelines before AI agent development, because agents need real data to operate on.
3. **Backend before frontend:** API contracts before UI, because the frontend is a consumer of backend capabilities.
4. **Abstractions before implementations:** Provider interfaces before concrete integrations, enabling parallel work and easy swapping.
5. **Phase-by-phase with quality gates:** Each phase is complete with tests before moving to the next.

## Phase 0 — Repository Setup (COMPLETE)

**Goal:** Establish project structure, documentation, and engineering standards.
**Deliverables:** README, CLAUDE.md, directory structure, .gitignore, .env.example, initial commit.

## Phase 1 — Architecture & Planning (COMPLETE)

**Goal:** Convert the master specification into actionable architecture artifacts.
**Deliverables:**
- Solution architecture (layers, components, data flow)
- Domain model (30+ entities, relationships, invariants)
- Agent architecture (17 agents, LangGraph orchestration, memory layers)
- Data architecture (PostgreSQL/pgvector/Redis/S3, ingestion pipeline)
- Security architecture (auth, agent sandboxing, prompt injection defense)
- Deployment architecture (Docker, CI/CD, observability)
- 6 Architecture Decision Records
- API & provider strategy
- Research methodology
- Testing strategy

## Phase 2 — Core Backend Foundation

**Goal:** A running Python backend with configuration, logging, database connectivity, and a CI pipeline.

**Key Deliverables:**
- Python project with `pyproject.toml`, dependency management (Poetry or uv)
- FastAPI application with health check endpoint
- Pydantic-settings configuration (env-based)
- Structured JSON logging with OpenTelemetry correlation IDs
- Alembic migration framework (empty initial migration)
- pytest setup with fixtures and coverage
- CI pipeline: ruff (lint) + mypy (type check) + pytest (test)

**Key Decisions:**
- FastAPI for async HTTP and WebSocket
- Pydantic v2 for all data validation
- SQLAlchemy 2.0 with async driver
- ruff for linting (replaces flake8/black/isort)
- mypy in strict mode

**Duration:** 1–2 sessions.

## Phase 3 — Domain & Data Model

**Goal:** Implement all domain entities as Pydantic models and SQLAlchemy ORM models with database migrations.

**Key Deliverables:**
- All entities from `architecture/domain-model.md` as Pydantic + SQLAlchemy models
- Database migrations creating all tables
- Repository layer (async CRUD operations)
- Value objects (Money, Percentage, FinancialRatio)
- Enum definitions for all categorical fields
- Model validation tests

**Key Decisions:**
- `NUMERIC` column type for all financial values (never FLOAT)
- UUID primary keys
- JSONB for flexible nested data (business segments, assumptions)
- Temporal partitioning strategy for high-volume tables

**Duration:** 2–3 sessions.

## Phase 4 — Provider Framework

**Goal:** Define and implement provider interfaces for all external service categories.

**Key Deliverables:**
- 11 provider interfaces (Protocol classes)
- Common error hierarchy (`ProviderError` and subtypes)
- Redis-backed rate limiter
- Retry framework with exponential backoff
- Provider factory with configuration-driven selection
- At least one concrete implementation per interface (can be stub/mock for MVP)
- Provider conformance test suite

**Key Decisions:**
- Python `Protocol` for interface definitions (structural typing)
- Rate limiting in Redis with token bucket algorithm
- `Decimal` conversion at provider boundary (never pass floats inward)

**Duration:** 2–3 sessions.

## Phase 5 — Evidence & Citation System

**Goal:** Build the evidence pipeline — from document ingestion to citation tracking.

**Key Deliverables:**
- Document ingestion pipeline (PDF/HTML → text extraction → storage)
- S3 document storage (MinIO for local dev)
- Embedding generation via EmbeddingProvider
- pgvector storage and semantic search
- Evidence extraction and storage
- Citation tracking (finding → evidence → document)
- Source tier classification
- Citation completeness validation

**Duration:** 2–3 sessions.

## Phase 6 — Financial Calculation Engine

**Goal:** Deterministic financial calculations — all `decimal.Decimal`, all tested against golden datasets.

**Key Deliverables:**
- CAGR, ratio, and margin calculators
- DCF model with configurable assumptions
- Reverse DCF model
- Multiple-based valuation models (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF)
- Historical valuation band analysis
- Peer comparison engine
- Scenario engine (Bear/Base/Bull with explicit assumptions)
- Financial forensics / red flag scoring
- Multi-criteria screening engine (AND/OR logic, saved screens)
- Golden dataset tests with hand-verified calculations

**Key Decisions:**
- All arithmetic uses `decimal.Decimal`
- Rounding rules documented per calculation type
- Valuation models always produce ranges, never single values
- All assumptions visible in output

**Duration:** 3–4 sessions.

## Phase 7 — Agent Implementation

**Goal:** Implement all 17 agents with LangGraph orchestration and quality gates.

**Key Deliverables:**
- LangGraph workflow graph with typed `ResearchState`
- Agent tool framework (input/output schemas, auth, logging)
- All 17 agents:
  1. Universe Discovery
  2. Financial Analysis (including forensics)
  3. Business Model
  4. Industry Analysis
  5. Competitive Moat (16 moat types)
  6. Management & Governance
  7. Future Growth & Optionality
  8. Macro Economics
  9. Competitor Analysis
  10. Valuation
  11. Risk
  12. Bull Case
  13. Bear Case
  14. Thesis Challenger (Devil's Advocate)
  15. Evidence Verification
  16. Research Synthesis
  17. Portfolio/Watchlist Monitoring
- Quality gate engine (12 gates)
- Agent workflow tests with mock LLM
- Reproducibility tests

**Key Decisions:**
- LangGraph for orchestration (ADR-001)
- Agents communicate via typed state, not free-text
- Parallel execution where data dependencies allow
- Quality gate failure → RESEARCH INCOMPLETE, not fabrication

**Duration:** 6–8 sessions.

## Phase 8 — API Layer

**Goal:** RESTful API exposing all platform capabilities.

**Key Deliverables:**
- Company CRUD and search endpoints
- Financial data endpoints (statements, ratios, time-series)
- Screening endpoints (filter, save, load screens)
- Research run endpoints (initiate, status, results)
- Thesis and report endpoints
- Watchlist/portfolio endpoints
- Research chat endpoint (WebSocket)
- Authentication (OAuth 2.0 / JWT)
- Authorization (RBAC: viewer, analyst, admin)
- OpenAPI documentation
- API tests (httpx TestClient)

**Duration:** 2–3 sessions.

## Phase 9 — Frontend Dashboard

**Goal:** A web dashboard for research, screening, and monitoring.

**Key Deliverables:**
- Next.js + TypeScript strict + Tailwind CSS
- Authentication UI
- Main dashboard (market overview, sector heatmap, research candidates, alerts)
- Stock screener (interactive filters, AND/OR, saved screens)
- Company detail page (overview, financials, moat, valuation, thesis, risks, catalysts)
- Company scorecard (10-dimension, evidence drill-down, no opaque scores)
- Research report viewer (with evidence labels: FACT/CALCULATION/etc.)
- AI research chat (interactive questions per company)
- Watchlist/portfolio management with alerts
- Interactive financial charts
- Responsive design (mobile + desktop)
- Frontend tests (Vitest + Playwright)

**Duration:** 4–6 sessions.

## Phase 10 — Integration & Deployment

**Goal:** Production-ready deployment with observability and end-to-end validation.

**Key Deliverables:**
- Docker Compose with all services
- Multi-stage Dockerfiles (backend, frontend)
- Database seed data (10-20 representative Indian companies)
- OpenTelemetry integration (traces, metrics, structured logs)
- Prometheus/Grafana dashboards
- End-to-end tests (Playwright)
- Security review
- Performance baseline
- Documentation finalization
- Production deployment guide

**Duration:** 2–3 sessions.

## MVP Scope (Phases 2–8)

The minimum viable product includes:
1. Indian stock universe (NSE/BSE)
2. Financial data ingestion from at least one provider
3. Company search
4. Stock screener with financial filters
5. Financial dashboard per company
6. Basic valuation (multiples + DCF)
7. Company research agent (full 17-agent workflow for single company)
8. Moat analysis with evidence
9. Industry analysis
10. Research report with source citations
11. AI research chat
12. Quality gates

## Architecture Documents Reference

| Document | Path |
|----------|------|
| Solution Architecture | `architecture/solution-architecture.md` |
| Domain Model | `architecture/domain-model.md` |
| Agent Architecture | `architecture/agent-architecture.md` |
| Data Architecture | `architecture/data-architecture.md` |
| Security Architecture | `architecture/security-architecture.md` |
| Deployment Architecture | `architecture/deployment-architecture.md` |
| ADR-001: LangGraph | `architecture/adr/001-langgraph-for-agent-orchestration.md` |
| ADR-002: Background Tasks | `architecture/adr/002-background-task-processor.md` |
| ADR-003: Decimal | `architecture/adr/003-decimal-for-financial-calculations.md` |
| ADR-004: Evidence Citations | `architecture/adr/004-evidence-citation-system.md` |
| ADR-005: Provider Abstraction | `architecture/adr/005-provider-abstraction-pattern.md` |
| ADR-006: India Market Focus | `architecture/adr/006-india-market-focus.md` |
| Provider Strategy | `docs/api-provider-strategy.md` |
| Research Methodology | `docs/research-methodology.md` |
| Testing Strategy | `docs/testing-strategy.md` |
