"""Admin endpoints (admin:access). Token revocation for incident response / "log out everywhere"."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.phase16.audit_logger import get_audit_logger
from app.security.deps import require
from app.security.revocation import LEEWAY_SECONDS, MAX_TOKEN_TTL_SECONDS, get_revocations
from app.security.tokens import Principal

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


class RevocationRequest(BaseModel):
    jti: str | None = None  # revoke one token
    user_id: str | None = None  # revoke everything issued to this user before not_before
    not_before: int | None = None  # epoch seconds; default now


@router.post("/revocations")
def revoke(body: RevocationRequest, principal: Principal = Depends(require("admin:access"))) -> dict[str, Any]:
    if bool(body.jti) == bool(body.user_id):
        raise HTTPException(status_code=422, detail="provide exactly one of jti or user_id")
    revocations = get_revocations()
    if body.jti:
        revocations.revoke_jti(body.jti, expires_at=int(time.time()) + MAX_TOKEN_TTL_SECONDS + LEEWAY_SECONDS)
        target = {"jti": body.jti}
    else:
        revocations.revoke_subject(body.user_id, not_before=body.not_before)
        target = {"user_id": body.user_id}
    get_audit_logger().log_event(
        event_type="TOKEN_REVOKED",
        actor=principal.user_id,
        resource=body.jti or body.user_id,
        details=target,
        organization_id=principal.org_id or "unscoped",
    )
    revocations.prune()
    return {"status": "REVOKED", **target}
