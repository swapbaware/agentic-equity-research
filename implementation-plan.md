# Implementation Plan

## Overview

This document describes the implementation roadmap for the Agentic Equity Research Platform — an evidence-driven research system for Indian listed companies (NSE/BSE). Each phase builds on the previous one, ending with a working, tested increment. The platform is NOT a stock-tip generator; it is a systematic research operating system.

## Guiding Principles for Sequencing

1. **Foundation before features:** Infrastructure and abstractions before business logic.
2. **Data before agents:** Reliable financial data pipelines before AI agent development, because agents need real data to operate on.
3. **Backend before frontend:** API contracts before UI, because the frontend is a consumer of backend capabilities.
4. **Abstractions before implementations:** Provider interfaces before concrete integrations, enabling parallel work and easy swapping.
5. **Phase-by-phase with quality gates:** Each phase is complete with tests before moving to the next.

---

## Phase 0 — Repository Setup

**Goal:** Establish project structure, documentation, and engineering standards.

**Dependencies:** None.

**Deliverables:**
- README.md with project overview and architecture diagram
- CLAUDE.md engineering constitution
- Directory structure (architecture/, docs/, backend/, frontend/, infrastructure/, scripts/, tests/)
- .gitignore, .env.example, .gitattributes
- Initial commit pushed to GitHub

**Acceptance Criteria:**
- Repository exists on GitHub with clean main branch
- All 7 directories created
- .gitignore covers Python, Node.js, secrets, IDEs, OS files
- .env.example documents all required environment variables with placeholder values
- No secrets in committed files

**Tests:** Manual verification — clean `git status`, no secrets in repo.

**Status:** COMPLETE — Commits `d5a975e`, `7035fdf`

---

## Phase 1 — Architecture & Planning

**Goal:** Convert the master specification into actionable, reviewed architecture artifacts.

**Dependencies:** Phase 0.

**Deliverables:**
- Solution architecture (layers, components, data flow, NFRs)
- Domain model (30+ entities, relationships, 7 invariants, value objects)
- Agent architecture (17 agents, LangGraph orchestration, memory layers, timeout/cost budgets)
- Data architecture (PostgreSQL schema, pgvector, Redis caching, S3 storage, ingestion pipeline)
- Security architecture (OAuth/JWT, RBAC, prompt injection defense, DPDP Act)
- Deployment architecture (Docker Compose, CI/CD, observability, alerting, migration/rollback)
- 9 Architecture Decision Records (ADR-001 through ADR-009)
- API & provider strategy (12 provider interfaces, data source tiering, rate limiting)
- Research methodology (15 dimensions, 12 quality gates, 10-dimension scoring)
- Testing strategy (8 categories, coverage targets, golden datasets)
- 20-point architecture review with remediation

**Acceptance Criteria:**
- All architecture documents internally consistent (no contradictions between documents)
- SEC EDGAR removed (India-only scope)
- NSE data access risk documented with mitigation strategy (ADR-009)
- Failure modes documented with bounded retry (max 2 iterations, 15-min timeout)
- LLM cost controls documented with per-agent budgets
- No unresolved critical gaps (open items tracked in progress.md)

**Tests:** Architecture review checklist (20 points reviewed and addressed).

**Status:** COMPLETE — Commits `387d53a`, `41f3c77`

---

## Phase 2 — Core Backend Foundation

**Goal:** A running Python backend with configuration, logging, database connectivity, and a CI pipeline.

**Dependencies:** Phase 1 (architecture docs as reference).

**Deliverables:**
- Python project with `pyproject.toml`, dependency management (uv or Poetry)
- FastAPI application with health check endpoint (`GET /health`)
- Readiness endpoint (`GET /health/ready`)
- Pydantic-settings configuration (env-based, all vars from .env.example)
- Structured JSON logging with OpenTelemetry correlation IDs
- SQLAlchemy 2.0 async engine with connection pooling
- Alembic migration framework (empty initial migration)
- pytest setup with fixtures, factories, and coverage reporting
- CI pipeline: ruff (lint) + mypy strict (type check) + pytest (test) + coverage threshold

**Acceptance Criteria:**
- `docker-compose up` starts backend + PostgreSQL + Redis
- `GET /health` returns 200 with DB and Redis connectivity status
- `GET /health/ready` returns 200 when migrations are current
- `alembic upgrade head` runs without error on clean database
- `alembic downgrade -1` reverses the initial migration
- All Python code passes `ruff check` and `mypy --strict`
- pytest runs with ≥80% coverage on new code
- CI pipeline runs on push/PR and blocks on failure
- No `float` types in any financial-related code paths
- Configuration loads from environment variables, not hardcoded values

**Tests:**
- Health check endpoint returns correct status
- Configuration loads all required env vars
- Database connection pool creates and releases connections
- Alembic upgrade/downgrade cycle completes without error
- Structured log output is valid JSON with trace_id

**Status:** NOT STARTED

**Key Decisions:**
- Evaluate uv vs Poetry for dependency management
- Evaluate Celery vs Temporal for background tasks (ADR-002)

---

## Phase 3 — Domain & Data Model

**Goal:** Implement all domain entities as Pydantic models and SQLAlchemy ORM models with database migrations.

**Dependencies:** Phase 2 (FastAPI app, Alembic, pytest).

**Deliverables:**
- All entities from `architecture/domain-model.md` as Pydantic + SQLAlchemy models
- Value objects: Money, Percentage, FinancialRatio, DateRange, SourceCitation, CAGRResult
- Enum definitions for all categorical fields (EvidenceType, ResearchStatus, MoatStrength, etc.)
- Database migrations creating all tables across 10 schemas
- Repository layer (async CRUD operations per entity)
- Model validation tests
- Junction tables for many-to-many relationships

**Acceptance Criteria:**
- All 30+ entities from domain model implemented with correct field types
- All financial columns use `NUMERIC` (verified by migration inspection)
- UUID primary keys on all entities
- `created_at` / `updated_at` on all entities
- Value objects enforce invariants (Money rejects negative amounts where appropriate, Percentage validates range)
- Pydantic models reject invalid data (wrong types, out-of-range values)
- Repository layer supports async CRUD for all entities
- All migrations reversible (`downgrade()` tested)
- No `float` anywhere in financial model definitions

**Tests:**
- Pydantic model validation: valid data accepted, invalid rejected (per entity)
- Value object arithmetic: Money + Money, Percentage calculations, FinancialRatio
- SQLAlchemy model round-trip: create → read → update → delete
- Migration up/down cycle on clean database
- Financial column type assertions (NUMERIC, not FLOAT)
- Balance sheet equation invariant enforcement
- Enum value completeness (all values from domain model present)

**Status:** NOT STARTED

**Key Decisions:**
- UUID v7 vs v4 for primary keys (v7 for time-ordering if available)
- JSONB field structure for flexible nested data

---

## Phase 4 — Provider Framework

**Goal:** Define and implement provider interfaces for all external service categories with at least one concrete implementation per interface.

**Dependencies:** Phase 3 (domain models for type safety at provider boundary).

**Deliverables:**
- 12 provider Protocol interfaces (MarketData, FinancialData, CorporateFilings, Shareholding, CorporateActions, News, Search, MacroData, Transcript, LLM, Embedding, PriceHistory)
- Common error hierarchy (`ProviderError` and subtypes)
- Redis-backed rate limiter (token bucket)
- Retry framework with exponential backoff and Retry-After respect
- Provider factory with configuration-driven selection
- At least one concrete implementation per interface (stub/mock acceptable for MVP)
- Provider conformance test suite
- BSE API integration (first real provider)
- SEBI XBRL parser (if data format analysis is complete)

**Acceptance Criteria:**
- Every provider interface defined as a Python `Protocol` with typed methods
- All financial values returned as `decimal.Decimal` (tested at boundary)
- Rate limiter correctly throttles requests per provider configuration
- Retry logic handles 429/5xx correctly (exponential backoff, respects Retry-After)
- Auth errors (401/403) fail immediately, no retry
- Provider factory selects implementation based on configuration
- Switching provider requires zero changes to business logic
- Provider conformance test suite validates any implementation against the interface contract
- At least one real provider (BSE API) fetches and parses live data correctly

**Tests:**
- Protocol conformance: every implementation satisfies its Protocol
- Rate limiter: blocks when limit exceeded, allows when tokens available
- Retry: correct backoff timing, retry count, Retry-After header respect
- Error hierarchy: each error type maps correctly from HTTP status codes
- Decimal boundary: provider never returns float for financial values
- Factory: correct implementation returned per configuration
- BSE API integration test (CI-skippable): fetches real company data

**Status:** NOT STARTED

**Key Decisions:**
- NSE data access strategy (ADR-009 — open)
- Commercial vendor evaluation if free sources are insufficient

---

## Phase 5 — Evidence & Citation System

**Goal:** Build the evidence pipeline — from document ingestion to citation tracking and semantic search.

**Dependencies:** Phase 4 (EmbeddingProvider), Phase 3 (Evidence/ResearchDocument models).

**Deliverables:**
- Document ingestion pipeline (PDF/HTML → text extraction → storage)
- Document sanitization (strip executable content, JavaScript, macros)
- S3/MinIO document storage with SHA-256 deduplication
- Embedding generation via EmbeddingProvider
- pgvector storage and semantic search
- Evidence extraction and storage
- Citation tracking (finding → evidence → document chain)
- Source tier classification (Tier 1/2/3)
- Citation completeness validation

**Acceptance Criteria:**
- PDF text extraction produces readable text from sample annual reports
- HTML sanitization removes all executable content
- Duplicate documents detected by SHA-256 content hash
- Embeddings stored in pgvector with correct dimensionality
- Semantic search returns relevant chunks for test queries
- Citation chain is complete: every Evidence record links to a ResearchDocument
- Source tier is recorded on every Evidence record
- Citation completeness validator catches missing citations on FACT-type findings
- Embedding dimension is configurable per provider (not hardcoded to 1536)

**Tests:**
- PDF extraction: sample PDF → expected text output
- HTML sanitization: malicious HTML → clean text (no script, no event handlers)
- Deduplication: same document ingested twice → single storage entry
- Embedding round-trip: text → embedding → storage → retrieval → similarity match
- Citation chain integrity: finding → evidence → document links valid
- Source tier assignment: Tier 1 for BSE data, Tier 3 for news
- Completeness validation: FACT without citation → flagged, FACT with citation → passes

**Status:** NOT STARTED

---

## Phase 6 — Financial Calculation Engine

**Goal:** Deterministic financial calculations — all `decimal.Decimal`, all tested against golden datasets.

**Dependencies:** Phase 3 (financial models), Phase 4 (data providers for real inputs).

**Deliverables:**
- CAGR calculation
- Ratio calculations (ROE, ROCE, ROIC, margins — all 20+ ratios from research methodology)
- DCF model with configurable assumptions
- Reverse DCF model
- Multiple-based valuation models (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF)
- Historical valuation band analysis
- Peer comparison engine
- Scenario engine (Bear/Base/Bull with explicit assumptions)
- Financial forensics / red flag scoring
- Multi-criteria screening engine (AND/OR logic, saved screens)
- Golden dataset tests with hand-verified calculations

**Acceptance Criteria:**
- Every calculation function accepts and returns `decimal.Decimal` exclusively
- No `float` in any calculation code path (enforced by type checker + tests)
- DCF model requires explicit assumptions for all inputs (no hidden defaults)
- Valuation models produce ranges (low/mid/high), never single values
- All assumptions visible in output objects
- Scenario engine produces Bear/Base/Bull with explicit per-scenario assumptions
- Financial forensics produces a red flag score with per-check evidence
- Screening engine supports AND/OR filters across all financial metrics
- Golden dataset: all calculations match hand-verified values for 3-5 reference companies

**Tests:**
- CAGR: known inputs → known output (e.g., 100→200 over 5 years = 14.87%)
- Every ratio: known financial statement inputs → exact expected ratio
- DCF: hand-calculated DCF with known inputs matches engine output
- Reverse DCF: given market price, derived implied growth rate is correct
- Multiples: P/E, EV/EBITDA match manual calculation
- Valuation bands: historical data produces correct percentile ranges
- Scenario engine: Bear/Base/Bull produce three distinct, valid results
- Forensics: known red flags (receivables growing faster than revenue) detected
- Screening: compound filter (ROCE>15 AND Debt/Equity<0.5 AND MarketCap>1000Cr) returns correct companies
- Edge cases: division by zero, negative equity, zero revenue

**Status:** NOT STARTED

---

## Phase 7 — Agent Implementation

**Goal:** Implement all 17 agents with LangGraph orchestration, quality gates, and cost controls.

**Dependencies:** Phase 5 (evidence system), Phase 6 (calculation engine), Phase 4 (all providers).

**Deliverables:**
- LangGraph workflow graph with typed `ResearchState`
- Agent base class and tool framework (input/output schemas, auth, logging, timeout)
- All 17 agents (see `architecture/agent-architecture.md`)
- Quality gate engine (12 gates)
- Per-agent timeout enforcement
- Per-agent token budget enforcement
- LangGraph checkpointing for resume on failure
- Redis advisory lock for concurrent run prevention
- Agent workflow tests with mock LLM
- Reproducibility tests

**Acceptance Criteria:**
- LangGraph graph compiles and executes with mock LLM
- All 17 agents produce outputs conforming to their Pydantic output schemas
- Parallel execution: agents without data dependencies run concurrently
- Quality gate loop: max 2 iterations (1 initial + 1 retry), then INCOMPLETE
- Per-agent timeout: agent killed after timeout, workflow continues
- Per-agent token budget: agent stopped if budget exceeded
- Total run timeout: 15 minutes max
- Redis lock: concurrent research on same company blocked
- LangGraph checkpointing: interrupted run can resume from last checkpoint
- Evidence Verification Agent performs deterministic structural checks (document exists, financial figures cross-checked) in addition to semantic checks
- Thesis Challenger runs in parallel with Bull/Bear, challenges accumulated findings
- Failed agent: marked FAILED, workflow continues with independent agents
- Quality gate failure: output marked RESEARCH INCOMPLETE, not fabricated
- Moat default: NONE. Score default: 0. Evidence required to upgrade.

**Tests:**
- Graph execution: end-to-end with mock LLM, all agents complete
- Agent output schema: each agent's output validates against Pydantic model
- Parallel execution: verify concurrent agents via timing assertions
- Quality gate pass: known-good inputs → all 12 gates pass
- Quality gate fail: incomplete data → specific gates fail → INCOMPLETE status
- Retry limit: quality gate fails twice → no third attempt → INCOMPLETE
- Timeout: slow mock agent → killed after timeout → workflow continues
- Token budget: verbose mock agent → stopped at budget → workflow continues
- Concurrent run lock: two research runs on same company → second blocked
- Checkpoint resume: interrupted run → resume → completes from checkpoint
- Evidence verification: FACT without document → flagged; FACT with valid document → passes
- Reproducibility: same inputs twice → structurally consistent outputs

**Status:** NOT STARTED

**Key Decisions:**
- Resolve LLMProvider interface alignment with LangGraph native invocation (K-4)

---

## Phase 8 — API Layer

**Goal:** RESTful API exposing all platform capabilities with authentication and authorization.

**Dependencies:** Phase 7 (agents), Phase 6 (screening/valuation), Phase 3 (all models).

**Deliverables:**
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

**Acceptance Criteria:**
- All endpoints follow URL-prefix versioning (`/api/v1/...`)
- List endpoints use cursor-based pagination (next_cursor, has_more)
- Error responses use consistent JSON format (`{"error": {"code", "message", "details"}}`)
- All endpoints except health check require authentication
- Role-based access enforced (viewer/analyst/admin permissions correct)
- Research run initiation returns run ID, status queryable via polling
- WebSocket research chat sends/receives JSON messages with `type` field
- CSRF protection via double-submit cookie pattern
- Rate limiting per user and per endpoint
- OpenAPI spec generated and accessible at `/docs`
- No financial data returned as float in any response

**Tests:**
- Auth: unauthenticated request → 401; wrong role → 403; valid token → 200
- CRUD: create/read/update/delete company → correct responses
- Pagination: large dataset → correct cursor-based pages
- Screening: complex filter → correct results (verified against direct DB query)
- Research run: initiate → poll status → retrieve results
- WebSocket: connect → send message → receive response with citations
- Error format: invalid input → consistent error JSON
- Rate limiting: exceed limit → 429 with Retry-After header
- RBAC: viewer cannot initiate research; analyst can; admin can manage users

**Status:** NOT STARTED

---

## Phase 9 — Frontend Dashboard

**Goal:** A web dashboard for research, screening, monitoring, and interactive AI chat.

**Dependencies:** Phase 8 (API layer).

**Deliverables:**
- Next.js + TypeScript strict + Tailwind CSS project
- Authentication UI (OAuth flow)
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

**Acceptance Criteria:**
- TypeScript strict mode, zero type errors
- All pages render correctly at mobile (375px) and desktop (1440px) widths
- Authentication flow works end-to-end (login → dashboard → logout)
- Screener: filter → results update → save screen → reload screen
- Company detail: all sections render with real data from API
- Scorecard: every score clickable → shows sub-scores → shows evidence
- Research report: every statement shows its classification label (FACT, AI_INFERENCE, etc.)
- Chat: send question → receive answer with citation links → click citation → see source
- Charts: render with valid data, show empty state for missing data
- No hardcoded API URLs (all from environment/config)

**Tests:**
- Component unit tests (Vitest): each component renders with mock data
- Screener logic: AND/OR filter combinations produce correct UI state
- Responsive: Playwright screenshots at mobile and desktop widths
- E2E: login → search company → view research → drill into scores
- E2E: login → open screener → set filters → view results → save screen
- E2E: login → chat → ask question → receive cited answer
- Accessibility: key pages pass axe-core checks

**Status:** NOT STARTED

---

## Phase 10 — Integration & Deployment

**Goal:** Production-ready deployment with observability, end-to-end validation, and documentation.

**Dependencies:** All previous phases.

**Deliverables:**
- Docker Compose with all 7 services (frontend, backend, worker, beat, db, redis, minio)
- Multi-stage Dockerfiles (backend, frontend)
- Database seed data (10-20 representative Indian companies)
- OpenTelemetry integration (traces, metrics, structured logs)
- Prometheus/Grafana dashboards (5 dashboards: system health, research ops, LLM usage, data pipeline, user activity)
- Alerting (8 alerts: service down, error rate, research failures, LLM errors, cost spike, data staleness, disk usage, quality gate degradation)
- End-to-end tests (Playwright: full research workflow)
- Security review
- Performance baseline
- Documentation finalization
- Production deployment guide

**Acceptance Criteria:**
- `docker-compose up` starts all services, all health checks pass
- Seed data loads: 10-20 companies with financial data visible in UI
- Full research workflow: initiate research → agents run → quality gates → report generated
- OpenTelemetry traces: request → backend → agent → LLM call fully traced
- Prometheus metrics: all 9 metric types from deployment architecture collected
- Grafana dashboards: all 5 render with data
- Alerting: test alerts fire for simulated conditions
- E2E: Playwright runs full user workflows without failure
- No known critical or high severity security issues
- Backend response time: < 200ms for non-research endpoints (p95)
- Research run: completes in < 5 minutes for single company
- All documentation current and accurate

**Tests:**
- Docker Compose: all services start and pass health checks
- Seed data: company list endpoint returns seeded companies
- E2E research: full workflow from UI initiation to report viewing
- Trace completeness: end-to-end trace spans present
- Alert test: simulated failures trigger correct alerts
- Performance: load test confirms p95 response times meet targets
- Security: dependency scan clean, no known vulnerabilities

**Status:** NOT STARTED

---

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

---

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
| ADR-007: Failure Modes | `architecture/adr/007-failure-modes-and-resilience.md` |
| ADR-008: LLM Cost Controls | `architecture/adr/008-llm-cost-controls.md` |
| ADR-009: NSE/BSE Data Access | `architecture/adr/009-nse-bse-data-access-strategy.md` |
| Provider Strategy | `docs/api-provider-strategy.md` |
| Research Methodology | `docs/research-methodology.md` |
| Testing Strategy | `docs/testing-strategy.md` |
| Development Workflow | `docs/development-workflow.md` |
| Acceptance Criteria | `tests/acceptance-criteria.md` |
