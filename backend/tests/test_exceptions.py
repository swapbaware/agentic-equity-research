from fastapi.testclient import TestClient

from app.exceptions import AppError, NotFoundError, ValidationError


class TestErrorHandler:
    def test_app_error_returns_structured_response(self, client: TestClient, app: object) -> None:
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

        @app.get("/test-error")
        async def raise_error() -> None:
            raise AppError(code="TEST_ERROR", message="Something went wrong", status_code=400)

        response = client.get("/test-error")
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "TEST_ERROR"
        assert data["error"]["message"] == "Something went wrong"

    def test_not_found_error(self, client: TestClient, app: object) -> None:
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

        @app.get("/test-not-found")
        async def raise_not_found() -> None:
            raise NotFoundError(message="Company not found")

        response = client.get("/test-not-found")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_validation_error(self, client: TestClient, app: object) -> None:
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

        @app.get("/test-validation")
        async def raise_validation() -> None:
            raise ValidationError(message="Invalid input", details={"field": "name"})

        response = client.get("/test-validation")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.json()["error"]["details"]["field"] == "name"

    def test_unhandled_error_returns_500(self, client: TestClient, app: object) -> None:
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

        @app.get("/test-unhandled")
        async def raise_unhandled() -> None:
            raise RuntimeError("Unexpected failure")

        response = client.get("/test-unhandled")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "Unexpected failure" not in response.json()["error"]["message"]
