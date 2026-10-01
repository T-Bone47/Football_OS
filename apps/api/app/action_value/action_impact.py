"""Deterministic Action Impact Model (Non-Spatial Baseline) (Phase 3.1I).
Evaluates verifiable action value based on observed discrete match actions.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from app.action_value.base import ActionValueItem, ActionValueModel, ActionValueResult


ACTION_IMPACT_WEIGHTS: dict[str, float] = {
    "GOAL": 1.00,
    "PENALTY_GOAL": 0.75,
    "ASSIST": 0.80,
    "KEY_PASS": 0.25,
    "SHOT_ON_TARGET": 0.20,
    "SHOT_OFF_TARGET": -0.04,
    "TACKLE": 0.15,
    "INTERCEPTION": 0.15,
    "BLOCK": 0.12,
    "DUEL_WON": 0.08,
    "DUEL_LOST": -0.05,
    "DRIBBLE_SUCCESS": 0.12,
    "PASS_COMPLETED": 0.02,
    "PASS_INCOMPLETE": -0.02,
    "FOUL_DRAWN": 0.06,
    "FOUL_COMMITTED": -0.08,
    "YELLOW_CARD": -0.30,
    "RED_CARD": -1.00,
    "SAVE": 0.35,
    "GOAL_CONCEDED": -0.85,
}


class ActionImpactModel(ActionValueModel):
    """Calculates deterministic action impact from observed actions.
    Does not require coordinate tracking, operating on verifiable Bronze/Silver events.
    """

    @property
    def model_name(self) -> str:
        return "football_os_action_impact_baseline"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def evaluate(
        self,
        player_id: uuid.UUID,
        actions: list[Any],
        minutes: int,
    ) -> ActionValueResult:
        now = datetime.datetime.now(datetime.timezone.utc)
        total_actions = len(actions)

        if total_actions == 0 or minutes <= 0:
            return ActionValueResult(
                player_id=player_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status="INSUFFICIENT_DATA",
                spatial_data_sufficient=False,
                total_actions_evaluated=0,
                net_action_value=None,
                action_value_per_90=None,
                data_limitation_reason="No actions recorded in evaluation window.",
                licensing_requirements=[],
                actions_sample=[],
                evaluation_metadata={},
                evaluated_at=now,
            )

        if minutes < 270:
            return ActionValueResult(
                player_id=player_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status="INSUFFICIENT_SAMPLE",
                spatial_data_sufficient=False,
                total_actions_evaluated=total_actions,
                net_action_value=None,
                action_value_per_90=None,
                data_limitation_reason=f"Sample minutes ({minutes}) below minimum required threshold (270 mins).",
                licensing_requirements=[],
                actions_sample=[],
                evaluation_metadata={"minutes": minutes, "threshold": 270},
                evaluated_at=now,
            )

        total_impact = 0.0
        sample_items: list[ActionValueItem] = []

        for a in actions:
            subtype = getattr(a, "action_subtype", None) or "OTHER"
            qty = getattr(a, "action_quantity", 1) or 1
            weight = ACTION_IMPACT_WEIGHTS.get(subtype, 0.0)
            item_impact = round(weight * qty, 4)
            total_impact += item_impact

            if abs(item_impact) >= 0.1 and len(sample_items) < 15:
                sample_items.append(
                    ActionValueItem(
                        action_id=getattr(a, "id", uuid.uuid4()),
                        action_type=getattr(a, "action_type", "OTHER"),
                        action_subtype=subtype,
                        minute=getattr(a, "minute", 0),
                        raw_value=float(qty),
                        spatial_x=getattr(a, "x", None),
                        spatial_y=getattr(a, "y", None),
                        impact_score=item_impact,
                        outcome=getattr(a, "outcome", "UNKNOWN"),
                    )
                )

        p90_factor = 90.0 / minutes if minutes > 0 else 0.0
        impact_p90 = round(total_impact * p90_factor, 3)

        return ActionValueResult(
            player_id=player_id,
            model_name=self.model_name,
            model_version=self.model_version,
            status="EVALUATED",
            spatial_data_sufficient=False,
            total_actions_evaluated=total_actions,
            net_action_value=round(total_impact, 3),
            action_value_per_90=impact_p90,
            data_limitation_reason="Evaluated using deterministic non-spatial action impact baseline.",
            licensing_requirements=[],
            actions_sample=sample_items,
            evaluation_metadata={
                "minutes": minutes,
                "p90_scaling": round(p90_factor, 4),
                "weights_version": "1.0",
            },
            evaluated_at=now,
        )
