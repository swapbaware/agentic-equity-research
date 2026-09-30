# Implementation Plan

## Overview

This document describes the implementation roadmap for the Agentic Equity Research Platform — an evidence-driven research system for Indian listed companies (NSE/BSE). Each phase builds on the previous one, ending with a working, tested increment. The platform is NOT a stock-tip generator; it is a systematic research operating system.

## Guiding Principles for Sequencing

1. **Foundation before features:** Infrastructure and abstractions before business logic.
2. **Data before agents:** Reliable financial data pipelines before AI agent development, because agents need real data to operate on.
3. **Backend before frontend:** API contracts before UI, because the frontend is a consumer of backend capabilities.
4. **Abstractions before implementations:** Provider interfaces before concrete integrations, enabling parallel work and easy swapping.
5. **Phase-by-phase with quality gates:** Each phase is complete with tests before moving to the next.
6. **Agent logic before orchestration:** Agent business logic and research execution persistence are established before LangGraph orchestration. Individual agents are independently testable domain modules; the graph wiring is a separate integration layer.

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

**Status:** COMPLETE — Commit `7bc1c18`

**Key Decisions:**
- pip/venv selected over uv/Poetry for dependency management (simplicity)
- Celery vs Temporal still pending (ADR-002)

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

**Status:** PARTIALLY COMPLETE — Commit `307ee32`

28 SQLAlchemy ORM models, 27 enums, 6 junction tables, 34 tables across 7 schemas, Alembic migrations, 156 unit tests + 6 integration tests.

**Deferred:** Value objects (Money, Percentage, FinancialRatio, DateRange, SourceCitation, CAGRResult). Full Pydantic validation layer. Repository layer for all entities (only evidence and screener repositories built).

**Key Decisions:**
- UUID v4 selected (v7 not available in stdlib until Python 3.12+)
- JSONB for flexible nested data (business segments, assumptions, agent logs)

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

**Status:** COMPLETE — Commits `307ee32`, `b1debdd`

11 Protocol interfaces (PriceHistory deferred — see TD-5), ProviderBase with retry/timeout/rate limiting, ProviderError hierarchy, token bucket rate limiter, ProviderFactory with registry, 11 mock providers. Concrete providers: YahooFinanceProvider, AlphaVantageProvider, BSEProvider, NSEProvider (metadata-only). 89 provider tests + 19 substitution tests + 70 data provider tests.

**Key Decisions:**
- NSE data access strategy (ADR-009 — open; NSE restricts automated access)
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

**Status:** PARTIALLY COMPLETE — Commit `307ee32`

Evidence repository (async CRUD), evidence service layer, evidence API endpoints (`/api/v1/evidence/`), FastAPI dependency injection. 24 service tests + 11 API tests.

**Deferred:** Document ingestion pipeline (PDF/HTML → text), S3/MinIO storage, SHA-256 deduplication, embedding generation, pgvector semantic search, citation completeness validator. These require infrastructure (S3, pgvector with embeddings) and will be built before or during agent orchestration.

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

**Status:** PARTIALLY COMPLETE — Commits `a90acaa` (Phase 6b: Analytics Engine), `c6d90b8` (Phase 6c: Screener)

**Phase 6b (COMPLETE):** Deterministic Financial Analytics Engine — CAGR (Revenue, EBITDA, EBIT, PAT, EPS), profitability margins (Gross, EBITDA, EBIT, Net), return ratios (ROE, ROCE, ROIC), leverage ratios (D/E, Net Debt/EBITDA, Interest Coverage, Current Ratio), cash flow metrics (CFO, FCF, CFO/PAT, FCF/PAT, Capex/Revenue), efficiency metrics (Working Capital, Receivable/Inventory/Payable Days, Cash Conversion Cycle), quality metrics (Return on Incremental Capital, Earnings Consistency). All Decimal. 129 unit tests with golden dataset.

**Phase 6c (COMPLETE):** Stock Screener — 20 screening fields, 8 operators, AND/OR/NOT filter groups, SQLAlchemy executor, saved screens, 7 API endpoints, interactive frontend. 88 screener tests.

**Phase 6d (COMPLETE):** Foundation Hardening — mypy strict zero errors, ruff zero errors, documentation synchronized, technical debt register updated.

**Phase 6e.1 (COMPLETE):** Deterministic DCF Valuation Engine — pure functional `dcf_valuation()` under `app/valuation/`, Decimal-only, no DB/HTTP/LLM. WACC calculation (CAPM), year-by-year FCF projection (EBIT-based NOPAT), Gordon Growth and Exit Multiple terminal value, 7×7 sensitivity matrix, CalculationResult audit trail. 69 tests with hand-verified golden dataset. Commit `fe6dee3`.

**Phase 6e.2 (COMPLETE):** Reverse DCF — bisection solver `reverse_dcf()` treating `dcf_valuation()` as black-box oracle. Solves for uniform implied revenue growth rate. Dual convergence criteria (growth tolerance AND price tolerance). ConvergenceStatus enum (CONVERGED, MAX_ITERATIONS, NO_SOLUTION_BELOW, NO_SOLUTION_ABOVE). ReverseDCFResult with embedded full DCF at solution. 37 tests with forward→reverse round-trip verification. Commit `e8a8fbc`.

**Phase 6e.3 (COMPLETE):** Multiple-Based Valuation Engine — 7 deterministic methods (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF) in `app/valuation/multiples.py`. P/E, P/S, P/B, PEG, FCF Yield are equity-based; EV/EBITDA and EV/FCF are enterprise-based with net debt bridge. FCF Yield uses equity FCF (CFO−CapEx) with CashFlowBasis.EQUITY_FCF. EV/FCF uses FCFF (EBIT×(1−t)+D&A−CapEx−ΔNWC) with CashFlowBasis.FCFF, accepting two periods for deterministic ΔNWC derivation. PEG uses growth in percentage points. All Decimal-only, CalculationResult audit trail, frozen Pydantic v2 MultipleValuationResult. 129 tests with golden datasets.

**Phase 6e.4 (COMPLETE):** Historical Valuation Bands — Deterministic, frequency-agnostic engine in `app/valuation/historical_bands.py`. 6 methods (P/E, EV/EBITDA, P/S, P/B, FCF Yield, EV/FCF); computation direction is observed price → ratio (opposite of Phase 6e.3). Point-in-time correctness via financials_available_date (VALID, LOOK_AHEAD_RISK, UNVERIFIED_TIMING). Only VALID observations in primary statistics. Validation order: structural → duplicate → timing → method-specific. Duplicate handling: identical→dedup, contradictory→HistoricalBandError. Nearest-rank percentile bands (index=ceil(P/100×N)−1). Midpoint percentile rank ((below+0.5×equal)/total×100). CurrentValuationPosition with distance_from_median_pct. DataSufficiency heuristics (INSUFFICIENT/MINIMAL/LOW/MODERATE/ADEQUATE). Full determinism: no system clock, calculated_at is caller-supplied passthrough. 108 tests with golden datasets. Commit `f4e9465`.

**Phase 6e.5 (COMPLETE):** Peer Comparison Engine — Deterministic cross-sectional engine in `app/valuation/peer_comparison.py`. Shared pure-function helpers extracted to `app/valuation/_valuation_calc.py` (resolves TD-12). Accepts explicit peer set (never discovers peers); one method per invocation. 6 methods (P/E, EV/EBITDA, P/S, P/B, FCF Yield, EV/FCF); PEG explicitly rejected. Peer-specific data sufficiency thresholds (0→INSUFFICIENT, 1-2→MINIMAL, 3-4→LOW, 5-9→MODERATE, 10+→ADEQUATE). Target-as-peer exclusion by company_id. Duplicate detection by company_id (identical→dedup, contradictory→PeerComparisonError). rank_if_inserted = count(peer_value ≤ target_value) + 1; ties go AFTER equal peers. Target positioning only when target VALID. Mixed currencies allowed (ratios dimensionless). Composition pattern: PeerObservationInput HAS-A HistoricalObservationInput. 7 new frozen Pydantic v2 models. Cross-engine consistency verified (identical inputs produce identical values from both historical_bands and peer_comparison). 89 peer comparison tests + 51 shared helper tests. All 108 Phase 6e.4 tests pass with zero assertion changes. Commit `2e86976`.

**Phase 6e.6 (COMPLETE):** Scenario Engine (Bear/Base/Bull) — Thin orchestration layer in `app/valuation/scenario.py` delegating to existing DCF and multiple-based valuation engines. No formula duplication. Exactly 3 scenarios required (BEAR, BASE, BULL). ScenarioExecutionStatus (COMPLETED/FAILED) for explicit failure modeling. Probability-weighted value only when all 3 complete with weights summing to Decimal("1"). 6 diagnostics: VALUE_ORDER_UNEXPECTED (warning only, not hard validation), IDENTICAL_ASSUMPTIONS, EXTREME_SPREAD, INCOMPLETE_COMPARISON, SCENARIO_EXECUTION_FAILED, MISSING_PROVENANCE. AssumptionProvenance with FindingType reused from app.models.enums. `calculated_at: datetime` is REQUIRED on all valuation APIs (dcf_valuation, all 7 multiples, reverse_dcf, run_scenarios) — no datetime.now() inside any engine, caller must supply. 9 new frozen Pydantic v2 models. ScenarioEngineError hierarchy. `run_scenarios()` entry point raises ScenarioExecutionError if all 3 fail. 106 tests with 2 golden datasets (DCF: bear=94.0153/base=223.3635/bull=357.2581; PE multiples: 12x/18x/25x). Zero regressions (589 valuation tests pass). Implementation commit `b7c86a1`, remediation commit `pending`.

**Phase 6e.7 (COMPLETE):** Financial Forensics / Red Flag Screening Engine — Pure deterministic forensic engine in `app/valuation/forensics.py` (~2100 lines) with domain models in `app/valuation/forensic_models.py`. 22 individual checks across 5 categories (Earnings Quality: 4 checks, Working Capital: 4 checks, Cash Flow Quality: 4 checks, Leverage: 4 checks, Profitability: 6 checks). 8-status model: FLAGGED, PASS, NOT_COMPUTABLE, INVALID_INPUT, NOT_APPLICABLE, INSUFFICIENT_HISTORY, UNVERIFIED_TIMING, LOOK_AHEAD_RISK. Point-in-time validation (VALID/LOOK_AHEAD_RISK/UNVERIFIED_TIMING); UNVERIFIED_TIMING computed but excluded from primary analysis. Beneish M-Score components (DSRI, GMI, SGI, TATA individually computable; AQI NOT_COMPUTABLE due to missing ppe_net; composite NOT_COMPUTABLE). Altman Z-Score components (X1, X3, X4, X5 computable; X2 NOT_COMPUTABLE due to missing retained_earnings; composite NOT_COMPUTABLE; X4 derives total_liabilities as total_assets − total_equity). CompanyType enum (GENERAL/FINANCIAL); FINANCIAL companies: exactly 3 of 22 checks applicable (eq.total_accruals_to_assets, cf.negative_cfo_count, pr.net_margin_decline). Interest coverage: zero interest_expense → NOT_COMPUTABLE, negative → INVALID_INPUT. ThresholdClassification (PUBLISHED_MODEL, ACCOUNTING_IDENTITY, PLATFORM_HEURISTIC). No aggregate/weighted score. Category summaries descriptive only. Language safety: never "fraud detected", "manipulation detected". Reuses safe_divide() from app.analytics._calc, CalculationResult from app.analytics.models, FindingType.CALCULATION from app.models.enums. ForensicPeriodInput wraps PeriodFinancials via composition. 12 frozen Pydantic v2 models. ForensicValidationError for input validation. DEFAULT_CONFIG with all 22 threshold configurations. No DB/ORM/network/LLM/system clock. Decimal-only arithmetic. 118 tests with golden datasets (A-E). Commit `c98c064`.

---

## Phase 7 — Research Run Infrastructure

**Goal:** Establish persistence models, execution tracking, and the agent base protocol for research runs — the foundation all agents and orchestration depend on.

**Dependencies:** Phase 6 (calculation engine), Phase 5 (evidence system), Phase 4 (providers).

**Deliverables:**
- Research execution domain models: ResearchRun, ResearchRunStep, ResearchFinding, ResearchArtifact, ResearchSource, ResearchExecution, AgentExecution, ThesisVersion
- Alembic migrations for research execution tables
- Agent base protocol (input/output schemas, tool interface, timeout contract, token budget contract)
- Typed `ResearchState` (shared state that agents read from and write to)
- Research run lifecycle management (create, start, step, complete, fail)
- Agent execution tracking (start, output, error, token usage, duration)
- Finding persistence (agent findings with evidence references, finding type classification)
- Repository layer for research execution entities

**Acceptance Criteria:**
- All research execution models implemented with correct field types
- All financial columns use `NUMERIC`
- UUID primary keys on all entities
- Migrations reversible (`downgrade()` tested)
- Agent base protocol defines typed input/output contract
- ResearchState is a typed Pydantic model, not arbitrary dict
- Research run lifecycle transitions are validated (no invalid state transitions)
- Agent execution records capture: agent_id, status, token_usage, duration, error
- Finding records capture: finding_type (7-type classification), evidence references, source tier

**Tests:**
- Model validation: valid data accepted, invalid rejected
- Migration up/down cycle
- Research run lifecycle: create → start → step → complete
- Research run lifecycle: create → start → fail
- Agent execution tracking: start → output → token usage recorded
- Finding persistence: finding with evidence reference round-trip
- ResearchState typed access: correct fields, type safety

**Status:** COMPLETE — Commit: `2f6c8a9`

**Phase 7 Implementation Notes:**
- ResearchRunStatus uses VARCHAR(20) + CHECK constraint (not PG native enum)
- 7-state machine: CREATED → QUEUED → RUNNING → {COMPLETED, FAILED, PARTIAL, CANCELLED}
- No INCOMPLETE state; INCOMPLETE mapped to PARTIAL in migration
- AgentExecution tracks reproducibility: model_provider, model_name, model_config, prompt_version, tool_versions
- Temporal integrity enforced: finding.observation_date ≤ run.observation_date, source_publication_date ≤ observation_date
- Finding immutability via supersedes_finding_id chains
- Concurrent run prevention via database query (not Redis locks)
- MAX_AGENT_RETRIES = 3 (per ADR-007)
- Pydantic v2 schema uses `llm_config` field name (ORM column is `model_config`) to avoid Pydantic reserved name conflict
- Existing Claim/ClaimEvidence models preserved untouched
- Deprecated JSONB fields retained (agent_execution_log, data_sources_used, cost_by_agent)
- No LangGraph, Celery/Temporal, Redis locks, REST/WebSocket endpoints
- 138 new tests, 1471 total passing

**Phase 7 Audit Hardening:**
- Service lifecycle methods refactored to delegate to repository update_status()
- ResearchRunSourceRepositoryProtocol added
- Post-INSERT temporal validation: source_publication_date ≤ finding.created_at (§12.2.2)
- Architecture document updated: QUEUED→CANCELLED transition documented
- ResearchRunStep uses TimestampMixin (migration 005 adds updated_at)
- Protocol signatures aligned with concrete implementations
- 151 Phase 7 tests total, 1485 total passing

---

## Phase 8 — Company Research Agent

**Goal:** First research agent — gathers and structures company profile data from providers.

**Dependencies:** Phase 7 (research run infrastructure), Phase 4 (data providers).

**Deliverables:**
- Company Research Agent implementation
- Typed agent input/output schemas
- Tool wiring to MarketData, FinancialData, CorporateFilings providers
- Company profile structuring (business description, segments, key metrics)
- Source attribution on all gathered data
- Agent unit tests with mock providers

**Acceptance Criteria:**
- Agent produces output conforming to its Pydantic output schema
- Every factual claim in output has a source citation
- Agent respects timeout and token budget contracts from Phase 7
- Agent handles provider errors gracefully (marks findings as unavailable, not fabricated)
- Output includes data provenance (source, retrieval timestamp, confidence)
- No LLM-fabricated financial data in output

**Tests:**
- Output schema validation with mock providers
- Provider error handling (timeout, rate limit, not found)
- Source attribution completeness (every FACT has citation)
- Timeout enforcement
- Token budget enforcement
- Reproducibility (same inputs → structurally consistent output)

**Status:** COMPLETE — Phase 8.1 commit `38f7939`, Phase 8.2 commit pending

**Phase 8.1 (Contracts & Schemas) — COMPLETE:**
- `app/agents/contracts.py` — 8 tool I/O contracts, LLM output schemas, TokenBudget, StepDefinition, CompanyResearchRequest/Config, constants (AGENT_TOKEN_BUDGET=30K, MAX_LLM_ATTEMPTS=2)
- `tests/agents/test_contracts.py` — 126 contract validation tests
- Zero database schema changes, zero new dependencies

**Phase 8.2 (Agent Implementation) — COMPLETE:**
- `app/agents/company_research/agent.py` — CompanyResearchAgent orchestrator: 7-step sequential workflow, generic step runners (_run_step_deterministic, _run_step_llm), LLM retry (MAX_LLM_ATTEMPTS=2), TokenBudget enforcement (30K hard/24K warning), concurrent document retrieval, evidence extraction/persistence, finding generation with evidence linking, deterministic validation, gap/contradiction detection
- `app/agents/company_research/tools.py` — 8 tool implementations (validate_company, discover_sources, retrieve_document, get_company_profile, search_company_news, get_financial_summary, persist_evidence, persist_findings) + create_research_document helper
- `app/agents/company_research/prompts.py` — LLM prompt templates with `<retrieved_document>` prompt injection defense
- `app/agents/company_research/exceptions.py` — AgentError hierarchy (CompanyNotFoundError, TokenBudgetExhaustedError, LLMParsingError, StepFailedError)
- `tests/agents/test_company_research_agent.py` — 64 tests across 15 test classes (construction, happy path, step runners, LLM retry, token budget, finding validation, evidence extraction, finding generation, gap/contradiction, error handling, response parsing, prompts, exceptions, golden scenarios, result model)
- Bug fix: `if findings:` guard before persist_findings (PersistFindingsInput min_length=1)
- No LangGraph, no later-phase agents, no investment recommendations
- Agent depends on Protocol interfaces only
- Total backend: 1675 passed, 7 skipped, 1 known failure (TD-6)

**Phase 8.2 Post-Audit Remediation — COMPLETE:**
- ISSUE-01: company_id update via service/repository layer (no direct ORM mutation)
- ISSUE-03: observation_date propagated to all FindingItem constructions
- ISSUE-07: temporal validation (source_publication_date > observation_date) in finding_validation
- ISSUE-08: ResearchRunSource records created during document retrieval
- 14 new regression tests (2 + 3 + 5 + 4)
- Total backend: 1690 passed, 7 skipped, 0 failed

---

## Phase 9 — Industry Research Agent

**Goal:** Analyzes industry structure, competitive dynamics, and sector trends.

**Dependencies:** Phase 7 (research run infrastructure), Phase 4 (providers).

**Deliverables:**
- Industry Research Agent implementation
- Industry classification and peer identification
- Sector-level metrics aggregation
- Industry trend analysis
- Source attribution on all findings

**Acceptance Criteria:**
- Agent produces typed output with industry classification
- Peer set identified with rationale
- Industry metrics sourced from providers, not fabricated
- Source tier recorded on all evidence

**Tests:**
- Output schema validation
- Peer identification logic
- Provider error handling
- Source attribution completeness

**Status:** NOT STARTED

---

## Phase 10 — Competitive Moat Agent

**Goal:** Assesses competitive advantages using the moat framework from `docs/research-methodology.md`.

**Dependencies:** Phase 7 (research run infrastructure), Phase 8 (company data), Phase 9 (industry data).

**Deliverables:**
- Competitive Moat Agent implementation
- Moat strength assessment (NONE/NARROW/WIDE) with evidence
- Moat source identification (brand, switching costs, network effects, cost advantages, intangibles)
- Moat durability analysis
- Conservative defaults (NONE until evidence upgrades)

**Acceptance Criteria:**
- Default moat strength is NONE; evidence required to upgrade
- Every moat claim references source evidence
- Moat assessment includes durability estimate
- Output follows MANAGEMENT_CLAIM vs FACT vs AI_INFERENCE classification

**Tests:**
- Default moat is NONE with no evidence
- Moat upgrade requires evidence
- Output schema validation
- Classification correctness (claims vs facts vs inferences)

**Status:** NOT STARTED

---

## Phase 11 — Management & Governance Agent

**Goal:** Evaluates management quality, governance practices, and related-party transactions.

**Dependencies:** Phase 7 (research run infrastructure), Phase 4 (CorporateFilings, Shareholding providers).

**Deliverables:**
- Management & Governance Agent implementation
- Management track record analysis
- Governance red flag detection (pledge levels, related-party, audit qualifications)
- Shareholding pattern analysis (promoter, institutional, public)
- Management claims separated from facts

**Acceptance Criteria:**
- Management statements labeled as MANAGEMENT_CLAIM, never FACT
- Governance red flags sourced from filings (Tier 1)
- Shareholding data from authoritative sources
- No LLM-fabricated governance data

**Tests:**
- Management claim classification
- Governance flag detection from sample filings
- Shareholding analysis with mock data
- Output schema validation

**Status:** NOT STARTED

---

## Phase 12 — Future Growth & Optionality Agent

**Goal:** Identifies growth drivers, optionality, and expansion potential.

**Dependencies:** Phase 7 (research run infrastructure), Phase 8 (company data), Phase 9 (industry data).

**Deliverables:**
- Future Growth & Optionality Agent implementation
- Growth driver identification with evidence
- Addressable market estimation
- Optionality assessment (new markets, products, adjacencies)
- Growth assumptions explicitly labeled as AI_INFERENCE or ASSUMPTION

**Acceptance Criteria:**
- Growth projections labeled as AI_INFERENCE or ASSUMPTION, never FACT
- Every growth driver references source data
- Market size estimates include methodology and uncertainty ranges

**Tests:**
- Classification correctness (inferences and assumptions labeled)
- Source attribution
- Output schema validation

**Status:** NOT STARTED

---

## Phase 13 — Macro Economics Agent

**Goal:** Analyzes macroeconomic factors relevant to the company and sector.

**Dependencies:** Phase 7 (research run infrastructure), Phase 4 (MacroData provider).

**Deliverables:**
- Macro Economics Agent implementation
- India-specific macro indicators (GDP, inflation, interest rates, INR)
- Sector-specific macro sensitivity analysis
- Regulatory environment assessment
- Source attribution on all macro data

**Acceptance Criteria:**
- Macro data sourced from providers, not fabricated
- India-specific focus (INR, RBI policy, SEBI regulations)
- Sensitivity analysis links macro changes to company impact
- Source tier recorded (Tier 1 for RBI/SEBI data)

**Tests:**
- Output schema validation
- Macro data source attribution
- Provider error handling
- India-specific data correctness

**Status:** NOT STARTED

---

## Phase 14 — Competitor Analysis Agent

**Goal:** Detailed competitor profiling and competitive positioning analysis.

**Dependencies:** Phase 7 (research run infrastructure), Phase 9 (industry data), Phase 6 (financial calculations).

**Deliverables:**
- Competitor Analysis Agent implementation
- Competitor financial comparison using peer comparison engine (Phase 6e.5)
- Market share analysis
- Competitive positioning matrix
- Source attribution on all competitor data

**Acceptance Criteria:**
- Competitor data sourced from providers, not fabricated
- Financial comparisons use the deterministic peer comparison engine
- Competitor claims distinguished from facts

**Tests:**
- Output schema validation
- Integration with peer comparison engine
- Source attribution completeness

**Status:** NOT STARTED

---

## Phase 15 — Risk Assessment / Bull-Bear Agent

**Goal:** Systematic risk identification and bull/bear case construction.

**Dependencies:** Phase 7 (research run infrastructure), Phase 6e.6 (scenario engine), Phase 6e.7 (forensics).

**Deliverables:**
- Risk Assessment Agent implementation
- Risk identification across categories (business, financial, regulatory, market, operational)
- Bull case construction with evidence
- Bear case construction with evidence
- Integration with scenario engine for quantified risk impact
- Integration with forensic engine for financial red flags

**Acceptance Criteria:**
- Every thesis includes a bear case (never omitted)
- Risk factors sourced from evidence, not fabricated
- Bull/bear cases reference specific data points
- Scenario engine provides quantified ranges for each case
- Forensic flags incorporated into risk assessment

**Tests:**
- Bear case always present
- Risk factor source attribution
- Scenario engine integration
- Forensic integration
- Output schema validation

**Status:** NOT STARTED

---

## Phase 16 — Thesis Challenger Agent

**Goal:** Adversarial agent that attempts to disprove the investment thesis.

**Dependencies:** Phase 7 (research run infrastructure), Phases 8-15 (agent outputs to challenge).

**Deliverables:**
- Thesis Challenger Agent implementation
- Counter-evidence gathering
- Thesis stress testing
- Identification of unaddressed risks and assumptions
- Challenge results fed back into quality gates

**Acceptance Criteria:**
- Challenger attempts to disprove accumulated findings
- Counter-evidence sourced, not fabricated
- Unaddressed assumptions flagged
- Challenge results influence final thesis confidence

**Tests:**
- Challenger identifies known weaknesses in test thesis
- Counter-evidence has source attribution
- Challenge output schema validation

**Status:** NOT STARTED

---

## Phase 17 — Evidence Verification Agent

**Goal:** Validates evidence integrity, cross-checks financial figures, and ensures citation completeness.

**Dependencies:** Phase 7 (research run infrastructure), Phase 5 (evidence system).

**Deliverables:**
- Evidence Verification Agent implementation
- Deterministic structural checks (document exists, financial cross-checks)
- Citation completeness validation (every FACT has source)
- Cross-statement consistency checks (balance sheet equation, CFO derivation)
- Evidence tier validation (financial data from Tier 1 sources)

**Acceptance Criteria:**
- FACT without citation → flagged
- Financial cross-checks use deterministic code, not LLM
- Balance sheet equation verified
- Source tier validated for financial data

**Tests:**
- Missing citation detection
- Cross-statement consistency (correct and incorrect)
- Source tier validation
- Deterministic vs LLM check separation

**Status:** NOT STARTED

---

## Phase 18 — Research Synthesis Agent

**Goal:** Synthesizes findings from all agents into a coherent research report with proper classification.

**Dependencies:** Phase 7 (research run infrastructure), Phases 8-17 (all agent outputs).

**Deliverables:**
- Research Synthesis Agent implementation
- Multi-agent output aggregation
- Finding classification enforcement (FACT/CALCULATION/MANAGEMENT_CLAIM/ANALYST_OPINION/AI_INFERENCE/ASSUMPTION/UNCERTAINTY)
- Research report generation with evidence labels
- Company scoring (10 dimensions from research methodology)
- Score defaults: 0 until evidence supports upgrade

**Acceptance Criteria:**
- All 7 finding types correctly classified in output
- Every statement in report labeled with its classification
- Company scores default to 0, evidence required to upgrade
- Report includes all required sections from research methodology
- No mixing or conflation of finding types

**Tests:**
- Finding classification correctness
- Score default behavior (0 without evidence)
- Report section completeness
- Evidence label propagation
- Output schema validation

**Status:** NOT STARTED

---

## Phase 19 — LangGraph Orchestration

**Goal:** Wire all agents into a LangGraph state machine with quality gates, checkpointing, and cost controls.

**Dependencies:** Phase 7 (research run infrastructure), Phases 8-18 (all agents).

**Deliverables:**
- LangGraph workflow graph with typed `ResearchState`
- Agent execution ordering (parallel where independent, sequential where dependent)
- Quality gate engine (12 gates from `docs/research-methodology.md`)
- Per-agent timeout enforcement (60s-180s per agent)
- Per-agent token budget enforcement (~325K total per run)
- Total run timeout (15 minutes)
- LangGraph checkpointing for resume on failure
- Redis advisory lock for concurrent run prevention
- Max 2 iterations (1 initial + 1 retry) for quality gate loop
- Failed agent handling (mark FAILED, continue with independent agents)

**Acceptance Criteria:**
- LangGraph graph compiles and executes with mock LLM
- All agents produce outputs conforming to their schemas
- Parallel execution: agents without data dependencies run concurrently
- Quality gate loop: max 2 iterations, then INCOMPLETE
- Per-agent timeout: agent killed after timeout, workflow continues
- Per-agent token budget: agent stopped if budget exceeded
- Total run timeout: 15 minutes max
- Redis lock: concurrent research on same company blocked
- LangGraph checkpointing: interrupted run can resume from last checkpoint
- Failed agent: marked FAILED, workflow continues
- Quality gate failure: output marked RESEARCH INCOMPLETE, not fabricated
- Moat default: NONE. Score default: 0. Evidence required to upgrade.

**Tests:**
- Graph execution: end-to-end with mock LLM, all agents complete
- Agent output schema: each agent's output validates against Pydantic model
- Parallel execution: verify concurrent agents via timing assertions
- Quality gate pass: known-good inputs → all 12 gates pass
- Quality gate fail: incomplete data → specific gates fail → INCOMPLETE
- Retry limit: quality gate fails twice → no third attempt → INCOMPLETE
- Timeout: slow mock agent → killed after timeout → workflow continues
- Token budget: verbose mock agent → stopped at budget → workflow continues
- Concurrent run lock: two research runs on same company → second blocked
- Checkpoint resume: interrupted run → resume → completes from checkpoint
- Reproducibility: same inputs twice → structurally consistent outputs

**Status:** NOT STARTED

**Key Decisions:**
- Resolve LLMProvider interface alignment with LangGraph native invocation (K-4)

---

## Phase 20 — Research UI & API Layer

**Goal:** Web interface and API layer for viewing research reports, company analysis, and financial data.

**Dependencies:** Phase 19 (orchestration), Phase 6 (calculation engine).

**Deliverables:**
- RESTful API layer for research data (authentication, authorization, pagination)
- Authentication (OAuth 2.0 / JWT) and authorization (RBAC: viewer, analyst, admin)
- Company detail page (overview, financials, moat, valuation, thesis, risks, catalysts)
- Research report viewer with evidence labels (FACT/CALCULATION/MANAGEMENT_CLAIM/etc.)
- Company scorecard (10-dimension, evidence drill-down)
- Interactive financial charts
- Stock screener integration (existing Phase 6c)
- Company search
- OpenAPI documentation
- Frontend tests (Vitest + Playwright)

**Acceptance Criteria:**
- All API endpoints follow URL-prefix versioning (`/api/v1/...`)
- Error responses use consistent JSON format
- Research report: every statement shows classification label
- Scorecard: every score clickable → shows sub-scores → shows evidence
- No financial data returned as float in any API response
- Responsive design (mobile + desktop)
- TypeScript strict mode, zero type errors

**Tests:**
- API endpoint tests (auth, CRUD, pagination, error format)
- Component tests (company detail, report viewer, scorecard)
- E2E: search company → view research → drill into scores
- Responsive: screenshots at mobile and desktop widths
- RBAC: viewer cannot initiate research; analyst can; admin can manage users

**Status:** NOT STARTED

---

## Phase 21 — Research Copilot

**Goal:** Interactive AI chat for asking questions about company research with citation support.

**Dependencies:** Phase 20 (research UI), Phase 5 (evidence system), Phase 19 (orchestration).

**Deliverables:**
- Research chat endpoint (WebSocket)
- Context-aware question answering per company
- Citation linking (answer → evidence → source document)
- Conversation history
- Prompt injection defense for user input

**Acceptance Criteria:**
- Chat: send question → receive answer with citation links → click citation → see source
- Answers grounded in research data, not hallucinated
- User input validated and sanitized
- Prompt injection defense active

**Tests:**
- WebSocket: connect → send message → receive response with citations
- Citation link validity
- Prompt injection: adversarial input → defense engaged
- Conversation context maintained

**Status:** NOT STARTED

---

## Phase 22 — Monitoring & Watchlist

**Goal:** Ongoing monitoring of researched companies with alerts for material changes.

**Dependencies:** Phase 20 (research UI), Phase 4 (data providers).

**Deliverables:**
- Watchlist/portfolio management
- Alert configuration (price, financial, governance triggers)
- Background monitoring jobs
- Alert notification delivery
- Thesis invalidation detection

**Acceptance Criteria:**
- Watchlist: add/remove companies, configure alerts
- Alerts fire on configured triggers
- Background jobs run without blocking research runs
- Thesis invalidation: material change → alert → re-research prompt

**Tests:**
- Watchlist CRUD
- Alert trigger detection
- Background job execution
- Alert delivery

**Status:** NOT STARTED

---

## Phase 23 — Evaluation & Quality

**Goal:** Systematic evaluation of research quality, agent accuracy, and platform reliability.

**Dependencies:** Phase 19 (orchestration), Phase 6 (golden datasets).

**Deliverables:**
- Research quality metrics framework
- Agent accuracy evaluation (against golden datasets)
- End-to-end research quality scoring
- Citation accuracy measurement
- Regression detection for research outputs

**Acceptance Criteria:**
- Quality metrics defined and measurable
- Golden dataset tests: research outputs match hand-verified baselines
- Citation accuracy: verified percentage of citations link to correct sources
- Regression: new agent versions tested against baseline quality

**Tests:**
- Quality metric calculation
- Golden dataset comparison
- Citation accuracy measurement
- Regression detection

**Status:** NOT STARTED

---

## Phase 24 — Security Hardening

**Goal:** Security audit, penetration testing preparation, and compliance verification.

**Dependencies:** Phase 20 (full platform running).

**Deliverables:**
- Authentication hardening (OAuth 2.0 / JWT review)
- Authorization review (RBAC enforcement across all endpoints)
- Prompt injection defense audit
- Dependency vulnerability scanning
- DPDP Act compliance review
- Security documentation

**Acceptance Criteria:**
- No known critical or high severity vulnerabilities
- All endpoints enforce authentication and authorization
- Prompt injection defense tested with adversarial inputs
- Dependencies scanned and patched
- DPDP Act gaps documented with remediation plan

**Tests:**
- Auth: unauthenticated → 401; wrong role → 403
- Prompt injection: adversarial documents → defense holds
- Dependency scan: clean report
- RBAC: comprehensive role-based access tests

**Status:** NOT STARTED

---

## Phase 25 — Production Readiness

**Goal:** Production deployment with observability, seed data, and operational documentation.

**Dependencies:** All previous phases.

**Deliverables:**
- Docker Compose with all services (frontend, backend, worker, beat, db, redis, minio)
- Multi-stage Dockerfiles
- Database seed data (10-20 representative Indian companies)
- OpenTelemetry integration (traces, metrics, structured logs)
- Prometheus/Grafana dashboards
- Alerting (service health, error rate, research failures, LLM costs)
- End-to-end Playwright tests
- Performance baseline
- Production deployment guide
- Documentation finalization

**Acceptance Criteria:**
- `docker-compose up` starts all services, all health checks pass
- Seed data loads: companies visible in UI
- Full research workflow: initiate → agents → quality gates → report
- Traces: request → backend → agent → LLM call fully traced
- Backend response time: < 200ms for non-research endpoints (p95)
- Research run: completes in < 5 minutes for single company
- All documentation current and accurate

**Tests:**
- Docker Compose: all services start and pass health checks
- Seed data: company list endpoint returns seeded companies
- E2E: full workflow from UI to report viewing
- Trace completeness
- Performance: load test confirms p95 targets
- Security: dependency scan clean

**Status:** NOT STARTED

---

## MVP Scope (Phases 2–21)

The minimum viable product includes:

1. Indian stock universe (NSE/BSE) — Phase 4
2. Financial data ingestion from at least one provider — Phase 4
3. Company search — Phase 20
4. Stock screener with financial filters — Phase 6c (complete)
5. Financial dashboard per company — Phase 20
6. Basic valuation (multiples + DCF) — Phase 6e (complete)
7. Company research (all research agents for single company) — Phases 8-18
8. Moat analysis with evidence — Phase 10
9. Industry analysis — Phase 9
10. Research report with source citations and evidence labels — Phases 18, 20
11. AI research chat — Phase 21
12. Quality gates and LangGraph orchestration — Phase 19

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
