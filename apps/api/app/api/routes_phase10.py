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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.operations import JobRun, OpsUser
from app.db.session import get_session
from app.ingestion.factory import build_snapshot_store
from app.phase17.audit import append_event
from app.phase17.auth import require
from app.phase17.live_ingestion import LiveIngestionRunner
from app.phase17.readiness import competition_readiness

from app.phase10.copilot_extension import copilot_dispatcher
from app.phase10.decision_records import decision_store
from app.phase10.model_lifecycle import model_lifecycle
from app.phase10.recruitment_projects import recruitment_manager
from app.phase10.reports import generate_recruitment_report, render_report_markdown
from app.phase10.scenarios import scenario_engine
from app.phase10.watchlists import AlertChangeType, watchlist_engine

router = APIRouter(prefix="/api/phase10", tags=["Phase 10 Operational Intelligence"])


# ── Schemas ─────────────────────────────────────────────────────────

class IngestionTriggerRequest(BaseModel):
    """Phase 18 (R4): a trigger names what to fetch; it can never carry the
    data. Unknown fields such as `payload` are rejected (422)."""
    model_config = ConfigDict(extra="forbid")

    provider: str
    resource: str
    params: dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    project_id: str | None = None
    name: str
    club: str = "Arsenal"
    season: str = "2024/2025"
    position: str = "CB"
    target_role: str = "Ball Playing Defender"
    formation: str = "4-3-3"
    budget_eur: float = 40_000_000.0
    min_age: int = 18
    max_age: int = 30
    risk_tolerance: str = "MODERATE"
    competition_constraints: list[str] = Field(default_factory=lambda: ["EPL", "LaLiga"])
    min_minutes_played: int = 900


class CandidateAddRequest(BaseModel):
    candidate_id: str | None = None
    player_id: str
    player_name: str
    current_club: str
    current_competition: str = "EPL"
    position: str = "CB"
    age: int = 24
    estimated_value_eur: float = 25_000_000.0
    tactical_fit_score: float = 80.0
    contribution_rating: float = 75.0
    overall_risk_score: float = 0.30
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
    project_id: str
    project_name: str
    chosen_candidate_id: str
    chosen_candidate_name: str
    decision_type: str = "TARGET_SIGNING"
    candidate_set: list[dict[str, Any]] = Field(default_factory=list)
    project_constraints: dict[str, Any] = Field(default_factory=dict)
    scenario_assumptions: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    signed_by: str = "Head of Recruitment"


class CopilotProjectQueryRequest(BaseModel):
    query: str
    project_id: str = "proj_cb_summer_2027"


# ── 1. Operational Ingestion Endpoints ───────────────────────────────

@router.post("/operations/ingestion/trigger")
async def trigger_ingestion(req: IngestionTriggerRequest, user: OpsUser = Depends(require("ingestion:run")),
                            session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Runs the real pipeline: provider request, contract check, SHA-256
    Bronze snapshot, Silver. A blocked or failing provider is reported as
    such (FAILED with the provider error); nothing is written in its place."""
    runner = LiveIngestionRunner(session, build_snapshot_store(get_settings()))
    result = await runner.run_job(req.provider, req.resource, req.params)
    await append_event(session, "INGESTION_JOB", str(user.id), f"{req.provider}/{req.resource}",
                       {"status": result.status, "snapshot": result.snapshot_sha256, "via": "phase10"}, commit=True)
    return result.to_dict()


@router.get("/operations/ingestion/runs")
async def list_ingestion_runs(limit: int = Query(50, le=500), _: OpsUser = Depends(require("ops:read")),
                              session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(limit))).scalars().all()
    return [_job_dict(j) for j in rows]


@router.get("/operations/ingestion/runs/{run_id}")
async def get_ingestion_run(run_id: uuid.UUID, _: OpsUser = Depends(require("ops:read")),
                            session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await session.get(JobRun, run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _job_dict(job)


def _job_dict(j: JobRun) -> dict[str, Any]:
    return {"id": str(j.id), "job_name": j.job_name, "provider": j.provider, "resource": j.resource,
            "parameters": j.parameters, "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "records": j.records, "errors": j.errors, "snapshot_sha256": j.snapshot_sha256}


# ── 2. Competition Readiness Endpoints ───────────────────────────────
# Phase 18 (R7): one readiness engine (app.phase17.readiness), read from
# PostgreSQL. The declared Phase 10 profiles are no longer served.

@router.get("/operations/competition-readiness")
async def list_competition_readiness(_: OpsUser = Depends(require("ops:read")),
                                     session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await competition_readiness(session)


@router.get("/operations/competition-readiness/{code}")
async def get_competition_readiness(code: str, _: OpsUser = Depends(require("ops:read")),
                                    session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    for row in await competition_readiness(session):
        # `code` is the competition's display name or one of its competition-season ids.
        if code.lower() == str(row["competition"]).lower() or code in row["competition_season_ids"]:
            return row
    raise HTTPException(status_code=404, detail="No readiness record for this competition")


# ── 3. Recruitment Projects Endpoints ────────────────────────────────

@router.get("/recruitment/projects")
def list_recruitment_projects() -> list[dict[str, Any]]:
    return recruitment_manager.list_projects()


@router.post("/recruitment/projects")
def create_recruitment_project(req: ProjectCreateRequest) -> dict[str, Any]:
    p = recruitment_manager.create_project(req.model_dump())
    return p.to_dict()


@router.get("/recruitment/projects/{project_id}")
def get_recruitment_project(project_id: str) -> dict[str, Any]:
    p = recruitment_manager.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p.to_dict()


@router.post("/recruitment/projects/{project_id}/candidates")
def add_project_candidate(project_id: str, req: CandidateAddRequest) -> dict[str, Any]:
    c = recruitment_manager.add_candidate(project_id, req.model_dump())
    if not c:
        raise HTTPException(status_code=404, detail="Project not found")
    return c.to_dict()


@router.put("/recruitment/projects/{project_id}/candidates/{candidate_id}/state")
def update_candidate_state(project_id: str, candidate_id: str, req: CandidateStateUpdateRequest) -> dict[str, Any]:
    c = recruitment_manager.update_candidate_state(project_id, candidate_id, req.new_state)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate or Project not found")
    return c.to_dict()


@router.post("/recruitment/projects/{project_id}/candidates/{candidate_id}/annotate")
def annotate_candidate(project_id: str, candidate_id: str, req: CandidateAnnotateRequest) -> dict[str, Any]:
    c = recruitment_manager.annotate_candidate(
        project_id, candidate_id, notes=req.notes, tags=req.tags, priority=req.priority
    )
    if not c:
        raise HTTPException(status_code=404, detail="Candidate or Project not found")
    return c.to_dict()


@router.delete("/recruitment/projects/{project_id}/candidates/{candidate_id}")
def remove_candidate(project_id: str, candidate_id: str) -> dict[str, Any]:
    ok = recruitment_manager.remove_candidate(project_id, candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True}


@router.post("/recruitment/projects/{project_id}/compare")
def compare_candidates(project_id: str, req: CandidateCompareRequest) -> dict[str, Any]:
    res = recruitment_manager.compare_candidates(project_id, req.candidate_ids)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# ── 4. Watchlists & Governed Alerts Endpoints ────────────────────────

@router.get("/watchlists")
def list_watchlists() -> list[dict[str, Any]]:
    return watchlist_engine.list_watchlists()


@router.post("/watchlists")
def create_watchlist(req: WatchlistCreateRequest) -> dict[str, Any]:
    w = watchlist_engine.create_watchlist(req.name, req.description, req.tags)
    return w.to_dict()


@router.get("/watchlists/alerts")
def list_alerts(
    watchlist_id: str | None = None,
    entity_id: str | None = None,
    change_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return watchlist_engine.list_alerts(
        watchlist_id=watchlist_id,
        entity_id=entity_id,
        change_type=change_type,
        limit=limit,
    )


@router.post("/watchlists/{watchlist_id}/items")
def add_watchlist_item(watchlist_id: str, req: WatchlistItemAddRequest) -> dict[str, Any]:
    item = watchlist_engine.add_item(watchlist_id, req.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return item.to_dict()


@router.delete("/watchlists/{watchlist_id}/items/{item_id}")
def remove_watchlist_item(watchlist_id: str, item_id: str) -> dict[str, Any]:
    ok = watchlist_engine.remove_item(watchlist_id, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item or Watchlist not found")
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/evaluate")
def evaluate_watchlist_change(watchlist_id: str, req: WatchlistEvaluateRequest) -> dict[str, Any]:
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


# ── 5. Scenarios Endpoints ───────────────────────────────────────────

@router.get("/scenarios")
def list_scenarios(project_id: str | None = None) -> list[dict[str, Any]]:
    return scenario_engine.list_scenarios(project_id=project_id)


@router.post("/scenarios")
def create_scenario(req: ScenarioCreateRequest) -> dict[str, Any]:
    s = scenario_engine.create_scenario(req.project_id, req.model_dump())
    return s.to_dict()


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict[str, Any]:
    s = scenario_engine.get_scenario(scenario_id)
    if not s:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return s.to_dict()


# ── 6. Decision Records Endpoints ────────────────────────────────────

@router.get("/decisions/records")
def list_decision_records(project_id: str | None = None) -> list[dict[str, Any]]:
    return decision_store.list_decisions(project_id=project_id)


@router.post("/decisions/records")
def record_decision(req: DecisionRecordRequest) -> dict[str, Any]:
    rec = decision_store.record_decision(req.model_dump())
    return rec.to_dict()


@router.get("/decisions/records/{decision_id}")
def get_decision_record(decision_id: str) -> dict[str, Any]:
    rec = decision_store.get_decision(decision_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Decision record not found")
    return rec.to_dict()


@router.get("/decisions/records/{decision_id}/verify")
def verify_decision_record(decision_id: str) -> dict[str, Any]:
    verified, msg = decision_store.verify_integrity(decision_id)
    return {"verified": verified, "message": msg}


# ── 7. Reports Endpoints ─────────────────────────────────────────────

@router.get("/recruitment/projects/{project_id}/report")
def get_project_report(project_id: str, format: str = "json") -> Any:
    rep = generate_recruitment_report(project_id)
    if "error" in rep:
        raise HTTPException(status_code=404, detail=rep["error"])
    if format == "markdown":
        return {"markdown": render_report_markdown(rep)}
    return rep


# ── 8. Scout Copilot Project Query Endpoint ──────────────────────────

@router.post("/copilot/project-query")
def copilot_project_query(req: CopilotProjectQueryRequest) -> dict[str, Any]:
    return copilot_dispatcher.dispatch_query(req.query, project_id=req.project_id)


# ── 9. Model Lifecycle & Impact Endpoints ────────────────────────────

@router.get("/models/lifecycle")
def list_models_lifecycle() -> list[dict[str, Any]]:
    return model_lifecycle.list_models()


@router.post("/models/impact-analysis")
def analyze_model_impact(records_count: int = 10, provider: str = "api-football") -> dict[str, Any]:
    rep = model_lifecycle.analyze_data_impact(records_count, source_provider=provider)
    return rep.to_dict()
