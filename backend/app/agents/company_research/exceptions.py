"""Exceptions specific to the Company Research Agent."""
from __future__ import annotations

from app.exceptions import AppError


class AgentError(AppError):
    """Base error for Company Research Agent failures."""

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            code="AGENT_ERROR",
            message=message,
            status_code=500,
            details=details,
        )


class CompanyNotFoundError(AgentError):
    def __init__(self, identifier: str, identifier_type: str) -> None:
        super().__init__(
            message=f"Company not found: {identifier} ({identifier_type})",
            details={"identifier": identifier, "identifier_type": identifier_type},
        )


class TokenBudgetExhaustedError(AgentError):
    def __init__(self, used: int, budget: int) -> None:
        super().__init__(
            message=f"Token budget exhausted: {used}/{budget}",
            details={"used": used, "budget": budget},
        )


class LLMParsingError(AgentError):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(
            message=f"Failed to parse LLM response in {step}: {detail}",
            details={"step": step, "detail": detail},
        )


class StepFailedError(AgentError):
    def __init__(self, step_name: str, reason: str) -> None:
        super().__init__(
            message=f"Step {step_name} failed: {reason}",
            details={"step_name": step_name, "reason": reason},
        )
