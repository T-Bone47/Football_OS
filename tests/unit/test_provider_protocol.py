import httpx
import pytest

from app.providers.api_football import ApiFootballProvider
from app.providers.statsbomb import StatsBombProvider


async def test_statsbomb_rejects_unknown_resource():
    provider = StatsBombProvider(client=httpx.AsyncClient())
    with pytest.raises(ValueError):
        await provider.fetch("not-a-real-resource")
    await provider.close()


async def test_api_football_sends_configured_auth_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=[{"id": 1}])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": "test-key-123"},
        transport=transport,
    )
    provider = ApiFootballProvider(client=client)

    response = await provider.fetch("leagues", season=2026)

    assert response.status_code == 200
    assert captured["headers"]["x-apisports-key"] == "test-key-123"
    await provider.close()


async def test_api_football_requires_key_when_no_client_given(monkeypatch):
    from app import config
    from app.providers import api_football

    # monkeypatch.delenv only clears the process environment — it doesn't
    # stop Settings from also reading a real .env file on disk (a separate
    # pydantic-settings source). Force _env_file=None so this test is
    # isolated from whatever .env happens to exist in this checkout.
    # Patched on the `api_football` module specifically: it did
    # `from app.config import get_settings`, which binds its own local
    # name — patching `app.config.get_settings` doesn't reach that binding.
    monkeypatch.setattr(
        api_football, "get_settings", lambda: config.Settings(api_football_key=None, _env_file=None)
    )

    with pytest.raises(RuntimeError):
        ApiFootballProvider()
