import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.api.v1.evidence import router as evidence_router
from app.config import Settings
from app.database import create_engine
from app.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.logging_config import setup_logging
from app.middleware import RequestIdMiddleware
from app.redis_client import create_redis
from app.screener.router import router as screener_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory."""
    if settings is None:
        settings = Settings()

    setup_logging(settings.app_log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting Agentic Equity Research backend v%s (env=%s)", __version__, settings.app_env)

        _app.state.db_engine = create_engine(settings)
        _app.state.redis = create_redis(settings)
        _app.state.settings = settings

        logger.info("Database and Redis connections established")
        yield

        await _app.state.db_engine.dispose()
        await _app.state.redis.aclose()
        logger.info("Connections closed, shutting down")

    app = FastAPI(
        title="Agentic Equity Research",
        description="Evidence-driven equity research for Indian listed companies (NSE/BSE)",
        version=__version__,
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]  # FastAPI accepts Exception subclass handlers
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health_router)
    app.include_router(evidence_router, prefix=settings.api_v1_prefix)
    app.include_router(screener_router, prefix=settings.api_v1_prefix)

    return app
