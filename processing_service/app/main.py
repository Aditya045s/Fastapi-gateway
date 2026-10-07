from app.api.jobs import router as jobs_router
from app.middleware.request_id import RequestIDMiddleware
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from arq import create_pool # type: ignore
from arq.connections import RedisSettings # type: ignore
from app.db.database import AsyncSessionLocal
from app.db.database import engine



app = FastAPI(title="Processing Service")


app.add_middleware(RequestIDMiddleware)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
@app.get("/ready")
async def ready():
    # Check PostgreSQL
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_NOT_READY",
                "message": "Database is not ready",
            },
        )

    # Check Redis
    try:
        redis = await create_pool(
            RedisSettings(
                host="redis",
                port=6379,
                database=0,
            )
        )

        await redis.ping()
        await redis.close()

    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "REDIS_NOT_READY",
                "message": "Redis is not ready",
            },
        )

    return {
        "status": "ready",
        "database": "ok",
        "redis": "ok",
    }
