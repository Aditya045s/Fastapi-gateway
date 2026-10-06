from uuid import UUID

import httpx
from fastapi import HTTPException
from app.core.config import settings

class ProcessingClient:

    def __init__(
        self,
        base_url: str,
        timeout: float,
        service_token: str
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.service_token = service_token

    async def create_job(
        self,
        name: str,
        data: dict,
        correlation_id: str
    ):

        url = f"{self.base_url}/internal/v1/jobs"

        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "X-Correlation-ID": correlation_id
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    url,
                    json={
                        "name": name,
                        "data": data
                    },
                    headers=headers
                )

        except httpx.TimeoutException:

            raise HTTPException(
                status_code=504,
                detail={
                    "code": "PROCESSING_SERVICE_TIMEOUT",
                    "message": "Processing service timed out"
                }
            )

        except httpx.ConnectError:

            raise HTTPException(
                status_code=503,
                detail={
                    "code": "PROCESSING_SERVICE_UNAVAILABLE",
                    "message": "Processing service is unavailable"
                }
            )

        if response.status_code == 401:

            raise HTTPException(
                status_code=401,
                detail={
                    "code": "PROCESSING_SERVICE_UNAUTHORIZED",
                    "message": "Processing service rejected the internal credential"
                }
            )

        if response.status_code == 404:

            raise HTTPException(
                status_code=404,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": "Job was not found"
                }
            )

        if response.status_code >= 500:

            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PROCESSING_SERVICE_ERROR",
                    "message": "Processing service returned an error"
                }
            )

        response.raise_for_status()

        return response.json()


    async def get_job(
        self,
        job_id: UUID,
        correlation_id: str | None = None,
    ):
        headers = {
            "Authorization": f"Bearer {settings.processing_service_token}"
        }

        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"{self.base_url}/internal/v1/jobs/{job_id}",
                        headers=headers,
                    )

                if response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "code": "PROCESSING_SERVICE_UNAUTHORIZED",
                            "message": "Processing service rejected the internal token"
                        },
                    )

                if response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "JOB_NOT_FOUND",
                            "message": "Job not found"
                        },
                    )

                if response.status_code >= 500:
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "code": "PROCESSING_SERVICE_ERROR",
                            "message": "Processing service returned an error"
                        },
                    )

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=504,
                    detail={
                        "code": "PROCESSING_SERVICE_TIMEOUT",
                        "message": "Processing service timed out"
                    },
                )

            except httpx.ConnectError:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "PROCESSING_SERVICE_UNAVAILABLE",
                        "message": "Processing service is unavailable"
                    },
                )