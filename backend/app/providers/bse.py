"""BSE (Bombay Stock Exchange) provider using BSE's public API.

Implements CorporateFilingsProvider for corporate announcements and filings.
Only uses publicly documented endpoints — does NOT scrape or bypass access controls.

BSE filings are Tier 1 (exchange) source data.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import httpx

from app.providers.base import ProviderBase, ProviderConfig
from app.providers.errors import (
    ProviderDataError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.providers.provenance import (
    Confidence,
    DataProvenance,
    DataQuality,
    SourceType,
)
from app.providers.rate_limiter import RateLimiter
from app.providers.symbol_map import DEVELOPMENT_COMPANIES, get_identifiers
from app.providers.types import (
    Filing,
    FilingDocument,
    ProviderHealth,
)

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "bse"
_BSE_API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"


def _make_provenance(*, source_url: str | None = None) -> DataProvenance:
    return DataProvenance(
        source="BSE India",
        source_type=SourceType.EXCHANGE,
        source_url=source_url,
        retrieved_at=datetime.now(UTC),
        provider=_PROVIDER_NAME,
        data_quality=DataQuality.AUTHORITATIVE,
        confidence=Confidence.HIGH,
    )


class BSEProvider(ProviderBase):
    """BSE corporate filings provider.

    Uses BSE's publicly accessible API for corporate announcements.
    Rate-limited conservatively to respect the exchange's infrastructure.
    """

    def __init__(
        self,
        config: ProviderConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        effective_config = config or ProviderConfig(
            provider_name=_PROVIDER_NAME,
            default_timeout=30.0,
            max_retries=2,
            base_retry_delay=2.0,
            rate_limit_requests=2.0,
            rate_limit_period=1.0,
        )
        super().__init__(effective_config, rate_limiter)

    def _resolve_bse_code(self, symbol: str) -> str:
        ids = get_identifiers(symbol)
        if ids is None:
            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=f"No BSE code mapping for symbol {symbol}",
                operation="resolve_bse_code",
            )
        return ids.bse_code

    async def _bse_request(self, endpoint: str, params: dict[str, str] | None = None) -> object:
        url = f"{_BSE_API_BASE}/{endpoint}"
        headers = {
            "User-Agent": "AgenticEquityResearch/0.1",
            "Accept": "application/json",
            "Referer": "https://www.bseindia.com",
        }
        async with httpx.AsyncClient(
            timeout=self._config.default_timeout,
            headers=headers,
        ) as client:
            resp = await client.get(url, params=params)

        if resp.status_code >= 500:  # noqa: PLR2004
            raise ProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message=f"BSE API returned {resp.status_code}",
            )
        if resp.status_code == 403:  # noqa: PLR2004
            raise ProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message="BSE API access restricted. Consider using official data feeds.",
            )
        if resp.status_code == 404:  # noqa: PLR2004
            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=f"BSE API endpoint not found: {endpoint}",
            )

        try:
            return resp.json()
        except Exception as exc:
            raise ProviderDataError(
                provider=_PROVIDER_NAME,
                message=f"Failed to parse BSE response: {exc}",
            ) from exc

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
            bse_code = self._resolve_bse_code(symbol)

            params: dict[str, str] = {"scripcode": bse_code}
            if start:
                params["fromdate"] = start.strftime("%Y%m%d")
            if end:
                params["todate"] = end.strftime("%Y%m%d")

            data = await self._bse_request(
                "AnnSubCategoryGetData/w", params=params
            )

            filings: list[Filing] = []
            if not isinstance(data, list):
                return filings

            provenance = _make_provenance(
                source_url=f"https://www.bseindia.com/corporates/ann.html?scrip={bse_code}"
            )
            for item in data:
                if not isinstance(item, dict):
                    continue

                ann_type = str(item.get("CATEGORYNAME", ""))
                if filing_type and filing_type.upper() not in ann_type.upper():
                    continue

                filing_date_str = item.get("NEWS_DT", "")
                try:
                    filing_dt = datetime.strptime(
                        str(filing_date_str).split("T")[0], "%Y-%m-%d"
                    ).date()
                except (ValueError, IndexError):
                    filing_dt = date.today()

                news_id = str(item.get("NEWSID", ""))
                filings.append(
                    Filing(
                        filing_id=f"BSE-{bse_code}-{news_id}",
                        symbol=symbol,
                        exchange="BSE",
                        filing_type=ann_type,
                        title=str(item.get("NEWSSUB", "BSE Announcement")),
                        filing_date=filing_dt,
                        url=item.get("ATTACHMENTNAME"),
                        provenance=provenance,
                    )
                )

            return filings

        return await self._execute("get_filings", _fetch)

    async def get_filing_document(self, filing_id: str) -> FilingDocument:
        async def _fetch() -> FilingDocument:
            parts = filing_id.split("-")
            if len(parts) < 3:  # noqa: PLR2004
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"Invalid BSE filing ID format: {filing_id}",
                    operation="get_filing_document",
                )
            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=(
                    "BSE document retrieval requires downloading the PDF from BSE's website. "
                    "Use the filing URL from get_filings() to access the document directly."
                ),
                operation="get_filing_document",
            )

        return await self._execute("get_filing_document", _fetch)

    async def check_health(self) -> ProviderHealth:
        try:
            ids = DEVELOPMENT_COMPANIES.get("RELIANCE")
            if ids is None:
                return ProviderHealth(
                    provider_name=_PROVIDER_NAME,
                    is_healthy=False,
                    message="No test company configured",
                    checked_at=datetime.now(UTC),
                )
            data = await self._bse_request(
                "AnnSubCategoryGetData/w",
                params={"scripcode": ids.bse_code},
            )
            is_healthy = isinstance(data, list)
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=is_healthy,
                message="ok" if is_healthy else "unexpected response format",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
            )
