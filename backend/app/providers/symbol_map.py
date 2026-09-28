"""Indian stock symbol resolution across exchanges and data providers.

Maps NSE symbols to the vendor-specific format each provider needs.
The development dataset covers 6 large-cap companies.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyIdentifiers:
    nse_symbol: str
    bse_code: str
    isin: str
    name: str


DEVELOPMENT_COMPANIES: dict[str, CompanyIdentifiers] = {
    "RELIANCE": CompanyIdentifiers(
        nse_symbol="RELIANCE", bse_code="500325",
        isin="INE002A01018", name="Reliance Industries Ltd",
    ),
    "TCS": CompanyIdentifiers(
        nse_symbol="TCS", bse_code="532540",
        isin="INE467B01029", name="Tata Consultancy Services Ltd",
    ),
    "INFY": CompanyIdentifiers(
        nse_symbol="INFY", bse_code="500209",
        isin="INE009A01021", name="Infosys Ltd",
    ),
    "HDFCBANK": CompanyIdentifiers(
        nse_symbol="HDFCBANK", bse_code="500180",
        isin="INE040A01034", name="HDFC Bank Ltd",
    ),
    "ICICIBANK": CompanyIdentifiers(
        nse_symbol="ICICIBANK", bse_code="532174",
        isin="INE090A01021", name="ICICI Bank Ltd",
    ),
    "BHARTIARTL": CompanyIdentifiers(
        nse_symbol="BHARTIARTL", bse_code="532454",
        isin="INE397D01024", name="Bharti Airtel Ltd",
    ),
}

_BSE_CODE_TO_NSE: dict[str, str] = {
    ids.bse_code: nse for nse, ids in DEVELOPMENT_COMPANIES.items()
}

_ISIN_TO_NSE: dict[str, str] = {
    ids.isin: nse for nse, ids in DEVELOPMENT_COMPANIES.items()
}


def nse_to_yahoo(symbol: str) -> str:
    return f"{symbol}.NS"


def bse_to_yahoo(bse_code: str) -> str:
    return f"{bse_code}.BO"


def nse_to_alpha_vantage(symbol: str) -> str:
    return f"{symbol}.BSE"


def resolve_nse_symbol(identifier: str) -> str | None:
    """Resolve a BSE code, ISIN, or NSE symbol to the canonical NSE symbol."""
    if identifier in DEVELOPMENT_COMPANIES:
        return identifier
    if identifier in _BSE_CODE_TO_NSE:
        return _BSE_CODE_TO_NSE[identifier]
    if identifier in _ISIN_TO_NSE:
        return _ISIN_TO_NSE[identifier]
    return None


def get_identifiers(nse_symbol: str) -> CompanyIdentifiers | None:
    return DEVELOPMENT_COMPANIES.get(nse_symbol)
