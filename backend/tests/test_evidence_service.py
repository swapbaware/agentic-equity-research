"""Unit tests for the Evidence domain service.

Key invariant: unsupported FACT/CALCULATION claims cannot be verified.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import NotFoundError, ValidationError
from app.models.enums import (
    ClaimType,
    ConfidenceLevel,
    DocumentType,
    EvidenceType,
    SourceTier,
    SourceType,
)
from app.models.evidence import Claim, ClaimEvidence, Source
from app.models.research import Evidence, ResearchDocument
from app.schemas.evidence import ClaimVerifyRequest
from app.services.evidence import EVIDENCE_REQUIRED_CLAIM_TYPES, EvidenceService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim(
    claim_type: ClaimType,
    *,
    is_verified: bool = False,
    claim_evidences: list[ClaimEvidence] | None = None,
) -> Claim:
    claim = Claim(
        id=uuid.uuid4(),
        content="Test claim content",
        claim_type=claim_type,
        confidence=ConfidenceLevel.MEDIUM,
    )
    claim.is_verified = is_verified
    claim.verified_at = None
    claim.verification_notes = None
    claim.created_at = datetime.now(UTC)
    claim.claim_evidences = claim_evidences or []
    return claim


def _make_evidence_with_chain(
    *,
    source_tier: SourceTier = SourceTier.TIER_1,
    source: Source | None = None,
) -> tuple[ClaimEvidence, Evidence, ResearchDocument]:
    """Build a claim_evidence → evidence → document → source chain."""
    if source is None:
        source = Source(
            id=uuid.uuid4(),
            name="NSE India",
            source_type=SourceType.EXCHANGE,
            default_tier=source_tier,
        )
    doc = ResearchDocument(
        id=uuid.uuid4(),
        document_type=DocumentType.ANNUAL_REPORT,
        title="Test Annual Report",
        source_tier=source_tier,
        source_name=source.name,
        source_id=source.id,
    )
    doc.source = source

    ev = Evidence(
        id=uuid.uuid4(),
        document_id=doc.id,
        evidence_type=EvidenceType.FACT,
        claim="Revenue was INR 1000 Cr",
        confidence=ConfidenceLevel.HIGH,
        extracted_by="data_extraction_agent",
    )
    ev.extracted_at = datetime.now(UTC)
    ev.context = None
    ev.page_or_section = "Page 42"
    ev.document = doc

    ce = ClaimEvidence(
        id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        evidence_id=ev.id,
        is_primary=True,
    )
    ce.evidence = ev
    return ce, ev, doc


def _make_service() -> tuple[EvidenceService, MagicMock]:
    mock_session = MagicMock()
    service = EvidenceService(mock_session)
    return service, mock_session


# ---------------------------------------------------------------------------
# 1. FACT claims CANNOT be verified without evidence
# ---------------------------------------------------------------------------


class TestFactClaimRequiresEvidence:
    """The core invariant: FACT claims need linked evidence to be verified."""

    @pytest.mark.asyncio
    async def test_fact_claim_without_evidence_cannot_be_verified(self) -> None:
        service, _ = _make_service()
        claim = _make_claim(ClaimType.FACT, claim_evidences=[])

        with (
            patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim),
            pytest.raises(ValidationError, match="cannot be verified without supporting evidence"),
        ):
            await service.verify_claim(claim.id, ClaimVerifyRequest())

    @pytest.mark.asyncio
    async def test_fact_claim_with_evidence_can_be_verified(self) -> None:
        service, mock_session = _make_service()
        ce, ev, doc = _make_evidence_with_chain()
        claim = _make_claim(ClaimType.FACT, claim_evidences=[ce])

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim):
            result = await service.verify_claim(claim.id, ClaimVerifyRequest(verification_notes="Confirmed via NSE"))

        assert result.is_verified is True
        assert result.verified_at is not None
        assert result.verification_notes == "Confirmed via NSE"


# ---------------------------------------------------------------------------
# 2. CALCULATION claims CANNOT be verified without evidence
# ---------------------------------------------------------------------------


class TestCalculationClaimRequiresEvidence:
    @pytest.mark.asyncio
    async def test_calculation_claim_without_evidence_cannot_be_verified(self) -> None:
        service, _ = _make_service()
        claim = _make_claim(ClaimType.CALCULATION, claim_evidences=[])

        with (
            patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim),
            pytest.raises(ValidationError, match="cannot be verified without supporting evidence"),
        ):
            await service.verify_claim(claim.id, ClaimVerifyRequest())

    @pytest.mark.asyncio
    async def test_calculation_claim_with_evidence_can_be_verified(self) -> None:
        service, mock_session = _make_service()
        ce, _, _ = _make_evidence_with_chain()
        claim = _make_claim(ClaimType.CALCULATION, claim_evidences=[ce])

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim):
            result = await service.verify_claim(claim.id, ClaimVerifyRequest())

        assert result.is_verified is True


# ---------------------------------------------------------------------------
# 3. Non-evidence claim types CAN be verified without evidence
# ---------------------------------------------------------------------------


class TestNonEvidenceClaimTypes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("claim_type", [
        ClaimType.AI_INFERENCE,
        ClaimType.MANAGEMENT_CLAIM,
        ClaimType.ASSUMPTION,
        ClaimType.EXTERNAL_ANALYST_VIEW,
    ])
    async def test_can_verify_without_evidence(self, claim_type: ClaimType) -> None:
        service, mock_session = _make_service()
        claim = _make_claim(claim_type, claim_evidences=[])

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim):
            result = await service.verify_claim(claim.id, ClaimVerifyRequest())

        assert result.is_verified is True


# ---------------------------------------------------------------------------
# 4. Already-verified claims cannot be re-verified
# ---------------------------------------------------------------------------


class TestAlreadyVerified:
    @pytest.mark.asyncio
    async def test_already_verified_claim_raises_error(self) -> None:
        service, _ = _make_service()
        claim = _make_claim(ClaimType.FACT, is_verified=True)

        with (
            patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=claim),
            pytest.raises(ValidationError, match="already verified"),
        ):
            await service.verify_claim(claim.id, ClaimVerifyRequest())


# ---------------------------------------------------------------------------
# 5. Claim not found raises NotFoundError
# ---------------------------------------------------------------------------


class TestClaimNotFound:
    @pytest.mark.asyncio
    async def test_verify_nonexistent_claim_raises_not_found(self) -> None:
        service, _ = _make_service()
        fake_id = uuid.uuid4()

        with (
            patch.object(service._claims, "get_with_evidences", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Claim not found"),
        ):
            await service.verify_claim(fake_id, ClaimVerifyRequest())


# ---------------------------------------------------------------------------
# 6. Citation resolution returns full chain
# ---------------------------------------------------------------------------


class TestCitationResolution:
    @pytest.mark.asyncio
    async def test_resolve_citation_returns_full_chain(self) -> None:
        service, _ = _make_service()
        ce, ev, doc = _make_evidence_with_chain(source_tier=SourceTier.TIER_1)
        claim = _make_claim(ClaimType.FACT, claim_evidences=[ce])

        with patch.object(service._claims, "get_with_full_chain", new_callable=AsyncMock, return_value=claim):
            chain = await service.resolve_citation(claim.id)

        assert chain.claim.id == claim.id
        assert chain.claim.claim_type == ClaimType.FACT
        assert len(chain.evidences) == 1

        citation_ev = chain.evidences[0]
        assert citation_ev.id == ev.id
        assert citation_ev.document.id == doc.id
        assert citation_ev.document.source is not None
        assert citation_ev.document.source.name == "NSE India"
        assert citation_ev.document.source_tier == SourceTier.TIER_1

    @pytest.mark.asyncio
    async def test_resolve_citation_claim_not_found(self) -> None:
        service, _ = _make_service()

        with (
            patch.object(service._claims, "get_with_full_chain", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Claim not found"),
        ):
            await service.resolve_citation(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_resolve_citation_without_source(self) -> None:
        """Document without a linked Source entity — citation still resolves."""
        service, _ = _make_service()

        doc = ResearchDocument(
            id=uuid.uuid4(),
            document_type=DocumentType.NEWS,
            title="News Article",
            source_tier=SourceTier.TIER_3,
            source_name="Financial Express",
        )
        doc.source = None

        ev = Evidence(
            id=uuid.uuid4(),
            document_id=doc.id,
            evidence_type=EvidenceType.ANALYST_OPINION,
            claim="Analyst says buy",
            confidence=ConfidenceLevel.LOW,
            extracted_by="manual",
        )
        ev.extracted_at = datetime.now(UTC)
        ev.context = None
        ev.page_or_section = None
        ev.document = doc

        ce = ClaimEvidence(
            id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            evidence_id=ev.id,
        )
        ce.evidence = ev

        claim = _make_claim(ClaimType.EXTERNAL_ANALYST_VIEW, claim_evidences=[ce])

        with patch.object(service._claims, "get_with_full_chain", new_callable=AsyncMock, return_value=claim):
            chain = await service.resolve_citation(claim.id)

        assert chain.evidences[0].document.source is None


# ---------------------------------------------------------------------------
# 7. Evidence-required claim types constant is correct
# ---------------------------------------------------------------------------


class TestEvidenceRequiredClaimTypes:
    def test_fact_requires_evidence(self) -> None:
        assert ClaimType.FACT in EVIDENCE_REQUIRED_CLAIM_TYPES

    def test_calculation_requires_evidence(self) -> None:
        assert ClaimType.CALCULATION in EVIDENCE_REQUIRED_CLAIM_TYPES

    def test_ai_inference_does_not_require_evidence(self) -> None:
        assert ClaimType.AI_INFERENCE not in EVIDENCE_REQUIRED_CLAIM_TYPES

    def test_management_claim_does_not_require_evidence(self) -> None:
        assert ClaimType.MANAGEMENT_CLAIM not in EVIDENCE_REQUIRED_CLAIM_TYPES

    def test_assumption_does_not_require_evidence(self) -> None:
        assert ClaimType.ASSUMPTION not in EVIDENCE_REQUIRED_CLAIM_TYPES

    def test_external_analyst_view_does_not_require_evidence(self) -> None:
        assert ClaimType.EXTERNAL_ANALYST_VIEW not in EVIDENCE_REQUIRED_CLAIM_TYPES


# ---------------------------------------------------------------------------
# 8. Source reliability assessment
# ---------------------------------------------------------------------------


class TestSourceReliability:
    @pytest.mark.asyncio
    async def test_assess_reliability_with_no_claims(self) -> None:
        service, _ = _make_service()
        source = Source(
            id=uuid.uuid4(),
            name="Test Source",
            source_type=SourceType.NEWS,
            default_tier=SourceTier.TIER_3,
        )

        with (
            patch.object(service._sources, "get_by_id", new_callable=AsyncMock, return_value=source),
            patch.object(service._claims, "count_by_source", new_callable=AsyncMock, return_value=(0, 0, 0)),
            patch.object(service._reliability, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda sr: sr
            result = await service.assess_source_reliability(source.id)

        assert result.reliability_score == Decimal("1.0000")
        assert result.total_claims == 0

    @pytest.mark.asyncio
    async def test_assess_reliability_with_mixed_claims(self) -> None:
        service, _ = _make_service()
        source = Source(
            id=uuid.uuid4(),
            name="BSE India",
            source_type=SourceType.EXCHANGE,
            default_tier=SourceTier.TIER_1,
        )

        with (
            patch.object(service._sources, "get_by_id", new_callable=AsyncMock, return_value=source),
            patch.object(service._claims, "count_by_source", new_callable=AsyncMock, return_value=(10, 8, 2)),
            patch.object(service._reliability, "create", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = lambda sr: sr
            result = await service.assess_source_reliability(source.id)

        assert result.reliability_score == Decimal("0.8000")
        assert result.total_claims == 10
        assert result.verified_claims == 8
        assert result.refuted_claims == 2

    @pytest.mark.asyncio
    async def test_assess_reliability_source_not_found(self) -> None:
        service, _ = _make_service()

        with (
            patch.object(service._sources, "get_by_id", new_callable=AsyncMock, return_value=None),
            pytest.raises(NotFoundError, match="Source not found"),
        ):
            await service.assess_source_reliability(uuid.uuid4())


# ---------------------------------------------------------------------------
# 9. ClaimType enum has exactly the requested values
# ---------------------------------------------------------------------------


class TestClaimTypeEnum:
    def test_claim_type_values(self) -> None:
        assert {e.value for e in ClaimType} == {
            "FACT",
            "CALCULATION",
            "MANAGEMENT_CLAIM",
            "EXTERNAL_ANALYST_VIEW",
            "AI_INFERENCE",
            "ASSUMPTION",
        }

    def test_claim_type_count(self) -> None:
        assert len(ClaimType) == 6
