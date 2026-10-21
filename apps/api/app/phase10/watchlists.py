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
  - Alerts report ONLY the values they were given. They do not claim a provider, a model version, verification
    or a confidence level: those are UNASSESSED / USER_SUPPLIED until a real detector supplies evidence.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.persistence.factory import get_stores
from app.persistence.stores import CollectionStore
from app.security.tokens import Principal


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
    source_provider: str = "USER_SUPPLIED"
    model_version: str | None = None
    confidence: str = "UNASSESSED"
    data_status: str = "UNVERIFIED_INPUT"
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
    name: str = ""
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: list[WatchlistItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    owner_id: str = ""
    organization_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WatchlistEngine:
    """Engine for persistent watchlists and governed change detection. Backed by a CollectionStore so watchlists
    and alerts survive a process restart."""

    _COLLECTION = "phase10_watchlists"
    _ALERT_COLLECTION = "phase10_alerts"

    def __init__(self, store: CollectionStore | None = None) -> None:
        self._store = store
        self._watchlists: dict[str, Watchlist] = {}
        self._alerts: list[GovernedAlert] = []
        if store is not None:
            for record in store.list(self._COLLECTION):
                data = record.payload
                wl = Watchlist(
                    watchlist_id=record.record_id,
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    created_at=data.get("created_at", ""),
                    items=[WatchlistItem(**i) for i in data.get("items", [])],
                    tags=data.get("tags", []),
                    owner_id=record.owner_id,
                    organization_id=record.organization_id,
                )
                self._watchlists[wl.watchlist_id] = wl
            for record in store.list(self._ALERT_COLLECTION):
                self._alerts.append(GovernedAlert(**record.payload))
            self._alerts.sort(key=lambda a: a.created_at)

    def _save(self, wl: Watchlist) -> None:
        if self._store is not None:
            self._store.put(self._COLLECTION, wl.watchlist_id, wl.owner_id, wl.organization_id, wl.to_dict())

    def create_watchlist(
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        owner_id: str = "",
        organization_id: str | None = None,
    ) -> Watchlist:
        if not str(name or "").strip():
            raise ValueError("watchlist name is required")
        if not owner_id:
            raise ValueError("owner_id is required")
        wl = Watchlist(
            watchlist_id=f"wl_{uuid.uuid4().hex[:8]}",
            name=name.strip(),
            description=description,
            tags=tags or [],
            owner_id=owner_id,
            organization_id=organization_id,
        )
        self._watchlists[wl.watchlist_id] = wl
        return wl

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlists.get(watchlist_id)

    def get_watchlist_for(self, principal: Principal, watchlist_id: str) -> Watchlist:
        """Watchlists are private to their owner; KeyError (-> 404) otherwise."""
        wl = self._watchlists.get(watchlist_id)
        if wl is None or wl.owner_id != principal.user_id:
            raise KeyError(f"Watchlist '{watchlist_id}' not found")
        return wl

    def list_watchlists(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._watchlists.values()]

    def list_watchlists_for(self, principal: Principal) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._watchlists.values() if w.owner_id == principal.user_id]

    def add_item(self, watchlist_id: str, item_data: dict[str, Any]) -> WatchlistItem | None:
        wl = self._watchlists.get(watchlist_id)
        if not wl:
            return None
        if not str(item_data.get("entity_id") or "").strip() or not str(item_data.get("entity_name") or "").strip():
            raise ValueError("entity_id and entity_name are required")
        item = WatchlistItem(
            item_id=f"item_{uuid.uuid4().hex[:8]}",
            entity_type=item_data.get("entity_type", WatchlistEntityType.PLAYER),
            entity_id=item_data["entity_id"],
            entity_name=item_data["entity_name"],
            current_value_snapshot=item_data.get("current_value_snapshot", {}),
            notes=item_data.get("notes", ""),
        )
        wl.items.append(item)
        self._save(wl)
        return item

    def remove_item(self, watchlist_id: str, item_id: str) -> bool:
        wl = self._watchlists.get(watchlist_id)
        if not wl:
            return False
        orig_len = len(wl.items)
        wl.items = [i for i in wl.items if i.item_id != item_id]
        removed = len(wl.items) < orig_len
        if removed:
            self._save(wl)
        return removed

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
            evidence_summary=[
                f"Supplied previous value: {previous_val}",
                f"Supplied new value: {new_val}",
                "Both values were supplied by the caller and have not been checked against a provider snapshot.",
            ],
        )

        self._alerts.append(alert)
        if self._store is not None:
            wl = self._watchlists.get(watchlist_id)
            owner = wl.owner_id if wl else ""
            org = wl.organization_id if wl else None
            self._store.put(self._ALERT_COLLECTION, alert.alert_id, owner, org, alert.to_dict())
        return alert

    def list_alerts(
        self,
        watchlist_id: str | None = None,
        entity_id: str | None = None,
        change_type: str | None = None,
        limit: int = 50,
        watchlist_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Alerts in reverse chronological order. `watchlist_ids` restricts to the caller's own watchlists
        (None = no restriction, for internal use only; routes always pass the caller's visible ids)."""
        res = self._alerts
        if watchlist_ids is not None:
            res = [a for a in res if a.watchlist_id in watchlist_ids]
        if watchlist_id:
            res = [a for a in res if a.watchlist_id == watchlist_id]
        if entity_id:
            res = [a for a in res if a.entity_id == entity_id]
        if change_type:
            res = [a for a in res if a.change_type == change_type]
        return [a.to_dict() for a in reversed(res[-limit:])]


def _default_engine() -> WatchlistEngine:
    return WatchlistEngine(store=get_stores()[0])


watchlist_engine = _default_engine()
