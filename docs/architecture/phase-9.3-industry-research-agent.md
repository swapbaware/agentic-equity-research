# Phase 9.3 — Industry Research Agent: Implementation-Ready Architecture Synthesis

**Status**: Architecture Synthesis — READY FOR IMPLEMENTATION  
**Date**: 2026-09-30  
**Depends On**: Phase 7 (Research Run Infrastructure), Phase 8 (Company Research Agent), Phase 9.1 (Schema Migration), Phase 9.2 (Contracts)  
**Produces**: Complete specification for Phase 9 implementation (agent, tools, prompts, tests)

---

## Document Purpose

This document is an **implementation-ready architecture synthesis**. It reconciles the Phase 9 architecture specification (`docs/architecture/phase-9-industry-research-agent.md`) with the actual codebase as of commit `7395a37`, including:

- Phase 7 infrastructure (ORM models, state machines, repositories, services, schemas)
- Phase 8 Company Research Agent (agent, tools, prompts, exceptions)
- Phase 9.1 schema migration (006: `target_type`, nullable `company_id`, `industry_id` FK, XOR constraint)
- Phase 9.2 contracts (`IndustryResearchRequest`, `IndustryResearchConfig`, `INDUSTRY_FINDING_CATEGORIES`, `INDUSTRY_RESEARCH_STEPS`, tool I/O schemas)
- Provider abstractions (11 Protocol interfaces, `ProviderFactory`, error hierarchy, rate limiting)
- Domain models (Classification, Company, Evidence subsystem)
- All 9 ADRs

Every section cites the source file and line numbers in the current codebase. Where the Phase 9 architecture document describes intent and the codebase contains implementation, this document bridges the two.

---

## Table of Contents

1. [Objectives and Scope](#1-objectives-and-scope)
2. [Non-Goals](#2-non-goals)
3. [Design Principles](#3-design-principles)
4. [Agent Responsibilities](#4-agent-responsibilities)
5. [Company Research vs Industry Research Boundary](#5-company-research-vs-industry-research-boundary)
6. [Research Dimensions](#6-research-dimensions)
7. [Porter's Five Forces Boundary](#7-porters-five-forces-boundary)
8. [Finding Taxonomy](#8-finding-taxonomy)
9. [Finding Type Classification](#9-finding-type-classification)
10. [Evidence Model](#10-evidence-model)
11. [Temporal Model](#11-temporal-model)
12. [Source Hierarchy](#12-source-hierarchy)
13. [Industry Taxonomy Model](#13-industry-taxonomy-model)
14. [Request Contract](#14-request-contract)
15. [Workflow Definition](#15-workflow-definition)
16. [Tool Architecture](#16-tool-architecture)
17. [Provider Boundaries](#17-provider-boundaries)
18. [LLM Boundary](#18-llm-boundary)
19. [Structured Output Contracts](#19-structured-output-contracts)
20. [Token and Cost Controls](#20-token-and-cost-controls)
21. [Security Model](#21-security-model)
22. [Research Gap Handling](#22-research-gap-handling)
23. [Contradiction Handling](#23-contradiction-handling)
24. [ResearchRun Integration](#24-researchrun-integration)
25. [Data Model Impact](#25-data-model-impact)
26. [Concurrency Model](#26-concurrency-model)
27. [Research Reuse and Freshness](#27-research-reuse-and-freshness)
28. [Retry, Failure, and Resume](#28-retry-failure-and-resume)
29. [Observability](#29-observability)
30. [API and UI Boundary](#30-api-and-ui-boundary)
31. [Quality Gates](#31-quality-gates)
32. [Evaluation Strategy](#32-evaluation-strategy)
33. [Test Strategy](#33-test-strategy)
34. [Phase 8 Reuse Matrix](#34-phase-8-reuse-matrix)
35. [Shared Component Analysis](#35-shared-component-analysis)
36. [Multi-Agent Compatibility](#36-multi-agent-compatibility)
37. [Implementation Sequence](#37-implementation-sequence)
38. [Acceptance Criteria](#38-acceptance-criteria)
39. [Open Questions](#39-open-questions)
40. [Architectural Risks](#40-architectural-risks)
41. [ADR Analysis](#41-adr-analysis)
42. [Decision Summary](#42-decision-summary)
43. [Readiness Assessment](#43-readiness-assessment)
44. [Final Report](#44-final-report)

---

## 1. Objectives and Scope

### Primary Objective

Build an Industry Research Agent (Agent #4 in the 17-agent architecture) that produces evidence-backed, structured findings about Indian industries. The agent operates at the **industry level**, not the company level — it characterizes market structure, competitive dynamics, regulatory environment, growth drivers, and risks for an entire industry classification.

### Scope

The agent covers 12 research dimensions for any industry in the `Classification` table with `level=INDUSTRY`:

1. Market size (TAM/SAM estimation)
2. Growth drivers (historical and projected growth rates)
3. Industry structure (concentration, fragmentation, key players)
4. Entry barriers (Porter's Force: threat of new entrants)
5. Supplier power (Porter's Force)
6. Buyer power (Porter's Force)
7. Substitution risk (Porter's Force: threat of substitutes)
8. Competitive rivalry (Porter's Force: intensity of rivalry)
9. Regulatory environment (regulations, licensing, compliance, incentives)
10. Cyclicality (commodity exposure, business cycle sensitivity)
11. India's global position (competitive positioning globally)
12. Industry-level structural risks

### Downstream Consumers

| Consumer Agent | What It Reads |
|---|---|
| Competitive Moat Agent (#5) | `entry_barriers`, `supplier_power`, `buyer_power`, `substitution_risk` |
| Competitor Analysis Agent (#9) | `competitive_rivalry`, `industry_structure` |
| Valuation Agent (#10) | `market_size`, `growth_drivers`, `cyclicality` |
| Risk Agent (#11) | `industry_risk`, `regulatory_environment`, `substitution_risk` |
| Research Synthesis Agent (#16) | All 14 categories |

### Codebase References

- Architecture: `docs/architecture/phase-9-industry-research-agent.md` §1
- Agent #4 in agent list: `architecture/agent-architecture.md`
- Classification model: `backend/app/models/company.py` — `Classification` class with `level` field (SECTOR/INDUSTRY hierarchy)

---

## 2. Non-Goals

The Industry Research Agent explicitly does NOT:

1. **Perform company-specific analysis** — that is Phase 8's responsibility
2. **Compute valuation** — Agent #10 (Valuation)
3. **Assess competitive moat** — Agent #5 (Moat)
4. **Produce INDUSTRY_ATTRACTIVENESS scores** — scoring is downstream; this agent produces findings
5. **Perform deep competitor comparisons** — Agent #9 (Competitor Analysis)
6. **Conduct macro-economic analysis** — Agent #8 (Macro Economics, Phase 13)
7. **Generate bull/bear cases or thesis** — Agent #12 (Thesis), Agent #14 (Thesis Challenger)
8. **Modify the Classification table** — taxonomy management is administrative
9. **Provide buy/sell recommendations** — prohibited by CLAUDE.md §1
10. **Predict returns or claim multibagger status** — prohibited by CLAUDE.md §1

### Codebase References

- Non-goals list: `docs/architecture/phase-9-industry-research-agent.md` §2
- CLAUDE.md prohibitions: `CLAUDE.md` §1, §13

---

## 3. Design Principles

The agent inherits all 14 design principles from Phase 8 (`docs/architecture/phase-8-company-research-agent.md` §4):

**Inherited principles (1–9)**: Evidence before inference, source provenance, deterministic calculations, provider abstraction, least-privilege tools, explicit uncertainty, no certainty manufacturing, cost awareness, failure isolation.

**Inherited principles (10–14)**: Temporal correctness, contradictory evidence preservation, reproducibility, auditability, security by design.

**Industry-specific application**:

- **Evidence before inference** applies differently: industry data sources are more diffuse (government publications, industry bodies) vs. company filings. Tier 2 sources are the primary data source, not Tier 1.
- **Explicit uncertainty** is more prevalent: industry-level data varies in quality. The agent uses UNCERTAINTY findings freely rather than fabricating estimates.
- **Temporal correctness** has an additional consideration: government publications may be 3–6 months stale. The agent records actual `as_of_date` from the source, not the retrieval date.

### Codebase References

- Phase 8 principles: `docs/architecture/phase-8-company-research-agent.md` §4
- ADR-004 (Evidence Citations): `architecture/adr/adr-004-evidence-citations.md`
- ADR-003 (Decimal): `architecture/adr/adr-003-decimal-financial-calculations.md`

---

## 4. Agent Responsibilities

The Industry Research Agent has 7 responsibilities, each mapping to one or more workflow steps:

### Responsibility 1: Industry Validation (Step 1)

**Input**: `industry_id: UUID` from `IndustryResearchRequest`  
**Processing**: Query `Classification` table, verify `level=INDUSTRY`, retrieve industry name, sector context, company count  
**Output**: `ValidateIndustryOutput` with industry metadata  
**Failure**: `industry_id` not found or `level != INDUSTRY` → run FAILED immediately  
**Persistence**: Step status only

### Responsibility 2: Source Discovery (Step 2)

**Input**: Industry name, sector name, observation_date, optional document_types filter  
**Processing**: Query `SearchProvider` and `NewsProvider` for industry-relevant sources. Optionally query `MacroDataProvider` for industry indicators. Filter by `information_available_date <= observation_date`.  
**Output**: Ranked list of `SourceCandidate` records (up to `source_limit`, default 30)  
**Failure**: No sources found → step COMPLETED with empty list, run may produce mostly UNCERTAINTY findings  
**Persistence**: `ResearchArtifact` (INTERMEDIATE_STATE) with candidate list

### Responsibility 3: Document Retrieval (Step 3)

**Input**: Source candidates from Step 2  
**Processing**: Retrieve documents via `SearchProvider`/`NewsProvider`. Register each as `ResearchDocument` with `company_id=NULL`. Create `DocumentVersion`. Record `ResearchRunSource` for each accessed document.  
**Output**: Retrieved document content for each successfully fetched source  
**Failure**: Individual document failure → continue with remaining; all failures → step FAILED  
**Persistence**: `ResearchDocument`, `DocumentVersion`, `ResearchRunSource`

### Responsibility 4: Evidence Extraction (Step 4 — LLM)

**Input**: Retrieved document content (in `<retrieved_document>` XML tags)  
**Processing**: LLM extracts structured evidence (`EvidenceExtractionOutput`). Classify each claim as FACT, FINANCIAL_DATA, MANAGEMENT_STATEMENT, ANALYST_OPINION, or REGULATORY_FILING.  
**Output**: List of `EvidenceItem` records with type, claim, context, confidence  
**Failure**: Malformed LLM output → retry once (MAX_LLM_ATTEMPTS=2); still malformed → step FAILED with partial results  
**Persistence**: Evidence records via `persist_evidence` tool

### Responsibility 5: Industry Analysis (Step 5 — LLM)

**Input**: Extracted evidence, industry profile, company list  
**Processing**: LLM synthesizes evidence into structured findings across all 14 industry categories (excluding `research_gap` and `contradiction`, which are generated in Step 7). Each finding has `agent_name="industry_research_agent"`, `finding_type`, `category`, `content`, `confidence`, `evidence_ids`.  
**Output**: `FindingGenerationOutput` with structured findings  
**Failure**: Same retry semantics as Step 4  
**Persistence**: Findings via `persist_findings` tool

### Responsibility 6: Finding Validation (Step 6 — Deterministic)

**Input**: All findings from Step 5  
**Processing**: Verify evidence linkage for FACT findings, validate `FindingType` enum, enforce temporal constraints, validate category membership against `INDUSTRY_FINDING_CATEGORIES`.  
**Output**: `FindingValidationResult` with valid/rejected counts and issues  
**Failure**: Validation issues do not fail the step; findings are rejected individually  
**Persistence**: `ResearchArtifact` (ANALYSIS) with validation report

### Responsibility 7: Gap and Contradiction Analysis (Step 7 — LLM)

**Input**: Validated findings from Step 6  
**Processing**: (1) Deterministic gap check against `EXPECTED_INDUSTRY_DIMENSIONS` (12 dimensions) — missing dimensions produce UNCERTAINTY findings with category `research_gap`. (2) LLM contradiction identification — conflicting findings produce AI_INFERENCE findings with category `contradiction`.  
**Output**: Gap findings + contradiction findings  
**Failure**: LLM failure → deterministic gap analysis still runs; contradiction detection skipped  
**Persistence**: Gap and contradiction findings via `persist_findings` tool

### Codebase References

- Agent responsibilities: `docs/architecture/phase-9-industry-research-agent.md` §4
- Phase 8 pattern: `backend/app/agents/company_research/agent.py` (748 lines, 7 step methods)
- FindingValidationResult: `backend/app/agents/contracts.py:451-469`

---

## 5. Company Research vs Industry Research Boundary

The boundary between Agents #3 (Company Research, Phase 8) and #4 (Industry Research, Phase 9) is strict and enforced by schema:

| Dimension | Company Research Agent | Industry Research Agent |
|---|---|---|
| Target | Single company (`company_id`) | Industry classification (`industry_id`) |
| `target_type` | `"company"` | `"industry"` |
| Primary source tier | Tier 1 (company filings) | Tier 2 (government data, industry bodies) |
| Finding categories | 14 company categories | 14 industry categories |
| `agent_name` | `"company_research_agent"` | `"industry_research_agent"` |
| `ResearchDocument.company_id` | Set to company | `NULL` |
| Concurrency key | `research_lock:company:{company_id}` | `research_lock:industry:{industry_id}:{observation_date}` |

### Category Overlap

Three finding categories share names between agents: `growth_drivers`, `research_gap`, `contradiction`. Downstream consumers MUST filter by `agent_name` in addition to `category` when querying findings.

### Boundary Enforcement

- **Schema level**: XOR CHECK constraint `chk_research_run_target` on `ResearchRun` ensures a run targets exactly one of company or industry (`backend/alembic/versions/006_research_run_target_type.py`)
- **Application level**: `ResearchRunCreate` schema uses `@model_validator(mode="after")` to enforce XOR at the Pydantic layer (`backend/app/schemas/research_run.py`)
- **Category level**: `FINDING_CATEGORIES` (14 company) and `INDUSTRY_FINDING_CATEGORIES` (14 industry) are separate `frozenset` constants validated at finding persistence time

### Codebase References

- Phase 8 agent: `backend/app/agents/company_research/agent.py`
- Company finding categories: `backend/app/agents/contracts.py:25-40` — `FINDING_CATEGORIES`
- Industry finding categories: `backend/app/agents/contracts.py:81-98` — `INDUSTRY_FINDING_CATEGORIES`
- XOR constraint: `backend/alembic/versions/006_research_run_target_type.py`
- ResearchRunCreate validator: `backend/app/schemas/research_run.py`

---

## 6. Research Dimensions

### 12 Primary Research Dimensions

Each dimension maps to one finding category and defines the analytical scope for that aspect of industry research:

| # | Dimension | Finding Category | Description |
|---|---|---|---|
| 1 | Market size | `market_size` | TAM, SAM, current industry revenue in India |
| 2 | Growth drivers | `growth_drivers` | Historical and projected growth rates, demand drivers |
| 3 | Industry structure | `industry_structure` | Concentration (HHI proxy), fragmentation, key players, market shares |
| 4 | Entry barriers | `entry_barriers` | Capital requirements, regulatory barriers, brand loyalty, network effects |
| 5 | Supplier power | `supplier_power` | Input concentration, switching costs, supplier alternatives |
| 6 | Buyer power | `buyer_power` | Buyer concentration, price sensitivity, switching costs |
| 7 | Substitution risk | `substitution_risk` | Alternative products/services, technology disruption |
| 8 | Competitive rivalry | `competitive_rivalry` | Number of competitors, exit barriers, product differentiation |
| 9 | Regulatory environment | `regulatory_environment` | Licensing, compliance burden, government incentives, policy changes |
| 10 | Cyclicality | `cyclicality` | Business cycle sensitivity, commodity exposure, seasonal patterns |
| 11 | India global position | `india_global_position` | India's competitive advantage, export potential, global market share |
| 12 | Industry risk | `industry_risk` | Structural risks (technology disruption, regulatory change, input dependency) |

### 2 Meta-Dimensions (Generated by Step 7)

| # | Dimension | Finding Category | Generation |
|---|---|---|---|
| 13 | Research gaps | `research_gap` | Deterministic check against `EXPECTED_INDUSTRY_DIMENSIONS` |
| 14 | Contradictions | `contradiction` | LLM-assisted identification of conflicting evidence |

### Codebase References

- EXPECTED_INDUSTRY_DIMENSIONS: defined in Phase 9 architecture §19, to be implemented as a list constant
- INDUSTRY_FINDING_CATEGORIES: `backend/app/agents/contracts.py:81-98`

---

## 7. Porter's Five Forces Boundary

Porter's Five Forces analysis is distributed across three agents. Phase 9 owns the **industry-level structural analysis**:

### Phase 9 Responsibility (Industry Research Agent)

| Force | Category | Scope |
|---|---|---|
| Threat of new entrants | `entry_barriers` | Industry-wide barriers (capital, regulation, brand, network effects) |
| Supplier power | `supplier_power` | Industry-wide supplier dynamics (concentration, switching costs) |
| Buyer power | `buyer_power` | Industry-wide buyer dynamics (concentration, price sensitivity) |
| Threat of substitutes | `substitution_risk` | Industry-wide substitution risk (alternative technologies, products) |
| Competitive rivalry | `competitive_rivalry` | Industry-wide rivalry intensity (number of players, exit barriers) |

### What Phase 9 Does NOT Own

- **Company-specific moat** derived from Five Forces → Agent #5 (Competitive Moat Agent, Phase 10)
- **Company-specific competitive position** within the industry → Agent #9 (Competitor Analysis Agent)

### Concrete Boundary Examples

**Banking (Financial Services)**:
- Phase 9: "Indian banking has high entry barriers due to RBI licensing requirements (capital adequacy norms, CRR/SLR)" → `entry_barriers` / FACT
- Phase 10 (NOT Phase 9): "HDFC Bank's branch network in Tier 2/3 cities creates a distribution moat"

**IT Services (Information Technology)**:
- Phase 9: "Indian IT services industry has moderate buyer power — top 10 clients account for 30–40% of industry revenue" → `buyer_power` / FACT
- Phase 10 (NOT Phase 9): "TCS's client retention rate of 99%+ suggests high switching costs at the company level"

### Each Force = Structured Findings

Each force produces one or more findings with:
- Its own category (`entry_barriers`, `supplier_power`, etc.)
- Its own evidence linkage
- Its own FindingType (FACT, AI_INFERENCE, or UNCERTAINTY)
- Its own ConfidenceLevel

Forces are NOT a free-form LLM essay. Framework adherence is enforced by schema validation in Step 6.

### Queryability

All Five Forces findings for an industry:
```sql
SELECT * FROM research_finding
WHERE agent_name = 'industry_research_agent'
  AND category IN ('entry_barriers', 'supplier_power', 'buyer_power', 'substitution_risk', 'competitive_rivalry')
  AND research_run_id = :run_id;
```

### Codebase References

- Phase 9 architecture: `docs/architecture/phase-9-industry-research-agent.md` §16
- ResearchFinding model: `backend/app/models/research.py` — `ResearchFinding` class with `agent_name`, `category` fields

---

## 8. Finding Taxonomy

### 14 Industry Finding Categories

Defined in `backend/app/agents/contracts.py:81-98` as `INDUSTRY_FINDING_CATEGORIES: frozenset[str]`:

| # | Category | Description | Primary FindingType(s) |
|---|---|---|---|
| 1 | `market_size` | TAM, SAM, current industry revenue | FACT, AI_INFERENCE |
| 2 | `growth_drivers` | Growth rates and demand drivers (merged from former `growth_rate`) | FACT, MANAGEMENT_CLAIM, AI_INFERENCE |
| 3 | `industry_structure` | Concentration, fragmentation, key players, market shares | FACT, AI_INFERENCE |
| 4 | `entry_barriers` | Porter: threat of new entrants | FACT, AI_INFERENCE |
| 5 | `supplier_power` | Porter: supplier bargaining power | FACT, AI_INFERENCE |
| 6 | `buyer_power` | Porter: buyer bargaining power | FACT, AI_INFERENCE |
| 7 | `substitution_risk` | Porter: threat of substitutes | FACT, AI_INFERENCE |
| 8 | `competitive_rivalry` | Porter: intensity of rivalry | FACT, AI_INFERENCE |
| 9 | `regulatory_environment` | Regulations, licensing, compliance, government incentives | FACT, REGULATORY_FILING |
| 10 | `cyclicality` | Business cycle sensitivity, commodity exposure | FACT, AI_INFERENCE |
| 11 | `india_global_position` | India's competitive positioning globally | FACT, AI_INFERENCE |
| 12 | `industry_risk` | Industry-level structural risks | AI_INFERENCE, FACT |
| 13 | `research_gap` | Missing information (always type=UNCERTAINTY) | UNCERTAINTY |
| 14 | `contradiction` | Contradictory evidence (always type=AI_INFERENCE) | AI_INFERENCE |

### Category Validation

Finding persistence (Step 5, Step 7) validates each finding's `category` against `INDUSTRY_FINDING_CATEGORIES`. Findings with invalid categories are rejected by the `persist_findings` tool.

### Name Collision with Phase 8

Three categories overlap: `growth_drivers`, `research_gap`, `contradiction`. Resolution: `agent_name` field on `FindingItem` distinguishes origin. Downstream queries MUST include `agent_name` filter.

### Codebase References

- Industry categories: `backend/app/agents/contracts.py:81-98`
- Company categories: `backend/app/agents/contracts.py:45-62`
- FindingItem model: `backend/app/agents/contracts.py:356-369`

---

## 9. Finding Type Classification

Every finding is classified using the `FindingType` enum (`backend/app/models/enums.py`):

| FindingType | Definition | Evidence Required? | Industry Usage |
|---|---|---|---|
| `FACT` | Verifiable statement from a source document | Yes (enforced by Step 6) | Market size data, regulatory facts, historical growth rates |
| `CALCULATION` | Deterministic computation from facts | Yes (inputs must be traceable) | Not primary in Phase 9 (no financial ratio computation) |
| `MANAGEMENT_CLAIM` | Forward-looking statement by management | Yes (MANAGEMENT_STATEMENT evidence) | Rare at industry level (occasional industry body projections) |
| `ANALYST_OPINION` | Analyst's subjective assessment | Optional | Broker views on industry outlook |
| `AI_INFERENCE` | Synthesis or conclusion by the LLM | No | Five Forces assessment, structural analysis, contradictions |
| `ASSUMPTION` | Explicitly stated assumption | No | Assumptions underlying TAM/SAM estimation |
| `UNCERTAINTY` | Missing or unreliable data | No | Research gaps, unavailable macro data |

### Classification Rules

1. FACT requires evidence linkage — enforced by Step 6 validation (any FACT without evidence is rejected)
2. MANAGEMENT_CLAIM requires evidence of type `MANAGEMENT_STATEMENT` — if source evidence type mismatch, re-classify as AI_INFERENCE or reject
3. AI_INFERENCE does not require evidence linkage but should reference the evidence that informed it
4. UNCERTAINTY is used for research gaps and data unavailability — never fabricate data
5. FACT and MANAGEMENT_CLAIM must NEVER be conflated (CLAUDE.md §8 rule 4, §13 rule 10)

### Codebase References

- FindingType enum: `backend/app/models/enums.py` (7 values)
- EvidenceType enum: `backend/app/models/enums.py` (5 values: FACT, FINANCIAL_DATA, MANAGEMENT_STATEMENT, ANALYST_OPINION, REGULATORY_FILING)
- ConfidenceLevel enum: `backend/app/models/enums.py` (3 values: HIGH, MEDIUM, LOW)
- Evidence-finding linkage: `backend/app/models/research.py` — `research_finding_evidence` junction table

---

## 10. Evidence Model

### Evidence Chain

The Industry Research Agent reuses the Phase 4 evidence chain without modification:

```
Source → ResearchDocument → DocumentVersion → Evidence → research_finding_evidence → ResearchFinding
```

### Industry-Specific Considerations

- **`ResearchDocument.company_id = NULL`** for industry-level documents. Field is already nullable (`backend/app/models/research.py:60-63`). No schema change needed.
- **Source registration**: Industry sources (NASSCOM, SIAM, Ministry of Statistics) registered as `Source` records with appropriate `source_type` and `default_tier`.
- **EvidenceType usage at industry level**:
  - `FACT`: Verifiable industry statistics (market size, growth rate, player count)
  - `FINANCIAL_DATA`: Industry-level financial aggregates (sector revenue, average margins)
  - `MANAGEMENT_STATEMENT`: Rare — industry body executive statements
  - `ANALYST_OPINION`: Broker/analyst views on industry outlook
  - `REGULATORY_FILING`: Regulatory actions affecting the industry

### Three Quality Mechanisms (Reused)

1. **SourceTier** on `ResearchDocument`: TIER_1, TIER_2, TIER_3
2. **ConfidenceLevel** on `Evidence`: HIGH, MEDIUM, LOW
3. **SourceReliability** on `Source`: Computed reliability score (`backend/app/models/evidence.py`)

### Codebase References

- Evidence model: `backend/app/models/evidence.py` — Source, DocumentVersion, Claim, ClaimEvidence, SourceReliability
- ResearchDocument: `backend/app/models/research.py` — company_id nullable at lines 60-63
- research_finding_evidence junction: `backend/app/models/research.py` — junction table definition
- EvidenceType enum: `backend/app/models/enums.py`
- SourceTier enum: `backend/app/models/enums.py` (TIER_1, TIER_2, TIER_3)

---

## 11. Temporal Model

### Canonical Rule

**`information_available_date <= observation_date`**

Reused from Phase 8 without modification. Every finding must be based on information that was publicly available on or before the observation date.

### 6 Temporal Dimensions

| Concept | Definition | Where Stored |
|---|---|---|
| `observation_date` | "As of" date for the research | `ResearchRun.observation_date`, `ResearchFinding.observation_date` |
| `information_available_date` | Date information became publicly accessible | Derived from filing/publication dates |
| `source_publication_date` | Date source document was published | `ResearchFinding.source_publication_date` |
| `document_date` | Date of document content (may differ from publication) | `ResearchDocument.document_date` |
| `filing_date` | Date filing was submitted (making it public) | Provider-specific (not directly in Phase 9) |
| `execution_timestamps` | When steps executed (not used for eligibility) | `AgentExecution.started_at`, `completed_at` |

### Industry-Specific Temporal Considerations

1. **Government publications**: May be 3–6 months stale. Agent records actual `as_of_date` from the source, not the retrieval date.
2. **Industry body annual reports**: May cover prior year. The publication date determines eligibility, not the reporting period.
3. **Research reports with projections**: Classified as AI_INFERENCE or ASSUMPTION, never FACT.
4. **Temporal filter**: `publication_date <= observation_date` applied in source discovery (Step 2) and validated in finding validation (Step 6).

### Phase 7 Temporal Validation (Reused)

`ResearchRunService._validate_temporal_consistency()` and `_validate_publication_date_against_created_at()` in `backend/app/services/research_run.py` enforce:
- `finding.observation_date <= run.observation_date`
- `finding.source_publication_date <= finding.observation_date`
- `finding.source_publication_date <= finding.created_at`

### Codebase References

- Temporal validation: `backend/app/services/research_run.py` — `_validate_temporal_consistency()`, `_validate_publication_date_against_created_at()`
- Phase 8 temporal model: `docs/architecture/phase-8-company-research-agent.md` §9
- Phase 9 temporal model: `docs/architecture/phase-9-industry-research-agent.md` §8

---

## 12. Source Hierarchy

### Three-Tier Architecture (Reused from ADR-004)

The tier hierarchy is identical to Phase 8, but the **relative importance shifts**:

| Tier | Sources | Phase 8 Importance | Phase 9 Importance |
|---|---|---|---|
| TIER_1 | NSE/BSE filings, SEBI, RBI, company filings | **Primary** | Secondary |
| TIER_2 | Government data, industry bodies (NASSCOM, SIAM, IBEF, CII/FICCI) | Secondary | **Primary** |
| TIER_3 | Publications, news, research reports, broker reports | Supplementary | Supplementary |

### Source Type Mapping for Industry Research

| Source | `source_type` (SourceType enum) | `default_tier` | Example |
|---|---|---|---|
| NASSCOM | `INDUSTRY_BODY` | TIER_2 | IT Services industry data |
| SIAM | `INDUSTRY_BODY` | TIER_2 | Automotive production data |
| Ministry of Statistics (MoSPI) | `GOVERNMENT` | TIER_2 | Industrial production index |
| IBEF | `INDUSTRY_BODY` | TIER_2 | India Brand Equity Foundation reports |
| CII/FICCI | `INDUSTRY_BODY` | TIER_2 | Industry surveys |
| SEBI | `REGULATOR` | TIER_1 | Regulatory actions |
| RBI | `GOVERNMENT` | TIER_1 | Financial services data |
| Broker research | `RESEARCH` | TIER_3 | Analyst industry reports |
| Business press | `NEWS` | TIER_3 | Economic Times, Business Standard, Mint |

### Existing Enum Coverage

`DocumentType` enum in `backend/app/models/enums.py` already covers industry research needs:
- `GOVERNMENT_PUBLICATION` — for ministry/government data
- `RESEARCH_REPORT` — for broker/analyst reports
- `NEWS` — for business press

`SourceType` enum already includes `GOVERNMENT`, `INDUSTRY_BODY`, `REGULATOR`, `RESEARCH`. No new enum values required.

### Codebase References

- DocumentType enum: `backend/app/models/enums.py` (8 values including GOVERNMENT_PUBLICATION)
- SourceType enum: `backend/app/models/enums.py` (8 values including GOVERNMENT, INDUSTRY_BODY)
- SourceTier enum: `backend/app/models/enums.py` (TIER_1, TIER_2, TIER_3)
- ADR-004: `architecture/adr/adr-004-evidence-citations.md`

---

## 13. Industry Taxonomy Model

### Classification Hierarchy

The Industry Research Agent operates on the `Classification` model (`backend/app/models/company.py`):

```
ClassificationLevel.SECTOR (parent)
  └── ClassificationLevel.INDUSTRY (child, parent_id → sector)
        └── Company.industry_id FK → Classification.id
```

### Validation Rules

- Agent validates `Classification.level == ClassificationLevel.INDUSTRY`
- `industry_id` in `IndustryResearchRequest` must reference a valid `Classification` record
- Agent retrieves sector context via `parent_id` FK (sector name, sector code)
- Company count per industry retrieved for context

### Agent Does NOT Modify Taxonomy

The Industry Research Agent does NOT create, update, or delete Classification records. Taxonomy management is administrative. This is Decision D-14 in the Phase 9 architecture.

### Codebase References

- Classification model: `backend/app/models/company.py` — `Classification` class with `level`, `parent_id`, `code`, `name`
- ClassificationLevel enum: `backend/app/models/enums.py` — SECTOR, INDUSTRY
- Company.industry_id FK: `backend/app/models/company.py` — `Company` class

---

## 14. Request Contract

### IndustryResearchRequest

Defined in `backend/app/agents/contracts.py:605-614`:

```python
class IndustryResearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID                          # Classification UUID, level=INDUSTRY
    observation_date: date                          # Point-in-time anchor
    initiated_by: str = Field(min_length=1, max_length=200)  # Audit trail
    company_context_id: uuid.UUID | None = None     # Optional triggering company
    configuration: IndustryResearchConfig | None = None
```

### IndustryResearchConfig

Defined in `backend/app/agents/contracts.py:589-602`:

```python
class IndustryResearchConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=20_000, gt=0)
    token_warning_threshold: int = Field(default=16_000, gt=0)
    max_llm_attempts: int = Field(default=2, ge=1, le=3)
    document_types: list[DocumentType] | None = None
    source_limit: int = Field(default=30, ge=1, le=100)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    generation_model: str | None = None
    analysis_model: str | None = None
```

### Design Decisions

- `industry_id` not `sector_id` — agent operates at industry level, not sector
- `company_context_id` is optional — agent can run standalone or triggered by a company research run
- `source_limit` defaults to 30 (higher than Phase 8's implicit 20) because industry data is more diffuse
- `extraction_model`, `generation_model`, `analysis_model` allow per-step model tier selection per ADR-008

### Codebase References

- IndustryResearchRequest: `backend/app/agents/contracts.py:605-614`
- IndustryResearchConfig: `backend/app/agents/contracts.py:589-602`
- INDUSTRY_AGENT_TOKEN_BUDGET constant: `backend/app/agents/contracts.py:77` (20_000)
- INDUSTRY_AGENT_TOKEN_WARNING constant: `backend/app/agents/contracts.py:78` (16_000)
- MAX_LLM_ATTEMPTS constant: `backend/app/agents/contracts.py:71` (2)

---

## 15. Workflow Definition

### 7-Step Sequential Workflow

Defined in `backend/app/agents/contracts.py:617-663` as `INDUSTRY_RESEARCH_STEPS`:

| Order | Step Name | Step Type | Timeout | Uses LLM | Provider(s) |
|---|---|---|---|---|---|
| 1 | `industry_validation` | `deterministic` | 5s | No | None (DB query) |
| 2 | `industry_source_discovery` | `provider_call` | 30s | No | SearchProvider, NewsProvider, MacroDataProvider |
| 3 | `document_retrieval` | `provider_call` | 60s | No | SearchProvider |
| 4 | `evidence_extraction` | `llm_reasoning` | 120s | Yes | LLMProvider |
| 5 | `industry_analysis` | `llm_reasoning` | 120s | Yes | LLMProvider |
| 6 | `finding_validation` | `deterministic` | 10s | No | None |
| 7 | `gap_contradiction_analysis` | `llm_reasoning` | 60s | Yes | LLMProvider |

### Step Execution Pattern

Steps execute **sequentially** — each depends on the prior step's output. The only concurrency is **within** Step 3 (bounded document retrieval, default 5 concurrent retrievals via `asyncio.gather()`).

### Step Type Constants

Defined in `backend/app/agents/contracts.py:518-520`:
- `STEP_TYPE_DETERMINISTIC = "deterministic"`
- `STEP_TYPE_PROVIDER_CALL = "provider_call"`
- `STEP_TYPE_LLM_REASONING = "llm_reasoning"`

### Phase 8 Comparison

| Phase 8 Step | Phase 9 Step | Difference |
|---|---|---|
| `company_validation` | `industry_validation` | Different target, different tool |
| `source_discovery` | `industry_source_discovery` | Different providers (Search+News vs Filing+Financial) |
| `document_retrieval` | `document_retrieval` | Same step name, similar logic |
| `evidence_extraction` | `evidence_extraction` | Same step name, different prompts |
| `finding_generation` | `industry_analysis` | Different step name, different categories |
| `finding_validation` | `finding_validation` | Same step name, different category set |
| `gap_contradiction_analysis` | `gap_contradiction_analysis` | Same step name, different expected dimensions |

### Codebase References

- INDUSTRY_RESEARCH_STEPS: `backend/app/agents/contracts.py:617-663`
- COMPANY_RESEARCH_STEPS: `backend/app/agents/contracts.py:535-581`
- StepDefinition model: `backend/app/agents/contracts.py:523-533`
- Phase 8 step execution: `backend/app/agents/company_research/agent.py`

---

## 16. Tool Architecture

### 8 Tools

The Industry Research Agent uses exactly 8 tools — 5 new, 3 reused from Phase 8:

#### Tool 1: `validate_industry` (NEW — Deterministic — Step 1)

**Input** (`ValidateIndustryInput`):
```python
industry_id: uuid.UUID
```

**Output** (`ValidateIndustryOutput`):
```python
industry_id: uuid.UUID
industry_name: str
industry_code: str | None
sector_id: uuid.UUID | None
sector_name: str | None
sector_code: str | None
company_count: int
```

**Implementation**: Query `Classification` table, verify `level=INDUSTRY`, join `parent_id` for sector context, count companies.

#### Tool 2: `discover_industry_sources` (NEW — Provider Call — Step 2)

**Input** (`DiscoverIndustrySourcesInput`):
```python
industry_name: str
sector_name: str
observation_date: date
document_types: list[DocumentType] | None = None
limit: int = Field(default=30, ge=1, le=100)
```

**Output** (`DiscoverIndustrySourcesOutput`):
```python
candidates: list[SourceCandidate]  # Reused contract from Phase 8
```

**Implementation**: Query `SearchProvider` with industry-contextualized queries + `NewsProvider` for sector news. Filter by `publication_date <= observation_date`. Rank by source tier.

#### Tool 3: `retrieve_document` (REUSED from Phase 8 — Provider Call — Step 3)

Uses `RetrieveDocumentInput` / `RetrieveDocumentOutput` from `backend/app/agents/contracts.py:208-221`. Identical contract and behavior.

#### Tool 4: `search_industry_data` (NEW — Provider Call — Steps 2/3)

**Input** (`SearchIndustryDataInput`):
```python
query: str = Field(min_length=1, max_length=500)
industry_name: str
observation_date: date
num_results: int = Field(default=10, ge=1, le=50)
```

**Output** (`SearchIndustryDataOutput`):
```python
results: list[IndustrySearchResult]
```

**`IndustrySearchResult`**:
```python
title: str
url: str
snippet: str
source_type: str
published_date: date | None
```

**Implementation**: Wraps `SearchProvider.search()` with industry-contextualized queries (e.g., `"{industry_name} India market size TAM"`).

#### Tool 5: `get_macro_indicators` (NEW — Provider Call — Step 2)

**Input** (`GetMacroIndicatorsInput`):
```python
indicator_ids: list[str] = Field(min_length=1, max_length=20)
start_date: date | None = None
end_date: date | None = None
```

**Output** (`GetMacroIndicatorsOutput`):
```python
indicators: list[MacroIndicatorResult]
```

**`MacroIndicatorResult`**:
```python
indicator_id: str
indicator_name: str
latest_value: Decimal
as_of_date: date
unit: str
source: str
```

**Implementation**: Wraps `MacroDataProvider`. Graceful degradation — if provider unavailable, returns empty list and agent produces UNCERTAINTY findings.

#### Tool 6: `get_industry_companies` (NEW — Deterministic — Steps 2/5)

**Input** (`GetIndustryCompaniesInput`):
```python
industry_id: uuid.UUID
limit: int = Field(default=20, ge=1, le=100)
```

**Output** (`GetIndustryCompaniesOutput`):
```python
companies: list[IndustryCompanyRecord]
total_count: int
```

**`IndustryCompanyRecord`**:
```python
company_id: uuid.UUID
name: str
nse_symbol: str | None
bse_code: str | None
market_cap: Decimal | None
is_active: bool
```

**Implementation**: Query `Company` table filtered by `industry_id`, ordered by `market_cap DESC`.

#### Tool 7: `persist_evidence` (REUSED from Phase 8 — Persistence — Step 4)

Uses `PersistEvidenceInput` / `PersistEvidenceOutput` from `backend/app/agents/contracts.py:338-349`. Identical contract.

#### Tool 8: `persist_findings` (REUSED from Phase 8 — Persistence — Steps 5/7)

Uses `PersistFindingsInput` / `PersistFindingsOutput` from `backend/app/agents/contracts.py:380-392`. **Important**: `FindingItem.agent_name` has a schema default of `"company_research_agent"` via the shared `AGENT_NAME` constant (`contracts.py:70`). The Industry Research Agent MUST explicitly pass `agent_name=INDUSTRY_AGENT_NAME` (`"industry_research_agent"`) when constructing `FindingItem` instances. This is a construction-time override — the shared `FindingItem` schema default is NOT changed for Phase 9.

### Tool Allowlisting

The agent has access to EXACTLY these 8 tools. No external invocation, no arbitrary URL access, no shell commands.

### Codebase References

- Reused tool contracts: `backend/app/agents/contracts.py:208-221` (retrieve_document), `338-349` (persist_evidence), `380-392` (persist_findings)
- SourceCandidate: `backend/app/agents/contracts.py:187-200`
- Phase 8 tools implementation: `backend/app/agents/company_research/tools.py` (399 lines)
- FindingItem with agent_name: `backend/app/agents/contracts.py:356-369`

---

## 17. Provider Boundaries

### 4 Provider Protocols Used

| Protocol | Phase 9 Role | Status | Fallback |
|---|---|---|---|
| `SearchProvider` | NEW — web search for industry data | Mock only | Agent degrades (fewer sources) |
| `MacroDataProvider` | NEW — limited, non-blocking | Mock only | Agent produces UNCERTAINTY findings |
| `NewsProvider` | Reused — sector/industry news | Mock only | Agent degrades (fewer sources) |
| `LLMProvider` | Reused — evidence extraction, analysis | Mock for tests | Required for production |

### 7 Provider Protocols NOT Used

| Protocol | Reason |
|---|---|
| `CorporateFilingsProvider` | Company-specific (Phase 8 only) |
| `FinancialDataProvider` | Company-specific financial statements |
| `TranscriptProvider` | Company-specific earnings calls |
| `MarketDataProvider` | Company-specific market data |
| `ShareholdingProvider` | Company-specific shareholding |
| `CorporateActionsProvider` | Company-specific corporate actions |
| `EmbeddingProvider` | Deferred to future phase |

### Provider Injection

```python
class IndustryResearchAgent:
    def __init__(
        self,
        *,
        session: AsyncSession,
        search_provider: SearchProvider,
        macro_provider: MacroDataProvider,
        news_provider: NewsProvider,
        llm_provider: LLMProvider,
        run_service: ResearchRunService,
    ) -> None: ...
```

Business logic NEVER imports concrete providers directly (CLAUDE.md §7 rule 3). All injection through constructor parameters typed as Protocol interfaces.

### MacroDataProvider Boundary

**Limited, non-critical dependency.** Phase 9 uses it for industry-specific indicators ONLY:
- Industrial Production Index (IIP) for manufacturing
- Credit growth for banking
- Auto sales SIAM data for automotive

Phase 13 (Macro Economics Agent #8) owns full macro analysis. Phase 9 does NOT perform macro analysis.

Graceful degradation: if `MacroDataProvider.check_health()` fails or mock returns empty → UNCERTAINTY findings for macro-dependent dimensions → run continues.

### SearchProvider Boundary

**Direct dependency.** Phase 9 requires `SearchProvider` for source discovery. Tool 2 (`discover_industry_sources`) and Tool 4 (`search_industry_data`) both wrap `SearchProvider.search()`.

Mock provider sufficient for development/testing. Concrete implementation (Google Custom Search, Bing Search, or SerpAPI) needed for production.

### Codebase References

- Provider interfaces: `backend/app/providers/interfaces.py` — 11 `@runtime_checkable` Protocol classes
- ProviderFactory: `backend/app/providers/factory.py` — `_SIMPLE_REGISTRY`, typed accessors, `register()`
- ProviderBase: `backend/app/providers/base.py` — retry, rate limiting, timeout, error handling
- Provider errors: `backend/app/providers/errors.py` — ProviderError hierarchy
- Provider config: `backend/app/providers/config.py` — ProviderSettings with slot defaults

---

## 18. LLM Boundary

### What the LLM Does (3 Tasks)

| Task | Step | Input | Output Schema | Model Tier |
|---|---|---|---|---|
| Evidence extraction | 4 | Document content in `<retrieved_document>` tags | `EvidenceExtractionOutput` | Fast/cheap (Haiku-tier) |
| Finding generation | 5 | Evidence + industry profile + company list | `FindingGenerationOutput` | Capable (Sonnet/Opus-tier) |
| Contradiction identification | 7 | Validated findings | Contradiction findings | Fast/cheap (Haiku-tier) |

### What the LLM Does NOT Do

1. **Financial calculations** — no CAGR, ratio computation, market size arithmetic. Deterministic code handles calculations.
2. **Data fabrication** — if data unavailable, report UNCERTAINTY. LLM cannot invent financial data.
3. **Source retrieval** — no web access. LLM operates on pre-retrieved, sanitized content only.
4. **Finding validation** — deterministic code in Step 6.
5. **Gap identification** — deterministic code checks against `EXPECTED_INDUSTRY_DIMENSIONS`.
6. **Category assignment validation** — deterministic code validates against `INDUSTRY_FINDING_CATEGORIES`.

### LLM Configuration

- **Temperature**: 0.0 (structured output requires determinism)
- **Max tokens**: 4096 (LLMProvider default)
- **Retry on malformed output**: 1 retry, max 2 total attempts (`MAX_LLM_ATTEMPTS=2`)
- **Model tier selection**: Configured via `IndustryResearchConfig.extraction_model`, `generation_model`, `analysis_model`

### Prompt Architecture

Prompts reside in `backend/app/agents/industry_research/prompts.py` (TO BE CREATED):
- `evidence_extraction_prompt()` — follows Phase 8 pattern from `backend/app/agents/company_research/prompts.py:94`
- `industry_analysis_prompt()` — industry-specific synthesis prompt
- `gap_contradiction_prompt()` — follows Phase 8 pattern

All prompts follow Phase 8 security rules:
- Content in `<retrieved_document>` tags
- System prompt declares content is data, not instructions
- Structured output schema enforced via `response_schema` parameter

### Codebase References

- Phase 8 prompts: `backend/app/agents/company_research/prompts.py` (94 lines)
- SYSTEM_PREAMBLE with prompt injection defense: `backend/app/agents/company_research/prompts.py`
- _wrap_document: `backend/app/agents/company_research/prompts.py`
- EvidenceExtractionOutput: `backend/app/agents/contracts.py:412-417`
- FindingGenerationOutput: `backend/app/agents/contracts.py:438-443`
- LLMProvider Protocol: `backend/app/providers/interfaces.py`

---

## 19. Structured Output Contracts

### Evidence Extraction Output (Reused)

`EvidenceExtractionOutput` from `backend/app/agents/contracts.py:412-417`:
```python
class EvidenceExtractionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidences: list[ExtractedEvidence]
```

Each `ExtractedEvidence` (`backend/app/agents/contracts.py:400-410`):
```python
class ExtractedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_type: EvidenceType
    claim: str = Field(min_length=1)
    context: str | None = None
    page_or_section: str | None = Field(default=None, max_length=200)
    confidence: ConfidenceLevel
```

### Finding Generation Output (Reused)

`FindingGenerationOutput` from `backend/app/agents/contracts.py:438-443`:
```python
class FindingGenerationOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    findings: list[GeneratedFinding]
```

Each `GeneratedFinding` (`backend/app/agents/contracts.py:425-435`):
```python
class GeneratedFinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    finding_type: FindingType
    category: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    confidence: ConfidenceLevel
    source_publication_date: date | None = None
    evidence_indices: list[int] | None = None
```

### Finding Validation Result (Reused)

`FindingValidationResult` from `backend/app/agents/contracts.py:461-469`:
```python
class FindingValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_findings: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    issues: list[FindingValidationIssue]
```

### All Models Frozen

Every structured output model uses `ConfigDict(frozen=True)` — immutable after creation. This prevents accidental mutation and ensures reproducibility.

### Malformed Output Handling

1. LLM output fails Pydantic validation → retry once (attempt 2)
2. Still fails → step FAILED with partial results
3. Partial results from earlier steps are preserved
4. Run transitions to PARTIAL (not FAILED) if ≥5 steps completed

---

## 20. Token and Cost Controls

### Budget Constants

From `backend/app/agents/contracts.py:77-79`:
```python
INDUSTRY_AGENT_TOKEN_BUDGET: int = 20_000
INDUSTRY_AGENT_TOKEN_WARNING: int = 16_000
INDUSTRY_AGENT_NAME: str = "industry_research_agent"
```

Shared constant from `backend/app/agents/contracts.py:71`:
```python
MAX_LLM_ATTEMPTS: int = 2
```

### Why 20,000 Not 30,000

Phase 8's `AGENT_TOKEN_BUDGET = 30_000` is the Company Research Agent (#3) budget (`backend/app/agents/contracts.py:68-70`). The architecture document (`architecture/agent-architecture.md`) assigns 20,000 to Industry Analysis Agent (#4). Industry reports are typically shorter per-document; more documents but less per-document extraction cost. The aggregate run budget across all 17 agents is ~325,000 tokens.

### Budget Distribution Across Steps

| Step | Input Tokens (est.) | Output Tokens (est.) | Total (est.) |
|---|---|---|---|
| 4 (Evidence extraction) | 6,000–10,000 | 1,000–3,000 | 7,000–13,000 |
| 5 (Industry analysis) | 4,000–6,000 | 2,000–4,000 | 6,000–10,000 |
| 7 (Contradiction analysis) | 1,000–2,000 | 500–1,500 | 1,500–3,500 |
| **Total** | **11,000–18,000** | **3,500–8,500** | **14,500–26,500** |

### Budget Enforcement (TokenBudget Class)

Reused from Phase 8. `TokenBudget` class (`backend/app/agents/contracts.py:477-512`):
- `budget`: Total token limit (default from config, 20,000)
- `warning_threshold`: Warning trigger (default 16,000)
- `is_warning`: True when `total_tokens >= warning_threshold`
- `is_exhausted`: True when `total_tokens >= budget`
- `utilization_pct`: `Decimal` percentage with 2 decimal places
- `record_usage(input_tokens, output_tokens)`: Cumulative tracking

### Exhaustion Behavior

When budget exhausted:
1. Complete current step with partial output
2. Skip remaining LLM steps
3. Run deterministic finding validation (Step 6)
4. Run deterministic-only gap analysis (no LLM contradiction analysis)
5. Mark run as PARTIAL (not FAILED)
6. `error_summary = "Token budget exhausted (20000 tokens)"`

### Budget Monitoring

- Metric: `industry_research.token_utilization_pct` — histogram of budget utilization per run
- Alert: If ≥30% of runs hit the budget ceiling, increase to 25,000

### Codebase References

- TokenBudget class: `backend/app/agents/contracts.py:477-512`
- INDUSTRY_AGENT_TOKEN_BUDGET: `backend/app/agents/contracts.py:77`
- INDUSTRY_AGENT_TOKEN_WARNING: `backend/app/agents/contracts.py:78`
- ADR-008: `architecture/adr/adr-008-cost-controls.md`

---

## 21. Security Model

### 10 Threat Vectors (Reused from Phase 8)

All Phase 8 threat vectors and mitigations apply without modification:

| # | Threat | Mitigation |
|---|---|---|
| 1 | Prompt injection via retrieved documents | Content in `<retrieved_document>` tags; system prompt declares data, not instructions |
| 2 | LLM output schema violation | Pydantic validation before persistence |
| 3 | Unauthorized tool access | Exactly 8 tools allowlisted |
| 4 | Write scope violation | Write tools scoped to current run's Evidence/Finding/Step/Execution/Source/Artifact |
| 5 | Token budget abuse | Hard budget enforcement (20,000) |
| 6 | Provider rate limit abuse | Redis-backed token bucket rate limiter via ProviderBase |
| 7 | Timeout abuse | Per-step timeouts (5s–120s) |
| 8 | Content injection (XSS/SQL) | Text-extracted, stripped of executable content, HTML sanitized |
| 9 | Secret exposure | API keys injected at construction, never in prompts; masked in logs |
| 10 | Audit trail gaps | ResearchRunStep + AgentExecution for every operation |

### Industry-Specific Additions

- **SearchProvider results**: Inherently less controlled than company filings (government PDFs, industry body reports from various sources). Same `<retrieved_document>` tagging and Pydantic validation applied.
- **MacroDataProvider results**: Structured numeric data (lower injection risk). Validated against Pydantic models with `Decimal` types.
- **Higher source volume**: More sources from more providers than Phase 8 → each logged as `ResearchRunSource`.

### Security Invariant

**"DOCUMENT CONTENT MUST NEVER MODIFY AGENT INSTRUCTIONS."**

Enforced via: architectural separation (content ≠ instructions), schema validation (output conforms to expected structure), tool allowlisting (8 tools only), write scope restriction (own run only).

### Codebase References

- Phase 8 security model: `docs/architecture/phase-8-company-research-agent.md` §20
- SYSTEM_PREAMBLE: `backend/app/agents/company_research/prompts.py`
- CLAUDE.md security: `CLAUDE.md` §5

---

## 22. Research Gap Handling

### Deterministic Gap Detection

Step 7 includes a deterministic check against `EXPECTED_INDUSTRY_DIMENSIONS` (12 dimensions, excluding `research_gap` and `contradiction`):

```python
EXPECTED_INDUSTRY_DIMENSIONS: list[str] = [
    "market_size", "growth_drivers", "industry_structure", "entry_barriers",
    "supplier_power", "buyer_power", "substitution_risk", "competitive_rivalry",
    "regulatory_environment", "cyclicality", "india_global_position", "industry_risk",
]
```

For each dimension with ZERO findings from Step 5, the agent generates:
- `finding_type = FindingType.UNCERTAINTY`
- `category = "research_gap"`
- `content = "No evidence found for {dimension} in {industry_name}"`
- `confidence = ConfidenceLevel.LOW`
- `evidence_ids = []` (no evidence by definition)

### Industry-Specific Gap Patterns

- **Unorganized sectors** (e.g., agriculture, small-scale manufacturing): Limited formal data → more UNCERTAINTY findings expected
- **Nascent industries** (e.g., EV components, renewable energy): Rapidly evolving → data may be stale or contradictory
- **Government-dominated industries** (e.g., defense, railways): Data access restricted → gaps are structural, not researchable

### No Fabrication Rule

CLAUDE.md §9 rule 6 and §13 rule 1: "If data is unavailable, report unavailable. Validation rejects schema/range failures." and "Never allow an LLM to invent financial data."

The agent NEVER fills gaps with fabricated data. UNCERTAINTY findings are the correct response to missing information.

---

## 23. Contradiction Handling

### Principle: Preserve Both Sides

Phase 9 inherits Phase 8's contradiction handling principle: **never collapse contradictory evidence into a single conclusion**. Both findings are persisted with separate evidence linkage.

### Mechanism

1. **Detection** (Step 7, LLM-assisted): LLM identifies findings that contradict each other (e.g., conflicting market size estimates)
2. **Preservation**: Both original findings remain in the database with their own evidence linkage
3. **Contradiction finding**: A new finding of type `AI_INFERENCE` with category `"contradiction"` is generated, describing the conflict
4. **No resolution**: The Industry Research Agent does NOT resolve contradictions. Downstream agents (Research Synthesis Agent #16) make the judgment.

### Common Industry Contradiction Patterns

| Contradiction Type | Example |
|---|---|
| Market size disagreements | NASSCOM estimates IT services TAM at $300B vs. McKinsey at $250B |
| Growth rate conflicts | Government projects 8% growth vs. industry body projects 12% |
| Regulatory interpretation | Different sources interpret PLI scheme impact differently |
| Competitive dynamics | Conflicting assessments of market concentration |

### Codebase References

- Phase 8 contradiction handling: `docs/architecture/phase-8-company-research-agent.md` §14
- Phase 9 contradiction handling: `docs/architecture/phase-9-industry-research-agent.md` §18

---

## 24. ResearchRun Integration

### Decision: Option A (Implemented in Phase 9.1)

The ResearchRun model supports industry research through:
- `target_type`: `"company"` (default) or `"industry"` — NOT NULL with server_default `"company"`
- `company_id`: Now nullable (was NOT NULL before migration 006)
- `industry_id`: New FK to `Classification(id)`
- XOR CHECK constraint `chk_research_run_target` ensuring mutual exclusivity

### Critical Distinction: `target_type` vs `run_type`

**`target_type`** is the target discriminator: "company" or "industry". It identifies WHAT is being researched.

**`run_type`** retains its existing execution-mode semantics: FULL, INCREMENTAL, THESIS_UPDATE, MONITORING, etc. It identifies HOW the research is executed.

These fields are orthogonal. `run_type` must NOT be used as a target discriminator. This was Decision D-17, resolved in the second reconciliation.

### ResearchRun Lifecycle (Unchanged)

```
CREATED → QUEUED → RUNNING → COMPLETED / FAILED / PARTIAL / CANCELLED
```

State machine: `backend/app/models/state_machines.py` — `VALID_RUN_TRANSITIONS`, `validate_run_transition()`

Active statuses: CREATED, QUEUED, RUNNING  
Terminal statuses: COMPLETED, FAILED, PARTIAL, CANCELLED

### Service Layer Integration

`ResearchRunService` (`backend/app/services/research_run.py`, 646 lines):

- `initiate_run()`: Already branches on `target_type`:
  - `"company"` → `get_active_run(company_id)` to check for existing active run
  - `"industry"` → `get_active_industry_run(industry_id, observation_date)` to check for existing active run
- `complete_run()`, `fail_run()`, `cancel_run()`: Unchanged — work on `ResearchRun.id`
- `record_step_*()`, `record_execution_*()`: Unchanged — reference `ResearchRun.id`, not target
- `update_run_aggregates()`: Unchanged — aggregates token usage across all AgentExecution records

### New Service Methods Required

- `get_reusable_run(target_type, target_id, observation_date, *, max_age_hours=24, allow_partial=False) -> ResearchRun | None` — checks freshness policy and returns a reusable COMPLETED run if one exists

### Repository Layer

`ResearchRunRepository` (`backend/app/repositories/research_run.py`, 484 lines):

- `get_active_industry_run(industry_id, observation_date)`: Already implemented — filters on `target_type=="industry"`, `industry_id`, `observation_date`, active statuses
- `get_by_industry(industry_id)` and `get_current_for_industry(industry_id)`: TO BE ADDED (parallel to existing `get_by_company()` and `get_current_for_company()`)

### Codebase References

- ResearchRun model: `backend/app/models/research.py` — with `target_type`, `industry_id`, `company_id` (nullable)
- Migration 006: `backend/alembic/versions/006_research_run_target_type.py` (147 lines)
- State machines: `backend/app/models/state_machines.py`
- ResearchRunService: `backend/app/services/research_run.py`
- ResearchRunRepository: `backend/app/repositories/research_run.py`
- ResearchRunCreate schema: `backend/app/schemas/research_run.py` — `@model_validator` enforcing XOR

---

## 25. Data Model Impact

### Schema Changes Already Applied (Phase 9.1 — Migration 006)

| Change | Status | Migration Line |
|---|---|---|
| `ResearchRun.target_type` VARCHAR NOT NULL DEFAULT 'company' | APPLIED | 006 |
| `ResearchRun.company_id` made nullable | APPLIED | 006 |
| `ResearchRun.industry_id` FK to `classification(id)` | APPLIED | 006 |
| CHECK `chk_research_run_target` (XOR) | APPLIED | 006 |
| Partial index `ix_research_run_industry` | APPLIED | 006 |
| Index `ix_research_run_target_type` | APPLIED | 006 |

### Schema Elements NOT Modified

| Element | Status | Reason |
|---|---|---|
| `run_type` values | **UNCHANGED** | Retains execution-mode semantics (D-17) |
| `ResearchDocument.company_id` | Already nullable | Lines 60-63 of `research.py` |
| `IndustryData` model | EXISTS, no change | `research_run_id` FK deferred (D-18) |
| `Classification` model | EXISTS, no change | Agent does not modify taxonomy (D-14) |
| All required enums | EXIST | No additions needed |

### Models Requiring No Changes for Phase 9

| Model | Why |
|---|---|
| `ResearchRunStep` | References `ResearchRun.id`, not company/industry |
| `AgentExecution` | References `ResearchRunStep.id` |
| `ResearchFinding` | References `ResearchRun.id` + uses `agent_name` discriminator |
| `ResearchArtifact` | References `ResearchRun.id` |
| `ResearchRunSource` | References `ResearchRun.id` |
| `Evidence` | Linked via `research_finding_evidence` junction |
| `ResearchDocument` | `company_id` already nullable |

### Codebase References

- Migration 006: `backend/alembic/versions/006_research_run_target_type.py`
- ResearchRun model: `backend/app/models/research.py`
- IndustryData model: `backend/app/models/company.py` or domain models
- Classification model: `backend/app/models/company.py`

---

## 26. Concurrency Model

### Three Explicitly Separated Mechanisms

Resolved from Open Question OQ-5 during the second reconciliation. The three mechanisms are:

1. **Concurrency Lock** — prevents simultaneous runs
2. **Research Reuse Identity** — determines if two requests ask the same question
3. **Freshness Policy** — determines if a completed result is still usable

These are separable, independently evolvable mechanisms — NOT a single conflated check.

### Mechanism 1: Concurrency Lock

**Purpose**: Prevent two runs for the same research question from executing simultaneously.

**Implementation**: Redis advisory lock + application-level active-run check.

| Target Type | Lock Key Pattern | Lock Scope |
|---|---|---|
| Company | `research_lock:company:{company_id}` | company_id only |
| Industry | `research_lock:industry:{industry_id}:{observation_date}` | industry_id + observation_date |

**Intentional asymmetry**: Company lock does NOT include `observation_date` (matches ADR-007's existing pattern). Industry lock DOES include `observation_date` because different observation dates access strictly different temporal windows — concurrent execution is safe.

**Scope**: Covers all active statuses (CREATED, QUEUED, RUNNING). A run in any active status holds the lock.

### Application-Level Active Run Check

Before acquiring the lock, `ResearchRunService.initiate_run()` checks for existing active runs:
- Company: `get_active_run(company_id)` — `backend/app/repositories/research_run.py`
- Industry: `get_active_industry_run(industry_id, observation_date)` — already filters on `target_type=="industry"`, `industry_id`, `observation_date`, active statuses

### Codebase References

- get_active_industry_run: `backend/app/repositories/research_run.py`
- ResearchRunService.initiate_run: `backend/app/services/research_run.py`
- ADR-007: `architecture/adr/adr-007-failure-resilience.md`
- Phase 9 concurrency: `docs/architecture/phase-9-industry-research-agent.md` §35

---

## 27. Research Reuse and Freshness

### Mechanism 2: Research Reuse Identity

**Purpose**: Determine if two research requests ask the same question.

**Identity tuple**: `(target_type, target_id, observation_date)`

- For industry: `("industry", industry_id, observation_date)`
- For company: `("company", company_id, observation_date)`

**NOT part of identity**: agent_version, prompt_version, tool_versions, configuration, run_type. Two requests with identical identity tuples are asking the same research question regardless of configuration differences.

### Mechanism 3: Freshness Policy

**Purpose**: Determine if a completed result is still usable.

**Parameters**:
- `max_age_hours: int = 24` — measured from `completed_at`
- `require_current_version: bool = False` — if true, require same agent version
- `allow_partial_reuse: bool = False` — if true, PARTIAL runs are also reusable

**Reusable statuses**: COMPLETED only (PARTIAL only with explicit opt-in; FAILED/CANCELLED never reusable)

**Service method** (TO BE IMPLEMENTED):
```python
async def get_reusable_run(
    self,
    target_type: str,
    target_id: uuid.UUID,
    observation_date: date,
    *,
    max_age_hours: int = 24,
    require_current_version: bool = False,
    allow_partial: bool = False,
) -> ResearchRun | None: ...
```

### Reuse Flow

```
1. Request arrives: IndustryResearchRequest(industry_id, observation_date, ...)
2. Check concurrency: get_active_industry_run(industry_id, observation_date)
   → If active run exists: return existing run (do not create duplicate)
3. Check reuse: get_reusable_run("industry", industry_id, observation_date)
   → If reusable COMPLETED run exists within freshness window: return it
4. No reusable run: create new ResearchRun and execute
```

---

## 28. Retry, Failure, and Resume

### Retry Rules (3 Levels)

| Level | Rule | Applies To |
|---|---|---|
| LLM step-level | 1 retry, max 2 total attempts (`MAX_LLM_ATTEMPTS=2`) | Steps 4, 5, 7 (malformed output, LLM timeout, empty output) |
| Provider-level | Exponential backoff via `ProviderBase` | Transparent to step; does not increment `attempt_number` |
| Deterministic steps | No retry | Steps 1, 6 |

### Failure Mapping

| Failure Type | Step Impact | Run Impact | Retry? |
|---|---|---|---|
| Industry not found | Step 1 FAILED | Run FAILED | No |
| Provider auth failure | Step FAILED | Run FAILED | ProviderBase retry (transparent) |
| Provider rate limit | Step FAILED | Run PARTIAL | ProviderBase backoff (transparent) |
| Provider timeout | Step FAILED | Run PARTIAL | ProviderBase retry (transparent) |
| Provider unavailable | Step FAILED | Run PARTIAL | No (fallback provider if configured) |
| Document retrieval failure (some) | Step COMPLETED | Run continues | Per-doc via ProviderBase |
| Document retrieval failure (all) | Step FAILED | Run FAILED or PARTIAL | ProviderBase retry |
| LLM timeout | Step FAILED | Run PARTIAL | 1 retry, max 2 |
| LLM malformed output | Step FAILED | Run PARTIAL | 1 retry, max 2 |
| LLM empty output | Step FAILED | Run PARTIAL | 1 retry, max 2 |
| LLM truncation | Step COMPLETED | Run continues | No (partial results usable) |
| Temporal/citation validation | Finding rejected | Run continues | No (finding-level rejection) |

### Resume Capability

Query `ResearchRunStep` records for the run, find last COMPLETED step, resume from next PENDING step. All partial state is already persisted in PostgreSQL (Evidence, Findings, Artifacts, Sources recorded step by step).

### Run Status Determination

- All 7 steps COMPLETED + all findings validated → **COMPLETED**
- ≥5 steps COMPLETED + some findings validated → **PARTIAL**
- Classification not found or critical failure → **FAILED**
- User-initiated abort → **CANCELLED**

### Codebase References

- MAX_LLM_ATTEMPTS: `backend/app/agents/contracts.py:71` (2)
- State machines: `backend/app/models/state_machines.py` — VALID_RUN_TRANSITIONS, TERMINAL_RUN_STATUSES
- ProviderBase retry: `backend/app/providers/base.py`
- Phase 8 retry logic: `backend/app/agents/company_research/agent.py` — `_run_step_llm` with retry
- ADR-007: `architecture/adr/adr-007-failure-resilience.md`

---

## 29. Observability

### Reused Phase 7 Models

All observability flows through existing Phase 7 models:
- `ResearchRunStep`: One per step with `step_status`, `started_at`, `completed_at`, `error_summary`
- `AgentExecution`: One per LLM invocation with `model_provider`, `model_name`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `attempt_number`
- `ResearchRun` aggregates: `total_input_tokens`, `total_output_tokens`, `total_cost_usd` (updated via `update_run_aggregates()`)

### Observable Metrics

| Metric | Type | Source |
|---|---|---|
| `industry_research.run_duration_seconds` | Histogram | `ResearchRun.started_at` → `completed_at` |
| `industry_research.step_duration_seconds` | Histogram per step | `ResearchRunStep.started_at` → `completed_at` |
| `industry_research.token_utilization_pct` | Histogram | `TokenBudget.utilization_pct` |
| `industry_research.finding_count` | Counter per category | `ResearchFinding` count by category |
| `industry_research.evidence_count` | Counter | `Evidence` count per run |
| `industry_research.source_count` | Counter | `ResearchRunSource` count per run |
| `industry_research.gap_count` | Counter | `research_gap` findings per run |
| `industry_research.contradiction_count` | Counter | `contradiction` findings per run |
| `industry_research.five_forces_coverage` | Gauge (0-5) | Count of Five Forces categories with ≥1 finding |
| `industry_research.run_status` | Counter per status | COMPLETED / PARTIAL / FAILED / CANCELLED |
| `industry_research.provider_latency_seconds` | Histogram per provider | Provider call duration |
| `industry_research.llm_retry_count` | Counter | Number of LLM retries across all steps |
| `industry_research.source_tier_distribution` | Histogram per tier | TIER_1 / TIER_2 / TIER_3 distribution |
| `industry_research.budget_exhaustion_rate` | Counter | Runs hitting token budget |

### Structured Logging Events

Following Phase 8 pattern (`backend/app/agents/company_research/agent.py`):
- `agent.run.started` — run ID, industry_id, observation_date
- `agent.step.started` / `agent.step.completed` / `agent.step.failed` — step name, duration
- `agent.llm.called` / `agent.llm.completed` — model, tokens, cost
- `agent.budget.warning` — when token usage crosses 16,000 (80% of 20,000)
- `agent.budget.exhausted` — when token usage reaches 20,000
- `agent.finding.persisted` — finding count, category distribution
- `agent.gap.detected` — gap count, missing dimensions
- `agent.contradiction.detected` — contradiction count

### Codebase References

- ResearchRunStep: `backend/app/models/research.py`
- AgentExecution: `backend/app/models/research.py`
- update_run_aggregates: `backend/app/services/research_run.py`
- Phase 7 observability: `docs/architecture/phase-7-research-run-infrastructure.md`

---

## 30. API and UI Boundary

### Phase 9 Scope

Phase 9 implements the agent core. It does NOT implement REST endpoints or frontend UI components.

### Future Endpoints (Phase 20)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/research/industry` | POST | Initiate an industry research run |
| `/api/v1/research/industry/{run_id}` | GET | Get industry research run status/results |
| `/api/v1/research/industry/{run_id}/findings` | GET | Get findings for an industry run |
| `/api/v1/industries/{industry_id}/research` | GET | List research runs for an industry |

### Interim Integration

During Phase 9 implementation, the agent is invoked programmatically:
```python
agent = IndustryResearchAgent(
    session=session,
    search_provider=search_provider,
    macro_provider=macro_provider,
    news_provider=news_provider,
    llm_provider=llm_provider,
    run_service=run_service,
)
result = await agent.execute(request)
```

---

## 31. Quality Gates

### Evidence Quality Gates

| Gate | Target | Enforcement |
|---|---|---|
| Source tier coverage | ≥50% of findings backed by Tier 1+2 evidence | Post-run metric |
| Evidence linkage rate | 100% of FACT findings must have evidence | Step 6 validation (deterministic) |
| Temporal correctness | 100% pass temporal validation | Step 6 validation (deterministic) |

### Analytical Quality Gates

| Gate | Target | Enforcement |
|---|---|---|
| Five Forces coverage | ≥4 of 5 forces have ≥1 finding per industry | Post-run metric |
| TAM/SAM estimation | `market_size` finding present for ≥80% of industries | Post-run metric |
| Research gap ratio | ≤25% (≤3 of 12 dimensions missing) | Post-run metric |
| Finding classification accuracy | ≥90% correct FindingType assignment | Manual review + golden dataset |

### Step 6 Validation (Deterministic)

Step 6 performs the following checks on all findings from Step 5:
1. Verify evidence linkage for FACT-type findings → reject if missing
2. Verify `FindingType` enum membership → reject if invalid
3. Enforce temporal constraints (`observation_date` vs `source_publication_date`) → reject violations
4. Validate category membership against `INDUSTRY_FINDING_CATEGORIES` → reject invalid categories
5. MANAGEMENT_CLAIM requires evidence of type MANAGEMENT_STATEMENT → re-classify or reject

---

## 32. Evaluation Strategy

### Golden Dataset: 5 Reference Industries

| # | Industry | Sector | Why Selected |
|---|---|---|---|
| 1 | IT Services | Information Technology | Well-documented, large, global competition |
| 2 | Two-Wheelers | Automobiles | Domestic-focused, clear market leaders |
| 3 | Private Banks | Financial Services | Heavily regulated, excellent data |
| 4 | Specialty Chemicals | Chemicals | Growing, China+1 tailwind |
| 5 | Cement | Construction Materials | Cyclical, regional dynamics |

### Golden Dataset Structure

For each reference industry:
- Pre-selected source documents (5-10 per industry)
- Hand-extracted evidence (15-25 per industry)
- Hand-written findings across all 14 categories
- Expected research gaps
- Expected contradictions (if applicable)

### Evaluation Targets

| Dimension | Target |
|---|---|
| Evidence linkage (FACT findings) | 100% |
| Source tier distribution | ≥50% Tier 1+2 |
| Temporal correctness | 100% |
| Five Forces coverage | ≥4/5 |
| TAM/SAM presence | ≥80% of industries |
| Research gap ratio | ≤25% |
| FindingType accuracy | ≥90% |
| Category accuracy | ≥95% |

---

## 33. Test Strategy

### Test Structure

Tests reside alongside agent code and in the shared test directory:

| Location | Content |
|---|---|
| `backend/app/agents/industry_research/` | Agent source: `agent.py`, `tools.py`, `prompts.py`, `exceptions.py` |
| `backend/tests/agents/` | Tests: `test_industry_research_agent.py`, `test_industry_research_tools.py`, `test_industry_research_prompts.py` |

### Test Categories and Estimated Counts

| Category | Count | Focus |
|---|---|---|
| Unit — tool I/O | 20-30 | Each tool validates input/output schemas |
| Unit — step execution | 25-35 | Each of 7 steps tested with mock providers |
| Unit — finding validation | 15-20 | Category validation, evidence linkage, temporal checks |
| Unit — token budget | 5-8 | Budget enforcement, warning threshold, exhaustion |
| Unit — error handling | 10-15 | Provider failures, LLM failures, retry semantics |
| Integration — full run | 5-8 | End-to-end with mock providers |
| Golden dataset | 3-5 | Reference industries with hand-verified findings |
| **Total** | **83-121** | |

### Coverage Targets

| Component | Target |
|---|---|
| Agent logic (domain) | 95% |
| Tool implementations | 85% |
| Service integration | 90% |
| Provider contract | 85% |
| Overall Phase 9 | 85% |

### Test Principles

1. **No network calls in unit tests** — all providers mocked (CLAUDE.md §6)
2. **`Decimal` assertions for financial values** — never approximate float matches (CLAUDE.md §9)
3. **Verify structure, not prose** — test output schema and evidence attachment, not LLM English quality
4. **Flaky tests are bugs** — investigate and fix non-determinism immediately
5. **Never weaken tests** — fix the implementation, not the test (CLAUDE.md §6, §13 rule 5)
6. **Golden dataset tests** — hand-verified inputs and outputs for 3-5 industries (CLAUDE.md §6)

### Codebase References

- Phase 8 test pattern: `backend/tests/agents/` (test files follow `test_company_research_*.py` naming)
- CLAUDE.md testing requirements: `CLAUDE.md` §6

---

## 34. Phase 8 Reuse Matrix

### Category A: Direct Reuse (20 Components)

These components are used as-is from Phase 8, with no modification:

| Component | File | Notes |
|---|---|---|
| `TokenBudget` class | `contracts.py:477-512` | Different default budget injected via config |
| `StepDefinition` model | `contracts.py:523-533` | Identical schema |
| `FindingItem` model | `contracts.py:356-369` | Different `agent_name` default |
| `PersistEvidenceInput/Output` | `contracts.py:338-349` | Identical contract |
| `PersistFindingsInput/Output` | `contracts.py:380-392` | Identical contract |
| `RetrieveDocumentInput/Output` | `contracts.py:208-221` | Identical contract |
| `SourceCandidate` model | `contracts.py:187-200` | Identical contract |
| `EvidenceExtractionOutput` | `contracts.py:412-417` | Identical schema |
| `FindingGenerationOutput` | `contracts.py:438-443` | Identical schema |
| `FindingValidationIssue` | `contracts.py:451-458` | Identical schema |
| `FindingValidationResult` | `contracts.py:461-469` | Identical schema |
| `ExtractedEvidence` | `contracts.py:400-410` | Identical schema |
| `GeneratedFinding` | `contracts.py:425-435` | Identical schema |
| `RejectedFinding` | `contracts.py:371-377` | Identical schema |
| Step type constants | `contracts.py:518-520` | DETERMINISTIC, PROVIDER_CALL, LLM_REASONING |
| `ResearchRunService` | `services/research_run.py` | Used as-is for lifecycle management |
| `ResearchRunRepository` | `repositories/research_run.py` | Used as-is (with new methods added) |
| Temporal validation logic | `services/research_run.py` | `_validate_temporal_consistency()` reused |
| Error hierarchy | `agents/company_research/exceptions.py` | `StepFailedError`, `LLMParsingError`, `TokenBudgetExhaustedError` |
| State machines | `models/state_machines.py` | All transition tables reused |

### Category B: Duplicate Intentionally (10 Components)

These components are structurally similar but semantically different — they get their own implementation:

| Phase 8 Component | Phase 9 Component | Reason |
|---|---|---|
| `CompanyResearchRequest` | `IndustryResearchRequest` | Different target fields |
| `CompanyResearchConfig` | `IndustryResearchConfig` | Different budget defaults |
| `ValidateCompanyInput/Output` | `ValidateIndustryInput/Output` | Different validation target |
| `DiscoverSourcesInput/Output` | `DiscoverIndustrySourcesInput/Output` | Different source types |
| `FINDING_CATEGORIES` (14) | `INDUSTRY_FINDING_CATEGORIES` (14) | Different category names |
| `COMPANY_RESEARCH_STEPS` (7) | `INDUSTRY_RESEARCH_STEPS` (7) | Different step names |
| Evidence extraction prompt | Industry extraction prompt | Different extraction context |
| Finding generation prompt | Industry analysis prompt | Different analysis dimensions |
| Gap/contradiction prompt | Industry gap/contradiction prompt | Different expected dimensions |
| `CompanyResearchAgent` | `IndustryResearchAgent` | Different orchestration logic |

### Category C: Candidate for Shared Extraction (4 Components)

These components have identical logic in both agents and should eventually be extracted to a shared module:

| Component | Lines Duplicated | Priority | Target Module |
|---|---|---|---|
| Step runner pattern (`_run_step_deterministic`, `_run_step_llm`, `_run_step_provider`) | ~80 lines | High | `app.agents.base` |
| LLM structured output caller (`_call_llm_structured`) | ~40 lines | High | `app.agents.base` |
| Token budget enforcement logic | ~30 lines | Medium | `app.agents.base` |
| Finding validation logic | ~50 lines | Medium | `app.agents.base` |

**Recommendation**: Extract to `app.agents.base` before Phase 10 (Competitive Moat Agent). Not required for Phase 9 — if deferred, ~200 lines of Phase 8 step execution logic are duplicated.

### Codebase References

- Phase 8 agent: `backend/app/agents/company_research/agent.py` (748 lines)
- Phase 8 tools: `backend/app/agents/company_research/tools.py` (399 lines)
- Phase 8 prompts: `backend/app/agents/company_research/prompts.py` (94 lines)
- Phase 8 exceptions: `backend/app/agents/company_research/exceptions.py` (53 lines)

---

## 35. Shared Component Analysis

### Extraction Target: `backend/app/agents/base.py`

If extracted before Phase 9 implementation, the shared module would contain:

```python
class BaseResearchAgent:
    async def _run_step_deterministic(self, step: StepDefinition, func: Callable) -> Any: ...
    async def _run_step_llm(self, step: StepDefinition, func: Callable) -> Any: ...
    async def _run_step_provider(self, step: StepDefinition, func: Callable) -> Any: ...
    async def _call_llm_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...
    def _enforce_token_budget(self, usage: TokenUsage) -> None: ...
    def _validate_findings(self, findings: list[GeneratedFinding], valid_categories: frozenset) -> FindingValidationResult: ...
```

### Decision: Defer to Phase 10

Phase 9 duplicates ~200 lines of Phase 8 logic. This is acceptable for one agent. If Phase 10 would triple the duplication, extract before Phase 10.

### Codebase References

- Phase 8 step runners: `backend/app/agents/company_research/agent.py` — `_run_step_deterministic`, `_run_step_llm` methods
- Phase 9 architecture: `docs/architecture/phase-9-industry-research-agent.md` §31

---

## 36. Multi-Agent Compatibility

### LangGraph Integration (Deferred)

Phase 9, like Phase 8, is plain async Python — no LangGraph dependency. The agent is designed to be wrappable as a LangGraph node in the future:

```python
async def industry_analysis_node(state: ResearchState) -> ResearchState:
    """LangGraph node signature for future integration."""
    request = IndustryResearchRequest(
        industry_id=state.industry_id,
        observation_date=state.observation_date,
        initiated_by="langgraph_orchestrator",
    )
    agent = IndustryResearchAgent(...)
    result = await agent.execute(request)
    state.industry_analysis = result
    return state
```

### Parallel Execution Compatibility

The Industry Research Agent can run in parallel with:
- Business Model Agent (#3) — different research scope
- Competitor Analysis Agent (#9) — reads industry findings but does not write them

It must NOT run in parallel with another Industry Research Agent instance for the same `(industry_id, observation_date)` — enforced by the concurrency lock (§26).

### Writes to `ResearchState.industry_analysis`

The agent's findings are stored in:
- `ResearchFinding` table (via `persist_findings`)
- `Evidence` table (via `persist_evidence`)
- `ResearchRun` + `ResearchRunStep` + `AgentExecution` (lifecycle records)

Downstream consumers query these tables filtered by `agent_name = "industry_research_agent"`.

### Codebase References

- ADR-001: `architecture/adr/adr-001-langgraph.md` — LangGraph as orchestration framework
- Phase 8 LangGraph boundary: `docs/architecture/phase-8-company-research-agent.md` §24

---

## 37. Implementation Sequence

### 4 Sub-Phases

#### Phase 9a: Schema + Service Layer (Already Partially Complete)

| Task | Status | Effort | Dependencies |
|---|---|---|---|
| Schema migration (006) | **COMPLETE** (Phase 9.1) | — | None |
| ORM model updates | **COMPLETE** (Phase 9.1) | — | Migration |
| ResearchRunService extensions | **PARTIAL** (initiate_run branches exist) | Small | Migration |
| ResearchRunRepository extensions | **PARTIAL** (get_active_industry_run exists) | Small | Migration |
| Schemas (ResearchRunCreate validator) | **COMPLETE** (Phase 9.1) | — | Migration |

**Remaining 9a work**: `get_reusable_run()` service method, `get_by_industry()` and `get_current_for_industry()` repository methods.

#### Phase 9b: Agent Contracts, Tools, and Prompts

| Task | Status | Effort | Dependencies |
|---|---|---|---|
| Agent contracts (request, config, categories, steps) | **COMPLETE** (Phase 9.2) | — | None |
| Industry-specific tool I/O schemas | TO DO | Medium | Contracts |
| `IndustryResearchTools` class (8 tools) | TO DO | Medium | Tool schemas |
| Agent prompts (extraction, analysis, gap/contradiction) | TO DO | Medium | None |

#### Phase 9c: Agent Core

| Task | Status | Effort | Dependencies |
|---|---|---|---|
| `IndustryResearchAgent` class (7-step workflow) | TO DO | Large | 9a, 9b |
| Agent exceptions | TO DO | Small | None |
| Unit tests | TO DO | Large | Agent core |
| Integration tests | TO DO | Medium | Agent core |

#### Phase 9d: Golden Dataset

| Task | Status | Effort | Dependencies |
|---|---|---|---|
| Golden dataset tests (3-5 industries) | TO DO | Medium | 9c |

**Note**: REST API endpoints (`POST /api/v1/research/industry`, etc.) are Phase 20 scope — see §30.

### Estimated Remaining Effort: 3-4 Days

Phase 9a and 9b are partially complete. The remaining work is primarily 9b (tools, prompts), 9c (agent core + tests), and 9d (golden dataset).

---

## 38. Acceptance Criteria

### Functional (AC-01 through AC-17)

| # | Criterion | Verification |
|---|---|---|
| AC-01 | Agent validates industry exists with `level=INDUSTRY` | Unit test |
| AC-02 | Agent discovers sources from SearchProvider and NewsProvider | Unit test with mock providers |
| AC-03 | Agent retrieves/registers documents with `company_id = NULL` | Unit test |
| AC-04 | Agent extracts evidence with correct EvidenceType | Unit test with mock LLM |
| AC-05 | Agent generates findings across all 14 industry categories (excl. `research_gap` and `contradiction` from Step 7) | Integration test |
| AC-06 | Five Forces analysis produces ≥1 finding per force (5 categories) | Integration test |
| AC-07 | TAM/SAM estimation produces ≥1 FACT or AI_INFERENCE finding in `market_size` | Integration test |
| AC-08 | All FACT findings have evidence linkage | Unit test (Step 6 validation) |
| AC-09 | Findings with `source_publication_date > observation_date` are rejected | Unit test (Step 6 validation) |
| AC-10 | Finding categories validated against `INDUSTRY_FINDING_CATEGORIES` (14) | Unit test |
| AC-11 | Research gaps identified for each missing dimension in `EXPECTED_INDUSTRY_DIMENSIONS` (12) | Unit test |
| AC-12 | Contradictions preserved as separate findings with category `contradiction` | Unit test |
| AC-13 | Token budget (20,000) enforced; exhaustion produces PARTIAL, not FAILED | Unit test |
| AC-14 | Agent produces ResearchRun with COMPLETED/PARTIAL/FAILED status | Integration test |
| AC-15 | All outputs persisted through ResearchRunService | Integration test |
| AC-16 | `target_type = "industry"` for all runs; `run_type` retains execution-mode value | Unit test |
| AC-17 | Agent degrades gracefully when MacroDataProvider unavailable (UNCERTAINTY, not FAILED) | Unit test |

### Concurrency, Reuse, and Freshness (AC-18 through AC-22a)

| # | Criterion | Verification |
|---|---|---|
| AC-18 | Lock key is `research_lock:industry:{industry_id}:{observation_date}` | Unit test |
| AC-19 | No duplicate runs for same `(industry_id, observation_date)` | Integration test with concurrent requests |
| AC-20 | COMPLETED run with matching identity reused within freshness window | Integration test |
| AC-21 | Freshness threshold configurable (default 24h), measured from `completed_at` | Unit test |
| AC-22 | PARTIAL and FAILED runs NOT reused by default | Unit test |
| AC-22a | Three mechanisms (lock, identity, freshness) implemented as separable | Code review / unit test |

### Non-Functional (AC-23 through AC-28)

| # | Criterion | Target |
|---|---|---|
| AC-23 | Total execution time | ≤120 seconds (excl. document retrieval latency) |
| AC-24 | Token usage | ≤20,000 tokens per run |
| AC-25 | Test coverage | ≥85% for agent module |
| AC-26 | No network calls in unit tests | All providers mocked |
| AC-27 | mypy strict passes | Zero type errors |
| AC-28 | ruff passes | Zero lint errors |

### Schema Migration (AC-29 through AC-36) — ALREADY SATISFIED

| # | Criterion | Status |
|---|---|---|
| AC-29 | `company_id` is nullable | **PASS** (Phase 9.1, migration 006) |
| AC-30 | `industry_id` FK exists | **PASS** (Phase 9.1) |
| AC-31 | XOR CHECK `chk_research_run_target` | **PASS** (Phase 9.1) |
| AC-32 | Existing records unaffected | **PASS** (Phase 9.1) |
| AC-33 | `target_type` NOT NULL DEFAULT 'company'; `run_type` unchanged | **PASS** (Phase 9.1) |
| AC-34 | Partial index `ix_research_run_industry` | **PASS** (Phase 9.1) |
| AC-34a | Index `ix_research_run_target_type` | **PASS** (Phase 9.1) |
| AC-35 | Downgrade path works | **PASS** (Phase 9.1 — tested) |
| AC-36 | Phase 8 backward compatibility | **PASS** (Phase 9.2 — tested) |

---

## 39. Open Questions

4 remaining open questions, all non-blocking for implementation:

### OQ-1: Concrete SearchProvider Implementation

**Options**: Google Custom Search API, Bing Search API, SerpAPI  
**Status**: Mock sufficient for development/testing  
**Recommendation**: Google Custom Search as default (well-documented, sufficient quota)  
**Impact if deferred**: Agent tests pass with mock. Production requires a concrete implementation.

### OQ-2: Concrete MacroDataProvider Implementation

**Options**: RBI DBIE API, data.gov.in API, FRED (for comparison data)  
**Status**: Non-blocking — agent degrades gracefully  
**Recommendation**: Minimal provider for most impactful Indian indicators (IIP, sectoral credit growth, SIAM auto sales)

### OQ-3: Industry Source Seeding

**Question**: Pre-register 10-15 major Indian industry data sources?  
**Sources**: NASSCOM, SIAM, IBEF, CII, FICCI, MoSPI, DPIIT, relevant ministry databases  
**Impact**: Without seeding, source discovery relies entirely on SearchProvider. With seeding, the agent has a baseline of known-good sources.

### OQ-4: IndustryData Population Strategy

**Question**: Should the agent populate `IndustryData` with extracted metrics, or defer to a separate pipeline?  
**Recommendation**: Agent populates key metrics (market size, growth rate, concentration) using `source_evidence_id` FK for provenance. Full population deferred.  
**Note**: `IndustryData.research_run_id` FK is deferred (Decision D-18).

---

## 40. Architectural Risks

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No concrete SearchProvider | Medium | High — source discovery degraded | Mock provider for testing; prioritize Google Custom Search |
| No concrete MacroDataProvider | Medium | Medium — macro context missing | Graceful degradation to UNCERTAINTY findings |
| Industry data quality varies widely | High | Medium — more UNCERTAINTY findings | Explicit gap handling; no data fabrication |
| Token budget insufficient (20K) for complex industries | Medium | Medium — PARTIAL runs | Monitor utilization; increase to 25K if ≥30% of runs hit ceiling |
| Schema migration affects existing tests | Low | Medium — test breakage | Migration already applied (Phase 9.1); backward compatibility verified |
| LLM prompt quality for industry analysis | Medium | High — poor finding quality | Golden dataset testing; iterative prompt refinement |
| Category name collision (`growth_drivers`) | Low | Medium — incorrect downstream queries | Document filter-by-agent_name requirement; add code comment at query sites |

### Process Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep into company-specific analysis | Medium | High — violates boundary | Strict category validation; code review |
| Phase 10 (Competitive Moat) blocked on Phase 9 | Low | Medium — schedule impact | Phase 9 acceptance criteria are self-contained |
| Category C extraction deferred too long | Medium | Low — code duplication | Extract to `app.agents.base` before Phase 10 |

---

## 41. ADR Analysis

### ADRs Directly Applicable to Phase 9

| ADR | Phase 9 Impact |
|---|---|
| ADR-001 (LangGraph) | Agent is standalone async; designed for LangGraph node wrapping. No LangGraph dependency in Phase 9. |
| ADR-003 (Decimal) | All financial values (`market_size`, growth rates, macro indicators) use `Decimal`. `MacroIndicatorResult.latest_value: Decimal`. |
| ADR-004 (Evidence Citations) | FACT findings require evidence; FindingType enforced. Applied without modification. |
| ADR-005 (Provider Abstraction) | Agent uses SearchProvider, MacroDataProvider, NewsProvider, LLMProvider through Protocol interfaces. Phase 9 adds SearchProvider and MacroDataProvider as new runtime dependencies. |
| ADR-007 (Failure & Resilience) | Retry semantics, PARTIAL status, idempotency lock. Applied with `industry_id:{observation_date}` lock key. |
| ADR-008 (Cost Controls) | 20,000 token budget (distinct from Phase 8's 30,000). Per-run cost tracking. Model tier optimization. |

### ADRs Not Applicable to Phase 9

| ADR | Reason |
|---|---|
| ADR-002 (Background Tasks) | Phase 9 is a synchronous agent run, not a background pipeline |
| ADR-006 (India Market Focus) | Implicit — agent focuses on Indian industries by design |
| ADR-009 (NSE/BSE Data Access) | Phase 9 does not access exchange data directly |

### Potential New ADR

**ADR-010: Industry-Level Research Run Identity** — The decision to make `ResearchRun.company_id` nullable and add `industry_id` with `target_type` discriminator warrants formal documentation. The ADR should cover:
- Need for non-company-anchored research runs
- XOR CHECK constraint design
- Impact on existing queries and indexes
- Backward compatibility with Phase 8

---

## 42. Decision Summary

18 architectural decisions resolved through two reconciliation passes:

| # | Decision | Rationale |
|---|---|---|
| D-01 | 7-step sequential workflow matching Phase 8 | Proven pattern; reusable infrastructure |
| D-02 | Option A: nullable `company_id` + `industry_id` FK + `target_type` discriminator with XOR constraint | Semantically correct; generalizes to Macro Agent |
| D-03 | `"industry_research_agent"` as distinct `agent_name` | Unambiguous finding attribution |
| D-04 | 14 finding categories; `growth_rate` merged into `growth_drivers` | Semantic consistency and queryability |
| D-05 | Porter's Five Forces as structured findings, not free-form text | Framework adherence enforced by schema |
| D-06 | SearchProvider = direct dependency; MacroDataProvider = limited, non-blocking | Phase 9 uses macro for context only; Phase 13 owns full macro |
| D-07 | 20,000 token budget (not 30,000) | 30K is Company Research Agent's budget; 20K consistent with architecture spec |
| D-08 | `ResearchDocument.company_id=NULL` for industry documents | Field already nullable; no schema change |
| D-09 | Concurrency lock keyed by `industry_id:observation_date`; three mechanisms separated | Prevents cross-temporal blocking; independent evolution |
| D-10 | Phase 8 reuse: 20 Category A, 10 Category B, 4 Category C | Explicit classification replaces ambiguous "reuse" |
| D-11 | Industry source discovery focuses on Tier 2 sources | Government and industry body data is primary for industry research |
| D-12 | No INDUSTRY_ATTRACTIVENESS score computation | Scoring is downstream; agent produces findings |
| D-13 | Plain async Python, no LangGraph | Consistent with Phase 8; designed for future wrapping |
| D-14 | Agent does not modify Classification table | Taxonomy management is administrative |
| D-15 | ADR-010 recommended for target_type + industry_id schema change | Decision significant enough for formal ADR |
| D-16 | Industry runs are reusable; identity = `(target_type, target_id, observation_date)` | Prevents redundant research; three mechanisms separated |
| D-17 | `target_type` (NOT `run_type`) is the target discriminator | `run_type` has existing execution-mode semantics; conflating is incorrect |
| D-18 | `IndustryData.research_run_id` FK deferred | `IndustryData` has `source_evidence_id` for provenance; population strategy is OQ-4 |

---

## 43. Readiness Assessment

### Infrastructure Readiness

| Component | Status | Blocker? |
|---|---|---|
| Phase 7 ResearchRun infrastructure | **COMPLETE** | No |
| Phase 8 Company Research Agent | **COMPLETE** (commit 393dc2f) | No |
| Phase 9.1 Schema migration | **COMPLETE** (commit 7395a37) | No |
| Phase 9.2 Contracts | **COMPLETE** (commit 7395a37) | No |
| Phase 4 Evidence subsystem | **COMPLETE** | No |
| Phase 3 Domain models | **COMPLETE** | No |
| Phase 5 Provider framework | **COMPLETE** | No |
| SearchProvider (concrete) | MOCK ONLY | **Not a blocker** — mock sufficient for dev/test |
| MacroDataProvider (concrete) | MOCK ONLY | No — graceful degradation |
| NewsProvider (concrete) | MOCK ONLY | No — graceful degradation |
| LLMProvider (concrete) | MOCK ONLY for tests | No — mock sufficient for testing |

### Contract Readiness

| Contract | Status | Reuse Category |
|---|---|---|
| `SourceCandidate` | **READY** | A — direct reuse |
| `TokenBudget` | **READY** | A — direct reuse (different default) |
| `FindingItem` | **READY** | A — direct reuse (different agent_name) |
| `PersistEvidenceInput/Output` | **READY** | A — direct reuse |
| `PersistFindingsInput/Output` | **READY** | A — direct reuse |
| `RetrieveDocumentInput/Output` | **READY** | A — direct reuse |
| `StepDefinition` | **READY** | A — direct reuse |
| `EvidenceExtractionOutput` | **READY** | A — direct reuse |
| `FindingGenerationOutput` | **READY** | A — direct reuse |
| `IndustryResearchRequest` | **READY** (Phase 9.2) | B — created |
| `IndustryResearchConfig` | **READY** (Phase 9.2) | B — created |
| `INDUSTRY_FINDING_CATEGORIES` | **READY** (Phase 9.2) | B — created |
| `INDUSTRY_RESEARCH_STEPS` | **READY** (Phase 9.2) | B — created |
| Industry-specific tool I/O schemas | TO BE CREATED | B — new contracts |

### Schema Readiness

| Schema Element | Status |
|---|---|
| `ResearchRun.target_type` NOT NULL DEFAULT 'company' | **APPLIED** (migration 006) |
| `ResearchRun.company_id` nullable | **APPLIED** |
| `ResearchRun.industry_id` FK | **APPLIED** |
| XOR CHECK constraint | **APPLIED** |
| Partial index `ix_research_run_industry` | **APPLIED** |
| Index `ix_research_run_target_type` | **APPLIED** |
| `run_type` values | **UNCHANGED** — correct |
| `ResearchDocument.company_id` nullable | **ALREADY NULLABLE** |
| All required enums | **EXIST** — no additions needed |

### Verdict: READY FOR IMPLEMENTATION

All material architectural decisions are resolved. Phase 9.1 (schema) and Phase 9.2 (contracts) are complete. The remaining implementation work is:

1. **Industry-specific tool I/O schemas** (5 new schemas)
2. **`IndustryResearchTools` class** (8 tools, 3 reused)
3. **Agent prompts** (3 prompt templates)
4. **`IndustryResearchAgent` class** (7-step workflow)
5. **Agent exceptions** (industry-specific error types)
6. **Service extensions** (`get_reusable_run`, `get_by_industry`)
7. **Unit and integration tests** (83-121 tests)
8. **Golden dataset tests** (3-5 reference industries)

No blockers. Mock providers sufficient for development and testing.

---

## 44. Final Report

### 25-Item Implementation Readiness Report

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Schema migration (target_type, company_id nullable, industry_id FK, XOR constraint) | **COMPLETE** | Phase 9.1, migration 006, commit 7395a37 |
| 2 | ORM model alignment (ResearchRun with target_type, industry_id) | **COMPLETE** | Phase 9.1, commit 7395a37 |
| 3 | ResearchRunCreate schema validator (XOR) | **COMPLETE** | Phase 9.1, @model_validator |
| 4 | IndustryResearchRequest contract | **COMPLETE** | Phase 9.2, contracts.py:605-614 |
| 5 | IndustryResearchConfig contract | **COMPLETE** | Phase 9.2, contracts.py:589-602 |
| 6 | INDUSTRY_FINDING_CATEGORIES (14 categories) | **COMPLETE** | Phase 9.2, contracts.py:81-98 |
| 7 | INDUSTRY_RESEARCH_STEPS (7 steps) | **COMPLETE** | Phase 9.2, contracts.py:617-663 |
| 8 | Token budget constants (20K budget, 16K warning) | **COMPLETE** | Phase 9.2, contracts.py:77-78 |
| 9 | Industry-specific tool I/O schemas (5 new) | **TO DO** | ValidateIndustry, DiscoverIndustrySources, SearchIndustryData, GetMacroIndicators, GetIndustryCompanies |
| 10 | IndustryResearchTools class (8 tools) | **TO DO** | 3 reused (retrieve_document, persist_evidence, persist_findings), 5 new |
| 11 | Agent prompts (evidence extraction, industry analysis, gap/contradiction) | **TO DO** | Follow Phase 8 prompt security patterns |
| 12 | IndustryResearchAgent class (7-step workflow) | **TO DO** | Core agent orchestrator |
| 13 | Agent exceptions (IndustryNotFoundError, etc.) | **TO DO** | Follow Phase 8 exception hierarchy |
| 14 | ResearchRunService.get_reusable_run() | **TO DO** | Freshness policy implementation |
| 15 | ResearchRunRepository extensions (get_by_industry, get_current_for_industry) | **TO DO** | Parallel to existing company methods |
| 16 | Unit tests — tool I/O | **TO DO** | 20-30 tests |
| 17 | Unit tests — step execution | **TO DO** | 25-35 tests |
| 18 | Unit tests — finding validation | **TO DO** | 15-20 tests |
| 19 | Unit tests — token budget | **TO DO** | 5-8 tests |
| 20 | Unit tests — error handling | **TO DO** | 10-15 tests |
| 21 | Integration tests — full run | **TO DO** | 5-8 tests |
| 22 | Golden dataset tests | **TO DO** | 3-5 reference industries |
| 23 | API endpoint (POST /api/v1/research/industry) | **PHASE 20** | Transport-independent; REST API deferred to Phase 20 (§30) |
| 24 | ADR-010 (Industry-Level Research Run Identity) | **RECOMMENDED** | Formal documentation of target_type decision |
| 25 | Category C shared extraction (app.agents.base) | **DEFERRED** | Recommended before Phase 10; ~200 lines duplicated |

### Summary

- **8 of 25 items COMPLETE** (items 1-8: schema, contracts, constants)
- **14 of 25 items TO DO** (items 9-22: tools, agent, prompts, tests)
- **3 of 25 items DEFERRED/RECOMMENDED/PHASE 20** (items 23-25: API, ADR-010, shared extraction)
- **0 blockers** — all prerequisites satisfied
- **Architecture reuses ~55% of Phase 8** (20 Category A direct-reuse components)
- **Estimated remaining effort: 3-4 days** for an experienced developer familiar with Phase 8

### Readiness Verdict

**READY FOR IMPLEMENTATION.** The Phase 9.3 architecture synthesis is complete. All material decisions are resolved. The implementation path is clear: complete tool schemas (9b), build agent core and tests (9c), then API integration (9d).
