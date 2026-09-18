import httpx
import pytest

from app.providers.http import request_with_retry_config


async def test_retries_on_429_then_succeeds(monkeypatch):
    # Don't actually sleep through backoff in a unit test.
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)

    calls = {"n": 0}

    @request_with_retry_config(max_attempts=3)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(429, request=request, headers={"retry-after": "0"})
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert calls["n"] == 3


async def test_does_not_retry_401():
    calls = {"n": 0}

    @request_with_retry_config(max_attempts=3)
    async def unauthorized():
        calls["n"] += 1
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("bad key", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await unauthorized()

    assert calls["n"] == 1
