"""Pydantic v2 schemas for the Evidence subsystem API."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ClaimType,
    ConfidenceLevel,
    DocumentType,
    SourceTier,
    SourceType,
)

# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class SourceCreate(BaseModel):
    name: str = Field(max_length=200)
    source_type: SourceType
    url: str | None = Field(default=None, max_length=2000)
    description: str | None = None
    default_tier: SourceTier


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: SourceType
    url: str | None
    description: str | None
    default_tier: SourceTier
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class DocumentCreate(BaseModel):
    company_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    document_type: DocumentType
    title: str = Field(max_length=1000)
    source_tier: SourceTier
    source_name: str = Field(max_length=200)
    source_url: str | None = Field(default=None, max_length=2000)
    document_date: date | None = None
    storage_path: str | None = None
    content_hash: str | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    source_id: uuid.UUID | None
    document_type: DocumentType
    title: str
    source_tier: SourceTier
    source_name: str
    source_url: str | None
    document_date: date | None
    storage_path: str | None
    content_hash: str | None
    ingested_at: datetime


class DocumentVersionCreate(BaseModel):
    version_number: int = Field(gt=0)
    content_hash: str | None = None
    storage_path: str | None = None
    changes_summary: str | None = None


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    content_hash: str | None
    storage_path: str | None
    retrieved_at: datetime
    changes_summary: str | None


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class EvidenceCreate(BaseModel):
    document_id: uuid.UUID
    evidence_type: str = Field(max_length=50)
    claim: str
    context: str | None = None
    page_or_section: str | None = Field(default=None, max_length=200)
    confidence: ConfidenceLevel
    extracted_by: str = Field(max_length=100)


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    evidence_type: str
    claim: str
    context: str | None
    page_or_section: str | None
    confidence: ConfidenceLevel
    extracted_at: datetime
    extracted_by: str


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


class ClaimCreate(BaseModel):
    content: str
    claim_type: ClaimType
    company_id: uuid.UUID | None = None
    research_run_id: uuid.UUID | None = None
    source_agent: str | None = Field(default=None, max_length=100)
    confidence: ConfidenceLevel


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    claim_type: ClaimType
    company_id: uuid.UUID | None
    research_run_id: uuid.UUID | None
    source_agent: str | None
    confidence: ConfidenceLevel
    is_verified: bool
    verified_at: datetime | None
    verification_notes: str | None
    created_at: datetime


class ClaimVerifyRequest(BaseModel):
    verification_notes: str | None = None


class ClaimEvidenceLinkRequest(BaseModel):
    evidence_id: uuid.UUID
    relevance: str | None = Field(default=None, max_length=200)
    excerpt: str | None = None
    is_primary: bool = False


class ClaimEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    relevance: str | None
    excerpt: str | None
    is_primary: bool


# ---------------------------------------------------------------------------
# Citation resolution
# ---------------------------------------------------------------------------


class CitationSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: SourceType
    default_tier: SourceTier


class CitationDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    document_type: DocumentType
    source_tier: SourceTier
    source_name: str
    document_date: date | None
    source: CitationSource | None = None


class CitationEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_type: str
    claim: str
    page_or_section: str | None
    confidence: ConfidenceLevel
    extracted_at: datetime
    document: CitationDocument


class CitationChain(BaseModel):
    claim: ClaimResponse
    evidences: list[CitationEvidence]


# ---------------------------------------------------------------------------
# Source reliability
# ---------------------------------------------------------------------------


class SourceReliabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    assessed_at: datetime
    reliability_score: float
    total_claims: int
    verified_claims: int
    refuted_claims: int
    notes: str | None
