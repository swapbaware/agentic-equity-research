"""Evidence subsystem API endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_evidence_service
from app.schemas.evidence import (
    CitationChain,
    ClaimCreate,
    ClaimEvidenceLinkRequest,
    ClaimEvidenceResponse,
    ClaimResponse,
    ClaimVerifyRequest,
    DocumentCreate,
    DocumentResponse,
    DocumentVersionCreate,
    DocumentVersionResponse,
    EvidenceCreate,
    EvidenceResponse,
    SourceCreate,
    SourceReliabilityResponse,
    SourceResponse,
)
from app.services.evidence import EvidenceService

router = APIRouter(prefix="/evidence", tags=["evidence"])

ServiceDep = Annotated[EvidenceService, Depends(get_evidence_service)]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(data: SourceCreate, service: ServiceDep) -> SourceResponse:
    source = await service.create_source(data)
    return SourceResponse.model_validate(source)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(source_id: uuid.UUID, service: ServiceDep) -> SourceResponse:
    source = await service.get_source(source_id)
    return SourceResponse.model_validate(source)


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    service: ServiceDep,
    limit: int = 100,
    offset: int = 0,
) -> list[SourceResponse]:
    sources = await service.list_sources(limit=limit, offset=offset)
    return [SourceResponse.model_validate(s) for s in sources]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def create_document(data: DocumentCreate, service: ServiceDep) -> DocumentResponse:
    doc = await service.create_document(data)
    return DocumentResponse.model_validate(doc)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID, service: ServiceDep) -> DocumentResponse:
    doc = await service.get_document(document_id)
    return DocumentResponse.model_validate(doc)


@router.post(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    status_code=201,
)
async def add_document_version(
    document_id: uuid.UUID,
    data: DocumentVersionCreate,
    service: ServiceDep,
) -> list[DocumentVersionResponse]:
    doc = await service.add_document_version(document_id, data)
    return [DocumentVersionResponse.model_validate(v) for v in doc.versions]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@router.post("/evidences", response_model=EvidenceResponse, status_code=201)
async def create_evidence(data: EvidenceCreate, service: ServiceDep) -> EvidenceResponse:
    evidence = await service.create_evidence(data)
    return EvidenceResponse.model_validate(evidence)


@router.get("/evidences/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_id: uuid.UUID, service: ServiceDep) -> EvidenceResponse:
    evidence = await service.get_evidence(evidence_id)
    return EvidenceResponse.model_validate(evidence)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


@router.post("/claims", response_model=ClaimResponse, status_code=201)
async def create_claim(data: ClaimCreate, service: ServiceDep) -> ClaimResponse:
    claim = await service.create_claim(data)
    return ClaimResponse.model_validate(claim)


@router.get("/claims/{claim_id}", response_model=ClaimResponse)
async def get_claim(claim_id: uuid.UUID, service: ServiceDep) -> ClaimResponse:
    claim = await service.get_claim(claim_id)
    return ClaimResponse.model_validate(claim)


@router.post(
    "/claims/{claim_id}/evidence",
    response_model=ClaimEvidenceResponse,
    status_code=201,
)
async def link_evidence_to_claim(
    claim_id: uuid.UUID,
    data: ClaimEvidenceLinkRequest,
    service: ServiceDep,
) -> ClaimEvidenceResponse:
    link = await service.link_evidence_to_claim(claim_id, data)
    return ClaimEvidenceResponse.model_validate(link)


@router.post("/claims/{claim_id}/verify", response_model=ClaimResponse)
async def verify_claim(
    claim_id: uuid.UUID,
    data: ClaimVerifyRequest,
    service: ServiceDep,
) -> ClaimResponse:
    claim = await service.verify_claim(claim_id, data)
    return ClaimResponse.model_validate(claim)


@router.get("/claims/{claim_id}/citation", response_model=CitationChain)
async def resolve_citation(claim_id: uuid.UUID, service: ServiceDep) -> CitationChain:
    return await service.resolve_citation(claim_id)


# ---------------------------------------------------------------------------
# Source reliability
# ---------------------------------------------------------------------------


@router.post(
    "/sources/{source_id}/reliability",
    response_model=SourceReliabilityResponse,
    status_code=201,
)
async def assess_source_reliability(
    source_id: uuid.UUID,
    service: ServiceDep,
) -> SourceReliabilityResponse:
    assessment = await service.assess_source_reliability(source_id)
    return SourceReliabilityResponse.model_validate(assessment)
