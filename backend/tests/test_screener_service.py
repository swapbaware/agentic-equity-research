"""Tests for ScreenService — business logic with mocked repository."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.screening import CompanyScreeningData, SavedScreen
from app.screener.schemas import (
    CreateScreenRequest,
    ExecuteScreenRequest,
    FilterCriterion,
    FilterGroup,
    Operator,
    ScreenField,
)
from app.screener.service import ScreenService


def _make_saved_screen(
    *,
    name: str = "Test Screen",
    groups: list[dict[str, object]] | None = None,
) -> SavedScreen:
    """Build a SavedScreen-like object without a database."""
    screen = MagicMock(spec=SavedScreen)
    screen.id = uuid.uuid4()
    screen.name = name
    screen.description = "test"
    screen.criteria = {
        "groups": groups or [
            {
                "logic": "AND",
                "negate": False,
                "criteria": [
                    {"field": "roe", "operator": "gt", "value": "0.15"},
                ],
            },
        ],
    }
    screen.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    screen.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return screen


def _make_screening_row(
    *,
    symbol: str = "TCS",
    company_name: str = "TCS Ltd",
    roe: Decimal | None = Decimal("0.35"),
) -> CompanyScreeningData:
    row = MagicMock(spec=CompanyScreeningData)
    row.company_id = uuid.uuid4()
    row.symbol = symbol
    row.company_name = company_name
    row.exchange = "NSE"
    row.sector = "IT"
    row.industry = "Software"
    row.market_cap = Decimal("1500000")
    row.pe_ratio = Decimal("30")
    row.ev_to_ebitda = Decimal("22")
    row.peg_ratio = Decimal("1.5")
    row.dividend_yield = Decimal("0.012")
    row.revenue_growth = Decimal("0.12")
    row.eps_growth = Decimal("0.15")
    row.roe = roe
    row.roce = Decimal("0.28")
    row.roic = Decimal("0.22")
    row.ebitda_margin = Decimal("0.27")
    row.debt_to_equity = Decimal("0.05")
    row.net_debt_to_ebitda = Decimal("-0.5")
    row.fcf_yield = Decimal("0.025")
    row.fcf_conversion = Decimal("0.85")
    row.promoter_holding = Decimal("72.05")
    row.promoter_pledge = Decimal("0")
    row.institutional_ownership = Decimal("18.5")
    row.data_period = "FY2025"
    return row


@pytest.fixture()
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def service(mock_repo: AsyncMock) -> ScreenService:
    return ScreenService(mock_repo)


class TestCreateScreen:
    @pytest.mark.asyncio()
    async def test_creates_screen(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.create_screen.return_value = _make_saved_screen()

        request = CreateScreenRequest(
            name="High ROE",
            groups=[FilterGroup(criteria=(
                FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
            ))],
        )
        result = await service.create_screen(request)

        assert result.name == "Test Screen"
        mock_repo.create_screen.assert_awaited_once()
        call_kwargs = mock_repo.create_screen.call_args.kwargs
        assert call_kwargs["name"] == "High ROE"
        assert "groups" in call_kwargs["criteria"]


class TestListScreens:
    @pytest.mark.asyncio()
    async def test_returns_all_screens(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.list_screens.return_value = [
            _make_saved_screen(name="Screen A"),
            _make_saved_screen(name="Screen B"),
        ]
        result = await service.list_screens()
        assert len(result) == 2
        mock_repo.list_screens.assert_awaited_once()


class TestGetScreen:
    @pytest.mark.asyncio()
    async def test_found(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        saved = _make_saved_screen()
        mock_repo.get_screen.return_value = saved
        result = await service.get_screen(saved.id)
        assert result is not None
        assert result.id == str(saved.id)

    @pytest.mark.asyncio()
    async def test_not_found(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.get_screen.return_value = None
        result = await service.get_screen(uuid.uuid4())
        assert result is None


class TestDeleteScreen:
    @pytest.mark.asyncio()
    async def test_delete_existing(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.delete_screen.return_value = True
        assert await service.delete_screen(uuid.uuid4()) is True

    @pytest.mark.asyncio()
    async def test_delete_missing(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.delete_screen.return_value = False
        assert await service.delete_screen(uuid.uuid4()) is False


class TestExecuteScreen:
    @pytest.mark.asyncio()
    async def test_returns_results(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.get_screen.return_value = _make_saved_screen()
        mock_repo.screen_companies.return_value = (
            [_make_screening_row(symbol="TCS"), _make_screening_row(symbol="INFY")],
            2,
        )

        screen_id = uuid.uuid4()
        result = await service.execute_screen(screen_id, ExecuteScreenRequest())
        assert result is not None
        assert result.total_matches == 2
        assert len(result.companies) == 2
        assert result.companies[0].symbol == "TCS"

    @pytest.mark.asyncio()
    async def test_screen_not_found(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.get_screen.return_value = None
        result = await service.execute_screen(uuid.uuid4(), ExecuteScreenRequest())
        assert result is None

    @pytest.mark.asyncio()
    async def test_passes_sort_params(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.get_screen.return_value = _make_saved_screen()
        mock_repo.screen_companies.return_value = ([], 0)

        params = ExecuteScreenRequest(
            sort_by=ScreenField.MARKET_CAP, sort_desc=False, limit=10, offset=5,
        )
        await service.execute_screen(uuid.uuid4(), params)

        call_kwargs = mock_repo.screen_companies.call_args.kwargs
        assert call_kwargs["sort_by"] == "market_cap"
        assert call_kwargs["sort_desc"] is False
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5


class TestExecuteAdHoc:
    @pytest.mark.asyncio()
    async def test_returns_results(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.screen_companies.return_value = (
            [_make_screening_row()],
            1,
        )
        groups = [FilterGroup(criteria=(
            FilterCriterion(field=ScreenField.ROE, operator=Operator.GT, value=Decimal("0.15")),
        ))]
        result = await service.execute_ad_hoc(groups, ExecuteScreenRequest())
        assert result.screen_id is None
        assert result.total_matches == 1

    @pytest.mark.asyncio()
    async def test_conditions_passed_to_repo(
        self, service: ScreenService, mock_repo: AsyncMock,
    ) -> None:
        mock_repo.screen_companies.return_value = ([], 0)
        groups = [FilterGroup(criteria=(
            FilterCriterion(field=ScreenField.PE_RATIO, operator=Operator.LT, value=Decimal("20")),
            FilterCriterion(field=ScreenField.SECTOR, operator=Operator.EQ, value="IT"),
        ))]
        await service.execute_ad_hoc(groups, ExecuteScreenRequest())

        call_args = mock_repo.screen_companies.call_args
        conditions = call_args[0][0]  # first positional arg
        assert len(conditions) == 1  # one group → one condition


class TestListCompanies:
    @pytest.mark.asyncio()
    async def test_no_filters(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.list_companies.return_value = (
            [_make_screening_row()],
            1,
        )
        result = await service.list_companies()
        assert result.total_matches == 1

    @pytest.mark.asyncio()
    async def test_with_exchange_filter(self, service: ScreenService, mock_repo: AsyncMock) -> None:
        mock_repo.list_companies.return_value = ([], 0)
        await service.list_companies(exchange="NSE")
        call_kwargs = mock_repo.list_companies.call_args.kwargs
        assert call_kwargs["exchange"] == "NSE"
