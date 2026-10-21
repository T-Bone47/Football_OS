from types import SimpleNamespace

import pytest

from app.llm.registry import LLMRegistry


class FakeProvider:
    provider_name = "Groq"
    model = "openai/gpt-oss-120b"

    async def verify_health(self):
        return {
            "status": "AVAILABLE",
            "model": self.model,
            "streaming_verified": True,
        }

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_active_status_resolves_canonical_provider_name():
    """The settings key may be lowercase while the provider reports "Groq".

    get_active_status() must read the same status object that verify_all()
    updated, otherwise the dashboard shows CONFIGURED_UNVERIFIED forever.
    """
    registry = LLMRegistry()
    registry._settings = SimpleNamespace(
        llm_provider="groq",
        llm_model="openai/gpt-oss-120b",
        llm_fallback_provider="none",
        llm_fallback_model=None,
        llm_allow_paid_fallback=False,
    )
    registry._create_provider = lambda name, model: FakeProvider()

    registry.initialize()
    results = await registry.verify_all()

    active = registry.get_active_status()
    assert results[0]["status"] == "AVAILABLE"
    assert active["provider"] == "Groq"
    assert active["status"] == "AVAILABLE"
    assert active["streaming_verified"] is True
    assert registry.get_provider("groq") is not None
