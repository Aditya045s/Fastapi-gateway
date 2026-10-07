import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.api.jobs import router as jobs_router
from app.core.errors import (
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.core.tracing import configure_tracing

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="Gateway Service")
configure_tracing(app)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    HTTPException,
    http_exception_handler,
)

app.add_middleware(RequestIDMiddleware)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    return {"status": "ready"}