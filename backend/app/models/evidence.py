"""Evidence subsystem models: Source, DocumentVersion, Claim, ClaimEvidence, SourceReliability."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ClaimType, ConfidenceLevel, SourceTier, SourceType

if TYPE_CHECKING:
    from app.models.research import Evidence, ResearchDocument


class Source(Base, TimestampMixin):
    __tablename__ = "source"
    __table_args__ = (
        sa.UniqueConstraint("name", name="uq_source_name"),
        sa.Index("ix_source_type", "source_type"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        sa.Enum(SourceType, name="source_type"),
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(sa.String(2000), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    default_tier: Mapped[SourceTier] = mapped_column(
        sa.Enum(SourceTier, name="source_tier", create_type=False),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    documents: Mapped[list[ResearchDocument]] = relationship(
        "ResearchDocument",
        back_populates="source",
    )
    reliability_assessments: Mapped[list[SourceReliability]] = relationship(
        back_populates="source",
        order_by="SourceReliability.assessed_at.desc()",
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_doc_num"),
        sa.Index("ix_document_version_document", "document_id"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    changes_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    document: Mapped[ResearchDocument] = relationship(
        "ResearchDocument",
        back_populates="versions",
    )


class Claim(Base):
    __tablename__ = "claim"
    __table_args__ = (
        sa.Index("ix_claim_company_run", "company_id", "research_run_id"),
        sa.Index("ix_claim_type", "claim_type"),
        sa.Index("ix_claim_verified", "is_verified"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        sa.Enum(ClaimType, name="claim_type"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=True,
    )
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=True,
    )
    source_agent: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    verified_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    verification_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    claim_evidences: Mapped[list[ClaimEvidence]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_pair"),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.claim.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevance: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())

    claim: Mapped[Claim] = relationship(back_populates="claim_evidences")
    evidence: Mapped[Evidence] = relationship("Evidence")


class SourceReliability(Base):
    __tablename__ = "source_reliability"
    __table_args__ = (
        sa.Index("ix_source_reliability_source_date", "source_id", sa.text("assessed_at DESC")),
        {"schema": "research"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.source.id"),
        nullable=False,
    )
    assessed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    reliability_score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 4), nullable=False)
    total_claims: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    verified_claims: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    refuted_claims: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    source: Mapped[Source] = relationship(back_populates="reliability_assessments")
