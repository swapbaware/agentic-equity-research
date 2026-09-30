"""Add target_type discriminator, nullable company_id, and industry_id FK to research_run.

Supports Industry Research Runs (Phase 9) while preserving existing Company
Research behavior.  Existing rows receive target_type='company' via DEFAULT.
An XOR CHECK enforces that exactly one of company_id / industry_id is populated,
matching the target_type value.

Revision ID: 006
Revises: 005
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "research"
TABLE = "research_run"


def upgrade() -> None:
    # Step 1: Add target_type discriminator (all existing rows become 'company').
    op.add_column(
        TABLE,
        sa.Column(
            "target_type",
            sa.String(50),
            nullable=False,
            server_default="company",
        ),
        schema=SCHEMA,
    )

    # Step 2: Make company_id nullable (required for industry runs).
    op.alter_column(
        TABLE,
        "company_id",
        existing_type=sa.Uuid,
        nullable=True,
        schema=SCHEMA,
    )

    # Step 3: Add industry_id FK to company.classification.
    op.add_column(
        TABLE,
        sa.Column("industry_id", sa.Uuid, nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_research_run_industry_id",
        TABLE,
        "classification",
        ["industry_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema="company",
    )

    # Step 4: XOR check constraint — exactly one target FK populated.
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
        ADD CONSTRAINT chk_research_run_target CHECK (
            (target_type = 'company'  AND company_id IS NOT NULL AND industry_id IS NULL)
            OR
            (target_type = 'industry' AND company_id IS NULL     AND industry_id IS NOT NULL)
        )
        """
    )

    # Step 5: Partial composite index for industry lookups.
    op.create_index(
        "ix_research_run_industry",
        TABLE,
        ["industry_id", sa.text("started_at DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("industry_id IS NOT NULL"),
    )

    # Step 6: Composite index on target_type + started_at.
    op.create_index(
        "ix_research_run_target_type",
        TABLE,
        ["target_type", sa.text("started_at DESC")],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Guard: refuse to downgrade if industry runs exist — they would become
    # invalid once company_id is forced NOT NULL and the XOR constraint is
    # dropped.  This is a deliberate safety measure (Phase 9 architecture §25).
    conn = op.get_bind()
    result = conn.execute(sa.text(f"SELECT count(*) FROM {SCHEMA}.{TABLE} WHERE target_type = 'industry'"))
    industry_count = result.scalar()
    if industry_count:
        raise RuntimeError(
            f"Cannot downgrade: {industry_count} industry research run(s) exist. "
            "Delete or migrate them before rolling back this migration."
        )

    # Reverse Step 6
    op.drop_index(
        "ix_research_run_target_type",
        table_name=TABLE,
        schema=SCHEMA,
    )

    # Reverse Step 5
    op.drop_index(
        "ix_research_run_industry",
        table_name=TABLE,
        schema=SCHEMA,
    )

    # Reverse Step 4
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} DROP CONSTRAINT chk_research_run_target")

    # Reverse Step 3
    op.drop_constraint(
        "fk_research_run_industry_id",
        TABLE,
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column(TABLE, "industry_id", schema=SCHEMA)

    # Reverse Step 2: Restore NOT NULL on company_id (safe — guard above
    # ensured no NULL company_id rows remain).
    op.alter_column(
        TABLE,
        "company_id",
        existing_type=sa.Uuid,
        nullable=False,
        schema=SCHEMA,
    )

    # Reverse Step 1
    op.drop_column(TABLE, "target_type", schema=SCHEMA)
