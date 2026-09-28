"""Repositories for Evidence subsystem entities."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.evidence import Claim, ClaimEvidence, DocumentVersion, Source, SourceReliability
from app.models.research import Evidence, ResearchDocument
from app.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Source)

    async def get_by_name(self, name: str) -> Source | None:
        stmt = sa.select(Source).where(Source.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class DocumentRepository(BaseRepository[ResearchDocument]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ResearchDocument)

    async def get_with_versions(self, document_id: uuid.UUID) -> ResearchDocument | None:
        stmt = (
            sa.select(ResearchDocument)
            .options(selectinload(ResearchDocument.versions))
            .where(ResearchDocument.id == document_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_version(self, version: DocumentVersion) -> DocumentVersion:
        self._session.add(version)
        await self._session.flush()
        await self._session.refresh(version)
        return version


class EvidenceRepository(BaseRepository[Evidence]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Evidence)

    async def get_with_document(self, evidence_id: uuid.UUID) -> Evidence | None:
        stmt = (
            sa.select(Evidence)
            .options(
                selectinload(Evidence.document).selectinload(ResearchDocument.source),
            )
            .where(Evidence.id == evidence_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_document(self, document_id: uuid.UUID) -> list[Evidence]:
        stmt = sa.select(Evidence).where(Evidence.document_id == document_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ClaimRepository(BaseRepository[Claim]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Claim)

    async def get_with_evidences(self, claim_id: uuid.UUID) -> Claim | None:
        stmt = (
            sa.select(Claim)
            .options(
                selectinload(Claim.claim_evidences).selectinload(ClaimEvidence.evidence),
            )
            .where(Claim.id == claim_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_full_chain(self, claim_id: uuid.UUID) -> Claim | None:
        """Load claim with evidence → document → source chain for citation resolution."""
        stmt = (
            sa.select(Claim)
            .options(
                selectinload(Claim.claim_evidences)
                .selectinload(ClaimEvidence.evidence)
                .selectinload(Evidence.document)
                .selectinload(ResearchDocument.source),
            )
            .where(Claim.id == claim_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def link_evidence(self, link: ClaimEvidence) -> ClaimEvidence:
        self._session.add(link)
        await self._session.flush()
        await self._session.refresh(link)
        return link

    async def list_by_company(
        self,
        company_id: uuid.UUID,
        *,
        claim_type: str | None = None,
        verified_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Claim]:
        stmt = sa.select(Claim).where(Claim.company_id == company_id)
        if claim_type is not None:
            stmt = stmt.where(Claim.claim_type == claim_type)
        if verified_only:
            stmt = stmt.where(Claim.is_verified.is_(True))
        stmt = stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_source(
        self,
        source_id: uuid.UUID,
    ) -> tuple[int, int, int]:
        """Count total, verified, and refuted claims linked to evidence from a source.

        Returns (total_claims, verified_claims, refuted_claims).
        Refuted = claims that have evidence but is_verified is False and verification_notes is set.
        """
        stmt = (
            sa.select(
                sa.func.count(sa.distinct(Claim.id)).label("total"),
                sa.func.count(sa.distinct(Claim.id)).filter(Claim.is_verified.is_(True)).label("verified"),
                sa.func.count(sa.distinct(Claim.id))
                .filter(Claim.is_verified.is_(False), Claim.verification_notes.isnot(None))
                .label("refuted"),
            )
            .select_from(Claim)
            .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
            .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
            .join(ResearchDocument, ResearchDocument.id == Evidence.document_id)
            .where(ResearchDocument.source_id == source_id)
        )
        result = await self._session.execute(stmt)
        row = result.one()
        return (row.total, row.verified, row.refuted)


class SourceReliabilityRepository(BaseRepository[SourceReliability]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceReliability)

    async def get_latest_for_source(self, source_id: uuid.UUID) -> SourceReliability | None:
        stmt = (
            sa.select(SourceReliability)
            .where(SourceReliability.source_id == source_id)
            .order_by(SourceReliability.assessed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
