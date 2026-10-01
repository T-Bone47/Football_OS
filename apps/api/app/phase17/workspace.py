"""Projects, decisions and provenance (§21, §22, §41-§43).

A decision's evidence graph is assembled on the server from the inference
ids it cites; a client cannot supply its own evidence. The graph walks
Decision -> Inference (model/feature/dataset version, cutoff) -> Silver
matches used -> Bronze snapshots (SHA-256) -> ingestion runs -> provider.
Decisions are immutable rows; a revision is a new row with supersedes_id.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Match
from app.db.models.operations import DecisionRecord, InferenceLog, OpsUser, OutcomeRecord, Project
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.phase17.audit import append_event


async def snapshot_lineage(session: AsyncSession, snapshot_id: uuid.UUID | None) -> dict[str, Any] | None:
    if snapshot_id is None:
        return None
    row = (await session.execute(
        select(DataSnapshot, IngestionRun, DataSource)
        .join(IngestionRun, DataSnapshot.ingestion_run_id == IngestionRun.id)
        .join(DataSource, IngestionRun.data_source_id == DataSource.id)
        .where(DataSnapshot.id == snapshot_id))).one_or_none()
    if row is None:
        return {"snapshot_id": str(snapshot_id), "status": "ORPHAN"}
    snap, run, src = row
    return {"snapshot_id": str(snap.id), "sha256": snap.sha256, "storage_location": snap.storage_location,
            "provider_retrieved_at": snap.provider_retrieved_at.isoformat() if snap.provider_retrieved_at else None,
            "http_status": snap.http_status, "source_url": snap.source_url, "validation": snap.validation_status.value,
            "schema_version": snap.schema_version,
            "ingestion_run": {"id": str(run.id), "endpoint": run.endpoint, "parameters": run.parameters,
                              "status": run.status.value},
            "provider": {"name": src.name, "license": src.license, "base_url": src.base_url}}


async def build_evidence_graph(session: AsyncSession, inference_ids: list[uuid.UUID]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    missing: list[str] = []
    for iid in inference_ids:
        inf = await session.get(InferenceLog, iid)
        if inf is None:
            missing.append(str(iid))
            continue
        subject = await session.get(Match, uuid.UUID(inf.subject_id)) if inf.subject_id else None
        history_ids = [uuid.UUID(h) for h in (inf.evidence or {}).get("history_match_ids", [])]
        hist_snaps = (await session.execute(select(Match.snapshot_id).where(Match.id.in_(history_ids)).distinct())).scalars().all() \
            if history_ids else []
        outcome = (await session.execute(select(OutcomeRecord).where(OutcomeRecord.inference_id == iid))).scalar_one_or_none()
        nodes.append({
            "inference": {"id": str(inf.id), "status": inf.status, "domain": inf.domain,
                          "prediction_type": inf.prediction_type, "created_at": inf.created_at.isoformat(),
                          "output": inf.output, "reasons": inf.reasons},
            "model": {"model_id": inf.model_id, "model_version": inf.model_version,
                      "feature_version": inf.feature_version, "dataset_version": inf.dataset_version},
            "data_cutoff": inf.data_cutoff.isoformat() if inf.data_cutoff else None,
            "subject_match": {"id": str(subject.id), "provider_fixture_id": subject.provider_fixture_id,
                              "snapshot": await snapshot_lineage(session, subject.snapshot_id)} if subject else None,
            "history": {"matches": len(history_ids),
                        "snapshots": [await snapshot_lineage(session, s) for s in hist_snaps if s]},
            "outcome": {"result": outcome.realized, "observation_mode": outcome.observation_mode,
                        "evaluation": outcome.evaluation} if outcome else None,
        })
    return {"nodes": nodes, "missing_inferences": missing, "complete": not missing and bool(nodes)}


def _content_hash(fields: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


async def create_decision(session: AsyncSession, user: OpsUser, project: Project, *, title: str, decision: str,
                          subject_type: str, subject_id: str, rationale: str, inference_ids: list[uuid.UUID],
                          idempotency_key: str | None, supersedes_id: uuid.UUID | None = None) -> tuple[DecisionRecord, bool]:
    """Returns (record, created). Replaying the same idempotency key returns
    the original record instead of a duplicate."""
    if idempotency_key:
        existing = (await session.execute(select(DecisionRecord).where(
            DecisionRecord.user_id == user.id, DecisionRecord.idempotency_key == idempotency_key))).scalar_one_or_none()
        if existing is not None:
            return existing, False
    graph = await build_evidence_graph(session, inference_ids)
    cutoffs = [n["data_cutoff"] for n in graph["nodes"] if n["data_cutoff"]]
    data_cutoff = max(datetime.fromisoformat(c) for c in cutoffs) if cutoffs else datetime.now(timezone.utc)
    fields = {"project": str(project.id), "user": str(user.id), "title": title, "decision": decision,
              "subject_type": subject_type, "subject_id": subject_id, "rationale": rationale,
              "inference_ids": sorted(str(i) for i in inference_ids), "supersedes": str(supersedes_id) if supersedes_id else None,
              "evidence_graph": graph, "data_cutoff": data_cutoff.isoformat()}
    rec = DecisionRecord(project_id=project.id, user_id=user.id, supersedes_id=supersedes_id,
                         idempotency_key=idempotency_key, title=title, decision=decision, subject_type=subject_type,
                         subject_id=subject_id, rationale=rationale, evidence_graph=graph,
                         inference_ids=[str(i) for i in inference_ids], data_cutoff=data_cutoff,
                         content_sha256=_content_hash(fields))
    session.add(rec)
    await session.flush()
    await append_event(session, "DECISION_RECORDED", str(user.id), str(rec.id),
                       {"project": str(project.id), "content_sha256": rec.content_sha256,
                        "evidence_complete": graph["complete"]})
    return rec, True


def verify_decision_integrity(rec: DecisionRecord) -> bool:
    fields = {"project": str(rec.project_id), "user": str(rec.user_id), "title": rec.title, "decision": rec.decision,
              "subject_type": rec.subject_type, "subject_id": rec.subject_id, "rationale": rec.rationale,
              "inference_ids": sorted(rec.inference_ids), "supersedes": str(rec.supersedes_id) if rec.supersedes_id else None,
              "evidence_graph": rec.evidence_graph, "data_cutoff": rec.data_cutoff.isoformat()}
    return _content_hash(fields) == rec.content_sha256


async def decision_staleness(session: AsyncSession, rec: DecisionRecord) -> dict[str, Any]:
    """STALE when any Silver match the decision relied on has been updated
    after the decision was recorded."""
    match_ids: set[uuid.UUID] = set()
    for node in rec.evidence_graph.get("nodes", []):
        if node.get("subject_match"):
            match_ids.add(uuid.UUID(node["subject_match"]["id"]))
    if not match_ids:
        return {"decision_id": str(rec.id), "state": "UNVERIFIED", "reason": "decision cites no Silver data"}
    newest = (await session.execute(select(func.max(Match.updated_at)).where(Match.id.in_(match_ids)))).scalar_one()
    stale = newest is not None and newest > rec.created_at
    return {"decision_id": str(rec.id), "state": "STALE" if stale else "CURRENT",
            "decision_recorded_at": rec.created_at.isoformat(),
            "latest_dependency_update": newest.isoformat() if newest else None}
