"""Evidence domain service — citation resolution, claim verification, source reliability."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, ValidationError
from app.models.enums import ClaimType
from app.models.evidence import Claim, ClaimEvidence, Source, SourceReliability
from app.models.research import Evidence, ResearchDocument
from app.repositories.evidence import (
    ClaimRepository,
    DocumentRepository,
    EvidenceRepository,
    SourceReliabilityRepository,
    SourceRepository,
)
from app.schemas.evidence import (
    CitationChain,
    CitationDocument,
    CitationEvidence,
    CitationSource,
    ClaimCreate,
    ClaimEvidenceLinkRequest,
    ClaimResponse,
    ClaimVerifyRequest,
    DocumentCreate,
    DocumentVersionCreate,
    EvidenceCreate,
    SourceCreate,
)

EVIDENCE_REQUIRED_CLAIM_TYPES = frozenset({ClaimType.FACT, ClaimType.CALCULATION})


class EvidenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sources = SourceRepository(session)
        self._documents = DocumentRepository(session)
        self._evidences = EvidenceRepository(session)
        self._claims = ClaimRepository(session)
        self._reliability = SourceReliabilityRepository(session)

    # -- Source operations --------------------------------------------------

    async def create_source(self, data: SourceCreate) -> Source:
        existing = await self._sources.get_by_name(data.name)
        if existing is not None:
            raise ValidationError(
                message=f"Source with name '{data.name}' already exists",
                details={"existing_id": str(existing.id)},
            )
        source = Source(
            name=data.name,
            source_type=data.source_type,
            url=data.url,
            description=data.description,
            default_tier=data.default_tier,
        )
        return await self._sources.create(source)

    async def get_source(self, source_id: uuid.UUID) -> Source:
        source = await self._sources.get_by_id(source_id)
        if source is None:
            raise NotFoundError(message="Source not found", details={"source_id": str(source_id)})
        return source

    async def list_sources(self, *, limit: int = 100, offset: int = 0) -> list[Source]:
        return await self._sources.list_all(limit=limit, offset=offset)

    # -- Document operations ------------------------------------------------

    async def create_document(self, data: DocumentCreate) -> ResearchDocument:
        if data.source_id is not None:
            source = await self._sources.get_by_id(data.source_id)
            if source is None:
                raise NotFoundError(message="Source not found", details={"source_id": str(data.source_id)})
        doc = ResearchDocument(
            company_id=data.company_id,
            source_id=data.source_id,
            document_type=data.document_type,
            title=data.title,
            source_tier=data.source_tier,
            source_name=data.source_name,
            source_url=data.source_url,
            document_date=data.document_date,
            storage_path=data.storage_path,
            content_hash=data.content_hash,
        )
        return await self._documents.create(doc)

    async def get_document(self, document_id: uuid.UUID) -> ResearchDocument:
        doc = await self._documents.get_with_versions(document_id)
        if doc is None:
            raise NotFoundError(message="Document not found", details={"document_id": str(document_id)})
        return doc

    async def add_document_version(
        self,
        document_id: uuid.UUID,
        data: DocumentVersionCreate,
    ) -> ResearchDocument:
        from app.models.evidence import DocumentVersion

        doc = await self._documents.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(message="Document not found", details={"document_id": str(document_id)})
        version = DocumentVersion(
            document_id=document_id,
            version_number=data.version_number,
            content_hash=data.content_hash,
            storage_path=data.storage_path,
            changes_summary=data.changes_summary,
        )
        await self._documents.add_version(version)
        return await self._documents.get_with_versions(document_id)  # type: ignore[return-value]

    # -- Evidence operations ------------------------------------------------

    async def create_evidence(self, data: EvidenceCreate) -> Evidence:
        doc = await self._documents.get_by_id(data.document_id)
        if doc is None:
            raise NotFoundError(message="Document not found", details={"document_id": str(data.document_id)})
        evidence = Evidence(
            document_id=data.document_id,
            evidence_type=data.evidence_type,
            claim=data.claim,
            context=data.context,
            page_or_section=data.page_or_section,
            confidence=data.confidence,
            extracted_by=data.extracted_by,
        )
        return await self._evidences.create(evidence)

    async def get_evidence(self, evidence_id: uuid.UUID) -> Evidence:
        evidence = await self._evidences.get_with_document(evidence_id)
        if evidence is None:
            raise NotFoundError(message="Evidence not found", details={"evidence_id": str(evidence_id)})
        return evidence

    # -- Claim operations ---------------------------------------------------

    async def create_claim(self, data: ClaimCreate) -> Claim:
        claim = Claim(
            content=data.content,
            claim_type=data.claim_type,
            company_id=data.company_id,
            research_run_id=data.research_run_id,
            source_agent=data.source_agent,
            confidence=data.confidence,
        )
        return await self._claims.create(claim)

    async def get_claim(self, claim_id: uuid.UUID) -> Claim:
        claim = await self._claims.get_with_evidences(claim_id)
        if claim is None:
            raise NotFoundError(message="Claim not found", details={"claim_id": str(claim_id)})
        return claim

    async def link_evidence_to_claim(
        self,
        claim_id: uuid.UUID,
        data: ClaimEvidenceLinkRequest,
    ) -> ClaimEvidence:
        claim = await self._claims.get_by_id(claim_id)
        if claim is None:
            raise NotFoundError(message="Claim not found", details={"claim_id": str(claim_id)})
        evidence = await self._evidences.get_by_id(data.evidence_id)
        if evidence is None:
            raise NotFoundError(message="Evidence not found", details={"evidence_id": str(data.evidence_id)})
        link = ClaimEvidence(
            claim_id=claim_id,
            evidence_id=data.evidence_id,
            relevance=data.relevance,
            excerpt=data.excerpt,
            is_primary=data.is_primary,
        )
        return await self._claims.link_evidence(link)

    async def verify_claim(
        self,
        claim_id: uuid.UUID,
        data: ClaimVerifyRequest,
    ) -> Claim:
        """Verify a claim. FACT and CALCULATION claims require linked evidence."""
        claim = await self._claims.get_with_evidences(claim_id)
        if claim is None:
            raise NotFoundError(message="Claim not found", details={"claim_id": str(claim_id)})

        if claim.is_verified:
            raise ValidationError(message="Claim is already verified")

        if claim.claim_type in EVIDENCE_REQUIRED_CLAIM_TYPES and not claim.claim_evidences:
            raise ValidationError(
                message=f"Claims of type {claim.claim_type.value} cannot be verified without supporting evidence",
                details={"claim_type": claim.claim_type.value, "evidence_count": 0},
            )

        claim.is_verified = True
        claim.verified_at = datetime.now(UTC)
        claim.verification_notes = data.verification_notes
        await self._session.flush()
        await self._session.refresh(claim)
        return claim

    # -- Citation resolution ------------------------------------------------

    async def resolve_citation(self, claim_id: uuid.UUID) -> CitationChain:
        """Resolve the full citation chain: claim → evidence(s) → document(s) → source(s)."""
        claim = await self._claims.get_with_full_chain(claim_id)
        if claim is None:
            raise NotFoundError(message="Claim not found", details={"claim_id": str(claim_id)})

        citation_evidences: list[CitationEvidence] = []
        for ce in claim.claim_evidences:
            ev = ce.evidence
            doc = ev.document

            citation_source: CitationSource | None = None
            if doc.source is not None:
                citation_source = CitationSource.model_validate(doc.source)

            citation_doc = CitationDocument(
                id=doc.id,
                title=doc.title,
                document_type=doc.document_type,
                source_tier=doc.source_tier,
                source_name=doc.source_name,
                document_date=doc.document_date,
                source=citation_source,
            )
            citation_evidences.append(
                CitationEvidence(
                    id=ev.id,
                    evidence_type=ev.evidence_type,
                    claim=ev.claim,
                    page_or_section=ev.page_or_section,
                    confidence=ev.confidence,
                    extracted_at=ev.extracted_at,
                    document=citation_doc,
                )
            )

        return CitationChain(
            claim=ClaimResponse.model_validate(claim),
            evidences=citation_evidences,
        )

    # -- Source reliability -------------------------------------------------

    async def assess_source_reliability(self, source_id: uuid.UUID) -> SourceReliability:
        """Calculate and record source reliability based on linked claim verification status."""
        source = await self._sources.get_by_id(source_id)
        if source is None:
            raise NotFoundError(message="Source not found", details={"source_id": str(source_id)})

        total, verified, refuted = await self._claims.count_by_source(source_id)
        score = Decimal("1.0") if total == 0 else Decimal(verified) / Decimal(total)

        assessment = SourceReliability(
            source_id=source_id,
            reliability_score=score.quantize(Decimal("0.0001")),
            total_claims=total,
            verified_claims=verified,
            refuted_claims=refuted,
        )
        return await self._reliability.create(assessment)
