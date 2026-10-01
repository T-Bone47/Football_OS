"""Phase 9 — Model Stability & Data Drift Analysis.

Evaluates model output stability across adjacent seasons, rolling windows,
competition subsets, and position subsets. Implements historical drift
analysis with PSI (Population Stability Index) where appropriate.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np


# ── Drift Detection ──────────────────────────────────────────────────────

PSI_THRESHOLD_LOW = 0.1       # Negligible drift
PSI_THRESHOLD_MEDIUM = 0.2    # Moderate drift — monitor
PSI_THRESHOLD_HIGH = 0.25     # Significant drift — investigate


@dataclass
class DriftResult:
    """Result of a distribution drift analysis."""
    feature_name: str
    reference_period: str
    comparison_period: str
    psi: float
    drift_level: str            # 'NONE', 'LOW', 'MODERATE', 'SIGNIFICANT'
    reference_mean: float = 0.0
    comparison_mean: float = 0.0
    reference_std: float = 0.0
    comparison_std: float = 0.0
    reference_count: int = 0
    comparison_count: int = 0
    notes: list[str] = field(default_factory=list)


def compute_psi(
    reference: Sequence[float],
    comparison: Sequence[float],
    n_bins: int = 10,
) -> float:
    """Compute Population Stability Index (PSI) between two distributions.

    PSI measures how much a distribution has shifted from a reference.
    Lower = more stable.

    Args:
        reference: Reference distribution values.
        comparison: Comparison (current) distribution values.
        n_bins: Number of bins for histogram comparison.

    Returns:
        PSI value (0.0 = identical distributions).
    """
    if len(reference) < 2 or len(comparison) < 2:
        return 0.0

    ref_arr = np.array(reference, dtype=float)
    comp_arr = np.array(comparison, dtype=float)

    # Use reference distribution to define bins
    _, bin_edges = np.histogram(ref_arr, bins=n_bins)

    ref_hist, _ = np.histogram(ref_arr, bins=bin_edges)
    comp_hist, _ = np.histogram(comp_arr, bins=bin_edges)

    # Normalize to proportions, with smoothing
    epsilon = 1e-6
    ref_pct = (ref_hist + epsilon) / (ref_arr.shape[0] + epsilon * n_bins)
    comp_pct = (comp_hist + epsilon) / (comp_arr.shape[0] + epsilon * n_bins)

    psi = float(np.sum((comp_pct - ref_pct) * np.log(comp_pct / ref_pct)))
    return round(max(0.0, psi), 6)


def classify_drift(psi: float) -> str:
    """Classify drift level from PSI value."""
    if psi < PSI_THRESHOLD_LOW:
        return "NONE"
    if psi < PSI_THRESHOLD_MEDIUM:
        return "LOW"
    if psi < PSI_THRESHOLD_HIGH:
        return "MODERATE"
    return "SIGNIFICANT"


def analyze_feature_drift(
    feature_name: str,
    reference_values: Sequence[float],
    comparison_values: Sequence[float],
    reference_period: str = "reference",
    comparison_period: str = "comparison",
) -> DriftResult:
    """Analyze drift for a single feature between two periods."""
    psi = compute_psi(reference_values, comparison_values)

    ref_arr = np.array(reference_values, dtype=float) if reference_values else np.array([0.0])
    comp_arr = np.array(comparison_values, dtype=float) if comparison_values else np.array([0.0])

    return DriftResult(
        feature_name=feature_name,
        reference_period=reference_period,
        comparison_period=comparison_period,
        psi=psi,
        drift_level=classify_drift(psi),
        reference_mean=round(float(np.mean(ref_arr)), 4),
        comparison_mean=round(float(np.mean(comp_arr)), 4),
        reference_std=round(float(np.std(ref_arr)), 4),
        comparison_std=round(float(np.std(comp_arr)), 4),
        reference_count=len(reference_values),
        comparison_count=len(comparison_values),
    )


# ── Model Stability ──────────────────────────────────────────────────────

class StabilityChangeType:
    EXPECTED = "EXPECTED"
    DATA_DRIVEN = "DATA_DRIVEN"
    MODEL_DRIVEN = "MODEL_DRIVEN"
    UNKNOWN = "UNKNOWN"


@dataclass
class StabilityWindow:
    """Stability assessment for one comparison window."""
    window_id: str
    window_description: str
    metric_name: str
    reference_value: float
    comparison_value: float
    absolute_change: float
    relative_change_pct: float
    change_type: str = StabilityChangeType.UNKNOWN
    is_stable: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class ModelStabilityReport:
    """Report assessing model output stability across slices."""
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: str = "model_stability_v1"
    model_name: str = ""
    model_version: str = ""
    drift_results: list[DriftResult] = field(default_factory=list)
    stability_windows: list[StabilityWindow] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STABILITY_THRESHOLD_PCT = 10.0  # Absolute relative change % before flagging


def assess_metric_stability(
    metric_name: str,
    window_id: str,
    window_description: str,
    ref_value: float,
    comp_value: float,
    threshold_pct: float = STABILITY_THRESHOLD_PCT,
) -> StabilityWindow:
    """Assess stability of a single metric across a comparison window."""
    abs_change = abs(comp_value - ref_value)
    rel_change = (abs_change / max(abs(ref_value), 1e-9)) * 100

    is_stable = rel_change <= threshold_pct

    # Classify change type heuristically
    if abs_change < 1e-6:
        change_type = StabilityChangeType.EXPECTED
    elif rel_change < 5.0:
        change_type = StabilityChangeType.DATA_DRIVEN
    elif rel_change < threshold_pct:
        change_type = StabilityChangeType.DATA_DRIVEN
    else:
        change_type = StabilityChangeType.UNKNOWN

    return StabilityWindow(
        window_id=window_id,
        window_description=window_description,
        metric_name=metric_name,
        reference_value=round(ref_value, 6),
        comparison_value=round(comp_value, 6),
        absolute_change=round(abs_change, 6),
        relative_change_pct=round(rel_change, 2),
        change_type=change_type,
        is_stable=is_stable,
    )


def build_stability_report(
    model_name: str,
    model_version: str,
    metrics_by_window: dict[str, dict[str, float]],
    reference_window: str,
    feature_drift_pairs: list[tuple[str, Sequence[float], Sequence[float]]] | None = None,
) -> ModelStabilityReport:
    """Build a complete model stability report.

    Args:
        model_name: Name of the model.
        model_version: Version string.
        metrics_by_window: Mapping of window_id → {metric_name: value}.
        reference_window: Window ID to use as the reference baseline.
        feature_drift_pairs: Optional list of (feature_name, ref_values, comp_values)
                            for PSI drift analysis.

    Returns:
        ModelStabilityReport.
    """
    report = ModelStabilityReport(
        model_name=model_name,
        model_version=model_version,
    )

    ref_metrics = metrics_by_window.get(reference_window, {})

    for window_id, metrics in metrics_by_window.items():
        if window_id == reference_window:
            continue
        for metric_name, value in metrics.items():
            ref_val = ref_metrics.get(metric_name)
            if ref_val is None:
                continue
            sw = assess_metric_stability(
                metric_name=metric_name,
                window_id=window_id,
                window_description=f"{reference_window} vs {window_id}",
                ref_value=ref_val,
                comp_value=value,
            )
            report.stability_windows.append(sw)

    # Feature drift analysis
    if feature_drift_pairs:
        for feat_name, ref_vals, comp_vals in feature_drift_pairs:
            dr = analyze_feature_drift(
                feature_name=feat_name,
                reference_values=ref_vals,
                comparison_values=comp_vals,
                reference_period=reference_window,
                comparison_period="comparison",
            )
            report.drift_results.append(dr)

    # Summary
    total_windows = len(report.stability_windows)
    stable_count = sum(1 for w in report.stability_windows if w.is_stable)
    drift_significant = sum(1 for d in report.drift_results if d.drift_level == "SIGNIFICANT")

    report.summary = {
        "total_stability_checks": total_windows,
        "stable": stable_count,
        "unstable": total_windows - stable_count,
        "stability_rate": round(stable_count / max(total_windows, 1), 3),
        "total_drift_features": len(report.drift_results),
        "significant_drifts": drift_significant,
        "overall_assessment": (
            "STABLE" if (stable_count == total_windows and drift_significant == 0)
            else "DEGRADED" if drift_significant > 0
            else "MONITOR"
        ),
    }

    report.limitations = [
        "Stability is assessed against a single reference window; multi-window trends not captured",
        f"Stability threshold is {STABILITY_THRESHOLD_PCT}% relative change; domain-specific thresholds may differ",
        f"PSI drift thresholds: LOW < {PSI_THRESHOLD_LOW}, MODERATE < {PSI_THRESHOLD_MEDIUM}, SIGNIFICANT ≥ {PSI_THRESHOLD_HIGH}",
        "Drift analysis requires sufficient sample size in both periods; small samples produce unreliable PSI",
    ]

    return report


# ── Temporal Dataset Validation ──────────────────────────────────────────

@dataclass
class TemporalDatasetSpec:
    """Specification for a temporal dataset with strict cutoff enforcement."""
    dataset_name: str
    feature_as_of: str | None = None
    target_date: str | None = None
    training_cutoff: str | None = None
    validation_cutoff: str | None = None
    test_cutoff: str | None = None
    total_records: int = 0
    training_records: int = 0
    validation_records: int = 0
    test_records: int = 0
    leakage_free: bool = True
    notes: list[str] = field(default_factory=list)


def validate_temporal_splits(spec: TemporalDatasetSpec) -> list[str]:
    """Validate that temporal dataset splits are correctly ordered and leak-free.

    Returns list of violation descriptions (empty = valid).
    """
    violations: list[str] = []

    cutoffs = [
        ("training_cutoff", spec.training_cutoff),
        ("validation_cutoff", spec.validation_cutoff),
        ("test_cutoff", spec.test_cutoff),
    ]

    # Verify ordering
    for i in range(len(cutoffs) - 1):
        name_a, val_a = cutoffs[i]
        name_b, val_b = cutoffs[i + 1]
        if val_a and val_b and val_a >= val_b:
            violations.append(
                f"Temporal ordering violation: {name_a} ({val_a}) must precede {name_b} ({val_b})"
            )

    # Verify record counts are consistent
    if spec.total_records > 0:
        split_sum = spec.training_records + spec.validation_records + spec.test_records
        if split_sum > 0 and abs(split_sum - spec.total_records) > spec.total_records * 0.05:
            violations.append(
                f"Split count mismatch: train({spec.training_records}) + "
                f"val({spec.validation_records}) + test({spec.test_records}) = "
                f"{split_sum} ≠ total({spec.total_records})"
            )

    if violations:
        spec.leakage_free = False

    return violations
