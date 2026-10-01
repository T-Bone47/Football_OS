"""Persistent hash-chained audit trail (§34, §43, adversarial 29).

Two independent protections:
1. The database rejects UPDATE/DELETE on ops_audit_events (trigger, 0014).
2. Each row's hash covers its content and the previous row's hash, so a
   change made by someone able to bypass the trigger (e.g. a superuser who
   disables it) is detected by `verify_chain`.

Appends are serialized with a transaction-scoped advisory lock so two
concurrent writers cannot fork the chain.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import AuditEvent
from app.observability.correlation import get_request_id
from app.observability.logging import redact_sensitive_str

GENESIS = "0" * 64
_AUDIT_LOCK_KEY = 1717_0001
_SECRET_KEY = re.compile(r"(?i)(api[-_]?key|token|password|secret|authorization|credential)")
# Bearer credentials survive the key=value pattern ("authorization: Bearer
# <token>" redacts the scheme word, not the token), so strip them explicitly.
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def redact(value: Any) -> Any:
    """Recursive redaction by key name and by value content."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SECRET_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_sensitive_str(_BEARER.sub("Bearer [REDACTED]", value))
    return value


def _event_hash(prev_hash: str, event_type: str, actor: str, resource: str, details: dict, created_at: str) -> str:
    body = json.dumps(
        {"prev": prev_hash, "type": event_type, "actor": actor, "resource": resource,
         "details": details, "at": created_at},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def append_event(
    session: AsyncSession,
    event_type: str,
    actor: str,
    resource: str,
    details: dict[str, Any] | None = None,
    commit: bool = False,
) -> AuditEvent:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    last = (await session.execute(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1))).scalar_one_or_none()
    prev = last.event_hash if last else GENESIS
    clean = redact(details or {})
    created = datetime.now(timezone.utc)
    row = AuditEvent(
        event_type=event_type, actor=str(actor), resource=str(resource), details=clean,
        correlation_id=get_request_id(), prev_hash=prev,
        event_hash=_event_hash(prev, event_type, str(actor), str(resource), clean, created.isoformat()),
        created_at=created,
    )
    session.add(row)
    await session.flush()
    if commit:
        await session.commit()
    return row


async def verify_chain(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc()))).scalars().all()
    prev = GENESIS
    for row in rows:
        expected = _event_hash(prev, row.event_type, row.actor, row.resource, row.details, row.created_at.isoformat())
        if row.prev_hash != prev or row.event_hash != expected:
            return {"valid": False, "events_checked": len(rows), "first_broken_seq": row.seq,
                    "reason": "prev_hash mismatch" if row.prev_hash != prev else "content hash mismatch"}
        prev = row.event_hash
    return {"valid": True, "events_checked": len(rows), "head_hash": prev}
