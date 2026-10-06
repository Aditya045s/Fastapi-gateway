from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.middleware.request_id import RequestIDMiddleware
from fastapi import HTTPException
from sqlalchemy import text

from app.db.database import engine



app = FastAPI(title="Processing Service")


app.add_middleware(RequestIDMiddleware)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def readiness_check():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        return {
            "status": "ready",
            "database": "available",
        }

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "database": "unavailable",
            },
    )



    