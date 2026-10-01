"""Cohort Engine for Phase 15 Global Football Research.

Manages reusable, immutable, versioned research cohorts for:
- Players
- Transfers
- Teams
- Matches

Rules:
- Once used in a completed experiment, cohort is sealed as immutable.
- Modifications require version increment with parent lineage.
- Cryptographic SHA-256 fingerprinting for reproducibility.
"""

import hashlib
import json
from typing import Any
from app.phase15.research_models import ResearchCohort


class CohortEngine:
    """Manages creation, versioning, immutability, and hashing of research cohorts."""

    def __init__(self) -> None:
        self._cohorts: dict[str, ResearchCohort] = {}
        self._completed_experiment_cohorts: set[str] = set()

    def create_cohort(
        self,
        cohort_id: str,
        cohort_type: str,
        name: str,
        filter_criteria: dict[str, Any],
        entity_ids: list[str],
        sample_size: int | None = None,
        competition_scope: list[str] | None = None,
        temporal_scope: dict[str, str] | None = None,
        version: str = "1.0.0",
        parent_version: str | None = None,
    ) -> ResearchCohort:
        """Creates a new versioned research cohort."""
        if cohort_id in self._cohorts:
            raise ValueError(f"Cohort {cohort_id} already exists. Cohorts must use versioned IDs.")

        normalized_criteria = json.dumps(filter_criteria, sort_keys=True)
        normalized_entities = json.dumps(sorted(entity_ids))
        raw_sig = f"{cohort_id}:{cohort_type}:{normalized_criteria}:{normalized_entities}:{version}"
        cohort_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

        cohort = ResearchCohort(
            research_id=f"res_{cohort_id}",
            cohort_id=cohort_id,
            cohort_type=cohort_type.upper(),
            name=name,
            filter_criteria=filter_criteria,
            entity_ids=sorted(entity_ids),
            sample_size=sample_size if sample_size is not None else len(entity_ids),
            competition_scope=competition_scope or [],
            temporal_scope=temporal_scope or {},
            version=version,
            parent_version=parent_version,
            cohort_hash=cohort_hash,
            is_immutable=False,
        )
        self._cohorts[cohort_id] = cohort
        return cohort

    def seal_cohort(self, cohort_id: str) -> ResearchCohort:
        """Seals a cohort as immutable once attached to a completed experiment."""
        cohort = self.get_cohort(cohort_id)
        cohort.is_immutable = True
        self._completed_experiment_cohorts.add(cohort_id)
        return cohort

    def update_cohort(
        self,
        cohort_id: str,
        new_filter_criteria: dict[str, Any],
        new_entity_ids: list[str],
    ) -> ResearchCohort:
        """Attempting to update an immutable cohort creates a new version instead."""
        existing = self.get_cohort(cohort_id)
        if existing.is_immutable or cohort_id in self._completed_experiment_cohorts:
            # Fork into a new version to preserve historical auditability
            parts = existing.version.split(".")
            major = int(parts[0])
            new_version = f"{major + 1}.0.0"
            new_id = f"{cohort_id}_v{new_version.replace('.', '_')}"
            return self.create_cohort(
                cohort_id=new_id,
                cohort_type=existing.cohort_type,
                name=f"{existing.name} (v{new_version})",
                filter_criteria=new_filter_criteria,
                entity_ids=new_entity_ids,
                version=new_version,
                parent_version=existing.version,
                competition_scope=existing.competition_scope,
                temporal_scope=existing.temporal_scope,
            )

        # Still mutable: update in place
        existing.filter_criteria = new_filter_criteria
        existing.entity_ids = sorted(new_entity_ids)
        existing.sample_size = len(new_entity_ids)
        raw_sig = f"{cohort_id}:{existing.cohort_type}:{json.dumps(new_filter_criteria, sort_keys=True)}:{json.dumps(existing.entity_ids)}:{existing.version}"
        existing.cohort_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
        return existing

    def get_cohort(self, cohort_id: str) -> ResearchCohort:
        if cohort_id not in self._cohorts:
            raise KeyError(f"Cohort '{cohort_id}' not found.")
        return self._cohorts[cohort_id]

    def list_cohorts(self, cohort_type: str | None = None) -> list[ResearchCohort]:
        cohorts = list(self._cohorts.values())
        if cohort_type:
            cohorts = [c for c in cohorts if c.cohort_type == cohort_type.upper()]
        return cohorts


_GLOBAL_COHORT_ENGINE: CohortEngine | None = None


def get_cohort_engine() -> CohortEngine:
    global _GLOBAL_COHORT_ENGINE
    if _GLOBAL_COHORT_ENGINE is None:
        _GLOBAL_COHORT_ENGINE = CohortEngine()
        # Seed standard research cohorts for tier-1 analysis
        _GLOBAL_COHORT_ENGINE.create_cohort(
            cohort_id="cohort_u23_midfielders_epl",
            cohort_type="PLAYER",
            name="U23 Central Midfielders in EPL (>=900 mins)",
            filter_criteria={"age_max": 23, "position": "CM", "competition": "EPL", "min_minutes": 900},
            entity_ids=["p_epl_01", "p_epl_02", "p_epl_03", "p_epl_04", "p_epl_05"],
            competition_scope=["EPL"],
            temporal_scope={"start": "2023-08-01", "end": "2024-05-30"},
        )
        _GLOBAL_COHORT_ENGINE.create_cohort(
            cohort_id="cohort_cross_league_transfers_u25",
            cohort_type="TRANSFER",
            name="Cross-League Transfers U25 (Source != Target, Fee > 10M)",
            filter_criteria={"age_max": 25, "is_cross_competition": True, "min_fee_eur": 10000000},
            entity_ids=["tr_01", "tr_02", "tr_03", "tr_04", "tr_05", "tr_06"],
            competition_scope=["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"],
            temporal_scope={"start": "2022-07-01", "end": "2024-09-01"},
        )
    return _GLOBAL_COHORT_ENGINE
