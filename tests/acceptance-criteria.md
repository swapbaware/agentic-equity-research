# Acceptance Criteria

This document defines the acceptance criteria for each major capability of the Agentic Equity Research Platform. These criteria are the "definition of done" — a feature is not complete until all its acceptance criteria pass. Tests in the test suite map directly to these criteria.

---

## AC-1: Health & Infrastructure

### AC-1.1: Backend Health Check
- `GET /health` returns `200` with JSON body containing `status`, `database`, `redis` fields
- Returns `503` if database or Redis is unreachable
- Response time < 500ms

### AC-1.2: Readiness Check
- `GET /health/ready` returns `200` when database migrations are current
- Returns `503` when pending migrations exist

### AC-1.3: Configuration
- Application loads all configuration from environment variables
- Missing required environment variable → startup fails with clear error message
- No hardcoded configuration values in application code

### AC-1.4: Structured Logging
- Every log entry is valid JSON
- Every log entry contains `timestamp`, `level`, `service`, `message`
- Every request-scoped log entry contains `trace_id` and `span_id`
- No secrets appear in log output

### AC-1.5: Database Migrations
- `alembic upgrade head` runs without error on clean database
- `alembic downgrade -1` reverses the latest migration without error
- Every migration has both `upgrade()` and `downgrade()` methods
- Schema changes are backwards-compatible (column additions nullable or with default)

---

## AC-2: Domain Model

### AC-2.1: Entity Completeness
- All 30+ entities from `architecture/domain-model.md` implemented as Pydantic + SQLAlchemy models
- All entities have UUID primary keys, `created_at`, `updated_at`
- All financial columns use PostgreSQL `NUMERIC` type

### AC-2.2: Value Objects
- `Money`: stores amount as `Decimal` + currency code. Arithmetic operations preserve currency.
- `Percentage`: validates 0-100 range (or wider with documented justification). Arithmetic operations correct.
- `FinancialRatio`: stores ratio as `Decimal`. Handles division-by-zero gracefully.
- `DateRange`: enforces start ≤ end.
- `SourceCitation`: requires document_id + location.

### AC-2.3: Model Validation
- Pydantic models reject: wrong types, out-of-range values, missing required fields
- Financial values: reject `float` input, accept `Decimal` and numeric strings
- Enum fields: reject values not in the enum definition

### AC-2.4: Repository Layer
- Every entity has async CRUD operations (create, read, update, delete, list)
- List operations support cursor-based pagination
- Queries are parameterized (no SQL injection)
- Round-trip test: create entity → read back → values match

---

## AC-3: Provider Framework

### AC-3.1: Interface Definitions
- All 12 provider interfaces defined as Python `Protocol` classes
- Every method has typed parameters and return types (no `Any`)
- Financial values returned as `decimal.Decimal`

### AC-3.2: Rate Limiting
- Redis-backed token bucket limits requests per provider
- Exceeding rate limit → `ProviderRateLimitError` raised
- Rate limit configuration per provider via environment variables
- Token bucket replenishes at configured rate

### AC-3.3: Retry Logic
- 429 response → exponential backoff, respects `Retry-After` header
- 5xx response → retry 3 times with exponential backoff
- Timeout → retry once with increased timeout
- 401/403 → fail immediately, no retry
- 4xx (other) → fail immediately, no retry

### AC-3.4: Provider Factory
- Configuration specifies which implementation to use per interface
- Factory returns correct implementation
- Changing configuration → different implementation, zero business logic changes

### AC-3.5: Decimal Boundary
- No provider returns `float` for any financial value
- Test: mock provider returning float → conversion to Decimal at boundary → Decimal in application

### AC-3.6: Conformance Suite
- Shared test suite validates any implementation against the Protocol contract
- New provider implementation can be validated by running conformance suite

---

## AC-4: Evidence & Citation System

### AC-4.1: Document Ingestion
- PDF → text extraction produces readable output for sample Indian annual reports
- HTML → sanitized text (no script tags, no event handlers, no embedded objects)
- Duplicate detection: same document ingested twice → single storage entry (SHA-256 hash)

### AC-4.2: Embedding & Search
- Text → embedding → pgvector storage → semantic search retrieval
- Search query returns top-k relevant chunks with similarity scores
- Embedding dimension configurable per provider (not hardcoded)

### AC-4.3: Citation Chain
- Every Evidence record links to a ResearchDocument
- Every FACT-type ResearchFinding links to at least one Evidence record
- Citation chain traversable: finding → evidence → document → source

### AC-4.4: Source Tier Classification
- BSE/NSE/SEBI data → Tier 1
- Industry body reports → Tier 2
- News articles, web content → Tier 3
- Tier recorded on every Evidence record

### AC-4.5: Citation Completeness Validation
- FACT-type finding without citation → validation fails
- CALCULATION-type finding → validation passes (calculation is deterministic)
- AI_INFERENCE-type finding without citation → warning (not hard failure)
- MANAGEMENT_CLAIM without source → validation fails

---

## AC-5: Financial Calculation Engine

### AC-5.1: Decimal Arithmetic
- Every calculation function accepts and returns `decimal.Decimal`
- No `float` anywhere in calculation code paths (enforced by type checker)
- Rounding rules documented per calculation type

### AC-5.2: Core Calculations
- CAGR: `start=100, end=200, years=5` → `14.87%` (exact Decimal match)
- ROE: `net_income=50, equity=200` → `25.00%`
- Every ratio from research methodology computable with known inputs
- Edge cases: division by zero → documented behavior (error or None), negative equity → handled

### AC-5.3: Valuation Models
- DCF: configurable inputs (revenue growth, margin, tax, capex, WC, terminal growth, WACC)
- DCF: produces range (low/mid/high), never single value
- All assumptions visible in output object
- Reverse DCF: given market price, derives implied growth rate
- Multiples: P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF — each matches manual calculation

### AC-5.4: Scenario Engine
- Bear/Base/Bull scenarios with distinct assumptions
- Each scenario: revenue CAGR, margin trajectory, EPS path, valuation range
- Assumptions differ between scenarios (not just the result)

### AC-5.5: Financial Forensics
- Receivables growing faster than revenue → red flag
- CFO below PAT → red flag
- Produces `FinancialRedFlagScore` with per-check evidence

### AC-5.6: Screening Engine
- AND/OR filters across financial metrics
- `ROCE > 15 AND Debt/Equity < 0.5` → correct company list
- Saved screens persist and reload correctly

### AC-5.7: Golden Dataset
- 3-5 reference companies with hand-verified financial data
- All calculations match hand-verified results exactly (Decimal comparison)

---

## AC-6: Agent Orchestration

### AC-6.1: Graph Execution
- LangGraph graph compiles without error
- End-to-end execution with mock LLM: all 17 agents complete
- Agents without data dependencies execute in parallel

### AC-6.2: Agent Output Schemas
- Every agent's output validates against its Pydantic output schema
- Every FACT-type finding has evidence references
- Moat default: NONE. Score default: 0.

### AC-6.3: Quality Gates
- All 12 gates from `docs/research-methodology.md` implemented
- Known-good data → all 12 gates pass → status COMPLETED
- Incomplete data → specific gates fail → status INCOMPLETE
- Gate failure after retry → no further attempts (max 2 iterations)
- Failed quality gate → clear error message identifying what's missing

### AC-6.4: Timeout & Budget Enforcement
- Per-agent timeout: agent killed after configured timeout
- Per-agent token budget: agent stopped if budget exceeded
- Total run timeout: 15 minutes max
- Exceeded budget/timeout → workflow continues with independent agents

### AC-6.5: Concurrency Control
- Redis advisory lock prevents concurrent research on same company
- Second research run on same company → rejected with clear message
- Lock released on completion (success or failure)

### AC-6.6: Checkpointing & Resume
- LangGraph checkpointing saves state after each agent
- Interrupted run → resume from last checkpoint → completes

### AC-6.7: Error Handling
- Agent failure → marked FAILED in execution log
- Workflow continues with agents that don't depend on failed agent
- Partial completion → status INCOMPLETE with list of failed agents

### AC-6.8: Evidence Verification
- Deterministic checks: document exists, financial figures cross-checked against stored data
- FACT-type finding citing non-existent document → flagged
- Financial figure in finding ≠ stored provider data → flagged
- Semantic similarity check: claimed fact vs source text

### AC-6.9: Reproducibility
- Same company + same data + same mock LLM → structurally consistent output
- Structural consistency: same agents complete, same quality gates pass/fail, same score dimensions present

---

## AC-7: API Layer

### AC-7.1: Authentication
- Unauthenticated request to protected endpoint → 401
- Invalid/expired JWT → 401
- Valid JWT → 200

### AC-7.2: Authorization
- viewer: can read reports, dashboards → 200; cannot initiate research → 403
- analyst: can read + initiate research + manage watchlists → 200
- admin: can manage users + system configuration → 200

### AC-7.3: API Conventions
- All endpoints under `/api/v1/`
- List endpoints: cursor-based pagination with `next_cursor` and `has_more`
- Error responses: `{"error": {"code": "...", "message": "...", "details": {...}}}`
- No financial data returned as `float` in any JSON response

### AC-7.4: Research Run API
- `POST /api/v1/research/runs` → initiates research, returns run ID
- `GET /api/v1/research/runs/{id}` → returns status (RUNNING/COMPLETED/INCOMPLETE/FAILED)
- `GET /api/v1/research/runs/{id}/report` → returns completed report with citations

### AC-7.5: WebSocket
- Research chat at `/ws/research/{company_id}`
- Messages are JSON with `type` field
- Responses include citation links

### AC-7.6: Rate Limiting
- Exceed per-user rate limit → 429 with `Retry-After` header

---

## AC-8: Frontend

### AC-8.1: Responsive Design
- All pages render without horizontal scroll at 375px width
- All pages render correctly at 1440px width

### AC-8.2: Authentication Flow
- Login → redirect to OAuth provider → callback → dashboard
- Session expiry → redirect to login

### AC-8.3: Screener
- Set financial filters → results update
- AND/OR filter combinations work correctly
- Save screen → reload → filters and results restored

### AC-8.4: Company Detail
- All sections render with data from API
- Scorecard: every score clickable → sub-scores → evidence
- Research report: every statement shows classification label

### AC-8.5: Research Chat
- Send question → receive answer with citations
- Click citation → view source document/section

### AC-8.6: No Hardcoded URLs
- All API URLs from environment/configuration
- No hardcoded localhost or IP addresses in production builds

---

## AC-9: Deployment & Observability

### AC-9.1: Docker Compose
- `docker-compose up` starts all 7 services
- All health checks pass within 60 seconds
- Seed data loads without error

### AC-9.2: Full Research Workflow
- Initiate research from UI → agents execute → quality gates → report viewable in UI
- Complete in < 5 minutes for single company

### AC-9.3: Observability
- OpenTelemetry traces: request → backend → agent → LLM call spans present
- Prometheus metrics: all metric types from deployment architecture collected
- Grafana dashboards: all 5 render with data
- Alerts: simulated failures trigger correct alerts

### AC-9.4: Performance
- Non-research API endpoints: p95 response time < 200ms
- Screening queries: p95 response time < 3 seconds

### AC-9.5: Security
- No known critical/high severity dependency vulnerabilities
- No secrets in Docker images or logs
- Database not exposed to public network in production configuration

---

## Cross-Cutting Acceptance Criteria

These apply to ALL phases:

### CC-1: Financial Data Integrity
- No `float` type used for financial data anywhere in the codebase
- All financial database columns are `NUMERIC`
- All financial calculations use `decimal.Decimal`

### CC-2: Evidence Traceability
- Every FACT-type finding has a source citation
- Citation chain is complete and traversable

### CC-3: Type Safety
- Python: `mypy --strict` passes with zero errors
- TypeScript: `tsc --strict` passes with zero errors

### CC-4: Test Coverage
- New code meets coverage targets from testing strategy
- No tests weakened or removed to pass CI

### CC-5: Security
- No secrets in source code, logs, or container images
- All external input validated
- Prompt injection defenses in place for any agent-processed content
