"""Competition readiness, provider capability matrix and freshness chain
(§4, §11, §18, §49), all computed from recorded evidence.

No competition inherits another's status: every number below is filtered
to the competition it describes.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Competition, CompetitionSeason, Match, MatchEvent, MatchLineup, Season, Transfer
from app.db.models.operations import (
    Alert,
    ContractFingerprint,
    DecisionRecord,
    FeatureRefreshRecord,
    InferenceLog,
    JobRun,
    ModelRegistryEntry,
    OutcomeRecord,
    QualityReport,
)
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.phase17 import CapabilityState, CompetitionOperationalState as C
from app.phase17.match_state import PROVIDER_TIMING
from app.phase17.model_ops import MATCH_DOMAIN, MODE_LIVE, competition_key
from app.phase17.provider_probe import latest_probe_states

MIN_MATCHES_FOR_DATA = 30
MIN_LIVE_OUTCOMES_FOR_PRODUCTION = 100

# What each provider publishes at all. Anything absent is UNAVAILABLE for
# that provider regardless of competition.
PROVIDER_RESOURCES = {
    "statsbomb": {"competitions", "matches", "lineups", "events"},
    "api-football": {"leagues", "fixtures", "teams", "players", "lineups", "events", "statistics",
                     "transfers", "injuries", "standings", "odds"},
    "football-data-org": {"competitions", "fixtures", "teams", "standings"},
}
ALL_RESOURCES = ("leagues", "competitions", "seasons", "fixtures", "matches", "teams", "players", "lineups",
                 "events", "statistics", "transfers", "injuries", "standings", "odds")


async def capability_matrix(session: AsyncSession) -> dict[str, Any]:
    probes = await latest_probe_states(session)
    runs = (await session.execute(
        select(DataSource.name, IngestionRun.endpoint, IngestionRun.parameters, IngestionRun.status,
               IngestionRun.finished_at, IngestionRun.id)
        .join(DataSource, IngestionRun.data_source_id == DataSource.id)
    )).all()
    evidence: dict[tuple[str, str, str], list[dict]] = {}
    for provider, endpoint, params, status, finished, run_id in runs:
        scope = json.dumps({k: params[k] for k in sorted(params)} if params else {}, sort_keys=True)
        evidence.setdefault((provider, endpoint, scope), []).append(
            {"run_id": str(run_id), "status": status.value if hasattr(status, "value") else status,
             "finished_at": finished.isoformat() if finished else None})

    providers: dict[str, Any] = {}
    for provider, published in PROVIDER_RESOURCES.items():
        probe_rows = {res: row for (p, res), row in probes.items() if p == provider}
        reachable = any(r.state == "AVAILABLE" for r in probe_rows.values())
        resources: dict[str, Any] = {}
        for res in ALL_RESOURCES:
            if res not in published:
                resources[res] = {"state": CapabilityState.UNAVAILABLE.value, "evidence": "provider does not publish this resource"}
                continue
            scoped = {k: v for k, v in evidence.items() if k[0] == provider and k[1] == res}
            ok_scopes = [json.loads(k[2]) for k, v in scoped.items() if any(e["status"] == "SUCCESS" for e in v)]
            failed_scopes = [json.loads(k[2]) for k, v in scoped.items() if not any(e["status"] == "SUCCESS" for e in v)]
            probe = probe_rows.get(res)
            if ok_scopes:
                state = CapabilityState.LIVE_AVAILABLE if not failed_scopes else CapabilityState.PARTIAL
            elif probe is not None and probe.state == "AVAILABLE":
                state = CapabilityState.LIVE_AVAILABLE
            else:
                state = CapabilityState.UNVERIFIED
            resources[res] = {
                "state": state.value,
                "successful_scopes": len(ok_scopes), "failed_scopes": len(failed_scopes),
                "probe": {"state": probe.state, "http_status": probe.http_status, "latency_ms": probe.latency_ms,
                          "probed_at": probe.probed_at.isoformat()} if probe else None,
                "evidence": "real ingestion runs" if ok_scopes else "probe" if probe else "none",
            }
        providers[provider] = {
            "connectivity": "AVAILABLE" if reachable else (next(iter(probe_rows.values())).state if probe_rows else "UNKNOWN"),
            "timing": PROVIDER_TIMING.get(provider),
            "resources": resources,
        }

    # Competition x season dimension, from the provider's own index where we have it.
    comp_seasons: list[dict[str, Any]] = []
    index_snap = (await session.execute(
        select(DataSnapshot).join(IngestionRun, DataSnapshot.ingestion_run_id == IngestionRun.id)
        .join(DataSource, IngestionRun.data_source_id == DataSource.id)
        .where(DataSource.name == "statsbomb", IngestionRun.endpoint == "competitions")
        .order_by(DataSnapshot.retrieved_at.desc()).limit(1)
    )).scalar_one_or_none()
    if index_snap and not index_snap.storage_location.startswith("s3://"):
        try:
            index = json.loads(Path(index_snap.storage_location).read_bytes())
        except (OSError, json.JSONDecodeError):
            index = []
        for entry in index:
            scope = {"competition_id": entry["competition_id"], "season_id": entry["season_id"]}
            key = json.dumps(dict(sorted(scope.items())), sort_keys=True)
            match_runs = evidence.get(("statsbomb", "matches", key), [])
            comp_seasons.append({
                "provider": "statsbomb", "competition": f"{entry['competition_name']} ({entry['country_name']})",
                "season": entry["season_name"], "competition_id": entry["competition_id"], "season_id": entry["season_id"],
                "provider_match_updated": entry.get("match_updated"),
                "matches": CapabilityState.LIVE_AVAILABLE.value if any(r["status"] == "SUCCESS" for r in match_runs)
                else CapabilityState.UNVERIFIED.value,
            })
    return {"computed_at": datetime.now(timezone.utc).isoformat(),
            "state_definitions": {
                "LIVE_AVAILABLE": "verified by a real request from this deployment (not a claim of real-time data)",
                "PARTIAL": "some scopes verified, some failed",
                "UNAVAILABLE": "provider does not publish it",
                "UNVERIFIED": "published by the provider but never successfully requested from here"},
            "providers": providers, "statsbomb_competition_seasons": comp_seasons,
            "statsbomb_index_snapshot": index_snap.sha256 if index_snap else None}


async def competition_readiness(session: AsyncSession) -> list[dict[str, Any]]:
    model = (await session.execute(select(ModelRegistryEntry).where(ModelRegistryEntry.domain == MATCH_DOMAIN))).scalars().first()
    probes = await latest_probe_states(session)
    provider_ok = {p for (p, _), r in probes.items() if r.state == "AVAILABLE"}
    probed = {p for (p, _) in probes}
    out: list[dict[str, Any]] = []
    comps = (await session.execute(select(Competition))).scalars().all()
    for comp in comps:
        key = competition_key(comp)
        cs_ids = (await session.execute(select(CompetitionSeason.id).where(CompetitionSeason.competition_id == comp.id))).scalars().all()
        seasons = (await session.execute(select(Season.name).join(CompetitionSeason, CompetitionSeason.season_id == Season.id)
                                         .where(CompetitionSeason.competition_id == comp.id))).scalars().all()
        mq = select(Match).where(Match.competition_season_id.in_(cs_ids)) if cs_ids else None
        matches = (await session.execute(mq)).scalars().all() if mq is not None else []
        match_ids = [m.id for m in matches]
        finished = sum(1 for m in matches if m.status == "FINISHED")
        providers = sorted({m.provider for m in matches})
        lineups = (await session.execute(select(func.count()).select_from(MatchLineup).where(MatchLineup.match_id.in_(match_ids)))).scalar_one() if match_ids else 0
        players = (await session.execute(select(func.count(func.distinct(MatchLineup.player_id))).where(MatchLineup.match_id.in_(match_ids)))).scalar_one() if match_ids else 0
        events = (await session.execute(select(func.count()).select_from(MatchEvent).where(MatchEvent.match_id.in_(match_ids)))).scalar_one() if match_ids else 0
        ev_matches = (await session.execute(select(func.count(func.distinct(MatchEvent.match_id))).where(MatchEvent.match_id.in_(match_ids)))).scalar_one() if match_ids else 0
        transfers = (await session.execute(select(func.count()).select_from(Transfer))).scalar_one()
        snaps = (await session.execute(select(func.max(DataSnapshot.provider_retrieved_at)).join(Match, Match.snapshot_id == DataSnapshot.id)
                                       .where(Match.id.in_(match_ids)))).scalar_one() if match_ids else None
        inf_rows = (await session.execute(select(InferenceLog.status, InferenceLog.evidence).where(InferenceLog.competition == key))).all()
        ood = sum(1 for s, _ in inf_rows if s == "OUT_OF_DISTRIBUTION")
        live_outcomes = (await session.execute(
            select(func.count()).select_from(OutcomeRecord).join(InferenceLog, OutcomeRecord.inference_id == InferenceLog.id)
            .where(InferenceLog.competition == key, OutcomeRecord.observation_mode == MODE_LIVE))).scalar_one()
        quality = (await session.execute(select(QualityReport.overall).where(QualityReport.scope.in_(
            [f"silver:{p}:{cid}" for p in providers for cid in cs_ids])).order_by(QualityReport.created_at.desc()).limit(1))).scalar_one_or_none()
        metrics = (model.validation_metrics or {}) if model else {}
        verdict = (metrics.get("per_competition") or {}).get(key) or metrics.get(key)
        supported = bool(model and key in (model.supported_competitions or []))

        if not matches:
            state = C.NOT_AVAILABLE
        elif finished < MIN_MATCHES_FOR_DATA:
            state = C.INSUFFICIENT_DATA
        elif not supported:
            state = C.DATA_AVAILABLE
        elif model.deployment_state in ("SHADOW", "CANARY"):
            state = C.SHADOW
        elif live_outcomes >= MIN_LIVE_OUTCOMES_FOR_PRODUCTION and model.deployment_state == "PRODUCTION":
            state = C.PRODUCTION_READY
        else:
            state = C.MODEL_VALIDATED
        if quality == "FAIL":
            state = C.BLOCKED
        elif matches and providers and all(p in probed and p not in provider_ok for p in providers):
            # A probe positively observed the provider failing. No probe at
            # all is UNKNOWN, reported below, not a degradation.
            state = C.DEGRADED

        out.append({
            "competition": key, "seasons": sorted(seasons), "providers": providers,
            "competition_season_ids": [str(c) for c in cs_ids],
            "match_data": {"matches": len(matches), "finished": finished},
            "player_data": {"lineup_rows": lineups, "distinct_players": players},
            "event_data": {"event_rows": events, "matches_with_events": ev_matches},
            "transfer_data": {"rows": transfers, "state": "NOT_AVAILABLE" if transfers == 0 else "AVAILABLE_UNSCOPED"},
            "model_support": {"model": model.model_id if model else None, "supported": supported,
                              "deployment_state": model.deployment_state if model else None,
                              "validation": verdict or {"status": "NOT_TESTED"}},
            "calibration": {"historical_replay": (verdict or {}).get("status", "NOT_TESTED"),
                            "live": "NOT_ENOUGH_LIVE_OUTCOMES" if live_outcomes < MIN_LIVE_OUTCOMES_FOR_PRODUCTION else "MEASURED",
                            "live_outcomes": live_outcomes},
            "freshness": {"latest_retrieval": snaps.isoformat() if snaps else None,
                          "data_mode": "; ".join(PROVIDER_TIMING.get(p, {}).get("data_mode", "UNKNOWN") for p in providers) or None},
            "ood": {"inference_requests": len(inf_rows), "ood_refusals": ood,
                    "ood_rate": round(ood / len(inf_rows), 4) if inf_rows else None},
            "latest_quality": quality or "NOT_TESTED",
            "provider_status": {p: ("AVAILABLE" if p in provider_ok else "NOT_AVAILABLE" if p in probed else "UNKNOWN")
                                for p in providers},
            "production_status": state.value,
        })
    return sorted(out, key=lambda r: r["competition"])


async def freshness_chain(session: AsyncSession, competition_season_id: uuid.UUID, now: datetime | None = None) -> dict[str, Any]:
    """Timestamps at every layer for one competition season (§11). A layer
    built before its upstream changed is STALE. Archive data is never LIVE."""
    now = now or datetime.now(timezone.utc)
    matches = (await session.execute(select(Match).where(Match.competition_season_id == competition_season_id))).scalars().all()
    if not matches:
        return {"competition_season_id": str(competition_season_id), "status": "NOT_AVAILABLE", "layers": []}
    ids = [m.id for m in matches]
    keys = [str(m.provider_fixture_id) for m in matches]
    snap = (await session.execute(select(DataSnapshot).join(Match, Match.snapshot_id == DataSnapshot.id)
                                  .where(Match.id.in_(ids)).order_by(DataSnapshot.provider_retrieved_at.desc()).limit(1))).scalar_one_or_none()
    source_ts = None
    if snap and not snap.storage_location.startswith("s3://"):
        try:
            payload = json.loads(Path(snap.storage_location).read_bytes())
            stamps = [r.get("last_updated") for r in payload if isinstance(r, dict) and str(r.get("match_id")) in keys and r.get("last_updated")]
            source_ts = max(stamps) if stamps else None
        except (OSError, json.JSONDecodeError):
            pass
    # Re-ingesting identical bytes refreshes Bronze but rightly leaves Silver
    # untouched, so staleness compares against when this content first arrived.
    content_first_seen = (await session.execute(select(func.min(DataSnapshot.provider_retrieved_at)).where(
        DataSnapshot.sha256 == snap.sha256))).scalar_one() if snap else None
    silver_ts = max((m.updated_at for m in matches if m.updated_at), default=None)
    feature_ts = (await session.execute(select(func.max(FeatureRefreshRecord.refreshed_at)).where(
        FeatureRefreshRecord.entity_id.like(f"%@{competition_season_id}")))).scalar_one()
    comp = (await session.execute(select(Competition).join(CompetitionSeason, CompetitionSeason.competition_id == Competition.id)
                                  .where(CompetitionSeason.id == competition_season_id))).scalar_one()
    model = (await session.execute(select(ModelRegistryEntry).where(ModelRegistryEntry.domain == MATCH_DOMAIN))).scalars().first()
    inference_ts = (await session.execute(select(func.max(InferenceLog.created_at)).where(
        InferenceLog.subject_id.in_([str(i) for i in ids])))).scalar_one()
    decision_ts = (await session.execute(select(func.max(DecisionRecord.created_at)).where(
        DecisionRecord.subject_id.in_([str(i) for i in ids])))).scalar_one()
    alert_ts = (await session.execute(select(func.max(Alert.triggered_at)))).scalar_one()
    contract = (await session.execute(select(ContractFingerprint).where(ContractFingerprint.provider == matches[0].provider,
                                                                          ContractFingerprint.resource == "matches"))).scalar_one_or_none()
    last_job = (await session.execute(select(JobRun).where(JobRun.snapshot_sha256 == (snap.sha256 if snap else None))
                                      .order_by(JobRun.started_at.desc()).limit(1))).scalar_one_or_none()

    def iso(ts: Any) -> str | None:
        return ts.isoformat() if isinstance(ts, datetime) else ts

    layers = [
        {"layer": "SOURCE", "timestamp": source_ts, "basis": "provider last_updated on match records"},
        {"layer": "BRONZE", "timestamp": iso(snap.provider_retrieved_at) if snap else None,
         "content_first_seen": iso(content_first_seen), "basis": f"snapshot {snap.sha256 if snap else None}"},
        {"layer": "SILVER", "timestamp": iso(silver_ts), "basis": "max(matches.updated_at)"},
        {"layer": "FEATURE", "timestamp": iso(feature_ts), "basis": "max(ops_feature_refresh.refreshed_at)"},
        {"layer": "MODEL_READINESS", "timestamp": iso(model.registered_at) if model else None,
         "basis": f"model {model.model_id if model else None} ({model.deployment_state if model else 'UNREGISTERED'})"},
        {"layer": "INTELLIGENCE", "timestamp": iso(inference_ts), "basis": "max(ops_inference_log.created_at) for these matches"},
        {"layer": "DECISION", "timestamp": iso(decision_ts), "basis": "max(ops_decisions.created_at) for these matches"},
        {"layer": "ALERT", "timestamp": iso(alert_ts), "basis": "max(ops_alerts.triggered_at)"},
    ]
    prev = None
    for layer in layers:
        ts = layer["timestamp"]
        if ts is None:
            layer["state"] = "NOT_AVAILABLE"
            continue
        t = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        layer["age_hours"] = round((now - t).total_seconds() / 3600, 2)
        layer["state"] = "STALE" if prev is not None and t < prev and layer["layer"] in ("SILVER", "FEATURE") else "CURRENT"
        if layer["layer"] in ("SOURCE", "BRONZE", "SILVER", "FEATURE"):
            basis = layer.get("content_first_seen") or ts
            bt = datetime.fromisoformat(basis) if isinstance(basis, str) else basis
            bt = bt if bt.tzinfo else bt.replace(tzinfo=timezone.utc)
            prev = bt if prev is None or bt > prev else prev
    mode = PROVIDER_TIMING.get(matches[0].provider, {}).get("data_mode", "UNKNOWN")
    return {"competition": competition_key(comp), "competition_season_id": str(competition_season_id),
            "data_mode": mode, "is_live": False if mode == "HISTORICAL_ARCHIVE" else "UNVERIFIED",
            "contract_registered": contract.fingerprint if contract else None,
            "last_ingestion_job": {"status": last_job.status, "started_at": iso(last_job.started_at)} if last_job else None,
            "layers": layers}
