"""Alpha Vantage provider using httpx async client.

Implements MarketDataProvider and FinancialDataProvider. Requires an API key
configured via PROVIDER_ALPHA_VANTAGE_API_KEY. Free tier is severely rate-limited
(25 requests/day), so aggressive caching and rate limiting are essential.

Alpha Vantage is a Tier 3 convenience source. Do NOT treat it as authoritative
when a primary filing is available.
"""
from __future__ import annotations

import contextlib
import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import ProviderBase, ProviderConfig
from app.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.providers.provenance import (
    Confidence,
    DataProvenance,
    DataQuality,
    SourceType,
)
from app.providers.rate_limiter import RateLimiter
from app.providers.types import (
    CompanySearchResult,
    FinancialStatement,
    PriceBar,
    ProviderHealth,
    Quote,
)

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "alpha_vantage"
_BASE_URL = "https://www.alphavantage.co/query"


def _to_decimal(value: str | object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"Cannot convert {value!r} to Decimal"
        raise ProviderDataError(provider=_PROVIDER_NAME, message=msg) from exc


def _to_decimal_or_none(value: str | object | None) -> Decimal | None:
    if value is None or value == "None" or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _make_provenance(*, data_period: str | None = None) -> DataProvenance:
    return DataProvenance(
        source="Alpha Vantage",
        source_type=SourceType.MARKET_DATA,
        source_url=_BASE_URL,
        retrieved_at=datetime.now(UTC),
        provider=_PROVIDER_NAME,
        data_period=data_period,
        data_quality=DataQuality.DERIVED,
        confidence=Confidence.MEDIUM,
    )


class AlphaVantageProvider(ProviderBase):
    def __init__(
        self,
        api_key: str,
        config: ProviderConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        effective_config = config or ProviderConfig(
            provider_name=_PROVIDER_NAME,
            default_timeout=30.0,
            max_retries=2,
            base_retry_delay=2.0,
            rate_limit_requests=5.0,
            rate_limit_period=60.0,
        )
        super().__init__(effective_config, rate_limiter)
        if not api_key:
            raise ProviderAuthError(
                provider=_PROVIDER_NAME,
                message="Alpha Vantage API key is required. Set PROVIDER_ALPHA_VANTAGE_API_KEY.",
            )
        self._api_key = api_key

    async def _request(self, params: dict[str, str]) -> dict[str, object]:
        params["apikey"] = self._api_key
        async with httpx.AsyncClient(timeout=self._config.default_timeout) as client:
            resp = await client.get(_BASE_URL, params=params)

        if resp.status_code == 401:  # noqa: PLR2004
            raise ProviderAuthError(
                provider=_PROVIDER_NAME,
                message="Invalid Alpha Vantage API key",
            )
        if resp.status_code == 429:  # noqa: PLR2004
            raise ProviderRateLimitError(
                provider=_PROVIDER_NAME,
                message="Alpha Vantage rate limit exceeded",
                retry_after=60.0,
            )
        if resp.status_code >= 500:  # noqa: PLR2004
            raise ProviderUnavailableError(
                provider=_PROVIDER_NAME,
                message=f"Alpha Vantage returned {resp.status_code}",
            )

        data: dict[str, object] = resp.json()

        if "Error Message" in data:
            raise ProviderNotFoundError(
                provider=_PROVIDER_NAME,
                message=str(data["Error Message"]),
            )
        if "Note" in data:
            raise ProviderRateLimitError(
                provider=_PROVIDER_NAME,
                message=str(data["Note"]),
                retry_after=60.0,
            )
        if "Information" in data and "premium" in str(data["Information"]).lower():
            raise ProviderRateLimitError(
                provider=_PROVIDER_NAME,
                message=str(data["Information"]),
                retry_after=60.0,
            )

        return data

    def _av_symbol(self, symbol: str, exchange: str) -> str:
        if exchange.upper() == "BSE":
            return f"{symbol}.BSE"
        return f"{symbol}.BSE"

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        async def _fetch() -> Quote:
            av_sym = self._av_symbol(symbol, exchange)
            data = await self._request({
                "function": "GLOBAL_QUOTE",
                "symbol": av_sym,
            })

            gq = data.get("Global Quote")
            if not gq or not isinstance(gq, dict):
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No quote data for {symbol}",
                    operation="get_quote",
                )

            price = _to_decimal(gq.get("05. price", "0"))
            return Quote(
                symbol=symbol,
                exchange=exchange,
                price=price,
                open=_to_decimal_or_none(gq.get("02. open")),
                high=_to_decimal_or_none(gq.get("03. high")),
                low=_to_decimal_or_none(gq.get("04. low")),
                close=_to_decimal_or_none(gq.get("08. previous close")),
                volume=int(gq["06. volume"]) if gq.get("06. volume") else None,
                timestamp=datetime.now(UTC),
                currency="INR",
                provenance=_make_provenance(),
            )

        return await self._execute("get_quote", _fetch)

    async def get_historical_prices(
        self, symbol: str, exchange: str, start: date, end: date
    ) -> list[PriceBar]:
        async def _fetch() -> list[PriceBar]:
            av_sym = self._av_symbol(symbol, exchange)
            data = await self._request({
                "function": "TIME_SERIES_DAILY",
                "symbol": av_sym,
                "outputsize": "full",
            })

            ts_key = "Time Series (Daily)"
            ts = data.get(ts_key)
            if not ts or not isinstance(ts, dict):
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No price history for {symbol}",
                    operation="get_historical_prices",
                )

            provenance = _make_provenance(
                data_period=f"{start.isoformat()} to {end.isoformat()}"
            )
            bars: list[PriceBar] = []
            for date_str, values in sorted(ts.items()):
                bar_date = date.fromisoformat(date_str)
                if bar_date < start or bar_date > end:
                    continue
                if not isinstance(values, dict):
                    continue
                bars.append(
                    PriceBar(
                        date=bar_date,
                        open=_to_decimal(values["1. open"]),
                        high=_to_decimal(values["2. high"]),
                        low=_to_decimal(values["3. low"]),
                        close=_to_decimal(values["4. close"]),
                        volume=int(values["5. volume"]),
                        provenance=provenance,
                    )
                )
            return bars

        return await self._execute("get_historical_prices", _fetch)

    async def search_companies(self, query: str) -> list[CompanySearchResult]:
        async def _fetch() -> list[CompanySearchResult]:
            data = await self._request({
                "function": "SYMBOL_SEARCH",
                "keywords": query,
            })

            matches = data.get("bestMatches")
            if not matches or not isinstance(matches, list):
                return []

            results: list[CompanySearchResult] = []
            for m in matches:
                if not isinstance(m, dict):
                    continue
                region = str(m.get("4. region", ""))
                if "India" not in region and "india" not in region:
                    continue
                sym_raw = str(m.get("1. symbol", ""))
                sym = sym_raw.replace(".BSE", "").replace(".NSE", "")
                exchange = "BSE" if ".BSE" in sym_raw else "NSE"
                results.append(
                    CompanySearchResult(
                        symbol=sym,
                        exchange=exchange,
                        name=str(m.get("2. name", "")),
                    )
                )
            return results

        return await self._execute("search_companies", _fetch)

    async def get_financial_statements(
        self,
        symbol: str,
        exchange: str,
        statement_type: str,
        period_type: str,
    ) -> list[FinancialStatement]:
        async def _fetch() -> list[FinancialStatement]:
            function_map = {
                "INCOME_STATEMENT": "INCOME_STATEMENT",
                "BALANCE_SHEET": "BALANCE_SHEET",
                "CASH_FLOW": "CASH_FLOW",
            }
            av_func = function_map.get(statement_type)
            if av_func is None:
                raise ProviderDataError(
                    provider=_PROVIDER_NAME,
                    message=f"Unknown statement type: {statement_type}",
                )

            av_sym = self._av_symbol(symbol, exchange)
            data = await self._request({
                "function": av_func,
                "symbol": av_sym,
            })

            report_key = "annualReports" if period_type == "ANNUAL" else "quarterlyReports"
            reports = data.get(report_key)
            if not reports or not isinstance(reports, list):
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No {statement_type} data for {symbol}",
                )

            statements: list[FinancialStatement] = []
            for report in reports:
                if not isinstance(report, dict):
                    continue
                fiscal_date = report.get("fiscalDateEnding", "")
                line_items: dict[str, Decimal] = {}
                for k, v in report.items():
                    if k == "fiscalDateEnding" or k == "reportedCurrency":
                        continue
                    dec = _to_decimal_or_none(v)
                    if dec is not None:
                        line_items[k] = dec

                filing_date = None
                if fiscal_date:
                    with contextlib.suppress(ValueError):
                        filing_date = date.fromisoformat(str(fiscal_date))

                period_str = str(fiscal_date) if fiscal_date else "unknown"
                statements.append(
                    FinancialStatement(
                        symbol=symbol,
                        exchange=exchange,
                        statement_type=statement_type,
                        period_type=period_type,
                        period=period_str,
                        filing_date=filing_date,
                        currency=str(report.get("reportedCurrency", "INR")),
                        line_items=line_items,
                        provenance=_make_provenance(data_period=period_str),
                    )
                )
            return statements

        return await self._execute("get_financial_statements", _fetch)

    async def get_financial_ratios(
        self, symbol: str, exchange: str
    ) -> dict[str, object]:
        async def _fetch() -> dict[str, object]:
            av_sym = self._av_symbol(symbol, exchange)
            data = await self._request({
                "function": "OVERVIEW",
                "symbol": av_sym,
            })

            if not data or "Symbol" not in data:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No overview data for {symbol}",
                )

            ratio_keys = {
                "TrailingPE": "pe_ratio",
                "ForwardPE": "forward_pe",
                "PriceToBookRatio": "pb_ratio",
                "ReturnOnEquityTTM": "roe",
                "OperatingMarginTTM": "operating_margin",
                "ProfitMargin": "profit_margin",
                "DividendYield": "dividend_yield",
                "Beta": "beta",
                "52WeekHigh": "week_52_high",
                "52WeekLow": "week_52_low",
                "EVToRevenue": "ev_to_revenue",
                "EVToEBITDA": "ev_to_ebitda",
            }

            ratios: dict[str, object] = {}
            for av_key, our_key in ratio_keys.items():
                val = data.get(av_key)
                dec = _to_decimal_or_none(val)
                if dec is not None:
                    ratios[our_key] = dec
            return ratios

        return await self._execute("get_financial_ratios", _fetch)

    async def check_health(self) -> ProviderHealth:
        try:
            data = await self._request({
                "function": "GLOBAL_QUOTE",
                "symbol": "RELIANCE.BSE",
            })
            is_healthy = "Global Quote" in data
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=is_healthy,
                message="ok" if is_healthy else "unexpected response",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
            )
