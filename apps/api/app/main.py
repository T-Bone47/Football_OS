import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.api.routes_canonical import router as canonical_router
from app.api.routes_ingestion import router as ingestion_router
from app.config import get_settings
from app.db.session import engine

settings = get_settings()

app = FastAPI(title="Football Intelligence OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/auth/me")
async def get_current_user() -> dict:
    """Provides local scout analyst session for decision-room workspace access."""
    return {
        "user_id": "scout_01",
        "email": "scout@football-intelligence.local",
        "name": "Head of Scouting",
        "picture": None,
    }


@app.post("/api/auth/logout")
async def logout() -> dict:
    return {"ok": True}


@app.get("/api/status")
async def api_status() -> dict:
    return {"status": "ok", "service": "Football Intelligence OS"}


class CopilotQueryRequest(BaseModel):
    session_id: str | None = None
    query: str
    context_players: list[dict] = []


@app.post("/api/copilot/query")
async def copilot_query(body: CopilotQueryRequest):
    async def sse_generator():
        text = (
            f"Analytical context: {len(body.context_players)} canonical players loaded in scope.\n\n"
            "Backend capability status: LLM Copilot reasoning service is not yet attached to this environment. "
            "All canonical data layers (Tactical Fit, Similarity, Role Profiles, Matches, Features) are active and queryable."
        )
        yield f"data: {json.dumps({'delta': text})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


