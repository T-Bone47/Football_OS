"""The release gate measures; it never defaults a check to PASS (handoff §7.12)."""
from __future__ import annotations

import json
from pathlib import Path

from app.market.ml.release_gate import EVIDENCE_CHECKS, FAIL, NOT_EVALUATED, PASS, evaluate_release_gate

VALUATION_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / "valuation"
ALL_EVIDENCE = {name: True for name in EVIDENCE_CHECKS}
GOOD = {"mae": 10.0, "rmse": 12.0, "log_mae": 0.3, "r2": 0.4}
WORSE = {"mae": 20.0, "rmse": 25.0, "log_mae": 0.6, "r2": 0.1}


def _gate(**kw):
    args = dict(test_metrics=GOOD, comparable_baseline=WORSE, position_median_baseline=WORSE, empirical_coverage=0.8,
                coverage_by_group={"fee_band:>70M": (0.8, 40)}, evidence=ALL_EVIDENCE)
    args.update(kw)
    return evaluate_release_gate(**args)


def _historical(evidence=None):
    results = json.loads((VALUATION_DIR / "pipeline_results.json").read_text())
    unc = results["uncertainty_report"]
    bands = results["calibration_analysis"]["fee_band_calibration"]
    groups = {f"fee_band:{b}": (cov, bands[b]["count"]) for b, cov in unc["coverage_by_fee_band"].items()}
    return dict(
        test_metrics=results["champion_test_metrics"],
        comparable_baseline=results["baseline_metrics"]["comparable_baseline"],
        position_median_baseline=results["baseline_metrics"]["position_median"],
        empirical_coverage=unc["empirical_coverage"],
        coverage_by_group=groups,
        evidence=evidence,
    )


def test_everything_measured_and_passing_validates():
    status, checks = _gate()
    assert status == "MODEL_VALIDATED" and set(checks.values()) == {PASS}


def test_unmeasured_checks_never_count_as_passed():
    """Regression: 7 of 10 checks used to be hard-coded True."""
    status, checks = _gate(evidence=None)
    assert status == "MODEL_CANDIDATE_ONLY"
    assert all(checks[name] == NOT_EVALUATED for name in EVIDENCE_CHECKS)


def test_a_single_failed_check_blocks_release():
    status, checks = _gate(evidence={**ALL_EVIDENCE, "training_data_provenance_verified": False})
    assert status == "MODEL_RELEASE_BLOCKED" and checks["training_data_provenance_verified"] == FAIL


def test_beating_baseline_on_mae_alone_is_not_enough():
    status, checks = _gate(test_metrics={**GOOD, "log_mae": 0.65})
    assert checks["beats_comparable_baseline"] == FAIL and status == "MODEL_RELEASE_BLOCKED"


def test_negative_test_r2_blocks_release():
    status, checks = _gate(test_metrics={**GOOD, "r2": -0.09})
    assert checks["test_r2_positive"] == FAIL and status == "MODEL_RELEASE_BLOCKED"


def test_subgroup_collapse_is_caught_but_tiny_groups_are_not_judged():
    _, collapsed = _gate(coverage_by_group={"fee_band:>70M": (0.24, 21)})
    assert collapsed["interval_coverage_by_group"] == FAIL
    _, noise = _gate(coverage_by_group={"fee_band:<10M": (0.33, 3), "fee_band:10-30M": (0.9, 36)})
    assert noise["interval_coverage_by_group"] == PASS


def test_shipped_valuation_artifact_does_not_pass_its_own_release_policy():
    """The committed pipeline_results.json claimed MODEL_VALIDATED; re-measured, it is blocked."""
    status, checks = evaluate_release_gate(**_historical())
    assert checks["beats_comparable_baseline"] == FAIL  # log_mae 0.4914 vs baseline 0.4907
    assert checks["test_r2_positive"] == FAIL  # test r2 = -0.0904
    assert checks["interval_coverage_by_group"] == FAIL  # >70M band covered 24% of intervals
    assert status == "MODEL_RELEASE_BLOCKED"


def test_committed_manifest_status_matches_the_measured_gate():
    manifest = json.loads((VALUATION_DIR / "registry_manifest.json").read_text())
    entry = manifest["models"][manifest["active_model_id"]]
    status, checks = evaluate_release_gate(**_historical(entry["release_gate_evidence"]))
    assert entry["status"] == status
    assert entry["release_gate_evaluation"] == checks
    assert entry["status"] != "MODEL_VALIDATED" and entry["blocking_reasons"]
