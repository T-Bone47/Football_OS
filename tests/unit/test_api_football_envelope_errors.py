"""§18: HTTP 200 with a non-empty errors[] must not be treated as success."""
import httpx
import pytest

from app.providers.api_football import ApiFootballProvider
from app.providers.errors import ProviderBadRequestError


async def test_200_with_errors_array_raises_bad_request():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"get": "leagues", "parameters": {}, "errors": {"token": "Invalid token"}, "results": 0, "response": []},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x")
    provider = ApiFootballProvider(client=client)

    with pytest.raises(ProviderBadRequestError):
        await provider.fetch("leagues")
    await provider.close()


async def test_200_with_empty_errors_succeeds():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"get": "leagues", "parameters": {}, "errors": [], "results": 1, "response": [{"id": 1}]}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x")
    provider = ApiFootballProvider(client=client)

    response = await provider.fetch("leagues")

    assert response.status_code == 200
    await provider.close()
