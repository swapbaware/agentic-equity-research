"""Add updated_at column to research_run_step for TimestampMixin compliance.

Revision ID: 005
Revises: 004
Create Date: 2026-09-30
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_run_step",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="research",
    )


def downgrade() -> None:
    op.drop_column("research_run_step", "updated_at", schema="research")
