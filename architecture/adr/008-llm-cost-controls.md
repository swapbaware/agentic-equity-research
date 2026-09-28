# ADR-008: LLM Cost Controls

## Status

Accepted

## Date

2026-09-28

## Context

The architecture review identified that LLM cost estimation was vague and no explicit cost controls existed. With 17 agents per research run, each making multiple LLM calls with tool use, costs can accumulate quickly. At scale (5000+ companies), uncontrolled LLM usage would be prohibitively expensive.

## Decision

Implement layered cost controls: per-agent token budgets, per-run cost tracking, per-user budget limits, and model selection optimization.

## Cost Structure

### Estimated Per-Research-Run Costs

| Agent Category | Agents | Est. Input Tokens | Est. Output Tokens |
|---------------|--------|-------------------|-------------------|
| Data extraction (Financial, Business Model) | 3 | 30K-60K | 5K-15K |
| Analysis (Moat, Industry, Competitor, Macro) | 5 | 40K-80K | 10K-30K |
| Synthesis (Bull/Bear/Risk/Thesis/Challenger) | 6 | 30K-60K | 10K-25K |
| Verification (Evidence, Quality Gates) | 2 | 10K-20K | 3K-8K |
| Monitoring (Portfolio) | 1 | 5K-10K | 2K-5K |
| **Total per run** | **17** | **115K-230K** | **30K-83K** |

### Cost Controls

#### 1. Per-Agent Token Budget

Each agent has a configured maximum token budget (input + output). If exceeded, the agent produces what it has and reports truncation.

```
financial_analysis_agent: max_tokens = 30_000
business_model_agent: max_tokens = 20_000
moat_agent: max_tokens = 25_000
synthesis_agent: max_tokens = 25_000
evidence_verification_agent: max_tokens = 15_000
...
```

#### 2. Per-Run Cost Tracking

Every `ResearchRun` record tracks:
- `total_input_tokens`: Sum across all agents
- `total_output_tokens`: Sum across all agents
- `total_cost_usd`: Calculated from provider pricing
- `cost_by_agent`: JSON breakdown per agent

#### 3. Per-User Budget Limits

Configurable daily/monthly LLM budget per user role:
- `analyst`: 100 research runs/month (configurable)
- `viewer`: 0 (read-only)
- `admin`: unlimited

Budget enforcement checked before initiating a research run.

#### 4. Model Selection Optimization

Not all agents need the most capable (expensive) model:

| Task Type | Recommended Model Tier | Rationale |
|-----------|----------------------|-----------|
| Data extraction, evidence retrieval | Fast/cheap (Haiku, GPT-4o-mini) | Structured extraction, not deep reasoning |
| Analysis, moat assessment, thesis | Capable (Sonnet/Opus, GPT-4o) | Requires nuanced reasoning |
| Evidence verification | Fast/cheap | Checklist validation, not reasoning |
| Research synthesis | Capable | Final report quality matters |

Model assignment is per-agent, configured in the research workflow definition.

#### 5. Caching

- **Embedding cache**: Embeddings for unchanged documents are not regenerated.
- **Screening cache**: Pre-computed financial metrics cached in Redis, not recomputed per request.
- **Agent result cache**: NOT cached (each run should reflect current data and potentially different model behavior). But intermediate tool results (financial calculations, ratio computations) are deterministic and cached.

## Consequences

- Token budgets may truncate agent output for complex companies — monitor truncation rate and adjust budgets
- Cost tracking adds a small overhead per LLM call but provides essential visibility
- Model selection optimization requires testing to verify cheaper models produce acceptable quality for extraction tasks
- Budget limits require a billing/usage tracking system in the user/auth layer
