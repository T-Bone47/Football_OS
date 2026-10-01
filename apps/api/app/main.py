import json
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_canonical import router as canonical_router
from app.api.routes_data_coverage import router as data_coverage_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_phase10 import router as phase10_router
from app.api.routes_phase11 import router as phase11_router
from app.api.routes_phase12 import router as phase12_router
from app.api.routes_phase13 import router as phase13_router
from app.api.routes_phase14 import router as phase14_router
from app.api.routes_phase15 import router as phase15_router
from app.api.routes_phase16 import router as phase16_router
from app.api.routes_phase17 import router as phase17_router
from app.config import get_settings
from app.db.session import engine, get_session
from app.decisions.copilot import orchestrate_copilot_decision

from app.observability.correlation import CorrelationIdMiddleware
from app.dev_fixtures import dev_seed_enabled
from app.phase17.auth import require
from app.db.models.operations import OpsUser
from app.phase17.environments import enforce_startup_policy
from app.phase17.telemetry import LatencyTelemetryMiddleware
from app.observability.system_health import (
    check_application_health,
    check_data_health,
    check_model_health,
    check_readiness,
)

settings = get_settings()
# Phase 17 §2/§46: staging and production refuse to start with development
# defaults, wildcard CORS or non-durable snapshot storage.
environment_audit = enforce_startup_policy(settings)

app = FastAPI(title="Football Intelligence OS", version="0.1.0")

app.add_middleware(LatencyTelemetryMiddleware)
app.add_middleware(CorrelationIdMiddleware)
# Phase 17 (reconnaissance R17): origins come from CORS_ALLOWED_ORIGINS. The
# previous list included "*" together with allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router)
app.include_router(canonical_router)
app.include_router(data_coverage_router)
app.include_router(phase10_router)
app.include_router(phase11_router)
app.include_router(phase12_router)
app.include_router(phase13_router)
app.include_router(phase14_router)
app.include_router(phase15_router)
app.include_router(phase16_router)
app.include_router(phase17_router)



@app.get("/health")
@app.get("/health/live")
async def health_live() -> dict:
    """Liveness: this process is running. Says nothing about data or models."""
    res = await check_application_health()
    res["environment"] = settings.environment
    # Visible to every client so a demo-fixture build can never pass as real data.
    res["demo_fixtures_enabled"] = dev_seed_enabled()
    return res


@app.get("/health/ready")
@app.get("/readiness")
async def health_ready(response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    """Readiness: the database answers and is migrated to this code's head.
    Answers 503 when not ready, so orchestrators stop routing traffic here."""
    res = await check_readiness(session)
    if res["status"] != "READY":
        response.status_code = 503
    return res


@app.get("/health/deep")
async def health_deep(_: OpsUser = Depends(require("ops:read")), session: AsyncSession = Depends(get_session)) -> dict:
    """Deep health: every component probed now (database, Redis, storage,
    providers, model artifact, worker). Authenticated: it calls external
    providers and must not be a free amplifier for anonymous traffic."""
    from app.phase17.system_health import system_status

    return await system_status(session, engine, settings)


@app.get("/model-status")
async def model_status(session: AsyncSession = Depends(get_session)) -> dict:
    """Model state read from the authoritative registry (ops_model_registry)."""
    return await check_model_health(session)


@app.get("/data-status")
async def data_status(session: AsyncSession = Depends(get_session)) -> dict:
    """Data state measured from PostgreSQL: counts, provenance coverage, snapshot age."""
    return await check_data_health(session)


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
async def copilot_query(
    body: CopilotQueryRequest,
    session: AsyncSession = Depends(get_session),
):
    async def sse_generator():
        try:
            async for chunk in orchestrate_copilot_decision(
                query=body.query,
                context_players=body.context_players,
                session=session,
            ):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'delta': f'Analytical query encountered an error: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


