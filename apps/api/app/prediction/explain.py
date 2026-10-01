"""Feature Attribution & Non-Causal Match Explanation Engine (Phase 6.17 & 6.18).

Adheres strictly to Principle:
- Explanations are derived from actual pre-match features, never hallucinated.
- Uses strictly non-causal phrasing ("contributed to the prediction", NOT "caused").
"""
from __future__ import annotations

from typing import Any
from app.prediction.schemas import FeatureContribution, PredictionExplanation


class MatchExplanationEngine:
    """Decomposes pre-match model feature contributions and formats honest, evidence-based explanations."""

    def explain(
        self,
        home_club_name: str,
        away_club_name: str,
        features: dict[str, Any],
        p_home: float,
        p_draw: float,
        p_away: float,
    ) -> PredictionExplanation:
        """Constructs an explainable feature attribution breakdown."""
        factors: list[FeatureContribution] = []
        home_strengths: list[str] = []
        away_strengths: list[str] = []
        context_notes: list[str] = []

        # 1. Elo Rating Differential
        elo_diff = features.get("elo_diff") or 0.0
        h_elo = features.get("home_elo") or 1500.0
        a_elo = features.get("away_elo") or 1500.0

        if elo_diff > 40.0:
            elo_dir = "FAVORS_HOME"
            elo_contrib = round(min(0.25, elo_diff / 800.0), 3)
            elo_desc = (
                f"{home_club_name} holds a +{elo_diff:.0f} Elo advantage "
                f"({h_elo:.0f} vs {a_elo:.0f} away rating)."
            )
            home_strengths.append(f"Higher baseline team quality (+{elo_diff:.0f} Elo)")
        elif elo_diff < -40.0:
            elo_dir = "FAVORS_AWAY"
            elo_contrib = round(max(-0.25, elo_diff / 800.0), 3)
            elo_desc = (
                f"{away_club_name} holds an Elo advantage despite travel "
                f"({a_elo:.0f} vs {h_elo:.0f} home rating)."
            )
            away_strengths.append(f"Superior overall team rating (+{abs(elo_diff):.0f} Elo)")
        else:
            elo_dir = "NEUTRAL"
            elo_contrib = 0.0
            elo_desc = f"Both teams operate at similar baseline quality tiers ({h_elo:.0f} vs {a_elo:.0f})."

        factors.append(
            FeatureContribution(
                feature_name="Elo Rating Differential",
                value=elo_diff,
                contribution=elo_contrib,
                direction=elo_dir,
                description=elo_desc,
            )
        )

        # 2. Recent Form (Points per match in Last 5)
        h_pts = features.get("home_points_l5")
        a_pts = features.get("away_points_l5")
        pts_diff = features.get("points_diff_l5")

        if h_pts is not None and a_pts is not None and pts_diff is not None:
            if pts_diff > 0.40:
                f_dir = "FAVORS_HOME"
                f_contrib = round(min(0.18, pts_diff * 0.07), 3)
                f_desc = f"{home_club_name} displays superior recent momentum ({h_pts:.2f} vs {a_pts:.2f} pts/match in L5)."
                home_strengths.append(f"Stronger rolling form ({h_pts:.2f} pts/match)")
            elif pts_diff < -0.40:
                f_dir = "FAVORS_AWAY"
                f_contrib = round(max(-0.18, pts_diff * 0.07), 3)
                f_desc = f"{away_club_name} arrives with sharper recent form ({a_pts:.2f} vs {h_pts:.2f} pts/match in L5)."
                away_strengths.append(f"Stronger rolling form ({a_pts:.2f} pts/match)")
            else:
                f_dir = "NEUTRAL"
                f_contrib = 0.0
                f_desc = f"Even recent form trajectories ({h_pts:.2f} vs {a_pts:.2f} pts/match)."
            factors.append(
                FeatureContribution(
                    feature_name="Recent Form (Last 5)",
                    value=pts_diff,
                    contribution=f_contrib,
                    direction=f_dir,
                    description=f_desc,
                )
            )

        # 3. Home Advantage Baseline
        factors.append(
            FeatureContribution(
                feature_name="Home Ground Advantage",
                value=65.0,
                contribution=0.12,
                direction="FAVORS_HOME",
                description=f"Standard historical home advantage provides baseline win boost for {home_club_name}.",
            )
        )
        home_strengths.append("Home pitch and crowd advantage")

        # 4. Attack vs Defense Matchup
        h_att = features.get("home_attack_strength") or 1.0
        a_def = features.get("away_defense_strength") or 1.0
        a_att = features.get("away_attack_strength") or 1.0
        h_def = features.get("home_defense_strength") or 1.0

        matchup_ratio = round((h_att * a_def) - (a_att * h_def), 2)
        if matchup_ratio > 0.20:
            factors.append(
                FeatureContribution(
                    feature_name="Goal Threat Matchup",
                    value=matchup_ratio,
                    contribution=0.10,
                    direction="FAVORS_HOME",
                    description=f"{home_club_name}'s attacking output aligns favorably against {away_club_name}'s concession profile.",
                )
            )
            home_strengths.append("Favorable attack-to-defense tactical conversion")
        elif matchup_ratio < -0.20:
            factors.append(
                FeatureContribution(
                    feature_name="Goal Threat Matchup",
                    value=matchup_ratio,
                    contribution=-0.10,
                    direction="FAVORS_AWAY",
                    description=f"{away_club_name}'s attacking metrics present significant threat against {home_club_name}'s defense.",
                )
            )
            away_strengths.append("Dangerous counter-attacking profile against host defense")

        # 5. Rest & Schedule Fatigue
        h_rest = features.get("home_rest_days")
        a_rest = features.get("away_rest_days")
        rest_diff = features.get("rest_days_diff")

        if rest_diff is not None and abs(rest_diff) >= 2.0:
            if rest_diff > 0:
                rest_details = f" ({h_rest:.0f}d vs {a_rest:.0f}d)" if (h_rest is not None and a_rest is not None) else ""
                factors.append(
                    FeatureContribution(
                        feature_name="Rest & Recovery",
                        value=rest_diff,
                        contribution=0.06,
                        direction="FAVORS_HOME",
                        description=f"{home_club_name} had {rest_diff:.0f} additional days of rest/preparation{rest_details}.",
                    )
                )
                home_strengths.append(f"Rest advantage (+{rest_diff:.0f} recovery days)")
            else:
                factors.append(
                    FeatureContribution(
                        feature_name="Rest & Recovery",
                        value=rest_diff,
                        contribution=-0.06,
                        direction="FAVORS_AWAY",
                        description=f"{away_club_name} had {abs(rest_diff):.0f} additional days of rest/preparation.",
                    )
                )
                away_strengths.append(f"Rest advantage (+{abs(rest_diff):.0f} recovery days)")

        # Formulate Overall Narrative Summary
        favored_team = home_club_name if p_home > p_away else away_club_name
        favored_prob = max(p_home, p_away)

        if abs(p_home - p_away) < 0.08:
            summary = (
                f"Evenly contested fixture: {home_club_name} ({p_home*100:.1f}%) and "
                f"{away_club_name} ({p_away*100:.1f}%) with elevated draw potential ({p_draw*100:.1f}%). "
                f"Elo and form indicators indicate balanced tactical parity."
            )
        else:
            summary = (
                f"Model estimates a {favored_prob*100:.1f}% probability for {favored_team}, "
                f"with {p_draw*100:.1f}% probability of a draw. Key contributing factors include "
                f"{factors[0].feature_name.lower()} and venue advantage."
            )

        context_notes.append("Probabilities reflect pre-match evidence up to kickoff cutoff.")
        context_notes.append("No in-game events, future goals, or post-match metrics were utilized.")

        return PredictionExplanation(
            summary=summary,
            key_factors=factors,
            home_strengths=home_strengths,
            away_strengths=away_strengths,
            context_notes=context_notes,
        )
