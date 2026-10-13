"""Phase 11.5 — Comprehensive validation rule tests for Management & Governance Agent.

Tests all validation rules defined in architecture §26:
  MSV-01 through MSV-08: ManagementStatement validation
  FV-01 through FV-07:   Finding validation
  RF-01 through RF-05:   Red flag validation
  SV-01 through SV-04:   Shareholding validation
  Cross-domain validation
  Edge cases (empty inputs, malformed data, boundary values)
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.agents.contracts import (
    ExtractedEvidence,
    GeneratedFinding,
    GovernanceAnalysisOutput,
    GovernanceValidationResult,
    ManagementStatementSummary,
    ShareholdingSnapshot,
)
from app.agents.management_governance.agent import (
    _validate_governance_output,
)
from app.models.enums import (
    ConfidenceLevel,
    EvidenceType,
    ManagementStatementCategory,
    ManagementStatementStatus,
)

# ---------------------------------------------------------------------------
# Fixed UUIDs
# ---------------------------------------------------------------------------

STMT_UUID_1 = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000001")
STMT_UUID_2 = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000002")
STMT_UUID_3 = uuid.UUID("cccccccc-dddd-eeee-ffff-000000000003")

OBSERVATION_DATE = date(2025, 9, 30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence(
    *,
    evidence_type: EvidenceType = EvidenceType.FACT,
    claim: str = "Test evidence",
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> ExtractedEvidence:
    return ExtractedEvidence(
        evidence_type=evidence_type,
        claim=claim,
        confidence=confidence,
    )


def _analysis(
    *,
    new_statements: list[dict[str, Any]] | None = None,
    statement_updates: list[dict[str, Any]] | None = None,
    capital_allocation: list[dict[str, Any]] | None = None,
    related_party: list[dict[str, Any]] | None = None,
    auditor: list[dict[str, Any]] | None = None,
    compensation: list[dict[str, Any]] | None = None,
    subsidiary: list[dict[str, Any]] | None = None,
    dilution: list[dict[str, Any]] | None = None,
    red_flags: list[dict[str, Any]] | None = None,
    general: list[dict[str, Any]] | None = None,
) -> GovernanceAnalysisOutput:
    data: dict[str, Any] = {
        "new_management_statements": new_statements or [],
        "statement_updates": statement_updates or [],
        "capital_allocation_findings": capital_allocation or [],
        "related_party_findings": related_party or [],
        "auditor_findings": auditor or [],
        "compensation_findings": compensation or [],
        "subsidiary_findings": subsidiary or [],
        "dilution_findings": dilution or [],
        "governance_red_flags": red_flags or [],
        "general_findings": general or [],
    }
    return GovernanceAnalysisOutput.model_validate(data)


def _validate(
    analysis: GovernanceAnalysisOutput | None = None,
    *,
    shareholding_findings: list[GeneratedFinding] | None = None,
    evidence: list[ExtractedEvidence] | None = None,
    evidence_ids: list[uuid.UUID] | None = None,
    existing_statements: list[ManagementStatementSummary] | None = None,
    observation_date: date = OBSERVATION_DATE,
    shareholding_snapshots: list[ShareholdingSnapshot] | None = None,
) -> GovernanceValidationResult:
    if analysis is None:
        analysis = _analysis()
    if evidence is None:
        evidence = []
    if evidence_ids is None:
        evidence_ids = [uuid.uuid4() for _ in evidence]
    return _validate_governance_output(
        analysis,
        shareholding_findings or [],
        evidence,
        evidence_ids,
        existing_statements or [],
        observation_date,
        shareholding_snapshots=shareholding_snapshots,
    )


def _stmt(
    sid: uuid.UUID = STMT_UUID_1,
    status: ManagementStatementStatus = ManagementStatementStatus.PENDING,
    category: ManagementStatementCategory = ManagementStatementCategory.REVENUE_GUIDANCE,
) -> ManagementStatementSummary:
    return ManagementStatementSummary(
        id=sid,
        statement_date=date(2025, 4, 15),
        statement="Revenue growth 20% by FY26",
        category=category,
        status=status,
    )


def _snapshot(
    *,
    as_of_date: date = date(2025, 6, 30),
    quarter: str = "Q1 FY26",
    promoter: str = "55.00",
    fii: str = "20.00",
    dii: str = "15.00",
    public: str = "10.00",
    pledged: str | None = "5.00",
) -> ShareholdingSnapshot:
    return ShareholdingSnapshot(
        as_of_date=as_of_date,
        quarter=quarter,
        promoter_holding_pct=Decimal(promoter),
        fii_holding_pct=Decimal(fii),
        dii_holding_pct=Decimal(dii),
        public_holding_pct=Decimal(public),
        total_shares=100_000_000,
        pledged_percentage=Decimal(pledged) if pledged is not None else None,
        source_provider="shareholding",
        source_tier=1,
    )


def _issue_types(result: GovernanceValidationResult) -> list[str]:
    return [i.issue_type for i in result.issues]


def _issue_actions(result: GovernanceValidationResult, issue_type: str) -> list[str]:
    return [i.action for i in result.issues if i.issue_type == issue_type]


# ===========================================================================
# MSV-01 through MSV-08: ManagementStatement Validation
# ===========================================================================


class TestMSV01TerminalTransitionRequiresEvidence:
    """MSV-01: PENDING → MET/PARTIALLY_MET/MISSED requires outcome_evidence_index."""

    def test_met_without_evidence_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "Target met",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "missing_outcome_evidence" in _issue_types(r)

    def test_partially_met_without_evidence_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "PARTIALLY_MET",
                    "actual_outcome": "Partial",
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "Partial achievement",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "missing_outcome_evidence" in _issue_types(r)

    def test_missed_without_evidence_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Not achieved",
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "Target missed",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "missing_outcome_evidence" in _issue_types(r)

    def test_met_with_valid_evidence_passes(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Confirmed",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1
        assert r.statement_updates_rejected == 0


class TestMSV02EvidenceIndexValidity:
    """MSV-02: outcome_evidence_index references a valid evidence item."""

    def test_out_of_range_evidence_index_rejected(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": 99,
                    "resolution_detail": None,
                    "justification": "Bad index",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "invalid_evidence_index" in _issue_types(r)

    def test_negative_evidence_index_accepted_by_validation(self) -> None:
        """Negative index -1 < len(evidence) so passes the >= check;
        this is a known contract boundary — Pydantic allows negative ints."""
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": -1,
                    "resolution_detail": None,
                    "justification": "Negative index",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert "invalid_evidence_index" not in _issue_types(r)

    def test_exact_boundary_evidence_index_rejected(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": 1,
                    "resolution_detail": None,
                    "justification": "At boundary",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "invalid_evidence_index" in _issue_types(r)

    def test_last_valid_index_passes(self) -> None:
        ev = [_evidence(), _evidence(claim="Second")]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": 1,
                    "resolution_detail": None,
                    "justification": "Last valid",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1


class TestMSV03StatementIdValidity:
    """MSV-03: statement_id references existing ManagementStatement."""

    def test_unknown_statement_id_rejected(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(uuid.uuid4()),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Unknown ID",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "invalid_statement_id" in _issue_types(r)

    def test_known_statement_id_passes(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Known ID",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1


class TestMSV04TerminalReTransition:
    """MSV-04: No re-transition from terminal states (MET, PARTIALLY_MET, MISSED)."""

    @pytest.mark.parametrize(
        "current",
        [
            ManagementStatementStatus.MET,
            ManagementStatementStatus.PARTIALLY_MET,
            ManagementStatementStatus.MISSED,
        ],
    )
    def test_re_transition_from_terminal_rejected(
        self,
        current: ManagementStatementStatus,
    ) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Changed",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Re-transition",
                }
            ],
        )
        r = _validate(
            a,
            evidence=ev,
            existing_statements=[_stmt(status=current)],
        )
        assert r.statement_updates_rejected == 1
        assert "terminal_re_transition" in _issue_types(r)

    def test_transition_from_pending_allowed(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "From PENDING",
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1

    def test_transition_from_unknown_allowed(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Resolved",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "From UNKNOWN",
                }
            ],
        )
        r = _validate(
            a,
            evidence=ev,
            existing_statements=[_stmt(status=ManagementStatementStatus.UNKNOWN)],
        )
        assert r.statement_updates_valid == 1


class TestMSV05UnknownRequiresResolutionDetail:
    """MSV-05: PENDING → UNKNOWN requires non-empty resolution_detail."""

    def test_unknown_without_resolution_detail_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "UNKNOWN",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "No detail",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "missing_resolution_detail" in _issue_types(r)

    def test_unknown_with_resolution_detail_passes(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "UNKNOWN",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": "INSUFFICIENT_EVIDENCE",
                    "justification": "Cannot determine",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1

    def test_unknown_with_empty_string_resolution_detail_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "UNKNOWN",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": "",
                    "justification": "Empty detail",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "missing_resolution_detail" in _issue_types(r)


class TestMSV06NewStatementCategory:
    """MSV-06: New statement category is valid ManagementStatementCategory."""

    def test_invalid_category_rejected(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            new_statements=[
                {
                    "statement": "We will grow",
                    "statement_date": "2025-09-30",
                    "category": "INVALID_CATEGORY",
                    "expected_outcome": "Growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.new_statements_rejected == 1

    def test_valid_category_passes(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            new_statements=[
                {
                    "statement": "Revenue target 20%",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "20% revenue growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.new_statements_valid == 1
        assert r.new_statements_rejected == 0


class TestMSV07NewStatementEvidenceIndex:
    """MSV-07: New statement evidence_index references valid evidence item."""

    def test_out_of_range_rejected(self) -> None:
        a = _analysis(
            new_statements=[
                {
                    "statement": "We plan growth",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "Growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 5,
                }
            ],
        )
        r = _validate(a, evidence=[])
        assert r.new_statements_rejected == 1

    def test_valid_index_passes(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            new_statements=[
                {
                    "statement": "15% margin target",
                    "statement_date": "2025-09-30",
                    "category": "MARGIN_GUIDANCE",
                    "expected_outcome": "15% margin",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.new_statements_valid == 1


class TestMSV08NewStatementNonEmpty:
    """MSV-08: New statement text is non-empty."""

    def test_empty_statement_rejected(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            new_statements=[
                {
                    "statement": "   ",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "Growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.new_statements_rejected == 1
        issues = _issue_types(r)
        assert "empty_statement" in issues


class TestMSVNotDueTransition:
    """NOT_DUE substate: must not propose a status transition."""

    def test_not_due_with_transition_rejected(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": None,
                    "outcome_evidence_index": 0,
                    "resolution_detail": "NOT_DUE",
                    "justification": "Marking met despite not due",
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "not_due_with_transition" in _issue_types(r)

    def test_not_due_without_transition_accepted(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "PENDING",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": "NOT_DUE",
                    "justification": "Timeframe not elapsed",
                }
            ],
        )
        r = _validate(a, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1

    def test_not_due_unknown_to_unknown_accepted(self) -> None:
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "UNKNOWN",
                    "actual_outcome": None,
                    "outcome_evidence_index": None,
                    "resolution_detail": "NOT_DUE",
                    "justification": "Not due yet",
                }
            ],
        )
        r = _validate(
            a,
            existing_statements=[_stmt(status=ManagementStatementStatus.UNKNOWN)],
        )
        assert r.statement_updates_valid == 1


class TestMSVRevisedCorrespondence:
    """REVISED substate: requires at least one NewManagementStatement."""

    def test_revised_without_replacement_rejected(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Revised target",
                    "outcome_evidence_index": 0,
                    "resolution_detail": "REVISED",
                    "justification": "Management revised guidance",
                }
            ],
            new_statements=[],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_rejected == 1
        assert "revised_without_replacement" in _issue_types(r)

    def test_revised_with_replacement_accepted(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Revised: old target superseded",
                    "outcome_evidence_index": 0,
                    "resolution_detail": "REVISED",
                    "justification": "Management revised downward",
                }
            ],
            new_statements=[
                {
                    "statement": "Revised growth target 15%",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "15% growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1

    def test_revised_existence_check_is_global(self) -> None:
        """The check only verifies any new statement exists, not 1:1 match."""
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MISSED",
                    "actual_outcome": "Revised",
                    "outcome_evidence_index": 0,
                    "resolution_detail": "REVISED",
                    "justification": "Revised",
                }
            ],
            new_statements=[
                {
                    "statement": "Unrelated new statement",
                    "statement_date": "2025-09-30",
                    "category": "CAPEX_GUIDANCE",
                    "expected_outcome": "Something else",
                    "expected_timeframe": "FY27",
                    "evidence_index": 0,
                }
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=[_stmt()])
        assert r.statement_updates_valid == 1


class TestMSVMultipleUpdates:
    """Multiple statement updates: valid and invalid do not interfere."""

    def test_mixed_valid_and_invalid_counted_separately(self) -> None:
        ev = [_evidence()]
        stmts = [
            _stmt(sid=STMT_UUID_1),
            _stmt(sid=STMT_UUID_2),
        ]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(STMT_UUID_1),
                    "proposed_status": "MET",
                    "actual_outcome": "Achieved",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Valid update",
                },
                {
                    "statement_id": str(STMT_UUID_2),
                    "proposed_status": "MET",
                    "actual_outcome": "Also achieved",
                    "outcome_evidence_index": None,
                    "resolution_detail": None,
                    "justification": "Missing evidence",
                },
            ],
        )
        r = _validate(a, evidence=ev, existing_statements=stmts)
        assert r.statement_updates_valid == 1
        assert r.statement_updates_rejected == 1


# ===========================================================================
# FV-01 through FV-07: Finding Validation
# ===========================================================================


class TestFV01FindingTypeValid:
    """FV-01: finding_type is a valid FindingType (enforced by Pydantic)."""

    def test_valid_finding_type_passes(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "FACT",
                    "category": "capital_allocation",
                    "content": "Valid fact finding",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.rejected_count == 0

    def test_invalid_finding_type_rejected_by_pydantic(self) -> None:
        """Pydantic rejects invalid FindingType at schema level."""
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            _analysis(
                capital_allocation=[
                    {
                        "finding_type": "INVALID_TYPE",
                        "category": "capital_allocation",
                        "content": "Bad type",
                        "confidence": "HIGH",
                        "source_publication_date": None,
                        "evidence_indices": [0],
                    }
                ],
            )


class TestFV02FindingCategory:
    """FV-02: category is in GOVERNANCE_FINDING_CATEGORIES."""

    def test_invalid_category_rejected(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "not_a_real_category",
                    "content": "Invalid category",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.rejected_count >= 1
        assert "invalid_category" in _issue_types(r)

    def test_all_valid_categories_accepted(self) -> None:
        from app.agents.contracts import GOVERNANCE_FINDING_CATEGORIES

        for cat in GOVERNANCE_FINDING_CATEGORIES:
            a = _analysis(
                capital_allocation=[
                    {
                        "finding_type": "AI_INFERENCE",
                        "category": cat,
                        "content": f"Finding in {cat}",
                        "confidence": "MEDIUM",
                        "source_publication_date": None,
                        "evidence_indices": [0],
                    }
                ],
            )
            ev = [_evidence()]
            r = _validate(a, evidence=ev)
            assert "invalid_category" not in _issue_types(r), f"Category {cat} rejected"


class TestFV03FactWithoutEvidence:
    """FV-03: FACT findings have at least one evidence index."""

    def test_fact_without_evidence_warns(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "FACT",
                    "category": "capital_allocation",
                    "content": "Fact without evidence",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        r = _validate(a)
        assert "fact_without_evidence" in _issue_types(r)
        assert _issue_actions(r, "fact_without_evidence") == ["warning"]

    def test_fact_with_empty_list_warns(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "FACT",
                    "category": "capital_allocation",
                    "content": "Fact empty list",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [],
                }
            ],
        )
        r = _validate(a)
        assert "fact_without_evidence" in _issue_types(r)

    def test_fact_with_evidence_no_warning(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "FACT",
                    "category": "capital_allocation",
                    "content": "Fact with evidence",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "fact_without_evidence" not in _issue_types(r)


class TestFV04ManagementClaimWithoutEvidence:
    """FV-04: MANAGEMENT_CLAIM findings have at least one evidence index."""

    def test_management_claim_without_evidence_warns(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "capital_allocation",
                    "content": "Management claims 25% ROCE",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        r = _validate(a)
        assert "management_claim_without_citation" in _issue_types(r)
        assert _issue_actions(r, "management_claim_without_citation") == ["warning"]

    def test_management_claim_with_evidence_no_warning(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "MANAGEMENT_CLAIM",
                    "category": "capital_allocation",
                    "content": "ROCE target 25%",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        r = _validate(a, evidence=ev)
        assert "management_claim_without_citation" not in _issue_types(r)


class TestFV05CalculationWithoutEvidence:
    """FV-05: CALCULATION findings have at least one evidence index."""

    def test_calculation_without_evidence_warns(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "CALCULATION",
                    "category": "capital_allocation",
                    "content": "Dividend payout ratio 35%",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        r = _validate(a)
        assert "calculation_without_evidence" in _issue_types(r)
        assert _issue_actions(r, "calculation_without_evidence") == ["warning"]

    def test_calculation_with_evidence_no_warning(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "CALCULATION",
                    "category": "capital_allocation",
                    "content": "Payout ratio 35%",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "calculation_without_evidence" not in _issue_types(r)


class TestFV06AIInferenceRedFlagEvidence:
    """FV-06: AI_INFERENCE for red flags has evidence indices."""

    def test_ai_inference_red_flag_without_evidence_rejected(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "governance_red_flag",
                    "content": "Potential governance concern inferred",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        r = _validate(a)
        assert r.rejected_count >= 1
        assert "ai_inference_red_flag_without_evidence" in _issue_types(r)

    def test_ai_inference_red_flag_with_evidence_passes(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "governance_red_flag",
                    "content": "Governance concern with evidence",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "ai_inference_red_flag_without_evidence" not in _issue_types(r)

    def test_ai_inference_non_red_flag_no_evidence_not_rejected(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "General inference",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": None,
                }
            ],
        )
        r = _validate(a)
        assert "ai_inference_red_flag_without_evidence" not in _issue_types(r)
        assert r.rejected_count == 0


class TestFV07AnalystOpinionNotAllowed:
    """FV-07: ANALYST_OPINION is not applicable to this agent."""

    def test_analyst_opinion_rejected(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "ANALYST_OPINION",
                    "category": "capital_allocation",
                    "content": "Analyst thinks stock is undervalued",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.rejected_count >= 1
        assert "analyst_opinion_not_allowed" in _issue_types(r)

    def test_other_finding_types_accepted(self) -> None:
        for ft in ["FACT", "AI_INFERENCE", "ASSUMPTION", "UNCERTAINTY"]:
            a = _analysis(
                capital_allocation=[
                    {
                        "finding_type": ft,
                        "category": "capital_allocation",
                        "content": f"{ft} finding content",
                        "confidence": "MEDIUM",
                        "source_publication_date": None,
                        "evidence_indices": [0],
                    }
                ],
            )
            ev = [_evidence()]
            r = _validate(a, evidence=ev)
            assert "analyst_opinion_not_allowed" not in _issue_types(r), f"FindingType {ft} incorrectly rejected"


class TestFindingTemporalValidation:
    """Temporal rule: source_publication_date must not exceed observation_date."""

    def test_future_publication_date_warns(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Future dated finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": "2025-12-31",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "temporal_violation" in _issue_types(r)
        assert _issue_actions(r, "temporal_violation") == ["warning"]

    def test_past_publication_date_no_warning(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Past dated finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": "2025-06-30",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "temporal_violation" not in _issue_types(r)

    def test_same_date_no_warning(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Same date finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": str(OBSERVATION_DATE),
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert "temporal_violation" not in _issue_types(r)


class TestFindingEmptyContent:
    """Finding with empty content is rejected."""

    def test_whitespace_content_rejected(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "   ",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.rejected_count >= 1
        assert "empty_content" in _issue_types(r)


# ===========================================================================
# RF-01 through RF-05: Red Flag Validation
# ===========================================================================


class TestRF01RedFlagCategory:
    """RF-01: category is in GOVERNANCE_RED_FLAG_CATEGORIES."""

    def test_invalid_category_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "not_a_category",
                    "description": "Bad flag",
                    "severity": "HIGH",
                    "justification": "Because",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "invalid_category" in _issue_types(r)

    def test_valid_category_accepted(self) -> None:
        from app.agents.contracts import GOVERNANCE_RED_FLAG_CATEGORIES

        for cat in GOVERNANCE_RED_FLAG_CATEGORIES:
            a = _analysis(
                red_flags=[
                    {
                        "category": cat,
                        "description": f"Red flag for {cat}",
                        "severity": "MEDIUM",
                        "justification": f"Justified for {cat}",
                        "evidence_indices": [0],
                    }
                ],
            )
            ev = [_evidence()]
            r = _validate(a, evidence=ev)
            cat_issues = [i for i in r.issues if i.issue_type == "invalid_category" and i.domain == "red_flag"]
            assert len(cat_issues) == 0, f"Category {cat} rejected"


class TestRF02RedFlagSeverity:
    """RF-02: severity is HIGH, MEDIUM, or LOW."""

    @pytest.mark.parametrize("severity", ["HIGH", "MEDIUM", "LOW"])
    def test_valid_severity_accepted(self, severity: str) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": severity,
                    "justification": "Justified",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1

    def test_invalid_severity_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "CRITICAL",
                    "justification": "Justified",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "invalid_severity" in _issue_types(r)

    def test_lowercase_severity_accepted(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "high",
                    "justification": "Justified",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1


class TestRF03RedFlagEvidence:
    """RF-03: evidence_indices is non-empty."""

    def test_empty_evidence_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [],
                }
            ],
        )
        r = _validate(a)
        assert r.red_flags_rejected == 1
        assert "missing_evidence" in _issue_types(r)

    def test_non_empty_evidence_passes(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1


class TestRF04RedFlagJustification:
    """RF-04: justification is non-empty."""

    def test_empty_justification_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "empty_justification" in _issue_types(r)

    def test_whitespace_justification_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "   \t  ",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "empty_justification" in _issue_types(r)

    def test_valid_justification_passes(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Pledged shares increased from 5% to 15%",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1


class TestRF05RedFlagEvidenceIndexValidity:
    """RF-05: All referenced evidence indices are valid."""

    def test_out_of_range_index_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [99],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "invalid_evidence_index" in _issue_types(r)

    def test_negative_index_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [-1],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1
        assert "invalid_evidence_index" in _issue_types(r)

    def test_valid_indices_pass(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [0, 1],
                }
            ],
        )
        ev = [_evidence(), _evidence(claim="Second")]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1

    def test_mixed_valid_and_invalid_rejected(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Flag",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [0, 50],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_rejected == 1


class TestRedFlagMultipleErrors:
    """Multiple red flag validation errors accumulate correctly."""

    def test_multiple_red_flags_counted_independently(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Valid",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [0],
                },
                {
                    "category": "not_a_category",
                    "description": "Invalid",
                    "severity": "HIGH",
                    "justification": "Justified",
                    "evidence_indices": [0],
                },
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1
        assert r.red_flags_rejected == 1


# ===========================================================================
# SV-01 through SV-04: Shareholding Validation
# ===========================================================================


class TestSV01ShareholdingSum:
    """SV-01: promoter + FII + DII + public ≈ 100% (±0.5%)."""

    def test_sum_within_tolerance_no_warning(self) -> None:
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(promoter="55.00", fii="20.00", dii="15.00", public="10.00")
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" not in _issue_types(r)

    def test_sum_above_tolerance_warns(self) -> None:
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(promoter="50.00", fii="20.00", dii="15.00", public="10.00")
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" in _issue_types(r)
        assert _issue_actions(r, "sum_mismatch") == ["warning"]

    def test_sum_at_exact_boundary_no_warning(self) -> None:
        """100.5% exactly: diff == 0.5, not > 0.5, so no warning."""
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(
            promoter="55.50",
            fii="20.00",
            dii="15.00",
            public="10.00",
        )
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" not in _issue_types(r)

    def test_sum_just_above_boundary_warns(self) -> None:
        """100.51%: diff == 0.51 > 0.5, so warning."""
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(
            promoter="55.51",
            fii="20.00",
            dii="15.00",
            public="10.00",
        )
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" in _issue_types(r)

    def test_sum_below_boundary_warns(self) -> None:
        """99.49%: diff == 0.51 > 0.5, so warning."""
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(
            promoter="54.49",
            fii="20.00",
            dii="15.00",
            public="10.00",
        )
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" in _issue_types(r)

    def test_sum_exactly_100_no_warning(self) -> None:
        from app.agents.management_governance.agent import (
            _generate_shareholding_findings,
        )

        snap = _snapshot(
            promoter="50.00",
            fii="25.00",
            dii="15.00",
            public="10.00",
        )
        findings = _generate_shareholding_findings([snap], OBSERVATION_DATE)
        r = _validate(shareholding_findings=findings)
        assert "sum_mismatch" not in _issue_types(r)


class TestSV02NegativePercentages:
    """SV-02: All percentages are non-negative."""

    def test_negative_promoter_rejected(self) -> None:
        snap = _snapshot(promoter="-5.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" in _issue_types(r)
        assert _issue_actions(r, "negative_percentage") == ["rejected"]

    def test_negative_fii_rejected(self) -> None:
        snap = _snapshot(fii="-1.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" in _issue_types(r)

    def test_negative_dii_rejected(self) -> None:
        snap = _snapshot(dii="-2.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" in _issue_types(r)

    def test_negative_public_rejected(self) -> None:
        snap = _snapshot(public="-3.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" in _issue_types(r)

    def test_zero_percentages_accepted(self) -> None:
        snap = _snapshot(promoter="0.00", fii="0.00", dii="0.00", public="0.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" not in _issue_types(r)

    def test_positive_percentages_accepted(self) -> None:
        snap = _snapshot()
        r = _validate(shareholding_snapshots=[snap])
        assert "negative_percentage" not in _issue_types(r)


class TestSV03PledgePercentage:
    """SV-03: pledge_pct ≤ 100%."""

    def test_pledge_above_100_rejected(self) -> None:
        snap = _snapshot(pledged="101.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "pledge_exceeds_100" in _issue_types(r)
        assert _issue_actions(r, "pledge_exceeds_100") == ["rejected"]

    def test_pledge_at_100_accepted(self) -> None:
        snap = _snapshot(pledged="100.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "pledge_exceeds_100" not in _issue_types(r)

    def test_pledge_below_100_accepted(self) -> None:
        snap = _snapshot(pledged="50.00")
        r = _validate(shareholding_snapshots=[snap])
        assert "pledge_exceeds_100" not in _issue_types(r)

    def test_pledge_none_accepted(self) -> None:
        snap = _snapshot(pledged=None)
        r = _validate(shareholding_snapshots=[snap])
        assert "pledge_exceeds_100" not in _issue_types(r)


class TestSV04SnapshotDate:
    """SV-04: as_of_date ≤ observation_date."""

    def test_future_snapshot_rejected(self) -> None:
        snap = _snapshot(as_of_date=date(2025, 12, 31))
        r = _validate(shareholding_snapshots=[snap])
        assert "future_snapshot" in _issue_types(r)
        assert _issue_actions(r, "future_snapshot") == ["rejected"]

    def test_same_date_accepted(self) -> None:
        snap = _snapshot(as_of_date=OBSERVATION_DATE)
        r = _validate(shareholding_snapshots=[snap])
        assert "future_snapshot" not in _issue_types(r)

    def test_past_date_accepted(self) -> None:
        snap = _snapshot(as_of_date=date(2025, 3, 31))
        r = _validate(shareholding_snapshots=[snap])
        assert "future_snapshot" not in _issue_types(r)


# ===========================================================================
# Cross-domain validation
# ===========================================================================


class TestCrossDomainValidation:
    """Cross-domain interactions between validation rules."""

    def test_valid_red_flag_with_valid_evidence_passes(self) -> None:
        a = _analysis(
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Pledge rising",
                    "severity": "MEDIUM",
                    "justification": "Pledged shares increased",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.red_flags_valid == 1
        assert r.rejected_count == 0

    def test_finding_rejection_does_not_affect_red_flags(self) -> None:
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "not_valid",
                    "content": "Bad finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
            red_flags=[
                {
                    "category": "promoter_pledge_elevation",
                    "description": "Good flag",
                    "severity": "HIGH",
                    "justification": "Validated",
                    "evidence_indices": [0],
                }
            ],
        )
        ev = [_evidence()]
        r = _validate(a, evidence=ev)
        assert r.rejected_count >= 1
        assert r.red_flags_valid == 1

    def test_statement_rejection_does_not_affect_findings(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            statement_updates=[
                {
                    "statement_id": str(uuid.uuid4()),
                    "proposed_status": "MET",
                    "actual_outcome": "Done",
                    "outcome_evidence_index": 0,
                    "resolution_detail": None,
                    "justification": "Invalid statement",
                }
            ],
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Valid finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.statement_updates_rejected == 1
        assert r.valid_count >= 1

    def test_empty_analysis_produces_no_issues(self) -> None:
        a = _analysis()
        r = _validate(a)
        assert r.rejected_count == 0
        assert len(r.issues) == 0


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Empty inputs, boundary values, and malformed data."""

    def test_no_statements_no_findings_no_red_flags(self) -> None:
        a = GovernanceAnalysisOutput.model_validate(
            {
                "new_management_statements": [],
                "statement_updates": [],
                "capital_allocation_findings": [],
                "related_party_findings": [],
                "auditor_findings": [],
                "compensation_findings": [],
                "subsidiary_findings": [],
                "dilution_findings": [],
                "governance_red_flags": [],
                "general_findings": [],
            }
        )
        r = _validate(a)
        assert r.total_findings == 0
        assert r.valid_count == 0
        assert r.rejected_count == 0
        assert r.statement_updates_valid == 0
        assert r.statement_updates_rejected == 0
        assert r.new_statements_valid == 0
        assert r.new_statements_rejected == 0
        assert r.red_flags_valid == 0
        assert r.red_flags_rejected == 0
        assert len(r.issues) == 0

    def test_findings_across_multiple_domains(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Cap alloc finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
            related_party=[
                {
                    "finding_type": "FACT",
                    "category": "related_party_transaction",
                    "content": "RPT finding",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
            auditor=[
                {
                    "finding_type": "FACT",
                    "category": "auditor_qualification",
                    "content": "Auditor finding",
                    "confidence": "HIGH",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                }
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.total_findings == 3
        assert r.valid_count == 3
        assert r.rejected_count == 0

    def test_multiple_new_statements_mixed_validity(self) -> None:
        ev = [_evidence(evidence_type=EvidenceType.MANAGEMENT_STATEMENT)]
        a = _analysis(
            new_statements=[
                {
                    "statement": "Valid statement",
                    "statement_date": "2025-09-30",
                    "category": "REVENUE_GUIDANCE",
                    "expected_outcome": "Growth",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                },
                {
                    "statement": "Bad category",
                    "statement_date": "2025-09-30",
                    "category": "INVALID_CAT",
                    "expected_outcome": "Bad",
                    "expected_timeframe": "FY26",
                    "evidence_index": 0,
                },
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.new_statements_valid == 1
        assert r.new_statements_rejected == 1

    def test_multiple_shareholding_snapshots_independently_validated(self) -> None:
        snaps = [
            _snapshot(quarter="Q1", as_of_date=date(2025, 3, 31)),
            _snapshot(quarter="Q2", as_of_date=date(2025, 12, 31)),
        ]
        r = _validate(shareholding_snapshots=snaps)
        assert "future_snapshot" in _issue_types(r)
        future_issues = [i for i in r.issues if i.issue_type == "future_snapshot"]
        assert len(future_issues) == 1

    def test_validation_result_counts_are_consistent(self) -> None:
        ev = [_evidence()]
        a = _analysis(
            capital_allocation=[
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "capital_allocation",
                    "content": "Valid finding",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
                {
                    "finding_type": "AI_INFERENCE",
                    "category": "invalid_cat",
                    "content": "Bad category",
                    "confidence": "MEDIUM",
                    "source_publication_date": None,
                    "evidence_indices": [0],
                },
            ],
        )
        r = _validate(a, evidence=ev)
        assert r.total_findings == 2
        assert r.valid_count + r.rejected_count == r.total_findings
