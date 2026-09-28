"""Provider framework — external service abstraction layer.

Import interfaces for type annotations, factory for instantiation.
Business logic depends only on Protocol interfaces, never concrete providers.
"""
from app.providers.config import ProviderSettings
from app.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
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
from app.providers.provenance import DataConflict, DataProvenance
from app.providers.reconciliation import DataReconciler

__all__ = [
    # Interfaces
    "CorporateActionsProvider",
    "CorporateFilingsProvider",
    "EmbeddingProvider",
    "FinancialDataProvider",
    "LLMProvider",
    "MacroDataProvider",
    "MarketDataProvider",
    "NewsProvider",
    "SearchProvider",
    "ShareholdingProvider",
    "TranscriptProvider",
    # Factory + config
    "ProviderFactory",
    "ProviderSettings",
    # Provenance + reconciliation
    "DataConflict",
    "DataProvenance",
    "DataReconciler",
    # Errors
    "ProviderAuthError",
    "ProviderDataError",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
