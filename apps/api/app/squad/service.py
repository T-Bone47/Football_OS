"""Squad Service (Phase 5A).
Constructs squads against tactical formations, evaluates role and position coverage,
identifies depth gaps, and computes squad aggregate health metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import (
    Club,
    Match,
    MatchLineup,
    Player,
    PlayerSeasonStats,
)
from app.market.risk import TransferRiskEngine
from app.market.valuation import BaselineValuationEngine
from app.roles.registry import map_position_to_group
from app.squad.schemas import (
    PositionCoverage,
    SquadAnalysisResponse,
    SquadBuildRequest,
    SquadPlayerProfile,
)


FORMATION_CONFIGS: dict[str, list[dict[str, Any]]] = {
    "4-3-3": [
        {"slot": "GK", "group": "GK", "target_pos": "GK", "preferred": ["GK", "G"], "target_role": "Goalkeeper"},
        {"slot": "LB", "group": "DEF", "target_pos": "LB", "preferred": ["LB", "LWB"], "target_role": "Attacking Fullback"},
        {"slot": "LCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Ball Playing Defender"},
        {"slot": "RCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Cover Defender"},
        {"slot": "RB", "group": "DEF", "target_pos": "RB", "preferred": ["RB", "RWB"], "target_role": "Attacking Fullback"},
        {"slot": "DM", "group": "MID", "target_pos": "DM", "preferred": ["DM", "CM", "MF", "M"], "target_role": "Deep Distributor"},
        {"slot": "LCM", "group": "MID", "target_pos": "CM", "preferred": ["CM", "AM", "MF", "M"], "target_role": "Box to Box"},
        {"slot": "RCM", "group": "MID", "target_pos": "CM", "preferred": ["CM", "AM", "MF", "M"], "target_role": "Playmaker"},
        {"slot": "LW", "group": "ATT", "target_pos": "LW", "preferred": ["LW", "LM", "W", "FW", "F"], "target_role": "Inside Forward"},
        {"slot": "ST", "group": "ATT", "target_pos": "ST", "preferred": ["ST", "CF", "FW", "F"], "target_role": "Target Forward"},
        {"slot": "RW", "group": "ATT", "target_pos": "RW", "preferred": ["RW", "RM", "W", "FW", "F"], "target_role": "Inside Forward"},
    ],
    "4-2-3-1": [
        {"slot": "GK", "group": "GK", "target_pos": "GK", "preferred": ["GK", "G"], "target_role": "Goalkeeper"},
        {"slot": "LB", "group": "DEF", "target_pos": "LB", "preferred": ["LB", "LWB"], "target_role": "Attacking Fullback"},
        {"slot": "LCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Ball Playing Defender"},
        {"slot": "RCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Cover Defender"},
        {"slot": "RB", "group": "DEF", "target_pos": "RB", "preferred": ["RB", "RWB"], "target_role": "Attacking Fullback"},
        {"slot": "LDM", "group": "MID", "target_pos": "DM", "preferred": ["DM", "CM", "MF", "M"], "target_role": "Deep Distributor"},
        {"slot": "RDM", "group": "MID", "target_pos": "DM", "preferred": ["DM", "CM", "MF", "M"], "target_role": "Ball Winner"},
        {"slot": "CAM", "group": "MID", "target_pos": "AM", "preferred": ["AM", "CM", "MF", "M"], "target_role": "Advanced Playmaker"},
        {"slot": "LW", "group": "ATT", "target_pos": "LW", "preferred": ["LW", "LM", "W", "FW", "F"], "target_role": "Inside Forward"},
        {"slot": "RW", "group": "ATT", "target_pos": "RW", "preferred": ["RW", "RM", "W", "FW", "F"], "target_role": "Inside Forward"},
        {"slot": "ST", "group": "ATT", "target_pos": "ST", "preferred": ["ST", "CF", "FW", "F"], "target_role": "Complete Forward"},
    ],
    "3-5-2": [
        {"slot": "GK", "group": "GK", "target_pos": "GK", "preferred": ["GK", "G"], "target_role": "Goalkeeper"},
        {"slot": "LCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Ball Playing Defender"},
        {"slot": "CB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Stopper"},
        {"slot": "RCB", "group": "DEF", "target_pos": "CB", "preferred": ["CB", "DF", "D"], "target_role": "Cover Defender"},
        {"slot": "LWB", "group": "DEF", "target_pos": "LWB", "preferred": ["LWB", "LB", "LM"], "target_role": "Wing Back"},
        {"slot": "RWB", "group": "DEF", "target_pos": "RWB", "preferred": ["RWB", "RB", "RM"], "target_role": "Wing Back"},
        {"slot": "DM", "group": "MID", "target_pos": "DM", "preferred": ["DM", "CM", "MF", "M"], "target_role": "Deep Distributor"},
        {"slot": "LCM", "group": "MID", "target_pos": "CM", "preferred": ["CM", "AM", "MF", "M"], "target_role": "Box to Box"},
        {"slot": "RCM", "group": "MID", "target_pos": "CM", "preferred": ["CM", "AM", "MF", "M"], "target_role": "Playmaker"},
        {"slot": "LST", "group": "ATT", "target_pos": "ST", "preferred": ["ST", "CF", "FW", "F"], "target_role": "Mobile Striker"},
        {"slot": "RST", "group": "ATT", "target_pos": "ST", "preferred": ["ST", "CF", "FW", "F"], "target_role": "Target Forward"},
    ],
}


class SquadService:
    """Core service for constructing, evaluating, and optimizing squad structures."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.risk_engine = TransferRiskEngine()
        self.valuation_engine = BaselineValuationEngine()

    @staticmethod
    def compute_player_slot_fit(
        player_pos: str | None,
        player_group: str,
        player_role: str | None,
        slot_config: dict[str, Any],
    ) -> float:
        """Evaluates compatibility between a player and a tactical formation slot."""
        norm_pos = (player_pos or "").strip().upper()
        preferred = [p.upper() for p in slot_config["preferred"]]

        # Positional Fit (60% weight)
        if norm_pos in preferred:
            pos_fit = 1.0
        elif player_group == slot_config["group"]:
            pos_fit = 0.80
        elif {player_group, slot_config["group"]} in [
            {"MID", "ATT"},
            {"MID", "DEF"},
        ]:
            pos_fit = 0.35
        else:
            pos_fit = 0.05

        # Role Fit (40% weight)
        target_role = slot_config.get("target_role", "").lower()
        cand_role = (player_role or "").lower()

        if cand_role and target_role:
            if cand_role == target_role:
                role_fit = 1.0
            elif cand_role.split()[0] == target_role.split()[0]:
                role_fit = 0.70
            elif player_group == slot_config["group"]:
                role_fit = 0.50
            else:
                role_fit = 0.20
        else:
            role_fit = 0.50

        return round(0.60 * pos_fit + 0.40 * role_fit, 3)

    async def get_squad_players(
        self,
        club_id: uuid.UUID | None = None,
        player_ids: list[uuid.UUID] | None = None,
        limit: int = 30,
        as_of: datetime | None = None,
    ) -> list[Player]:
        """The club's roster from stored data only: players with season stats
        for the club or lineup rows for it in matches at or before as_of.
        Phase 18 (R24): no fallback to unrelated players when the club has none."""
        self.last_squad_source: list[str] = []
        stmt = select(Player).options(selectinload(Player.role_profiles))
        if player_ids:
            self.last_squad_source = ["REQUESTED_PLAYER_IDS"]
            stmt = stmt.where(Player.id.in_(player_ids))
        elif club_id:
            cutoff = as_of or datetime.now(timezone.utc)
            via_stats = select(PlayerSeasonStats.player_id).where(PlayerSeasonStats.club_id == club_id)
            via_lineups = (select(MatchLineup.player_id).join(Match, Match.id == MatchLineup.match_id)
                           .where(MatchLineup.club_id == club_id, Match.date <= cutoff))
            self.last_squad_source = ["player_season_stats", "match_lineups"]
            stmt = stmt.where(Player.id.in_(via_stats.union(via_lineups)))
        else:
            return []
        return list((await self.session.execute(stmt.order_by(Player.name))).scalars().all())

    def build_player_profile(
        self,
        player: Player,
        as_of: datetime,
    ) -> SquadPlayerProfile:
        """Observed facts plus the latest QUALIFIED role profile at as_of.
        Valuation and transfer risk are not filled in here (never estimated
        from age or a baseline)."""
        age = round((as_of.date() - player.date_of_birth).days / 365.25, 1) if player.date_of_birth else None
        group = map_position_to_group(player.primary_position).value if player.primary_position else "UNKNOWN"
        primary_role = role_conf = None
        qualified = [r for r in (player.role_profiles or [])
                     if r.role_status == "QUALIFIED" and r.as_of is not None and r.as_of <= as_of]
        if qualified:
            latest_role = max(qualified, key=lambda r: r.as_of)
            primary_role = latest_role.primary_archetype
            role_conf = latest_role.archetype_confidence
        return SquadPlayerProfile(
            player_id=player.id,
            player_name=player.name,
            age=age,
            nationality=player.nationality,
            primary_position=player.primary_position,
            position_group=group,
            primary_role=primary_role,
            role_confidence=role_conf,
            tactical_fit_score=None,
            estimated_value_eur=None,
            transfer_risk_score=None,
            transfer_risk_level=None,
            is_starter=False,
            slot_name=None,
        )

    async def analyze_squad(
        self,
        request: SquadBuildRequest,
        as_of: datetime | None = None,
    ) -> SquadAnalysisResponse:
        """Constructs tactical formation line-up and position coverage depth."""
        eval_time = as_of or datetime.now(timezone.utc)
        formation = request.formation if request.formation in FORMATION_CONFIGS else "4-3-3"
        slot_configs = FORMATION_CONFIGS[formation]

        # 1. Fetch club info if provided
        club_name = None
        if request.club_id:
            c_res = await self.session.execute(select(Club).where(Club.id == request.club_id))
            club = c_res.scalar_one_or_none()
            if club:
                club_name = club.name

        # 2. Fetch players
        players = await self.get_squad_players(
            club_id=request.club_id,
            player_ids=request.player_ids,
            as_of=eval_time,
        )

        profiles = [self.build_player_profile(p, eval_time) for p in players]

        # 3. Greedy Formation Assignment
        assigned_starters: dict[str, SquadPlayerProfile] = {}
        assigned_player_ids: set[uuid.UUID] = set()

        for slot_cfg in slot_configs:
            slot_name = slot_cfg["slot"]
            best_cand: SquadPlayerProfile | None = None
            best_fit = -1.0

            for p in profiles:
                if p.player_id in assigned_player_ids:
                    continue

                fit = self.compute_player_slot_fit(
                    p.primary_position,
                    p.position_group,
                    p.primary_role,
                    slot_cfg,
                )

                if fit > best_fit:
                    best_fit = fit
                    best_cand = p

            if best_cand and best_fit >= 0.30:
                starter_copy = best_cand.model_copy(
                    update={
                        "is_starter": True,
                        "slot_name": slot_name,
                        "tactical_fit_score": best_fit,
                    }
                )
                assigned_starters[slot_name] = starter_copy
                assigned_player_ids.add(best_cand.player_id)

        # 4. Position Depth & Backup Allocation
        positions: list[PositionCoverage] = []
        key_gaps: list[str] = []
        key_strengths: list[str] = []

        total_starter_quality = 0.0
        quality_count = 0
        total_starter_tactical_fit = 0.0
        starters_count = len(assigned_starters)

        for slot_cfg in slot_configs:
            slot_name = slot_cfg["slot"]
            starter = assigned_starters.get(slot_name)

            # Find compatible backup players
            backups: list[SquadPlayerProfile] = []
            for p in profiles:
                if p.player_id in assigned_player_ids:
                    continue
                # Compatible if matching group or preferred position
                if p.position_group == slot_cfg["group"] or p.primary_position in slot_cfg["preferred"]:
                    fit = self.compute_player_slot_fit(
                        p.primary_position,
                        p.position_group,
                        p.primary_role,
                        slot_cfg,
                    )
                    backup_copy = p.model_copy(
                        update={
                            "is_starter": False,
                            "slot_name": slot_name,
                            "tactical_fit_score": fit,
                        }
                    )
                    backups.append(backup_copy)

            # Depth analysis
            depth_count = (1 if starter else 0) + len(backups)
            cov_quality = starter.tactical_fit_score if starter and starter.tactical_fit_score else 0.0

            if not starter:
                cov_status = "CRITICAL_GAP"
                key_gaps.append(f"{slot_name} ({slot_cfg['target_role']}) has no starter.")
            elif depth_count == 1:
                cov_status = "THIN"
                key_gaps.append(f"{slot_name} has no recognized backup cover.")
            elif depth_count == 2:
                cov_status = "ADEQUATE"
            else:
                cov_status = "SOLID"
                if cov_quality >= 0.75:
                    key_strengths.append(f"{slot_name} ({starter.player_name}) provides solid depth & tactical fit.")

            if starter and starter.tactical_fit_score is not None:
                total_starter_tactical_fit += starter.tactical_fit_score
                if starter.role_confidence is not None:  # quality needs role evidence; never a default
                    total_starter_quality += 0.5 * starter.tactical_fit_score + 0.5 * starter.role_confidence
                    quality_count += 1

            positions.append(
                PositionCoverage(
                    slot_name=slot_name,
                    position_group=slot_cfg["group"],
                    starter=starter,
                    backups=backups,
                    depth_count=depth_count,
                    coverage_quality=round(cov_quality, 3),
                    coverage_status=cov_status,
                )
            )

        # 5. Composite Metrics
        num_slots = len(slot_configs)
        role_coverage_score = round(starters_count / max(1, num_slots), 3)

        avg_starter_tactical_fit = (
            round(total_starter_tactical_fit / starters_count, 3) if starters_count > 0 else 0.0
        )
        squad_quality_score = round(total_starter_quality / quality_count, 3) if quality_count else None

        # Depth risk: penalized heavily if positions are empty, moderately if thin
        gap_penalty = sum(
            1.0 if p.coverage_status == "CRITICAL_GAP" else 0.4 if p.coverage_status == "THIN" else 0.0
            for p in positions
        )
        depth_risk_score = round(min(1.0, gap_penalty / max(1, num_slots)), 3)

        if depth_risk_score >= 0.50:
            depth_risk_level = "CRITICAL"
        elif depth_risk_score >= 0.30:
            depth_risk_level = "HIGH"
        elif depth_risk_score >= 0.15:
            depth_risk_level = "MODERATE"
        else:
            depth_risk_level = "LOW"

        # Demographics & Values
        ages = [p.age for p in profiles if p.age is not None]
        avg_age = round(sum(ages) / len(ages), 1) if ages else None
        total_value = None  # valuation model UNVERIFIED: no value is served

        return SquadAnalysisResponse(
            club_id=request.club_id,
            club_name=club_name,
            formation=formation,
            status="SQUAD_ANALYSED" if profiles else "NO_SQUAD_DATA",
            squad_source=list(getattr(self, "last_squad_source", [])),
            assumptions=[
                "Slot fit is a declared rule: 60% position match + 40% role match; a missing role scores 0.5.",
                "Coverage counts players by stored position group; it does not observe fitness or availability.",
            ],
            total_players=len(profiles),
            starters_count=starters_count,
            backups_count=len(profiles) - starters_count,
            average_age=avg_age,
            total_estimated_value_eur=total_value,
            squad_quality_score=squad_quality_score,
            role_coverage_score=role_coverage_score,
            tactical_fit_score=avg_starter_tactical_fit,
            depth_risk_score=depth_risk_score,
            depth_risk_level=depth_risk_level,
            positions=positions,
            key_gaps=key_gaps,
            key_strengths=key_strengths,
            evaluated_at=eval_time,
        )
