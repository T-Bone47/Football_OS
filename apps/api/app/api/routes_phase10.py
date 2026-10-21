"""Phase 10 — Operational Intelligence API Routes.

Exposes REST endpoints for:
  - Controlled recurring ingestion & run telemetry (§2, §3)
  - Competition readiness & governance (§4, §5)
  - Persistent recruitment projects & candidate shortlist lifecycle (§6, §7, §8)
  - Persistent watchlists & governed non-causal alerts (§9, §10)
  - Multi-alternative scenarios & match simulation contract (§11, §12)
  - Immutable decision records & cryptographic verification (§13)
  - 14-section evidence-backed report generation (§14)
  - Project-aware Scout Copilot queries (§15)
  - Model lifecycle governance & data change impact analysis (§16, §17)
"""
from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.demo_gate import require_demo_data
from app.config import get_settings
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.db.session import get_session
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.factory import build_snapshot_store
from app.ingestion.service import IngestionService
from app.phase10.competition_readiness import competition_manager
from app.phase10.copilot_extension import copilot_dispatcher
from app.phase10.decision_records import decision_store
from app.phase10.model_lifecycle import model_lifecycle
from app.phase10.operational_ingestion import cycle_view, sha256_from_location, validate_provider_params
from app.phase10.recruitment_projects import recruitment_manager
from app.phase10.reports import generate_recruitment_report, render_report_markdown
from app.phase10.scenarios import scenario_engine
from app.phase10.watchlists import AlertChangeType, watchlist_engine
from app.providers.registry import default_registry
from app.security.deps import get_principal, require
from app.security.tokens import Principal

router = APIRouter(prefix="/api/phase10", tags=["Phase 10 Operational Intelligence"])


# ── Schemas ─────────────────────────────────────────────────────────

class IngestionTriggerRequest(BaseModel):
    """No default provider/resource and NO caller-supplied payload: Bronze only ever holds bytes a
    registered provider actually returned (the old `payload` field let any caller write Bronze)."""

    provider: str
    resource: str
    params: dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    """Required: name, club, season, position, target_role. Everything else stays unset (None) unless given;
    the old defaults (Arsenal, CB, 4-3-3, EUR 40M, ages 18-30, EPL/LaLiga, 900 minutes) were invented context."""

    name: str
    club: str
    season: str
    position: str
    target_role: str
    formation: str | None = None
    budget_eur: float | None = None
    min_age: int | None = None
    max_age: int | None = None
    risk_tolerance: str | None = None
    competition_constraints: list[str] = Field(default_factory=list)
    min_minutes_played: int | None = None


class CandidateAddRequest(BaseModel):
    """Identity is required. Every other value is optional and recorded as USER_SUPPLIED when given; the old
    defaults (age 24, EUR 25M, fit 80, contribution 75, risk 0.30, EPL, CB) were invented player attributes."""

    candidate_id: str | None = None
    player_id: str
    player_name: str
    current_club: str | None = None
    current_competition: str | None = None
    position: str | None = None
    age: int | None = None
    estimated_value_eur: float | None = None
    tactical_fit_score: float | None = None
    contribution_rating: float | None = None
    overall_risk_score: float | None = None
    role_compatibility: float | None = None
    scout_notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CandidateStateUpdateRequest(BaseModel):
    new_state: str  # DISCOVERED, REVIEWING, SHORTLISTED, SCENARIO_TESTED, DECISION_RECORDED, ARCHIVED


class CandidateAnnotateRequest(BaseModel):
    notes: list[str] | None = None
    tags: list[str] | None = None
    priority: str | None = None


class CandidateCompareRequest(BaseModel):
    candidate_ids: list[str]


class WatchlistCreateRequest(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class WatchlistItemAddRequest(BaseModel):
    entity_type: str = "PLAYER"
    entity_id: str
    entity_name: str
    current_value_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class WatchlistEvaluateRequest(BaseModel):
    entity_id: str
    entity_name: str
    metric_name: str
    previous_val: float
    new_val: float
    change_type: str = "performance_change"


class ScenarioCreateRequest(BaseModel):
    project_id: str
    name: str
    scenario_type: str = "SELL_BUY"
    assumptions: list[str] = Field(default_factory=list)
    movements: list[dict[str, Any]] = Field(default_factory=list)


class DecisionRecordRequest(BaseModel):
    """The signer is the authenticated user and confidence/status are never caller-asserted, so none of
    those are accepted here (the old request took a free-text `signed_by` like "Head of Recruitment")."""

    project_id: str
    project_name: str = ""
    chosen_candidate_id: str
    chosen_candidate_name: str = ""
    decision_type: str
    candidate_set: list[dict[str, Any]] = Field(default_factory=list)
    project_constraints: dict[str, Any] = Field(default_factory=dict)
    scenario_assumptions: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    feature_set_version: str = ""


class CopilotProjectQueryRequest(BaseModel):
    query: str
    project_id: str


# ── 1. Operational Ingestion Endpoints ───────────────────────────────

def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


async def _cycle_views(session: AsyncSession, runs: list[tuple[IngestionRun, str]]) -> list[dict[str, Any]]:
    snapshots: dict[Any, DataSnapshot] = {}
    if runs:
        rows = await session.execute(select(DataSnapshot).where(DataSnapshot.ingestion_run_id.in_([r.id for r, _ in runs])))
        snapshots = {snap.ingestion_run_id: snap for snap in rows.scalars()}
    views = []
    for run, provider in runs:
        snap = snapshots.get(run.id)
        views.append(
            cycle_view(
                run_id=str(run.id),
                provider=provider,
                resource=run.endpoint,
                run_status=_enum_value(run.status),
                error=run.error,
                started_at=run.started_at,
                finished_at=run.finished_at,
                record_count=run.record_count,
                snapshot=None
                if snap is None
                else {
                    "sha256": sha256_from_location(snap.storage_location),
                    "size_bytes": snap.size_bytes,
                    "validation_status": _enum_value(snap.validation_status),
                    "validation_errors": snap.validation_errors,
                },
            )
        )
    return views


@router.post("/operations/ingestion/trigger")
async def trigger_ingestion(
    req: IngestionTriggerRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require("data:write")),
) -> dict[str, Any]:
    """Runs the REAL ingestion service (capability gate, provider fetch, Bronze snapshot, validation)."""
    try:
        params = validate_provider_params(req.params)
        service = IngestionService(
            session=session,
            provider_registry=default_registry,
            snapshot_store=build_snapshot_store(get_settings()),
            capability_registry=CapabilityRegistry(session),
        )
        run = await service.run(req.provider, req.resource, **params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return (await _cycle_views(session, [(run, req.provider)]))[0]


@router.get("/operations/ingestion/runs")
async def list_ingestion_runs(
    limit: int = Query(50, ge=1, le=200), session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(IngestionRun, DataSource.name)
        .join(DataSource, DataSource.id == IngestionRun.data_source_id)
        .order_by(IngestionRun.started_at.desc().nullslast())
        .limit(limit)
    )
    return await _cycle_views(session, [(run, name) for run, name in rows.all()])


@router.get("/operations/ingestion/runs/{run_id}")
async def get_ingestion_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = (
        await session.execute(
            select(IngestionRun, DataSource.name)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .where(IngestionRun.id == run_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return (await _cycle_views(session, [(row[0], row[1])]))[0]


# ── 2. Competition Readiness Endpoints ───────────────────────────────

@router.get("/operations/competition-readiness")
def list_competition_readiness() -> list[dict[str, Any]]:
    return competition_manager.list_all()


@router.get("/operations/competition-readiness/{code}")
def get_competition_readiness(code: str) -> dict[str, Any]:
    return competition_manager.get_profile(code)


# ── Access helpers: every object is checked against the verified principal; 404 hides other tenants' objects ──

def _project_for(principal: Principal, project_id: str):
    try:
        return recruitment_manager.get_project_for(principal, project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


def _watchlist_for(principal: Principal, watchlist_id: str):
    try:
        return watchlist_engine.get_watchlist_for(principal, watchlist_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc


# ── 3. Recruitment Projects Endpoints ────────────────────────────────

@router.get("/recruitment/projects")
def list_recruitment_projects(principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return [p.to_dict() for p in recruitment_manager.list_projects_for(principal)]


@router.post("/recruitment/projects")
def create_recruitment_project(req: ProjectCreateRequest, principal: Principal = Depends(require("project:manage"))) -> dict[str, Any]:
    try:
        p = recruitment_manager.create_project(req.model_dump(), owner_id=principal.user_id, organization_id=principal.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return p.to_dict()


@router.get("/recruitment/projects/{project_id}")
def get_recruitment_project(project_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    return _project_for(principal, project_id).to_dict()


@router.post("/recruitment/projects/{project_id}/candidates")
def add_project_candidate(project_id: str, req: CandidateAddRequest, principal: Principal = Depends(require("project:manage"))) -> dict[str, Any]:
    _project_for(principal, project_id)
    try:
        c = recruitment_manager.add_candidate(project_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return c.to_dict()


@router.put("/recruitment/projects/{project_id}/candidates/{candidate_id}/state")
def update_candidate_state(
    project_id: str, candidate_id: str, req: CandidateStateUpdateRequest, principal: Principal = Depends(require("project:manage"))
) -> dict[str, Any]:
    _project_for(principal, project_id)
    c = recruitment_manager.update_candidate_state(project_id, candidate_id, req.new_state)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate or Project not found")
    return c.to_dict()


@router.post("/recruitment/projects/{project_id}/candidates/{candidate_id}/annotate")
def annotate_candidate(
    project_id: str, candidate_id: str, req: CandidateAnnotateRequest, principal: Principal = Depends(require("project:manage"))
) -> dict[str, Any]:
    _project_for(principal, project_id)
    c = recruitment_manager.annotate_candidate(project_id, candidate_id, notes=req.notes, tags=req.tags, priority=req.priority)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate or Project not found")
    return c.to_dict()


@router.delete("/recruitment/projects/{project_id}/candidates/{candidate_id}")
def remove_candidate(project_id: str, candidate_id: str, principal: Principal = Depends(require("project:manage"))) -> dict[str, Any]:
    _project_for(principal, project_id)
    if not recruitment_manager.remove_candidate(project_id, candidate_id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True}


@router.post("/recruitment/projects/{project_id}/compare")
def compare_candidates(project_id: str, req: CandidateCompareRequest, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    _project_for(principal, project_id)
    res = recruitment_manager.compare_candidates(project_id, req.candidate_ids)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# ── 4. Watchlists & Alerts Endpoints (private to their owner) ────────

@router.get("/watchlists")
def list_watchlists(principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return watchlist_engine.list_watchlists_for(principal)


@router.post("/watchlists")
def create_watchlist(req: WatchlistCreateRequest, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    try:
        w = watchlist_engine.create_watchlist(
            req.name, req.description, req.tags, owner_id=principal.user_id, organization_id=principal.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return w.to_dict()


@router.get("/watchlists/alerts")
def list_alerts(
    watchlist_id: str | None = None,
    entity_id: str | None = None,
    change_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    visible = {w["watchlist_id"] for w in watchlist_engine.list_watchlists_for(principal)}
    return watchlist_engine.list_alerts(
        watchlist_id=watchlist_id, entity_id=entity_id, change_type=change_type, limit=limit, watchlist_ids=visible
    )


@router.post("/watchlists/{watchlist_id}/items")
def add_watchlist_item(watchlist_id: str, req: WatchlistItemAddRequest, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    _watchlist_for(principal, watchlist_id)
    try:
        item = watchlist_engine.add_item(watchlist_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return item.to_dict()


@router.delete("/watchlists/{watchlist_id}/items/{item_id}")
def remove_watchlist_item(watchlist_id: str, item_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    _watchlist_for(principal, watchlist_id)
    if not watchlist_engine.remove_item(watchlist_id, item_id):
        raise HTTPException(status_code=404, detail="Item or Watchlist not found")
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/evaluate")
def evaluate_watchlist_change(
    watchlist_id: str, req: WatchlistEvaluateRequest, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    _watchlist_for(principal, watchlist_id)
    ctype = AlertChangeType.PERFORMANCE_CHANGE
    for member in AlertChangeType:
        if member.value.lower() == req.change_type.lower():
            ctype = member
            break
    alert = watchlist_engine.evaluate_change(
        watchlist_id=watchlist_id,
        entity_id=req.entity_id,
        entity_name=req.entity_name,
        metric_name=req.metric_name,
        previous_val=req.previous_val,
        new_val=req.new_val,
        change_type=ctype,
    )
    if not alert:
        return {"status": "NO_SIGNIFICANT_CHANGE", "alert": None}
    return {"status": "ALERT_RECORDED", "alert": alert.to_dict()}


# ── 5. Scenarios Endpoints (arithmetic on user-entered figures only) ─

@router.get("/scenarios")
def list_scenarios(project_id: str | None = None, principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return scenario_engine.list_scenarios_for(principal, project_id=project_id)


@router.post("/scenarios")
def create_scenario(req: ScenarioCreateRequest, principal: Principal = Depends(require("scenario:simulate"))) -> dict[str, Any]:
    _project_for(principal, req.project_id)
    try:
        s = scenario_engine.create_scenario(
            req.project_id, req.model_dump(), owner_id=principal.user_id, organization_id=principal.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return s.to_dict()


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    try:
        return scenario_engine.get_scenario_for(principal, scenario_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Scenario not found") from exc


# ── 6. Decision Records Endpoints (hash-chained evidence records) ────

@router.get("/decisions/records")
def list_decision_records(project_id: str | None = None, principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return decision_store.list_decisions_for(principal, project_id=project_id)


@router.post("/decisions/records")
def record_decision(req: DecisionRecordRequest, principal: Principal = Depends(require("decision:create"))) -> dict[str, Any]:
    _project_for(principal, req.project_id)
    try:
        rec = decision_store.record_decision(req.model_dump(), signed_by=principal.user_id, organization_id=principal.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return rec.to_dict()


def _decision_for(principal: Principal, decision_id: str):
    try:
        return decision_store.get_decision_for(principal, decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Decision record not found") from exc


@router.get("/decisions/records/{decision_id}")
def get_decision_record(decision_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    return _decision_for(principal, decision_id).to_dict()


@router.get("/decisions/records/{decision_id}/verify")
def verify_decision_record(decision_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    _decision_for(principal, decision_id)
    verified, msg = decision_store.verify_integrity(decision_id)
    return {"verified": verified, "message": msg}


# ── 7. Reports Endpoints ─────────────────────────────────────────────

@router.get("/recruitment/projects/{project_id}/report")
def get_project_report(project_id: str, format: str = "json", principal: Principal = Depends(get_principal)) -> Any:
    project = _project_for(principal, project_id)
    rep = generate_recruitment_report(
        project,
        scenarios=scenario_engine.list_scenarios_for(principal, project_id),
        decisions=decision_store.list_decisions_for(principal, project_id),
    )
    if format == "markdown":
        return {"markdown": render_report_markdown(rep)}
    return rep


# ── 8. Scout Copilot Project Query Endpoint ──────────────────────────

@router.post("/copilot/project-query")
def copilot_project_query(req: CopilotProjectQueryRequest, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    res = copilot_dispatcher.dispatch_query(req.query, project_id=req.project_id, principal=principal)
    if "error" in res and res["error"].startswith("Project '"):
        raise HTTPException(status_code=404, detail="Project not found")
    return res


# ── 9. Model Lifecycle & Impact Endpoints ────────────────────────────

@router.get("/models/lifecycle", dependencies=[Depends(require_demo_data)])
def list_models_lifecycle() -> list[dict[str, Any]]:
    return model_lifecycle.list_models()


@router.post("/models/impact-analysis", dependencies=[Depends(require_demo_data)])
def analyze_model_impact(records_count: int = 10, provider: str = "api-football") -> dict[str, Any]:
    rep = model_lifecycle.analyze_data_impact(records_count, source_provider=provider)
    return rep.to_dict()
