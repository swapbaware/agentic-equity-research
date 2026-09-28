"""FastAPI endpoints for the Stock Screener.

Endpoints
---------
GET  /companies                — List companies with optional exchange/sector filter
POST /screens                  — Create (save) a screen
GET  /screens                  — List saved screens
GET  /screens/{screen_id}      — Get a single saved screen
POST /screens/{screen_id}/execute — Execute a saved screen
POST /screens/execute          — Execute an ad-hoc screen without saving
DELETE /screens/{screen_id}    — Delete a saved screen
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_screen_service
from app.screener.schemas import (
    AdHocScreenRequest,
    CreateScreenRequest,
    ExecuteScreenRequest,
    SavedScreenResponse,
    ScreenExecutionResult,
)
from app.screener.service import ScreenService

router = APIRouter(tags=["screener"])

ServiceDep = Annotated[ScreenService, Depends(get_screen_service)]


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid screen ID") from exc


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@router.get("/companies", response_model=ScreenExecutionResult)
async def list_companies(
    service: ServiceDep,
    exchange: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ScreenExecutionResult:
    return await service.list_companies(
        exchange=exchange, sector=sector, limit=limit, offset=offset,
    )


# ---------------------------------------------------------------------------
# Screens — CRUD
# ---------------------------------------------------------------------------


@router.post("/screens", response_model=SavedScreenResponse, status_code=201)
async def create_screen(
    body: CreateScreenRequest, service: ServiceDep,
) -> SavedScreenResponse:
    return await service.create_screen(body)


@router.get("/screens", response_model=list[SavedScreenResponse])
async def list_screens(service: ServiceDep) -> list[SavedScreenResponse]:
    return await service.list_screens()


@router.get("/screens/{screen_id}", response_model=SavedScreenResponse)
async def get_screen(
    screen_id: str, service: ServiceDep,
) -> SavedScreenResponse:
    sid = _parse_uuid(screen_id)
    result = await service.get_screen(sid)
    if result is None:
        raise HTTPException(status_code=404, detail="Screen not found")
    return result


@router.delete("/screens/{screen_id}", status_code=204)
async def delete_screen(
    screen_id: str, service: ServiceDep,
) -> None:
    sid = _parse_uuid(screen_id)
    deleted = await service.delete_screen(sid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Screen not found")


# ---------------------------------------------------------------------------
# Screens — Execution
# ---------------------------------------------------------------------------


@router.post(
    "/screens/execute",
    response_model=ScreenExecutionResult,
)
async def execute_ad_hoc(
    body: AdHocScreenRequest, service: ServiceDep,
) -> ScreenExecutionResult:
    params = ExecuteScreenRequest(
        limit=body.limit,
        offset=body.offset,
        sort_by=body.sort_by,
        sort_desc=body.sort_desc,
    )
    return await service.execute_ad_hoc(body.groups, params)


@router.post(
    "/screens/{screen_id}/execute",
    response_model=ScreenExecutionResult,
)
async def execute_screen(
    screen_id: str,
    service: ServiceDep,
    body: ExecuteScreenRequest | None = None,
) -> ScreenExecutionResult:
    sid = _parse_uuid(screen_id)
    params = body or ExecuteScreenRequest()
    result = await service.execute_screen(sid, params)
    if result is None:
        raise HTTPException(status_code=404, detail="Screen not found")
    return result
