"""Provider configuration loaded from environment variables."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderSettings(BaseSettings):
    """Environment-driven provider selection and credentials.

    Each PROVIDER setting selects the active implementation (e.g. "mock", "alpha_vantage").
    API keys and per-provider tuning are separate fields.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="PROVIDER_",
    )

    # Active provider selection (defaults to mock for safe local dev)
    market_data: str = "mock"
    financial_data: str = "mock"
    corporate_filings: str = "mock"
    shareholding: str = "mock"
    corporate_actions: str = "mock"
    news: str = "mock"
    search: str = "mock"
    macro_data: str = "mock"
    transcript: str = "mock"
    llm: str = "mock"
    embedding: str = "mock"

    # API keys (empty = not configured)
    alpha_vantage_api_key: str = ""
    polygon_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    serp_api_key: str = ""

    # Data reconciliation
    reconciliation_threshold_pct: float = 1.0

    # Defaults
    default_timeout: float = Field(default=30.0, ge=1.0)
    default_max_retries: int = Field(default=3, ge=0)
    rate_limit_requests: float = Field(default=100.0, ge=1.0)
    rate_limit_period: float = Field(default=60.0, ge=1.0)
