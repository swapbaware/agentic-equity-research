"""State machine transition rules for research run lifecycle entities."""
from __future__ import annotations

from app.exceptions import ValidationError
from app.models.enums import AgentExecutionStatus, ResearchRunStatus, StepStatus

VALID_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    ResearchRunStatus.CREATED: frozenset({ResearchRunStatus.QUEUED}),
    ResearchRunStatus.QUEUED: frozenset({
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.CANCELLED,
    }),
    ResearchRunStatus.RUNNING: frozenset({
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.CANCELLED,
    }),
    ResearchRunStatus.COMPLETED: frozenset(),
    ResearchRunStatus.FAILED: frozenset(),
    ResearchRunStatus.PARTIAL: frozenset(),
    ResearchRunStatus.CANCELLED: frozenset(),
}

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({
    ResearchRunStatus.COMPLETED,
    ResearchRunStatus.FAILED,
    ResearchRunStatus.PARTIAL,
    ResearchRunStatus.CANCELLED,
})

VALID_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.SKIPPED}),
    StepStatus.RUNNING: frozenset({StepStatus.COMPLETED, StepStatus.FAILED}),
    StepStatus.COMPLETED: frozenset(),
    StepStatus.FAILED: frozenset({StepStatus.RUNNING}),
    StepStatus.SKIPPED: frozenset(),
}

VALID_EXECUTION_TRANSITIONS: dict[str, frozenset[str]] = {
    AgentExecutionStatus.RUNNING: frozenset({
        AgentExecutionStatus.COMPLETED,
        AgentExecutionStatus.FAILED,
        AgentExecutionStatus.TIMEOUT,
        AgentExecutionStatus.TRUNCATED,
    }),
    AgentExecutionStatus.COMPLETED: frozenset(),
    AgentExecutionStatus.FAILED: frozenset(),
    AgentExecutionStatus.TIMEOUT: frozenset(),
    AgentExecutionStatus.TRUNCATED: frozenset(),
}

TERMINAL_EXECUTION_STATUSES: frozenset[str] = frozenset({
    AgentExecutionStatus.COMPLETED,
    AgentExecutionStatus.FAILED,
    AgentExecutionStatus.TIMEOUT,
    AgentExecutionStatus.TRUNCATED,
})


def validate_run_transition(current: str, target: str) -> None:
    allowed = VALID_RUN_TRANSITIONS.get(current)
    if allowed is None:
        raise ValidationError(
            message=f"Unknown run status: {current}",
            details={"current_status": current, "target_status": target},
        )
    if target not in allowed:
        raise ValidationError(
            message=f"Invalid run transition: {current} → {target}",
            details={
                "current_status": current,
                "target_status": target,
                "allowed_transitions": sorted(allowed),
            },
        )


def validate_step_transition(current: str, target: str) -> None:
    allowed = VALID_STEP_TRANSITIONS.get(current)
    if allowed is None:
        raise ValidationError(
            message=f"Unknown step status: {current}",
            details={"current_status": current, "target_status": target},
        )
    if target not in allowed:
        raise ValidationError(
            message=f"Invalid step transition: {current} → {target}",
            details={
                "current_status": current,
                "target_status": target,
                "allowed_transitions": sorted(allowed),
            },
        )


def validate_execution_transition(current: str, target: str) -> None:
    allowed = VALID_EXECUTION_TRANSITIONS.get(current)
    if allowed is None:
        raise ValidationError(
            message=f"Unknown execution status: {current}",
            details={"current_status": current, "target_status": target},
        )
    if target not in allowed:
        raise ValidationError(
            message=f"Invalid execution transition: {current} → {target}",
            details={
                "current_status": current,
                "target_status": target,
                "allowed_transitions": sorted(allowed),
            },
        )
