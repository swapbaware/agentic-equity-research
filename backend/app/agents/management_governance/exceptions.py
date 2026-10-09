"""Exceptions for the Management & Governance Agent."""

from __future__ import annotations

from app.agents.company_research.exceptions import AgentError


class CompanyNotFoundForGovernanceError(AgentError):
    """Raised when the target company is not found in the database."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Company not found for governance analysis: {identifier}")
        self.identifier = identifier
