"""Phase 7: Research run infrastructure — new tables, evolved columns, status enum migration.

Migrates research_run.status from PostgreSQL native enum to VARCHAR + CHECK constraint.
Adds new columns to research_run, research_finding, thesis_version.
Creates research_run_step, agent_execution, research_artifact, research_run_source tables.

Revision ID: 004
Revises: 003
Create Date: 2026-09-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESEARCH_RUN_STATUSES = (
    "'CREATED', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL', 'CANCELLED'"
)
STEP_STATUSES = "'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED'"
EXECUTION_STATUSES = "'RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'TRUNCATED'"


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Migrate research_run.status from PG enum to VARCHAR + CHECK
    # -----------------------------------------------------------------------

    # Convert column type from enum to varchar
    op.execute(
        "ALTER TABLE research.research_run "
        "ALTER COLUMN status TYPE VARCHAR(20) USING status::text"
    )

    # Migrate INCOMPLETE → PARTIAL in existing data
    op.execute(
        "UPDATE research.research_run SET status = 'PARTIAL' WHERE status = 'INCOMPLETE'"
    )

    # Change server default from RUNNING to CREATED
    op.execute(
        "ALTER TABLE research.research_run "
        "ALTER COLUMN status SET DEFAULT 'CREATED'"
    )

    # Add CHECK constraint
    op.execute(
        "ALTER TABLE research.research_run "
        f"ADD CONSTRAINT ck_research_run_status_valid "
        f"CHECK (status IN ({RESEARCH_RUN_STATUSES}))"
    )

    # Drop the old PG enum type
    op.execute("DROP TYPE IF EXISTS research_run_status")

    # -----------------------------------------------------------------------
    # 2. Add new columns to research_run
    # -----------------------------------------------------------------------

    op.add_column(
        "research_run",
        sa.Column("run_type", sa.String(50), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column("trigger_type", sa.String(50), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column(
            "parent_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id"),
            nullable=True,
        ),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column("observation_date", sa.Date, nullable=True),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column("configuration", JSONB, nullable=True),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column("error_summary", sa.Text, nullable=True),
        schema="research",
    )
    # TimestampMixin columns (created_at may already exist via started_at pattern)
    op.add_column(
        "research_run",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="research",
    )
    op.add_column(
        "research_run",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="research",
    )

    # Indexes for new columns
    op.create_index(
        "ix_research_run_parent",
        "research_run",
        ["parent_run_id"],
        schema="research",
    )
    op.create_index(
        "ix_research_run_observation",
        "research_run",
        ["company_id", sa.text("observation_date DESC")],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 3. Add new columns to research_finding
    # -----------------------------------------------------------------------

    # agent_execution_id FK will be added after agent_execution table is created
    op.add_column(
        "research_finding",
        sa.Column("observation_date", sa.Date, nullable=True),
        schema="research",
    )
    op.add_column(
        "research_finding",
        sa.Column("source_publication_date", sa.Date, nullable=True),
        schema="research",
    )
    op.add_column(
        "research_finding",
        sa.Column("calculation_version", sa.String(50), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_finding",
        sa.Column(
            "supersedes_finding_id",
            sa.Uuid,
            sa.ForeignKey("research.research_finding.id"),
            nullable=True,
        ),
        schema="research",
    )

    op.create_index(
        "ix_research_finding_observation_date",
        "research_finding",
        ["research_run_id", "observation_date"],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 4. Add new columns to thesis_version
    # -----------------------------------------------------------------------

    op.add_column(
        "thesis_version",
        sa.Column(
            "research_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id"),
            nullable=True,
        ),
        schema="thesis",
    )
    op.add_column(
        "thesis_version",
        sa.Column("snapshot_data", JSONB, nullable=True),
        schema="thesis",
    )
    op.add_column(
        "thesis_version",
        sa.Column("key_changes", JSONB, nullable=True),
        schema="thesis",
    )

    # -----------------------------------------------------------------------
    # 5. Create research_run_step table
    # -----------------------------------------------------------------------

    op.create_table(
        "research_run_step",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "research_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("input_state_hash", sa.String(64), nullable=True),
        sa.Column("output_state_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({STEP_STATUSES})",
            name="ck_research_run_step_status_valid",
        ),
        schema="research",
    )
    op.create_index(
        "ix_research_run_step_run_id",
        "research_run_step",
        ["research_run_id"],
        schema="research",
    )
    op.create_index(
        "ix_research_run_step_status",
        "research_run_step",
        ["research_run_id", "status"],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 6. Create agent_execution table
    # -----------------------------------------------------------------------

    op.create_table(
        "agent_execution",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "research_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run_step.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column(
            "attempt_number",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "input_tokens",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_tokens",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("model_provider", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_config", JSONB, nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("tool_versions", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column(
            "findings_produced",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({EXECUTION_STATUSES})",
            name="ck_agent_execution_status_valid",
        ),
        schema="research",
    )
    op.create_index(
        "ix_agent_execution_run_id",
        "agent_execution",
        ["research_run_id"],
        schema="research",
    )
    op.create_index(
        "ix_agent_execution_step_id",
        "agent_execution",
        ["step_id"],
        schema="research",
    )
    op.create_index(
        "ix_agent_execution_agent_name",
        "agent_execution",
        ["research_run_id", "agent_name"],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 7. Add agent_execution_id FK to research_finding (now that table exists)
    # -----------------------------------------------------------------------

    op.add_column(
        "research_finding",
        sa.Column(
            "agent_execution_id",
            sa.Uuid,
            sa.ForeignKey("research.agent_execution.id"),
            nullable=True,
        ),
        schema="research",
    )
    op.create_index(
        "ix_research_finding_execution_id",
        "research_finding",
        ["agent_execution_id"],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 8. Create research_artifact table
    # -----------------------------------------------------------------------

    op.create_table(
        "research_artifact",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "research_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_execution_id",
            sa.Uuid,
            sa.ForeignKey("research.agent_execution.id"),
            nullable=True,
        ),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("inline_content", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="research",
    )
    op.create_index(
        "ix_research_artifact_run_id",
        "research_artifact",
        ["research_run_id"],
        schema="research",
    )
    op.create_index(
        "ix_research_artifact_type",
        "research_artifact",
        ["research_run_id", "artifact_type"],
        schema="research",
    )

    # -----------------------------------------------------------------------
    # 9. Create research_run_source table
    # -----------------------------------------------------------------------

    op.create_table(
        "research_run_source",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "research_run_id",
            sa.Uuid,
            sa.ForeignKey("research.research_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid,
            sa.ForeignKey("research.research_document.id"),
            nullable=False,
        ),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("access_type", sa.String(50), nullable=False),
        sa.UniqueConstraint(
            "research_run_id",
            "document_id",
            name="uq_research_run_source_run_doc",
        ),
        schema="research",
    )
    op.create_index(
        "ix_research_run_source_run_id",
        "research_run_source",
        ["research_run_id"],
        schema="research",
    )
    op.create_index(
        "ix_research_run_source_document_id",
        "research_run_source",
        ["document_id"],
        schema="research",
    )


def downgrade() -> None:
    # -----------------------------------------------------------------------
    # Drop new tables (reverse order of creation)
    # -----------------------------------------------------------------------

    op.drop_index("ix_research_run_source_document_id", "research_run_source", schema="research")
    op.drop_index("ix_research_run_source_run_id", "research_run_source", schema="research")
    op.drop_table("research_run_source", schema="research")

    op.drop_index("ix_research_artifact_type", "research_artifact", schema="research")
    op.drop_index("ix_research_artifact_run_id", "research_artifact", schema="research")
    op.drop_table("research_artifact", schema="research")

    # Remove agent_execution_id from research_finding (before dropping agent_execution)
    op.drop_index("ix_research_finding_execution_id", "research_finding", schema="research")
    op.drop_column("research_finding", "agent_execution_id", schema="research")

    op.drop_index("ix_agent_execution_agent_name", "agent_execution", schema="research")
    op.drop_index("ix_agent_execution_step_id", "agent_execution", schema="research")
    op.drop_index("ix_agent_execution_run_id", "agent_execution", schema="research")
    op.drop_table("agent_execution", schema="research")

    op.drop_index("ix_research_run_step_status", "research_run_step", schema="research")
    op.drop_index("ix_research_run_step_run_id", "research_run_step", schema="research")
    op.drop_table("research_run_step", schema="research")

    # -----------------------------------------------------------------------
    # Remove new columns from thesis_version
    # -----------------------------------------------------------------------

    op.drop_column("thesis_version", "key_changes", schema="thesis")
    op.drop_column("thesis_version", "snapshot_data", schema="thesis")
    op.drop_column("thesis_version", "research_run_id", schema="thesis")

    # -----------------------------------------------------------------------
    # Remove new columns from research_finding
    # -----------------------------------------------------------------------

    op.drop_index("ix_research_finding_observation_date", "research_finding", schema="research")
    op.drop_column("research_finding", "supersedes_finding_id", schema="research")
    op.drop_column("research_finding", "calculation_version", schema="research")
    op.drop_column("research_finding", "source_publication_date", schema="research")
    op.drop_column("research_finding", "observation_date", schema="research")

    # -----------------------------------------------------------------------
    # Remove new columns from research_run
    # -----------------------------------------------------------------------

    op.drop_index("ix_research_run_observation", "research_run", schema="research")
    op.drop_index("ix_research_run_parent", "research_run", schema="research")
    op.drop_column("research_run", "updated_at", schema="research")
    op.drop_column("research_run", "created_at", schema="research")
    op.drop_column("research_run", "error_summary", schema="research")
    op.drop_column("research_run", "configuration", schema="research")
    op.drop_column("research_run", "observation_date", schema="research")
    op.drop_column("research_run", "parent_run_id", schema="research")
    op.drop_column("research_run", "trigger_type", schema="research")
    op.drop_column("research_run", "run_type", schema="research")

    # -----------------------------------------------------------------------
    # Restore research_run.status to PG native enum
    # -----------------------------------------------------------------------

    # Drop CHECK constraint
    op.execute(
        "ALTER TABLE research.research_run "
        "DROP CONSTRAINT IF EXISTS ck_research_run_status_valid"
    )

    # Recreate PG enum type
    op.execute(
        "CREATE TYPE research_run_status AS ENUM "
        "('RUNNING', 'COMPLETED', 'FAILED', 'INCOMPLETE')"
    )

    # Migrate PARTIAL back to INCOMPLETE
    op.execute(
        "UPDATE research.research_run SET status = 'INCOMPLETE' WHERE status = 'PARTIAL'"
    )

    # Remove values that don't exist in the old enum
    op.execute(
        "UPDATE research.research_run SET status = 'RUNNING' "
        "WHERE status IN ('CREATED', 'QUEUED', 'CANCELLED')"
    )

    # Restore default
    op.execute(
        "ALTER TABLE research.research_run "
        "ALTER COLUMN status SET DEFAULT 'RUNNING'"
    )

    # Convert back to PG enum
    op.execute(
        "ALTER TABLE research.research_run "
        "ALTER COLUMN status TYPE research_run_status "
        "USING status::research_run_status"
    )
