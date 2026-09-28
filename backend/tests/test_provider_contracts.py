"""Contract tests for every provider interface.

Each test class verifies that the mock implementation satisfies its Protocol contract:
- Returns the correct type
- Financial values are Decimal
- Not-found cases raise ProviderNotFoundError
- Health checks return ProviderHealth
- The mock is structurally compatible with the Protocol (isinstance check)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.providers.errors import ProviderNotFoundError
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
from app.providers.types import (
    ChatMessage,
    CompanySearchResult,
    CorporateActionRecord,
    EmbeddingResult,
    Filing,
    FilingDocument,
    FinancialStatement,
    LLMResponse,
    MacroIndicatorInfo,
    MacroSeries,
    NewsArticle,
    PriceBar,
    ProviderHealth,
    Quote,
    SearchResult,
    ShareholdingPattern,
    Transcript,
    TranscriptSummary,
)

# ---------------------------------------------------------------------------
# MarketDataProvider
# ---------------------------------------------------------------------------


class TestMarketDataProviderContract:
    @pytest.fixture
    def provider(self) -> MockMarketDataProvider:
        return MockMarketDataProvider()

    def test_isinstance_check(self, provider: MockMarketDataProvider) -> None:
        assert isinstance(provider, MarketDataProvider)

    @pytest.mark.asyncio
    async def test_get_quote_returns_quote(self, provider: MockMarketDataProvider) -> None:
        result = await provider.get_quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert isinstance(result.price, Decimal)
        assert result.symbol == "RELIANCE"
        assert result.exchange == "NSE"
        assert result.currency == "INR"

    @pytest.mark.asyncio
    async def test_get_quote_market_cap_is_decimal(self, provider: MockMarketDataProvider) -> None:
        result = await provider.get_quote("TCS", "NSE")
        assert result.market_cap is not None
        assert isinstance(result.market_cap, Decimal)

    @pytest.mark.asyncio
    async def test_get_quote_not_found(self, provider: MockMarketDataProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_quote("NONEXISTENT", "NSE")

    @pytest.mark.asyncio
    async def test_get_historical_prices(self, provider: MockMarketDataProvider) -> None:
        bars = await provider.get_historical_prices(
            "INFY", "NSE", date(2024, 1, 1), date(2024, 1, 10)
        )
        assert len(bars) > 0
        assert all(isinstance(b, PriceBar) for b in bars)
        assert all(isinstance(b.close, Decimal) for b in bars)

    @pytest.mark.asyncio
    async def test_get_historical_prices_not_found(self, provider: MockMarketDataProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_historical_prices("FAKE", "NSE", date(2024, 1, 1), date(2024, 1, 10))

    @pytest.mark.asyncio
    async def test_search_companies(self, provider: MockMarketDataProvider) -> None:
        results = await provider.search_companies("Reliance")
        assert len(results) >= 1
        assert all(isinstance(r, CompanySearchResult) for r in results)
        assert results[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_search_companies_no_match(self, provider: MockMarketDataProvider) -> None:
        results = await provider.search_companies("zzzzzzz")
        assert results == []

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockMarketDataProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# FinancialDataProvider
# ---------------------------------------------------------------------------


class TestFinancialDataProviderContract:
    @pytest.fixture
    def provider(self) -> MockFinancialDataProvider:
        return MockFinancialDataProvider()

    def test_isinstance_check(self, provider: MockFinancialDataProvider) -> None:
        assert isinstance(provider, FinancialDataProvider)

    @pytest.mark.asyncio
    async def test_get_income_statement(self, provider: MockFinancialDataProvider) -> None:
        stmts = await provider.get_financial_statements("RELIANCE", "NSE", "INCOME_STATEMENT", "ANNUAL")
        assert len(stmts) >= 1
        stmt = stmts[0]
        assert isinstance(stmt, FinancialStatement)
        assert all(isinstance(v, Decimal) for v in stmt.line_items.values())
        assert "revenue" in stmt.line_items

    @pytest.mark.asyncio
    async def test_get_balance_sheet(self, provider: MockFinancialDataProvider) -> None:
        stmts = await provider.get_financial_statements("INFY", "NSE", "BALANCE_SHEET", "ANNUAL")
        assert "total_assets" in stmts[0].line_items

    @pytest.mark.asyncio
    async def test_get_cash_flow(self, provider: MockFinancialDataProvider) -> None:
        stmts = await provider.get_financial_statements("TCS", "NSE", "CASH_FLOW", "ANNUAL")
        assert "free_cash_flow" in stmts[0].line_items

    @pytest.mark.asyncio
    async def test_get_financial_statements_not_found(self, provider: MockFinancialDataProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_financial_statements("FAKE", "NSE", "INCOME_STATEMENT", "ANNUAL")

    @pytest.mark.asyncio
    async def test_get_financial_ratios(self, provider: MockFinancialDataProvider) -> None:
        ratios = await provider.get_financial_ratios("RELIANCE", "NSE")
        assert "pe_ratio" in ratios
        assert isinstance(ratios["pe_ratio"], Decimal)

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockFinancialDataProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# CorporateFilingsProvider
# ---------------------------------------------------------------------------


class TestCorporateFilingsProviderContract:
    @pytest.fixture
    def provider(self) -> MockCorporateFilingsProvider:
        return MockCorporateFilingsProvider()

    def test_isinstance_check(self, provider: MockCorporateFilingsProvider) -> None:
        assert isinstance(provider, CorporateFilingsProvider)

    @pytest.mark.asyncio
    async def test_get_filings(self, provider: MockCorporateFilingsProvider) -> None:
        filings = await provider.get_filings("RELIANCE", "NSE")
        assert len(filings) >= 1
        assert all(isinstance(f, Filing) for f in filings)
        assert filings[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_filings_not_found(self, provider: MockCorporateFilingsProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_filings("FAKE", "NSE")

    @pytest.mark.asyncio
    async def test_get_filing_document(self, provider: MockCorporateFilingsProvider) -> None:
        doc = await provider.get_filing_document("RELIANCE-AR-2024")
        assert isinstance(doc, FilingDocument)
        assert doc.filing_id == "RELIANCE-AR-2024"
        assert len(doc.content) > 0

    @pytest.mark.asyncio
    async def test_get_filing_document_not_found(self, provider: MockCorporateFilingsProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_filing_document("FAKE-AR-2024")

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockCorporateFilingsProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# ShareholdingProvider
# ---------------------------------------------------------------------------


class TestShareholdingProviderContract:
    @pytest.fixture
    def provider(self) -> MockShareholdingProvider:
        return MockShareholdingProvider()

    def test_isinstance_check(self, provider: MockShareholdingProvider) -> None:
        assert isinstance(provider, ShareholdingProvider)

    @pytest.mark.asyncio
    async def test_get_shareholding_pattern(self, provider: MockShareholdingProvider) -> None:
        pattern = await provider.get_shareholding_pattern("RELIANCE", "NSE", "Q1FY2025")
        assert isinstance(pattern, ShareholdingPattern)
        assert len(pattern.categories) > 0
        total_pct = sum(c.percentage for c in pattern.categories)
        assert total_pct == Decimal("100.00")
        assert all(isinstance(c.percentage, Decimal) for c in pattern.categories)

    @pytest.mark.asyncio
    async def test_get_shareholding_not_found(self, provider: MockShareholdingProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_shareholding_pattern("FAKE", "NSE", "Q1FY2025")

    @pytest.mark.asyncio
    async def test_get_shareholding_history(self, provider: MockShareholdingProvider) -> None:
        history = await provider.get_shareholding_history("INFY", "NSE")
        assert len(history) >= 1
        assert all(isinstance(p, ShareholdingPattern) for p in history)

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockShareholdingProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# CorporateActionsProvider
# ---------------------------------------------------------------------------


class TestCorporateActionsProviderContract:
    @pytest.fixture
    def provider(self) -> MockCorporateActionsProvider:
        return MockCorporateActionsProvider()

    def test_isinstance_check(self, provider: MockCorporateActionsProvider) -> None:
        assert isinstance(provider, CorporateActionsProvider)

    @pytest.mark.asyncio
    async def test_get_corporate_actions(self, provider: MockCorporateActionsProvider) -> None:
        actions = await provider.get_corporate_actions("RELIANCE", "NSE")
        assert len(actions) >= 1
        assert all(isinstance(a, CorporateActionRecord) for a in actions)
        assert actions[0].action_type == "DIVIDEND"
        assert isinstance(actions[0].value, Decimal)

    @pytest.mark.asyncio
    async def test_get_corporate_actions_not_found(self, provider: MockCorporateActionsProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_corporate_actions("FAKE", "NSE")

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockCorporateActionsProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# NewsProvider
# ---------------------------------------------------------------------------


class TestNewsProviderContract:
    @pytest.fixture
    def provider(self) -> MockNewsProvider:
        return MockNewsProvider()

    def test_isinstance_check(self, provider: MockNewsProvider) -> None:
        assert isinstance(provider, NewsProvider)

    @pytest.mark.asyncio
    async def test_search_news(self, provider: MockNewsProvider) -> None:
        articles = await provider.search_news("Reliance Industries")
        assert len(articles) >= 1
        assert all(isinstance(a, NewsArticle) for a in articles)

    @pytest.mark.asyncio
    async def test_get_company_news(self, provider: MockNewsProvider) -> None:
        articles = await provider.get_company_news("TCS", "NSE")
        assert len(articles) >= 1
        assert all(isinstance(a, NewsArticle) for a in articles)
        assert "TCS" in articles[0].symbols

    @pytest.mark.asyncio
    async def test_get_company_news_not_found(self, provider: MockNewsProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_company_news("FAKE", "NSE")

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockNewsProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# SearchProvider
# ---------------------------------------------------------------------------


class TestSearchProviderContract:
    @pytest.fixture
    def provider(self) -> MockSearchProvider:
        return MockSearchProvider()

    def test_isinstance_check(self, provider: MockSearchProvider) -> None:
        assert isinstance(provider, SearchProvider)

    @pytest.mark.asyncio
    async def test_search(self, provider: MockSearchProvider) -> None:
        results = await provider.search("Indian equity market")
        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)
        assert len(results[0].url) > 0

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockSearchProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# MacroDataProvider
# ---------------------------------------------------------------------------


class TestMacroDataProviderContract:
    @pytest.fixture
    def provider(self) -> MockMacroDataProvider:
        return MockMacroDataProvider()

    def test_isinstance_check(self, provider: MockMacroDataProvider) -> None:
        assert isinstance(provider, MacroDataProvider)

    @pytest.mark.asyncio
    async def test_get_indicator(self, provider: MockMacroDataProvider) -> None:
        series = await provider.get_indicator("REPO_RATE")
        assert isinstance(series, MacroSeries)
        assert len(series.data_points) > 0
        assert all(isinstance(dp.value, Decimal) for dp in series.data_points)

    @pytest.mark.asyncio
    async def test_get_indicator_not_found(self, provider: MockMacroDataProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_indicator("NONEXISTENT_INDICATOR")

    @pytest.mark.asyncio
    async def test_list_indicators(self, provider: MockMacroDataProvider) -> None:
        indicators = await provider.list_indicators()
        assert len(indicators) >= 1
        assert all(isinstance(i, MacroIndicatorInfo) for i in indicators)

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockMacroDataProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# TranscriptProvider
# ---------------------------------------------------------------------------


class TestTranscriptProviderContract:
    @pytest.fixture
    def provider(self) -> MockTranscriptProvider:
        return MockTranscriptProvider()

    def test_isinstance_check(self, provider: MockTranscriptProvider) -> None:
        assert isinstance(provider, TranscriptProvider)

    @pytest.mark.asyncio
    async def test_get_transcript(self, provider: MockTranscriptProvider) -> None:
        transcript = await provider.get_transcript("RELIANCE", "NSE", "Q1", 2025)
        assert isinstance(transcript, Transcript)
        assert len(transcript.segments) > 0
        assert transcript.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_transcript_not_found(self, provider: MockTranscriptProvider) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_transcript("FAKE", "NSE", "Q1", 2025)

    @pytest.mark.asyncio
    async def test_list_transcripts(self, provider: MockTranscriptProvider) -> None:
        summaries = await provider.list_transcripts("INFY", "NSE")
        assert len(summaries) >= 1
        assert all(isinstance(s, TranscriptSummary) for s in summaries)

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockTranscriptProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# LLMProvider
# ---------------------------------------------------------------------------


class TestLLMProviderContract:
    @pytest.fixture
    def provider(self) -> MockLLMProvider:
        return MockLLMProvider()

    def test_isinstance_check(self, provider: MockLLMProvider) -> None:
        assert isinstance(provider, LLMProvider)

    @pytest.mark.asyncio
    async def test_generate(self, provider: MockLLMProvider) -> None:
        response = await provider.generate("What is the PE ratio of Reliance?")
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
        assert response.usage.total_tokens > 0
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_generate_with_model(self, provider: MockLLMProvider) -> None:
        response = await provider.generate("test", model="custom-model")
        assert response.model == "custom-model"

    @pytest.mark.asyncio
    async def test_generate_tracks_cost(self, provider: MockLLMProvider) -> None:
        response = await provider.generate("test prompt")
        assert response.cost_usd is not None
        assert isinstance(response.cost_usd, Decimal)

    @pytest.mark.asyncio
    async def test_chat(self, provider: MockLLMProvider) -> None:
        messages = [
            ChatMessage(role="user", content="Analyze Infosys stock"),
        ]
        response = await provider.chat(messages)
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
        assert response.usage.input_tokens > 0

    @pytest.mark.asyncio
    async def test_chat_multi_turn(self, provider: MockLLMProvider) -> None:
        messages = [
            ChatMessage(role="user", content="What is TCS?"),
            ChatMessage(role="assistant", content="TCS is Tata Consultancy Services."),
            ChatMessage(role="user", content="What is its market cap?"),
        ]
        response = await provider.chat(messages)
        assert isinstance(response, LLMResponse)

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockLLMProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True


# ---------------------------------------------------------------------------
# EmbeddingProvider
# ---------------------------------------------------------------------------


class TestEmbeddingProviderContract:
    @pytest.fixture
    def provider(self) -> MockEmbeddingProvider:
        return MockEmbeddingProvider(dimensions=384)

    def test_isinstance_check(self, provider: MockEmbeddingProvider) -> None:
        assert isinstance(provider, EmbeddingProvider)

    @pytest.mark.asyncio
    async def test_embed(self, provider: MockEmbeddingProvider) -> None:
        result = await provider.embed(["hello world", "financial analysis"])
        assert isinstance(result, EmbeddingResult)
        assert len(result.embeddings) == 2
        assert len(result.embeddings[0]) == 384
        assert all(isinstance(v, float) for v in result.embeddings[0])

    @pytest.mark.asyncio
    async def test_embed_single(self, provider: MockEmbeddingProvider) -> None:
        vector = await provider.embed_single("test text")
        assert isinstance(vector, list)
        assert len(vector) == 384

    @pytest.mark.asyncio
    async def test_embed_deterministic(self, provider: MockEmbeddingProvider) -> None:
        v1 = await provider.embed_single("same input")
        v2 = await provider.embed_single("same input")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_different_inputs_differ(self, provider: MockEmbeddingProvider) -> None:
        v1 = await provider.embed_single("input A")
        v2 = await provider.embed_single("input B")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_embed_tracks_usage(self, provider: MockEmbeddingProvider) -> None:
        result = await provider.embed(["some text"])
        assert result.usage.total_tokens > 0

    @pytest.mark.asyncio
    async def test_health_check(self, provider: MockEmbeddingProvider) -> None:
        health = await provider.check_health()
        assert isinstance(health, ProviderHealth)
        assert health.is_healthy is True
