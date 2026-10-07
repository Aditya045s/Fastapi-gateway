from sqlalchemy import select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.models.job import Job


async def process_job(ctx, job_id: str):
    """
    Background job executed by the ARQ worker.
    """

    async with AsyncSessionLocal() as session:
        # 1. Find the job
        result = await session.execute(
            select(Job).where(Job.id == job_id)
        )

        job = result.scalar_one_or_none()

        if job is None:
            return

        try:
            # 2. Mark job as PROCESSING
            job.status = "PROCESSING"
            await session.commit()

            # ------------------------------------------------
            # Put the actual background processing here
            # ------------------------------------------------

            # Temporary simulation
            # Later replace this with your real processing logic.
            print(f"Processing job: {job_id}")

            # ------------------------------------------------

            # 3. Mark job as COMPLETED
            job.status = "COMPLETED"
            await session.commit()

        except Exception:
            # 4. Mark job as FAILED
            job.status = "FAILED"
            await session.commit()

            raise