# ADR-001: LangGraph for Agent Orchestration

## Status

Accepted

## Date

2026-09-28

## Context

The platform requires orchestration of 17 specialized AI agents in a deterministic research workflow. Agents must communicate through structured state, support parallel execution where possible, handle failures gracefully, and produce auditable execution traces.

Options considered:

1. **LangGraph** — State-machine-based agent orchestration from LangChain ecosystem
2. **Custom orchestration** — Hand-built state machine with async Python
3. **Temporal** — Workflow engine with durable execution
4. **CrewAI** — Multi-agent framework

## Decision

Use **LangGraph** for agent orchestration.

## Rationale

- **Deterministic workflows**: LangGraph models workflows as directed graphs with explicit state transitions, matching our requirement for deterministic orchestration rather than emergent agent conversations.
- **Structured state**: The `TypedDict` state model aligns with our Pydantic-first architecture. Agents read from and write to well-defined state fields.
- **Parallel execution**: LangGraph supports parallel node execution for agents with no data dependencies (e.g., Business Model + Industry + Competitor agents).
- **Conditional routing**: Supports conditional edges for quality gate logic — if a gate fails, the graph can route back to specific agents.
- **Observability**: Built-in support for LangSmith tracing, compatible with OpenTelemetry integration.
- **Ecosystem**: Access to LangChain's tool and provider abstractions while allowing custom implementations.

**Why not custom?** Building a robust state machine with parallel execution, error handling, retry logic, and observability would duplicate significant effort that LangGraph provides.

**Why not Temporal?** Temporal is excellent for durable workflows but adds infrastructure complexity (Temporal server). It's better suited for long-running background pipelines. We may adopt Temporal for data ingestion pipelines (see ADR-002) but use LangGraph for the agent research workflow where LLM integration is the primary concern.

**Why not CrewAI?** CrewAI encourages free-text agent-to-agent communication, which contradicts our structured-state requirement.

## Consequences

- Team must learn LangGraph's graph definition API
- Agent implementations follow LangGraph's node function pattern
- State schema changes require updating the graph definition
- LangChain dependency introduced (limited to orchestration layer — business logic remains framework-independent)
