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
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import engine, get_session
from app.phase17.environments import is_hardened, resolve_environment
from app.phase17.model_ops import MODE_LIVE, drift_report, model_health_snapshot
from app.phase17.readiness import competition_readiness
from app.phase17.system_health import system_status

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
    PredictionServingResponse,
    get_model_serving_engine,
)
from app.phase16.projects_and_auth import (
    AuthorizationError,
    ProductionWatchlist,
    RecruitmentProject,
    UserProfile,
    WatchlistItem,
    get_project_auth_manager,
)
from app.phase16.provider_orchestrator import (
    ProviderCapabilityProfile,
    get_provider_orchestrator,
)

router = APIRouter(tags=["Phase 16 - Production Operations"])


def _demo_only() -> None:
    """Phase 17 (reconnaissance R9/R12): Phase 16's mutating routes act on
    in-process memory and trust a user_id in the request body. They remain
    for development/test and are refused in staging/production, where the
    authenticated, persistent equivalents live under /api/v1/ops."""
    if is_hardened(resolve_environment(get_settings().environment)):
        raise HTTPException(status_code=410, detail="Phase 16 in-memory route disabled in this environment; use /api/v1/ops")


DEMO_ONLY = [Depends(_demo_only)]


def _unavailable(exc: Exception) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "reason": f"backend state unreadable: {type(exc).__name__}"}


# ============================================================
# 1. OPERATIONS & SYSTEM STATUS
# ============================================================

@router.get("/api/v1/operations/status")
def get_operations_status() -> dict[str, Any]:
    """Provides high-level operational status across ingestion, models, decisions, and system."""
    ingest = get_ingestion_orchestrator()
    fresh = get_freshness_engine()
    models = get_model_serving_engine()
    alerts = get_alerting_engine()
    jobs = get_job_manager()

    active_alerts = alerts.list_alerts(status="ACTIVE")
    critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]

    return {
        "status": "OPERATIONAL" if not critical_alerts else "DEGRADED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state_source": "IN_MEMORY_PHASE16_ENGINES",
        "active_ingestion_runs": len(ingest.list_runs()),
        "registered_freshness_entities": len(fresh.list_snapshots()),
        "active_models": len([m for m in models.list_models() if m.deployment_state == DeploymentState.ACTIVE]),
        "active_alerts_count": len(active_alerts),
        "critical_alerts_count": len(critical_alerts),
        "running_jobs_count": len(jobs.list_jobs(status=JobStatus.RUNNING)),
        "epistemic_guarantees": "ENFORCED",
    }


@router.get("/api/v1/operations/health")
async def get_operations_health(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Phase 17: real component probes (previously hardcoded, reconnaissance R5)."""
    status = await system_status(session, engine, get_settings())
    return {"overall_health": status["status"], "checked_at": status["checked_at"], "components": status["components"]}


@router.get("/api/v1/system/status")
async def get_system_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Phase 17: real component probes (previously hardcoded, reconnaissance R5)."""
    status = await system_status(session, engine, get_settings())
    return {"status": status["status"], "checked_at": status["checked_at"], "environment": status["environment"],
            "services": {k: (v.get("status") if isinstance(v, dict) and "status" in v else v)
                         for k, v in status["components"].items()}}


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


@router.post("/api/v1/operations/alerts/{alert_id}/acknowledge", response_model=OperationalAlert, dependencies=DEMO_ONLY)
def acknowledge_alert(alert_id: str) -> OperationalAlert:
    try:
        return get_alerting_engine().acknowledge_alert(alert_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/operations/alerts/{alert_id}/resolve", response_model=OperationalAlert, dependencies=DEMO_ONLY)
def resolve_alert(alert_id: str) -> OperationalAlert:
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


@router.post("/api/v1/operations/jobs", response_model=ProductionJob, dependencies=DEMO_ONLY)
def enqueue_background_job(body: JobEnqueueRequest) -> ProductionJob:
    mgr = get_job_manager()
    return mgr.enqueue_job(
        job_id=body.job_id,
        job_type=body.job_type,
        parameters=body.parameters,
        max_retries=body.max_retries,
    )


@router.post("/api/v1/operations/jobs/{job_id}/start", response_model=ProductionJob, dependencies=DEMO_ONLY)
def start_job(job_id: str) -> ProductionJob:
    try:
        return get_job_manager().start_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/operations/jobs/{job_id}/complete", response_model=ProductionJob, dependencies=DEMO_ONLY)
def complete_job(job_id: str, result_ref: str = "result_done") -> ProductionJob:
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


@router.post("/api/v1/data/incidents/{incident_id}/resolve", response_model=DataQualityIncident, dependencies=DEMO_ONLY)
def resolve_incident(incident_id: str, body: IncidentResolveRequest) -> DataQualityIncident:
    try:
        return get_data_quality_engine().resolve_incident(incident_id, body.remediation_note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v1/data/readiness")
async def get_competition_readiness(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Phase 17: computed from the database (previously a hardcoded table, R7)."""
    try:
        return {"competitions": await competition_readiness(session),
                "governance_rule": "No competition may inherit readiness from another competition."}
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc)


# ============================================================
# 5. MODEL SERVING & GOVERNANCE
# ============================================================

@router.get("/api/v1/models/production", response_model=list[ModelServingProfile])
def list_production_models() -> list[ModelServingProfile]:
    return get_model_serving_engine().list_models()


@router.get("/api/v1/models/health")
async def get_model_health_overview(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Phase 17: computed from ops_inference_log (previously hardcoded, R6)."""
    try:
        return await model_health_snapshot(session)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc)


@router.get("/api/v1/models/drift")
async def get_model_drift_overview(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Phase 17: PSI over logged live inferences (previously hardcoded, R6)."""
    try:
        return await drift_report(session, MODE_LIVE)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc)


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
    user_id: str
    domain: str
    model_key: str
    authorization_token: str | None = None


@router.post("/api/v1/models/promote", dependencies=DEMO_ONLY)
def promote_model(body: ModelPromoteRequest) -> dict[str, Any]:
    """Promotes a model to champion with strict authoritative RBAC check."""
    auth_mgr = get_project_auth_manager()
    try:
        auth_mgr.authorize(body.user_id, "model:promote")
    except AuthorizationError as exc:
        # Audit rejected promotion
        get_audit_logger().log_event(
            event_type="UNAUTHORIZED_MODEL_PROMOTION_ATTEMPT",
            actor=body.user_id,
            resource=body.model_key,
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    serving = get_model_serving_engine()
    serving.set_champion(body.domain, body.model_key)

    # Log successful promotion
    get_audit_logger().log_event(
        event_type="MODEL_PROMOTION",
        actor=body.user_id,
        resource=body.model_key,
        details={"domain": body.domain, "new_status": "ACTIVE_CHAMPION"},
    )
    return {"status": "PROMOTED", "domain": body.domain, "model_key": body.model_key}


class PredictionRequest(BaseModel):
    domain: str = "valuation"
    competition: str = "EPL"
    position: str = "MF"
    input_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/models/predict", dependencies=DEMO_ONLY)
def serve_prediction(body: PredictionRequest) -> dict[str, Any]:
    serving = get_model_serving_engine()
    try:
        prod_resp, shadow_resp = serving.serve_inference(
            domain=body.domain,
            input_data=body.input_data,
            competition=body.competition,
            position=body.position,
        )
    except KeyError:
        return {"production_prediction": {"data_status": "MODEL_UNAVAILABLE", "predicted_value": None,
                                          "domain": body.domain},
                "shadow_challenger": None}
    return {
        "production_prediction": prod_resp.model_dump(),
        "shadow_challenger": shadow_resp.model_dump() if shadow_resp else None,
    }


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
# 7. PROJECTS & WORKSPACES
# ============================================================

class ProjectCreateRequest(BaseModel):
    user_id: str
    project_id: str
    org_id: str
    name: str
    description: str
    target_position: str
    target_role: str
    budget_eur: float | None = None
    competition_scope: list[str] = Field(default_factory=list)


@router.get("/api/v1/projects", response_model=list[RecruitmentProject], dependencies=DEMO_ONLY)
def list_projects(org_id: str | None = None) -> list[RecruitmentProject]:
    return get_project_auth_manager().list_projects(org_id=org_id)


@router.post("/api/v1/projects", response_model=RecruitmentProject, dependencies=DEMO_ONLY)
def create_project(body: ProjectCreateRequest) -> RecruitmentProject:
    auth_mgr = get_project_auth_manager()
    try:
        auth_mgr.authorize(body.user_id, "project:manage")
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    proj = auth_mgr.create_project(
        project_id=body.project_id,
        org_id=body.org_id,
        name=body.name,
        description=body.description,
        target_position=body.target_position,
        target_role=body.target_role,
        budget_eur=body.budget_eur,
        competition_scope=body.competition_scope,
        lead_scout_id=body.user_id,
    )
    get_audit_logger().log_event(
        event_type="PROJECT_CREATED",
        actor=body.user_id,
        resource=body.project_id,
        details={"name": body.name, "target_role": body.target_role},
    )
    return proj


# ============================================================
# 8. WATCHLISTS
# ============================================================

class WatchlistCreateRequest(BaseModel):
    user_id: str
    watchlist_id: str
    org_id: str
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


@router.get("/api/v1/watchlists", response_model=list[ProductionWatchlist], dependencies=DEMO_ONLY)
def list_watchlists(user_id: str | None = None) -> list[ProductionWatchlist]:
    return get_project_auth_manager().list_watchlists(user_id=user_id)


@router.post("/api/v1/watchlists", response_model=ProductionWatchlist, dependencies=DEMO_ONLY)
def create_watchlist(body: WatchlistCreateRequest) -> ProductionWatchlist:
    auth_mgr = get_project_auth_manager()
    wl = auth_mgr.create_watchlist(
        watchlist_id=body.watchlist_id,
        user_id=body.user_id,
        org_id=body.org_id,
        name=body.name,
        description=body.description,
    )
    get_audit_logger().log_event(
        event_type="WATCHLIST_CREATED",
        actor=body.user_id,
        resource=body.watchlist_id,
        details={"name": body.name},
    )
    return wl


@router.post("/api/v1/watchlists/{watchlist_id}/items", response_model=WatchlistItem, dependencies=DEMO_ONLY)
def add_watchlist_item(watchlist_id: str, body: WatchlistItemAddRequest) -> WatchlistItem:
    try:
        return get_project_auth_manager().add_watchlist_item(
            watchlist_id=watchlist_id,
            item_id=body.item_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            entity_name=body.entity_name,
            initial_state=body.initial_state,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/watchlists/{watchlist_id}/items/{item_id}/evaluate", response_model=WatchlistItem, dependencies=DEMO_ONLY)
def evaluate_watchlist_item(
    watchlist_id: str,
    item_id: str,
    body: WatchlistItemEvaluateRequest,
) -> WatchlistItem:
    try:
        item = get_project_auth_manager().evaluate_watchlist_item(
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
# 9. AUDIT LOG (APPEND-ONLY)
# ============================================================

@router.get("/api/v1/audit", response_model=list[AuditEvent])
def list_audit_trail(event_type: str | None = None) -> list[AuditEvent]:
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
