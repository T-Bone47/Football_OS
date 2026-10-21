"""Grounded copilot API.

Three surfaces:

* ``POST /api/v1/copilot/grounded`` - one grounded turn (answer + evidence + tool
  trace + validation report).
* ``POST /api/v1/copilot/grounded/stream`` - the same turn, streamed as SSE events
  (``status`` / ``tool`` / ``delta`` / ``evidence`` / ``validation`` / ``done``).
* ``GET /api/v1/copilot/tools`` - the typed tool catalogue (also the schema the model
  is offered).

The existing ``/api/copilot/query`` endpoint is untouched: it remains the
keyword-routed streaming path.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.llm.registry import get_llm_registry
from app.llm.tools.fio_tools import build_tool_registry
from app.llm.tools.orchestrator import GroundedCopilot
from app.security.deps import get_principal
from app.security.tokens import Principal

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class GroundedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=2000)
    context_players: list[dict[str, Any]] = Field(default_factory=list, max_length=25)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


class StreamRequest(GroundedRequest):
    pass


@router.get("/tools")
async def list_tools() -> dict[str, Any]:
    """The typed tool catalogue: names, schemas, services and data sources."""
    registry = build_tool_registry()
    return {
        "tool_count": len(registry.names()),
        "tools": registry.catalogue(),
    }


_CAPABILITY_CACHE: dict[str, Any] = {"checked_at": 0.0, "result": None}
_CAPABILITY_TTL_SECONDS = 900.0


@router.get("/capabilities")
async def copilot_capabilities(
    verify: bool = Query(
        default=False, description="Force a live provider check instead of the cached result."
    ),
) -> dict[str, Any]:
    """What the assistant can actually do right now.

    "configured", "tested" and "reachable" are reported separately. The live check is
    cached so a page load never triggers an inference request.
    """
    registry = get_llm_registry()
    if not getattr(registry, "_initialized", False):
        registry.initialize()
    provider = registry.get_primary()
    active = registry.get_active_status()

    now = time.time()
    cached = _CAPABILITY_CACHE.get("result")
    if cached and not verify and (now - float(_CAPABILITY_CACHE.get("checked_at", 0))) < _CAPABILITY_TTL_SECONDS:
        return cached

    result: dict[str, Any] = {
        "provider": active.get("provider"),
        "model": active.get("model"),
        "configured": bool(active.get("configured")),
        "status": active.get("status"),
        "streaming_enabled": bool(getattr(provider, "supports_streaming", False)),
        "tool_calling_supported": bool(getattr(provider, "supports_tool_calling", False)),
        "last_success_at": active.get("last_success_at"),
        "last_error": active.get("last_error"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "live_check_performed": False,
    }
    if verify and provider is not None:
        try:
            health = await provider.verify_health()
            result["live_check_performed"] = True
            result["live_status"] = health.get("status")
            result["live_model"] = health.get("model")
            result["streaming_verified"] = health.get("streaming_verified")
        except Exception as exc:  # noqa: BLE001 - a failed probe is a reported result
            result["live_check_performed"] = True
            result["live_status"] = "ERROR"
            result["live_error"] = type(exc).__name__

    _CAPABILITY_CACHE["checked_at"] = now
    _CAPABILITY_CACHE["result"] = result
    return result


@router.post("/grounded")
async def grounded_copilot(
    body: GroundedRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    """One grounded turn: the model may only speak about what the tools retrieved."""
    copilot = GroundedCopilot(session=session, principal=principal)
    result = await copilot.answer(
        body.query,
        context_players=body.context_players,
        history=body.history,
    )
    return result.to_dict()


@router.post("/grounded/stream")
async def grounded_copilot_stream(
    body: StreamRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> StreamingResponse:
    """The grounded turn, streamed as SSE events."""
    copilot = GroundedCopilot(session=session, principal=principal)

    async def event_stream():
        async for event in copilot.answer_stream(
            body.query,
            context_players=body.context_players,
            history=body.history,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
