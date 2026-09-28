from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_healthy_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["redis"] == "connected"

    def test_database_down_returns_503(self, client: TestClient, app: MagicMock) -> None:
        engine = MagicMock()
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("DB unreachable"))
        async_cm.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=async_cm)
        app.state.db_engine = engine

        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert data["redis"] == "connected"

    def test_redis_down_returns_503(self, client: TestClient, app: MagicMock) -> None:
        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=ConnectionError("Redis unreachable"))
        app.state.redis = redis

        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "connected"
        assert data["redis"] == "disconnected"

    def test_both_down_returns_503(self, client: TestClient, app: MagicMock) -> None:
        engine = MagicMock()
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("DB unreachable"))
        async_cm.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=async_cm)
        app.state.db_engine = engine

        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=ConnectionError("Redis unreachable"))
        app.state.redis = redis

        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert data["redis"] == "disconnected"

    def test_health_includes_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36  # UUID format


class TestReadinessEndpoint:
    def test_ready_returns_200(self, client: TestClient) -> None:
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["migration"] == "001"

    def test_no_migrations_returns_503(self, client: TestClient, app: MagicMock) -> None:
        engine = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        async_cm.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=async_cm)
        app.state.db_engine = engine

        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["reason"] == "no_migrations_applied"

    def test_db_unavailable_returns_503(self, client: TestClient, app: MagicMock) -> None:
        engine = MagicMock()
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("DB unreachable"))
        async_cm.__aexit__ = AsyncMock(return_value=False)
        engine.connect = MagicMock(return_value=async_cm)
        app.state.db_engine = engine

        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["reason"] == "database_unavailable"
