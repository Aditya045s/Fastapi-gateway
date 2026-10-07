import logging
import time
import uuid
from opentelemetry import trace

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import log_event

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        start_time = time.perf_counter()

        correlation_id = request.headers.get(
            "X-Correlation-ID"
        )

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        request_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        request.state.request_id = request_id

        span = trace.get_current_span()

        if span.is_recording():
            span.set_attribute(
                "app.request_id",
                request_id,
            )
            span.set_attribute(
                "app.correlation_id",
                correlation_id,
            )

        try:
            response = await call_next(request)

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "request_completed",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                status=response.status_code,
            )

            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "request_failed",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                status=500,
                level=logging.ERROR,
            )

            raise