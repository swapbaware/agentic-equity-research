# Progress Tracker

**Last Updated:** 2026-09-28

---

## Completed Phases

### Phase 0: Repository Setup — COMPLETE

- [x] Initialize git repository
- [x] Create project documentation (README, CLAUDE.md, progress.md, implementation-plan.md)
- [x] Create architecture directory structure (7 directories with .gitkeep)
- [x] Create .gitignore and .env.example
- [x] Create .gitattributes (line ending normalization)
- [x] Initial commit (`d5a975e`)
- [x] Push to GitHub origin (`origin/main`)

### Phase 1: Architecture & Planning — COMPLETE

- [x] Solution architecture document
- [x] Domain model (30+ entities, relationships, 7 invariants)
- [x] Agent architecture (17 agents, LangGraph orchestration, memory layers)
- [x] Data architecture (PostgreSQL/pgvector/Redis/S3, ingestion pipeline)
- [x] Security architecture (auth, agent sandboxing, prompt injection, DPDP Act)
- [x] Deployment architecture (Docker, CI/CD, observability, alerting)
- [x] Architecture Decision Records (ADR-001 through ADR-006)
- [x] API & provider strategy (12 provider interfaces)
- [x] Research methodology (15 dimensions, 12 quality gates, scoring)
- [x] Testing strategy (8 test categories, pyramid, coverage targets)
- [x] Architecture commit (`387d53a`)
- [x] 20-point architecture review
- [x] ADR-007: Failure modes and resilience
- [x] ADR-008: LLM cost controls
- [x] ADR-009: NSE/BSE data access strategy
- [x] Architecture review commit (`41f3c77`)

---

### Phase 1.5: Development Control Plane — COMPLETE

- [x] CLAUDE.md expanded to 13-section engineering constitution
- [x] progress.md restructured with 9 tracking categories
- [x] implementation-plan.md updated with acceptance criteria per phase
- [x] tests/acceptance-criteria.md created
- [x] docs/development-workflow.md created
- [x] Commit (`dcd1f33`)

### Phase 2: Core Backend Foundation — COMPLETE

- [x] Python project setup (pyproject.toml, pip/venv)
- [x] FastAPI application factory with lifespan management
- [x] pydantic-settings configuration (auto async driver conversion)
- [x] Structured JSON logging with request ID propagation (contextvars)
- [x] SQLAlchemy 2.0 async engine with connection pooling
- [x] Redis async client
- [x] Alembic async migrations (initial: pgvector + 10 schemas)
- [x] Health endpoint (database + Redis checks)
- [x] Readiness endpoint (migration version check)
- [x] RequestIdMiddleware with exception handling
- [x] Consistent error response format and exception hierarchy
- [x] pytest setup — 19 tests, all passing
- [x] Next.js 14 frontend with TypeScript strict, Tailwind CSS
- [x] Frontend health page
- [x] Vitest setup — 5 tests, all passing
- [x] ESLint with @typescript-eslint plugin
- [x] ruff linting (check + format) — passing
- [x] mypy strict type checking — passing (mypy 1.13.0 on Windows)
- [x] TypeScript strict type checking (tsc --noEmit) — passing
- [x] Docker Compose (PostgreSQL 16/pgvector, Redis 7, backend, frontend)
- [x] Multi-stage Dockerfiles (backend + frontend)
- [x] GitHub Actions CI (7 jobs: backend-lint, backend-typecheck, backend-test, frontend-lint, frontend-typecheck, frontend-test, docker-build)
- [x] .env.example updated

### Phase 3: Domain Models & Database Schema — COMPLETE

- [x] SQLAlchemy 2.0 declarative base with naming convention (base.py)
- [x] 27 domain enumerations covering all 7 schemas (enums.py)
- [x] Company schema: Exchange, Classification (Sector/Industry), Company, Security
- [x] Financial schema: FinancialStatement (with CHECK constraint), FinancialMetric, QuarterlyResult
- [x] Governance schema: Shareholding, PromoterPledge, CorporateAction, CorporateAnnouncement
- [x] Research schema: ResearchDocument, Evidence, ManagementStatement, ResearchRun, ResearchFinding
- [x] Analysis schema: MoatAssessment, GrowthOpportunity, Competitor, IndustryData, MacroIndicator
- [x] Valuation schema: ValuationModel, Scenario
- [x] Thesis schema: InvestmentThesis, ThesisVersion, Risk, Catalyst, CompanyScore
- [x] 6 junction tables for many-to-many evidence relationships
- [x] 34 total tables across 7 PostgreSQL schemas
- [x] All financial columns use `Numeric` (never Float)
- [x] UUID primary keys on all 28 model classes
- [x] TimestampMixin (created_at, updated_at) with server_default
- [x] Partial unique indexes for nullable columns (nse_symbol, bse_code)
- [x] CHECK constraint: quarter consistency on FinancialStatement
- [x] Conservative defaults: MoatStrength defaults to NONE, score defaults to 0
- [x] Alembic migration 002: explicit DDL for all 34 tables + 27 enum types
- [x] 156 unit tests (schema structure validation without database)
- [x] 6 integration tests (database round-trip, marked `@pytest.mark.integration`)
- [x] ruff lint passing (TCH003 suppressed for model files — SQLAlchemy needs runtime types)
- [x] All enums use `StrEnum` (Python 3.11+)

### Phase 4: Evidence Subsystem — COMPLETE

- [x] Evidence repository (async SQLAlchemy CRUD)
- [x] Evidence service layer (business logic)
- [x] Evidence API endpoints (`/api/v1/evidence/`)
- [x] FastAPI dependency injection for services
- [x] Alembic migration 003: evidence subsystem tables
- [x] 24 service tests, 11 API tests — all passing

### Phase 5: Provider Framework — COMPLETE

- [x] 11 Protocol interfaces (MarketData, FinancialData, CorporateFilings, Shareholding, CorporateActions, News, Search, MacroData, Transcript, LLM, Embedding)
- [x] ProviderBase with retry, timeout, rate limiting, structured logging
- [x] ProviderError hierarchy (Auth, RateLimit, NotFound, Timeout, Unavailable, Data)
- [x] Token bucket rate limiter (InMemoryRateLimiter + NullRateLimiter)
- [x] ProviderConfig (dataclass) + ProviderSettings (env-driven via pydantic-settings)
- [x] ProviderFactory with registry pattern
- [x] 11 mock provider implementations (deterministic Indian market data)
- [x] 89 provider tests (63 contract + 18 base + 8 rate limiter) — all passing

### Phase 6: Initial Indian Data Providers — COMPLETE

- [x] DataProvenance model (source, source_type, retrieved_at, data_quality, confidence)
- [x] DataConflict model for cross-source conflict detection
- [x] Indian stock symbol mapper (NSE/BSE/ISIN resolution for 6 dev companies)
- [x] YahooFinanceProvider (MarketData + FinancialData + CorporateActions via yfinance)
  - Thread pool for sync yfinance calls, Decimal conversion at boundary
  - NSE (.NS) and BSE (.BO) symbol mapping
  - Provenance attached to all returned records
- [x] AlphaVantageProvider (MarketData + FinancialData via httpx async)
  - API key from env (PROVIDER_ALPHA_VANTAGE_API_KEY)
  - HTTP error handling (401/429/5xx mapped to provider errors)
  - Provenance attached to all returned records
- [x] BSEProvider (CorporateFilings via BSE public API)
  - Conservative rate limiting (2 req/s)
  - Tier 1 (AUTHORITATIVE) provenance
  - Filing metadata with document URLs
- [x] NSEProvider (metadata-only placeholder — NSE restricts automated access)
- [x] DataReconciler (cross-source conflict detection with configurable threshold)
- [x] Optional provenance field added to Quote, PriceBar, FinancialStatement, Filing, CorporateActionRecord
- [x] Factory updated: yahoo, alpha_vantage, bse, nse registered across interfaces
- [x] Factory lazy imports (vendor SDKs loaded only when provider selected)
- [x] `ProviderFactory.register()` for runtime provider registration without modifying factory
- [x] 70 provider tests (19 Yahoo Finance, 13 Alpha Vantage, 13 BSE/NSE, 15 symbol map, 10 reconciliation)
- [x] 19 provider substitution tests (MockProductionProvider, config-only swap, lazy import regression)
- [x] Development dataset: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, BHARTIARTL
- [x] No API keys in source code, no live API calls in tests
- [x] Provider architecture review: 13/13 requirements verified
- [x] Total: 394 tests passing, ruff clean, mypy strict clean on providers

### Phase 6b: Financial Analytics Engine — COMPLETE

- [x] Deterministic Financial Analytics Engine (`app/analytics/`)
- [x] CAGR calculations: Revenue, EBITDA, EBIT, PAT, EPS (via Decimal ln/exp)
- [x] Profitability margins: Gross, EBITDA, EBIT, Net
- [x] Return ratios: ROE, ROCE, ROIC (with average balance sheet values)
- [x] Leverage ratios: Debt/Equity, Net Debt/EBITDA, Interest Coverage, Current Ratio
- [x] Cash flow metrics: CFO, FCF, CFO/PAT, FCF/PAT, Capex/Revenue
- [x] Efficiency metrics: Working Capital, Receivable Days, Inventory Days, Payable Days, Cash Conversion Cycle
- [x] Quality metrics: Return on Incremental Capital, Earnings Consistency (composite score)
- [x] All calculations use `decimal.Decimal` — never float
- [x] Every result retains: input values, period, formula, calculation version, output
- [x] Engine orchestrator (`compute_all`) produces 28 metrics from multi-period data
- [x] 129 unit tests with hand-verified expected values
- [x] Golden dataset: 3-year synthetic company with exact Decimal assertions
- [x] ruff clean, mypy strict clean
- [x] Total: 523 tests passing

### Phase 6c: Stock Screener — COMPLETE

- [x] Screener schemas: 20 screening fields, 8 operators, field/operator validation (`app/screener/schemas.py`)
- [x] Screening criteria: Sector, Industry, Market Cap, Revenue Growth, EPS Growth, ROE, ROCE, ROIC, D/E, Net Debt/EBITDA, FCF Yield, P/E, EV/EBITDA, PEG, Dividend Yield, Promoter Holding, Promoter Pledge, Institutional Ownership, EBITDA Margin, FCF Conversion
- [x] Logical operators: AND, OR, NOT, >, >=, <, <=, =, BETWEEN, IN, NOT IN
- [x] Filter groups: multiple criteria per group, multiple groups per screen (ANDed)
- [x] SQLAlchemy executor: criteria → deterministic SQL WHERE conditions (`app/screener/executor.py`)
- [x] Screen repository: CRUD for saved screens, screening query execution (`app/screener/repository.py`)
- [x] Screen service: orchestration layer with ad-hoc and saved screen execution (`app/screener/service.py`)
- [x] API endpoints: GET /companies, POST /screens, GET /screens, GET /screens/{id}, POST /screens/{id}/execute, POST /screens/execute, DELETE /screens/{id} (`app/screener/router.py`)
- [x] Database models: SavedScreen (JSONB criteria), CompanyScreeningData (denormalized 20-column screening table) (`app/models/screening.py`)
- [x] All financial columns use NUMERIC — never FLOAT
- [x] Frontend screener page: interactive filter builder with field/operator/value dropdowns, save/load screens, results table (`frontend/src/app/screener/page.tsx`)
- [x] TypeScript types mirroring backend schemas (`frontend/src/types/screener.ts`)
- [x] 88 screener tests (40 schema validation, 35 executor SQL generation, 13 service logic)
- [x] ruff clean, mypy strict clean on screener module, tsc strict clean, eslint clean
- [x] Total: 617 tests passing

---

### Phase 6d: Foundation Hardening — COMPLETE

- [x] Fix 21 mypy `type-arg` errors: bare `Mapped[dict]` → `Mapped[dict[str, object]]` across 6 model files
- [x] Fix 1 mypy `import-untyped` error: yfinance import annotation
- [x] Fix 14 ruff errors in Alembic files (import sorting, Union→`|`, Sequence import, line length)
- [x] Verify test baseline: 617 backend tests passing, 5 frontend tests passing, 1 pre-existing failure documented
- [x] Synchronize progress.md and implementation-plan.md with actual repository state
- [x] Update technical debt register (TD-1 through TD-11)
- [x] Commit CLAUDE.md Project Progress Tracking section
- [x] mypy strict: zero errors (65 source files)
- [x] ruff: zero errors
- [x] tsc strict: zero errors

### Phase 6e.1: Deterministic DCF Valuation Engine — COMPLETE

- [x] `app/valuation/models.py` — Pydantic v2 frozen models: WACCComponents, DCFAssumptions (with model validators), ProjectedYear, TerminalValueResult, SensitivityCell, DCFResult
- [x] `app/valuation/wacc.py` — WACC calculation: Ke = Rf + β × ERP, Kd = PreTax × (1-tax), WACC = equity_weight × Ke + debt_weight × Kd
- [x] `app/valuation/projector.py` — Year-by-year FCF projection: Revenue → EBIT → NOPAT → D&A → CapEx → ΔNWC → FCF, with discount factors and PV(FCF)
- [x] `app/valuation/terminal.py` — Terminal value: Gordon Growth (FCF×(1+g)/(WACC-g)) and Exit Multiple (EBITDA×multiple)
- [x] `app/valuation/sensitivity.py` — 7×7 WACC × terminal-growth sensitivity grid (±3 steps of 1pp)
- [x] `app/valuation/dcf.py` — 9-step orchestrator: resolve WACC → validate → project → terminal → EV → equity → per-share → upside/downside → sensitivity
- [x] `app/valuation/__init__.py` — Public API exporting dcf_valuation and all model types
- [x] `tests/test_valuation_models.py` — 15 model validation tests (construction, per-year lists, WACC components, frozen immutability, validation errors)
- [x] `tests/test_valuation_wacc.py` — 5 WACC tests (hand-verified: basic, all-equity, high-beta, decimal enforcement, audit trail)
- [x] `tests/test_valuation_dcf.py` — 49 DCF tests (golden dataset 5-year hand-verified, WACC components integration, exit multiple, single-year, per-year assumptions, edge cases, sensitivity matrix, audit trail, reproducibility, no-float enforcement)
- [x] All 69 DCF valuation tests passing
- [x] Full backend: 686 passed, 1 known failure (TD-6), 7 skipped
- [x] mypy strict: zero errors on valuation module (7 source files)
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] Frontend: 5 tests passing

### Phase 6e.2: Reverse DCF Valuation — COMPLETE

- [x] `app/valuation/models.py` — Added ConvergenceStatus enum (CONVERGED, MAX_ITERATIONS, NO_SOLUTION_BELOW, NO_SOLUTION_ABOVE) and ReverseDCFResult model
- [x] `app/valuation/reverse_dcf.py` — Bisection solver treating dcf_valuation() as black-box oracle. Solves for implied uniform revenue growth rate. Dual convergence criteria (growth tolerance AND price tolerance). Structured no-solution handling.
- [x] `app/valuation/__init__.py` — Exports: reverse_dcf, ReverseDCFResult, ConvergenceStatus
- [x] `tests/test_valuation_reverse_dcf.py` — 37 tests across 12 test classes: golden round-trip (10%/0%/5%), convergence, max_iterations, no-solution below/above, boundary targets, custom bounds, exit multiple, input validation, Decimal enforcement, reproducibility, audit trail, DCF result consistency, purity
- [x] All 37 reverse DCF tests passing
- [x] Full backend: 723 passed, 1 known failure (TD-6), 7 skipped
- [x] mypy strict: zero errors on valuation module (8 source files)
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] Frontend: 5 tests passing

### Phase 6e.3: Multiple-Based Valuation Engine — COMPLETE

- [x] `app/valuation/models.py` — Added ValuationMethodType enum (7 methods), CashFlowBasis enum (EQUITY_FCF, FCFF), MultipleValuationResult model (frozen Pydantic v2)
- [x] `app/valuation/multiples.py` — Seven deterministic valuation functions: pe_valuation, ev_ebitda_valuation, ps_valuation, pb_valuation, peg_valuation, fcf_yield_valuation, ev_fcf_valuation. Shared helpers for net debt derivation, upside/downside, EV-to-per-share pipeline, equity-to-per-share. MultipleValuationError for invalid inputs.
- [x] `app/valuation/__init__.py` — Exports all seven functions + CashFlowBasis, ValuationMethodType, MultipleValuationResult, MultipleValuationError
- [x] P/E: equity-based, EPS × Target P/E
- [x] EV/EBITDA: enterprise-based, EBITDA × multiple → EV → equity → per share
- [x] P/S: equity-based, Revenue × Target P/S
- [x] P/B: equity-based, Total Equity × Target P/B
- [x] PEG: equity-based, growth in percentage points (15 = 15%), Implied P/E = PEG × Growth%
- [x] FCF Yield: equity-based, Equity FCF = CFO − CapEx, CashFlowBasis.EQUITY_FCF
- [x] EV/FCF: enterprise-based, FCFF = EBIT×(1−t) + D&A − CapEx − ΔNWC, accepts two periods, CashFlowBasis.FCFF
- [x] ΔNWC derived deterministically from current and prior PeriodFinancials
- [x] Net debt/net cash handled correctly for all enterprise-value methods
- [x] `tests/test_valuation_multiples.py` — 129 tests across 22 test classes: golden datasets (Company A zero ΔNWC, Company B positive ΔNWC), all seven methods, validation (zero/negative/missing inputs), audit trail, cross-method cash-flow-basis consistency, Decimal enforcement, reproducibility, upside/downside
- [x] All 129 multiple valuation tests passing
- [x] Full backend: 852 passed, 1 known failure (TD-6), 7 skipped
- [x] mypy strict: zero errors on valuation module (9 source files)
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] Frontend: 5 tests passing

---

## Current Phase

**Next Phase:** Phase 6e.4 — Historical Valuation Bands

---

## Completed Features

- Health check endpoint (`GET /health`) — database and Redis connectivity
- Readiness endpoint (`GET /health/ready`) — migration version validation
- Frontend health page (`/health`) — static system status display
- Structured JSON logging with request ID correlation
- Request ID middleware with unhandled exception safety net
- Complete domain model: 28 ORM models, 6 junction tables, 27 enums across 7 schemas
- Evidence subsystem: full CRUD API for evidence, claims, citations
- Provider framework: 11 Protocol interfaces, factory, rate limiter, error hierarchy
- Indian data providers: Yahoo Finance, Alpha Vantage, BSE, NSE (metadata)
- Data provenance tracking on all provider-sourced records
- Cross-source data reconciliation with conflict detection
- Deterministic Financial Analytics Engine: 28 metrics (CAGR, margins, returns, leverage, cash flow, efficiency, quality)
- Stock Screener: 20 criteria, 8 operators, AND/OR/NOT groups, saved screens, 7 API endpoints, interactive frontend
- Deterministic DCF Valuation Engine: pure functional, Decimal-only, WACC/FCF/terminal value/sensitivity, CalculationResult audit trail, 69 tests with golden dataset
- Reverse DCF: bisection solver for implied revenue growth rate, treats forward DCF as black-box oracle, dual convergence criteria, structured no-solution handling, 37 tests with round-trip verification
- Multiple-Based Valuation Engine: 7 methods (P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF), FCFF-based EV/FCF with ΔNWC derivation, CashFlowBasis metadata, 129 tests with golden datasets

---

## Failing Tests

- `test_health.py::TestReadinessEndpoint::test_ready_returns_200` — pre-existing, requires running PostgreSQL with migrations applied. This is an integration test that validates the readiness endpoint checks Alembic migration state against a live database. Cannot pass without PostgreSQL. 723 other backend tests pass. 5 frontend tests pass. 7 tests skipped (6 integration tests requiring PostgreSQL, 1 provider test requiring API key).

---

## Known Issues

| ID | Issue | Severity | Phase to Address |
|----|-------|----------|-----------------|
| K-1 | NSE does not offer a free, open API — primary data source at risk | Critical | Phase 4 |
| K-2 | Background task processor not decided (Celery vs Temporal) | Medium | Phase 2 |
| K-3 | Embedding dimension hardcoded to 1536 — should be configurable | Low | Phase 5 |
| K-4 | LLMProvider interface may not align with LangGraph native invocation | Medium | Phase 7 |
| K-5 | DPDP Act 2023 compliance requires legal review before commercialization | Medium | Pre-launch |
| K-6 | Evidence Verification Agent has circular LLM dependency — mitigated by partial deterministic checks | Low | Phase 7 |

---

## Architectural Decisions

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| 001 | LangGraph for agent orchestration | Accepted | Chosen over custom/Temporal/CrewAI |
| 002 | Background task processor | Pending | Celery vs Temporal — evaluate in Phase 2 |
| 003 | Decimal for financial calculations | Accepted | `decimal.Decimal` mandate, never float |
| 004 | Evidence citation system | Accepted | Mandatory citation with 7-type classification |
| 005 | Provider abstraction pattern | Accepted | Protocol-based interfaces, factory injection |
| 006 | India market focus | Accepted | NSE/BSE, INR, Ind AS, April-March FY |
| 007 | Failure modes and resilience | Accepted | Max 2 loop iterations, 15-min timeout, Redis lock |
| 008 | LLM cost controls | Accepted | Per-agent budgets, per-run tracking, model tiers |
| 009 | NSE/BSE data access strategy | Open | SEBI XBRL recommended; commercial vendor as upgrade |

### Review Decisions (from 20-point architecture review)

1. Maximum 2 quality gate loop iterations (ADR-007)
2. 15-minute total research run timeout with per-agent timeouts (ADR-007)
3. Redis advisory lock for concurrent research run prevention (ADR-007)
4. Per-agent token budgets and per-run cost tracking (ADR-008)
5. Model tier selection: cheap for extraction, capable for analysis (ADR-008)
6. SEC EDGAR removed from scope (ADR-006)
7. SEBI XBRL as primary free financial data source (ADR-009)
8. Partitioning deferred until data volume warrants it
9. Cursor-based pagination for API endpoints
10. URL-prefix API versioning (/api/v1/)

---

## Pending Integrations

| Integration | Provider Interface | Status | Blocker |
|------------|-------------------|--------|---------|
| BSE API | CorporateFilingsProvider | Implemented | Phase 6 — BSEProvider with public API |
| SEBI XBRL | CorporateFilingsProvider, FinancialDataProvider | Not started | Phase 7+ |
| Yahoo Finance India | MarketData, FinancialData, CorporateActions | Implemented | Phase 6 — YahooFinanceProvider |
| Alpha Vantage | MarketData, FinancialData | Implemented | Phase 6 — AlphaVantageProvider (API key required) |
| NSE | CorporateFilingsProvider | Placeholder | Phase 6 — metadata-only, NSE restricts automated access |
| Anthropic Claude | LLMProvider | Not started | Phase 7 |
| OpenAI | LLMProvider, EmbeddingProvider | Not started | Phase 5/7 |
| MinIO / S3 | Object Storage | Not started | Phase 5 |
| PostgreSQL + pgvector | Data layer | Configured | Connection pooling, async engine, Alembic migrations |
| Redis | Cache, rate limiting, locks | Configured | Async client, health check wired |

---

## Technical Debt

| ID | Description | Incurred | Plan to Address |
|----|-------------|----------|-----------------|
| TD-1 | mypy pinned to 1.13.0 — mypy 2.x blocked by Windows Application Control (librt DLL) | Phase 2 | CI uses Linux so 2.x works there; revisit when Windows policy changes |
| TD-2 | npm audit shows 10 vulnerabilities (3 moderate, 5 high, 2 critical) — Next.js 14 / ESLint 8 transitive deps | Phase 2 | Address during Next.js 15 upgrade |
| TD-3 | ruff TCH003 suppressed for `app/models/*.py` — SQLAlchemy needs `datetime`/`Decimal` at runtime for `Mapped[]` resolution | Phase 3 | Inherent SQLAlchemy constraint; not fixable without removing `from __future__ import annotations` |
| TD-4 | Domain value objects not implemented: Money, Percentage, FinancialRatio, DateRange, SourceCitation, CAGRResult | Phase 3 | Implement when agent layer needs typed value passing; raw Decimal works for current analytics engine |
| TD-5 | PriceHistory provider interface not implemented — impl plan specified 12 interfaces but only 11 built | Phase 5 | Evaluate whether PriceHistory should be a separate interface or folded into MarketDataProvider when historical analysis features are built |
| TD-6 | Readiness test (`test_ready_returns_200`) requires running PostgreSQL — cannot pass in unit test mode | Phase 2 | Requires PostgreSQL with migrations applied; document as integration test and verify with infrastructure |
| TD-7 | Valuation engine gap — historical valuation bands, peer comparison, scenario engine not yet implemented (DCF, Reverse DCF, multiple-based valuation complete) | Phase 6 | Phase 6e.4+ — required before agent orchestration |
| TD-8 | Financial forensics / red flag scoring not implemented | Phase 6 | Phase 6e — part of original Phase 6 scope |
| TD-9 | Document ingestion pipeline, S3 storage, embedding/pgvector semantic search not implemented (partial evidence subsystem) | Phase 4 | Required for full citation chain; implement before or during agent layer |
| TD-10 | Repository layer exists only for evidence and screener — not all 28 domain entities | Phase 3 | Build repositories as needed when agents/API endpoints require them |
| TD-11 | `pytest.mark.integration` not registered — produces PytestUnknownMarkWarning | Phase 3 | Register mark in `pyproject.toml` `[tool.pytest.ini_options]` markers list |

---

## Next Actions

1. **Phase 6e.4: Historical Valuation Bands**
   - Historical valuation band analysis
   - Peer comparison engine
   - Scenario engine (Bear/Base/Bull with explicit assumptions per scenario)
   - Financial forensics / red flag scoring
   - Golden dataset tests with hand-verified calculations
2. **Phase 7: Agent Orchestration (LangGraph)**
   - LangGraph state machine with typed ResearchState
   - First 3 agents: DataCollector, FinancialAnalyst, ThesisChallenger
   - Agent tool wiring (providers → agent tools)
   - Quality gate framework (12 gates)
3. **SEBI XBRL integration** for authoritative financial data
4. **Evaluate Celery vs Temporal** (ADR-002) for background tasks
