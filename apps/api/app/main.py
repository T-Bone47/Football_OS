from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api.routes_canonical import router as canonical_router
from app.api.routes_ingestion import router as ingestion_router
from app.config import get_settings
from app.db.session import engine

settings = get_settings()

app = FastAPI(title="Football Intelligence OS", version="0.1.0")
app.include_router(ingestion_router)
app.include_router(canonical_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/ready")
async def health_ready() -> dict:
    """Unlike /health (process is up), this checks the dependency this
    process actually needs — Postgres — per architecture doc §40's
    'depend on healthy dependencies, not merely container creation'.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"database not ready: {exc}") from exc
    return {"status": "ready"}
