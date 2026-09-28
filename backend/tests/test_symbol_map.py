"""Tests for Indian stock symbol resolution."""
from __future__ import annotations

from app.providers.symbol_map import (
    DEVELOPMENT_COMPANIES,
    get_identifiers,
    nse_to_alpha_vantage,
    nse_to_yahoo,
    resolve_nse_symbol,
)


class TestDevelopmentDataset:
    def test_has_six_companies(self) -> None:
        assert len(DEVELOPMENT_COMPANIES) == 6

    def test_all_companies_have_required_fields(self) -> None:
        for sym, ids in DEVELOPMENT_COMPANIES.items():
            assert ids.nse_symbol == sym
            assert ids.bse_code
            assert ids.isin.startswith("INE")
            assert ids.name


class TestNseToYahoo:
    def test_reliance(self) -> None:
        assert nse_to_yahoo("RELIANCE") == "RELIANCE.NS"

    def test_tcs(self) -> None:
        assert nse_to_yahoo("TCS") == "TCS.NS"

    def test_hdfcbank(self) -> None:
        assert nse_to_yahoo("HDFCBANK") == "HDFCBANK.NS"


class TestNseToAlphaVantage:
    def test_reliance(self) -> None:
        assert nse_to_alpha_vantage("RELIANCE") == "RELIANCE.BSE"

    def test_infy(self) -> None:
        assert nse_to_alpha_vantage("INFY") == "INFY.BSE"


class TestResolveNseSymbol:
    def test_from_nse_symbol(self) -> None:
        assert resolve_nse_symbol("RELIANCE") == "RELIANCE"

    def test_from_bse_code(self) -> None:
        assert resolve_nse_symbol("500325") == "RELIANCE"

    def test_from_isin(self) -> None:
        assert resolve_nse_symbol("INE002A01018") == "RELIANCE"

    def test_unknown_returns_none(self) -> None:
        assert resolve_nse_symbol("UNKNOWN") is None

    def test_all_dev_companies_resolvable_by_bse(self) -> None:
        for _sym, ids in DEVELOPMENT_COMPANIES.items():
            assert resolve_nse_symbol(ids.bse_code) == ids.nse_symbol

    def test_all_dev_companies_resolvable_by_isin(self) -> None:
        for _sym, ids in DEVELOPMENT_COMPANIES.items():
            assert resolve_nse_symbol(ids.isin) == ids.nse_symbol


class TestGetIdentifiers:
    def test_known_symbol(self) -> None:
        ids = get_identifiers("RELIANCE")
        assert ids is not None
        assert ids.bse_code == "500325"
        assert ids.isin == "INE002A01018"

    def test_unknown_symbol(self) -> None:
        assert get_identifiers("UNKNOWN") is None
