"""Pre-Match Feature Builder & Temporal Snapshot Engine (Phase 6.2, 6.3, 6.4).

Guarantees:
- Strict Pre-Match Cutoff: Every feature uses ONLY matches strictly preceding the kickoff (match.date < as_of).
- Zero Target Leakage: The current match's result, score, and events are strictly forbidden from features.
- Reproducible Snapshots: Generates an immutable PredictionSnapshot tracking exact feature values and provenance.
"""
from __future__ import annotations

from datetime import datetime
import math
import uuid
from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field

from app.prediction.elo import DEFAULT_HOME_ADVANTAGE, EloRatingEngine

FEATURE_SET_VERSION = "match_prediction_v2"
CALCULATION_VERSION = "temporal_pre_match_v1"


class PredictionSnapshot(BaseModel):
    """Immutable pre-match analytical snapshot used for inference and reproducibility."""
    model_config = ConfigDict(extra="ignore")

    match_id: uuid.UUID
    as_of: datetime
    prediction_time: datetime
    home_club_id: uuid.UUID
    away_club_id: uuid.UUID
    competition_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    feature_version: str = FEATURE_SET_VERSION
    calculation_version: str = CALCULATION_VERSION
    features: dict[str, float | None]
    home_sample_size: int
    away_sample_size: int
    h2h_sample_size: int
    data_status: str


class PreMatchFeatureBuilder:
    """Extracts leakage-safe pre-match features across Team Strength, Form, Venue, Rest, and H2H."""

    def __init__(self, elo_engine: EloRatingEngine | None = None) -> None:
        self.elo_engine = elo_engine or EloRatingEngine()

    def build_features(
        self,
        match_id: uuid.UUID,
        home_club_id: uuid.UUID,
        away_club_id: uuid.UUID,
        kickoff_time: datetime,
        historical_matches: Sequence[Any],
        as_of: datetime | None = None,
        competition_id: uuid.UUID | None = None,
        season_id: uuid.UUID | None = None,
    ) -> PredictionSnapshot:
        """Constructs an immutable PredictionSnapshot strictly as of the cutoff timestamp."""
        eval_cutoff = as_of if as_of is not None else kickoff_time
        # Strict pre-match condition: cannot look into kickoff itself or future
        cutoff = min(kickoff_time, eval_cutoff)

        # 1. Filter matches strictly before cutoff
        past_matches = []
        for m in historical_matches:
            m_date = getattr(m, "date", None)
            if m_date is None and isinstance(m, dict):
                m_date = m.get("date")

            m_id = getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else None)
            # Never include the match itself
            if m_id == match_id:
                continue

            if m_date is not None and m_date < cutoff:
                status = getattr(m, "status", None) or (m.get("status") if isinstance(m, dict) else None)
                if status in ("FT", "FINISHED", "AET", "PEN"):
                    past_matches.append(m)

        past_matches.sort(
            key=lambda x: getattr(x, "date", None) or x.get("date")
        )

        # 2. Team Strength (Elo)
        home_elo, away_elo, elo_diff = self.elo_engine.get_match_ratings(
            home_club_id, away_club_id, past_matches, cutoff
        )

        # 3. Filter chronological sub-sequences for home and away teams
        home_history = []
        away_history = []
        h2h_history = []

        for m in past_matches:
            h_id = getattr(m, "home_club_id", None) or (m.get("home_club_id") if isinstance(m, dict) else None)
            a_id = getattr(m, "away_club_id", None) or (m.get("away_club_id") if isinstance(m, dict) else None)

            is_home_in_m = (h_id == home_club_id or a_id == home_club_id)
            is_away_in_m = (h_id == away_club_id or a_id == away_club_id)

            if is_home_in_m:
                home_history.append(m)
            if is_away_in_m:
                away_history.append(m)
            if (h_id == home_club_id and a_id == away_club_id) or (h_id == away_club_id and a_id == home_club_id):
                h2h_history.append(m)

        # 4. Form and Goal Statistics for a team history
        def extract_team_stats(team_id: uuid.UUID, history: list[Any], window: int) -> dict[str, float | None]:
            recent = history[-window:] if window > 0 else history
            if not recent:
                return {
                    "points_per_match": None,
                    "goals_scored_per_match": None,
                    "goals_conceded_per_match": None,
                    "goal_diff_per_match": None,
                    "win_rate": None,
                }

            points = 0
            goals_for = 0
            goals_against = 0
            wins = 0

            for m in recent:
                h_id = getattr(m, "home_club_id", None) or (m.get("home_club_id") if isinstance(m, dict) else None)
                h_sc = getattr(m, "home_score", None) if hasattr(m, "home_score") else (m.get("home_score") if isinstance(m, dict) else None)
                a_sc = getattr(m, "away_score", None) if hasattr(m, "away_score") else (m.get("away_score") if isinstance(m, dict) else None)

                if h_sc is None or a_sc is None:
                    continue

                if h_id == team_id:
                    gf, ga = h_sc, a_sc
                else:
                    gf, ga = a_sc, h_sc

                goals_for += gf
                goals_against += ga

                if gf > ga:
                    points += 3
                    wins += 1
                elif gf == ga:
                    points += 1

            n = len(recent)
            return {
                "points_per_match": round(points / n, 3),
                "goals_scored_per_match": round(goals_for / n, 3),
                "goals_conceded_per_match": round(goals_against / n, 3),
                "goal_diff_per_match": round((goals_for - goals_against) / n, 3),
                "win_rate": round(wins / n, 3),
            }

        home_l5 = extract_team_stats(home_club_id, home_history, 5)
        away_l5 = extract_team_stats(away_club_id, away_history, 5)
        home_l3 = extract_team_stats(home_club_id, home_history, 3)
        away_l3 = extract_team_stats(away_club_id, away_history, 3)

        # 5. Venue specific performance (Home at Home, Away at Away)
        home_home_matches = [
            m for m in home_history
            if (getattr(m, "home_club_id", None) or m.get("home_club_id")) == home_club_id
        ]
        away_away_matches = [
            m for m in away_history
            if (getattr(m, "away_club_id", None) or m.get("away_club_id")) == away_club_id
        ]
        home_venue_stats = extract_team_stats(home_club_id, home_home_matches, 5)
        away_venue_stats = extract_team_stats(away_club_id, away_away_matches, 5)

        # 6. Relative Attack & Defense parameters (relative to 1.30 baseline per team)
        h_scored = home_l5["goals_scored_per_match"] if home_l5["goals_scored_per_match"] is not None else 1.35
        h_conceded = home_l5["goals_conceded_per_match"] if home_l5["goals_conceded_per_match"] is not None else 1.20
        a_scored = away_l5["goals_scored_per_match"] if away_l5["goals_scored_per_match"] is not None else 1.15
        a_conceded = away_l5["goals_conceded_per_match"] if away_l5["goals_conceded_per_match"] is not None else 1.35

        home_att_strength = round(max(0.40, min(2.50, h_scored / 1.30)), 3)
        home_def_strength = round(max(0.40, min(2.50, h_conceded / 1.30)), 3)
        away_att_strength = round(max(0.40, min(2.50, a_scored / 1.30)), 3)
        away_def_strength = round(max(0.40, min(2.50, a_conceded / 1.30)), 3)

        # 7. Rest Days
        def get_rest_days(history: list[Any]) -> float | None:
            if not history:
                return None
            last_m = history[-1]
            last_date = getattr(last_m, "date", None) or last_m.get("date")
            if last_date:
                # Rest before the fixture, measured at kickoff. (v1 measured at
                # the request time, so the same fixture got different values
                # depending on when it was asked; train/serve skew, Phase 18.)
                days = (kickoff_time - last_date).total_seconds() / 86400.0
                return round(max(0.0, min(30.0, days)), 1)
            return None

        home_rest = get_rest_days(home_history)
        away_rest = get_rest_days(away_history)
        rest_diff = round(home_rest - away_rest, 1) if (home_rest is not None and away_rest is not None) else None

        # 8. Head to Head Record
        h2h_h_wins = 0
        h2h_draws = 0
        h2h_a_wins = 0
        for m in h2h_history:
            h_id = getattr(m, "home_club_id", None) or (m.get("home_club_id") if isinstance(m, dict) else None)
            h_sc = getattr(m, "home_score", None) if hasattr(m, "home_score") else (m.get("home_score") if isinstance(m, dict) else None)
            a_sc = getattr(m, "away_score", None) if hasattr(m, "away_score") else (m.get("away_score") if isinstance(m, dict) else None)
            if h_sc is not None and a_sc is not None:
                if h_sc > a_sc:
                    if h_id == home_club_id:
                        h2h_h_wins += 1
                    else:
                        h2h_a_wins += 1
                elif h_sc < a_sc:
                    if h_id == home_club_id:
                        h2h_a_wins += 1
                    else:
                        h2h_h_wins += 1
                else:
                    h2h_draws += 1

        # 9. Data Status Gating
        home_n = len(home_history)
        away_n = len(away_history)
        if home_n == 0 and away_n == 0:
            data_status = "INSUFFICIENT_DATA"
        elif home_n < 3 or away_n < 3:
            data_status = "LOW_CONFIDENCE"
        else:
            data_status = "PREDICTION_AVAILABLE"

        feature_dict = {
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": elo_diff,
            "home_points_l5": home_l5["points_per_match"],
            "away_points_l5": away_l5["points_per_match"],
            "points_diff_l5": (
                round(home_l5["points_per_match"] - away_l5["points_per_match"], 3)
                if home_l5["points_per_match"] is not None and away_l5["points_per_match"] is not None
                else None
            ),
            "home_points_l3": home_l3["points_per_match"],
            "away_points_l3": away_l3["points_per_match"],
            "home_goals_scored_l5": home_l5["goals_scored_per_match"],
            "away_goals_scored_l5": away_l5["goals_scored_per_match"],
            "home_goals_conceded_l5": home_l5["goals_conceded_per_match"],
            "away_goals_conceded_l5": away_l5["goals_conceded_per_match"],
            "home_goal_diff_l5": home_l5["goal_diff_per_match"],
            "away_goal_diff_l5": away_l5["goal_diff_per_match"],
            "home_win_rate_l5": home_l5["win_rate"],
            "away_win_rate_l5": away_l5["win_rate"],
            "home_venue_points_l5": home_venue_stats["points_per_match"],
            "away_venue_points_l5": away_venue_stats["points_per_match"],
            "home_attack_strength": home_att_strength,
            "home_defense_strength": home_def_strength,
            "away_attack_strength": away_att_strength,
            "away_defense_strength": away_def_strength,
            "home_rest_days": home_rest,
            "away_rest_days": away_rest,
            "rest_days_diff": rest_diff,
            "h2h_home_wins": h2h_h_wins,
            "h2h_draws": h2h_draws,
            "h2h_away_wins": h2h_a_wins,
            "home_sample_size": home_n,
            "away_sample_size": away_n,
        }

        return PredictionSnapshot(
            match_id=match_id,
            as_of=cutoff,
            prediction_time=datetime.now(),
            home_club_id=home_club_id,
            away_club_id=away_club_id,
            competition_id=competition_id,
            season_id=season_id,
            feature_version=FEATURE_SET_VERSION,
            calculation_version=CALCULATION_VERSION,
            features=feature_dict,
            home_sample_size=home_n,
            away_sample_size=away_n,
            h2h_sample_size=len(h2h_history),
            data_status=data_status,
        )
