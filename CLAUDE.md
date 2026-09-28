# CLAUDE.md — Engineering Constitution

This file is the engineering constitution for the Agentic Equity Research Platform. Every commit, review, and design decision must be consistent with these principles. When in doubt, this file is authoritative.

---

## 1. Project Purpose

An evidence-driven Agentic Equity Research Operating System for Indian listed companies (NSE/BSE). The platform orchestrates 17 specialized AI agents to produce institutional-quality equity research with full source attribution.

**The platform IS**: A research and decision-support system that discovers, analyzes, and monitors companies while maintaining strict separation between facts, calculations, management claims, analyst opinions, AI inference, assumptions, and uncertainty.

**The platform IS NOT**: A stock-tip generator. It must never claim a company will become a "multibagger," manufacture certainty about future returns, or generate personalized buy/sell recommendations.

---

## 2. Architectural Principles

- **Clean Architecture**: Domain logic at the center, dependencies point inward. No framework or infrastructure concerns leak into business logic. Separate concerns into layers — domain, application, infrastructure, presentation.
- **Provider Abstraction**: Every external service (LLM, financial data, storage, search) is accessed through a Protocol interface. Concrete implementations are injected, never imported directly by business logic. Providers are swappable via configuration. See `docs/api-provider-strategy.md`.
- **Strong Typing**: Pydantic v2 models (backend) and TypeScript strict mode (frontend) everywhere. No `Any` types except at serialization boundaries. No `# type: ignore` without a comment explaining why.
- **Structured Agent Communication**: Agents communicate through typed `ResearchState`, not arbitrary text passing. LangGraph state machine with defined workflow, not emergent agent-to-agent chat.
- **Evidence-First**: Every factual claim must be traceable to a source document. No LLM-fabricated financial data enters the system as fact.
- **Record Architectural Decisions**: Important decisions are documented in `architecture/adr/` files. Do not silently make architectural assumptions.

---

## 3. Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) | |
| Frontend | Next.js, TypeScript strict, Tailwind CSS | |
| Agent Orchestration | LangGraph | ADR-001 |
| Database | PostgreSQL 16+, pgvector | NUMERIC for financials |
| Cache | Redis 7+ | Token bucket rate limiting |
| Object Storage | S3-compatible (MinIO for local dev) | |
| Background Tasks | Celery or Temporal | ADR-002 (pending) |
| Observability | OpenTelemetry, structured JSON logging | |
| Auth | OAuth 2.0 / JWT | |
| Deployment | Docker, Docker Compose | |
| CI/CD | GitHub Actions | |
| Linting | ruff (Python), eslint (TypeScript) | |
| Type Checking | mypy strict (Python), tsc strict (TypeScript) | |
| Testing | pytest, Vitest, Playwright | |

---

## 4. Coding Standards

### Python
- **Linter**: ruff (replaces flake8/black/isort)
- **Type checker**: mypy in strict mode
- **Formatter**: ruff format
- **Imports**: stdlib → third-party → local, separated by blank lines
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants
- **No `Any`**: Except at serialization boundaries, with a comment explaining why
- **No `# type: ignore`**: Without a comment explaining why
- **No prototype code in main**: No "TODO: fix later" without a linked issue

### TypeScript
- **Strict mode**: Always enabled
- **No `any`**: Use `unknown` and narrow
- **React**: Functional components, hooks only

### General
- Prefer composition over inheritance
- Keep modules small and focused — each independently testable
- No over-engineering: build what is needed for the current phase
- Do not silently expand scope for hypothetical future requirements
- Default to no comments; add one only when the WHY is non-obvious

---

## 5. Security Requirements

- **No hard-coded secrets**: API keys, database credentials, and tokens live in environment variables loaded from `.env` (never committed). Use `.env.example` as the template.
- **Validate all external input**: Financial data from APIs, user input, and LLM outputs must be validated before use.
- **Prompt injection defense**: Documents retrieved from the web are untrusted input. Retrieved content placed inside `<retrieved_document>` XML delimiter tags. System prompt explicitly states content is data, not instructions. Agent outputs validated against expected schemas.
- **Document sanitization**: Ingested documents (PDFs, HTML) are text-extracted and stripped of executable content before storage. HTML sanitized to plain text or safe Markdown.
- **Agent least privilege**: Each agent has access only to the tools it needs. No agent has unrestricted tool access.
- **No secrets in logs**: Mask secrets in error messages and stack traces.
- **HTTPS required in production**: HTTP acceptable for local development only.
- **Dependency security**: Dependencies pinned to exact versions in lock files. Automated vulnerability scanning.

---

## 6. Testing Requirements

- **Test-Driven Development**: Write tests before or alongside implementation.
- **Coverage targets**: 95% domain logic, 90% API endpoints, 85% provider adapters, 80% agent orchestration, 75% frontend components, 80% overall.
- **Never remove or weaken tests to make implementation pass**: If a test fails, fix the implementation.
- **Financial calculations require exact assertions**: Use `Decimal` comparisons, never approximate float matches.
- **Agent tests verify structure, not prose**: Test that the output schema is correct and evidence is attached, not that the LLM wrote good English.
- **No network calls in unit tests**: Mock all external dependencies.
- **Flaky tests are bugs**: Investigate and fix non-determinism immediately.
- **Golden dataset tests**: 3-5 reference companies with hand-verified calculations.
- **See**: `docs/testing-strategy.md`, `tests/acceptance-criteria.md`.

---

## 7. Provider Abstraction Rules

1. Every external service is accessed through a Python `Protocol` interface (structural typing).
2. Concrete implementations are injected via a provider factory, driven by configuration.
3. Business logic NEVER imports a concrete provider directly.
4. All financial values are converted to `decimal.Decimal` at the provider boundary — no floats cross inward.
5. Every provider implementation uses the shared Redis-backed `RateLimiter`.
6. Every provider logs all API calls (provider, endpoint, latency, status) via structured logging.
7. Switching a provider requires: implementing the interface, adding config, updating the factory, running the conformance test suite. No changes to business logic, agents, or UI.
8. Provider error hierarchy: `ProviderError` → Auth, RateLimit, NotFound, Timeout, Unavailable, Data errors.
9. Rate limiting: token bucket algorithm in Redis.
10. See: `docs/api-provider-strategy.md`, ADR-005.

---

## 8. Evidence & Citation Rules

1. Every AI-generated research finding must cite its source data.
2. Agent outputs include provenance metadata.
3. Research findings are classified as: **FACT**, **CALCULATION**, **MANAGEMENT_CLAIM**, **ANALYST_OPINION**, **AI_INFERENCE**, **ASSUMPTION**, **UNCERTAINTY**.
4. These categories must NEVER be mixed or conflated.
5. Every FACT-type finding must have a source citation linking to an `Evidence` record.
6. Management statements are labeled as MANAGEMENT_CLAIM, never presented as fact.
7. AI inferences are labeled as AI_INFERENCE.
8. Source tier recorded with every Evidence record (Tier 1: NSE/BSE/SEBI/company filings, Tier 2: industry bodies, Tier 3: publications/research).
9. Financial data (revenue, profit, ratios) must come from Tier 1 sources.
10. Only verified, source-backed facts enter Evidence Memory. LLM-generated inferences stored as AI_INFERENCE, never promoted to fact without evidence.
11. See: ADR-004, `docs/research-methodology.md`.

---

## 9. Financial Calculation Rules

1. **`decimal.Decimal` always**: All monetary and financial ratio calculations use Python `decimal.Decimal`. Never floating-point.
2. **PostgreSQL `NUMERIC`**: All financial columns use `NUMERIC`, never `FLOAT` or `DOUBLE PRECISION`.
3. **Deterministic code, not LLM**: Financial calculations performed by deterministic Python code, never by LLM arithmetic.
4. **Document rounding rules**: Every calculation type documents its rounding rule explicitly.
5. **Valuation produces ranges**: Never single false-precision values. All assumptions visible in output.
6. **No fabricated data**: If data is unavailable, report unavailable. Validation rejects schema/range failures.
7. **Cross-statement consistency**: Balance sheet equation must hold. CFO derivation consistent. Net Income matches retained earnings change.
8. **Golden dataset testing**: Every calculation tested against hand-verified inputs and outputs.
9. See: ADR-003.

---

## 10. Agent Development Rules

1. **Single responsibility**: Each agent has one well-defined analytical domain.
2. **Typed state**: Agents read from and write to typed `ResearchState`.
3. **Tool-based data access**: Through typed tools, not raw API calls or direct DB queries.
4. **Evidence attachment**: Every agent finding must reference source evidence.
5. **Schema validation**: All agent inputs and outputs validated against Pydantic schemas.
6. **Timeouts**: Per-agent (60s-180s). Total run: 15 minutes. See `architecture/agent-architecture.md`.
7. **Token budgets**: Per-agent budgets (~325K total per run). See ADR-008.
8. **Conservative defaults**: Default moat = NONE. Default score = 0. Evidence required to upgrade.
9. **Quality gates**: 12 gates before publication. Failed gates → RESEARCH INCOMPLETE, not fabrication.
10. **Max 2 iterations**: Quality gate loop limited to 1 initial + 1 retry. See ADR-007.
11. **Adversarial testing**: Thesis Challenger must attempt to disprove. Every thesis includes Bear Case.
12. **Error handling**: Failed agent → mark FAILED, save partial state, continue with independent agents.
13. See: `architecture/agent-architecture.md`, ADR-001, ADR-007, ADR-008.

---

## 11. Database & Migration Rules

- **Tool**: Alembic (SQLAlchemy migration framework).
- **Zero-downtime migrations**: Column additions use `nullable=True` or `server_default`. Column removals are two-phase.
- **Rollback**: Every migration has a `downgrade()` method. Tested in CI before merge.
- **Data migrations**: Separated from schema migrations. Distinct Alembic revisions.
- **UUID primary keys**: All entities.
- **JSONB**: For flexible nested data (business segments, assumptions).
- **Partitioning**: Deferred until data volume warrants it.
- **Connection pooling**: SQLAlchemy async engine, pool_size=10, max_overflow=20, pool_timeout=30s, pool_recycle=1800s.

---

## 12. Git Workflow

- **Conventional commits**: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- **Git checkpoints**: Commit working states after major phases. Each commit is a self-contained, buildable unit.
- **Branch strategy**: Feature branches off `main`. No direct pushes to `main` after Phase 1.
- **No force pushes to main**: Ever.
- **PR required**: After Phase 1, all changes go through pull requests with CI passing.
- **No secrets committed**: Enforced by `.gitignore`. Review `git status` before committing.

---

## 13. Prohibited Shortcuts

1. **Never allow an LLM to invent financial data.** Report unavailable, don't fabricate.
2. **Never use floating-point for financial calculations.** Always `decimal.Decimal` / `NUMERIC`.
3. **Never hard-code a single data vendor.** All data access through provider interfaces.
4. **Never hard-code a single LLM provider.** All LLM access through provider interfaces.
5. **Never remove or weaken tests to make implementation pass.** Fix the implementation.
6. **Never skip type checking.** mypy strict + tsc strict must pass in CI.
7. **Never commit secrets.** No API keys, passwords, or tokens in source code.
8. **Never let retrieved documents override system instructions.** Prompt injection defense mandatory.
9. **Never produce a single-point valuation.** Always a range with visible assumptions.
10. **Never present management claims as fact.** Separate MANAGEMENT_CLAIM from FACT.
11. **Never skip quality gates.** 12 gates must pass, or output is marked INCOMPLETE.
12. **Never allow agents unlimited retries or token consumption.** Budgets enforced.

---

## Project Structure

```
backend/          — Python backend (FastAPI application)
frontend/         — TypeScript frontend (Next.js application)
architecture/     — ADRs, design documents, system diagrams
architecture/adr/ — Architecture Decision Records
docs/             — API strategy, research methodology, testing strategy, workflow
infrastructure/   — Docker, CI/CD, deployment configs
scripts/          — Development and operational scripts
tests/            — Integration/E2E tests and acceptance criteria (unit tests next to source)
```

## Key References

| Document | Path |
|----------|------|
| Solution Architecture | `architecture/solution-architecture.md` |
| Domain Model | `architecture/domain-model.md` |
| Agent Architecture | `architecture/agent-architecture.md` |
| Data Architecture | `architecture/data-architecture.md` |
| Security Architecture | `architecture/security-architecture.md` |
| Deployment Architecture | `architecture/deployment-architecture.md` |
| Research Methodology | `docs/research-methodology.md` |
| Testing Strategy | `docs/testing-strategy.md` |
| Provider Strategy | `docs/api-provider-strategy.md` |
| Development Workflow | `docs/development-workflow.md` |
| Acceptance Criteria | `tests/acceptance-criteria.md` |

## Development Commands

(To be populated as tooling is added in Phase 2)

## Project Progress Tracking

The project uses progress.md as the persistent development state.

After every implementation phase or significant task:

1. Read progress.md before starting work.
2. Update progress.md when work begins.
3. Mark completed tasks only after implementation and testing.
4. Record failed tests and unresolved issues.
5. Record important architectural decisions.
6. Record known limitations.
7. Record the current phase.
8. Record the next phase.
9. Record the latest Git commit hash when a phase is committed.

Never claim a feature is complete unless:
- implementation exists
- relevant tests pass
- acceptance criteria are satisfied

When starting a new Claude Code session:
1. Read CLAUDE.md
2. Read progress.md
3. Read implementation-plan.md
4. Inspect recent Git history
5. Inspect current git status
6. Review relevant architecture documentation
7. Then continue from the current phase

Do not restart completed work unless explicitly instructed.

## Phase Execution Workflow

### Before Starting Any Phase

1. Read CLAUDE.md.
2. Read progress.md.
3. Read implementation-plan.md.
4. Inspect git status.
5. Inspect recent git history.
6. Inspect relevant architecture and ADR documents.
7. Identify the current phase and its acceptance criteria.
8. Do not restart or reimplement completed phases unless explicitly instructed.

### After Completing Any Phase

1. Run the relevant automated tests.
2. Run linting.
3. Run type checks.
4. Verify all phase acceptance criteria.
5. Check for regressions in previously completed functionality.
6. Update progress.md.
7. Update implementation-plan.md.
8. Record new technical debt or known limitations.
9. Review git diff.
10. Verify that no secrets or API keys were added.
11. Create a Git commit for the completed phase.
12. Do not push to GitHub unless explicitly instructed.

### Phase Completion Rule

A phase is complete only when:

- implementation is complete
- acceptance criteria are satisfied
- relevant tests pass
- lint passes
- type checks pass
- documentation is updated
- progress.md is updated
- implementation-plan.md is updated
- Git commit is created

Do not automatically start the next phase after completing a phase.

Stop and report:

- implementation completed
- tests and results
- acceptance criteria status
- files changed
- technical debt
- Git commit hash
- recommended next phase