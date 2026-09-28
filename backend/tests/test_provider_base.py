"""Tests for ProviderBase retry/timeout logic and ProviderFactory."""
from __future__ import annotations

import asyncio

import pytest

from app.providers.base import ProviderBase, ProviderConfig
from app.providers.config import ProviderSettings
from app.providers.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.factory import ProviderFactory
from app.providers.interfaces import (
    CorporateActionsProvider,
    CorporateFilingsProvider,
    EmbeddingProvider,
    FinancialDataProvider,
    LLMProvider,
    MacroDataProvider,
    MarketDataProvider,
    NewsProvider,
    SearchProvider,
    ShareholdingProvider,
    TranscriptProvider,
)
from app.providers.rate_limiter import NullRateLimiter


class TestProviderBaseRetry:
    def _make_base(self, *, max_retries: int = 3, timeout: float = 5.0) -> ProviderBase:
        config = ProviderConfig(
            provider_name="test",
            default_timeout=timeout,
            max_retries=max_retries,
            base_retry_delay=0.01,
            max_retry_delay=0.05,
        )
        return ProviderBase(config, rate_limiter=NullRateLimiter())

    @pytest.mark.asyncio
    async def test_successful_call(self) -> None:
        base = self._make_base()

        async def return_42() -> int:
            return 42

        result = await base._execute("op", return_42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_retries_on_unavailable(self) -> None:
        base = self._make_base(max_retries=3)
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderUnavailableError(provider="test", message="down")
            return "ok"

        result = await base._execute("op", flaky)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_auth_error(self) -> None:
        base = self._make_base(max_retries=3)
        call_count = 0

        async def auth_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise ProviderAuthError(provider="test", message="bad key")

        with pytest.raises(ProviderAuthError):
            await base._execute("op", auth_fail)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_not_found(self) -> None:
        base = self._make_base(max_retries=3)
        call_count = 0

        async def not_found() -> str:
            nonlocal call_count
            call_count += 1
            raise ProviderNotFoundError(provider="test", message="gone")

        with pytest.raises(ProviderNotFoundError):
            await base._execute("op", not_found)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self) -> None:
        base = self._make_base(max_retries=2, timeout=0.05)
        call_count = 0

        async def slow() -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(ProviderTimeoutError):
            await base._execute("op", slow)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_health_check_default(self) -> None:
        base = self._make_base()
        health = await base.check_health()
        assert health.is_healthy is True
        assert health.provider_name == "test"


# ---------------------------------------------------------------------------
# ProviderFactory
# ---------------------------------------------------------------------------


class TestProviderFactory:
    @pytest.fixture
    def factory(self) -> ProviderFactory:
        settings = ProviderSettings()
        return ProviderFactory(settings)

    def test_creates_market_data_provider(self, factory: ProviderFactory) -> None:
        provider = factory.market_data()
        assert isinstance(provider, MarketDataProvider)

    def test_creates_financial_data_provider(self, factory: ProviderFactory) -> None:
        provider = factory.financial_data()
        assert isinstance(provider, FinancialDataProvider)

    def test_creates_corporate_filings_provider(self, factory: ProviderFactory) -> None:
        provider = factory.corporate_filings()
        assert isinstance(provider, CorporateFilingsProvider)

    def test_creates_shareholding_provider(self, factory: ProviderFactory) -> None:
        provider = factory.shareholding()
        assert isinstance(provider, ShareholdingProvider)

    def test_creates_corporate_actions_provider(self, factory: ProviderFactory) -> None:
        provider = factory.corporate_actions()
        assert isinstance(provider, CorporateActionsProvider)

    def test_creates_news_provider(self, factory: ProviderFactory) -> None:
        provider = factory.news()
        assert isinstance(provider, NewsProvider)

    def test_creates_search_provider(self, factory: ProviderFactory) -> None:
        provider = factory.search()
        assert isinstance(provider, SearchProvider)

    def test_creates_macro_data_provider(self, factory: ProviderFactory) -> None:
        provider = factory.macro_data()
        assert isinstance(provider, MacroDataProvider)

    def test_creates_transcript_provider(self, factory: ProviderFactory) -> None:
        provider = factory.transcript()
        assert isinstance(provider, TranscriptProvider)

    def test_creates_llm_provider(self, factory: ProviderFactory) -> None:
        provider = factory.llm()
        assert isinstance(provider, LLMProvider)

    def test_creates_embedding_provider(self, factory: ProviderFactory) -> None:
        provider = factory.embedding()
        assert isinstance(provider, EmbeddingProvider)

    def test_unknown_provider_raises_value_error(self) -> None:
        settings = ProviderSettings()
        settings.market_data = "nonexistent_vendor"
        factory = ProviderFactory(settings)
        with pytest.raises(ValueError, match="Unknown provider"):
            factory.market_data()
