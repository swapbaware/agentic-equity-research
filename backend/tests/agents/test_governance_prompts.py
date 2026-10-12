"""Tests for Management & Governance Agent prompt builders (Phase 11.3).

Follows the established pattern from
``backend/tests/agents/test_competitive_moat_prompts.py``.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.agents.management_governance.prompts import (
    GOVERNANCE_SYSTEM_PREAMBLE,
    _wrap_document,
    governance_analysis_prompt,
    governance_evidence_extraction_prompt,
)

# ===========================================================================
# Helpers
# ===========================================================================

_COMPANY = "Reliance Industries Limited"
_INDUSTRY = "Diversified Conglomerate"
_OBS_DATE = date(2024, 3, 31)
_SOURCE_ID = "src-001"
_DOC_TITLE = "Annual Report FY2024"
_SAMPLE_DOC = "The promoter holding stands at 50.49% as on 31 March 2024."

_SAMPLE_EVIDENCE = (
    "[0] MANAGEMENT_STATEMENT (HIGH): Management guided revenue growth of 15% "
    "for FY25. Context: Chairman's letter.\n"
    "[1] FACT (HIGH): Promoter holding at 50.49% as of 31 March 2024. "
    "Context: Shareholding pattern.\n"
    "[2] REGULATORY_FILING (MEDIUM): Auditor raised emphasis of matter on "
    "subsidiary valuation. Context: Statutory auditor report.\n"
)

_SAMPLE_STATEMENTS = (
    "ID: stmt-aaa | Status: PENDING | Date: 2023-06-15 | Category: "
    "REVENUE_GUIDANCE | Statement: 'Targeting 20% revenue growth in FY24' | "
    "Expected outcome: 20% revenue growth by FY24\n"
    "ID: stmt-bbb | Status: MET | Date: 2022-04-01 | Category: CAPEX_PLAN | "
    "Statement: 'Commission Jamnagar expansion by Q2 FY23'\n"
)

_SAMPLE_SHAREHOLDING = "Promoter: 50.49% | FII: 23.11% | DII: 14.03% | Public: 12.37% | As of: 2024-03-31\n"

_SAMPLE_CORPORATE_ACTIONS = "2023-09-15: RIGHTS_ISSUE — Rights issue of 1:15 at INR 1257\n"


# ===========================================================================
# GOVERNANCE_SYSTEM_PREAMBLE
# ===========================================================================


class TestGovernanceSystemPreamble:
    def test_is_string(self) -> None:
        assert isinstance(GOVERNANCE_SYSTEM_PREAMBLE, str)

    def test_non_empty(self) -> None:
        assert len(GOVERNANCE_SYSTEM_PREAMBLE) > 0

    def test_mentions_retrieved_document_tag(self) -> None:
        assert "<retrieved_document>" in GOVERNANCE_SYSTEM_PREAMBLE

    def test_marks_content_as_data(self) -> None:
        assert "DATA" in GOVERNANCE_SYSTEM_PREAMBLE

    def test_marks_content_as_not_instructions(self) -> None:
        assert "NOT" in GOVERNANCE_SYSTEM_PREAMBLE
        assert "instructions" in GOVERNANCE_SYSTEM_PREAMBLE.lower()

    def test_never_follow_directives(self) -> None:
        lower = GOVERNANCE_SYSTEM_PREAMBLE.lower()
        assert "never follow" in lower or "never obey" in lower

    def test_mentions_governance_domain(self) -> None:
        lower = GOVERNANCE_SYSTEM_PREAMBLE.lower()
        assert "governance" in lower

    def test_mentions_management(self) -> None:
        lower = GOVERNANCE_SYSTEM_PREAMBLE.lower()
        assert "management" in lower

    def test_mentions_json(self) -> None:
        assert "JSON" in GOVERNANCE_SYSTEM_PREAMBLE

    def test_mentions_indian_companies(self) -> None:
        lower = GOVERNANCE_SYSTEM_PREAMBLE.lower()
        assert "indian" in lower

    def test_no_secrets(self) -> None:
        lower = GOVERNANCE_SYSTEM_PREAMBLE.lower()
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

    def test_newlines_around_content(self) -> None:
        result = _wrap_document("body", "s", "t")
        lines = result.split("\n")
        assert len(lines) >= 3

    def test_empty_content(self) -> None:
        result = _wrap_document("", "s", "t")
        assert "<retrieved_document" in result
        assert "</retrieved_document>" in result

    def test_special_characters(self) -> None:
        content = 'He said "hello" & <script>alert(1)</script>'
        result = _wrap_document(content, "s", "t")
        assert content in result


# ===========================================================================
# governance_evidence_extraction_prompt
# ===========================================================================


class TestGovernanceEvidenceExtractionPrompt:
    def _build(self, **kwargs: object) -> str:
        defaults: dict[str, object] = {
            "company_name": _COMPANY,
            "industry_name": _INDUSTRY,
            "document_content": _SAMPLE_DOC,
            "source_id": _SOURCE_ID,
            "document_title": _DOC_TITLE,
            "observation_date": _OBS_DATE,
        }
        defaults.update(kwargs)
        return governance_evidence_extraction_prompt(**defaults)  # type: ignore[arg-type]

    def test_returns_string(self) -> None:
        assert isinstance(self._build(), str)

    def test_includes_preamble(self) -> None:
        assert GOVERNANCE_SYSTEM_PREAMBLE in self._build()

    def test_includes_company_name(self) -> None:
        assert _COMPANY in self._build()

    def test_includes_industry_name(self) -> None:
        assert _INDUSTRY in self._build()

    def test_includes_observation_date(self) -> None:
        assert _OBS_DATE.isoformat() in self._build()

    def test_wraps_document_in_retrieved_document_tags(self) -> None:
        result = self._build()
        assert "<retrieved_document" in result
        assert "</retrieved_document>" in result

    def test_document_content_present(self) -> None:
        assert _SAMPLE_DOC in self._build()

    def test_source_id_in_wrapper(self) -> None:
        assert _SOURCE_ID in self._build()

    def test_document_title_in_wrapper(self) -> None:
        assert _DOC_TITLE in self._build()

    # --- Governance domain coverage (AC-07, AC-10) ---

    def test_covers_management_statements_domain(self) -> None:
        lower = self._build().lower()
        assert "management" in lower
        assert "forward-looking" in lower or "guidance" in lower

    def test_covers_promise_tracking_domain(self) -> None:
        lower = self._build().lower()
        assert "promise" in lower or "outcome" in lower or "commitment" in lower

    def test_covers_shareholding_domain(self) -> None:
        lower = self._build().lower()
        assert "shareholding" in lower

    def test_covers_promoter_pledge_domain(self) -> None:
        lower = self._build().lower()
        assert "pledge" in lower

    def test_covers_capital_allocation_domain(self) -> None:
        lower = self._build().lower()
        assert "capital allocation" in lower or "dividend" in lower

    def test_covers_related_party_transactions_domain(self) -> None:
        lower = self._build().lower()
        assert "related-party" in lower or "related party" in lower

    def test_covers_auditor_qualifications_domain(self) -> None:
        lower = self._build().lower()
        assert "auditor" in lower
        assert "qualification" in lower or "emphasis" in lower

    def test_covers_executive_compensation_domain(self) -> None:
        lower = self._build().lower()
        assert "compensation" in lower or "remuneration" in lower

    def test_covers_subsidiary_domain(self) -> None:
        lower = self._build().lower()
        assert "subsidiary" in lower

    def test_covers_dilution_domain(self) -> None:
        lower = self._build().lower()
        assert "dilution" in lower or "esop" in lower

    # --- Evidence type classification (AC-12) ---

    def test_lists_all_evidence_types(self) -> None:
        result = self._build()
        for et in ("FACT", "FINANCIAL_DATA", "MANAGEMENT_STATEMENT", "ANALYST_OPINION", "REGULATORY_FILING"):
            assert et in result

    def test_management_statement_not_fact_rule(self) -> None:
        lower = self._build().lower()
        assert "management" in lower
        assert "never" in lower and "fact" in lower

    # --- Confidence levels ---

    def test_lists_confidence_levels(self) -> None:
        result = self._build()
        for cl in ("HIGH", "MEDIUM", "LOW"):
            assert cl in result

    # --- Schema reference ---

    def test_references_evidence_extraction_output_schema(self) -> None:
        result = self._build()
        assert "EvidenceExtractionOutput" in result

    def test_references_json_keys(self) -> None:
        result = self._build()
        assert '"evidences"' in result
        assert '"evidence_type"' in result
        assert '"claim"' in result
        assert '"confidence"' in result

    # --- Anti-hallucination (AC-16) ---

    def test_anti_hallucination_instructions(self) -> None:
        lower = self._build().lower()
        assert "fabricat" in lower or "hallucin" in lower or "do not invent" in lower

    def test_prohibits_fabricated_figures(self) -> None:
        lower = self._build().lower()
        assert "fabricat" in lower

    # --- Temporal rules (AC-13) ---

    def test_temporal_rules_present(self) -> None:
        result = self._build()
        assert "observation date" in result.lower()
        assert "temporal" in result.lower() or "date" in result.lower()

    def test_prohibits_date_fabrication(self) -> None:
        lower = self._build().lower()
        assert "fabricat" in lower and "date" in lower

    # --- Security ---

    def test_no_secrets(self) -> None:
        lower = self._build().lower()
        for indicator in ["api_key", "api-key", "password", "secret_key", "bearer"]:
            assert indicator not in lower

    # --- Pure function ---

    def test_deterministic(self) -> None:
        assert self._build() == self._build()

    def test_different_company_produces_different_output(self) -> None:
        a = self._build(company_name="Infosys Limited")
        b = self._build(company_name="TCS Limited")
        assert a != b


# ===========================================================================
# governance_analysis_prompt
# ===========================================================================


class TestGovernanceAnalysisPrompt:
    def _build(self, **kwargs: object) -> str:
        defaults: dict[str, object] = {
            "company_name": _COMPANY,
            "industry_name": _INDUSTRY,
            "evidence_summaries": _SAMPLE_EVIDENCE,
            "existing_statements": _SAMPLE_STATEMENTS,
            "shareholding_context": _SAMPLE_SHAREHOLDING,
            "corporate_actions_context": _SAMPLE_CORPORATE_ACTIONS,
            "observation_date": _OBS_DATE,
        }
        defaults.update(kwargs)
        return governance_analysis_prompt(**defaults)  # type: ignore[arg-type]

    def test_returns_string(self) -> None:
        assert isinstance(self._build(), str)

    def test_includes_preamble(self) -> None:
        assert GOVERNANCE_SYSTEM_PREAMBLE in self._build()

    def test_includes_company_name(self) -> None:
        assert _COMPANY in self._build()

    def test_includes_industry_name(self) -> None:
        assert _INDUSTRY in self._build()

    def test_includes_observation_date(self) -> None:
        assert _OBS_DATE.isoformat() in self._build()

    def test_includes_evidence_summaries(self) -> None:
        assert _SAMPLE_EVIDENCE in self._build()

    def test_includes_existing_statements(self) -> None:
        assert _SAMPLE_STATEMENTS in self._build()

    def test_includes_shareholding_context(self) -> None:
        assert _SAMPLE_SHAREHOLDING in self._build()

    def test_includes_corporate_actions_context(self) -> None:
        assert _SAMPLE_CORPORATE_ACTIONS in self._build()

    # --- ManagementStatement lifecycle (AC-08, AC-11) ---

    def test_includes_management_statement_statuses(self) -> None:
        result = self._build()
        for status in ("PENDING", "MET", "PARTIALLY_MET", "MISSED", "UNKNOWN"):
            assert status in result

    def test_includes_transition_rules(self) -> None:
        result = self._build()
        assert "TERMINAL" in result or "terminal" in result.lower()
        assert "no further transitions" in result.lower()

    def test_terminal_requires_evidence_index(self) -> None:
        lower = self._build().lower()
        assert "outcome_evidence_index" in lower
        assert "must" in lower or "required" in lower

    def test_unknown_requires_resolution_detail(self) -> None:
        result = self._build()
        assert "resolution_detail" in result
        lower = result.lower()
        assert "required" in lower or "must" in lower

    def test_includes_resolution_substates(self) -> None:
        result = self._build()
        for substate in ("NOT_DUE", "INSUFFICIENT_EVIDENCE", "CONTRADICTORY", "REVISED"):
            assert substate in result

    def test_not_due_skip_rule(self) -> None:
        lower = self._build().lower()
        assert "not_due" in lower
        assert "skip" in lower or "do not propose" in lower

    def test_terminal_no_update_rule(self) -> None:
        lower = self._build().lower()
        assert "terminal" in lower
        assert "no further" in lower or "do not propose" in lower

    # --- ManagementStatement categories ---

    def test_includes_statement_categories(self) -> None:
        result = self._build()
        for cat in ("REVENUE_GUIDANCE", "MARGIN_GUIDANCE", "CAPEX_PLAN", "PRODUCT_LAUNCH", "EXPANSION", "OTHER"):
            assert cat in result

    # --- NewManagementStatement schema ---

    def test_new_statement_schema_keys(self) -> None:
        result = self._build()
        for key in (
            '"statement"',
            '"statement_date"',
            '"category"',
            '"expected_outcome"',
            '"expected_timeframe"',
            '"evidence_index"',
        ):
            assert key in result

    # --- ManagementStatementUpdate schema ---

    def test_update_schema_keys(self) -> None:
        result = self._build()
        for key in (
            '"statement_id"',
            '"proposed_status"',
            '"outcome_evidence_index"',
            '"resolution_detail"',
            '"justification"',
        ):
            assert key in result

    # --- Finding type classification (AC-12) ---

    def test_lists_all_finding_types(self) -> None:
        result = self._build()
        for ft in (
            "FACT",
            "CALCULATION",
            "MANAGEMENT_CLAIM",
            "ANALYST_OPINION",
            "AI_INFERENCE",
            "ASSUMPTION",
            "UNCERTAINTY",
        ):
            assert ft in result

    def test_management_claim_not_fact_rule(self) -> None:
        lower = self._build().lower()
        assert "never" in lower
        assert "management" in lower
        assert "fact" in lower

    # --- Governance finding categories (AC-14) ---

    def test_lists_all_governance_finding_categories(self) -> None:
        result = self._build()
        for cat in (
            "management_claim",
            "promise_tracking",
            "shareholding",
            "promoter_pledge",
            "capital_allocation",
            "related_party_transaction",
            "auditor_qualification",
            "executive_compensation",
            "subsidiary_complexity",
            "equity_dilution",
            "governance_red_flag",
            "governance_general",
            "data_gap",
        ):
            assert cat in result

    # --- Governance domain coverage ---

    def test_covers_capital_allocation_domain(self) -> None:
        lower = self._build().lower()
        assert "capital allocation" in lower

    def test_covers_related_party_domain(self) -> None:
        lower = self._build().lower()
        assert "related-party" in lower or "related party" in lower

    def test_covers_auditor_domain(self) -> None:
        lower = self._build().lower()
        assert "auditor" in lower

    def test_covers_compensation_domain(self) -> None:
        lower = self._build().lower()
        assert "compensation" in lower or "remuneration" in lower

    def test_covers_subsidiary_domain(self) -> None:
        lower = self._build().lower()
        assert "subsidiary" in lower

    def test_covers_dilution_domain(self) -> None:
        lower = self._build().lower()
        assert "dilution" in lower

    # --- Governance red flag categories (AC-15) ---

    def test_lists_all_red_flag_categories(self) -> None:
        result = self._build()
        for cat in (
            "promoter_pledge_elevation",
            "declining_promoter_holding",
            "auditor_qualification",
            "auditor_change",
            "related_party_materiality",
            "executive_compensation_excess",
            "promise_track_record",
            "equity_dilution",
            "subsidiary_opacity",
        ):
            assert cat in result

    # --- Red flag schema ---

    def test_red_flag_schema_keys(self) -> None:
        result = self._build()
        assert '"severity"' in result
        assert '"justification"' in result
        assert '"evidence_indices"' in result

    # --- Shareholding exclusion ---

    def test_shareholding_findings_excluded_from_llm(self) -> None:
        lower = self._build().lower()
        assert "step 5a" in lower or "deterministic" in lower

    # --- Output schema ---

    def test_references_governance_analysis_output(self) -> None:
        result = self._build()
        assert "GovernanceAnalysisOutput" in result

    def test_references_generated_finding_schema(self) -> None:
        result = self._build()
        assert "GeneratedFinding" in result

    def test_all_output_field_names_in_schema(self) -> None:
        result = self._build()
        for field in (
            "new_management_statements",
            "statement_updates",
            "capital_allocation_findings",
            "related_party_findings",
            "auditor_findings",
            "compensation_findings",
            "subsidiary_findings",
            "dilution_findings",
            "governance_red_flags",
            "general_findings",
        ):
            assert field in result

    # --- Evidence referencing ---

    def test_evidence_indices_instruction(self) -> None:
        result = self._build()
        assert "evidence_indices" in result
        lower = result.lower()
        assert "0-based" in lower

    # --- Anti-hallucination (AC-16) ---

    def test_anti_hallucination_instructions(self) -> None:
        lower = self._build().lower()
        assert "fabricat" in lower or "hallucin" in lower

    def test_conservative_defaults(self) -> None:
        lower = self._build().lower()
        assert "conservative" in lower or "uncertainty" in lower

    # --- Temporal rules (AC-13) ---

    def test_temporal_rules_present(self) -> None:
        lower = self._build().lower()
        assert "observation date" in lower

    def test_prohibits_date_fabrication(self) -> None:
        lower = self._build().lower()
        assert "fabricat" in lower and "date" in lower

    # --- Security ---

    def test_no_secrets(self) -> None:
        lower = self._build().lower()
        for indicator in ["api_key", "api-key", "password", "secret_key", "bearer"]:
            assert indicator not in lower

    # --- Pure function ---

    def test_deterministic(self) -> None:
        assert self._build() == self._build()

    def test_different_company_produces_different_output(self) -> None:
        a = self._build(company_name="Infosys Limited")
        b = self._build(company_name="TCS Limited")
        assert a != b

    def test_empty_evidence(self) -> None:
        result = self._build(evidence_summaries="")
        assert isinstance(result, str)

    def test_empty_statements(self) -> None:
        result = self._build(existing_statements="")
        assert isinstance(result, str)


# ===========================================================================
# Cross-Cutting Properties (AC-09, AC-19)
# ===========================================================================


class TestCrossCuttingProperties:
    """Properties that must hold across all prompt builders."""

    @pytest.mark.parametrize(
        "prompt_fn",
        [
            lambda: governance_evidence_extraction_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                document_content=_SAMPLE_DOC,
                source_id=_SOURCE_ID,
                document_title=_DOC_TITLE,
                observation_date=_OBS_DATE,
            ),
            lambda: governance_analysis_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                evidence_summaries=_SAMPLE_EVIDENCE,
                existing_statements=_SAMPLE_STATEMENTS,
                shareholding_context=_SAMPLE_SHAREHOLDING,
                corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
                observation_date=_OBS_DATE,
            ),
        ],
        ids=["evidence_extraction", "governance_analysis"],
    )
    def test_preamble_in_all_prompts(self, prompt_fn: object) -> None:
        result = prompt_fn()  # type: ignore[operator]
        assert GOVERNANCE_SYSTEM_PREAMBLE in result

    @pytest.mark.parametrize(
        "prompt_fn",
        [
            lambda: governance_evidence_extraction_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                document_content=_SAMPLE_DOC,
                source_id=_SOURCE_ID,
                document_title=_DOC_TITLE,
                observation_date=_OBS_DATE,
            ),
            lambda: governance_analysis_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                evidence_summaries=_SAMPLE_EVIDENCE,
                existing_statements=_SAMPLE_STATEMENTS,
                shareholding_context=_SAMPLE_SHAREHOLDING,
                corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
                observation_date=_OBS_DATE,
            ),
        ],
        ids=["evidence_extraction", "governance_analysis"],
    )
    def test_no_secrets_in_all_prompts(self, prompt_fn: object) -> None:
        result = prompt_fn()  # type: ignore[operator]
        lower = result.lower()
        for indicator in ["api_key", "api-key", "password", "secret_key", "bearer", "authorization:"]:
            assert indicator not in lower

    @pytest.mark.parametrize(
        "prompt_fn",
        [
            lambda: governance_evidence_extraction_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                document_content=_SAMPLE_DOC,
                source_id=_SOURCE_ID,
                document_title=_DOC_TITLE,
                observation_date=_OBS_DATE,
            ),
            lambda: governance_analysis_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                evidence_summaries=_SAMPLE_EVIDENCE,
                existing_statements=_SAMPLE_STATEMENTS,
                shareholding_context=_SAMPLE_SHAREHOLDING,
                corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
                observation_date=_OBS_DATE,
            ),
        ],
        ids=["evidence_extraction", "governance_analysis"],
    )
    def test_all_prompts_are_deterministic(self, prompt_fn: object) -> None:
        assert prompt_fn() == prompt_fn()  # type: ignore[operator]

    @pytest.mark.parametrize(
        "prompt_fn",
        [
            lambda: governance_evidence_extraction_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                document_content=_SAMPLE_DOC,
                source_id=_SOURCE_ID,
                document_title=_DOC_TITLE,
                observation_date=_OBS_DATE,
            ),
            lambda: governance_analysis_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                evidence_summaries=_SAMPLE_EVIDENCE,
                existing_statements=_SAMPLE_STATEMENTS,
                shareholding_context=_SAMPLE_SHAREHOLDING,
                corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
                observation_date=_OBS_DATE,
            ),
        ],
        ids=["evidence_extraction", "governance_analysis"],
    )
    def test_all_prompts_return_strings(self, prompt_fn: object) -> None:
        result = prompt_fn()  # type: ignore[operator]
        assert isinstance(result, str)
        assert len(result) > 0

    def test_document_wrapping_only_in_extraction(self) -> None:
        extraction = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=_OBS_DATE,
        )
        analysis = governance_analysis_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            evidence_summaries=_SAMPLE_EVIDENCE,
            existing_statements=_SAMPLE_STATEMENTS,
            shareholding_context=_SAMPLE_SHAREHOLDING,
            corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
            observation_date=_OBS_DATE,
        )
        assert "</retrieved_document>" in extraction
        assert "</retrieved_document>" not in analysis


# ===========================================================================
# Temporal Awareness (AC-13)
# ===========================================================================


class TestTemporalAwareness:
    def test_extraction_includes_observation_date(self) -> None:
        result = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=_OBS_DATE,
        )
        assert _OBS_DATE.isoformat() in result

    def test_analysis_includes_observation_date(self) -> None:
        result = governance_analysis_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            evidence_summaries=_SAMPLE_EVIDENCE,
            existing_statements=_SAMPLE_STATEMENTS,
            shareholding_context=_SAMPLE_SHAREHOLDING,
            corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
            observation_date=_OBS_DATE,
        )
        assert _OBS_DATE.isoformat() in result

    def test_extraction_temporal_rules(self) -> None:
        result = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=_OBS_DATE,
        )
        lower = result.lower()
        assert "observation date" in lower

    def test_analysis_temporal_rules(self) -> None:
        result = governance_analysis_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            evidence_summaries=_SAMPLE_EVIDENCE,
            existing_statements=_SAMPLE_STATEMENTS,
            shareholding_context=_SAMPLE_SHAREHOLDING,
            corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
            observation_date=_OBS_DATE,
        )
        lower = result.lower()
        assert "observation date" in lower

    def test_different_dates_produce_different_prompts(self) -> None:
        a = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=date(2024, 3, 31),
        )
        b = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=date(2023, 9, 30),
        )
        assert a != b

    def test_no_fabricated_dates_in_extraction(self) -> None:
        result = governance_evidence_extraction_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            document_content=_SAMPLE_DOC,
            source_id=_SOURCE_ID,
            document_title=_DOC_TITLE,
            observation_date=_OBS_DATE,
        )
        lower = result.lower()
        assert "do not fabricate" in lower or "fabricat" in lower

    def test_no_fabricated_dates_in_analysis(self) -> None:
        result = governance_analysis_prompt(
            company_name=_COMPANY,
            industry_name=_INDUSTRY,
            evidence_summaries=_SAMPLE_EVIDENCE,
            existing_statements=_SAMPLE_STATEMENTS,
            shareholding_context=_SAMPLE_SHAREHOLDING,
            corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
            observation_date=_OBS_DATE,
        )
        lower = result.lower()
        assert "fabricat" in lower


# ===========================================================================
# Date Fabrication Prohibition
# ===========================================================================


class TestDateFabricationProhibition:
    @pytest.mark.parametrize(
        "prompt_fn",
        [
            lambda: governance_evidence_extraction_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                document_content=_SAMPLE_DOC,
                source_id=_SOURCE_ID,
                document_title=_DOC_TITLE,
                observation_date=_OBS_DATE,
            ),
            lambda: governance_analysis_prompt(
                company_name=_COMPANY,
                industry_name=_INDUSTRY,
                evidence_summaries=_SAMPLE_EVIDENCE,
                existing_statements=_SAMPLE_STATEMENTS,
                shareholding_context=_SAMPLE_SHAREHOLDING,
                corporate_actions_context=_SAMPLE_CORPORATE_ACTIONS,
                observation_date=_OBS_DATE,
            ),
        ],
        ids=["evidence_extraction", "governance_analysis"],
    )
    def test_prohibits_date_invention(self, prompt_fn: object) -> None:
        result = prompt_fn()  # type: ignore[operator]
        lower = result.lower()
        assert "fabricat" in lower
