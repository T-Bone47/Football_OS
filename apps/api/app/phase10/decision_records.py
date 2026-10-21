"""Phase 10 — Immutable Decision Records & Historical Replayability (§13).

A decision record is an EVIDENCE record. Every content field is covered by its SHA-256 audit hash and
records form a hash chain per organisation, so changing any field of any record, or removing or reordering
records, is detectable (verify_integrity / verify_chain). What the store does NOT do is verify the inputs:
candidate data and model versions are recorded as supplied (lineage_status CLAIMED_NOT_VERIFIED), and
confidence / status / signer are never caller-asserted (UNASSESSED / RECORDED_UNVERIFIED / the authenticated user).

The previous version seeded a "validated" record about named real players whose evidence digest was the
SHA-256 of the EMPTY string, hashed only 6 of the fields, and accepted a free-text signer and confidence.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.persistence.factory import get_stores
from app.persistence.stores import LedgerConflict, LedgerRow, LedgerStore
from app.security.tokens import Principal

DECISION_TYPES = ("TARGET_SIGNING", "REJECT_TARGET", "RETAIN_INTERNAL")


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass
class DecisionRecord:
    """Immutable recruitment decision record (§13)."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    project_name: str = ""
    chosen_candidate_id: str = ""
    chosen_candidate_name: str = ""
    decision_type: str = ""  # TARGET_SIGNING, REJECT_TARGET, RETAIN_INTERNAL (explicit; never defaulted)
    decision_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Snapshot context
    candidate_set: list[dict[str, Any]] = field(default_factory=list)
    project_constraints: dict[str, Any] = field(default_factory=dict)
    scenario_assumptions: list[str] = field(default_factory=list)

    # Lineage: recorded as supplied, not verified
    model_versions: dict[str, str] = field(default_factory=dict)
    lineage_status: str = "CLAIMED_NOT_VERIFIED"
    feature_set_version: str = ""
    evidence_dag_digest: str = ""  # computed by the store from the evidence fields
    evidence_nodes_count: int = 0

    # Decision integrity
    confidence: str = "UNASSESSED"
    data_status: str = "RECORDED_UNVERIFIED"
    is_immutable: bool = True
    signed_by: str = ""  # the authenticated user
    organization_id: str | None = None
    prev_audit_hash: str = ""  # hash chain: the previous record of the same ledger
    audit_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.audit_hash:
            self.audit_hash = self.compute_digest()

    def compute_digest(self) -> str:
        """SHA-256 over EVERY field except audit_hash itself (canonical JSON)."""
        payload = asdict(self)
        payload.pop("audit_hash")
        return hashlib.sha256(_canonical(payload)).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionRecordStore:
    """Append-only store of decision records. With a LedgerStore (PostgreSQL in production) records are hash-chained
    per ledger and survive a restart; without one it is process-local."""

    KIND = "decision"

    def __init__(self, ledger_store: LedgerStore | None = None) -> None:
        self._ledger = ledger_store
        self._records: dict[str, DecisionRecord] = {}
        self._ledgers: dict[str, list[str]] = {}
        if ledger_store is not None:
            for key in ledger_store.ledger_keys(self.KIND):
                ids = self._ledgers.setdefault(key, [])
                for row in ledger_store.read(key):
                    self._records[row.entry_id] = DecisionRecord(**row.payload)
                    ids.append(row.entry_id)

    @staticmethod
    def _ledger_key(organization_id: str | None, signed_by: str) -> str:
        return organization_id if organization_id else f"user:{signed_by}"

    @staticmethod
    def _can_see(principal: Principal, record: DecisionRecord) -> bool:
        in_org = principal.org_id is not None and record.organization_id == principal.org_id
        return in_org or record.signed_by == principal.user_id

    def record_decision(self, data: dict[str, Any], *, signed_by: str, organization_id: str | None = None) -> DecisionRecord:
        if not signed_by:
            raise ValueError("signed_by (the authenticated user) is required")
        for key in ("project_id", "chosen_candidate_id"):
            if not str(data.get(key) or "").strip():
                raise ValueError(f"{key} is required")
        decision_type = data.get("decision_type")
        if decision_type not in DECISION_TYPES:
            raise ValueError(f"decision_type must be one of {DECISION_TYPES}")
        decision_id = data.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"
        if decision_id in self._records:
            raise ValueError(f"decision '{decision_id}' already exists")

        candidate_set = list(data.get("candidate_set") or [])
        evidence = {
            "candidate_set": candidate_set,
            "project_constraints": dict(data.get("project_constraints") or {}),
            "scenario_assumptions": list(data.get("scenario_assumptions") or []),
            "model_versions": dict(data.get("model_versions") or {}),
            "feature_set_version": str(data.get("feature_set_version") or ""),
        }
        ledger_key = self._ledger_key(organization_id, signed_by)
        ledger = self._ledgers.setdefault(ledger_key, [])
        prev_hash = self._records[ledger[-1]].audit_hash if ledger else ""
        record = DecisionRecord(
            decision_id=decision_id,
            project_id=str(data["project_id"]),
            project_name=str(data.get("project_name") or ""),
            chosen_candidate_id=str(data["chosen_candidate_id"]),
            chosen_candidate_name=str(data.get("chosen_candidate_name") or ""),
            decision_type=decision_type,
            candidate_set=candidate_set,
            project_constraints=evidence["project_constraints"],
            scenario_assumptions=evidence["scenario_assumptions"],
            model_versions=evidence["model_versions"],
            feature_set_version=evidence["feature_set_version"],
            evidence_dag_digest=hashlib.sha256(_canonical(evidence)).hexdigest(),
            evidence_nodes_count=len(candidate_set),
            signed_by=signed_by,
            organization_id=organization_id,
            prev_audit_hash=prev_hash,
        )
        record.audit_hash = record.compute_digest()
        if self._ledger is not None:
            try:
                self._ledger.append(
                    LedgerRow(
                        ledger_key=ledger_key,
                        seq=len(ledger) + 1,
                        entry_kind=self.KIND,
                        entry_id=decision_id,
                        organization_id=organization_id,
                        payload=record.to_dict(),
                        prev_hash=prev_hash,
                        entry_hash=record.audit_hash,
                    )
                )
            except LedgerConflict as exc:
                raise ValueError(f"decision '{decision_id}' was appended concurrently: {exc}") from exc
        self._records[decision_id] = record
        ledger.append(decision_id)
        return record

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        return self._records.get(decision_id)

    def get_decision_for(self, principal: Principal, decision_id: str) -> DecisionRecord:
        record = self._records.get(decision_id)
        if record is None or not self._can_see(principal, record):
            raise KeyError(f"Decision record '{decision_id}' not found")
        return record

    def list_decisions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        res = list(self._records.values())
        if project_id:
            res = [r for r in res if r.project_id == project_id]
        return [r.to_dict() for r in res]

    def list_decisions_for(self, principal: Principal, project_id: str | None = None) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records.values() if self._can_see(principal, r) and (not project_id or r.project_id == project_id)]

    def verify_integrity(self, decision_id: str) -> tuple[bool, str]:
        """Recomputes the record's digest over every field."""
        record = self._records.get(decision_id)
        if record is None:
            return False, "Decision record not found"
        if record.compute_digest() != record.audit_hash:
            return False, "Integrity violation: record content does not match its audit hash"
        return True, "Integrity verified: audit hash matches the record content"

    def verify_chain(self, ledger_key: str) -> tuple[bool, str]:
        """Every record's content hash AND its link to the previous record must hold."""
        ids = self._ledgers.get(ledger_key, [])
        previous = ""
        for decision_id in ids:
            record = self._records[decision_id]
            if record.compute_digest() != record.audit_hash:
                return False, f"record {decision_id}: content does not match its audit hash"
            if record.prev_audit_hash != previous:
                return False, f"record {decision_id}: broken link to the previous record"
            previous = record.audit_hash
        return True, f"chain intact ({len(ids)} records)"

    def verify_persisted_chain(self, ledger_key: str) -> tuple[bool, str]:
        """Re-reads the ledger from the store (no in-memory state) and verifies every content hash and link."""
        if self._ledger is None:
            return False, "no durable ledger store is configured"
        rows = self._ledger.read(ledger_key)
        previous = ""
        for row in rows:
            if DecisionRecord(**row.payload).compute_digest() != row.entry_hash:
                return False, f"record {row.entry_id}: content does not match its entry hash"
            if row.prev_hash != previous:
                return False, f"record {row.entry_id}: broken link to the previous entry"
            previous = row.entry_hash
        return True, f"persisted chain intact ({len(rows)} records)"


def _default_store() -> DecisionRecordStore:
    return DecisionRecordStore(ledger_store=get_stores()[1])


decision_store = _default_store()
