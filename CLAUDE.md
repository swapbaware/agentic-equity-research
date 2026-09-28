# CLAUDE.md — Engineering Principles

This file is the engineering constitution for the Agentic Equity Research Platform. Every commit, review, and design decision must be consistent with these principles.

## Platform Purpose

An evidence-driven Agentic Equity Research Operating System for Indian listed companies (NSE/BSE). The platform is a RESEARCH AND DECISION-SUPPORT SYSTEM, not a stock-tip generator. It must never claim a company will become a "multibagger" or manufacture certainty about future returns.

## Architecture Principles

- **Clean Architecture:** Separate concerns into layers — domain, application, infrastructure, presentation. Dependencies point inward.
- **Provider Abstraction:** Every external service (LLM, financial data, storage) is accessed through an interface. Concrete implementations are injected, never imported directly by business logic. Providers are swappable via configuration.
- **Strong Typing:** Use Pydantic models (backend) and TypeScript strict mode (frontend) everywhere. No `Any` types except at serialization boundaries. No `# type: ignore` without a comment explaining why.
- **Modular Design:** Each module must be independently testable. Prefer composition over inheritance. Keep modules small and focused.
- **Record Architectural Decisions:** Important decisions are documented in `architecture/adr/` files. Do not silently make architectural assumptions.

## Financial Data Integrity

- **Deterministic Financial Calculations:** Use `decimal.Decimal` (Python) for all monetary and financial ratio calculations. Never use floating-point arithmetic for financial data. Document rounding rules explicitly. Use PostgreSQL `NUMERIC`, never `FLOAT`.
- **No Fabricated Financial Data:** If data is unavailable, say so explicitly. Never allow an LLM to invent financial figures. Validation rejects data that fails schema or range checks.
- **Evidence-Backed AI Research:** Every AI-generated research finding must cite its source data. Agent outputs include provenance metadata. Research findings are classified as: FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, or UNCERTAINTY.
- **Separation of Concerns in Research:** Factual data, calculated metrics, management statements, external analyst opinions, AI-generated inference, assumptions, and uncertainty must never be mixed or conflated.
- **Primary Sources First:** NSE, BSE, SEBI, company annual reports, investor presentations, financial results, corporate filings, RBI, and government sources are preferred. See `docs/research-methodology.md` for source tiering.

## Code Quality

- **Production-Quality from Day One:** No "TODO: fix later" without a linked issue. No prototype code in main.
- **Test-Driven Development:** Write tests before or alongside implementation. Minimum 80% line coverage for new modules. Integration tests for every API endpoint and agent workflow. Never remove or weaken tests to make implementation pass.
- **Do Not Over-Engineer:** Build what is needed for the current phase. Do not silently expand scope for hypothetical future requirements.

## Agent Architecture

- **Structured Agent Communication:** Agents communicate through typed `ResearchState`, not arbitrary text passing.
- **Deterministic Orchestration:** LangGraph state machine with defined workflow, not emergent agent-to-agent chat.
- **LLM for Reasoning Only:** Financial calculations performed by deterministic code, never by LLM arithmetic.
- **Quality Gates:** Every research run passes 12 quality gates before publication. Failed gates produce RESEARCH INCOMPLETE, not fabricated data.
- **Adversarial Testing:** The Thesis Challenger agent must attempt to disprove the thesis. The Evidence Verification agent must identify unsupported claims. Every thesis includes a Bear Case.

## Security

- **No Hard-Coded Secrets:** API keys, database credentials, and tokens live in environment variables loaded from `.env` (never committed). Use `.env.example` as the template.
- **Validate All External Input:** Financial data from APIs, user input, and LLM outputs must be validated before use.
- **Prompt Injection Defense:** Documents retrieved from the web are untrusted input. Never allow retrieved content to redefine system instructions. Agent outputs validated against expected schemas.
- **Agent Least Privilege:** Each agent has access only to the tools it needs. No agent has unrestricted tool access.

## Git Workflow

- **Git Checkpoints:** Commit working states after major phases. Each commit should be a self-contained, buildable unit.
- **Commit Messages:** Use conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- **Branch Strategy:** Feature branches off `main`. No direct pushes to `main` after Phase 1.

## Project Structure

- `backend/` — Python backend (FastAPI application)
- `frontend/` — TypeScript frontend (Next.js application)
- `architecture/` — ADRs, design documents, system diagrams
- `architecture/adr/` — Architecture Decision Records
- `docs/` — API strategy, research methodology, testing strategy
- `infrastructure/` — Docker, CI/CD, deployment configs
- `scripts/` — Development and operational scripts
- `tests/` — Integration and end-to-end tests (unit tests live next to source)

## Key References

- Solution Architecture: `architecture/solution-architecture.md`
- Domain Model: `architecture/domain-model.md`
- Agent Architecture: `architecture/agent-architecture.md`
- Research Methodology: `docs/research-methodology.md`
- Testing Strategy: `docs/testing-strategy.md`
- Provider Strategy: `docs/api-provider-strategy.md`

## Development Commands

(To be populated as tooling is added in Phase 2)
