"""Generic async repository base class for SQLAlchemy models."""
from __future__ import annotations

import uuid
from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model_class: type[ModelT]) -> None:
        self._session = session
        self._model_class = model_class

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self._model_class, entity_id)

    async def create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = sa.select(self._model_class).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.flush()
