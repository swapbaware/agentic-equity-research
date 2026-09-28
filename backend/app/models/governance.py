"""Governance schema models: Shareholding, PromoterPledge, CorporateAction, CorporateAnnouncement."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import CorporateActionType


class Shareholding(Base, TimestampMixin):
    __tablename__ = "shareholding"
    __table_args__ = (
        sa.UniqueConstraint("company_id", "as_of_date", name="uq_shareholding_company_date"),
        {"schema": "governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    promoter_holding_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    fii_holding_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    dii_holding_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    public_holding_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=True,
    )


class PromoterPledge(Base, TimestampMixin):
    __tablename__ = "promoter_pledge"
    __table_args__ = (
        sa.UniqueConstraint("company_id", "as_of_date", name="uq_promoter_pledge_company_date"),
        {"schema": "governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    shares_pledged: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    pledge_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=True,
    )


class CorporateAction(Base, TimestampMixin):
    __tablename__ = "corporate_action"
    __table_args__ = {"schema": "governance"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    action_type: Mapped[CorporateActionType] = mapped_column(
        sa.Enum(CorporateActionType, name="corporate_action_type"),
        nullable=False,
    )
    ex_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    record_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)


class CorporateAnnouncement(Base, TimestampMixin):
    __tablename__ = "corporate_announcement"
    __table_args__ = (
        sa.Index("ix_corporate_announcement_company_date", "company_id", "announcement_date"),
        {"schema": "governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    announcement_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(sa.String(2000), nullable=True)
    exchange: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
