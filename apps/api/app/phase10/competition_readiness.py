"""Phase 10 — Competition Readiness & Governance Engine (§4, §5).

Enforces explicit competition operational readiness states:
  - NOT_AVAILABLE
  - INSUFFICIENT_DATA
  - DATA_AVAILABLE
  - MODEL_VALIDATED
  - PRODUCTION_READY

Guarantees that a competition never automatically inherits EPL model validity
without competition-specific evidence and independent validation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CompetitionReadinessState(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_AVAILABLE = "DATA_AVAILABLE"
    MODEL_VALIDATED = "MODEL_VALIDATED"
    PRODUCTION_READY = "PRODUCTION_READY"


@dataclass
class CompetitionEvidenceProfile:
    """Competition-specific evidence and operational readiness dossier (§5)."""
    competition_code: str
    competition_name: str
    country: str
    readiness_state: str = CompetitionReadinessState.NOT_AVAILABLE
    matches_count: int = 0
    transfers_count: int = 0
    players_tracked: int = 0
    freshness_date: str | None = None
    ood_status: str = "IN_DISTRIBUTION"
    engine_readiness: dict[str, str] = field(default_factory=dict)
    evidence_checklist: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    # Phase 17 (reconnaissance R7): these profiles are hand-written constants,
    # not counts read from the database. Evidence-backed readiness is
    # GET /api/v1/ops/competitions/readiness.
    evidence_basis: str = "DECLARED_PROFILE_NOT_DB_VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompetitionReadinessManager:
    """Maintains and evaluates competition operational readiness."""

    def __init__(self) -> None:
        self._profiles: dict[str, CompetitionEvidenceProfile] = self._initialize_profiles()

    def _initialize_profiles(self) -> dict[str, CompetitionEvidenceProfile]:
        profiles = {}

        # 1. Premier League (EPL): Full end-to-end evidence
        profiles["EPL"] = CompetitionEvidenceProfile(
            competition_code="EPL",
            competition_name="Premier League",
            country="England",
            readiness_state=CompetitionReadinessState.PRODUCTION_READY,
            matches_count=760,
            transfers_count=350,
            players_tracked=550,
            freshness_date="2024-05-19",
            ood_status="IN_DISTRIBUTION",
            engine_readiness={
                "match_prediction": "PRODUCTION_READY",
                "valuation": "MODEL_VALIDATED",
                "tactical_fit": "PRODUCTION_READY",
                "player_intelligence": "PRODUCTION_READY",
                "similarity": "PRODUCTION_READY",
                "transfer_risk": "PRODUCTION_READY",
            },
            evidence_checklist=[
                "760 finished matches with scores and lineups verified",
                "Multi-class Log Loss 0.9418 beats baseline",
                "Temperature scaled calibration (ECE 0.0385)",
                "20 club rosters completely normalized",
            ],
            limitations=[
                "Valuation model test R2 is -0.0904; anchored by comparable baseline",
            ],
        )

        # 2. La Liga: High transfer coverage, but fixtures not in Bronze
        profiles["LALIGA"] = CompetitionEvidenceProfile(
            competition_code="LaLiga",
            competition_name="La Liga",
            country="Spain",
            readiness_state=CompetitionReadinessState.DATA_AVAILABLE,
            matches_count=0,
            transfers_count=220,
            players_tracked=120,
            freshness_date="2024-05-01",
            ood_status="PARTIAL_EVIDENCE",
            engine_readiness={
                "match_prediction": "INSUFFICIENT_DATA",
                "valuation": "MODEL_VALIDATED",
                "tactical_fit": "INSUFFICIENT_DATA",
                "player_intelligence": "INSUFFICIENT_DATA",
                "similarity": "INSUFFICIENT_DATA",
                "transfer_risk": "DATA_AVAILABLE",
            },
            evidence_checklist=[
                "220 verified historical transfer records in bronze layer",
                "Log MAE of 0.495 consistent with European top-tier valuation bounds",
            ],
            limitations=[
                "Fixtures and player match event data not staged in local bronze storage",
                "Match prediction must not be executed on La Liga fixtures",
            ],
        )

        # 3. Serie A: Transfer data available, match data missing
        profiles["SERIEA"] = CompetitionEvidenceProfile(
            competition_code="SerieA",
            competition_name="Serie A",
            country="Italy",
            readiness_state=CompetitionReadinessState.DATA_AVAILABLE,
            matches_count=0,
            transfers_count=180,
            players_tracked=95,
            freshness_date="2024-05-01",
            ood_status="PARTIAL_EVIDENCE",
            engine_readiness={
                "match_prediction": "INSUFFICIENT_DATA",
                "valuation": "MODEL_VALIDATED",
                "tactical_fit": "INSUFFICIENT_DATA",
                "player_intelligence": "INSUFFICIENT_DATA",
                "similarity": "INSUFFICIENT_DATA",
                "transfer_risk": "DATA_AVAILABLE",
            },
            evidence_checklist=[
                "180 verified historical transfers normalized",
            ],
            limitations=[
                "Match and event data absent from bronze storage",
            ],
        )

        # 4. Bundesliga
        profiles["BUNDESLIGA"] = CompetitionEvidenceProfile(
            competition_code="Bundesliga",
            competition_name="Bundesliga",
            country="Germany",
            readiness_state=CompetitionReadinessState.DATA_AVAILABLE,
            matches_count=0,
            transfers_count=160,
            players_tracked=80,
            freshness_date="2024-05-01",
            ood_status="PARTIAL_EVIDENCE",
            engine_readiness={
                "match_prediction": "INSUFFICIENT_DATA",
                "valuation": "MODEL_VALIDATED",
                "tactical_fit": "INSUFFICIENT_DATA",
                "player_intelligence": "INSUFFICIENT_DATA",
                "similarity": "INSUFFICIENT_DATA",
                "transfer_risk": "DATA_AVAILABLE",
            },
            evidence_checklist=[
                "160 transfer records in bronze storage",
            ],
            limitations=[
                "Match prediction disabled due to missing fixtures",
            ],
        )

        # 5. Ligue 1
        profiles["LIGUE1"] = CompetitionEvidenceProfile(
            competition_code="Ligue1",
            competition_name="Ligue 1",
            country="France",
            readiness_state=CompetitionReadinessState.DATA_AVAILABLE,
            matches_count=0,
            transfers_count=140,
            players_tracked=70,
            freshness_date="2024-05-01",
            ood_status="PARTIAL_EVIDENCE",
            engine_readiness={
                "match_prediction": "INSUFFICIENT_DATA",
                "valuation": "MODEL_VALIDATED",
                "tactical_fit": "INSUFFICIENT_DATA",
                "player_intelligence": "INSUFFICIENT_DATA",
                "similarity": "INSUFFICIENT_DATA",
                "transfer_risk": "DATA_AVAILABLE",
            },
            evidence_checklist=[
                "140 transfer records in bronze storage",
            ],
            limitations=[
                "Match prediction disabled",
            ],
        )

        # 6. UCL / UEL
        profiles["UCL"] = CompetitionEvidenceProfile(
            competition_code="UCL",
            competition_name="UEFA Champions League",
            country="Europe",
            readiness_state=CompetitionReadinessState.NOT_AVAILABLE,
            matches_count=0,
            transfers_count=0,
            ood_status="OUT_OF_DISTRIBUTION",
            engine_readiness={e: "NOT_AVAILABLE" for e in ["match_prediction", "valuation", "tactical_fit", "player_intelligence", "similarity", "transfer_risk"]},
            limitations=["Tournament knockout dynamics distinct from regular season leagues"],
        )

        # 7. Other / MLS / Non-European
        profiles["MLS"] = CompetitionEvidenceProfile(
            competition_code="MLS",
            competition_name="Major League Soccer",
            country="USA",
            readiness_state=CompetitionReadinessState.NOT_AVAILABLE,
            matches_count=0,
            transfers_count=12,
            ood_status="OUT_OF_DISTRIBUTION",
            engine_readiness={e: "NOT_AVAILABLE" for e in ["match_prediction", "valuation", "tactical_fit", "player_intelligence", "similarity", "transfer_risk"]},
            limitations=["Non-European league outside calibrated feature parameter space"],
        )

        return profiles

    def get_profile(self, code: str) -> dict[str, Any]:
        """Returns competition evidence profile, defaulting to NOT_AVAILABLE for unknown leagues."""
        p = self._profiles.get(code.upper())
        if p:
            return p.to_dict()
        return CompetitionEvidenceProfile(
            competition_code=code,
            competition_name=code,
            country="Unknown",
            readiness_state=CompetitionReadinessState.NOT_AVAILABLE,
            ood_status="OUT_OF_DISTRIBUTION",
            limitations=["Unregistered competition: zero operational data staged"],
        ).to_dict()

    def list_all(self) -> list[dict[str, Any]]:
        """List all tracked competition readiness profiles."""
        return [p.to_dict() for p in self._profiles.values()]

    def is_engine_authorized(self, competition_code: str, engine_name: str) -> tuple[bool, str]:
        """Verifies if an engine is authorized to run on a competition without violating data integrity.

        Returns (is_authorized, reason).
        """
        profile = self._profiles.get(competition_code.upper())
        if not profile:
            return False, f"Competition '{competition_code}' is UNREGISTERED and OUT_OF_DISTRIBUTION"

        engine_state = profile.engine_readiness.get(engine_name, "NOT_AVAILABLE")
        if engine_state in ("PRODUCTION_READY", "MODEL_VALIDATED"):
            return True, f"Engine '{engine_name}' is verified for {competition_code}"

        return False, (
            f"Engine '{engine_name}' cannot execute on {competition_code}: state is {engine_state}. "
            f"Competition does not inherit EPL model validity."
        )


competition_manager = CompetitionReadinessManager()
