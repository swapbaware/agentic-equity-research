# ADR-002: Background Task Processor Selection

## Status

Pending — requires evaluation in Phase 1

## Date

2026-09-28

## Context

The platform needs background task processing for:
- Data ingestion from financial providers (scheduled and event-driven)
- Research run execution (long-running, 2-5 minutes per company)
- Monitoring and alerting (periodic checks)
- Report generation

Options:

1. **Celery** — Mature Python task queue with Redis/RabbitMQ broker
2. **Temporal** — Durable workflow engine with retry, versioning, visibility

## Decision

Deferred. Evaluate both in Phase 1 with a proof-of-concept.

## Evaluation Criteria

| Criterion | Weight | Celery | Temporal |
|-----------|--------|--------|----------|
| Setup complexity | Medium | Low | High (Temporal server) |
| Durability | High | Limited (task state in broker) | Strong (event sourcing) |
| Retry/error handling | High | Good (built-in) | Excellent (native) |
| Workflow composition | Medium | Limited (chains/chords) | Excellent (native) |
| Observability | Medium | Flower dashboard | Temporal Web UI |
| Team familiarity | Low | Common in Python | Less common |
| Infrastructure cost | Medium | Redis only | Temporal server + DB |

## Leaning

Celery for Phase 1 (simpler setup, sufficient for MVP), with architecture designed to swap to Temporal if workflow complexity demands it in later phases.

## Consequences

- The background task interface must be abstracted so the processor can be swapped
- Phase 1 implementation should use a `TaskRunner` interface with a Celery implementation
- Temporal evaluation deferred to Phase 3 when agent workflow complexity is clearer
