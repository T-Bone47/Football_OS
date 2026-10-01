"""Operational Alerting Engine & Deduplication Governor for Phase 16.

12 Alert Categories:
1. DATA_FAILURE
2. DATA_STALENESS
3. MODEL_DRIFT
4. MODEL_DEGRADATION
5. OOD_SPIKE
6. DECISION_STALE
7. TRANSFER_EVENT
8. PLAYER_BREAKOUT
9. ROLE_TRANSITION
10. MARKET_CHANGE
11. COMPETITION_READINESS_CHANGE
12. SYSTEM_FAILURE

Severity Levels: INFO, LOW, MEDIUM, HIGH, CRITICAL.
Deduplication: Suppresses duplicate alerts with identical deduplication_key.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import AlertSeverity


class OperationalAlert(BaseModel):
    alert_id: str
    category: str
    severity: AlertSeverity
    source: str
    title: str
    description: str
    evidence: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "ACTIVE"  # ACTIVE, ACKNOWLEDGED, RESOLVED, SUPPRESSED
    deduplication_key: str
    occurrence_count: int = 1


class AlertingEngine:
    """Manages emission, deduplication, and suppression of operational alerts."""

    def __init__(self) -> None:
        self._alerts: dict[str, OperationalAlert] = {}
        self._dedup_index: dict[str, str] = {}  # dedup_key -> alert_id

    def emit_alert(
        self,
        category: str,
        severity: AlertSeverity,
        source: str,
        title: str,
        description: str,
        evidence: list[str] | None = None,
        custom_dedup_key: str | None = None,
    ) -> tuple[OperationalAlert, bool]:
        """Emits an operational alert with automated deduplication.

        Returns (alert, was_created_new).
        """
        raw_key = custom_dedup_key or f"{category}:{source}:{title}"
        dedup_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

        if dedup_key in self._dedup_index:
            existing_id = self._dedup_index[dedup_key]
            existing_alert = self._alerts[existing_id]
            existing_alert.occurrence_count += 1
            existing_alert.timestamp = datetime.now(timezone.utc).isoformat()
            if evidence:
                existing_alert.evidence.extend(evidence)
            return existing_alert, False

        alert_id = f"alt_{category.lower()}_{dedup_key[:8]}"
        alert = OperationalAlert(
            alert_id=alert_id,
            category=category.upper(),
            severity=severity,
            source=source,
            title=title,
            description=description,
            evidence=evidence or [],
            deduplication_key=dedup_key,
            occurrence_count=1,
        )

        self._alerts[alert_id] = alert
        self._dedup_index[dedup_key] = alert_id
        return alert, True

    def acknowledge_alert(self, alert_id: str) -> OperationalAlert:
        alert = self.get_alert(alert_id)
        alert.status = "ACKNOWLEDGED"
        return alert

    def resolve_alert(self, alert_id: str) -> OperationalAlert:
        alert = self.get_alert(alert_id)
        alert.status = "RESOLVED"
        return alert

    def get_alert(self, alert_id: str) -> OperationalAlert:
        if alert_id not in self._alerts:
            raise KeyError(f"Alert '{alert_id}' not found.")
        return self._alerts[alert_id]

    def list_alerts(self, severity: AlertSeverity | None = None, status: str | None = None) -> list[OperationalAlert]:
        alerts = list(self._alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if status:
            alerts = [a for a in alerts if a.status == status.upper()]
        return alerts


_GLOBAL_ALERTING_ENGINE: AlertingEngine | None = None


def get_alerting_engine() -> AlertingEngine:
    global _GLOBAL_ALERTING_ENGINE
    if _GLOBAL_ALERTING_ENGINE is None:
        _GLOBAL_ALERTING_ENGINE = AlertingEngine()
        # Seed realistic alerts
        _GLOBAL_ALERTING_ENGINE.emit_alert(
            category="DECISION_STALE",
            severity=AlertSeverity.HIGH,
            source="freshness_engine",
            title="Recruitment Decision Staleness Detected",
            description="Decision 'dec_rec_timber_2023' requires review: market valuation aged and player role shifted.",
            evidence=["Market valuation delta: +12%", "Primary role usage changed to Inverted FB"],
        )
        _GLOBAL_ALERTING_ENGINE.emit_alert(
            category="MODEL_DRIFT",
            severity=AlertSeverity.MEDIUM,
            source="drift_monitoring",
            title="Moderate Feature Drift in Ligue 1",
            description="Population Stability Index (PSI = 0.185) elevated in Ligue 1 winger progressive carries.",
            evidence=["PSI: 0.185 > 0.10 baseline warning threshold"],
        )
    return _GLOBAL_ALERTING_ENGINE
