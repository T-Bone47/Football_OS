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
import json
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.operations import OpsUser, Organization, Project
from app.db.session import get_session
from app.phase17 import OpsRole

# analysis:run (Phase 18) covers compute-only POST endpoints (simulations,
# comparisons, analyses) that store nothing. VIEWER cannot run them.
PERMISSIONS: dict[str, set[str]] = {
    OpsRole.ADMIN.value: {"ops:read", "project:write", "decision:write", "watchlist:write", "alert:ack",
                          "ingestion:run", "probe:run", "model:promote", "user:admin", "audit:read", "incident:drill",
                          "analysis:run"},
    OpsRole.DATA_ENGINEER.value: {"ops:read", "ingestion:run", "probe:run", "audit:read", "incident:drill"},
    OpsRole.ANALYST.value: {"ops:read", "project:write", "decision:write", "watchlist:write", "alert:ack", "analysis:run"},
    OpsRole.SCOUT.value: {"ops:read", "project:write", "watchlist:write", "alert:ack", "analysis:run"},
    OpsRole.RESEARCHER.value: {"ops:read", "project:write", "analysis:run"},
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
    user = OpsUser(organization_id=org.id, email=email.lower(), name=name, role=role.value, token_sha256=hash_token(token),
                   token_expires_at=_token_expiry())
    session.add(user)
    await session.flush()
    return user, token


def _token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=get_settings().token_ttl_hours)


async def rotate_token(session: AsyncSession, user: OpsUser) -> str:
    """Issues a new token for `user`; the previous one stops working at once."""
    token = secrets.token_urlsafe(32)
    user.token_sha256 = hash_token(token)
    user.token_expires_at = _token_expiry()
    user.token_revoked_at = None
    await session.flush()
    return token


async def revoke_token(session: AsyncSession, user: OpsUser) -> None:
    user.token_revoked_at = datetime.now(timezone.utc)
    await session.flush()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


# ----------------------------------------------------------------------- OIDC
_jwks_cache: dict[str, Any] = {"url": None, "keys": None, "fetched": 0.0}
JWKS_CACHE_SECONDS = 600


async def _jwks(url: str) -> list[dict[str, Any]]:
    now = time.monotonic()
    if _jwks_cache["url"] == url and _jwks_cache["keys"] is not None and now - _jwks_cache["fetched"] < JWKS_CACHE_SECONDS:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    _jwks_cache.update(url=url, keys=keys, fetched=now)
    return keys


async def verify_oidc_token(token: str) -> dict[str, Any]:
    """Verifies signature (RS256, key from the issuer's JWKS), issuer, audience
    and expiry. Raises 401 on any failure; never trusts unverified claims."""
    import jwt

    settings = get_settings()
    if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
        raise _unauthorized("OIDC is not configured")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        keys = await _jwks(settings.oidc_jwks_url)
        jwk = next((k for k in keys if k.get("kid") == kid), None)
        if jwk is None:
            raise _unauthorized("token signed with an unknown key")
        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        return jwt.decode(token, key, algorithms=["RS256"], audience=settings.oidc_audience,
                          issuer=settings.oidc_issuer, options={"require": ["exp", "iss", "sub", "aud"]})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - any verification failure is a 401
        raise _unauthorized(f"invalid OIDC token ({type(exc).__name__})") from exc


async def resolve_principal(authorization: str | None, session: AsyncSession) -> OpsUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token.count(".") == 2:  # a JWT: only accepted when signed by the configured issuer
        claims = await verify_oidc_token(token)
        try:
            user = (await session.execute(select(OpsUser).where(
                OpsUser.oidc_issuer == claims["iss"], OpsUser.oidc_subject == str(claims["sub"])))).scalar_one_or_none()
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(status_code=503, detail="authentication backend unavailable") from exc
        if user is None:
            raise HTTPException(status_code=403, detail="identity verified but not provisioned in this platform")
        if not user.is_active:
            raise _unauthorized("account disabled")
    else:
        try:
            user = (await session.execute(select(OpsUser).where(OpsUser.token_sha256 == hash_token(token)))).scalar_one_or_none()
        except (SQLAlchemyError, OSError) as exc:
            # Fail closed, and say why: the token could not be checked.
            raise HTTPException(status_code=503, detail="authentication backend unavailable") from exc
        if user is None or not user.is_active:
            raise _unauthorized("invalid or revoked token")
        if user.token_revoked_at is not None:
            raise _unauthorized("token revoked")
        if user.token_expires_at is not None and user.token_expires_at <= datetime.now(timezone.utc):
            raise _unauthorized("token expired")
    enforce_rate_limit(user)
    return user


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> OpsUser:
    # Resolved once per request (the global gate may already have done it).
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    user = await resolve_principal(authorization, session)
    request.state.principal = user
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
