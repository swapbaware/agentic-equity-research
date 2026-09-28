"""Add evidence subsystem tables: source, document_version, claim, claim_evidence, source_reliability.

Also adds source_id FK to research_document and new enum types.

Revision ID: 003
Revises: 002
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ENUM_TYPES: list[tuple[str, list[str]]] = [
    ("claim_type", [
        "FACT", "CALCULATION", "MANAGEMENT_CLAIM",
        "EXTERNAL_ANALYST_VIEW", "AI_INFERENCE", "ASSUMPTION",
    ]),
    ("source_type", [
        "EXCHANGE", "REGULATOR", "COMPANY", "NEWS",
        "RESEARCH_FIRM", "GOVERNMENT", "INDUSTRY_BODY", "OTHER",
    ]),
]


def _enum(name: str) -> sa.Enum:
    return sa.Enum(name=name, create_type=False)


def upgrade() -> None:
    # 1. Create new enum types
    for name, values in NEW_ENUM_TYPES:
        sa.Enum(*values, name=name).create(op.get_bind(), checkfirst=True)

    # 2. Create source table
    op.create_table(
        "source",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", _enum("source_type"), nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("default_tier", _enum("source_tier"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_source_name"),
        schema="research",
    )
    op.create_index("ix_source_type", "source", ["source_type"], schema="research")

    # 3. Add source_id to research_document
    op.add_column(
        "research_document",
        sa.Column("source_id", sa.Uuid, sa.ForeignKey("research.source.id"), nullable=True),
        schema="research",
    )

    # 4. Create document_version table
    op.create_table(
        "document_version",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("document_id", sa.Uuid, sa.ForeignKey("research.research_document.id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("changes_summary", sa.Text, nullable=True),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_doc_num"),
        schema="research",
    )
    op.create_index("ix_document_version_document", "document_version", ["document_id"], schema="research")

    # 5. Create claim table
    op.create_table(
        "claim",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("claim_type", _enum("claim_type"), nullable=False),
        sa.Column("company_id", sa.Uuid, sa.ForeignKey("company.company.id"), nullable=True),
        sa.Column("research_run_id", sa.Uuid, sa.ForeignKey("research.research_run.id"), nullable=True),
        sa.Column("source_agent", sa.String(100), nullable=True),
        sa.Column("confidence", _enum("confidence_level"), nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="research",
    )
    op.create_index("ix_claim_company_run", "claim", ["company_id", "research_run_id"], schema="research")
    op.create_index("ix_claim_type", "claim", ["claim_type"], schema="research")
    op.create_index("ix_claim_verified", "claim", ["is_verified"], schema="research")

    # 6. Create claim_evidence table
    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("claim_id", sa.Uuid, sa.ForeignKey("research.claim.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.Uuid, sa.ForeignKey("research.evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relevance", sa.String(200), nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_pair"),
        schema="research",
    )

    # 7. Create source_reliability table
    op.create_table(
        "source_reliability",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("source_id", sa.Uuid, sa.ForeignKey("research.source.id"), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reliability_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("total_claims", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("verified_claims", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("refuted_claims", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text, nullable=True),
        schema="research",
    )
    op.create_index(
        "ix_source_reliability_source_date",
        "source_reliability",
        ["source_id", sa.text("assessed_at DESC")],
        schema="research",
    )


def downgrade() -> None:
    op.drop_table("source_reliability", schema="research")
    op.drop_table("claim_evidence", schema="research")
    op.drop_index("ix_claim_verified", "claim", schema="research")
    op.drop_index("ix_claim_type", "claim", schema="research")
    op.drop_index("ix_claim_company_run", "claim", schema="research")
    op.drop_table("claim", schema="research")
    op.drop_index("ix_document_version_document", "document_version", schema="research")
    op.drop_table("document_version", schema="research")
    op.drop_column("research_document", "source_id", schema="research")
    op.drop_index("ix_source_type", "source", schema="research")
    op.drop_table("source", schema="research")

    for name, values in reversed(NEW_ENUM_TYPES):
        sa.Enum(*values, name=name).drop(op.get_bind(), checkfirst=True)
