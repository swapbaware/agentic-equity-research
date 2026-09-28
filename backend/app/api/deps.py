"""FastAPI dependency injection for database sessions and services."""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import create_session_factory
from app.screener.repository import ScreenRepository
from app.screener.service import ScreenService
from app.services.evidence import EvidenceService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    engine = request.app.state.db_engine
    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        yield session


async def get_evidence_service(request: Request) -> AsyncIterator[EvidenceService]:
    engine = request.app.state.db_engine
    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        yield EvidenceService(session)


async def get_screen_service(request: Request) -> AsyncIterator[ScreenService]:
    engine = request.app.state.db_engine
    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        repo = ScreenRepository(session)
        yield ScreenService(repo)
