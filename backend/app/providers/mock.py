"""Mock provider implementations for testing.

Each mock satisfies its Protocol interface and returns deterministic data
for a small set of Indian companies (RELIANCE, INFY, TCS on NSE).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.providers.errors import ProviderNotFoundError
from app.providers.types import (
    ChatMessage,
    CompanySearchResult,
    CorporateActionRecord,
    EmbeddingResult,
    Filing,
    FilingDocument,
    FinancialStatement,
    LLMResponse,
    MacroDataPoint,
    MacroIndicatorInfo,
    MacroSeries,
    NewsArticle,
    PriceBar,
    ProviderHealth,
    Quote,
    SearchResult,
    ShareholderCategory,
    ShareholdingPattern,
    TokenUsage,
    ToolDefinition,
    Transcript,
    TranscriptSegment,
    TranscriptSummary,
)

_KNOWN_SYMBOLS = {"RELIANCE", "INFY", "TCS"}


def _check_symbol(provider: str, symbol: str) -> None:
    if symbol not in _KNOWN_SYMBOLS:
        raise ProviderNotFoundError(
            provider=provider,
            message=f"Symbol {symbol} not found",
            operation="lookup",
        )


def _health(name: str) -> ProviderHealth:
    return ProviderHealth(
        provider_name=name,
        is_healthy=True,
        latency_ms=1.0,
        message="mock",
        checked_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# MarketDataProvider
# ---------------------------------------------------------------------------

_QUOTES: dict[str, dict[str, Decimal]] = {
    "RELIANCE": {"price": Decimal("2456.75"), "market_cap": Decimal("16623500000000")},
    "INFY": {"price": Decimal("1534.20"), "market_cap": Decimal("6380000000000")},
    "TCS": {"price": Decimal("3842.50"), "market_cap": Decimal("14050000000000")},
}


class MockMarketDataProvider:
    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        _check_symbol("mock_market_data", symbol)
        q = _QUOTES[symbol]
        return Quote(
            symbol=symbol,
            exchange=exchange,
            price=q["price"],
            open=q["price"] - Decimal("10"),
            high=q["price"] + Decimal("20"),
            low=q["price"] - Decimal("15"),
            close=q["price"],
            volume=5_000_000,
            market_cap=q["market_cap"],
            timestamp=datetime.now(UTC),
        )

    async def get_historical_prices(
        self, symbol: str, exchange: str, start: date, end: date
    ) -> list[PriceBar]:
        _check_symbol("mock_market_data", symbol)
        base = _QUOTES[symbol]["price"]
        bars: list[PriceBar] = []
        current = start
        day_delta = (end - start).days or 1
        for i in range(min(day_delta, 30)):
            d = date.fromordinal(current.toordinal() + i)
            offset = Decimal(str(i * 2))
            bars.append(
                PriceBar(
                    date=d,
                    open=base + offset,
                    high=base + offset + Decimal("15"),
                    low=base + offset - Decimal("10"),
                    close=base + offset + Decimal("5"),
                    volume=5_000_000 + i * 100_000,
                )
            )
        return bars

    async def search_companies(self, query: str) -> list[CompanySearchResult]:
        results = []
        q = query.upper()
        mapping = {
            "RELIANCE": ("Reliance Industries Ltd", "INE002A01018"),
            "INFY": ("Infosys Ltd", "INE009A01021"),
            "TCS": ("Tata Consultancy Services Ltd", "INE467B01029"),
        }
        for sym, (name, isin) in mapping.items():
            if q in sym or q in name.upper():
                results.append(
                    CompanySearchResult(symbol=sym, exchange="NSE", name=name, isin=isin)
                )
        return results

    async def check_health(self) -> ProviderHealth:
        return _health("mock_market_data")


# ---------------------------------------------------------------------------
# FinancialDataProvider
# ---------------------------------------------------------------------------


class MockFinancialDataProvider:
    async def get_financial_statements(
        self,
        symbol: str,
        exchange: str,
        statement_type: str,
        period_type: str,
    ) -> list[FinancialStatement]:
        _check_symbol("mock_financial_data", symbol)
        if statement_type == "INCOME_STATEMENT":
            items = {
                "revenue": Decimal("250000000000"),
                "cost_of_goods_sold": Decimal("150000000000"),
                "gross_profit": Decimal("100000000000"),
                "operating_expenses": Decimal("30000000000"),
                "operating_income": Decimal("70000000000"),
                "net_income": Decimal("50000000000"),
            }
        elif statement_type == "BALANCE_SHEET":
            items = {
                "total_assets": Decimal("1500000000000"),
                "total_liabilities": Decimal("800000000000"),
                "total_equity": Decimal("700000000000"),
                "cash_and_equivalents": Decimal("120000000000"),
                "total_debt": Decimal("300000000000"),
            }
        else:
            items = {
                "operating_cash_flow": Decimal("80000000000"),
                "investing_cash_flow": Decimal("-40000000000"),
                "financing_cash_flow": Decimal("-25000000000"),
                "free_cash_flow": Decimal("55000000000"),
            }
        return [
            FinancialStatement(
                symbol=symbol,
                exchange=exchange,
                statement_type=statement_type,
                period_type=period_type,
                period="FY2024",
                filing_date=date(2024, 5, 15),
                line_items=items,
            )
        ]

    async def get_financial_ratios(
        self, symbol: str, exchange: str
    ) -> dict[str, object]:
        _check_symbol("mock_financial_data", symbol)
        return {
            "pe_ratio": Decimal("28.5"),
            "pb_ratio": Decimal("4.2"),
            "debt_to_equity": Decimal("0.43"),
            "roe": Decimal("0.185"),
            "roce": Decimal("0.162"),
            "current_ratio": Decimal("1.45"),
        }

    async def check_health(self) -> ProviderHealth:
        return _health("mock_financial_data")


# ---------------------------------------------------------------------------
# CorporateFilingsProvider
# ---------------------------------------------------------------------------


class MockCorporateFilingsProvider:
    async def get_filings(
        self,
        symbol: str,
        exchange: str,
        *,
        filing_type: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Filing]:
        _check_symbol("mock_corporate_filings", symbol)
        return [
            Filing(
                filing_id=f"{symbol}-AR-2024",
                symbol=symbol,
                exchange=exchange,
                filing_type="ANNUAL_REPORT",
                title=f"{symbol} Annual Report FY2024",
                filing_date=date(2024, 5, 30),
                url=f"https://example.com/filings/{symbol}/ar2024.pdf",
            ),
            Filing(
                filing_id=f"{symbol}-QR-Q1FY25",
                symbol=symbol,
                exchange=exchange,
                filing_type="QUARTERLY_RESULT",
                title=f"{symbol} Q1 FY2025 Results",
                filing_date=date(2024, 7, 20),
            ),
        ]

    async def get_filing_document(self, filing_id: str) -> FilingDocument:
        symbol = filing_id.split("-")[0]
        if symbol not in _KNOWN_SYMBOLS:
            raise ProviderNotFoundError(
                provider="mock_corporate_filings",
                message=f"Filing {filing_id} not found",
                operation="get_filing_document",
            )
        return FilingDocument(
            filing_id=filing_id,
            content=f"Mock filing content for {filing_id}. Revenue grew 15% YoY.",
            content_type="text/plain",
        )

    async def check_health(self) -> ProviderHealth:
        return _health("mock_corporate_filings")


# ---------------------------------------------------------------------------
# ShareholdingProvider
# ---------------------------------------------------------------------------


class MockShareholdingProvider:
    async def get_shareholding_pattern(
        self, symbol: str, exchange: str, quarter: str
    ) -> ShareholdingPattern:
        _check_symbol("mock_shareholding", symbol)
        return ShareholdingPattern(
            symbol=symbol,
            exchange=exchange,
            quarter=quarter,
            date=date(2024, 6, 30),
            categories=[
                ShareholderCategory(category="PROMOTER", percentage=Decimal("50.49"), shares=3_406_000_000),
                ShareholderCategory(category="FII", percentage=Decimal("23.34"), shares=1_575_000_000),
                ShareholderCategory(category="DII", percentage=Decimal("13.12"), shares=885_000_000),
                ShareholderCategory(category="PUBLIC", percentage=Decimal("13.05"), shares=880_000_000),
            ],
            total_shares=6_746_000_000,
            pledged_percentage=Decimal("0.00"),
        )

    async def get_shareholding_history(
        self, symbol: str, exchange: str, *, start: date | None = None, end: date | None = None
    ) -> list[ShareholdingPattern]:
        pattern = await self.get_shareholding_pattern(symbol, exchange, "Q1FY2025")
        return [pattern]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_shareholding")


# ---------------------------------------------------------------------------
# CorporateActionsProvider
# ---------------------------------------------------------------------------


class MockCorporateActionsProvider:
    async def get_corporate_actions(
        self,
        symbol: str,
        exchange: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateActionRecord]:
        _check_symbol("mock_corporate_actions", symbol)
        return [
            CorporateActionRecord(
                symbol=symbol,
                exchange=exchange,
                action_type="DIVIDEND",
                ex_date=date(2024, 7, 18),
                record_date=date(2024, 7, 19),
                details="Final Dividend of INR 10 per share",
                value=Decimal("10.00"),
            ),
        ]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_corporate_actions")


# ---------------------------------------------------------------------------
# NewsProvider
# ---------------------------------------------------------------------------


class MockNewsProvider:
    async def search_news(
        self, query: str, *, start: date | None = None, end: date | None = None, limit: int = 10
    ) -> list[NewsArticle]:
        return [
            NewsArticle(
                title=f"Market update: {query}",
                url="https://example.com/news/1",
                source="MockFinancialTimes",
                published_at=datetime.now(UTC),
                summary=f"Latest developments related to {query}.",
                symbols=[],
            ),
        ]

    async def get_company_news(
        self, symbol: str, exchange: str, *, limit: int = 10
    ) -> list[NewsArticle]:
        _check_symbol("mock_news", symbol)
        return [
            NewsArticle(
                title=f"{symbol} reports strong quarterly results",
                url=f"https://example.com/news/{symbol.lower()}/1",
                source="MockFinancialTimes",
                published_at=datetime.now(UTC),
                summary=f"{symbol} beats market expectations with 15% revenue growth.",
                symbols=[symbol],
            ),
        ]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_news")


# ---------------------------------------------------------------------------
# SearchProvider
# ---------------------------------------------------------------------------


class MockSearchProvider:
    async def search(self, query: str, *, num_results: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Result for: {query}",
                url=f"https://example.com/search?q={query}",
                snippet=f"Mock search result snippet for query: {query}",
            ),
        ]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_search")


# ---------------------------------------------------------------------------
# MacroDataProvider
# ---------------------------------------------------------------------------

_MACRO_INDICATORS = {
    "REPO_RATE": MacroIndicatorInfo(
        indicator_id="REPO_RATE",
        name="RBI Repo Rate",
        description="Reserve Bank of India policy repo rate",
        source="RBI",
        frequency="MONTHLY",
        unit="PERCENTAGE",
    ),
    "CPI_INFLATION": MacroIndicatorInfo(
        indicator_id="CPI_INFLATION",
        name="CPI Inflation (YoY)",
        source="MOSPI",
        frequency="MONTHLY",
        unit="PERCENTAGE",
    ),
    "GDP_GROWTH": MacroIndicatorInfo(
        indicator_id="GDP_GROWTH",
        name="GDP Growth Rate (YoY)",
        source="MOSPI",
        frequency="QUARTERLY",
        unit="PERCENTAGE",
    ),
}


class MockMacroDataProvider:
    async def get_indicator(
        self, indicator_id: str, *, start: date | None = None, end: date | None = None
    ) -> MacroSeries:
        info = _MACRO_INDICATORS.get(indicator_id)
        if info is None:
            raise ProviderNotFoundError(
                provider="mock_macro_data",
                message=f"Indicator {indicator_id} not found",
                operation="get_indicator",
            )
        return MacroSeries(
            indicator_id=info.indicator_id,
            name=info.name,
            unit=info.unit,
            data_points=[
                MacroDataPoint(date=date(2024, 1, 1), value=Decimal("6.50")),
                MacroDataPoint(date=date(2024, 4, 1), value=Decimal("6.50")),
                MacroDataPoint(date=date(2024, 7, 1), value=Decimal("6.25")),
            ],
        )

    async def list_indicators(self) -> list[MacroIndicatorInfo]:
        return list(_MACRO_INDICATORS.values())

    async def check_health(self) -> ProviderHealth:
        return _health("mock_macro_data")


# ---------------------------------------------------------------------------
# TranscriptProvider
# ---------------------------------------------------------------------------


class MockTranscriptProvider:
    async def get_transcript(
        self, symbol: str, exchange: str, quarter: str, year: int
    ) -> Transcript:
        _check_symbol("mock_transcript", symbol)
        return Transcript(
            symbol=symbol,
            exchange=exchange,
            quarter=quarter,
            year=year,
            date=date(year, 7, 20),
            title=f"{symbol} {quarter} FY{year} Earnings Call",
            segments=[
                TranscriptSegment(
                    speaker="CEO",
                    role="CEO",
                    text=f"We are pleased to report strong results for {quarter}.",
                ),
                TranscriptSegment(
                    speaker="CFO",
                    role="CFO",
                    text="Revenue grew 15% year-over-year driven by all segments.",
                ),
                TranscriptSegment(
                    speaker="Analyst",
                    role="ANALYST",
                    text="What is your guidance for the next quarter?",
                ),
            ],
            raw_text=f"Mock transcript for {symbol} {quarter} FY{year}",
        )

    async def list_transcripts(self, symbol: str, exchange: str) -> list[TranscriptSummary]:
        _check_symbol("mock_transcript", symbol)
        return [
            TranscriptSummary(
                symbol=symbol,
                exchange=exchange,
                quarter="Q1",
                year=2025,
                date=date(2024, 7, 20),
                title=f"{symbol} Q1 FY2025 Earnings Call",
            ),
        ]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_transcript")


# ---------------------------------------------------------------------------
# LLMProvider
# ---------------------------------------------------------------------------


class MockLLMProvider:
    def __init__(self, *, default_model: str = "mock-llm-v1") -> None:
        self._default_model = default_model
        self._call_count = 0

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        response_schema: dict[str, object] | None = None,
    ) -> LLMResponse:
        self._call_count += 1
        used_model = model or self._default_model
        content = f"Mock LLM response to: {prompt[:100]}"
        input_tokens = len(prompt) // 4
        output_tokens = len(content) // 4
        return LLMResponse(
            content=content,
            model=used_model,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason="stop",
            response_id=str(uuid.uuid4()),
            cost_usd=Decimal("0.001"),
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self._call_count += 1
        used_model = model or self._default_model
        last_msg = messages[-1].content if messages else ""
        content = f"Mock chat response to: {last_msg[:100]}"
        input_tokens = sum(len(m.content) // 4 for m in messages)
        output_tokens = len(content) // 4
        return LLMResponse(
            content=content,
            model=used_model,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason="stop",
            response_id=str(uuid.uuid4()),
            cost_usd=Decimal("0.002"),
        )

    async def check_health(self) -> ProviderHealth:
        return _health("mock_llm")


# ---------------------------------------------------------------------------
# EmbeddingProvider
# ---------------------------------------------------------------------------


class MockEmbeddingProvider:
    def __init__(self, *, dimensions: int = 1536, default_model: str = "mock-embed-v1") -> None:
        self._dimensions = dimensions
        self._default_model = default_model

    async def embed(
        self, texts: list[str], *, model: str | None = None
    ) -> EmbeddingResult:
        embeddings = [self._deterministic_vector(t) for t in texts]
        total_tokens = sum(len(t) // 4 for t in texts)
        return EmbeddingResult(
            embeddings=embeddings,
            model=model or self._default_model,
            usage=TokenUsage(input_tokens=total_tokens, output_tokens=0, total_tokens=total_tokens),
        )

    async def embed_single(
        self, text: str, *, model: str | None = None
    ) -> list[float]:
        result = await self.embed([text], model=model)
        return result.embeddings[0]

    async def check_health(self) -> ProviderHealth:
        return _health("mock_embedding")

    def _deterministic_vector(self, text: str) -> list[float]:
        h = hash(text) & 0xFFFFFFFF
        return [((h * (i + 1)) % 1000) / 1000.0 for i in range(self._dimensions)]
