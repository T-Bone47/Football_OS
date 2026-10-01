"""Append-Only Production Audit Logging & Lineage for Phase 16.

Audits critical operations:
- login
- project_creation
- decision_creation
- scenario_execution
- model_deployment
- model_promotion
- data_source_changes
- research_validation
- watchlist_changes
- permission_changes

Rules:
- Append-only structure; entries cannot be updated or deleted.
- Automatic secret redaction.
- Cryptographic chained hashing for tamper evidence.
"""

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from pydantic import BaseModel, Field

SECRET_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
]


def redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redacts values for keys matching sensitive secret patterns."""
    redacted: dict[str, Any] = {}
    for k, v in data.items():
        if any(p.search(k) for p in SECRET_PATTERNS):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_secrets(v)
        else:
            redacted[k] = v
    return redacted


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    user_id: str
    organization_id: str
    resource_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: dict[str, Any] = Field(default_factory=dict)
    previous_event_hash: str = ""
    event_hash: str = ""

    @property
    def resource(self) -> str:
        return self.resource_id

    @resource.setter
    def resource(self, value: str) -> None:
        self.resource_id = value


class AuditLogger:
    """Manages immutable, cryptographically chained audit events."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._last_hash = "GENESIS_AUDIT_BLOCK"

    def record_event(
        self,
        event_type: str,
        user_id: str,
        organization_id: str,
        resource_id: str,
        details: dict[str, Any],
    ) -> AuditEvent:
        clean_details = redact_secrets(details)
        evt_idx = len(self._events) + 1
        event_id = f"aud_{evt_idx}_{event_type.lower()}"
        ts = datetime.now(timezone.utc).isoformat()

        raw_sig = f"{event_id}:{event_type}:{user_id}:{organization_id}:{resource_id}:{ts}:{json.dumps(clean_details, sort_keys=True)}:{self._last_hash}"
        evt_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

        event = AuditEvent(
            event_id=event_id,
            event_type=event_type.upper(),
            user_id=user_id,
            organization_id=organization_id,
            resource_id=resource_id,
            timestamp=ts,
            details=clean_details,
            previous_event_hash=self._last_hash,
            event_hash=evt_hash,
        )

        self._events.append(event)
        self._last_hash = evt_hash
        return event

    def log_event(
        self,
        event_type: str,
        actor: str,
        resource: str,
        details: dict[str, Any] | None = None,
        organization_id: str = "org_arsenal",
    ) -> AuditEvent:
        """Convenience wrapper for record_event."""
        return self.record_event(
            event_type=event_type,
            user_id=actor,
            organization_id=organization_id,
            resource_id=resource,
            details=details or {},
        )

    def list_events(self, limit: int = 50, event_type: str | None = None) -> list[AuditEvent]:
        evts = list(reversed(self._events[-limit:]))
        if event_type:
            evts = [e for e in evts if e.event_type == event_type.upper()]
        return evts

    def verify_chain_integrity(self) -> tuple[bool, str | None]:
        """Verifies cryptographic hash chain integrity across all audit events.

        Returns (is_valid, broken_event_id_or_none).
        """
        curr_prev = "GENESIS_AUDIT_BLOCK"
        for evt in self._events:
            if evt.previous_event_hash != curr_prev:
                return False, evt.event_id
            raw_sig = f"{evt.event_id}:{evt.event_type}:{evt.user_id}:{evt.organization_id}:{evt.resource_id}:{evt.timestamp}:{json.dumps(evt.details, sort_keys=True)}:{curr_prev}"
            expected_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
            if evt.event_hash != expected_hash:
                return False, evt.event_id
            curr_prev = evt.event_hash
        return True, None



_GLOBAL_AUDIT_LOGGER: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _GLOBAL_AUDIT_LOGGER
    if _GLOBAL_AUDIT_LOGGER is None:
        _GLOBAL_AUDIT_LOGGER = AuditLogger()
        _GLOBAL_AUDIT_LOGGER.record_event(
            event_type="SYSTEM_INITIALIZATION",
            user_id="system",
            organization_id="system_platform",
            resource_id="kernel_v16.0",
            details={"status": "INITIALIZED", "certified_state": "ADAPTIVE_INTELLIGENCE_VALIDATED"},
        )
    return _GLOBAL_AUDIT_LOGGER
