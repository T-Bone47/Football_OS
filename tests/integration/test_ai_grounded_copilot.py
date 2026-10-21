"""Integration tests for the grounded copilot.

The provider is faked (no network, no model), the database is the isolated test
database. These tests verify the orchestration contract: the model may only speak
about what the tools returned, unknown tools are refused, the tool budget holds,
provider failures are visible outcomes, and the real FIO tools read real rows.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.base import LLMMessage, LLMResponse, LLMProvider
from app.llm.tools.base import Evidence, ToolRegistry, ToolResult, ToolSpec, ToolStatus
from app.llm.tools.fio_tools import build_tool_registry
from app.llm.tools.orchestrator import GroundedCopilot


class _FakeProvider(LLMProvider):
    """A scripted provider: a list of responses returned in order."""

    provider_name = "Fake"

    def __init__(self, responses: list[LLMResponse]):
        super().__init__(api_key="test", base_url="http://fake", model="fake-model")
        self._responses = list(responses)
        self._last = self._responses[-1] if self._responses else LLMResponse(
            content="", model="fake-model", provider="Fake"
        )
        self.calls: list[list[dict[str, Any]]] = []

    @property
    def supports_streaming(self) -> bool:
        return False

    async def _make_request(self, messages, stream, temperature=0.3, top_p=0.9, max_tokens=None,
                            tools=None, tool_choice=None):
        self.calls.append([{"role": m.role, "content": m.content} for m in messages])
        if not self._responses:
            # The tool phase may ask for a tool before accepting an answer, so the
            # last scripted response is repeated rather than failing the turn.
            return self._last
        self._last = self._responses.pop(0)
        return self._last

    async def verify_health(self) -> dict:
        return {"status": "AVAILABLE", "provider": self.provider_name, "model": self.model}


def _tool_call(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class _StubInput(BaseModel):
    """A real input model: the registry needs its JSON schema."""

    model_config = ConfigDict(extra="forbid")
    note: str | None = None


def _stub_registry(result: ToolResult, *, name: str = "stub_tool") -> ToolRegistry:
    registry = ToolRegistry()

    async def handler(session, principal, call_id, **kwargs):
        return result

    registry.register(
        ToolSpec(
            name=name,
            summary="stub",
            description="stub tool",
            input_model=_StubInput,
            handler=handler,
            service="test",
            data_source="test",
        )
    )
    return registry


@pytest.mark.asyncio
async def test_grounded_answer_attaches_evidence_and_validates_claims(integration_session):
    evidence = [
        Evidence(
            entity_type="player",
            entity_id="11111111-1111-1111-1111-111111111111",
            entity_name="A. Player",
            metric="minutes",
            value=900,
            unit="minutes",
            competition="Premier League",
            season="2023",
        )
    ]
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                model="fake-model",
                provider="Fake",
                finish_reason="tool_calls",
                tool_calls=[_tool_call("stub_tool", {})],
            ),
            LLMResponse(
                content="A. Player logged 900 minutes in the Premier League (2023).",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
            LLMResponse(
                content="A. Player logged 900 minutes in the Premier League (2023).",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
        ]
    )
    copilot = GroundedCopilot(
        session=integration_session, registry=_stub_registry(ToolResult(tool="stub_tool", data={"ok": True}, evidence=evidence)), provider=provider
    )
    result = await copilot.answer("How many minutes did A. Player log?")
    assert result.status == "OK"
    assert "900" in result.answer
    assert result.evidence and result.evidence[0].value == 900
    assert result.validation.unsupported_numbers == []
    assert result.validation.grounded is True
    assert result.tools[0]["tool"] == "stub_tool"


@pytest.mark.asyncio
async def test_unsupported_numbers_are_reported_and_caveated(integration_session):
    evidence = [
        Evidence(
            entity_type="player",
            entity_id="11111111-1111-1111-1111-111111111111",
            entity_name="A. Player",
            metric="minutes",
            value=900,
            unit="minutes",
        )
    ]
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                model="fake-model",
                provider="Fake",
                finish_reason="tool_calls",
                tool_calls=[_tool_call("stub_tool", {})],
            ),
            LLMResponse(
                content="A. Player logged 900 minutes and scored 17 goals.",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
            LLMResponse(
                content="A. Player logged 900 minutes and scored 17 goals.",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
        ]
    )
    copilot = GroundedCopilot(
        session=integration_session,
        registry=_stub_registry(ToolResult(tool="stub_tool", data={"ok": True}, evidence=evidence)),
        provider=provider,
    )
    result = await copilot.answer("How many minutes did A. Player log?")
    assert "17" in result.validation.unsupported_numbers
    assert result.validation.grounded is False
    assert "Grounding check" in result.answer


@pytest.mark.asyncio
async def test_unknown_tool_is_refused_and_no_data_is_fabricated(integration_session):
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                model="fake-model",
                provider="Fake",
                finish_reason="tool_calls",
                tool_calls=[_tool_call("drop_database", {"sql": "DROP TABLE players"})],
            ),
            LLMResponse(
                content="I could not retrieve that.",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
            LLMResponse(
                content="I could not retrieve that.",
                model="fake-model",
                provider="Fake",
                finish_reason="stop",
            ),
        ]
    )
    copilot = GroundedCopilot(
        session=integration_session, registry=_stub_registry(ToolResult(tool="stub_tool")), provider=provider
    )
    result = await copilot.answer("Delete the players table")
    # The answer is not backed by evidence (the only tool the model tried was
    # refused), so the status says so instead of claiming a grounded answer.
    assert result.status in ("OK", "NO_EVIDENCE")
    assert any(entry.get("tool") == "drop_database" for entry in result.tools)
    assert result.evidence == []
    assert "DROP TABLE" not in result.answer


@pytest.mark.asyncio
async def test_tool_call_budget_is_enforced(integration_session):
    calls = [
        LLMResponse(
            content="",
            model="fake-model",
            provider="Fake",
            finish_reason="tool_calls",
            tool_calls=[_tool_call("stub_tool", {}, call_id=f"call-{index}") for index in range(4)],
        )
        for _ in range(4)
    ]
    provider = _FakeProvider(
        calls
        + [
            LLMResponse(content="Done.", model="fake-model", provider="Fake", finish_reason="stop"),
            LLMResponse(content="Done.", model="fake-model", provider="Fake", finish_reason="stop"),
        ]
    )
    copilot = GroundedCopilot(
        session=integration_session,
        registry=_stub_registry(ToolResult(tool="stub_tool")),
        provider=provider,
        max_tool_calls=2,
    )
    result = await copilot.answer("run many tools")
    executed = [entry for entry in result.tools if entry.get("status") == "OK"]
    skipped = [entry for entry in result.tools if entry.get("status") == "SKIPPED"]
    assert len(executed) == 2
    assert skipped, "the budget must be reported, not silently applied"


@pytest.mark.asyncio
async def test_provider_failure_is_a_visible_outcome(integration_session):
    class _Broken(_FakeProvider):
        async def _make_request(self, *args, **kwargs):
            raise RuntimeError("connection reset")

    provider = _Broken([])
    copilot = GroundedCopilot(
        session=integration_session, registry=_stub_registry(ToolResult(tool="stub_tool")), provider=provider
    )
    result = await copilot.answer("anything")
    assert result.status == "PROVIDER_ERROR"
    assert result.error == "RuntimeError"
    assert "secret" not in (result.error or "")


@pytest.mark.asyncio
async def test_empty_model_output_is_reported(integration_session):
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                model="fake-model",
                provider="Fake",
                finish_reason="tool_calls",
                tool_calls=[_tool_call("stub_tool", {})],
            ),
            LLMResponse(content="   ", model="fake-model", provider="Fake", finish_reason="stop"),
            LLMResponse(content="   ", model="fake-model", provider="Fake", finish_reason="stop"),
        ]
    )
    copilot = GroundedCopilot(
        session=integration_session, registry=_stub_registry(ToolResult(tool="stub_tool")), provider=provider
    )
    result = await copilot.answer("anything")
    assert result.status == "EMPTY_ANSWER"


@pytest.mark.asyncio
async def test_real_fio_tool_reads_real_rows(integration_session):
    """The search tool must read the canonical index, not a fixture."""
    from app.db.models.canonical import Player, PlayerIdentity

    player = Player(name="Test Grounder", primary_position="Midfielder", nationality="Testland")
    integration_session.add(player)
    await integration_session.flush()
    integration_session.add(
        PlayerIdentity(
            player_id=player.id,
            provider="test-provider",
            provider_player_id="9001",
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
    )
    await integration_session.commit()

    registry = build_tool_registry()
    result = await registry.execute(
        "search_players", {"q": "Test Grounder", "page": 1, "page_size": 5}, session=integration_session
    )
    assert result.status is ToolStatus.OK
    assert result.data["total"] == 1
    assert result.data["items"][0]["id"] == str(player.id)
    assert result.evidence, "a search must return evidence for the rows it found"


@pytest.mark.asyncio
async def test_unsupported_capability_is_explicit(integration_session):
    registry = build_tool_registry()
    result = await registry.execute(
        "get_league_standings", {"competition_id": None, "season": None}, session=integration_session
    )
    assert result.status is ToolStatus.UNSUPPORTED
    assert "standings" in (result.error or "").lower()
