import logging
import time
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.core.logging import log_event


logger = logging.getLogger(__name__)


class ProcessingClient:

    def __init__(
        self,
        base_url: str,
        timeout: float,
        service_token: str,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.service_token = service_token

    async def create_job(
        self,
        name: str,
        data: dict,
        correlation_id: str,
        request_id: str,
        idempotency_key: str,
    ):
        url = f"{self.base_url}/internal/v1/jobs"

        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "X-Correlation-ID": correlation_id,
            "Idempotency-Key": idempotency_key,
        }

        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    url,
                    json={
                        "name": name,
                        "data": data,
                    },
                    headers=headers,
                )

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            job_id = None

            try:
                job_id = response.json().get("job_id")
            except Exception:
                pass

            log_event(
                logger,
                "processing_service_response",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=job_id,
                duration_ms=duration_ms,
                status=response.status_code,
            )

        except httpx.TimeoutException:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "processing_service_timeout",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                status="TIMEOUT",
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=504,
                detail={
                    "code": "PROCESSING_SERVICE_TIMEOUT",
                    "message": "Processing service timed out",
                },
            )

        except httpx.ConnectError:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "processing_service_unavailable",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                status="UNAVAILABLE",
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=503,
                detail={
                    "code": "PROCESSING_SERVICE_UNAVAILABLE",
                    "message": "Processing service is unavailable",
                },
            )

        if response.status_code == 401:
            log_event(
                logger,
                "processing_service_unauthorized",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=401,
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=401,
                detail={
                    "code": "PROCESSING_SERVICE_UNAUTHORIZED",
                    "message": (
                        "Processing service rejected "
                        "the internal credential"
                    ),
                },
            )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": "Job was not found",
                },
            )

        if response.status_code == 409:
            log_event(
                logger,
                "idempotency_conflict",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=409,
                level=logging.WARNING,
            )

            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": (
                        "Idempotency key was already used "
                        "with a different request"
                    ),
                },
            )

        if response.status_code >= 500:
            log_event(
                logger,
                "processing_service_error",
                request_id=request_id,
                correlation_id=correlation_id,
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=response.status_code,
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PROCESSING_SERVICE_ERROR",
                    "message": "Processing service returned an error",
                },
            )

        response.raise_for_status()

        return response.json()

    async def get_job(
        self,
        job_id: UUID,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ):
        headers = {
            "Authorization": f"Bearer {self.service_token}",
        }

        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.get(
                    f"{self.base_url}/internal/v1/jobs/{job_id}",
                    headers=headers,
                )

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "processing_service_response",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=duration_ms,
                status=response.status_code,
            )

        except httpx.TimeoutException:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "processing_service_timeout",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=duration_ms,
                status="TIMEOUT",
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=504,
                detail={
                    "code": "PROCESSING_SERVICE_TIMEOUT",
                    "message": "Processing service timed out",
                },
            )

        except httpx.ConnectError:

            duration_ms = (
                time.perf_counter() - start_time
            ) * 1000

            log_event(
                logger,
                "processing_service_unavailable",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=duration_ms,
                status="UNAVAILABLE",
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=503,
                detail={
                    "code": "PROCESSING_SERVICE_UNAVAILABLE",
                    "message": "Processing service is unavailable",
                },
            )

        if response.status_code == 401:
            log_event(
                logger,
                "processing_service_unauthorized",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=401,
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=401,
                detail={
                    "code": "PROCESSING_SERVICE_UNAUTHORIZED",
                    "message": (
                        "Processing service rejected "
                        "the internal token"
                    ),
                },
            )

        if response.status_code == 404:
            log_event(
                logger,
                "job_not_found",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=404,
                level=logging.WARNING,
            )

            raise HTTPException(
                status_code=404,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": "Job not found",
                },
            )

        if response.status_code >= 500:
            log_event(
                logger,
                "processing_service_error",
                request_id=request_id,
                correlation_id=correlation_id,
                job_id=str(job_id),
                duration_ms=(
                    time.perf_counter() - start_time
                ) * 1000,
                status=response.status_code,
                level=logging.ERROR,
            )

            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PROCESSING_SERVICE_ERROR",
                    "message": "Processing service returned an error",
                },
            )

        response.raise_for_status()

        return response.json()