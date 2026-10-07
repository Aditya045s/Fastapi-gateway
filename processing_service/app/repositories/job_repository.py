import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


async def create_job(
    db: AsyncSession,
    name: str,
    data: dict,
    idempotency_key: str | None = None,
) -> Job:
    job = Job(
        name=name,
        data=json.dumps(data),
        status="CREATED",
        idempotency_key=idempotency_key,
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


async def get_job_by_idempotency_key(
    db: AsyncSession,
    idempotency_key: str,
) -> Job | None:
    result = await db.execute(
        select(Job).where(
            Job.idempotency_key == idempotency_key
        )
    )

    return result.scalar_one_or_none()