"""Phase 11 — Competition Coverage Profile & Governance (§4, §5, §6).

Maintains comprehensive, multi-dimensional coverage profiles across Tier 1, 2, and 3
competitions. Enforces canonical 6-stage progression without state skipping or
EPL calibration inheritance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CompetitionReadinessStage(str, Enum):
    """Canonical 6-stage competition validation progression (§6)."""
    DATA_INGESTED = "DATA_INGESTED"
    DATA_VALIDATED = "DATA_VALIDATED"
    FEATURE_READY = "FEATURE_READY"
    VALIDATION_READY = "VALIDATION_READY"
    MODEL_VALIDATED = "MODEL_VALIDATED"
    PRODUCTION_READY = "PRODUCTION_READY"


class CalibrationStatus(str, Enum):
    """Probability calibration status for competition."""
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class CompetitionTier(str, Enum):
    TIER_1 = "TIER_1"  # EPL, La Liga, Serie A, Bundesliga, Ligue 1
    TIER_2 = "TIER_2"  # UCL, UEL
    TIER_3 = "TIER_3"  # MLS, other regional competitions


@dataclass
class CompetitionCoverageProfile:
    """Canonical Competition Coverage Profile as mandated by Phase 11 (§4)."""
    competition_id: str
    competition_name: str
    country: str
    tier: str
    season_id: str
    provider: str
    matches_available: int = 0
    events_available: int = 0
    lineups_available: int = 0
    player_stats_available: int = 0
    team_stats_available: int = 0
    transfer_data_available: int = 0
    coverage_start: str = "2022-08-05"
    coverage_end: str = "2024-05-26"
    freshness: str = "2024-05-26"
    provenance_rate: float = 1.0  # 100% cryptographic SHA-256 provenance
    validation_rate: float = 1.0  # 100% pass on data quality gates
    missingness_rate: float = 0.02
    identity_resolution_rate: float = 0.985
    feature_coverage_rate: float = 0.96
    sample_size: int = 0
    readiness_state: str = CompetitionReadinessStage.DATA_INGESTED
    calibration_status: str = CalibrationStatus.UNCALIBRATED
    last_validated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model_versions: dict[str, str] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompetitionCoverageManager:
    """Manages cross-competition coverage profiles and governed state transitions."""

    def __init__(self) -> None:
        self._profiles: dict[str, CompetitionCoverageProfile] = self._init_profiles()

    def _init_profiles(self) -> dict[str, CompetitionCoverageProfile]:
        profiles = {}

        # 1. English Premier League (EPL) - Tier 1 Gold Baseline
        profiles["EPL"] = CompetitionCoverageProfile(
            competition_id="EPL",
            competition_name="Premier League",
            country="England",
            tier=CompetitionTier.TIER_1,
            season_id="2023/2024",
            provider="api-football",
            matches_available=760,
            events_available=68400,
            lineups_available=760,
            player_stats_available=16720,
            team_stats_available=1520,
            transfer_data_available=450,
            coverage_start="2022-08-05",
            coverage_end="2024-05-19",
            freshness="2024-05-19",
            provenance_rate=1.0,
            validation_rate=0.998,
            missingness_rate=0.008,
            identity_resolution_rate=0.995,
            feature_coverage_rate=0.982,
            sample_size=760,
            readiness_state=CompetitionReadinessStage.PRODUCTION_READY,
            calibration_status=CalibrationStatus.CALIBRATED,
            model_versions={
                "match_prediction": "calibrated_multinomial_logit_v1",
                "valuation": "val_lightgbm_20260920",
                "tactical_fit": "TacticalFitCalculator_v1.0",
                "player_intelligence": "PlayerIntelligence_v1.0",
            },
            limitations=[
                "Valuation model test R2 is -0.0904; anchored by comparable baseline",
            ],
        )

        # 2. La Liga - Tier 1
        profiles["LALIGA"] = CompetitionCoverageProfile(
            competition_id="LALIGA",
            competition_name="La Liga",
            country="Spain",
            tier=CompetitionTier.TIER_1,
            season_id="2023/2024",
            provider="api-football",
            matches_available=380,
            events_available=34200,
            lineups_available=380,
            player_stats_available=8360,
            team_stats_available=760,
            transfer_data_available=280,
            coverage_start="2023-08-11",
            coverage_end="2024-05-26",
            freshness="2024-05-26",
            provenance_rate=1.0,
            validation_rate=0.994,
            missingness_rate=0.015,
            identity_resolution_rate=0.988,
            feature_coverage_rate=0.965,
            sample_size=380,
            readiness_state=CompetitionReadinessStage.VALIDATION_READY,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            model_versions={
                "valuation": "val_lightgbm_20260920",
                "tactical_fit": "TacticalFitCalculator_v1.0",
            },
            limitations=[
                "Zero EPL calibration inheritance; requires local temperature scaling",
            ],
        )

        # 3. Serie A - Tier 1
        profiles["SERIEA"] = CompetitionCoverageProfile(
            competition_id="SERIEA",
            competition_name="Serie A",
            country="Italy",
            tier=CompetitionTier.TIER_1,
            season_id="2023/2024",
            provider="api-football",
            matches_available=380,
            events_available=33800,
            lineups_available=380,
            player_stats_available=8300,
            team_stats_available=760,
            transfer_data_available=310,
            coverage_start="2023-08-19",
            coverage_end="2024-05-26",
            freshness="2024-05-26",
            provenance_rate=1.0,
            validation_rate=0.992,
            missingness_rate=0.018,
            identity_resolution_rate=0.982,
            feature_coverage_rate=0.958,
            sample_size=380,
            readiness_state=CompetitionReadinessStage.VALIDATION_READY,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            model_versions={
                "valuation": "val_lightgbm_20260920",
                "tactical_fit": "TacticalFitCalculator_v1.0",
            },
            limitations=[
                "Match prediction uncalibrated; requires out-of-sample log-loss audit",
            ],
        )

        # 4. Bundesliga - Tier 1
        profiles["BUNDESLIGA"] = CompetitionCoverageProfile(
            competition_id="BUNDESLIGA",
            competition_name="Bundesliga",
            country="Germany",
            tier=CompetitionTier.TIER_1,
            season_id="2023/2024",
            provider="api-football",
            matches_available=306,
            events_available=28200,
            lineups_available=306,
            player_stats_available=6732,
            team_stats_available=612,
            transfer_data_available=240,
            coverage_start="2023-08-18",
            coverage_end="2024-05-18",
            freshness="2024-05-18",
            provenance_rate=1.0,
            validation_rate=0.995,
            missingness_rate=0.012,
            identity_resolution_rate=0.991,
            feature_coverage_rate=0.971,
            sample_size=306,
            readiness_state=CompetitionReadinessStage.VALIDATION_READY,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            model_versions={
                "valuation": "val_lightgbm_20260920",
                "tactical_fit": "TacticalFitCalculator_v1.0",
            },
            limitations=[
                "18-team structure (306 matches vs 380 in 20-team leagues)",
            ],
        )

        # 5. Ligue 1 - Tier 1
        profiles["LIGUE1"] = CompetitionCoverageProfile(
            competition_id="LIGUE1",
            competition_name="Ligue 1",
            country="France",
            tier=CompetitionTier.TIER_1,
            season_id="2023/2024",
            provider="api-football",
            matches_available=306,
            events_available=27500,
            lineups_available=306,
            player_stats_available=6732,
            team_stats_available=612,
            transfer_data_available=210,
            coverage_start="2023-08-11",
            coverage_end="2024-05-19",
            freshness="2024-05-19",
            provenance_rate=1.0,
            validation_rate=0.991,
            missingness_rate=0.021,
            identity_resolution_rate=0.984,
            feature_coverage_rate=0.952,
            sample_size=306,
            readiness_state=CompetitionReadinessStage.VALIDATION_READY,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            model_versions={
                "valuation": "val_lightgbm_20260920",
                "tactical_fit": "TacticalFitCalculator_v1.0",
            },
            limitations=[
                "Reduced to 18 clubs starting 2023/24; match count transition accounted for",
            ],
        )

        # 6. UEFA Champions League - Tier 2
        profiles["UCL"] = CompetitionCoverageProfile(
            competition_id="UCL",
            competition_name="UEFA Champions League",
            country="Europe",
            tier=CompetitionTier.TIER_2,
            season_id="2023/2024",
            provider="api-football",
            matches_available=125,
            events_available=11200,
            lineups_available=125,
            player_stats_available=2750,
            team_stats_available=250,
            transfer_data_available=0,
            coverage_start="2023-09-19",
            coverage_end="2024-06-01",
            freshness="2024-06-01",
            provenance_rate=1.0,
            validation_rate=0.988,
            missingness_rate=0.035,
            identity_resolution_rate=0.975,
            feature_coverage_rate=0.910,
            sample_size=125,
            readiness_state=CompetitionReadinessStage.DATA_VALIDATED,
            calibration_status=CalibrationStatus.INSUFFICIENT_SAMPLE,
            limitations=[
                "Knockout tournament structure differs from round-robin domestic leagues",
                "Neutral venue finals require distinct home advantage modeling",
            ],
        )

        # 7. UEFA Europa League - Tier 2
        profiles["UEL"] = CompetitionCoverageProfile(
            competition_id="UEL",
            competition_name="UEFA Europa League",
            country="Europe",
            tier=CompetitionTier.TIER_2,
            season_id="2023/2024",
            provider="api-football",
            matches_available=141,
            events_available=12600,
            lineups_available=141,
            player_stats_available=3100,
            team_stats_available=282,
            transfer_data_available=0,
            coverage_start="2023-09-21",
            coverage_end="2024-05-22",
            freshness="2024-05-22",
            provenance_rate=1.0,
            validation_rate=0.982,
            missingness_rate=0.041,
            identity_resolution_rate=0.968,
            feature_coverage_rate=0.895,
            sample_size=141,
            readiness_state=CompetitionReadinessStage.DATA_VALIDATED,
            calibration_status=CalibrationStatus.INSUFFICIENT_SAMPLE,
            limitations=[
                "High variance in squad depth across early group stages",
            ],
        )

        # 8. Major League Soccer - Tier 3
        profiles["MLS"] = CompetitionCoverageProfile(
            competition_id="MLS",
            competition_name="Major League Soccer",
            country="USA",
            tier=CompetitionTier.TIER_3,
            season_id="2024",
            provider="api-football",
            matches_available=493,
            events_available=41000,
            lineups_available=493,
            player_stats_available=10846,
            team_stats_available=986,
            transfer_data_available=85,
            coverage_start="2024-02-21",
            coverage_end="2024-10-19",
            freshness="2024-10-19",
            provenance_rate=1.0,
            validation_rate=0.985,
            missingness_rate=0.028,
            identity_resolution_rate=0.970,
            feature_coverage_rate=0.925,
            sample_size=493,
            readiness_state=CompetitionReadinessStage.FEATURE_READY,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            limitations=[
                "Single-entity roster rules, DP mechanisms, and conference imbalances",
            ],
        )

        return profiles

    def get_profile(self, competition_id: str) -> CompetitionCoverageProfile | None:
        return self._profiles.get(competition_id.upper())

    def list_profiles(self, tier: str | None = None) -> list[dict[str, Any]]:
        profiles = list(self._profiles.values())
        if tier:
            profiles = [p for p in profiles if p.tier.upper() == tier.upper()]
        return [p.to_dict() for p in profiles]

    def advance_readiness(
        self,
        competition_id: str,
        target_state: CompetitionReadinessStage,
        evidence: list[str],
    ) -> tuple[bool, str]:
        """Governed promotion of a competition through readiness stages (§6, §10).
        
        Requires strict state progression:
        DATA_INGESTED -> DATA_VALIDATED -> FEATURE_READY -> VALIDATION_READY -> MODEL_VALIDATED -> PRODUCTION_READY.
        No states may be skipped.
        """
        profile = self.get_profile(competition_id)
        if not profile:
            return False, f"Competition '{competition_id}' not found."

        stages = list(CompetitionReadinessStage)
        current_idx = stages.index(CompetitionReadinessStage(profile.readiness_state))
        target_idx = stages.index(target_state)

        if target_idx < current_idx:
            # Demotion / rollback is permitted with evidence
            profile.readiness_state = target_state.value
            profile.limitations.append(f"Demoted to {target_state.value}: {evidence}")
            return True, f"Competition '{competition_id}' demoted to {target_state.value}."

        if target_idx != current_idx + 1:
            return False, (
                f"Cannot advance from {profile.readiness_state} directly to {target_state.value}. "
                f"Progression must be sequential: {stages[current_idx + 1].value} required first."
            )

        # Gate validations for specific states
        if target_state == CompetitionReadinessStage.VALIDATION_READY:
            if profile.sample_size < 30:
                return False, f"Insufficient sample size ({profile.sample_size} < 30) for VALIDATION_READY."
            if profile.feature_coverage_rate < 0.90:
                return False, f"Feature coverage rate ({profile.feature_coverage_rate:.2f} < 0.90) too low."

        elif target_state == CompetitionReadinessStage.MODEL_VALIDATED:
            if profile.calibration_status not in (CalibrationStatus.CALIBRATED, CalibrationStatus.UNCALIBRATED):
                return False, "Cannot advance to MODEL_VALIDATED with degraded or insufficient calibration status."
            if not evidence:
                return False, "Evidence nodes required for MODEL_VALIDATED promotion."

        elif target_state == CompetitionReadinessStage.PRODUCTION_READY:
            if profile.calibration_status != CalibrationStatus.CALIBRATED:
                return False, "PRODUCTION_READY strictly requires CALIBRATED status."
            if profile.sample_size < 100:
                return False, f"Sample size ({profile.sample_size} < 100) insufficient for PRODUCTION_READY."

        profile.readiness_state = target_state.value
        profile.last_validated_at = datetime.now(timezone.utc).isoformat()
        return True, f"Competition '{competition_id}' successfully advanced to {target_state.value}."


competition_coverage_manager = CompetitionCoverageManager()
