"""Deterministic Team Strength Engine: Elo-Style Rating System (Phase 6.5).

Specifications:
- Initial Rating: 1500.0
- Base K-Factor: 32.0
- Home Advantage (H): +65.0 rating points
- Margin of Victory Multiplier: World Football Elo standard
- Pre-Match Freezing: Ratings are computed chronologically and frozen as of match kickoff.
"""
from __future__ import annotations

from datetime import datetime
import math
import uuid
from typing import Any, Sequence

INITIAL_RATING = 1500.0
DEFAULT_HOME_ADVANTAGE = 65.0
BASE_K_FACTOR = 32.0


def calculate_expected_score(
    rating_a: float,
    rating_b: float,
    home_advantage: float = 0.0,
) -> float:
    """Calculates expected score for team A vs team B using standard logistic curve.

    Expected score is in [0.0, 1.0] where 1.0 = certain win, 0.5 = equal, 0.0 = certain loss.
    """
    effective_diff = (rating_a + home_advantage) - rating_b
    return 1.0 / (1.0 + math.pow(10.0, -effective_diff / 400.0))


def compute_goal_difference_multiplier(goals_for: int, goals_against: int) -> float:
    """Calculates margin of victory multiplier based on World Football Elo ratings standard."""
    diff = abs(goals_for - goals_against)
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return (11.0 + diff) / 8.0


def elo_to_1x2_probabilities(
    home_rating: float,
    away_rating: float,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> tuple[float, float, float]:
    """Converts rating differential into a valid 1X2 probability distribution.

    Uses empirical logistic formulation where draw probability peaks at parity
    and decays smoothly with team disparity, strictly normalized to 1.0.
    """
    effective_diff = (home_rating + home_advantage) - away_rating

    # Draw probability modeled with a Gaussian decay centered at 0 disparity
    # At parity (diff=0), draw probability is ~27% (the historical European league median)
    base_draw_prob = 0.27
    decay_rate = 0.5 * (abs(effective_diff) / 400.0) ** 2
    p_draw = max(0.10, min(0.35, base_draw_prob * math.exp(-decay_rate)))

    # Remaining probability (1 - p_draw) divided between Home and Away based on logistic win expectancy
    e_home = 1.0 / (1.0 + math.pow(10.0, -effective_diff / 400.0))
    p_home_decisive = e_home
    p_away_decisive = 1.0 - e_home

    p_home = (1.0 - p_draw) * p_home_decisive
    p_away = (1.0 - p_draw) * p_away_decisive

    # Strict normalization to guarantee sum == 1.0 within float precision
    total = p_home + p_draw + p_away
    p_home_norm = round(p_home / total, 4)
    p_draw_norm = round(p_draw / total, 4)
    p_away_norm = round(1.0 - p_home_norm - p_draw_norm, 4)

    return p_home_norm, p_draw_norm, p_away_norm


class EloRatingEngine:
    """Computes, maintains, and freezes chronological team Elo ratings."""

    def __init__(
        self,
        base_rating: float = INITIAL_RATING,
        k_factor: float = BASE_K_FACTOR,
        home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    ) -> None:
        self.base_rating = base_rating
        self.k_factor = k_factor
        self.home_advantage = home_advantage

    def update_ratings(
        self,
        r_home: float,
        r_away: float,
        home_score: int,
        away_score: int,
    ) -> tuple[float, float]:
        """Calculates single match Elo rating adjustment for home and away clubs."""
        e_home = calculate_expected_score(r_home, r_away, self.home_advantage)
        e_away = 1.0 - e_home

        if home_score > away_score:
            s_home, s_away = 1.0, 0.0
        elif away_score > home_score:
            s_home, s_away = 0.0, 1.0
        else:
            s_home, s_away = 0.5, 0.5

        mov_mult = compute_goal_difference_multiplier(home_score, away_score)
        delta_home = self.k_factor * mov_mult * (s_home - e_home)
        delta_away = -delta_home

        return round(r_home + delta_home, 2), round(r_away + delta_away, 2)

    def compute_team_ratings_as_of(
        self,
        historical_matches: Sequence[Any],
        as_of: datetime,
    ) -> dict[uuid.UUID, float]:
        """Reconstructs point-in-time ratings strictly before as_of.

        Guarantees that no match kicking off at or after as_of affects the ratings.
        """
        ratings: dict[uuid.UUID, float] = {}

        # 1. Filter and sort matches strictly chronologically
        valid_matches = []
        for m in historical_matches:
            m_date = getattr(m, "date", None)
            if m_date is None and isinstance(m, dict):
                m_date = m.get("date")

            if m_date is not None and m_date < as_of:
                # Only finished matches with scores update ratings
                status = getattr(m, "status", None) or (m.get("status") if isinstance(m, dict) else None)
                if status in ("FT", "FINISHED", "AET", "PEN"):
                    valid_matches.append(m)

        valid_matches.sort(
            key=lambda x: getattr(x, "date", None) or x.get("date")
        )

        # 2. Sequential Elo updates
        for m in valid_matches:
            home_id = getattr(m, "home_club_id", None) or (m.get("home_club_id") if isinstance(m, dict) else None)
            away_id = getattr(m, "away_club_id", None) or (m.get("away_club_id") if isinstance(m, dict) else None)
            h_score = getattr(m, "home_score", None) if hasattr(m, "home_score") else (m.get("home_score") if isinstance(m, dict) else None)
            a_score = getattr(m, "away_score", None) if hasattr(m, "away_score") else (m.get("away_score") if isinstance(m, dict) else None)

            if home_id is None or away_id is None or h_score is None or a_score is None:
                continue

            r_home = ratings.get(home_id, self.base_rating)
            r_away = ratings.get(away_id, self.base_rating)

            # Expected score with home advantage
            e_home = calculate_expected_score(r_home, r_away, self.home_advantage)
            e_away = 1.0 - e_home

            # Actual score
            if h_score > a_score:
                s_home, s_away = 1.0, 0.0
            elif a_score > h_score:
                s_home, s_away = 0.0, 1.0
            else:
                s_home, s_away = 0.5, 0.5

            # Goal difference multiplier
            mov_mult = compute_goal_difference_multiplier(h_score, a_score)

            # Rating adjustment
            delta_home = self.k_factor * mov_mult * (s_home - e_home)
            delta_away = self.k_factor * mov_mult * (s_away - e_away)

            ratings[home_id] = round(r_home + delta_home, 2)
            ratings[away_id] = round(r_away + delta_away, 2)

        return ratings

    def get_match_ratings(
        self,
        home_club_id: uuid.UUID,
        away_club_id: uuid.UUID,
        historical_matches: Sequence[Any],
        as_of: datetime,
    ) -> tuple[float, float, float]:
        """Returns frozen pre-match (home_rating, away_rating, elo_diff) as of kickoff."""
        ratings = self.compute_team_ratings_as_of(historical_matches, as_of)
        r_home = ratings.get(home_club_id, self.base_rating)
        r_away = ratings.get(away_club_id, self.base_rating)
        elo_diff = round((r_home + self.home_advantage) - r_away, 2)
        return r_home, r_away, elo_diff
