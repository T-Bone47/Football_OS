"""Phase 18 — the legacy ingestion trigger performs real ingestion (R4).

The trigger used to accept a caller-supplied payload and report a full
pipeline cycle without contacting any provider. It now runs the same
pipeline as /api/v1/ops/ingestion/jobs. The provider transport here serves
committed StatsBomb excerpts (TEST FIXTURE, real provider bytes); an
unreachable provider must produce FAILED and write nothing.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

import app.api.routes_phase10 as routes_phase10
from app.db.models.operations import JobRun
from app.db.models.provenance import DataSnapshot
from app.db.session import get_session
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.main import app
from app.phase17 import OpsRole
from app.phase17.auth import issue_user
from app.phase17.live_ingestion import LiveIngestionRunner
from app.phase17.rate_governor import RateGovernor
from phase17_support import StatsBombFixtureTransport


class _Unreachable(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise httpx.ConnectError("provider unreachable (test)", request=request)


@pytest.fixture
async def api(p17_session, tmp_path, monkeypatch):
    state = {"transport": StatsBombFixtureTransport()}

    class _Runner(LiveIngestionRunner):
        def __init__(self, session, _store, **kw):
            super().__init__(session, LocalFilesystemSnapshotStore(tmp_path / "bronze"), governor=RateGovernor(),
                             transport=state["transport"])

    monkeypatch.setattr(routes_phase10, "LiveIngestionRunner", _Runner)

    async def override():
        async with p17_session.test_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        client.state = state
        yield client
    app.dependency_overrides.clear()


async def _token(session, role=OpsRole.DATA_ENGINEER) -> dict[str, str]:
    _, token = await issue_user(session, "Org", f"{role.value.lower()}@example.test", "U", role)
    await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def test_trigger_requires_authentication_and_permission(api, p17_session):
    body = {"provider": "statsbomb", "resource": "matches", "params": {"competition_id": 43, "season_id": 106}}
    assert (await api.post("/api/phase10/operations/ingestion/trigger", json=body)).status_code == 401
    viewer = await _token(p17_session, OpsRole.VIEWER)
    assert (await api.post("/api/phase10/operations/ingestion/trigger", json=body, headers=viewer)).status_code == 403


async def test_trigger_rejects_a_caller_supplied_payload(api, p17_session):
    h = await _token(p17_session)
    r = await api.post("/api/phase10/operations/ingestion/trigger", headers=h, json={
        "provider": "api-football", "resource": "fixtures",
        "payload": {"response": [{"fixture": {"id": 1}, "teams": {"home": {"name": "Arsenal"}}}]}})
    assert r.status_code == 422
    assert (await p17_session.execute(select(func.count()).select_from(DataSnapshot))).scalar() == 0


async def test_trigger_ingests_real_provider_bytes(api, p17_session):
    h = await _token(p17_session)
    r = await api.post("/api/phase10/operations/ingestion/trigger", headers=h, json={
        "provider": "statsbomb", "resource": "matches", "params": {"competition_id": 43, "season_id": 106}})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "SUCCESS"
    assert len(body["snapshot_sha256"]) == 64
    assert "/matches/43/106.json" in api.state["transport"].requests  # the provider was actually called
    runs = (await api.get("/api/phase10/operations/ingestion/runs", headers=h)).json()
    assert runs[0]["status"] == "SUCCESS" and runs[0]["snapshot_sha256"] == body["snapshot_sha256"]


async def test_unreachable_provider_fails_and_writes_nothing(api, p17_session):
    api.state["transport"] = _Unreachable()
    h = await _token(p17_session)
    r = await api.post("/api/phase10/operations/ingestion/trigger", headers=h, json={
        "provider": "statsbomb", "resource": "matches", "params": {"competition_id": 43, "season_id": 106}})
    body = r.json()
    assert body["status"] == "FAILED" and body["snapshot_sha256"] is None
    assert (await p17_session.execute(select(func.count()).select_from(DataSnapshot))).scalar() == 0
    job = (await p17_session.execute(select(JobRun))).scalars().one()
    assert job.status == "FAILED" and job.errors


async def test_phase10_and_phase11_readiness_are_the_authoritative_engine(api, p17_session):
    h = await _token(p17_session)
    a = (await api.get("/api/phase10/operations/competition-readiness", headers=h)).json()
    b = (await api.get("/api/phase11/competitions/coverage", headers=h)).json()
    c = (await api.get("/api/v1/ops/competitions/readiness", headers=h)).json()["competitions"]
    assert a == b == c
    assert (await api.post("/api/phase11/competitions/EPL/advance", json={})).status_code == 410
