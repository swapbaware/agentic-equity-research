"""Financial schema models: FinancialStatement, FinancialMetric, QuarterlyResult."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import MetricUnit, PeriodType, StatementType


class FinancialStatement(Base, TimestampMixin):
    __tablename__ = "financial_statement"
    __table_args__ = (
        sa.CheckConstraint(
            "(period_type = 'ANNUAL' AND fiscal_quarter IS NULL) OR "
            "(period_type = 'QUARTERLY' AND fiscal_quarter IS NOT NULL)",
            name="ck_financial_statement_quarter_consistency",
        ),
        sa.Index(
            "ix_financial_statement_annual_identity",
            "company_id",
            "statement_type",
            "fiscal_year",
            "is_consolidated",
            unique=True,
            postgresql_where=sa.text("period_type = 'ANNUAL'"),
        ),
        sa.Index(
            "ix_financial_statement_quarterly_identity",
            "company_id",
            "statement_type",
            "fiscal_year",
            "fiscal_quarter",
            "is_consolidated",
            unique=True,
            postgresql_where=sa.text("period_type = 'QUARTERLY'"),
        ),
        sa.Index(
            "ix_financial_statement_company_period",
            "company_id",
            "period_type",
            "fiscal_year",
        ),
        {"schema": "financial"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    statement_type: Mapped[StatementType] = mapped_column(
        sa.Enum(StatementType, name="statement_type"),
        nullable=False,
    )
    period_type: Mapped[PeriodType] = mapped_column(
        sa.Enum(PeriodType, name="period_type"),
        nullable=False,
    )
    fiscal_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    period_start: Mapped[date] = mapped_column(sa.Date, nullable=False)
    period_end: Mapped[date] = mapped_column(sa.Date, nullable=False)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, server_default="INR")
    is_audited: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    is_consolidated: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    source: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=True,
    )

    metrics: Mapped[list[FinancialMetric]] = relationship(
        back_populates="statement",
        cascade="all, delete-orphan",
    )


class FinancialMetric(Base):
    __tablename__ = "financial_metric"
    __table_args__ = (
        sa.Index("ix_financial_metric_statement_name", "statement_id", "metric_name"),
        {"schema": "financial"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("financial.financial_statement.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    unit: Mapped[MetricUnit] = mapped_column(
        sa.Enum(MetricUnit, name="metric_unit"),
        nullable=False,
    )
    is_calculated: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    calculation_formula: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    statement: Mapped[FinancialStatement] = relationship(back_populates="metrics")


class QuarterlyResult(Base, TimestampMixin):
    __tablename__ = "quarterly_result"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "fiscal_year",
            "fiscal_quarter",
            name="uq_quarterly_result_company_period",
        ),
        sa.Index(
            "ix_quarterly_result_company_period",
            "company_id",
            "fiscal_year",
            "fiscal_quarter",
        ),
        {"schema": "financial"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("company.company.id"),
        nullable=False,
    )
    fiscal_year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    revenue: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    ebitda: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    ebit: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    pat: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 8), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("research.research_document.id"),
        nullable=True,
    )
    filing_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
