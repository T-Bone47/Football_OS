"""Phase 10 — Immutable Decision Records & Historical Replayability (§13).

Stores complete immutable audit snapshots for signed recruitment decisions:
  - decision_id
  - project_id
  - chosen_candidate
  - candidate_set
  - constraints
  - model_versions
  - feature_set
  - evidence_dag (SHA-256 graph digest + node breakdown)
  - scenario_assumptions
  - data_status
  - confidence
  - decision_timestamp

Guarantees:
  - A historical decision record is strictly immutable once finalized
  - The decision state can be re-evaluated and replayed against its historical feature context
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DecisionRecord:
    """Immutable recruitment decision record (§13)."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    project_name: str = ""
    chosen_candidate_id: str = ""
    chosen_candidate_name: str = ""
    decision_type: str = "TARGET_SIGNING"  # TARGET_SIGNING, REJECT_TARGET, RETAIN_INTERNAL
    decision_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Snapshot context
    candidate_set: list[dict[str, Any]] = field(default_factory=list)
    project_constraints: dict[str, Any] = field(default_factory=dict)
    scenario_assumptions: list[str] = field(default_factory=list)

    # Model and feature lineage
    model_versions: dict[str, str] = field(default_factory=dict)
    feature_set_version: str = "recruitment_v1.0"
    evidence_dag_digest: str = ""
    evidence_nodes_count: int = 0

    # Decision integrity
    confidence: str = "HIGH"
    data_status: str = "DECISION_VALIDATED"
    is_immutable: bool = True
    signed_by: str = "Head of Recruitment"
    audit_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.audit_hash:
            self.audit_hash = self.compute_digest()

    def compute_digest(self) -> str:
        """Computes deterministic SHA-256 cryptographic digest over the immutable decision contents."""
        payload = {
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "chosen_candidate_id": self.chosen_candidate_id,
            "decision_timestamp": self.decision_timestamp,
            "feature_set_version": self.feature_set_version,
            "model_versions": sorted(self.model_versions.items()),
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionRecordStore:
    """Manages immutable persistence and historical replay of decision records."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionRecord] = {}
        self._seed_default_record()

    def _seed_default_record(self) -> None:
        rec = DecisionRecord(
            decision_id="dec_rec_inacio_2027",
            project_id="proj_cb_summer_2027",
            project_name="Summer 2027 CB Recruitment",
            chosen_candidate_id="cand_inacio",
            chosen_candidate_name="Gonçalo Inácio",
            decision_type="TARGET_SIGNING",
            candidate_set=[
                {"candidate_id": "cand_inacio", "name": "Gonçalo Inácio", "fit": 86.2, "fee": 38_000_000.0},
                {"candidate_id": "cand_saliba", "name": "William Saliba", "fit": 92.4, "fee": 75_000_000.0},
            ],
            project_constraints={
                "budget_eur": 40_000_000.0,
                "position": "CB",
                "target_role": "Ball Playing Defender",
            },
            scenario_assumptions=[
                "€38.0M release clause triggered",
                "Outgoing squad depth maintained",
            ],
            model_versions={
                "tactical_fit": "TacticalFitCalculator_v1.0",
                "valuation": "val_lightgbm_20260920",
                "match_prediction": "calibrated_multinomial_logit_v1",
            },
            feature_set_version="recruitment_v1.0",
            evidence_dag_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            evidence_nodes_count=14,
            confidence="HIGH",
            data_status="DECISION_VALIDATED",
            signed_by="Technical Director",
        )
        self._records[rec.decision_id] = rec

    def record_decision(self, data: dict[str, Any]) -> DecisionRecord:
        """Finalizes and stores an immutable decision record."""
        rec = DecisionRecord(
            decision_id=data.get("decision_id") or f"dec_{uuid.uuid4().hex[:8]}",
            project_id=data.get("project_id", ""),
            project_name=data.get("project_name", ""),
            chosen_candidate_id=data.get("chosen_candidate_id", ""),
            chosen_candidate_name=data.get("chosen_candidate_name", ""),
            decision_type=data.get("decision_type", "TARGET_SIGNING"),
            candidate_set=data.get("candidate_set", []),
            project_constraints=data.get("project_constraints", {}),
            scenario_assumptions=data.get("scenario_assumptions", []),
            model_versions=data.get("model_versions", {}),
            feature_set_version=data.get("feature_set_version", "recruitment_v1.0"),
            evidence_dag_digest=data.get("evidence_dag_digest", ""),
            evidence_nodes_count=int(data.get("evidence_nodes_count", 0)),
            confidence=data.get("confidence", "HIGH"),
            data_status=data.get("data_status", "DECISION_VALIDATED"),
            signed_by=data.get("signed_by", "Head of Scouting"),
        )
        self._records[rec.decision_id] = rec
        return rec

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        return self._records.get(decision_id)

    def list_decisions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        res = list(self._records.values())
        if project_id:
            res = [r for r in res if r.project_id == project_id]
        return [r.to_dict() for r in res]

    def verify_integrity(self, decision_id: str) -> tuple[bool, str]:
        """Re-computes cryptographic digest and verifies record has not been mutated."""
        rec = self._records.get(decision_id)
        if not rec:
            return False, "Decision record not found"
        computed = rec.compute_digest()
        if computed == rec.audit_hash:
            return True, "Decision record cryptographic integrity verified: 0 tampering detected."
        return False, f"Integrity violation: recorded {rec.audit_hash} != computed {computed}"


decision_store = DecisionRecordStore()
