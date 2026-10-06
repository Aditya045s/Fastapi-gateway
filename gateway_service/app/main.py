from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.middleware.request_id import RequestIDMiddleware


app = FastAPI(title="Gateway Service")


app.add_middleware(RequestIDMiddleware)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    return {"status": "ready"}