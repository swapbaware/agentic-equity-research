# CLAUDE.md — Engineering Principles

This file is the engineering constitution for the Agentic Equity Research Platform. Every commit, review, and design decision must be consistent with these principles.

## Architecture Principles

- **Clean Architecture:** Separate concerns into layers — domain, application, infrastructure, presentation. Dependencies point inward.
- **Provider Abstraction:** Every external service (LLM, financial data, storage) is accessed through an interface. Concrete implementations are injected, never imported directly by business logic.
- **Strong Typing:** Use Pydantic models (backend) and TypeScript strict mode (frontend) everywhere. No `Any` types except at serialization boundaries. No `# type: ignore` without a comment explaining why.
- **Modular Design:** Each module must be independently testable. Prefer composition over inheritance. Keep modules small and focused.

## Code Quality

- **Production-Quality from Day One:** No "TODO: fix later" without a linked issue. No prototype code in main.
- **Test-Driven Development:** Write tests before or alongside implementation. Minimum 80% line coverage for new modules. Integration tests for every API endpoint and agent workflow.
- **Deterministic Financial Calculations:** Use `decimal.Decimal` (Python) for all monetary and financial ratio calculations. Never use floating-point arithmetic for financial data. Document rounding rules explicitly.
- **Evidence-Backed AI Research:** Every AI-generated research finding must cite its source data. Agent outputs include provenance metadata. Never fabricate financial data — if data is unavailable, say so explicitly.

## Security

- **No Hard-Coded Secrets:** API keys, database credentials, and tokens live in environment variables loaded from `.env` (never committed). Use `.env.example` as the template.
- **Validate All External Input:** Financial data from APIs, user input, and LLM outputs must be validated before use.

## Git Workflow

- **Git Checkpoints:** Commit working states frequently. Each commit should be a self-contained, buildable unit.
- **Commit Messages:** Use conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- **Branch Strategy:** Feature branches off `main`. No direct pushes to `main` after Phase 0.

## Project Structure

- `backend/` — Python backend (FastAPI application)
- `frontend/` — TypeScript frontend (Next.js application)
- `architecture/` — ADRs, design documents, system diagrams
- `docs/` — User-facing documentation
- `infrastructure/` — Docker, CI/CD, deployment configs
- `scripts/` — Development and operational scripts
- `tests/` — Integration and end-to-end tests (unit tests live next to source in `backend/` and `frontend/`)

## Development Commands

(To be populated as tooling is added in Phase 1)
