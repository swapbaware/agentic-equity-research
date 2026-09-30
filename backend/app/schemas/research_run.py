"""Pydantic v2 schemas for Research Run infrastructure."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Token / cost DTOs
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


# ---------------------------------------------------------------------------
# ResearchRun
# ---------------------------------------------------------------------------


class ResearchRunCreate(BaseModel):
    company_id: uuid.UUID
    initiated_by: str = Field(max_length=200)
    run_type: str = Field(max_length=50)
    trigger_type: str = Field(max_length=50)
    parent_run_id: uuid.UUID | None = None
    observation_date: date | None = None
    configuration: dict[str, object] | None = None


class ResearchRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    initiated_by: str
    run_type: str | None
    trigger_type: str | None
    parent_run_id: uuid.UUID | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    observation_date: date | None
    configuration: dict[str, object] | None
    quality_gate_results: dict[str, object] | None
    research_completeness: Decimal | None
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_cost_usd: Decimal | None
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


class RunSummary(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    status: str
    run_type: str | None
    started_at: datetime
    completed_at: datetime | None
    observation_date: date | None
    findings_count: int = 0
    research_completeness: Decimal | None
    total_cost_usd: Decimal | None


class RunProgress(BaseModel):
    run_id: uuid.UUID
    status: str
    steps_total: int = 0
    steps_completed: int = 0
    current_step: str | None = None
    current_agent: str | None = None
    findings_count: int = 0
    elapsed_seconds: int = 0


# ---------------------------------------------------------------------------
# ResearchRunStep
# ---------------------------------------------------------------------------


class ResearchRunStepCreate(BaseModel):
    step_name: str = Field(max_length=100)
    step_order: int = Field(ge=0)
    step_type: str = Field(max_length=50)


class ResearchRunStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    step_name: str
    step_order: int
    step_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    input_state_hash: str | None
    output_state_hash: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# AgentExecution
# ---------------------------------------------------------------------------


class AgentExecutionCreate(BaseModel):
    agent_name: str = Field(max_length=100)
    attempt_number: int = Field(ge=1, default=1)
    model_provider: str = Field(max_length=50)
    model_name: str = Field(max_length=100)
    llm_config: dict[str, object] | None = None
    prompt_version: str | None = Field(default=None, max_length=50)
    tool_versions: dict[str, object] | None = None


class AgentExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    step_id: uuid.UUID | None
    agent_name: str
    attempt_number: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    model_provider: str
    model_name: str
    llm_config: dict[str, object] | None = None
    prompt_version: str | None
    tool_versions: dict[str, object] | None
    error_message: str | None
    error_type: str | None
    findings_produced: int
    created_at: datetime


# ---------------------------------------------------------------------------
# ResearchFinding
# ---------------------------------------------------------------------------


class ResearchFindingCreate(BaseModel):
    agent_name: str = Field(max_length=100)
    finding_type: str = Field(max_length=50)
    category: str = Field(max_length=100)
    content: str
    confidence: str = Field(max_length=20)
    observation_date: date | None = None
    source_publication_date: date | None = None
    calculation_version: str | None = Field(default=None, max_length=50)
    supersedes_finding_id: uuid.UUID | None = None


class ResearchFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    agent_execution_id: uuid.UUID | None
    agent_name: str
    finding_type: str
    category: str
    content: str
    confidence: str
    observation_date: date | None
    source_publication_date: date | None
    calculation_version: str | None
    supersedes_finding_id: uuid.UUID | None
    created_at: datetime


# ---------------------------------------------------------------------------
# ResearchArtifact
# ---------------------------------------------------------------------------


class ResearchArtifactCreate(BaseModel):
    artifact_type: str = Field(max_length=50)
    title: str = Field(max_length=500)
    content_type: str = Field(max_length=100)
    content_hash: str = Field(max_length=64)
    storage_path: str | None = Field(default=None, max_length=1000)
    inline_content: dict[str, object] | None = None
    metadata: dict[str, object] | None = None


class ResearchArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    agent_execution_id: uuid.UUID | None
    artifact_type: str
    title: str
    content_type: str
    content_hash: str
    storage_path: str | None
    inline_content: dict[str, object] | None
    created_at: datetime


# ---------------------------------------------------------------------------
# ResearchRunSource
# ---------------------------------------------------------------------------


class ResearchRunSourceCreate(BaseModel):
    document_id: uuid.UUID
    access_type: str = Field(max_length=50)


# ---------------------------------------------------------------------------
# Evidence chain (read model)
# ---------------------------------------------------------------------------


class EvidenceChainItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: uuid.UUID
    evidence_type: str
    claim: str
    page_or_section: str | None
    confidence: str
    document_id: uuid.UUID
    document_title: str
    source_tier: str
    source_name: str


class FindingEvidenceChain(BaseModel):
    finding: ResearchFindingRead
    evidences: list[EvidenceChainItem] = Field(default_factory=list)
