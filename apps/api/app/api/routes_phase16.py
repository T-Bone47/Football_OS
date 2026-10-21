"""FastAPI Routes for Phase 16 Production Football Intelligence Platform.

Exposes endpoints conforming to Section 41 (API Contract):
- /api/v1/operations/status, health, alerts, jobs, copilot
- /api/v1/system/status
- /api/v1/data/providers, freshness, incidents, readiness
- /api/v1/models/production, health, drift, challengers, promote, predict
- /api/v1/decisions/freshness, review-required
- /api/v1/projects
- /api/v1/watchlists
- /api/v1/audit
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.observability.model_governance import governance_registry
from app.observability.status import OK, UNKNOWN, aggregate_status
from app.observability.system_health import check_model_health, check_readiness
from app.phase16 import (
    AlertSeverity,
    DeploymentState,
    FreshnessState,
    IncidentSeverity,
    IncidentStatus,
    JobStatus,
    SystemHealthStatus,
    UserRole,
)
from app.phase16.alerting_engine import OperationalAlert, get_alerting_engine
from app.phase16.audit_logger import AuditEvent, get_audit_logger
from app.phase16.background_jobs import ProductionJob, get_job_manager
from app.phase16.caching_layer import get_deterministic_cache
from app.phase16.copilot_v6 import CopilotV6Response, get_copilot_v6
from app.phase16.data_quality_engine import DataQualityIncident, get_data_quality_engine
from app.phase16.freshness_engine import EntityFreshnessSnapshot, get_freshness_engine
from app.phase16.ingestion_orchestrator import IngestionRunRecord, get_ingestion_orchestrator
from app.phase16.model_serving import (
    ModelServingProfile,
    ModelUnavailableError,
    get_model_serving_engine,
)
from app.phase16.projects_and_auth import (
    AuthorizationError,
    DuplicateIdError,
    ProductionWatchlist,
    RecruitmentProject,
    WatchlistItem,
    get_project_auth_manager,
)
from app.phase16.provider_orchestrator import (
    ProviderCapabilityProfile,
    get_provider_orchestrator,
)
from app.security.deps import get_principal, require
from app.security.tokens import AuthError, Principal, require_permission

router = APIRouter(tags=["Phase 16 - Production Operations"])


# ============================================================
# 1. OPERATIONS & SYSTEM STATUS
# ============================================================

@router.get("/api/v1/operations/status")
def get_operations_status() -> dict[str, Any]:
    """Counts from this process's in-memory registries (lost on restart); nothing is asserted beyond that."""
    ingest = get_ingestion_orchestrator()
    fresh = get_freshness_engine()
    models = get_model_serving_engine()
    alerts = get_alerting_engine()
    jobs = get_job_manager()

    active_alerts = alerts.list_alerts(status="ACTIVE")
    critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]

    return {
        "status": "DEGRADED" if critical_alerts else "NO_CRITICAL_ALERTS",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_scope": "PROCESS_LOCAL_IN_MEMORY",
        "active_ingestion_runs": len(ingest.list_runs()),
        "registered_freshness_entities": len(fresh.list_snapshots()),
        "active_models": len([m for m in models.list_models() if m.deployment_state == DeploymentState.ACTIVE]),
        "active_alerts_count": len(active_alerts),
        "critical_alerts_count": len(critical_alerts),
        "running_jobs_count": len(jobs.list_jobs(status=JobStatus.RUNNING)),
    }


async def _component_health(session: AsyncSession) -> dict[str, dict[str, Any]]:
    readiness = await check_readiness(session)
    models = await check_model_health()
    return {
        "database": {"status": readiness["database"]["status"], "latency_ms": readiness["database"]["latency_ms"]},
        "object_storage": {"status": readiness["snapshot_storage"]["status"], "backend": readiness["snapshot_storage"].get("backend")},
        "model_serving": {"status": models["status"], "artifacts": len(models["artifacts"])},
        # No cache server, worker pool or rate-limit gateway exists in this codebase: say so rather than invent numbers.
        "redis_cache": {"status": "NOT_CONFIGURED"},
        "background_workers": {"status": "NOT_CONFIGURED", "detail": "jobs are tracked in memory; no worker pool exists"},
        "provider_gateway": {"status": "UNKNOWN", "detail": "provider availability is not probed"},
    }


@router.get("/api/v1/operations/health")
async def get_operations_health(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Measured component health (database, storage, model artifacts); unmeasured components say so."""
    components = await _component_health(session)
    return {
        "overall_health": aggregate_status({name: c["status"] for name, c in components.items()}),
        "components": components,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/system/status")
async def get_system_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Unified status derived from the same measured checks (no hard-coded 'HEALTHY')."""
    from app.config import get_settings

    components = await _component_health(session)
    return {
        "status": aggregate_status({name: c["status"] for name, c in components.items()}),
        "version": "1.0.0-phase16",
        "environment": get_settings().environment,
        "services": {name: c["status"] for name, c in components.items()},
    }


# ============================================================
# 2. ALERTS & NOTIFICATIONS
# ============================================================

@router.get("/api/v1/operations/alerts", response_model=list[OperationalAlert])
def list_operational_alerts(
    severity: str | None = None,
    status: str | None = None,
) -> list[OperationalAlert]:
    engine = get_alerting_engine()
    sev_enum = AlertSeverity(severity.upper()) if severity else None
    return engine.list_alerts(severity=sev_enum, status=status)


@router.post("/api/v1/operations/alerts/{alert_id}/acknowledge", response_model=OperationalAlert)
def acknowledge_alert(alert_id: str, _: Principal = Depends(require("data:write"))) -> OperationalAlert:
    try:
        return get_alerting_engine().acknowledge_alert(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/operations/alerts/{alert_id}/resolve", response_model=OperationalAlert)
def resolve_alert(alert_id: str, _: Principal = Depends(require("data:write"))) -> OperationalAlert:
    try:
        return get_alerting_engine().resolve_alert(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ============================================================
# 3. BACKGROUND JOBS
# ============================================================

class JobEnqueueRequest(BaseModel):
    job_id: str
    job_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3


@router.get("/api/v1/operations/jobs", response_model=list[ProductionJob])
def list_background_jobs(status: str | None = None) -> list[ProductionJob]:
    mgr = get_job_manager()
    st_enum = JobStatus(status.upper()) if status else None
    return mgr.list_jobs(status=st_enum)


@router.post("/api/v1/operations/jobs", response_model=ProductionJob)
def enqueue_background_job(body: JobEnqueueRequest, _: Principal = Depends(require("data:write"))) -> ProductionJob:
    mgr = get_job_manager()
    return mgr.enqueue_job(
        job_id=body.job_id,
        job_type=body.job_type,
        parameters=body.parameters,
        max_retries=body.max_retries,
    )


@router.post("/api/v1/operations/jobs/{job_id}/start", response_model=ProductionJob)
def start_job(job_id: str, _: Principal = Depends(require("data:write"))) -> ProductionJob:
    try:
        return get_job_manager().start_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/operations/jobs/{job_id}/complete", response_model=ProductionJob)
def complete_job(job_id: str, result_ref: str = "result_done", _: Principal = Depends(require("data:write"))) -> ProductionJob:
    try:
        return get_job_manager().complete_job(job_id, result_reference=result_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ============================================================
# 4. DATA PLANE: PROVIDERS, FRESHNESS, INCIDENTS, READINESS
# ============================================================

@router.get("/api/v1/data/providers", response_model=list[ProviderCapabilityProfile])
def list_provider_profiles() -> list[ProviderCapabilityProfile]:
    return get_provider_orchestrator().list_capabilities()


@router.get("/api/v1/data/freshness", response_model=list[EntityFreshnessSnapshot])
def list_entity_freshness() -> list[EntityFreshnessSnapshot]:
    return get_freshness_engine().list_snapshots()


@router.get("/api/v1/data/incidents", response_model=list[DataQualityIncident])
def list_quality_incidents(status: str | None = None) -> list[DataQualityIncident]:
    st_enum = IncidentStatus(status.upper()) if status else None
    return get_data_quality_engine().list_incidents(status=st_enum)


class IncidentResolveRequest(BaseModel):
    remediation_note: str


@router.post("/api/v1/data/incidents/{incident_id}/resolve", response_model=DataQualityIncident)
def resolve_incident(incident_id: str, body: IncidentResolveRequest, _: Principal = Depends(require("data:write"))) -> DataQualityIncident:
    try:
        return get_data_quality_engine().resolve_incident(incident_id, body.remediation_note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v1/data/readiness")
def get_competition_readiness() -> dict[str, Any]:
    """Readiness is NOT asserted without evidence (the old static matrix claimed PRODUCTION_READY everywhere).

    A competition/capability is only ready with ingested coverage, a MODEL_VALIDATED artifact,
    calibration evidence and a recorded release approval. None of that is wired to this endpoint yet,
    so every competition is NOT_ASSESSED; the model evidence that does exist is listed below.
    """
    return {
        "status": "NOT_ASSESSED",
        "competitions": {},
        "model_evidence": {
            r["name"] + ":" + r["version"]: {"status": r["status"], "artifact_hash": r["artifact_hash"]}
            for r in governance_registry.list_all_models()
        },
        "reason": "No automated per-competition readiness assessment is implemented.",
        "governance_rule": "No competition may inherit readiness from another competition.",
    }


# ============================================================
# 5. MODEL SERVING & GOVERNANCE
# ============================================================

@router.get("/api/v1/models/production", response_model=list[ModelServingProfile])
def list_production_models() -> list[ModelServingProfile]:
    """Registered artifacts with hash-integrity and release status (derived from the registry, not seeded)."""
    return get_model_serving_engine().list_models()


@router.get("/api/v1/models/health")
async def get_model_health_overview() -> dict[str, Any]:
    """Measured artifact health + process-local inference telemetry. Unmeasured signals are None."""
    health = await check_model_health()
    return {
        "health_state": health["status"],
        "artifacts": health["artifacts"],
        "inference_telemetry": get_model_serving_engine().telemetry.snapshot(),
        "population_stability_index": None,
        "feature_missingness_pct": None,
        "ood_rate_pct": None,
        "calibration_status": None,
        "note": "PSI, missingness, OOD and calibration monitoring are not implemented; they are reported as null, not estimated.",
    }


@router.get("/api/v1/models/drift")
def get_model_drift_overview() -> dict[str, Any]:
    return {
        "status": "NOT_MEASURED",
        "drift_detected": None,
        "features_monitored": 0,
        "psi_by_feature": {},
        "reason": "No drift monitor exists: it needs a stored training-distribution reference and a window of production feature vectors.",
    }


@router.get("/api/v1/models/challengers")
def list_challengers() -> list[dict[str, Any]]:
    models = get_model_serving_engine().list_models()
    challengers = [m for m in models if m.deployment_state in (DeploymentState.SHADOW, DeploymentState.CANARY)]
    return [
        {
            "model_id": c.model_id,
            "model_version": c.model_version,
            "deployment_state": c.deployment_state.value,
            "canary_weight_percent": c.canary_weight_percent,
            "calibration_state": c.calibration_state,
        }
        for c in challengers
    ]


class ModelPromoteRequest(BaseModel):
    domain: str
    model_key: str  # registry model_id


@router.post("/api/v1/models/promote")
def promote_model(body: ModelPromoteRequest, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    """Human-governed promotion: caller must hold model:promote; only a MODEL_VALIDATED, hash-verified model is promotable."""
    org = principal.org_id or "unscoped"
    try:
        require_permission(principal, "model:promote")
    except AuthError as exc:
        get_audit_logger().log_event(
            event_type="UNAUTHORIZED_MODEL_PROMOTION_ATTEMPT",
            actor=principal.user_id,
            resource=body.model_key,
            details={"error": exc.detail},
            organization_id=org,
        )
        raise HTTPException(status_code=403, detail=exc.detail) from exc

    try:
        profile = get_model_serving_engine().promote(body.domain, body.model_key)
    except ModelUnavailableError as exc:
        get_audit_logger().log_event(
            event_type="MODEL_PROMOTION_REFUSED",
            actor=principal.user_id,
            resource=body.model_key,
            details={"code": exc.code, "detail": exc.detail},
            organization_id=org,
        )
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "detail": exc.detail}) from exc

    get_audit_logger().log_event(
        event_type="MODEL_PROMOTION",
        actor=principal.user_id,
        resource=body.model_key,
        details={"domain": body.domain, "artifact_sha256": profile.artifact_sha256},
        organization_id=org,
    )
    return {"status": "PROMOTED", "domain": body.domain, "model_key": body.model_key, "artifact_sha256": profile.artifact_sha256}


class PredictionRequest(BaseModel):
    """No defaults: competition and the full feature mapping must be supplied by the caller."""

    domain: str = "valuation"
    competition: str
    position: str | None = None
    as_of: str | None = None
    features: dict[str, Any]


@router.post("/api/v1/models/predict")
def serve_prediction(body: PredictionRequest) -> dict[str, Any]:
    """Served by the real artifact, or refused with a machine-readable reason (never a formula)."""
    try:
        response = get_model_serving_engine().serve_inference(
            domain=body.domain,
            features=body.features,
            competition=body.competition,
            position=body.position,
            as_of=body.as_of,
        )
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "detail": exc.detail}) from exc
    return {"production_prediction": response.model_dump(), "shadow_challenger": None}


# ============================================================
# 6. DECISIONS FRESHNESS & REVIEW REQUIRED
# ============================================================

@router.get("/api/v1/decisions/freshness")
def list_decisions_freshness() -> list[dict[str, Any]]:
    fresh_mgr = get_freshness_engine()
    snaps = fresh_mgr.list_snapshots()
    dec_snaps = [s for s in snaps if s.entity_type == "DECISION"]
    return [s.model_dump() for s in dec_snaps]


@router.get("/api/v1/decisions/review-required")
def list_decisions_review_required() -> list[dict[str, Any]]:
    fresh_mgr = get_freshness_engine()
    snaps = fresh_mgr.list_snapshots()
    review_snaps = [s for s in snaps if s.entity_type == "DECISION" and s.requires_review]
    return [
        {
            "decision_id": s.entity_id,
            "freshness_state": s.freshness_state.value,
            "requires_review": s.requires_review,
            "stale_reasons": s.stale_reasons,
            "last_validated_at": s.last_validated_at,
        }
        for s in review_snaps
    ]


# ============================================================
# 7. PROJECTS & WORKSPACES  (identity from the verified token; org-scoped)
# ============================================================

class ProjectCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str
    target_position: str
    target_role: str
    budget_eur: float | None = None
    competition_scope: list[str] = Field(default_factory=list)


@router.get("/api/v1/projects", response_model=list[RecruitmentProject])
def list_projects(principal: Principal = Depends(get_principal)) -> list[RecruitmentProject]:
    return get_project_auth_manager().list_projects_for(principal)


@router.post("/api/v1/projects", response_model=RecruitmentProject)
def create_project(body: ProjectCreateRequest, principal: Principal = Depends(require("project:manage"))) -> RecruitmentProject:
    if principal.org_id is None:
        raise HTTPException(status_code=403, detail="token carries no organisation; cannot create an org-scoped project")
    try:
        proj = get_project_auth_manager().create_project(
            project_id=body.project_id,
            org_id=principal.org_id,
            name=body.name,
            description=body.description,
            target_position=body.target_position,
            target_role=body.target_role,
            budget_eur=body.budget_eur,
            competition_scope=body.competition_scope,
            lead_scout_id=principal.user_id,
        )
    except DuplicateIdError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_audit_logger().log_event(
        event_type="PROJECT_CREATED",
        actor=principal.user_id,
        resource=body.project_id,
        details={"name": body.name, "target_role": body.target_role},
        organization_id=principal.org_id,
    )
    return proj


# ============================================================
# 8. WATCHLISTS  (private to their owner)
# ============================================================

class WatchlistCreateRequest(BaseModel):
    watchlist_id: str
    name: str
    description: str = ""


class WatchlistItemAddRequest(BaseModel):
    item_id: str
    entity_type: str
    entity_id: str
    entity_name: str
    initial_state: dict[str, Any] = Field(default_factory=dict)


class WatchlistItemEvaluateRequest(BaseModel):
    new_state: dict[str, Any]
    evidence: list[str] = Field(default_factory=list)


@router.get("/api/v1/watchlists", response_model=list[ProductionWatchlist])
def list_watchlists(principal: Principal = Depends(get_principal)) -> list[ProductionWatchlist]:
    return get_project_auth_manager().list_watchlists_for(principal)


@router.post("/api/v1/watchlists", response_model=ProductionWatchlist)
def create_watchlist(body: WatchlistCreateRequest, principal: Principal = Depends(get_principal)) -> ProductionWatchlist:
    try:
        wl = get_project_auth_manager().create_watchlist(
            watchlist_id=body.watchlist_id,
            user_id=principal.user_id,
            org_id=principal.org_id or "unscoped",
            name=body.name,
            description=body.description,
        )
    except DuplicateIdError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_audit_logger().log_event(
        event_type="WATCHLIST_CREATED",
        actor=principal.user_id,
        resource=body.watchlist_id,
        details={"name": body.name},
        organization_id=principal.org_id or "unscoped",
    )
    return wl


@router.post("/api/v1/watchlists/{watchlist_id}/items", response_model=WatchlistItem)
def add_watchlist_item(watchlist_id: str, body: WatchlistItemAddRequest, principal: Principal = Depends(get_principal)) -> WatchlistItem:
    mgr = get_project_auth_manager()
    try:
        mgr.get_watchlist_for(principal, watchlist_id)  # 404 for missing AND for someone else's watchlist
        return mgr.add_watchlist_item(
            watchlist_id=watchlist_id,
            item_id=body.item_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            entity_name=body.entity_name,
            initial_state=body.initial_state,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/watchlists/{watchlist_id}/items/{item_id}/evaluate", response_model=WatchlistItem)
def evaluate_watchlist_item(
    watchlist_id: str,
    item_id: str,
    body: WatchlistItemEvaluateRequest,
    principal: Principal = Depends(get_principal),
) -> WatchlistItem:
    mgr = get_project_auth_manager()
    try:
        mgr.get_watchlist_for(principal, watchlist_id)
        item = mgr.evaluate_watchlist_item(
            watchlist_id=watchlist_id,
            item_id=item_id,
            new_state=body.new_state,
            evidence=body.evidence,
        )
        if item.change:
            get_alerting_engine().emit_alert(
                category="PLAYER_BREAKOUT" if item.entity_type == "PLAYER" else "SYSTEM_FAILURE",
                severity=AlertSeverity.MEDIUM,
                source="watchlist_evaluation",
                title=f"Watchlist Change: {item.entity_name}",
                description=item.change,
                evidence=item.evidence,
            )
        return item
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ============================================================
# 9. AUDIT LOG (APPEND-ONLY, ADMIN ONLY)
# ============================================================

@router.get("/api/v1/audit", response_model=list[AuditEvent])
def list_audit_trail(event_type: str | None = None, _: Principal = Depends(require("admin:access"))) -> list[AuditEvent]:
    return get_audit_logger().list_events(event_type=event_type)


# ============================================================
# 10. COPILOT V6 OPERATIONAL DISPATCH
# ============================================================

class CopilotOperationalRequest(BaseModel):
    query: str
    context: dict[str, Any] | None = None


@router.post("/api/v1/operations/copilot", response_model=CopilotV6Response)
def dispatch_copilot_v6(body: CopilotOperationalRequest) -> CopilotV6Response:
    copilot = get_copilot_v6()
    return copilot.dispatch(query=body.query, context=body.context)
