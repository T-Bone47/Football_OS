"""Phase 17 live operations API, mounted under /api/v1/ops.

Every endpoint requires a bearer token (see app.phase17.auth). Every value
returned is read from PostgreSQL, the snapshot store, a live probe or an
in-process measurement — none is a constant.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.operations import (
    Alert,
    AuditEvent,
    DecisionRecord,
    FieldValidationRecord,
    Incident,
    InferenceLog,
    JobRun,
    ModelRegistryEntry,
    Notification,
    OpsUser,
    Project,
    QualityReport,
    Watchlist,
    WatchlistItem,
)
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.db.session import engine, get_session
from app.ingestion.factory import build_snapshot_store
from app.phase17 import AlertState, CompetitionOperationalState, OpsRole
from app.phase17.alerts import InvalidCondition, channel_status, evaluate_item, transition, validate_condition
from app.phase17.audit import append_event, verify_chain
from app.phase17.auth import current_user, issue_user, load_project_for, rate_limit_backend, require
from app.phase17.copilot_v7 import ToolContext, answer
from app.phase17.live_ingestion import SCHEDULES, LiveIngestionRunner
from app.phase17.match_state import match_state
from app.phase17.model_ops import (
    MATCH_DOMAIN,
    MODE_LIVE,
    MODE_REPLAY,
    MODE_VALIDATION,
    calibration_report,
    drift_report,
    infer_match,
    model_health_snapshot,
    record_outcome,
)
from app.phase17.feature_refresh import refresh_competition_season
from app.phase17.provider_probe import latest_probe_states, provider_rollup, run_probes
from app.phase17.rate_governor import get_rate_governor
from app.phase17.readiness import MIN_LIVE_OUTCOMES_FOR_PRODUCTION, capability_matrix, competition_readiness, freshness_chain
from app.phase17.research_guard import FutureDataContamination, research_dataset
from app.phase17.system_health import system_status
from app.phase17.telemetry import latency_report
from app.phase17.workspace import build_evidence_graph, create_decision, decision_staleness, verify_decision_integrity

router = APIRouter(prefix="/api/v1/ops", tags=["Phase 17 - Live Operations"])
READ = require("ops:read")


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


# --------------------------------------------------------------- identity
class UserCreate(BaseModel):
    email: str
    name: str
    role: OpsRole


@router.get("/me")
async def me(user: OpsUser = Depends(current_user)) -> dict[str, Any]:
    return {"id": str(user.id), "email": user.email, "name": user.name, "role": user.role,
            "organization_id": str(user.organization_id)}


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, admin: OpsUser = Depends(require("user:admin")),
                      session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from app.db.models.operations import Organization

    org = await session.get(Organization, admin.organization_id)
    user, token = await issue_user(session, org.name, body.email, body.name, body.role)
    await append_event(session, "USER_CREATED", str(admin.id), str(user.id), {"role": body.role.value})
    await session.commit()
    return {"id": str(user.id), "role": user.role, "token": token,
            "note": "the token is shown once and stored only as a SHA-256 hash"}


# --------------------------------------------------------------- system / providers
@router.get("/system/status")
async def get_system_status(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    status = await system_status(session, engine, get_settings())
    status["components"]["api_rate_limit"] = {"backend": rate_limit_backend()}
    return status


@router.get("/providers")
async def get_providers(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    latest = await latest_probe_states(session)
    return {"rollup": provider_rollup(latest),
            "probes": [{"provider": p, "resource": r, "state": row.state, "authentication_state": row.authentication_state,
                        "http_status": row.http_status, "latency_ms": row.latency_ms, "quota": row.quota,
                        "endpoint": row.endpoint, "detail": row.detail, "probed_at": _iso(row.probed_at)}
                       for (p, r), row in sorted(latest.items())],
            "rate_governance": get_rate_governor().report()}


@router.post("/providers/probe")
async def probe_providers(user: OpsUser = Depends(require("probe:run")),
                          session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    results = await run_probes(session, get_settings())
    await append_event(session, "PROVIDER_PROBE", str(user.id), "providers",
                       {"states": {f"{r.provider}/{r.resource}": r.state for r in results}}, commit=True)
    return [r.to_dict() for r in results]


@router.get("/capabilities")
async def get_capabilities(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await capability_matrix(session)


# --------------------------------------------------------------- ingestion
class IngestionJobRequest(BaseModel):
    provider: str
    resource: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/schedules")
async def get_schedules(_: OpsUser = Depends(READ)) -> list[dict[str, Any]]:
    return [{"job_name": s.job_name, "provider": s.provider, "resource": s.resource,
             "schedule_class": s.schedule_class.value, "rationale": s.rationale} for s in SCHEDULES]


@router.post("/ingestion/jobs")
async def run_ingestion_job(body: IngestionJobRequest, user: OpsUser = Depends(require("ingestion:run")),
                            session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    runner = LiveIngestionRunner(session, build_snapshot_store(get_settings()))
    result = await runner.run_job(body.provider, body.resource, body.params)
    await append_event(session, "INGESTION_JOB", str(user.id), f"{body.provider}/{body.resource}",
                       {"status": result.status, "snapshot": result.snapshot_sha256}, commit=True)
    return result.to_dict()


@router.get("/ingestion/jobs")
async def list_jobs(limit: int = Query(100, le=500), _: OpsUser = Depends(READ),
                    session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(limit))).scalars().all()
    return [{"id": str(j.id), "job_name": j.job_name, "schedule_class": j.schedule_class, "provider": j.provider,
             "resource": j.resource, "parameters": j.parameters, "status": j.status, "started_at": _iso(j.started_at),
             "finished_at": _iso(j.finished_at), "latency_ms": j.latency_ms, "records": j.records, "errors": j.errors,
             "snapshot_sha256": j.snapshot_sha256} for j in rows]


@router.get("/ingestion/snapshots")
async def list_snapshots(limit: int = Query(100, le=500), _: OpsUser = Depends(READ),
                         session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(DataSnapshot, IngestionRun, DataSource).join(IngestionRun, DataSnapshot.ingestion_run_id == IngestionRun.id)
        .join(DataSource, IngestionRun.data_source_id == DataSource.id)
        .order_by(DataSnapshot.retrieved_at.desc()).limit(limit))).all()
    return [{"sha256": s.sha256, "provider": src.name, "endpoint": r.endpoint, "parameters": r.parameters,
             "provider_retrieved_at": _iso(s.provider_retrieved_at), "http_status": s.http_status,
             "size_bytes": s.size_bytes, "validation": s.validation_status.value, "schema_version": s.schema_version,
             "license": src.license, "ingestion_run_id": str(r.id)} for s, r, src in rows]


@router.get("/quality/reports")
async def list_quality(limit: int = Query(100, le=500), _: OpsUser = Depends(READ),
                       session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(QualityReport).order_by(QualityReport.created_at.desc()).limit(limit))).scalars().all()
    return [{"id": str(q.id), "scope": q.scope, "overall": q.overall, "snapshot_sha256": q.snapshot_sha256,
             "records_examined": q.records_examined, "checks": q.checks, "created_at": _iso(q.created_at)} for q in rows]


@router.get("/freshness/{competition_season_id}")
async def get_freshness(competition_season_id: uuid.UUID, _: OpsUser = Depends(READ),
                        session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await freshness_chain(session, competition_season_id)


@router.get("/competitions/readiness")
async def get_readiness(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rows = await competition_readiness(session)
    return {"computed_at": datetime.now(timezone.utc).isoformat(), "competitions": rows,
            "state_vocabulary": [s.value for s in CompetitionOperationalState],
            "rule": "every figure is filtered to its own competition; no competition inherits another's status"}


# --------------------------------------------------------------- models
@router.get("/models")
async def list_models(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(ModelRegistryEntry))).scalars().all()
    return [{"domain": m.domain, "model_id": m.model_id, "model_version": m.model_version,
             "feature_version": m.feature_version, "dataset_version": m.dataset_version,
             "artifact_sha256": m.artifact_sha256, "deployment_state": m.deployment_state,
             "supported_competitions": m.supported_competitions, "validation_metrics": m.validation_metrics,
             "min_history_matches": m.min_history_matches, "max_feature_age_hours": m.max_feature_age_hours,
             "registered_at": _iso(m.registered_at)} for m in rows]


@router.get("/models/health")
async def get_model_health(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await model_health_snapshot(session, MATCH_DOMAIN)


@router.get("/models/calibration")
async def get_calibration(mode: str = Query(MODE_LIVE, pattern=f"^({MODE_LIVE}|{MODE_REPLAY})$"),
                          _: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await calibration_report(session, mode)


@router.get("/models/drift")
async def get_drift(mode: str = Query(MODE_LIVE, pattern=f"^({MODE_LIVE}|{MODE_REPLAY}|{MODE_VALIDATION})$"),
                    _: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await drift_report(session, mode)


@router.post("/models/{model_id}/promote")
async def promote_model(model_id: str, user: OpsUser = Depends(current_user),
                        session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Human promotion to ACTIVE, gated on live evidence. Never automatic."""
    if user.role != OpsRole.ADMIN.value:
        await append_event(session, "UNAUTHORIZED_MODEL_PROMOTION_ATTEMPT", str(user.id), model_id,
                           {"role": user.role}, commit=True)
        raise HTTPException(status_code=403, detail="only ADMIN may promote a model")
    model = (await session.execute(select(ModelRegistryEntry).where(ModelRegistryEntry.model_id == model_id))).scalars().first()
    if model is None:
        raise HTTPException(status_code=404, detail="model not registered")
    live = await calibration_report(session, MODE_LIVE, model_id=model.model_id)
    drift = await drift_report(session, MODE_LIVE)
    blockers = []
    if model.deployment_state != "SHADOW":
        blockers.append(f"deployment_state is {model.deployment_state}; only SHADOW models can be promoted")
    if live["status"] != "MEASURED":
        blockers.append(f"live calibration {live['status']} ({live.get('n', 0)}/{MIN_LIVE_OUTCOMES_FOR_PRODUCTION} live outcomes)")
    elif not live.get("beats_class_prior_baseline"):
        blockers.append("live log loss does not beat the class-prior baseline")
    if drift["status"] in ("CRITICAL_DRIFT",):
        blockers.append("critical drift on live inputs")
    if blockers:
        await append_event(session, "MODEL_PROMOTION_REFUSED", str(user.id), model_id, {"blockers": blockers}, commit=True)
        raise HTTPException(status_code=409, detail={"status": "PROMOTION_BLOCKED", "blockers": blockers})
    model.deployment_state = "ACTIVE"
    await append_event(session, "MODEL_PROMOTED", str(user.id), model_id, {"live_outcomes": live["n"]})
    await session.commit()
    return {"status": "PROMOTED", "model_id": model_id}


@router.post("/models/{model_id}/demote")
async def demote_model(model_id: str, user: OpsUser = Depends(require("model:promote")),
                       session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Model rollback lever: ACTIVE -> SHADOW, SHADOW -> REGISTERED. Takes
    effect on the next request; predictions already logged are untouched."""
    model = (await session.execute(select(ModelRegistryEntry).where(ModelRegistryEntry.model_id == model_id))).scalars().first()
    if model is None:
        raise HTTPException(status_code=404, detail="model not registered")
    previous = model.deployment_state
    target = {"ACTIVE": "SHADOW", "SHADOW": "REGISTERED"}.get(previous)
    if target is None:
        raise HTTPException(status_code=409, detail=f"nothing to roll back from {previous}")
    model.deployment_state = target
    await append_event(session, "MODEL_DEMOTED", str(user.id), model_id, {"from": previous, "to": target})
    await session.commit()
    return {"status": "DEMOTED", "model_id": model_id, "from": previous, "to": target}


# --------------------------------------------------------------- inference / matches
@router.post("/inference/match/{match_id}")
async def infer(match_id: uuid.UUID, as_of: datetime | None = None,
                mode: str = Query(MODE_LIVE, pattern=f"^({MODE_LIVE}|{MODE_REPLAY})$"),
                user: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """LIVE (default): cutoff is now, cannot be backdated. HISTORICAL_REPLAY:
    explicit past cutoff, labelled as replay in the immutable log."""
    row = await infer_match(session, match_id, as_of=as_of, mode=mode)
    await session.commit()
    return {"inference_id": str(row.id), "status": row.status, "prediction_type": row.prediction_type,
            "mode": (row.evidence or {}).get("mode"),
            "output": row.output, "reasons": row.reasons, "model_id": row.model_id, "model_version": row.model_version,
            "feature_version": row.feature_version, "dataset_version": row.dataset_version,
            "data_cutoff": _iso(row.data_cutoff), "competition": row.competition, "is_ood": row.is_ood,
            "missing_features": row.missing_features, "latency_ms": row.latency_ms}


@router.post("/features/refresh/{competition_season_id}")
async def refresh_features(competition_season_id: uuid.UUID, user: OpsUser = Depends(require("ingestion:run")),
                           session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    outcomes = await refresh_competition_season(session, competition_season_id)
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status.value] = counts.get(o.status.value, 0) + 1
    await append_event(session, "FEATURE_REFRESH", str(user.id), str(competition_season_id), counts, commit=True)
    return {"competition_season_id": str(competition_season_id), "status_counts": counts,
            "recomputed": sum(1 for o in outcomes if o.computed), "entities": [o.to_dict() for o in outcomes]}


@router.get("/inference")
async def list_inferences(subject_id: str | None = None, status: str | None = None, limit: int = Query(50, le=500),
                          _: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(InferenceLog).order_by(InferenceLog.created_at.desc()).limit(limit)
    if subject_id:
        stmt = stmt.where(InferenceLog.subject_id == subject_id)
    if status:
        stmt = stmt.where(InferenceLog.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [{"inference_id": str(r.id), "status": r.status, "mode": (r.evidence or {}).get("mode"),
             "model_id": r.model_id, "competition": r.competition, "subject_id": r.subject_id,
             "data_cutoff": _iso(r.data_cutoff), "output": r.output, "reasons": r.reasons,
             "created_at": _iso(r.created_at)} for r in rows]


@router.post("/inference/{inference_id}/outcome")
async def link_outcome(inference_id: uuid.UUID, _: OpsUser = Depends(READ),
                       session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    inf = await session.get(InferenceLog, inference_id)
    if inf is None:
        raise HTTPException(status_code=404, detail="inference not found")
    outcome = await record_outcome(session, inf)
    await session.commit()
    if outcome is None:
        return {"inference_id": str(inference_id), "status": "OUTCOME_NOT_AVAILABLE",
                "reason": "prediction was not served, or the match has no final result in Silver"}
    return {"inference_id": str(inference_id), "status": "OUTCOME_RECORDED", "realized": outcome.realized,
            "observation_mode": outcome.observation_mode, "evaluation": outcome.evaluation,
            "outcome_source": outcome.outcome_source, "outcome_snapshot_sha256": outcome.outcome_snapshot_sha256}


@router.get("/inference/{inference_id}/provenance")
async def inference_provenance(inference_id: uuid.UUID, _: OpsUser = Depends(READ),
                               session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    graph = await build_evidence_graph(session, [inference_id])
    if not graph["nodes"]:
        raise HTTPException(status_code=404, detail="inference not found")
    return graph


@router.get("/matches/{match_id}/state")
async def get_match_state(match_id: uuid.UUID, _: OpsUser = Depends(READ),
                          session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    state = await match_state(session, match_id)
    if state is None:
        raise HTTPException(status_code=404, detail="match not found")
    return state


# --------------------------------------------------------------- projects / watchlists / alerts
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    kind: str = Field("RECRUITMENT", pattern="^(RECRUITMENT|RESEARCH|WATCH)$")
    description: str = ""
    visibility: str = Field("PRIVATE", pattern="^(PRIVATE|ORGANIZATION)$")
    parameters: dict[str, Any] = Field(default_factory=dict)


def _project(p: Project) -> dict[str, Any]:
    return {"id": str(p.id), "name": p.name, "kind": p.kind, "description": p.description, "visibility": p.visibility,
            "owner_user_id": str(p.owner_user_id), "parameters": p.parameters, "created_at": _iso(p.created_at)}


@router.get("/projects")
async def list_projects(user: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Project).where(Project.organization_id == user.organization_id))).scalars().all()
    from app.phase17.auth import can_view_project
    return [_project(p) for p in rows if can_view_project(user, p)]


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreate, user: OpsUser = Depends(require("project:write")),
                         session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    p = Project(organization_id=user.organization_id, owner_user_id=user.id, name=body.name, kind=body.kind,
                description=body.description, visibility=body.visibility, parameters=body.parameters)
    session.add(p)
    await session.flush()
    await append_event(session, "PROJECT_CREATED", str(user.id), str(p.id), {"name": body.name})
    await session.commit()
    return _project(p)


@router.get("/projects/{project_id}")
async def get_project(project_id: uuid.UUID, user: OpsUser = Depends(READ),
                      session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    p = await load_project_for(session, user, project_id)
    wls = (await session.execute(select(Watchlist).where(Watchlist.project_id == p.id))).scalars().all()
    decs = (await session.execute(select(DecisionRecord).where(DecisionRecord.project_id == p.id))).scalars().all()
    return {**_project(p), "watchlists": [{"id": str(w.id), "name": w.name} for w in wls],
            "decisions": [{"id": str(d.id), "title": d.title, "decision": d.decision, "created_at": _iso(d.created_at)} for d in decs]}


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class WatchlistItemCreate(BaseModel):
    entity_type: str = Field(pattern="^(PLAYER|CLUB)$")
    entity_id: uuid.UUID
    entity_name: str
    condition: dict[str, Any]


async def _watchlist_for(session: AsyncSession, user: OpsUser, watchlist_id: uuid.UUID, edit: bool = False) -> Watchlist:
    wl = await session.get(Watchlist, watchlist_id)
    if wl is None:
        raise HTTPException(status_code=404, detail="watchlist not found")
    await load_project_for(session, user, wl.project_id, edit=edit)
    return wl


@router.post("/projects/{project_id}/watchlists", status_code=201)
async def create_watchlist(project_id: uuid.UUID, body: WatchlistCreate, user: OpsUser = Depends(require("watchlist:write")),
                           session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    p = await load_project_for(session, user, project_id, edit=True)
    wl = Watchlist(project_id=p.id, owner_user_id=user.id, name=body.name)
    session.add(wl)
    await session.flush()
    await session.commit()
    return {"id": str(wl.id), "name": wl.name, "project_id": str(p.id)}


@router.post("/watchlists/{watchlist_id}/items", status_code=201)
async def add_item(watchlist_id: uuid.UUID, body: WatchlistItemCreate, user: OpsUser = Depends(require("watchlist:write")),
                   session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    wl = await _watchlist_for(session, user, watchlist_id, edit=True)
    try:
        validate_condition(body.entity_type, body.condition)
    except InvalidCondition as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    exists = (await session.execute(select(WatchlistItem.id).where(
        WatchlistItem.watchlist_id == wl.id, WatchlistItem.entity_type == body.entity_type,
        WatchlistItem.entity_id == str(body.entity_id)))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="entity already on this watchlist; one condition per entity per watchlist")
    item = WatchlistItem(watchlist_id=wl.id, entity_type=body.entity_type, entity_id=str(body.entity_id),
                         entity_name=body.entity_name, condition=body.condition, last_state={})
    session.add(item)
    await session.flush()
    await session.commit()
    return {"id": str(item.id), "entity_type": item.entity_type, "entity_id": item.entity_id, "condition": item.condition}


@router.post("/watchlists/{watchlist_id}/evaluate")
async def evaluate_watchlist(watchlist_id: uuid.UUID, user: OpsUser = Depends(READ),
                             session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    wl = await _watchlist_for(session, user, watchlist_id)
    project = await session.get(Project, wl.project_id)
    items = (await session.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id))).scalars().all()
    results = [await evaluate_item(session, it, get_settings(), project.organization_id) for it in items]
    await session.commit()
    return {"watchlist_id": str(wl.id), "evaluated_at": datetime.now(timezone.utc).isoformat(), "items": results}


@router.get("/alerts")
async def list_alerts(user: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    from sqlalchemy import or_

    from app.phase17.alerts import PLATFORM_ALERT_ROLES

    visible = Alert.organization_id == user.organization_id
    if user.role in PLATFORM_ALERT_ROLES:
        visible = or_(visible, Alert.organization_id.is_(None))
    rows = (await session.execute(select(Alert).where(visible).order_by(Alert.triggered_at.desc()).limit(200))).scalars().all()
    notes = (await session.execute(select(Notification).where(Notification.alert_id.in_([a.id for a in rows])))).scalars().all() if rows else []
    by_alert: dict[uuid.UUID, list] = {}
    for n in notes:
        by_alert.setdefault(n.alert_id, []).append({"channel": n.channel, "state": n.state, "attempts": n.attempts,
                                                    "last_error": n.last_error})
    return [{"id": str(a.id), "title": a.title, "category": a.category, "severity": a.severity, "state": a.state,
             "condition": a.condition, "threshold": a.threshold, "evidence": a.evidence, "source": a.source,
             "dedup_key": a.dedup_key, "triggered_at": _iso(a.triggered_at), "delivered_at": _iso(a.delivered_at),
             "acknowledged_at": _iso(a.acknowledged_at), "resolved_at": _iso(a.resolved_at),
             "notifications": by_alert.get(a.id, [])} for a in rows]


@router.post("/alerts/{alert_id}/{action}")
async def alert_action(alert_id: uuid.UUID, action: str, user: OpsUser = Depends(require("alert:ack")),
                       session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    target = {"acknowledge": AlertState.ACKNOWLEDGED, "dismiss": AlertState.DISMISSED, "resolve": AlertState.RESOLVED}.get(action)
    if target is None:
        raise HTTPException(status_code=404, detail="unknown action")
    from app.phase17.alerts import PLATFORM_ALERT_ROLES

    alert = await session.get(Alert, alert_id)
    platform_ok = alert is not None and alert.organization_id is None and user.role in PLATFORM_ALERT_ROLES
    if alert is None or (alert.organization_id != user.organization_id and not platform_ok):
        raise HTTPException(status_code=404, detail="alert not found")
    try:
        await transition(session, alert, target, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return {"id": str(alert.id), "state": alert.state}


@router.get("/notifications/channels")
async def notification_channels(_: OpsUser = Depends(READ)) -> dict[str, str]:
    return channel_status(get_settings())


# --------------------------------------------------------------- decisions
class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    decision: str = Field(pattern="^(PURSUE|MONITOR|REJECT|DEFER|NO_ACTION)$")
    subject_type: str = Field(pattern="^(MATCH|PLAYER|CLUB)$")
    subject_id: str
    rationale: str = Field(min_length=1)
    inference_ids: list[uuid.UUID] = Field(default_factory=list)
    supersedes_id: uuid.UUID | None = None


@router.post("/projects/{project_id}/decisions", status_code=201)
async def record_decision(project_id: uuid.UUID, body: DecisionCreate,
                          idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                          user: OpsUser = Depends(require("decision:write")),
                          session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    p = await load_project_for(session, user, project_id, edit=True)
    if body.supersedes_id:
        prior = await session.get(DecisionRecord, body.supersedes_id)
        if prior is None or prior.project_id != p.id:
            raise HTTPException(status_code=404, detail="superseded decision not found in this project")
    rec, created = await create_decision(session, user, p, title=body.title, decision=body.decision,
                                         subject_type=body.subject_type, subject_id=body.subject_id,
                                         rationale=body.rationale, inference_ids=body.inference_ids,
                                         idempotency_key=idempotency_key, supersedes_id=body.supersedes_id)
    await session.commit()
    return {"id": str(rec.id), "created": created, "content_sha256": rec.content_sha256,
            "evidence_complete": rec.evidence_graph.get("complete"), "data_cutoff": _iso(rec.data_cutoff)}


@router.get("/decisions/{decision_id}/provenance")
async def decision_provenance(decision_id: uuid.UUID, user: OpsUser = Depends(READ),
                              session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rec = await session.get(DecisionRecord, decision_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="decision not found")
    await load_project_for(session, user, rec.project_id)
    return {"id": str(rec.id), "title": rec.title, "decision": rec.decision, "rationale": rec.rationale,
            "created_at": _iso(rec.created_at), "data_cutoff": _iso(rec.data_cutoff),
            "supersedes_id": str(rec.supersedes_id) if rec.supersedes_id else None,
            "content_sha256": rec.content_sha256, "integrity_verified": verify_decision_integrity(rec),
            "staleness": await decision_staleness(session, rec), "evidence_graph": rec.evidence_graph}


# --------------------------------------------------------------- audit / copilot / research / ops
@router.get("/audit")
async def list_audit(limit: int = Query(200, le=1000), _: OpsUser = Depends(require("audit:read")),
                     session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit))).scalars().all()
    return [{"seq": e.seq, "event_type": e.event_type, "actor": e.actor, "resource": e.resource, "details": e.details,
             "correlation_id": e.correlation_id, "event_hash": e.event_hash, "created_at": _iso(e.created_at)} for e in rows]


@router.get("/audit/verify")
async def audit_verify(_: OpsUser = Depends(require("audit:read")), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await verify_chain(session)


class CopilotQuery(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


@router.post("/copilot")
async def copilot(body: CopilotQuery, user: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await answer(body.query, ToolContext(session, engine, get_settings(), user))


class ResearchDatasetRequest(BaseModel):
    cutoff: datetime
    competitions: list[str] | None = None


@router.post("/research/dataset")
async def get_research_dataset(body: ResearchDatasetRequest, _: OpsUser = Depends(READ),
                               session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        return await research_dataset(session, body.cutoff, body.competitions)
    except FutureDataContamination as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/incidents")
async def list_incidents(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Incident).order_by(Incident.detected_at.desc()))).scalars().all()
    return [{"id": str(i.id), "kind": i.kind, "is_drill": i.is_drill, "state": i.state, "severity": i.severity,
             "detected_at": _iso(i.detected_at), "recovered_at": _iso(i.recovered_at),
             "degraded_behaviour": i.degraded_behaviour, "timeline": i.timeline, "verification": i.verification} for i in rows]


@router.get("/field-validation")
async def field_validation(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(FieldValidationRecord).order_by(FieldValidationRecord.created_at.asc()))).scalars().all()
    return [{"workflow": r.workflow, "step": r.step, "execution_ms": r.execution_ms, "data_sufficiency": r.data_sufficiency,
             "system_response": r.system_response, "evidence_available": r.evidence_available, "error": r.error,
             "outcome": r.outcome, "created_at": _iso(r.created_at)} for r in rows]


@router.get("/telemetry/latency")
async def telemetry(_: OpsUser = Depends(READ)) -> dict[str, Any]:
    return latency_report()


@router.get("/usage")
async def usage(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """§44: usage metrics only. No provider exposes billing here, so no
    monetary figure is reported."""
    bronze_bytes = (await session.execute(select(func.coalesce(func.sum(DataSnapshot.size_bytes), 0)))).scalar_one()
    distinct_bytes = (await session.execute(text(
        "SELECT COALESCE(SUM(size_bytes),0) FROM (SELECT DISTINCT ON (sha256) sha256, size_bytes FROM data_snapshots) s"))).scalar_one()
    db_bytes = (await session.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
    worker_ms = (await session.execute(select(func.coalesce(func.sum(JobRun.latency_ms), 0.0)))).scalar_one()
    inferences = (await session.execute(select(func.count()).select_from(InferenceLog))).scalar_one()
    notifications = (await session.execute(select(Notification.channel, func.count()).group_by(Notification.channel))).all()
    return {"provider_requests": get_rate_governor().report(),
            "bronze_bytes_referenced": int(bronze_bytes), "bronze_bytes_distinct_content": int(distinct_bytes),
            "database_bytes": int(db_bytes), "job_runtime_ms_total": round(float(worker_ms), 1),
            "inference_requests": inferences, "notifications_by_channel": {c: n for c, n in notifications},
            "monetary_cost": "UNAVAILABLE (no provider billing API configured)"}


RETENTION_POLICY = [
    {"layer": "Bronze snapshots", "retention": "indefinite; content-addressed, never overwritten", "enforcement": "store writes only if absent"},
    {"layer": "Silver canonical rows", "retention": "indefinite; upserted from Bronze", "enforcement": "rebuildable from Bronze"},
    {"layer": "Gold / feature refresh records", "retention": "indefinite; append-only history", "enforcement": "application"},
    {"layer": "Audit events", "retention": "indefinite", "enforcement": "DB trigger blocks UPDATE/DELETE + hash chain"},
    {"layer": "Decisions", "retention": "indefinite", "enforcement": "DB trigger blocks UPDATE/DELETE"},
    {"layer": "Inference log (predictions)", "retention": "indefinite", "enforcement": "DB trigger blocks UPDATE/DELETE"},
    {"layer": "Outcomes", "retention": "indefinite", "enforcement": "FK RESTRICT to inference log"},
    {"layer": "Model artifacts", "retention": "indefinite; registry rows keep artifact SHA-256", "enforcement": "application"},
]


@router.get("/retention")
async def retention(_: OpsUser = Depends(READ), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    triggers = (await session.execute(text(
        "SELECT event_object_table, string_agg(DISTINCT event_manipulation, ',') FROM information_schema.triggers "
        "WHERE trigger_name LIKE 'ops_%_immutable' GROUP BY event_object_table"))).all()
    return {"policy": RETENTION_POLICY, "immutability_triggers_present": {t: ops for t, ops in triggers},
            "automatic_deletion_jobs": "none exist"}
