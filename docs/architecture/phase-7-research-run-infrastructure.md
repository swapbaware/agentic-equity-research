# Phase 7: Research Run Infrastructure — Architecture Proposal

**Status**: PROPOSAL — Reconciliation Applied, Pending Final Review
**Date**: 2026-09-29
**Author**: Architecture Review (automated)
**Supersedes**: None (new document)
**Related**: ADR-001 (LangGraph), ADR-004 (Evidence Citations), ADR-005 (Provider Abstraction), ADR-007 (Failure Modes), ADR-008 (Cost Controls)

---

## 1. Objective

Design the persistent Research Run Infrastructure that becomes the system-of-record for all agentic equity research. Every research execution, agent finding, evidence linkage, thesis version, and artifact produced by the 17-agent pipeline must be durably recorded with full provenance, temporal integrity, and audit trail.

This infrastructure is the persistence and domain layer that individual agents (Phases 8–18) write into and LangGraph orchestration (Phase 19) coordinates across. It must be independently testable, LangGraph-compatible without LangGraph-coupled, and ready for incremental agent onboarding.

## 2. Scope

### In Scope
- Domain models for research run lifecycle (ResearchRun, ResearchRunStep, AgentExecution)
- Domain models for research outputs (ResearchFinding, ResearchArtifact, ResearchSource)
- ThesisVersion evolution and evidence graph persistence
- State machines for ResearchRun and AgentExecution lifecycles
- Retry, idempotency, and failure/resume semantics
- Temporal integrity (point-in-time fields on all relevant entities)
- Reproducibility metadata capture
- Database schema, indexing, and migration strategy
- Repository pattern for persistence access
- API boundary definition (interfaces only, not implementation)
- Testing strategy and acceptance criteria

### Out of Scope (deferred to later phases)
- LangGraph graph definition or orchestration code (Phase 19)
- Agent business logic or prompt engineering (Phases 8–18)
- REST/WebSocket API endpoint implementation (Phase 20)
- FinOps dashboards or cost analytics UI (Phase 22+)
- Security hardening beyond architectural boundaries (Phase 24)
- Background task processor selection (ADR-002, pending)

## 3. Non-Goals

Phase 7 does NOT implement any of the following:

- **Byte-level LLM reproducibility**: LLM outputs are inherently non-deterministic. We capture reproducibility metadata (model, temperature, prompt version, tool versions) for auditability, not replay.
- **Investment recommendation model**: The platform produces research, not recommendations. No entity represents a buy/sell/hold signal.
- **Buy/sell recommendations or investment advice**: The platform is a research system, not a recommendation engine.
- **Trust scores on sources**: Sources have a `SourceTier` (Tier 1/2/3) as established in the existing model. We do NOT add numeric trust scores — tier classification is sufficient.
- **FinOps dashboards**: Cost/token fields are captured on AgentExecution for future use; no dashboard or alerting is built in Phase 7.
- **Endpoint implementation**: API boundary is defined as Protocol interfaces. HTTP handlers are Phase 20.
- **LangGraph orchestration**: LangGraph is Phase 19. Phase 7 has zero LangGraph imports.
- **LLM providers**: No LLM provider code or imports. Provider resolution is runtime via ADR-005.
- **Research agents**: Agent business logic is Phases 8–18.
- **Background worker selection**: The service layer is processor-agnostic. Worker choice is deferred to ADR-002.
- **Research UI**: Frontend is Phase 20+.
- **Monitoring / Watchlist**: Phase 22.
- **Portfolio recommendations**: Not in scope for any phase — the platform produces research, not advice.
- **Advanced evaluation framework**: Phase 23.
- **Security hardening**: Phase 24. Phase 7 defines correct architectural boundaries only.

## 4. Existing Architecture Reused

### 4.1 Entities Retained As-Is

| Entity | Location | Rationale |
|--------|----------|-----------|
| `Source` | `models/evidence.py:19-48` | Fully adequate. Has name, type, url, default_tier, is_active, timestamps. |
| `ResearchDocument` | `models/research.py:47-98` | Mature. Has company_id, document_type, source_tier, content_hash, storage_path, metadata. |
| `DocumentVersion` | `models/evidence.py:51-77` | Adequate for document versioning. |
| `Evidence` | `models/research.py:100-132` | Sound. Has document_id, evidence_type, claim, context, page_or_section, confidence. |
| `InvestmentThesis` | `models/thesis.py:88-128` | Mature. FK to research_run, version field, structured summaries, bear/bull cases. |
| `Risk` | `models/thesis.py:169-203` | Adequate. Has evidence junction table. |
| `Catalyst` | `models/thesis.py:206-236` | Adequate. Has evidence junction table. |
| `CompanyScore` | `models/thesis.py:239-271` | Adequate. Unique constraint on (company_id, research_run_id, dimension). |
| `ValuationModel` | `models/valuation.py` | Adequate. FK to research_run. |
| `Scenario` | `models/valuation.py` | Adequate. FK to research_run. |
| `MoatAssessment` | `models/analysis.py` | Adequate. FK to research_run. |

### 4.2 Entities to Evolve

| Entity | Current State | Required Evolution |
|--------|--------------|-------------------|
| `ResearchRun` | `models/research.py:178-221` | Expand status enum. Add temporal fields. Replace JSONB agent_execution_log with proper AgentExecution table. Add reproducibility metadata. Add run_type, trigger_type. |
| `ResearchFinding` | `models/research.py:223-256` | Add temporal integrity fields (observation_date, source_publication_date). Add calculation_version for CALCULATION findings. Add supersedes_finding_id for finding chains. |
| `ThesisVersion` | `models/thesis.py:131-166` | Add snapshot_data (JSONB) for point-in-time thesis state. Add research_run_id FK. |
| `ResearchRunStatus` enum | `models/enums.py` | Add CREATED, QUEUED, CANCELLED, PARTIAL states. Remove INCOMPLETE (subsumed by PARTIAL). See §7.1 state machine. |
| `Claim` / `ClaimEvidence` | `models/evidence.py:80-147` | **Preserved as-is in Phase 7.** Claim and ClaimEvidence are actively used across repositories, services, APIs, schemas, and tests (10 files). Long-term consolidation with ResearchFinding is a deferred decision. See §24. |

### 4.3 Entities to Create (New)

| Entity | Rationale |
|--------|-----------|
| `ResearchRunStep` | Tracks workflow step execution (which agents ran in what order, with what inputs). Currently no structured step tracking exists. |
| `AgentExecution` | Replaces `ResearchRun.agent_execution_log` (JSONB blob) with a proper relational audit table. Each agent invocation is an immutable record with tokens, cost, latency, status, model used, prompt version. |
| `ResearchArtifact` | Stores generated artifacts (reports, charts, intermediate analyses) with content hash and storage path. Currently no artifact tracking exists beyond findings. |

## 5. Domain Model

### 5.1 Entity Definitions

#### ResearchRun (evolve existing)

The root aggregate for a single research execution against one company.

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| id | UUID PK | existing | |
| company_id | FK → Company | existing | Target company |
| initiated_by | String(200) | existing | User ID or system trigger |
| run_type | String(50) | **new** | FULL, INCREMENTAL, THESIS_UPDATE, MONITORING |
| trigger_type | String(50) | **new** | USER_INITIATED, SCHEDULED, EVENT_TRIGGERED, RERUN |
| parent_run_id | FK → ResearchRun (nullable) | **new** | Links reruns/incremental runs to original |
| started_at | DateTime(tz) | existing | |
| completed_at | DateTime(tz, nullable) | existing | |
| status | ResearchRunStatus | existing (evolve enum) | See state machine §7.1 |
| observation_date | Date | **new** | The "as-of" date for this research (typically today) |
| configuration | JSONB | **new** | Frozen run configuration (agent list, model assignments, token budgets, feature flags) |
| quality_gate_results | JSONB | existing | Gate pass/fail map |
| research_completeness | Numeric(5,2) | existing | 0.00–100.00 |
| total_input_tokens | BigInteger | existing | |
| total_output_tokens | BigInteger | existing | |
| total_cost_usd | Numeric(10,4) | existing | |
| error_summary | Text (nullable) | **new** | Human-readable summary if FAILED/PARTIAL |
| created_at | DateTime(tz) | via TimestampMixin | |
| updated_at | DateTime(tz) | via TimestampMixin | |

**Deprecated fields** (legacy, retained for backward compatibility):
- `agent_execution_log` (JSONB) — superseded by `AgentExecution` table. New code must NOT read or write this field. Removal requires explicit dependency verification (see §20.1 Migration 3).
- `data_sources_used` (JSONB) — superseded by `ResearchRunSource` table. Same removal policy.
- `cost_by_agent` (JSONB) — derivable from `AgentExecution.cost_usd`. Same removal policy.

**Deprecation lifecycle**:
- **Phase 7**: AgentExecution becomes canonical. New business logic must not depend on `agent_execution_log`.
- **Phases 8–18**: AgentExecution used for all execution history. Legacy JSONB fields retained only for backward compatibility.
- **Phase 19**: Verify no remaining consumers of deprecated JSONB fields.
- **Post-verification**: Remove deprecated columns through a dedicated migration. Removal is NOT automatic upon Phase 19 completion — it requires explicit dependency verification and a separate architecture decision.

**Relationships**:
- `steps` → ResearchRunStep (cascade all, delete-orphan)
- `agent_executions` → AgentExecution (cascade all, delete-orphan)
- `findings` → ResearchFinding (existing, cascade all, delete-orphan)
- `artifacts` → ResearchArtifact (cascade all, delete-orphan)

#### ResearchRunStep (new)

Represents a discrete step in the research workflow. Steps are ordered and track which agents participate.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| research_run_id | FK → ResearchRun (CASCADE) | Parent run |
| step_name | String(100) | e.g. "financial_analysis", "moat_assessment", "quality_gate_check" |
| step_order | Integer | Execution order (parallel steps share the same order number) |
| step_type | String(50) | AGENT, QUALITY_GATE, CALCULATION, AGGREGATION |
| status | StepStatus enum | PENDING, RUNNING, COMPLETED, FAILED, SKIPPED |
| started_at | DateTime(tz, nullable) | |
| completed_at | DateTime(tz, nullable) | |
| error_message | Text (nullable) | |
| input_state_hash | String(64, nullable) | SHA-256 of input state slice (for reproducibility) |
| output_state_hash | String(64, nullable) | SHA-256 of output state slice |
| created_at | DateTime(tz) | via TimestampMixin |

**Relationships**:
- `research_run` → ResearchRun
- `agent_executions` → AgentExecution (steps may have multiple agent executions for retries)

#### AgentExecution (new)

Immutable audit record of a single agent invocation. Replaces the JSONB `agent_execution_log` blob.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| research_run_id | FK → ResearchRun (CASCADE) | |
| step_id | FK → ResearchRunStep (CASCADE, nullable) | Parent step |
| agent_name | String(100) | e.g. "financial_analysis_agent" |
| attempt_number | Integer | 1 for first attempt, 2+ for retries |
| status | AgentExecutionStatus enum | RUNNING, COMPLETED, FAILED, TIMEOUT, TRUNCATED |
| started_at | DateTime(tz) | |
| completed_at | DateTime(tz, nullable) | |
| duration_ms | Integer (nullable) | Wall-clock duration |
| input_tokens | BigInteger | |
| output_tokens | BigInteger | |
| cost_usd | Numeric(10,6) | Per-execution cost |
| model_provider | String(50) | e.g. "anthropic", "openai" |
| model_name | String(100) | e.g. "claude-sonnet-5", "gpt-4o" |
| model_config | JSONB | temperature, max_tokens, top_p, etc. |
| prompt_version | String(50, nullable) | Version tag/hash of the prompt template used |
| tool_versions | JSONB (nullable) | Versions of deterministic tools invoked |
| error_message | Text (nullable) | |
| error_type | String(100, nullable) | Error classification (TIMEOUT, RATE_LIMIT, PROVIDER_ERROR, etc.) |
| findings_produced | Integer | Count of ResearchFindings created by this execution |
| created_at | DateTime(tz) | via TimestampMixin |

**Immutability**: AgentExecution records are append-only. Retries create new records with incremented `attempt_number`, never update previous attempts.

**Relationships**:
- `research_run` → ResearchRun
- `step` → ResearchRunStep
- `findings` → ResearchFinding (via finding.agent_execution_id)

#### ResearchFinding (evolve existing)

An individual finding produced by an agent. Immutable once created.

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| id | UUID PK | existing | |
| research_run_id | FK → ResearchRun | existing | |
| agent_execution_id | FK → AgentExecution (nullable) | **new** | Which execution produced this finding |
| agent_name | String(100) | existing | Denormalized for query convenience |
| finding_type | FindingType enum | existing | FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, UNCERTAINTY |
| category | String(100) | existing | |
| content | Text | existing | |
| confidence | ConfidenceLevel | existing | HIGH, MEDIUM, LOW |
| observation_date | Date (nullable) | **new** | When the underlying fact was observed/true |
| source_publication_date | Date (nullable) | **new** | When the source was published |
| calculation_version | String(50, nullable) | **new** | Version of calculation engine, for CALCULATION type |
| supersedes_finding_id | FK → ResearchFinding (nullable) | **new** | Links to finding this one supersedes (for thesis updates) |
| created_at | DateTime(tz) | existing | |

**Existing relationship preserved**: `evidences` → Evidence (via `research_finding_evidence` junction table)
**New relationship**: `agent_execution` → AgentExecution

#### ResearchArtifact (new)

A generated artifact from a research run — reports, intermediate analyses, chart data, calculation results.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| research_run_id | FK → ResearchRun (CASCADE) | |
| agent_execution_id | FK → AgentExecution (nullable) | Which execution produced this |
| artifact_type | ArtifactType enum | REPORT, ANALYSIS, CHART_DATA, CALCULATION_RESULT, INTERMEDIATE_STATE |
| title | String(500) | |
| content_type | String(100) | MIME type (application/json, text/markdown, etc.) |
| content_hash | String(64) | SHA-256 for dedup and integrity |
| storage_path | String(1000, nullable) | S3 path for large artifacts |
| inline_content | JSONB (nullable) | For small artifacts stored inline |
| metadata | JSONB (nullable) | Artifact-specific metadata |
| created_at | DateTime(tz) | via TimestampMixin |

**Design choice**: Small artifacts (< 64KB, e.g., calculation results, JSON analyses) are stored inline in `inline_content`. Large artifacts (reports, full analyses) go to S3 with `storage_path`. The `content_hash` is always computed regardless of storage location.

#### ResearchSource (view / query concept, not a new table)

The user's requirements specified `ResearchSource` as an entity. After analysis, the existing `Source` + `ResearchDocument` + `Evidence` chain already provides this capability:

```
Source (identity) → ResearchDocument (document instance) → Evidence (extracted claim)
                                                         ↗
                                          ResearchFinding (agent output)
```

Rather than creating a redundant `ResearchSource` table, we define a **ResearchRunSource** junction table that tracks which sources were actually consulted during a research run:

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| research_run_id | FK → ResearchRun (CASCADE) | |
| document_id | FK → ResearchDocument | |
| accessed_at | DateTime(tz) | When the document was accessed during this run |
| access_type | String(50) | FULL_READ, SEMANTIC_SEARCH, METADATA_ONLY |

This replaces the removed `data_sources_used` JSONB field with proper relational tracking.

#### ThesisVersion (evolve existing)

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| id | UUID PK | existing | |
| company_id | FK → Company | existing | |
| thesis_id | FK → InvestmentThesis | existing | Current thesis |
| previous_thesis_id | FK → InvestmentThesis (nullable) | existing | Previous thesis |
| research_run_id | FK → ResearchRun (nullable) | **new** | Which run triggered this version |
| change_summary | Text | existing | |
| change_trigger | String(500) | existing | |
| snapshot_data | JSONB (nullable) | **new** | Frozen thesis state at version time |
| key_changes | JSONB (nullable) | **new** | Structured diff of what changed (scores, confidence, bear/bull) |
| created_at | DateTime(tz) | existing | |

### 5.2 New Enumerations

```python
class ResearchRunStatus(str, Enum):
    CREATED = "CREATED"          # new: run record exists, not yet queued
    QUEUED = "QUEUED"            # new: waiting for execution slot
    RUNNING = "RUNNING"          # existing: agents executing
    COMPLETED = "COMPLETED"      # existing: all gates passed
    FAILED = "FAILED"            # run terminated unsuccessfully without producing a complete usable research result
    CANCELLED = "CANCELLED"      # new: explicitly cancelled by user
    PARTIAL = "PARTIAL"          # run contains usable completed work/findings but did not complete all required steps

class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class AgentExecutionStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    TRUNCATED = "TRUNCATED"      # token budget hit, partial output produced

class ArtifactType(str, Enum):
    REPORT = "REPORT"
    ANALYSIS = "ANALYSIS"
    CHART_DATA = "CHART_DATA"
    CALCULATION_RESULT = "CALCULATION_RESULT"
    INTERMEDIATE_STATE = "INTERMEDIATE_STATE"
```

## 6. Entity Relationships

```
                        ┌──────────────────┐
                        │    Company        │
                        └────────┬─────────┘
                                 │ 1:N
                        ┌────────▼─────────┐
                        │  ResearchRun      │◄──── parent_run_id (self-ref)
                        └──┬──┬──┬──┬──┬───┘
                           │  │  │  │  │
          ┌────────────────┘  │  │  │  └────────────────┐
          │                   │  │  │                    │
    ┌─────▼──────┐  ┌────────▼──▼───────┐  ┌───────────▼──────────┐
    │ Research    │  │  AgentExecution    │  │  ResearchRunSource   │
    │ RunStep     │  │  (immutable audit) │  │  (documents used)    │
    └─────┬──────┘  └────────┬──────────┘  └──────────────────────┘
          │                  │
          │ N:1              │ 1:N
          │                  │
          │         ┌────────▼──────────┐
          │         │ ResearchFinding    │◄──── supersedes_finding_id (self-ref)
          │         │ (immutable)        │
          │         └────┬─────┬────────┘
          │              │     │
          │     M:N      │     │  1:N
          │  (junction)  │     │
          │         ┌────▼──┐  │  ┌──────────────────┐
          │         │Evidence│  └──▶ ResearchArtifact │
          │         └───┬───┘     └──────────────────┘
          │             │
          │        ┌────▼────────────┐
          │        │ResearchDocument  │
          │        └────┬────────────┘
          │             │
          │        ┌────▼────┐
          │        │ Source   │
          │        └─────────┘
          │
    ┌─────▼───────────────┐
    │ InvestmentThesis     │◄─── ThesisVersion (linked list)
    │ Risk, Catalyst       │
    │ CompanyScore         │
    │ ValuationModel       │
    │ MoatAssessment       │
    └─────────────────────┘
```

### Evidence Graph

#### Core Provenance Chain

```
Source → ResearchDocument → Evidence → ResearchFinding → InvestmentThesis
                                    ↗                  ↘
                   ResearchFinding (M:N junction)       ThesisVersion
```

The chain `Source → Document → Evidence → Finding → Thesis` is the platform's provenance backbone. Every factual claim in a thesis is traceable through this chain to a source document.

#### Finding Relationships

```
ResearchFinding
  ├── supporting evidence    (via research_finding_evidence junction, M:N)
  ├── contradictory evidence (via supersedes_finding_id chain — newer finding
  │                           contradicts or updates an older finding)
  └── calculations           (via finding_type = CALCULATION + calculation_version)
```

Contradictory findings are NOT collapsed into a single confidence score. Both the original and contradicting findings persist (immutability). The `supersedes_finding_id` chain makes the contradiction explicit and queryable.

#### Thesis Relationships

```
InvestmentThesis
  ├── supporting findings    (via ResearchRun → ResearchFinding)
  ├── contradictory findings (via supersedes_finding_id chains within findings)
  ├── assumptions            (via findings with finding_type = ASSUMPTION)
  ├── valuation context      (via ValuationModel / Scenario linked to same ResearchRun)
  └── risk context           (via Risk / Catalyst linked to same ResearchRun)
```

## 7. Lifecycle & State Machines

### 7.1 ResearchRun State Machine

```
                    ┌──────────┐
     create()       │ CREATED  │
    ─────────────►  └────┬─────┘
                         │ enqueue()
                    ┌────▼─────┐
                    │ QUEUED   ├──────── cancel() ──┐
                    └────┬─────┘                    │
                         │ start()                  │
                    ┌────▼─────┐                    │
                    │ RUNNING  │                    │
                    └──┬──┬──┬──┬──┘                │
                       │  │  │  │                   │
          complete()   │  │  │  │ cancel()          │
                       │  │  │  │                   │
              ┌────────▼┐ │  │ ┌▼──────────┐        │
              │COMPLETED│ │  │ │ CANCELLED  │◄──────┘
              └─────────┘ │  │ └────────────┘
                          │  │
                  fail()  │  │ partial()
                          │  │
                 ┌────────▼┐ ┌▼──────────┐
                 │ FAILED  │ │  PARTIAL   │
                 └─────────┘ └────────────┘
```

**Transition rules**:
- CREATED → QUEUED: Only via `enqueue()`. Validates company exists, no concurrent run (Redis advisory lock).
- QUEUED → RUNNING: Only via `start()`. Acquires execution slot.
- QUEUED → CANCELLED: User-initiated cancellation before execution begins.
- RUNNING → COMPLETED: All quality gates pass. Full research result produced.
- RUNNING → FAILED: The run terminated unsuccessfully without producing a complete usable research result (unrecoverable error, db failure, configuration error).
- RUNNING → PARTIAL: The run contains usable completed work/findings but did not complete all required research steps. This includes: quality gates failing after max 2 iterations (ADR-007), timeout at 15 minutes, some agents completing while others failed, or explicit partial save.
- RUNNING → CANCELLED: User-initiated cancellation. Partial results are saved but the run is marked as explicitly stopped by the user.
- Terminal states: COMPLETED, FAILED, PARTIAL, CANCELLED. No transitions out of terminal states.

**FAILED vs PARTIAL distinction**:
- **FAILED**: No usable research output. The run terminated before producing meaningful findings (e.g., database failure during initialization, configuration error, no agents completed).
- **PARTIAL**: Usable but incomplete research output. Some agents completed and produced findings, but the run did not reach COMPLETED (e.g., some agents failed, quality gates failed after retries, timeout with partial results).

### 7.2 AgentExecution State Machine

```
     create()        ┌─────────┐
    ──────────────►   │ RUNNING │
                      └──┬──┬──┘
                         │  │
            complete()   │  │  fail() / timeout()
                         │  │
                  ┌──────▼┐ ┌▼─────────┐
                  │COMPLETED│ │ FAILED   │
                  └────────┘ └──────────┘
                  ┌─────────┐ ┌──────────┐
                  │TRUNCATED│ │ TIMEOUT  │
                  └─────────┘ └──────────┘
```

**TRUNCATED**: Agent hit its token budget. Partial output produced and saved. The run continues — truncation is a degraded success, not a failure.

**Retry semantics**: A retry creates a NEW AgentExecution record with `attempt_number = previous + 1`. The previous attempt's record is preserved (immutable audit trail). Max retries per agent: 3 (ADR-007).

### 7.3 ResearchRunStep State Machine

```
     create()       ┌─────────┐
    ──────────────►  │ PENDING │
                     └────┬────┘
                          │ start()
                     ┌────▼────┐
                     │ RUNNING │
                     └──┬──┬───┘
                        │  │
           complete()   │  │ fail()
                        │  │
                 ┌──────▼┐ ┌▼──────┐
                 │COMPLETED│ │FAILED │
                 └────────┘ └───────┘

    SKIPPED: entered if step's dependencies cannot be met
             (e.g., agent depends on a failed predecessor)
```

**Step retry semantics**: A step retry (e.g., triggered by a quality gate failure loop) creates a new `AgentExecution` record while the logical `ResearchRunStep` remains the same unit of work. The step's status resets to RUNNING, and the new AgentExecution has an incremented `attempt_number`. All previous AgentExecution records for that step are preserved as immutable audit records. The step itself tracks which execution was successful; the execution history is the append-only log.

## 8. Evidence Graph Design

### 8.1 Provenance Chain

Every research output maintains a chain to its source:

```
InvestmentThesis
  └─ produced by ResearchRun (research_run_id)
       └─ contains ResearchFindings
            └─ each finding has finding_type classification
            └─ FACT findings linked to Evidence (M:N junction)
                 └─ Evidence linked to ResearchDocument
                      └─ Document linked to Source
                           └─ Source has SourceTier (1/2/3)
```

### 8.2 Finding Classification Rules (from CLAUDE.md §8)

| Type | Description | Evidence Required | Source Tier |
|------|-------------|-------------------|-------------|
| FACT | Verified factual claim | At least 1 Evidence record | Tier 1 for financial data |
| CALCULATION | Deterministic computation result | Inputs must be FACTs | N/A (derived) |
| MANAGEMENT_CLAIM | Statement by company management | Evidence from transcript/filing | Tier 1 |
| ANALYST_OPINION | External analyst's view | Evidence from research report | Tier 2/3 |
| AI_INFERENCE | LLM-generated analytical insight | None required | N/A |
| ASSUMPTION | Explicitly stated assumption | None required | N/A |
| UNCERTAINTY | Known unknowns | None required | N/A |

### 8.3 Quality Gate Integration

Quality Gate #11 (Citation Completeness) queries the evidence graph:
```sql
-- Findings of type FACT without evidence linkage → gate failure
SELECT f.id, f.content
FROM research_finding f
LEFT JOIN research_finding_evidence rfe ON rfe.research_finding_id = f.id
WHERE f.research_run_id = :run_id
  AND f.finding_type = 'FACT'
  AND rfe.evidence_id IS NULL;
```

## 9. Versioning Strategy

### 9.1 Thesis Versioning

Thesis changes create new `ThesisVersion` records forming a linked list:

```
ThesisVersion(v3) → ThesisVersion(v2) → ThesisVersion(v1)
    │                    │                    │
    thesis_id ──►        thesis_id ──►        thesis_id ──►
    (current thesis)     (prev thesis)        (original)
```

Each ThesisVersion captures:
- `snapshot_data`: Frozen state of the thesis at that point (JSONB)
- `key_changes`: Structured diff of what changed
- `change_trigger`: What caused the update
- `research_run_id`: Which run produced this version

### 9.2 Finding Supersession

When a newer finding contradicts or updates a prior finding:
```
Finding(new, supersedes_finding_id=old.id) → Finding(old)
```

The old finding is NOT deleted (immutability). The `supersedes_finding_id` chain makes it queryable which findings are "current" for a given company.

### 9.3 Entity Immutability Model

| Entity | Immutability | Rationale |
|--------|-------------|-----------|
| ResearchRun | Mutable operational state; append-only execution history | Lifecycle state (status, timestamps, quality gates) mutates. Execution history (steps, agent executions) is append-only — never delete or overwrite previous execution records. |
| ResearchRunStep | Mutable lifecycle state; execution attempts preserved | Step status and timestamps mutate during execution. All AgentExecution attempts for the step are preserved as immutable audit records. |
| AgentExecution | **Immutable** audit record | Once created, never modified. Retries create new records with incremented attempt_number. |
| ResearchFinding | **Immutable** / versioned research output | Once created, never modified. Updates/contradictions use supersedes_finding_id chain. |
| ResearchArtifact | **Immutable** content reference | Content hash ensures integrity. Once stored, not modified. |
| ThesisVersion | **Immutable** per version | Each version is a frozen snapshot of thesis state. |
| Source | Stable identity; controlled metadata updates | Source identity (name, type, url) is stable. Operational metadata (is_active, default_tier) may be updated. |
| Evidence | Immutable identity; metadata can update | Document reference and claim are fixed; confidence may be reassessed |
| InvestmentThesis | Mutable (version field increments) | Active thesis evolves; ThesisVersion preserves history |
| ResearchDocument | Mutable (embedding_id, metadata) | Document metadata may be enriched post-ingestion |

## 10. Retry, Resume & Idempotency

Three distinct concepts govern re-execution. They must not be conflated.

### 10.1 Agent Retry (within a single ResearchRun)

A failed agent is retried within the **same** ResearchRun. Every retry creates a NEW AgentExecution record — the previous attempt is preserved as an immutable audit record.

```
ResearchRun A
    └── ResearchRunStep: financial_analysis
          ├── AgentExecution(id=uuid1, attempt_number=1, status=FAILED)
          ├── AgentExecution(id=uuid2, attempt_number=2, status=FAILED)
          └── AgentExecution(id=uuid3, attempt_number=3, status=COMPLETED)
```

- Each retry creates a NEW AgentExecution record (new UUID, incremented attempt_number)
- Previous attempts are preserved (immutable audit)
- Max 3 attempts per agent (ADR-007)
- Exponential backoff between attempts (managed by orchestrator, not stored in Phase 7)
- Findings from a failed attempt are NOT promoted — only findings from the successful execution are linked to the run
- The ResearchRunStep's status resets to RUNNING on retry, updates to COMPLETED/FAILED on final outcome

### 10.2 Research Resume (new ResearchRun with parent linkage)

A partially completed research run (PARTIAL or FAILED) may be resumed through a **NEW** ResearchRun linked to the original via `parent_run_id`.

```
ResearchRun A (status: PARTIAL)
    ├── completed steps with findings
    ├── completed findings (preserved)
    └── failed or unfinished step

Resume creates:
ResearchRun B (parent_run_id = A.id, run_type = INCREMENTAL, trigger_type = RERUN)
    └── new steps, new agent executions, new findings
```

- ResearchRun A is NOT modified. Its status remains PARTIAL/FAILED.
- ResearchRun B is an independent run with its own UUID, steps, executions, and findings.
- The orchestrator (Phase 19) reads the parent run's step/execution state to determine which steps to skip. This is an orchestration concern — Phase 7 provides the `parent_run_id` linkage.
- ResearchRun B may reuse valid prior results from A where explicitly allowed by the orchestrator, but all execution history remains append-only.

### 10.3 New Research Run (independent)

A completely new research request creates an independent ResearchRun with no parent linkage.

```
ResearchRun C (parent_run_id = NULL, run_type = FULL, trigger_type = USER_INITIATED)
    └── full independent execution
```

No relationship to any prior run unless explicitly requested via `parent_run_id`.

### 10.4 Concurrent Run Prevention

Redis advisory lock `research_run:{company_id}` prevents concurrent runs for the same company (ADR-007). The lock is acquired in QUEUED state and released when the run reaches a terminal state. Different companies can run concurrently (capped by `active_research_runs` gauge, default max 5).

## 11. Failure & Resume

### 11.1 Failure Modes (per ADR-007)

| Failure | ResearchRun Status | Recovery |
|---------|-------------------|----------|
| Single agent fails after 3 retries | Continues if independent | Mark agent step FAILED, continue with remaining agents |
| LLM provider down | PARTIAL | Resume via new run with parent_run_id (§10.2) |
| Database failure | FAILED | No resume — investigate infrastructure |
| Quality gates fail after 2 iterations | PARTIAL | Manual rerun; partial results preserved |
| Total timeout (15 min) | PARTIAL | Partial results saved; manual rerun |
| User cancellation | CANCELLED | Partial results saved |
| No agents completed before failure | FAILED | No usable output; manual rerun from scratch |

### 11.2 Resume Strategy

A PARTIAL or FAILED run can be resumed by creating a new run (see §10.2 Research Resume). The orchestrator (Phase 19) reads the parent run's step/execution state to determine which steps to skip. This is an orchestration concern, not a persistence concern — Phase 7 provides the `parent_run_id` data model to make resume decisions.

### 11.3 Partial State Preservation

After each agent completes, its findings and execution record are committed to the database. If the run fails mid-execution:
- All completed agent findings are preserved
- All AgentExecution records (including failed attempts) are preserved
- The ResearchRun record shows which steps completed (via ResearchRunStep status)
- No finding or evidence is lost

## 12. Temporal Integrity

### 12.1 Point-in-Time Fields

Every research output must be interpretable in its temporal context. The platform tracks distinct time dimensions that must not be collapsed into a single `created_at`:

| Time Dimension | Entity.Field | Purpose |
|----------------|-------------|---------|
| Financial period end | FinancialStatement.`period_end` | Which financial period the data covers (e.g., FY2026 Q2 ending 2026-09-30) |
| Observation date | ResearchRun.`observation_date` | The "as-of" date for this research — what date the research considers "today" |
| Source publication date | ResearchFinding.`source_publication_date` / ResearchDocument.`document_date` | When the source document was published |
| Information availability date | ResearchFinding.`observation_date` | When the underlying fact was observable/true (may differ from publication date) |
| Source retrieval date | ResearchRunSource.`accessed_at` / Evidence.`extracted_at` | When the source document was actually accessed/retrieved during the run |
| Research execution timestamps | ResearchRun.`started_at` / `completed_at`, AgentExecution.`started_at` / `completed_at` | When the research execution physically happened |

Point-in-time research must use information that was available at the relevant `observation_date`. A finding should not reference data published after the run's observation date.

### 12.2 Temporal Consistency Rules

1. `ResearchFinding.observation_date` ≤ `ResearchRun.observation_date` — a finding cannot observe the future.
2. `ResearchFinding.source_publication_date` ≤ `ResearchFinding.created_at` — source must exist before finding.
3. Financial data used in a run must have `period_end` ≤ `ResearchRun.observation_date` — no future-period data.
4. These rules are enforced at the application layer (repository/service), not as database constraints, to allow for legitimate corrections and data loading order.

### 12.3 Look-Back Queries

The temporal fields enable point-in-time queries:
```sql
-- "What did we know about Company X as of 2026-06-30?"
SELECT f.* FROM research_finding f
JOIN research_run r ON f.research_run_id = r.id
WHERE r.company_id = :company_id
  AND r.observation_date <= '2026-06-30'
  AND r.status IN ('COMPLETED', 'PARTIAL')
ORDER BY r.observation_date DESC, f.created_at DESC;
```

## 13. Reproducibility

### 13.1 Captured Metadata

For each research run, the following is recorded to support reproducibility analysis (not byte-level replay):

| Metadata | Stored In | Format |
|----------|-----------|--------|
| Agent list and execution order | ResearchRunStep records | Relational |
| LLM model + provider per agent | AgentExecution.model_provider, model_name | String fields |
| LLM configuration (temperature, etc.) | AgentExecution.model_config | JSONB |
| Prompt template version | AgentExecution.prompt_version | String (semver or hash) |
| Tool versions (calculation engines) | AgentExecution.tool_versions | JSONB |
| Source document content hashes | ResearchDocument.content_hash | SHA-256 |
| Input state hash per step | ResearchRunStep.input_state_hash | SHA-256 |
| Output state hash per step | ResearchRunStep.output_state_hash | SHA-256 |
| Run configuration (budgets, flags) | ResearchRun.configuration | JSONB |
| Observation date | ResearchRun.observation_date | Date |
| Calculation engine version | ResearchFinding.calculation_version | String |

### 13.2 What Reproducibility Means Here

Given the same:
- Source documents (verified by content_hash)
- Configuration (agent list, model assignments, token budgets)
- Calculation engine version
- Observation date

The deterministic parts of the pipeline (financial calculations, ratio computations, data extraction) will produce identical results. The LLM-driven parts (analysis, inference, synthesis) will produce structurally similar but textually different outputs — this is inherent and expected.

## 14. Persistence Architecture

### 14.1 Repository Pattern

All database access goes through typed repository interfaces. Business logic and agents never import SQLAlchemy models or construct queries directly.

```python
class ResearchRunRepository(Protocol):
    async def create(self, run: ResearchRunCreate) -> ResearchRun: ...
    async def get(self, run_id: UUID) -> ResearchRun | None: ...
    async def get_by_company(self, company_id: UUID, limit: int = 10) -> list[ResearchRun]: ...
    async def update_status(self, run_id: UUID, status: ResearchRunStatus,
                            error_summary: str | None = None) -> ResearchRun: ...
    async def get_active_run(self, company_id: UUID) -> ResearchRun | None: ...

class AgentExecutionRepository(Protocol):
    async def create(self, execution: AgentExecutionCreate) -> AgentExecution: ...
    async def get_by_run(self, run_id: UUID) -> list[AgentExecution]: ...
    async def get_by_step(self, step_id: UUID) -> list[AgentExecution]: ...
    async def complete(self, execution_id: UUID, tokens: TokenUsage,
                       cost: Decimal, findings_count: int) -> AgentExecution: ...
    async def fail(self, execution_id: UUID, error: str,
                   error_type: str) -> AgentExecution: ...

class ResearchFindingRepository(Protocol):
    async def create_batch(self, findings: list[ResearchFindingCreate]) -> list[ResearchFinding]: ...
    async def get_by_run(self, run_id: UUID,
                         finding_type: FindingType | None = None) -> list[ResearchFinding]: ...
    async def get_current_for_company(self, company_id: UUID) -> list[ResearchFinding]: ...
    async def get_unsupported_facts(self, run_id: UUID) -> list[ResearchFinding]: ...

class ResearchArtifactRepository(Protocol):
    async def create(self, artifact: ResearchArtifactCreate) -> ResearchArtifact: ...
    async def get_by_run(self, run_id: UUID,
                         artifact_type: ArtifactType | None = None) -> list[ResearchArtifact]: ...

class ResearchRunStepRepository(Protocol):
    async def create_batch(self, steps: list[ResearchRunStepCreate]) -> list[ResearchRunStep]: ...
    async def update_status(self, step_id: UUID, status: StepStatus) -> ResearchRunStep: ...
    async def get_by_run(self, run_id: UUID) -> list[ResearchRunStep]: ...
```

### 14.2 Domain Service Layer

The repository is wrapped by a domain service that enforces business rules:

```python
class ResearchRunService(Protocol):
    async def initiate_run(self, company_id: UUID, initiated_by: str,
                           run_type: str, configuration: dict) -> ResearchRun: ...
    async def start_run(self, run_id: UUID) -> ResearchRun: ...
    async def record_agent_execution(self, run_id: UUID, step_id: UUID,
                                      agent_name: str, attempt: int) -> AgentExecution: ...
    async def complete_agent(self, execution_id: UUID, findings: list[ResearchFindingCreate],
                             artifacts: list[ResearchArtifactCreate],
                             token_usage: TokenUsage, cost: Decimal) -> None: ...
    async def fail_agent(self, execution_id: UUID, error: str, error_type: str) -> None: ...
    async def complete_run(self, run_id: UUID, quality_gates: dict) -> ResearchRun: ...
    async def fail_run(self, run_id: UUID, error: str) -> ResearchRun: ...
    async def cancel_run(self, run_id: UUID) -> ResearchRun: ...
```

State transition enforcement, concurrent run prevention, and temporal validation happen in the service layer.

### 14.3 Schema Organization

New entities follow the existing schema-per-domain pattern:

| Entity | PostgreSQL Schema | Rationale |
|--------|------------------|-----------|
| ResearchRun | `research` | Existing location |
| ResearchRunStep | `research` | Part of research run aggregate |
| AgentExecution | `research` | Part of research run aggregate |
| ResearchFinding | `research` | Existing location |
| ResearchArtifact | `research` | Research output |
| ResearchRunSource | `research` | Research run linkage |
| ThesisVersion | `thesis` | Existing location |

## 15. API Boundary

### 15.1 Service Interfaces (Protocol Only)

Phase 7 defines the service Protocol interfaces that Phase 20 (API Layer) will expose as HTTP endpoints. No HTTP handlers, routers, or serializers are built in Phase 7.

**Research Run Lifecycle**:
- `initiate_run(company_id, initiated_by, run_type, config) → ResearchRun`
- `get_run(run_id) → ResearchRun` (with steps, execution summary)
- `get_runs_for_company(company_id, limit, offset) → list[ResearchRun]`
- `cancel_run(run_id) → ResearchRun`

**Research Run Progress** (for real-time updates via Phase 20 WebSocket):
- `get_run_progress(run_id) → RunProgress` (steps completed, current agent, findings count, elapsed time)

**Findings & Evidence**:
- `get_findings(run_id, finding_type?, page, limit) → PaginatedFindings`
- `get_finding_evidence_chain(finding_id) → EvidenceChain` (finding → evidence → document → source)

**Thesis History**:
- `get_thesis_versions(company_id) → list[ThesisVersion]`
- `get_thesis_at_date(company_id, as_of_date) → InvestmentThesis | None`

**Artifacts**:
- `get_artifacts(run_id, artifact_type?) → list[ResearchArtifact]`

### 15.2 Read Models (Query DTOs)

Pydantic models for query results. These are the response shapes that Phase 20 will serialize to JSON:

```python
class RunSummary(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    status: ResearchRunStatus
    run_type: str
    started_at: datetime
    completed_at: datetime | None
    observation_date: date
    findings_count: int
    research_completeness: Decimal
    total_cost_usd: Decimal

class RunProgress(BaseModel):
    run_id: UUID
    status: ResearchRunStatus
    steps_total: int
    steps_completed: int
    current_step: str | None
    current_agent: str | None
    findings_count: int
    elapsed_seconds: int

class EvidenceChain(BaseModel):
    finding: ResearchFindingRead
    evidences: list[EvidenceRead]
    documents: list[ResearchDocumentRead]
    sources: list[SourceRead]
```

## 16. Observability

### 16.1 Structured Logging

All research run operations emit structured JSON logs (per CLAUDE.md §3, OpenTelemetry):

```json
{
  "event": "agent_execution_completed",
  "research_run_id": "uuid",
  "agent_name": "financial_analysis_agent",
  "attempt_number": 1,
  "duration_ms": 12340,
  "input_tokens": 15230,
  "output_tokens": 4521,
  "cost_usd": "0.0234",
  "findings_produced": 8,
  "model": "claude-sonnet-5"
}
```

### 16.2 Metrics (OpenTelemetry)

| Metric | Type | Labels |
|--------|------|--------|
| `research_run_duration_seconds` | Histogram | status, run_type |
| `research_run_total` | Counter | status, run_type |
| `agent_execution_duration_seconds` | Histogram | agent_name, status |
| `agent_execution_total` | Counter | agent_name, status |
| `agent_execution_tokens_total` | Counter | agent_name, direction(input/output) |
| `agent_execution_cost_usd_total` | Counter | agent_name, model |
| `findings_produced_total` | Counter | agent_name, finding_type |
| `active_research_runs` | Gauge | — |
| `quality_gate_failures_total` | Counter | gate_name |

### 16.3 Tracing

Each research run is a trace. Each agent execution is a span within the trace. OpenTelemetry trace context propagates through the agent pipeline.

```
Trace: research_run/{run_id}
  ├── Span: step/financial_analysis
  │     ├── Span: agent_execution/{exec_id} (attempt 1)
  │     │     ├── Span: llm_call (model: claude-sonnet-5)
  │     │     └── Span: tool_call/calculate_ratios
  │     └── Span: persist_findings
  ├── Span: step/business_model
  │     └── ...
  └── Span: quality_gate_check
```

## 17. Security Boundaries

### 17.1 Agent Isolation (per security-architecture.md)

- Each agent receives only the tools and state slices it needs (least privilege)
- Retrieved document content is wrapped in `<retrieved_document>` tags (prompt injection defense)
- Agent outputs are validated against Pydantic schemas before persistence
- Financial values in agent outputs are cross-checked against stored provider data

### 17.2 Data Access Boundaries

| Actor | Can Access | Cannot Access |
|-------|-----------|---------------|
| Agent (via tools) | Own run's state, company data, documents | Other runs, user data, system config |
| Service layer | All runs, findings, evidence | Raw LLM provider credentials |
| Repository layer | Database entities via SQLAlchemy | External APIs, LLM providers |
| API layer (Phase 20) | Service interfaces only | Direct DB access, repository internals |

### 17.3 Secrets

Phase 7 models reference `model_provider` and `model_name` but never store API keys. Provider credentials are resolved at runtime via environment variables through the provider factory (ADR-005).

## 18. LangGraph Compatibility

### 18.1 Design Principle

Phase 7 must NOT use LangGraph. Phase 7 must allow Phase 19 to wire LangGraph nodes that create/update ResearchRun, ResearchRunStep, AgentExecution, ResearchFinding, ResearchArtifact, and ThesisVersion records.

**LangGraph must NOT become the system of record.** The Phase 7 persistence layer (PostgreSQL via the service/repository contracts) is the authoritative source of truth for all research run state, findings, and execution history. LangGraph is an orchestration layer that coordinates agent execution and manages graph state — but durable state lives in the Phase 7 infrastructure.

### 18.2 Compatibility Contract

The `ResearchRunService` interface is what LangGraph nodes will call. Each LangGraph node (Phase 19) will:

1. Call `service.record_agent_execution(run_id, step_id, agent_name, attempt)` to start tracking
2. Execute the agent's business logic (Phase 8–18)
3. Call `service.complete_agent(execution_id, findings, artifacts, tokens, cost)` on success
4. Call `service.fail_agent(execution_id, error, error_type)` on failure

The service layer handles all persistence. LangGraph handles orchestration (graph topology, parallel execution, conditional routing, retry scheduling).

### 18.3 ResearchState Compatibility

The existing `ResearchState` TypedDict (agent-architecture.md §Research State) includes `research_run_id: str`. The service layer maps between:
- LangGraph state (`research_run_id` string in `ResearchState`)
- Persistence layer (UUID-based ORM models)

Phase 7 provides helper functions to:
- Create the initial `ResearchState` from a `ResearchRun` record
- Extract findings/artifacts from `ResearchState` for persistence
- Update `ResearchRun` aggregate fields from `ResearchState`

These are pure functions with no LangGraph dependency.

## 19. Database & Indexing Strategy

### 19.1 New Tables

```sql
-- Schema: research
-- Status fields use VARCHAR + CHECK constraint (not PostgreSQL enum types)
-- for easier schema evolution, simpler migrations, and no enum lifecycle coupling.

CREATE TABLE research.research_run_step (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_run_id UUID NOT NULL REFERENCES research.research_run(id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    input_state_hash VARCHAR(64),
    output_state_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE research.agent_execution (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_run_id UUID NOT NULL REFERENCES research.research_run(id) ON DELETE CASCADE,
    step_id UUID REFERENCES research.research_run_step(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'TRUNCATED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
    model_provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_config JSONB,
    prompt_version VARCHAR(50),
    tool_versions JSONB,
    error_message TEXT,
    error_type VARCHAR(100),
    findings_produced INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE research.research_artifact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_run_id UUID NOT NULL REFERENCES research.research_run(id) ON DELETE CASCADE,
    agent_execution_id UUID REFERENCES research.agent_execution(id),
    artifact_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    storage_path VARCHAR(1000),
    inline_content JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE research.research_run_source (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_run_id UUID NOT NULL REFERENCES research.research_run(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES research.research_document(id),
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    access_type VARCHAR(50) NOT NULL
);
```

### 19.2 Existing Table Alterations

```sql
-- research.research_run: add columns
ALTER TABLE research.research_run
    ADD COLUMN run_type VARCHAR(50),
    ADD COLUMN trigger_type VARCHAR(50),
    ADD COLUMN parent_run_id UUID REFERENCES research.research_run(id),
    ADD COLUMN observation_date DATE,
    ADD COLUMN configuration JSONB,
    ADD COLUMN error_summary TEXT;

-- research.research_run: migrate status from PG enum to VARCHAR + CHECK
-- (exact migration DDL depends on current column type; this is illustrative)
-- New valid values: CREATED, QUEUED, RUNNING, COMPLETED, FAILED, PARTIAL, CANCELLED
-- Note: INCOMPLETE is removed; PARTIAL subsumes its semantics.

-- research.research_run: deprecated JSONB columns (NOT dropped in this migration)
-- agent_execution_log, data_sources_used, cost_by_agent remain for backward
-- compatibility. Removal requires explicit dependency verification (DD-3).
-- See Migration 3 in §20.1.

-- research.research_finding: add columns
ALTER TABLE research.research_finding
    ADD COLUMN agent_execution_id UUID REFERENCES research.agent_execution(id),
    ADD COLUMN observation_date DATE,
    ADD COLUMN source_publication_date DATE,
    ADD COLUMN calculation_version VARCHAR(50),
    ADD COLUMN supersedes_finding_id UUID REFERENCES research.research_finding(id);

-- thesis.thesis_version: add columns
ALTER TABLE thesis.thesis_version
    ADD COLUMN research_run_id UUID REFERENCES research.research_run(id),
    ADD COLUMN snapshot_data JSONB,
    ADD COLUMN key_changes JSONB;
```

### 19.3 Indexes

```sql
-- ResearchRunStep
CREATE INDEX ix_research_run_step_run_id ON research.research_run_step(research_run_id);
CREATE INDEX ix_research_run_step_status ON research.research_run_step(research_run_id, status);

-- AgentExecution
CREATE INDEX ix_agent_execution_run_id ON research.agent_execution(research_run_id);
CREATE INDEX ix_agent_execution_step_id ON research.agent_execution(step_id);
CREATE INDEX ix_agent_execution_agent_name ON research.agent_execution(research_run_id, agent_name);

-- ResearchArtifact
CREATE INDEX ix_research_artifact_run_id ON research.research_artifact(research_run_id);
CREATE INDEX ix_research_artifact_type ON research.research_artifact(research_run_id, artifact_type);

-- ResearchRunSource
CREATE INDEX ix_research_run_source_run_id ON research.research_run_source(research_run_id);
CREATE INDEX ix_research_run_source_document_id ON research.research_run_source(document_id);
CREATE UNIQUE INDEX uq_research_run_source ON research.research_run_source(research_run_id, document_id);

-- New indexes on altered tables
CREATE INDEX ix_research_finding_execution_id ON research.research_finding(agent_execution_id);
CREATE INDEX ix_research_finding_observation_date ON research.research_finding(research_run_id, observation_date);
CREATE INDEX ix_research_run_parent ON research.research_run(parent_run_id) WHERE parent_run_id IS NOT NULL;
CREATE INDEX ix_research_run_observation ON research.research_run(company_id, observation_date DESC);
```

## 20. Migration Strategy

### 20.1 Phased Migration

**Migration 1 (additive)**: Create new tables + add new nullable columns to existing tables.
- Creates: `research_run_step`, `agent_execution`, `research_artifact`, `research_run_source`
- Adds nullable columns to: `research_run`, `research_finding`, `thesis_version`
- All new columns are nullable or have server defaults
- Zero-downtime: no existing queries break

**Migration 2 (data)**: Migrate data from JSONB blobs to relational tables.
- Transform `ResearchRun.agent_execution_log` → `AgentExecution` records
- Transform `ResearchRun.data_sources_used` → `ResearchRunSource` records
- Transform `ResearchRun.cost_by_agent` → derived from `AgentExecution.cost_usd`
- This migration is idempotent (can be re-run safely)

**Migration 3 (cleanup, deferred — see DD-3)**: Drop deprecated JSONB columns after explicit dependency verification.
- Drop `agent_execution_log`, `data_sources_used`, `cost_by_agent` from `research_run`
- Requires explicit verification that no consumers remain (not automatic upon any phase completion)
- Separate Alembic revision from schema migration (per CLAUDE.md §11)
- Must be preceded by a dependency audit confirming no code, query, or report reads these columns

### 20.2 Rollback Safety

Each migration has a `downgrade()` method:
- Migration 1 downgrade: drop new tables, drop new columns
- Migration 2 downgrade: no-op (JSONB blobs are not deleted in migration 2, only supplemented)
- Migration 3 downgrade: re-add columns (data would need to be re-populated from new tables)

## 21. Testing Strategy

### 21.1 Unit Tests

| Test Area | What | Framework |
|-----------|------|-----------|
| State machine transitions | Valid transitions succeed, invalid transitions raise | pytest |
| Temporal consistency rules | Validation rejects future observation dates | pytest |
| Finding immutability | Cannot update finding content after creation | pytest |
| Supersession chains | Superseded findings correctly linked | pytest |
| Enum coverage | All status enums have transition rules | pytest |

### 21.2 Repository Tests (Integration)

| Test Area | What | Framework |
|-----------|------|-----------|
| CRUD operations | Create, read, update for all new entities | pytest + async PostgreSQL |
| Cascade deletes | Deleting run cascades to steps, executions, findings | pytest + PostgreSQL |
| Concurrent run prevention | Second run for same company blocked | pytest + Redis |
| Query performance | Key queries complete within budget | pytest + EXPLAIN ANALYZE |
| Pagination | Findings and runs paginate correctly | pytest + PostgreSQL |

### 21.3 Service Tests

| Test Area | What | Framework |
|-----------|------|-----------|
| Full run lifecycle | CREATED → QUEUED → RUNNING → COMPLETED | pytest |
| Agent retry lifecycle | Fail → retry → succeed, verify all records | pytest |
| Quality gate integration | Gate failure → PARTIAL status | pytest |
| Evidence chain integrity | Finding → Evidence → Document → Source chain queryable | pytest |
| Thesis versioning | New run creates version, links to previous | pytest |

### 21.4 Migration Tests

- Forward migration on empty database succeeds
- Forward migration with existing data preserves data
- Downgrade migration succeeds
- JSONB → relational data migration is correct and complete

### 21.5 Golden Dataset

3–5 reference companies with hand-crafted research run data:
- Complete run (all agents succeed, all gates pass)
- Partial run (some agents fail, run PARTIAL)
- Incremental run (thesis update triggered by new data)
- Run with retries (agent fails twice, succeeds on third attempt)
- Cancelled run (user cancellation mid-execution)

## 22. Acceptance Criteria

1. **ResearchRun lifecycle enforced**: A run can be created, enqueued, started, and completed/failed/partial/cancelled with proper state transitions enforced. Invalid transitions raise errors.
2. **No INCOMPLETE state**: The ResearchRunStatus enum contains exactly: CREATED, QUEUED, RUNNING, COMPLETED, FAILED, PARTIAL, CANCELLED. No INCOMPLETE state exists.
3. **PARTIAL semantics documented and enforced**: PARTIAL means usable but incomplete research output. Distinguished from FAILED (no usable output) at the service layer.
4. **AgentExecution append-only**: Every agent invocation produces an immutable execution record with tokens, cost, model, provider, and prompt version. Records are never updated after creation.
5. **Retries preserve execution history**: Failed agents create new AgentExecution records with incremented attempt_number. Previous attempts remain as immutable audit records.
6. **Resume uses parent_run_id**: A resumed run creates a new ResearchRun with parent_run_id pointing to the original. The original run is not modified.
7. **Existing Claim functionality preserved**: Claim, ClaimEvidence, and all their existing queries, APIs, relationships, and behavior are untouched by Phase 7. No deprecation or removal.
8. **ResearchFinding supports evidence provenance**: FACT findings link to Evidence via M:N junction. Findings without evidence linkage are queryable (Quality Gate #11).
9. **Contradictory evidence supported**: Finding supersession via supersedes_finding_id chain. Contradictory findings are not collapsed into a single confidence score.
10. **Point-in-time timestamps preserved**: observation_date, source_publication_date on findings; observation_date on runs; all temporal dimensions from §12.1 tracked and distinct.
11. **Temporal validation supported**: Application-layer enforcement of temporal consistency rules (§12.2).
12. **Finding immutability**: ResearchFindings cannot be modified after creation.
13. **Concurrent run prevention**: Two runs for the same company cannot execute simultaneously (Redis advisory lock).
14. **Thesis versioning**: New research runs create ThesisVersions with snapshot_data and research_run_id.
15. **No LangGraph dependency**: Phase 7 code has zero LangGraph imports.
16. **No processor dependency**: The service layer is processor-agnostic. No Celery, Temporal, or other background worker imports.
17. **Legacy JSONB is non-canonical**: AgentExecution is the canonical execution audit model. New code must not depend on agent_execution_log JSONB.
18. **Future JSONB removal requires dependency verification**: Deprecated JSONB columns are not automatically removed. Removal requires explicit verification that no consumers remain.
19. **Migration safety**: Migrations are additive (no data loss), with tested downgrade paths. Column drops are deferred and separate from schema additions.
20. **Repository/service separation**: All database access through typed Protocol interfaces. Business logic never imports SQLAlchemy models directly.
21. **Reproducibility metadata**: AgentExecution records capture model, provider, prompt_version, tool_versions, model_config.
22. **Cost/token/latency metadata**: Every AgentExecution records input_tokens, output_tokens, cost_usd, duration_ms.
23. **Auditability**: Complete execution history (all attempts, all findings, all artifacts) is preserved and queryable.

## 23. Design Review Questions — Answers

**Q1: Does ResearchRun need a `run_type` or are all runs equivalent?**
Yes. Four run types: FULL (initial deep research), INCREMENTAL (update with new data), THESIS_UPDATE (triggered by thesis-invalidating event), MONITORING (lightweight watchlist check). Run type determines which agents execute and what token budgets apply.

**Q2: Should AgentExecution be a separate table or JSONB on ResearchRun?**
Separate table. JSONB is unqueryable for cost analysis, agent performance tracking, retry audit, and temporal queries. The existing `agent_execution_log` JSONB blob is a Phase 4 shortcut that must be replaced with proper relational modeling.

**Q3: How are retries recorded — update in place or append?**
Append. Each retry creates a new AgentExecution record with incremented `attempt_number`. Previous attempts are immutable audit records. This is critical for understanding failure patterns and cost attribution.

**Q4: What is the immutability boundary?**
ResearchFinding, AgentExecution, ResearchArtifact, and ThesisVersion records are immutable after creation. ResearchRun and ResearchRunStep have mutable operational state (status, timestamps). See §9.3 for full model.

**Q5: How does temporal integrity work for look-back queries?**
Every finding carries `observation_date` and `source_publication_date`. Every run carries `observation_date`. Point-in-time queries filter by `observation_date <= target_date`. See §12 for full model.

**Q6: How does the evidence graph connect Source → Evidence → Finding → Thesis?**
Source → ResearchDocument (1:N) → Evidence (1:N) → ResearchFinding (M:N via junction) → InvestmentThesis (via ResearchRun FK). The chain is queryable for any finding. See §8.

**Q7: What happens when a quality gate fails?**
The orchestrator (Phase 19) may retry up to 1 additional iteration (ADR-007). If gates still fail, the run status becomes PARTIAL with `quality_gate_results` recording which gates failed. The run contains usable findings from agents that completed, but is not a full research result. No fabrication occurs.

**Q8: How is concurrent execution prevented?**
Redis advisory lock `research_run:{company_id}` acquired in QUEUED state, released on terminal state (ADR-007 §4). Different companies can run concurrently (capped by `active_research_runs` gauge).

**Q9: How does finding supersession work?**
`ResearchFinding.supersedes_finding_id` links to the finding it replaces. Both findings persist (immutability). The "current" finding for a company is the one with no superseding finding. Chains enable thesis change tracking.

**Q10: How do we avoid hard-coding LLM providers?**
AgentExecution stores `model_provider` and `model_name` as strings. The actual provider is resolved at runtime via the provider factory (ADR-005). Phase 7 has no provider imports.

**Q11: What is the ResearchArtifact storage strategy?**
Small artifacts (< 64KB) stored inline as JSONB in `inline_content`. Large artifacts stored in S3 with `storage_path`. Content hash always computed for integrity. Both storage paths return content via the same repository interface.

**Q12: How does ThesisVersion capture point-in-time state?**
`snapshot_data` (JSONB) captures the full thesis state at version time. `key_changes` (JSONB) captures a structured diff. `research_run_id` links to the run that produced this version. The linked list via `previous_thesis_id` enables thesis history traversal.

**Q13: What is the migration strategy for existing data?**
Three-phase: (1) additive schema changes, (2) data migration from JSONB to relational, (3) deferred column drops. All phases have downgrade methods. See §20.

**Q14: How does Phase 7 relate to Phase 19 (LangGraph)?**
Phase 7 provides the persistence layer (models, repositories, services). Phase 19 provides the orchestration layer (graph topology, parallel execution, retry scheduling). They interact through the `ResearchRunService` Protocol interface. Phase 7 has zero LangGraph imports.

**Q15: How are costs tracked?**
Per-execution: `AgentExecution.input_tokens`, `output_tokens`, `cost_usd`, `model_provider`, `model_name`. Per-run: `ResearchRun.total_input_tokens`, `total_output_tokens`, `total_cost_usd` (aggregated from executions). Per-agent-per-run: queryable from AgentExecution grouped by `agent_name`.

**Q16: What about the Claim/ClaimEvidence overlap with ResearchFinding/Evidence?**
`Claim` and `ClaimEvidence` are preserved as-is in Phase 7. They are actively used across repositories, services, APIs, schemas, and tests (10 files). `ResearchFinding` becomes the canonical finding model for the new Research Run infrastructure, but Claim and ClaimEvidence are NOT deprecated, removed, or modified. Long-term consolidation is a deferred architectural decision (see §24, DD-1).

**Q17: How does the configuration freeze work?**
`ResearchRun.configuration` (JSONB) stores a frozen copy of the run configuration at initiation time: agent list, model assignments, token budgets, feature flags. This enables reproducibility analysis — you can see exactly what configuration produced a given run's results, even if the system defaults change later.

## 24. Deferred Decisions (Non-Blocking for Phase 7)

The following decisions were identified during architecture review and are explicitly deferred. None of these block Phase 7 implementation.

**DD-1: Claim vs ResearchFinding long-term consolidation**
`Claim` (evidence.py:80-123) and `ClaimEvidence` (evidence.py:126-147) overlap with `ResearchFinding` + `research_finding_evidence`. `Claim` has `claim_type` (6 values) vs `ResearchFinding.finding_type` (7 values). `ClaimEvidence` has `relevance` and `excerpt` fields not present on the junction table. **Phase 7 decision**: Preserve both. Claim/ClaimEvidence are actively used across 10 files (repositories, services, APIs, schemas, tests). ResearchFinding is the canonical model for the new Research Run infrastructure. No existing Claim queries, APIs, relationships, or behavior shall be broken. **Deferred**: A future architecture review will decide whether to consolidate into a single model, keep both with clear domain boundaries, or evolve independently. This requires a separate design decision with its own migration plan.

**DD-2: Background task processor selection**
ADR-002 is pending. Research runs are long-running (up to 15 minutes) and should not run in the HTTP request cycle. Phase 7 service interfaces are processor-agnostic. **Deferred to**: ADR-002 / Phase 19. The choice between Celery, Temporal, arq, or other processors affects orchestration (Phase 19), not persistence (Phase 7).

**DD-3: Legacy agent_execution_log removal timing**
The three deprecated JSONB columns on ResearchRun (`agent_execution_log`, `data_sources_used`, `cost_by_agent`) should eventually be removed. Removal is NOT automatic upon any phase completion — it requires explicit dependency verification confirming no remaining consumers. **Deferred to**: Post-Phase 19, after verification. See §5.1 ResearchRun deprecation lifecycle.

## 25. Resolved Decisions (from Architecture Reconciliation)

The following decisions were resolved during the architecture reconciliation review (2026-09-30):

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| Claim/ClaimEvidence deprecation | **Preserved as-is.** Deferred consolidation (DD-1). | Actively used across 10 files. Cannot deprecate without separate migration plan. |
| ResearchRunStatus storage type | **VARCHAR + CHECK constraint.** | Easier schema evolution, simpler migrations, avoids PostgreSQL enum lifecycle coupling. |
| INCOMPLETE status | **Removed.** PARTIAL subsumes its semantics. | PARTIAL already represents usable-but-incomplete output. Two states for the same concept adds ambiguity. |
| Background processor | **Deferred (DD-2).** Service layer is processor-agnostic. | Orchestration concern, not persistence. |
| JSONB canonical model | **AgentExecution is canonical.** Legacy JSONB deprecated. | Relational model enables queries, auditing, cost analysis that JSONB cannot. |
| Retry vs Resume semantics | **Three-case model.** Agent Retry, Research Resume, New Research Run (§10). | Clear separation prevents conflation of within-run retry with cross-run resume. |

## 26. Further Deferred Decisions

| Decision | Deferred To | Rationale |
|----------|-------------|-----------|
| Claim vs ResearchFinding consolidation | Future architecture review | Requires separate design decision and migration plan (DD-1) |
| Background task processor (Celery vs Temporal vs arq) | ADR-002 / Phase 19 | Orchestration concern, not persistence (DD-2) |
| Legacy JSONB column removal | Post-Phase 19 verification | Requires explicit dependency verification (DD-3) |
| LangGraph checkpointing strategy | Phase 19 | LangGraph-specific, requires graph topology |
| WebSocket progress notification | Phase 20 | API layer concern |
| Cost alerting thresholds | Phase 22 | FinOps concern |
| Agent prompt versioning scheme (semver vs hash) | Phase 8 (first agent) | Needs practical prompt development experience |
| Rate limiting for research run initiation | Phase 20/24 | API + security layer concern |
| Partitioning strategy for agent_execution | Post-Phase 25 | Only needed at scale (> 10M rows) |

---

## Appendix A: Compatibility Matrix

| Existing Entity | Phase 7 Impact | Breaking Change |
|----------------|---------------|-----------------|
| ResearchRun | Evolve: add columns, deprecate JSONB blobs | No (additive) |
| ResearchFinding | Evolve: add columns | No (additive) |
| ThesisVersion | Evolve: add columns | No (additive) |
| Evidence | No change | No |
| ResearchDocument | No change | No |
| Source | No change | No |
| InvestmentThesis | No change | No |
| Risk / Catalyst / CompanyScore | No change | No |
| ValuationModel / Scenario | No change | No |
| MoatAssessment / GrowthOpportunity | No change | No |
| Claim / ClaimEvidence | No change (preserved as-is) | No |

## Appendix B: Entity Count Summary

| Category | Entities |
|----------|----------|
| Retained as-is | 11 |
| Evolved (additive columns) | 3 (ResearchRun, ResearchFinding, ThesisVersion) |
| New tables | 4 (ResearchRunStep, AgentExecution, ResearchArtifact, ResearchRunSource) |
| New enums | 3 (StepStatus, AgentExecutionStatus, ArtifactType) |
| Evolved enums | 1 (ResearchRunStatus: 4 → 7 values) |
