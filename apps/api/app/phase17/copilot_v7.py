"""Copilot V7: operational answers grounded in registered tool calls (§26, §54).

- Every answer is composed from the results of tools in TOOLS, called at
  answer time. The response lists each call with a digest of its result.
- Tools are read-only. There is no tool that promotes, deletes, ingests or
  writes, so a prompt cannot make the Copilot do any of those things.
- Routing is deterministic keyword matching over a fixed intent table; the
  query text is never passed into a tool as a parameter.
- If a tool fails the answer is UNAVAILABLE. If nothing was recorded the
  answer says so; it never fills the gap.
- Secrets never enter tool results, and every result is redacted again
  before it is returned.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.db.models.operations import (
    Alert,
    DecisionRecord,
    InferenceLog,
    JobRun,
    ModelRegistryEntry,
    Notification,
    OpsUser,
    Project,
)
from app.phase17.audit import redact, verify_chain
from app.phase17.model_ops import MATCH_DOMAIN, model_health_snapshot
from app.phase17.provider_probe import latest_probe_states
from app.phase17.readiness import competition_readiness
from app.phase17.system_health import system_status
from app.phase17.workspace import decision_staleness

INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (all|previous|prior) (instructions|rules)|system prompt|reveal|print (the )?(env|environment)|"
    r"api[_ -]?key|\w+_key\b|secret|password|token|credential|promote|delete|drop table|truncate|disable (the )?(audit|trigger)|"
    r"pretend|you are now|override)"
)


def _digest(result: Any) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()[:16]


class ToolContext:
    def __init__(self, session: AsyncSession, engine: AsyncEngine, settings: Settings, user: OpsUser) -> None:
        self.session, self.engine, self.settings, self.user = session, engine, settings, user


async def t_recent_jobs(ctx: ToolContext, since: datetime) -> list[dict[str, Any]]:
    rows = (await ctx.session.execute(select(JobRun).where(JobRun.started_at >= since)
                                      .order_by(JobRun.started_at.desc()).limit(200))).scalars().all()
    return [{"job": r.job_name, "status": r.status, "provider": r.provider, "resource": r.resource,
             "params": r.parameters, "records": r.records, "snapshot_sha256": r.snapshot_sha256,
             "started_at": r.started_at.isoformat(), "errors": r.errors[:3]} for r in rows]


async def t_org_alerts(ctx: ToolContext, since: datetime | None = None) -> list[dict[str, Any]]:
    stmt = select(Alert).where(Alert.organization_id == ctx.user.organization_id)
    if since:
        stmt = stmt.where(Alert.triggered_at >= since)
    rows = (await ctx.session.execute(stmt.order_by(Alert.triggered_at.desc()).limit(100))).scalars().all()
    return [{"alert_id": str(a.id), "title": a.title, "state": a.state, "category": a.category,
             "triggered_at": a.triggered_at.isoformat(), "evidence_matches": len(a.evidence)} for a in rows]


async def t_inference_counts(ctx: ToolContext, since: datetime) -> dict[str, int]:
    rows = (await ctx.session.execute(select(InferenceLog.status).where(InferenceLog.created_at >= since))).scalars().all()
    out: dict[str, int] = {}
    for s in rows:
        out[s] = out.get(s, 0) + 1
    return out


async def t_providers(ctx: ToolContext) -> list[dict[str, Any]]:
    latest = await latest_probe_states(ctx.session)
    return [{"provider": p, "resource": r, "state": row.state, "http_status": row.http_status,
             "probed_at": row.probed_at.isoformat(), "detail": (row.detail or "")[:160]} for (p, r), row in latest.items()]


async def t_readiness(ctx: ToolContext) -> list[dict[str, Any]]:
    return [{"competition": r["competition"], "production_status": r["production_status"],
             "matches": r["match_data"]["matches"], "model_validation": r["model_support"]["validation"].get("status"),
             "live_calibration": r["calibration"]["live"]} for r in await competition_readiness(ctx.session)]


async def t_model_health(ctx: ToolContext) -> dict[str, Any]:
    h = await model_health_snapshot(ctx.session, MATCH_DOMAIN)
    h.pop("confidence_histogram", None)
    return h


async def t_models(ctx: ToolContext) -> list[dict[str, Any]]:
    rows = (await ctx.session.execute(select(ModelRegistryEntry))).scalars().all()
    return [{"domain": m.domain, "model_id": m.model_id, "model_version": m.model_version,
             "deployment_state": m.deployment_state, "supported_competitions": m.supported_competitions} for m in rows]


async def t_failures(ctx: ToolContext, since: datetime) -> dict[str, Any]:
    jobs = (await ctx.session.execute(select(JobRun).where(
        JobRun.started_at >= since, JobRun.status != "SUCCESS"))).scalars().all()
    notes = (await ctx.session.execute(select(Notification).where(Notification.state.in_(["FAILED", "RETRYING"])))).scalars().all()
    return {"jobs": [{"job": j.job_name, "status": j.status, "errors": j.errors[:2], "started_at": j.started_at.isoformat()}
                     for j in jobs],
            "notifications": [{"channel": n.channel, "state": n.state, "last_error": n.last_error} for n in notes]}


async def t_stale_decisions(ctx: ToolContext) -> list[dict[str, Any]]:
    rows = (await ctx.session.execute(select(DecisionRecord).join(Project, DecisionRecord.project_id == Project.id)
                                      .where(Project.organization_id == ctx.user.organization_id))).scalars().all()
    out = []
    for rec in rows:
        project = await ctx.session.get(Project, rec.project_id)
        if project.visibility != "ORGANIZATION" and project.owner_user_id != ctx.user.id and ctx.user.role != "ADMIN":
            continue
        st = await decision_staleness(ctx.session, rec)
        out.append({"decision_id": str(rec.id), "title": rec.title, **st})
    return out


async def t_system(ctx: ToolContext) -> dict[str, Any]:
    s = await system_status(ctx.session, ctx.engine, ctx.settings)
    return {"status": s["status"], "components": {k: v.get("status") if isinstance(v, dict) and "status" in v else v
                                                  for k, v in s["components"].items()}}


async def t_audit(ctx: ToolContext) -> dict[str, Any]:
    return await verify_chain(ctx.session)


TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "recent_jobs": t_recent_jobs, "org_alerts": t_org_alerts, "inference_counts": t_inference_counts,
    "providers": t_providers, "competition_readiness": t_readiness, "model_health": t_model_health,
    "models": t_models, "failures": t_failures, "stale_decisions": t_stale_decisions,
    "system_status": t_system, "audit_chain": t_audit,
}

# (intent, keyword groups — every group needs one hit, tools)
INTENTS: list[tuple[str, list[tuple[str, ...]], list[str]]] = [
    ("WATCHLIST_TRIGGERS", [("watchlist",)], ["org_alerts"]),
    ("STALE_DECISIONS", [("decision",), ("stale", "review", "outdated")], ["stale_decisions"]),
    ("PROVIDER_AVAILABILITY", [("provider",)], ["providers"]),
    ("COMPETITION_READINESS", [("competition", "league"), ("ready", "readiness", "production", "supported", "pilot")],
     ["competition_readiness"]),
    ("ACTIVE_MODEL", [("model",), ("active", "current", "which", "version")], ["models"]),
    ("PREDICTION_HEALTH", [("prediction", "model"), ("health", "healthy", "working", "ok")], ["model_health", "models"]),
    ("RECENT_INGESTION", [("ingest", "data"), ("recent", "today", "latest", "last")], ["recent_jobs"]),
    ("FAILURES", [("fail", "error", "broken", "wrong")], ["failures"]),
    ("EVIDENCE", [("evidence", "audit", "proof", "lineage")], ["audit_chain", "recent_jobs"]),
    ("WHAT_CHANGED", [("changed", "change", "new", "happened")], ["recent_jobs", "org_alerts", "inference_counts"]),
    ("SYSTEM_STATUS", [("status", "health", "system", "up", "down")], ["system_status"]),
]


def classify(query: str) -> tuple[str, list[str]]:
    q = query.lower()
    for intent, groups, tools in INTENTS:
        if all(any(k in q for k in g) for g in groups):
            return intent, tools
    return "UNSUPPORTED", []


def _compose(intent: str, results: dict[str, Any]) -> str:
    if intent == "WATCHLIST_TRIGGERS":
        a = results["org_alerts"]
        return f"{len(a)} watchlist alert(s) recorded for your organization." if a else \
            "No watchlist alert has been triggered for your organization."
    if intent == "STALE_DECISIONS":
        d = results["stale_decisions"]
        stale = [x for x in d if x["state"] == "STALE"]
        return f"{len(stale)} of {len(d)} visible decision(s) are STALE (a Silver dependency changed after the decision)." \
            if d else "No decisions are recorded in projects you can see."
    if intent == "PROVIDER_AVAILABILITY":
        p = results["providers"]
        if not p:
            return "UNVERIFIED: no provider probe has been recorded."
        bad = sorted({x["provider"] for x in p if x["state"] != "AVAILABLE"})
        good = sorted({x["provider"] for x in p if x["state"] == "AVAILABLE"} - set(bad))
        return f"Unavailable/blocked: {', '.join(bad) or 'none'}. Available at last probe: {', '.join(good) or 'none'}."
    if intent == "COMPETITION_READINESS":
        r = results["competition_readiness"]
        ready = [x["competition"] for x in r if x["production_status"] == "PRODUCTION_READY"]
        states = ", ".join(f"{x['competition']}={x['production_status']}" for x in r)
        return (f"Production-ready: {', '.join(ready)}." if ready else "No competition is PRODUCTION_READY.") + \
            (f" All competitions: {states}." if r else " No competition data is loaded.")
    if intent == "ACTIVE_MODEL":
        m = results["models"]
        active = [f"{x['model_id']}:{x['model_version']}" for x in m if x["deployment_state"] == "ACTIVE"]
        shadow = [f"{x['model_id']}:{x['model_version']}" for x in m if x["deployment_state"] == "SHADOW"]
        return f"ACTIVE: {', '.join(active) or 'none'}. SHADOW: {', '.join(shadow) or 'none'}."
    if intent == "PREDICTION_HEALTH":
        h = results["model_health"]
        if h["inference_volume"] == 0:
            return "UNVERIFIED: no match prediction requests have been logged."
        return (f"{h['inference_volume']} requests logged ({h['live_inference_volume']} live); refusal rate "
                f"{h['refusal_rate']}; p95 latency {h['latency_ms']['p95']} ms; live calibration "
                f"{h['live_calibration']['status']}.")
    if intent == "RECENT_INGESTION":
        j = results["recent_jobs"]
        ok = sum(1 for x in j if x["status"] == "SUCCESS")
        return f"{len(j)} ingestion job(s) in the last 24 h, {ok} SUCCESS." if j else "No ingestion job ran in the last 24 h."
    if intent == "FAILURES":
        f = results["failures"]
        return f"{len(f['jobs'])} non-successful job(s) in the last 24 h; {len(f['notifications'])} failed/retrying notification(s)."
    if intent == "EVIDENCE":
        a = results["audit_chain"]
        return f"Audit chain {'VALID' if a['valid'] else 'BROKEN at seq ' + str(a.get('first_broken_seq'))} " \
               f"({a['events_checked']} events). Recent ingestion snapshots are listed in evidence."
    if intent == "WHAT_CHANGED":
        return (f"Since 00:00 UTC: {len(results['recent_jobs'])} ingestion job(s), {len(results['org_alerts'])} alert(s), "
                f"inference requests by status {results['inference_counts'] or '{}'}.")
    if intent == "SYSTEM_STATUS":
        return f"System status {results['system_status']['status']}."
    return ""


async def answer(query: str, ctx: ToolContext) -> dict[str, Any]:
    asked_at = datetime.now(timezone.utc)
    if INJECTION_PATTERNS.search(query):
        return {"query": query, "intent": "REFUSED", "status": "REFUSED", "tool_calls": [],
                "answer": "Refused: the Copilot only reads operational state through registered read-only tools. "
                          "It cannot reveal credentials, change models, or alter records.",
                "asked_at": asked_at.isoformat()}
    intent, tools = classify(query)
    if intent == "UNSUPPORTED":
        return {"query": query, "intent": intent, "status": "UNVERIFIED", "tool_calls": [],
                "answer": "UNVERIFIED: no registered tool answers this question.", "asked_at": asked_at.isoformat(),
                "supported_intents": [i for i, _, _ in INTENTS]}
    day = asked_at.replace(hour=0, minute=0, second=0, microsecond=0)
    args = {"recent_jobs": (asked_at - timedelta(hours=24),) if intent != "WHAT_CHANGED" else (day,),
            "org_alerts": (day,) if intent == "WHAT_CHANGED" else (), "inference_counts": (day,),
            "failures": (asked_at - timedelta(hours=24),)}
    calls, results = [], {}
    for name in tools:
        try:
            result = redact(await TOOLS[name](ctx, *args.get(name, ())))
            results[name] = result
            calls.append({"tool": name, "status": "OK", "called_at": datetime.now(timezone.utc).isoformat(),
                          "result_digest": _digest(result)})
        except Exception as exc:  # noqa: BLE001
            calls.append({"tool": name, "status": "UNAVAILABLE", "error": type(exc).__name__})
            return {"query": query, "intent": intent, "status": "UNAVAILABLE", "tool_calls": calls,
                    "answer": f"UNAVAILABLE: tool '{name}' could not read operational state ({type(exc).__name__}).",
                    "asked_at": asked_at.isoformat()}
    text = _compose(intent, results)
    # Tools ran, but if what they returned cannot support a claim the answer
    # is UNVERIFIED, and the status says so too.
    status = "UNVERIFIED" if text.startswith("UNVERIFIED") else "GROUNDED"
    return {"query": query, "intent": intent, "status": status, "tool_calls": calls,
            "answer": text, "evidence": results, "asked_at": asked_at.isoformat()}
