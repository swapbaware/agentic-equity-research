"""Tests for Future Growth & Optionality Agent prompt builders (Phase 12.3).

Follows the established pattern from
``backend/tests/agents/test_competitive_moat_prompts.py`` and
``backend/tests/agents/test_governance_prompts.py``.

Acceptance criteria verified:
  AC-09: System preamble includes <retrieved_document> XML tag defense
  AC-10: Evidence extraction prompt covers growth domains
  AC-11: Growth analysis prompt enforces maturity classification rules
  AC-12: Growth analysis prompt enforces finding type rules (no FACT for projections)
  AC-13: Temporal rules embedded in all LLM prompts
  AC-14: Growth challenge prompt requires risk identification per opportunity
"""

from __future__ import annotations

from datetime import date

import pytest

from app.agents.future_growth.prompts import (
    GROWTH_SYSTEM_PREAMBLE,
    _wrap_document,
    growth_analysis_prompt,
    growth_challenge_prompt,
    growth_evidence_extraction_prompt,
)

# ===========================================================================
# Helpers
# ===========================================================================

_COMPANY = "Reliance Industries Limited"
_INDUSTRY = "Diversified Conglomerate"
_OBS_DATE = date(2024, 3, 31)
_SOURCE_ID = "src-001"
_DOC_TITLE = "Annual Report FY2024"
_SAMPLE_DOC = "The company announced a Rs 75,000 crore capex plan for FY25."

_SAMPLE_EVIDENCE = (
    "[0] FACT (HIGH): Jio Platforms reported Rs 21,000 crore revenue in Q3 FY24. "
    "Context: Quarterly results.\n"
    "[1] MANAGEMENT_STATEMENT (HIGH): Management guided 20% growth in new energy "
    "segment for FY25. Context: Chairman's letter.\n"
    "[2] FINANCIAL_DATA (MEDIUM): India EV market expected to reach $100 billion "
    "by 2030. Context: Industry report.\n"
)

_SAMPLE_OPPORTUNITIES = (
    "Opportunity 1: New Energy Business\n"
    "  Category: EXPANSION\n"
    "  Maturity: EARLY_STAGE\n"
    "  TAM: 50,000 crores\n"
    "  Confidence: MEDIUM\n"
    "\n"
    "Opportunity 2: 5G Services Rollout\n"
    "  Category: TECHNOLOGY\n"
    "  Maturity: COMMERCIALIZING\n"
    "  TAM: 120,000 crores\n"
    "  Confidence: HIGH\n"
)


# ===========================================================================
# GROWTH_SYSTEM_PREAMBLE — AC-09
# ===========================================================================


class TestGrowthSystemPreamble:
    def test_is_string(self) -> None:
        assert isinstance(GROWTH_SYSTEM_PREAMBLE, str)

    def test_non_empty(self) -> None:
        assert len(GROWTH_SYSTEM_PREAMBLE) > 0

    def test_mentions_retrieved_document_tag(self) -> None:
        assert "<retrieved_document>" in GROWTH_SYSTEM_PREAMBLE

    def test_marks_content_as_data(self) -> None:
        assert "DATA" in GROWTH_SYSTEM_PREAMBLE

    def test_marks_content_as_not_instructions(self) -> None:
        assert "NOT" in GROWTH_SYSTEM_PREAMBLE
        assert "instructions" in GROWTH_SYSTEM_PREAMBLE.lower()

    def test_never_follow_directives(self) -> None:
        lower = GROWTH_SYSTEM_PREAMBLE.lower()
        assert "never follow" in lower or "never obey" in lower

    def test_mentions_growth_domain(self) -> None:
        lower = GROWTH_SYSTEM_PREAMBLE.lower()
        assert "growth" in lower

    def test_mentions_optionality(self) -> None:
        lower = GROWTH_SYSTEM_PREAMBLE.lower()
        assert "optionality" in lower

    def test_mentions_json(self) -> None:
        assert "JSON" in GROWTH_SYSTEM_PREAMBLE

    def test_mentions_indian_companies(self) -> None:
        assert "Indian listed companies" in GROWTH_SYSTEM_PREAMBLE

    def test_no_secrets(self) -> None:
        lower = GROWTH_SYSTEM_PREAMBLE.lower()
        for secret_indicator in ["api_key", "api-key", "password", "secret", "token"]:
            assert secret_indicator not in lower


# ===========================================================================
# _wrap_document
# ===========================================================================


class TestWrapDocument:
    def test_wraps_in_xml_tags(self) -> None:
        result = _wrap_document("content", "src-1", "Title")
        assert result.startswith("<retrieved_document")
        assert result.endswith("</retrieved_document>")

    def test_content_inside_tags(self) -> None:
        result = _wrap_document("my content here", "src-1", "Title")
        assert "my content here" in result

    def test_source_id_attribute(self) -> None:
        result = _wrap_document("c", "src-42", "T")
        assert 'source_id="src-42"' in result

    def test_title_attribute(self) -> None:
        result = _wrap_document("c", "s", "My Document Title")
        assert 'title="My Document Title"' in result

    def test_newline_separates_tag_and_content(self) -> None:
        result = _wrap_document("content", "s", "t")
        lines = result.split("\n")
        assert len(lines) >= 3
        assert lines[0].startswith("<retrieved_document")
        assert lines[-1] == "</retrieved_document>"

    def test_empty_content(self) -> None:
        result = _wrap_document("", "s", "t")
        assert "<retrieved_document" in result
        assert "</retrieved_document>" in result

    def test_content_with_special_characters(self) -> None:
        content = 'He said "hello" & <goodbye>'
        result = _wrap_document(content, "s", "t")
        assert content in result


# ===========================================================================
# growth_evidence_extraction_prompt — AC-10, AC-13
# ===========================================================================


class TestGrowthEvidenceExtractionPrompt:
    def test_includes_system_preamble(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, _INDUSTRY, _SAMPLE_DOC, _SOURCE_ID, _DOC_TITLE, _OBS_DATE)
        assert GROWTH_SYSTEM_PREAMBLE in result

    def test_includes_company_name(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        assert "TCS" in result

    def test_includes_industry_name_when_provided(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", "IT Services", "doc", "s1", "title", _OBS_DATE)
        assert "IT Services" in result

    def test_omits_industry_line_when_none(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        assert "Industry:" not in result

    def test_wraps_document_in_xml_tags(self) -> None:
        result = growth_evidence_extraction_prompt("Reliance", None, "document body", "src-42", "AR 2024", _OBS_DATE)
        assert '<retrieved_document source_id="src-42" title="AR 2024">' in result
        assert "</retrieved_document>" in result
        assert "document body" in result

    # -- AC-10: Growth domains -----------------------------------------------

    def test_covers_capacity_expansion_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "capacity expansion" in lower

    def test_covers_new_products_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "new products" in lower or "product launches" in lower

    def test_covers_new_markets_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "new markets" in lower or "geographic expansion" in lower

    def test_covers_partnerships_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "partnership" in lower or "alliance" in lower

    def test_covers_tam_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "total addressable market" in lower or "tam" in lower

    def test_covers_government_incentives_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "government incentive" in lower or "pli" in lower

    def test_covers_technology_adoption_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "technology adoption" in lower or "digital transformation" in lower

    def test_covers_revenue_from_new_initiatives_domain(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "revenue from new initiatives" in lower or "recently launched" in lower

    # -- Evidence types and confidence ---------------------------------------

    def test_specifies_evidence_types(self) -> None:
        result = growth_evidence_extraction_prompt("ITC", None, "doc", "s1", "title", _OBS_DATE)
        for evidence_type in (
            "FACT",
            "FINANCIAL_DATA",
            "MANAGEMENT_STATEMENT",
            "ANALYST_OPINION",
            "REGULATORY_FILING",
        ):
            assert evidence_type in result, f"Missing evidence type: {evidence_type}"

    def test_specifies_confidence_levels(self) -> None:
        result = growth_evidence_extraction_prompt("ITC", None, "doc", "s1", "title", _OBS_DATE)
        assert "HIGH" in result
        assert "MEDIUM" in result
        assert "LOW" in result

    def test_management_statement_classification_instruction(self) -> None:
        result = growth_evidence_extraction_prompt("ICICI", None, "doc", "s1", "title", _OBS_DATE)
        assert "MANAGEMENT_STATEMENT" in result
        lower = result.lower()
        assert "never" in lower and "fact" in lower

    def test_fact_prohibition_for_forward_looking(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        assert "Never use FACT for forward-looking" in result

    def test_snippet_confidence_guidance(self) -> None:
        result = growth_evidence_extraction_prompt("Bajaj", None, "doc", "s1", "title", _OBS_DATE)
        assert "snippet" in result.lower()

    def test_requests_evidences_json_key(self) -> None:
        result = growth_evidence_extraction_prompt("SBI", None, "doc", "s1", "title", _OBS_DATE)
        assert '"evidences"' in result

    # -- Anti-hallucination --------------------------------------------------

    def test_prohibits_hallucination(self) -> None:
        result = growth_evidence_extraction_prompt("Wipro", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate" in lower or "do not invent" in lower

    def test_prohibits_tam_fabrication(self) -> None:
        result = growth_evidence_extraction_prompt(_COMPANY, None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "do not invent tam" in lower or "do not fabricate" in lower

    # -- Purity and safety ---------------------------------------------------

    def test_contains_no_secrets(self) -> None:
        result = growth_evidence_extraction_prompt("Test Co", None, "doc", "s1", "title", _OBS_DATE)
        for keyword in ("api_key", "password", "token=", "secret", "credential"):
            assert keyword not in result.lower()

    def test_is_pure_function(self) -> None:
        a = growth_evidence_extraction_prompt("X", "Y", "d", "s", "t", _OBS_DATE)
        b = growth_evidence_extraction_prompt("X", "Y", "d", "s", "t", _OBS_DATE)
        assert a == b


# ===========================================================================
# growth_analysis_prompt — AC-11, AC-12
# ===========================================================================


class TestGrowthAnalysisPrompt:
    def test_includes_system_preamble(self) -> None:
        result = growth_analysis_prompt(_COMPANY, _INDUSTRY, _SAMPLE_EVIDENCE, None, None, _OBS_DATE)
        assert GROWTH_SYSTEM_PREAMBLE in result

    def test_includes_company_name(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, _OBS_DATE)
        assert "TCS" in result

    def test_includes_industry_when_provided(self) -> None:
        result = growth_analysis_prompt("TCS", "IT Services", "ev", None, None, _OBS_DATE)
        assert "IT Services" in result

    def test_omits_industry_when_none(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, _OBS_DATE)
        assert "Industry:" not in result

    def test_includes_company_context_when_provided(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", "company findings here", None, _OBS_DATE)
        assert "company findings here" in result

    def test_omits_company_context_when_none(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, _OBS_DATE)
        assert "Prior Company Research" not in result

    def test_includes_industry_context_when_provided(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, "industry findings here", _OBS_DATE)
        assert "industry findings here" in result

    def test_omits_industry_context_when_none(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, _OBS_DATE)
        assert "Prior Industry Research" not in result

    def test_includes_evidence_summaries(self) -> None:
        result = growth_analysis_prompt("Test", None, "my evidence data here", None, None, _OBS_DATE)
        assert "my evidence data here" in result

    # -- AC-11: Growth categories --------------------------------------------

    def test_lists_all_7_growth_categories(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        expected_categories = [
            "NEW_PRODUCT",
            "NEW_MARKET",
            "ACQUISITION",
            "PARTNERSHIP",
            "GOVERNMENT_INCENTIVE",
            "TECHNOLOGY",
            "EXPANSION",
        ]
        for category in expected_categories:
            assert category in result, f"Missing growth category: {category}"

    # -- AC-11: Maturity classification --------------------------------------

    def test_lists_all_5_maturity_tiers(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        expected_tiers = [
            "PROVEN",
            "COMMERCIALIZING",
            "EARLY_STAGE",
            "EXPERIMENTAL",
            "SPECULATIVE",
        ]
        for tier in expected_tiers:
            assert tier in result, f"Missing maturity tier: {tier}"

    def test_speculative_is_default_maturity(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "default" in lower and "speculative" in lower

    def test_proven_requires_fact_evidence(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "PROVEN" in result
        lower = result.lower()
        assert "fact" in lower and "revenue" in lower

    def test_management_claims_stay_speculative(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "management" in lower and "speculative" in lower

    def test_no_maturity_upgrade_on_claims_alone(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "do not upgrade" in lower and "management claims" in lower

    # -- TAM estimation rules ------------------------------------------------

    def test_tam_requires_methodology(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "tam_methodology" in result

    def test_tam_requires_uncertainty_ranges(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "tam_low" in result
        assert "tam_high" in result

    def test_tam_prohibits_fabrication(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate tam" in lower or ("do not fabricate" in lower and "tam" in lower)

    # -- Dual scoring: Growth Quality vs Future Optionality ------------------

    def test_growth_quality_scoring_section(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "Growth Quality" in result
        assert "growth_quality_scores" in result

    def test_future_optionality_scoring_section(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "Future Optionality" in result
        assert "future_optionality_scores" in result

    def test_growth_vs_optionality_separation(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "growth_vs_optionality_separation" in result

    def test_score_range_0_to_100(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "0-100" in result or "score" in result.lower()

    # -- India structural themes ---------------------------------------------

    def test_lists_all_10_india_themes(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        expected_themes = [
            "artificial_intelligence",
            "data_centres",
            "semiconductors",
            "defence_indigenisation",
            "electric_vehicles",
            "renewable_energy",
            "pharma_innovation",
            "digital_payments",
            "manufacturing_pli",
            "infrastructure",
        ]
        for theme in expected_themes:
            assert theme in result, f"Missing India theme: {theme}"

    def test_themes_require_evidence(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "supporting evidence" in lower or "do not assign themes speculatively" in lower

    # -- AC-12: Finding type rules -------------------------------------------

    def test_specifies_all_finding_types(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        for ft in (
            "FACT",
            "CALCULATION",
            "MANAGEMENT_CLAIM",
            "ANALYST_OPINION",
            "AI_INFERENCE",
            "ASSUMPTION",
            "UNCERTAINTY",
        ):
            assert ft in result, f"Missing finding type: {ft}"

    def test_fact_prohibition_for_projections(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "NEVER" in result
        lower = result.lower()
        assert "fact" in lower and "projection" in lower

    def test_management_claim_not_fact(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "MANAGEMENT_CLAIM" in result
        lower = result.lower()
        assert "never" in lower and "fact" in lower

    def test_growth_projections_are_ai_inference(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "AI_INFERENCE" in result
        lower = result.lower()
        assert "growth projection" in lower or "projections" in lower

    # -- Finding categories --------------------------------------------------

    def test_lists_all_14_finding_categories(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        expected_categories = [
            "growth_opportunity",
            "growth_quality",
            "future_optionality",
            "tam_estimate",
            "growth_trajectory",
            "theme_alignment",
            "management_growth_claim",
            "growth_risk",
            "growth_challenge",
            "maturity_classification",
            "growth_score_rationale",
            "optionality_score_rationale",
            "research_gap",
            "contradiction",
        ]
        for cat in expected_categories:
            assert cat in result, f"Missing finding category: {cat}"

    # -- Anti-hallucination --------------------------------------------------

    def test_prohibits_hallucination(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate" in lower or "do not invent" in lower

    def test_conservative_default_speculative(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "conservative" in lower and "speculative" in lower

    def test_research_gap_for_missing_evidence(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "research_gap" in result

    # -- Output format -------------------------------------------------------

    def test_requests_opportunities_key(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert '"opportunities"' in result

    def test_requests_findings_key(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert '"findings"' in result

    def test_specifies_evidence_indices(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "evidence_indices" in result

    # -- Purity and safety ---------------------------------------------------

    def test_contains_no_secrets(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        for keyword in ("api_key", "password", "token=", "credential", "database_url"):
            assert keyword not in result.lower()

    def test_is_pure_function(self) -> None:
        a = growth_analysis_prompt("X", "Y", "e", "c", "i", _OBS_DATE)
        b = growth_analysis_prompt("X", "Y", "e", "c", "i", _OBS_DATE)
        assert a == b

    def test_full_context_prompt(self) -> None:
        result = growth_analysis_prompt(
            "Reliance Industries",
            "Oil & Gas",
            "Evidence: strong brand recognition",
            "Company has dominant market position",
            "Industry growing at 8% CAGR",
            _OBS_DATE,
        )
        assert "Reliance Industries" in result
        assert "Oil & Gas" in result
        assert "Evidence: strong brand recognition" in result
        assert "Company has dominant market position" in result
        assert "Industry growing at 8% CAGR" in result


# ===========================================================================
# growth_challenge_prompt — AC-14
# ===========================================================================


class TestGrowthChallengePrompt:
    def test_includes_system_preamble(self) -> None:
        result = growth_challenge_prompt(_COMPANY, _SAMPLE_OPPORTUNITIES, _SAMPLE_EVIDENCE)
        assert GROWTH_SYSTEM_PREAMBLE in result

    def test_includes_company_name(self) -> None:
        result = growth_challenge_prompt("TCS", "opportunities", "evidence")
        assert "TCS" in result

    def test_includes_opportunities_summary(self) -> None:
        result = growth_challenge_prompt("Test", "New Energy: EARLY_STAGE, EXPANSION", "evidence")
        assert "New Energy: EARLY_STAGE, EXPANSION" in result

    def test_includes_evidence_summaries(self) -> None:
        result = growth_challenge_prompt("Test", "opportunities", "evidence data here")
        assert "evidence data here" in result

    # -- AC-14: Challenge areas (5 required) ---------------------------------

    def test_requires_materialisation_risk(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "materialisation risk" in lower or "materialisation" in lower

    def test_requires_tam_challenge(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "tam challenge" in lower or "tam" in lower

    def test_requires_competitive_risk(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "competitive risk" in lower or "competitive" in lower

    def test_requires_execution_risk(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "execution risk" in lower or "execution" in lower

    def test_requires_over_optimism_assessment(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "over-optimism" in lower

    # -- Adversarial mandate -------------------------------------------------

    def test_adversarial_mandate(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "adversarial" in lower or "disprove" in lower

    def test_stress_test_each_opportunity(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "stress-test" in lower or "stress test" in lower

    # -- Challenge rules -----------------------------------------------------

    def test_non_speculative_must_have_challenge(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "non-speculative" in lower or "non-speculative" in lower.replace(" ", "-")

    def test_speculative_already_conservative(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "speculative" in lower and "conservative" in lower

    def test_management_claim_stays_management_claim(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "MANAGEMENT_CLAIM" in result
        lower = result.lower()
        assert "not fact" in lower or "never" in lower

    def test_challenge_outputs_are_ai_inference(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "AI_INFERENCE" in result

    def test_conservative_preference(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "conservative" in lower and "speculative" in lower

    # -- Research gaps and contradictions -------------------------------------

    def test_requires_research_gap_findings(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "research_gap" in result

    def test_requires_contradiction_findings(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "contradiction" in result

    # -- Anti-hallucination --------------------------------------------------

    def test_prohibits_hallucination(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        lower = result.lower()
        assert "do not invent" in lower or "do not fabricate" in lower

    # -- Output format -------------------------------------------------------

    def test_requests_challenges_key(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert '"challenges"' in result

    def test_requests_findings_key(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert '"findings"' in result

    def test_requests_overall_optimism_assessment(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "overall_optimism_assessment" in result

    def test_challenge_output_fields(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        assert "opportunity_name" in result
        assert "challenge" in result
        assert "tam_challenge" in result
        assert "competitive_risk" in result
        assert "execution_risk" in result
        assert "revised_confidence" in result

    # -- Purity and safety ---------------------------------------------------

    def test_contains_no_secrets(self) -> None:
        result = growth_challenge_prompt("Test", "opps", "ev")
        for keyword in ("api_key", "password", "token=", "secret", "credential"):
            assert keyword not in result.lower()

    def test_is_pure_function(self) -> None:
        a = growth_challenge_prompt("X", "a", "e")
        b = growth_challenge_prompt("X", "a", "e")
        assert a == b


# ===========================================================================
# Cross-cutting prompt properties
# ===========================================================================


class TestCrossCuttingProperties:
    """Properties that must hold across all three prompt builders."""

    @pytest.mark.parametrize(
        "prompt_fn,args",
        [
            (
                growth_evidence_extraction_prompt,
                ("Co", None, "doc", "s", "t", _OBS_DATE),
            ),
            (growth_analysis_prompt, ("Co", None, "ev", None, None, _OBS_DATE)),
            (growth_challenge_prompt, ("Co", "opps", "ev")),
        ],
    )
    def test_all_prompts_include_preamble(self, prompt_fn, args) -> None:  # type: ignore[no-untyped-def]
        result = prompt_fn(*args)
        assert GROWTH_SYSTEM_PREAMBLE in result

    @pytest.mark.parametrize(
        "prompt_fn,args",
        [
            (
                growth_evidence_extraction_prompt,
                ("Co", None, "doc", "s", "t", _OBS_DATE),
            ),
            (growth_analysis_prompt, ("Co", None, "ev", None, None, _OBS_DATE)),
            (growth_challenge_prompt, ("Co", "opps", "ev")),
        ],
    )
    def test_all_prompts_contain_no_secrets(self, prompt_fn, args) -> None:  # type: ignore[no-untyped-def]
        result = prompt_fn(*args)
        for keyword in (
            "api_key",
            "password",
            "token=",
            "credential",
            "database_url",
            "redis_url",
        ):
            assert keyword not in result.lower()

    @pytest.mark.parametrize(
        "prompt_fn,args",
        [
            (
                growth_evidence_extraction_prompt,
                ("Co", None, "doc", "s", "t", _OBS_DATE),
            ),
            (growth_analysis_prompt, ("Co", None, "ev", None, None, _OBS_DATE)),
            (growth_challenge_prompt, ("Co", "opps", "ev")),
        ],
    )
    def test_all_prompts_are_deterministic(self, prompt_fn, args) -> None:  # type: ignore[no-untyped-def]
        a = prompt_fn(*args)
        b = prompt_fn(*args)
        assert a == b

    @pytest.mark.parametrize(
        "prompt_fn,args",
        [
            (
                growth_evidence_extraction_prompt,
                ("Co", None, "doc", "s", "t", _OBS_DATE),
            ),
            (growth_analysis_prompt, ("Co", None, "ev", None, None, _OBS_DATE)),
            (growth_challenge_prompt, ("Co", "opps", "ev")),
        ],
    )
    def test_all_prompts_return_strings(self, prompt_fn, args) -> None:  # type: ignore[no-untyped-def]
        result = prompt_fn(*args)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_evidence_extraction_wraps_document(self) -> None:
        result = growth_evidence_extraction_prompt("Co", None, "content", "src-123", "Title", _OBS_DATE)
        assert '<retrieved_document source_id="src-123" title="Title">' in result
        assert "</retrieved_document>" in result

    def test_analysis_does_not_wrap_document(self) -> None:
        result = growth_analysis_prompt("Co", None, "evidence", None, None, _OBS_DATE)
        assert "<retrieved_document source_id=" not in result

    def test_challenge_does_not_wrap_document(self) -> None:
        result = growth_challenge_prompt("Co", "opps", "evidence")
        assert "<retrieved_document source_id=" not in result


# ===========================================================================
# AC-13: Temporal awareness
# ===========================================================================


class TestTemporalAwareness:
    """Tests for AC-13: observation_date parameter and temporal rules."""

    def test_observation_date_parameter_accepted(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", "IT Services", "doc", "s1", "title", date(2024, 3, 31))
        assert isinstance(result, str)

    def test_observation_date_appears_in_extraction_prompt(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", date(2024, 3, 31))
        assert "2024-03-31" in result

    def test_observation_date_appears_in_analysis_prompt(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, date(2024, 3, 31))
        assert "2024-03-31" in result

    def test_temporal_rule_observation_date_boundary(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "observation date" in lower
        assert "<= the observation date" in lower or "on or before" in lower

    def test_date_type_distinction(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        assert "publication_date" in result
        assert "document_date" in result
        assert "filing_date" in result
        assert "period_end" in result
        assert "information_available_date" in result

    def test_post_observation_exclusion_instruction(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "after the observation" in lower and "exclude" in lower

    def test_no_fabricated_dates_instruction(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate" in lower

    def test_uncertainty_preservation_instruction(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "uncertainty" in lower

    def test_analysis_temporal_rules(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "observation date" in lower
        assert "do not fabricate dates" in lower or ("do not fabricate" in lower and "date" in lower)

    def test_analysis_projections_labeled_inference(self) -> None:
        result = growth_analysis_prompt("Test", None, "ev", None, None, _OBS_DATE)
        assert "AI_INFERENCE" in result
        assert "ASSUMPTION" in result
        lower = result.lower()
        assert "never fact" in lower or "never" in lower


# ===========================================================================
# Date fabrication prohibition
# ===========================================================================


class TestDateFabricationProhibition:
    """Tests that date fabrication is prohibited in all prompts."""

    def test_evidence_extraction_prohibits_date_fabrication(self) -> None:
        result = growth_evidence_extraction_prompt("TCS", None, "doc", "s1", "title", _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate" in lower

    def test_analysis_prohibits_date_fabrication(self) -> None:
        result = growth_analysis_prompt("TCS", None, "ev", None, None, _OBS_DATE)
        lower = result.lower()
        assert "do not fabricate" in lower

    def test_challenge_prohibits_date_fabrication(self) -> None:
        result = growth_challenge_prompt("TCS", "opps", "ev")
        lower = result.lower()
        assert "do not invent" in lower or "do not fabricate" in lower
