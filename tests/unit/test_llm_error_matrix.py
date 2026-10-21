"""Mocked LLM provider error matrix and copilot abstention tests.

These use a mocked HTTP transport, so they are deterministic and never touch
a real provider. Live Groq completion/streaming is verified separately and is
not claimed by this file.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.decisions.copilot import ScoutDecisionTools
from app.llm.base import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMMessage,
    LLMRateLimitError,
    LLMResponse,
)
from app.llm.openai_compatible import GroqProvider
from app.llm.registry import LLMRegistry, ProviderStatus


def _provider(handler, *, max_retries: int = 0, enable_streaming: bool = True) -> GroqProvider:
    return GroqProvider(
        api_key="test-key-not-real",
        model="openai/gpt-oss-120b",
        base_url="https://api.example.test",
        max_retries=max_retries,
        max_output_tokens=64,
        enable_streaming=enable_streaming,
    )


def _client(provider: GroqProvider, handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.example.test",
    )


def _ok(content: str = "FIO_GROQ_OK", finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [
                {"message": {"content": content}, "finish_reason": finish_reason}
            ],
            "usage": {"total_tokens": 12},
        },
    )


@pytest.mark.asyncio
async def test_401_is_authentication_failure():
    provider = _provider(lambda request: httpx.Response(401, json={"error": "bad key"}))
    await provider._client.aclose()
    provider._client = _client(provider, lambda request: httpx.Response(401, json={"error": "bad key"}))
    try:
        with pytest.raises(LLMAuthenticationError):
            await provider.complete([LLMMessage(role="user", content="hi")])
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_429_is_rate_limit_not_bad_request():
    def handler(request):
        return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow down"})

    provider = _provider(handler)
    await provider._client.aclose()
    provider._client = _client(provider, handler)
    try:
        with pytest.raises(LLMRateLimitError):
            await provider.complete([LLMMessage(role="user", content="hi")])
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_404_unknown_model_is_a_bad_request_with_status_text():
    def handler(request):
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    provider = _provider(handler)
    await provider._client.aclose()
    provider._client = _client(provider, handler)
    try:
        with pytest.raises(LLMBadRequestError) as exc:
            await provider.complete([LLMMessage(role="user", content="hi")])
        assert "404" in str(exc.value)
        assert "model not found" in str(exc.value)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_empty_completion_is_returned_empty_not_invented():
    provider = _provider(lambda request: _ok("", finish_reason="length"))
    await provider._client.aclose()
    provider._client = _client(provider, lambda request: _ok("", finish_reason="length"))
    try:
        response = await provider.complete([LLMMessage(role="user", content="hi")])
        assert response.content == ""
        assert response.finish_reason == "length"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_streaming_yields_incremental_chunks():
    sse = (
        'data: {"model":"openai/gpt-oss-120b","choices":[{"delta":{"content":"FIO"},"finish_reason":null}]}\n\n'
        'data: {"model":"openai/gpt-oss-120b","choices":[{"delta":{"content":"_GROQ_OK"},"finish_reason":null}]}\n\n'
        'data: {"model":"openai/gpt-oss-120b","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)

    provider = _provider(handler)
    await provider._client.aclose()
    provider._client = _client(provider, handler)
    try:
        stream = await provider.complete([LLMMessage(role="user", content="hi")], stream=True)
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert [c.delta for c in chunks] == ["FIO", "_GROQ_OK"]
        assert chunks[-1].finish_reason is None or chunks[-1].finish_reason == "stop"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_health_reports_authentication_failed():
    provider = _provider(lambda request: httpx.Response(401, json={}))
    await provider._client.aclose()
    provider._client = _client(provider, lambda request: httpx.Response(401, json={}))
    try:
        status = await provider.verify_health()
        assert status["status"] == "AUTHENTICATION_FAILED"
    finally:
        await provider.close()


class _FakeProvider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.provider_name = name
        self.model = "test-model"
        self.called = False
        self._fail = fail

    async def complete(self, messages, stream: bool = False, **kwargs):
        self.called = True
        if self._fail:
            raise LLMRateLimitError("quota", self.provider_name)
        return LLMResponse(
            content="ok",
            model=self.model,
            provider=self.provider_name,
            latency_ms=12,
            finish_reason="stop",
        )

    async def verify_health(self):
        return {"status": "AVAILABLE", "model": self.model}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_fallback_disabled_does_not_call_secondary():
    registry = LLMRegistry()
    primary = _FakeProvider("primary", fail=True)
    fallback = _FakeProvider("fallback")
    registry._settings = SimpleNamespace(llm_allow_paid_fallback=False)
    registry._primary = primary
    registry._fallback = fallback
    registry._primary_key = "primary"
    registry._fallback_key = "fallback"
    registry._statuses = {
        "primary": ProviderStatus(provider="primary", model="test-model", configured=True),
        "fallback": ProviderStatus(provider="fallback", model="test-model", configured=True),
    }

    with pytest.raises(LLMRateLimitError):
        await registry.complete_with_fallback([{"role": "user", "content": "hi"}])
    assert fallback.called is False
    assert registry._statuses["primary"].last_error is not None


@pytest.mark.asyncio
async def test_success_records_last_measured_completion():
    registry = LLMRegistry()
    primary = _FakeProvider("primary")
    registry._settings = SimpleNamespace(llm_allow_paid_fallback=False)
    registry._primary = primary
    registry._primary_key = "primary"

    registry._statuses = {
        "primary": ProviderStatus(provider="primary", model="test-model", configured=True)
    }

    await registry.complete_with_fallback([{"role": "user", "content": "hi"}])
    assert registry._statuses["primary"].last_success_at is not None
    assert registry._statuses["primary"].last_success_latency_ms == 12
    assert registry._statuses["primary"].last_success_finish_reason == "stop"


@pytest.mark.asyncio
async def test_copilot_tools_abstain_without_session_instead_of_canned_values():
    tools = ScoutDecisionTools(session=None)
    match = await tools.get_match_prediction(uuid.uuid4())
    assert match["status"] == "UNAVAILABLE"
    assert "probabilities" not in match

    market = await tools.get_market_context(uuid.uuid4())
    assert market["status"] == "UNAVAILABLE"
    assert "contract_expiration" not in market

    intelligence = await tools.get_player_intelligence(uuid.uuid4())
    assert intelligence["status"] == "UNAVAILABLE"
    assert "contribution_model_version" not in intelligence
