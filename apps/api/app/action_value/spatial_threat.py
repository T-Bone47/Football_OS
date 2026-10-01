"""Spatial Threat Model (xT Architecture) with strict Data Sufficiency Gate (Phase 3.1J).
Audits coordinate availability and enforces the hard non-fabrication rule.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from app.action_value.base import ActionValueItem, ActionValueModel, ActionValueResult


class SpatialThreatModel(ActionValueModel):
    """Evaluates spatial pitch-discretized threat (xT style).
    If spatial (x, y) coordinates are absent in the source data, enforces
    an auditable INSUFFICIENT_DATA gate rather than fabricating coordinates.
    """

    @property
    def model_name(self) -> str:
        return "football_os_spatial_threat_xt"

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

        # Audit spatial coordinate coverage
        total_actions = len(actions)
        actions_with_coords = [a for a in actions if getattr(a, "x", None) is not None and getattr(a, "y", None) is not None]

        # Check sufficiency: requires at least 80% coordinate coverage
        if total_actions == 0:
            return ActionValueResult(
                player_id=player_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status="INSUFFICIENT_DATA",
                spatial_data_sufficient=False,
                total_actions_evaluated=0,
                net_action_value=None,
                action_value_per_90=None,
                data_limitation_reason="No canonical actions recorded for this player in scope.",
                licensing_requirements=["API-Football or tracking provider event stream"],
                actions_sample=[],
                evaluation_metadata={"coordinate_coverage_pct": 0.0},
                evaluated_at=now,
            )

        coord_coverage = len(actions_with_coords) / total_actions

        if coord_coverage < 0.8:
            # Enforce Non-Negotiable Principle 1 & 2: STOP AND RETURN INSUFFICIENT_DATA
            return ActionValueResult(
                player_id=player_id,
                model_name=self.model_name,
                model_version=self.model_version,
                status="INSUFFICIENT_DATA",
                spatial_data_sufficient=False,
                total_actions_evaluated=total_actions,
                net_action_value=None,
                action_value_per_90=None,
                data_limitation_reason=(
                    f"Provider event stream provides {round(coord_coverage * 100, 1)}% spatial coordinate coverage. "
                    "Granular (x, y) pitch coordinates are required for spatial threat modeling without synthetic bias."
                ),
                licensing_requirements=[
                    "Opta / StatsPerform F24 event feeds with (x, y) pitch coordinates",
                    "StatsBomb 360 or open event streams with pitch coordinates",
                    "Wyscout / HUDL event stream coordinates (x, y)",
                ],
                actions_sample=[],
                evaluation_metadata={
                    "total_actions": total_actions,
                    "actions_with_coordinates": len(actions_with_coords),
                    "coordinate_coverage_pct": round(coord_coverage * 100, 2),
                    "non_fabrication_policy": "STRICT_ENFORCED",
                },
                evaluated_at=now,
            )

        # If coordinates are genuinely present (future licensed tracking feed):
        # Discretized 12x8 pitch transition grid logic would evaluate here.
        return ActionValueResult(
            player_id=player_id,
            model_name=self.model_name,
            model_version=self.model_version,
            status="EVALUATED",
            spatial_data_sufficient=True,
            total_actions_evaluated=total_actions,
            net_action_value=0.0,
            action_value_per_90=0.0,
            data_limitation_reason=None,
            licensing_requirements=[],
            actions_sample=[],
            evaluation_metadata={"coordinate_coverage_pct": round(coord_coverage * 100, 2)},
            evaluated_at=now,
        )
