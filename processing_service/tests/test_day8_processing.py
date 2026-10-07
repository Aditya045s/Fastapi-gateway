import asyncio
import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv


# =========================================================
# Environment
# =========================================================

PROCESSING_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(
    PROCESSING_ROOT / ".env"
)

PROCESSING_TEST_URL = os.getenv(
    "PROCESSING_TEST_URL",
    "http://127.0.0.1:8001",
)

PROCESSING_SERVICE_TOKEN = os.getenv(
    "PROCESSING_SERVICE_TOKEN",
    "change_me_internal_token",
)


# =========================================================
# Import application
# =========================================================

sys.path.insert(
    0,
    str(PROCESSING_ROOT),
)

from app.main import app
from app.workers import tasks


# =========================================================
# Helpers
# =========================================================

def service_headers(
    token: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:

    headers = {
        "Authorization": (
            f"Bearer {token or PROCESSING_SERVICE_TOKEN}"
        ),
    }

    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    return headers


def job_payload(
    name: str = "Processing integration job",
) -> dict:

    return {
        "name": name,
        "data": {
            "source": "processing-pytest",
        },
    }


def idempotency_key() -> str:
    return f"processing-test-{uuid.uuid4()}"


@pytest_asyncio.fixture
async def client():

    async with httpx.AsyncClient(
        base_url=PROCESSING_TEST_URL,
        timeout=10,
    ) as client:

        yield client


@pytest_asyncio.fixture
async def asgi_client():

    transport = httpx.ASGITransport(
        app=app,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=10,
    ) as client:

        yield client


# =========================================================
# 1. Processing Service receives internal request
# =========================================================

@pytest.mark.asyncio
async def test_internal_job_creation(client):

    response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(),
        headers={
            **service_headers(),
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert "job_id" in body
    assert body["name"] == (
        "Processing integration job"
    )

    assert body["status"] in {
        "CREATED",
        "QUEUED",
        "PROCESSING",
        "COMPLETED",
    }


# =========================================================
# 2. Invalid internal credential -> 401
# =========================================================

@pytest.mark.asyncio
async def test_invalid_internal_credential(client):

    response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(),
        headers={
            "Authorization": "Bearer invalid-token",
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert response.status_code == 401


# =========================================================
# 3. Missing internal credential -> 401
# =========================================================

@pytest.mark.asyncio
async def test_missing_internal_credential(client):

    response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(),
        headers={
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert response.status_code == 401


# =========================================================
# 4. Correlation ID reaches Processing Service
# =========================================================

@pytest.mark.asyncio
async def test_correlation_id(client):

    correlation_id = (
        f"processing-corr-{uuid.uuid4()}"
    )

    response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(
            "Correlation ID test"
        ),
        headers={
            **service_headers(
                correlation_id=correlation_id,
            ),
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert response.status_code == 200

    assert response.headers[
        "X-Correlation-ID"
    ] == correlation_id


# =========================================================
# 5. Processing Service creates DB record
# =========================================================

@pytest.mark.asyncio
async def test_job_is_persisted(client):

    create_response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(
            "Persistence test"
        ),
        headers={
            **service_headers(),
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert create_response.status_code == 200

    job_id = create_response.json()["job_id"]

    # Read the same job back from the Processing
    # Service. This verifies persistence through its API.
    get_response = await client.get(
        f"/internal/v1/jobs/{job_id}",
        headers=service_headers(),
    )

    assert get_response.status_code == 200

    body = get_response.json()

    assert body["job_id"] == job_id
    assert body["name"] == "Persistence test"


# =========================================================
# 6. Job not found -> 404
# =========================================================

@pytest.mark.asyncio
async def test_job_not_found(client):

    missing_job_id = uuid.uuid4()

    response = await client.get(
        f"/internal/v1/jobs/{missing_job_id}",
        headers=service_headers(),
    )

    assert response.status_code == 404


# =========================================================
# 7. ARQ worker changes job to COMPLETED
# =========================================================

@pytest.mark.asyncio
async def test_arq_worker_completes_job(client):

    create_response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(
            "Worker completion test"
        ),
        headers={
            **service_headers(),
            "Idempotency-Key": idempotency_key(),
        },
    )

    assert create_response.status_code == 200

    job_id = create_response.json()["job_id"]

    final_status = None

    for _ in range(20):

        await asyncio.sleep(0.5)

        response = await client.get(
            f"/internal/v1/jobs/{job_id}",
            headers=service_headers(),
        )

        assert response.status_code == 200

        final_status = response.json()["status"]

        if final_status == "COMPLETED":
            break

    assert final_status == "COMPLETED"


# =========================================================
# 8. Failed worker changes job to FAILED
# =========================================================

@pytest.mark.asyncio
async def test_worker_failure_changes_status_to_failed(
    monkeypatch,
):

    class FakeJob:

        def __init__(self):
            self.id = uuid.uuid4()
            self.name = "Forced failure"
            self._status = "QUEUED"

        @property
        def status(self):
            return self._status

        @status.setter
        def status(self, value):

            # Force failure when worker tries to
            # mark the job as completed.
            if value == "COMPLETED":
                raise RuntimeError(
                    "Forced worker failure"
                )

            self._status = value


    class FakeResult:

        def __init__(self, job):
            self.job = job

        def scalar_one_or_none(self):
            return self.job


    class FakeSession:

        def __init__(self, job):
            self.job = job
            self.commits = 0

        async def execute(self, query):
            return FakeResult(self.job)

        async def commit(self):
            self.commits += 1

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False


    fake_job = FakeJob()
    fake_session = FakeSession(fake_job)

    monkeypatch.setattr(
        tasks,
        "AsyncSessionLocal",
        lambda: fake_session,
    )

    with pytest.raises(
        RuntimeError,
        match="Forced worker failure",
    ):
        await tasks.process_job(
            {},
            str(fake_job.id),
        )

    assert fake_job.status == "FAILED"
    assert fake_session.commits >= 2


# =========================================================
# 9. Same idempotency key + same payload
#    returns same job
# =========================================================

@pytest.mark.asyncio
async def test_same_idempotency_key_same_payload(
    client,
):

    key = idempotency_key()

    payload = job_payload(
        "Idempotency replay test"
    )

    first_response = await client.post(
        "/internal/v1/jobs",
        json=payload,
        headers={
            **service_headers(),
            "Idempotency-Key": key,
        },
    )

    second_response = await client.post(
        "/internal/v1/jobs",
        json=payload,
        headers={
            **service_headers(),
            "Idempotency-Key": key,
        },
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
#     -> 409
# =========================================================

@pytest.mark.asyncio
async def test_same_idempotency_key_different_payload(
    client,
):

    key = idempotency_key()

    first_response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(
            "Original job"
        ),
        headers={
            **service_headers(),
            "Idempotency-Key": key,
        },
    )

    assert first_response.status_code == 200

    second_response = await client.post(
        "/internal/v1/jobs",
        json=job_payload(
            "Different job"
        ),
        headers={
            **service_headers(),
            "Idempotency-Key": key,
        },
    )

    assert second_response.status_code == 409

    body = second_response.json()

    assert body["detail"]["code"] == (
        "IDEMPOTENCY_CONFLICT"
    )


# =========================================================
# 11. Health endpoint
# =========================================================

@pytest.mark.asyncio
async def test_health(client):

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
async def test_readiness(client):

    response = await client.get(
        "/ready"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"


# =========================================================
# 13. Readiness fails when database unavailable
# =========================================================

@pytest.mark.asyncio
async def test_readiness_fails_when_database_unavailable(
    asgi_client,
    monkeypatch,
):

    class FailingDatabase:

        async def __aenter__(self):
            raise RuntimeError(
                "Database unavailable"
            )

        async def __aexit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False


    monkeypatch.setattr(
        "app.main.AsyncSessionLocal",
        lambda: FailingDatabase(),
    )

    response = await asgi_client.get(
        "/ready"
    )

    assert response.status_code == 503

    body = response.json()

    assert body["detail"]["code"] == (
        "DATABASE_NOT_READY"
    )


# =========================================================
# 14. Readiness fails when Redis unavailable
# =========================================================

@pytest.mark.asyncio
async def test_readiness_fails_when_redis_unavailable(
    asgi_client,
    monkeypatch,
):

    class FakeDatabase:

        async def __aenter__(self):
            return self

        async def __aexit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        async def execute(self, query):
            return None


    class FailingRedis:

        async def ping(self):
            raise RuntimeError(
                "Redis unavailable"
            )

        async def close(self):
            pass


    async def failing_create_pool(*args, **kwargs):
        return FailingRedis()


    monkeypatch.setattr(
        "app.main.AsyncSessionLocal",
        lambda: FakeDatabase(),
    )

    monkeypatch.setattr(
        "app.main.create_pool",
        failing_create_pool,
    )

    response = await asgi_client.get(
        "/ready"
    )

    assert response.status_code == 503

    body = response.json()

    assert body["detail"]["code"] == (
        "REDIS_NOT_READY"
    )