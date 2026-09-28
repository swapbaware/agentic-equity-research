"""API endpoint tests for the Evidence subsystem using TestClient with mocked service."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator  # noqa: TC003 — used in async generator fixture
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_evidence_service
from app.exceptions import NotFoundError, ValidationError
from app.main import create_app
from app.models.enums import (
    ClaimType,
    ConfidenceLevel,
    DocumentType,
    SourceTier,
    SourceType,
)
from app.models.evidence import Claim, Source
from app.models.research import Evidence, ResearchDocument
from app.schemas.evidence import (
    CitationChain,
    CitationDocument,
    CitationEvidence,
    ClaimResponse,
)
from app.services.evidence import EvidenceService


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=EvidenceService)


@pytest.fixture
def app(mock_service: AsyncMock):  # noqa: ANN201
    application = create_app()

    async def _override() -> AsyncIterator[AsyncMock]:
        yield mock_service

    application.dependency_overrides[get_evidence_service] = _override
    return application


@pytest.fixture
def client(app):  # noqa: ANN001, ANN201
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SOURCE_ID = uuid.uuid4()
DOC_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()
CLAIM_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def _mock_source() -> Source:
    s = Source(
        id=SOURCE_ID,
        name="NSE India",
        source_type=SourceType.EXCHANGE,
        default_tier=SourceTier.TIER_1,
    )
    s.is_active = True
    s.created_at = NOW
    s.updated_at = NOW
    return s


def _mock_document() -> ResearchDocument:
    d = ResearchDocument(
        id=DOC_ID,
        document_type=DocumentType.ANNUAL_REPORT,
        title="Test Report",
        source_tier=SourceTier.TIER_1,
        source_name="NSE India",
    )
    d.ingested_at = NOW
    d.source_id = SOURCE_ID
    d.company_id = None
    d.source_url = None
    d.document_date = None
    d.storage_path = None
    d.content_hash = None
    return d


def _mock_evidence() -> Evidence:
    e = Evidence(
        id=EVIDENCE_ID,
        document_id=DOC_ID,
        evidence_type="FACT",
        claim="Revenue was INR 1000 Cr",
        confidence=ConfidenceLevel.HIGH,
        extracted_by="test_agent",
    )
    e.extracted_at = NOW
    e.context = None
    e.page_or_section = "Page 42"
    return e


def _mock_claim(*, is_verified: bool = False) -> Claim:
    c = Claim(
        id=CLAIM_ID,
        content="Company revenue grew 20% YoY",
        claim_type=ClaimType.FACT,
        confidence=ConfidenceLevel.HIGH,
    )
    c.is_verified = is_verified
    c.verified_at = NOW if is_verified else None
    c.verification_notes = None
    c.created_at = NOW
    c.company_id = None
    c.research_run_id = None
    c.source_agent = None
    c.claim_evidences = []
    return c


# ---------------------------------------------------------------------------
# Source endpoints
# ---------------------------------------------------------------------------


class TestSourceEndpoints:
    def test_create_source(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.create_source.return_value = _mock_source()
        resp = client.post(
            "/api/v1/evidence/sources",
            json={
                "name": "NSE India",
                "source_type": "EXCHANGE",
                "default_tier": "TIER_1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "NSE India"
        assert data["source_type"] == "EXCHANGE"
        assert data["default_tier"] == "TIER_1"

    def test_get_source(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.get_source.return_value = _mock_source()
        resp = client.get(f"/api/v1/evidence/sources/{SOURCE_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(SOURCE_ID)

    def test_get_source_not_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.get_source.side_effect = NotFoundError("Source not found")
        resp = client.get(f"/api/v1/evidence/sources/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_list_sources(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.list_sources.return_value = [_mock_source()]
        resp = client.get("/api/v1/evidence/sources")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Document endpoints
# ---------------------------------------------------------------------------


class TestDocumentEndpoints:
    def test_create_document(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.create_document.return_value = _mock_document()
        resp = client.post(
            "/api/v1/evidence/documents",
            json={
                "document_type": "ANNUAL_REPORT",
                "title": "Test Report",
                "source_tier": "TIER_1",
                "source_name": "NSE India",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Test Report"


# ---------------------------------------------------------------------------
# Evidence endpoints
# ---------------------------------------------------------------------------


class TestEvidenceEndpoints:
    def test_create_evidence(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.create_evidence.return_value = _mock_evidence()
        resp = client.post(
            "/api/v1/evidence/evidences",
            json={
                "document_id": str(DOC_ID),
                "evidence_type": "FACT",
                "claim": "Revenue was INR 1000 Cr",
                "confidence": "HIGH",
                "extracted_by": "test_agent",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["claim"] == "Revenue was INR 1000 Cr"


# ---------------------------------------------------------------------------
# Claim endpoints
# ---------------------------------------------------------------------------


class TestClaimEndpoints:
    def test_create_claim(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.create_claim.return_value = _mock_claim()
        resp = client.post(
            "/api/v1/evidence/claims",
            json={
                "content": "Company revenue grew 20% YoY",
                "claim_type": "FACT",
                "confidence": "HIGH",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["claim_type"] == "FACT"
        assert data["is_verified"] is False

    def test_verify_fact_claim_without_evidence_returns_422(self, client: TestClient, mock_service: AsyncMock) -> None:
        """API-level test: trying to verify an unsupported FACT claim returns 422."""
        mock_service.verify_claim.side_effect = ValidationError(
            message="Claims of type FACT cannot be verified without supporting evidence",
            details={"claim_type": "FACT", "evidence_count": 0},
        )
        resp = client.post(f"/api/v1/evidence/claims/{CLAIM_ID}/verify", json={})
        assert resp.status_code == 422
        assert "cannot be verified without supporting evidence" in resp.json()["error"]["message"]

    def test_verify_fact_claim_with_evidence_succeeds(self, client: TestClient, mock_service: AsyncMock) -> None:
        claim = _mock_claim(is_verified=True)
        claim.verification_notes = "Confirmed"
        mock_service.verify_claim.return_value = claim
        resp = client.post(f"/api/v1/evidence/claims/{CLAIM_ID}/verify", json={"verification_notes": "Confirmed"})
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True

    def test_get_claim(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.get_claim.return_value = _mock_claim()
        resp = client.get(f"/api/v1/evidence/claims/{CLAIM_ID}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Citation resolution endpoint
# ---------------------------------------------------------------------------


class TestCitationResolutionEndpoint:
    def test_resolve_citation(self, client: TestClient, mock_service: AsyncMock) -> None:
        chain = CitationChain(
            claim=ClaimResponse(
                id=CLAIM_ID,
                content="Revenue grew 20%",
                claim_type=ClaimType.FACT,
                company_id=None,
                research_run_id=None,
                source_agent=None,
                confidence=ConfidenceLevel.HIGH,
                is_verified=True,
                verified_at=NOW,
                verification_notes=None,
                created_at=NOW,
            ),
            evidences=[
                CitationEvidence(
                    id=EVIDENCE_ID,
                    evidence_type="FACT",
                    claim="Revenue was INR 1000 Cr",
                    page_or_section="Page 42",
                    confidence=ConfidenceLevel.HIGH,
                    extracted_at=NOW,
                    document=CitationDocument(
                        id=DOC_ID,
                        title="Annual Report FY24",
                        document_type=DocumentType.ANNUAL_REPORT,
                        source_tier=SourceTier.TIER_1,
                        source_name="NSE India",
                        document_date=None,
                        source=None,
                    ),
                ),
            ],
        )
        mock_service.resolve_citation.return_value = chain
        resp = client.get(f"/api/v1/evidence/claims/{CLAIM_ID}/citation")

        assert resp.status_code == 200
        data = resp.json()
        assert data["claim"]["id"] == str(CLAIM_ID)
        assert len(data["evidences"]) == 1
        assert data["evidences"][0]["document"]["title"] == "Annual Report FY24"
        assert data["evidences"][0]["document"]["source_tier"] == "TIER_1"
