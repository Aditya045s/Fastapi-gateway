import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from uuid import UUID
from sqlalchemy import select


async def create_job(
    db: AsyncSession,
    name: str,
    data: dict
 ):

    job = Job(
        name=name,
        data=json.dumps(data),
        status="CREATED"
    )

    db.add(job)

    await db.commit()

    await db.refresh(job)

    return job

async def get_job_by_id(
    db: AsyncSession,
    job_id: UUID,
 ):
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )

    return result.scalar_one_or_none()
