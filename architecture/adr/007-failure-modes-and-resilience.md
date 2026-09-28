# ADR-007: Failure Modes and Resilience Strategy

## Status

Accepted

## Date

2026-09-28

## Context

The architecture review identified that failure modes, circuit breakers, and partial-completion strategies were undocumented. A research run involves 17 LLM agent invocations, multiple external provider calls, and database writes — any of which can fail.

## Decision

Define explicit failure handling for every failure class.

## Failure Modes and Mitigations

### 1. LLM Provider Unavailability

**Failure**: Anthropic or OpenAI API is down or rate-limited.

**Mitigation**:
- **Primary/fallback provider**: If the primary LLM provider fails, attempt the configured fallback provider (e.g., Claude → OpenAI or vice versa). This is already enabled by `LLMProvider` abstraction.
- **Per-agent retry**: 3 retries with exponential backoff per agent LLM call.
- **Research run degradation**: If the LLM is unavailable after retries, mark the affected agent as FAILED in `ResearchRun.agent_execution_log`. Continue with remaining agents that don't depend on the failed agent. Mark the run as INCOMPLETE, not FAILED.

### 2. Partial Research Run Completion

**Failure**: Agent N of 17 fails mid-workflow.

**Mitigation**:
- **Save partial state**: `ResearchState` is persisted to PostgreSQL after each agent completes (via LangGraph checkpointing). Partial results are never lost.
- **Resume capability**: A failed run can be resumed from the last successful agent, not restarted from scratch.
- **Partial output**: If ≥ 80% of agents complete, the Research Synthesis agent can produce a partial thesis marked with explicit gaps. Quality gates will flag missing sections.
- **INCOMPLETE status**: Partial runs are never marked COMPLETED. The quality gate engine identifies exactly which dimensions are missing.

### 3. Financial Data Provider Failure

**Failure**: NSE/BSE data feed is down, Alpha Vantage returns errors.

**Mitigation**:
- **Cached data**: Recent financial data is cached in PostgreSQL. Agents use stored data when provider is unavailable. Data freshness is recorded and surfaced.
- **Staleness flag**: If data is older than the configured freshness threshold, Quality Gate #6 (Current-Source Validation) flags it. The research continues with stale data but the output notes the staleness.
- **No fabrication**: Missing data is NEVER invented. The system reports "data unavailable for [metric] for [period]."

### 4. Concurrent Research Run Collision

**Failure**: Two research runs initiated for the same company simultaneously.

**Mitigation**:
- **Idempotency lock**: A Redis-based advisory lock (`research_run:{company_id}`) prevents concurrent runs for the same company. The second request receives a 409 Conflict with a reference to the in-progress run.
- **Different companies**: Concurrent runs for different companies are allowed (limited by the `active_research_runs` gauge, default max 5).

### 5. Quality Gate Loop

**Failure**: Quality gates fail repeatedly, causing the workflow to loop back to agents indefinitely.

**Mitigation**:
- **Maximum loop iterations**: 2 (one initial pass + one retry pass). After the retry pass, if quality gates still fail, the run is marked INCOMPLETE with the specific gate failures listed.
- **No infinite loops**: This is a hard limit enforced in the LangGraph graph definition.

### 6. Research Run Timeout

**Decision**: Each research run has a maximum wall-clock timeout of 15 minutes. Individual agents have a 3-minute timeout. If the total run exceeds 15 minutes, it is terminated and marked INCOMPLETE with partial results saved.

### 7. Background Task Failure (Celery)

**Mitigation**:
- **Dead letter queue**: Failed tasks are routed to a dead letter queue for investigation, not silently dropped.
- **Task idempotency**: Data ingestion tasks are idempotent (content hash dedup prevents duplicate storage).
- **Retry policy**: Data ingestion tasks retry 3 times. Research runs do not auto-retry (user must re-initiate).

### 8. Database Failure

**Mitigation**:
- **Connection pooling**: SQLAlchemy async connection pool with configurable max connections and overflow.
- **Health check**: `GET /health` verifies database connectivity. Load balancer routes traffic away from unhealthy instances.
- **Backups**: Daily automated backups with point-in-time recovery.

## Consequences

- ResearchState checkpointing adds overhead but enables resume
- Redis advisory lock requires Redis to be available for research runs
- Maximum loop iterations may cause some research to be INCOMPLETE that could have been COMPLETED with more retries — this is acceptable; the user can re-run
- 15-minute timeout may be too short for complex companies with extensive documentation — monitor and adjust based on real-world usage
