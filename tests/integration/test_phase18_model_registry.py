"""Phase 18 — one authoritative model registry, artifact-backed serving (R8, R18, R20, R21)."""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.db.models.canonical import Player
from app.db.models.operations import ModelRegistryEntry
from app.db.session import get_session
from app.main import app
from app.ml.valuation_registry import register_valuation_model
from app.phase17 import OpsRole
from app.phase17.auth import issue_user
from app.phase17.model_ops import ensure_match_model_registered
from test_phase17_live_operations import final_match, ingest_all


@pytest.fixture
async def api(p17_session):
    async def override():
        async with p17_session.test_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client
    app.dependency_overrides.clear()


async def _h(session, role=OpsRole.ADMIN):
    _, token = await issue_user(session, "Org", f"r-{uuid.uuid4().hex[:6]}@example.com", "R", role)
    await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def test_registry_states_follow_evidence(p17_session):
    match = await ensure_match_model_registered(p17_session)
    valuation = await register_valuation_model(p17_session)
    await p17_session.commit()
    assert match.deployment_state == "VALIDATED" and match.lineage_status == "VERIFIED"
    assert match.artifact_uri and len(match.artifact_sha256) == 64 and match.dataset_sha256
    assert valuation.deployment_state == "UNVERIFIED" and valuation.lineage_status == "SOURCE_UNVERIFIED"
    assert valuation.reproduction["status"] == "REPRODUCTION_BLOCKED"
    assert valuation.validation_metrics["metrics_status"] == "METRICS_UNVERIFIED"


async def test_valuation_is_refused_by_the_registry(api, p17_session):
    await register_valuation_model(p17_session)
    player = Player(name="Registry Test Player")
    p17_session.add(player)
    await p17_session.commit()
    h = await _h(p17_session, OpsRole.ANALYST)
    r = await api.get(f"/api/v1/players/{player.id}/valuation", headers=h)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "MODEL_UNVERIFIED"
    assert "estimated_value_eur" not in body and body["modality"] == "NOT_AVAILABLE"
    status = (await api.get("/api/v1/market/model-status", headers=h)).json()
    assert status["models"][0]["status"] == "UNVERIFIED"


async def test_match_prediction_route_is_registry_gated(api, p17_session, tmp_path):
    await ingest_all(p17_session, tmp_path)
    final = await final_match(p17_session)
    await ensure_match_model_registered(p17_session)
    await p17_session.commit()
    h = await _h(p17_session, OpsRole.ANALYST)
    live = (await api.get(f"/api/v1/matches/{final.id}/prediction", headers=h)).json()
    assert live["status"] == "MODEL_UNAVAILABLE"  # VALIDATED is not a serving state
    history = (await api.get(f"/api/v1/matches/{final.id}/prediction/history", headers=h)).json()
    assert [i["status"] for i in history["inferences"]] == ["MODEL_UNAVAILABLE"]  # the refusal is logged too
    ms = (await api.get("/api/v1/prediction/model-status", headers=h)).json()
    assert ms["models"][0]["model_id"] == "match_outcome_logit" and ms["status"] == "NO_SERVABLE_MODEL"


async def test_promotion_is_one_evidence_gated_step_at_a_time(api, p17_session):
    await ensure_match_model_registered(p17_session)
    await p17_session.commit()
    admin = await _h(p17_session)
    url = "/api/v1/ops/models/match_outcome_logit/promote"
    r = await api.post(url, headers=admin, json={"target_state": "SHADOW", "reason": "start shadow"})
    assert r.status_code == 409 and any("reproduction" in b for b in r.json()["detail"]["blockers"])

    row = (await p17_session.execute(select(ModelRegistryEntry).where(
        ModelRegistryEntry.model_id == "match_outcome_logit"))).scalar_one()
    row.reproduction = {"status": "REPRODUCED", "source": "committed_dataset_file"}
    await p17_session.commit()
    r = await api.post(url, headers=admin, json={"target_state": "SHADOW", "reason": "start shadow"})
    assert r.status_code == 200 and r.json()["to"] == "SHADOW"
    r = await api.post(url, headers=admin, json={"target_state": "CANARY", "reason": "too early"})
    assert r.status_code == 409 and any("live outcomes for CANARY" in b for b in r.json()["detail"]["blockers"])
    r = await api.post("/api/v1/ops/models/match_outcome_logit/demote", headers=admin)
    assert r.json()["to"] == "VALIDATED"
