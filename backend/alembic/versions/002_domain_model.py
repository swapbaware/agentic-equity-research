"""Create domain model tables and enum types.

Revision ID: 002
Revises: 001
Create Date: 2026-09-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Enum type definitions (all in public schema for cross-schema access)
# ---------------------------------------------------------------------------

ENUM_TYPES: list[tuple[str, list[str]]] = [
    ("classification_level", ["SECTOR", "INDUSTRY"]),
    ("security_type", ["EQUITY", "PREFERENCE", "DEBENTURE"]),
    ("statement_type", ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]),
    ("period_type", ["ANNUAL", "QUARTERLY"]),
    ("metric_unit", ["CURRENCY", "PERCENTAGE", "RATIO", "COUNT"]),
    ("corporate_action_type", ["DIVIDEND", "SPLIT", "BONUS", "BUYBACK", "RIGHTS", "MERGER"]),
    (
        "document_type",
        [
            "ANNUAL_REPORT", "QUARTERLY_RESULT", "INVESTOR_PRESENTATION",
            "TRANSCRIPT", "FILING", "NEWS", "RESEARCH_REPORT", "GOVERNMENT_PUBLICATION",
        ],
    ),
    ("source_tier", ["TIER_1", "TIER_2", "TIER_3"]),
    ("evidence_type", ["FACT", "FINANCIAL_DATA", "MANAGEMENT_STATEMENT", "ANALYST_OPINION", "REGULATORY_FILING"]),
    ("confidence_level", ["HIGH", "MEDIUM", "LOW"]),
    (
        "management_statement_category",
        ["REVENUE_GUIDANCE", "MARGIN_GUIDANCE", "CAPEX_PLAN", "PRODUCT_LAUNCH", "EXPANSION", "OTHER"],
    ),
    ("management_statement_status", ["PENDING", "MET", "PARTIALLY_MET", "MISSED", "UNKNOWN"]),
    ("research_run_status", ["RUNNING", "COMPLETED", "FAILED", "INCOMPLETE"]),
    (
        "finding_type",
        ["FACT", "CALCULATION", "MANAGEMENT_CLAIM", "ANALYST_OPINION", "AI_INFERENCE", "ASSUMPTION", "UNCERTAINTY"],
    ),
    (
        "moat_type",
        [
            "BRAND", "COST_ADVANTAGE", "NETWORK_EFFECT", "SWITCHING_COST", "DISTRIBUTION",
            "SCALE", "REGULATORY", "IP", "TECHNOLOGY", "DATA", "ECOSYSTEM",
            "CUSTOMER_EMBEDDEDNESS", "MANUFACTURING", "SUPPLY_CHAIN", "CAPITAL_ACCESS", "LOCATION",
        ],
    ),
    ("moat_strength", ["NONE", "NARROW", "MODERATE", "WIDE"]),
    (
        "growth_category",
        ["NEW_PRODUCT", "NEW_MARKET", "ACQUISITION", "PARTNERSHIP", "GOVERNMENT_INCENTIVE", "TECHNOLOGY", "EXPANSION"],
    ),
    ("growth_maturity", ["PROVEN", "COMMERCIALIZING", "EARLY_STAGE", "EXPERIMENTAL", "SPECULATIVE"]),
    ("competitor_relevance", ["DIRECT", "INDIRECT", "POTENTIAL"]),
    (
        "valuation_model_type",
        [
            "PE", "EV_EBITDA", "PS", "PB", "PEG", "FCF_YIELD", "EV_FCF",
            "DCF", "REVERSE_DCF", "HISTORICAL_BAND", "PEER_COMPARISON",
        ],
    ),
    ("scenario_type", ["BEAR", "BASE", "BULL"]),
    (
        "risk_type",
        [
            "BUSINESS", "FINANCIAL", "VALUATION", "GOVERNANCE", "REGULATORY", "TECHNOLOGY",
            "DISRUPTION", "COMMODITY", "CURRENCY", "GEOPOLITICAL",
            "CUSTOMER_CONCENTRATION", "SUPPLIER_CONCENTRATION", "EXECUTION",
        ],
    ),
    ("severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
    ("likelihood", ["LOW", "MEDIUM", "HIGH"]),
    ("catalyst_impact", ["LOW", "MEDIUM", "HIGH"]),
    (
        "score_dimension",
        [
            "BUSINESS_QUALITY", "FINANCIAL_QUALITY", "GROWTH_QUALITY", "MOAT_STRENGTH",
            "MANAGEMENT_QUALITY", "FUTURE_OPTIONALITY", "INDUSTRY_ATTRACTIVENESS",
            "VALUATION_ATTRACTIVENESS", "BALANCE_SHEET_STRENGTH", "RISK",
        ],
    ),
]


def _enum(name: str) -> sa.Enum:
    """Reference an already-created enum type (create_type=False)."""
    return sa.Enum(name=name, create_type=False)


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -- Enum types ----------------------------------------------------------
    for name, values in ENUM_TYPES:
        sa.Enum(*values, name=name).create(op.get_bind(), checkfirst=True)

    # -- company schema ------------------------------------------------------
    op.create_table(
        "exchange",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country", sa.String(2), nullable=False, server_default="IN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_exchange_code"),
        schema="company",
    )

    op.create_table(
        "classification",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("level", _enum("classification_level"), nullable=False),
        sa.Column("parent_id", sa.Uuid, sa.ForeignKey("company.classification.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", "level", name="uq_classification_code_level"),
        schema="company",
    )

    op.create_table(
        "company",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("nse_symbol", sa.String(20), nullable=True),
        sa.Column("bse_code", sa.String(10), nullable=True),
        sa.Column("isin", sa.String(12), nullable=False),
        sa.Column("sector_id", sa.Uuid, sa.ForeignKey("company.classification.id"), nullable=True),
        sa.Column("industry_id", sa.Uuid, sa.ForeignKey("company.classification.id"), nullable=True),
        sa.Column("market_cap", sa.Numeric(20, 4), nullable=True),
        sa.Column("enterprise_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("incorporation_date", sa.Date, nullable=True),
        sa.Column("listing_date", sa.Date, nullable=True),
        sa.Column("registered_address", sa.Text, nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("business_segments", JSONB, nullable=True),
        sa.Column("major_products", JSONB, nullable=True),
        sa.Column("geographies", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("isin", name="uq_company_isin"),
        schema="company",
    )
    op.create_index(
        "ix_company_nse_symbol", "company", ["nse_symbol"],
        unique=True, schema="company",
        postgresql_where=sa.text("nse_symbol IS NOT NULL"),
    )
    op.create_index(
        "ix_company_bse_code", "company", ["bse_code"],
        unique=True, schema="company",
        postgresql_where=sa.text("bse_code IS NOT NULL"),
    )
    op.create_index("ix_company_sector_mcap", "company", ["sector_id", "market_cap"], schema="company")

    op.create_table(
        "security",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("exchange_id", sa.Uuid, sa.ForeignKey("company.exchange.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("security_type", _enum("security_type"), nullable=False),
        sa.Column("face_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("lot_size", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "exchange_id", name="uq_security_company_exchange"),
        schema="company",
    )

    # -- research schema (before financial/governance — they reference research_document) --
    op.create_table(
        "research_document",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=True),
        sa.Column("document_type", _enum("document_type"), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("source_tier", _enum("source_tier"), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("document_date", sa.Date, nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("embedding_id", sa.String(200), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_research_document_content_hash"),
        schema="research",
    )
    op.create_index(
        "ix_research_document_company_type_date",
        "research_document",
        ["company_id", "document_type", "document_date"],
        schema="research",
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("document_id", sa.Uuid, sa.ForeignKey("research.research_document.id"), nullable=False),
        sa.Column("evidence_type", _enum("evidence_type"), nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("page_or_section", sa.String(200), nullable=True),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("extracted_by", sa.String(100), nullable=False),
        schema="research",
    )
    op.create_index("ix_evidence_document", "evidence", ["document_id"], schema="research")
    op.create_index("ix_evidence_type", "evidence", ["evidence_type"], schema="research")

    op.create_table(
        "management_statement",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("statement_date", sa.Date, nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("category", _enum("management_statement_category"), nullable=False),
        sa.Column("source_evidence_id", sa.Uuid, sa.ForeignKey("research.evidence.id"), nullable=True),
        sa.Column("expected_outcome", sa.Text, nullable=True),
        sa.Column("actual_outcome", sa.Text, nullable=True),
        sa.Column("outcome_evidence_id", sa.Uuid, sa.ForeignKey("research.evidence.id"), nullable=True),
        sa.Column("status", _enum("management_statement_status"), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="research",
    )
    op.create_index(
        "ix_management_statement_company",
        "management_statement",
        ["company_id", "statement_date"],
        schema="research",
    )

    op.create_table(
        "research_run",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("initiated_by", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _enum("research_run_status"), nullable=False, server_default="RUNNING"),
        sa.Column("quality_gate_results", JSONB, nullable=True),
        sa.Column("agent_execution_log", JSONB, nullable=True),
        sa.Column("data_sources_used", JSONB, nullable=True),
        sa.Column("research_completeness", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_input_tokens", sa.BigInteger, nullable=True),
        sa.Column("total_output_tokens", sa.BigInteger, nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("cost_by_agent", JSONB, nullable=True),
        schema="research",
    )
    op.create_index(
        "ix_research_run_company_started",
        "research_run",
        ["company_id", sa.text("started_at DESC")],
        schema="research",
    )

    op.create_table(
        "research_finding",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "research_run_id", sa.Uuid,
            sa.ForeignKey("research.research_run.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("finding_type", _enum("finding_type"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="research",
    )
    op.create_index(
        "ix_research_finding_run_agent",
        "research_finding",
        ["research_run_id", "agent_name"],
        schema="research",
    )

    op.create_table(
        "research_finding_evidence",
        sa.Column(
            "research_finding_id", sa.Uuid,
            sa.ForeignKey("research.research_finding.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="research",
    )

    # -- financial schema ----------------------------------------------------
    op.create_table(
        "financial_statement",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("statement_type", _enum("statement_type"), nullable=False),
        sa.Column("period_type", _enum("period_type"), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("fiscal_quarter", sa.SmallInteger, nullable=True),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("is_audited", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_consolidated", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column(
            "source_document_id", sa.Uuid,
            sa.ForeignKey("research.research_document.id"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(period_type = 'ANNUAL' AND fiscal_quarter IS NULL) OR "
            "(period_type = 'QUARTERLY' AND fiscal_quarter IS NOT NULL)",
            name="ck_financial_statement_quarter_consistency",
        ),
        schema="financial",
    )
    op.create_index(
        "ix_financial_statement_annual_identity",
        "financial_statement",
        ["company_id", "statement_type", "fiscal_year", "is_consolidated"],
        unique=True, schema="financial",
        postgresql_where=sa.text("period_type = 'ANNUAL'"),
    )
    op.create_index(
        "ix_financial_statement_quarterly_identity",
        "financial_statement",
        ["company_id", "statement_type", "fiscal_year", "fiscal_quarter", "is_consolidated"],
        unique=True, schema="financial",
        postgresql_where=sa.text("period_type = 'QUARTERLY'"),
    )
    op.create_index(
        "ix_financial_statement_company_period",
        "financial_statement",
        ["company_id", "period_type", "fiscal_year"],
        schema="financial",
    )

    op.create_table(
        "financial_metric",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "statement_id", sa.Uuid,
            sa.ForeignKey("financial.financial_statement.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), nullable=False),
        sa.Column("unit", _enum("metric_unit"), nullable=False),
        sa.Column("is_calculated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("calculation_formula", sa.String(500), nullable=True),
        schema="financial",
    )
    op.create_index(
        "ix_financial_metric_statement_name",
        "financial_metric",
        ["statement_id", "metric_name"],
        schema="financial",
    )

    op.create_table(
        "quarterly_result",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("fiscal_quarter", sa.SmallInteger, nullable=False),
        sa.Column("revenue", sa.Numeric(20, 4), nullable=True),
        sa.Column("ebitda", sa.Numeric(20, 4), nullable=True),
        sa.Column("ebit", sa.Numeric(20, 4), nullable=True),
        sa.Column("pat", sa.Numeric(20, 4), nullable=True),
        sa.Column("eps", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "source_document_id", sa.Uuid,
            sa.ForeignKey("research.research_document.id"), nullable=True,
        ),
        sa.Column("filing_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "fiscal_year", "fiscal_quarter", name="uq_quarterly_result_company_period"),
        schema="financial",
    )
    op.create_index(
        "ix_quarterly_result_company_period",
        "quarterly_result",
        ["company_id", "fiscal_year", "fiscal_quarter"],
        schema="financial",
    )

    # -- governance schema ---------------------------------------------------
    op.create_table(
        "shareholding",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("promoter_holding_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("fii_holding_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("dii_holding_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("public_holding_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "source_document_id", sa.Uuid,
            sa.ForeignKey("research.research_document.id"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "as_of_date", name="uq_shareholding_company_date"),
        schema="governance",
    )

    op.create_table(
        "promoter_pledge",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("shares_pledged", sa.BigInteger, nullable=False),
        sa.Column("pledge_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "source_document_id", sa.Uuid,
            sa.ForeignKey("research.research_document.id"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "as_of_date", name="uq_promoter_pledge_company_date"),
        schema="governance",
    )

    op.create_table(
        "corporate_action",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("action_type", _enum("corporate_action_type"), nullable=False),
        sa.Column("ex_date", sa.Date, nullable=True),
        sa.Column("record_date", sa.Date, nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="governance",
    )

    op.create_table(
        "corporate_announcement",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("announcement_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(1000), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("exchange", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="governance",
    )
    op.create_index(
        "ix_corporate_announcement_company_date",
        "corporate_announcement",
        ["company_id", "announcement_date"],
        schema="governance",
    )

    # -- analysis schema -----------------------------------------------------
    op.create_table(
        "moat_assessment",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("moat_type", _enum("moat_type"), nullable=False),
        sa.Column("strength", _enum("moat_strength"), nullable=False, server_default="NONE"),
        sa.Column("durability_years", sa.Integer, nullable=True),
        sa.Column("threats", JSONB, nullable=True),
        sa.Column("competitor_comparison", JSONB, nullable=True),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="analysis",
    )
    op.create_index(
        "ix_moat_assessment_company_run", "moat_assessment",
        ["company_id", "research_run_id"], schema="analysis",
    )

    op.create_table(
        "moat_assessment_evidence",
        sa.Column(
            "moat_assessment_id", sa.Uuid,
            sa.ForeignKey("analysis.moat_assessment.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="analysis",
    )

    op.create_table(
        "growth_opportunity",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("opportunity_name", sa.String(500), nullable=False),
        sa.Column("category", _enum("growth_category"), nullable=False),
        sa.Column("maturity", _enum("growth_maturity"), nullable=False),
        sa.Column("addressable_market", sa.Numeric(20, 4), nullable=True),
        sa.Column("timeline_years", sa.Integer, nullable=True),
        sa.Column("risks", JSONB, nullable=True),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="analysis",
    )
    op.create_index(
        "ix_growth_opportunity_company_run", "growth_opportunity",
        ["company_id", "research_run_id"], schema="analysis",
    )

    op.create_table(
        "growth_opportunity_evidence",
        sa.Column(
            "growth_opportunity_id", sa.Uuid,
            sa.ForeignKey("analysis.growth_opportunity.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="analysis",
    )

    op.create_table(
        "competitor",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("competitor_company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=True),
        sa.Column("competitor_name", sa.String(500), nullable=False),
        sa.Column("is_domestic", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("relevance", _enum("competitor_relevance"), nullable=False),
        sa.Column("comparison_metrics", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="analysis",
    )
    op.create_index("ix_competitor_company", "competitor", ["company_id"], schema="analysis")

    op.create_table(
        "industry_data",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("industry_id", sa.Uuid, sa.ForeignKey("company.classification.id"), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("source_evidence_id", sa.Uuid, sa.ForeignKey("research.evidence.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="analysis",
    )
    op.create_index(
        "ix_industry_data_industry_metric", "industry_data",
        ["industry_id", "metric_name"], schema="analysis",
    )

    op.create_table(
        "macro_indicator",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("indicator_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Numeric(20, 8), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("country", sa.String(10), nullable=False, server_default="IN"),
        sa.Column("company_impact_mapping", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="analysis",
    )
    op.create_index(
        "ix_macro_indicator_name_date", "macro_indicator",
        ["indicator_name", "as_of_date"], schema="analysis",
    )

    # -- valuation schema ----------------------------------------------------
    op.create_table(
        "valuation_model",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("model_type", _enum("valuation_model_type"), nullable=False),
        sa.Column("scenario", _enum("scenario_type"), nullable=False),
        sa.Column("assumptions", JSONB, nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=False),
        sa.Column("implied_value_per_share", sa.Numeric(20, 4), nullable=False),
        sa.Column("current_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("upside_downside_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("calculation_timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="valuation",
    )
    op.create_index(
        "ix_valuation_model_company_run", "valuation_model",
        ["company_id", "research_run_id"], schema="valuation",
    )

    op.create_table(
        "scenario",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("scenario_type", _enum("scenario_type"), nullable=False),
        sa.Column("revenue_cagr", sa.Numeric(10, 6), nullable=True),
        sa.Column("ebitda_margin", sa.Numeric(10, 6), nullable=True),
        sa.Column("eps_growth", sa.Numeric(10, 6), nullable=True),
        sa.Column("fcf_growth", sa.Numeric(10, 6), nullable=True),
        sa.Column("exit_multiple", sa.Numeric(10, 4), nullable=True),
        sa.Column("valuation_range_low", sa.Numeric(20, 4), nullable=True),
        sa.Column("valuation_range_high", sa.Numeric(20, 4), nullable=True),
        sa.Column("key_assumptions", JSONB, nullable=True),
        sa.Column("what_must_go_right", ARRAY(sa.Text), nullable=True),
        sa.Column("what_can_go_wrong", ARRAY(sa.Text), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "research_run_id", "scenario_type", name="uq_scenario_company_run_type"),
        schema="valuation",
    )

    # -- thesis schema -------------------------------------------------------
    op.create_table(
        "investment_thesis",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("one_line_thesis", sa.String(1000), nullable=False),
        sa.Column("business_quality_summary", sa.Text, nullable=True),
        sa.Column("moat_summary", sa.Text, nullable=True),
        sa.Column("growth_summary", sa.Text, nullable=True),
        sa.Column("management_summary", sa.Text, nullable=True),
        sa.Column("financial_quality_summary", sa.Text, nullable=True),
        sa.Column("valuation_summary", sa.Text, nullable=True),
        sa.Column("bear_case", sa.Text, nullable=True),
        sa.Column("bull_case", sa.Text, nullable=True),
        sa.Column("key_monitoring_metrics", JSONB, nullable=True),
        sa.Column("thesis_invalidation_conditions", ARRAY(sa.Text), nullable=True),
        sa.Column("overall_confidence", _enum("confidence_level"), nullable=False),
        sa.Column("fact_vs_inference_labels", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="thesis",
    )
    op.create_index(
        "ix_investment_thesis_company_version",
        "investment_thesis",
        ["company_id", sa.text("version DESC")],
        schema="thesis",
    )

    op.create_table(
        "thesis_version",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("thesis_id", sa.Uuid, sa.ForeignKey("thesis.investment_thesis.id"), nullable=False),
        sa.Column("previous_thesis_id", sa.Uuid, sa.ForeignKey("thesis.investment_thesis.id"), nullable=True),
        sa.Column("change_summary", sa.Text, nullable=False),
        sa.Column("change_trigger", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="thesis",
    )
    op.create_index("ix_thesis_version_company", "thesis_version", ["company_id"], schema="thesis")

    op.create_table(
        "risk",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("risk_type", _enum("risk_type"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", _enum("severity"), nullable=False),
        sa.Column("likelihood", _enum("likelihood"), nullable=False),
        sa.Column("mitigation", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="thesis",
    )
    op.create_index("ix_risk_company_run", "risk", ["company_id", "research_run_id"], schema="thesis")

    op.create_table(
        "risk_evidence",
        sa.Column(
            "risk_id", sa.Uuid,
            sa.ForeignKey("thesis.risk.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="thesis",
    )

    op.create_table(
        "catalyst",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("expected_timeline", sa.String(200), nullable=True),
        sa.Column("impact", _enum("catalyst_impact"), nullable=False),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="thesis",
    )
    op.create_index("ix_catalyst_company_run", "catalyst", ["company_id", "research_run_id"], schema="thesis")

    op.create_table(
        "catalyst_evidence",
        sa.Column(
            "catalyst_id", sa.Uuid,
            sa.ForeignKey("thesis.catalyst.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="thesis",
    )

    op.create_table(
        "company_score",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=False),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=False),
        sa.Column("dimension", _enum("score_dimension"), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("sub_scores", JSONB, nullable=True),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "company_id", "research_run_id", "dimension",
            name="uq_company_score_company_run_dimension",
        ),
        schema="thesis",
    )

    op.create_table(
        "company_score_evidence",
        sa.Column(
            "company_score_id", sa.Uuid,
            sa.ForeignKey("thesis.company_score.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "evidence_id", sa.Uuid,
            sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), primary_key=True,
        ),
        schema="thesis",
    )


def downgrade() -> None:
    # -- thesis schema (reverse order) ---------------------------------------
    op.drop_table("company_score_evidence", schema="thesis")
    op.drop_table("company_score", schema="thesis")
    op.drop_table("catalyst_evidence", schema="thesis")
    op.drop_table("catalyst", schema="thesis")
    op.drop_table("risk_evidence", schema="thesis")
    op.drop_table("risk", schema="thesis")
    op.drop_table("thesis_version", schema="thesis")
    op.drop_table("investment_thesis", schema="thesis")

    # -- valuation schema ----------------------------------------------------
    op.drop_table("scenario", schema="valuation")
    op.drop_table("valuation_model", schema="valuation")

    # -- analysis schema -----------------------------------------------------
    op.drop_table("macro_indicator", schema="analysis")
    op.drop_table("industry_data", schema="analysis")
    op.drop_table("competitor", schema="analysis")
    op.drop_table("growth_opportunity_evidence", schema="analysis")
    op.drop_table("growth_opportunity", schema="analysis")
    op.drop_table("moat_assessment_evidence", schema="analysis")
    op.drop_table("moat_assessment", schema="analysis")

    # -- governance schema ---------------------------------------------------
    op.drop_table("corporate_announcement", schema="governance")
    op.drop_table("corporate_action", schema="governance")
    op.drop_table("promoter_pledge", schema="governance")
    op.drop_table("shareholding", schema="governance")

    # -- financial schema ----------------------------------------------------
    op.drop_table("quarterly_result", schema="financial")
    op.drop_table("financial_metric", schema="financial")
    op.drop_table("financial_statement", schema="financial")

    # -- research schema -----------------------------------------------------
    op.drop_table("research_finding_evidence", schema="research")
    op.drop_table("research_finding", schema="research")
    op.drop_table("research_run", schema="research")
    op.drop_table("management_statement", schema="research")
    op.drop_table("evidence", schema="research")
    op.drop_table("research_document", schema="research")

    # -- company schema ------------------------------------------------------
    op.drop_table("security", schema="company")
    op.drop_table("company", schema="company")
    op.drop_table("classification", schema="company")
    op.drop_table("exchange", schema="company")

    # -- enum types ----------------------------------------------------------
    for name, _values in reversed(ENUM_TYPES):
        op.execute(f"DROP TYPE IF EXISTS {name}")
