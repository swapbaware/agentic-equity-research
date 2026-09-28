from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    app_debug: bool = False
    app_log_level: str = "INFO"
    app_secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/equity_research"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_v1_prefix: str = "/api/v1"

    @field_validator("database_url")
    @classmethod
    def ensure_async_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic offline mode."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
