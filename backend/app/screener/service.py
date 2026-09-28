"""Business logic layer for the Stock Screener."""
from __future__ import annotations

import uuid  # noqa: TC003 — used in method signatures

from app.models.screening import CompanyScreeningData, SavedScreen  # noqa: TC001 — used in type annotations
from app.screener.executor import build_conditions
from app.screener.repository import ScreenRepository  # noqa: TC001 — used in __init__
from app.screener.schemas import (
    CompanyResult,
    CreateScreenRequest,
    ExecuteScreenRequest,
    FilterGroup,
    SavedScreenResponse,
    ScreenDefinition,
    ScreenExecutionResult,
)


class ScreenService:
    """Orchestrates screen persistence and execution."""

    def __init__(self, repo: ScreenRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Screen CRUD
    # ------------------------------------------------------------------

    async def create_screen(
        self, request: CreateScreenRequest,
    ) -> SavedScreenResponse:
        criteria_json: dict[str, object] = {
            "groups": [g.model_dump(mode="json") for g in request.groups],
        }
        screen = await self._repo.create_screen(
            name=request.name,
            description=request.description,
            criteria=criteria_json,
        )
        return _screen_to_response(screen)

    async def get_screen(
        self, screen_id: uuid.UUID,
    ) -> SavedScreenResponse | None:
        screen = await self._repo.get_screen(screen_id)
        if screen is None:
            return None
        return _screen_to_response(screen)

    async def list_screens(self) -> list[SavedScreenResponse]:
        screens = await self._repo.list_screens()
        return [_screen_to_response(s) for s in screens]

    async def delete_screen(self, screen_id: uuid.UUID) -> bool:
        return await self._repo.delete_screen(screen_id)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_screen(
        self,
        screen_id: uuid.UUID,
        params: ExecuteScreenRequest,
    ) -> ScreenExecutionResult | None:
        screen = await self._repo.get_screen(screen_id)
        if screen is None:
            return None

        groups = _parse_groups(screen.criteria)
        definition = ScreenDefinition(groups=tuple(groups))
        conditions = build_conditions(definition)

        rows, total = await self._repo.screen_companies(
            conditions,
            sort_by=params.sort_by.value if params.sort_by else None,
            sort_desc=params.sort_desc,
            limit=params.limit,
            offset=params.offset,
        )
        return ScreenExecutionResult(
            screen_id=str(screen_id),
            total_matches=total,
            companies=[_row_to_result(r) for r in rows],
        )

    async def execute_ad_hoc(
        self,
        groups: list[FilterGroup],
        params: ExecuteScreenRequest,
    ) -> ScreenExecutionResult:
        definition = ScreenDefinition(groups=tuple(groups))
        conditions = build_conditions(definition)

        rows, total = await self._repo.screen_companies(
            conditions,
            sort_by=params.sort_by.value if params.sort_by else None,
            sort_desc=params.sort_desc,
            limit=params.limit,
            offset=params.offset,
        )
        return ScreenExecutionResult(
            screen_id=None,
            total_matches=total,
            companies=[_row_to_result(r) for r in rows],
        )

    async def list_companies(
        self,
        *,
        exchange: str | None = None,
        sector: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScreenExecutionResult:
        rows, total = await self._repo.list_companies(
            exchange=exchange, sector=sector, limit=limit, offset=offset,
        )
        return ScreenExecutionResult(
            screen_id=None,
            total_matches=total,
            companies=[_row_to_result(r) for r in rows],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _screen_to_response(screen: SavedScreen) -> SavedScreenResponse:
    groups = _parse_groups(screen.criteria)
    return SavedScreenResponse(
        id=str(screen.id),
        name=screen.name,
        description=screen.description,
        groups=groups,
        created_at=screen.created_at,
        updated_at=screen.updated_at,
    )


def _parse_groups(criteria: dict[str, object]) -> list[FilterGroup]:
    raw_groups = criteria.get("groups", [])
    if not isinstance(raw_groups, list):
        return []
    return [FilterGroup(**g) for g in raw_groups]


def _row_to_result(row: CompanyScreeningData) -> CompanyResult:
    return CompanyResult(
        company_id=str(row.company_id),
        symbol=row.symbol,
        company_name=row.company_name,
        exchange=row.exchange,
        sector=row.sector,
        industry=row.industry,
        market_cap=row.market_cap,
        pe_ratio=row.pe_ratio,
        ev_to_ebitda=row.ev_to_ebitda,
        peg_ratio=row.peg_ratio,
        dividend_yield=row.dividend_yield,
        revenue_growth=row.revenue_growth,
        eps_growth=row.eps_growth,
        roe=row.roe,
        roce=row.roce,
        roic=row.roic,
        ebitda_margin=row.ebitda_margin,
        debt_to_equity=row.debt_to_equity,
        net_debt_to_ebitda=row.net_debt_to_ebitda,
        fcf_yield=row.fcf_yield,
        fcf_conversion=row.fcf_conversion,
        promoter_holding=row.promoter_holding,
        promoter_pledge=row.promoter_pledge,
        institutional_ownership=row.institutional_ownership,
        data_period=row.data_period,
    )
