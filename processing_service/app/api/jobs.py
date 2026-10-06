import json

from fastapi import APIRouter, Depends, HTTPException

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_internal_token
from app.db.database import get_db
from app.repositories.job_repository import create_job as create_job_record
from app.schemas.job import JobCreateInternal, JobResponse
from app.repositories.job_repository import get_job_by_id
from arq import create_pool
from arq.connections import RedisSettings

from app.workers.tasks import process_job


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

    job_record = await create_job_record(
        db=db,
        name=job.name,
        data=job.data
    )

    redis = await create_pool(
        RedisSettings(
            host="localhost",
            port=6379,
            database=0,
        )
    )

    await redis.enqueue_job(
        "process_job",
        str(job.id),
    )

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