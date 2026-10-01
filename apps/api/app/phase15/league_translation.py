"""Descriptive League Translation Intelligence for Phase 15.

Evaluates transitions from SOURCE_COMPETITION -> TARGET_COMPETITION across:
1. Contribution
2. Role
3. Minutes
4. Tactical usage
5. Physical workload (where available)
6. Availability
7. Valuation movement
8. Transfer realization

Rule:
- Non-causal policy: League A does NOT "cause" improvement or decline.
- Uses: OBSERVED_ASSOCIATION, TRANSLATION_UNCERTAINTY, INSUFFICIENT_EVIDENCE.
"""

from typing import Any
from pydantic import BaseModel, Field
from app.phase15.causality_guardrail import CausalityGuardrail


class DimensionTranslation(BaseModel):
    dimension: str
    source_mean: float | None = None
    target_mean: float | None = None
    delta_mean: float | None = None
    delta_percent: float | None = None
    uncertainty_band: tuple[float, float] | None = None
    sample_size: int
    evidence_status: str  # OBSERVED_ASSOCIATION, TRANSLATION_UNCERTAINTY, INSUFFICIENT_EVIDENCE
    descriptive_finding: str


class LeagueTranslationReport(BaseModel):
    translation_id: str
    source_competition: str
    target_competition: str
    total_transitioned_players: int
    dimensions: dict[str, DimensionTranslation]
    overall_translation_uncertainty: str
    non_causal_statement: str
    sample_limitations: list[str] = Field(default_factory=list)


class LeagueTranslationEngine:
    """Computes descriptive league-to-league transition distributions without causal claims."""

    def __init__(self, min_samples_per_dimension: int = 10) -> None:
        self.min_samples_per_dimension = min_samples_per_dimension
        self._reports: dict[str, LeagueTranslationReport] = {}

    def analyze_translation(
        self,
        source_competition: str,
        target_competition: str,
        transitions_data: list[dict[str, Any]],
    ) -> LeagueTranslationReport:
        translation_id = f"trans_{source_competition.lower()}_to_{target_competition.lower()}"
        n_players = len(transitions_data)

        dim_keys = [
            "contribution",
            "role_usage",
            "minutes",
            "tactical_usage",
            "physical_workload",
            "availability",
            "valuation",
            "transfer_realization",
        ]

        dimensions: dict[str, DimensionTranslation] = {}
        limitations: list[str] = []

        if n_players < self.min_samples_per_dimension:
            limitations.append(
                f"Sample size (N={n_players}) is below minimum statistical threshold ({self.min_samples_per_dimension})."
            )

        for dim in dim_keys:
            # Gather pairs
            valid_pairs = [
                (t[f"{dim}_src"], t[f"{dim}_tgt"])
                for t in transitions_data
                if f"{dim}_src" in t and f"{dim}_tgt" in t and t[f"{dim}_src"] is not None and t[f"{dim}_tgt"] is not None
            ]

            n_dim = len(valid_pairs)
            if n_dim < 5:
                dimensions[dim] = DimensionTranslation(
                    dimension=dim,
                    sample_size=n_dim,
                    evidence_status="INSUFFICIENT_EVIDENCE",
                    descriptive_finding=f"Insufficient observed pairs (N={n_dim}) for descriptive transition analysis in {dim}.",
                )
                continue

            src_vals = [p[0] for p in valid_pairs]
            tgt_vals = [p[1] for p in valid_pairs]
            src_mean = round(sum(src_vals) / n_dim, 3)
            tgt_mean = round(sum(tgt_vals) / n_dim, 3)
            delta = round(tgt_mean - src_mean, 3)
            delta_pct = round((delta / max(abs(src_mean), 1e-4)) * 100, 2)

            evidence_status = "OBSERVED_ASSOCIATION" if n_dim >= self.min_samples_per_dimension else "TRANSLATION_UNCERTAINTY"
            diffs = [p[1] - p[0] for p in valid_pairs]
            sorted_diffs = sorted(diffs)
            p10 = sorted_diffs[int(0.10 * n_dim)]
            p90 = sorted_diffs[min(int(0.90 * n_dim), n_dim - 1)]

            dimensions[dim] = DimensionTranslation(
                dimension=dim,
                source_mean=src_mean,
                target_mean=tgt_mean,
                delta_mean=delta,
                delta_percent=delta_pct,
                uncertainty_band=(round(p10, 3), round(p90, 3)),
                sample_size=n_dim,
                evidence_status=evidence_status,
                descriptive_finding=f"Observed average {dim} shifted by {delta_pct:+0.1f}% between {source_competition} and {target_competition} (P10-P90: [{p10:+.2f}, {p90:+.2f}]).",
            )

        non_causal_statement = CausalityGuardrail.generate_statement(
            metric=f"metrics upon transition from {source_competition} to {target_competition}",
            condition=f"cohort of {n_players} players",
            relationship="associated",
        )

        report = LeagueTranslationReport(
            translation_id=translation_id,
            source_competition=source_competition,
            target_competition=target_competition,
            total_transitioned_players=n_players,
            dimensions=dimensions,
            overall_translation_uncertainty="Moderate-to-High across contextual dimensions",
            non_causal_statement=non_causal_statement,
            sample_limitations=limitations,
        )

        self._reports[translation_id] = report
        return report

    def get_report(self, source_comp: str, target_comp: str) -> LeagueTranslationReport:
        translation_id = f"trans_{source_comp.lower()}_to_{target_comp.lower()}"
        if translation_id not in self._reports:
            raise KeyError(f"No translation report found for {source_comp} -> {target_comp}")
        return self._reports[translation_id]

    def list_reports(self) -> list[LeagueTranslationReport]:
        return list(self._reports.values())


_GLOBAL_LEAGUE_TRANSLATION_ENGINE: LeagueTranslationEngine | None = None


def get_league_translation_engine() -> LeagueTranslationEngine:
    global _GLOBAL_LEAGUE_TRANSLATION_ENGINE
    if _GLOBAL_LEAGUE_TRANSLATION_ENGINE is None:
        _GLOBAL_LEAGUE_TRANSLATION_ENGINE = LeagueTranslationEngine()
        # Seed realistic Bundesliga -> EPL transition cohort
        sample_transitions = [
            {"contribution_src": 0.58, "contribution_tgt": 0.51, "minutes_src": 2400, "minutes_tgt": 1950, "valuation_src": 35.0, "valuation_tgt": 42.0},
            {"contribution_src": 0.62, "contribution_tgt": 0.59, "minutes_src": 2600, "minutes_tgt": 2200, "valuation_src": 45.0, "valuation_tgt": 55.0},
            {"contribution_src": 0.44, "contribution_tgt": 0.38, "minutes_src": 1800, "minutes_tgt": 1300, "valuation_src": 20.0, "valuation_tgt": 22.0},
            {"contribution_src": 0.70, "contribution_tgt": 0.66, "minutes_src": 2800, "minutes_tgt": 2500, "valuation_src": 60.0, "valuation_tgt": 75.0},
            {"contribution_src": 0.52, "contribution_tgt": 0.48, "minutes_src": 2100, "minutes_tgt": 1800, "valuation_src": 28.0, "valuation_tgt": 32.0},
            {"contribution_src": 0.55, "contribution_tgt": 0.54, "minutes_src": 2300, "minutes_tgt": 2050, "valuation_src": 32.0, "valuation_tgt": 38.0},
            {"contribution_src": 0.49, "contribution_tgt": 0.42, "minutes_src": 1900, "minutes_tgt": 1400, "valuation_src": 24.0, "valuation_tgt": 26.0},
            {"contribution_src": 0.65, "contribution_tgt": 0.61, "minutes_src": 2700, "minutes_tgt": 2400, "valuation_src": 50.0, "valuation_tgt": 62.0},
            {"contribution_src": 0.40, "contribution_tgt": 0.35, "minutes_src": 1700, "minutes_tgt": 1100, "valuation_src": 18.0, "valuation_tgt": 19.0},
            {"contribution_src": 0.59, "contribution_tgt": 0.56, "minutes_src": 2450, "minutes_tgt": 2150, "valuation_src": 38.0, "valuation_tgt": 46.0},
            {"contribution_src": 0.68, "contribution_tgt": 0.63, "minutes_src": 2750, "minutes_tgt": 2350, "valuation_src": 55.0, "valuation_tgt": 68.0},
        ]
        _GLOBAL_LEAGUE_TRANSLATION_ENGINE.analyze_translation(
            source_competition="Bundesliga",
            target_competition="EPL",
            transitions_data=sample_transitions,
        )
    return _GLOBAL_LEAGUE_TRANSLATION_ENGINE
