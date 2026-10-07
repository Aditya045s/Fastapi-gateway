
from arq.connections import RedisSettings # type: ignore

from app.workers.tasks import process_job


async def startup(ctx):
    print("ARQ worker started")


async def shutdown(ctx):
    print("ARQ worker stopped")


class WorkerSettings:
    functions = [
        process_job,
    ]

    redis_settings = RedisSettings(
        host="redis",
        port=6379,
        database=0,
    )

    on_startup = startup
    on_shutdown = shutdown