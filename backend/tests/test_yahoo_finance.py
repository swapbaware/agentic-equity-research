"""Tests for YahooFinanceProvider with mocked yfinance calls."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.providers.errors import ProviderNotFoundError
from app.providers.interfaces import (
    CorporateActionsProvider,
    FinancialDataProvider,
    MarketDataProvider,
)
from app.providers.rate_limiter import NullRateLimiter
from app.providers.yahoo_finance import YahooFinanceProvider

# ---------------------------------------------------------------------------
# Fixtures: realistic yfinance mock data for Indian stocks
# ---------------------------------------------------------------------------

_RELIANCE_INFO = {
    "regularMarketPrice": 2456.75,
    "regularMarketOpen": 2440.00,
    "regularMarketDayHigh": 2470.50,
    "regularMarketDayLow": 2435.00,
    "regularMarketPreviousClose": 2445.30,
    "regularMarketVolume": 8_500_000,
    "marketCap": 16_623_500_000_000,
    "currency": "INR",
    "trailingPE": 28.5,
    "priceToBook": 4.2,
    "returnOnEquity": 0.185,
    "currentRatio": 1.45,
    "operatingMargins": 0.22,
    "profitMargins": 0.15,
}

_HDFCBANK_INFO = {
    "regularMarketPrice": 1650.25,
    "regularMarketOpen": 1645.00,
    "regularMarketDayHigh": 1660.00,
    "regularMarketDayLow": 1640.50,
    "regularMarketPreviousClose": 1648.00,
    "regularMarketVolume": 12_000_000,
    "marketCap": 12_500_000_000_000,
    "currency": "INR",
}


def _make_history_df(base_price: float = 2456.75, days: int = 5) -> pd.DataFrame:
    dates = pd.date_range(start="2024-01-01", periods=days, freq="B")
    data = {
        "Open": [base_price + i * 2 for i in range(days)],
        "High": [base_price + i * 2 + 15 for i in range(days)],
        "Low": [base_price + i * 2 - 10 for i in range(days)],
        "Close": [base_price + i * 2 + 5 for i in range(days)],
        "Volume": [5_000_000 + i * 100_000 for i in range(days)],
    }
    return pd.DataFrame(data, index=dates)


def _make_financials_df() -> pd.DataFrame:
    columns = pd.DatetimeIndex([datetime(2024, 3, 31), datetime(2023, 3, 31)])
    data = {
        columns[0]: [250_000_000_000, 150_000_000_000, 50_000_000_000],
        columns[1]: [220_000_000_000, 135_000_000_000, 42_000_000_000],
    }
    return pd.DataFrame(
        data,
        index=["Total Revenue", "Cost Of Revenue", "Net Income"],
    )


def _make_dividends() -> pd.Series:
    dates = pd.DatetimeIndex([datetime(2024, 7, 18), datetime(2023, 7, 20)])
    return pd.Series([10.0, 8.0], index=dates)


def _make_splits() -> pd.Series:
    dates = pd.DatetimeIndex([datetime(2020, 9, 28)])
    return pd.Series([2.0], index=dates)


def _make_search_results() -> MagicMock:
    mock = MagicMock()
    mock.quotes = [
        {
            "symbol": "RELIANCE.NS",
            "exchange": "NSI",
            "shortname": "Reliance Industries",
        },
        {
            "symbol": "RELIANCE.BO",
            "exchange": "BOM",
            "shortname": "Reliance Industries",
        },
        {
            "symbol": "REL",
            "exchange": "NYSE",
            "shortname": "Reliance Steel",
        },
    ]
    return mock


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> YahooFinanceProvider:
    return YahooFinanceProvider(rate_limiter=NullRateLimiter())


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_is_market_data_provider(self, provider: YahooFinanceProvider) -> None:
        assert isinstance(provider, MarketDataProvider)

    def test_is_financial_data_provider(self, provider: YahooFinanceProvider) -> None:
        assert isinstance(provider, FinancialDataProvider)

    def test_is_corporate_actions_provider(self, provider: YahooFinanceProvider) -> None:
        assert isinstance(provider, CorporateActionsProvider)


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------


class TestGetQuote:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_returns_quote_with_decimal_price(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = _RELIANCE_INFO
        mock_ticker_cls.return_value = mock_ticker

        quote = await provider.get_quote("RELIANCE", "NSE")

        assert quote.symbol == "RELIANCE"
        assert quote.exchange == "NSE"
        assert isinstance(quote.price, Decimal)
        assert quote.price == Decimal("2456.75")
        assert quote.currency == "INR"
        mock_ticker_cls.assert_called_with("RELIANCE.NS")

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_quote_has_provenance(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = _RELIANCE_INFO
        mock_ticker_cls.return_value = mock_ticker

        quote = await provider.get_quote("RELIANCE", "NSE")

        assert quote.provenance is not None
        assert quote.provenance.source == "Yahoo Finance"
        assert quote.provenance.provider == "yahoo_finance"

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_bse_exchange_uses_bo_suffix(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = _HDFCBANK_INFO
        mock_ticker_cls.return_value = mock_ticker

        await provider.get_quote("HDFCBANK", "BSE")
        mock_ticker_cls.assert_called_with("HDFCBANK.BO")

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_raises_not_found_for_empty_info(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(ProviderNotFoundError):
            await provider.get_quote("UNKNOWN", "NSE")

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_all_financial_values_are_decimal(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = _RELIANCE_INFO
        mock_ticker_cls.return_value = mock_ticker

        quote = await provider.get_quote("RELIANCE", "NSE")
        for field_name in ("price", "open", "high", "low", "close", "market_cap"):
            val = getattr(quote, field_name)
            if val is not None:
                assert isinstance(val, Decimal), f"{field_name} should be Decimal"


# ---------------------------------------------------------------------------
# get_historical_prices
# ---------------------------------------------------------------------------


class TestGetHistoricalPrices:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_returns_price_bars(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history_df()
        mock_ticker_cls.return_value = mock_ticker

        bars = await provider.get_historical_prices(
            "RELIANCE", "NSE", date(2024, 1, 1), date(2024, 1, 10)
        )

        assert len(bars) == 5
        for bar in bars:
            assert isinstance(bar.open, Decimal)
            assert isinstance(bar.close, Decimal)
            assert isinstance(bar.volume, int)
            assert bar.provenance is not None

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_raises_not_found_for_empty_data(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(ProviderNotFoundError):
            await provider.get_historical_prices(
                "UNKNOWN", "NSE", date(2024, 1, 1), date(2024, 1, 10)
            )


# ---------------------------------------------------------------------------
# search_companies
# ---------------------------------------------------------------------------


class TestSearchCompanies:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Search")
    async def test_filters_indian_exchanges(
        self, mock_search_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_search_cls.return_value = _make_search_results()

        results = await provider.search_companies("Reliance")

        assert len(results) == 2
        exchanges = {r.exchange for r in results}
        assert exchanges == {"NSE", "BSE"}

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Search")
    async def test_strips_suffix_from_symbol(
        self, mock_search_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_search_cls.return_value = _make_search_results()

        results = await provider.search_companies("Reliance")

        for r in results:
            assert not r.symbol.endswith(".NS")
            assert not r.symbol.endswith(".BO")


# ---------------------------------------------------------------------------
# get_financial_statements
# ---------------------------------------------------------------------------


class TestGetFinancialStatements:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_returns_income_statement(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.financials = _make_financials_df()
        mock_ticker_cls.return_value = mock_ticker

        stmts = await provider.get_financial_statements(
            "RELIANCE", "NSE", "INCOME_STATEMENT", "ANNUAL"
        )

        assert len(stmts) == 2
        stmt = stmts[0]
        assert stmt.statement_type == "INCOME_STATEMENT"
        assert stmt.period_type == "ANNUAL"
        assert all(isinstance(v, Decimal) for v in stmt.line_items.values())
        assert stmt.provenance is not None

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_raises_for_empty_data(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.financials = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(ProviderNotFoundError):
            await provider.get_financial_statements(
                "UNKNOWN", "NSE", "INCOME_STATEMENT", "ANNUAL"
            )


# ---------------------------------------------------------------------------
# get_financial_ratios
# ---------------------------------------------------------------------------


class TestGetFinancialRatios:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_returns_decimal_ratios(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = _RELIANCE_INFO
        mock_ticker_cls.return_value = mock_ticker

        ratios = await provider.get_financial_ratios("RELIANCE", "NSE")

        assert "pe_ratio" in ratios
        assert isinstance(ratios["pe_ratio"], Decimal)
        assert "roe" in ratios
        assert isinstance(ratios["roe"], Decimal)


# ---------------------------------------------------------------------------
# get_corporate_actions
# ---------------------------------------------------------------------------


class TestGetCorporateActions:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_returns_dividends_and_splits(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.dividends = _make_dividends()
        mock_ticker.splits = _make_splits()
        mock_ticker_cls.return_value = mock_ticker

        actions = await provider.get_corporate_actions("RELIANCE", "NSE")

        types = {a.action_type for a in actions}
        assert "DIVIDEND" in types
        assert "STOCK_SPLIT" in types
        for a in actions:
            assert isinstance(a.value, Decimal)
            assert a.provenance is not None

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_date_filter_applies(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.dividends = _make_dividends()
        mock_ticker.splits = _make_splits()
        mock_ticker_cls.return_value = mock_ticker

        actions = await provider.get_corporate_actions(
            "RELIANCE", "NSE", start=date(2024, 1, 1), end=date(2024, 12, 31)
        )

        for a in actions:
            assert a.ex_date is not None
            assert a.ex_date >= date(2024, 1, 1)
            assert a.ex_date <= date(2024, 12, 31)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_healthy_when_data_available(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 2456.75}
        mock_ticker_cls.return_value = mock_ticker

        health = await provider.check_health()
        assert health.is_healthy is True

    @pytest.mark.asyncio
    @patch("app.providers.yahoo_finance.yf.Ticker")
    async def test_unhealthy_on_exception(
        self, mock_ticker_cls: MagicMock, provider: YahooFinanceProvider
    ) -> None:
        mock_ticker_cls.side_effect = RuntimeError("network down")

        health = await provider.check_health()
        assert health.is_healthy is False
