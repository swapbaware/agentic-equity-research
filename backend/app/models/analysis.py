"""Analysis schema models: MoatAssessment, GrowthOpportunity, Competitor, IndustryData, MacroIndicator."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    CompetitorRelevance,
    ConfidenceLevel,
    GrowthCategory,
    GrowthMaturity,
    MoatStrength,
    MoatType,
)

if TYPE_CHECKING:
    from app.models.research import Evidence

moat_assessment_evidence = sa.Table(
    "moat_assessment_evidence",
    Base.metadata,
    sa.Column(
        "moat_assessment_id",
        sa.Uuid,
        sa.ForeignKey("analysis.moat_assessment.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="analysis",
)

growth_opportunity_evidence = sa.Table(
    "growth_opportunity_evidence",
    Base.metadata,
    sa.Column(
        "growth_opportunity_id",
        sa.Uuid,
        sa.ForeignKey("analysis.growth_opportunity.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.Uuid,
        sa.ForeignKey("research.evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema="analysis",
)


class MoatAssessment(Base, TimestampMixin):
    __tablename__ = "moat_assessment"
    __table_args__ = (
        sa.Index("ix_moat_assessment_company_run", "company_id", "research_run_id"),
        {"schema": "analysis"},
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
    moat_type: Mapped[MoatType] = mapped_column(
        sa.Enum(MoatType, name="moat_type"),
        nullable=False,
    )
    strength: Mapped[MoatStrength] = mapped_column(
        sa.Enum(MoatStrength, name="moat_strength"),
        nullable=False,
        server_default="NONE",
    )
    durability_years: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    threats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    competitor_comparison: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    evidences: Mapped[list[Evidence]] = relationship(
        "Evidence",
        secondary=moat_assessment_evidence,
    )


class GrowthOpportunity(Base, TimestampMixin):
    __tablename__ = "growth_opportunity"
    __table_args__ = (
        sa.Index("ix_growth_opportunity_company_run", "company_id", "research_run_id"),
        {"schema": "analysis"},
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
    opportunity_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    category: Mapped[GrowthCategory] = mapped_column(
        sa.Enum(GrowthCategory, name="growth_category"),
        nullable=False,
    )
    maturity: Mapped[GrowthMaturity] = mapped_column(
        sa.Enum(GrowthMaturity, name="growth_maturity"),
        nullable=False,
    )
    addressable_market: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4),
        nullable=True,
    )
    timeline_years: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    risks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        sa.Enum(ConfidenceLevel, name="confidence_level", create_type=False),
        nullable=False,
    )

    evidences: Mapped[list[Evidence]] = relationship(
        "Evidence",
        secondary=growth_opportunity_evidence,
    )


class Competitor(Base, TimestampMixin):
    __tablename__ = "competitor"
    __table_args__ = (
        sa.Index("ix_competitor_company", "company_id"),
        {"schema": "analysis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    competitor_company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=True,
    )
    competitor_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    is_domestic: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    relevance: Mapped[CompetitorRelevance] = mapped_column(
        sa.Enum(CompetitorRelevance, name="competitor_relevance"),
        nullable=False,
    )
    comparison_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class IndustryData(Base, TimestampMixin):
    __tablename__ = "industry_data"
    __table_args__ = (
        sa.Index("ix_industry_data_industry_metric", "industry_id", "metric_name"),
        {"schema": "analysis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.classification.id"),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    as_of_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.evidence.id"),
        nullable=True,
    )


class MacroIndicator(Base, TimestampMixin):
    __tablename__ = "macro_indicator"
    __table_args__ = (
        sa.Index("ix_macro_indicator_name_date", "indicator_name", "as_of_date"),
        {"schema": "analysis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    indicator_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8), nullable=False)
    unit: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    as_of_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    source: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    country: Mapped[str] = mapped_column(sa.String(10), nullable=False, server_default="IN")
    company_impact_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
