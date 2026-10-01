"""Unified Freshness Engine and Dependency Propagation for Phase 16.

Tracks and propagates freshness across 5 architectural tiers:
1. RAW DATA
2. CANONICAL DATA
3. FEATURE STORE
4. MODEL READINESS
5. DECISION RECORDS

Propagation Rule:
Stale Raw Data -> Stale Canonical -> Stale Feature -> Degraded Model Readiness -> Decision Review Required.
"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import FreshnessState
from app.dev_fixtures import dev_seed_enabled


class EntityFreshnessSnapshot(BaseModel):
    entity_id: str
    entity_type: str  # RAW, CANONICAL, FEATURE, MODEL, DECISION
    last_observed_at: str
    last_ingested_at: str
    last_validated_at: str
    last_feature_refresh: str | None = None
    last_model_refresh: str | None = None
    freshness_state: FreshnessState
    age_hours: float
    max_threshold_hours: float
    stale_reasons: list[str] = Field(default_factory=list)
    requires_review: bool = False


class FreshnessEngine:
    """Manages multi-tier freshness thresholds and deterministic dependency propagation."""

    # Default TTLs in hours
    DEFAULT_THRESHOLDS = {
        "RAW": 24.0,        # Raw match/fixture updates
        "CANONICAL": 24.0,  # Silver normalized tables
        "FEATURE": 48.0,    # Gold feature snapshots
        "MODEL": 168.0,     # 7 days before model health review
        "DECISION": 336.0,  # 14 days before recruitment decision staleness
    }

    def __init__(self) -> None:
        self._snapshots: dict[str, EntityFreshnessSnapshot] = {}
        self._dependencies: dict[str, list[str]] = {}

    def register_entity(
        self,
        entity_id: str,
        entity_type: str,
        ttl_hours: float,
        dependencies: list[str] | None = None,
    ) -> EntityFreshnessSnapshot:
        self._dependencies[entity_id] = list(dependencies or [])
        now_str = datetime.now(timezone.utc).isoformat()
        return self.record_freshness(
            entity_id=entity_id,
            entity_type=entity_type,
            last_observed_at=now_str,
            last_ingested_at=now_str,
            last_validated_at=now_str,
            max_threshold_hours=ttl_hours,
        )

    def mark_stale(self, entity_id: str, reason: str = "") -> EntityFreshnessSnapshot:
        if entity_id in self._snapshots:
            snap = self._snapshots[entity_id]
            reasons = list(snap.stale_reasons)
            if reason and reason not in reasons:
                reasons.append(reason)
            updated = EntityFreshnessSnapshot(
                entity_id=snap.entity_id,
                entity_type=snap.entity_type,
                last_observed_at=snap.last_observed_at,
                last_ingested_at=snap.last_ingested_at,
                last_validated_at=snap.last_validated_at,
                last_feature_refresh=snap.last_feature_refresh,
                last_model_refresh=snap.last_model_refresh,
                freshness_state=FreshnessState.STALE,
                age_hours=snap.age_hours,
                max_threshold_hours=snap.max_threshold_hours,
                stale_reasons=reasons,
                requires_review=True,
            )
            self._snapshots[entity_id] = updated
            return updated
        now_str = datetime.now(timezone.utc).isoformat()
        snap = EntityFreshnessSnapshot(
            entity_id=entity_id,
            entity_type="RAW",
            last_observed_at=now_str,
            last_ingested_at=now_str,
            last_validated_at=now_str,
            freshness_state=FreshnessState.STALE,
            age_hours=99.0,
            max_threshold_hours=24.0,
            stale_reasons=[reason] if reason else ["MANUALLY_MARKED_STALE"],
            requires_review=True,
        )
        self._snapshots[entity_id] = snap
        return snap

    def propagate_freshness(self) -> None:
        changed = True
        iterations = 0
        while changed and iterations < 10:
            changed = False
            iterations += 1
            for entity_id, deps in self._dependencies.items():
                target_snap = self._snapshots.get(entity_id)
                if not target_snap:
                    continue
                for dep_id in deps:
                    dep_snap = self._snapshots.get(dep_id)
                    if dep_snap and (dep_snap.freshness_state in (FreshnessState.STALE, FreshnessState.EXPIRED, FreshnessState.AGING) or dep_snap.requires_review):
                        if target_snap.freshness_state != FreshnessState.STALE or not target_snap.requires_review or "UPSTREAM_DEPENDENCY_STALE" not in target_snap.stale_reasons:
                            reasons = list(target_snap.stale_reasons)
                            if "UPSTREAM_DEPENDENCY_STALE" not in reasons:
                                reasons.append("UPSTREAM_DEPENDENCY_STALE")
                            self._snapshots[entity_id] = EntityFreshnessSnapshot(
                                entity_id=target_snap.entity_id,
                                entity_type=target_snap.entity_type,
                                last_observed_at=target_snap.last_observed_at,
                                last_ingested_at=target_snap.last_ingested_at,
                                last_validated_at=target_snap.last_validated_at,
                                last_feature_refresh=target_snap.last_feature_refresh,
                                last_model_refresh=target_snap.last_model_refresh,
                                freshness_state=FreshnessState.STALE,
                                age_hours=target_snap.age_hours,
                                max_threshold_hours=target_snap.max_threshold_hours,
                                stale_reasons=reasons,
                                requires_review=True,
                            )
                            target_snap = self._snapshots[entity_id]
                            changed = True

    def get_snapshot(self, entity_id: str) -> EntityFreshnessSnapshot:
        return self.get_freshness(entity_id)

    def record_freshness(
        self,
        entity_id: str,
        entity_type: str,
        last_observed_at: str,
        last_ingested_at: str,
        last_validated_at: str,
        last_feature_refresh: str | None = None,
        last_model_refresh: str | None = None,
        max_threshold_hours: float | None = None,
        custom_reasons: list[str] | None = None,
    ) -> EntityFreshnessSnapshot:
        threshold = max_threshold_hours or self.DEFAULT_THRESHOLDS.get(entity_type.upper(), 48.0)

        now = datetime.now(timezone.utc)
        obs_dt = datetime.fromisoformat(last_observed_at.replace("Z", "+00:00"))
        age_hours = round((now - obs_dt).total_seconds() / 3600.0, 2)

        stale_reasons: list[str] = list(custom_reasons or [])
        requires_review = False

        state: FreshnessState
        if age_hours <= threshold * 0.5:
            state = FreshnessState.FRESH
        elif age_hours <= threshold:
            state = FreshnessState.AGING
        elif age_hours <= threshold * 2.0:
            state = FreshnessState.STALE
            stale_reasons.append(f"Entity age ({age_hours}h) exceeds freshness threshold ({threshold}h).")
            requires_review = True
        else:
            state = FreshnessState.EXPIRED
            stale_reasons.append(f"Entity data expired ({age_hours}h > {threshold * 2.0}h).")
            requires_review = True

        snapshot = EntityFreshnessSnapshot(
            entity_id=entity_id,
            entity_type=entity_type.upper(),
            last_observed_at=last_observed_at,
            last_ingested_at=last_ingested_at,
            last_validated_at=last_validated_at,
            last_feature_refresh=last_feature_refresh,
            last_model_refresh=last_model_refresh,
            freshness_state=state,
            age_hours=age_hours,
            max_threshold_hours=threshold,
            stale_reasons=stale_reasons,
            requires_review=requires_review,
        )

        self._snapshots[entity_id] = snapshot
        return snapshot

    def propagate_staleness(
        self,
        raw_entity_id: str,
        canonical_id: str,
        feature_id: str,
        model_id: str,
        decision_id: str,
    ) -> list[EntityFreshnessSnapshot]:
        """Propagates staleness down the entire dependency chain:

        Raw -> Canonical -> Feature -> Model -> Decision.
        """
        raw = self.get_freshness(raw_entity_id)
        chain_snapshots: list[EntityFreshnessSnapshot] = [raw]

        is_stale = raw.freshness_state in (FreshnessState.STALE, FreshnessState.EXPIRED)

        # 1. Canonical
        canon_snap = self.record_freshness(
            entity_id=canonical_id,
            entity_type="CANONICAL",
            last_observed_at=raw.last_observed_at,
            last_ingested_at=raw.last_ingested_at,
            last_validated_at=raw.last_validated_at,
            custom_reasons=["UPSTREAM_RAW_STALE"] if is_stale else [],
        )
        chain_snapshots.append(canon_snap)

        # 2. Feature
        feat_snap = self.record_freshness(
            entity_id=feature_id,
            entity_type="FEATURE",
            last_observed_at=raw.last_observed_at,
            last_ingested_at=raw.last_ingested_at,
            last_validated_at=raw.last_validated_at,
            custom_reasons=["UPSTREAM_CANONICAL_STALE"] if is_stale else [],
        )
        chain_snapshots.append(feat_snap)

        # 3. Model
        model_snap = self.record_freshness(
            entity_id=model_id,
            entity_type="MODEL",
            last_observed_at=raw.last_observed_at,
            last_ingested_at=raw.last_ingested_at,
            last_validated_at=raw.last_validated_at,
            custom_reasons=["MODEL_INPUT_FEATURES_STALE"] if is_stale else [],
        )
        chain_snapshots.append(model_snap)

        # 4. Decision
        dec_snap = self.record_freshness(
            entity_id=decision_id,
            entity_type="DECISION",
            last_observed_at=raw.last_observed_at,
            last_ingested_at=raw.last_ingested_at,
            last_validated_at=raw.last_validated_at,
            custom_reasons=["DATA_CHANGED", "MARKET_CHANGED"] if is_stale else [],
        )
        chain_snapshots.append(dec_snap)

        return chain_snapshots

    def get_freshness(self, entity_id: str) -> EntityFreshnessSnapshot:
        if entity_id not in self._snapshots:
            raise KeyError(f"Freshness record for entity '{entity_id}' not found.")
        return self._snapshots[entity_id]

    def list_snapshots(self, entity_type: str | None = None) -> list[EntityFreshnessSnapshot]:
        snaps = list(self._snapshots.values())
        if entity_type:
            snaps = [s for s in snaps if s.entity_type == entity_type.upper()]
        return snaps


_GLOBAL_FRESHNESS_ENGINE: FreshnessEngine | None = None


def get_freshness_engine() -> FreshnessEngine:
    global _GLOBAL_FRESHNESS_ENGINE
    if _GLOBAL_FRESHNESS_ENGINE is None:
        _GLOBAL_FRESHNESS_ENGINE = FreshnessEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed initial operational freshness records
            now_str = datetime.now(timezone.utc).isoformat()
            _GLOBAL_FRESHNESS_ENGINE.record_freshness(
                entity_id="raw_epl_fixtures_2024",
                entity_type="RAW",
                last_observed_at=now_str,
                last_ingested_at=now_str,
                last_validated_at=now_str,
            )
            _GLOBAL_FRESHNESS_ENGINE.record_freshness(
                entity_id="canon_player_rice_2024",
                entity_type="CANONICAL",
                last_observed_at=now_str,
                last_ingested_at=now_str,
                last_validated_at=now_str,
            )
    return _GLOBAL_FRESHNESS_ENGINE
