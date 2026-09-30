"""Research schema models: runs, findings, steps, executions, artifacts, sources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    ManagementStatementCategory,
    ManagementStatementStatus,
    SourceTier,
)

if TYPE_CHECKING:
    from app.models.evidence import DocumentVersion, Source

research_finding_evidence = sa.Table(
    "research_finding_evidence",
    Base.metadata,
    sa.Column(
        "research_finding_id",
        sa.Uuid,
        sa.ForeignKey("research.research_finding.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="research",
)


class ResearchDocument(Base, TimestampMixin):
    __tablename__ = "research_document"
    __table_args__ = (
        sa.UniqueConstraint("content_hash", name="uq_research_document_content_hash"),
        sa.Index(
            "ix_research_document_company_type_date",
            "company_id",
            "document_type",
            "document_date",
        ),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.source.id"),
        nullable=True,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        sa.Enum(DocumentType, name="document_type"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    source_tier: Mapped[SourceTier] = mapped_column(
        sa.Enum(SourceTier, name="source_tier"),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(sa.String(2000), nullable=True)
    document_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    metadata_: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    source: Mapped[Source | None] = relationship("Source", back_populates="documents")
    evidences: Mapped[list[Evidence]] = relationship(back_populates="document")
    versions: Mapped[list[DocumentVersion]] = relationship(
        "DocumentVersion",
        back_populates="document",
        order_by="DocumentVersion.version_number",
    )


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        sa.Index("ix_evidence_document", "document_id"),
        sa.Index("ix_evidence_type", "evidence_type"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=False,
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        sa.Enum(EvidenceType, name="evidence_type"),
        nullable=False,
    )
    claim: Mapped[str] = mapped_column(sa.Text, nullable=False)
    context: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    page_or_section: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level"),
        nullable=False,
    )
    extracted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    extracted_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)

    document: Mapped[ResearchDocument] = relationship(back_populates="evidences")


class ManagementStatement(Base, TimestampMixin):
    __tablename__ = "management_statement"
    __table_args__ = (
        sa.Index("ix_management_statement_company", "company_id", "statement_date"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    statement_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    statement: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[ManagementStatementCategory] = mapped_column(
        sa.Enum(ManagementStatementCategory, name="management_statement_category"),
        nullable=False,
    )
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.evidence.id"),
        nullable=True,
    )
    expected_outcome: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actual_outcome: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    outcome_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.evidence.id"),
        nullable=True,
    )
    status: Mapped[ManagementStatementStatus] = mapped_column(
        sa.Enum(ManagementStatementStatus, name="management_statement_status"),
        nullable=False,
        server_default="PENDING",
    )

    source_evidence: Mapped[Evidence | None] = relationship(
        "Evidence",
        foreign_keys=[source_evidence_id],
    )
    outcome_evidence: Mapped[Evidence | None] = relationship(
        "Evidence",
        foreign_keys=[outcome_evidence_id],
    )


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_run"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('CREATED', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL', 'CANCELLED')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "(target_type = 'company'  AND company_id IS NOT NULL AND industry_id IS NULL) "
            "OR "
            "(target_type = 'industry' AND company_id IS NULL     AND industry_id IS NOT NULL)",
            name="chk_research_run_target",
        ),
        sa.Index("ix_research_run_company_started", "company_id", sa.text("started_at DESC")),
        sa.Index("ix_research_run_parent", "parent_run_id"),
        sa.Index("ix_research_run_observation", "company_id", sa.text("observation_date DESC")),
        sa.Index(
            "ix_research_run_industry",
            "industry_id",
            sa.text("started_at DESC"),
            postgresql_where=sa.text("industry_id IS NOT NULL"),
        ),
        sa.Index("ix_research_run_target_type", "target_type", sa.text("started_at DESC")),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        server_default="company",
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=True,
    )
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.classification.id"),
        nullable=True,
    )
    initiated_by: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    run_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    trigger_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="CREATED",
    )
    observation_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    configuration: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    quality_gate_results: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    research_completeness: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2),
        nullable=True,
    )
    total_input_tokens: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    total_output_tokens: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Deprecated JSONB fields — superseded by AgentExecution / ResearchRunSource.
    # Retained for backward compatibility. New code must NOT depend on these.
    agent_execution_log: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    data_sources_used: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    cost_by_agent: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    findings: Mapped[list[ResearchFinding]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    steps: Mapped[list[ResearchRunStep]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        order_by="ResearchRunStep.step_order",
    )
    agent_executions: Mapped[list[AgentExecution]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list[ResearchArtifact]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    sources_used: Mapped[list[ResearchRunSource]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )


class ResearchFinding(Base):
    __tablename__ = "research_finding"
    __table_args__ = (
        sa.Index("ix_research_finding_run_agent", "research_run_id", "agent_name"),
        sa.Index("ix_research_finding_execution_id", "agent_execution_id"),
        sa.Index("ix_research_finding_observation_date", "research_run_id", "observation_date"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.agent_execution.id"),
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    finding_type: Mapped[FindingType] = mapped_column(
        sa.Enum(FindingType, name="finding_type"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )
    observation_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    source_publication_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    calculation_version: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    supersedes_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_finding.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="findings")
    agent_execution: Mapped[AgentExecution | None] = relationship(
        "AgentExecution",
        back_populates="findings",
    )
    evidences: Mapped[list[Evidence]] = relationship(
        secondary=research_finding_evidence,
    )
    superseded_by: Mapped[ResearchFinding | None] = relationship(
        "ResearchFinding",
        remote_side="ResearchFinding.supersedes_finding_id",
        uselist=False,
    )


class ResearchRunStep(Base, TimestampMixin):
    __tablename__ = "research_run_step"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')",
            name="status_valid",
        ),
        sa.Index("ix_research_run_step_run_id", "research_run_id"),
        sa.Index("ix_research_run_step_status", "research_run_id", "status"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    step_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="PENDING",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    input_state_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    output_state_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    research_run: Mapped[ResearchRun] = relationship(back_populates="steps")
    agent_executions: Mapped[list[AgentExecution]] = relationship(
        back_populates="step",
        order_by="AgentExecution.attempt_number",
    )


class AgentExecution(Base):
    __tablename__ = "agent_execution"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'TRUNCATED')",
            name="status_valid",
        ),
        sa.Index("ix_agent_execution_run_id", "research_run_id"),
        sa.Index("ix_agent_execution_step_id", "step_id"),
        sa.Index("ix_agent_execution_agent_name", "research_run_id", "agent_name"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_run_step.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    attempt_number: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default="RUNNING",
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(
        sa.BigInteger,
        nullable=False,
        server_default=sa.text("0"),
    )
    output_tokens: Mapped[int] = mapped_column(
        sa.BigInteger,
        nullable=False,
        server_default=sa.text("0"),
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 6),
        nullable=False,
        server_default=sa.text("0"),
    )
    model_provider: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    model_config: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    tool_versions: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    findings_produced: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="agent_executions")
    step: Mapped[ResearchRunStep | None] = relationship(back_populates="agent_executions")
    findings: Mapped[list[ResearchFinding]] = relationship(
        back_populates="agent_execution",
    )


class ResearchArtifact(Base):
    __tablename__ = "research_artifact"
    __table_args__ = (
        sa.Index("ix_research_artifact_run_id", "research_run_id"),
        sa.Index("ix_research_artifact_type", "research_run_id", "artifact_type"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.agent_execution.id"),
        nullable=True,
    )
    artifact_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    inline_content: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="artifacts")


class ResearchRunSource(Base):
    __tablename__ = "research_run_source"
    __table_args__ = (
        sa.UniqueConstraint("research_run_id", "document_id", name="uq_research_run_source_run_doc"),
        sa.Index("ix_research_run_source_run_id", "research_run_id"),
        sa.Index("ix_research_run_source_document_id", "document_id"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=False,
    )
    accessed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    access_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)

    research_run: Mapped[ResearchRun] = relationship(back_populates="sources_used")
    document: Mapped[ResearchDocument] = relationship("ResearchDocument")
