"""Phase 12 — Operational Alerts V2 Engine (§24).

Generates strictly non-causal, factual operational alerts across:
  - PLAYER_TRAJECTORY_CHANGE
  - ROLE_TRANSITION
  - EMERGING_PLAYER
  - VALUE_GAP_DETECTED
  - DECISION_STALE
  - MODEL_RETRAIN_RECOMMENDED
  - CHALLENGER_OUTPERFORMS
  - CALIBRATION_DEGRADATION
  - COMPETITION_PROMOTION_READY
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertCategoryV2(str, Enum):
    PLAYER_TRAJECTORY_CHANGE = "PLAYER_TRAJECTORY_CHANGE"
    ROLE_TRANSITION = "ROLE_TRANSITION"
    EMERGING_PLAYER = "EMERGING_PLAYER"
    VALUE_GAP_DETECTED = "VALUE_GAP_DETECTED"
    DECISION_STALE = "DECISION_STALE"
    MODEL_RETRAIN_RECOMMENDED = "MODEL_RETRAIN_RECOMMENDED"
    CHALLENGER_OUTPERFORMS = "CHALLENGER_OUTPERFORMS"
    CALIBRATION_DEGRADATION = "CALIBRATION_DEGRADATION"
    COMPETITION_PROMOTION_READY = "COMPETITION_PROMOTION_READY"


@dataclass
class OperationalAlertV2:
    """A factual, non-causal operational alert with exact before/after telemetry."""
    alert_id: str = field(default_factory=lambda: f"alt_v2_{uuid.uuid4().hex[:12]}")
    category: AlertCategoryV2 = AlertCategoryV2.EMERGING_PLAYER
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    entity_id: str = ""
    entity_name: str = ""
    observed_values: dict[str, Any] = field(default_factory=dict)
    previous_values: dict[str, Any] = field(default_factory=dict)
    delta: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    model_version: str = "v1.0"
    confidence: str = "HIGH"
    status: str = "ACTIVE"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        return data


class OperationalAlertsManagerV2:
    """Manages active continuous intelligence alerts."""

    def __init__(self) -> None:
        self._alerts: dict[str, OperationalAlertV2] = {}
        self._seed_default_alerts()

    def _seed_default_alerts(self) -> None:
        # Alert 1: Emerging Player
        a1 = OperationalAlertV2(
            alert_id="alt_emg_inacio_001",
            category=AlertCategoryV2.EMERGING_PLAYER,
            severity="INFO",
            entity_id="cand_inacio",
            entity_name="Gonçalo Inácio",
            observed_values={"contribution_percentile": 81.2, "minutes": 1540},
            previous_values={"contribution_percentile": 72.4, "minutes": 980},
            delta={"contribution_percentile": +8.8, "minutes": +560},
            evidence=[
                "Player reached top quintile contribution across 1,540 competitive minutes.",
                "Development velocity calculated at +4.4 pts per evaluation window.",
            ],
            model_version="action_value_v2.0",
            confidence="HIGH",
        )
        self._alerts[a1.alert_id] = a1

        # Alert 2: Role Transition
        a2 = OperationalAlertV2(
            alert_id="alt_trans_trent_002",
            category=AlertCategoryV2.ROLE_TRANSITION,
            severity="INFO",
            entity_id="player_trent_66",
            entity_name="Trent Alexander-Arnold",
            observed_values={"primary_role": "Inverted Playmaker", "central_touches_pct": 54.2},
            previous_values={"primary_role": "Traditional Attacking Fullback", "central_touches_pct": 28.4},
            delta={"central_touches_pct": +25.8},
            evidence=[
                "Role similarity shifted to Inverted Playmaker (0.92) across 1,440 minutes.",
                "Central-third touch share increased by +25.8%.",
            ],
            model_version="role_discovery_v2.0",
            confidence="HIGH",
        )
        self._alerts[a2.alert_id] = a2

        # Alert 3: Decision Stale
        a3 = OperationalAlertV2(
            alert_id="alt_stale_inacio_003",
            category=AlertCategoryV2.DECISION_STALE,
            severity="WARNING",
            entity_id="dec_rec_inacio_2027",
            entity_name="Summer 2027 CB Recruitment Decision",
            observed_values={"market_valuation_eur": 44_500_000.0},
            previous_values={"market_valuation_eur": 38_000_000.0},
            delta={"market_valuation_eur": +6_500_000.0},
            evidence=[
                "Player valuation appreciated +17.1% since original sign-off.",
                "Historical decision remains frozen; freshness assessment marked STALE for scout review.",
            ],
            model_version="GBR_ValuationEngine_v1.0",
            confidence="HIGH",
        )
        self._alerts[a3.alert_id] = a3

    def record_alert(self, alert: OperationalAlertV2) -> OperationalAlertV2:
        self._alerts[alert.alert_id] = alert
        return alert

    def list_alerts(self, category: AlertCategoryV2 | None = None) -> list[OperationalAlertV2]:
        alerts = list(self._alerts.values())
        if category:
            alerts = [a for a in alerts if a.category == category]
        return alerts


alerts_manager_v2 = OperationalAlertsManagerV2()
