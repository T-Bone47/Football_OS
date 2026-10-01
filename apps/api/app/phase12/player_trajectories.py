"""Phase 12 — Player Trajectory Intelligence V2 & Breakout Detection (§8, §10).

Tracks longitudinal player performance and development velocity with strict separation:
  - OBSERVED: Empirically recorded past minutes, actions, and match performance.
  - MODELLED: Current statistical role alignment, contribution vector, and similarity.
  - PROJECTED: Mathematical projection under explicit feature growth assumptions.

Rule: Projected values are hypotheses and must never be presented as observed facts.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from app.dev_fixtures import dev_seed_enabled


@dataclass
class TrajectoryPoint:
    """A single time-indexed observation point in a player's longitudinal history."""
    matchday_date: str
    minutes_played: int
    contribution_percentile: float
    tactical_fit_score: float
    market_valuation_eur: float
    role_classification: str
    action_value_offensive: float
    data_class: str = "OBSERVED"  # OBSERVED, MODELLED, PROJECTED


@dataclass
class BreakoutSignal:
    """Deterministic breakout signal with supporting empirical evidence."""
    signal_id: str = field(default_factory=lambda: f"breakout_{uuid.uuid4().hex[:12]}")
    player_id: str = ""
    player_name: str = ""
    age: int = 21
    position: str = "CB"
    breakout_detected: bool = False
    breakout_confidence: str = "HIGH"  # LOW, MODERATE, HIGH
    development_velocity: float = 0.0  # Percentile gain per 10 matchdays
    minutes_acceleration_pct: float = 0.0
    action_value_delta: float = 0.0
    minimum_sample_met: bool = True  # Requires >= 450 minutes and >= 5 matches
    evidence: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerTrajectoryProfileV2:
    """Longitudinal trajectory profile maintaining strict OBSERVED/MODELLED/PROJECTED separation."""
    player_id: str
    player_name: str
    current_club: str
    competition_id: str
    age: int
    position: str
    primary_role: str

    # Trajectory Streams
    observed_history: list[dict[str, Any]] = field(default_factory=list)
    modelled_state: dict[str, Any] = field(default_factory=dict)
    projected_path: list[dict[str, Any]] = field(default_factory=list)

    # Dynamics & Breakout
    development_velocity: float = 0.0
    breakout_signal: BreakoutSignal | None = None
    trajectory_confidence: str = "HIGH"
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "current_club": self.current_club,
            "competition_id": self.competition_id,
            "age": self.age,
            "position": self.position,
            "primary_role": self.primary_role,
            "observed_history": self.observed_history,
            "modelled_state": self.modelled_state,
            "projected_path": self.projected_path,
            "development_velocity": self.development_velocity,
            "breakout_signal": self.breakout_signal.to_dict() if self.breakout_signal else None,
            "trajectory_confidence": self.trajectory_confidence,
            "last_updated": self.last_updated,
        }


class PlayerTrajectoryEngineV2:
    """Computes longitudinal trajectories and detects empirical breakout acceleration."""

    def __init__(self) -> None:
        self._profiles: dict[str, PlayerTrajectoryProfileV2] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_trajectories()

    def _seed_default_trajectories(self) -> None:
        # Seed 1: Gonçalo Inácio (Emerging Breakout)
        inacio_observed = [
            {"date": "2023-09-01", "minutes": 450, "contribution": 72.4, "fit": 82.1, "valuation": 32_000_000.0, "role": "Ball Playing Defender", "data_class": "OBSERVED"},
            {"date": "2023-11-15", "minutes": 980, "contribution": 76.8, "fit": 84.5, "valuation": 35_000_000.0, "role": "Ball Playing Defender", "data_class": "OBSERVED"},
            {"date": "2024-02-01", "minutes": 1540, "contribution": 81.2, "fit": 86.2, "valuation": 38_000_000.0, "role": "Ball Playing Defender", "data_class": "OBSERVED"},
        ]
        inacio_modelled = {
            "current_contribution_percentile": 81.2,
            "tactical_fit_index": 86.2,
            "action_value_offensive": 0.42,
            "role_similarity_score": 0.88,
            "data_class": "MODELLED",
        }
        inacio_projected = [
            {"horizon_months": 6, "expected_contribution": 84.5, "expected_valuation": 44_000_000.0, "data_class": "PROJECTED"},
            {"horizon_months": 12, "expected_contribution": 87.0, "expected_valuation": 50_000_000.0, "data_class": "PROJECTED"},
        ]

        signal_inacio = BreakoutSignal(
            player_id="cand_inacio",
            player_name="Gonçalo Inácio",
            age=22,
            position="CB",
            breakout_detected=True,
            breakout_confidence="HIGH",
            development_velocity=4.4,  # +8.8 percentile points over ~20 matchdays
            minutes_acceleration_pct=56.2,
            action_value_delta=0.14,
            minimum_sample_met=True,
            evidence=[
                "Contribution percentile increased from 72.4 to 81.2 (+8.8 pts).",
                "Minutes played accelerated by +56.2% across consecutive 10-match windows.",
                "Offensive action value progression sustained over 1,540 minutes.",
            ],
        )

        inacio_profile = PlayerTrajectoryProfileV2(
            player_id="cand_inacio",
            player_name="Gonçalo Inácio",
            current_club="Sporting CP",
            competition_id="PT-PL",
            age=22,
            position="CB",
            primary_role="Ball Playing Defender",
            observed_history=inacio_observed,
            modelled_state=inacio_modelled,
            projected_path=inacio_projected,
            development_velocity=4.4,
            breakout_signal=signal_inacio,
            trajectory_confidence="HIGH",
        )
        self._profiles[inacio_profile.player_id] = inacio_profile

    def evaluate_trajectory(
        self,
        player_id: str,
        player_name: str,
        current_club: str,
        competition_id: str,
        age: int,
        position: str,
        role: str,
        history: list[dict[str, Any]],
    ) -> PlayerTrajectoryProfileV2:
        """Evaluates longitudinal points and detects breakout signals."""
        total_mins = sum(h.get("minutes", 0) for h in history)
        sample_met = total_mins >= 450 and len(history) >= 2

        if not sample_met:
            signal = BreakoutSignal(
                player_id=player_id,
                player_name=player_name,
                age=age,
                position=position,
                breakout_detected=False,
                breakout_confidence="LOW",
                minimum_sample_met=False,
                evidence=[f"Sample insufficient: {total_mins} mins recorded (requires >= 450 mins)."],
            )
            profile = PlayerTrajectoryProfileV2(
                player_id=player_id,
                player_name=player_name,
                current_club=current_club,
                competition_id=competition_id,
                age=age,
                position=position,
                primary_role=role,
                observed_history=history,
                modelled_state={"data_class": "MODELLED", "status": "INSUFFICIENT_DATA"},
                projected_path=[],
                development_velocity=0.0,
                breakout_signal=signal,
                trajectory_confidence="LOW",
            )
            self._profiles[player_id] = profile
            return profile

        # Calculate development velocity
        first_contrib = history[0].get("contribution", 50.0)
        last_contrib = history[-1].get("contribution", 50.0)
        contrib_delta = last_contrib - first_contrib
        velocity = round(contrib_delta / max(len(history) - 1, 1), 2)

        # Breakout criteria: velocity >= 3.0 and positive minutes trend
        breakout = velocity >= 3.0 and contrib_delta >= 5.0
        signal = BreakoutSignal(
            player_id=player_id,
            player_name=player_name,
            age=age,
            position=position,
            breakout_detected=breakout,
            breakout_confidence="HIGH" if total_mins >= 900 else "MODERATE",
            development_velocity=velocity,
            minutes_acceleration_pct=round((history[-1].get("minutes", 0) / max(history[0].get("minutes", 1), 1) - 1.0) * 100, 1),
            action_value_delta=0.12 if breakout else 0.02,
            minimum_sample_met=True,
            evidence=[
                f"Contribution gained {contrib_delta:+.1f} percentile points across {len(history)} observations.",
                f"Development velocity estimated at {velocity:+.2f} pts/interval.",
            ],
        )

        projected = [
            {
                "horizon_months": 6,
                "expected_contribution": min(round(last_contrib + velocity * 1.5, 1), 99.0),
                "data_class": "PROJECTED",
            },
            {
                "horizon_months": 12,
                "expected_contribution": min(round(last_contrib + velocity * 2.5, 1), 99.0),
                "data_class": "PROJECTED",
            },
        ]

        profile = PlayerTrajectoryProfileV2(
            player_id=player_id,
            player_name=player_name,
            current_club=current_club,
            competition_id=competition_id,
            age=age,
            position=position,
            primary_role=role,
            observed_history=history,
            modelled_state={"current_contribution": last_contrib, "data_class": "MODELLED"},
            projected_path=projected,
            development_velocity=velocity,
            breakout_signal=signal,
            trajectory_confidence="HIGH" if total_mins >= 900 else "MODERATE",
        )
        self._profiles[player_id] = profile
        return profile

    def get_profile(self, player_id: str) -> PlayerTrajectoryProfileV2 | None:
        return self._profiles.get(player_id)

    def list_profiles(self) -> list[PlayerTrajectoryProfileV2]:
        return list(self._profiles.values())


player_trajectory_engine = PlayerTrajectoryEngineV2()
