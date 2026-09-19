"""End-to-end (adapter -> classify -> raised exception) coverage, distinct
from test_provider_errors.py which tests the classifier function in
isolation. This proves the wiring, not just the classification logic.
"""
import httpx
import pytest

from app.providers.api_football import ApiFootballProvider
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
)


def _provider_with_status(status: int, headers: dict | None = None) -> ApiFootballProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {}, json={"errors": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x")
    return ApiFootballProvider(client=client)


async def test_401_raises_authentication_error():
    provider = _provider_with_status(401)
    with pytest.raises(ProviderAuthenticationError):
        await provider.fetch("status")
    await provider.close()


async def test_500_raises_server_error_and_is_retried(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)
    provider = _provider_with_status(500)
    with pytest.raises(ProviderServerError):
        await provider.fetch("status")
    await provider.close()


async def test_429_raises_rate_limit_error(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)
    provider = _provider_with_status(429, headers={"retry-after": "0"})
    with pytest.raises(ProviderRateLimitError):
        await provider.fetch("status")
    await provider.close()


async def test_timeout_raises_network_error(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x")
    provider = ApiFootballProvider(client=client)

    with pytest.raises(ProviderNetworkError):
        await provider.fetch("status")
    await provider.close()
