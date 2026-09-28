"""Thesis schema models: InvestmentThesis, ThesisVersion, Risk, Catalyst, CompanyScore."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    CatalystImpact,
    ConfidenceLevel,
    Likelihood,
    RiskType,
    ScoreDimension,
    Severity,
)

if TYPE_CHECKING:
    from app.models.research import Evidence

# ---------------------------------------------------------------------------
# Junction tables
# ---------------------------------------------------------------------------

risk_evidence = sa.Table(
    "risk_evidence",
    Base.metadata,
    sa.Column(
        "risk_id",
        sa.Uuid,
        sa.ForeignKey("thesis.risk.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="thesis",
)

catalyst_evidence = sa.Table(
    "catalyst_evidence",
    Base.metadata,
    sa.Column(
        "catalyst_id",
        sa.Uuid,
        sa.ForeignKey("thesis.catalyst.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="thesis",
)

company_score_evidence = sa.Table(
    "company_score_evidence",
    Base.metadata,
    sa.Column(
        "company_score_id",
        sa.Uuid,
        sa.ForeignKey("thesis.company_score.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="thesis",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class InvestmentThesis(Base):
    __tablename__ = "investment_thesis"
    __table_args__ = (
        sa.Index("ix_investment_thesis_company_version", "company_id", sa.text("version DESC")),
        {"schema": "thesis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    one_line_thesis: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    business_quality_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    moat_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    growth_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    management_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    financial_quality_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valuation_summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    bear_case: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    bull_case: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    key_monitoring_metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    thesis_invalidation_conditions: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.Text),
        nullable=True,
    )
    overall_confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )
    fact_vs_inference_labels: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


class ThesisVersion(Base):
    __tablename__ = "thesis_version"
    __table_args__ = (
        sa.Index("ix_thesis_version_company", "company_id"),
        {"schema": "thesis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("thesis.investment_thesis.id"),
        nullable=False,
    )
    previous_thesis_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("thesis.investment_thesis.id"),
        nullable=True,
    )
    change_summary: Mapped[str] = mapped_column(sa.Text, nullable=False)
    change_trigger: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    thesis: Mapped[InvestmentThesis] = relationship(
        "InvestmentThesis",
        foreign_keys=[thesis_id],
    )
    previous_thesis: Mapped[InvestmentThesis | None] = relationship(
        "InvestmentThesis",
        foreign_keys=[previous_thesis_id],
    )


class Risk(Base, TimestampMixin):
    __tablename__ = "risk"
    __table_args__ = (
        sa.Index("ix_risk_company_run", "company_id", "research_run_id"),
        {"schema": "thesis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=False,
    )
    risk_type: Mapped[RiskType] = mapped_column(
        sa.Enum(RiskType, name="risk_type"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        sa.Enum(Severity, name="severity"),
        nullable=False,
    )
    likelihood: Mapped[Likelihood] = mapped_column(
        sa.Enum(Likelihood, name="likelihood"),
        nullable=False,
    )
    mitigation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    evidences: Mapped[list[Evidence]] = relationship(
        "Evidence",
        secondary=risk_evidence,
    )


class Catalyst(Base, TimestampMixin):
    __tablename__ = "catalyst"
    __table_args__ = (
        sa.Index("ix_catalyst_company_run", "company_id", "research_run_id"),
        {"schema": "thesis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    expected_timeline: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    impact: Mapped[CatalystImpact] = mapped_column(
        sa.Enum(CatalystImpact, name="catalyst_impact"),
        nullable=False,
    )
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )

    evidences: Mapped[list[Evidence]] = relationship(
        "Evidence",
        secondary=catalyst_evidence,
    )


class CompanyScore(Base, TimestampMixin):
    __tablename__ = "company_score"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "research_run_id",
            "dimension",
            name="uq_company_score_company_run_dimension",
        ),
        {"schema": "thesis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("research.research_run.id"),
        nullable=False,
    )
    dimension: Mapped[ScoreDimension] = mapped_column(
        sa.Enum(ScoreDimension, name="score_dimension"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sub_scores: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str] = mapped_column(sa.Text, nullable=False)

    evidences: Mapped[list[Evidence]] = relationship(
        "Evidence",
        secondary=company_score_evidence,
    )
