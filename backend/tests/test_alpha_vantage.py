"""Tests for AlphaVantageProvider with mocked httpx responses."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderRateLimitError,
)
from app.providers.interfaces import FinancialDataProvider, MarketDataProvider
from app.providers.rate_limiter import NullRateLimiter

# ---------------------------------------------------------------------------
# Mock API response fixtures
# ---------------------------------------------------------------------------

_GLOBAL_QUOTE_RESPONSE = {
    "Global Quote": {
        "01. symbol": "RELIANCE.BSE",
        "02. open": "2440.0000",
        "03. high": "2470.5000",
        "04. low": "2435.0000",
        "05. price": "2456.7500",
        "06. volume": "8500000",
        "07. latest trading day": "2024-06-14",
        "08. previous close": "2445.3000",
        "09. change": "11.4500",
        "10. change percent": "0.4683%",
    }
}

_TIME_SERIES_RESPONSE = {
    "Meta Data": {"2. Symbol": "RELIANCE.BSE"},
    "Time Series (Daily)": {
        "2024-01-05": {
            "1. open": "2460.00",
            "2. high": "2475.00",
            "3. low": "2450.00",
            "4. close": "2465.00",
            "5. volume": "5200000",
        },
        "2024-01-04": {
            "1. open": "2450.00",
            "2. high": "2468.00",
            "3. low": "2445.00",
            "4. close": "2460.00",
            "5. volume": "5100000",
        },
        "2024-01-03": {
            "1. open": "2445.00",
            "2. high": "2460.00",
            "3. low": "2440.00",
            "4. close": "2455.00",
            "5. volume": "5000000",
        },
    },
}

_SYMBOL_SEARCH_RESPONSE = {
    "bestMatches": [
        {
            "1. symbol": "RELIANCE.BSE",
            "2. name": "Reliance Industries Limited",
            "3. type": "Equity",
            "4. region": "India/Bombay",
            "5. marketOpen": "09:15",
            "6. marketClose": "15:30",
            "7. timezone": "UTC+5.5",
            "8. currency": "INR",
            "9. matchScore": "1.0000",
        },
        {
            "1. symbol": "REL",
            "2. name": "Reliance Steel",
            "3. type": "Equity",
            "4. region": "United States",
            "5. marketOpen": "09:30",
            "6. marketClose": "16:00",
            "7. timezone": "UTC-5",
            "8. currency": "USD",
            "9. matchScore": "0.5000",
        },
    ]
}

_INCOME_STATEMENT_RESPONSE = {
    "symbol": "RELIANCE.BSE",
    "annualReports": [
        {
            "fiscalDateEnding": "2024-03-31",
            "reportedCurrency": "INR",
            "totalRevenue": "250000000000",
            "costOfRevenue": "150000000000",
            "grossProfit": "100000000000",
            "netIncome": "50000000000",
        },
        {
            "fiscalDateEnding": "2023-03-31",
            "reportedCurrency": "INR",
            "totalRevenue": "220000000000",
            "netIncome": "42000000000",
        },
    ],
    "quarterlyReports": [],
}

_OVERVIEW_RESPONSE = {
    "Symbol": "RELIANCE.BSE",
    "Name": "Reliance Industries Limited",
    "TrailingPE": "28.50",
    "ForwardPE": "24.80",
    "PriceToBookRatio": "4.20",
    "ReturnOnEquityTTM": "0.185",
    "OperatingMarginTTM": "0.22",
    "ProfitMargin": "0.15",
    "DividendYield": "0.004",
    "Beta": "0.85",
    "52WeekHigh": "3050.00",
    "52WeekLow": "2200.00",
}


def _make_response(
    data: dict[str, object], status_code: int = 200
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> AlphaVantageProvider:
    return AlphaVantageProvider(
        api_key="test-key-12345",
        rate_limiter=NullRateLimiter(),
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_is_market_data_provider(self, provider: AlphaVantageProvider) -> None:
        assert isinstance(provider, MarketDataProvider)

    def test_is_financial_data_provider(self, provider: AlphaVantageProvider) -> None:
        assert isinstance(provider, FinancialDataProvider)

    def test_requires_api_key(self) -> None:
        with pytest.raises(ProviderAuthError):
            AlphaVantageProvider(api_key="")


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------


class TestGetQuote:
    @pytest.mark.asyncio
    async def test_returns_decimal_price(self, provider: AlphaVantageProvider) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_GLOBAL_QUOTE_RESPONSE
        ):
            quote = await provider.get_quote("RELIANCE", "NSE")

        assert quote.symbol == "RELIANCE"
        assert isinstance(quote.price, Decimal)
        assert quote.price == Decimal("2456.7500")
        assert quote.provenance is not None
        assert quote.provenance.source == "Alpha Vantage"

    @pytest.mark.asyncio
    async def test_raises_not_found_for_empty_response(
        self, provider: AlphaVantageProvider
    ) -> None:
        with (
            patch.object(
                provider, "_request", new_callable=AsyncMock, return_value={"Global Quote": {}}
            ),
            pytest.raises(ProviderNotFoundError),
        ):
            await provider.get_quote("UNKNOWN", "NSE")


# ---------------------------------------------------------------------------
# get_historical_prices
# ---------------------------------------------------------------------------


class TestGetHistoricalPrices:
    @pytest.mark.asyncio
    async def test_returns_price_bars_with_decimal(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_TIME_SERIES_RESPONSE
        ):
            bars = await provider.get_historical_prices(
                "RELIANCE", "NSE", date(2024, 1, 3), date(2024, 1, 5)
            )

        assert len(bars) == 3
        for bar in bars:
            assert isinstance(bar.open, Decimal)
            assert isinstance(bar.close, Decimal)
            assert isinstance(bar.volume, int)
            assert bar.provenance is not None

    @pytest.mark.asyncio
    async def test_filters_by_date_range(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_TIME_SERIES_RESPONSE
        ):
            bars = await provider.get_historical_prices(
                "RELIANCE", "NSE", date(2024, 1, 4), date(2024, 1, 5)
            )

        assert len(bars) == 2
        dates = {b.date for b in bars}
        assert date(2024, 1, 3) not in dates


# ---------------------------------------------------------------------------
# search_companies
# ---------------------------------------------------------------------------


class TestSearchCompanies:
    @pytest.mark.asyncio
    async def test_filters_to_indian_region(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_SYMBOL_SEARCH_RESPONSE
        ):
            results = await provider.search_companies("Reliance")

        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"
        assert results[0].exchange == "BSE"


# ---------------------------------------------------------------------------
# get_financial_statements
# ---------------------------------------------------------------------------


class TestGetFinancialStatements:
    @pytest.mark.asyncio
    async def test_returns_annual_income_statement(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_INCOME_STATEMENT_RESPONSE
        ):
            stmts = await provider.get_financial_statements(
                "RELIANCE", "NSE", "INCOME_STATEMENT", "ANNUAL"
            )

        assert len(stmts) == 2
        stmt = stmts[0]
        assert stmt.statement_type == "INCOME_STATEMENT"
        assert stmt.period == "2024-03-31"
        assert all(isinstance(v, Decimal) for v in stmt.line_items.values())
        assert Decimal("250000000000") in stmt.line_items.values()
        assert stmt.provenance is not None


# ---------------------------------------------------------------------------
# get_financial_ratios
# ---------------------------------------------------------------------------


class TestGetFinancialRatios:
    @pytest.mark.asyncio
    async def test_returns_decimal_ratios(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_OVERVIEW_RESPONSE
        ):
            ratios = await provider.get_financial_ratios("RELIANCE", "NSE")

        assert "pe_ratio" in ratios
        assert isinstance(ratios["pe_ratio"], Decimal)
        assert ratios["pe_ratio"] == Decimal("28.50")
        assert "roe" in ratios


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


class TestHttpErrorHandling:
    @pytest.mark.asyncio
    async def test_rate_limit_note_raises(
        self, provider: AlphaVantageProvider
    ) -> None:
        with (
            patch.object(
                provider,
                "_request",
                new_callable=AsyncMock,
                side_effect=ProviderRateLimitError(
                    provider="alpha_vantage",
                    message="rate limited",
                    retry_after=60.0,
                ),
            ),
            pytest.raises(ProviderRateLimitError),
        ):
            await provider.get_quote("RELIANCE", "NSE")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_on_valid_response(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, return_value=_GLOBAL_QUOTE_RESPONSE
        ):
            health = await provider.check_health()
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(
        self, provider: AlphaVantageProvider
    ) -> None:
        with patch.object(
            provider, "_request", new_callable=AsyncMock, side_effect=RuntimeError("down")
        ):
            health = await provider.check_health()
        assert health.is_healthy is False
