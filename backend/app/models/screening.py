"""Screening schema models: SavedScreen, CompanyScreeningData."""
from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SavedScreen(Base, TimestampMixin):
    """User-saved screening criteria."""

    __tablename__ = "saved_screen"
    __table_args__ = {"schema": "analysis"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    criteria: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class CompanyScreeningData(Base, TimestampMixin):
    """Denormalized company metrics for screening queries.

    One row per company containing the latest computed metrics.
    All financial columns use NUMERIC — never FLOAT.
    """

    __tablename__ = "company_screening_data"
    __table_args__ = (
        sa.UniqueConstraint("company_id", name="uq_screening_company"),
        sa.Index("ix_screening_symbol", "symbol"),
        sa.Index("ix_screening_sector", "sector"),
        sa.Index("ix_screening_market_cap", "market_cap"),
        {"schema": "analysis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    company_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    exchange: Mapped[str] = mapped_column(sa.String(10), nullable=False)

    # Classification
    sector: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    industry: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)

    # Valuation
    market_cap: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    ev_to_ebitda: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    peg_ratio: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)

    # Growth
    revenue_growth: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    eps_growth: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)

    # Profitability
    roe: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    roce: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    roic: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    ebitda_margin: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)

    # Leverage
    debt_to_equity: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    net_debt_to_ebitda: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)

    # Cash Flow
    fcf_yield: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    fcf_conversion: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)

    # Ownership
    promoter_holding: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 4), nullable=True)
    promoter_pledge: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 4), nullable=True)
    institutional_ownership: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(8, 4), nullable=True,
    )

    # Period metadata
    data_period: Mapped[str] = mapped_column(sa.String(20), nullable=False)
