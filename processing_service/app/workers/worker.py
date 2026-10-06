from arq import Worker

from app.core.config import settings
from app.workers.tasks import process_job


class WorkerSettings:
    functions = [
        process_job,
    ]

    redis_settings = settings.REDIS_URL


async def startup(ctx):
    print("ARQ worker started")


async def shutdown(ctx):
    print("ARQ worker stopped")