"""Phase 10 — Operational Ingestion Pipeline & Run Management (§2, §3).

Validates caller-supplied payloads against the Phase 9 quality gates and
records the run. It performs no provider request and writes nothing to
Bronze; see execute_cycle() for the Phase 17 correction. Real ingestion is
app.phase17.live_ingestion (POST /api/v1/ops/ingestion/jobs).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.phase9.data_quality_gates import GateDecision, run_all_gates


class IngestionRunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


@dataclass
class IngestionCycleRecord:
    """Telemetry record for a single operational ingestion cycle (§3)."""
    ingestion_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = "api-football"
    resource: str = "fixtures"
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    status: str = IngestionRunStatus.QUEUED
    records_seen: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    validation_status: str = "PENDING"
    snapshot_id: str | None = None
    checksum: str | None = None
    error_summary: str | None = None
    stages_completed: list[str] = field(default_factory=list)
    impact_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationalIngestionPipeline:
    """Manages scheduled and on-demand operational ingestion runs."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.data_root = Path(data_root) if data_root else Path(__file__).resolve().parents[3] / "data"
        self._history: list[IngestionCycleRecord] = []

    def execute_cycle(
        self,
        provider: str = "api-football",
        resource: str = "fixtures",
        payload: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> IngestionCycleRecord:
        """Validates a caller-supplied payload against the Phase 9 quality gates.

        Phase 17 correction (reconnaissance R4): this cycle used to invent an
        API-Football fixture when no payload was given, write it into the
        provider's Bronze namespace, and report normalization, feature
        refresh and model readiness stages it never ran. It now:
        - refuses to run without a payload (no synthetic data, ever);
        - never writes a caller-supplied payload into provider Bronze storage,
          because a caller is not the provider;
        - lists only the stages it actually executed.
        Real provider ingestion is POST /api/v1/ops/ingestion/jobs.
        """
        cycle = IngestionCycleRecord(
            provider=provider,
            resource=resource,
            status=IngestionRunStatus.RUNNING,
        )
        not_executed = [
            "provider_authentication", "provider_request", "bronze_persistence", "silver_normalization",
            "identity_resolution", "feature_refresh", "model_readiness", "decision_impact",
        ]
        cycle.impact_summary = {"status": "UNVERIFIED", "stages_not_executed": not_executed}

        if payload is None:
            cycle.status = IngestionRunStatus.FAILED
            cycle.validation_status = "NOT_RUN"
            cycle.error_summary = (
                "NO_PROVIDER_PAYLOAD: this pipeline only validates a supplied payload and never "
                "generates data. Use POST /api/v1/ops/ingestion/jobs for real provider ingestion."
            )
            cycle.completed_at = datetime.now(timezone.utc).isoformat()
            self._history.append(cycle)
            return cycle

        try:
            cycle.stages_completed.append("payload_received")
            raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            cycle.checksum = sha256
            cycle.snapshot_id = f"unpersisted_{sha256[:12]}"
            cycle.stages_completed.append("payload_hashed")

            items = payload.get("response", []) if isinstance(payload, dict) else []
            cycle.records_seen = len(items)

            validation_records = [
                {
                    "provider": provider,
                    "source_record_id": str(r.get("fixture", {}).get("id", "0")),
                    "date": str(r.get("fixture", {}).get("date", ""))[:10],
                }
                for r in items
            ]

            gate_res = run_all_gates(
                records=validation_records,
                batch_id=cycle.ingestion_run_id,
                schema_fields=["provider", "source_record_id", "date"],
                id_fields=["source_record_id"],
                date_fields=["date"],
            )

            if gate_res.overall_decision in (GateDecision.REJECT, GateDecision.QUARANTINE):
                cycle.records_rejected = cycle.records_seen
                cycle.records_accepted = 0
                cycle.validation_status = "REJECTED" if gate_res.overall_decision == GateDecision.REJECT else "QUARANTINED"
                cycle.status = IngestionRunStatus.FAILED
                cycle.error_summary = f"Quality gate failure: {gate_res.overall_decision.value}"
                cycle.completed_at = datetime.now(timezone.utc).isoformat()
                self._history.append(cycle)
                return cycle

            cycle.records_accepted = cycle.records_seen
            cycle.records_rejected = 0
            cycle.validation_status = "PASSED"
            cycle.stages_completed.append("validation_gates_passed")
            # Validation of a supplied payload is all this cycle does.
            cycle.status = IngestionRunStatus.SUCCESS
            cycle.completed_at = datetime.now(timezone.utc).isoformat()

        except Exception as exc:
            cycle.status = IngestionRunStatus.FAILED
            cycle.error_summary = f"{type(exc).__name__}: {str(exc)}"
            cycle.completed_at = datetime.now(timezone.utc).isoformat()

        self._history.append(cycle)
        return cycle

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns historical run telemetry in reverse chronological order."""
        return [r.to_dict() for r in reversed(self._history[-limit:])]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch a specific ingestion run record by ID."""
        for r in self._history:
            if r.ingestion_run_id == run_id:
                return r.to_dict()
        return None


# Global singleton instance for operational use
operational_pipeline = OperationalIngestionPipeline()
