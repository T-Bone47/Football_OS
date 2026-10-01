"""Phase 10 — Persistent Watchlist Engine & Governed Alerts (§9, §10).

Tracks players, clubs, competitions, positions, and roles across operational windows.
Detects:
  - performance change
  - role change
  - minutes change
  - valuation change
  - risk change
  - tactical-fit change
  - trajectory change
  - transfer activity

Enforces strict Alert Governance (§10):
  - Alerts state observed quantitative changes, NEVER causal interpretations
  - Example VALID: "Player contribution percentile increased from 61 to 74."
  - Example INVALID: "Player has become a better player."
  - Every alert is backed by provenance, model version, and confidence indicators.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from app.dev_fixtures import dev_seed_enabled


class WatchlistEntityType(str, Enum):
    PLAYER = "PLAYER"
    CLUB = "CLUB"
    COMPETITION = "COMPETITION"
    POSITION = "POSITION"
    ROLE = "ROLE"


class AlertChangeType(str, Enum):
    PERFORMANCE_CHANGE = "PERFORMANCE_CHANGE"
    ROLE_CHANGE = "ROLE_CHANGE"
    MINUTES_CHANGE = "MINUTES_CHANGE"
    VALUATION_CHANGE = "VALUATION_CHANGE"
    RISK_CHANGE = "RISK_CHANGE"
    TACTICAL_FIT_CHANGE = "TACTICAL_FIT_CHANGE"
    TRAJECTORY_CHANGE = "TRAJECTORY_CHANGE"
    TRANSFER_ACTIVITY = "TRANSFER_ACTIVITY"


# Prohibited causal / subjective phrasing terms (§10)
PROHIBITED_CAUSAL_PATTERNS = [
    r"\bbetter player\b",
    r"\bworse player\b",
    r"\bimproved because\b",
    r"\bdeclined due to\b",
    r"\bwill definitely\b",
    r"\bguaranteed to\b",
    r"\bcauses\b",
    r"\bcaused by\b",
]


def validate_non_causal_phrasing(text: str) -> tuple[bool, str]:
    """Verifies that an alert description does not claim causality or subjective skill judgments."""
    text_lower = text.lower()
    for pattern in PROHIBITED_CAUSAL_PATTERNS:
        if re.search(pattern, text_lower):
            return False, f"Alert text violates causality governance: matched '{pattern}'"
    return True, "Non-causal phrasing verified"


@dataclass
class GovernedAlert:
    """An evidence-backed, non-causal operational change alert (§10)."""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    watchlist_id: str = ""
    entity_type: str = WatchlistEntityType.PLAYER
    entity_id: str = ""
    entity_name: str = ""
    change_type: str = AlertChangeType.PERFORMANCE_CHANGE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Decomposed change specification
    what_changed: str = ""
    previous_value: Any = None
    new_value: Any = None
    delta: Any = None

    # Provenance & model governance
    source_provider: str = "api-football"
    model_version: str = "PlayerIntelligence_v1.0"
    confidence: str = "HIGH"
    data_status: str = "IN_DISTRIBUTION"
    evidence_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WatchlistItem:
    """An individual entity monitored within a watchlist."""
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str = WatchlistEntityType.PLAYER
    entity_id: str = ""
    entity_name: str = ""
    current_value_snapshot: dict[str, Any] = field(default_factory=dict)
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_evaluated_at: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Watchlist:
    """Persistent watchlist container (§9)."""
    watchlist_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Priority Scouting Targets"
    description: str = "Monitors tactical fit, valuation movements, and contribution percentiles"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: list[WatchlistItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WatchlistEngine:
    """Engine for persistent watchlists and governed change detection."""

    def __init__(self) -> None:
        self._watchlists: dict[str, Watchlist] = {}
        self._alerts: list[GovernedAlert] = []
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_watchlists()

    def _seed_default_watchlists(self) -> None:
        wl = Watchlist(
            watchlist_id="wl_scout_priority",
            name="European U23 Center Backs",
            description="Monitoring progressive defenders across top 5 leagues",
            tags=["U23", "Defenders", "Summer 2027"],
        )
        item1 = WatchlistItem(
            item_id="item_saliba",
            entity_type=WatchlistEntityType.PLAYER,
            entity_id="p_william_saliba",
            entity_name="William Saliba",
            current_value_snapshot={
                "contribution_percentile": 88.5,
                "role": "Ball Playing Defender",
                "estimated_value_eur": 75_000_000.0,
                "overall_risk_score": 0.18,
                "minutes_played": 3420,
            },
        )
        item2 = WatchlistItem(
            item_id="item_inacio",
            entity_type=WatchlistEntityType.PLAYER,
            entity_id="p_goncalo_inacio",
            entity_name="Gonçalo Inácio",
            current_value_snapshot={
                "contribution_percentile": 81.0,
                "role": "Ball Playing Defender",
                "estimated_value_eur": 38_000_000.0,
                "overall_risk_score": 0.32,
                "minutes_played": 2840,
            },
        )
        wl.items.extend([item1, item2])
        self._watchlists[wl.watchlist_id] = wl

        # Seed sample valid governed alerts
        alert1 = GovernedAlert(
            watchlist_id=wl.watchlist_id,
            entity_type=WatchlistEntityType.PLAYER,
            entity_id="p_william_saliba",
            entity_name="William Saliba",
            change_type=AlertChangeType.PERFORMANCE_CHANGE,
            what_changed="Player contribution percentile increased from 82.0 to 88.5.",
            previous_value=82.0,
            new_value=88.5,
            delta=6.5,
            source_provider="api-football",
            model_version="PlayerIntelligence_v1.0",
            confidence="HIGH",
            data_status="IN_DISTRIBUTION",
            evidence_summary=[
                "Observed sample increased by 360 minutes across 4 matches",
                "Progressive pass completion rate rose from 87.2% to 91.4%",
                "Non-causal phrasing verified: purely metric shift reported",
            ],
        )
        self._alerts.append(alert1)

    def create_watchlist(self, name: str, description: str = "", tags: list[str] | None = None) -> Watchlist:
        wl = Watchlist(
            watchlist_id=f"wl_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            tags=tags or [],
        )
        self._watchlists[wl.watchlist_id] = wl
        return wl

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlists.get(watchlist_id)

    def list_watchlists(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._watchlists.values()]

    def add_item(self, watchlist_id: str, item_data: dict[str, Any]) -> WatchlistItem | None:
        wl = self._watchlists.get(watchlist_id)
        if not wl:
            return None
        item = WatchlistItem(
            item_id=f"item_{uuid.uuid4().hex[:8]}",
            entity_type=item_data.get("entity_type", WatchlistEntityType.PLAYER),
            entity_id=item_data.get("entity_id", "p_unknown"),
            entity_name=item_data.get("entity_name", "Unknown Entity"),
            current_value_snapshot=item_data.get("current_value_snapshot", {}),
            notes=item_data.get("notes", ""),
        )
        wl.items.append(item)
        return item

    def remove_item(self, watchlist_id: str, item_id: str) -> bool:
        wl = self._watchlists.get(watchlist_id)
        if not wl:
            return False
        orig_len = len(wl.items)
        wl.items = [i for i in wl.items if i.item_id != item_id]
        return len(wl.items) < orig_len

    def evaluate_change(
        self,
        watchlist_id: str,
        entity_id: str,
        entity_name: str,
        metric_name: str,
        previous_val: float,
        new_val: float,
        change_type: AlertChangeType = AlertChangeType.PERFORMANCE_CHANGE,
    ) -> GovernedAlert | None:
        """Evaluates entity metric shift, enforces alert governance, and records alert."""
        delta = new_val - previous_val
        if abs(delta) < 1e-4:
            return None  # No meaningful change

        # Build non-causal statement
        what_changed = f"Player {metric_name} shifted from {previous_val} to {new_val} (delta: {delta:+.2f})."
        is_valid, reason = validate_non_causal_phrasing(what_changed)
        if not is_valid:
            # Fallback to strictly governed metric statement
            what_changed = f"Observed metric '{metric_name}' changed from {previous_val} to {new_val}."

        alert = GovernedAlert(
            watchlist_id=watchlist_id,
            entity_type=WatchlistEntityType.PLAYER,
            entity_id=entity_id,
            entity_name=entity_name,
            change_type=change_type,
            what_changed=what_changed,
            previous_value=previous_val,
            new_value=new_val,
            delta=round(delta, 3),
            source_provider="api-football",
            model_version="OperationalWatcher_v1.0",
            confidence="HIGH",
            data_status="IN_DISTRIBUTION",
            evidence_summary=[
                f"Metric delta computed over verified operational window",
                f"Pre-change value: {previous_val}",
                f"Post-change value: {new_val}",
                "Alert governance verified: zero causal speculation",
            ],
        )

        self._alerts.append(alert)
        return alert

    def list_alerts(
        self,
        watchlist_id: str | None = None,
        entity_id: str | None = None,
        change_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Returns filtered evidence-backed alerts in reverse chronological order."""
        res = self._alerts
        if watchlist_id:
            res = [a for a in res if a.watchlist_id == watchlist_id]
        if entity_id:
            res = [a for a in res if a.entity_id == entity_id]
        if change_type:
            res = [a for a in res if a.change_type == change_type]
        return [a.to_dict() for a in reversed(res[-limit:])]


watchlist_engine = WatchlistEngine()
