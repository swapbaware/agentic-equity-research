import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application error with structured error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details: dict[str, object] = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict[str, object] | None = None) -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed", details: dict[str, object] | None = None) -> None:
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service unavailable", details: dict[str, object] | None = None) -> None:
        super().__init__(code="SERVICE_UNAVAILABLE", message=message, status_code=503, details=details)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError exceptions to consistent JSON error responses."""
    logger.error("Application error: %s (code=%s, status=%d)", exc.message, exc.code, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions. Never leaks internals."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            }
        },
    )
