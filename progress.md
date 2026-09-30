# Progress Tracker

**Last Updated:** 2026-09-30 (Phase 8.2 Company Research Agent implementation complete)

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

### Phase 6e.4: Historical Valuation Bands — COMPLETE

- [x] `app/valuation/models.py` — Added FinancialPeriodType enum (ANNUAL, TTM), ObservationStatus enum (7 statuses), DataSufficiency enum (5 levels), DataSufficiencyThresholds, HistoricalObservationInput, HistoricalValuationObservation, PercentileBand, ValuationBandStatistics, CurrentValuationPosition, HistoricalValuationResult
- [x] `app/valuation/historical_bands.py` — Deterministic, frequency-agnostic engine: 6 methods (P/E, EV/EBITDA, P/S, P/B, FCF Yield, EV/FCF), point-in-time validation, look-ahead bias prevention, duplicate detection (identical→dedup, contradictory→error), nearest-rank percentile bands, midpoint percentile rank, current position with distance_from_median_pct
- [x] `app/valuation/__init__.py` — Exports: historical_valuation_bands, HistoricalBandError, all new model types
- [x] Six valuation methods: P/E (Price/EPS), EV/EBITDA, P/S (MCap/Revenue), P/B (MCap/Equity), FCF Yield (EquityFCF/MCap, CashFlowBasis.EQUITY_FCF), EV/FCF (EV/FCFF, CashFlowBasis.FCFF)
- [x] FCFF = EBIT×(1−t) + D&A − CapEx − ΔNWC (consistent with Phase 6e.3)
- [x] Point-in-time correctness: financials_available_date <= observation_date → VALID; future → LOOK_AHEAD_RISK; null → UNVERIFIED_TIMING
- [x] VALID observations only in primary statistics; UNVERIFIED_TIMING and LOOK_AHEAD_RISK excluded
- [x] Validation order: structural → duplicate → timing → method-specific
- [x] Determinism: no date.today(), no datetime.now(), calculated_at is caller-supplied passthrough
- [x] All Decimal arithmetic, never float
- [x] `tests/test_valuation_bands.py` — 108 tests across 25 test classes: all six methods, point-in-time validation, duplicate detection, structural validation, statistics (min/max/mean/median/std_dev), nearest-rank percentile bands, midpoint percentile rank, data sufficiency, current position, lookback filtering, edge cases, determinism, median/std_dev helpers, immutability, golden datasets (P/E 5-obs, EV/EBITDA 3-obs, FCF Yield, EV/FCF FCFF), TTM period type, mixed statuses, engine version, method field propagation
- [x] All 108 historical valuation bands tests passing
- [x] Full backend: 960 passed, 1 known failure (TD-6), 7 skipped
- [x] mypy strict: zero errors on valuation module
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] Frontend: 5 tests passing

### Phase 6e.5: Peer Comparison Engine — COMPLETE

- [x] `app/valuation/_valuation_calc.py` — Shared pure-function helpers extracted from historical_bands.py (TD-12 resolved): constants, validation, financial helpers, per-method compute functions, statistical helpers. `compute_observation()` parameterized with `engine_version` and `metric_prefix` keyword arguments.
- [x] `app/valuation/historical_bands.py` — Refactored to import shared helpers from `_valuation_calc.py`. All local function definitions moved to shared module. `validate_percentiles` ValueError wrapped in HistoricalBandError.
- [x] `app/valuation/models.py` — Added 7 peer comparison models: PeerSelectionMethod (6 values), PeerSetMetadata, PeerObservationInput (composition: HAS-A HistoricalObservationInput), PeerValuationObservation, PeerStatistics, TargetVsPeerPosition (with rank_if_inserted), PeerComparisonResult. All frozen Pydantic v2.
- [x] `app/valuation/peer_comparison.py` — Deterministic cross-sectional peer comparison engine. One method per invocation. Accepts explicit peer set (never discovers peers). Peer-specific data sufficiency thresholds (0→INSUFFICIENT, 1-2→MINIMAL, 3-4→LOW, 5-9→MODERATE, 10+→ADEQUATE). Target-as-peer exclusion by company_id. Duplicate detection by company_id (identical→dedup, contradictory→PeerComparisonError). rank_if_inserted = count(peer_value ≤ target_value) + 1. Target positioning only when target is VALID. PEG explicitly rejected. Mixed currencies allowed (ratios are dimensionless). No DB/network/LLM/system clock.
- [x] `app/valuation/__init__.py` — Updated exports for all peer comparison types, compare_peers, PeerComparisonError
- [x] `tests/test_valuation_calc.py` — 51 tests for shared helper functions (constants, validation, timing, denom, EV components, compute_observation 6 methods + PEG rejection, statistical helpers)
- [x] `tests/test_peer_comparison.py` — 89 tests across 19 test classes: all 6 methods (P/E, EV/EBITDA, P/S, P/B, FCF Yield, EV/FCF), PEG rejection, target timing (VALID→position, LOOK_AHEAD_RISK→None, UNVERIFIED_TIMING→None), rank_if_inserted semantics (7 positions), percentile rank, mixed currencies (INR+USD+EUR), duplicate peers (identical→dedup, contradictory→error), target-as-peer exclusion, input ordering independence, data sufficiency (8 threshold levels + custom), invalid data (8 scenarios), net cash, statistics (single peer, std_dev, custom percentiles, median odd/even), determinism, provenance (engine_version, calculated_at, metadata, company identity), target positioning (difference_from_median, pct, vs_p25/p75), edge cases (empty, all invalid, single), golden datasets (5-peer P/E, 3-peer EV/EBITDA, EV/FCF FCFF chain), cross-engine consistency (3 methods: P/E, EV/FCF, FCF Yield), immutability
- [x] `tests/test_valuation_bands.py` — Import paths updated for shared helpers; zero assertion changes; all 108 tests pass
- [x] All 1101 backend tests passing (89 peer comparison + 51 shared helper + 108 historical bands regression + 853 existing)
- [x] mypy strict: zero errors on valuation module
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] Frontend: 5 tests passing

### Phase 6e.6: Scenario Engine (Bear/Base/Bull) — COMPLETE

- [x] `app/valuation/models.py` — Added 9 scenario models after PeerComparisonResult: ScenarioLabel (BEAR/BASE/BULL), ScenarioExecutionStatus (COMPLETED/FAILED), ScenarioDiagnostic (6 values), AssumptionProvenance (parameter, value_description, evidence_category via FindingType, rationale), MultipleScenarioAssumption (method + target_multiple with positive validator), ScenarioDefinition (label, narrative, dcf_assumptions, optional multiple_assumptions, optional probability_weight with non-negative validator, optional assumption_provenance), SingleScenarioOutput (execution_status, dcf_result, multiple_results, implied_value, error_message, diagnostics), ScenarioComparison (value_range, midpoint, probability_weighted_value, upside/downside per scenario, completed_scenario_count, calculations audit trail), ScenarioResult (scenarios, comparison, diagnostics, calculated_at, engine_version). All frozen Pydantic v2 with ConfigDict(frozen=True).
- [x] `app/valuation/dcf.py` — `calculated_at: datetime` is now a REQUIRED keyword argument. No datetime.now() inside the engine. Caller must supply.
- [x] `app/valuation/multiples.py` — `calculated_at: datetime` is now REQUIRED on all 7 valuation functions (pe, ev_ebitda, ps, pb, peg, fcf_yield, ev_fcf). No datetime.now() inside any engine.
- [x] `app/valuation/reverse_dcf.py` — `calculated_at: datetime` is now REQUIRED keyword argument. Passed through to all dcf_valuation calls and the result. No datetime.now() inside the engine.
- [x] `app/valuation/scenario.py` — ~280-line scenario engine. Thin orchestration layer, no formula duplication. ENGINE_VERSION="1.0.0". Error hierarchy: ScenarioEngineError → ScenarioValidationError, ScenarioExecutionError. `_validate_scenarios()` enforces exactly 3 labels, probability weight all-or-none + sum-to-1. `_dispatch_multiple()` typed dispatch to 7 existing valuation functions. `_execute_scenario()` delegates to dcf_valuation with error handling (DCFValidationError/TerminalValueError/ValueError). `_build_comparison()` computes range/midpoint/pwv/upside per scenario. `_collect_diagnostics()` detects VALUE_ORDER_UNEXPECTED, IDENTICAL_ASSUMPTIONS, EXTREME_SPREAD, INCOMPLETE_COMPARISON, MISSING_PROVENANCE. `run_scenarios()` main entry: validate → execute BEAR/BASE/BULL → build comparison → collect diagnostics → return ScenarioResult. Raises ScenarioExecutionError if all 3 fail.
- [x] `app/valuation/__init__.py` — Updated exports: ScenarioLabel, ScenarioExecutionStatus, ScenarioDiagnostic, AssumptionProvenance, MultipleScenarioAssumption, ScenarioDefinition, SingleScenarioOutput, ScenarioComparison, ScenarioResult, ScenarioEngineError, ScenarioValidationError, ScenarioExecutionError, run_scenarios
- [x] `tests/test_scenario_engine.py` — 106 tests across 22+ test classes: model validation, exactly-3-scenarios, duplicate/missing labels, input validation, probability weights, DCF delegation, multiple delegation, scenario failure handling, comparison (range/midpoint/pwv/upside), diagnostics (value ordering/identical assumptions/extreme spread/incomplete/missing provenance), provenance (coverage for DCF assumptions and multiple assumptions), audit trail, Decimal arithmetic, determinism (calculated_at passthrough, no hidden clock dependency, propagation to DCF and multiples results), sensitivity boundary, boundaries (zero/max equity), value ordering (diagnostic only), FCFF consistency (EV/FCF two periods), projection validation, error hierarchy, golden dataset A (bear=94.0153, base=223.3635, bull=357.2581), golden dataset B (PE multiples 12x/18x/25x), reverse DCF regression, immutability
- [x] All 106 scenario engine tests passing
- [x] All 589 valuation tests passing (483 existing + 106 scenario = zero regressions)
- [x] Full backend: 1199 passed, 7 skipped, 1 known failure (TD-6)
- [x] mypy strict: zero errors on valuation module; 1 preexisting error in yahoo_finance.py (unused type: ignore, Phase 6d)
- [x] ruff: zero errors
- [x] tsc strict: zero errors
- [x] FindingType reused from app.models.enums (FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, UNCERTAINTY)
- [x] No persistence, no ORM, no database, no LLM, no network

### Phase 6e.7: Financial Forensics / Red Flag Screening Engine — COMPLETE

- [x] `app/valuation/forensic_models.py` — 12 frozen Pydantic v2 domain models: ForensicCheckStatus (8 values), ForensicSeverity (4), ForensicCategory (5), ThresholdDirection (2), ThresholdClassification (3), CompanyType (2), ForensicPeriodInput (composition with PeriodFinancials), ThresholdConfig, ForensicConfig, DataQualityDiagnostic, ForensicCheckResult, ForensicCategorySummary, ForensicResult
- [x] `app/valuation/forensics.py` — ~2100-line deterministic forensic engine. 22 individual checks across 5 categories (Earnings Quality, Working Capital, Cash Flow Quality, Leverage, Profitability). 8-status model: FLAGGED, PASS, NOT_COMPUTABLE, INVALID_INPUT, NOT_APPLICABLE, INSUFFICIENT_HISTORY, UNVERIFIED_TIMING, LOOK_AHEAD_RISK. Point-in-time validation (VALID/LOOK_AHEAD_RISK/UNVERIFIED_TIMING). Beneish components (DSRI, GMI, SGI, TATA — composite NOT_COMPUTABLE due to missing ppe_net/retained_earnings). Altman components (X1, X3, X4, X5 — composite NOT_COMPUTABLE due to missing retained_earnings; X4 derives total_liabilities as total_assets − total_equity). Financial company support (exactly 3 of 22 checks applicable). Interest coverage: zero → NOT_COMPUTABLE, negative → INVALID_INPUT. ThresholdClassification (PUBLISHED_MODEL, ACCOUNTING_IDENTITY, PLATFORM_HEURISTIC). No aggregate score. Language safety: never "fraud", "manipulation", etc. Category summaries are descriptive only.
- [x] `app/valuation/__init__.py` — Updated exports: 13 forensic model types + DEFAULT_CONFIG, FINANCIAL_APPLICABLE_CHECKS, ForensicValidationError, forensic_analysis
- [x] `tests/test_forensics.py` — 118 tests across 30+ test classes: input validation (5), timing semantics (4), all 22 individual checks, Beneish components (7), Altman components (10), financial company (4), category summaries (4), data quality diagnostics (3), determinism (3), audit trail (5), language safety (2), Decimal enforcement (2), check count (2), no aggregate score (1), golden datasets A-E (12), threshold config (3), edge cases
- [x] All 118 forensic tests passing
- [x] Full backend: 1324 passed, 7 skipped, 1 known failure (TD-6)
- [x] mypy strict: zero new errors (1 preexisting in yahoo_finance.py)
- [x] ruff: zero errors
- [x] No DB/ORM/network/LLM/system clock dependencies
- [x] Decimal-only arithmetic throughout
- [x] safe_divide() reused from app.analytics._calc
- [x] CalculationResult audit trail on every check
- [x] FindingType.CALCULATION reused from app.models.enums

### Phase 7: Research Run Infrastructure — COMPLETE

- [x] `app/models/enums.py` — Evolved ResearchRunStatus from 4 to 7 values (CREATED, QUEUED, RUNNING, COMPLETED, FAILED, PARTIAL, CANCELLED); added StepStatus (5 values), AgentExecutionStatus (5 values), ArtifactType (5 values)
- [x] `app/models/research.py` — Evolved ResearchRun (VARCHAR+CHECK, parent_run_id, observation_date, configuration, error_summary, TimestampMixin); evolved ResearchFinding (observation_date, source_publication_date, calculation_version, supersedes_finding_id, agent_execution_id); added ResearchRunStep, AgentExecution (reproducibility fields), ResearchArtifact, ResearchRunSource
- [x] `app/models/thesis.py` — Added research_run_id FK, snapshot_data JSONB, key_changes JSONB to ThesisVersion
- [x] `app/models/state_machines.py` — State transition tables and validators for run, step, execution state machines; ValidationError on invalid transitions
- [x] `alembic/versions/004_research_run_infrastructure.py` — Migration: PG enum → VARCHAR+CHECK (INCOMPLETE→PARTIAL), 4 new tables, new columns/indexes, full downgrade
- [x] `app/schemas/research_run.py` — Pydantic v2 DTOs: Run, Step, Execution, Finding, Artifact, Source, EvidenceChain (ConfigDict from_attributes=True); `llm_config` field name to avoid Pydantic v2 `model_config` conflict
- [x] `app/repositories/research_run.py` — 6 Protocol interfaces + 6 SQLAlchemy implementations (ResearchRun, Step, Execution, Finding, Artifact, Source); concurrent run prevention via DB query
- [x] `app/services/research_run.py` — Full lifecycle service: initiate/enqueue/start/complete/fail/partial/cancel run; step management; agent execution with MAX_AGENT_RETRIES=3; findings with temporal validation; artifacts; aggregates
- [x] Existing Claim/ClaimEvidence models preserved untouched
- [x] Deprecated JSONB fields (agent_execution_log, data_sources_used, cost_by_agent) retained
- [x] No LangGraph, no Celery/Temporal, no Redis locks, no REST/WebSocket endpoints
- [x] `tests/test_research_run_state_machine.py` — Tier 1: 13 state machine tests
- [x] `tests/test_research_run_models.py` — Tier 2: 30 model/enum/constraint tests
- [x] `tests/test_research_run_repository.py` — Tier 3: 20 repository tests with mocked AsyncSession
- [x] `tests/test_research_run_service.py` — Tier 4: 75 service tests (lifecycle, resume, execution, findings, artifacts, aggregates, steps, not-found)
- [x] `tests/test_models.py` — Updated: ALL_MODELS +4, enum assertions updated for 7-value ResearchRunStatus + 3 new enums
- [x] Full backend: 1471 passed, 7 skipped, 1 known failure (TD-6)
- [x] mypy strict: zero new errors (1 preexisting in yahoo_finance.py)
- [x] ruff: zero errors
- [x] 138 new Phase 7 tests total

### Phase 7 Audit Hardening — COMPLETE

Post-audit remediation of 6 findings from Phase 7 implementation audit:

- [x] Issue #1: Service lifecycle methods (start_run, complete_run, fail_run, partial_run, cancel_run, complete_step) refactored to delegate to repository `update_status()` instead of direct session mutation
- [x] Issue #2: Added `ResearchRunSourceRepositoryProtocol` with `create()` and `get_by_run()` methods
- [x] Issue #3: Added post-INSERT temporal validation enforcing `source_publication_date ≤ finding.created_at` (architecture §12.2.2)
- [x] Issue #4: Updated architecture document to include QUEUED→CANCELLED transition in state diagram and transition rules
- [x] Issue #5: Added `TimestampMixin` to `ResearchRunStep` (provides `updated_at` alongside existing `created_at`); migration 005 adds `updated_at` column
- [x] Issue #6: Aligned `ResearchRunRepositoryProtocol.update_status()` signature with concrete implementation (added `started_at`, `quality_gate_results`, return type `ResearchRun | None`); same for `ResearchRunStepRepositoryProtocol`
- [x] `alembic/versions/005_add_updated_at_to_research_run_step.py` — adds `updated_at` column with server_default and downgrade
- [x] 13 new tests: 7 service/repository boundary, 5 temporal validation (§12.2.2), 1 protocol compliance
- [x] Full backend: 1485 passed, 7 skipped, 1 known failure (TD-6)
- [x] mypy strict: zero new errors (1 preexisting in yahoo_finance.py)
- [x] ruff: zero errors
- [x] Frontend: 5 passed, tsc clean

---

### Phase 8.1: Company Research Agent Contracts & Schemas — COMPLETE

- [x] `app/agents/__init__.py` — Agent module init
- [x] `app/agents/contracts.py` — All Phase 8.1 typed contracts (~480 lines):
  - `IdentifierType` enum (NSE_SYMBOL, BSE_CODE, ISIN)
  - `FINDING_CATEGORIES` frozenset (14 categories)
  - Constants: AGENT_TOKEN_BUDGET=30,000, AGENT_TOKEN_WARNING_THRESHOLD=24,000, AGENT_NAME, MAX_LLM_ATTEMPTS=2
  - `CompanyResearchRequest` (frozen) — agent input contract
  - `CompanyResearchConfig` (frozen) — agent configuration
  - `SourceCandidate` (frozen) — generic source representation (Filing/Transcript/News)
  - 8 tool I/O contracts (validate_company through persist_findings)
  - `EvidenceExtractionOutput` — LLM structured output schema
  - `FindingGenerationOutput` — LLM structured output schema with evidence_indices
  - `FindingValidationResult` — deterministic validation results
  - `TokenBudget` (mutable) — cumulative usage tracking with Decimal utilization_pct
  - `StepDefinition` + `COMPANY_RESEARCH_STEPS` — 7-step workflow configuration
- [x] `tests/agents/__init__.py` — Test package init
- [x] `tests/agents/test_contracts.py` — 126 comprehensive tests (~750 lines):
  - 20+ test classes covering all contract areas
  - Constants, enums, request/config, SourceCandidate, all 8 tools, LLM outputs
  - Validation (frozen immutability, field constraints, boundary values)
  - Enum reuse verification (DocumentType, SourceTier, EvidenceType, FindingType, ConfidenceLevel)
  - JSON serialization round-trip tests with Decimal preservation
- [x] `pyproject.toml` — Added agents per-file ignore for ruff TCH rules
- [x] Quality gates: 126 tests passing, ruff clean, mypy strict clean
- [x] Zero database schema changes
- [x] Zero new dependencies
- [x] Full backend: 1612 passed, 7 skipped, 1 known failure (TD-6)

### Phase 8.2: Company Research Agent Implementation — COMPLETE

- [x] `app/agents/company_research/agent.py` — CompanyResearchAgent orchestrator (~721 lines):
  - CompanyResearchResult (frozen Pydantic v2): run_id, status, company_id, company_name, findings_count, evidence_count, steps_completed, steps_total, token_budget, validation_result, error
  - 7-step sequential workflow: company_validation → source_discovery → document_retrieval → evidence_extraction → finding_generation → finding_validation → gap_contradiction_analysis
  - `_run_step_deterministic()` and `_run_step_llm()` generic step runners (TypeVar `_T`)
  - LLM retry: MAX_LLM_ATTEMPTS=2 (1 initial + 1 retry) per ADR-007
  - TokenBudget enforcement: 30K hard limit, 24K warning threshold
  - Concurrent document retrieval via asyncio.gather
  - Evidence extraction with structured LLM output parsing
  - Finding generation with evidence linking (evidence_indices)
  - Finding validation (deterministic): category check, content length, FACT-requires-evidence
  - Gap/contradiction detection via LLM
  - Error handling: early failure → FAILED, late failure → PARTIAL
- [x] `app/agents/company_research/tools.py` — 8 tool implementations + create_research_document helper (~400 lines):
  - validate_company: DB lookup by NSE_SYMBOL/BSE_CODE/ISIN
  - discover_sources: aggregates filings + transcripts + news, sorted by date
  - retrieve_document: fetches filing content with SHA-256 hash
  - get_company_profile: full company profile from DB
  - search_company_news: filtered by observation_date
  - get_financial_summary: INCOME_STATEMENT + BALANCE_SHEET + CASH_FLOW
  - persist_evidence: batch evidence creation
  - persist_findings: validated finding creation via ResearchRunService
- [x] `app/agents/company_research/prompts.py` — LLM prompt templates (~95 lines):
  - SYSTEM_PREAMBLE with `<retrieved_document>` prompt injection defense
  - evidence_extraction_prompt: extracts FACT/FINANCIAL_DATA/MANAGEMENT_STATEMENT/ANALYST_OPINION/REGULATORY_FILING
  - finding_generation_prompt: generates findings with 7-type classification and 14 categories
  - gap_contradiction_prompt: identifies research_gap and contradiction findings
- [x] `app/agents/company_research/exceptions.py` — Agent-specific exception hierarchy (~53 lines):
  - AgentError(AppError) base, CompanyNotFoundError, TokenBudgetExhaustedError, LLMParsingError, StepFailedError
- [x] `app/agents/company_research/__init__.py` — Package exports
- [x] **Bug fix**: Added `if findings:` guard before `persist_findings` call in `_step_finding_generation` (PersistFindingsInput requires min_length=1)
- [x] `tests/agents/test_company_research_agent.py` — 64 tests across 15 test classes (~1100 lines):
  - TestAgentConstruction (4), TestHappyPath (2), TestDeterministicStepRunner (2)
  - TestLLMStepRunner (7): success, retry on parsing/provider error, max attempts, budget exhaustion
  - TestTokenBudgetEnforcement (6), TestFindingValidation (7), TestEvidenceExtraction (3)
  - TestFindingGeneration (3), TestGapContradiction (3), TestErrorHandling (4)
  - TestResponseParsing (6), TestPromptTemplates (4), TestExceptions (4)
  - TestGoldenScenarios (5): RELIANCE, TCS, INFY, HDFCBANK, BSE code
  - TestCompanyResearchResultModel (4)
- [x] Zero database schema changes
- [x] Zero new dependencies
- [x] No LangGraph
- [x] Agent depends on Protocol interfaces only (no concrete provider imports)
- [x] Prompt injection defense: document content in `<retrieved_document>` XML tags
- [x] ruff: zero errors on all agent module files
- [x] mypy strict: zero new errors (1 preexisting in yahoo_finance.py)
- [x] Full backend: 1675 passed, 7 skipped, 1 known failure (TD-6) — zero regressions

---

## Current Phase

**Next Phase:** Phase 9 — Industry Research Agent

---

## Completed Features

- Health check endpoint (`GET /health`) — database and Redis connectivity
- Readiness endpoint (`GET /health/ready`) — migration version validation
- Frontend health page (`/health`) — static system status display
- Structured JSON logging with request ID correlation
- Request ID middleware with unhandled exception safety net
- Complete domain model: 32 ORM models, 6 junction tables, 30 enums across 7 schemas
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
- Historical Valuation Bands: 6 methods (P/E, EV/EBITDA, P/S, P/B, FCF Yield, EV/FCF), point-in-time correctness, look-ahead bias prevention, nearest-rank percentile bands, midpoint percentile rank, current position, frequency-agnostic, 108 tests with golden datasets
- Peer Comparison Engine: 6 methods, explicit peer set input, rank_if_inserted positioning, cross-sectional statistics, peer-specific data sufficiency, target-as-peer exclusion, duplicate detection, mixed currencies, shared helper extraction (_valuation_calc.py), 89 tests with golden datasets and cross-engine consistency
- Scenario Engine (Bear/Base/Bull): thin orchestration over DCF + multiples engines, exactly 3 scenarios required, explicit failure modeling (ScenarioExecutionStatus), probability-weighted value, 6 diagnostics, AssumptionProvenance with FindingType, deterministic calculated_at passthrough, 99 tests with golden datasets
- Financial Forensics / Red Flag Screening Engine: 22 checks across 5 categories, 8-status model, Beneish/Altman components (composites NOT_COMPUTABLE due to missing fields), point-in-time validation, financial company support (3 applicable checks), language safety, no aggregate score, 118 tests with golden datasets
- Research Run Infrastructure: ResearchRun lifecycle (7-state machine), ResearchRunStep, AgentExecution (with reproducibility metadata), ResearchFinding (with temporal integrity and supersession), ResearchArtifact, ResearchRunSource; state machines, repository layer (6 Protocol interfaces + SQLAlchemy implementations), service layer with concurrent run prevention, MAX_AGENT_RETRIES=3, temporal validation; 138 tests
- Company Research Agent: 7-step sequential orchestrator (validate → discover → retrieve → extract → generate → validate → gap/contradiction), 8 tool implementations, LLM integration with structured output parsing, evidence extraction and persistence, finding generation with evidence linking, deterministic finding validation, gap/contradiction detection, token budget enforcement (30K hard/24K warning), retry handling (MAX_LLM_ATTEMPTS=2), prompt injection defense; 64 tests with 5 golden scenarios

---

## Failing Tests

- `test_health.py::TestReadinessEndpoint::test_ready_returns_200` — pre-existing, requires running PostgreSQL with migrations applied. This is an integration test that validates the readiness endpoint checks Alembic migration state against a live database. Cannot pass without PostgreSQL. 1471 other backend tests pass. 5 frontend tests pass. 7 tests skipped (6 integration tests requiring PostgreSQL, 1 provider test requiring API key).

---

## Known Issues

| ID | Issue | Severity | Phase to Address |
|----|-------|----------|-----------------|
| K-1 | NSE does not offer a free, open API — primary data source at risk | Critical | Phase 4 |
| K-2 | Background task processor not decided (Celery vs Temporal) | Medium | Phase 2 |
| K-3 | Embedding dimension hardcoded to 1536 — should be configurable | Low | Phase 5 |
| K-4 | LLMProvider interface may not align with LangGraph native invocation | Medium | Phase 19 |
| K-5 | DPDP Act 2023 compliance requires legal review before commercialization | Medium | Pre-launch |
| K-6 | Evidence Verification Agent has circular LLM dependency — mitigated by partial deterministic checks | Low | Phase 17 |

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
| Anthropic Claude | LLMProvider | Not started | Phase 8 (first agent needing LLM) |
| OpenAI | LLMProvider, EmbeddingProvider | Not started | Phase 5/8 |
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
| TD-7 | ~~Valuation engine gap — financial forensics / red flag scoring not yet implemented~~ | Phase 6 | **RESOLVED** — Phase 6e.7 complete |
| TD-8 | ~~Financial forensics / red flag scoring not implemented~~ | Phase 6 | **RESOLVED** — Phase 6e.7 complete |
| TD-9 | Document ingestion pipeline, S3 storage, embedding/pgvector semantic search not implemented (partial evidence subsystem) | Phase 4 | Required for full citation chain; implement before or during agent layer |
| TD-10 | Repository layer exists only for evidence and screener — not all 28 domain entities | Phase 3 | Build repositories as needed when agents/API endpoints require them |
| TD-11 | `pytest.mark.integration` not registered — produces PytestUnknownMarkWarning | Phase 3 | Register mark in `pyproject.toml` `[tool.pytest.ini_options]` markers list |

---

## Next Actions

1. **Phase 9: Industry Research Agent** — second agent implementation (industry structure, competitive dynamics, sector trends)
2. **SEBI XBRL integration** for authoritative financial data
3. **Evaluate Celery vs Temporal** (ADR-002) for background tasks
