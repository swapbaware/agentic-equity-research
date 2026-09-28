# Agent Architecture

## Overview

The platform uses a multi-agent architecture orchestrated by LangGraph. Each agent has a clearly defined responsibility, structured input/output schemas, and access to specific tools. Agents communicate through typed state objects, never free-text message passing.

## Design Principles

1. **Single Responsibility**: Each agent has one well-defined analytical domain.
2. **Structured State**: Agents read from and write to a typed `ResearchState` object.
3. **Deterministic Orchestration**: The workflow graph is a defined state machine, not emergent agent-to-agent chat.
4. **Tool-Based Data Access**: Agents access data through typed tools, not raw API calls.
5. **Evidence Attachment**: Every agent finding must reference source evidence.
6. **LLM for Reasoning Only**: Financial calculations are performed by deterministic tools, not LLM arithmetic.

## Research State

The shared state passed through the agent graph:

```python
class ResearchState(TypedDict):
    company: CompanyProfile
    research_run_id: str
    financial_data: FinancialData
    business_model: BusinessModelAnalysis | None
    industry_analysis: IndustryAnalysis | None
    moat_assessment: list[MoatAssessment]
    management_analysis: ManagementAnalysis | None
    growth_analysis: GrowthAnalysis | None
    macro_analysis: MacroAnalysis | None
    competitor_analysis: CompetitorAnalysis | None
    valuation: ValuationResult | None
    risks: list[Risk]
    catalysts: list[Catalyst]
    bull_case: ScenarioAnalysis | None
    bear_case: ScenarioAnalysis | None
    thesis_challenge: ThesisChallengeResult | None
    evidence_verification: EvidenceVerificationResult | None
    findings: list[ResearchFinding]
    evidence: list[Evidence]
    scores: dict[str, CompanyScore]
    quality_gate_results: dict[str, bool]
    thesis: InvestmentThesis | None
    errors: list[str]
    status: ResearchStatus
```

## Agent Definitions

### 1. Universe Discovery Agent

**Responsibility**: Discover and filter companies matching user-defined criteria.

**Inputs**: Screening criteria (market cap, sector, financial filters)
**Outputs**: List of candidate companies with basic profiles

**Tools**:
- `search_company()` — Search by name, symbol, sector
- `get_company_profile()` — Basic company data
- `screen_companies()` — Apply financial filters

**Does NOT**: Perform deep analysis. Only discovery and initial filtering.

---

### 2. Financial Analysis Agent

**Responsibility**: Comprehensive quantitative analysis of 5-10 year financials.

**Inputs**: Company ID, financial statements
**Outputs**: `FinancialData` with growth rates, profitability, balance sheet health, cash flow analysis, quality metrics

**Tools**:
- `get_financial_statements()` — Retrieve statements (5-10yr)
- `get_quarterly_results()` — Recent quarterly data
- `calculate_ratios()` — Deterministic ratio calculation
- `calculate_cagr()` — Compound growth rates
- `detect_anomalies()` — Flag unusual patterns

**Key Metrics Analyzed**:
- Growth: Revenue/EBITDA/EBIT/PAT/EPS/FCF CAGR
- Profitability: Gross/EBITDA/EBIT/Net margin, ROE, ROCE, ROIC
- Balance Sheet: Debt/Equity, Net Debt/EBITDA, interest coverage, current ratio
- Cash Flow: CFO, FCF, CFO/PAT, FCF/PAT, capex, working capital
- Quality: Earnings consistency, cash conversion, margin stability, return on incremental capital

**Financial Forensics Sub-Analysis**:
- Receivables growth vs revenue growth
- Inventory build-up
- CFO below PAT
- Capitalized expenses
- Related-party transactions
- Auditor qualifications
- Produces: `FinancialRedFlagScore`

---

### 3. Business Model Agent

**Responsibility**: Understand and articulate how the company makes money.

**Inputs**: Company profile, annual reports, investor presentations
**Outputs**: `BusinessModelAnalysis`

**Tools**:
- `get_annual_report()` — Annual report content
- `get_investor_presentation()` — Presentation content
- `retrieve_document()` — Semantic document search

**Analyzes**:
- Revenue streams and segmentation
- Revenue concentration (customer, product, geography)
- Recurring vs transactional revenue
- Pricing power indicators
- Operating leverage
- Capital intensity
- Working capital intensity

---

### 4. Industry Analysis Agent

**Responsibility**: Analyze the industry structure and attractiveness.

**Inputs**: Company's industry, competitor data
**Outputs**: `IndustryAnalysis`

**Tools**:
- `get_peer_data()` — Industry peer financials
- `search_web()` — Industry reports and data
- `get_macro_data()` — Industry-level indicators

**Framework**: Porter's Five Forces + TAM/SAM analysis

**Analyzes**:
- Market size (TAM, SAM)
- Growth rate and drivers
- Industry structure and concentration
- Entry barriers
- Supplier/buyer power
- Substitution risk
- Regulatory environment
- Cyclicality and commodity exposure
- Global competitive dynamics

---

### 5. Competitive Moat Agent

**Responsibility**: Identify, evidence, and assess economic moats.

**Inputs**: Business model analysis, industry analysis, financial data
**Outputs**: `list[MoatAssessment]`

**Tools**:
- `get_peer_data()` — Competitor comparison
- `retrieve_document()` — Evidence retrieval
- `compare_companies()` — Side-by-side analysis

**Evaluates 16 Moat Types**:
Brand, Cost Advantage, Network Effects, Switching Costs, Distribution, Scale, Regulatory Barriers, IP, Technology, Data, Ecosystem, Customer Embeddedness, Manufacturing, Supply Chain, Capital Access, Location

**For Each Moat**:
- Evidence (with source citations)
- Strength: None / Narrow / Moderate / Wide
- Durability estimate (years)
- Competitive comparison
- Threats that could weaken it
- Confidence level

**Critical Rule**: Must NOT label a moat as "wide" without specific evidence. The default is "none" — evidence upgrades the assessment.

---

### 6. Management & Governance Agent

**Responsibility**: Assess management quality, governance, and capital allocation.

**Inputs**: Shareholding data, corporate actions, management statements
**Outputs**: `ManagementAnalysis`

**Tools**:
- `get_shareholding()` — Promoter/institutional ownership
- `get_corporate_filings()` — Related-party disclosures
- `retrieve_document()` — Management commentary

**Analyzes**:
- Promoter ownership and pledge trends
- Capital allocation track record (dividends, buybacks, acquisitions, capex)
- Related-party transactions
- Auditor history and qualifications
- Executive compensation
- Subsidiary complexity
- Equity dilution history
- Promise vs execution tracking (PROMISE → EXPECTATION → ACTUAL)

---

### 7. Future Growth & Optionality Agent

**Responsibility**: Identify future business potential beyond current operations.

**Inputs**: Business model, management commentary, industry data
**Outputs**: `GrowthAnalysis` with classified opportunities

**Tools**:
- `retrieve_document()` — Management guidance, presentations
- `search_web()` — Industry/theme research
- `get_macro_data()` — Government incentives, policy data

**Classifies Opportunities By Maturity**:
- **Proven**: Revenue-generating, scaled
- **Commercializing**: Product/market fit, early revenue
- **Early Stage**: Pilot/prototype phase
- **Experimental**: R&D, no revenue
- **Speculative**: Announced intent only

**Separates**: Current Business from Future Optionality

**Themes Tracked**: AI, data centres, semiconductors, defence, EV, renewable energy, pharma innovation, digital payments, manufacturing, infrastructure, etc.

---

### 8. Macro Economics Agent

**Responsibility**: Map macroeconomic factors to company-specific impact.

**Inputs**: Company profile, sector, macro indicators
**Outputs**: `MacroAnalysis`

**Tools**:
- `get_macro_data()` — GDP, inflation, rates, FX, commodities
- `search_web()` — Policy updates, government data

**Maps Company-Specific Impact**:
```
Example:
  Oil price ↑ → Airline: costs ↑, margins ↓
  Oil price ↑ → ONGC: revenue ↑
  Interest rates ↓ → Banks: NIM compression
  Interest rates ↓ → Real estate: demand ↑
```

**Macro Factors**: India GDP, inflation, RBI repo rate, INR/USD, crude oil, commodity prices, government capex, fiscal policy, credit growth, global growth, US rates, China dynamics, geopolitics, trade policy, government incentives (PLI etc.)

---

### 9. Competitor Analysis Agent

**Responsibility**: Identify and compare relevant competitors.

**Inputs**: Company profile, industry, peer data
**Outputs**: `CompetitorAnalysis`

**Tools**:
- `get_peer_data()` — Competitor financials
- `compare_companies()` — Multi-metric comparison
- `search_web()` — Unlisted/global competitor data

**Compares**: Revenue growth, EBITDA margin, ROCE, ROIC, FCF conversion, debt, valuation, market share, product portfolio, R&D, capex, geographic exposure

**Must Answer**:
- "Why might this company win against its competitors?"
- "Why might it lose?"

---

### 10. Valuation Agent

**Responsibility**: Run multiple valuation models with explicit assumptions.

**Inputs**: Financial data, growth analysis, comparable company data
**Outputs**: `ValuationResult` with BEAR/BASE/BULL scenarios

**Tools**:
- `calculate_dcf()` — Deterministic DCF model
- `calculate_ratios()` — Valuation multiples
- `get_valuation_history()` — Historical valuation bands
- `get_peer_data()` — Peer valuation comparison

**Models**: P/E, EV/EBITDA, P/S, P/B, PEG, FCF Yield, EV/FCF, DCF, Reverse DCF, Historical Bands, Peer Comparison

**Rules**:
- All assumptions must be visible in output
- Always produce a RANGE, never a single false-precision value
- DCF inputs are configurable (revenue growth, margin, tax, capex, working capital, terminal growth, WACC)
- Business Quality vs Valuation matrix output

---

### 11. Risk Agent

**Responsibility**: Systematically identify and categorize risks.

**Inputs**: All prior analyses
**Outputs**: `list[Risk]` ranked by severity

**Risk Types**: Business, Financial, Valuation, Governance, Regulatory, Technology, Disruption, Commodity, Currency, Geopolitical, Customer Concentration, Supplier Concentration, Execution

**Output**: Top 5 risks + thesis invalidation conditions

---

### 12. Bull Case Agent

**Responsibility**: Construct the optimistic scenario with supporting evidence.

**Inputs**: All analyses, growth opportunities, catalysts
**Outputs**: `ScenarioAnalysis` (BULL)

**Must Define**: Revenue CAGR, margin trajectory, EPS path, FCF path, exit multiple, valuation range, key assumptions, "What Must Go Right"

---

### 13. Bear Case Agent

**Responsibility**: Construct the pessimistic scenario with supporting evidence.

**Inputs**: All analyses, risks, competitive threats
**Outputs**: `ScenarioAnalysis` (BEAR)

**Must Define**: Same structure as Bull Case + "What Can Go Wrong"

---

### 14. Thesis Challenger Agent

**Responsibility**: Actively attempt to disprove the investment thesis. Acts as Devil's Advocate.

**Inputs**: Draft thesis, all analyses
**Outputs**: `ThesisChallengeResult`

**Must**:
- Identify confirmation bias in the research
- Find counter-evidence
- Challenge growth assumptions
- Question moat durability
- Stress-test valuation sensitivity
- Flag unrealistic expectations

---

### 15. Evidence Verification Agent

**Responsibility**: Verify that all factual claims have valid sources.

**Inputs**: All findings and evidence references
**Outputs**: `EvidenceVerificationResult`

**Checks**:
- Every FACT-type finding has a source citation
- Sources are from appropriate tiers
- No LLM-fabricated data in factual claims
- Management claims are labeled as such
- AI inferences are labeled as such
- Sources are current (not stale)

---

### 16. Research Synthesis Agent

**Responsibility**: Combine all agent outputs into a coherent investment thesis and research report.

**Inputs**: Complete `ResearchState`
**Outputs**: `InvestmentThesis`, research report, company scorecard

**Report Structure**:
1. Executive Summary
2. Company Overview
3. Investment Thesis
4. Industry & Market
5. Competitive Position & Moat
6. Financial Analysis
7. Management & Governance
8. Future Growth
9. Valuation (Bear/Base/Bull)
10. Risks & Catalysts
11. Thesis Invalidation
12. Sources

**Labels Everything**: FACT / CALCULATION / MANAGEMENT CLAIM / ANALYST OPINION / AI INFERENCE / ASSUMPTION / UNCERTAINTY

---

### 17. Portfolio/Watchlist Monitoring Agent

**Responsibility**: Continuous monitoring of watched companies for thesis-relevant changes.

**Inputs**: Watchlist companies, stored theses
**Outputs**: Alerts and thesis change notifications

**Monitors**:
- New quarterly results vs expectations
- Management commentary changes
- Shareholding changes (promoter, institutional)
- Corporate announcements
- Price/valuation changes
- Macro factor changes

**Triggers**: THESIS CHANGE DETECTED when new data contradicts stored thesis

## Orchestration Graph (LangGraph)

```
                    ┌──────────────────┐
                    │      START       │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Universe         │
                    │ Discovery        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Financial        │
                    │ Analysis         │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼───┐  ┌───────▼──────┐
     │ Business   │  │ Industry │  │ Competitor   │
     │ Model      │  │ Analysis │  │ Analysis     │
     └────────┬───┘  └──────┬───┘  └───────┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼───┐  ┌───────▼──────┐
     │ Moat       │  │Management│  │ Future       │
     │ Analysis   │  │& Gov     │  │ Growth       │
     └────────┬───┘  └──────┬───┘  └───────┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼─────────┐
                    │ Macro            │
                    │ Economics        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Valuation        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Risk             │
                    │ Analysis         │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼───┐  ┌───────▼──────┐
     │ Bull Case  │  │Bear Case │  │ Thesis       │
     │            │  │          │  │ Challenger   │
     └────────┬───┘  └──────┬───┘  └───────┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼─────────┐
                    │ Evidence         │
                    │ Verification     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Quality Gates    │
                    │ (12 checks)      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Research         │
                    │ Synthesis        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │      END         │
                    └──────────────────┘
```

**Parallel Execution**: Where agents have no data dependencies (e.g., Business Model / Industry / Competitor, or Moat / Management / Growth), they run in parallel.

**Conditional Routing**: If a quality gate fails, the workflow can loop back to specific agents for additional evidence gathering before proceeding.

## Agent Memory Architecture

| Layer | Scope | Persistence | Contents |
|-------|-------|-------------|----------|
| Short-Term | Current research run | In-memory (ResearchState) | Current task context |
| Company Memory | Per company | PostgreSQL | Historical research, financials, theses |
| Market Memory | Cross-company | PostgreSQL + pgvector | Sector research, industry data |
| Thesis Memory | Per company | PostgreSQL | Previous conclusions, assumptions, versions |
| Evidence Memory | Global | PostgreSQL + S3 | Source-backed facts, documents |

**Critical Rule**: Only verified, source-backed facts enter Evidence Memory. LLM-generated inferences are stored as `finding_type = AI_INFERENCE` and never promoted to factual memory without evidence.

## Agent Tool Schema

Every agent tool follows this contract:

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
