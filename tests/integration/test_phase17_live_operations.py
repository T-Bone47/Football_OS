"""Phase 17 functional integration tests against a migrated PostgreSQL.

Provider payloads are real StatsBomb excerpts served by a mock transport, so
the pipeline under test is the production pipeline, offline.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.db.models.canonical import Match, MatchEvent, MatchLineup, Player
from app.db.models.operations import Alert, InferenceLog, JobRun, Notification
from app.db.session import get_session
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.main import app
from app.phase17 import OpsRole
from app.phase17.alerts import deliver, evaluate_item
from app.phase17.audit import verify_chain
from app.phase17.auth import issue_user
from app.phase17.feature_refresh import refresh_competition_season
from app.phase17.live_ingestion import LiveIngestionRunner, replay_snapshot, silver_counts
from app.phase17.match_state import match_state
from app.phase17.model_ops import (
    MODE_LIVE,
    MODE_REPLAY,
    MODE_VALIDATION,
    calibration_report,
    ensure_match_model_registered,
    infer_match,
    model_health_snapshot,
    record_outcome,
)
from app.phase17.rate_governor import RateGovernor
from app.phase17.readiness import competition_readiness, freshness_chain
from phase17_support import FINAL_ID, StatsBombFixtureTransport

pytestmark = pytest.mark.asyncio


async def ingest_all(session, tmp_path, transport=None, governor=None):
    transport = transport or StatsBombFixtureTransport()
    runner = LiveIngestionRunner(session, LocalFilesystemSnapshotStore(tmp_path / "bronze"),
                                 governor=governor or RateGovernor(), transport=transport)
    out = {"matches": await runner.run_job("statsbomb", "matches", {"competition_id": 43, "season_id": 106}),
           "lineups": await runner.run_job("statsbomb", "lineups", {"match_id": FINAL_ID}),
           "events": await runner.run_job("statsbomb", "events", {"match_id": FINAL_ID})}
    return runner, transport, out


async def final_match(session) -> Match:
    return (await session.execute(select(Match).where(Match.provider_fixture_id == str(FINAL_ID)))).scalar_one()


async def test_real_payloads_flow_bronze_to_silver_with_provenance(p17_session, tmp_path):
    _, transport, out = await ingest_all(p17_session, tmp_path)
    assert {k: v.status for k, v in out.items()} == {"matches": "SUCCESS", "lineups": "SUCCESS", "events": "SUCCESS"}
    m = out["matches"]
    raw = (tmp_path / "bronze" / "statsbomb" / "matches" / f"{m.snapshot_sha256}.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m.snapshot_sha256
    counts = await silver_counts(p17_session)
    assert counts["matches"] == 13 and counts["match_lineups"] > 30
    final = await final_match(p17_session)
    goals = (await p17_session.execute(select(func.count()).select_from(MatchEvent).where(
        MatchEvent.match_id == final.id, MatchEvent.event_type == "GOAL"))).scalar_one()
    assert (final.home_score, final.away_score, goals) == (3, 3, 6)
    assert m.silver_quality["checks"]
    assert {c["name"]: c for c in m.silver_quality["checks"]}["referential_integrity"]["status"] == "PASS"
    job = (await p17_session.execute(select(JobRun).where(JobRun.id == uuid.UUID(m.job_id)))).scalar_one()
    assert job.status == "SUCCESS" and job.records == 13 and job.snapshot_sha256 == m.snapshot_sha256


async def test_reingestion_is_idempotent(p17_session, tmp_path):
    runner, _, first = await ingest_all(p17_session, tmp_path)
    before = await silver_counts(p17_session)
    again = await runner.run_job("statsbomb", "matches", {"competition_id": 43, "season_id": 106})
    again_l = await runner.run_job("statsbomb", "lineups", {"match_id": FINAL_ID})
    assert again.snapshot_sha256 == first["matches"].snapshot_sha256
    assert again_l.snapshot_sha256 == first["lineups"].snapshot_sha256
    assert await silver_counts(p17_session) == before


async def test_feature_refresh_skips_unchanged_dependencies(p17_session, tmp_path):
    await ingest_all(p17_session, tmp_path)
    cs = (await final_match(p17_session)).competition_season_id
    first = await refresh_competition_season(p17_session, cs)
    second = await refresh_competition_season(p17_session, cs)
    assert all(o.status.value == "REFRESHED" and o.computed for o in first)
    assert all(o.status.value == "UNCHANGED" and not o.computed for o in second)


async def _validated_model(session, tmp_path):
    await ingest_all(session, tmp_path)
    final = await final_match(session)
    await refresh_competition_season(session, final.competition_season_id)
    model = await ensure_match_model_registered(session)
    await session.commit()
    return model, final


async def test_inference_gates_refuse_instead_of_guessing(p17_session, tmp_path):
    model, final = await _validated_model(p17_session, tmp_path)
    # Registered but not validated for any competition: nothing servable in LIVE.
    live = await infer_match(p17_session, final.id, mode=MODE_LIVE)
    assert live.status == "MODEL_UNAVAILABLE"
    # Validation mode may use a REGISTERED model; the final has 6+ prior matches per side.
    val = await infer_match(p17_session, final.id, as_of=final.date - timedelta(seconds=1), mode=MODE_VALIDATION)
    assert val.status == "SERVED"
    assert abs(sum(val.output[k] for k in ("home_win", "draw", "away_win")) - 1.0) < 1e-6
    assert max(datetime.fromisoformat(val.evidence["history_max_date"]), final.date) == final.date
    # Pre-match cutoff at kickoff is a temporal violation.
    v2 = await infer_match(p17_session, final.id, as_of=final.date, mode=MODE_VALIDATION)
    assert v2.status == "TEMPORAL_VIOLATION"
    # First Argentina match: no prior history.
    first = (await p17_session.execute(select(Match).order_by(Match.date.asc()))).scalars().first()
    v3 = await infer_match(p17_session, first.id, as_of=first.date - timedelta(seconds=1), mode=MODE_VALIDATION)
    assert v3.status == "INSUFFICIENT_DATA"
    # SHADOW with support for the competition, then LIVE on archive data:
    model.deployment_state = "SHADOW"
    model.supported_competitions = [val.competition]
    await p17_session.commit()
    live2 = await infer_match(p17_session, final.id, mode=MODE_LIVE)
    assert live2.status == "TEMPORAL_VIOLATION"  # kickoff is in 2022
    backdated = await infer_match(p17_session, final.id, as_of=final.date - timedelta(hours=2), mode=MODE_LIVE)
    assert backdated.status == "TEMPORAL_VIOLATION" and "backdated" in backdated.reasons[0]
    replay = await infer_match(p17_session, final.id, as_of=final.date - timedelta(hours=2), mode=MODE_REPLAY)
    assert replay.status == "SERVED"
    await p17_session.commit()
    logged = (await p17_session.execute(select(func.count()).select_from(InferenceLog))).scalar_one()
    assert logged == 7  # every request, served or refused, is logged


async def test_outcome_is_classified_by_timestamps_and_calibration_is_gated(p17_session, tmp_path):
    _, final = await _validated_model(p17_session, tmp_path)
    inf = await infer_match(p17_session, final.id, as_of=final.date - timedelta(seconds=1), mode=MODE_VALIDATION)
    await p17_session.commit()
    outcome = await record_outcome(p17_session, inf)
    assert outcome.observation_mode == MODE_REPLAY  # predicted in 2026 for a 2022 match
    assert outcome.realized == {"result": "DRAW", "home_score": 3, "away_score": 3}
    assert outcome.outcome_snapshot_sha256
    live = await calibration_report(p17_session, MODE_LIVE)
    assert live["status"] == "NOT_ENOUGH_LIVE_OUTCOMES" and live["n"] == 0
    health = await model_health_snapshot(p17_session)
    assert health["inference_volume"] == 1 and health["live_inference_volume"] == 0
    assert health["live_calibration"]["status"] == "NOT_ENOUGH_LIVE_OUTCOMES"


async def test_match_state_and_freshness_never_claim_live(p17_session, tmp_path):
    await ingest_all(p17_session, tmp_path)
    final = await final_match(p17_session)
    state = await match_state(p17_session, final.id)
    assert state["state"] == "FINAL" and state["real_time"] is False
    assert state["data_mode"] == "HISTORICAL_ARCHIVE" and state["source_timestamp"]
    assert state["retrieval_timestamp"] and state["data_age_seconds"] is not None
    chain = await freshness_chain(p17_session, final.competition_season_id)
    assert chain["is_live"] is False
    assert [layer["layer"] for layer in chain["layers"]][:3] == ["SOURCE", "BRONZE", "SILVER"]
    assert all(layer["state"] != "STALE" for layer in chain["layers"][:3])


async def test_competition_readiness_does_not_inherit(p17_session, tmp_path):
    model, final = await _validated_model(p17_session, tmp_path)
    rows = await competition_readiness(p17_session)
    assert len(rows) == 1
    row = rows[0]
    assert row["production_status"] == "INSUFFICIENT_DATA"  # 13 matches < 30
    assert row["calibration"]["live"] == "NOT_ENOUGH_LIVE_OUTCOMES"
    assert row["transfer_data"]["state"] == "NOT_AVAILABLE"
    assert row["provider_status"] == {"statsbomb": "UNKNOWN"}  # no probe recorded in this database


async def test_snapshot_replay_is_deterministic(p17_session, tmp_path):
    _, _, out = await ingest_all(p17_session, tmp_path)

    async def silver_digest():
        rows = (await p17_session.execute(select(Match.provider_fixture_id, Match.date, Match.home_score, Match.away_score,
                                                 Match.status).order_by(Match.provider_fixture_id))).all()
        lu = (await p17_session.execute(select(func.count()).select_from(MatchLineup))).scalar_one()
        return hashlib.sha256(json.dumps([list(map(str, r)) for r in rows] + [lu]).encode()).hexdigest()

    d1 = await silver_digest()
    snaps = [uuid.UUID(out[k].snapshot_id) for k in ("matches", "lineups", "events")]
    for sid in snaps:
        await replay_snapshot(p17_session, sid)
    assert await silver_digest() == d1


# ------------------------------------------------------------------ watchlists / alerts / notifications
class _Hook(BaseHTTPRequestHandler):
    received: list[bytes] = []

    def do_POST(self):  # noqa: N802
        _Hook.received.append(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def webhook_server():
    _Hook.received = []
    server = HTTPServer(("127.0.0.1", 0), _Hook)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/hook"
    server.shutdown()


async def _watch_item(session, metric="appearances", threshold=3, window=3):
    from app.db.models.operations import Project, Watchlist, WatchlistItem

    admin, _ = await issue_user(session, "Org A", f"a-{uuid.uuid4().hex[:6]}@example.test", "A", OpsRole.ANALYST)
    project = Project(organization_id=admin.organization_id, owner_user_id=admin.id, name="p", kind="WATCH",
                      description="", visibility="PRIVATE", parameters={})
    session.add(project)
    await session.flush()
    wl = Watchlist(project_id=project.id, owner_user_id=admin.id, name="w")
    session.add(wl)
    await session.flush()
    messi = (await session.execute(select(Player).where(Player.name.like("Lionel%Messi%")))).scalar_one()
    item = WatchlistItem(watchlist_id=wl.id, entity_type="PLAYER", entity_id=str(messi.id), entity_name=messi.name,
                         condition={"metric": metric, "operator": ">=", "threshold": threshold, "window_matches": window},
                         last_state={})
    session.add(item)
    await session.flush()
    return admin, item


async def test_watchlist_alert_requires_evidence_dedups_and_delivers(p17_session, tmp_path, webhook_server):
    # Lineups exist only for the final, so a 1-match window is the honest scope.
    await ingest_all(p17_session, tmp_path)
    admin, item = await _watch_item(p17_session, "goals", threshold=2, window=1)
    settings = Settings(_env_file=None, notification_webhook_url=webhook_server)
    r1 = await evaluate_item(p17_session, item, settings, admin.organization_id)
    assert r1["condition_met"] is True and r1["value"] == 2  # Messi scored twice in the final (shootout excluded)
    assert r1["evidence"][0]["provider_fixture_id"] == str(FINAL_ID) and r1["evidence"][0]["lineup_snapshot_sha256"]
    alert = await p17_session.get(Alert, uuid.UUID(r1["alert"]["id"]))
    assert alert.state == "DELIVERED" and alert.evidence and alert.dedup_key
    r2 = await evaluate_item(p17_session, item, settings, admin.organization_id)
    assert r2["alert"] is None  # still met: no repeat alert
    await deliver(p17_session, alert, settings)  # explicit redelivery attempt
    await p17_session.commit()
    notes = (await p17_session.execute(select(Notification).where(Notification.alert_id == alert.id))).scalars().all()
    assert sorted((n.channel, n.state, n.attempts) for n in notes) == [("IN_APP", "SENT", 1), ("WEBHOOK", "SENT", 1)]
    assert len(_Hook.received) == 1
    assert (await verify_chain(p17_session))["valid"]


async def test_watchlist_with_missing_events_is_insufficient_not_zero(p17_session, tmp_path):
    transport = StatsBombFixtureTransport()
    runner = LiveIngestionRunner(p17_session, LocalFilesystemSnapshotStore(tmp_path / "b"), governor=RateGovernor(),
                                 transport=transport)
    await runner.run_job("statsbomb", "matches", {"competition_id": 43, "season_id": 106})
    await runner.run_job("statsbomb", "lineups", {"match_id": FINAL_ID})
    admin, item = await _watch_item(p17_session, "goals", threshold=1, window=1)
    r = await evaluate_item(p17_session, item, Settings(_env_file=None), admin.organization_id)
    assert r["condition_met"] is None and r["data_sufficiency"] == "EVENTS_NOT_INGESTED"
    assert (await p17_session.execute(select(func.count()).select_from(Alert))).scalar_one() == 0


async def test_failed_webhook_is_never_reported_sent(p17_session, tmp_path):
    await ingest_all(p17_session, tmp_path)
    admin, item = await _watch_item(p17_session, "appearances", threshold=1, window=1)
    settings = Settings(_env_file=None, notification_webhook_url="http://127.0.0.1:9/closed")
    r = await evaluate_item(p17_session, item, settings, admin.organization_id)
    alert = await p17_session.get(Alert, uuid.UUID(r["alert"]["id"]))
    hook = (await p17_session.execute(select(Notification).where(Notification.alert_id == alert.id,
                                                                  Notification.channel == "WEBHOOK"))).scalar_one()
    assert hook.state == "FAILED" and hook.attempts == 3 and hook.last_error
    await deliver(p17_session, alert, settings)
    assert hook.attempts == 3  # bounded: no retry storm


# ------------------------------------------------------------------ API workflow
@pytest.fixture
async def api(p17_session):
    async def override():
        async with p17_session.test_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client
    app.dependency_overrides.clear()


def H(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_api_decision_workflow_with_provenance(p17_session, tmp_path, api):
    _, final = await _validated_model(p17_session, tmp_path)
    inf = await infer_match(p17_session, final.id, as_of=final.date - timedelta(seconds=1), mode=MODE_VALIDATION)
    analyst, token = await issue_user(p17_session, "Org A", "analyst@example.test", "Analyst", OpsRole.ANALYST)
    await p17_session.commit()

    me = await api.get("/api/v1/ops/me", headers=H(token))
    assert me.status_code == 200 and me.json()["role"] == "ANALYST"
    proj = await api.post("/api/v1/ops/projects", headers=H(token), json={"name": "WC final review"})
    assert proj.status_code == 201
    pid = proj.json()["id"]
    body = {"title": "Final assessment", "decision": "MONITOR", "subject_type": "MATCH", "subject_id": str(final.id),
            "rationale": "Model output reviewed against data cutoff.", "inference_ids": [str(inf.id)]}
    d1 = await api.post(f"/api/v1/ops/projects/{pid}/decisions", headers={**H(token), "Idempotency-Key": "k-1"}, json=body)
    d2 = await api.post(f"/api/v1/ops/projects/{pid}/decisions", headers={**H(token), "Idempotency-Key": "k-1"}, json=body)
    assert d1.status_code == d2.status_code == 201
    assert d1.json()["id"] == d2.json()["id"] and d2.json()["created"] is False  # replay returns the original
    prov = (await api.get(f"/api/v1/ops/decisions/{d1.json()['id']}/provenance", headers=H(token))).json()
    node = prov["evidence_graph"]["nodes"][0]
    assert prov["integrity_verified"] is True and prov["evidence_graph"]["complete"] is True
    assert node["model"]["model_id"] == "calibrated_multinomial_logit_v1"
    assert node["subject_match"]["snapshot"]["provider"]["name"] == "statsbomb"
    assert node["history"]["snapshots"][0]["sha256"]
    assert prov["staleness"]["state"] == "CURRENT"


async def test_copilot_answers_are_tool_grounded(p17_session, tmp_path, api):
    await ingest_all(p17_session, tmp_path)
    _, token = await issue_user(p17_session, "Org A", "viewer@example.test", "Viewer", OpsRole.VIEWER)
    await p17_session.commit()
    for q in ("What data was ingested recently?", "Which providers are unavailable?",
              "Which competitions are production-ready?", "Which model is currently active?", "Show me the evidence."):
        r = (await api.post("/api/v1/ops/copilot", headers=H(token), json={"query": q})).json()
        assert r["status"] in ("GROUNDED", "UNVERIFIED"), (q, r)
        assert r["tool_calls"] and all(c["status"] == "OK" and c["result_digest"] for c in r["tool_calls"])
    providers = (await api.post("/api/v1/ops/copilot", headers=H(token), json={"query": "Which providers are unavailable?"})).json()
    assert providers["status"] == "UNVERIFIED" and providers["answer"].startswith("UNVERIFIED")  # no probe recorded here
    ingested = (await api.post("/api/v1/ops/copilot", headers=H(token), json={"query": "What data was ingested recently?"})).json()
    assert ingested["status"] == "GROUNDED" and "3 ingestion job(s)" in ingested["answer"]
    unknown = (await api.post("/api/v1/ops/copilot", headers=H(token), json={"query": "Who will win the league?"})).json()
    assert unknown["status"] == "UNVERIFIED" and not unknown["tool_calls"]
