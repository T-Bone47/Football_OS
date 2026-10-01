"""Phase 9 — Pipeline Replay & Determinism Verification.

Replays the full pipeline (Bronze → Silver → Features → Models → Decision Intelligence)
for representative historical windows and verifies deterministic output.

Expected on replay:
  - same canonical records
  - same feature snapshots
  - same model inputs
  - same decision graph
  - same provenance
where deterministic semantics apply.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ReplayStep:
    """Result of replaying a single pipeline step."""
    step_name: str              # 'bronze_ingest', 'silver_normalize', 'feature_compute', etc.
    input_hash: str | None = None
    output_hash: str | None = None
    record_count: int = 0
    duration_ms: float = 0.0
    status: str = "NOT_RUN"     # 'SUCCESS', 'FAILED', 'SKIPPED', 'NOT_RUN'
    errors: list[str] = field(default_factory=list)


@dataclass
class ReplayRun:
    """A single complete pipeline replay run."""
    run_id: str
    replay_window: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    steps: list[ReplayStep] = field(default_factory=list)
    overall_hash: str | None = None
    status: str = "NOT_RUN"


@dataclass
class PipelineReplayReport:
    """Full pipeline replay verification report."""
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: str = "pipeline_replay_v1"
    runs: list[ReplayRun] = field(default_factory=list)
    determinism_verified: bool = False
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_canonical_hash(data: Any) -> str:
    """Compute a deterministic SHA-256 hash of canonical data.

    Handles dicts, lists, and primitives. Sorts dict keys to ensure
    deterministic ordering.
    """
    canonical = _canonicalize(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonicalize(obj: Any) -> str:
    """Canonicalize an object to a deterministic string representation."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return json.dumps(obj)
    if isinstance(obj, dict):
        parts = []
        for key in sorted(obj.keys()):
            parts.append(f"{json.dumps(key)}:{_canonicalize(obj[key])}")
        return "{" + ",".join(parts) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canonicalize(item) for item in obj) + "]"
    return str(obj)


def replay_pipeline_step(
    step_name: str,
    input_data: Any,
    process_fn: Any = None,
) -> ReplayStep:
    """Execute a single pipeline replay step.

    Args:
        step_name: Name of the pipeline step.
        input_data: Input data for the step.
        process_fn: Optional callable to process input_data and return output.

    Returns:
        ReplayStep with hashes for determinism comparison.
    """
    import time

    step = ReplayStep(step_name=step_name)
    step.input_hash = compute_canonical_hash(input_data)

    if process_fn is None:
        # Passthrough — used for structural validation
        step.output_hash = step.input_hash
        step.status = "SUCCESS"
        step.record_count = len(input_data) if isinstance(input_data, (list, dict)) else 1
        return step

    start = time.perf_counter()
    try:
        output = process_fn(input_data)
        step.output_hash = compute_canonical_hash(output)
        step.record_count = len(output) if isinstance(output, (list, dict)) else 1
        step.status = "SUCCESS"
    except Exception as exc:
        step.status = "FAILED"
        step.errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        step.duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return step


def run_full_replay(
    replay_window: str,
    run_id: str,
    bronze_data: Any = None,
    normalize_fn: Any = None,
    feature_fn: Any = None,
    model_fn: Any = None,
    decision_fn: Any = None,
) -> ReplayRun:
    """Run a complete pipeline replay for a historical window.

    Each step is hashed for determinism verification.
    """
    run = ReplayRun(run_id=run_id, replay_window=replay_window)

    data = bronze_data or {}

    # Step 1: Bronze ingest
    step1 = replay_pipeline_step("bronze_ingest", data)
    run.steps.append(step1)

    # Step 2: Silver normalization
    step2 = replay_pipeline_step("silver_normalize", data, normalize_fn)
    run.steps.append(step2)

    # Step 3: Feature computation
    step3 = replay_pipeline_step("feature_compute", data, feature_fn)
    run.steps.append(step3)

    # Step 4: Model inference
    step4 = replay_pipeline_step("model_inference", data, model_fn)
    run.steps.append(step4)

    # Step 5: Decision intelligence
    step5 = replay_pipeline_step("decision_intelligence", data, decision_fn)
    run.steps.append(step5)

    # Compute overall hash
    step_hashes = [s.output_hash or "" for s in run.steps]
    run.overall_hash = compute_canonical_hash(step_hashes)
    run.completed_at = datetime.now(timezone.utc).isoformat()

    failed = any(s.status == "FAILED" for s in run.steps)
    run.status = "FAILED" if failed else "SUCCESS"

    return run


def verify_replay_determinism(
    run_a: ReplayRun,
    run_b: ReplayRun,
) -> tuple[bool, list[dict[str, Any]]]:
    """Compare two replay runs for determinism.

    Returns:
        (is_deterministic, list_of_mismatches)
    """
    mismatches: list[dict[str, Any]] = []

    if run_a.overall_hash != run_b.overall_hash:
        mismatches.append({
            "type": "overall_hash",
            "run_a": run_a.overall_hash,
            "run_b": run_b.overall_hash,
        })

    for step_a, step_b in zip(run_a.steps, run_b.steps):
        if step_a.output_hash != step_b.output_hash:
            mismatches.append({
                "type": "step_hash",
                "step": step_a.step_name,
                "run_a_hash": step_a.output_hash,
                "run_b_hash": step_b.output_hash,
            })

    return len(mismatches) == 0, mismatches


def build_replay_report(
    runs: list[ReplayRun],
    verify_pairs: bool = True,
) -> PipelineReplayReport:
    """Build a complete pipeline replay verification report.

    If verify_pairs is True and there are ≥2 runs for the same window,
    verifies determinism between them.
    """
    report = PipelineReplayReport()
    report.runs = runs

    # Group runs by replay_window
    by_window: dict[str, list[ReplayRun]] = {}
    for run in runs:
        by_window.setdefault(run.replay_window, []).append(run)

    determinism_checks = 0
    determinism_passes = 0

    if verify_pairs:
        for window, window_runs in by_window.items():
            if len(window_runs) >= 2:
                is_det, mm = verify_replay_determinism(window_runs[0], window_runs[1])
                determinism_checks += 1
                if is_det:
                    determinism_passes += 1
                else:
                    report.mismatches.extend(mm)

    report.determinism_verified = (
        determinism_checks > 0 and determinism_passes == determinism_checks
    )

    report.summary = {
        "total_runs": len(runs),
        "successful_runs": sum(1 for r in runs if r.status == "SUCCESS"),
        "failed_runs": sum(1 for r in runs if r.status == "FAILED"),
        "windows_replayed": len(by_window),
        "determinism_checks": determinism_checks,
        "determinism_passes": determinism_passes,
        "determinism_verified": report.determinism_verified,
        "total_mismatches": len(report.mismatches),
    }

    report.limitations = [
        "Pipeline replay is structural — it replays data flow, not live API calls",
        "Determinism verification requires identical input data for both runs",
        "Timestamp-dependent computations may produce expected differences",
        "Process functions (normalize_fn, etc.) must be provided for full replay; "
        "otherwise passthrough hashing is used",
    ]

    return report
