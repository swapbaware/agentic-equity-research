"""Create database schemas and enable extensions.

Revision ID: 001
Revises:
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = [
    "company",
    "financial",
    "governance",
    "research",
    "analysis",
    "valuation",
    "thesis",
    "screening",
    "portfolio",
    "auth",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
