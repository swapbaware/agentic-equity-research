# Deployment Architecture

## Overview

The platform is deployed as a set of containerized services orchestrated with Docker Compose (development) and adaptable to Kubernetes or cloud-managed services (production). The architecture follows twelve-factor app principles.

## Service Topology

```
┌─────────────────────────────────────────────────────────────┐
│                        Load Balancer / CDN                   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
     ┌─────────▼──────────┐         ┌─────────▼──────────┐
     │   Frontend          │         │   Backend API       │
     │   (Next.js)         │         │   (FastAPI)         │
     │   Port: 3000        │         │   Port: 8000        │
     └─────────────────────┘         └──────────┬──────────┘
                                                │
                              ┌─────────────────┼──────────┐
                              │                 │          │
                    ┌─────────▼───┐   ┌─────────▼───┐  ┌──▼──────────┐
                    │ PostgreSQL  │   │   Redis     │  │ Celery      │
                    │ + pgvector  │   │             │  │ Workers     │
                    │ Port: 5432  │   │ Port: 6379  │  │             │
                    └─────────────┘   └─────────────┘  └──┬──────────┘
                                                          │
                                                ┌─────────▼──────────┐
                                                │   MinIO / S3       │
                                                │   Port: 9000       │
                                                └────────────────────┘
```

## Container Definitions

### docker-compose.yml Services

| Service | Image | Purpose | Ports |
|---------|-------|---------|-------|
| `frontend` | Node 20 + Next.js | Web dashboard | 3000 |
| `backend` | Python 3.11 + FastAPI | API server | 8000 |
| `worker` | Python 3.11 + Celery | Background task processing | — |
| `beat` | Python 3.11 + Celery Beat | Task scheduling | — |
| `db` | PostgreSQL 16 + pgvector | Primary database | 5432 |
| `redis` | Redis 7 | Cache, message broker | 6379 |
| `minio` | MinIO | Local S3-compatible storage | 9000, 9001 |

### Backend Dockerfile (Multi-stage)

```
Stage 1: Builder
  - Python 3.11 slim base
  - Install build dependencies
  - Install Python packages from lock file
  - Copy application code

Stage 2: Runtime
  - Python 3.11 slim base
  - Copy installed packages from builder
  - Copy application code
  - Non-root user
  - Health check endpoint
  - Uvicorn entrypoint
```

### Frontend Dockerfile (Multi-stage)

```
Stage 1: Dependencies
  - Node 20 alpine
  - Install npm packages from lock file

Stage 2: Builder
  - Copy source
  - Build Next.js (next build)

Stage 3: Runtime
  - Node 20 alpine
  - Copy built assets
  - Non-root user
  - Next.js start entrypoint
```

## Environment Configuration

### Twelve-Factor Compliance

| Factor | Implementation |
|--------|---------------|
| Codebase | Single repo, tracked in Git |
| Dependencies | Lock files (poetry.lock, package-lock.json) |
| Config | Environment variables (.env) |
| Backing services | PostgreSQL, Redis, S3 as attached resources |
| Build/release/run | Docker multi-stage builds |
| Processes | Stateless backend, state in PostgreSQL/Redis |
| Port binding | Each service binds its own port |
| Concurrency | Horizontal scaling of backend + workers |
| Disposability | Fast startup, graceful shutdown |
| Dev/prod parity | Docker Compose mirrors production topology |
| Logs | Structured JSON to stdout |
| Admin processes | Management commands via CLI |

### Environment Files

```
.env.example          # Template with all variables, no secrets
.env                  # Local development values (gitignored)
.env.test             # Test environment overrides (gitignored)
```

## Health Checks

| Service | Endpoint | Check |
|---------|----------|-------|
| Backend | `GET /health` | App running, DB connected, Redis connected |
| Backend | `GET /health/ready` | All providers initialized, migrations current |
| Frontend | `GET /api/health` | Next.js server running |
| PostgreSQL | `pg_isready` | Database accepting connections |
| Redis | `redis-cli ping` | Redis responding |

## Scaling Strategy

### Horizontal Scaling

| Component | Scaling Approach |
|-----------|-----------------|
| Frontend | Multiple Next.js instances behind load balancer |
| Backend API | Multiple FastAPI instances (stateless) |
| Celery Workers | Add workers for research throughput |
| PostgreSQL | Read replicas for read-heavy screening queries |
| Redis | Cluster mode for cache scaling |

### Resource Estimates (Initial)

| Service | CPU | Memory | Storage |
|---------|-----|--------|---------|
| Backend API | 2 vCPU | 2 GB | — |
| Celery Worker (per) | 2 vCPU | 4 GB | — |
| PostgreSQL | 2 vCPU | 4 GB | 50 GB |
| Redis | 1 vCPU | 1 GB | — |
| MinIO / S3 | 1 vCPU | 1 GB | 100 GB |
| Frontend | 1 vCPU | 1 GB | — |

### LLM API Cost Considerations

- Research runs are LLM-intensive (17 agents, multiple tool calls each)
- Estimated tokens per full company research: 50K-200K input, 20K-80K output
- Token usage tracking per research run (stored in ResearchRun)
- Budget limits configurable per user/organization
- Caching of LLM responses where deterministic (same input → same output not guaranteed, but intermediate results cached)

## CI/CD Pipeline

### GitHub Actions Workflow

```
Push / PR to main
      │
      ├── Backend:
      │     ├── Lint (ruff)
      │     ├── Type check (mypy)
      │     ├── Unit tests (pytest)
      │     └── Integration tests (pytest + test DB)
      │
      ├── Frontend:
      │     ├── Lint (eslint)
      │     ├── Type check (tsc)
      │     └── Unit tests (vitest)
      │
      └── Docker:
            ├── Build images
            └── Smoke test (docker-compose up + health checks)

Merge to main
      │
      ├── Build production images
      ├── Push to container registry
      └── Deploy (manual trigger for production)
```

### Quality Gates (CI)

- All tests pass
- Type checks pass (mypy strict, tsc strict)
- Linting passes (ruff, eslint)
- No known security vulnerabilities (dependency scan)
- Docker images build successfully
- Test coverage meets threshold (80%)

## Observability

### OpenTelemetry Integration

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Backend    │────▶│  OTel        │────▶│  Backend     │
│  (FastAPI)  │     │  Collector   │     │  (Jaeger /   │
│             │     │              │     │   Grafana)   │
│  Workers    │────▶│              │────▶│              │
│  (Celery)   │     │              │     │  Prometheus  │
└─────────────┘     └──────────────┘     └──────────────┘
```

### Metrics

| Metric | Type | Purpose |
|--------|------|---------|
| `research_run_duration` | Histogram | Research workflow latency |
| `agent_execution_duration` | Histogram | Per-agent latency |
| `llm_tokens_used` | Counter | Token consumption tracking |
| `llm_api_latency` | Histogram | LLM provider response time |
| `data_provider_latency` | Histogram | Financial data API latency |
| `data_provider_errors` | Counter | Provider error rate |
| `screening_query_duration` | Histogram | Screening performance |
| `active_research_runs` | Gauge | Concurrent research runs |
| `quality_gate_pass_rate` | Gauge | Research quality tracking |

### Structured Logging

```json
{
  "timestamp": "2026-09-28T10:30:00Z",
  "level": "INFO",
  "service": "backend",
  "trace_id": "abc123",
  "span_id": "def456",
  "message": "Research run completed",
  "company_id": "uuid",
  "research_run_id": "uuid",
  "duration_ms": 245000,
  "agents_executed": 17,
  "quality_gates_passed": 12
}
```

### Dashboards

| Dashboard | Purpose |
|-----------|---------|
| System Health | Service status, error rates, latency |
| Research Operations | Active runs, completion rate, quality gate results |
| LLM Usage | Token consumption, cost, provider latency |
| Data Pipeline | Ingestion status, data freshness, validation failures |
| User Activity | Active users, research requests, screening queries |

## Local Development Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd agentic-equity-research

# 2. Copy environment template
cp .env.example .env
# Edit .env with API keys

# 3. Start all services
docker-compose up -d

# 4. Run database migrations
docker-compose exec backend alembic upgrade head

# 5. Access services
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
# MinIO Console: http://localhost:9001
```

## Production Deployment Options

### Option A: Docker Compose on VPS

- Suitable for initial deployment and small-scale usage
- Single machine with Docker Compose
- Nginx reverse proxy with Let's Encrypt SSL
- Managed PostgreSQL recommended (RDS or equivalent)

### Option B: Kubernetes

- Suitable for scaling and high availability
- Helm charts for service deployment
- Horizontal Pod Autoscaling for backend + workers
- Managed database and Redis services
- Ingress controller for routing

### Option C: Cloud-Native (AWS/GCP)

- ECS/Cloud Run for containers
- RDS/Cloud SQL for PostgreSQL
- ElastiCache/Memorystore for Redis
- S3/GCS for object storage
- CloudFront/CDN for frontend
- Managed Kubernetes (EKS/GKE) as alternative

The initial deployment targets Option A, with the architecture designed to migrate to B or C without application changes.

## Database Migration Strategy

- **Tool**: Alembic (SQLAlchemy's migration tool)
- **Zero-downtime migrations**: Schema changes must be backwards-compatible. Column additions use `nullable=True` or `server_default`. Column removals are two-phase: (1) stop writing to the column, deploy; (2) drop the column in a later migration.
- **Rollback**: Every migration has a `downgrade()` method. Tested in CI before merge.
- **Data migrations**: Separated from schema migrations. Run as distinct Alembic revisions.

## Rollback Strategy

- **Application rollback**: Deploy the previous Docker image tag. Stateless services (backend, frontend) roll back instantly.
- **Database rollback**: Run `alembic downgrade -1` to reverse the latest migration. Only safe if the migration's `downgrade()` was tested.
- **Feature flags**: For high-risk features, use configuration-based feature flags (not a feature flag service) to enable/disable without deployment.

## LLM Observability

In addition to OpenTelemetry traces and Prometheus metrics, LLM-specific observability includes:

- **Per-agent traces**: Each agent invocation is a span within the research run trace. Includes model used, input/output token counts, tool calls made, and duration.
- **Prompt logging**: Agent prompts and completions logged to a separate structured log stream (not the main application log) for debugging and evaluation. PII and secrets are never included.
- **LangSmith integration** (optional): For detailed agent conversation tracing during development. Disabled in production by default to avoid sending data to external services.
- **Cost dashboard**: Real-time LLM cost tracking per research run, per agent, and per user. See ADR-008.

## Alerting Strategy

| Alert | Condition | Severity |
|-------|-----------|----------|
| Service down | Health check fails for > 2 minutes | Critical |
| High error rate | API 5xx rate > 5% over 5 minutes | High |
| Research run failures | > 3 consecutive FAILED runs | High |
| LLM provider error | Provider unavailable for > 5 minutes | High |
| LLM cost spike | Daily cost exceeds 2x 7-day average | Medium |
| Data staleness | Financial data older than configured threshold | Medium |
| Disk usage | PostgreSQL/S3 storage > 80% capacity | Medium |
| Quality gate degradation | Quality gate pass rate < 70% over 24h | Medium |
