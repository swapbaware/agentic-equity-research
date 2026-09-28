"""Valuation schema models: ValuationModel, Scenario."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import ScenarioType, ValuationModelType


class ValuationModel(Base, TimestampMixin):
    __tablename__ = "valuation_model"
    __table_args__ = (
        sa.Index("ix_valuation_model_company_run", "company_id", "research_run_id"),
        {"schema": "valuation"},
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
    model_type: Mapped[ValuationModelType] = mapped_column(
        sa.Enum(ValuationModelType, name="valuation_model_type"),
        nullable=False,
    )
    scenario: Mapped[ScenarioType] = mapped_column(
        sa.Enum(ScenarioType, name="scenario_type"),
        nullable=False,
    )
    assumptions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    implied_value_per_share: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 4),
        nullable=False,
    )
    current_price: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    upside_downside_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4), nullable=False)
    calculation_timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenario"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "research_run_id",
            "scenario_type",
            name="uq_scenario_company_run_type",
        ),
        {"schema": "valuation"},
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
    scenario_type: Mapped[ScenarioType] = mapped_column(
        sa.Enum(ScenarioType, name="scenario_type", create_type=False),
        nullable=False,
    )
    revenue_cagr: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 6), nullable=True)
    ebitda_margin: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 6), nullable=True)
    eps_growth: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 6), nullable=True)
    fcf_growth: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 6), nullable=True)
    exit_multiple: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    valuation_range_low: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4),
        nullable=True,
    )
    valuation_range_high: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4),
        nullable=True,
    )
    key_assumptions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    what_must_go_right: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.Text),
        nullable=True,
    )
    what_can_go_wrong: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.Text),
        nullable=True,
    )
