# Development Workflow

This document defines how development work flows through the project — from picking up a task to merging tested code. It complements CLAUDE.md (engineering rules) and the testing strategy (how to test).

---

## Phase Lifecycle

Each implementation phase follows this lifecycle:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PLAN      │────▶│   BUILD     │────▶│   VERIFY    │────▶│   SHIP      │
│             │     │             │     │             │     │             │
│ Review arch │     │ Implement   │     │ Run tests   │     │ Commit      │
│ docs        │     │ Write tests │     │ Run linters │     │ Update      │
│ Check deps  │     │ alongside   │     │ Run types   │     │ progress.md │
│ Check AC    │     │             │     │ Check AC    │     │ PR / merge  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### PLAN
1. Read the phase definition in `implementation-plan.md`
2. Read the acceptance criteria in `tests/acceptance-criteria.md`
3. Read the relevant architecture documents
4. Identify dependencies — is the preceding phase complete?
5. Identify key decisions that need to be made (documented in the phase)
6. Create a branch: `phase-{N}-{short-description}` (e.g., `phase-2-backend-foundation`)

### BUILD
1. Implement incrementally — commit working states, not big-bang deliveries
2. Write tests alongside implementation (TDD or test-alongside, never test-after)
3. Run `ruff check` and `mypy --strict` continuously
4. Follow coding standards from CLAUDE.md §4
5. Respect all prohibited shortcuts from CLAUDE.md §13

### VERIFY
1. Run the full test suite: `pytest` (backend), `vitest` (frontend)
2. Run linters: `ruff check`, `eslint`
3. Run type checkers: `mypy --strict`, `tsc --strict`
4. Check coverage meets targets (see CLAUDE.md §6)
5. Verify acceptance criteria from `tests/acceptance-criteria.md` for this phase
6. Review for security issues (no secrets, no injection, validated inputs)

### SHIP
1. Commit with conventional commit message (`feat:`, `fix:`, `test:`, etc.)
2. Update `progress.md` — mark phase tasks complete, update current phase
3. After Phase 1: create PR, request review, CI must pass
4. Merge to main
5. Tag milestone if appropriate

---

## Branching Strategy

### During Phase 0-1 (Documentation Only)
- Direct commits to `main` acceptable
- Commits are documentation and architecture only

### Phase 2 Onward (Implementation)
- Feature branches off `main`: `phase-{N}-{description}`
- Pull request required for merge to `main`
- CI pipeline must pass (lint + type check + test + coverage)
- No force pushes to `main`

### Branch Naming
```
phase-2-backend-foundation
phase-3-domain-models
phase-4-provider-framework
fix/health-check-redis-timeout
feat/bse-api-provider
refactor/calculation-engine-decimal
```

---

## Commit Conventions

### Format
```
type: short description

Optional longer description explaining WHY, not WHAT.
```

### Types
| Type | Use When |
|------|----------|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `test:` | Adding or updating tests |
| `refactor:` | Code restructuring without behavior change |
| `docs:` | Documentation only |
| `chore:` | Build, CI, dependency, tooling changes |
| `perf:` | Performance improvement |

### Rules
- Subject line < 72 characters
- Imperative mood ("add health check", not "added health check")
- Reference ADR when implementing an architectural decision
- Each commit should be a self-contained, buildable unit

---

## CI Pipeline

### On Every Push / PR

```
┌─────────────────────────────────────────────────────────────┐
│                     Parallel Jobs                           │
│                                                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ Lint       │  │ Type Check │  │ Unit Tests │            │
│  │ ruff check │  │ mypy       │  │ pytest     │            │
│  │ eslint     │  │ tsc        │  │ vitest     │            │
│  └────────────┘  └────────────┘  └──────┬─────┘            │
│                                         │                   │
│                                  ┌──────▼───────┐           │
│                                  │ Coverage     │           │
│                                  │ Report       │           │
│                                  │ (fail < 80%) │           │
│                                  └──────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### On Merge to Main (additionally)

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Integration     │  │ API Tests       │                  │
│  │ Tests           │  │ (httpx)         │                  │
│  │ (Docker DB)     │  │                 │                  │
│  └─────────────────┘  └─────────────────┘                  │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Agent Tests     │  │ Docker Build    │                  │
│  │ (mock LLM)      │  │ + Smoke Test    │                  │
│  └─────────────────┘  └─────────────────┘                  │
│                                                             │
│  ┌─────────────────┐                                        │
│  │ E2E Tests       │                                        │
│  │ (Playwright)    │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### CI Blockers (merge blocked if any fail)
- Any lint error
- Any type check error
- Any test failure
- Coverage below threshold
- Docker image build failure
- Known security vulnerabilities in dependencies

---

## Testing Workflow

### Write Tests First or Alongside
```
1. Read acceptance criteria for the feature
2. Write test that asserts the acceptance criterion
3. Run test — verify it fails (red)
4. Implement the feature
5. Run test — verify it passes (green)
6. Refactor if needed — tests still pass
```

### Test File Location
- **Unit tests**: Next to source file (`backend/app/services/calculation.py` → `backend/app/services/test_calculation.py`)
- **Integration tests**: `tests/integration/`
- **API tests**: `tests/api/`
- **Agent tests**: `tests/agent/`
- **E2E tests**: `tests/e2e/`
- **Acceptance criteria reference**: `tests/acceptance-criteria.md`

### Running Tests

Commands to be populated in Phase 2. Expected pattern:

```bash
# Unit tests
pytest backend/ -x -q

# Unit tests with coverage
pytest backend/ --cov=backend/app --cov-report=term-missing

# Integration tests (requires Docker services)
pytest tests/integration/ -x

# API tests
pytest tests/api/ -x

# Agent tests (mock LLM)
pytest tests/agent/ -x

# All backend tests
pytest

# Frontend unit tests
cd frontend && npm run test

# E2E tests
cd frontend && npm run test:e2e

# Type checking
mypy backend/ --strict
cd frontend && npx tsc --noEmit

# Linting
ruff check backend/
cd frontend && npm run lint
```

---

## Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/swapbaware/agentic-equity-research.git
cd agentic-equity-research

# 2. Copy environment template
cp .env.example .env
# Edit .env with your API keys

# 3. Start infrastructure services
docker-compose up -d db redis minio

# 4. Set up Python backend
cd backend
python -m venv .venv        # or: uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"     # or: uv pip install -e ".[dev]"

# 5. Run database migrations
alembic upgrade head

# 6. Start backend
uvicorn app.main:app --reload --port 8000

# 7. Set up frontend (separate terminal)
cd frontend
npm install
npm run dev

# 8. Access services
# Backend API: http://localhost:8000/docs
# Frontend: http://localhost:3000
# MinIO Console: http://localhost:9001
```

---

## Code Review Checklist

When reviewing code (self-review or PR review), check:

### Correctness
- [ ] Does it do what the acceptance criteria require?
- [ ] Are edge cases handled?
- [ ] Are financial values `decimal.Decimal`, never `float`?

### Security
- [ ] No hardcoded secrets?
- [ ] External input validated?
- [ ] Prompt injection defenses in place for agent-processed content?
- [ ] No secrets in logs?

### Testing
- [ ] Tests written for new functionality?
- [ ] Tests use exact `Decimal` comparisons for financial values?
- [ ] No network calls in unit tests?
- [ ] Coverage meets targets?

### Architecture
- [ ] Provider abstraction maintained? (no direct imports of concrete providers)
- [ ] Domain logic free of infrastructure concerns?
- [ ] Agent outputs validated against Pydantic schemas?

### Code Quality
- [ ] `ruff check` passes?
- [ ] `mypy --strict` passes?
- [ ] No unnecessary comments?
- [ ] No over-engineering?

---

## Handling Failures

### Test Failure
1. Read the test — understand what it expects
2. Read the implementation — understand what it does
3. Fix the **implementation**, not the test
4. If the test is genuinely wrong (spec changed, not a bug): update the test AND update `tests/acceptance-criteria.md`

### CI Pipeline Failure
1. Read the failure log
2. Reproduce locally
3. Fix and push — do not skip checks (`--no-verify` is prohibited)

### Architecture Conflict
1. If implementation reveals the architecture is wrong, update the architecture document
2. Create or update an ADR if the decision is significant
3. Update `progress.md` with the decision

---

## Progress Tracking

### After Every Work Session
1. Update `progress.md`:
   - Check off completed tasks
   - Update "Current Phase" section
   - Add any new known issues
   - Update "Next Actions"
2. Commit progress.md changes

### After Phase Completion
1. Mark phase COMPLETE in `progress.md` and `implementation-plan.md`
2. Update "Current Phase" to the next phase
3. Review and update known issues
4. Review and update technical debt

---

## Key File Locations

| File | Purpose | Update When |
|------|---------|-------------|
| `CLAUDE.md` | Engineering rules | Rules change or are clarified |
| `progress.md` | Current state tracker | Every work session |
| `implementation-plan.md` | Phase roadmap with acceptance criteria | Phase definition changes |
| `tests/acceptance-criteria.md` | Definition of done per feature | New features defined or criteria refined |
| `docs/development-workflow.md` | This file — how work flows | Process changes |
| `architecture/adr/*.md` | Decision records | New architectural decisions |
