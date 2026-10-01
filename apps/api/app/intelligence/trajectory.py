"""Longitudinal Player Trajectory Engine (Phase 3.2K).
Compiles chronological historical match-by-match performance, rolling output,
and seasonal trajectory without predictive simulation.
"""
from __future__ import annotations

from typing import Any


class TrajectoryCompiler:
    """Builds longitudinal trajectory profiles from chronological match statistics."""

    def compile_trajectory(
        self,
        stats_with_matches: list[tuple[Any, Any]],  # list of (PlayerMatchStats, Match) sorted by Match.date ASC
    ) -> dict[str, Any]:
        """Produces historical longitudinal performance and contribution progression."""
        if not stats_with_matches:
            return {
                "trajectory_status": "INSUFFICIENT_DATA",
                "total_recorded_matches": 0,
                "cumulative_minutes": 0,
                "volatility_score": None,
                "timeline": [],
                "seasonal_trend": [],
            }

        timeline: list[dict[str, Any]] = []
        cumulative_mins = 0
        ratings: list[float] = []

        seasons_dict: dict[str, dict[str, Any]] = {}

        for pms, m in stats_with_matches:
            mins = getattr(pms, "minutes", 0) or 0
            rating = getattr(pms, "rating", None)
            cumulative_mins += mins

            if rating is not None:
                ratings.append(float(rating))

            m_date = getattr(m, "date", None)
            date_str = m_date.isoformat() if m_date else None

            # Calculate match empirical impact estimate
            goals = getattr(pms, "goals", 0) or 0
            assists = getattr(pms, "assists", 0) or 0
            key_passes = getattr(pms, "passes_key", 0) or 0
            tackles = getattr(pms, "tackles_total", 0) or 0
            interceptions = getattr(pms, "interceptions", 0) or 0
            match_impact = round(
                1.0 * goals + 0.8 * assists + 0.25 * key_passes + 0.15 * tackles + 0.15 * interceptions,
                2,
            )

            timeline_item = {
                "match_id": str(getattr(pms, "match_id", "")),
                "date": date_str,
                "minutes": mins,
                "rating": rating,
                "goals": goals,
                "assists": assists,
                "match_impact": match_impact,
                "cumulative_minutes": cumulative_mins,
            }
            timeline.append(timeline_item)

            # Seasonal aggregation
            s_name = getattr(m, "round", None) or "Current"
            if s_name not in seasons_dict:
                seasons_dict[s_name] = {
                    "period": s_name,
                    "matches": 0,
                    "minutes": 0,
                    "goals": 0,
                    "assists": 0,
                    "rating_sum": 0.0,
                    "rated_matches": 0,
                }
            seasons_dict[s_name]["matches"] += 1
            seasons_dict[s_name]["minutes"] += mins
            seasons_dict[s_name]["goals"] += goals
            seasons_dict[s_name]["assists"] += assists
            if rating is not None:
                seasons_dict[s_name]["rating_sum"] += float(rating)
                seasons_dict[s_name]["rated_matches"] += 1

        # Volatility: standard deviation of ratings
        if len(ratings) >= 2:
            mean_r = sum(ratings) / len(ratings)
            variance = sum((r - mean_r) ** 2 for r in ratings) / (len(ratings) - 1)
            volatility = round(variance ** 0.5, 3)
        else:
            volatility = None

        seasonal_trend = []
        for s_key, s_data in seasons_dict.items():
            avg_r = (
                round(s_data["rating_sum"] / s_data["rated_matches"], 2)
                if s_data["rated_matches"] > 0
                else None
            )
            seasonal_trend.append({
                "period": s_data["period"],
                "matches": s_data["matches"],
                "minutes": s_data["minutes"],
                "goals": s_data["goals"],
                "assists": s_data["assists"],
                "average_rating": avg_r,
            })

        status = "EVALUATED" if len(timeline) >= 3 else "INSUFFICIENT_SAMPLE"

        return {
            "trajectory_status": status,
            "total_recorded_matches": len(timeline),
            "cumulative_minutes": cumulative_mins,
            "volatility_score": volatility,
            "timeline": timeline,
            "seasonal_trend": seasonal_trend,
        }
