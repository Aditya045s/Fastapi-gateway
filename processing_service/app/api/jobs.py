from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from arq import create_pool # type: ignore
from arq.connections import RedisSettings # type: ignore

from app.core.config import settings
from app.core.security import verify_internal_token
from app.db.database import get_db
from app.repositories.job_repository import (
    create_job as create_job_record,
    get_job_by_id,
 )
from app.schemas.job import JobCreateInternal, JobResponse


router = APIRouter(
    prefix="/internal/v1/jobs",
    tags=["Internal Jobs"]
)


@router.post(
    "",
    response_model=JobResponse,
    dependencies=[Depends(verify_internal_token)]
)
async def create_job(
    job: JobCreateInternal,
    db: AsyncSession = Depends(get_db)
 ):
    # 1. Create job in PostgreSQL
    job_record = await create_job_record(
        db=db,
        name=job.name,
        data=job.data
    )

    # 2. Connect to Redis using the Docker environment URL
    redis = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL)
    )

    try:
        # 3. Enqueue the database job ID
        await redis.enqueue_job(
            "process_job",
            str(job_record.id)
        )

        # 4. Update status after successful enqueue
        job_record.status = "QUEUED"

        await db.commit()
        await db.refresh(job_record)

    finally:
        await redis.close()

    return JobResponse(
        job_id=str(job_record.id),
        name=job_record.name,
        status=job_record.status
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_internal_token),
  ):
    job = await get_job_by_id(db, job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    return JobResponse(
        job_id=str(job.id),
        name=job.name,
        status=job.status,
    )