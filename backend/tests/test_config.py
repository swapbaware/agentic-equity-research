import pytest

from app.config import Settings


class TestSettings:
    def test_default_values(self) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]  # prevent loading .env during tests
        )
        assert settings.app_env == "development"
        assert settings.app_debug is False
        assert settings.app_log_level == "INFO"
        assert settings.api_v1_prefix == "/api/v1"

    def test_database_url_async_conversion(self) -> None:
        settings = Settings(
            database_url="postgresql://user:pass@host:5432/db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_database_url_already_async(self) -> None:
        settings = Settings(
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_sync_url_property(self) -> None:
        settings = Settings(
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.database_url_sync == "postgresql://user:pass@host:5432/db"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_DEBUG", "false")
        monkeypatch.setenv("APP_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("DATABASE_URL", "postgresql://prod:secret@db:5432/prod_db")
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.app_env == "production"
        assert settings.app_debug is False
        assert settings.app_log_level == "ERROR"
        assert settings.database_url == "postgresql+asyncpg://prod:secret@db:5432/prod_db"
        assert settings.redis_url == "redis://redis:6379/0"


class TestLogging:
    def test_json_formatter_output(self) -> None:
        import json
        import logging

        from app.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["service"] == "backend"
        assert "timestamp" in parsed

    def test_json_formatter_includes_trace_id(self) -> None:
        import json
        import logging

        from app.logging_config import JSONFormatter, request_id_ctx

        token = request_id_ctx.set("test-trace-123")
        try:
            formatter = JSONFormatter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="Traced message",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["trace_id"] == "test-trace-123"
        finally:
            request_id_ctx.reset(token)
