from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import router as health_router
from app.config import Settings
from app.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.middleware import RequestIdMiddleware


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        app_debug=False,
        app_log_level="WARNING",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test_db",
        redis_url="redis://localhost:6379/1",
    )


@pytest.fixture()
def mock_db_engine() -> MagicMock:
    engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="001")))

    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    async_cm.__aexit__ = AsyncMock(return_value=False)
    engine.connect = MagicMock(return_value=async_cm)

    return engine


@pytest.fixture()
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture()
def app(test_settings: Settings, mock_db_engine: MagicMock, mock_redis: AsyncMock) -> FastAPI:
    """Create a test app with mocked infrastructure."""
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)
    test_app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    test_app.add_exception_handler(Exception, unhandled_error_handler)
    test_app.include_router(health_router)
    test_app.state.settings = test_settings
    test_app.state.db_engine = mock_db_engine
    test_app.state.redis = mock_redis
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
