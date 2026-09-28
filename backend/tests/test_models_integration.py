"""Integration tests for domain models — require a live PostgreSQL database.

Run with: pytest tests/test_models_integration.py -m integration

These tests verify actual database operations: table creation, constraints,
cascades, and data integrity. Skip automatically when DATABASE_URL is not set
or the database is unreachable.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Classification,
    Company,
    Evidence,
    Exchange,
    FinancialMetric,
    FinancialStatement,
    ResearchDocument,
    ResearchFinding,
    ResearchRun,
    Security,
)
from app.models.enums import (
    ClassificationLevel,
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    MetricUnit,
    PeriodType,
    ResearchRunStatus,
    SecurityType,
    SourceTier,
    StatementType,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/equity_research_test",
)

pytestmark = pytest.mark.integration


def _can_connect() -> bool:
    """Quick check: can we reach the test database?"""
    try:
        sync_url = DATABASE_URL.replace("+asyncpg", "")
        engine = sa.create_engine(sync_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


skip_no_db = pytest.mark.skipif(not _can_connect(), reason="Test database not available")


@pytest.fixture(scope="module")
def engine():
    eng = create_async_engine(DATABASE_URL, echo=False)
    yield eng


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
async def session(session_factory) -> AsyncSession:  # type: ignore[misc]
    async with session_factory() as sess:
        yield sess
        await sess.rollback()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

@skip_no_db
class TestSchemaCreation:
    async def test_create_all_tables(self, engine) -> None:
        """Verify that all tables can be created from metadata on a clean DB."""
        async with engine.begin() as conn:
            for schema in ["company", "financial", "governance", "research", "analysis", "valuation", "thesis"]:
                await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            await conn.run_sync(Base.metadata.create_all)

        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    "SELECT schemaname, tablename FROM pg_tables "
                    "WHERE schemaname IN ('company','financial','governance','research','analysis','valuation','thesis') "
                    "ORDER BY schemaname, tablename"
                )
            )
            tables = result.fetchall()
            table_names = {f"{row[0]}.{row[1]}" for row in tables}
            assert "company.exchange" in table_names
            assert "company.company" in table_names
            assert "financial.financial_statement" in table_names
            assert "research.evidence" in table_names
            assert "thesis.investment_thesis" in table_names

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            for schema in reversed(["company", "financial", "governance", "research", "analysis", "valuation", "thesis"]):
                await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


# ---------------------------------------------------------------------------
# CRUD smoke tests
# ---------------------------------------------------------------------------

@skip_no_db
class TestCRUD:
    @pytest.fixture(autouse=True)
    async def _setup_schema(self, engine):
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            for schema in ["company", "financial", "governance", "research", "analysis", "valuation", "thesis"]:
                await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            await conn.run_sync(Base.metadata.create_all)
        yield
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            for schema in reversed(["company", "financial", "governance", "research", "analysis", "valuation", "thesis"]):
                await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))

    async def test_insert_exchange(self, session: AsyncSession) -> None:
        ex = Exchange(id=uuid.uuid4(), code="NSE", name="National Stock Exchange of India")
        session.add(ex)
        await session.flush()
        result = await session.execute(
            sa.select(Exchange).where(Exchange.code == "NSE")
        )
        loaded = result.scalar_one()
        assert loaded.name == "National Stock Exchange of India"

    async def test_insert_company_with_security(self, session: AsyncSession) -> None:
        exchange = Exchange(id=uuid.uuid4(), code="BSE", name="Bombay Stock Exchange")
        session.add(exchange)
        await session.flush()

        company = Company(
            id=uuid.uuid4(),
            name="Infosys Limited",
            isin="INE009A01021",
            nse_symbol="INFY",
        )
        session.add(company)
        await session.flush()

        security = Security(
            id=uuid.uuid4(),
            company_id=company.id,
            exchange_id=exchange.id,
            symbol="INFY",
            security_type=SecurityType.EQUITY,
            face_value=Decimal("5.0000"),
        )
        session.add(security)
        await session.flush()

        result = await session.execute(
            sa.select(Security).where(Security.company_id == company.id)
        )
        loaded = result.scalar_one()
        assert loaded.symbol == "INFY"
        assert loaded.face_value == Decimal("5.0000")

    async def test_financial_metric_decimal_precision(self, session: AsyncSession) -> None:
        company = Company(id=uuid.uuid4(), name="Test Corp", isin="INE000T00001")
        session.add(company)
        await session.flush()

        doc = ResearchDocument(
            id=uuid.uuid4(),
            document_type=DocumentType.QUARTERLY_RESULT,
            title="Q1 FY25 Results",
            source_tier=SourceTier.TIER_1,
            source_name="BSE",
        )
        session.add(doc)
        await session.flush()

        stmt = FinancialStatement(
            id=uuid.uuid4(),
            company_id=company.id,
            statement_type=StatementType.INCOME_STATEMENT,
            period_type=PeriodType.QUARTERLY,
            fiscal_year=2025,
            fiscal_quarter=1,
            period_start=date(2024, 4, 1),
            period_end=date(2024, 6, 30),
            source_document_id=doc.id,
        )
        session.add(stmt)
        await session.flush()

        metric = FinancialMetric(
            id=uuid.uuid4(),
            statement_id=stmt.id,
            metric_name="revenue",
            value=Decimal("123456789.1234"),
            unit=MetricUnit.CURRENCY,
        )
        session.add(metric)
        await session.flush()

        loaded = await session.get(FinancialMetric, metric.id)
        assert loaded is not None
        assert loaded.value == Decimal("123456789.1234")

    async def test_unique_constraint_violation(self, session: AsyncSession) -> None:
        ex1 = Exchange(id=uuid.uuid4(), code="NSE", name="NSE 1")
        ex2 = Exchange(id=uuid.uuid4(), code="NSE", name="NSE 2")
        session.add(ex1)
        await session.flush()
        session.add(ex2)
        with pytest.raises(sa.exc.IntegrityError):
            await session.flush()

    async def test_research_finding_evidence_junction(self, session: AsyncSession) -> None:
        company = Company(id=uuid.uuid4(), name="Test Corp 2", isin="INE000T00002")
        session.add(company)
        await session.flush()

        doc = ResearchDocument(
            id=uuid.uuid4(),
            document_type=DocumentType.ANNUAL_REPORT,
            title="Annual Report FY25",
            source_tier=SourceTier.TIER_1,
            source_name="Company Website",
        )
        session.add(doc)
        await session.flush()

        evidence = Evidence(
            id=uuid.uuid4(),
            document_id=doc.id,
            evidence_type=EvidenceType.FACT,
            claim="Revenue grew 20%",
            confidence=ConfidenceLevel.HIGH,
            extracted_by="test",
        )
        session.add(evidence)
        await session.flush()

        run = ResearchRun(
            id=uuid.uuid4(),
            company_id=company.id,
            initiated_by="test",
            status=ResearchRunStatus.RUNNING,
        )
        session.add(run)
        await session.flush()

        finding = ResearchFinding(
            id=uuid.uuid4(),
            research_run_id=run.id,
            agent_name="test_agent",
            finding_type=FindingType.FACT,
            category="financial",
            content="Revenue grew 20%",
            confidence=ConfidenceLevel.HIGH,
        )
        finding.evidences.append(evidence)
        session.add(finding)
        await session.flush()

        loaded = await session.get(ResearchFinding, finding.id)
        assert loaded is not None
