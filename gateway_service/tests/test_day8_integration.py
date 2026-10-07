import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from jose import jwt


# ---------------------------------------------------------
# Load environment before importing the Gateway application
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(GATEWAY_ROOT / ".env", override=False)

# Processing Service is exposed to the host on port 8001.
PROCESSING_TEST_URL = os.getenv(
    "PROCESSING_TEST_URL",
    "http://127.0.0.1:8001",
)

PROCESSING_SERVICE_TOKEN = os.getenv(
    "PROCESSING_SERVICE_TOKEN",
    "change_me_internal_token",
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256",
)

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not configured"
    )


# ---------------------------------------------------------
# Import Gateway application
# ---------------------------------------------------------

sys.path.insert(0, str(GATEWAY_ROOT))

from app.main import app
from app.api.jobs import processing_client


# Force local integration tests to use the Processing
# Service exposed on localhost:8001.
processing_client.base_url = PROCESSING_TEST_URL


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def create_test_token() -> str:
    payload = {
        "sub": "integration-test-user",
        "exp": (
            datetime.now(timezone.utc)
            + timedelta(minutes=10)
        ),
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def auth_headers(
    *,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:

    headers = {
        "Authorization": (
            f"Bearer {create_test_token()}"
        ),
    }

    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    return headers


def job_payload(
    name: str = "Integration test job",
) -> dict:
    return {
        "name": name,
        "data": {
            "source": "pytest",
        },
    }


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=10,
    ) as client:
        yield client

# =========================================================
# 1. Gateway creates a job successfully
# =========================================================

@pytest.mark.asyncio
async def test_gateway_creates_job_successfully(client):

    idempotency_key = (
        f"test-create-{uuid.uuid4()}"
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert response.status_code == 200

    body = response.json()

    assert "job_id" in body
    assert body["name"] == "Integration test job"
    assert body["status"] in {
        "CREATED",
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
    }


# =========================================================
# 2. Processing Service receives internal request
# =========================================================

@pytest.mark.asyncio
async def test_processing_service_receives_internal_request(
    client,
    monkeypatch,
):

    captured = {}

    original_post = httpx.AsyncClient.post

    async def wrapped_post(
        self,
        *args,
        **kwargs,
    ):
        captured["headers"] = kwargs.get(
            "headers",
            {},
        )

        return await original_post(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        wrapped_post,
    )

    idempotency_key = (
        f"test-internal-{uuid.uuid4()}"
    )

    correlation_id = (
        f"corr-{uuid.uuid4()}"
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        ),
    )

    assert response.status_code == 200

    headers = captured["headers"]

    assert headers["Authorization"] == (
        f"Bearer {PROCESSING_SERVICE_TOKEN}"
    )


# =========================================================
# 3. Invalid internal credential fails with 401
# =========================================================

@pytest.mark.asyncio
async def test_invalid_internal_credential_fails(
    client,
    monkeypatch,
):

    monkeypatch.setattr(
        processing_client,
        "service_token",
        "invalid-internal-token",
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=(
                f"test-invalid-token-{uuid.uuid4()}"
            ),
        ),
    )

    assert response.status_code == 401

    body = response.json()

    assert body["error"]["code"] == (
        "PROCESSING_SERVICE_UNAUTHORIZED"
    )


# =========================================================
# 4. Correlation ID reaches downstream request
# =========================================================

@pytest.mark.asyncio
async def test_correlation_id_reaches_processing_service(
    client,
    monkeypatch,
):

    captured = {}

    original_post = httpx.AsyncClient.post

    async def wrapped_post(
        self,
        *args,
        **kwargs,
    ):
        captured["headers"] = kwargs.get(
            "headers",
            {},
        )

        return await original_post(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        wrapped_post,
    )

    correlation_id = (
        f"corr-{uuid.uuid4()}"
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=(
                f"test-correlation-{uuid.uuid4()}"
            ),
            correlation_id=correlation_id,
        ),
    )

    assert response.status_code == 200

    headers = captured["headers"]

    assert headers["X-Correlation-ID"] == (
        correlation_id
    )

    assert response.headers[
        "X-Correlation-ID"
    ] == correlation_id


# =========================================================
# 5. Gateway handles Processing Service timeout
# =========================================================

@pytest.mark.asyncio
async def test_processing_service_timeout(
    client,
    monkeypatch,
):
    original_post = httpx.AsyncClient.post

    async def raise_timeout(
        self,
        *args,
        **kwargs,
    ):
        # Only simulate timeout for the
        # Gateway -> Processing Service request.
        url = str(args[0]) if args else ""

        if "/internal/v1/jobs" in url:
            raise httpx.ReadTimeout(
                "Processing Service timed out"
            )

        # Allow the outer test client to call
        # the Gateway normally.
        return await original_post(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        raise_timeout,
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=(
                f"test-timeout-{uuid.uuid4()}"
            ),
        ),
    )

    assert response.status_code == 504

    body = response.json()

    assert body["error"]["code"] == (
        "PROCESSING_SERVICE_TIMEOUT"
    )


# =========================================================
# 6. Processing Service unavailable -> 503
# =========================================================

@pytest.mark.asyncio
async def test_processing_service_unavailable(
    client,
    monkeypatch,
):
    original_post = httpx.AsyncClient.post

    async def raise_connection_error(
        self,
        *args,
        **kwargs,
    ):
        # Only simulate failure for the
        # Gateway -> Processing Service request.
        url = str(args[0]) if args else ""

        if "/internal/v1/jobs" in url:
            raise httpx.ConnectError(
                "Processing Service unavailable"
            )

        # Allow the outer test client to call
        # the Gateway normally.
        return await original_post(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        raise_connection_error,
    )

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(
            idempotency_key=(
                f"test-unavailable-{uuid.uuid4()}"
            ),
        ),
    )

    assert response.status_code == 503

    body = response.json()

    assert body["error"]["code"] == (
        "PROCESSING_SERVICE_UNAVAILABLE"
    )


# =========================================================
# 7. Processing Service creates DB record
# =========================================================

@pytest.mark.asyncio
async def test_processing_service_creates_db_record(
    client,
):

    idempotency_key = (
        f"test-db-{uuid.uuid4()}"
    )

    create_response = await client.post(
        "/api/v1/jobs",
        json=job_payload(
            "Database integration test"
        ),
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert create_response.status_code == 200

    job_id = create_response.json()["job_id"]

    get_response = await client.get(
        f"/api/v1/jobs/{job_id}",
        headers=auth_headers(),
    )

    assert get_response.status_code == 200

    body = get_response.json()

    assert body["job_id"] == job_id
    assert body["name"] == (
        "Database integration test"
    )


# =========================================================
# 8. ARQ worker changes job status to COMPLETED
# =========================================================

@pytest.mark.asyncio
async def test_arq_worker_completes_job(client):

    idempotency_key = (
        f"test-worker-{uuid.uuid4()}"
    )

    create_response = await client.post(
        "/api/v1/jobs",
        json=job_payload(
            "Worker completion test"
        ),
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert create_response.status_code == 200

    job_id = create_response.json()["job_id"]

    final_status = None

    for _ in range(20):

        await asyncio.sleep(0.5)

        get_response = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers=auth_headers(),
        )

        assert get_response.status_code == 200

        final_status = get_response.json()["status"]

        if final_status == "COMPLETED":
            break

    assert final_status == "COMPLETED"


# =========================================================
# 9. Same idempotency key + same payload
#     returns same job
# =========================================================

@pytest.mark.asyncio
async def test_duplicate_idempotency_key_same_payload(
    client,
):

    idempotency_key = (
        f"test-duplicate-{uuid.uuid4()}"
    )

    payload = job_payload(
        "Idempotency replay test"
    )

    first_response = await client.post(
        "/api/v1/jobs",
        json=payload,
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    second_response = await client.post(
        "/api/v1/jobs",
        json=payload,
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_job = first_response.json()
    second_job = second_response.json()

    assert first_job["job_id"] == (
        second_job["job_id"]
    )


# =========================================================
# 10. Same idempotency key + different payload
#     returns 409
# =========================================================

@pytest.mark.asyncio
async def test_duplicate_idempotency_key_different_payload(
    client,
):

    idempotency_key = (
        f"test-conflict-{uuid.uuid4()}"
    )

    first_response = await client.post(
        "/api/v1/jobs",
        json=job_payload(
            "Original payload"
        ),
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert first_response.status_code == 200

    second_response = await client.post(
        "/api/v1/jobs",
        json=job_payload(
            "Different payload"
        ),
        headers=auth_headers(
            idempotency_key=idempotency_key,
        ),
    )

    assert second_response.status_code == 409

    body = second_response.json()

    assert body["error"]["code"] == (
        "IDEMPOTENCY_CONFLICT"
    )


# =========================================================
# 11. Health endpoint
# =========================================================

@pytest.mark.asyncio
async def test_health_endpoint(client):

    response = await client.get(
        "/health"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy"
    }


# =========================================================
# 12. Readiness endpoint
# =========================================================

@pytest.mark.asyncio
async def test_readiness_endpoint(client):

    response = await client.get(
        "/ready"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready"
    }


# =========================================================
# 13. Job not found -> 404
# =========================================================

@pytest.mark.asyncio
async def test_job_not_found(client):

    missing_job_id = uuid.uuid4()

    response = await client.get(
        f"/api/v1/jobs/{missing_job_id}",
        headers=auth_headers(),
    )

    assert response.status_code == 404

    body = response.json()

    assert body["error"]["code"] == (
        "JOB_NOT_FOUND"
    )


# =========================================================
# 14. Missing JWT -> 401
# =========================================================

@pytest.mark.asyncio
async def test_missing_jwt(client):

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers={
            "Idempotency-Key": (
                f"test-no-jwt-{uuid.uuid4()}"
            )
        },
    )

    assert response.status_code == 401

    body = response.json()

    assert body["error"]["code"] == (
        "UNAUTHORIZED"
    )


# =========================================================
# 15. Missing idempotency key -> 422
# =========================================================

@pytest.mark.asyncio
async def test_missing_idempotency_key(client):

    response = await client.post(
        "/api/v1/jobs",
        json=job_payload(),
        headers=auth_headers(),
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"]["code"] == (
        "VALIDATION_ERROR"
    )