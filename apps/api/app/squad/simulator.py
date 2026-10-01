"""Transfer Simulator Engine (Phase 5A).
Models the before-and-after systemic impact of prospective transfers on squad quality,
age profile, role coverage, and depth risk.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Player
from app.squad.schemas import (
    SquadBuildRequest,
    SquadPlayerProfile,
    TransferSimulationImpact,
    TransferSimulationRequest,
    TransferSimulationResponse,
)
from app.squad.service import SquadService


class TransferSimulator:
    """Simulates roster transitions and evaluates squad health trajectories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.squad_service = SquadService(session)

    async def simulate_transfer(
        self,
        request: TransferSimulationRequest,
        as_of: datetime | None = None,
    ) -> TransferSimulationResponse:
        """Executes before/after transfer simulation with provenance and impact attribution."""
        eval_time = as_of or datetime.now(timezone.utc)

        # 1. Resolve current baseline squad players
        curr_players = await self.squad_service.get_squad_players(
            club_id=request.club_id,
            player_ids=request.current_player_ids,
        )
        curr_ids = [p.id for p in curr_players]

        # 2. Compute BEFORE squad analysis
        before_req = SquadBuildRequest(
            club_id=request.club_id,
            player_ids=curr_ids,
            formation=request.formation,
        )
        before = await self.squad_service.analyze_squad(before_req, as_of=eval_time)

        # 3. Resolve OUTGOING and INCOMING player entities
        outgoing_set = set(request.outgoing_player_ids)
        incoming_set = set(request.incoming_player_ids)

        outgoing_players = [p for p in curr_players if p.id in outgoing_set]
        outgoing_profiles = [
            self.squad_service.build_player_profile(p, eval_time) for p in outgoing_players
        ]

        incoming_players = []
        if incoming_set:
            inc_res = await self.squad_service.get_squad_players(player_ids=list(incoming_set))
            incoming_players = inc_res

        incoming_profiles = [
            self.squad_service.build_player_profile(p, eval_time) for p in incoming_players
        ]

        # 4. Construct AFTER roster
        after_ids = [pid for pid in curr_ids if pid not in outgoing_set]
        for inc_p in incoming_players:
            if inc_p.id not in after_ids:
                after_ids.append(inc_p.id)

        after_req = SquadBuildRequest(
            club_id=request.club_id,
            player_ids=after_ids,
            formation=request.formation,
        )
        after = await self.squad_service.analyze_squad(after_req, as_of=eval_time)

        # 5. Financial Net Spend
        outgoing_val = sum(p.estimated_value_eur or 0.0 for p in outgoing_profiles)
        incoming_val = sum(p.estimated_value_eur or 0.0 for p in incoming_profiles)
        net_spend = round(incoming_val - outgoing_val, 2)

        # 6. Delta Metrics
        delta_quality = round(after.squad_quality_score - before.squad_quality_score, 3)
        delta_age = round(after.average_age - before.average_age, 2)
        delta_value = round(after.total_estimated_value_eur - before.total_estimated_value_eur, 2)
        delta_coverage = round(after.role_coverage_score - before.role_coverage_score, 3)
        delta_fit = round(after.tactical_fit_score - before.tactical_fit_score, 3)
        delta_depth_risk = round(after.depth_risk_score - before.depth_risk_score, 3)

        # 7. Summary & Recommendations Generation
        summary_parts = []
        if len(outgoing_profiles) > 0 or len(incoming_profiles) > 0:
            summary_parts.append(
                f"Modeled {len(outgoing_profiles)} departure(s) and {len(incoming_profiles)} arrival(s)."
            )

        if delta_quality > 0:
            summary_parts.append(f"Squad quality improves by +{delta_quality * 100:.1f}%.")
        elif delta_quality < 0:
            summary_parts.append(f"Squad quality drops by {delta_quality * 100:.1f}%.")
        else:
            summary_parts.append("Squad quality remains neutral.")

        if delta_depth_risk < 0:
            summary_parts.append(f"Depth risk reduced by {abs(delta_depth_risk) * 100:.1f}%.")
        elif delta_depth_risk > 0:
            summary_parts.append(f"Depth risk increased by +{delta_depth_risk * 100:.1f}%.")

        summary = " ".join(summary_parts)

        recommendations = []
        if delta_depth_risk > 0:
            recommendations.append(
                "Review departing positions: roster depth is stretched thin in vacated tactical slots."
            )
        if delta_age > 1.0:
            recommendations.append(
                f"Squad average age increased by +{delta_age:.1f} years; evaluate long-term renewal pipeline."
            )
        elif delta_age < -1.0:
            recommendations.append(
                f"Squad rejuvenates by {abs(delta_age):.1f} years, lowering long-term demographic risk."
            )
        if delta_fit > 0.05:
            recommendations.append("Tactical cohesion improves under the selected formation.")
        elif delta_fit < -0.05:
            recommendations.append("Tactical compatibility decreases; incoming profiles may require system adjustments.")

        if not recommendations:
            recommendations.append("Balanced roster impact with stable tactical continuity.")

        impact = TransferSimulationImpact(
            delta_squad_quality=delta_quality,
            delta_average_age=delta_age,
            delta_total_value_eur=delta_value,
            delta_role_coverage=delta_coverage,
            delta_tactical_fit=delta_fit,
            delta_depth_risk=delta_depth_risk,
            summary=summary,
            recommendations=recommendations,
        )

        return TransferSimulationResponse(
            before=before,
            after=after,
            outgoing_players=outgoing_profiles,
            incoming_players=incoming_profiles,
            net_spend_eur=net_spend,
            impact=impact,
            evaluated_at=eval_time,
        )
