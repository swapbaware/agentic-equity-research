import logging
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import request_id_ctx

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID, catches unhandled exceptions, and logs requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request_id_ctx.set(request_id)

        start_time = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception during %s %s", request.method, request.url.path)
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "details": {},
                    }
                },
            )

        duration_ms = (time.monotonic() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response
