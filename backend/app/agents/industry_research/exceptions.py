"""Exceptions specific to the Industry Research Agent."""

from __future__ import annotations

from app.agents.company_research.exceptions import AgentError


class IndustryNotFoundError(AgentError):
    def __init__(self, industry_id: str) -> None:
        super().__init__(
            message=f"Industry classification not found: {industry_id}",
            details={"industry_id": industry_id},
        )
