"""Unit tests for domain models — validates schema structure without a database."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models import (
    Base,
    Catalyst,
    Claim,
    ClaimEvidence,
    Classification,
    Company,
    CompanyScore,
    CompanyScreeningData,
    Competitor,
    CorporateAction,
    CorporateAnnouncement,
    DocumentVersion,
    Evidence,
    FinancialMetric,
    FinancialStatement,
    GrowthOpportunity,
    IndustryData,
    InvestmentThesis,
    MacroIndicator,
    ManagementStatement,
    MoatAssessment,
    PromoterPledge,
    QuarterlyResult,
    ResearchDocument,
    ResearchFinding,
    ResearchRun,
    Risk,
    SavedScreen,
    Scenario,
    Security,
    Shareholding,
    Source,
    SourceReliability,
    ThesisVersion,
    ValuationModel,
    catalyst_evidence,
    company_score_evidence,
    growth_opportunity_evidence,
    moat_assessment_evidence,
    research_finding_evidence,
    risk_evidence,
)
from app.models.company import Exchange
from app.models.enums import (
    CatalystImpact,
    ClaimType,
    ClassificationLevel,
    CompetitorRelevance,
    ConfidenceLevel,
    CorporateActionType,
    DocumentType,
    EvidenceType,
    FindingType,
    GrowthCategory,
    GrowthMaturity,
    Likelihood,
    ManagementStatementCategory,
    ManagementStatementStatus,
    MetricUnit,
    MoatStrength,
    MoatType,
    PeriodType,
    ResearchRunStatus,
    RiskType,
    ScenarioType,
    ScoreDimension,
    SecurityType,
    Severity,
    SourceTier,
    SourceType,
    StatementType,
    ValuationModelType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_MODELS: list[type] = [
    Exchange,
    Classification,
    Company,
    Security,
    FinancialStatement,
    FinancialMetric,
    QuarterlyResult,
    Shareholding,
    PromoterPledge,
    CorporateAction,
    CorporateAnnouncement,
    ResearchDocument,
    Evidence,
    ManagementStatement,
    ResearchRun,
    ResearchFinding,
    Source,
    DocumentVersion,
    Claim,
    ClaimEvidence,
    SourceReliability,
    MoatAssessment,
    GrowthOpportunity,
    Competitor,
    IndustryData,
    MacroIndicator,
    ValuationModel,
    Scenario,
    InvestmentThesis,
    ThesisVersion,
    Risk,
    Catalyst,
    CompanyScore,
    SavedScreen,
    CompanyScreeningData,
]

JUNCTION_TABLES: list[sa.Table] = [
    research_finding_evidence,
    moat_assessment_evidence,
    growth_opportunity_evidence,
    risk_evidence,
    catalyst_evidence,
    company_score_evidence,
]


# ---------------------------------------------------------------------------
# 1. All models registered in metadata
# ---------------------------------------------------------------------------

class TestMetadataRegistration:
    def test_all_models_have_tables(self) -> None:
        tables = Base.metadata.tables
        for model in ALL_MODELS:
            key = f"{model.__table__.schema}.{model.__tablename__}"
            assert key in tables, f"{model.__name__} not registered in metadata"

    def test_junction_tables_registered(self) -> None:
        tables = Base.metadata.tables
        for tbl in JUNCTION_TABLES:
            key = f"{tbl.schema}.{tbl.name}"
            assert key in tables, f"Junction table {tbl.name} not registered"

    def test_total_table_count(self) -> None:
        assert len(Base.metadata.tables) == len(ALL_MODELS) + len(JUNCTION_TABLES)


# ---------------------------------------------------------------------------
# 2. Schema assignment
# ---------------------------------------------------------------------------

SCHEMA_MAPPING: dict[str, list[type]] = {
    "company": [Exchange, Classification, Company, Security],
    "financial": [FinancialStatement, FinancialMetric, QuarterlyResult],
    "governance": [Shareholding, PromoterPledge, CorporateAction, CorporateAnnouncement],
    "research": [
        ResearchDocument, Evidence, ManagementStatement, ResearchRun, ResearchFinding,
        Source, DocumentVersion, Claim, ClaimEvidence, SourceReliability,
    ],
    "analysis": [MoatAssessment, GrowthOpportunity, Competitor, IndustryData, MacroIndicator],
    "valuation": [ValuationModel, Scenario],
    "thesis": [InvestmentThesis, ThesisVersion, Risk, Catalyst, CompanyScore],
}


class TestSchemaAssignment:
    @pytest.mark.parametrize("schema,models", SCHEMA_MAPPING.items())
    def test_models_in_correct_schema(self, schema: str, models: list[type]) -> None:
        for model in models:
            assert model.__table__.schema == schema, (
                f"{model.__name__} should be in {schema} schema, got {model.__table__.schema}"
            )


# ---------------------------------------------------------------------------
# 3. UUID primary keys
# ---------------------------------------------------------------------------

class TestPrimaryKeys:
    @pytest.mark.parametrize("model", ALL_MODELS)
    def test_uuid_primary_key(self, model: type) -> None:
        pk_cols = [c for c in model.__table__.columns if c.primary_key]
        assert len(pk_cols) == 1, f"{model.__name__} should have exactly one PK column"
        assert isinstance(pk_cols[0].type, sa.Uuid), f"{model.__name__}.id should be UUID type"


# ---------------------------------------------------------------------------
# 4. Timestamp columns
# ---------------------------------------------------------------------------

TIMESTAMP_MODELS = [m for m in ALL_MODELS if hasattr(m, "created_at")]


class TestTimestamps:
    @pytest.mark.parametrize("model", TIMESTAMP_MODELS)
    def test_has_created_at(self, model: type) -> None:
        col = model.__table__.c["created_at"]
        assert isinstance(col.type, sa.DateTime)
        assert col.server_default is not None

    @pytest.mark.parametrize("model", [m for m in TIMESTAMP_MODELS if hasattr(m, "updated_at")])
    def test_has_updated_at(self, model: type) -> None:
        col = model.__table__.c["updated_at"]
        assert isinstance(col.type, sa.DateTime)


# ---------------------------------------------------------------------------
# 5. Financial columns use NUMERIC, never FLOAT
# ---------------------------------------------------------------------------

NUMERIC_TABLES = [
    FinancialStatement,
    FinancialMetric,
    QuarterlyResult,
    Shareholding,
    PromoterPledge,
    Company,
    ValuationModel,
    Scenario,
    MoatAssessment,
    GrowthOpportunity,
    IndustryData,
    MacroIndicator,
    ResearchRun,
    CompanyScore,
]


class TestDecimalColumns:
    @pytest.mark.parametrize("model", NUMERIC_TABLES)
    def test_no_float_columns(self, model: type) -> None:
        for col in model.__table__.columns:
            assert not isinstance(col.type, sa.Float), (
                f"{model.__name__}.{col.name} uses Float — must use Numeric"
            )

    def test_financial_metric_value_is_numeric(self) -> None:
        col = FinancialMetric.__table__.c["value"]
        assert isinstance(col.type, sa.Numeric)

    def test_quarterly_result_revenue_is_numeric(self) -> None:
        col = QuarterlyResult.__table__.c["revenue"]
        assert isinstance(col.type, sa.Numeric)

    def test_valuation_model_implied_value_is_numeric(self) -> None:
        col = ValuationModel.__table__.c["implied_value_per_share"]
        assert isinstance(col.type, sa.Numeric)

    def test_shareholding_pcts_are_numeric(self) -> None:
        for col_name in ["promoter_holding_pct", "fii_holding_pct", "dii_holding_pct", "public_holding_pct"]:
            col = Shareholding.__table__.c[col_name]
            assert isinstance(col.type, sa.Numeric), f"Shareholding.{col_name} should be Numeric"


# ---------------------------------------------------------------------------
# 6. Unique constraints
# ---------------------------------------------------------------------------

class TestUniqueConstraints:
    @staticmethod
    def _has_unique(table: sa.Table, col_names: set[str]) -> bool:
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint) and {c.name for c in constraint.columns} == col_names:
                return True
        return False

    def test_company_isin_unique(self) -> None:
        assert self._has_unique(Company.__table__, {"isin"})

    def test_exchange_code_unique(self) -> None:
        assert self._has_unique(Exchange.__table__, {"code"})

    def test_classification_code_level_unique(self) -> None:
        assert self._has_unique(Classification.__table__, {"code", "level"})

    def test_security_company_exchange_unique(self) -> None:
        assert self._has_unique(Security.__table__, {"company_id", "exchange_id"})

    def test_quarterly_result_company_period_unique(self) -> None:
        assert self._has_unique(QuarterlyResult.__table__, {"company_id", "fiscal_year", "fiscal_quarter"})

    def test_shareholding_company_date_unique(self) -> None:
        assert self._has_unique(Shareholding.__table__, {"company_id", "as_of_date"})

    def test_promoter_pledge_company_date_unique(self) -> None:
        assert self._has_unique(PromoterPledge.__table__, {"company_id", "as_of_date"})

    def test_research_document_content_hash_unique(self) -> None:
        assert self._has_unique(ResearchDocument.__table__, {"content_hash"})

    def test_scenario_company_run_type_unique(self) -> None:
        assert self._has_unique(Scenario.__table__, {"company_id", "research_run_id", "scenario_type"})

    def test_company_score_unique(self) -> None:
        assert self._has_unique(CompanyScore.__table__, {"company_id", "research_run_id", "dimension"})


# ---------------------------------------------------------------------------
# 7. Foreign keys point to the right targets
# ---------------------------------------------------------------------------

class TestForeignKeys:
    @staticmethod
    def _fk_targets(table: sa.Table, col_name: str) -> set[str]:
        col = table.c[col_name]
        return {str(fk.target_fullname) for fk in col.foreign_keys}

    def test_security_company_fk(self) -> None:
        assert "company.company.id" in self._fk_targets(Security.__table__, "company_id")

    def test_security_exchange_fk(self) -> None:
        assert "company.exchange.id" in self._fk_targets(Security.__table__, "exchange_id")

    def test_financial_statement_company_fk(self) -> None:
        assert "company.company.id" in self._fk_targets(FinancialStatement.__table__, "company_id")

    def test_financial_statement_document_fk(self) -> None:
        assert "research.research_document.id" in self._fk_targets(
            FinancialStatement.__table__, "source_document_id"
        )

    def test_financial_metric_statement_fk(self) -> None:
        assert "financial.financial_statement.id" in self._fk_targets(
            FinancialMetric.__table__, "statement_id"
        )

    def test_evidence_document_fk(self) -> None:
        assert "research.research_document.id" in self._fk_targets(Evidence.__table__, "document_id")

    def test_research_finding_run_fk(self) -> None:
        assert "research.research_run.id" in self._fk_targets(ResearchFinding.__table__, "research_run_id")

    def test_moat_assessment_run_fk(self) -> None:
        assert "research.research_run.id" in self._fk_targets(MoatAssessment.__table__, "research_run_id")

    def test_investment_thesis_run_fk(self) -> None:
        assert "research.research_run.id" in self._fk_targets(InvestmentThesis.__table__, "research_run_id")

    def test_industry_data_classification_fk(self) -> None:
        assert "company.classification.id" in self._fk_targets(IndustryData.__table__, "industry_id")


# ---------------------------------------------------------------------------
# 8. Junction tables structure
# ---------------------------------------------------------------------------

class TestJunctionTables:
    @pytest.mark.parametrize(
        "table,col_a,col_b",
        [
            (research_finding_evidence, "research_finding_id", "evidence_id"),
            (moat_assessment_evidence, "moat_assessment_id", "evidence_id"),
            (growth_opportunity_evidence, "growth_opportunity_id", "evidence_id"),
            (risk_evidence, "risk_id", "evidence_id"),
            (catalyst_evidence, "catalyst_id", "evidence_id"),
            (company_score_evidence, "company_score_id", "evidence_id"),
        ],
    )
    def test_junction_has_composite_pk(self, table: sa.Table, col_a: str, col_b: str) -> None:
        pk_cols = {c.name for c in table.primary_key.columns}
        assert pk_cols == {col_a, col_b}

    @pytest.mark.parametrize("table", JUNCTION_TABLES)
    def test_junction_fks_have_cascade_delete(self, table: sa.Table) -> None:
        for col in table.columns:
            for fk in col.foreign_keys:
                assert fk.ondelete == "CASCADE", (
                    f"{table.name}.{col.name} FK should have CASCADE delete"
                )


# ---------------------------------------------------------------------------
# 9. Enum completeness
# ---------------------------------------------------------------------------

class TestEnumValues:
    def test_finding_type_matches_spec(self) -> None:
        expected = {
            "FACT", "CALCULATION", "MANAGEMENT_CLAIM", "ANALYST_OPINION",
            "AI_INFERENCE", "ASSUMPTION", "UNCERTAINTY",
        }
        assert {e.value for e in FindingType} == expected

    def test_moat_type_count(self) -> None:
        assert len(MoatType) == 16

    def test_score_dimension_count(self) -> None:
        assert len(ScoreDimension) == 10

    def test_source_tier_values(self) -> None:
        assert {e.value for e in SourceTier} == {"TIER_1", "TIER_2", "TIER_3"}

    def test_confidence_level_values(self) -> None:
        assert {e.value for e in ConfidenceLevel} == {"HIGH", "MEDIUM", "LOW"}

    def test_scenario_type_values(self) -> None:
        assert {e.value for e in ScenarioType} == {"BEAR", "BASE", "BULL"}

    def test_research_run_status_values(self) -> None:
        assert {e.value for e in ResearchRunStatus} == {"RUNNING", "COMPLETED", "FAILED", "INCOMPLETE"}

    def test_all_enums_are_str_enums(self) -> None:
        all_enums = [
            ClassificationLevel, SecurityType, StatementType, PeriodType, MetricUnit,
            CorporateActionType, DocumentType, SourceTier, EvidenceType, ConfidenceLevel,
            ManagementStatementCategory, ManagementStatementStatus, ResearchRunStatus,
            FindingType, ClaimType, SourceType, MoatType, MoatStrength, GrowthCategory,
            GrowthMaturity, CompetitorRelevance, ValuationModelType, ScenarioType,
            RiskType, Severity, Likelihood, CatalystImpact, ScoreDimension,
        ]
        for enum_cls in all_enums:
            assert issubclass(enum_cls, str), f"{enum_cls.__name__} must be a str enum"
            for member in enum_cls:
                assert isinstance(member.value, str)


# ---------------------------------------------------------------------------
# 10. Check constraints
# ---------------------------------------------------------------------------

class TestCheckConstraints:
    def test_financial_statement_quarter_consistency(self) -> None:
        check_names = [
            c.name
            for c in FinancialStatement.__table__.constraints
            if isinstance(c, sa.CheckConstraint)
        ]
        assert any("quarter_consistency" in (n or "") for n in check_names)


# ---------------------------------------------------------------------------
# 11. Model instantiation (smoke test)
# ---------------------------------------------------------------------------

class TestModelInstantiation:
    def test_create_exchange(self) -> None:
        ex = Exchange(id=uuid.uuid4(), code="NSE", name="National Stock Exchange")
        assert ex.code == "NSE"

    def test_create_company(self) -> None:
        c = Company(
            id=uuid.uuid4(),
            name="Test Corp Ltd",
            isin="INE000A00001",
        )
        assert c.name == "Test Corp Ltd"
        # is_active uses server_default, so it's None in-memory (DB sets it on INSERT)
        assert c.isin == "INE000A00001"

    def test_create_financial_metric(self) -> None:
        fm = FinancialMetric(
            id=uuid.uuid4(),
            statement_id=uuid.uuid4(),
            metric_name="revenue",
            value=Decimal("10000.5000"),
            unit=MetricUnit.CURRENCY,
        )
        assert fm.value == Decimal("10000.5000")
        assert fm.unit == MetricUnit.CURRENCY

    def test_create_evidence(self) -> None:
        ev = Evidence(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            evidence_type=EvidenceType.FACT,
            claim="Revenue grew 15% YoY",
            confidence=ConfidenceLevel.HIGH,
            extracted_by="financial_analysis_agent",
        )
        assert ev.evidence_type == EvidenceType.FACT

    def test_create_research_finding(self) -> None:
        rf = ResearchFinding(
            id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            agent_name="moat_agent",
            finding_type=FindingType.AI_INFERENCE,
            category="moat",
            content="Company has strong brand moat",
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert rf.finding_type == FindingType.AI_INFERENCE

    def test_create_valuation_model(self) -> None:
        vm = ValuationModel(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            model_type=ValuationModelType.DCF,
            scenario=ScenarioType.BASE,
            assumptions={"wacc": "10%"},
            inputs={"fcf": [100, 110, 120]},
            outputs={"terminal_value": 1500},
            implied_value_per_share=Decimal("450.0000"),
            current_price=Decimal("400.0000"),
            upside_downside_pct=Decimal("12.5000"),
        )
        assert vm.model_type == ValuationModelType.DCF

    def test_create_risk(self) -> None:
        r = Risk(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            research_run_id=uuid.uuid4(),
            risk_type=RiskType.GOVERNANCE,
            description="Promoter pledge at 30%",
            severity=Severity.HIGH,
            likelihood=Likelihood.MEDIUM,
        )
        assert r.severity == Severity.HIGH


# ---------------------------------------------------------------------------
# 12. Indexes exist
# ---------------------------------------------------------------------------

class TestIndexes:
    @staticmethod
    def _index_names(table: sa.Table) -> set[str]:
        return {idx.name for idx in table.indexes}

    def test_company_indexes(self) -> None:
        names = self._index_names(Company.__table__)
        assert "ix_company_nse_symbol" in names
        assert "ix_company_bse_code" in names
        assert "ix_company_sector_mcap" in names

    def test_financial_statement_indexes(self) -> None:
        names = self._index_names(FinancialStatement.__table__)
        assert "ix_financial_statement_company_period" in names
        assert "ix_financial_statement_annual_identity" in names
        assert "ix_financial_statement_quarterly_identity" in names

    def test_research_document_indexes(self) -> None:
        names = self._index_names(ResearchDocument.__table__)
        assert "ix_research_document_company_type_date" in names

    def test_evidence_indexes(self) -> None:
        names = self._index_names(Evidence.__table__)
        assert "ix_evidence_document" in names
        assert "ix_evidence_type" in names

    def test_moat_assessment_indexes(self) -> None:
        names = self._index_names(MoatAssessment.__table__)
        assert "ix_moat_assessment_company_run" in names
