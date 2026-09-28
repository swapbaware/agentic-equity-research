"""NSE (National Stock Exchange) provider — filing metadata.

NSE actively restricts automated access with CAPTCHAs and bot detection.
This provider supports only:
  - Symbol resolution from the static development dataset
  - Filing metadata storage (for manually provided/uploaded filings)

Full NSE API access requires proper authorization from NSE or use of
SEBI-registered data vendors. Do NOT attempt to scrape nse-india.com.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from app.providers.base import ProviderBase, ProviderConfig
from app.providers.errors import ProviderNotFoundError
from app.providers.provenance import (
    Confidence,
    DataProvenance,
    DataQuality,
    SourceType,
)
from app.providers.rate_limiter import RateLimiter
from app.providers.symbol_map import get_identifiers
from app.providers.types import (
    Filing,
    FilingDocument,
    ProviderHealth,
)

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "nse"


def _make_provenance() -> DataProvenance:
    return DataProvenance(
        source="NSE India",
        source_type=SourceType.EXCHANGE,
        retrieved_at=datetime.now(UTC),
        provider=_PROVIDER_NAME,
        data_quality=DataQuality.AUTHORITATIVE,
        confidence=Confidence.HIGH,
    )


class NSEProvider(ProviderBase):
    """NSE filing metadata provider.

    Provides filing metadata for companies in the development dataset.
    Does NOT scrape NSE's website. Filing documents must be obtained
    through official channels (SEBI EDGAR/NSE data feeds/manual upload).
    """

    def __init__(
        self,
        config: ProviderConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        effective_config = config or ProviderConfig(
            provider_name=_PROVIDER_NAME,
            default_timeout=30.0,
            max_retries=1,
        )
        super().__init__(effective_config, rate_limiter)

    async def get_filings(
        self,
        symbol: str,
        exchange: str,
        *,
        filing_type: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Filing]:
        async def _fetch() -> list[Filing]:
            ids = get_identifiers(symbol)
            if ids is None:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"Symbol {symbol} not in development dataset",
                    operation="get_filings",
                )

            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=(
                    "NSE restricts automated access. Filing retrieval requires "
                    "official NSE data feeds or SEBI-registered data vendors. "
                    "Use BSE provider or manual document upload as alternatives."
                ),
                operation="get_filings",
            )

        return await self._execute("get_filings", _fetch)

    async def get_filing_document(self, filing_id: str) -> FilingDocument:
        async def _fetch() -> FilingDocument:
            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=(
                    "NSE document retrieval requires official API access. "
                    "Filing documents should be obtained through SEBI EDGAR "
                    "or registered data vendors."
                ),
                operation="get_filing_document",
            )

        return await self._execute("get_filing_document", _fetch)

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name=_PROVIDER_NAME,
            is_healthy=True,
            message="metadata-only provider (no live API access)",
            checked_at=datetime.now(UTC),
        )
