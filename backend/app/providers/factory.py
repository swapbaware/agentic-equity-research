"""Provider factory — configuration-driven provider creation.

The factory maps provider names (from ProviderSettings) to concrete classes.
Adding a new provider means registering it here and implementing the interface.
Business logic never touches this module; it receives providers via DI.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import ProviderConfig
from app.providers.bse import BSEProvider
from app.providers.config import ProviderSettings
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
from app.providers.mock import (
    MockCorporateActionsProvider,
    MockCorporateFilingsProvider,
    MockEmbeddingProvider,
    MockFinancialDataProvider,
    MockLLMProvider,
    MockMacroDataProvider,
    MockMarketDataProvider,
    MockNewsProvider,
    MockSearchProvider,
    MockShareholdingProvider,
    MockTranscriptProvider,
)
from app.providers.nse import NSEProvider
from app.providers.rate_limiter import InMemoryRateLimiter, RateLimiter
from app.providers.yahoo_finance import YahooFinanceProvider

_P = TypeVar("_P")

# Simple providers that need no constructor args
_SIMPLE_REGISTRY: dict[str, dict[str, type[object]]] = {
    "market_data": {"mock": MockMarketDataProvider},
    "financial_data": {"mock": MockFinancialDataProvider},
    "corporate_filings": {"mock": MockCorporateFilingsProvider},
    "shareholding": {"mock": MockShareholdingProvider},
    "corporate_actions": {"mock": MockCorporateActionsProvider},
    "news": {"mock": MockNewsProvider},
    "search": {"mock": MockSearchProvider},
    "macro_data": {"mock": MockMacroDataProvider},
    "transcript": {"mock": MockTranscriptProvider},
    "llm": {"mock": MockLLMProvider},
    "embedding": {"mock": MockEmbeddingProvider},
}


def _make_config(name: str, settings: ProviderSettings) -> ProviderConfig:
    return ProviderConfig(
        provider_name=name,
        default_timeout=settings.default_timeout,
        max_retries=settings.default_max_retries,
        rate_limit_requests=settings.rate_limit_requests,
        rate_limit_period=settings.rate_limit_period,
    )


class ProviderFactory:
    """Creates provider instances based on configuration.

    Usage:
        settings = ProviderSettings()
        factory = ProviderFactory(settings)
        market = factory.market_data()  # returns the configured MarketDataProvider
    """

    def __init__(
        self,
        settings: ProviderSettings | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings or ProviderSettings()
        self._rate_limiter = rate_limiter or InMemoryRateLimiter(
            rate=self._settings.rate_limit_requests,
            period=self._settings.rate_limit_period,
        )
        self._custom_factories: dict[str, dict[str, Callable[[], object]]] = (
            self._build_custom_factories()
        )

    def _build_custom_factories(self) -> dict[str, dict[str, Callable[[], object]]]:
        """Register providers that need constructor arguments."""
        s = self._settings
        rl = self._rate_limiter

        def _yahoo() -> YahooFinanceProvider:
            return YahooFinanceProvider(
                config=_make_config("yahoo_finance", s), rate_limiter=rl,
            )

        def _alpha_vantage() -> AlphaVantageProvider:
            return AlphaVantageProvider(
                api_key=s.alpha_vantage_api_key,
                config=_make_config("alpha_vantage", s),
                rate_limiter=rl,
            )

        def _bse() -> BSEProvider:
            return BSEProvider(
                config=_make_config("bse", s), rate_limiter=rl,
            )

        def _nse() -> NSEProvider:
            return NSEProvider(
                config=_make_config("nse", s), rate_limiter=rl,
            )

        return {
            "market_data": {"yahoo": _yahoo, "alpha_vantage": _alpha_vantage},
            "financial_data": {"yahoo": _yahoo, "alpha_vantage": _alpha_vantage},
            "corporate_filings": {"bse": _bse, "nse": _nse},
            "corporate_actions": {"yahoo": _yahoo},
        }

    def _resolve(self, interface_name: str, provider_key: str) -> object:
        custom = self._custom_factories.get(interface_name, {})
        factory_fn = custom.get(provider_key)
        if factory_fn is not None:
            return factory_fn()

        providers = _SIMPLE_REGISTRY.get(interface_name)
        if providers is None:
            msg = f"Unknown interface: {interface_name}"
            raise ValueError(msg)
        cls = providers.get(provider_key)
        if cls is None:
            all_keys = list(providers) + list(custom)
            msg = f"Unknown provider '{provider_key}' for {interface_name}. Available: {all_keys}"
            raise ValueError(msg)
        return cls()

    def market_data(self) -> MarketDataProvider:
        provider = self._resolve("market_data", self._settings.market_data)
        assert isinstance(provider, MarketDataProvider)  # noqa: S101
        return provider

    def financial_data(self) -> FinancialDataProvider:
        provider = self._resolve("financial_data", self._settings.financial_data)
        assert isinstance(provider, FinancialDataProvider)  # noqa: S101
        return provider

    def corporate_filings(self) -> CorporateFilingsProvider:
        provider = self._resolve("corporate_filings", self._settings.corporate_filings)
        assert isinstance(provider, CorporateFilingsProvider)  # noqa: S101
        return provider

    def shareholding(self) -> ShareholdingProvider:
        provider = self._resolve("shareholding", self._settings.shareholding)
        assert isinstance(provider, ShareholdingProvider)  # noqa: S101
        return provider

    def corporate_actions(self) -> CorporateActionsProvider:
        provider = self._resolve("corporate_actions", self._settings.corporate_actions)
        assert isinstance(provider, CorporateActionsProvider)  # noqa: S101
        return provider

    def news(self) -> NewsProvider:
        provider = self._resolve("news", self._settings.news)
        assert isinstance(provider, NewsProvider)  # noqa: S101
        return provider

    def search(self) -> SearchProvider:
        provider = self._resolve("search", self._settings.search)
        assert isinstance(provider, SearchProvider)  # noqa: S101
        return provider

    def macro_data(self) -> MacroDataProvider:
        provider = self._resolve("macro_data", self._settings.macro_data)
        assert isinstance(provider, MacroDataProvider)  # noqa: S101
        return provider

    def transcript(self) -> TranscriptProvider:
        provider = self._resolve("transcript", self._settings.transcript)
        assert isinstance(provider, TranscriptProvider)  # noqa: S101
        return provider

    def llm(self) -> LLMProvider:
        provider = self._resolve("llm", self._settings.llm)
        assert isinstance(provider, LLMProvider)  # noqa: S101
        return provider

    def embedding(self) -> EmbeddingProvider:
        provider = self._resolve("embedding", self._settings.embedding)
        assert isinstance(provider, EmbeddingProvider)  # noqa: S101
        return provider
