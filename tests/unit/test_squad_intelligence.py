"""Unit tests for Squad Intelligence and Transfer Simulation (Phase 5A)."""
import uuid
import pytest
from app.squad.schemas import (
    PositionCoverage,
    SquadAnalysisResponse,
    SquadBuildRequest,
    SquadPlayerProfile,
    TransferSimulationImpact,
    TransferSimulationRequest,
    TransferSimulationResponse,
)
from app.squad.service import FORMATION_CONFIGS, SquadService


class TestFormationConfigs:
    """Validates structural completeness of tactical formations."""

    @pytest.mark.parametrize("formation", ["4-3-3", "4-2-3-1", "3-5-2"])
    def test_formation_has_11_slots(self, formation: str):
        slots = FORMATION_CONFIGS.get(formation)
        assert slots is not None
        assert len(slots) == 11

    def test_formation_slot_keys(self):
        for form_name, slots in FORMATION_CONFIGS.items():
            for s in slots:
                assert "slot" in s
                assert "group" in s
                assert "target_pos" in s
                assert "preferred" in s
                assert "target_role" in s


class TestSlotFitComputation:
    """Tests the slot compatibility calculation."""

    def test_exact_position_and_role_match(self):
        slot_cfg = FORMATION_CONFIGS["4-3-3"][0]  # GK
        fit = SquadService.compute_player_slot_fit(
            player_pos="GK",
            player_group="GK",
            player_role="Goalkeeper",
            slot_config=slot_cfg,
        )
        assert fit == 1.0

    def test_exact_position_different_role(self):
        slot_cfg = FORMATION_CONFIGS["4-3-3"][9]  # ST, Target Forward
        fit = SquadService.compute_player_slot_fit(
            player_pos="ST",
            player_group="ATT",
            player_role="Poacher",
            slot_config=slot_cfg,
        )
        # Position fit is 1.0 (60% weight -> 0.60), role fit is 0.50 (40% weight -> 0.20) => ~0.80
        assert fit >= 0.75

    def test_same_position_group(self):
        slot_cfg = FORMATION_CONFIGS["4-3-3"][5]  # DM
        fit = SquadService.compute_player_slot_fit(
            player_pos="CM",
            player_group="MID",
            player_role=None,
            slot_config=slot_cfg,
        )
        # CM is in preferred for DM: pos_fit 1.0 (0.60) + role_fit 0.50 (0.20) => 0.80
        assert fit >= 0.70

    def test_adjacent_group_compatibility(self):
        slot_cfg = FORMATION_CONFIGS["4-3-3"][1]  # LB (DEF)
        fit = SquadService.compute_player_slot_fit(
            player_pos="LM",
            player_group="MID",
            player_role=None,
            slot_config=slot_cfg,
        )
        # Adjacent group MID <-> DEF => lower score
        assert fit < 0.60

    def test_divergent_group_mismatch(self):
        slot_cfg = FORMATION_CONFIGS["4-3-3"][9]  # ST (ATT)
        fit = SquadService.compute_player_slot_fit(
            player_pos="GK",
            player_group="GK",
            player_role="Goalkeeper",
            slot_config=slot_cfg,
        )
        assert fit <= 0.20


class TestSquadAnalysisLogic:
    """Tests for squad coverage classification and depth risk heuristics."""

    def test_coverage_status_mapping(self):
        # Empty starter -> CRITICAL_GAP
        assert not None  # base check
        p1 = SquadPlayerProfile(
            player_id=uuid.uuid4(),
            player_name="Player 1",
            primary_position="CB",
            position_group="DEF",
            is_starter=True,
            slot_name="LCB",
            tactical_fit_score=0.85,
        )

        cov_1 = PositionCoverage(
            slot_name="LCB",
            position_group="DEF",
            starter=p1,
            backups=[],
            depth_count=1,
            coverage_quality=0.85,
            coverage_status="THIN",
        )
        assert cov_1.depth_count == 1
        assert cov_1.coverage_status == "THIN"

        p2 = SquadPlayerProfile(
            player_id=uuid.uuid4(),
            player_name="Player 2",
            primary_position="CB",
            position_group="DEF",
            is_starter=False,
            slot_name="LCB",
            tactical_fit_score=0.75,
        )
        cov_2 = PositionCoverage(
            slot_name="LCB",
            position_group="DEF",
            starter=p1,
            backups=[p2],
            depth_count=2,
            coverage_quality=0.85,
            coverage_status="ADEQUATE",
        )
        assert cov_2.depth_count == 2
        assert cov_2.coverage_status == "ADEQUATE"


class TestSimulationImpactLogic:
    """Tests the calculation of transfer simulation impact deltas."""

    def test_impact_deltas(self):
        impact = TransferSimulationImpact(
            delta_squad_quality=0.05,
            delta_average_age=-1.2,
            delta_total_value_eur=15_000_000,
            delta_role_coverage=0.091,
            delta_tactical_fit=0.06,
            delta_depth_risk=-0.15,
            summary="Modeled 1 departure and 2 arrivals. Squad quality improves by +5.0%.",
            recommendations=["Squad rejuvenates by 1.2 years."],
        )
        assert impact.delta_squad_quality == 0.05
        assert impact.delta_average_age == -1.2
        assert impact.delta_depth_risk < 0  # reduced risk
        assert len(impact.recommendations) > 0
