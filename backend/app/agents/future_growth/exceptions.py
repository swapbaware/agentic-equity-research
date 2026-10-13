"""Exceptions for the Future Growth & Optionality Agent."""

from __future__ import annotations

from app.agents.company_research.exceptions import AgentError


class CompanyNotFoundForGrowthError(AgentError):
    """Raised when the target company is not found in the database."""

    def __init__(self, company_id: str) -> None:
        super().__init__(
            message=f"Company not found for growth analysis: {company_id}",
            details={"company_id": company_id},
        )
