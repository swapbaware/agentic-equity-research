# ADR-004: Mandatory Evidence Citation System

## Status

Accepted

## Date

2026-09-28

## Context

The platform's credibility depends on distinguishing verified facts from AI-generated inference. Without a citation system, LLM-generated research could present fabricated data as fact, which is unacceptable for a financial research platform.

## Decision

Implement a mandatory evidence citation system where:

1. Every `ResearchFinding` with `finding_type = FACT` must reference at least one `Evidence` record
2. Every `Evidence` record must reference a `ResearchDocument` (the source)
3. Sources are tiered by reliability (Tier 1: official filings, Tier 2: government data, Tier 3: publications)
4. All research outputs label each statement as: FACT, CALCULATION, MANAGEMENT_CLAIM, ANALYST_OPINION, AI_INFERENCE, ASSUMPTION, or UNCERTAINTY

## Implementation

- `Evidence` table stores extracted claims with document reference, page/section, and confidence
- `ResearchFinding` table has a `finding_type` enum enforcing classification
- Quality Gate #11 (Citation Completeness) blocks research publication if FACT-type findings lack citations
- Evidence Verification Agent runs as a dedicated workflow step to catch unsupported claims
- Frontend renders evidence labels visually (color-coded badges per finding type)

## Consequences

- Agents must attach evidence IDs to their findings — this constrains agent prompt design
- Research runs take longer due to evidence verification step
- Some valid AI insights may be marked as AI_INFERENCE rather than FACT — this is correct and intended
- The system may produce RESEARCH INCOMPLETE rather than a polished report if sources are insufficient — this is the desired behavior
