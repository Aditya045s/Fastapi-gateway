import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


SERVICE_NAME = "gateway-service"


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "event": getattr(
                record,
                "event",
                record.getMessage(),
            ),
            "request_id": getattr(
                record,
                "request_id",
                None,
            ),
            "correlation_id": getattr(
                record,
                "correlation_id",
                None,
            ),
            "job_id": getattr(
                record,
                "job_id",
                None,
            ),
            "duration_ms": getattr(
                record,
                "duration_ms",
                None,
            ),
            "status": getattr(
                record,
                "status",
                None,
            ),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(log_data, default=str)


def configure_logging() -> None:
    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger.addHandler(handler)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    duration_ms: float | None = None,
    status: int | str | None = None,
    level: int = logging.INFO,
    **_: Any,
) -> None:
    logger.log(
        level,
        event,
        extra={
            "event": event,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "job_id": job_id,
            "duration_ms": (
                round(duration_ms, 2)
                if duration_ms is not None
                else None
            ),
            "status": status,
        },
    )