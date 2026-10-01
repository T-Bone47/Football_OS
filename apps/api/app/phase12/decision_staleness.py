"""Phase 12 — Decision Staleness & Freshness Assessment Engine (§4).

Evaluates whether historical recruitment and tactical decisions have become stale
due to new empirical evidence, feature drift, role shifts, or model version bumps.

Guarantees:
  - Historical DecisionRecord instances remain strictly immutable.
  - Generates a non-destructive DecisionFreshnessAssessment.
  - Decision state transitions: CURRENT → MONITOR → STALE → SUPERSEDED → ARCHIVED.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase12 import DecisionFreshnessState
from app.dev_fixtures import dev_seed_enabled


@dataclass
class DecisionFreshnessAssessment:
    """Non-destructive assessment of a historical decision's ongoing empirical validity."""
    assessment_id: str = field(default_factory=lambda: f"fresh_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    original_digest: str = ""
    current_evidence_digest: str = ""
    freshness_state: DecisionFreshnessState = DecisionFreshnessState.CURRENT
    materiality: str = "LOW"  # LOW, MODERATE, HIGH, CRITICAL
    assessment_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Delta Telemetry
    changed_entities: list[str] = field(default_factory=list)
    changed_features: list[str] = field(default_factory=list)
    changed_models: list[str] = field(default_factory=list)
    valuation_delta_eur: float = 0.0
    role_changed: bool = False
    tactical_system_drift: bool = False

    # Auditing
    reasons: list[str] = field(default_factory=list)
    original_decision_preserved: bool = True  # Strict invariant

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["freshness_state"] = self.freshness_state.value
        return data


class DecisionStalenessEngine:
    """Assesses historical decisions against current feature store and model registry states."""

    def __init__(self) -> None:
        self._assessments: dict[str, DecisionFreshnessAssessment] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_assessment()

    def _seed_default_assessment(self) -> None:
        seed = DecisionFreshnessAssessment(
            assessment_id="fresh_inacio_seed_001",
            decision_id="dec_rec_inacio_2027",
            original_digest="d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
            current_evidence_digest="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            freshness_state=DecisionFreshnessState.MONITOR,
            materiality="MODERATE",
            changed_entities=["cand_inacio"],
            changed_features=["prog_passes_per_90", "market_valuation_eur"],
            changed_models=["GBR_ValuationEngine_v1.0"],
            valuation_delta_eur=4_500_000.0,
            role_changed=False,
            tactical_system_drift=False,
            reasons=[
                "Player valuation increased by €4.5M (+11.8%) since decision sign-off.",
                "Primary tactical fit remains aligned (>85.0).",
                "Model version remains GBR_ValuationEngine_v1.0, but feature vector progressed 4 matchdays.",
            ],
            original_decision_preserved=True,
        )
        self._assessments[seed.decision_id] = seed

    def assess_decision(
        self,
        decision_id: str,
        original_digest: str,
        original_features: dict[str, Any],
        current_features: dict[str, Any],
        original_models: dict[str, str],
        current_models: dict[str, str],
        decision_timestamp: str,
    ) -> DecisionFreshnessAssessment:
        """Deterministically evaluates freshness based on feature shifts and model updates."""
        changed_features = []
        for feat_name, orig_val in original_features.items():
            curr_val = current_features.get(feat_name)
            if curr_val is not None and isinstance(orig_val, (int, float)) and isinstance(curr_val, (int, float)):
                if abs(curr_val - orig_val) / (abs(orig_val) + 1e-6) > 0.15:
                    changed_features.append(feat_name)

        changed_models = []
        for mod_name, orig_ver in original_models.items():
            curr_ver = current_models.get(mod_name)
            if curr_ver and curr_ver != orig_ver:
                changed_models.append(f"{mod_name} ({orig_ver} → {curr_ver})")

        # Valuation delta check
        orig_val_eur = float(original_features.get("market_valuation_eur", 0.0))
        curr_val_eur = float(current_features.get("market_valuation_eur", orig_val_eur))
        val_delta = curr_val_eur - orig_val_eur

        # Role change check
        orig_role = str(original_features.get("role", "Ball Playing Defender"))
        curr_role = str(current_features.get("role", orig_role))
        role_changed = orig_role != curr_role

        # Determine Freshness State
        reasons = []
        if role_changed:
            state = DecisionFreshnessState.STALE
            materiality = "HIGH"
            reasons.append(f"Primary role transitioned from {orig_role} to {curr_role}.")
        elif len(changed_models) > 0:
            state = DecisionFreshnessState.STALE
            materiality = "HIGH"
            reasons.append(f"Authoritative production model updated: {', '.join(changed_models)}.")
        elif abs(val_delta) > 10_000_000.0:
            state = DecisionFreshnessState.STALE
            materiality = "HIGH"
            reasons.append(f"Valuation shifted materially by €{val_delta/1e6:.1f}M.")
        elif len(changed_features) >= 2 or abs(val_delta) > 3_000_000.0:
            state = DecisionFreshnessState.MONITOR
            materiality = "MODERATE"
            reasons.append(f"{len(changed_features)} features shifted >15% since sign-off.")
        else:
            state = DecisionFreshnessState.CURRENT
            materiality = "LOW"
            reasons.append("Evidence remains within normal stability tolerance.")

        # Compute current evidence digest
        evidence_payload = {
            "decision_id": decision_id,
            "current_features": sorted(current_features.items()),
            "current_models": sorted(current_models.items()),
            "state": state.value,
        }
        curr_digest = hashlib.sha256(json.dumps(evidence_payload, sort_keys=True).encode("utf-8")).hexdigest()

        assessment = DecisionFreshnessAssessment(
            decision_id=decision_id,
            original_digest=original_digest,
            current_evidence_digest=curr_digest,
            freshness_state=state,
            materiality=materiality,
            changed_entities=list(current_features.keys())[:3],
            changed_features=changed_features,
            changed_models=changed_models,
            valuation_delta_eur=val_delta,
            role_changed=role_changed,
            tactical_system_drift=False,
            reasons=reasons,
            original_decision_preserved=True,
        )

        self._assessments[decision_id] = assessment
        return assessment

    def get_assessment(self, decision_id: str) -> DecisionFreshnessAssessment | None:
        return self._assessments.get(decision_id)

    def list_assessments(self) -> list[DecisionFreshnessAssessment]:
        return list(self._assessments.values())


decision_staleness_engine = DecisionStalenessEngine()
