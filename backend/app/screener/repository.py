"""Database operations for the Stock Screener."""
from __future__ import annotations

import uuid
from collections.abc import Sequence  # noqa: TC003 — used in return annotations

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 — used in __init__ signature

from app.models.screening import CompanyScreeningData, SavedScreen


class ScreenRepository:
    """CRUD for saved screens and screening-data queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # SavedScreen CRUD
    # ------------------------------------------------------------------

    async def create_screen(
        self,
        *,
        name: str,
        description: str | None,
        criteria: dict[str, object],
    ) -> SavedScreen:
        screen = SavedScreen(
            id=uuid.uuid4(),
            name=name,
            description=description,
            criteria=criteria,
        )
        self._session.add(screen)
        await self._session.flush()
        return screen

    async def get_screen(self, screen_id: uuid.UUID) -> SavedScreen | None:
        return await self._session.get(SavedScreen, screen_id)

    async def list_screens(self) -> Sequence[SavedScreen]:
        result = await self._session.execute(
            select(SavedScreen).order_by(SavedScreen.updated_at.desc()),
        )
        return result.scalars().all()

    async def delete_screen(self, screen_id: uuid.UUID) -> bool:
        screen = await self.get_screen(screen_id)
        if screen is None:
            return False
        await self._session.delete(screen)
        await self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Screening queries
    # ------------------------------------------------------------------

    async def screen_companies(
        self,
        conditions: Sequence[sa.ColumnElement[bool]],
        *,
        sort_by: str | None = None,
        sort_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[CompanyScreeningData], int]:
        """Apply *conditions* and return matching rows + total count."""
        base = select(CompanyScreeningData)
        count_base = select(func.count()).select_from(CompanyScreeningData)

        for cond in conditions:
            base = base.where(cond)
            count_base = count_base.where(cond)

        if sort_by is not None:
            col = getattr(CompanyScreeningData, sort_by)
            base = base.order_by(col.desc() if sort_desc else col.asc())
        else:
            base = base.order_by(CompanyScreeningData.company_name.asc())

        base = base.limit(limit).offset(offset)

        rows_result = await self._session.execute(base)
        count_result = await self._session.execute(count_base)
        return rows_result.scalars().all(), count_result.scalar_one()

    async def list_companies(
        self,
        *,
        exchange: str | None = None,
        sector: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[CompanyScreeningData], int]:
        """List companies with optional exchange/sector filter."""
        query = select(CompanyScreeningData)
        count_query = select(func.count()).select_from(CompanyScreeningData)

        if exchange is not None:
            query = query.where(CompanyScreeningData.exchange == exchange)
            count_query = count_query.where(CompanyScreeningData.exchange == exchange)
        if sector is not None:
            query = query.where(CompanyScreeningData.sector == sector)
            count_query = count_query.where(CompanyScreeningData.sector == sector)

        query = query.order_by(CompanyScreeningData.company_name.asc())
        query = query.limit(limit).offset(offset)

        rows_result = await self._session.execute(query)
        count_result = await self._session.execute(count_query)
        return rows_result.scalars().all(), count_result.scalar_one()
