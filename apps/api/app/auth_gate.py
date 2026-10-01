"""Deny-by-default access policy for the whole API (Phase 18, R9 / N5 / N8).

Installed as an application-level dependency, so it runs before every route:

1. PUBLIC: liveness/readiness probes and the API schema. Nothing else.
2. DEMO_ONLY: legacy routes whose state lives only in process memory
   (in-memory projects, watchlists, decision records, experiments, legacy
   copilots). Outside DEV_SEED demo mode they answer 410 and name the
   persistent replacement. State that must survive a restart is never kept
   only in memory.
3. Everything else needs an authenticated principal (bearer token or a
   verified OIDC token; never an identity taken from the request body).
   Reads need `ops:read`. Writes need the route's own permission, or
   `analysis:run` for compute endpoints, or `ingestion:run` for ingestion.
"""
from __future__ import annotations

import re

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dev_fixtures import dev_seed_enabled
from app.phase17.auth import PERMISSIONS, current_user

PUBLIC_PATHS = {
    "/health", "/health/live", "/health/ready", "/readiness", "/api/status",
    "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
}

OPS = "/api/v1/ops"

# (methods or None for all, pattern, persistent replacement)
DEMO_ONLY: list[tuple[set[str] | None, re.Pattern[str], str]] = [
    (None, re.compile(r"^/api/phase10/(recruitment|watchlists|decisions|scenarios)(/|$)"),
     f"{OPS}/projects, {OPS}/watchlists, {OPS}/decisions"),
    (None, re.compile(r"^/api/phase1[0-2]/copilot(/|$)"), f"{OPS}/copilot"),
    (None, re.compile(r"^/api/v1/(decision-lab|operations|outcomes|research)/copilot$"), f"{OPS}/copilot"),
    ({"POST"}, re.compile(r"^/api/phase11/datasets$"), "dataset manifests (docs/PHASE_18_REPRODUCIBILITY.md)"),
    ({"POST"}, re.compile(r"^/api/phase11/models/[^/]+/shadow/inference$"), f"{OPS}/inference/match/{{id}}"),
    ({"POST"}, re.compile(r"^/api/phase12/(benchmarks|learning/promote)$"), f"{OPS}/models/{{id}}/promote"),
    # Phase 13 Decision Lab: string club ids ("arsenal_fc"), seeded rosters and
    # in-memory scenarios. Replaced by the canonical decision and squad APIs.
    (None, re.compile(r"^/api/v1/decision-lab(/|$)"),
     "/api/v1/decisions/*, /api/v1/squads/*, /api/v1/scenarios/transfer"),
    ({"POST"}, re.compile(r"^/api/v1/outcomes/(research|evaluate)$"), f"{OPS}/inference/{{id}}/outcome"),
    ({"POST"}, re.compile(r"^/api/v1/research/(experiments|validate)$"), f"{OPS}/research/dataset"),
    (None, re.compile(r"^/api/v1/(projects|watchlists)(/|$)"), f"{OPS}/projects, {OPS}/watchlists"),
    (None, re.compile(r"^/api/v1/operations/(jobs|alerts)(/|$)"), f"{OPS}/ingestion/jobs, {OPS}/alerts"),
    ({"POST"}, re.compile(r"^/api/v1/models/(promote|predict)$"), f"{OPS}/models/{{id}}/promote, {OPS}/inference/match/{{id}}"),
    ({"POST"}, re.compile(r"^/api/v1/data/incidents/"), f"{OPS}/incidents"),
]

INGESTION_WRITE = re.compile(r"^/api/v1/(ingestion|normalization)(/|$)")
READ_METHODS = {"GET", "HEAD"}


def demo_only_match(method: str, path: str) -> str | None:
    for methods, pattern, replacement in DEMO_ONLY:
        if (methods is None or method in methods) and pattern.search(path):
            return replacement
    return None


def required_permission(method: str, path: str) -> str | None:
    """Permission the gate enforces; None when the route enforces its own."""
    if path.startswith(OPS) or path.startswith("/api/auth/"):
        return None  # these routes declare require(...) / current_user themselves
    if method in READ_METHODS:
        return "ops:read"
    if INGESTION_WRITE.search(path):
        return "ingestion:run"
    if path == "/api/phase10/operations/ingestion/trigger":
        return None  # route requires ingestion:run
    return "analysis:run"


async def auth_gate(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> None:
    method, path = request.method.upper(), request.url.path
    if method == "OPTIONS" or path in PUBLIC_PATHS:
        return
    replacement = demo_only_match(method, path)
    if replacement and not dev_seed_enabled():
        raise HTTPException(status_code=410, detail={
            "status": "RETIRED_IN_MEMORY_STATE",
            "reason": "this route kept records only in process memory; they would not survive a restart",
            "use_instead": replacement,
        })
    user = await current_user(request, authorization, session)
    permission = required_permission(method, path)
    if permission and permission not in PERMISSIONS.get(user.role, set()):
        raise HTTPException(status_code=403, detail=f"role {user.role} lacks permission {permission}")
