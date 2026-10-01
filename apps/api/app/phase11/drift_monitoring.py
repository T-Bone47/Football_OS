"""Phase 11 — Continuous Drift Monitoring & Competition Operational Alerts (§16, §17, §27).

Tracks population stability index (PSI), calibration degradation, Brier score drift,
missingness drift, and emits non-causal operational alerts.
Thresholds:
  PSI < 0.10: NORMAL
  0.10 <= PSI < 0.20: MONITOR
  0.20 <= PSI <= 0.25: WARNING
  PSI > 0.25: MATERIAL_DRIFT (triggers REVIEW_REQUIRED)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Sequence
import numpy as np


class DriftStatus(str, Enum):
    NORMAL = "NORMAL"
    MONITOR = "MONITOR"
    WARNING = "WARNING"
    MATERIAL_DRIFT = "MATERIAL_DRIFT"


class DriftAlertCategory(str, Enum):
    MODEL_DRIFT_DETECTED = "MODEL_DRIFT_DETECTED"
    CALIBRATION_DEGRADATION = "CALIBRATION_DEGRADATION"
    DATA_FRESHNESS_DEGRADED = "DATA_FRESHNESS_DEGRADED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    COMPETITION_READINESS_CHANGED = "COMPETITION_READINESS_CHANGED"
    MODEL_PROMOTION_READY = "MODEL_PROMOTION_READY"
    MODEL_RETRAIN_REQUIRED = "MODEL_RETRAIN_REQUIRED"
    FEATURE_COVERAGE_DROP = "FEATURE_COVERAGE_DROP"
    IDENTITY_RESOLUTION_DROP = "IDENTITY_RESOLUTION_DROP"


@dataclass
class CompetitionDriftSnapshot:
    """Competition-level drift monitoring evaluation record (§17)."""
    competition: str
    season: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    feature_psi: dict[str, float] = field(default_factory=dict)
    overall_psi: float = 0.0
    drift_status: str = DriftStatus.NORMAL
    brier_drift: float = 0.0
    log_loss_drift: float = 0.0
    ece_drift: float = 0.0
    missingness_drift: float = 0.0
    review_required: bool = False
    evidence_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperationalAlert:
    """Factual, non-causal operational alert (§27)."""
    alert_id: str
    category: str
    competition: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    headline: str
    details: dict[str, Any]
    evidence: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_psi(
    expected: Sequence[float],
    actual: Sequence[float],
    n_bins: int = 10,
    eps: float = 1e-4,
) -> float:
    """Calculates Population Stability Index between baseline and actual distributions.
    
    Formula: PSI = sum((actual% - expected%) * ln(actual% / expected%))
    """
    if len(expected) == 0 or len(actual) == 0:
        return 0.0

    # Determine quantiles based on expected distribution
    percentiles = np.linspace(0, 100, n_bins + 1)
    bin_edges = np.percentile(expected, percentiles)
    # Ensure distinct bin edges
    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return 0.0

    exp_counts, _ = np.histogram(expected, bins=bin_edges)
    act_counts, _ = np.histogram(actual, bins=bin_edges)

    exp_pct = [(c / len(expected)) + eps for c in exp_counts]
    act_pct = [(c / len(actual)) + eps for c in act_counts]

    # Re-normalize
    sum_exp = sum(exp_pct)
    sum_act = sum(act_pct)
    exp_pct = [p / sum_exp for p in exp_pct]
    act_pct = [p / sum_act for p in act_pct]

    psi = sum((act - exp) * math.log(act / exp) for exp, act in zip(exp_pct, act_pct))
    return round(float(psi), 4)


class ContinuousDriftMonitor:
    """Continuous competition and model drift evaluation system."""

    def __init__(self) -> None:
        self._snapshots: list[CompetitionDriftSnapshot] = []
        self._alerts: list[OperationalAlert] = []
        self._seed_default_drift()

    def _seed_default_drift(self) -> None:
        # EPL baseline snapshot (healthy)
        s_epl = CompetitionDriftSnapshot(
            competition="EPL",
            season="2023/2024",
            feature_psi={"home_advantage": 0.021, "elo_diff": 0.045, "goal_diff": 0.038},
            overall_psi=0.035,
            drift_status=DriftStatus.NORMAL,
            brier_drift=0.002,
            log_loss_drift=0.004,
            ece_drift=-0.001,
            missingness_drift=0.000,
            review_required=False,
            evidence_nodes=[
                "Feature distributions stable over 2023/24 season",
                "PSI 0.035 < 0.10 normal threshold",
                "Log Loss drift +0.004 within normal tolerance bounds",
            ],
        )
        self._snapshots.append(s_epl)

    def evaluate_competition_drift(
        self,
        competition: str,
        season: str,
        baseline_features: dict[str, list[float]],
        current_features: dict[str, list[float]],
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
    ) -> CompetitionDriftSnapshot:
        """Evaluates multi-feature and performance drift against established thresholds."""
        feature_psis = {}
        for feat_name, base_vals in baseline_features.items():
            curr_vals = current_features.get(feat_name, [])
            if base_vals and curr_vals:
                feature_psis[feat_name] = calculate_psi(base_vals, curr_vals)

        overall_psi = round(
            float(np.mean(list(feature_psis.values()))) if feature_psis else 0.0, 4
        )

        # Threshold classification (§17)
        if overall_psi < 0.10:
            status = DriftStatus.NORMAL
            review_required = False
        elif overall_psi < 0.20:
            status = DriftStatus.MONITOR
            review_required = False
        elif overall_psi <= 0.25:
            status = DriftStatus.WARNING
            review_required = True
        else:
            status = DriftStatus.MATERIAL_DRIFT
            review_required = True

        brier_drift = round(current_metrics.get("brier_score", 0.0) - baseline_metrics.get("brier_score", 0.0), 4)
        log_loss_drift = round(current_metrics.get("log_loss", 0.0) - baseline_metrics.get("log_loss", 0.0), 4)
        ece_drift = round(current_metrics.get("ece", 0.0) - baseline_metrics.get("ece", 0.0), 4)
        missingness_drift = round(current_metrics.get("missingness", 0.0) - baseline_metrics.get("missingness", 0.0), 4)

        evidence = [
            f"Overall Feature PSI: {overall_psi} (Status: {status.value})",
            f"Brier score drift: {brier_drift:+.4f}",
            f"Log Loss drift: {log_loss_drift:+.4f}",
            f"ECE drift: {ece_drift:+.4f}",
        ]

        snapshot = CompetitionDriftSnapshot(
            competition=competition,
            season=season,
            feature_psi=feature_psis,
            overall_psi=overall_psi,
            drift_status=status.value,
            brier_drift=brier_drift,
            log_loss_drift=log_loss_drift,
            ece_drift=ece_drift,
            missingness_drift=missingness_drift,
            review_required=review_required,
            evidence_nodes=evidence,
        )
        self._snapshots.append(snapshot)

        # Trigger operational alerts if thresholds are breached
        if review_required:
            alert = OperationalAlert(
                alert_id=f"alt_drift_{len(self._alerts) + 1}",
                category=DriftAlertCategory.MODEL_DRIFT_DETECTED.value,
                competition=competition,
                severity="WARNING" if status == DriftStatus.WARNING else "CRITICAL",
                headline=f"Distributional drift detected in {competition}: PSI {overall_psi}",
                details={"overall_psi": overall_psi, "feature_psis": feature_psis},
                evidence=evidence,
            )
            self._alerts.append(alert)

        if ece_drift > 0.04:
            alert = OperationalAlert(
                alert_id=f"alt_calib_{len(self._alerts) + 1}",
                category=DriftAlertCategory.CALIBRATION_DEGRADATION.value,
                competition=competition,
                severity="CRITICAL",
                headline=f"Probability calibration degraded in {competition}: ECE delta {ece_drift:+.4f}",
                details={"ece_drift": ece_drift, "current_ece": current_metrics.get("ece")},
                evidence=[f"ECE rose by {ece_drift:+.4f} exceeding 0.04 degradation gate."],
            )
            self._alerts.append(alert)

        return snapshot

    def list_snapshots(self, competition: str | None = None) -> list[dict[str, Any]]:
        res = self._snapshots
        if competition:
            res = [s for s in res if s.competition.upper() == competition.upper()]
        return [s.to_dict() for s in res]

    def list_alerts(self, competition: str | None = None) -> list[dict[str, Any]]:
        res = self._alerts
        if competition:
            res = [a for a in res if a.competition.upper() == competition.upper()]
        return [a.to_dict() for a in reversed(res)]


drift_monitor = ContinuousDriftMonitor()
