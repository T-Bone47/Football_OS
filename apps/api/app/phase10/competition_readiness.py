"""Phase 10 — Competition Readiness & Governance Engine (§4, §5).

Enforces explicit competition operational readiness states:
  - NOT_ASSESSED      (no evidence recorded: the honest default)
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
    NOT_ASSESSED = "NOT_ASSESSED"
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
    readiness_state: str = CompetitionReadinessState.NOT_ASSESSED
    # None = not measured. (They used to be hand-typed constants, e.g. EPL "760 matches", and 0 for "unknown".)
    matches_count: int | None = None
    transfers_count: int | None = None
    players_tracked: int | None = None
    freshness_date: str | None = None
    ood_status: str = "UNKNOWN"
    engine_readiness: dict[str, str] = field(default_factory=dict)
    evidence_checklist: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompetitionReadinessManager:
    """Maintains and evaluates competition operational readiness."""

    def __init__(self) -> None:
        self._profiles: dict[str, CompetitionEvidenceProfile] = self._initialize_profiles()

    # Competitions in scope. Nothing about their readiness is asserted here: the previous version hand-typed
    # PRODUCTION_READY / MODEL_VALIDATED states, match counts and metrics (EPL "760 matches, log loss 0.9418",
    # La Liga valuation "MODEL_VALIDATED" while the valuation model is MODEL_RELEASE_BLOCKED). A competition
    # becomes ready only through an evidence-derived assessment, which is not implemented yet (open issue).
    _IN_SCOPE = (
        ("EPL", "EPL", "Premier League", "England"),
        ("LALIGA", "LaLiga", "La Liga", "Spain"),
        ("SERIEA", "SerieA", "Serie A", "Italy"),
        ("BUNDESLIGA", "Bundesliga", "Bundesliga", "Germany"),
        ("LIGUE1", "Ligue1", "Ligue 1", "France"),
        ("UCL", "UCL", "UEFA Champions League", "Europe"),
        ("MLS", "MLS", "Major League Soccer", "USA"),
    )
    _ENGINES = ("match_prediction", "valuation", "tactical_fit", "player_intelligence", "similarity", "transfer_risk")

    def _initialize_profiles(self) -> dict[str, CompetitionEvidenceProfile]:
        return {
            key: CompetitionEvidenceProfile(
                competition_code=code,
                competition_name=name,
                country=country,
                engine_readiness={e: CompetitionReadinessState.NOT_ASSESSED.value for e in self._ENGINES},
                limitations=["No readiness assessment has been recorded; counts and engine states are not measured here."],
            )
            for key, code, name, country in self._IN_SCOPE
        }

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
