"""Yahoo Finance provider using yfinance.

Implements MarketDataProvider, FinancialDataProvider, and CorporateActionsProvider
for Indian listed companies. yfinance is synchronous, so all calls are dispatched
to a thread pool via asyncio.to_thread.

Yahoo Finance is a convenience source (Tier 3). Do NOT treat it as authoritative
when a primary filing is available.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import yfinance as yf  # type: ignore[import-untyped]  # no py.typed marker or stubs

from app.providers.base import ProviderBase, ProviderConfig
from app.providers.errors import ProviderDataError, ProviderNotFoundError
from app.providers.provenance import (
    Confidence,
    DataProvenance,
    DataQuality,
    SourceType,
)
from app.providers.rate_limiter import RateLimiter
from app.providers.symbol_map import nse_to_yahoo
from app.providers.types import (
    CompanySearchResult,
    CorporateActionRecord,
    FinancialStatement,
    PriceBar,
    ProviderHealth,
    Quote,
)

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "yahoo_finance"


def _to_decimal(value: object) -> Decimal:
    """Convert a value to Decimal at the provider boundary. Never let floats cross inward."""
    if value is None:
        msg = "Cannot convert None to Decimal"
        raise ValueError(msg)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"Cannot convert {value!r} to Decimal"
        raise ProviderDataError(provider=_PROVIDER_NAME, message=msg) from exc


def _to_decimal_or_none(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and str(value) == "nan"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _make_provenance(*, data_period: str | None = None) -> DataProvenance:
    return DataProvenance(
        source="Yahoo Finance",
        source_type=SourceType.MARKET_DATA,
        retrieved_at=datetime.now(UTC),
        provider=_PROVIDER_NAME,
        provider_version=yf.__version__,
        data_period=data_period,
        data_quality=DataQuality.DERIVED,
        confidence=Confidence.MEDIUM,
    )


def _yahoo_symbol(symbol: str, exchange: str) -> str:
    """Map (symbol, exchange) to a Yahoo Finance ticker string."""
    if exchange.upper() == "BSE":
        return f"{symbol}.BO"
    return nse_to_yahoo(symbol)


class YahooFinanceProvider(ProviderBase):
    def __init__(
        self,
        config: ProviderConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        effective_config = config or ProviderConfig(
            provider_name=_PROVIDER_NAME,
            default_timeout=30.0,
            max_retries=2,
            base_retry_delay=1.0,
            rate_limit_requests=5.0,
            rate_limit_period=1.0,
        )
        super().__init__(effective_config, rate_limiter)

    def _get_ticker(self, symbol: str, exchange: str) -> yf.Ticker:
        yahoo_sym = _yahoo_symbol(symbol, exchange)
        return yf.Ticker(yahoo_sym)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        async def _fetch() -> Quote:
            ticker = self._get_ticker(symbol, exchange)
            info: dict[str, Any] = await asyncio.to_thread(lambda: ticker.info)

            if not info or info.get("regularMarketPrice") is None:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No quote data for {symbol} on {exchange}",
                    operation="get_quote",
                )

            price = _to_decimal(info["regularMarketPrice"])
            return Quote(
                symbol=symbol,
                exchange=exchange,
                price=price,
                open=_to_decimal_or_none(info.get("regularMarketOpen")),
                high=_to_decimal_or_none(info.get("regularMarketDayHigh")),
                low=_to_decimal_or_none(info.get("regularMarketDayLow")),
                close=_to_decimal_or_none(info.get("regularMarketPreviousClose")),
                volume=info.get("regularMarketVolume"),
                market_cap=_to_decimal_or_none(info.get("marketCap")),
                timestamp=datetime.now(UTC),
                currency=info.get("currency", "INR"),
                provenance=_make_provenance(),
            )

        return await self._execute("get_quote", _fetch)

    async def get_historical_prices(
        self, symbol: str, exchange: str, start: date, end: date
    ) -> list[PriceBar]:
        async def _fetch() -> list[PriceBar]:
            ticker = self._get_ticker(symbol, exchange)
            df = await asyncio.to_thread(
                lambda: ticker.history(start=start.isoformat(), end=end.isoformat())
            )

            if df is None or df.empty:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No price history for {symbol} on {exchange}",
                    operation="get_historical_prices",
                )

            provenance = _make_provenance(
                data_period=f"{start.isoformat()} to {end.isoformat()}"
            )
            bars: list[PriceBar] = []
            for idx, row in df.iterrows():
                bar_date = idx.date() if hasattr(idx, "date") else idx
                bars.append(
                    PriceBar(
                        date=bar_date,
                        open=_to_decimal(row["Open"]),
                        high=_to_decimal(row["High"]),
                        low=_to_decimal(row["Low"]),
                        close=_to_decimal(row["Close"]),
                        volume=int(row["Volume"]),
                        adjusted_close=_to_decimal_or_none(row.get("Adj Close")),
                        provenance=provenance,
                    )
                )
            return bars

        return await self._execute("get_historical_prices", _fetch)

    async def search_companies(self, query: str) -> list[CompanySearchResult]:
        async def _fetch() -> list[CompanySearchResult]:
            results_raw = await asyncio.to_thread(lambda: yf.Search(query))
            quotes = getattr(results_raw, "quotes", []) or []

            results: list[CompanySearchResult] = []
            for q in quotes:
                exch = q.get("exchange", "")
                if exch in ("NSI", "NSE", "BSE", "BOM"):
                    mapped_exchange = "BSE" if exch in ("BOM", "BSE") else "NSE"
                    sym = q.get("symbol", "")
                    if sym.endswith(".NS") or sym.endswith(".BO"):
                        sym = sym[:-3]
                    results.append(
                        CompanySearchResult(
                            symbol=sym,
                            exchange=mapped_exchange,
                            name=q.get("shortname", q.get("longname", "")),
                            isin=None,
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
            ticker = self._get_ticker(symbol, exchange)

            attr_map = {
                "INCOME_STATEMENT": "financials" if period_type == "ANNUAL" else "quarterly_financials",
                "BALANCE_SHEET": "balance_sheet" if period_type == "ANNUAL" else "quarterly_balance_sheet",
                "CASH_FLOW": "cashflow" if period_type == "ANNUAL" else "quarterly_cashflow",
            }

            attr = attr_map.get(statement_type)
            if attr is None:
                raise ProviderDataError(
                    provider=_PROVIDER_NAME,
                    message=f"Unknown statement type: {statement_type}",
                    operation="get_financial_statements",
                )

            df = await asyncio.to_thread(lambda: getattr(ticker, attr))

            if df is None or df.empty:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No {statement_type} data for {symbol}",
                    operation="get_financial_statements",
                )

            statements: list[FinancialStatement] = []
            for col in df.columns:
                period_date = col.date() if hasattr(col, "date") else col
                line_items: dict[str, Decimal] = {}
                for row_label in df.index:
                    val = df.loc[row_label, col]
                    dec = _to_decimal_or_none(val)
                    if dec is not None:
                        key = str(row_label).lower().replace(" ", "_")
                        line_items[key] = dec

                fiscal_year = period_date.year if hasattr(period_date, "year") else None
                period_str = f"FY{fiscal_year}" if period_type == "ANNUAL" else str(period_date)

                statements.append(
                    FinancialStatement(
                        symbol=symbol,
                        exchange=exchange,
                        statement_type=statement_type,
                        period_type=period_type,
                        period=period_str,
                        filing_date=period_date if isinstance(period_date, date) else None,
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
            ticker = self._get_ticker(symbol, exchange)
            info: dict[str, Any] = await asyncio.to_thread(lambda: ticker.info)

            if not info:
                raise ProviderNotFoundError(
                    provider=_PROVIDER_NAME,
                    message=f"No data for {symbol}",
                    operation="get_financial_ratios",
                )

            ratio_keys = {
                "trailingPE": "pe_ratio",
                "forwardPE": "forward_pe",
                "priceToBook": "pb_ratio",
                "debtToEquity": "debt_to_equity",
                "returnOnEquity": "roe",
                "currentRatio": "current_ratio",
                "quickRatio": "quick_ratio",
                "operatingMargins": "operating_margin",
                "profitMargins": "profit_margin",
                "revenueGrowth": "revenue_growth",
                "earningsGrowth": "earnings_growth",
                "dividendYield": "dividend_yield",
            }

            ratios: dict[str, object] = {}
            for yf_key, our_key in ratio_keys.items():
                val = info.get(yf_key)
                dec = _to_decimal_or_none(val)
                if dec is not None:
                    ratios[our_key] = dec
            return ratios

        return await self._execute("get_financial_ratios", _fetch)

    async def get_corporate_actions(
        self,
        symbol: str,
        exchange: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateActionRecord]:
        async def _fetch() -> list[CorporateActionRecord]:
            ticker = self._get_ticker(symbol, exchange)

            dividends = await asyncio.to_thread(lambda: ticker.dividends)
            splits = await asyncio.to_thread(lambda: ticker.splits)

            provenance = _make_provenance()
            actions: list[CorporateActionRecord] = []

            if dividends is not None and not dividends.empty:
                for idx, val in dividends.items():
                    action_date = idx.date() if hasattr(idx, "date") else idx
                    if start and action_date < start:
                        continue
                    if end and action_date > end:
                        continue
                    actions.append(
                        CorporateActionRecord(
                            symbol=symbol,
                            exchange=exchange,
                            action_type="DIVIDEND",
                            ex_date=action_date,
                            details=f"Dividend of INR {val} per share",
                            value=_to_decimal(val),
                            provenance=provenance,
                        )
                    )

            if splits is not None and not splits.empty:
                for idx, val in splits.items():
                    action_date = idx.date() if hasattr(idx, "date") else idx
                    if start and action_date < start:
                        continue
                    if end and action_date > end:
                        continue
                    actions.append(
                        CorporateActionRecord(
                            symbol=symbol,
                            exchange=exchange,
                            action_type="STOCK_SPLIT",
                            ex_date=action_date,
                            details=f"Stock split {val}:1",
                            value=_to_decimal(val),
                            provenance=provenance,
                        )
                    )

            return actions

        return await self._execute("get_corporate_actions", _fetch)

    async def check_health(self) -> ProviderHealth:
        try:
            ticker = yf.Ticker("RELIANCE.NS")
            info = await asyncio.to_thread(lambda: ticker.info)
            is_healthy = bool(info and info.get("regularMarketPrice"))
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=is_healthy,
                message="ok" if is_healthy else "no data returned",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            return ProviderHealth(
                provider_name=_PROVIDER_NAME,
                is_healthy=False,
                message=str(exc),
                checked_at=datetime.now(UTC),
            )
