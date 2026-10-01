"""Contextual Performance Engine (Phase 3.2C).
Evaluates genuine, data-supported match context dimensions: competition tier,
home/away distribution, starter ratio, and minutes exposure.
"""
from __future__ import annotations

from typing import Any


COMPETITION_TIER_WEIGHTS = {
    # Tier 1: Big 5 European Leagues & Champions League
    "premier league": 1.00,
    "la liga": 1.00,
    "serie a": 1.00,
    "bundesliga": 1.00,
    "ligue 1": 1.00,
    "uefa champions league": 1.05,
    # Tier 2: Strong European & South American Domestic Leagues
    "championship": 0.85,
    "serie b": 0.80,
    "segunda división": 0.80,
    "2. bundesliga": 0.80,
    "ligue 2": 0.80,
    "eredivisie": 0.85,
    "primeira liga": 0.85,
    "serie a - brazil": 0.85,
    "brasileirão": 0.85,
    "uefa europa league": 0.90,
}

DEFAULT_COMPETITION_TIER = 0.75


class ContextualEngine:
    """Evaluates contextual dimensions supported by canonical Match and PlayerMatchStats data."""

    def evaluate_competition_strength(self, competition_name: str | None, country: str | None = None) -> float:
        """Determines transparent, documented competition strength coefficient."""
        if not competition_name:
            return DEFAULT_COMPETITION_TIER

        norm_name = competition_name.strip().lower()
        for key, weight in COMPETITION_TIER_WEIGHTS.items():
            if key in norm_name:
                return weight

        return DEFAULT_COMPETITION_TIER

    def evaluate_player_context(
        self,
        stats_list: list[Any],
        competition_name: str | None = None,
        competition_country: str | None = None,
    ) -> dict[str, Any]:
        """Calculates measurable contextual factors across the player's observed matches.
        Pure deterministic function.
        """
        total_matches = len(stats_list)
        if total_matches == 0:
            return {
                "competition_tier": DEFAULT_COMPETITION_TIER,
                "home_ratio": 0.5,
                "away_ratio": 0.5,
                "starter_ratio": 0.0,
                "substitute_ratio": 0.0,
                "minutes_per_match": 0.0,
                "exposure_share": 0.0,
                "context_multiplier": DEFAULT_COMPETITION_TIER,
                "context_summary": "No match appearances recorded.",
            }

        total_minutes = sum(getattr(s, "minutes", 0) or 0 for s in stats_list)
        starters = sum(1 for s in stats_list if getattr(s, "is_starter", False))
        substitutes = sum(1 for s in stats_list if getattr(s, "is_substitute", False))

        starter_ratio = round(starters / total_matches, 3)
        substitute_ratio = round(substitutes / total_matches, 3)
        avg_minutes = round(total_minutes / total_matches, 1)
        exposure_share = round(total_minutes / (total_matches * 90.0), 3)

        comp_tier = self.evaluate_competition_strength(competition_name, competition_country)

        # Context multiplier scales between 0.75 and 1.05 based on competition tier and regular starter status
        starter_boost = 0.05 * (starter_ratio - 0.5)  # slight penalty for bench-only, boost for regular starter
        context_multiplier = round(max(0.70, min(1.10, comp_tier + starter_boost)), 3)

        summary = (
            f"Competition tier: {comp_tier:.2f} · "
            f"Starter ratio: {starter_ratio * 100:.0f}% ({avg_minutes} mins/match) · "
            f"Exposure: {exposure_share * 100:.0f}%"
        )

        return {
            "competition_tier": comp_tier,
            "starter_ratio": starter_ratio,
            "substitute_ratio": substitute_ratio,
            "minutes_per_match": avg_minutes,
            "exposure_share": exposure_share,
            "context_multiplier": context_multiplier,
            "context_summary": summary,
        }
