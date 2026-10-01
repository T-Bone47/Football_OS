"""Frontend Data-Coverage Surface Routes (Phase 9 §20).

Exposes truthful data quality, coverage, sample size, model validation status,
confidence levels, OOD boundaries, provenance tracking, and explicit limitations
for client applications and scouting decision surfaces.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.phase9.coverage_audit import build_coverage_matrix
from app.phase9.ood_validation import OODTestResult, validate_ood_behavior

router = APIRouter(prefix="/api/data-coverage", tags=["Data Coverage Surface"])


def _get_data_root() -> Path:
    # Resolve to repo_root / "data"
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "data" / "bronze").exists():
            return parent / "data"
    # Fallback to 4 levels up
    return p.parents[4] / "data"


@router.get("/summary")
def get_data_coverage_summary() -> dict[str, Any]:
    """Exposes high-level truthful coverage summary for scouting decision surfaces (§20)."""
    data_root = _get_data_root()
    matrix = build_coverage_matrix(data_root)

    dimensions_summary = {}
    for dim_name, dim in matrix.dimensions.items():
        dimensions_summary[dim_name] = {
            "record_count": dim.record_count,
            "provider": dim.provider,
            "quality": dim.coverage_quality,
            "validation_status": dim.validation_status,
            "provenance_complete": dim.provenance_completeness >= 1.0,
            "missingness_rate": dim.missingness_rate,
        }

    return {
        # Derived from the files actually audited, never a literal.
        "status": "NO_BRONZE_FILES" if matrix.total_bronze_files == 0 else "AUDITED",
        "scope": "local Bronze files on this host",
        "audit_version": matrix.audit_version,
        "overall_quality": matrix.overall_quality,
        "total_files": matrix.total_bronze_files,
        "total_bytes": matrix.total_bronze_bytes,
        "providers_active": matrix.providers_used,
        "dimensions": dimensions_summary,
        "competitions": {
            k: {
                "country": v.country,
                "coverage_quality": v.coverage_quality,
                "provider": v.provider,
            }
            for k, v in matrix.competitions.items()
        },
        "material_limitations": matrix.limitations,
    }


@router.get("/matrix")
def get_data_coverage_matrix() -> dict[str, Any]:
    """Returns the detailed multi-dimensional coverage matrix."""
    data_root = _get_data_root()
    matrix = build_coverage_matrix(data_root)
    return matrix.to_dict()


@router.get("/ood-status")
def get_ood_status() -> dict[str, Any]:
    """Exposes out-of-distribution boundaries and handling rules for frontends."""
    ood = validate_ood_behavior()
    results = [s.test_result for s in ood.scenarios]
    return {
        # An in-process self-test of the OOD gates, run now. Its status is the
        # result of that run, not a declaration.
        "status": "ALL_SCENARIOS_PASSED" if results and all(r == OODTestResult.PASSED for r in results)
        else "SCENARIO_FAILURES_OR_SKIPS",
        "evidence_type": "IN_PROCESS_SELF_TEST",
        "ood_policy": "NO_SILENT_NORMAL_CONFIDENCE",
        "labels_supported": [
            "IN_DISTRIBUTION",
            "LOW_CONFIDENCE",
            "INSUFFICIENT_DATA",
            "OUT_OF_DISTRIBUTION",
        ],
        "summary": ood.summary,
        "scenarios": [
            {
                "id": s.scenario_id,
                "category": s.category,
                "engine": s.engine,
                "expected_status": s.expected_status,
                "result": s.test_result,
            }
            for s in ood.scenarios
        ],
        "limitations": ood.limitations,
    }


@router.get("/model-validation", status_code=410)
def get_model_validation_surface() -> dict[str, Any]:
    """Retired in Phase 18: the report embedded literal test counts
    (413 passed, 0 failed, 61 skipped) and declared model metrics. Model
    state comes from the registry; validation evidence from the ops API."""
    raise HTTPException(status_code=410, detail={
        "status": "RETIRED", "reason": "embedded declared test counts and model metrics",
        "use_instead": ["/model-status", "/api/v1/ops/models", "/api/v1/ops/models/calibration"],
    })


@router.get("/dry-run", status_code=410)
def get_dry_run_status() -> dict[str, Any]:
    """Retired in Phase 18: it pushed a hand-typed API-Football fixture through
    the pipeline as a "production dry run". Real ingestion runs through
    /api/v1/ops/ingestion/jobs and reports the provider's actual state."""
    raise HTTPException(status_code=410, detail={
        "status": "RETIRED", "reason": "processed a hand-typed provider payload",
        "use_instead": ["/api/v1/ops/ingestion/jobs", "/api/v1/ops/providers/probe"],
    })
