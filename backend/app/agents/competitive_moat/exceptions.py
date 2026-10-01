"""Exceptions specific to the Competitive Moat Agent."""

from __future__ import annotations

from app.agents.company_research.exceptions import AgentError


class CompanyNotFoundForMoatError(AgentError):
    def __init__(self, company_id: str) -> None:
        super().__init__(
            message=f"Company not found for moat analysis: {company_id}",
            details={"company_id": company_id},
        )
