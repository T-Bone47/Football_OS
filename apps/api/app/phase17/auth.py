"""Authentication and authorization for the Phase 17 operations API (§22, §38).

Identity comes from a bearer token, never from a request body field. A
token is 32 random bytes shown once at issuance; only its SHA-256 is
stored. Authorization is checked on the server for every request:
- organization boundary: a user never sees another organization's data;
- project visibility: PRIVATE projects are visible to their owner (and the
  organization's ADMINs), ORGANIZATION projects to the whole organization;
- role permissions: e.g. only ADMIN may promote a model.
A resource the caller may not see answers 404, the same as one that does
not exist, so identifiers cannot be enumerated.
"""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from collections import defaultdict

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.operations import OpsUser, Organization, Project
from app.db.session import get_session
from app.phase17 import OpsRole

PERMISSIONS: dict[str, set[str]] = {
    OpsRole.ADMIN.value: {"ops:read", "project:write", "decision:write", "watchlist:write", "alert:ack",
                          "ingestion:run", "probe:run", "model:promote", "user:admin", "audit:read", "incident:drill"},
    OpsRole.DATA_ENGINEER.value: {"ops:read", "ingestion:run", "probe:run", "audit:read", "incident:drill"},
    OpsRole.ANALYST.value: {"ops:read", "project:write", "decision:write", "watchlist:write", "alert:ack"},
    OpsRole.SCOUT.value: {"ops:read", "project:write", "watchlist:write", "alert:ack"},
    OpsRole.RESEARCHER.value: {"ops:read", "project:write"},
    OpsRole.VIEWER.value: {"ops:read"},
}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_or_create_org(session: AsyncSession, name: str) -> Organization:
    org = (await session.execute(select(Organization).where(Organization.name == name))).scalar_one_or_none()
    if org is None:
        org = Organization(name=name)
        session.add(org)
        await session.flush()
    return org


async def issue_user(session: AsyncSession, org_name: str, email: str, name: str, role: OpsRole) -> tuple[OpsUser, str]:
    org = await get_or_create_org(session, org_name)
    token = secrets.token_urlsafe(32)
    user = OpsUser(organization_id=org.id, email=email.lower(), name=name, role=role.value, token_sha256=hash_token(token))
    session.add(user)
    await session.flush()
    return user, token


async def current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> OpsUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    token = authorization.split(" ", 1)[1].strip()
    user = (await session.execute(select(OpsUser).where(OpsUser.token_sha256 == hash_token(token)))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="invalid or revoked token", headers={"WWW-Authenticate": "Bearer"})
    enforce_rate_limit(user)
    return user


def require(permission: str):
    async def dep(user: OpsUser = Depends(current_user)) -> OpsUser:
        if permission not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(status_code=403, detail=f"role {user.role} lacks permission {permission}")
        return user
    return dep


def can_view_project(user: OpsUser, project: Project) -> bool:
    if project.organization_id != user.organization_id:
        return False
    if project.owner_user_id == user.id or user.role == OpsRole.ADMIN.value:
        return True
    return project.visibility == "ORGANIZATION"


def can_edit_project(user: OpsUser, project: Project) -> bool:
    if project.organization_id != user.organization_id:
        return False
    return project.owner_user_id == user.id or user.role == OpsRole.ADMIN.value


async def load_project_for(session: AsyncSession, user: OpsUser, project_id: uuid.UUID, edit: bool = False) -> Project:
    project = await session.get(Project, project_id)
    if project is None or not can_view_project(user, project):
        raise HTTPException(status_code=404, detail="project not found")
    if edit and not can_edit_project(user, project):
        raise HTTPException(status_code=403, detail="only the owner or an ADMIN may modify this project")
    return project


# --- Per-identity request budget (adversarial: rate-limit bypass) ---
# Keyed on the authenticated user id, so changing IPs, headers or body
# fields does not reset it. Redis is used when reachable so the budget is
# shared across workers; otherwise a process-local window keeps enforcing.
_local_windows: dict[str, list[float]] = defaultdict(list)
_redis_state = {"client": None, "checked": 0.0, "backend": "UNINITIALIZED"}


def _redis():
    now = time.monotonic()
    if _redis_state["client"] is None and now - _redis_state["checked"] > 30:
        _redis_state["checked"] = now
        try:
            import redis

            client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.2, socket_connect_timeout=0.2)
            client.ping()
            _redis_state.update(client=client, backend="REDIS")
        except Exception:  # noqa: BLE001 — degrade to local window, never to "unlimited"
            _redis_state.update(client=None, backend="PROCESS_LOCAL_FALLBACK")
    return _redis_state["client"]


def rate_limit_backend() -> str:
    return _redis_state["backend"]


def enforce_rate_limit(user: OpsUser) -> None:
    limit = get_settings().api_rate_limit_per_minute
    key = str(user.id)
    client = _redis()
    if client is not None:
        try:
            bucket = f"fios:rl:{key}:{int(time.time() // 60)}"
            count = client.incr(bucket)
            client.expire(bucket, 70)
            if count > limit:
                raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": "60"})
            return
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            _redis_state.update(client=None, backend="PROCESS_LOCAL_FALLBACK")
    now = time.monotonic()
    window = [t for t in _local_windows[key] if now - t < 60]
    window.append(now)
    _local_windows[key] = window
    if len(window) > limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": "60"})
