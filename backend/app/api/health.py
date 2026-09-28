import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """Check backend, database, and Redis connectivity."""
    db_ok = False
    redis_ok = False

    try:
        engine = request.app.state.db_engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.warning("Database health check failed", exc_info=True)

    try:
        redis_client = request.app.state.redis
        await redis_client.ping()
        redis_ok = True
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)

    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "unhealthy",
            "database": "connected" if db_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
        },
    )


@router.get("/health/ready")
async def readiness_check(request: Request) -> JSONResponse:
    """Check that database is reachable and migrations are current."""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory

        alembic_ini = BACKEND_DIR / "alembic.ini"
        if not alembic_ini.exists():
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "alembic_config_missing"},
            )

        cfg = AlembicConfig(str(alembic_ini))
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
    except Exception:
        logger.warning("Could not determine Alembic head revision", exc_info=True)
        head = None

    try:
        engine = request.app.state.db_engine
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current: str | None = result.scalar_one_or_none()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database_unavailable"},
        )

    if current is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "no_migrations_applied"},
        )

    if head is not None and current != head:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "reason": "pending_migrations",
                "current": current,
                "head": head,
            },
        )

    return JSONResponse(content={"status": "ready", "migration": current})
