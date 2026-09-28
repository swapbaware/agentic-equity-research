"""Tests for BSE filing provider with mocked httpx responses."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.bse import BSEProvider
from app.providers.errors import ProviderNotFoundError
from app.providers.interfaces import CorporateFilingsProvider
from app.providers.rate_limiter import NullRateLimiter

# ---------------------------------------------------------------------------
# Mock BSE API responses
# ---------------------------------------------------------------------------

_BSE_ANNOUNCEMENTS = [
    {
        "NEWSID": "12345",
        "NEWSSUB": "Board Meeting Outcome - Financial Results",
        "NEWS_DT": "2024-07-20T00:00:00",
        "CATEGORYNAME": "Board Meeting",
        "ATTACHMENTNAME": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/12345.pdf",
    },
    {
        "NEWSID": "12346",
        "NEWSSUB": "Annual Report FY2024",
        "NEWS_DT": "2024-06-15T00:00:00",
        "CATEGORYNAME": "Annual Report",
        "ATTACHMENTNAME": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/12346.pdf",
    },
    {
        "NEWSID": "12347",
        "NEWSSUB": "Shareholding Pattern Q1 FY2025",
        "NEWS_DT": "2024-07-14T00:00:00",
        "CATEGORYNAME": "Shareholding Pattern",
        "ATTACHMENTNAME": None,
    },
]


# ---------------------------------------------------------------------------
# Provider fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> BSEProvider:
    return BSEProvider(rate_limiter=NullRateLimiter())


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_is_corporate_filings_provider(self, provider: BSEProvider) -> None:
        assert isinstance(provider, CorporateFilingsProvider)


# ---------------------------------------------------------------------------
# get_filings
# ---------------------------------------------------------------------------


class TestGetFilings:
    @pytest.mark.asyncio
    async def test_returns_filings_for_known_company(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, return_value=_BSE_ANNOUNCEMENTS
        ):
            filings = await provider.get_filings("RELIANCE", "BSE")

        assert len(filings) == 3
        for f in filings:
            assert f.symbol == "RELIANCE"
            assert f.exchange == "BSE"
            assert f.filing_id.startswith("BSE-500325-")
            assert f.provenance is not None
            assert f.provenance.source == "BSE India"
            assert f.provenance.data_quality.value == "AUTHORITATIVE"

    @pytest.mark.asyncio
    async def test_filters_by_filing_type(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, return_value=_BSE_ANNOUNCEMENTS
        ):
            filings = await provider.get_filings(
                "RELIANCE", "BSE", filing_type="Annual Report"
            )

        assert len(filings) == 1
        assert "Annual Report" in filings[0].filing_type

    @pytest.mark.asyncio
    async def test_raises_not_found_for_unknown_symbol(
        self, provider: BSEProvider
    ) -> None:
        with pytest.raises(ProviderNotFoundError):
            await provider.get_filings("UNKNOWN_COMPANY", "BSE")

    @pytest.mark.asyncio
    async def test_returns_empty_for_non_list_response(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, return_value={"error": "no data"}
        ):
            filings = await provider.get_filings("RELIANCE", "BSE")

        assert filings == []

    @pytest.mark.asyncio
    async def test_filing_has_url_when_available(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, return_value=_BSE_ANNOUNCEMENTS
        ):
            filings = await provider.get_filings("RELIANCE", "BSE")

        filing_with_url = filings[0]
        assert filing_with_url.url is not None
        assert "bseindia.com" in filing_with_url.url

        filing_without_url = filings[2]
        assert filing_without_url.url is None


# ---------------------------------------------------------------------------
# get_filing_document
# ---------------------------------------------------------------------------


class TestGetFilingDocument:
    @pytest.mark.asyncio
    async def test_raises_not_found_with_guidance(
        self, provider: BSEProvider
    ) -> None:
        with pytest.raises(ProviderNotFoundError, match="Use the filing URL"):
            await provider.get_filing_document("BSE-500325-12345")

    @pytest.mark.asyncio
    async def test_raises_for_invalid_id_format(
        self, provider: BSEProvider
    ) -> None:
        with pytest.raises(ProviderNotFoundError, match="Invalid BSE filing ID"):
            await provider.get_filing_document("bad-id")


# ---------------------------------------------------------------------------
# NSE provider (metadata-only)
# ---------------------------------------------------------------------------

from app.providers.nse import NSEProvider  # noqa: E402


class TestNSEProvider:
    @pytest.fixture
    def nse_provider(self) -> NSEProvider:
        return NSEProvider(rate_limiter=NullRateLimiter())

    def test_is_corporate_filings_provider(self, nse_provider: NSEProvider) -> None:
        assert isinstance(nse_provider, CorporateFilingsProvider)

    @pytest.mark.asyncio
    async def test_get_filings_raises_not_found_with_explanation(
        self, nse_provider: NSEProvider
    ) -> None:
        with pytest.raises(ProviderNotFoundError, match="restricts automated access"):
            await nse_provider.get_filings("RELIANCE", "NSE")

    @pytest.mark.asyncio
    async def test_health_check_reports_metadata_only(
        self, nse_provider: NSEProvider
    ) -> None:
        health = await nse_provider.check_health()
        assert health.is_healthy is True
        assert "metadata-only" in str(health.message)


# ---------------------------------------------------------------------------
# BSE health check
# ---------------------------------------------------------------------------


class TestBSEHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_api_returns_list(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, return_value=[]
        ):
            health = await provider.check_health()
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(
        self, provider: BSEProvider
    ) -> None:
        with patch.object(
            provider, "_bse_request", new_callable=AsyncMock, side_effect=RuntimeError("down")
        ):
            health = await provider.check_health()
        assert health.is_healthy is False
