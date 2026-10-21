import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_canonical import router as canonical_router
from app.api.routes_copilot import router as copilot_router
from app.api.routes_coverage import router as coverage_router
from app.api.routes_data_coverage import router as data_coverage_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_phase10 import router as phase10_router
from app.api.routes_phase11 import router as phase11_router
from app.api.routes_phase12 import router as phase12_router
from app.api.routes_phase13 import router as phase13_router
from app.api.routes_phase14 import router as phase14_router
from app.api.routes_phase15 import router as phase15_router
from app.api.routes_phase16 import router as phase16_router
from app.config import get_settings
from app.db.session import get_session
from app.decisions.copilot import orchestrate_copilot_decision

from app.llm.registry import get_llm_registry
from app.observability.correlation import CorrelationIdMiddleware
from app.observability.system_health import (
    check_application_health,
    check_data_health,
    check_model_health,
    check_readiness,
)
from app.api.demo_gate import require_demo_data
from app.api.routes_admin import router as admin_router
from app.security.cors import parse_cors_origins
from app.security.deps import get_principal
from app.security.tokens import Principal

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize LLM registry
    logger.info("Initializing LLM registry...")
    llm_registry = get_llm_registry()
    llm_registry.initialize()
    logger.info(f"LLM registry initialized. Primary: {llm_registry.get_active_status()}")

    # Verify LLM provider health on startup
    if llm_registry.get_primary():
        health_results = await llm_registry.verify_all()
        logger.info(f"LLM provider health: {health_results}")

    yield

    # Shutdown
    logger.info("Shutting down LLM providers...")
    await llm_registry.close_all()

app = FastAPI(title="Football Intelligence OS", version="0.1.0", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware)
# Credentialed CORS to explicit origins only (CORS_ALLOWED_ORIGINS); a wildcard is a startup error.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Correlation-ID"],
)

# Every application router requires a verified principal. Only the probes defined below are public
# (tests/unit/test_route_protection.py enforces this).
_AUTHENTICATED = [Depends(get_principal)]
app.include_router(admin_router, dependencies=_AUTHENTICATED)
app.include_router(ingestion_router, dependencies=_AUTHENTICATED)
app.include_router(canonical_router, dependencies=_AUTHENTICATED)
app.include_router(copilot_router, dependencies=_AUTHENTICATED)
app.include_router(coverage_router, dependencies=_AUTHENTICATED)
app.include_router(data_coverage_router, dependencies=_AUTHENTICATED)
app.include_router(phase10_router, dependencies=_AUTHENTICATED)
# Phases 11-14 compute from hand-typed demonstration figures (competition coverage, learning loop, simulated squads and
# outcomes): demo mode only, 409 DEMO_ONLY otherwise.
_DEMO_ONLY = [*_AUTHENTICATED, Depends(require_demo_data)]
app.include_router(phase11_router, dependencies=_DEMO_ONLY)
app.include_router(phase12_router, dependencies=_DEMO_ONLY)
app.include_router(phase13_router, dependencies=_DEMO_ONLY)
app.include_router(phase14_router, dependencies=_DEMO_ONLY)
app.include_router(phase15_router, dependencies=_AUTHENTICATED)
app.include_router(phase16_router, dependencies=_AUTHENTICATED)



@app.get("/health")
async def health() -> dict:
    """LIVENESS only: the process answers. Says nothing about data, models or dependencies."""
    res = await check_application_health()
    return {"status": res["status"], "service": res["service"], "timestamp": res["timestamp"], "environment": settings.environment}


@app.get("/readiness")
async def readiness(response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    """READINESS: the database (required dependency) is reachable. 503 unless READY."""
    result = await check_readiness(session)
    if result["status"] != "READY":
        response.status_code = 503
    return result


@app.get("/health/ready")
async def health_ready(session: AsyncSession = Depends(get_session)) -> dict:
    """Legacy alias for Docker compose healthchecks. Never echoes exception text (it can embed the DSN)."""
    result = await check_readiness(session)
    if result["status"] != "READY":
        raise HTTPException(status_code=503, detail="database not ready")
    return {"status": "ready"}


@app.get("/model-status", dependencies=_AUTHENTICATED)
async def model_status() -> dict:
    """MODEL HEALTH: registered artifacts, hash integrity and release status (measured, not asserted)."""
    return await check_model_health()


@app.get("/llm-status", dependencies=_AUTHENTICATED)
async def llm_status() -> dict:
    """LLM PROVIDER HEALTH: active provider, model, streaming status, and verification."""
    llm_registry = get_llm_registry()
    active = llm_registry.get_active_status()
    all_statuses = llm_registry.get_all_statuses()

    return {
        "active": active,
        "providers": all_statuses,
        "fallback_enabled": settings.llm_allow_paid_fallback,
    }


@app.get("/data-status", dependencies=_AUTHENTICATED)
async def data_status(session: AsyncSession = Depends(get_session)) -> dict:
    """DATA HEALTH: measured row counts, schema version and last successful ingestion."""
    return await check_data_health(session)


@app.get("/api/v1/whoami")
async def whoami(principal: Principal = Depends(get_principal)) -> dict:
    """The verified identity behind the bearer token (nothing is invented or defaulted)."""
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "org_id": principal.org_id,
        "roles": sorted(principal.roles),
        "permissions": sorted(principal.permissions),
    }


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
    principal: Principal = Depends(get_principal),
):
    async def sse_generator():
        try:
            async for chunk in orchestrate_copilot_decision(
                query=body.query,
                context_players=body.context_players,
                session=session,
            ):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except Exception:
            logger.exception("copilot query failed (user=%s)", principal.user_id)
            yield f"data: {json.dumps({'delta': 'The analytical query failed. Details were logged server-side.', 'error': True})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


