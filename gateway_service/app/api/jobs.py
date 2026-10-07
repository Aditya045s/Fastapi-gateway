from uuid import UUID

from fastapi import APIRouter, Request, Header,Depends

from app.schemas.job import JobCreate, JobResponse
from app.clients.processing_client import ProcessingClient
from app.core.config import settings
from app.core.auth import verify_jwt

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"]
)


processing_client = ProcessingClient(
    base_url=settings.processing_base_url,
    timeout=settings.processing_timeout_seconds,
    service_token=settings.processing_service_token
)


@router.post(
    "",
    response_model=JobResponse,
    dependencies=[Depends(verify_jwt)],
)
async def create_job(
    job: JobCreate,
    request: Request,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
    ),
):
    result = await processing_client.create_job(
        name=job.name,
        data=job.data,
        correlation_id=request.state.correlation_id,
        idempotency_key=idempotency_key,
    )

    return result


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    dependencies=[Depends(verify_jwt)],
)
async def get_job(
    job_id: UUID,
    request: Request,
):
    correlation_id = request.state.correlation_id

    return await processing_client.get_job(
        job_id=job_id,
        correlation_id=correlation_id,
    )