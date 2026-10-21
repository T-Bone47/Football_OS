"""Player pagination API regression tests.

These seed deterministic canonical fixtures (not provider payloads) and
exercise the paginated canonical endpoint. They run inside the shared
transaction-rollback fixture, so they do not truncate or drop shared tables.
"""
import httpx
import pytest
import pytest_asyncio

from app.db.session import get_session
from app.main import app
from app.normalization.schemas import NormalizedPlayer
from app.normalization.service import NormalizationService

PREFIX = "Pagination Fixture"


@pytest_asyncio.fixture
async def seeded_players_client(integration_session):
    service = NormalizationService(integration_session)
    positions = ["Goalkeeper", "Defender", "Midfielder", "Attacker"]
    nationalities = ["England", "France", "Spain", "Germany"]
    for i in range(60):
        await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id=f"pagination-{i:03d}",
                name=f"{PREFIX} {i:03d}",
                primary_position=positions[i % len(positions)],
                nationality=nationalities[i % len(nationalities)],
            ),
        )
    # A literal wildcard must not behave like "match everything".
    await service.upsert_player(
        "api-football",
        NormalizedPlayer(
            provider_id="pagination-wildcard",
            name="100% Fit",
            primary_position="Midfielder",
            nationality="England",
        ),
    )
    await integration_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _search(client, **params):
    res = await client.get("/api/v1/players/search", params=params)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_pagination_reports_true_total_and_pages(seeded_players_client):
    first = await _search(seeded_players_client, q=PREFIX, page=1, page_size=25)
    assert first["total"] == 60
    assert first["page"] == 1
    assert first["page_size"] == 25
    assert first["total_pages"] == 3
    assert first["has_next"] is True
    assert len(first["items"]) == 25

    middle = await _search(seeded_players_client, q=PREFIX, page=2, page_size=25)
    assert len(middle["items"]) == 25
    assert middle["has_next"] is True

    last = await _search(seeded_players_client, q=PREFIX, page=3, page_size=25)
    assert len(last["items"]) == 10
    assert last["has_next"] is False
    assert last["total_pages"] == 3

    ids = [p["id"] for p in first["items"] + middle["items"] + last["items"]]
    assert len(ids) == 60
    assert len(set(ids)) == 60


@pytest.mark.asyncio
async def test_search_reaches_players_beyond_first_page(seeded_players_client):
    result = await _search(
        seeded_players_client, q=f"{PREFIX} 059", page=1, page_size=25
    )
    assert result["total"] == 1
    assert result["items"][0]["name"] == f"{PREFIX} 059"


@pytest.mark.asyncio
async def test_filters_apply_before_pagination(seeded_players_client):
    result = await _search(
        seeded_players_client, q=PREFIX, position="D", page=1, page_size=25
    )
    assert result["total"] == 15
    assert result["total_pages"] == 1
    assert all(p["primary_position"] == "Defender" for p in result["items"])

    national = await _search(
        seeded_players_client, q=PREFIX, nationality="France", page=1, page_size=25
    )
    assert national["total"] == 15
    assert all(p["nationality"] == "France" for p in national["items"])


@pytest.mark.asyncio
async def test_sorting_is_stable_and_page_disjoint(seeded_players_client):
    page1 = await _search(
        seeded_players_client, q=PREFIX, page=1, page_size=10, sort_by="name"
    )
    page2 = await _search(
        seeded_players_client, q=PREFIX, page=2, page_size=10, sort_by="name"
    )
    names1 = [p["name"] for p in page1["items"]]
    names2 = [p["name"] for p in page2["items"]]
    assert names1 == sorted(names1)
    assert names2 == sorted(names2)
    assert names1[-1] < names2[0]
    assert not ({p["id"] for p in page1["items"]} & {p["id"] for p in page2["items"]})


@pytest.mark.asyncio
async def test_invalid_pagination_parameters_are_rejected(seeded_players_client):
    assert (
        await seeded_players_client.get("/api/v1/players/search", params={"page": 0})
    ).status_code == 422
    assert (
        await seeded_players_client.get(
            "/api/v1/players/search", params={"page_size": 101}
        )
    ).status_code == 422
    assert (
        await seeded_players_client.get(
            "/api/v1/players/search", params={"page_size": 0}
        )
    ).status_code == 422


@pytest.mark.asyncio
async def test_wildcards_are_escaped(seeded_players_client):
    result = await _search(seeded_players_client, q="100%", page_size=25)
    assert result["total"] == 1
    assert result["items"][0]["name"] == "100% Fit"


@pytest.mark.asyncio
async def test_legacy_players_endpoint_is_bounded_but_not_capped_at_50(
    seeded_players_client,
):
    res = await seeded_players_client.get("/api/v1/players", params={"limit": 100})
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 61
    assert len(data) <= 100

    # An explicit offset is honoured by the legacy list, so consumers that
    # want to walk it are not stuck on the first page.
    page2 = await seeded_players_client.get(
        "/api/v1/players", params={"limit": 10, "offset": 10}
    )
    assert page2.status_code == 200
    assert len(page2.json()) == 10


@pytest.mark.asyncio
async def test_facets_are_database_wide(seeded_players_client):
    res = await seeded_players_client.get("/api/v1/players/facets")
    assert res.status_code == 200
    body = res.json()
    assert body["total_players"] >= 61
    assert "Defender" in body["positions"]
    assert "France" in body["nationalities"]


@pytest.mark.asyncio
async def test_coverage_endpoint_measures_canonical_rows(seeded_players_client):
    res = await seeded_players_client.get("/api/v1/players/coverage")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_players"] >= 61
    assert body["provider_mappings"]["api-football"] >= 61
    assert body["unique_mapped_players_by_provider"]["api-football"] >= 61
    assert body["duplicate_provider_ids"] == 0
    assert "ingestion_completeness" in body
    assert body["ingestion_completeness"]["status"] in {
        "COMPLETE",
        "PARTIAL",
        "INCOMPLETE",
        "UNKNOWN",
        "BLOCKED_BY_PLAN",
    }
