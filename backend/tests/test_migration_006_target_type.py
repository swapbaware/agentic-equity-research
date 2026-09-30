"""Tests for migration 006: research_run target_type discriminator.

Verifies the Alembic migration script structure, ORM model alignment,
and downgrade safety guard.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

from app.models.research import ResearchRun

if TYPE_CHECKING:
    import types

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "006_research_run_target_type.py"


# ---------------------------------------------------------------------------
# Migration script structure tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def migration_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_006",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigrationMetadata:
    def test_revision_id(self, migration_module: types.ModuleType) -> None:
        assert migration_module.revision == "006"

    def test_down_revision(self, migration_module: types.ModuleType) -> None:
        assert migration_module.down_revision == "005"

    def test_has_upgrade_function(self, migration_module: types.ModuleType) -> None:
        assert callable(getattr(migration_module, "upgrade", None))

    def test_has_downgrade_function(self, migration_module: types.ModuleType) -> None:
        assert callable(getattr(migration_module, "downgrade", None))


# ---------------------------------------------------------------------------
# ORM model alignment tests
# ---------------------------------------------------------------------------


class TestResearchRunTargetTypeModel:
    """Verify the ORM model declares the new columns correctly."""

    def test_target_type_column_exists(self) -> None:
        col = ResearchRun.__table__.columns["target_type"]
        assert col is not None
        assert str(col.type) == "VARCHAR(50)"
        assert col.nullable is False
        assert col.server_default is not None

    def test_target_type_default_is_company(self) -> None:
        col = ResearchRun.__table__.columns["target_type"]
        assert col.server_default.arg == "company"

    def test_company_id_is_nullable(self) -> None:
        col = ResearchRun.__table__.columns["company_id"]
        assert col.nullable is True

    def test_industry_id_column_exists(self) -> None:
        col = ResearchRun.__table__.columns["industry_id"]
        assert col is not None
        assert col.nullable is True

    def test_industry_id_has_foreign_key(self) -> None:
        col = ResearchRun.__table__.columns["industry_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "company.classification.id" in fk_targets

    def test_company_id_foreign_key_preserved(self) -> None:
        col = ResearchRun.__table__.columns["company_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "company.company.id" in fk_targets

    def test_run_type_unchanged(self) -> None:
        col = ResearchRun.__table__.columns["run_type"]
        assert str(col.type) == "VARCHAR(50)"
        assert col.nullable is True

    def test_xor_check_constraint_declared(self) -> None:
        constraints = [
            arg for arg in ResearchRun.__table_args__ if hasattr(arg, "sqltext") and "target_type" in str(arg.sqltext)
        ]
        assert len(constraints) == 1
        text = str(constraints[0].sqltext)
        assert "company_id IS NOT NULL" in text
        assert "industry_id IS NULL" in text or "industry_id IS NOT NULL" in text

    def test_industry_index_declared(self) -> None:
        index_names = {arg.name for arg in ResearchRun.__table_args__ if isinstance(arg, sa.Index)}
        assert "ix_research_run_industry" in index_names

    def test_target_type_index_declared(self) -> None:
        index_names = {arg.name for arg in ResearchRun.__table_args__ if isinstance(arg, sa.Index)}
        assert "ix_research_run_target_type" in index_names


class TestResearchRunModelConstruction:
    """Verify model can be constructed for both target types."""

    def test_company_run_default_target_type(self) -> None:
        run = ResearchRun(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
        )
        assert run.company_id is not None
        assert run.industry_id is None

    def test_industry_run_construction(self) -> None:
        run = ResearchRun(
            industry_id=uuid.uuid4(),
            target_type="industry",
            initiated_by="test_user",
        )
        assert run.industry_id is not None
        assert run.company_id is None
        assert run.target_type == "industry"

    def test_run_type_still_independent(self) -> None:
        run = ResearchRun(
            company_id=uuid.uuid4(),
            initiated_by="test_user",
            run_type="FULL",
            target_type="company",
        )
        assert run.run_type == "FULL"
        assert run.target_type == "company"
