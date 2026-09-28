"""Research schema models: ResearchDocument, Evidence, ManagementStatement, ResearchRun, ResearchFinding."""
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
    ResearchRunStatus,
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
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
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


class ResearchRun(Base):
    __tablename__ = "research_run"
    __table_args__ = (
        sa.Index("ix_research_run_company_started", "company_id", sa.text("started_at DESC")),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    initiated_by: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[ResearchRunStatus] = mapped_column(
        sa.Enum(ResearchRunStatus, name="research_run_status"),
        nullable=False,
        server_default="RUNNING",
    )
    quality_gate_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_execution_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data_sources_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    research_completeness: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2),
        nullable=True,
    )
    total_input_tokens: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    total_output_tokens: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    cost_by_agent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    findings: Mapped[list[ResearchFinding]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )


class ResearchFinding(Base):
    __tablename__ = "research_finding"
    __table_args__ = (
        sa.Index("ix_research_finding_run_agent", "research_run_id", "agent_name"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
        nullable=False,
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
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    research_run: Mapped[ResearchRun] = relationship(back_populates="findings")
    evidences: Mapped[list[Evidence]] = relationship(
        secondary=research_finding_evidence,
    )
