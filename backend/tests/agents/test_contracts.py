"""Comprehensive tests for Phase 8.1 Company Research Agent contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    AGENT_NAME,
    AGENT_TOKEN_BUDGET,
    AGENT_TOKEN_WARNING_THRESHOLD,
    COMPANY_RESEARCH_STEPS,
    FINDING_CATEGORIES,
    MAX_LLM_ATTEMPTS,
    STEP_TYPE_DETERMINISTIC,
    STEP_TYPE_LLM_REASONING,
    STEP_TYPE_PROVIDER_CALL,
    CompanyResearchConfig,
    CompanyResearchRequest,
    DiscoverSourcesInput,
    DiscoverSourcesOutput,
    EvidenceExtractionOutput,
    EvidenceItem,
    ExtractedEvidence,
    FinancialStatementResult,
    FindingGenerationOutput,
    FindingItem,
    FindingValidationIssue,
    FindingValidationResult,
    GeneratedFinding,
    GetCompanyProfileInput,
    GetCompanyProfileOutput,
    GetFinancialSummaryInput,
    GetFinancialSummaryOutput,
    IdentifierType,
    NewsArticleResult,
    PersistEvidenceInput,
    PersistEvidenceOutput,
    PersistFindingsInput,
    PersistFindingsOutput,
    RejectedFinding,
    RetrieveDocumentInput,
    RetrieveDocumentOutput,
    SearchCompanyNewsInput,
    SearchCompanyNewsOutput,
    SourceCandidate,
    StepDefinition,
    TokenBudget,
    ValidateCompanyInput,
    ValidateCompanyOutput,
)
from app.models.enums import (
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    FindingType,
    SourceTier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
RUN_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
EXEC_UUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
DOC_UUID = uuid.UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")
EVIDENCE_UUID = uuid.UUID("fedcbafe-dcba-fedc-bafe-dcbafedcbafe")


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    def test_agent_token_budget(self) -> None:
        assert AGENT_TOKEN_BUDGET == 30_000

    def test_agent_token_warning_threshold(self) -> None:
        assert AGENT_TOKEN_WARNING_THRESHOLD == 24_000

    def test_warning_threshold_is_80_percent(self) -> None:
        assert int(AGENT_TOKEN_BUDGET * 0.8) == AGENT_TOKEN_WARNING_THRESHOLD

    def test_max_llm_attempts(self) -> None:
        assert MAX_LLM_ATTEMPTS == 2

    def test_agent_name(self) -> None:
        assert AGENT_NAME == "company_research_agent"

    def test_finding_categories_complete(self) -> None:
        expected = {
            "company_identity",
            "business_overview",
            "business_model",
            "revenue_streams",
            "products_services",
            "revenue_drivers",
            "customer_exposure",
            "geographic_exposure",
            "management_claim",
            "growth_drivers",
            "competitive_context",
            "risk",
            "research_gap",
            "contradiction",
        }
        assert expected == FINDING_CATEGORIES

    def test_finding_categories_is_frozenset(self) -> None:
        assert isinstance(FINDING_CATEGORIES, frozenset)

    def test_step_type_values(self) -> None:
        assert STEP_TYPE_DETERMINISTIC == "deterministic"
        assert STEP_TYPE_PROVIDER_CALL == "provider_call"
        assert STEP_TYPE_LLM_REASONING == "llm_reasoning"


# ===========================================================================
# IdentifierType
# ===========================================================================


class TestIdentifierType:
    def test_nse_symbol(self) -> None:
        assert IdentifierType.NSE_SYMBOL == "NSE_SYMBOL"

    def test_bse_code(self) -> None:
        assert IdentifierType.BSE_CODE == "BSE_CODE"

    def test_isin(self) -> None:
        assert IdentifierType.ISIN == "ISIN"

    def test_all_values(self) -> None:
        assert set(IdentifierType) == {"NSE_SYMBOL", "BSE_CODE", "ISIN"}


# ===========================================================================
# CompanyResearchRequest
# ===========================================================================


class TestCompanyResearchRequest:
    def test_valid_request(self) -> None:
        req = CompanyResearchRequest(
            company_identifier="RELIANCE",
            identifier_type=IdentifierType.NSE_SYMBOL,
            observation_date=date(2025, 9, 30),
            initiated_by="test_user",
        )
        assert req.company_identifier == "RELIANCE"
        assert req.identifier_type == IdentifierType.NSE_SYMBOL
        assert req.observation_date == date(2025, 9, 30)
        assert req.initiated_by == "test_user"
        assert req.configuration is None

    def test_with_configuration(self) -> None:
        config = CompanyResearchConfig(token_budget=25_000)
        req = CompanyResearchRequest(
            company_identifier="INE002A01018",
            identifier_type=IdentifierType.ISIN,
            observation_date=date(2025, 6, 30),
            initiated_by="system",
            configuration=config,
        )
        assert req.configuration is not None
        assert req.configuration.token_budget == 25_000

    def test_frozen(self) -> None:
        req = CompanyResearchRequest(
            company_identifier="TCS",
            identifier_type=IdentifierType.NSE_SYMBOL,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        with pytest.raises(ValidationError):
            req.company_identifier = "INFY"  # type: ignore[misc]

    def test_empty_identifier_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchRequest(
                company_identifier="",
                identifier_type=IdentifierType.NSE_SYMBOL,
                observation_date=date(2025, 9, 30),
                initiated_by="user",
            )

    def test_identifier_too_long(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchRequest(
                company_identifier="X" * 21,
                identifier_type=IdentifierType.NSE_SYMBOL,
                observation_date=date(2025, 9, 30),
                initiated_by="user",
            )

    def test_empty_initiated_by_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchRequest(
                company_identifier="TCS",
                identifier_type=IdentifierType.NSE_SYMBOL,
                observation_date=date(2025, 9, 30),
                initiated_by="",
            )

    def test_bse_code_identifier(self) -> None:
        req = CompanyResearchRequest(
            company_identifier="500325",
            identifier_type=IdentifierType.BSE_CODE,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
        )
        assert req.identifier_type == IdentifierType.BSE_CODE


# ===========================================================================
# CompanyResearchConfig
# ===========================================================================


class TestCompanyResearchConfig:
    def test_defaults(self) -> None:
        config = CompanyResearchConfig()
        assert config.token_budget == 30_000
        assert config.token_warning_threshold == 24_000
        assert config.max_llm_attempts == 2
        assert config.document_types is None
        assert config.source_limit == 20
        assert config.concurrent_retrievals == 5
        assert config.extraction_model is None
        assert config.generation_model is None
        assert config.analysis_model is None

    def test_custom_values(self) -> None:
        config = CompanyResearchConfig(
            token_budget=25_000,
            token_warning_threshold=20_000,
            max_llm_attempts=1,
            document_types=[DocumentType.ANNUAL_REPORT, DocumentType.FILING],
            source_limit=10,
            concurrent_retrievals=3,
            extraction_model="haiku",
            generation_model="sonnet",
            analysis_model="sonnet",
        )
        assert config.token_budget == 25_000
        assert config.max_llm_attempts == 1
        assert config.document_types == [DocumentType.ANNUAL_REPORT, DocumentType.FILING]
        assert config.concurrent_retrievals == 3

    def test_frozen(self) -> None:
        config = CompanyResearchConfig()
        with pytest.raises(ValidationError):
            config.token_budget = 50_000  # type: ignore[misc]

    def test_token_budget_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchConfig(token_budget=0)

    def test_max_llm_attempts_max_is_3(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchConfig(max_llm_attempts=4)

    def test_source_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchConfig(source_limit=0)
        with pytest.raises(ValidationError):
            CompanyResearchConfig(source_limit=101)

    def test_concurrent_retrievals_bounds(self) -> None:
        with pytest.raises(ValidationError):
            CompanyResearchConfig(concurrent_retrievals=0)
        with pytest.raises(ValidationError):
            CompanyResearchConfig(concurrent_retrievals=21)


# ===========================================================================
# SourceCandidate
# ===========================================================================


class TestSourceCandidate:
    def test_from_filing(self) -> None:
        sc = SourceCandidate(
            source_id="BSE-12345",
            source_type=DocumentType.FILING,
            provider="bse",
            title="Annual Report FY2025",
            publication_date=date(2025, 5, 30),
            document_date=date(2025, 3, 31),
            source_tier=SourceTier.TIER_1,
            url="https://bseindia.com/filing/12345",
            provider_metadata={"exchange": "BSE"},
        )
        assert sc.source_id == "BSE-12345"
        assert sc.source_type == DocumentType.FILING
        assert sc.publication_date == date(2025, 5, 30)
        assert sc.document_date == date(2025, 3, 31)
        assert sc.source_tier == SourceTier.TIER_1

    def test_from_transcript(self) -> None:
        sc = SourceCandidate(
            source_id="RELIANCE:Q3:2025",
            source_type=DocumentType.TRANSCRIPT,
            provider="mock_transcripts",
            title="RELIANCE Q3 FY2025 Earnings Call",
            publication_date=date(2025, 1, 25),
            source_tier=SourceTier.TIER_1,
            provider_metadata={"quarter": "Q3", "year": 2025},
        )
        assert sc.source_type == DocumentType.TRANSCRIPT
        assert sc.document_date is None
        assert sc.url is None

    def test_from_news(self) -> None:
        sc = SourceCandidate(
            source_id="https://example.com/news/123",
            source_type=DocumentType.NEWS,
            provider="yahoo",
            title="Reliance announces new partnership",
            publication_date=date(2025, 8, 15),
            source_tier=SourceTier.TIER_3,
            url="https://example.com/news/123",
        )
        assert sc.source_type == DocumentType.NEWS
        assert sc.source_tier == SourceTier.TIER_3

    def test_frozen(self) -> None:
        sc = SourceCandidate(
            source_id="X",
            source_type=DocumentType.FILING,
            provider="test",
            title="Test",
            publication_date=date(2025, 1, 1),
            source_tier=SourceTier.TIER_1,
        )
        with pytest.raises(ValidationError):
            sc.source_id = "Y"  # type: ignore[misc]

    def test_empty_source_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceCandidate(
                source_id="",
                source_type=DocumentType.FILING,
                provider="test",
                title="Test",
                publication_date=date(2025, 1, 1),
                source_tier=SourceTier.TIER_1,
            )

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceCandidate(
                source_id="X",
                source_type=DocumentType.FILING,
                provider="test",
                title="",
                publication_date=date(2025, 1, 1),
                source_tier=SourceTier.TIER_1,
            )


# ===========================================================================
# Tool 1: validate_company
# ===========================================================================


class TestValidateCompanyContracts:
    def test_input(self) -> None:
        inp = ValidateCompanyInput(
            identifier="RELIANCE",
            identifier_type=IdentifierType.NSE_SYMBOL,
        )
        assert inp.identifier == "RELIANCE"
        assert inp.identifier_type == IdentifierType.NSE_SYMBOL

    def test_input_frozen(self) -> None:
        inp = ValidateCompanyInput(identifier="TCS", identifier_type=IdentifierType.NSE_SYMBOL)
        with pytest.raises(ValidationError):
            inp.identifier = "INFY"  # type: ignore[misc]

    def test_input_empty_identifier(self) -> None:
        with pytest.raises(ValidationError):
            ValidateCompanyInput(identifier="", identifier_type=IdentifierType.NSE_SYMBOL)

    def test_output(self) -> None:
        out = ValidateCompanyOutput(
            company_id=COMPANY_UUID,
            name="Reliance Industries Ltd",
            nse_symbol="RELIANCE",
            bse_code="500325",
            isin="INE002A01018",
            sector="Energy",
            industry="Oil & Gas",
        )
        assert out.company_id == COMPANY_UUID
        assert out.isin == "INE002A01018"
        assert out.sector == "Energy"

    def test_output_optional_fields(self) -> None:
        out = ValidateCompanyOutput(
            company_id=COMPANY_UUID,
            name="Test Co",
            isin="INE123456789",
        )
        assert out.nse_symbol is None
        assert out.bse_code is None
        assert out.sector is None
        assert out.industry is None


# ===========================================================================
# Tool 2: discover_sources
# ===========================================================================


class TestDiscoverSourcesContracts:
    def test_input_defaults(self) -> None:
        inp = DiscoverSourcesInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
        )
        assert inp.limit == 20
        assert inp.document_types is None

    def test_input_with_types(self) -> None:
        inp = DiscoverSourcesInput(
            company_id=COMPANY_UUID,
            observation_date=date(2025, 9, 30),
            document_types=[DocumentType.ANNUAL_REPORT, DocumentType.TRANSCRIPT],
            limit=10,
        )
        assert len(inp.document_types) == 2

    def test_output_empty(self) -> None:
        out = DiscoverSourcesOutput(candidates=[])
        assert out.candidates == []

    def test_output_with_candidates(self) -> None:
        candidates = [
            SourceCandidate(
                source_id="f1",
                source_type=DocumentType.FILING,
                provider="bse",
                title="Filing 1",
                publication_date=date(2025, 5, 1),
                source_tier=SourceTier.TIER_1,
            ),
            SourceCandidate(
                source_id="n1",
                source_type=DocumentType.NEWS,
                provider="yahoo",
                title="News 1",
                publication_date=date(2025, 8, 1),
                source_tier=SourceTier.TIER_3,
            ),
        ]
        out = DiscoverSourcesOutput(candidates=candidates)
        assert len(out.candidates) == 2
        assert out.candidates[0].source_tier == SourceTier.TIER_1


# ===========================================================================
# Tool 3: retrieve_document
# ===========================================================================


class TestRetrieveDocumentContracts:
    def test_input(self) -> None:
        inp = RetrieveDocumentInput(filing_id="BSE-12345", provider="bse")
        assert inp.filing_id == "BSE-12345"
        assert inp.provider == "bse"

    def test_input_no_provider(self) -> None:
        inp = RetrieveDocumentInput(filing_id="BSE-12345")
        assert inp.provider is None

    def test_input_empty_filing_id(self) -> None:
        with pytest.raises(ValidationError):
            RetrieveDocumentInput(filing_id="")

    def test_output(self) -> None:
        out = RetrieveDocumentOutput(
            content="Annual report content...",
            content_type="text/plain",
            content_hash="abc123def456",
            filing_id="BSE-12345",
        )
        assert out.content == "Annual report content..."
        assert out.content_hash == "abc123def456"

    def test_output_frozen(self) -> None:
        out = RetrieveDocumentOutput(
            content="text",
            content_type="text/plain",
            content_hash="hash",
            filing_id="f1",
        )
        with pytest.raises(ValidationError):
            out.content = "new"  # type: ignore[misc]


# ===========================================================================
# Tool 4: get_company_profile
# ===========================================================================


class TestGetCompanyProfileContracts:
    def test_input(self) -> None:
        inp = GetCompanyProfileInput(company_id=COMPANY_UUID)
        assert inp.company_id == COMPANY_UUID

    def test_output_full(self) -> None:
        out = GetCompanyProfileOutput(
            name="Reliance Industries Ltd",
            nse_symbol="RELIANCE",
            bse_code="500325",
            isin="INE002A01018",
            sector_id=uuid.uuid4(),
            sector_name="Energy",
            industry_id=uuid.uuid4(),
            industry_name="Oil & Gas",
            market_cap=Decimal("1500000.0000"),
            incorporation_date=date(1966, 5, 8),
            listing_date=date(1977, 1, 1),
            website="https://www.ril.com",
            description="A conglomerate",
            registered_address="Mumbai",
            business_segments={"oil": "60%", "retail": "25%", "jio": "15%"},
            major_products={"refining": True},
            geographies={"india": "80%", "international": "20%"},
            is_active=True,
        )
        assert out.name == "Reliance Industries Ltd"
        assert out.market_cap == Decimal("1500000.0000")

    def test_output_minimal(self) -> None:
        out = GetCompanyProfileOutput(
            name="Test Co",
            isin="INE123456789",
            is_active=True,
        )
        assert out.nse_symbol is None
        assert out.market_cap is None
        assert out.business_segments is None


# ===========================================================================
# Tool 5: search_company_news
# ===========================================================================


class TestSearchCompanyNewsContracts:
    def test_input_defaults(self) -> None:
        inp = SearchCompanyNewsInput(
            symbol="RELIANCE",
            exchange="NSE",
            observation_date=date(2025, 9, 30),
        )
        assert inp.limit == 10

    def test_input_custom_limit(self) -> None:
        inp = SearchCompanyNewsInput(
            symbol="TCS",
            exchange="NSE",
            observation_date=date(2025, 9, 30),
            limit=25,
        )
        assert inp.limit == 25

    def test_input_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SearchCompanyNewsInput(
                symbol="TCS",
                exchange="NSE",
                observation_date=date(2025, 9, 30),
                limit=0,
            )
        with pytest.raises(ValidationError):
            SearchCompanyNewsInput(
                symbol="TCS",
                exchange="NSE",
                observation_date=date(2025, 9, 30),
                limit=51,
            )

    def test_article_result(self) -> None:
        article = NewsArticleResult(
            title="Reliance acquires company",
            url="https://example.com/news/1",
            source="Economic Times",
            published_at=datetime(2025, 8, 15, 10, 30, 0),
            summary="Reliance has announced...",
        )
        assert article.title == "Reliance acquires company"
        assert article.summary is not None

    def test_output(self) -> None:
        out = SearchCompanyNewsOutput(
            articles=[
                NewsArticleResult(
                    title="News 1",
                    url="https://example.com/1",
                    source="ET",
                    published_at=datetime(2025, 8, 1, 0, 0, 0),
                ),
            ]
        )
        assert len(out.articles) == 1
        assert out.articles[0].summary is None


# ===========================================================================
# Tool 6: get_financial_summary
# ===========================================================================


class TestGetFinancialSummaryContracts:
    def test_input_defaults(self) -> None:
        inp = GetFinancialSummaryInput(
            symbol="RELIANCE",
            exchange="NSE",
            observation_date=date(2025, 9, 30),
        )
        assert inp.periods == 4

    def test_input_observation_date_explicit(self) -> None:
        inp = GetFinancialSummaryInput(
            symbol="RELIANCE",
            exchange="NSE",
            observation_date=date(2025, 6, 30),
            periods=8,
        )
        assert inp.observation_date == date(2025, 6, 30)
        assert inp.periods == 8

    def test_financial_statement_result(self) -> None:
        stmt = FinancialStatementResult(
            symbol="RELIANCE",
            exchange="NSE",
            statement_type="INCOME_STATEMENT",
            period_type="ANNUAL",
            period="FY2025",
            filing_date=date(2025, 5, 30),
            currency="INR",
            line_items={
                "total_revenue": Decimal("950000"),
                "net_income": Decimal("75000"),
            },
        )
        assert stmt.line_items["total_revenue"] == Decimal("950000")
        assert stmt.filing_date == date(2025, 5, 30)

    def test_financial_statement_no_filing_date(self) -> None:
        stmt = FinancialStatementResult(
            symbol="TCS",
            exchange="NSE",
            statement_type="BALANCE_SHEET",
            period_type="QUARTERLY",
            period="Q3FY2025",
            currency="INR",
            line_items={"total_assets": Decimal("200000")},
        )
        assert stmt.filing_date is None

    def test_output(self) -> None:
        out = GetFinancialSummaryOutput(statements=[])
        assert out.statements == []


# ===========================================================================
# Tool 7: persist_evidence
# ===========================================================================


class TestPersistEvidenceContracts:
    def test_evidence_item(self) -> None:
        item = EvidenceItem(
            evidence_type=EvidenceType.FACT,
            claim="Revenue for FY2025 was Rs 950,000 crore",
            context="From audited financial statements",
            page_or_section="Page 45",
            confidence=ConfidenceLevel.HIGH,
        )
        assert item.evidence_type == EvidenceType.FACT
        assert item.confidence == ConfidenceLevel.HIGH

    def test_evidence_item_management_statement(self) -> None:
        item = EvidenceItem(
            evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
            claim="Management expects 20% revenue growth in FY2026",
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert item.evidence_type == EvidenceType.MANAGEMENT_STATEMENT

    def test_evidence_item_empty_claim_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItem(
                evidence_type=EvidenceType.FACT,
                claim="",
                confidence=ConfidenceLevel.HIGH,
            )

    def test_input(self) -> None:
        inp = PersistEvidenceInput(
            document_id=DOC_UUID,
            evidences=[
                EvidenceItem(
                    evidence_type=EvidenceType.FACT,
                    claim="Test claim",
                    confidence=ConfidenceLevel.HIGH,
                ),
            ],
        )
        assert inp.document_id == DOC_UUID
        assert len(inp.evidences) == 1

    def test_input_empty_evidences_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistEvidenceInput(
                document_id=DOC_UUID,
                evidences=[],
            )

    def test_output(self) -> None:
        out = PersistEvidenceOutput(evidence_ids=[EVIDENCE_UUID])
        assert len(out.evidence_ids) == 1


# ===========================================================================
# Tool 8: persist_findings
# ===========================================================================


class TestPersistFindingsContracts:
    def test_finding_item_fact(self) -> None:
        item = FindingItem(
            finding_type=FindingType.FACT,
            category="company_identity",
            content="Reliance Industries was incorporated on May 8, 1966",
            confidence=ConfidenceLevel.HIGH,
            observation_date=date(2025, 9, 30),
            source_publication_date=date(2025, 5, 30),
            evidence_ids=[EVIDENCE_UUID],
        )
        assert item.finding_type == FindingType.FACT
        assert item.agent_name == AGENT_NAME
        assert len(item.evidence_ids) == 1

    def test_finding_item_ai_inference(self) -> None:
        item = FindingItem(
            finding_type=FindingType.AI_INFERENCE,
            category="business_model",
            content="The company's revenue concentration in a single segment poses risk",
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert item.finding_type == FindingType.AI_INFERENCE
        assert item.evidence_ids is None
        assert item.source_publication_date is None

    def test_finding_item_management_claim(self) -> None:
        item = FindingItem(
            finding_type=FindingType.MANAGEMENT_CLAIM,
            category="management_claim",
            content="Management expects 20% revenue growth",
            confidence=ConfidenceLevel.MEDIUM,
            source_publication_date=date(2025, 1, 25),
            evidence_ids=[EVIDENCE_UUID],
        )
        assert item.finding_type == FindingType.MANAGEMENT_CLAIM

    def test_finding_item_uncertainty(self) -> None:
        item = FindingItem(
            finding_type=FindingType.UNCERTAINTY,
            category="research_gap",
            content="Customer concentration data not disclosed",
            confidence=ConfidenceLevel.LOW,
        )
        assert item.finding_type == FindingType.UNCERTAINTY

    def test_finding_item_default_agent_name(self) -> None:
        item = FindingItem(
            finding_type=FindingType.FACT,
            category="company_identity",
            content="Test",
            confidence=ConfidenceLevel.HIGH,
        )
        assert item.agent_name == "company_research_agent"

    def test_finding_item_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FindingItem(
                finding_type=FindingType.FACT,
                category="company_identity",
                content="",
                confidence=ConfidenceLevel.HIGH,
            )

    def test_finding_item_empty_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FindingItem(
                finding_type=FindingType.FACT,
                category="",
                content="Test",
                confidence=ConfidenceLevel.HIGH,
            )

    def test_rejected_finding(self) -> None:
        rej = RejectedFinding(index=0, reason="FACT finding without evidence")
        assert rej.index == 0
        assert rej.reason == "FACT finding without evidence"

    def test_rejected_finding_negative_index(self) -> None:
        with pytest.raises(ValidationError):
            RejectedFinding(index=-1, reason="Bad")

    def test_input(self) -> None:
        inp = PersistFindingsInput(
            run_id=RUN_UUID,
            execution_id=EXEC_UUID,
            findings=[
                FindingItem(
                    finding_type=FindingType.FACT,
                    category="company_identity",
                    content="Test finding",
                    confidence=ConfidenceLevel.HIGH,
                    evidence_ids=[EVIDENCE_UUID],
                ),
            ],
        )
        assert inp.run_id == RUN_UUID
        assert inp.execution_id == EXEC_UUID

    def test_input_empty_findings_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistFindingsInput(
                run_id=RUN_UUID,
                execution_id=EXEC_UUID,
                findings=[],
            )

    def test_output(self) -> None:
        out = PersistFindingsOutput(
            finding_ids=[uuid.uuid4(), uuid.uuid4()],
            rejected=[RejectedFinding(index=2, reason="No evidence")],
        )
        assert len(out.finding_ids) == 2
        assert len(out.rejected) == 1

    def test_output_no_rejections(self) -> None:
        out = PersistFindingsOutput(
            finding_ids=[uuid.uuid4()],
            rejected=[],
        )
        assert len(out.rejected) == 0


# ===========================================================================
# LLM structured output — evidence extraction
# ===========================================================================


class TestEvidenceExtractionOutput:
    def test_extracted_evidence(self) -> None:
        ev = ExtractedEvidence(
            evidence_type=EvidenceType.FACT,
            claim="Revenue grew 15% YoY to Rs 950,000 crore",
            context="From the audited income statement",
            page_or_section="Section 3.1",
            confidence=ConfidenceLevel.HIGH,
        )
        assert ev.evidence_type == EvidenceType.FACT
        assert ev.confidence == ConfidenceLevel.HIGH

    def test_extraction_output(self) -> None:
        out = EvidenceExtractionOutput(
            evidences=[
                ExtractedEvidence(
                    evidence_type=EvidenceType.FACT,
                    claim="Claim 1",
                    confidence=ConfidenceLevel.HIGH,
                ),
                ExtractedEvidence(
                    evidence_type=EvidenceType.MANAGEMENT_STATEMENT,
                    claim="Management says growth will be 20%",
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ]
        )
        assert len(out.evidences) == 2

    def test_extraction_output_empty(self) -> None:
        out = EvidenceExtractionOutput(evidences=[])
        assert len(out.evidences) == 0

    def test_extracted_evidence_all_types(self) -> None:
        for et in EvidenceType:
            ev = ExtractedEvidence(
                evidence_type=et,
                claim=f"Test {et.value}",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert ev.evidence_type == et


# ===========================================================================
# LLM structured output — finding generation
# ===========================================================================


class TestFindingGenerationOutput:
    def test_generated_finding(self) -> None:
        f = GeneratedFinding(
            finding_type=FindingType.FACT,
            category="company_identity",
            content="Reliance Industries is an Indian conglomerate",
            confidence=ConfidenceLevel.HIGH,
            source_publication_date=date(2025, 5, 30),
            evidence_indices=[0, 1],
        )
        assert f.finding_type == FindingType.FACT
        assert f.evidence_indices == [0, 1]

    def test_generated_finding_no_evidence(self) -> None:
        f = GeneratedFinding(
            finding_type=FindingType.AI_INFERENCE,
            category="risk",
            content="Revenue concentration risk",
            confidence=ConfidenceLevel.MEDIUM,
        )
        assert f.evidence_indices is None
        assert f.source_publication_date is None

    def test_generation_output(self) -> None:
        out = FindingGenerationOutput(
            findings=[
                GeneratedFinding(
                    finding_type=FindingType.FACT,
                    category="business_model",
                    content="B2B model",
                    confidence=ConfidenceLevel.HIGH,
                    evidence_indices=[0],
                ),
            ]
        )
        assert len(out.findings) == 1

    def test_all_finding_types(self) -> None:
        for ft in FindingType:
            f = GeneratedFinding(
                finding_type=ft,
                category="test",
                content="Test content",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert f.finding_type == ft


# ===========================================================================
# Finding validation
# ===========================================================================


class TestFindingValidationResult:
    def test_all_valid(self) -> None:
        result = FindingValidationResult(
            total_findings=5,
            valid_count=5,
            rejected_count=0,
            issues=[],
        )
        assert result.total_findings == 5
        assert result.rejected_count == 0
        assert len(result.issues) == 0

    def test_with_issues(self) -> None:
        result = FindingValidationResult(
            total_findings=10,
            valid_count=8,
            rejected_count=2,
            issues=[
                FindingValidationIssue(
                    finding_index=3,
                    issue_type="missing_evidence",
                    message="FACT finding has no evidence linkage",
                ),
                FindingValidationIssue(
                    finding_index=7,
                    issue_type="temporal_violation",
                    message="source_publication_date after observation_date",
                ),
            ],
        )
        assert result.rejected_count == 2
        assert result.issues[0].issue_type == "missing_evidence"
        assert result.issues[1].finding_index == 7

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FindingValidationResult(
                total_findings=-1,
                valid_count=0,
                rejected_count=0,
                issues=[],
            )


# ===========================================================================
# Token budget
# ===========================================================================


class TestTokenBudget:
    def test_defaults(self) -> None:
        budget = TokenBudget()
        assert budget.budget == 30_000
        assert budget.warning_threshold == 24_000
        assert budget.input_tokens == 0
        assert budget.output_tokens == 0
        assert budget.total_tokens == 0
        assert budget.remaining == 30_000
        assert budget.is_warning is False
        assert budget.is_exhausted is False
        assert budget.utilization_pct == Decimal("0.00")

    def test_record_usage(self) -> None:
        budget = TokenBudget()
        budget.record_usage(5_000, 2_000)
        assert budget.input_tokens == 5_000
        assert budget.output_tokens == 2_000
        assert budget.total_tokens == 7_000
        assert budget.remaining == 23_000

    def test_cumulative_usage(self) -> None:
        budget = TokenBudget()
        budget.record_usage(5_000, 2_000)
        budget.record_usage(3_000, 1_000)
        assert budget.total_tokens == 11_000
        assert budget.remaining == 19_000

    def test_warning_threshold(self) -> None:
        budget = TokenBudget()
        budget.record_usage(20_000, 4_000)
        assert budget.is_warning is True
        assert budget.is_exhausted is False

    def test_exactly_at_warning(self) -> None:
        budget = TokenBudget()
        budget.record_usage(20_000, 4_000)
        assert budget.total_tokens == 24_000
        assert budget.is_warning is True

    def test_budget_exhausted(self) -> None:
        budget = TokenBudget()
        budget.record_usage(20_000, 10_000)
        assert budget.is_exhausted is True
        assert budget.remaining == 0

    def test_over_budget(self) -> None:
        budget = TokenBudget()
        budget.record_usage(25_000, 10_000)
        assert budget.total_tokens == 35_000
        assert budget.remaining == 0
        assert budget.is_exhausted is True

    def test_utilization_pct(self) -> None:
        budget = TokenBudget()
        budget.record_usage(15_000, 0)
        assert budget.utilization_pct == Decimal("50.00")

    def test_utilization_pct_full(self) -> None:
        budget = TokenBudget()
        budget.record_usage(30_000, 0)
        assert budget.utilization_pct == Decimal("100.00")

    def test_custom_budget(self) -> None:
        budget = TokenBudget(budget=10_000, warning_threshold=8_000)
        budget.record_usage(8_000, 0)
        assert budget.is_warning is True
        assert budget.is_exhausted is False
        budget.record_usage(2_000, 0)
        assert budget.is_exhausted is True

    def test_mutable(self) -> None:
        budget = TokenBudget()
        budget.input_tokens = 100
        assert budget.input_tokens == 100


# ===========================================================================
# Step configuration
# ===========================================================================


class TestStepDefinition:
    def test_deterministic_step(self) -> None:
        step = StepDefinition(
            step_order=1,
            step_name="company_validation",
            step_type=STEP_TYPE_DETERMINISTIC,
            timeout_seconds=5,
        )
        assert step.uses_llm is False

    def test_llm_step(self) -> None:
        step = StepDefinition(
            step_order=4,
            step_name="evidence_extraction",
            step_type=STEP_TYPE_LLM_REASONING,
            timeout_seconds=120,
            uses_llm=True,
        )
        assert step.uses_llm is True

    def test_frozen(self) -> None:
        step = StepDefinition(
            step_order=1,
            step_name="test",
            step_type="deterministic",
            timeout_seconds=5,
        )
        with pytest.raises(ValidationError):
            step.step_name = "other"  # type: ignore[misc]

    def test_step_order_bounds(self) -> None:
        with pytest.raises(ValidationError):
            StepDefinition(
                step_order=0,
                step_name="test",
                step_type="deterministic",
                timeout_seconds=5,
            )
        with pytest.raises(ValidationError):
            StepDefinition(
                step_order=8,
                step_name="test",
                step_type="deterministic",
                timeout_seconds=5,
            )

    def test_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            StepDefinition(
                step_order=1,
                step_name="test",
                step_type="deterministic",
                timeout_seconds=0,
            )


class TestCompanyResearchSteps:
    def test_seven_steps(self) -> None:
        assert len(COMPANY_RESEARCH_STEPS) == 7

    def test_step_order_sequence(self) -> None:
        orders = [s.step_order for s in COMPANY_RESEARCH_STEPS]
        assert orders == [1, 2, 3, 4, 5, 6, 7]

    def test_step_names(self) -> None:
        names = [s.step_name for s in COMPANY_RESEARCH_STEPS]
        assert names == [
            "company_validation",
            "source_discovery",
            "document_retrieval",
            "evidence_extraction",
            "finding_generation",
            "finding_validation",
            "gap_contradiction_analysis",
        ]

    def test_step_types(self) -> None:
        types = [s.step_type for s in COMPANY_RESEARCH_STEPS]
        assert types == [
            "deterministic",
            "provider_call",
            "provider_call",
            "llm_reasoning",
            "llm_reasoning",
            "deterministic",
            "llm_reasoning",
        ]

    def test_llm_steps(self) -> None:
        llm_steps = [s for s in COMPANY_RESEARCH_STEPS if s.uses_llm]
        assert len(llm_steps) == 3
        assert [s.step_name for s in llm_steps] == [
            "evidence_extraction",
            "finding_generation",
            "gap_contradiction_analysis",
        ]

    def test_deterministic_steps(self) -> None:
        det_steps = [s for s in COMPANY_RESEARCH_STEPS if s.step_type == STEP_TYPE_DETERMINISTIC]
        assert len(det_steps) == 2
        assert [s.step_name for s in det_steps] == [
            "company_validation",
            "finding_validation",
        ]

    def test_provider_steps(self) -> None:
        prov_steps = [s for s in COMPANY_RESEARCH_STEPS if s.step_type == STEP_TYPE_PROVIDER_CALL]
        assert len(prov_steps) == 2
        assert [s.step_name for s in prov_steps] == [
            "source_discovery",
            "document_retrieval",
        ]

    def test_is_tuple(self) -> None:
        assert isinstance(COMPANY_RESEARCH_STEPS, tuple)

    def test_timeout_values(self) -> None:
        timeouts = {s.step_name: s.timeout_seconds for s in COMPANY_RESEARCH_STEPS}
        assert timeouts["company_validation"] == 5
        assert timeouts["source_discovery"] == 30
        assert timeouts["document_retrieval"] == 60
        assert timeouts["evidence_extraction"] == 120
        assert timeouts["finding_generation"] == 120
        assert timeouts["finding_validation"] == 10
        assert timeouts["gap_contradiction_analysis"] == 60


# ===========================================================================
# Cross-cutting: enum reuse
# ===========================================================================


class TestEnumReuse:
    """Verify contracts use existing enums, not new ones."""

    def test_source_candidate_uses_document_type(self) -> None:
        for dt in [
            DocumentType.FILING,
            DocumentType.TRANSCRIPT,
            DocumentType.NEWS,
            DocumentType.ANNUAL_REPORT,
            DocumentType.QUARTERLY_RESULT,
        ]:
            sc = SourceCandidate(
                source_id="x",
                source_type=dt,
                provider="test",
                title="T",
                publication_date=date(2025, 1, 1),
                source_tier=SourceTier.TIER_1,
            )
            assert sc.source_type == dt

    def test_source_candidate_uses_source_tier(self) -> None:
        for tier in SourceTier:
            sc = SourceCandidate(
                source_id="x",
                source_type=DocumentType.FILING,
                provider="test",
                title="T",
                publication_date=date(2025, 1, 1),
                source_tier=tier,
            )
            assert sc.source_tier == tier

    def test_evidence_item_uses_evidence_type(self) -> None:
        for et in EvidenceType:
            item = EvidenceItem(
                evidence_type=et,
                claim="Test",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert item.evidence_type == et

    def test_finding_item_uses_finding_type(self) -> None:
        for ft in FindingType:
            item = FindingItem(
                finding_type=ft,
                category="test",
                content="Test",
                confidence=ConfidenceLevel.MEDIUM,
            )
            assert item.finding_type == ft

    def test_evidence_item_uses_confidence_level(self) -> None:
        for cl in ConfidenceLevel:
            item = EvidenceItem(
                evidence_type=EvidenceType.FACT,
                claim="Test",
                confidence=cl,
            )
            assert item.confidence == cl


# ===========================================================================
# Serialization round-trip
# ===========================================================================


class TestSerialization:
    def test_source_candidate_json_round_trip(self) -> None:
        sc = SourceCandidate(
            source_id="BSE-12345",
            source_type=DocumentType.FILING,
            provider="bse",
            title="Annual Report",
            publication_date=date(2025, 5, 30),
            source_tier=SourceTier.TIER_1,
        )
        data = sc.model_dump(mode="json")
        sc2 = SourceCandidate.model_validate(data)
        assert sc == sc2

    def test_finding_item_json_round_trip(self) -> None:
        item = FindingItem(
            finding_type=FindingType.FACT,
            category="company_identity",
            content="Test finding",
            confidence=ConfidenceLevel.HIGH,
            observation_date=date(2025, 9, 30),
            source_publication_date=date(2025, 5, 30),
            evidence_ids=[EVIDENCE_UUID],
        )
        data = item.model_dump(mode="json")
        item2 = FindingItem.model_validate(data)
        assert item == item2

    def test_company_research_request_json_round_trip(self) -> None:
        req = CompanyResearchRequest(
            company_identifier="RELIANCE",
            identifier_type=IdentifierType.NSE_SYMBOL,
            observation_date=date(2025, 9, 30),
            initiated_by="user",
            configuration=CompanyResearchConfig(token_budget=25_000),
        )
        data = req.model_dump(mode="json")
        req2 = CompanyResearchRequest.model_validate(data)
        assert req == req2

    def test_token_budget_json_round_trip(self) -> None:
        budget = TokenBudget(budget=20_000, warning_threshold=16_000)
        budget.record_usage(5_000, 1_000)
        data = budget.model_dump(mode="json")
        budget2 = TokenBudget.model_validate(data)
        assert budget2.total_tokens == 6_000

    def test_validation_result_json_round_trip(self) -> None:
        result = FindingValidationResult(
            total_findings=5,
            valid_count=4,
            rejected_count=1,
            issues=[
                FindingValidationIssue(
                    finding_index=2,
                    issue_type="missing_evidence",
                    message="No evidence",
                ),
            ],
        )
        data = result.model_dump(mode="json")
        result2 = FindingValidationResult.model_validate(data)
        assert result == result2

    def test_financial_statement_decimal_preserved(self) -> None:
        stmt = FinancialStatementResult(
            symbol="TCS",
            exchange="NSE",
            statement_type="INCOME_STATEMENT",
            period_type="ANNUAL",
            period="FY2025",
            currency="INR",
            line_items={"revenue": Decimal("123456.7890")},
        )
        data = stmt.model_dump(mode="json")
        stmt2 = FinancialStatementResult.model_validate(data)
        assert isinstance(stmt2.line_items["revenue"], Decimal)

    def test_get_company_profile_decimal_preserved(self) -> None:
        out = GetCompanyProfileOutput(
            name="Test Co",
            isin="INE123456789",
            market_cap=Decimal("1500000.0000"),
            is_active=True,
        )
        data = out.model_dump(mode="json")
        out2 = GetCompanyProfileOutput.model_validate(data)
        assert isinstance(out2.market_cap, Decimal)
