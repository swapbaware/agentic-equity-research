# Phase 9 — Industry Research Agent Architecture

**Status:** Architecture Document  
**Date:** 2026-09-30  
**Author:** Architecture synthesis from repository inspection  
**Depends on:** Phase 7 (Research Run Infrastructure), Phase 8 (Company Research Agent), Phase 5 (Provider Framework), Phase 4 (Evidence Subsystem), Phase 3 (Domain Models)

---

## Table of Contents

1. [Objective and Scope](#1-objective-and-scope)
2. [Non-Goals](#2-non-goals)
3. [Design Principles](#3-design-principles)
4. [Agent Responsibilities](#4-agent-responsibilities)
5. [Company Research vs Industry Research Boundary](#5-company-research-vs-industry-research-boundary)
6. [Request Contract](#6-request-contract)
7. [Industry Taxonomy Model](#7-industry-taxonomy-model)
8. [Temporal Model](#8-temporal-model)
9. [Source Hierarchy for Industry Research](#9-source-hierarchy-for-industry-research)
10. [Tool Architecture](#10-tool-architecture)
11. [Provider Architecture](#11-provider-architecture)
12. [Evidence Architecture](#12-evidence-architecture)
13. [Finding Architecture](#13-finding-architecture)
14. [Finding Categories](#14-finding-categories)
15. [Economics Boundary](#15-economics-boundary)
16. [Competitive Dynamics Boundary](#16-competitive-dynamics-boundary)
17. [Regulatory Research Boundary](#17-regulatory-research-boundary)
18. [Contradiction Handling](#18-contradiction-handling)
19. [Gap Handling](#19-gap-handling)
20. [ResearchRun Integration](#20-researchrun-integration)
21. [Research Workflow](#21-research-workflow)
22. [LLM Boundary](#22-llm-boundary)
23. [Token Budget](#23-token-budget)
24. [Security Model](#24-security-model)
25. [Data Model Impact](#25-data-model-impact)
26. [API and UI Boundary](#26-api-and-ui-boundary)
27. [Observability](#27-observability)
28. [Evaluation Strategy](#28-evaluation-strategy)
29. [Testing Strategy](#29-testing-strategy)
30. [Phase 8 Reuse Matrix](#30-phase-8-reuse-matrix)
31. [Shared Component Analysis](#31-shared-component-analysis)
32. [Multi-Agent Compatibility](#32-multi-agent-compatibility)
33. [Reproducibility](#33-reproducibility)
34. [Failure, Retry, and Resume](#34-failure-retry-and-resume)
35. [Open Questions](#35-open-questions)
36. [ADR Analysis](#36-adr-analysis)
37. [Acceptance Criteria](#37-acceptance-criteria)
38. [Implementation Sequence](#38-implementation-sequence)
39. [Risks](#39-risks)
40. [Decision Summary](#40-decision-summary)
41. [Readiness Assessment](#41-readiness-assessment)

---

## 1. Objective and Scope

### Why the Industry Research Agent Exists

The Company Research Agent (Phase 8) answers "What does this company do?" The Industry Research Agent answers "What is the structure, attractiveness, and trajectory of the industry this company operates in?"

The platform's research methodology (§B, Industry Attractiveness) requires analysis of market size, growth drivers, competitive structure (Porter's Five Forces), entry barriers, cyclicality, regulatory environment, and India's competitive position globally. The agent architecture (`architecture/agent-architecture.md`, Agent #4) specifies the Industry Analysis Agent as a distinct research agent that runs in parallel with the Business Model and Competitor agents.

No existing agent produces industry-level research findings. The Company Research Agent identifies competitive context but explicitly defers industry structure analysis, TAM/SAM estimation, and Porter's Five Forces to Phase 9.

### What Problem It Solves

Given an industry identifier (resolved from a company's `industry_id` or provided directly) and an observation date, the Industry Research Agent:

1. Validates the industry exists in the Classification taxonomy.
2. Discovers and retrieves industry-relevant source documents (government publications, industry body reports, regulatory filings, sector news, research reports).
3. Extracts structured evidence about industry structure, size, growth, and competitive dynamics.
4. Generates evidence-backed research findings across Porter's Five Forces, TAM/SAM, entry barriers, regulatory environment, cyclicality, and India's global competitive position.
5. Classifies every finding by type (FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, UNCERTAINTY).
6. Identifies research gaps and contradictions across industry data sources.
7. Persists all findings, evidence, artifacts, and execution metadata through the Phase 7 ResearchRun infrastructure.

### What Output It Produces

- **ResearchRun** with status COMPLETED, PARTIAL, or FAILED.
- **ResearchFinding** records with `agent_name = "industry_research_agent"`, each with a `FindingType`, evidence references, observation date, and source publication date.
- **Evidence** records linked to **ResearchDocument** records with source provenance.
- **ResearchArtifact** records (structured industry analysis: Five Forces matrix, TAM/SAM estimates, competitive structure map).
- **AgentExecution** records with full reproducibility metadata.
- **ResearchRunSource** records tracking every document accessed.
- **IndustryData** records populated with evidence-backed metrics (market size, growth rate, concentration ratios).

### Research Dimensions Covered

| Research Dimension | Phase 9 Responsibility | Research Methodology Reference |
|---|---|---|
| Total addressable market (TAM) | **Phase 9** | §B |
| Serviceable addressable market (SAM) | **Phase 9** | §B |
| Industry growth rate and drivers | **Phase 9** | §B |
| Porter's Five Forces | **Phase 9** | §B |
| Entry barriers | **Phase 9** | §B |
| Supplier power | **Phase 9** | §B |
| Buyer power | **Phase 9** | §B |
| Substitution / threat of substitutes | **Phase 9** | §B |
| Competitive rivalry / industry concentration | **Phase 9** | §B |
| Regulatory environment | **Phase 9** | §B |
| Cyclicality and commodity exposure | **Phase 9** | §B |
| India's competitive position globally | **Phase 9** | §B |
| Industry risks | **Phase 9** | §B, §J |
| Research gaps and contradictions | **Phase 9** | reused from Phase 8 |

---

## 2. Non-Goals

The Industry Research Agent explicitly does NOT:

1. **Perform company-specific research.** No company validation, no company financials, no company-level business model analysis. The Company Research Agent (Phase 8) handles this.
2. **Assess competitive moat for a specific company.** No moat type evaluation, no moat scoring. The Competitive Moat Agent (#5) handles this. Phase 9 analyzes industry-level competitive dynamics but does not map them to a specific company's moat.
3. **Perform deep competitor comparison.** No company-vs-company financial benchmarking. The Competitor Analysis Agent (#9) handles this. Phase 9 identifies industry structure and major players but does not compare their financials.
4. **Perform valuation.** No DCF, multiples, or target price. The Valuation Agent (#10) handles this.
5. **Perform macro research.** No GDP/inflation/interest rate analysis. The Macro Economics Agent (#8) handles this. Phase 9 references macro factors where they directly shape industry dynamics (e.g., "interest rate sensitivity affects housing demand") but does not perform independent macro analysis.
6. **Construct bull/bear cases.** No scenario analysis. Bull Case (#12) and Bear Case (#13) agents handle this.
7. **Score management quality.** The Management & Governance Agent (#6) handles this.
8. **Synthesize investment thesis.** The Research Synthesis Agent (#16) handles this.
9. **Produce an INDUSTRY_ATTRACTIVENESS score.** Scoring is a downstream consumer of Phase 9 findings. The scoring infrastructure uses Phase 9 findings as input but the Industry Research Agent does not compute the 0-100 score itself.
10. **Compute financial ratios or growth rates.** Deterministic computation belongs in the analytics engine (Phase 6b). The agent may reference computed values in findings but does not calculate them.
11. **Predict industry outcomes.** No forecasts beyond what is attributable to cited sources.
12. **Generate buy/sell recommendations or claim multibagger potential.** Never.

---

## 3. Design Principles

### Principles Reused from Phase 8 (Unchanged)

1. **Evidence before inference** (Research Methodology §1). Every factual claim requires a source.
2. **Source provenance** (ADR-004). Every Evidence record references a ResearchDocument; every ResearchDocument references a Source with a tier classification.
3. **Deterministic calculations, not LLM** (ADR-003, CLAUDE.md §9). The agent does not perform financial arithmetic.
4. **Provider abstraction** (ADR-005). The agent accesses external data through Protocol interfaces, never concrete implementations.
5. **Least-privilege agent tools** (Security Architecture). The agent can only call tools explicitly granted to it.
6. **Explicit uncertainty** (Research Methodology §2, §6). When information is unavailable, the agent produces a finding of type UNCERTAINTY.
7. **No certainty manufacturing** (CLAUDE.md §1).
8. **Cost awareness** (ADR-008). Per-agent token budget enforced.
9. **Failure isolation** (ADR-007). A failed agent step is recorded as FAILED; partial results are preserved.
10. **Temporal correctness** (Phase 8 §9). Every finding records `observation_date` and `source_publication_date`. Sources published after the observation date are excluded.
11. **Contradictory evidence preservation** (Phase 8 §14). Contradictions are preserved, not collapsed.
12. **Reproducibility** (Phase 8 §19). All inputs captured in AgentExecution metadata.
13. **Auditability** (Phase 8 §23). Every step logged through ResearchRunStep / AgentExecution infrastructure.
14. **Security by design** (Phase 8 §20). Retrieved document content is untrusted data.

### Principles Introduced by Phase 9

15. **Industry-first, company-second.** The agent researches an industry as a first-class entity. A company's `industry_id` is the entry point, but the research output is about the industry, not the company. Multiple companies in the same industry share a single industry research run's findings.
16. **Source diversity for industry research.** Industry research draws heavily from Tier 2 sources (government publications, industry body reports) and Tier 3 sources (research reports, news) in addition to Tier 1 company filings. The source hierarchy is intentionally broader than Phase 8's company-centric hierarchy.
17. **Analytical framework adherence.** The agent must structure its analysis around Porter's Five Forces — not as a free-form LLM summary, but as separate findings for each force. The framework is the output schema, not a suggestion to the LLM.

---

## 4. Agent Responsibilities

### Responsibility 1: Industry Validation

| Aspect | Detail |
|---|---|
| **Input** | Industry identifier: either a `Classification.id` (UUID) directly, or resolved from a company's `industry_id` |
| **Processing** | Deterministic: query the `company.classification` table. Verify the record exists and `level = INDUSTRY`. Resolve the parent sector (`parent_id`). |
| **Output** | Resolved industry Classification record with UUID, name, code, and parent sector. |
| **Persistence** | ResearchRunStep status transition; no findings produced. |
| **Failure** | If industry not found → ResearchRun fails with `error_summary`. |

### Responsibility 2: Industry Source Discovery

| Aspect | Detail |
|---|---|
| **Input** | Industry name, sector name, observation_date, research configuration. |
| **Processing** | Provider/tool call: query SearchProvider for industry reports, NewsProvider for sector news, MacroDataProvider for industry-level indicators. Filter by observation_date (sources published after observation_date excluded). Rank by SourceTier. |
| **Output** | Ordered list of candidate source documents. |
| **Persistence** | ResearchRunStep; candidate list stored as ResearchArtifact (INTERMEDIATE_STATE). |
| **Failure** | If no sources found → finding of type UNCERTAINTY. Step marked COMPLETED with zero findings. |

### Responsibility 3: Document Retrieval & Registration

| Aspect | Detail |
|---|---|
| **Input** | Candidate source document list from step 2. |
| **Processing** | Provider/tool call: retrieve document content. Deterministic: compute content_hash, deduplicate. Industry-level documents use `ResearchDocument.company_id = NULL` (the field is nullable). |
| **Output** | ResearchDocument records (with `company_id = NULL` for industry-level documents), DocumentVersion records. |
| **Persistence** | ResearchDocument, DocumentVersion via EvidenceService. ResearchRunSource record per accessed document. |
| **Failure** | Individual document failure → log, continue. All fail → step FAILED. |

### Responsibility 4: Evidence Extraction

| Aspect | Detail |
|---|---|
| **Input** | Retrieved document content (text-extracted, sanitized). |
| **Processing** | LLM reasoning: extract structured claims about industry structure, market size, competitive dynamics, regulatory environment. Each claim classified by EvidenceType. LLM output validated against Evidence Pydantic schema. |
| **Output** | Evidence records linked to source ResearchDocuments. |
| **Persistence** | Evidence records via EvidenceService.create_evidence(). |
| **Failure** | Malformed LLM output → retry. If retry fails → log error, continue with successfully extracted evidence. |

### Responsibility 5: Industry Analysis and Finding Generation

| Aspect | Detail |
|---|---|
| **Input** | Extracted evidence records, industry profile (Classification + IndustryData). |
| **Processing** | LLM reasoning: synthesize evidence into structured research findings organized around Porter's Five Forces, TAM/SAM, entry barriers, regulatory environment, cyclicality, and India's competitive position. Each finding classified using FindingType. Each finding references Evidence records. |
| **Output** | ResearchFinding records with evidence linkages. |
| **Persistence** | ResearchFinding via ResearchRunService.record_findings(). |
| **Failure** | Malformed LLM output → retry. FACT findings without evidence → rejected. |

### Responsibility 6: Finding Validation

| Aspect | Detail |
|---|---|
| **Input** | Generated findings. |
| **Processing** | Deterministic: verify evidence linkage for FACT-type findings, verify FindingType enum, verify temporal constraints (observation_date vs source_publication_date), verify finding categories are from the allowed set. |
| **Output** | Validation result with rejected findings list. |
| **Persistence** | Validation summary stored as ResearchArtifact. |
| **Failure** | Validation itself cannot fail (deterministic). |

### Responsibility 7: Gap & Contradiction Analysis

| Aspect | Detail |
|---|---|
| **Input** | Validated findings. |
| **Processing** | LLM reasoning: identify contradictory findings across sources (e.g., conflicting market size estimates). Deterministic: identify missing research dimensions (e.g., no findings for "regulatory_environment"). |
| **Output** | Contradiction findings (AI_INFERENCE, category "contradiction"), gap findings (UNCERTAINTY, category "research_gap"). |
| **Persistence** | Additional ResearchFinding records. |
| **Failure** | Non-critical. If LLM fails → gaps identified deterministically, contradictions skipped. |

---

## 5. Company Research vs Industry Research Boundary

### Clear Separation of Concerns

| Aspect | Company Research Agent (Phase 8) | Industry Research Agent (Phase 9) |
|---|---|---|
| **Primary entity** | Company (company.company table) | Industry (company.classification table, level=INDUSTRY) |
| **Research question** | "What does this company do?" | "What is the structure and attractiveness of this industry?" |
| **Source focus** | Company filings, annual reports, investor presentations, transcripts | Government publications, industry body reports, research reports, regulatory filings, sector news |
| **Finding categories** | company_identity, business_overview, business_model, revenue_streams, etc. | industry_structure, market_size, growth_drivers, entry_barriers, etc. |
| **agent_name** | `company_research_agent` | `industry_research_agent` |
| **ResearchDocument.company_id** | Set to the researched company's UUID | NULL (industry-level documents are not company-specific) |
| **Entry point** | Company identifier (NSE symbol, BSE code, ISIN) | Industry Classification UUID or company's industry_id |
| **Provider dependencies** | CorporateFilingsProvider, TranscriptProvider, NewsProvider, FinancialDataProvider, LLMProvider | SearchProvider, MacroDataProvider, NewsProvider, LLMProvider |

### How They Interact in the Multi-Agent Workflow

Per `architecture/agent-architecture.md`, the Industry Analysis Agent (#4) runs in parallel with the Business Model Agent (#3) and Competitor Analysis Agent (#9) after Financial Analysis (#2). The Company Research Agent (Phase 8) corresponds to agent #3 (extended with company validation and source discovery). The Industry Research Agent (Phase 9) corresponds to agent #4.

In the orchestration graph, both agents receive the company profile from the preceding step, but their research scope is independent:
- Phase 8 writes to `ResearchState.business_model` (or its equivalent findings).
- Phase 9 writes to `ResearchState.industry_analysis` (or its equivalent findings).
- Neither agent depends on the other's output.

### Overlapping Research Dimensions

Some research dimensions overlap between company and industry research. The boundary rule:

| Dimension | Phase 8 (Company) | Phase 9 (Industry) |
|---|---|---|
| Competitors mentioned | Extracts competitor names from company documents | Analyzes overall competitive structure and concentration |
| Revenue growth drivers | Company-specific growth drivers | Industry-level growth drivers |
| Risks | Company-specific operational risks | Industry-level structural risks |
| Regulatory mentions | Regulations mentioned in company filings | Regulatory environment analysis for the industry |
| Geographic exposure | Company's geographic breakdown | India's position in the global industry |

The Industry Research Agent never contradicts or overrides Company Research Agent findings. Both sets of findings are available for downstream agents (Moat, Valuation, Synthesis) to use and reconcile.

---

## 6. Request Contract

### IndustryResearchRequest

```python
class IndustryResearchRequest(BaseModel):
    """Input contract for initiating an Industry Research Agent run."""

    model_config = ConfigDict(frozen=True)

    industry_id: uuid.UUID
    observation_date: date
    initiated_by: str = Field(min_length=1, max_length=200)
    company_context_id: uuid.UUID | None = None
    configuration: IndustryResearchConfig | None = None
```

**Fields:**

- `industry_id` (required): UUID from the `company.classification` table where `level = INDUSTRY`. If the caller has a company but not its industry, they resolve `Company.industry_id` before calling.
- `observation_date` (required): The point-in-time anchor for all research. No source published after this date is considered.
- `initiated_by` (required): Audit trail — who or what triggered the research.
- `company_context_id` (optional): If this industry research was triggered by a company research workflow, the company UUID is recorded for provenance. This does NOT restrict the research to that company — the research covers the entire industry.
- `configuration` (optional): Agent-level overrides for token budget, source limits, model selection.

### IndustryResearchConfig

```python
class IndustryResearchConfig(BaseModel):
    """Agent-level configuration for an Industry Research Agent run."""

    model_config = ConfigDict(frozen=True)

    token_budget: int = Field(default=INDUSTRY_AGENT_TOKEN_BUDGET, gt=0)
    token_warning_threshold: int = Field(default=INDUSTRY_AGENT_TOKEN_WARNING, gt=0)
    max_llm_attempts: int = Field(default=MAX_LLM_ATTEMPTS, ge=1, le=3)
    document_types: list[DocumentType] | None = None
    source_limit: int = Field(default=30, ge=1, le=100)
    concurrent_retrievals: int = Field(default=5, ge=1, le=20)
    extraction_model: str | None = None
    generation_model: str | None = None
    analysis_model: str | None = None
```

### Design Decisions

- **industry_id, not sector_id**: The agent researches at the industry level (e.g., "IT Services") not the sector level (e.g., "Information Technology"). Sector-level aggregation is a downstream concern.
- **company_context_id is optional**: The agent can run standalone for industry research without a company context. When triggered from the multi-agent workflow, the company context provides audit linkage but does not change the research scope.
- **source_limit defaults to 30**: Industry research typically requires more sources than company research because data is spread across government, industry body, and news sources rather than concentrated in company filings.

---

## 7. Industry Taxonomy Model

### Existing Classification Infrastructure

The `company.classification` table (Phase 3, `backend/app/models/company.py`) provides the industry taxonomy:

```
Classification
    id: UUID (PK)
    name: str
    code: str
    level: ClassificationLevel (SECTOR or INDUSTRY)
    parent_id: FK → Classification (nullable; Industry → Sector)
    description: str | None
    is_active: bool
```

### How the Industry Research Agent Uses the Taxonomy

1. **Entry point resolution**: The agent receives `industry_id` and queries Classification to resolve the industry name, code, and parent sector.
2. **Sector context**: The parent sector (via `parent_id`) provides context for the industry research. An industry like "IT Services" exists within the "Information Technology" sector, and sector-level dynamics inform industry analysis.
3. **Peer industry discovery**: Other industries sharing the same `parent_id` (i.e., sibling industries within the same sector) may be relevant for comparative context but are not researched in depth.
4. **Company enumeration**: Companies in the researched industry are discoverable via `Company.industry_id`, enabling the agent to identify industry participants. The agent does NOT perform company-level research on these companies — it uses them to understand market structure and concentration.

### Taxonomy Integrity Requirements

- The agent MUST validate that the provided `industry_id` resolves to a Classification record with `level = INDUSTRY`.
- The agent MUST resolve and record the parent sector for contextual completeness.
- The agent does NOT modify the Classification table. Taxonomy management is a separate administrative function.

---

## 8. Temporal Model

### Reused from Phase 8 Without Modification

The Industry Research Agent applies the same temporal model as Phase 8:

**Canonical rule:** `information_available_date <= observation_date`

- `observation_date` is set on the IndustryResearchRequest.
- Every finding records both `observation_date` and `source_publication_date`.
- Source discovery filters out sources published after `observation_date`.
- Finding validation (Step 6) rejects findings where `source_publication_date > observation_date`.
- Phase 7's `ResearchRunService._validate_temporal_consistency()` is reused without modification.

### Industry-Specific Temporal Considerations

Industry data sources have different temporal characteristics than company filings:

| Source Type | Typical Frequency | Temporal Freshness Concern |
|---|---|---|
| Government statistical publications | Quarterly or annual | May be 3-6 months stale; the agent records the actual `as_of_date` of the data, not the publication date |
| Industry body annual reports | Annual | May cover the prior year; `document_date` reflects the period covered |
| Research reports | Ad hoc | May contain projections; forward-looking content classified as AI_INFERENCE or ASSUMPTION, never FACT |
| Regulatory filings | Event-driven | Date-specific; directly usable |
| Sector news | Daily | Most temporally current; but lower reliability tier |

The agent records both `document_date` (the period the content covers) and `publication_date` (when the document was published/filed). The temporal filter uses `publication_date <= observation_date`.

---

## 9. Source Hierarchy for Industry Research

### Industry-Adjusted Source Tiers

The three-tier hierarchy (TIER_1, TIER_2, TIER_3) is reused from ADR-004 and Phase 8. However, industry research shifts the relative importance of tiers:

```
TIER_1: Official sources
    │   Exchange filings containing industry data (NSE/BSE industry reports)
    │   SEBI regulations affecting the industry
    │   RBI publications (for financial services industries)
    │   Government of India publications (Ministry of Statistics, DPIIT)
    │
TIER_2: Government data and industry bodies — PRIMARY SOURCE FOR INDUSTRY RESEARCH
    │   NASSCOM (IT/BPO industry)
    │   SIAM (automotive industry)
    │   IBEF (India Brand Equity Foundation)
    │   CII / FICCI (cross-sector industry data)
    │   Ministry-specific publications
    │   Industry association reports
    │
TIER_3: Publications, news, research reports
        Research reports (broker/analyst)
        Business press (Economic Times, Business Standard, Mint)
        International industry databases
```

### Key Difference from Phase 8

In Phase 8 (company research), Tier 1 company filings are the dominant source. In Phase 9 (industry research), **Tier 2 sources are the primary data source** for most industries. Government and industry body publications provide the most authoritative industry-level data (market size, growth rates, concentration metrics).

Tier 1 remains authoritative for regulatory environment analysis (SEBI circulars, RBI guidelines) and for cross-referencing industry claims against actual company filings.

### Source Type Mapping

The existing `SourceType` enum already supports industry research sources:

| SourceType | Industry Research Relevance |
|---|---|
| `GOVERNMENT` | Ministry publications, statistical data |
| `INDUSTRY_BODY` | NASSCOM, SIAM, IBEF, CII, FICCI |
| `REGULATOR` | SEBI, RBI, sectoral regulators |
| `EXCHANGE` | NSE/BSE industry-level reports |
| `COMPANY` | Used indirectly — company filings provide data about industry structure |
| `NEWS` | Sector news coverage |
| `RESEARCH` | Broker/analyst industry reports |

### DocumentType Mapping

The existing `DocumentType` enum supports industry research documents:

| DocumentType | Industry Research Usage |
|---|---|
| `GOVERNMENT_PUBLICATION` | Primary source for industry statistics and policy |
| `RESEARCH_REPORT` | Industry analysis reports from brokers, consultancies |
| `FILING` | Regulatory filings with industry implications |
| `NEWS` | Sector news for event-driven industry analysis |
| `ANNUAL_REPORT` | Company annual reports containing industry context sections (these have a company_id) |

No new enum values are required.

---

## 10. Tool Architecture

### Tool Contract (Reused from Phase 8)

Every tool follows the `AgentTool` contract from `architecture/agent-architecture.md`:

```python
class AgentTool:
    name: str
    description: str
    input_schema: type[BaseModel]     # Pydantic model
    output_schema: type[BaseModel]    # Pydantic model
    requires_auth: bool
    timeout_seconds: int
    max_retries: int
    audit_logged: bool = True
    version: str
```

### Industry Research Agent Tools

The agent has access to exactly 8 tools (matching Phase 8's tool count for architectural consistency):

| # | Tool | Step | Type | New/Reused |
|---|---|---|---|---|
| 1 | `validate_industry` | 1 | Deterministic | **New** |
| 2 | `discover_industry_sources` | 2 | Provider call | **New** |
| 3 | `retrieve_document` | 3 | Provider call | **Reused from Phase 8** |
| 4 | `search_industry_data` | 2, 3 | Provider call | **New** |
| 5 | `get_macro_indicators` | 2 | Provider call | **New** |
| 6 | `get_industry_companies` | 2, 5 | Deterministic | **New** |
| 7 | `persist_evidence` | 4 | Persistence | **Reused from Phase 8** |
| 8 | `persist_findings` | 5, 7 | Persistence | **Reused from Phase 8** |

### Tool 1: validate_industry

```python
class ValidateIndustryInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    industry_id: uuid.UUID

class ValidateIndustryOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    industry_id: uuid.UUID
    industry_name: str
    industry_code: str
    sector_id: uuid.UUID
    sector_name: str
    sector_code: str
    company_count: int
```

### Tool 2: discover_industry_sources

```python
class DiscoverIndustrySourcesInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    industry_name: str
    sector_name: str
    observation_date: date
    document_types: list[DocumentType] | None = None
    limit: int = Field(default=30, ge=1, le=100)

class DiscoverIndustrySourcesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidates: list[SourceCandidate]
```

This tool queries `SearchProvider.search()` with industry-specific queries, `NewsProvider.search_news()` with sector keywords, and discovers existing `ResearchDocument` records with matching industry context. It returns `SourceCandidate` (reused from Phase 8 contracts) normalized across all provider types.

### Tool 3: retrieve_document (Reused)

Identical to Phase 8's `retrieve_document` tool. Uses `RetrieveDocumentInput` and `RetrieveDocumentOutput` from `app.agents.contracts`.

### Tool 4: search_industry_data

```python
class SearchIndustryDataInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    query: str = Field(min_length=1, max_length=500)
    industry_name: str
    observation_date: date
    num_results: int = Field(default=10, ge=1, le=50)

class SearchIndustryDataOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    results: list[IndustrySearchResult]

class IndustrySearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    url: str
    snippet: str
    source_type: str
    published_date: date | None = None
```

This tool wraps `SearchProvider.search()` with industry-contextualized queries. It constructs search queries that combine the industry name with specific research dimensions (e.g., "{industry_name} India market size TAM", "{industry_name} regulatory framework India").

### Tool 5: get_macro_indicators

```python
class GetMacroIndicatorsInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    indicator_ids: list[str] = Field(min_length=1, max_length=20)
    start_date: date | None = None
    end_date: date | None = None

class GetMacroIndicatorsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    indicators: list[MacroIndicatorResult]

class MacroIndicatorResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    indicator_id: str
    indicator_name: str
    latest_value: Decimal
    as_of_date: date
    unit: str
    source: str
```

This tool wraps `MacroDataProvider.get_indicator()` and is used to retrieve industry-relevant macro indicators (e.g., industry-specific production indices, sectoral GDP contribution). The tool is read-only; it does not compute derived values.

### Tool 6: get_industry_companies

```python
class GetIndustryCompaniesInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    industry_id: uuid.UUID
    limit: int = Field(default=20, ge=1, le=100)

class GetIndustryCompaniesOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    companies: list[IndustryCompanyRecord]
    total_count: int

class IndustryCompanyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    company_id: uuid.UUID
    name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    market_cap: Decimal | None = None
    is_active: bool
```

This tool queries `Company.industry_id` to enumerate companies in the industry. Used for concentration analysis and to provide context to the LLM about industry participants. The tool returns basic profiles — it does NOT retrieve company financials (that belongs to the Financial Analysis Agent and the analytics engine).

### Tool 7: persist_evidence (Reused)

Identical to Phase 8. Uses `PersistEvidenceInput` and `PersistEvidenceOutput` from `app.agents.contracts`.

### Tool 8: persist_findings (Reused)

Identical to Phase 8. Uses `PersistFindingsInput` and `PersistFindingsOutput` from `app.agents.contracts`. The only difference: `FindingItem.agent_name` defaults to `INDUSTRY_AGENT_NAME = "industry_research_agent"`.

---

## 11. Provider Architecture

### Provider Dependencies

| Provider Protocol | Used By Phase 9 | Purpose |
|---|---|---|
| `SearchProvider` | **Yes — NEW dependency** | Web search for industry reports, government data, research publications |
| `MacroDataProvider` | **Yes — NEW dependency** | Industry-level macro indicators (production indices, sectoral GDP) |
| `NewsProvider` | **Yes — Reused** | Sector and industry news |
| `LLMProvider` | **Yes — Reused** | Evidence extraction, finding generation, contradiction analysis |
| `CorporateFilingsProvider` | No | Phase 8 dependency; Phase 9 uses SearchProvider instead |
| `TranscriptProvider` | No | Phase 8 dependency; transcripts are company-specific |
| `FinancialDataProvider` | No | Financial data is company-specific |
| `MarketDataProvider` | No | Market data is company-specific |
| `ShareholdingProvider` | No | Shareholding is company-specific |
| `CorporateActionsProvider` | No | Corporate actions are company-specific |
| `EmbeddingProvider` | No | Deferred to semantic search integration |

### New Provider Dependencies: SearchProvider and MacroDataProvider

These two providers are defined in `backend/app/providers/interfaces.py` as Protocol interfaces but currently only have mock implementations (via `MockProvider` in `backend/app/providers/mock.py`).

**SearchProvider:**
```python
@runtime_checkable
class SearchProvider(Protocol):
    async def search(self, query: str, *, num_results: int = 10) -> list[SearchResult]: ...
    async def check_health(self) -> ProviderHealth: ...
```

Phase 9 implementation requires a concrete SearchProvider (e.g., Google Custom Search, Bing Search, SerpAPI). The mock provider is sufficient for testing and development.

**MacroDataProvider — LIMITED Dependency (Reconciliation Decision):**

```python
@runtime_checkable
class MacroDataProvider(Protocol):
    async def get_indicator(
        self, indicator_id: str, *, start: date | None = None, end: date | None = None
    ) -> MacroSeries: ...
    async def list_indicators(self) -> list[MacroIndicatorInfo]: ...
    async def check_health(self) -> ProviderHealth: ...
```

**Reconciliation note:** The original draft listed MacroDataProvider as a peer dependency alongside SearchProvider. After reconciliation, the relationship is clarified as a **limited, non-critical dependency**:

- **Phase 9 uses MacroDataProvider for industry-specific indicators only:** Industrial production index (IIP) for manufacturing, credit growth for banking, auto sales SIAM data for automotive. These are industry context, not macro analysis.
- **Phase 13 (Macro Economics Agent #8) owns full macro analysis:** GDP, inflation, interest rates, exchange rates, fiscal policy. Phase 9 does NOT perform macro analysis.
- **Phase 9 degrades gracefully without MacroDataProvider:** If the provider is unavailable (health check fails or mock returns empty), the agent produces UNCERTAINTY findings for macro-dependent dimensions and continues. No step fails on MacroDataProvider unavailability alone.
- **The `get_macro_indicators` tool (Tool 5) is the ONLY Phase 9 touch point with MacroDataProvider.** It makes 1-3 calls per run for industry-specific indicators, not the full macro indicator catalog.
- **Concrete implementation is NOT required for Phase 9:** The mock provider is sufficient. A concrete MacroDataProvider (RBI DBIE, data.gov.in) can be implemented alongside Phase 13 or earlier, but Phase 9 does not block on it.

**Decision:** MacroDataProvider is a **direct but limited and non-blocking** dependency for Phase 9. The agent calls it, handles its absence gracefully, and does not attempt macro analysis.

### Provider Injection

The agent receives provider instances through constructor injection, following the Phase 8 pattern:

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

No concrete provider is imported by the agent module. The factory (`ProviderFactory`) resolves the active providers based on configuration.

---

## 12. Evidence Architecture

### Reused from Phase 8 Without Modification

The evidence chain is identical to Phase 8:

```
Source                    (research.source)
    │
    ▼
ResearchDocument          (research.research_document)
    │
    ├── DocumentVersion   (research.document_version)
    │
    ▼
Evidence                  (research.evidence)
    │
    ▼
research_finding_evidence (junction table)
    │
    ▼
ResearchFinding           (research.research_finding)
```

### Industry-Specific Evidence Considerations

1. **ResearchDocument.company_id = NULL.** Industry-level documents (government publications, industry body reports) are not associated with a specific company. The `company_id` field on `ResearchDocument` is already nullable (verified in `backend/app/models/research.py`), so no schema change is needed.

2. **Source registration.** Industry data sources must be registered in the `Source` table with appropriate `source_type` and `default_tier`:
   - NASSCOM → `source_type=INDUSTRY_BODY`, `default_tier=TIER_2`
   - Ministry of Statistics → `source_type=GOVERNMENT`, `default_tier=TIER_2`
   - SEBI → `source_type=REGULATOR`, `default_tier=TIER_1`
   - Research reports → `source_type=RESEARCH`, `default_tier=TIER_3`

3. **EvidenceType usage.** The same `EvidenceType` enum applies:
   - `FACT` — Verifiable industry statistics from authoritative sources.
   - `FINANCIAL_DATA` — Industry-level financial aggregates (market size, growth rates).
   - `MANAGEMENT_STATEMENT` — Rarely used at industry level; may appear when industry body leaders make claims.
   - `ANALYST_OPINION` — Broker/analyst views on industry outlook.
   - `REGULATORY_FILING` — Regulatory actions affecting the industry.

4. **Evidence quality.** The same three-mechanism quality representation applies: SourceTier, ConfidenceLevel, and SourceReliability.

---

## 13. Finding Architecture

### Reused from Phase 8

The `FindingItem` contract from `app.agents.contracts` is reused with one modification — the `agent_name` default:

```python
INDUSTRY_AGENT_NAME: str = "industry_research_agent"

class FindingItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: str = Field(default=INDUSTRY_AGENT_NAME, max_length=100)
    finding_type: FindingType
    category: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    confidence: ConfidenceLevel
    observation_date: date | None = None
    source_publication_date: date | None = None
    evidence_ids: list[uuid.UUID] | None = None
```

### FindingType Usage for Industry Research

| FindingType | Industry Research Usage | Evidence Required |
|---|---|---|
| `FACT` | Verifiable industry statistic (e.g., "IT services industry TAM in FY2024 was $245B globally") | Yes — must link to source evidence |
| `CALCULATION` | Derived industry metric (e.g., industry concentration ratio computed from company market caps) | Yes — references input data |
| `MANAGEMENT_CLAIM` | Claims by industry body leaders or company executives about industry outlook | Yes — must link to evidence of type MANAGEMENT_STATEMENT |
| `ANALYST_OPINION` | Broker/analyst views on industry trajectory | Yes — links to analyst report evidence |
| `AI_INFERENCE` | Agent's synthesis (e.g., "Entry barriers in this industry appear moderate based on...") | Not required — but references informing evidence in content |
| `ASSUMPTION` | Assumptions made to proceed (e.g., "Assuming government incentive scheme continues") | Not required |
| `UNCERTAINTY` | Missing information (e.g., "Accurate industry concentration data not available from public sources") | Not required |

### Finding Persistence

Findings are persisted through `ResearchRunService.record_findings()`, the same Phase 7 service method used by Phase 8. The `PersistFindingsInput` contract is reused without modification.

---

## 14. Finding Categories

### Reconciliation Note

The original draft had 15 categories. After reconciliation analysis, `growth_rate` was merged into `growth_drivers` — they are semantically inseparable (growth rate IS the quantitative measure of growth drivers). This yields 14 categories, matching Phase 8's category count for consistency.

### Industry Research Finding Categories

The Industry Research Agent uses a distinct set of finding categories from Phase 8. These categories map to the research dimensions in `docs/research-methodology.md` §B:

```python
INDUSTRY_FINDING_CATEGORIES: frozenset[str] = frozenset({
    "industry_structure",        # Concentration, fragmentation, key players, market shares
    "market_size",               # TAM, SAM, current industry revenue
    "growth_drivers",            # What drives growth; includes historical and projected growth rates
    "entry_barriers",            # Barriers to new entrants (Porter's Force: Threat of New Entrants)
    "supplier_power",            # Porter's Force: supplier bargaining power
    "buyer_power",               # Porter's Force: buyer bargaining power
    "substitution_risk",         # Porter's Force: threat of substitutes
    "competitive_rivalry",       # Porter's Force: intensity of rivalry
    "regulatory_environment",    # Regulations, licensing, compliance, government incentives
    "cyclicality",               # Industry cyclicality and commodity exposure
    "india_global_position",     # India's competitive position globally
    "industry_risk",             # Industry-level structural risks
    "research_gap",              # Missing information (type=UNCERTAINTY)
    "contradiction",             # Contradictory evidence across sources (type=AI_INFERENCE)
})
```

### Category Design Rationale

1. **14 categories (matching Phase 8 count).** Not a hard constraint but a useful signal of appropriate granularity.
2. **`growth_rate` merged into `growth_drivers`.** A finding like "IT services industry grew at 8.4% CAGR FY2019–FY2024" is both a growth rate and a growth driver observation. Separate categories would force an arbitrary classification that hurts queryability. Growth rate data is expressed as FACT findings within `growth_drivers`; growth driver synthesis is expressed as AI_INFERENCE findings in the same category.
3. **`entry_barriers` is a Porter's Force finding AND a standalone research dimension.** The category serves double duty. This is intentional — entry barriers are both one of the Five Forces and a standalone attractiveness indicator. No duplication occurs because the finding content distinguishes the analytical context.
4. **`regulatory_environment` subsumes government incentives.** PLI schemes, subsidies, and tax benefits are regulatory/policy interventions, not a separate category.

### Relationship to Phase 8 Categories

Phase 8 `FINDING_CATEGORIES` (14 categories) and Phase 9 `INDUSTRY_FINDING_CATEGORIES` (14 categories) are **mostly disjoint** with a deliberate 3-category overlap: `growth_drivers`, `research_gap`, and `contradiction`. The overlap is intentional — `growth_drivers` captures a genuine semantic parallel at different analysis levels, while `research_gap` and `contradiction` are meta-categories that apply to any research domain. Downstream consumers MUST filter by `agent_name` alongside `category` when querying these shared categories.

| Phase 8 (Company) | Phase 9 (Industry) | Overlap Risk |
|---|---|---|
| `competitive_context` | `competitive_rivalry` | Distinct: company-level mentions vs industry-level structural analysis |
| `growth_drivers` | `growth_drivers` | **NAME COLLISION** — resolved by querying `agent_name` alongside `category` |
| `risk` | `industry_risk` | Distinct: company-specific vs industry-level |

**Important:** Three categories appear in both Phase 8 and Phase 9 sets: `growth_drivers`, `research_gap`, and `contradiction`. For `growth_drivers`, the semantic overlap is genuine — both agents produce growth driver findings, but at different levels of analysis (company vs industry). For `research_gap` and `contradiction`, these are meta-categories that apply universally across research domains. Downstream consumers MUST filter by `agent_name` when querying any of these shared categories. The alternative (renaming to `industry_growth_drivers`) was rejected because it creates an artificial naming convention that doesn't generalize to agents 5-17.

### Queryability Contract

Downstream agents and the API layer can query findings using:
- `agent_name = "industry_research_agent"` — all Phase 9 findings
- `agent_name + category` — specific dimension (e.g., `industry_research_agent` + `entry_barriers`)
- `category IN (porter_categories)` — all Five Forces findings, where `porter_categories = {"entry_barriers", "supplier_power", "buyer_power", "substitution_risk", "competitive_rivalry"}`

### Category Validation

Finding validation (Step 6) verifies that every finding's `category` field is a member of `INDUSTRY_FINDING_CATEGORIES`. Findings with invalid categories are rejected.

---

## 15. Economics Boundary

### What the Industry Research Agent Computes

The agent does NOT perform financial calculations. It produces findings about industry economics based on extracted evidence:

- **Market size** (TAM, SAM): Extracted from industry reports as FACT findings, not computed.
- **Growth rates**: Extracted from source data as FACT findings. The agent does NOT compute CAGR or growth rates from raw data — that is the analytics engine's responsibility.
- **Industry revenue and margin benchmarks**: Extracted from industry reports as FACT findings.
- **Concentration metrics** (Herfindahl index, CR4/CR10): May be computed deterministically from company market cap data available through the `get_industry_companies` tool. If computed, the finding type is CALCULATION with the computation method documented. If extracted from a source, the finding type is FACT.

### What Belongs to Other Agents

- Company-level financial metrics: Financial Analysis Agent (#2).
- Company-specific revenue growth: Company Research Agent (#3, Phase 8).
- Macro indicators interpretation: Macro Economics Agent (#8).
- Valuation multiples: Valuation Agent (#10).

### Decimal Discipline

Per ADR-003, all financial values within findings use `Decimal`. Market size figures extracted from documents are parsed to `Decimal` at the provider boundary. The agent never uses floating-point for financial values.

---

## 16. Competitive Dynamics Boundary

### Reconciliation Note

This section was expanded during reconciliation to include concrete examples for each boundary line, required by the reconciliation specification.

### What the Industry Research Agent Covers

The agent analyzes competitive dynamics at the **industry level**:

- **Industry concentration**: How fragmented or consolidated is the industry? Top N player market shares.
- **Competitive intensity**: Pricing pressure, margin trends across the industry.
- **New entrant activity**: Recent entries or exits.
- **Competitive landscape evolution**: Consolidation trends, M&A activity at the industry level.

### What Belongs to Other Agents

- **Company-vs-company comparison**: Competitor Analysis Agent (#9).
- **Specific company's competitive moat**: Competitive Moat Agent (#5, Phase 10).
- **Company's competitive position within the industry**: Phase 8 covers surface-level competitive context.

### Concrete Boundary Examples

**Example: Private Banking Industry**

| Research Finding | Owner | Why |
|---|---|---|
| "India's private banking sector has CR5 of 68% by assets as of FY2024" | **Phase 9 (Industry)** — `industry_structure`, FACT | Industry-level concentration metric |
| "HDFC Bank holds 14.2% market share in private sector deposits" | **Phase 9 (Industry)** — `competitive_rivalry`, FACT | Industry participant data for structure analysis |
| "HDFC Bank's CASA ratio of 42% is above the 35% industry average" | **Competitor Agent (#9)** | Company-vs-industry benchmarking |
| "HDFC Bank's branch network density creates a distribution moat" | **Moat Agent (#5)** | Company-specific competitive advantage |
| "New entrants require RBI banking license; no new universal banking license issued since 2015" | **Phase 9 (Industry)** — `entry_barriers`, FACT | Industry-level entry barrier |
| "HDFC Bank's technology platform enables lower cost-to-income vs peers" | **Phase 8 (Company)** — `competitive_context` | Company-level competitive observation |

**Example: IT Services Industry**

| Research Finding | Owner | Why |
|---|---|---|
| "India IT services TAM estimated at $245B globally in FY2024" | **Phase 9 (Industry)** — `market_size`, FACT | Industry-level market size |
| "Top 5 Indian IT firms (TCS, Infosys, Wipro, HCL, Tech Mahindra) hold ~35% of India's IT export revenue" | **Phase 9 (Industry)** — `industry_structure`, FACT | Industry concentration |
| "TCS revenue growth of 8.2% outpaced industry average of 3.8% in FY2024" | **Competitor Agent (#9)** | Company vs industry comparison |
| "TCS's vendor lock-in through large multi-year contracts creates switching cost moat" | **Moat Agent (#5)** | Company-specific moat assessment |
| "Cloud migration and GenAI adoption are the primary industry growth drivers" | **Phase 9 (Industry)** — `growth_drivers`, AI_INFERENCE | Industry-level growth analysis |
| "Macro Economics Agent (#8) provides USD/INR impact on sector margins" | **Macro Agent (#8)** | Macro factor, not industry structure |

### Porter's Five Forces as Structured Output

The Five Forces analysis is NOT a free-form LLM essay. Each force is a separate finding with its own category, evidence linkage, and confidence:

| Porter's Force | Finding Category | Expected Finding Content |
|---|---|---|
| Threat of new entrants | `entry_barriers` | Entry barriers strength assessment with evidence |
| Supplier bargaining power | `supplier_power` | Supplier concentration, switching costs, evidence |
| Buyer bargaining power | `buyer_power` | Buyer concentration, price sensitivity, evidence |
| Threat of substitutes | `substitution_risk` | Substitute products/services, switching costs |
| Competitive rivalry | `competitive_rivalry` | Number of competitors, growth rate, differentiation |

Each force may generate multiple findings of different types (FACT for evidence-backed observations, AI_INFERENCE for synthesis, UNCERTAINTY for missing data).

### Five Forces → Downstream Agent Mapping

| Phase 9 Finding | Consuming Agent | How It's Used |
|---|---|---|
| `entry_barriers` findings | Moat Agent (#5) | High entry barriers → stronger moat durability assessment |
| `competitive_rivalry` findings | Competitor Agent (#9) | Industry rivalry context for company-level comparison |
| `supplier_power` findings | Moat Agent (#5) | Supplier power informs cost advantage and supply chain moat types |
| `buyer_power` findings | Moat Agent (#5) | Buyer power informs pricing power and switching cost moat types |
| `substitution_risk` findings | Risk Agent (#11) | Substitution threat feeds into industry risk for the company |

---

## 17. Regulatory Research Boundary

### What the Industry Research Agent Covers

- **Regulatory framework**: Key regulations governing the industry (e.g., TRAI for telecom, RBI for banking, SEBI for financial services).
- **Licensing requirements**: Entry permits, operational licenses.
- **Compliance burden**: Regulatory costs and constraints.
- **Recent regulatory changes**: Policy changes within the observation window.
- **Government incentives**: PLI schemes, subsidies, tax benefits affecting the industry.

### What Belongs to Other Agents

- **Company-specific regulatory compliance**: Management & Governance Agent (#6).
- **Macro policy analysis**: Macro Economics Agent (#8).
- **Regulatory risk scoring for a specific company**: Risk Agent (#11).

### Regulatory Data Sources

Regulatory data comes primarily from:
- Tier 1: SEBI circulars, RBI guidelines, ministry notifications (via CorporateFilingsProvider or SearchProvider).
- Tier 2: Regulatory body annual reports, industry body regulatory summaries.
- Tier 3: Legal and regulatory news coverage.

---

## 18. Contradiction Handling

### Reused from Phase 8 (§14)

The contradiction handling strategy is identical to Phase 8:

1. **Preserve both sides.** When two sources disagree about an industry fact (e.g., NASSCOM reports industry growth at 8% while a broker report says 12%), both findings are persisted as separate ResearchFinding records, each with its own evidence linkage.
2. **Generate a contradiction finding.** A separate finding of type `AI_INFERENCE` with category `"contradiction"` documents the disagreement, referencing both conflicting evidence records.
3. **Do NOT resolve contradictions.** The agent does not pick a winner. Downstream agents (Research Synthesis) make the judgment call with access to both findings.

### Industry-Specific Contradiction Patterns

Industry research commonly encounters these contradiction patterns:

| Pattern | Example | Handling |
|---|---|---|
| Conflicting market size estimates | NASSCOM vs McKinsey on TAM | Both persisted; contradiction finding generated |
| Growth rate disagreements | Government data vs industry body projections | Both persisted; source tier noted in finding |
| Regulatory interpretation differences | Different sources interpreting a regulation differently | Both persisted; UNCERTAINTY finding added |

---

## 19. Gap Handling

### Reused from Phase 8 (§15)

Gap detection is deterministic. The agent checks whether findings exist for each expected research dimension. The dimensions list matches the non-meta categories from `INDUSTRY_FINDING_CATEGORIES` (excludes `research_gap` and `contradiction` which are outputs of gap/contradiction analysis itself):

```python
EXPECTED_INDUSTRY_DIMENSIONS: list[str] = [
    "market_size",
    "growth_drivers",           # includes growth rates (merged from former "growth_rate")
    "industry_structure",
    "entry_barriers",
    "supplier_power",
    "buyer_power",
    "substitution_risk",
    "competitive_rivalry",
    "regulatory_environment",
    "cyclicality",
    "india_global_position",
    "industry_risk",
]
```

This is 12 dimensions. For each dimension with no findings, a finding of type `UNCERTAINTY` with category `"research_gap"` is generated, describing what information is missing and why.

### Industry-Specific Gap Considerations

Some industries have inherently limited public data:
- Unorganized or informal sectors may lack reliable market size data.
- Nascent industries may lack historical growth data.
- Government-dominated industries may lack competitive dynamics data.

The agent acknowledges these structural data limitations as `UNCERTAINTY` findings rather than manufacturing estimates.

---

## 20. ResearchRun Integration

### Reconciliation Note — ResearchRun Target Semantics

This section was completely rewritten during reconciliation. The original draft proposed nullable `company_id` + `industry_id` FK without analyzing the existing schema fields or evaluating against all 17 agents. This reconciled version evaluates three options against the actual ResearchRun model.

### Existing ResearchRun Fields (Critical Context)

The current `ResearchRun` model already has fields relevant to this decision:

```python
# backend/app/models/research.py (lines 191-201)
company_id: Mapped[uuid.UUID] = mapped_column(
    sa.ForeignKey("company.company.id"), nullable=False,
)
run_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
trigger_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
    sa.ForeignKey("research.research_run.id"), nullable=True,
)
```

- `company_id` is NOT NULL with a FK to `company.company.id`.
- `run_type` is a nullable String(50) — **already in active use for execution-mode semantics** (see below).
- `trigger_type` is a nullable String(50) — also unused by Phase 8.
- `parent_run_id` is a self-referential FK (nullable) with an existing index (`ix_research_run_parent`).

#### run_type Has Existing Semantics (Second Reconciliation Finding)

**This finding was discovered during the second reconciliation pass.** The first reconciliation incorrectly described `run_type` as "unused by Phase 8 but available for semantic tagging." In fact, `run_type` already has defined semantics across multiple layers:

| Source | Values | Meaning |
|---|---|---|
| Phase 7 architecture (§5.1) | FULL, INCREMENTAL, THESIS_UPDATE, MONITORING | Execution mode — determines which agents execute and what token budgets apply |
| Phase 8 agent code (`agent.py:148`) | `"company_research"` | Execution mode — identifies this as a company research run |
| Phase 7 test suite | `"FULL"`, `"INCREMENTAL"` | Verified in assertions (lines 149, 303) |
| `ResearchRunCreate` schema (`schemas/research_run.py:28`) | `run_type: str = Field(max_length=50)` | **Required field** (not nullable) in the API contract |

**Conclusion:** `run_type` describes the **execution mode** (HOW the research is performed), not the **target type** (WHAT is being researched). An industry research run can be FULL or INCREMENTAL. Setting `run_type = "industry"` would conflate two orthogonal dimensions. A separate `target_type` discriminator field is required.

### Three Options Evaluated

#### Option A: Nullable company_id + industry_id FK + target_type Discriminator

```python
target_type: Mapped[str] = mapped_column(
    sa.String(50), nullable=False, server_default="company",
)
company_id: Mapped[uuid.UUID | None] = mapped_column(
    sa.ForeignKey("company.company.id"), nullable=True,
)
industry_id: Mapped[uuid.UUID | None] = mapped_column(
    sa.ForeignKey("company.classification.id"), nullable=True,
)
# XOR CHECK — exactly one target FK is set, consistent with target_type:
# CHECK (
#   (target_type = 'company' AND company_id IS NOT NULL AND industry_id IS NULL)
#   OR (target_type = 'industry' AND company_id IS NULL AND industry_id IS NOT NULL)
# )
```

**Pros:**
- Semantically precise: the FK target type matches the research target type.
- True mutual exclusivity: a run is "about" exactly one entity type — never both, never neither.
- `target_type` is orthogonal to `run_type` (execution mode). An industry run can be FULL, INCREMENTAL, etc.
- Existing queries by `company_id` require only a null check (minor).
- `target_type` enables efficient filtering without FK introspection: `WHERE target_type = 'industry'`.

**Cons:**
- Making `company_id` nullable is a significant change — 3 existing indexes include `company_id`. All Phase 8 code and repository queries assume non-null.
- Does not generalize to agents 5-17. The Macro Economics Agent (#8) researches macro indicators, not a company or industry. The Risk Agent (#11) may aggregate across multiple entities. Each new target type would require yet another nullable FK column.
- The domain model (`architecture/domain-model.md`) describes `ResearchRun.company_id` as required. Changing it has documentation and mental model impact.

#### Option B: Generic ResearchTarget Abstraction

```python
class ResearchTarget(Base):
    id: uuid.UUID
    target_type: str  # "company", "industry", "macro", "portfolio"
    target_entity_id: uuid.UUID  # FK to varying tables
```

**Pros:**
- Fully generic — any future target type is one row, no schema change.

**Cons:**
- Polymorphic FK (target_entity_id points to different tables depending on target_type) breaks referential integrity at the DB level.
- Over-engineering for the current need. Only 2 of 17 agents need non-company targets (Industry #4, Macro #8). Several more might (Portfolio Monitoring #17), but that's speculative.
- Violates CLAUDE.md §4 ("No over-engineering: build what is needed for the current phase").
- Significant refactor of existing code for an abstraction that may never be needed beyond industry.

#### Option C: Child-Run Pattern Using Existing Fields

Keep `company_id` NOT NULL. Industry research runs are created as child runs of a company research workflow, using the existing `parent_run_id` and `run_type` fields:

```python
# Industry research run within a company research workflow:
ResearchRun(
    company_id=<the triggering company's UUID>,
    run_type="industry",  # PROBLEM: conflicts with run_type's execution-mode semantics
    parent_run_id=<the company run's UUID>,
    trigger_type="workflow",
)
```

For standalone industry research (no company context), an industry research run would use a "context company" — any company in that industry — as the `company_id`, with `run_type="industry"` distinguishing it from a company run.

**Pros:**
- Zero schema migration. All existing code, indexes, and queries continue to work unchanged.
- `parent_run_id` already exists with an index.
- Phase 8 code and repository methods require zero changes.

**Cons:**
- **`run_type` already has defined semantics.** Phase 7 specifies run_type as execution mode (FULL, INCREMENTAL, THESIS_UPDATE, MONITORING). Phase 8 uses "company_research". Setting `run_type = "industry"` conflates execution mode with target type. An industry research run that is also FULL would lose its execution-mode classification.
- Semantically imprecise for standalone runs — `company_id` doesn't mean "this run is about this company" for industry runs.
- The "context company" pattern is a hack — which company in the industry is the canonical context company? Not deterministic.
- Downstream queries for "all industry runs" require `WHERE run_type = 'industry'` AND joining through the company to get the industry_id. Indirect and fragile.
- For the 17-agent orchestration workflow, industry research always runs in the context of a company being analyzed. But the architecture document (§6) explicitly states that the agent "can run standalone for industry research without a company context." Option C makes standalone impossible without the context-company hack.

### Decision: OPTION A WITH TARGET_TYPE DISCRIMINATOR

**Option A is selected** (nullable `company_id` + `industry_id` FK + explicit `target_type` discriminator) with the following mitigations for the cons:

1. **Index impact is manageable.** The 3 existing indexes that include `company_id` remain valid — they continue to index non-null values for company runs. A new partial index for industry runs covers the industry path:
   ```sql
   CREATE INDEX ix_research_run_industry ON research.research_run (industry_id, started_at DESC)
       WHERE industry_id IS NOT NULL;
   ```

2. **Phase 8 code impact is minimal.** Phase 8 always sets `company_id`. The DB column becomes nullable, but Phase 8 callers always provide a non-null company_id. The `target_type` column has `server_default="company"`, so Phase 8 runs are automatically classified. Phase 8 code does NOT need to be modified to set `target_type` — the server default handles it.

3. **Forward compatibility for agents 5-17.** The remaining agents that need non-company targets:
   - **Macro Economics Agent (#8):** Will need a `macro_context_id` or similar. When that arrives (Phase 13+), it can be added as another nullable FK, with `target_type = "macro"` added to the check constraint. Each new target type = one new nullable FK column + one new `target_type` value. This pattern scales to 2-3 additional target types without the polymorphic FK problem of Option B.
   - **Portfolio Monitoring Agent (#17):** Runs against a watchlist, which is a company-scoped concept. No schema change needed.
   - **All other agents (#2, #3, #5–7, #9–16):** Company-scoped. No change needed.

   **Conclusion:** Option A handles the only near-term non-company agent (Industry #4) and the pattern generalizes to the one additional case (Macro #8) without over-engineering for speculative future needs.

4. **`target_type` is the discriminator, `run_type` is the execution mode.** These are orthogonal dimensions:
   ```python
   # Standalone industry research — full analysis:
   ResearchRun(
       target_type="industry",
       company_id=None,
       industry_id=industry_classification_uuid,
       run_type="FULL",           # execution mode — unchanged semantics
       initiated_by="...",
   )

   # Incremental industry research update:
   ResearchRun(
       target_type="industry",
       company_id=None,
       industry_id=industry_classification_uuid,
       run_type="INCREMENTAL",    # execution mode — unchanged semantics
       initiated_by="...",
   )
   ```

5. **`parent_run_id` is used for orchestration.** When industry research is triggered from a multi-agent company workflow:
   ```python
   ResearchRun(
       target_type="industry",
       company_id=None,
       industry_id=industry_uuid,
       run_type="FULL",
       parent_run_id=parent_company_run_uuid,
       trigger_type="workflow",
   )
   ```
   This enables tracing industry runs back to the company workflow that triggered them, without polluting `company_id`.

6. **XOR constraint enforces mutual exclusivity.** The check constraint ties `target_type` to FK state, preventing inconsistency:
   ```sql
   CHECK (
       (target_type = 'company' AND company_id IS NOT NULL AND industry_id IS NULL)
       OR (target_type = 'industry' AND company_id IS NULL AND industry_id IS NOT NULL)
   )
   ```
   A run cannot have both `company_id` and `industry_id` set. A run cannot have neither set. The `target_type` value must match which FK is populated.

### Why Not Option C

Option C was seriously considered because it requires zero schema migration. However:
1. `run_type` already has defined semantics (execution mode: FULL, INCREMENTAL, etc.) — repurposing it as a target discriminator conflates two orthogonal concepts.
2. The "context company" hack for standalone industry runs is semantically incorrect and would create tech debt.
3. The migration cost of Option A is small (one new column, one nullable change, one constraint) and pays for itself by enabling clean standalone industry runs and a generalizable pattern.

### ResearchRunService Impact

The `ResearchRunService` methods that reference `company_id` will need adjustment:

- `initiate_run()`: Accept optional `industry_id` and `target_type` parameters. When `industry_id` is set and `company_id` is None, `target_type` must be `"industry"`. Application-level validation enforces the XOR invariant before reaching the database.
- `get_active_run()`: Currently filters by `company_id`. Remains unchanged for company runs.
- `get_active_industry_run(industry_id, observation_date)`: **New method.** Prevents concurrent runs for the same (industry_id, observation_date) pair (see §35 for the concurrency/reuse separation).
- `update_run_company()`: Remains unchanged (used by Phase 8).

### ResearchRunRepository Impact

- `get_by_company()`: Unchanged. Filters by `company_id` which is still indexed.
- `get_by_industry(industry_id)`: **New method.** Returns runs where `industry_id` matches.
- `get_active_run(company_id)`: Unchanged.
- `get_active_industry_run(industry_id, observation_date)`: **New method.** Filters by `industry_id`, `observation_date`, and active statuses.

### ResearchRunStep and AgentExecution

No changes needed. These records reference `ResearchRun.id`, not `company_id` directly.

### ResearchRunCreate Schema Impact

The API schema `ResearchRunCreate` currently has `company_id: uuid.UUID` as required and `run_type: str` as required. For industry research runs, the schema must support the target_type discriminator:

```python
class ResearchRunCreate(BaseModel):
    company_id: uuid.UUID | None = None
    industry_id: uuid.UUID | None = None
    target_type: str = "company"       # "company" or "industry"
    run_type: str = Field(max_length=50)  # execution mode: FULL, INCREMENTAL, etc. — unchanged
    # ... other fields unchanged

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.target_type == "company":
            if self.company_id is None:
                raise ValueError("company_id required when target_type='company'")
            if self.industry_id is not None:
                raise ValueError("industry_id must be None when target_type='company'")
        elif self.target_type == "industry":
            if self.industry_id is None:
                raise ValueError("industry_id required when target_type='industry'")
            if self.company_id is not None:
                raise ValueError("company_id must be None when target_type='industry'")
        else:
            raise ValueError(f"Unknown target_type: {self.target_type}")
        return self
```

**Note:** `run_type` retains its existing semantics (execution mode). Phase 8 callers continue to pass `run_type="company_research"` or `run_type="FULL"`. The `target_type` field defaults to `"company"` for backward compatibility — Phase 8 callers do not need to set it explicitly.

### Impact on Existing ResearchFindingRepository.get_current_for_company()

This method (lines 356-374 of `research_run.py`) joins `ResearchFinding → ResearchRun` and filters by `ResearchRun.company_id`. It will continue to work correctly because industry runs have `company_id = NULL` and are automatically excluded from company-scoped queries. A parallel method `get_current_for_industry(industry_id)` is needed for industry-scoped queries.

---

## 21. Research Workflow

### Seven-Step Sequential Workflow

The Industry Research Agent follows the same seven-step sequential structure as Phase 8:

```
ResearchRun created (Phase 7 infrastructure)
    │
    ▼
Step 1: INDUSTRY_VALIDATION [deterministic]
    │  Input:  industry_id (Classification UUID)
    │  Action: query Classification table, verify level=INDUSTRY, resolve parent sector
    │  Output: resolved industry and sector records
    │
    ▼
Step 2: INDUSTRY_SOURCE_DISCOVERY [provider/tool call]
    │  Input:  industry_name, sector_name, observation_date
    │  Action: query SearchProvider, NewsProvider, MacroDataProvider
    │  Filter: publication_date <= observation_date
    │  Output: ranked candidate source list
    │
    ▼
Step 3: DOCUMENT_RETRIEVAL [provider/tool call]
    │  Input:  candidate source list
    │  Action: retrieve documents, compute content_hash, deduplicate
    │  Output: ResearchDocument (company_id=NULL) + DocumentVersion records
    │
    ▼
Step 4: EVIDENCE_EXTRACTION [LLM reasoning]
    │  Input:  document content (sanitized, inside <retrieved_document> tags)
    │  Action: LLM extracts industry-specific evidence with classification
    │  Output: Evidence records linked to ResearchDocuments
    │
    ▼
Step 5: INDUSTRY_ANALYSIS_AND_FINDING_GENERATION [LLM reasoning]
    │  Input:  extracted evidence, industry profile, industry company list
    │  Action: LLM synthesizes evidence into Five Forces, TAM/SAM, growth,
    │          regulatory, cyclicality, India position findings
    │  Output: ResearchFinding records with evidence linkages
    │
    ▼
Step 6: FINDING_VALIDATION [deterministic]
    │  Input:  generated findings
    │  Action: verify evidence linkage, FindingType, temporal constraints,
    │          category membership in INDUSTRY_FINDING_CATEGORIES
    │  Output: validation result, rejected findings list
    │
    ▼
Step 7: GAP_AND_CONTRADICTION_ANALYSIS [LLM reasoning + deterministic]
    │  Input:  validated findings
    │  Action: identify contradictions (LLM), identify gaps against
    │          EXPECTED_INDUSTRY_DIMENSIONS (deterministic)
    │  Output: contradiction findings, gap findings
    │
    ▼
ResearchRun completed (Phase 7 infrastructure)
```

### Step Classification

| Step | Type | Uses LLM | Uses Provider | Writes to DB |
|---|---|---|---|---|
| 1. Industry Validation | Deterministic | No | No | Step status only |
| 2. Industry Source Discovery | Provider/tool call | No | Yes | Artifact (candidate list) |
| 3. Document Retrieval | Provider/tool call (bounded concurrency) | No | Yes | ResearchDocument, DocumentVersion, ResearchRunSource |
| 4. Evidence Extraction | LLM reasoning | Yes | No | Evidence |
| 5. Industry Analysis | LLM reasoning | Yes | No | ResearchFinding, research_finding_evidence |
| 6. Finding Validation | Deterministic | No | No | Artifact (validation report) |
| 7. Gap & Contradiction | LLM + deterministic | Yes (optional) | No | ResearchFinding (UNCERTAINTY, AI_INFERENCE) |

### Step Definitions

```python
INDUSTRY_RESEARCH_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_order=1,
        step_name="industry_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=5,
    ),
    StepDefinition(
        step_order=2,
        step_name="industry_source_discovery",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=30,
    ),
    StepDefinition(
        step_order=3,
        step_name="document_retrieval",
        step_type=STEP_TYPE_PROVIDER_CALL,
        timeout_seconds=60,
    ),
    StepDefinition(
        step_order=4,
        step_name="evidence_extraction",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=5,
        step_name="industry_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=120,
        uses_llm=True,
    ),
    StepDefinition(
        step_order=6,
        step_name="finding_validation",
        step_type=STEP_TYPE_DETERMINISTIC,
        timeout_seconds=10,
    ),
    StepDefinition(
        step_order=7,
        step_name="gap_contradiction_analysis",
        step_type=STEP_TYPE_LLM_REASONING,
        timeout_seconds=60,
        uses_llm=True,
    ),
)
```

---

## 22. LLM Boundary

### What the LLM Does

The LLM performs three tasks (matching Phase 8's LLM boundary):

1. **Evidence extraction** (Step 4): Extract structured claims from industry documents. Input: sanitized document text in `<retrieved_document>` tags. Output: `EvidenceExtractionOutput` schema.
2. **Finding generation** (Step 5): Synthesize extracted evidence into structured industry research findings organized by Porter's Five Forces, TAM/SAM, growth drivers, etc. Input: evidence records + industry profile + company list. Output: `FindingGenerationOutput` schema.
3. **Contradiction identification** (Step 7): Identify contradictory findings across sources. Input: validated findings. Output: contradiction findings.

### What the LLM Does NOT Do

- **Financial calculations**: No CAGR, no ratio computation, no market size arithmetic.
- **Data fabrication**: If industry data is unavailable, the LLM reports UNCERTAINTY.
- **Source retrieval**: The LLM does not access the web or any provider. It operates on pre-retrieved, sanitized document content.
- **Finding validation**: Deterministic code validates evidence linkage, temporal constraints, and category membership.
- **Gap identification**: Deterministic code checks whether all expected research dimensions have findings.

### Model Tier Selection

Per ADR-008 model optimization:

| Step | Model Tier | Rationale |
|---|---|---|
| Evidence extraction | Fast/cheap (Haiku-tier) | Structured extraction from documents |
| Industry analysis / finding generation | Capable (Sonnet/Opus-tier) | Nuanced reasoning about industry structure |
| Contradiction identification | Fast/cheap (Haiku-tier) | Pattern matching across findings |

Model assignment is configured per-step, matching Phase 8's approach via `IndustryResearchConfig.extraction_model`, `generation_model`, and `analysis_model`.

### Prompt Architecture

Prompt templates are industry-specific and separate from Phase 8 prompts. They are stored in `backend/app/agents/industry_research/prompts.py`:

- `evidence_extraction_prompt()`: Adapted from Phase 8 but with industry-specific extraction categories (market size data, regulatory data, competitive structure data).
- `industry_analysis_prompt()`: New prompt specifically designed for Five Forces analysis, TAM/SAM estimation, and industry structure synthesis.
- `gap_contradiction_prompt()`: Adapted from Phase 8 but checking against `EXPECTED_INDUSTRY_DIMENSIONS`.

All prompts follow Phase 8's security rules:
- Document content enclosed in `<retrieved_document>` XML tags.
- System prompt explicitly states content is data, not instructions.
- Structured output schema enforced.

---

## 23. Token Budget

### Reconciliation Note

This section reconciles the token budget against `architecture/agent-architecture.md` and Phase 8's implementation. The 20,000 budget is confirmed correct.

### Budget Allocation

Per `architecture/agent-architecture.md`, the Industry Analysis Agent has a budget of **20,000 tokens**:

```python
INDUSTRY_AGENT_TOKEN_BUDGET: int = 20_000
INDUSTRY_AGENT_TOKEN_WARNING: int = 16_000
INDUSTRY_AGENT_NAME: str = "industry_research_agent"
MAX_LLM_ATTEMPTS: int = 2
```

### Why 20,000, Not 30,000

Phase 8's Company Research Agent uses 30,000 tokens (`AGENT_TOKEN_BUDGET = 30_000` in `app.agents.contracts`). However, Phase 8 corresponds to the **Financial Analysis Agent (#2)** in the agent-architecture budget table (30,000), not the Business Model Agent (#3) (20,000). The architecture document explicitly assigns 20,000 to the Industry Analysis Agent (#4).

The difference is justified:
- **Phase 8 processes company filings (annual reports, investor presentations)** — these are long, dense documents requiring more extraction tokens.
- **Phase 9 processes industry reports and news** — typically shorter per-document, with more documents but less per-document extraction cost.
- **The aggregate run budget is ~325,000 tokens across 17 agents.** Each agent's budget is sized relative to its analytical complexity. Industry analysis (structured framework application) is less token-intensive than financial analysis (comprehensive quantitative analysis across 5-10 years of statements).

### Budget vs Aggregate Run Budget

| Concept | Value | Enforced By |
|---|---|---|
| Industry Agent token budget | 20,000 | `TokenBudget` class (agent-level) |
| Aggregate run budget | ~325,000 | `ResearchRun.total_input_tokens + total_output_tokens` (run-level) |
| Per-run cost tracking | `ResearchRun.total_cost_usd` | `ResearchRunService.update_aggregates()` |

The agent-level budget is enforced within the agent. The aggregate run budget is a monitoring concern, not an enforcement mechanism within Phase 9. The `ResearchRunService.update_aggregates()` method records the agent's token usage against the run's totals after execution.

### Budget Distribution Across Steps

| Step | Estimated Input Tokens | Estimated Output Tokens | Notes |
|---|---|---|---|
| 4. Evidence extraction | 6,000–10,000 | 1,000–3,000 | Depends on number and size of retrieved documents |
| 5. Industry analysis | 4,000–6,000 | 2,000–4,000 | Evidence synthesis is the most token-intensive reasoning step |
| 7. Contradiction analysis | 1,000–2,000 | 500–1,500 | Optional; skipped if budget is exhausted |
| **Total LLM usage** | **11,000–18,000** | **3,500–8,500** | |

**Risk:** The upper bound of total estimated usage (18,000 + 8,500 = 26,500) exceeds the 20,000 budget. This is intentional — the estimates assume worst-case document count. In practice, the model tier optimization (Haiku for extraction, Sonnet for analysis) and document count limits keep usage within budget. If ≥30% of runs hit the budget ceiling, the budget should be increased to 25,000 (see §39 Risks).

### Budget Enforcement

The `TokenBudget` class from `app.agents.contracts` is reused without modification:

```python
class TokenBudget(BaseModel):
    model_config = ConfigDict(frozen=False)
    budget: int = Field(default=INDUSTRY_AGENT_TOKEN_BUDGET, gt=0)
    warning_threshold: int = Field(default=INDUSTRY_AGENT_TOKEN_WARNING, gt=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
```

When the budget is exhausted (`is_exhausted` returns True), the agent:
1. Completes the current step with partial output.
2. Skips remaining LLM steps.
3. Runs finding validation (Step 6, deterministic — no token cost).
4. Runs gap analysis with deterministic gap detection only (no LLM contradiction analysis).
5. Marks the run as PARTIAL, not FAILED.

### TokenBudget Reuse Classification

The `TokenBudget` class is **Category A: Direct Reuse** from Phase 8. The only change is the default budget value (20,000 vs 30,000), which is passed through `IndustryResearchConfig.token_budget` and injected via the constructor, not by modifying the `TokenBudget` class itself.

---

## 24. Security Model

### Reused from Phase 8 Without Modification

All 10 threat vectors identified in Phase 8 §20 apply to the Industry Research Agent:

1. **Prompt injection via retrieved documents**: Industry documents (government reports, news articles) are untrusted. Content placed inside `<retrieved_document>` tags. System prompt declares content is data, not instructions.
2. **LLM output schema violation**: Output validated against Pydantic schemas before persistence.
3. **Tool allowlisting**: The agent has access to exactly 8 tools. No tool outside this set can be invoked.
4. **Write scope restriction**: The agent writes only to Evidence, ResearchFinding, ResearchRunStep, AgentExecution, ResearchRunSource, and ResearchArtifact records within its own ResearchRun scope.
5. **Token budget enforcement**: Prevents unbounded LLM consumption.
6. **Provider rate limiting**: All provider calls go through the rate limiter infrastructure.
7. **Timeout enforcement**: Per-step timeouts prevent runaway operations.
8. **Content sanitization**: Retrieved documents are text-extracted and stripped of executable content.
9. **No secret exposure**: The agent has no access to API keys, credentials, or environment variables.
10. **Audit trail**: Every action is logged through ResearchRunStep and AgentExecution records.

### Industry-Specific Security Considerations

- **SearchProvider results**: Web search results are inherently less controlled than company filings. The agent applies the same `<retrieved_document>` tagging and schema validation to search results.
- **MacroDataProvider**: Returns structured data (time series), not free-form text. Lower prompt injection risk.
- **Source diversity**: Industry research accesses more sources from more providers than company research. Each source interaction is logged as a ResearchRunSource entry.

---

## 25. Data Model Impact

### Reconciliation Note — Migration Gate

This section was updated during reconciliation to reflect the Option A decision from §20 and to provide explicit migration specifications with backward compatibility analysis.

### Required Schema Changes

The following schema changes are required for Phase 9 implementation. They are documented here for architecture completeness. **No migrations are created in this architecture phase.** The migration is the first task in the implementation sequence (§38, Task 1).

#### Change 1: ResearchRun Target Semantics — target_type + Nullable company_id + industry_id FK

**Migration: Phase 9a — Must be the first implementation task.**

**Second reconciliation note:** The first reconciliation proposed using `run_type` as a denormalized discriminator and backfilling `run_type = 'company'` for existing rows. This is incorrect — `run_type` already has defined semantics (execution mode: FULL, INCREMENTAL, THESIS_UPDATE, MONITORING, company_research). A new `target_type` field is introduced instead. No `run_type` values are modified.

```sql
-- Step 1: Add target_type discriminator
-- server_default='company' auto-backfills all existing rows
ALTER TABLE research.research_run
    ADD COLUMN target_type VARCHAR(50) NOT NULL DEFAULT 'company';

-- Step 2: Make company_id nullable
ALTER TABLE research.research_run
    ALTER COLUMN company_id DROP NOT NULL;

-- Step 3: Add industry_id FK
ALTER TABLE research.research_run
    ADD COLUMN industry_id UUID
    REFERENCES company.classification(id);

-- Step 4: Add XOR check constraint (mutual exclusivity)
-- Ensures exactly one target FK is set, consistent with target_type
ALTER TABLE research.research_run
    ADD CONSTRAINT chk_research_run_target
    CHECK (
        (target_type = 'company' AND company_id IS NOT NULL AND industry_id IS NULL)
        OR (target_type = 'industry' AND company_id IS NULL AND industry_id IS NOT NULL)
    );

-- Step 5: Add partial index for industry runs
CREATE INDEX ix_research_run_industry
    ON research.research_run (industry_id, started_at DESC)
    WHERE industry_id IS NOT NULL;

-- Step 6: Add index for target_type filtering
CREATE INDEX ix_research_run_target_type
    ON research.research_run (target_type, started_at DESC);
```

**Why no run_type backfill:** Existing `run_type` values ("FULL", "INCREMENTAL", "company_research", NULL) are execution-mode values — they must NOT be overwritten with "company". The `target_type` column (Step 1) provides the target discriminator. PostgreSQL's `NOT NULL DEFAULT 'company'` on `ADD COLUMN` automatically sets `target_type = 'company'` for all existing rows in a single pass — no separate UPDATE statement is needed.

**Backward compatibility analysis:**

| Existing Component | Impact | Action Required |
|---|---|---|
| `ResearchRun` model (ORM) | `company_id` type changes from `Mapped[uuid.UUID]` to `Mapped[uuid.UUID \| None]` | Update type annotation, add `industry_id` and `target_type` mapped columns |
| `ix_research_run_company_started` index | Continues to work — indexes non-null company_id values | None |
| `ix_research_run_observation` index | Continues to work — indexes non-null company_id values | None |
| `ResearchRunRepository.get_by_company()` | Filters by `company_id` — unchanged, works correctly because industry runs have `company_id = NULL` and are excluded | None |
| `ResearchRunRepository.get_active_run(company_id)` | Same — filters by `company_id`, excludes industry runs | None |
| `ResearchRunRepository.update_company_id()` | Used by Phase 8 only — unchanged | None |
| `ResearchFindingRepository.get_current_for_company()` | Joins through `ResearchRun.company_id` — industry runs excluded automatically | None |
| `ResearchRunCreate` API schema | Currently requires `company_id` — must be updated to accept `target_type` + either `company_id` or `industry_id` | Update schema with `@model_validator` |
| `run_type` values on existing records | Retain their execution-mode values (FULL, INCREMENTAL, company_research, NULL) | **No modification** |
| All existing ResearchRun records | Have non-null `company_id` — constraint satisfied. `target_type` auto-set to `'company'` by server_default. | None |

**Downgrade path:**

```sql
-- Downgrade: remove industry support
DROP INDEX IF EXISTS research.ix_research_run_target_type;
DROP INDEX IF EXISTS research.ix_research_run_industry;
ALTER TABLE research.research_run DROP CONSTRAINT IF EXISTS chk_research_run_target;
DELETE FROM research.research_run WHERE company_id IS NULL;  -- remove industry-only runs
ALTER TABLE research.research_run ALTER COLUMN company_id SET NOT NULL;
ALTER TABLE research.research_run DROP COLUMN IF EXISTS industry_id;
ALTER TABLE research.research_run DROP COLUMN IF EXISTS target_type;
-- Note: run_type values are untouched — no reversal needed
```

#### Change 2: IndustryData.research_run_id FK (Optional — Deferred)

The existing `IndustryData` model (`backend/app/models/analysis.py`) stores per-industry metrics:

```python
class IndustryData(Base, TimestampMixin):
    industry_id: FK → Classification
    metric_name: str
    value: Decimal
    as_of_date: date
    source_evidence_id: FK → Evidence
```

Adding an optional `research_run_id` FK enables tracing which research run produced or updated an IndustryData record. However, IndustryData already has `source_evidence_id` for provenance. **This change is deferred** — it adds operational traceability but is not required for Phase 9 functional completeness. The agent writes findings to `ResearchFinding`; IndustryData population is an open question (§35, OQ-4) that can be resolved during or after Phase 9 implementation.

### No Other Schema Changes

- No new tables required.
- No enum changes required (`DocumentType`, `SourceType`, `FindingType`, `SourceTier`, `EvidenceType` all have the values needed — verified against `backend/app/models/enums.py`).
- No changes to Evidence, ResearchDocument, ResearchFinding, or any other existing model.
- `ResearchDocument.company_id` is already nullable — verified at `backend/app/models/research.py` line 60-63.

---

## 26. API and UI Boundary

### API Endpoints

The Industry Research Agent is exposed through the existing research run API pattern:

| Endpoint | Method | Description |
|---|---|---|
| `POST /api/v1/research/industry` | POST | Initiate an industry research run |
| `GET /api/v1/research/runs/{run_id}` | GET | Get research run status (existing endpoint; works for industry runs) |
| `GET /api/v1/research/runs/{run_id}/findings` | GET | Get findings for a run (existing endpoint) |
| `GET /api/v1/research/industry/{industry_id}/latest` | GET | Get latest industry research findings |

The `POST /api/v1/research/industry` endpoint accepts `IndustryResearchRequest` and returns a `ResearchRun` record. The existing run status, findings, and artifacts endpoints work without modification because they reference `run_id`, not `company_id`.

### UI Considerations (Out of Scope)

The frontend is not modified in Phase 9. However, the architecture anticipates:
- An "Industry Analysis" tab/section in the company research view, populated from industry-level findings.
- An industry research dashboard showing research coverage by industry.
- Finding type badges and source tier indicators (reused from Phase 8 UI patterns).

---

## 27. Observability

### Reused from Phase 8 and Phase 7

The same observability infrastructure applies:

1. **Structured JSON logging**: Every step logs start, completion, and error events with structured fields (run_id, step_name, agent_name, duration_ms).
2. **OpenTelemetry spans**: One span per research run, child spans per step, child spans per tool call and LLM invocation.
3. **Token tracking**: LLM token usage recorded per AgentExecution and aggregated on the ResearchRun.
4. **Cost tracking**: `ResearchRun.total_cost_usd` and per-agent breakdown.
5. **ResearchRunStep records**: Step-level status transitions with timing.
6. **AgentExecution records**: Full execution metadata (model, prompt version, attempt number).
7. **ResearchRunSource records**: Every document access logged.

### Industry-Specific Metrics

| Metric | Type | Description |
|---|---|---|
| `industry_research.sources_discovered` | Counter | Number of source candidates found per run |
| `industry_research.findings_generated` | Counter | Number of findings produced per category |
| `industry_research.research_gaps` | Counter | Number of gap findings per run |
| `industry_research.contradictions` | Counter | Number of contradiction findings per run |
| `industry_research.five_forces_coverage` | Gauge | How many of the 5 forces have at least one finding |
| `industry_research.token_utilization_pct` | Gauge | Percentage of token budget consumed |

---

## 28. Evaluation Strategy

### Evidence Quality Evaluation

| Criterion | Measurement | Target |
|---|---|---|
| Source tier coverage | Percentage of findings backed by Tier 1/2 vs Tier 3 evidence | ≥ 50% Tier 1+2 |
| Evidence linkage rate | Percentage of FACT findings with evidence | 100% (enforced by validation) |
| Temporal correctness | Findings passing temporal validation | 100% (enforced by validation) |

### Analytical Quality Evaluation

| Criterion | Measurement | Target |
|---|---|---|
| Five Forces coverage | All 5 forces have at least 1 finding per industry | ≥ 4 of 5 forces |
| TAM/SAM estimation | Market size finding present | For ≥ 80% of industries |
| Research gap ratio | Gap findings / total expected dimensions | ≤ 25% (≤ 3 of 12 dimensions missing) |
| Finding classification accuracy | Manual review of FindingType assignments | ≥ 90% correct |

### Golden Dataset

3-5 reference industries with hand-verified data for regression testing:

| Industry | Sector | Characteristics |
|---|---|---|
| IT Services | Information Technology | Well-documented, large, global competition |
| Two-Wheelers | Automobiles | Domestic-focused, clear market leaders |
| Private Banks | Financial Services | Heavily regulated, excellent data availability |
| Specialty Chemicals | Chemicals | Growing, China+1 tailwind |
| Cement | Construction Materials | Cyclical, regional dynamics |

---

## 29. Testing Strategy

### Test Structure

Following Phase 8's test organization:

```
backend/
  app/
    agents/
      industry_research/
        __init__.py
        agent.py
        prompts.py
        tools.py
        exceptions.py
  tests/
    agents/
      test_industry_research_agent.py
      test_industry_research_tools.py
      test_industry_research_prompts.py
```

### Test Categories

| Category | Count (Est.) | Focus |
|---|---|---|
| Unit tests — tool I/O | 20–30 | Each tool validates input/output schemas |
| Unit tests — step execution | 25–35 | Each of 7 steps tested with mock providers |
| Unit tests — finding validation | 15–20 | Category validation, evidence linkage, temporal checks |
| Unit tests — token budget | 5–8 | Budget enforcement, warning threshold, exhaustion behavior |
| Unit tests — error handling | 10–15 | Provider failures, LLM failures, retry semantics |
| Integration tests — full run | 5–8 | End-to-end with mock providers |
| Golden dataset tests | 3–5 | Reference industries with hand-verified findings |
| **Total** | **83–121** | |

### Test Principles (Reused from Phase 8)

- No network calls in unit tests — all providers mocked.
- Financial values use Decimal assertions.
- Agent tests verify structure, not prose.
- Flaky tests are bugs.
- Never remove or weaken tests to make implementation pass.

---

## 30. Phase 8 Reuse Matrix

### Reconciliation Note

This section was restructured during reconciliation to classify every reused component into one of three categories:
- **Category A: Reuse Directly** — import and use as-is, or with configuration-only changes (e.g., different default values).
- **Category B: Duplicate Intentionally** — copy the pattern/structure, implement with industry-specific logic. Code is structurally similar but semantically different enough that sharing would create coupling.
- **Category C: Candidate for Shared Extraction** — currently lives in Phase 8 module but is generic enough to extract to `app.agents.shared` or `app.agents.base`. Extraction is optional for Phase 9 but recommended before Phase 10.

### Category A: Reuse Directly

| Component | Location | Notes |
|---|---|---|
| `TokenBudget` | `app.agents.contracts` | Reuse class; inject different default via `IndustryResearchConfig.token_budget` |
| `StepDefinition` | `app.agents.contracts` | Reuse class; define new step instances |
| `FindingItem` | `app.agents.contracts` | Reuse class; pass `agent_name=INDUSTRY_AGENT_NAME` |
| `PersistEvidenceInput/Output` | `app.agents.contracts` | Identical contract |
| `PersistFindingsInput/Output` | `app.agents.contracts` | Identical contract |
| `RetrieveDocumentInput/Output` | `app.agents.contracts` | Identical contract; Tool 3 is Phase 8's retrieve_document |
| `SourceCandidate` | `app.agents.contracts` | Identical contract for normalized source representation |
| `EvidenceExtractionOutput` | `app.agents.contracts` | LLM output schema is generic enough for industry evidence |
| `FindingGenerationOutput` | `app.agents.contracts` | LLM output schema is generic |
| `FindingValidationIssue` | `app.agents.contracts` | Identical contract |
| `FindingValidationResult` | `app.agents.contracts` | Identical contract |
| `ExtractedEvidence` | `app.agents.contracts` | Identical contract |
| `GeneratedFinding` | `app.agents.contracts` | Identical contract |
| Step type constants | `app.agents.contracts` | `STEP_TYPE_DETERMINISTIC`, `STEP_TYPE_PROVIDER_CALL`, `STEP_TYPE_LLM_REASONING` |
| `ResearchRunService` | `app.services.research_run` | Add `industry_id` parameter to `create_research_run()` and new `get_active_industry_run()` method. Existing methods unchanged. |
| `EvidenceService` | `app.services.evidence` | Unchanged — already supports `company_id=None` on ResearchDocument |
| `ResearchRunRepository` | `app.repositories.research_run` | Add `get_by_industry()` and `get_active_industry_run()`. Existing methods unchanged. |
| Temporal validation logic | `ResearchRunService._validate_temporal_consistency()` | Unchanged — operates on dates, not entity types |
| Error hierarchy | `app.agents.company_research.exceptions` | `StepFailedError`, `LLMParsingError`, `TokenBudgetExhaustedError` are agent-generic |

### Category B: Duplicate Intentionally

| Component | Phase 8 Source | Phase 9 Counterpart | Why Duplicate |
|---|---|---|---|
| `CompanyResearchRequest` | `app.agents.contracts` | `IndustryResearchRequest` | Different entry point (`industry_id` vs `company_identifier`) |
| `CompanyResearchConfig` | `app.agents.contracts` | `IndustryResearchConfig` | Different defaults (`source_limit=30` vs `20`, `token_budget=20000` vs `30000`) |
| `ValidateCompanyInput/Output` | `app.agents.contracts` | `ValidateIndustryInput/Output` | Different validation target (Company vs Classification) |
| `DiscoverSourcesInput/Output` | `app.agents.contracts` | `DiscoverIndustrySourcesInput/Output` | Different discovery strategy (filings vs search+news) |
| `FINDING_CATEGORIES` | `app.agents.contracts` | `INDUSTRY_FINDING_CATEGORIES` | Entirely different category set |
| `COMPANY_RESEARCH_STEPS` | `app.agents.contracts` | `INDUSTRY_RESEARCH_STEPS` | Different step names and timeout values |
| Evidence extraction prompt | `company_research/prompts.py` | `industry_research/prompts.py` | Industry-specific extraction categories |
| Finding generation prompt | `company_research/prompts.py` | `industry_research/prompts.py` | Five Forces framework, industry dimensions |
| Gap/contradiction prompt | `company_research/prompts.py` | `industry_research/prompts.py` | Different expected dimensions |
| `IndustryResearchAgent` | `CompanyResearchAgent` pattern | `IndustryResearchAgent` | Same 7-step pattern, different step implementations |

### Category C: Candidate for Shared Extraction

| Component | Current Location | Shared Usage | Extraction Priority |
|---|---|---|---|
| Step runner pattern (`_run_step_deterministic`, `_run_step_llm`, `_run_step_provider`) | `CompanyResearchAgent` | Both agents (and agents #5-17) use identical step execution, error handling, and status transition logic | **High** — prevents duplication in every future agent |
| LLM structured output caller (`_call_llm_structured`) | `CompanyResearchAgent` | Both agents parse structured LLM output identically (prompt → LLM → Pydantic validation → retry) | **High** — same pattern in every LLM-using agent |
| Token budget enforcement logic (check before LLM call, record after, skip-on-exhaustion) | `CompanyResearchAgent` | Same budget tracking in every agent | **Medium** — simpler to extract |
| Finding validation logic (evidence linkage check, temporal check, category membership check) | `CompanyResearchAgent` | Steps 6 structure is identical, only the category set differs | **Medium** |

**Decision:** Extraction to `app.agents.base` is **recommended but not required** for Phase 9. If extraction is deferred, code duplication between Phase 8 and Phase 9 agent modules is acceptable for the initial implementation, with extraction done before Phase 10 to prevent triplication.

### Components Requiring New Implementation

| Component | Reason |
|---|---|
| `IndustryResearchRequest` / `IndustryResearchConfig` | New request contract (Category B) |
| `ValidateIndustryInput/Output` | Different validation target |
| `DiscoverIndustrySourcesInput/Output` | Different source discovery strategy |
| `SearchIndustryDataInput/Output` | New tool wrapping SearchProvider |
| `GetMacroIndicatorsInput/Output` | New tool wrapping MacroDataProvider |
| `GetIndustryCompaniesInput/Output` | New tool for company enumeration |
| `IndustryResearchTools` | New tool implementation class |
| `INDUSTRY_FINDING_CATEGORIES` | New category set (14 categories) |
| `INDUSTRY_RESEARCH_STEPS` | New step definitions |
| Industry-specific prompt templates | New prompts for industry analysis |
| `IndustryResearchAgent` | New agent class (following Phase 8 pattern) |
| Schema migration | ResearchRun.company_id nullable + industry_id FK |
| Repository extensions | `get_by_industry()`, `get_active_industry_run()` |

---

## 31. Shared Component Analysis

### Components That Should Be Extracted to a Shared Module

During Phase 9 implementation, the following components currently in `app.agents.company_research.*` should be evaluated for extraction to a shared `app.agents.shared` or `app.agents.base` module:

| Component | Current Location | Shared Usage |
|---|---|---|
| Step runner pattern (`_run_step_deterministic`, `_run_step_llm`) | `agent.py` | Both agents use the same step execution pattern |
| LLM structured output caller | `agent.py` | Both agents parse structured LLM output identically |
| Token budget enforcement logic | `agent.py` | Same budget tracking in every agent |
| Error classes (`StepFailedError`, `LLMParsingError`, `TokenBudgetExhaustedError`) | `exceptions.py` | Applicable to any agent |

**Decision:** Extraction is a Phase 9 implementation decision. The architecture document records the opportunity but does not mandate it. If extraction is deferred, code duplication between Phase 8 and Phase 9 agent modules is acceptable for the initial implementation.

---

## 32. Multi-Agent Compatibility

### LangGraph Integration Point

Per ADR-001, the full 17-agent workflow will be orchestrated by LangGraph. Phase 9 (like Phase 8) is implemented as plain async Python, designed to be wrapped as a LangGraph node without modification.

The Industry Research Agent's contract with LangGraph:

```python
# LangGraph node signature (future)
async def industry_analysis_node(state: ResearchState) -> ResearchState:
    agent = IndustryResearchAgent(...)
    request = IndustryResearchRequest(
        industry_id=state["company"].industry_id,
        observation_date=state["observation_date"],
        initiated_by="langgraph_workflow",
        company_context_id=state["company"].id,
    )
    result = await agent.execute(request)
    state["industry_analysis"] = result
    return state
```

### Parallel Execution Compatibility

The Industry Research Agent runs in parallel with:
- Business Model Agent (#3 / Phase 8 Company Research Agent)
- Competitor Analysis Agent (#9)

Parallel execution is safe because:
- Each agent writes to separate `ResearchFinding` records with distinct `agent_name` values.
- Each agent creates its own `AgentExecution` records.
- The Industry Research Agent does not read or modify Company Research Agent findings.
- Database writes use separate transactions within their respective research runs.

### Downstream Consumer Compatibility

The following agents consume Phase 9 findings:
- **Competitive Moat Agent (#5)**: Uses industry structure and entry barriers findings to assess moat strength.
- **Valuation Agent (#10)**: Uses industry growth rate and TAM/SAM for comparable analysis.
- **Risk Agent (#11)**: Uses industry-level risks.
- **Research Synthesis Agent (#16)**: Incorporates industry analysis into the final research report.

These agents access Phase 9 findings through `ResearchFindingRepository.get_by_run()` filtered by `agent_name = "industry_research_agent"`.

### ResearchState Integration

The `ResearchState` TypedDict (from `architecture/agent-architecture.md`) includes `industry_analysis: IndustryAnalysis | None`. Phase 9 writes its findings to the ResearchRun infrastructure and populates this state field for LangGraph consumption.

---

## 33. Reproducibility

### Reused from Phase 8 (§19)

Given the same industry, observation date, source documents, and model configuration, the agent should produce equivalent findings. Reproducibility is ensured by:

1. **Input capture**: `AgentExecution` records store the model name, model version, prompt version hash, configuration, and the list of source documents used.
2. **Deterministic steps**: Steps 1, 3, and 6 produce identical output for identical input.
3. **LLM steps**: Steps 4, 5, and 7 are bounded by temperature=0.0 (default). However, LLM output is non-deterministic even at temperature=0 due to batching effects. The reproducibility contract is "equivalent findings" (same categories, similar content), not "identical strings."
4. **Source pinning**: The list of source documents accessed is recorded as `ResearchRunSource` entries. Replaying with the same sources should produce equivalent findings.

### Industry-Specific Reproducibility Considerations

Industry research uses `SearchProvider`, which returns results based on external search engine state. Search results for the same query may change over time. The agent records:
- The search queries used (in AgentExecution metadata).
- The source documents discovered and retrieved (as ResearchRunSource entries).
- The content hashes of all retrieved documents (in ResearchDocument).

Full reproducibility requires re-running with the same source documents (pinned by document IDs), not re-running the search queries.

---

## 34. Failure, Retry, and Resume

### Reused from Phase 8 and ADR-007

| Failure Class | Handling |
|---|---|
| Provider unavailability (SearchProvider, MacroDataProvider, NewsProvider) | Retry 3x with exponential backoff (via ProviderBase). If all retries fail, step FAILED, continue with remaining steps. |
| LLM unavailability | Primary/fallback provider (ADR-007). If both fail after retries, LLM step FAILED. |
| LLM malformed output | Retry 1x (MAX_LLM_ATTEMPTS=2). If still malformed, step FAILED with partial results. |
| Token budget exhaustion | Complete current step with partial output. Skip remaining LLM steps. Run deterministic steps. Mark run PARTIAL. |
| Individual document retrieval failure | Log error, continue with remaining documents. If all documents fail, step FAILED. |
| Classification not found | Run FAILED with descriptive error_summary. |
| Database failure | Connection pool handles transient failures. Persistent failure → step FAILED, partial state preserved. |

### Resume Semantics

An industry research run can be resumed from the last successful step, matching Phase 8's resume semantics. The `ResearchRunService` tracks step completion, and the agent checks step status before executing each step.

### Run Status Determination

| Condition | Status |
|---|---|
| All 7 steps complete, all findings validated | COMPLETED |
| ≥5 steps complete, some findings validated | PARTIAL |
| Classification not found or critical failure | FAILED |
| User-initiated abort | CANCELLED |

---

## 35. Open Questions

### Reconciliation Note

OQ-5 (Cross-Industry Research Deduplication) has been promoted from an open question to a resolved decision (see §20.A Idempotency and Reusability below). OQ-1 through OQ-4 remain open questions for the implementation phase.

### OQ-1: Concrete SearchProvider Implementation

Phase 9 requires a concrete `SearchProvider` implementation. Options include Google Custom Search API, Bing Search API, and SerpAPI. The mock provider is sufficient for testing but production use requires a real implementation.

**Impact:** Without a concrete SearchProvider, industry source discovery is limited to existing ResearchDocument records and NewsProvider results.

**Recommendation:** Implement a Google Custom Search provider as the default, with configuration-driven provider selection.

### OQ-2: Concrete MacroDataProvider Implementation

Phase 9 uses `MacroDataProvider` for industry-relevant indicators. Currently only a mock exists. Options include RBI DBIE API, data.gov.in API, and FRED (for global indicators).

**Impact:** Without a concrete MacroDataProvider, the agent cannot retrieve macro indicators. Industry analysis proceeds without macro context, producing more UNCERTAINTY findings.

**Recommendation:** Implement a minimal provider for the most impactful Indian indicators (industrial production index, sectoral indices). Full macro coverage is the Macro Economics Agent's (#8) responsibility. See §11 reconciliation note on MacroDataProvider boundary.

### OQ-3: Industry Source Seeding

The agent discovers sources through SearchProvider and NewsProvider, but some high-value industry sources (NASSCOM annual reports, IBEF sector pages, Ministry publications) should be pre-registered as Source records in the database.

**Impact:** Without seeding, the agent relies entirely on web search to find authoritative industry sources, which may miss some key publications.

**Recommendation:** Create seed data for 10-15 major Indian industry data sources (NASSCOM, SIAM, IBEF, CII, FICCI, relevant ministries) with appropriate SourceType and SourceTier classifications.

### OQ-4: IndustryData Population Strategy

The `IndustryData` model exists but is currently unpopulated. Should the Industry Research Agent populate it with extracted metrics, or should a separate data pipeline handle this?

**Impact:** If the agent populates IndustryData, its findings and the IndustryData records must stay consistent. If a separate pipeline does it, the agent uses IndustryData as read-only context.

**Recommendation:** The agent populates IndustryData with key metrics (market size, growth rate, concentration) extracted during its run, using the `source_evidence_id` FK for provenance. This keeps the IndustryData table current with each research run.

### RESOLVED: Concurrency, Research Identity, and Freshness (Second Reconciliation)

**Formerly OQ-5.** Promoted to a resolved architectural decision during first reconciliation, then restructured during second reconciliation to explicitly separate three distinct mechanisms that were previously conflated.

#### Mechanism 1: Concurrency Lock (Prevents Simultaneous Runs)

**Purpose:** Prevent two runs for the same research target from executing simultaneously.

**Mechanism:** Redis advisory lock + application-level active-run check.

**Lock key pattern (generalized):**

| Target Type | Redis Lock Key | Application Check |
|---|---|---|
| Company | `research_lock:company:{company_id}` | `get_active_run(company_id)` — existing, unchanged |
| Industry | `research_lock:industry:{industry_id}:{observation_date}` | `get_active_industry_run(industry_id, observation_date)` — new |

**Asymmetry between company and industry locking (intentional):**
- **Company:** Lock does NOT include `observation_date`. This matches ADR-007's existing `research_run:{company_id}` pattern and the current `get_active_run(company_id)` which blocks ANY active run for the company, regardless of observation_date. Company research for different dates may overlap in data retrieval and source processing.
- **Industry:** Lock INCLUDES `observation_date`. Industry research for different observation dates accesses strictly different temporal windows. Concurrent execution for the same industry on different dates is safe and desirable (e.g., quarterly industry snapshots).

The `observation_date` asymmetry is a design choice, not an oversight. If a future requirement arises to allow concurrent company runs for different observation dates, the company lock can be extended to include `observation_date` without affecting industry locking.

**Scope:** The lock covers ALL active statuses (CREATED, QUEUED, RUNNING) for the target key.

#### Mechanism 2: Research Reuse Identity (Same Research Question?)

**Purpose:** Determine whether a completed run answers the same research question as a new request, enabling result sharing across callers.

**Identity tuple:** `(target_type, target_id, observation_date)`
- Company: `("company", company_id, observation_date)`
- Industry: `("industry", industry_id, observation_date)`

Two requests with identical identity tuples are asking the same research question. If a COMPLETED run exists for that identity tuple, its results may be reused (subject to freshness — Mechanism 3).

**What is NOT part of the identity:**
- **`agent_version` / `prompt_version` / `tool_versions`:** Tracked on `AgentExecution` for reproducibility, but NOT part of reuse identity. A newer agent version produces findings that supersede the older version's findings — the freshness policy handles staleness. Over-keying the identity by including versions would defeat reuse entirely, since every code deployment changes agent_version.
- **`configuration` (token budget, model tier, etc.):** NOT part of reuse identity. Different configurations affect research depth but not the research question itself.
- **`run_type` (execution mode):** NOT part of reuse identity. A FULL run's results can satisfy an INCREMENTAL request if fresh enough (the FULL run is strictly more complete).

**Concrete example:** HDFC Bank and ICICI Bank both have `industry_id` pointing to "Private Banks" in the Classification table. When the multi-agent workflow runs for HDFC Bank, it triggers an industry research run for Private Banks with `("industry", private_banks_uuid, 2024-06-30)`. If ICICI Bank's workflow then starts with the same observation_date:

1. **Concurrent:** The second encounters the Redis advisory lock and waits. When the first completes, the second discovers a COMPLETED run for the same identity tuple and reuses it.
2. **Sequential (same observation_date):** The second queries for a reusable run matching the identity tuple. Found → link existing findings.
3. **Sequential (different observation_date):** Different identity tuple → new research run.

#### Mechanism 3: Freshness Policy (Is the Result Still Usable?)

**Purpose:** Determine whether a completed run's results are fresh enough to use, given that data and agent versions change over time.

**Configurable parameters:**

| Parameter | Default | Description |
|---|---|---|
| `max_age_hours` | 24 | Maximum age of a reusable run, measured from `completed_at` |
| `require_current_version` | `false` | If `true`, reuse only if the run's agent version matches the current version |

**Reference timestamp:** `completed_at` (when the research finished, not when it started). This ensures the freshness window reflects when the results were produced, not when the run was initiated.

**Reusable statuses:**
- **COMPLETED:** Reusable within freshness window.
- **PARTIAL:** NOT reusable by default. PARTIAL results have known gaps — the caller must explicitly opt in to use them. A separate `allow_partial_reuse: bool = False` configuration flag controls this.
- **FAILED / CANCELLED:** NOT reusable. Ever.

**Version mismatch handling:** When `require_current_version = false` (the default), a completed run using an older agent version is still reusable within the freshness window. The assumption: newer versions improve quality but don't invalidate prior findings within a 24-hour window. When stricter freshness is needed (e.g., after a critical prompt fix), set `require_current_version = true` or reduce `max_age_hours`.

**Reuse query pattern:**

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
) -> ResearchRun | None:
    """Find a reusable completed run matching the research identity.

    Returns the most recent run matching (target_type, target_id, observation_date)
    that is COMPLETED (or PARTIAL if allow_partial), within the freshness window,
    and optionally matching the current agent version.
    """
```

**Service layer changes (complete list for all three mechanisms):**
- `get_active_industry_run(industry_id, observation_date)`: Mechanism 1 — returns an active (CREATED/QUEUED/RUNNING) run for the concurrency key.
- `get_reusable_run(target_type, target_id, observation_date, **policy)`: Mechanism 2+3 — returns a reusable COMPLETED run matching the identity tuple within the freshness window.
- `get_completed_industry_run(industry_id, observation_date, max_age_hours=24)`: Convenience wrapper around `get_reusable_run` for industry target type.

**Orchestration-level usage (LangGraph node):**

```python
# In the multi-agent workflow:
# Step 1: Check for reusable result (Mechanism 2 + 3)
existing_run = await run_service.get_reusable_run(
    target_type="industry",
    target_id=industry_id,
    observation_date=observation_date,
)
if existing_run is not None:
    state["industry_analysis"] = await load_industry_findings(existing_run.id)
    return state

# Step 2: Check concurrency lock (Mechanism 1)
active_run = await run_service.get_active_industry_run(industry_id, observation_date)
if active_run is not None:
    # Wait or raise — another run is in progress
    raise ConcurrentRunError(active_run_id=active_run.id)

# Step 3: No reusable or active run — create and execute
run = await run_service.initiate_run(
    ResearchRunCreate(
        target_type="industry",
        industry_id=industry_id,
        run_type="FULL",
        ...
    )
)
result = await agent.execute(request)
```

---

## 36. ADR Analysis

### ADRs Directly Applicable to Phase 9

| ADR | Applicability | Phase 9 Impact |
|---|---|---|
| ADR-001 (LangGraph) | Phase 9 agent is a standalone async module, designed to be wrapped as a LangGraph node | No LangGraph dependency in Phase 9 |
| ADR-003 (Decimal) | All financial values (market size, growth rates) use Decimal | Applied without modification |
| ADR-004 (Evidence Citations) | FACT findings require evidence; finding types enforced | Applied without modification |
| ADR-005 (Provider Abstraction) | Agent uses SearchProvider, MacroDataProvider, NewsProvider, LLMProvider through Protocol interfaces | Phase 9 adds SearchProvider and MacroDataProvider as new runtime dependencies |
| ADR-007 (Failure & Resilience) | Retry semantics, PARTIAL status, idempotency lock | Applied with industry_id lock instead of company_id lock |
| ADR-008 (Cost Controls) | 20,000 token budget, per-run cost tracking, model tier optimization | Applied with industry-specific budget |

### ADRs Not Applicable to Phase 9

| ADR | Reason |
|---|---|
| ADR-002 (Background Tasks) | Phase 9 is a synchronous agent run, not a background pipeline |
| ADR-006 (India Market Focus) | Implicit — the Industry Research Agent focuses on Indian industries by design |
| ADR-009 (NSE/BSE Data Access) | Phase 9 does not access exchange data directly |

### Potential New ADR

**ADR-010: Industry-Level Research Run Identity** — The decision to make `ResearchRun.company_id` nullable and add `industry_id` is significant enough to warrant an ADR. The ADR should document:
- The need for non-company-anchored research runs.
- The check constraint ensuring at least one target is set.
- The impact on existing queries and indexes.
- The backward compatibility with existing data.

---

## 37. Acceptance Criteria

### Reconciliation Note

Acceptance criteria updated during second reconciliation to reflect: `target_type` discriminator (replaces `run_type` for target semantics), XOR check constraint (replaces OR), separated concurrency/reuse/freshness mechanisms, and corrected backfill semantics.

### Functional Acceptance Criteria

| # | Criterion | Verification |
|---|---|---|
| AC-01 | Agent validates industry exists in Classification table with `level=INDUSTRY` | Unit test |
| AC-02 | Agent discovers industry-relevant sources from SearchProvider and NewsProvider | Unit test with mock providers |
| AC-03 | Agent retrieves and registers documents with `company_id = NULL` | Unit test |
| AC-04 | Agent extracts evidence from industry documents with correct EvidenceType | Unit test with mock LLM |
| AC-05 | Agent generates findings across all 14 industry categories (excl. research_gap and contradiction which are generated by Step 7) | Integration test |
| AC-06 | Five Forces analysis produces at least one finding per force (5 categories: `entry_barriers`, `supplier_power`, `buyer_power`, `substitution_risk`, `competitive_rivalry`) | Integration test |
| AC-07 | TAM/SAM estimation produces at least one FACT or AI_INFERENCE finding in `market_size` category | Integration test |
| AC-08 | All FACT findings have evidence linkage (enforced by validation step) | Unit test |
| AC-09 | Findings with `source_publication_date > observation_date` are rejected | Unit test (validation step) |
| AC-10 | Finding categories are validated against `INDUSTRY_FINDING_CATEGORIES` (14 categories) | Unit test |
| AC-11 | Research gaps identified for each missing dimension in `EXPECTED_INDUSTRY_DIMENSIONS` (12 dimensions) | Unit test |
| AC-12 | Contradictions between sources are preserved as separate findings with category `contradiction` | Unit test |
| AC-13 | Token budget (20,000) is enforced; exhaustion produces PARTIAL, not FAILED | Unit test |
| AC-14 | Agent produces ResearchRun with COMPLETED/PARTIAL/FAILED status | Integration test |
| AC-15 | All outputs are persisted through ResearchRunService | Integration test |
| AC-16 | `ResearchRun.target_type` is set to `"industry"` for all industry research runs; `run_type` retains execution-mode value (e.g., "FULL") | Unit test |
| AC-17 | Agent gracefully degrades when MacroDataProvider is unavailable (UNCERTAINTY findings, not FAILED) | Unit test |

### Concurrency, Reuse, and Freshness Acceptance Criteria

| # | Criterion | Verification |
|---|---|---|
| AC-18 | Concurrency lock key is `research_lock:industry:{industry_id}:{observation_date}` | Unit test |
| AC-19 | Concurrent industry research requests for the same (industry_id, observation_date) do not create duplicate runs | Integration test with concurrent requests |
| AC-20 | A COMPLETED industry run with matching research identity `(target_type="industry", industry_id, observation_date)` is reused by subsequent requests within freshness window | Integration test |
| AC-21 | Reuse freshness threshold is configurable (default 24 hours), measured from `completed_at` | Unit test |
| AC-22 | PARTIAL and FAILED runs are NOT reused by default — a new run is created | Unit test |
| AC-22a | Concurrency lock, research reuse identity, and freshness policy are implemented as separable mechanisms (not a single conflated check) | Code review / unit test |

### Non-Functional Acceptance Criteria

| # | Criterion | Target |
|---|---|---|
| AC-23 | Total agent execution time | ≤ 120 seconds (excluding document retrieval latency) |
| AC-24 | Token usage | ≤ 20,000 tokens per run |
| AC-25 | Test coverage | ≥ 85% for agent module |
| AC-26 | No network calls in unit tests | All providers mocked |
| AC-27 | mypy strict passes | Zero type errors |
| AC-28 | ruff passes | Zero lint errors |

### Schema Migration Acceptance Criteria

| # | Criterion | Verification |
|---|---|---|
| AC-29 | `ResearchRun.company_id` is nullable | Migration + schema introspection test |
| AC-30 | `ResearchRun.industry_id` FK to `company.classification(id)` exists | Migration + schema introspection test |
| AC-31 | XOR check constraint `chk_research_run_target` enforces mutual exclusivity: `(target_type='company' AND company_id IS NOT NULL AND industry_id IS NULL) OR (target_type='industry' AND company_id IS NULL AND industry_id IS NOT NULL)` | Migration + unit test |
| AC-32 | Existing ResearchRun records unaffected (all have company_id, constraint satisfied; target_type auto-set to 'company' by server_default) | Migration + data verification |
| AC-33 | `target_type` column exists with `NOT NULL DEFAULT 'company'`; existing `run_type` values are NOT modified | Migration + data verification |
| AC-34 | Partial index `ix_research_run_industry` exists for `industry_id IS NOT NULL` | Schema introspection test |
| AC-34a | Index `ix_research_run_target_type` exists for `(target_type, started_at DESC)` | Schema introspection test |
| AC-35 | Downgrade path works (drops industry_id, target_type; re-applies NOT NULL on company_id) | Migration rollback test |
| AC-36 | Phase 8 agent continues to work without modification after migration (backward compatibility) — `target_type` server_default handles it, `run_type` unchanged | Integration test — run Phase 8 agent against migrated schema |

---

## 38. Implementation Sequence

### Recommended Implementation Order

| Order | Task | Dependencies | Estimated Effort |
|---|---|---|---|
| 1 | Schema migration: target_type column + ResearchRun.company_id nullable + industry_id FK + XOR constraint + indexes | None | Small |
| 2 | ResearchRunService: add target_type/industry_id support, `get_active_industry_run()`, `get_reusable_run()` | Task 1 | Small |
| 3 | ResearchRunRepository: add `get_by_industry()` | Task 1 | Small |
| 4 | Agent contracts: `IndustryResearchRequest`, `IndustryResearchConfig`, industry tool I/O schemas, `INDUSTRY_FINDING_CATEGORIES`, `INDUSTRY_RESEARCH_STEPS` | None | Medium |
| 5 | Agent tools: `IndustryResearchTools` class with 8 tools | Task 4 | Medium |
| 6 | Agent prompts: evidence extraction, industry analysis, gap/contradiction | None | Medium |
| 7 | Agent core: `IndustryResearchAgent` class with 7-step workflow | Tasks 2-6 | Large |
| 8 | Agent tests: unit tests, integration tests | Task 7 | Large |
| 9 | API endpoint: `POST /api/v1/research/industry` | Tasks 2, 7 | Small |
| 10 | Golden dataset tests: 3-5 reference industries | Task 8 | Medium |

### Implementation Phase Mapping

This implementation can be split into sub-phases:

- **Phase 9a**: Schema migration + service layer updates (Tasks 1-3).
- **Phase 9b**: Agent contracts, tools, and prompts (Tasks 4-6).
- **Phase 9c**: Agent core implementation and tests (Tasks 7-8).
- **Phase 9d**: API integration and golden dataset tests (Tasks 9-10).

---

## 39. Risks

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No concrete SearchProvider available | Medium | High — source discovery degraded | Mock provider for testing; prioritize Google Custom Search implementation |
| No concrete MacroDataProvider available | Medium | Medium — macro context missing | Agent produces UNCERTAINTY findings; not a blocker |
| Industry data quality varies widely | High | Medium — more UNCERTAINTY findings | Explicit gap handling; no data fabrication |
| Token budget insufficient for complex industries | Medium | Medium — PARTIAL runs | Monitor utilization; adjust budget if ≥30% of runs hit budget |
| Schema migration affects existing tests | Low | Medium — test breakage | Migration adds nullable field; existing data unaffected |
| LLM prompt quality for industry analysis | Medium | High — poor finding quality | Golden dataset testing; iterative prompt refinement |

### Process Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep into company-specific analysis | Medium | High — violates boundary | Strict category validation; agent review |
| Phase 10 (Competitive Moat) blocked on Phase 9 | Low | Medium — schedule impact | Phase 9 acceptance criteria are self-contained |

---

## 40. Decision Summary

### Reconciliation Note

Decision summary updated through two reconciliation passes. Decisions marked [R] were resolved during first reconciliation; [R2] marks second-reconciliation corrections.

| # | Decision | Rationale | Reconciled? |
|---|---|---|---|
| D-01 | 7-step sequential workflow matching Phase 8 | Proven pattern; reusable infrastructure | No change |
| D-02 | [R2] **Option A: nullable `company_id` + `industry_id` FK + explicit `target_type` discriminator** (not Option B generic target, not Option C child-run). XOR check constraint enforces mutual exclusivity. | Semantically correct; `target_type` is orthogonal to `run_type` (execution mode); generalizes to Macro Agent; manageable migration cost. See §20 for full analysis. | **Second reconciliation** |
| D-03 | `industry_research_agent` as distinct `agent_name` | Unambiguous finding attribution | No change |
| D-04 | [R] **14 finding categories** (`growth_rate` merged into `growth_drivers`). One name collision (`growth_drivers`) with Phase 8 — resolved by requiring `agent_name` filter. | Optimized for semantic consistency and queryability. See §14 for rationale. | **Reconciled** |
| D-05 | Porter's Five Forces as structured findings, not free-form text. Concrete boundary examples provided for Banking and IT Services. | Framework adherence enforced by schema. See §16 for examples. | **Reconciled (expanded)** |
| D-06 | [R] SearchProvider = direct dependency. **MacroDataProvider = limited, non-blocking dependency.** Agent degrades gracefully without it. | Phase 9 uses macro for industry context only; Phase 13 owns full macro. See §11 reconciliation note. | **Reconciled** |
| D-07 | [R] **20,000 token budget confirmed.** Phase 8's 30,000 is for Financial Analysis (#2), not the Industry Agent (#4). | Consistent with architecture specification. Agent-level budget; aggregate run budget is a separate concern. See §23. | **Reconciled (confirmed)** |
| D-08 | ResearchDocument.company_id=NULL for industry documents | Field already nullable at line 60-63 of research.py; no schema change needed | No change |
| D-09 | [R2] **Concurrency lock keyed by `research_lock:industry:{industry_id}:{observation_date}`**. Concurrency, research reuse identity, and freshness policy are explicitly separated as three independent mechanisms. | Observation_date in lock prevents cross-temporal blocking. Separation ensures each mechanism can evolve independently. See §35 for full specification. | **Second reconciliation** |
| D-10 | [R] Phase 8 reuse classified as A (direct) / B (duplicate) / C (extract candidate). 20 Category A components, 10 Category B, 4 Category C. | Explicit classification replaces ambiguous "reuse" label. See §30. | **Reconciled** |
| D-11 | Industry source discovery focuses on Tier 2 sources | Government and industry body data is the primary source for industry research | No change |
| D-12 | No INDUSTRY_ATTRACTIVENESS score computation | Scoring is downstream; agent produces findings, not scores | No change |
| D-13 | Plain async Python, no LangGraph | Consistent with Phase 8; designed for future LangGraph wrapping | No change |
| D-14 | Agent does not modify Classification table | Taxonomy management is administrative | No change |
| D-15 | ADR-010 recommended for target_type + industry_id schema change | Decision is significant enough for formal ADR | Updated scope |
| D-16 | [R] **Industry research runs are reusable.** Research reuse identity = `(target_type, target_id, observation_date)`. Freshness = configurable TTL (default 24h) from `completed_at`. PARTIAL/FAILED not reusable by default. | Prevents redundant research. Three mechanisms explicitly separated. See §35. | **Reconciled + second reconciliation** |
| D-17 | [R2] **`target_type` field (NOT `run_type`) is the target discriminator.** `target_type = "industry"` for industry runs; `target_type = "company"` for company runs (server_default). `run_type` retains its existing execution-mode semantics (FULL, INCREMENTAL, etc.) and is NOT modified.** | `run_type` already has defined semantics across Phase 7 architecture, Phase 8 code, and test suite. Conflating target type with execution mode is incorrect. See §20 "run_type Has Existing Semantics" finding. | **Second reconciliation (critical correction)** |
| D-18 | [R] **IndustryData.research_run_id FK deferred** — not required for Phase 9. | IndustryData already has `source_evidence_id` for provenance. Population strategy is OQ-4. See §25. | **New (reconciliation)** |

---

## 41. Readiness Assessment

### Reconciliation Note

Readiness assessment updated to reflect all reconciled decisions. The ResearchRun target model and schema implications are now explicitly resolved (§20, §25).

### Infrastructure Readiness

| Component | Status | Blocker? |
|---|---|---|
| Phase 7 ResearchRun infrastructure | COMPLETED | No |
| Phase 8 Company Research Agent | COMPLETED (commit 393dc2f) | No |
| Phase 4 Evidence subsystem | COMPLETED | No |
| Phase 3 Domain models (Classification, IndustryData) | COMPLETED | No |
| Phase 5 Provider framework (Protocol interfaces) | COMPLETED | No |
| SearchProvider (concrete implementation) | MOCK ONLY | **Not a blocker** — mock sufficient for development/testing; needed for production |
| MacroDataProvider (concrete implementation) | MOCK ONLY | No — agent degrades gracefully (§11 reconciliation); limited dependency |
| NewsProvider (concrete implementation) | MOCK ONLY | No — agent degrades gracefully |
| LLMProvider (concrete implementation) | MOCK ONLY for tests | No — mock sufficient for testing |

### Contract Readiness

| Contract | Status | Reuse Category (§30) |
|---|---|---|
| SourceCandidate | READY | A — direct reuse |
| TokenBudget | READY | A — direct reuse (different default) |
| FindingItem | READY | A — direct reuse (different agent_name) |
| PersistEvidenceInput/Output | READY | A — direct reuse |
| PersistFindingsInput/Output | READY | A — direct reuse |
| RetrieveDocumentInput/Output | READY | A — direct reuse |
| StepDefinition | READY | A — direct reuse |
| EvidenceExtractionOutput | READY | A — direct reuse |
| FindingGenerationOutput | READY | A — direct reuse |
| IndustryResearchRequest | TO BE CREATED | B — new contract |
| IndustryResearchConfig | TO BE CREATED | B — new contract |
| Industry-specific tool I/O schemas | TO BE CREATED | B — new contracts |

### Schema Readiness

| Schema Element | Status | Reconciled Decision |
|---|---|---|
| ResearchRun.target_type (NOT NULL DEFAULT 'company') | REQUIRES MIGRATION | D-17 (§40) — second reconciliation |
| ResearchRun.company_id nullable | REQUIRES MIGRATION | Option A (§20) |
| ResearchRun.industry_id FK | REQUIRES MIGRATION | Option A (§20) |
| XOR check constraint (target_type ↔ FK consistency) | REQUIRES MIGRATION | Option A (§20) — second reconciliation |
| Partial index ix_research_run_industry | REQUIRES MIGRATION | §25 |
| Index ix_research_run_target_type | REQUIRES MIGRATION | §25 |
| run_type values | **NO MODIFICATION** — retains execution-mode semantics | D-17 (§40) — second reconciliation |
| ResearchDocument.company_id nullable | ALREADY NULLABLE (line 60-63 of research.py) | No change needed |
| IndustryData model | EXISTS | No change needed (research_run_id FK deferred — D-18) |
| Classification model | EXISTS | No change needed |
| All required enums | EXIST (verified against enums.py) | No additions needed |

### Resolved Architectural Decisions

All 11 first-reconciliation topics + 3 second-reconciliation corrections have been resolved:

| # | Topic | Resolution | Section |
|---|---|---|---|
| 1 | ResearchRun target semantics | **Option A** — nullable company_id + industry_id FK + explicit `target_type` discriminator with XOR constraint. `run_type` retains execution-mode semantics. | §20 (second reconciliation) |
| 2 | Industry research reusability | **Three-mechanism design** — concurrency lock, research reuse identity, freshness policy explicitly separated | §35 (second reconciliation) |
| 3 | Concurrency | **Lock key = `research_lock:industry:{industry_id}:{observation_date}`** (concurrency only — not conflated with reuse) | §35 (second reconciliation) |
| 4 | Token budget | **20,000 confirmed** — distinct from Phase 8's 30,000 (Financial Analysis budget) | §23 |
| 5 | Porter Five Forces boundary | **Industry Agent = structural forces; Moat Agent = company-specific moat; Competitor Agent = company comparison.** Concrete examples for Banking and IT Services. | §16 |
| 6 | Macro provider boundary | **Limited, non-blocking.** MacroDataProvider is direct but gracefully degradable. Phase 13 owns full macro. | §11 |
| 7 | Finding taxonomy | **14 categories** — `growth_rate` merged into `growth_drivers`. One collision (`growth_drivers`) resolved by requiring agent_name filter. | §14 |
| 8 | Phase 8 reuse classification | **20 Category A, 10 Category B, 4 Category C** components classified | §30 |
| 9 | Database migration gate | **Required, minimal.** One migration with 6 SQL statements. Full backward compatibility analysis provided. | §25 |
| 10 | Acceptance criteria | **36 acceptance criteria** (17 functional, 5 idempotency, 6 non-functional, 8 migration) | §37 |
| 11 | Readiness verdict | See below | This section |

### Verdict: READY FOR IMPLEMENTATION

Phase 9 implementation is **READY TO BEGIN**. All material architectural decisions are resolved.

**Prerequisites (must be completed in order):**

1. **Phase 9a (first task):** Schema migration — `target_type` column + ResearchRun.company_id nullable + industry_id FK + XOR check constraint + indexes. Must complete before any agent code is written. No `run_type` modification.
2. **Phase 9a (second task):** ResearchRunService and ResearchRunRepository extensions — `get_active_industry_run()`, `get_reusable_run()`, `get_by_industry()`.

**No blockers:**
- All Phase 3/4/5/7/8 infrastructure is in place.
- All required enum values exist.
- Mock providers are sufficient for development and testing.
- Concrete SearchProvider/MacroDataProvider implementations are needed for production but not for development.

**Remaining open questions (OQ-1 through OQ-4):** These are implementation-phase decisions that do not block starting. They concern concrete provider selection, source seeding strategy, and IndustryData population — none affect the agent's architecture or schema.

**Clarifications for the implementer:**
- `growth_drivers` name collision with Phase 8: downstream queries MUST filter by `agent_name` in addition to `category`. This is documented in §14 but the implementer should add a code comment at the query site.
- Category C components (step runner, LLM caller, budget enforcement): extraction to shared module is recommended before Phase 10 but not required for Phase 9. If deferred, Phase 9 duplicates ~200 lines of Phase 8's step execution logic.
- The 20,000 token budget may prove tight for industries with many data sources. Monitor `industry_research.token_utilization_pct` metric and escalate to 25,000 if ≥30% of runs hit budget.

The architecture reuses ~55% of Phase 8's contracts and infrastructure (20 Category A components), requires new implementation for 11 components (Category B), and identifies 4 components that should eventually be shared (Category C).

Estimated implementation effort: **3-5 days** for an experienced developer familiar with the Phase 8 codebase.
