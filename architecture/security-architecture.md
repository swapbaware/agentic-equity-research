# Security Architecture

## Overview

The platform handles financial data, user portfolios, and interacts with external LLM providers. Security is designed around defense-in-depth: authentication, authorization, input validation, agent sandboxing, secret management, and audit logging.

## Authentication & Authorization

### Authentication

- **Method**: OAuth 2.0 with JWT tokens
- **Provider**: Configurable (Auth0, Keycloak, or custom)
- **Token Handling**:
  - Access tokens: Short-lived (15 minutes)
  - Refresh tokens: Long-lived (7 days), stored server-side
  - Tokens stored in httpOnly, secure, SameSite=Strict cookies (frontend)
  - API access via Bearer token header

### Authorization

- **Model**: Role-Based Access Control (RBAC)
- **Roles**:
  - `viewer`: Read research reports, view dashboards
  - `analyst`: Run research, create watchlists, interact with AI chat
  - `admin`: User management, system configuration, provider management

### API Security

- All endpoints require authentication except health check
- Rate limiting per user and per endpoint
- CORS configured for frontend origin only
- Request size limits enforced
- HTTPS required in production

## Secret Management

### Principles

- No secrets in source code, ever
- No secrets in container images
- Secrets loaded from environment variables
- `.env` files never committed (enforced by `.gitignore`)
- `.env.example` documents required variables with placeholder values

### Secret Categories

| Secret | Storage | Rotation |
|--------|---------|----------|
| LLM API keys (Anthropic, OpenAI) | Environment variable | Provider-managed |
| Financial data API keys | Environment variable | Provider-managed |
| Database credentials | Environment variable | On infrastructure change |
| JWT signing key | Environment variable | 90-day rotation |
| Redis password | Environment variable | On infrastructure change |
| S3 credentials | Environment variable / IAM role | IAM role preferred |
| OAuth client secret | Environment variable | Provider-managed |

### Production Secret Management

- Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, or equivalent)
- Inject secrets as environment variables at container startup
- Never log secret values
- Mask secrets in error messages and stack traces

## Agent Security

### Prompt Injection Protection

External documents (annual reports, news articles, web content) are **untrusted input**. The platform must prevent prompt injection through retrieved content.

**Mitigations**:

1. **Input Isolation**: Retrieved document content is placed in clearly delimited data sections within prompts, never mixed with system instructions
2. **Output Validation**: Agent outputs are validated against expected Pydantic schemas. Free-text injection in structured fields is detected
3. **Tool Authorization**: Agents can only call tools explicitly granted to them. No agent has unrestricted tool access
4. **No Instruction Override**: System prompts include explicit instructions that retrieved content is data, not instructions

### Agent Sandboxing

| Control | Implementation |
|---------|---------------|
| Tool allowlist | Each agent has a defined set of permitted tools |
| Data access scope | Agents access data through tools, not direct DB queries |
| Output schema enforcement | Pydantic validation on all agent outputs |
| Execution timeout | Per-agent and per-tool timeout limits |
| Token budget | Maximum LLM tokens per agent invocation |
| Retry limits | Maximum retries per tool call |

### Tool Security

Every agent tool implements:

```
- Input validation (Pydantic schema)
- Authentication (API key or service credential)
- Authorization (tool-level permission check)
- Timeout (configurable per tool)
- Retry with backoff (max retries configurable)
- Audit logging (all invocations logged)
- Output sanitization
- Error handling (no raw errors to agent)
```

## Data Protection

### Financial Data

- All financial data sourced from providers is validated before storage
- Data provenance tracked (source, ingestion timestamp, validation status)
- No fabricated financial data enters the system — validation rejects data that fails schema or range checks
- User-entered data (watchlists, custom screens) isolated per user

### User Data

- User portfolios and watchlists are private by default
- Research chat history is per-user, not shared
- PII minimized — only email and display name stored
- Password handling delegated to OAuth provider (no local password storage)

### LLM Data

- Sensitive financial data sent to LLM providers is limited to what's necessary for the analysis task
- No user PII sent to LLM providers
- LLM API keys are per-deployment, not per-user
- LLM responses are validated and logged (structured logging, not raw dumps)

## Input Validation

### API Layer

- All request bodies validated with Pydantic models
- Path and query parameters typed and bounded
- File uploads: type checking, size limits, virus scanning for document ingestion
- SQL injection: prevented by SQLAlchemy ORM (parameterized queries)
- XSS: React's default escaping + Content-Security-Policy headers

### Financial Data Validation

- Numeric range checks (e.g., percentage values 0-100, no negative revenue)
- Balance sheet equation validation (Assets = Liabilities + Equity)
- Cross-statement consistency (Net Income on IS matches BS retained earnings change)
- Temporal consistency (no future-dated historical data)

### LLM Output Validation

- All agent outputs parsed against Pydantic schemas
- Financial values in agent outputs are cross-checked against stored data
- Claims marked as FACT are verified against evidence store
- Unsupported factual claims flagged by Evidence Verification Agent

## Audit & Logging

### Audit Events

| Event | Logged Fields |
|-------|--------------|
| User login/logout | user_id, timestamp, IP, method |
| Research run initiated | user_id, company_id, timestamp |
| Agent tool invocation | agent, tool, inputs (sanitized), timestamp, duration |
| LLM API call | provider, model, token_count, timestamp, duration |
| Data provider API call | provider, endpoint, timestamp, status |
| Data ingestion | source, records_count, validation_results |
| Thesis generation | company_id, research_run_id, timestamp |
| User watchlist change | user_id, action, company_id |
| Admin action | user_id, action, target, timestamp |

### Logging Standards

- Structured JSON logging (not free-text)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- No secrets or PII in logs
- Correlation IDs for request tracing (OpenTelemetry trace_id)
- Log retention: 90 days hot, 1 year cold storage

## Network Security

### Production

- All traffic over TLS 1.2+
- Internal services communicate over private network
- Database not exposed to public internet
- Redis not exposed to public internet
- S3 accessed via VPC endpoint or private network
- Rate limiting at API gateway level
- DDoS protection at edge (CDN/load balancer)

### Local Development

- HTTP acceptable for local development
- MinIO for local S3 (no cloud credentials needed)
- Docker network isolation between services

## Regulatory Considerations

### SEBI Compliance

- The platform is a research and decision-support tool, not a registered investment adviser
- All outputs include disclaimers distinguishing research from advice
- If commercialized, SEBI Research Analyst / Investment Adviser regulations must be reviewed with legal counsel
- SEBI RA regulations were amended as recently as August 2025 — the compliance layer must accommodate current regulations
- The platform does NOT generate personalized buy/sell recommendations

### Data Licensing

- Each financial data provider's terms of service must be reviewed
- Data redistribution restrictions must be respected
- API rate limits must be enforced
- Provider attribution displayed where required

## Dependency Security

- Dependencies pinned to exact versions in lock files
- Automated vulnerability scanning (Dependabot / Snyk)
- No known-vulnerable dependencies in production
- Regular dependency audit (monthly)
