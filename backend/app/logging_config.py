import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "service": "backend",
            "logger": record.name,
            "message": record.getMessage(),
        }

        trace_id = request_id_ctx.get("")
        if trace_id:
            log_entry["trace_id"] = trace_id

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class RequestIdFilter(logging.Filter):
    """Injects the current request ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = request_id_ctx.get("")  # noqa: B010  # dynamically added for JSON formatter
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
