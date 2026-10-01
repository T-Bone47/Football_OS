"""
Unit tests for Phase 7 Decision Intelligence API routes and contracts.
Uses dependency overrides to test route handling, Pydantic serialization,
and contract adherence without requiring a live external PostgreSQL instance.
"""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app
from app.decisions.schemas import (
    CandidateComparisonResponse,
    DecisionAssessment,
    EvidenceGraphResponse,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    RecruitmentTargetResponse,
    ReplacementDecisionResponse,
    TransferScenarioDecisionResponse,
)


@pytest.mark.asyncio
async def test_get_recruitment_contract_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/decisions/recruitment?target_position=CM&limit=3")
        assert res.status_code == 200
        data = res.json()
        assert "decision" in data
        assert "top_recommendations" in data
        assert "excluded_summaries" in data
        assert data["decision"]["decision_type"] == "RECRUITMENT"
        assert "confidence" in data["decision"]
        assert "confidence_tier" in data["decision"]["confidence"]
        assert "data_confidence" in data["decision"]["confidence"]
        assert "model_confidence" in data["decision"]["confidence"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_recruitment_analyze_contract_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "target_position": "CB",
            "tactical_context_id": "433_cb_ball_playing_cover",
            "budget_eur": 45000000.0,
            "min_age": 20,
            "max_age": 29,
            "min_minutes": 450,
            "risk_tolerance": "HIGH",
            "limit": 5,
        }
        res = await client.post("/api/v1/decisions/recruitment/analyze", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["decision"]["decision_type"] == "RECRUITMENT"
        assert isinstance(data["top_recommendations"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_replacement_contract_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pid = str(uuid.uuid4())
        payload = {
            "player_id_to_replace": pid,
            "target_role": "Playmaker",
            "min_similarity": 0.55,
            "budget_eur": 40000000.0,
            "limit": 4,
        }
        res = await client.post("/api/v1/decisions/replacement", json=payload)
        # Without database records, attempting to replace a non-existent player correctly returns 404
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_transfer_scenario_contract_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "club_id": str(uuid.uuid4()),
            "roster_changes": [
                {"player_id": str(uuid.uuid4()), "direction": "IN", "fee_eur": 35000000.0},
                {"player_id": str(uuid.uuid4()), "direction": "OUT", "fee_eur": 28000000.0},
            ],
            "formation": "4-3-3",
            "budget_eur": 75000000.0,
        }
        res = await client.post("/api/v1/decisions/transfer-scenario", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["decision"]["decision_type"] == "TRANSFER_SCENARIO"
        assert "financial_impact" in data
        assert "squad_impact_summary" in data
        assert data["financial_impact"]["total_expenditure_eur"] == 35000000.0
        assert data["financial_impact"]["net_transfer_spend_eur"] == 7000000.0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_compare_contract_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c1, c2 = str(uuid.uuid4()), str(uuid.uuid4())
        payload = {"candidate_ids": [c1, c2]}
        res = await client.post("/api/v1/decisions/compare", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "candidates" in data
        assert "trade_off_analysis" in data
        assert "dimension_leaders" in data
        assert isinstance(data["candidates"], list)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_copilot_decision_orchestrator_mocked():
    async def fake_get_session():
        yield None

    app.dependency_overrides[get_session] = fake_get_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "query": "Find me a replacement for our midfielder under €40M",
            "context_players": [{"id": str(uuid.uuid4()), "name": "Test Midfielder", "primary_position": "MF"}],
        }
        res = await client.post("/api/copilot/query", json=payload)
        assert res.status_code == 200
        text = res.text
        assert "data: " in text
        assert "Decision Intelligence" in text

    app.dependency_overrides.clear()
