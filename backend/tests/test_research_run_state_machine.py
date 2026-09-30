"""Tier 1: State machine unit tests for research run lifecycle entities.

Tests valid transitions, invalid transitions, terminal state enforcement,
and enum coverage for all three state machines.
"""
from __future__ import annotations

import pytest

from app.exceptions import ValidationError
from app.models.enums import AgentExecutionStatus, ResearchRunStatus, StepStatus
from app.models.state_machines import (
    TERMINAL_EXECUTION_STATUSES,
    TERMINAL_RUN_STATUSES,
    VALID_EXECUTION_TRANSITIONS,
    VALID_RUN_TRANSITIONS,
    VALID_STEP_TRANSITIONS,
    validate_execution_transition,
    validate_run_transition,
    validate_step_transition,
)

# ---------------------------------------------------------------------------
# ResearchRun state machine (AC-1, AC-2, AC-3)
# ---------------------------------------------------------------------------


class TestResearchRunStateMachine:
    def test_all_statuses_have_transition_rules(self) -> None:
        for status in ResearchRunStatus:
            assert status.value in VALID_RUN_TRANSITIONS, (
                f"Missing transition rule for {status.value}"
            )

    def test_exactly_seven_statuses(self) -> None:
        assert len(ResearchRunStatus) == 7
        expected = {
            "CREATED", "QUEUED", "RUNNING",
            "COMPLETED", "FAILED", "PARTIAL", "CANCELLED",
        }
        assert {s.value for s in ResearchRunStatus} == expected

    def test_no_incomplete_status(self) -> None:
        values = {s.value for s in ResearchRunStatus}
        assert "INCOMPLETE" not in values

    def test_created_to_queued(self) -> None:
        validate_run_transition("CREATED", "QUEUED")

    def test_queued_to_running(self) -> None:
        validate_run_transition("QUEUED", "RUNNING")

    def test_running_to_completed(self) -> None:
        validate_run_transition("RUNNING", "COMPLETED")

    def test_running_to_failed(self) -> None:
        validate_run_transition("RUNNING", "FAILED")

    def test_running_to_partial(self) -> None:
        validate_run_transition("RUNNING", "PARTIAL")

    def test_running_to_cancelled(self) -> None:
        validate_run_transition("RUNNING", "CANCELLED")

    def test_queued_to_cancelled(self) -> None:
        validate_run_transition("QUEUED", "CANCELLED")

    @pytest.mark.parametrize("status", [
        "COMPLETED", "FAILED", "PARTIAL", "CANCELLED",
    ])
    def test_terminal_states_have_no_transitions(self, status: str) -> None:
        assert VALID_RUN_TRANSITIONS[status] == frozenset()

    @pytest.mark.parametrize("status", [
        "COMPLETED", "FAILED", "PARTIAL", "CANCELLED",
    ])
    def test_terminal_states_in_terminal_set(self, status: str) -> None:
        assert status in TERMINAL_RUN_STATUSES

    def test_created_not_terminal(self) -> None:
        assert "CREATED" not in TERMINAL_RUN_STATUSES

    @pytest.mark.parametrize("current,target", [
        ("CREATED", "RUNNING"),
        ("CREATED", "COMPLETED"),
        ("QUEUED", "COMPLETED"),
        ("QUEUED", "FAILED"),
        ("COMPLETED", "RUNNING"),
        ("FAILED", "RUNNING"),
        ("PARTIAL", "COMPLETED"),
        ("CANCELLED", "RUNNING"),
    ])
    def test_invalid_transitions_raise(self, current: str, target: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_run_transition(current, target)
        assert "Invalid run transition" in exc_info.value.message

    def test_unknown_status_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_run_transition("BOGUS", "RUNNING")
        assert "Unknown run status" in exc_info.value.message


# ---------------------------------------------------------------------------
# StepStatus state machine
# ---------------------------------------------------------------------------


class TestStepStateMachine:
    def test_all_statuses_have_transition_rules(self) -> None:
        for status in StepStatus:
            assert status.value in VALID_STEP_TRANSITIONS, (
                f"Missing transition rule for {status.value}"
            )

    def test_pending_to_running(self) -> None:
        validate_step_transition("PENDING", "RUNNING")

    def test_pending_to_skipped(self) -> None:
        validate_step_transition("PENDING", "SKIPPED")

    def test_running_to_completed(self) -> None:
        validate_step_transition("RUNNING", "COMPLETED")

    def test_running_to_failed(self) -> None:
        validate_step_transition("RUNNING", "FAILED")

    def test_failed_to_running_allows_retry(self) -> None:
        validate_step_transition("FAILED", "RUNNING")

    def test_completed_is_terminal(self) -> None:
        assert VALID_STEP_TRANSITIONS["COMPLETED"] == frozenset()

    def test_skipped_is_terminal(self) -> None:
        assert VALID_STEP_TRANSITIONS["SKIPPED"] == frozenset()

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_step_transition("COMPLETED", "RUNNING")


# ---------------------------------------------------------------------------
# AgentExecution state machine (AC-4)
# ---------------------------------------------------------------------------


class TestAgentExecutionStateMachine:
    def test_all_statuses_have_transition_rules(self) -> None:
        for status in AgentExecutionStatus:
            assert status.value in VALID_EXECUTION_TRANSITIONS, (
                f"Missing transition rule for {status.value}"
            )

    def test_running_to_completed(self) -> None:
        validate_execution_transition("RUNNING", "COMPLETED")

    def test_running_to_failed(self) -> None:
        validate_execution_transition("RUNNING", "FAILED")

    def test_running_to_timeout(self) -> None:
        validate_execution_transition("RUNNING", "TIMEOUT")

    def test_running_to_truncated(self) -> None:
        validate_execution_transition("RUNNING", "TRUNCATED")

    @pytest.mark.parametrize("status", [
        "COMPLETED", "FAILED", "TIMEOUT", "TRUNCATED",
    ])
    def test_terminal_states_have_no_transitions(self, status: str) -> None:
        assert VALID_EXECUTION_TRANSITIONS[status] == frozenset()

    @pytest.mark.parametrize("status", [
        "COMPLETED", "FAILED", "TIMEOUT", "TRUNCATED",
    ])
    def test_terminal_states_in_terminal_set(self, status: str) -> None:
        assert status in TERMINAL_EXECUTION_STATUSES

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(ValidationError):
            validate_execution_transition("COMPLETED", "RUNNING")
