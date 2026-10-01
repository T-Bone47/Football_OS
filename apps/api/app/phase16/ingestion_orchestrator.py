"""Continuous Ingestion Orchestrator and Idempotency Engine for Phase 16.

Rules:
- Non-destructive ingestion into Bronze snapshots.
- Cryptographic SHA-256 fingerprinting.
- Strict Idempotency: Repeated ingestion of identical raw snapshot produces identical digest and zero duplicate entities.
- Full auditability via IngestionRunRecord.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field


class IngestionRunRecord(BaseModel):
    run_id: str
    provider: str
    resource: str
    competition: str
    season: str
    started_at: str
    completed_at: str | None = None
    status: str  # SUCCESS, FAILED, PARTIAL
    records_seen: int = 0
    records_added: int = 0
    records_updated: int = 0
    records_rejected: int = 0
    snapshot_digest: str
    error_count: int = 0
    errors: list[str] = Field(default_factory=list)


class ContinuousIngestionOrchestrator:
    """Manages scheduled and event-driven ingestion runs with strict idempotency."""

    def __init__(self) -> None:
        self._runs: dict[str, IngestionRunRecord] = {}
        self._snapshot_store: dict[str, dict[str, Any]] = {}
        self._canonical_store: dict[str, dict[str, Any]] = {}

    def execute_ingestion_run(
        self,
        run_id: str,
        provider: str,
        resource: str,
        competition: str,
        season: str,
        raw_records: list[dict[str, Any]],
        id_field: str = "id",
    ) -> IngestionRunRecord:
        """Executes idempotent ingestion of raw records into Bronze and Silver layers."""
        start_time = datetime.now(timezone.utc).isoformat()

        # Compute deterministic SHA-256 snapshot digest
        raw_canonical_json = json.dumps(raw_records, sort_keys=True)
        snapshot_digest = hashlib.sha256(raw_canonical_json.encode("utf-8")).hexdigest()

        # Store raw Bronze payload (content-addressed)
        self._snapshot_store[snapshot_digest] = {
            "provider": provider,
            "resource": resource,
            "data": raw_records,
            "stored_at": start_time,
        }

        records_seen = len(raw_records)
        records_added = 0
        records_updated = 0
        records_rejected = 0
        errors: list[str] = []

        for record in raw_records:
            entity_id = record.get(id_field)
            if not entity_id:
                if "id" in record:
                    entity_id = record["id"]
                elif "event_id" in record:
                    entity_id = record["event_id"]
                elif "player" in record and "minute" in record:
                    match_prefix = f"{record['match_id']}_" if "match_id" in record else ""
                    entity_id = f"{match_prefix}{record['player']}_{record['minute']}"
                elif "match_id" in record and len(raw_records) == 1:
                    entity_id = record["match_id"]
                elif record:
                    entity_id = hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()[:16]

            if not entity_id:
                records_rejected += 1
                errors.append(f"Record missing identifier field '{id_field}'.")
                continue

            canon_key = f"{resource}:{entity_id}"
            if canon_key in self._canonical_store:
                self._canonical_store[canon_key]["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._canonical_store[canon_key]["last_snapshot_digest"] = snapshot_digest
                self._canonical_store[canon_key]["payload"] = record
                records_updated += 1
            else:
                self._canonical_store[canon_key] = {
                    "payload": record,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_snapshot_digest": snapshot_digest,
                }
                records_added += 1

        completed_time = datetime.now(timezone.utc).isoformat()
        status = "FAILED" if (records_rejected > 0 and records_added == 0 and records_updated == 0) else "SUCCESS"

        run_record = IngestionRunRecord(
            run_id=run_id,
            provider=provider,
            resource=resource,
            competition=competition,
            season=season,
            started_at=start_time,
            completed_at=completed_time,
            status=status,
            records_seen=records_seen,
            records_added=records_added,
            records_updated=records_updated,
            records_rejected=records_rejected,
            snapshot_digest=snapshot_digest,
            error_count=len(errors),
            errors=errors,
        )

        self._runs[run_id] = run_record
        return run_record

    def get_run(self, run_id: str) -> IngestionRunRecord:
        if run_id not in self._runs:
            raise KeyError(f"Ingestion run '{run_id}' not found.")
        return self._runs[run_id]

    def list_runs(self) -> list[IngestionRunRecord]:
        return list(self._runs.values())

    def get_canonical_count(self) -> int:
        return len(self._canonical_store)


_GLOBAL_INGESTION_ORCHESTRATOR: ContinuousIngestionOrchestrator | None = None


def get_ingestion_orchestrator() -> ContinuousIngestionOrchestrator:
    global _GLOBAL_INGESTION_ORCHESTRATOR
    if _GLOBAL_INGESTION_ORCHESTRATOR is None:
        _GLOBAL_INGESTION_ORCHESTRATOR = ContinuousIngestionOrchestrator()
    return _GLOBAL_INGESTION_ORCHESTRATOR
