from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Football Intelligence OS", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
