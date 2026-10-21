"""Measured release gate for valuation models (handoff §7.12, §8.2, §8.4).

The previous gate hard-coded 7 of its 10 checks to True and compared MAE only. Here every check
is either computed from evidence or reported NOT_EVALUATED; a model is MODEL_VALIDATED only when
every check was evaluated and passed.
"""
from __future__ import annotations

from collections.abc import Mapping

PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUATED = "NOT_EVALUATED"

MIN_OVERALL_COVERAGE = 0.70
MIN_GROUP_COVERAGE = 0.60
MIN_GROUP_N = 10  # groups smaller than this are noise (e.g. 1 of 3 intervals covering) and are not judged
MIN_TEST_R2 = 0.0  # a "validated" model must explain more test variance than the test mean
_PRIMARY_ERROR_METRICS = ("mae", "rmse", "log_mae")

# Facts the training pipeline cannot establish by itself; the caller passes True/False only
# when it measured them. None / absent => NOT_EVALUATED.
EVIDENCE_CHECKS = (
    "target_policy_verified",
    "feature_contract_documented",
    "temporal_split_chronological",
    "test_set_untouched_during_tuning",
    "explainability_deterministic_non_causal",
    "sufficiency_and_ood_gate_operational",
    "reproducibility_verified",
    "training_data_provenance_verified",
    "training_features_observed",
)


def _beats(model: Mapping[str, float], baseline: Mapping[str, float]) -> str:
    if not baseline:
        return NOT_EVALUATED
    compared = [m for m in _PRIMARY_ERROR_METRICS if m in model and m in baseline]
    if not compared:
        return NOT_EVALUATED
    return PASS if all(model[m] < baseline[m] for m in compared) else FAIL


def evaluate_release_gate(
    *,
    test_metrics: Mapping[str, float],
    comparable_baseline: Mapping[str, float] | None,
    position_median_baseline: Mapping[str, float] | None,
    empirical_coverage: float | None,
    coverage_by_group: Mapping[str, tuple[float, int]] | None,
    evidence: Mapping[str, bool | None] | None = None,
) -> tuple[str, dict[str, str]]:
    """Return (status, per-check PASS/FAIL/NOT_EVALUATED)."""
    evidence = evidence or {}
    checks: dict[str, str] = {}
    for name in EVIDENCE_CHECKS:
        value = evidence.get(name)
        checks[name] = NOT_EVALUATED if value is None else (PASS if value else FAIL)

    checks["beats_comparable_baseline"] = _beats(test_metrics, comparable_baseline or {})
    checks["beats_position_median_baseline"] = _beats(test_metrics, position_median_baseline or {})

    r2 = test_metrics.get("r2")
    checks["test_r2_positive"] = NOT_EVALUATED if r2 is None else (PASS if r2 > MIN_TEST_R2 else FAIL)

    checks["interval_coverage_overall"] = (
        NOT_EVALUATED if empirical_coverage is None else (PASS if empirical_coverage >= MIN_OVERALL_COVERAGE else FAIL)
    )
    # coverage_by_group maps group -> (empirical coverage, sample size); overall coverage can
    # hide a collapse inside a subgroup (the shipped artifact covered 24% of >70M transfers).
    judged = [c for c, n in (coverage_by_group or {}).values() if n >= MIN_GROUP_N]
    if not judged:
        checks["interval_coverage_by_group"] = NOT_EVALUATED
    else:
        checks["interval_coverage_by_group"] = PASS if all(c >= MIN_GROUP_COVERAGE for c in judged) else FAIL

    values = set(checks.values())
    if FAIL in values:
        return "MODEL_RELEASE_BLOCKED", checks
    if NOT_EVALUATED in values:
        return "MODEL_CANDIDATE_ONLY", checks
    return "MODEL_VALIDATED", checks
