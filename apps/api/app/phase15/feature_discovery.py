"""Governed Feature Discovery for Phase 15.

Tracks candidate features identified in empirical experiments:
- Evaluates stability, leakage status, and OOD sensitivity across competitions.
- Prohibits automatic production promotion.
"""

from app.phase15.research_models import FeatureCandidate


class FeatureDiscoveryEngine:
    """Manages discovery, leakage audits, and stability scoring of candidate features."""

    def __init__(self) -> None:
        self._candidates: dict[str, FeatureCandidate] = {}

    def register_candidate(
        self,
        candidate_id: str,
        feature_name: str,
        target_metric: str,
        rationale: str,
        discovered_in_experiments: list[str],
        effect_magnitude: float,
        stability_score: float,
        leakage_audited: bool = True,
        ood_sensitivity: str = "LOW",
        competition_coverage: list[str] | None = None,
    ) -> FeatureCandidate:
        candidate = FeatureCandidate(
            research_id=f"res_{candidate_id}",
            candidate_id=candidate_id,
            feature_name=feature_name,
            target_metric=target_metric,
            rationale=rationale,
            discovered_in_experiments=discovered_in_experiments,
            effect_magnitude=round(effect_magnitude, 4),
            stability_score=round(stability_score, 4),
            leakage_audited=leakage_audited,
            ood_sensitivity=ood_sensitivity,
            competition_coverage=competition_coverage or ["EPL", "La_Liga", "Bundesliga"],
            production_ready=False,  # Enforce governed gate: never auto-promoted
        )
        self._candidates[candidate_id] = candidate
        return candidate

    def get_candidate(self, candidate_id: str) -> FeatureCandidate:
        if candidate_id not in self._candidates:
            raise KeyError(f"FeatureCandidate '{candidate_id}' not found.")
        return self._candidates[candidate_id]

    def list_candidates(self) -> list[FeatureCandidate]:
        return list(self._candidates.values())


_GLOBAL_FEATURE_ENGINE: FeatureDiscoveryEngine | None = None


def get_feature_discovery_engine() -> FeatureDiscoveryEngine:
    global _GLOBAL_FEATURE_ENGINE
    if _GLOBAL_FEATURE_ENGINE is None:
        _GLOBAL_FEATURE_ENGINE = FeatureDiscoveryEngine()
        _GLOBAL_FEATURE_ENGINE.register_candidate(
            candidate_id="feat_oppo_box_entry_slope",
            feature_name="box_entry_retention_ratio",
            target_metric="goal_contribution_p90",
            rationale="Measures proportion of box entries resulting in shot or second-phase retention, consistently outperforming raw box touches.",
            discovered_in_experiments=["exp_u23_retention_study"],
            effect_magnitude=0.312,
            stability_score=0.88,
            leakage_audited=True,
            ood_sensitivity="LOW",
            competition_coverage=["EPL", "La_Liga", "Bundesliga", "Serie_A"],
        )
        _GLOBAL_FEATURE_ENGINE.register_candidate(
            candidate_id="feat_counter_press_recovery_distance",
            feature_name="recovery_distance_from_possession_loss",
            target_metric="defensive_transition_score",
            rationale="Average meters traveled toward ball within 5 seconds of turnover.",
            discovered_in_experiments=["exp_u23_retention_study"],
            effect_magnitude=0.225,
            stability_score=0.79,
            leakage_audited=True,
            ood_sensitivity="MEDIUM",
            competition_coverage=["EPL", "Bundesliga"],
        )
    return _GLOBAL_FEATURE_ENGINE
