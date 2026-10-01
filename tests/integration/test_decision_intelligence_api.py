"""
Integration and Contract Tests for Phase 7 Unified Decision Intelligence APIs.

Verifies:
- GET /api/v1/decisions/recruitment
- POST /api/v1/decisions/recruitment/analyze
- POST /api/v1/decisions/replacement
- POST /api/v1/decisions/transfer-scenario
- POST /api/v1/decisions/compare
- GET /api/v1/decisions/{decision_id}
- GET /api/v1/decisions/{decision_id}/evidence
- POST /api/copilot/query (Scout Copilot Decision Orchestrator)
"""

import uuid
import pytest
import pytest_asyncio
from phase17_support import bearer_headers
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.db.models.canonical import PlayerSeasonStats
from app.normalization.schemas import NormalizedClub, NormalizedPlayer
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def decision_client(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"Database not reachable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    # Seed test clubs and players
    async with Session() as session:
        service = NormalizationService(session)
        club = await service.upsert_club(
            "api-football",
            NormalizedClub(
                provider_id="101",
                name="Arsenal FC",
                code="ARS",
                country="England",
                venue_name="Emirates Stadium",
            ),
        )
        p1 = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="201",
                name="Martin Odegaard",
                nationality="Norway",
                primary_position="Midfielder",
            ),
        )
        p2 = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="202",
                name="Declan Rice",
                nationality="England",
                primary_position="Midfielder",
            ),
        )
        p3 = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="203",
                name="Bukayo Saka",
                nationality="England",
                primary_position="Attacker",
            ),
        )
        p1.club_id = club.id
        p2.club_id = club.id
        p3.club_id = club.id

        comp = await service.get_or_create_competition("Premier League", "England", "EPL")
        season = await service.get_or_create_season("2023", 2023, 2024)
        comp_season = await service.get_or_create_competition_season(comp.id, season.id)

        # Phase 17: the original call used a NormalizationService method and
        # NormalizedPlayerStats fields that never existed in this repository.
        session.add(PlayerSeasonStats(player_id=p1.id, club_id=club.id, competition_season_id=comp_season.id,
                                      appearances=30, lineups=30,
                                      minutes=2500, goals=8, assists=10))
        # Phase 17: the original call used a NormalizationService method and
        # NormalizedPlayerStats fields that never existed in this repository.
        session.add(PlayerSeasonStats(player_id=p2.id, club_id=club.id, competition_season_id=comp_season.id,
                                      appearances=32, lineups=32,
                                      minutes=2700, goals=6, assists=7))
        await session.commit()

        # Cache IDs
        club_id = str(club.id)
        p1_id = str(p1.id)
        p2_id = str(p2.id)
        p3_id = str(p3.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=await bearer_headers(Session)) as client:
        client.sessionmaker = Session
        client.test_club_id = club_id
        client.p1_id = p1_id
        client.p2_id = p2_id
        client.p3_id = p3_id
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_recruitment_targets_api(decision_client):
    res = await decision_client.get("/api/v1/decisions/recruitment?target_position=CM&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "decision" in data
    assert "top_recommendations" in data
    assert "excluded_summaries" in data
    assert data["decision"]["decision_type"] == "RECRUITMENT"


@pytest.mark.asyncio
async def test_post_recruitment_analyze_api(decision_client):
    """Real DB state: two players with reported minutes, no date of birth and
    no contribution or tactical evidence. Unknown age fails the requested age
    window; nothing is ranked on invented evidence."""
    payload = {
        "target_position": "CM",
        "tactical_context_id": "433_cm_progressive_midfielder",
        "budget_eur": 50000000.0,
        "min_minutes": 500,
        "risk_tolerance": "MEDIUM",
        "limit": 5,
    }
    res = await decision_client.post("/api/v1/decisions/recruitment/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["decision_type"] == "RECRUITMENT"
    assert data["status"] == "INSUFFICIENT_EVIDENCE" and data["top_recommendations"] == []
    by_name = {c["player_name"]: c for c in data["insufficient_evidence"]}
    assert by_name["Martin Odegaard"]["minutes_played"] == 2500  # provider-reported
    assert by_name["Martin Odegaard"]["dimension_status"]["minutes"] == "OBSERVED"
    assert by_name["Martin Odegaard"]["performance"] is None and by_name["Martin Odegaard"]["market"] is None

    payload["min_age"] = 20
    data = (await decision_client.post("/api/v1/decisions/recruitment/analyze", json=payload)).json()
    reasons = [r for e in data["excluded_summaries"] for r in e["exclusion_reasons"]]
    assert data["insufficient_evidence"] == [] and any("Age UNKNOWN" in r for r in reasons)


@pytest.mark.asyncio
async def test_analysis_is_persisted_and_scoped_to_the_organization(decision_client):
    data = (await decision_client.get("/api/v1/decisions/recruitment?target_position=CM&limit=5")).json()
    decision_id = data["decision"]["decision_id"]
    stored = await decision_client.get(f"/api/v1/decisions/{decision_id}")
    assert stored.status_code == 200
    body = stored.json()
    assert body["analysis"]["decision"]["decision_id"] == decision_id and len(body["content_sha256"]) == 64
    assert (await decision_client.get(f"/api/v1/decisions/{decision_id}/evidence")).status_code == 200

    from app.phase17 import OpsRole
    from app.phase17.auth import issue_user

    async with decision_client.sessionmaker() as s:
        _, token = await issue_user(s, "Another organization", f"o-{uuid.uuid4().hex[:8]}@example.com", "Other", OpsRole.ANALYST)
        await s.commit()
    other = await decision_client.get(f"/api/v1/decisions/{decision_id}", headers={"Authorization": f"Bearer {token}"})
    assert other.status_code == 404  # another organization never reads this analysis


@pytest.mark.asyncio
async def test_post_replacement_api(decision_client):
    payload = {
        "player_id_to_replace": decision_client.p1_id,
        "target_role": "Playmaker",
        "min_similarity": 0.60,
        "budget_eur": 60000000.0,
        "limit": 3,
    }
    res = await decision_client.post("/api/v1/decisions/replacement", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["replaced_player_id"] == decision_client.p1_id
    assert data["status"] == "INSUFFICIENT_EVIDENCE"  # no stored role profiles to compare
    assert [c["player_name"] for c in data["insufficient_evidence"]] == ["Declan Rice"]
    assert data["insufficient_evidence"][0]["dimension_status"]["similarity"] == "NOT_ASSESSED"

    missing = await decision_client.post("/api/v1/decisions/replacement",
                                         json={"player_id_to_replace": str(uuid.uuid4())})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_post_transfer_scenario_api(decision_client):
    payload = {
        "club_id": decision_client.test_club_id,
        "roster_changes": [
            {"player_id": decision_client.p3_id, "direction": "IN"},
            {"player_id": decision_client.p1_id, "direction": "OUT", "fee_eur": 40000000.0},
        ],
        "budget_eur": 80000000.0,
    }
    res = await decision_client.post("/api/v1/decisions/transfer-scenario", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["decision_type"] == "TRANSFER_SCENARIO"
    assert data["decision"]["provenance"]["modality"] == "COUNTERFACTUAL"
    fin = data["financial_impact"]
    assert fin["fees_missing_for"] == [decision_client.p3_id]
    assert fin["net_transfer_spend_eur"] is None and fin["financial_feasibility"] == "UNKNOWN"
    squad = data["squad_impact_summary"]
    assert squad["roster_size_before"] == 2 and squad["roster_size_after"] == 2  # the stored roster, not a seed
    assert data["match_prediction_impact"] is None

    unknown = dict(payload, club_id=str(uuid.uuid4()))
    assert (await decision_client.post("/api/v1/decisions/transfer-scenario", json=unknown)).status_code == 404


@pytest.mark.asyncio
async def test_post_compare_api(decision_client):
    missing = str(uuid.uuid4())
    payload = {"candidate_ids": [decision_client.p1_id, decision_client.p2_id, missing]}
    res = await decision_client.post("/api/v1/decisions/compare", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert [c["player_name"] for c in data["candidates"]] == ["Martin Odegaard", "Declan Rice"]
    assert data["not_found_candidate_ids"] == [missing]
    # Risk is scored from reported minutes and appearances (two dimensions);
    # no tactical, performance or value evidence is stored, so no such leader.
    assert set(data["dimension_leaders"]) == {"lowest_risk"}
    risk = data["candidates"][0]["risk"]
    assert risk["financial_risk"] is None and risk["adaptation_risk"] is None
    assert data["candidates"][0]["dimension_status"]["risk"] == "MODELLED"


@pytest.mark.asyncio
async def test_copilot_decision_query_streaming(decision_client):
    payload = {
        "query": "Find a replacement for our attacking playmaker under 50m",
        "context_players": [{"id": decision_client.p1_id, "name": "Martin Odegaard", "primary_position": "MF"}],
    }
    res = await decision_client.post("/api/copilot/query", json=payload)
    assert res.status_code == 200
    text_content = res.text
    assert "data: " in text_content
    assert "Decision Intelligence" in text_content
