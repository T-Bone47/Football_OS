"""Position-Aware Peer Benchmarking Engine (Phase 3.2D).
Calculates standardized Z-scores, normal percentiles, and peer distributions
relative to verified position groups (GK, DEF, MID, ATT).
"""
from __future__ import annotations

import math
from typing import Any

from app.intelligence.taxonomy import BenchmarkGroup, MIN_MINUTES_EVALUATED


# Reference empirical distributions (mean, std) by position group derived from top-tier league baselines
PEER_DISTRIBUTIONS: dict[str, dict[str, tuple[float, float]]] = {
    "GK": {
        "saves_p90": (3.10, 1.10),
        "goals_conceded_p90": (1.30, 0.60),
        "passes_total_p90": (26.0, 8.5),
        "pass_accuracy": (66.0, 12.0),
    },
    "DEF": {
        "tackles_total_p90": (1.90, 0.85),
        "interceptions_p90": (1.40, 0.65),
        "blocks_p90": (0.75, 0.40),
        "duels_won_p90": (3.60, 1.40),
        "passes_total_p90": (48.0, 16.0),
        "pass_accuracy": (83.0, 6.5),
    },
    "MID": {
        "passes_total_p90": (52.0, 18.0),
        "pass_accuracy": (84.5, 5.5),
        "passes_key_p90": (1.20, 0.70),
        "tackles_total_p90": (1.80, 0.80),
        "interceptions_p90": (1.20, 0.60),
        "dribbles_success_p90": (1.15, 0.75),
        "duels_won_p90": (4.10, 1.50),
    },
    "ATT": {
        "shots_total_p90": (2.45, 1.05),
        "shots_on_target_p90": (1.05, 0.55),
        "goals_p90": (0.32, 0.28),
        "passes_key_p90": (1.35, 0.70),
        "dribbles_success_p90": (1.65, 0.95),
        "duels_won_p90": (3.10, 1.30),
    },
}


def _norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function (error function approximation)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class PeerBenchmarkingEngine:
    """Computes standardized peer benchmark metrics for a player's position family."""

    def evaluate_benchmarks(
        self,
        raw_metrics: dict[str, Any],
        position_group: str,
        sample_minutes: int,
        peer_population_size: int = 50,
    ) -> dict[str, Any]:
        """Calculates Z-scores, normal percentiles, and group distributions for key metrics.
        Strictly enforces data sufficiency gate (< 270 mins -> percentiles are None).
        """
        pos_grp = position_group.upper() if position_group in PEER_DISTRIBUTIONS else "MID"
        distributions = PEER_DISTRIBUTIONS[pos_grp]

        if sample_minutes < MIN_MINUTES_EVALUATED:
            # Insufficient sample: return metric placeholders with None percentiles
            items = {}
            for metric in distributions:
                items[metric] = {
                    "metric": metric,
                    "value_p90": raw_metrics.get(f"{metric}_p90") if f"{metric}_p90" in raw_metrics else raw_metrics.get(metric),
                    "peer_mean": distributions[metric][0],
                    "peer_std": distributions[metric][1],
                    "z_score": None,
                    "percentile": None,
                    "status": "INSUFFICIENT_SAMPLE",
                }
            return {
                "position_group": pos_grp,
                "benchmark_status": "INSUFFICIENT_SAMPLE",
                "sample_minutes": sample_minutes,
                "average_percentile": None,
                "metrics": items,
            }

        items = {}
        percentiles: list[float] = []

        for metric, (mean, std) in distributions.items():
            val = raw_metrics.get(f"{metric}_p90") if f"{metric}_p90" in raw_metrics else raw_metrics.get(metric)
            if val is not None and isinstance(val, (int, float)):
                # Clamped Z-score to [-3.0, 3.0] to prevent outlier distortion
                z = max(-3.0, min(3.0, (float(val) - mean) / std))
                pct = round(_norm_cdf(z) * 100.0, 1)
                percentiles.append(pct)
                items[metric] = {
                    "metric": metric,
                    "value_p90": round(float(val), 2),
                    "peer_mean": mean,
                    "peer_std": std,
                    "z_score": round(z, 2),
                    "percentile": pct,
                    "status": "EVALUATED",
                }
            else:
                items[metric] = {
                    "metric": metric,
                    "value_p90": None,
                    "peer_mean": mean,
                    "peer_std": std,
                    "z_score": None,
                    "percentile": None,
                    "status": "NOT_OBSERVED",
                }

        avg_pct = round(sum(percentiles) / len(percentiles), 1) if percentiles else None

        return {
            "position_group": pos_grp,
            "benchmark_status": "EVALUATED",
            "sample_minutes": sample_minutes,
            "peer_sample_size": peer_population_size,
            "average_percentile": avg_pct,
            "metrics": items,
        }
