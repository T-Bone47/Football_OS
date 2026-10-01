"""Incident records (§35). A drill walks DETECT -> ALERT -> ISOLATE ->
DEGRADED -> RECOVER -> VERIFY -> AUDIT, timestamping each stage when it is
actually observed. When the incident is a database outage the timeline is
held in memory and written once the database is back — the write itself is
part of VERIFY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import Incident
from app.phase17.audit import append_event

STAGES = ("DETECT", "ALERT", "ISOLATE", "DEGRADED", "RECOVER", "VERIFY", "AUDIT")


@dataclass
class IncidentDrill:
    kind: str
    severity: str = "HIGH"
    is_drill: bool = True
    timeline: list[dict[str, Any]] = field(default_factory=list)
    degraded_behaviour: str | None = None
    verification: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime | None = None
    recovered_at: datetime | None = None

    def stage(self, name: str, observation: str, **data: Any) -> None:
        if name not in STAGES:
            raise ValueError(name)
        now = datetime.now(timezone.utc)
        if name == "DETECT":
            self.detected_at = now
        if name == "RECOVER":
            self.recovered_at = now
        self.timeline.append({"stage": name, "at": now.isoformat(), "observation": observation, **data})

    @property
    def complete(self) -> bool:
        return [s["stage"] for s in self.timeline if s["stage"] in STAGES] == list(STAGES)

    async def persist(self, session: AsyncSession) -> Incident:
        # CLOSED requires every stage AND an explicit passing verification.
        closed = self.complete and self.verification.get("passed") is True
        row = Incident(kind=self.kind, is_drill=self.is_drill, severity=self.severity,
                       state="CLOSED" if closed else "INCOMPLETE", timeline=self.timeline,
                       degraded_behaviour=self.degraded_behaviour, detected_at=self.detected_at or datetime.now(timezone.utc),
                       recovered_at=self.recovered_at, verification=self.verification)
        session.add(row)
        await session.flush()
        await append_event(session, "INCIDENT_DRILL" if self.is_drill else "INCIDENT", "system:incident", str(row.id),
                           {"kind": self.kind, "complete": self.complete,
                            "recovery_seconds": (self.recovered_at - self.detected_at).total_seconds()
                            if self.recovered_at and self.detected_at else None})
        return row
