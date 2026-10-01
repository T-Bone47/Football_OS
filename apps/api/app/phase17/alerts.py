"""Watchlist evaluation, alert governance and notification delivery
(§23, §24, §25).

- A watchlist condition is evaluated on Silver rows; the evidence is the
  list of matches (with their Bronze snapshot hashes) that produced the
  value.
- An alert is raised only when a condition goes from not-met to met, so a
  condition that stays true does not alert again (noise control). The
  dedup key also makes a repeated evaluation idempotent.
- The database refuses an alert without evidence (CHECK constraint, 0014).
  There is no API to create an alert directly.
- IN_APP delivery is a database row and is always available. WEBHOOK is
  used only when NOTIFICATION_WEBHOOK_URL is configured, and is SENT only
  on a 2xx answer. EMAIL has no configured provider in this deployment and
  therefore no delivery path at all; its channel status is NOT_CONFIGURED.
"""
from __future__ import annotations

import hashlib
import json
import operator
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.canonical import Match, MatchEvent, MatchLineup
from app.db.models.operations import Alert, Notification, Project, Watchlist, WatchlistItem
from app.db.models.provenance import DataSnapshot
from app.phase17 import AlertState, NotificationChannel, NotificationState
from app.phase17.audit import append_event

OPERATORS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq}
PLAYER_METRICS = {"goals", "starts", "appearances", "cards"}
CLUB_METRICS = {"points", "goals_for", "goals_against"}
MAX_WEBHOOK_ATTEMPTS = 3

ALLOWED_TRANSITIONS = {
    AlertState.TRIGGERED.value: {AlertState.DELIVERED.value, AlertState.ACKNOWLEDGED.value, AlertState.DISMISSED.value,
                                 AlertState.RESOLVED.value},
    AlertState.DELIVERED.value: {AlertState.ACKNOWLEDGED.value, AlertState.DISMISSED.value, AlertState.RESOLVED.value},
    AlertState.ACKNOWLEDGED.value: {AlertState.RESOLVED.value, AlertState.DISMISSED.value},
    AlertState.DISMISSED.value: set(),
    AlertState.RESOLVED.value: set(),
}


class InvalidCondition(ValueError):
    pass


def validate_condition(entity_type: str, condition: dict[str, Any]) -> None:
    metrics = PLAYER_METRICS if entity_type == "PLAYER" else CLUB_METRICS if entity_type == "CLUB" else set()
    if not metrics:
        raise InvalidCondition("entity_type must be PLAYER or CLUB")
    if condition.get("metric") not in metrics:
        raise InvalidCondition(f"metric must be one of {sorted(metrics)}")
    if condition.get("operator") not in OPERATORS:
        raise InvalidCondition(f"operator must be one of {sorted(OPERATORS)}")
    if not isinstance(condition.get("threshold"), (int, float)):
        raise InvalidCondition("threshold must be a number")
    n = condition.get("window_matches")
    if not isinstance(n, int) or not 1 <= n <= 50:
        raise InvalidCondition("window_matches must be an integer in [1, 50]")


async def _player_window(session: AsyncSession, player_id: uuid.UUID, n: int) -> list[tuple[Match, MatchLineup]]:
    rows = (await session.execute(
        select(Match, MatchLineup).join(MatchLineup, MatchLineup.match_id == Match.id)
        .where(MatchLineup.player_id == player_id, Match.status == "FINISHED")
        .order_by(Match.date.desc()).limit(n)
    )).all()
    return list(rows)


async def _club_window(session: AsyncSession, club_id: uuid.UUID, n: int) -> list[Match]:
    return list((await session.execute(
        select(Match).where(or_(Match.home_club_id == club_id, Match.away_club_id == club_id), Match.status == "FINISHED")
        .order_by(Match.date.desc()).limit(n)
    )).scalars().all())


async def _snapshot_sha(session: AsyncSession, snapshot_id: uuid.UUID | None) -> str | None:
    if snapshot_id is None:
        return None
    snap = await session.get(DataSnapshot, snapshot_id)
    return snap.sha256 if snap else None


async def measure(session: AsyncSession, item: WatchlistItem) -> dict[str, Any]:
    cond = item.condition
    n = cond["window_matches"]
    metric = cond["metric"]
    entity = uuid.UUID(item.entity_id)
    evidence: list[dict[str, Any]] = []
    if item.entity_type == "PLAYER":
        window = await _player_window(session, entity, n)
        match_ids = [m.id for m, _ in window]
        events = (await session.execute(select(MatchEvent).where(
            MatchEvent.match_id.in_(match_ids), MatchEvent.player_id == entity,
            MatchEvent.event_type.in_(["GOAL", "CARD"])))).scalars().all() if match_ids else []
        events_ingested = set((await session.execute(select(MatchEvent.match_id).where(
            MatchEvent.match_id.in_(match_ids)).distinct())).scalars().all()) if match_ids else set()
        total = 0
        for m, lu in window:
            if metric == "starts":
                v = int(lu.is_starter)
            elif metric == "appearances":
                v = 1
            else:
                kind = "GOAL" if metric == "goals" else "CARD"
                v = sum(1 for e in events if e.match_id == m.id and e.event_type == kind
                        and (kind != "GOAL" or e.event_detail != "Own Goal"))
            total += v
            evidence.append({"match_id": str(m.id), "provider_fixture_id": m.provider_fixture_id,
                             "date": m.date.isoformat(), "value": v,
                             "events_ingested": m.id in events_ingested if metric in ("goals", "cards") else None,
                             "lineup_snapshot_sha256": await _snapshot_sha(session, lu.snapshot_id)})
        missing_events = metric in ("goals", "cards") and any(not e["events_ingested"] for e in evidence)
    else:
        window = await _club_window(session, entity, n)
        total = 0
        for m in window:
            home = m.home_club_id == entity
            f, a = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
            v = {"points": 3 if f > a else 1 if f == a else 0, "goals_for": f, "goals_against": a}[metric]
            total += v
            evidence.append({"match_id": str(m.id), "provider_fixture_id": m.provider_fixture_id,
                             "date": m.date.isoformat(), "value": v,
                             "match_snapshot_sha256": await _snapshot_sha(session, m.snapshot_id)})
        missing_events = False
    sufficient = len(evidence) >= n and not missing_events
    return {"metric": metric, "value": total, "window_matches": n, "matches_found": len(evidence),
            "data_sufficiency": "SUFFICIENT" if sufficient else
            ("EVENTS_NOT_INGESTED" if missing_events else "INSUFFICIENT_DATA"),
            "evidence": sorted(evidence, key=lambda e: e["date"])}


def dedup_key(item_id: uuid.UUID, condition: dict[str, Any], last_match_id: str) -> str:
    return hashlib.sha256(json.dumps([str(item_id), condition, last_match_id], sort_keys=True).encode()).hexdigest()


async def evaluate_item(session: AsyncSession, item: WatchlistItem, settings: Settings,
                        organization_id: uuid.UUID) -> dict[str, Any]:
    m = await measure(session, item)
    cond = item.condition
    now = datetime.now(timezone.utc)
    previously_met = bool((item.last_state or {}).get("condition_met"))
    result: dict[str, Any] = {"item_id": str(item.id), "entity_name": item.entity_name, **m, "alert": None}
    if m["data_sufficiency"] != "SUFFICIENT":
        result["condition_met"] = None
        item.last_state = {**(item.last_state or {}), "last_measure": m["value"], "data_sufficiency": m["data_sufficiency"]}
        item.last_evaluated_at = now
        await session.flush()
        return result
    met = OPERATORS[cond["operator"]](m["value"], cond["threshold"])
    result["condition_met"] = met
    if met and not previously_met:
        key = dedup_key(item.id, cond, m["evidence"][-1]["match_id"])
        existing = (await session.execute(select(Alert).where(Alert.dedup_key == key))).scalar_one_or_none()
        if existing is None:
            alert = Alert(
                dedup_key=key, organization_id=organization_id, watchlist_item_id=item.id,
                category="WATCHLIST_CONDITION", severity="MEDIUM", condition=cond,
                threshold={"operator": cond["operator"], "value": cond["threshold"]},
                evidence=m["evidence"], source="watchlist_evaluation:silver",
                state=AlertState.TRIGGERED.value, triggered_at=now,
                title=f"{item.entity_name}: {cond['metric']} {m['value']} {cond['operator']} {cond['threshold']} "
                      f"over last {cond['window_matches']} matches",
            )
            session.add(alert)
            await session.flush()
            await append_event(session, "ALERT_TRIGGERED", "system:watchlist", str(alert.id),
                               {"dedup_key": key, "item": str(item.id), "value": m["value"]})
            await deliver(session, alert, settings)
            result["alert"] = {"id": str(alert.id), "state": alert.state, "dedup_key": key}
        else:
            result["alert"] = {"id": str(existing.id), "state": existing.state, "dedup_key": key, "deduplicated": True}
    elif not met and previously_met:
        open_alerts = (await session.execute(select(Alert).where(
            Alert.watchlist_item_id == item.id,
            Alert.state.in_([AlertState.TRIGGERED.value, AlertState.DELIVERED.value, AlertState.ACKNOWLEDGED.value])
        ))).scalars().all()
        for a in open_alerts:
            a.state = AlertState.RESOLVED.value
            a.resolved_at = now
        result["resolved_alerts"] = [str(a.id) for a in open_alerts]
    item.last_state = {"condition_met": met, "last_measure": m["value"],
                       "window_last_match": m["evidence"][-1]["match_id"] if m["evidence"] else None,
                       "data_sufficiency": m["data_sufficiency"]}
    item.last_evaluated_at = now
    await session.flush()
    return result


def channel_status(settings: Settings) -> dict[str, str]:
    return {
        NotificationChannel.IN_APP.value: "AVAILABLE",
        NotificationChannel.WEBHOOK.value: "CONFIGURED" if settings.notification_webhook_url else "NOT_CONFIGURED",
        NotificationChannel.EMAIL.value: "NOT_CONFIGURED",
    }


async def _notification(session: AsyncSession, alert: Alert, channel: NotificationChannel) -> Notification:
    row = (await session.execute(select(Notification).where(
        Notification.alert_id == alert.id, Notification.channel == channel.value))).scalar_one_or_none()
    if row is None:
        row = Notification(alert_id=alert.id, channel=channel.value, state=NotificationState.QUEUED.value, attempts=0)
        session.add(row)
        await session.flush()
    return row


async def deliver(session: AsyncSession, alert: Alert, settings: Settings,
                  transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, Any]]:
    """Idempotent: a channel already SENT is never sent again."""
    out = []
    in_app = await _notification(session, alert, NotificationChannel.IN_APP)
    if in_app.state != NotificationState.SENT.value:
        in_app.state = NotificationState.SENT.value
        in_app.attempts += 1
        in_app.provider_response = "stored in ops_notifications (in-app inbox)"
    out.append({"channel": in_app.channel, "state": in_app.state})

    if settings.notification_webhook_url:
        hook = await _notification(session, alert, NotificationChannel.WEBHOOK)
        if hook.state != NotificationState.SENT.value and hook.attempts < MAX_WEBHOOK_ATTEMPTS:
            body = {"alert_id": str(alert.id), "title": alert.title, "category": alert.category,
                    "evidence": alert.evidence, "triggered_at": alert.triggered_at.isoformat(), "dedup_key": alert.dedup_key}
            async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
                while hook.attempts < MAX_WEBHOOK_ATTEMPTS:
                    hook.attempts += 1
                    try:
                        resp = await client.post(settings.notification_webhook_url, json=body,
                                                 headers={"Idempotency-Key": alert.dedup_key})
                        hook.provider_response = f"HTTP {resp.status_code}"
                        if 200 <= resp.status_code < 300:
                            hook.state = NotificationState.SENT.value
                            hook.last_error = None
                            break
                        hook.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    except httpx.HTTPError as exc:
                        hook.last_error = f"{type(exc).__name__}: {exc}"
                    hook.state = NotificationState.RETRYING.value if hook.attempts < MAX_WEBHOOK_ATTEMPTS \
                        else NotificationState.FAILED.value
        out.append({"channel": hook.channel, "state": hook.state, "attempts": hook.attempts, "last_error": hook.last_error})

    if alert.state == AlertState.TRIGGERED.value and any(o["state"] == NotificationState.SENT.value for o in out):
        alert.state = AlertState.DELIVERED.value
        alert.delivered_at = datetime.now(timezone.utc)
    await session.flush()
    return out


async def transition(session: AsyncSession, alert: Alert, new_state: AlertState, actor_id: uuid.UUID) -> Alert:
    if new_state.value not in ALLOWED_TRANSITIONS.get(alert.state, set()):
        raise ValueError(f"illegal alert transition {alert.state} -> {new_state.value}")
    now = datetime.now(timezone.utc)
    alert.state = new_state.value
    alert.actor_user_id = actor_id
    if new_state == AlertState.ACKNOWLEDGED:
        alert.acknowledged_at = now
    if new_state in (AlertState.RESOLVED, AlertState.DISMISSED):
        alert.resolved_at = now
    await append_event(session, f"ALERT_{new_state.value}", str(actor_id), str(alert.id), {})
    await session.flush()
    return alert


async def watchlist_items_for_org(session: AsyncSession, organization_id: uuid.UUID) -> list[WatchlistItem]:
    return list((await session.execute(
        select(WatchlistItem).join(Watchlist, WatchlistItem.watchlist_id == Watchlist.id)
        .join(Project, Watchlist.project_id == Project.id)
        .where(and_(Project.organization_id == organization_id))
    )).scalars().all())


async def requeue_notification(session: AsyncSession, notification: Notification, actor: str) -> Notification:
    """Operator action after a channel outage: a FAILED notification gets a
    fresh retry budget. The previous error is kept in provider_response and
    the requeue is audited."""
    if notification.state != NotificationState.FAILED.value:
        raise ValueError(f"only FAILED notifications can be requeued (state={notification.state})")
    notification.provider_response = f"requeued after: {notification.last_error}"
    notification.state = NotificationState.QUEUED.value
    notification.attempts = 0
    await append_event(session, "NOTIFICATION_REQUEUED", actor, str(notification.id), {"channel": notification.channel})
    await session.flush()
    return notification


PLATFORM_ALERT_ROLES = ("ADMIN", "DATA_ENGINEER")


async def raise_operational_alert(session: AsyncSession, *, category: str, severity: str, title: str,
                                  evidence: list[dict[str, Any]], source: str, dedup_scope: str) -> Alert:
    """Platform-level alert (organization_id NULL) for operational failures.
    Deduplicated per category/scope per hour, so a failing provider raises
    one alert per hour, not one per request. Evidence is mandatory."""
    if not evidence:
        raise ValueError("an alert requires evidence")
    now = datetime.now(timezone.utc)
    key = hashlib.sha256(f"{category}|{dedup_scope}|{now:%Y-%m-%dT%H}".encode()).hexdigest()
    existing = (await session.execute(select(Alert).where(Alert.dedup_key == key))).scalar_one_or_none()
    if existing is not None:
        return existing
    alert = Alert(dedup_key=key, organization_id=None, category=category, severity=severity,
                  condition={"category": category, "scope": dedup_scope},
                  threshold={"rule": "any occurrence; deduplicated hourly"}, evidence=evidence, source=source,
                  state=AlertState.TRIGGERED.value, triggered_at=now, title=title[:256])
    session.add(alert)
    await session.flush()
    in_app = await _notification(session, alert, NotificationChannel.IN_APP)
    in_app.state = NotificationState.SENT.value
    in_app.attempts = 1
    in_app.provider_response = "stored in ops_notifications (in-app inbox)"
    alert.state = AlertState.DELIVERED.value
    alert.delivered_at = now
    await append_event(session, "OPERATIONAL_ALERT", f"system:{source}", str(alert.id), {"category": category, "scope": dedup_scope})
    return alert
