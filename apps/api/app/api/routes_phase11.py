"""Phase 11 — Global Data Expansion & Cross-Competition Validation API Routes (§23).

Exposes REST endpoints for:
  - Global competition coverage profiles & readiness stages (§4, §5, §6)
  - Governed readiness state progression (§6, §10)
  - Multi-engine cross-competition validation (§8, §11, §12, §13, §14, §15)
  - Probability calibration evaluation (§8, §9)
  - Immutable dataset registry & lineage verification (§20)
  - Model shadow mode execution & telemetry (§18, §19)
  - Population stability & continuous drift monitoring (§17)
  - Deterministic Scout Copilot tool dispatch (§25)
  - 16-section cross-competition report generation (§28)
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import OpsUser
from app.db.session import get_session
from app.phase17.auth import require
from app.phase17.readiness import competition_readiness
from pydantic import BaseModel, Field

from app.phase11.calibration_engine import calibration_engine
from app.phase11.copilot_extension import copilot_dispatcher_v11
from app.phase11.cross_competition_validator import cross_competition_validator
from app.phase11.dataset_registry import dataset_registry
from app.phase11.drift_monitoring import drift_monitor
from app.phase11.reports import generate_cross_competition_report, render_report_markdown
from app.phase11.shadow_mode import shadow_executor

router = APIRouter(prefix="/api/phase11", tags=["Phase 11 Global Intelligence Operations"])


# ── Request Schemas ──────────────────────────────────────────────────

class ReadinessAdvanceRequest(BaseModel):
    target_state: str  # "DATA_VALIDATED", "FEATURE_READY", "VALIDATION_READY", "MODEL_VALIDATED", "PRODUCTION_READY"
    evidence: list[str] = Field(default_factory=list)


class CalibrationRequest(BaseModel):
    method: str = "TEMPERATURE_SCALING"
    validation_window: str = "2024-01-16 to 2024-03-31"


class DatasetRegisterRequest(BaseModel):
    dataset_id: str
    dataset_version: str = "1.0.0"
    source_snapshots: list[str] = Field(default_factory=list)
    feature_set_version: str = "match_prediction_v1"
    query_definition: str
    competition_scope: str = "GLOBAL"
    season_scope: str = "2023/2024"
    row_count: int = 0
    temporal_splits: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class ShadowInferenceRequest(BaseModel):
    entity_id: str
    competition: str = "LALIGA"
    input_features: dict[str, Any] = Field(default_factory=dict)
    production_model_id: str = "calibrated_multinomial_logit_v1"
    shadow_model_id: str = "candidate_laliga_logit_v1"


class CopilotQueryRequest(BaseModel):
    query: str


# ── 1. Competition Coverage & Readiness Endpoints ────────────────────

# Phase 18 (R7): readiness comes from the one authoritative engine
# (app.phase17.readiness), computed from PostgreSQL. Readiness can no longer
# be advanced by assertion.

@router.get("/competitions/coverage")
async def list_competition_coverage(_: OpsUser = Depends(require("ops:read")),
                                    session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await competition_readiness(session)


@router.get("/competitions/{competition_id}/readiness")
async def get_competition_readiness(competition_id: str, _: OpsUser = Depends(require("ops:read")),
                                    session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    for row in await competition_readiness(session):
        if competition_id.lower() == str(row["competition"]).lower() or competition_id in row["competition_season_ids"]:
            return row
    raise HTTPException(status_code=404, detail="Competition not found")


@router.post("/competitions/{competition_id}/advance", status_code=410)
def advance_competition_readiness(competition_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail={
        "status": "RETIRED",
        "reason": "readiness is computed from data, validation and live outcomes; it cannot be set by request",
        "use_instead": "/api/v1/ops/competitions/readiness"})


# ── 2. Cross-Competition Validation & Calibration Endpoints ─────────

@router.get("/competitions/{competition_id}/validation")
def get_competition_validation(competition_id: str) -> dict[str, Any]:
    dossier = cross_competition_validator.validate_match_prediction(competition_id)
    return dossier.to_dict()


@router.post("/competitions/{competition_id}/calibrate")
def calibrate_competition(competition_id: str, req: CalibrationRequest) -> dict[str, Any]:
    # Provide representative validation distribution
    y_dummy = [0, 1, 2, 0, 1, 0, 2, 1, 0, 0] * 4  # N = 40
    p_dummy = [
        [0.50, 0.30, 0.20], [0.35, 0.40, 0.25], [0.20, 0.30, 0.50], [0.55, 0.25, 0.20],
        [0.30, 0.45, 0.25], [0.60, 0.25, 0.15], [0.25, 0.30, 0.45], [0.35, 0.40, 0.25],
        [0.45, 0.30, 0.25], [0.50, 0.30, 0.20],
    ] * 4
    res = calibration_engine.calibrate_and_evaluate(
        competition=competition_id.upper(),
        y_val=y_dummy,
        probs_val=p_dummy,
        validation_window=req.validation_window,
        method=req.method,
    )
    return res.to_dict()


@router.post("/validation/matrix")
def generate_validation_matrix() -> dict[str, Any]:
    matrix = cross_competition_validator.generate_full_matrix()
    return matrix.to_dict()


# ── 3. Immutable Dataset Registry Endpoints ──────────────────────────

@router.get("/datasets")
def list_datasets(competition_scope: str | None = None) -> list[dict[str, Any]]:
    return dataset_registry.list_datasets(competition_scope=competition_scope)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, version: str | None = None) -> dict[str, Any]:
    ds = dataset_registry.get_dataset(dataset_id, version=version)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds.to_dict()


@router.get("/datasets/{dataset_id}/lineage")
def verify_dataset_lineage(dataset_id: str, version: str | None = None) -> dict[str, Any]:
    return dataset_registry.verify_lineage(dataset_id, version=version)


@router.post("/datasets")
def register_dataset(req: DatasetRegisterRequest) -> dict[str, Any]:
    try:
        identity = dataset_registry.register(req.model_dump())
        return identity.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── 4. Model Shadow Mode Endpoints ───────────────────────────────────

@router.post("/models/{model_id}/shadow/inference")
def execute_shadow_inference(model_id: str, req: ShadowInferenceRequest) -> dict[str, Any]:
    # Dummy mock predict functions simulating production vs candidate logic
    def prod_pred(features: dict[str, Any]) -> dict[str, Any]:
        return {"probabilities": [0.48, 0.28, 0.24], "predicted_outcome": "HOME_WIN", "model": model_id}

    def shadow_pred(features: dict[str, Any]) -> dict[str, Any]:
        return {"probabilities": [0.49, 0.27, 0.24], "predicted_outcome": "HOME_WIN", "model": req.shadow_model_id}

    prod_out, record = shadow_executor.execute_dual_inference(
        entity_id=req.entity_id,
        competition=req.competition,
        input_features=req.input_features,
        prod_predict_fn=prod_pred,
        shadow_predict_fn=shadow_pred,
        prod_model_id=req.production_model_id,
        shadow_model_id=req.shadow_model_id,
    )
    return {
        "authoritative_production_output": prod_out,
        "shadow_record": record.to_dict(),
    }


@router.get("/models/{model_id}/shadow/summary")
def get_shadow_summary(
    model_id: str,
    shadow_model_id: str = "candidate_laliga_logit_v1",
) -> dict[str, Any]:
    summary = shadow_executor.get_summary(model_id, shadow_model_id)
    return summary.to_dict()


@router.get("/models/shadow/records")
def list_shadow_records(limit: int = 50) -> list[dict[str, Any]]:
    return shadow_executor.list_records(limit=limit)


# ── 5. Continuous Drift & Telemetry Endpoints ────────────────────────

@router.get("/competitions/{competition_id}/drift")
def list_competition_drift(competition_id: str) -> list[dict[str, Any]]:
    return drift_monitor.list_snapshots(competition=competition_id)


@router.get("/drift/alerts")
def list_drift_alerts(competition_id: str | None = None) -> list[dict[str, Any]]:
    return drift_monitor.list_alerts(competition=competition_id)


# ── 6. 16-Section Cross-Competition Report Endpoints ─────────────────

@router.get("/reports/cross-competition/{competition_id}")
def get_cross_competition_report(
    competition_id: str,
    format: str = Query("json", enum=["json", "markdown"]),
) -> Any:
    rep = generate_cross_competition_report(competition_id)
    if format == "markdown":
        md = render_report_markdown(rep)
        return Response(content=md, media_type="text/markdown")
    return rep.to_dict()


# ── 7. Scout Copilot Operational Dispatcher Endpoints ────────────────

@router.post("/copilot/query")
def dispatch_copilot_query(req: CopilotQueryRequest) -> dict[str, Any]:
    return copilot_dispatcher_v11.dispatch(req.query)
