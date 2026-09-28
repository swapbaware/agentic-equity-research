"""Provider substitution test — verifies that any provider can be swapped
through configuration alone, without changing domain models, agents, or UI.

Creates a MockProductionProvider that simulates a paid Indian financial data
vendor, then demonstrates config-only substitution from:
  - YahooFinanceProvider → MockProductionProvider
  - AlphaVantageProvider → MockProductionProvider

This is a regression test for the core architectural requirement:
"Build provider abstraction so production providers can be substituted
without changing the domain, agents, research workflows or UI."
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.providers.config import ProviderSettings
from app.providers.errors import ProviderNotFoundError
from app.providers.factory import ProviderFactory
from app.providers.interfaces import (
    CorporateActionsProvider,
    CorporateFilingsProvider,
    FinancialDataProvider,
    MarketDataProvider,
)
from app.providers.provenance import (
    Confidence,
    DataProvenance,
    DataQuality,
    SourceType,
)
from app.providers.rate_limiter import NullRateLimiter
from app.providers.types import (
    CompanySearchResult,
    CorporateActionRecord,
    Filing,
    FilingDocument,
    FinancialStatement,
    PriceBar,
    ProviderHealth,
    Quote,
)

# ---------------------------------------------------------------------------
# MockProductionProvider — simulates a paid Indian financial data vendor
# ---------------------------------------------------------------------------

_PROD_COMPANIES = {
    "RELIANCE": {
        "name": "Reliance Industries Ltd",
        "price": Decimal("2500.00"),
        "market_cap": Decimal("16900000000000"),
    },
    "TCS": {
        "name": "Tata Consultancy Services Ltd",
        "price": Decimal("3900.00"),
        "market_cap": Decimal("14200000000000"),
    },
    "INFY": {
        "name": "Infosys Ltd",
        "price": Decimal("1560.00"),
        "market_cap": Decimal("6500000000000"),
    },
    "HDFCBANK": {
        "name": "HDFC Bank Ltd",
        "price": Decimal("1680.00"),
        "market_cap": Decimal("12800000000000"),
    },
    "ICICIBANK": {
        "name": "ICICI Bank Ltd",
        "price": Decimal("1120.00"),
        "market_cap": Decimal("7900000000000"),
    },
    "BHARTIARTL": {
        "name": "Bharti Airtel Ltd",
        "price": Decimal("1450.00"),
        "market_cap": Decimal("8600000000000"),
    },
}


def _prod_provenance(*, data_period: str | None = None) -> DataProvenance:
    return DataProvenance(
        source="MockProductionVendor",
        source_type=SourceType.MARKET_DATA,
        retrieved_at=datetime.now(UTC),
        provider="mock_production",
        data_quality=DataQuality.AUTHORITATIVE,
        confidence=Confidence.HIGH,
        data_period=data_period,
    )


class MockProductionProvider:
    """Simulates a paid production data vendor implementing all 4 key interfaces.

    This class exists solely to prove that the provider abstraction allows
    config-only substitution. It is NOT a real provider.
    """

    def _check(self, symbol: str) -> dict[str, Decimal | str]:
        data = _PROD_COMPANIES.get(symbol)
        if data is None:
            raise ProviderNotFoundError(
                provider="mock_production",
                message=f"Symbol {symbol} not found",
            )
        return data

    # --- MarketDataProvider ---

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        data = self._check(symbol)
        return Quote(
            symbol=symbol,
            exchange=exchange,
            price=Decimal(str(data["price"])),
            market_cap=Decimal(str(data["market_cap"])),
            timestamp=datetime.now(UTC),
            currency="INR",
            provenance=_prod_provenance(),
        )

    async def get_historical_prices(
        self, symbol: str, exchange: str, start: date, end: date
    ) -> list[PriceBar]:
        self._check(symbol)
        base = Decimal(str(_PROD_COMPANIES[symbol]["price"]))
        bars: list[PriceBar] = []
        days = (end - start).days
        for i in range(min(days, 5)):
            d = date.fromordinal(start.toordinal() + i)
            offset = Decimal(str(i))
            bars.append(
                PriceBar(
                    date=d,
                    open=base + offset,
                    high=base + offset + Decimal("10"),
                    low=base + offset - Decimal("5"),
                    close=base + offset + Decimal("3"),
                    volume=10_000_000,
                    provenance=_prod_provenance(),
                )
            )
        return bars

    async def search_companies(self, query: str) -> list[CompanySearchResult]:
        q = query.upper()
        return [
            CompanySearchResult(
                symbol=sym,
                exchange="NSE",
                name=str(data["name"]),
            )
            for sym, data in _PROD_COMPANIES.items()
            if q in sym or q in str(data["name"]).upper()
        ]

    # --- FinancialDataProvider ---

    async def get_financial_statements(
        self, symbol: str, exchange: str, statement_type: str, period_type: str
    ) -> list[FinancialStatement]:
        self._check(symbol)
        return [
            FinancialStatement(
                symbol=symbol,
                exchange=exchange,
                statement_type=statement_type,
                period_type=period_type,
                period="FY2024",
                filing_date=date(2024, 5, 15),
                line_items={
                    "revenue": Decimal("300000000000"),
                    "net_income": Decimal("60000000000"),
                },
                provenance=_prod_provenance(data_period="FY2024"),
            )
        ]

    async def get_financial_ratios(self, symbol: str, exchange: str) -> dict[str, object]:
        self._check(symbol)
        return {
            "pe_ratio": Decimal("25.0"),
            "pb_ratio": Decimal("3.8"),
            "roe": Decimal("0.20"),
        }

    # --- CorporateFilingsProvider ---

    async def get_filings(
        self,
        symbol: str,
        exchange: str,
        *,
        filing_type: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Filing]:
        self._check(symbol)
        return [
            Filing(
                filing_id=f"PROD-{symbol}-AR-2024",
                symbol=symbol,
                exchange=exchange,
                filing_type="ANNUAL_REPORT",
                title=f"{symbol} Annual Report FY2024",
                filing_date=date(2024, 5, 30),
                provenance=_prod_provenance(),
            )
        ]

    async def get_filing_document(self, filing_id: str) -> FilingDocument:
        return FilingDocument(
            filing_id=filing_id,
            content=f"Production filing content for {filing_id}",
            content_type="text/plain",
        )

    # --- CorporateActionsProvider ---

    async def get_corporate_actions(
        self,
        symbol: str,
        exchange: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateActionRecord]:
        self._check(symbol)
        return [
            CorporateActionRecord(
                symbol=symbol,
                exchange=exchange,
                action_type="DIVIDEND",
                ex_date=date(2024, 7, 18),
                details="Final Dividend INR 12 per share",
                value=Decimal("12.00"),
                provenance=_prod_provenance(),
            )
        ]

    # --- Health ---

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name="mock_production",
            is_healthy=True,
            message="production vendor healthy",
            checked_at=datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# Protocol conformance — verify MockProductionProvider satisfies all interfaces
# ---------------------------------------------------------------------------


class TestMockProductionProtocolConformance:
    def test_satisfies_market_data_provider(self) -> None:
        assert isinstance(MockProductionProvider(), MarketDataProvider)

    def test_satisfies_financial_data_provider(self) -> None:
        assert isinstance(MockProductionProvider(), FinancialDataProvider)

    def test_satisfies_corporate_filings_provider(self) -> None:
        assert isinstance(MockProductionProvider(), CorporateFilingsProvider)

    def test_satisfies_corporate_actions_provider(self) -> None:
        assert isinstance(MockProductionProvider(), CorporateActionsProvider)


# ---------------------------------------------------------------------------
# Configuration-only substitution tests
# ---------------------------------------------------------------------------


class TestConfigOnlySubstitution:
    """Prove that switching providers requires ONLY a config change."""

    @pytest.fixture
    def factory_with_production(self) -> ProviderFactory:
        settings = ProviderSettings()
        settings.market_data = "production"
        settings.financial_data = "production"
        settings.corporate_filings = "production"
        settings.corporate_actions = "production"

        factory = ProviderFactory(settings, rate_limiter=NullRateLimiter())

        prod_factory = MockProductionProvider
        factory.register("market_data", "production", prod_factory)
        factory.register("financial_data", "production", prod_factory)
        factory.register("corporate_filings", "production", prod_factory)
        factory.register("corporate_actions", "production", prod_factory)

        return factory

    def test_market_data_substitution(
        self, factory_with_production: ProviderFactory
    ) -> None:
        """Yahoo → Production: config only, no domain changes."""
        provider = factory_with_production.market_data()
        assert isinstance(provider, MarketDataProvider)
        assert type(provider).__name__ == "MockProductionProvider"

    def test_financial_data_substitution(
        self, factory_with_production: ProviderFactory
    ) -> None:
        """AlphaVantage → Production: config only, no domain changes."""
        provider = factory_with_production.financial_data()
        assert isinstance(provider, FinancialDataProvider)
        assert type(provider).__name__ == "MockProductionProvider"

    def test_corporate_filings_substitution(
        self, factory_with_production: ProviderFactory
    ) -> None:
        """BSE → Production: config only, no domain changes."""
        provider = factory_with_production.corporate_filings()
        assert isinstance(provider, CorporateFilingsProvider)
        assert type(provider).__name__ == "MockProductionProvider"

    def test_corporate_actions_substitution(
        self, factory_with_production: ProviderFactory
    ) -> None:
        """Yahoo actions → Production: config only, no domain changes."""
        provider = factory_with_production.corporate_actions()
        assert isinstance(provider, CorporateActionsProvider)
        assert type(provider).__name__ == "MockProductionProvider"


# ---------------------------------------------------------------------------
# Data contract tests — production provider returns the same types as free
# ---------------------------------------------------------------------------


class TestProductionProviderDataContracts:
    """Verify production provider returns the same types the application expects."""

    @pytest.fixture
    def provider(self) -> MockProductionProvider:
        return MockProductionProvider()

    @pytest.mark.asyncio
    async def test_quote_returns_decimal_price(
        self, provider: MockProductionProvider
    ) -> None:
        quote = await provider.get_quote("RELIANCE", "NSE")
        assert isinstance(quote.price, Decimal)
        assert isinstance(quote.market_cap, Decimal)
        assert quote.currency == "INR"

    @pytest.mark.asyncio
    async def test_quote_has_provenance(
        self, provider: MockProductionProvider
    ) -> None:
        quote = await provider.get_quote("RELIANCE", "NSE")
        assert quote.provenance is not None
        assert quote.provenance.source == "MockProductionVendor"
        assert quote.provenance.data_quality.value == "AUTHORITATIVE"

    @pytest.mark.asyncio
    async def test_historical_prices_returns_price_bars(
        self, provider: MockProductionProvider
    ) -> None:
        bars = await provider.get_historical_prices(
            "TCS", "NSE", date(2024, 1, 1), date(2024, 1, 10)
        )
        assert len(bars) == 5
        for bar in bars:
            assert isinstance(bar.open, Decimal)
            assert isinstance(bar.close, Decimal)

    @pytest.mark.asyncio
    async def test_financial_statements_returns_decimal_line_items(
        self, provider: MockProductionProvider
    ) -> None:
        stmts = await provider.get_financial_statements(
            "RELIANCE", "NSE", "INCOME_STATEMENT", "ANNUAL"
        )
        assert len(stmts) == 1
        assert all(isinstance(v, Decimal) for v in stmts[0].line_items.values())
        assert stmts[0].provenance is not None

    @pytest.mark.asyncio
    async def test_filings_returns_filing_objects(
        self, provider: MockProductionProvider
    ) -> None:
        filings = await provider.get_filings("RELIANCE", "BSE")
        assert len(filings) == 1
        assert filings[0].filing_id.startswith("PROD-")

    @pytest.mark.asyncio
    async def test_corporate_actions_returns_decimal_values(
        self, provider: MockProductionProvider
    ) -> None:
        actions = await provider.get_corporate_actions("RELIANCE", "NSE")
        assert len(actions) == 1
        assert isinstance(actions[0].value, Decimal)

    @pytest.mark.asyncio
    async def test_not_found_for_unknown_symbol(
        self, provider: MockProductionProvider
    ) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_quote("UNKNOWN", "NSE")

    @pytest.mark.asyncio
    async def test_search_returns_dev_dataset_companies(
        self, provider: MockProductionProvider
    ) -> None:
        results = await provider.search_companies("HDFC")
        assert len(results) >= 1
        assert results[0].symbol == "HDFCBANK"

    @pytest.mark.asyncio
    async def test_health_check(
        self, provider: MockProductionProvider
    ) -> None:
        health = await provider.check_health()
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# Simultaneous dual-provider test (two sources for same data)
# ---------------------------------------------------------------------------


class TestDualProviderCoexistence:
    """Verify two providers can supply the same interface simultaneously."""

    def test_factory_can_host_mock_and_production(self) -> None:
        settings = ProviderSettings()
        factory = ProviderFactory(settings, rate_limiter=NullRateLimiter())
        factory.register("market_data", "production", MockProductionProvider)

        settings.market_data = "mock"
        mock_provider = factory.market_data()

        settings.market_data = "production"
        prod_provider = factory.market_data()

        assert type(mock_provider).__name__ == "MockMarketDataProvider"
        assert type(prod_provider).__name__ == "MockProductionProvider"
        assert isinstance(mock_provider, MarketDataProvider)
        assert isinstance(prod_provider, MarketDataProvider)


# ---------------------------------------------------------------------------
# Lazy import regression test
# ---------------------------------------------------------------------------


class TestLazyImports:
    """Verify the factory does NOT eagerly import vendor SDKs."""

    def test_factory_import_does_not_load_yfinance(self) -> None:
        import sys

        if "yfinance" in sys.modules:
            pytest.skip("yfinance already imported by earlier test")

        pre = set(sys.modules.keys())
        ProviderFactory(ProviderSettings(), rate_limiter=NullRateLimiter())
        post = set(sys.modules.keys())

        vendor = [m for m in (post - pre) if "yfinance" in m]
        assert vendor == [], f"yfinance loaded eagerly: {vendor}"
