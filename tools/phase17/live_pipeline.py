"""Phase 17 live data pipeline evidence run.

Executes, against real providers and a freshly migrated PostgreSQL database:
probes -> competitions index -> pilot competition ingestion (matches,
lineups, a sample of events) -> idempotency re-runs -> feature refresh (x2)
-> model registration and walk-forward validation per competition ->
LIVE-mode inference attempts -> calibration / drift / health -> readiness,
capability matrix, freshness chain, match states -> provenance audit.

Usage:  python tools/phase17/live_pipeline.py [--events-per-comp N]
Writes: docs/evidence/phase17/live_pipeline.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import uuid
from collections import Counter
from datetime import timedelta
from pathlib import Path

from common import ROOT, Timer, now, recreate_database, write_evidence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models.canonical import Match, MatchEvent, MatchLineup
from app.db.models.operations import InferenceLog, JobRun
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.phase17 import ScheduleClass
from app.phase17.feature_refresh import refresh_competition_season
from app.phase17.live_ingestion import LiveIngestionRunner, silver_counts
from app.phase17.match_state import match_state
from app.phase17.model_ops import (
    MODE_LIVE,
    MODE_REPLAY,
    MODE_VALIDATION,
    calibration_report,
    competition_key,
    drift_report,
    ensure_match_model_registered,
    historical_backtest,
    infer_match,
    match_context,
    model_health_snapshot,
    validate_competition_support,
)
from app.phase17.provider_probe import run_probes
from app.phase17.rate_governor import get_rate_governor
from app.phase17.readiness import capability_matrix, competition_readiness, freshness_chain
from app.phase17.workspace import snapshot_lineage

DB = "fios_p17_live"
PILOTS = [
    {"name": "Premier League 2015/2016", "competition_id": 2, "season_id": 27},
    {"name": "FIFA World Cup 2022", "competition_id": 43, "season_id": 106},
    {"name": "1. Bundesliga 2023/2024", "competition_id": 9, "season_id": 281},
]


async def main(events_per_comp: int) -> None:
    timer = Timer()
    evidence: dict = {"database": DB, "bronze_root": "data/bronze", "pilots": {}, "started_at": now()}
    url = recreate_database(DB)
    # Credentials come from the gitignored .env (never printed or stored).
    settings = Settings(_env_file=ROOT / ".env", database_url=url, environment="development")
    evidence["credentials_configured"] = {"api_football_key": bool(settings.api_football_key),
                                          "football_data_token": bool(settings.football_data_token)}
    engine = create_async_engine(url, pool_size=5)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    store = LocalFilesystemSnapshotStore(ROOT / "data" / "bronze")
    governor = get_rate_governor()

    async with Session() as s:
        with timer.stage("provider_probes"):
            evidence["probes"] = [r.to_dict() for r in await run_probes(s, settings)]

        runner = LiveIngestionRunner(s, store, governor=governor)
        with timer.stage("competitions_index"):
            idx = await runner.run_job("statsbomb", "competitions", {}, "statsbomb_competitions_index", ScheduleClass.WEEKLY)
            evidence["competitions_index"] = {k: idx.to_dict()[k] for k in ("status", "snapshot_sha256", "records", "contract", "payload_quality")}

        for pilot in PILOTS:
            p = evidence["pilots"].setdefault(pilot["name"], {})
            params = {"competition_id": pilot["competition_id"], "season_id": pilot["season_id"]}
            with timer.stage(f"matches:{pilot['name']}"):
                res = await runner.run_job("statsbomb", "matches", params, "statsbomb_season_matches", ScheduleClass.SEASONAL)
            p["matches_job"] = {k: res.to_dict()[k] for k in ("status", "snapshot_sha256", "records", "errors", "silver",
                                                               "silver_quality", "payload_quality", "contract", "latency_ms")}
            if res.status != "SUCCESS":
                continue
            payload = json.loads(Path(res.storage_location).read_bytes())
            match_ids = [m["match_id"] for m in sorted(payload, key=lambda m: (m["match_date"], m["match_id"]))]
            with timer.stage(f"lineups:{pilot['name']}"):
                statuses = Counter()
                for mid in match_ids:
                    while not governor.headroom("statsbomb"):
                        await asyncio.sleep(max(1.0, governor.seconds_until_headroom("statsbomb")))
                    r = await runner.run_job("statsbomb", "lineups", {"match_id": mid}, "statsbomb_match_lineups")
                    statuses[r.status] += 1
                    if r.status != "SUCCESS":
                        p.setdefault("lineup_failures", []).append({"match_id": mid, "status": r.status, "errors": r.errors[:2]})
            p["lineup_jobs"] = dict(statuses)
            sample = random.Random(17).sample(match_ids, min(events_per_comp, len(match_ids)))
            if pilot["competition_id"] == 43 and 3869685 not in sample:
                sample[0] = 3869685  # include the 2022 final (penalty shootout)
            with timer.stage(f"events:{pilot['name']}"):
                ev_status = Counter()
                for mid in sample:
                    while not governor.headroom("statsbomb"):
                        await asyncio.sleep(max(1.0, governor.seconds_until_headroom("statsbomb")))
                    r = await runner.run_job("statsbomb", "events", {"match_id": mid}, "statsbomb_match_events")
                    ev_status[r.status] += 1
                    p.setdefault("event_jobs_detail", []).append({"match_id": mid, "status": r.status, "records": r.records,
                                                                  "silver_delta": (r.silver or {}).get("delta"),
                                                                  "payload_quality": (r.payload_quality or {}).get("overall")})
            p["event_jobs"] = dict(ev_status)
            first = (await s.execute(select(Match).where(Match.provider == "statsbomb",
                                                         Match.provider_fixture_id == str(match_ids[0])))).scalar_one()
            p["competition_season_id"] = str(first.competition_season_id)

        evidence["silver_counts_after_ingestion"] = await silver_counts(s)

        # --- Idempotency: identical re-ingestion must not change Silver.
        with timer.stage("idempotency"):
            idem = []
            for pilot in PILOTS:
                before = await silver_counts(s)
                r = await runner.run_job("statsbomb", "matches", {"competition_id": pilot["competition_id"],
                                                                  "season_id": pilot["season_id"]})
                after = await silver_counts(s)
                idem.append({"scope": pilot["name"], "resource": "matches", "status": r.status,
                             "sha256": r.snapshot_sha256,
                             "first_sha256": evidence["pilots"][pilot["name"]]["matches_job"]["snapshot_sha256"],
                             "silver_delta": {k: after[k] - before[k] for k in after}})
            for resource, mid in (("lineups", 3869685), ("events", 3869685)):
                before = await silver_counts(s)
                r = await runner.run_job("statsbomb", resource, {"match_id": mid})
                after = await silver_counts(s)
                idem.append({"scope": f"match {mid}", "resource": resource, "status": r.status, "sha256": r.snapshot_sha256,
                             "silver_delta": {k: after[k] - before[k] for k in after}})
            for i in idem:
                i["idempotent"] = all(v == 0 for v in i["silver_delta"].values()) and \
                    (i.get("first_sha256") in (None, i["sha256"]))
            evidence["idempotency"] = idem

        # --- Feature refresh: second pass must be all UNCHANGED.
        with timer.stage("feature_refresh"):
            fr = {}
            for pilot in PILOTS:
                cs = uuid.UUID(evidence["pilots"][pilot["name"]]["competition_season_id"])
                first = await refresh_competition_season(s, cs)
                second = await refresh_competition_season(s, cs)
                fr[pilot["name"]] = {"first_pass": dict(Counter(o.status.value for o in first)),
                                     "second_pass": dict(Counter(o.status.value for o in second)),
                                     "recomputed_on_second_pass": sum(1 for o in second if o.computed),
                                     "example": first[0].to_dict() if first else None}
            evidence["feature_refresh"] = fr

        # --- Model registration + walk-forward validation per competition.
        with timer.stage("model_validation"):
            model = await ensure_match_model_registered(s)
            await s.commit()
            mv = {}
            for pilot in PILOTS:
                cs = uuid.UUID(evidence["pilots"][pilot["name"]]["competition_season_id"])
                bt = await historical_backtest(s, cs)
                m = (await s.execute(select(Match).where(Match.competition_season_id == cs))).scalars().first()
                ctx = await match_context(s, m.id)
                comp = competition_key(ctx[1])
                verdict = await validate_competition_support(s, comp)
                mv[pilot["name"]] = {"backtest": bt, "competition_key": comp, "verdict": verdict}
            await s.refresh(model)
            evidence["model_validation"] = mv
            evidence["model_registry"] = {"model_id": model.model_id, "model_version": model.model_version,
                                          "deployment_state": model.deployment_state,
                                          "supported_competitions": model.supported_competitions,
                                          "dataset_version": model.dataset_version,
                                          "artifact_sha256": model.artifact_sha256}

        # --- LIVE-mode inference: what the system says when asked for a live
        # pre-match prediction today on archive data.
        with timer.stage("live_inference_attempts"):
            attempts = []
            for pilot in PILOTS:
                cs = uuid.UUID(evidence["pilots"][pilot["name"]]["competition_season_id"])
                ms = (await s.execute(select(Match).where(Match.competition_season_id == cs).order_by(Match.date.desc()).limit(2))).scalars().all()
                for m in ms:
                    inf = await infer_match(s, m.id, mode=MODE_LIVE)
                    attempts.append({"competition": pilot["name"], "match": m.provider_fixture_id, "status": inf.status,
                                     "reasons": inf.reasons})
                    # A backdated LIVE request must be refused, not served as "live".
                    inf2 = await infer_match(s, m.id, as_of=m.date - timedelta(hours=2), mode=MODE_LIVE)
                    attempts.append({"competition": pilot["name"], "match": m.provider_fixture_id,
                                     "as_of": "kickoff - 2h (backdated LIVE)", "status": inf2.status, "reasons": inf2.reasons})
                    # The same cutoff as an explicit HISTORICAL_REPLAY request.
                    inf3 = await infer_match(s, m.id, as_of=m.date - timedelta(hours=2), mode=MODE_REPLAY)
                    attempts.append({"competition": pilot["name"], "match": m.provider_fixture_id,
                                     "as_of": "kickoff - 2h (HISTORICAL_REPLAY)", "status": inf3.status,
                                     "reasons": inf3.reasons, "output": inf3.output})
            await s.commit()
            evidence["live_inference_attempts"] = attempts

        with timer.stage("monitoring"):
            evidence["calibration"] = {"live": await calibration_report(s, MODE_LIVE),
                                       "historical_replay_validation": await calibration_report(s, MODE_REPLAY, evidence_mode=MODE_VALIDATION)}
            evidence["drift"] = {"live": await drift_report(s, MODE_LIVE),
                                 "historical_validation": await drift_report(s, MODE_VALIDATION)}
            evidence["model_health"] = await model_health_snapshot(s)

        with timer.stage("readiness_and_freshness"):
            evidence["competition_readiness"] = await competition_readiness(s)
            cap = await capability_matrix(s)
            evidence["capability_matrix"] = {**cap, "statsbomb_competition_seasons_total": len(cap["statsbomb_competition_seasons"]),
                                             "statsbomb_competition_seasons_verified": [c for c in cap["statsbomb_competition_seasons"]
                                                                                        if c["matches"] == "LIVE_AVAILABLE"],
                                             "statsbomb_competition_seasons": cap["statsbomb_competition_seasons"]}
            evidence["freshness"] = {pilot["name"]: await freshness_chain(s, uuid.UUID(evidence["pilots"][pilot["name"]]["competition_season_id"]))
                                     for pilot in PILOTS}
            final = (await s.execute(select(Match).where(Match.provider_fixture_id == "3869685"))).scalar_one()
            evidence["match_state_examples"] = [await match_state(s, final.id)]

        # --- Provenance audit: Silver row -> snapshot -> recomputed SHA-256.
        with timer.stage("provenance_audit"):
            rng = random.Random(1717)
            matches = (await s.execute(select(Match))).scalars().all()
            lineups = (await s.execute(select(MatchLineup).limit(5000))).scalars().all()
            events = (await s.execute(select(MatchEvent))).scalars().all()
            sample = [("match", m.id, m.snapshot_id) for m in rng.sample(matches, min(40, len(matches)))] + \
                     [("lineup", l.id, l.snapshot_id) for l in rng.sample(lineups, min(40, len(lineups)))] + \
                     [("event", e.id, e.snapshot_id) for e in rng.sample(events, min(20, len(events)))]
            audit = []
            for kind, rid, sid in sample:
                lin = await snapshot_lineage(s, sid)
                ok = False
                if lin and lin.get("storage_location"):
                    actual = hashlib.sha256(Path(lin["storage_location"]).read_bytes()).hexdigest()
                    ok = actual == lin["sha256"]
                audit.append({"kind": kind, "record_id": str(rid), "lineage_complete": bool(lin) and lin.get("status") != "ORPHAN",
                              "sha256_recomputed_matches": ok, "provider": (lin or {}).get("provider", {}).get("name"),
                              "endpoint": (lin or {}).get("ingestion_run", {}).get("endpoint")})
            orphan_counts = {
                "matches_without_snapshot": (await s.execute(select(func.count()).select_from(Match).where(Match.snapshot_id.is_(None)))).scalar_one(),
                "lineups_without_snapshot": (await s.execute(select(func.count()).select_from(MatchLineup).where(MatchLineup.snapshot_id.is_(None)))).scalar_one(),
                "events_without_snapshot": (await s.execute(select(func.count()).select_from(MatchEvent).where(MatchEvent.snapshot_id.is_(None)))).scalar_one(),
            }
            evidence["provenance_audit"] = {"sampled": len(audit), "all_complete": all(a["lineage_complete"] for a in audit),
                                            "all_hashes_match": all(a["sha256_recomputed_matches"] for a in audit),
                                            "orphans": orphan_counts, "samples": audit[:10]}

        jobs = (await s.execute(select(JobRun.status, func.count()).group_by(JobRun.status))).all()
        evidence["job_status_counts"] = {k: v for k, v in jobs}
        evidence["inference_status_counts"] = {k: v for k, v in (await s.execute(
            select(InferenceLog.status, func.count()).group_by(InferenceLog.status))).all()}
        evidence["rate_governance"] = governor.report()
        evidence["silver_counts_final"] = await silver_counts(s)

    await engine.dispose()
    evidence["stage_seconds"] = timer.stages
    evidence["finished_at"] = now()
    print("wrote", write_evidence("live_pipeline", evidence))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--events-per-comp", type=int, default=8)
    asyncio.run(main(ap.parse_args().events_per_comp))
