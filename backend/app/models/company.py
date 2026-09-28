"""Company schema models: Exchange, Classification, Company, Security."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ClassificationLevel, SecurityType


class Exchange(Base, TimestampMixin):
    __tablename__ = "exchange"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_exchange_code"),
        {"schema": "company"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    country: Mapped[str] = mapped_column(sa.String(2), nullable=False, server_default="IN")

    securities: Mapped[list[Security]] = relationship(back_populates="exchange")


class Classification(Base, TimestampMixin):
    __tablename__ = "classification"
    __table_args__ = (
        sa.UniqueConstraint("code", "level", name="uq_classification_code_level"),
        {"schema": "company"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    level: Mapped[ClassificationLevel] = mapped_column(
        sa.Enum(ClassificationLevel, name="classification_level"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.classification.id"),
        nullable=True,
    )

    parent: Mapped[Classification | None] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list[Classification]] = relationship(back_populates="parent")


class Company(Base, TimestampMixin):
    __tablename__ = "company"
    __table_args__ = (
        sa.UniqueConstraint("isin", name="uq_company_isin"),
        sa.Index(
            "ix_company_nse_symbol",
            "nse_symbol",
            unique=True,
            postgresql_where=sa.text("nse_symbol IS NOT NULL"),
        ),
        sa.Index(
            "ix_company_bse_code",
            "bse_code",
            unique=True,
            postgresql_where=sa.text("bse_code IS NOT NULL"),
        ),
        sa.Index("ix_company_sector_mcap", "sector_id", "market_cap"),
        {"schema": "company"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    nse_symbol: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    bse_code: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    isin: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.classification.id"),
        nullable=True,
    )
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("company.classification.id"),
        nullable=True,
    )
    market_cap: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    enterprise_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    incorporation_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    listing_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    website: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    business_segments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    major_products: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geographies: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    sector: Mapped[Classification | None] = relationship(
        "Classification",
        foreign_keys=[sector_id],
    )
    industry: Mapped[Classification | None] = relationship(
        "Classification",
        foreign_keys=[industry_id],
    )
    securities: Mapped[list[Security]] = relationship(back_populates="company")


class Security(Base, TimestampMixin):
    __tablename__ = "security"
    __table_args__ = (
        sa.UniqueConstraint("company_id", "exchange_id", name="uq_security_company_exchange"),
        {"schema": "company"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    exchange_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.exchange.id"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    security_type: Mapped[SecurityType] = mapped_column(
        sa.Enum(SecurityType, name="security_type"),
        nullable=False,
    )
    face_value: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4), nullable=False)
    lot_size: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("1"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    company: Mapped[Company] = relationship(back_populates="securities")
    exchange: Mapped[Exchange] = relationship(back_populates="securities")
