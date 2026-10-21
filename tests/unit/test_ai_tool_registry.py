"""Unit tests for the grounded assistant: tool registry, claim validation, docs retrieval.

These use a fake provider and the isolated test database, so no network call and no
live model is involved.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.llm.tools.base import (
    EpistemicStatus,
    Evidence,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
)
from app.llm.tools.claims import validate_answer
from app.llm.tools.docs import get_index, retrieve_documentation


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=10)


def _spec(handler, **kwargs) -> ToolSpec:
    return ToolSpec(
        name="echo_tool",
        summary="Echo",
        description="Echo a value",
        input_model=_Input,
        handler=handler,
        service="test.service",
        data_source="test",
        **kwargs,
    )


# --------------------------------------------------------------------- registry
async def test_unknown_tool_is_rejected_cleanly():
    registry = ToolRegistry()
    result = await registry.execute("does_not_exist", {})
    assert result.status is ToolStatus.ERROR
    assert "unknown tool" in (result.error or "")
    assert result.ok is False


async def test_invalid_arguments_are_rejected_before_execution():
    called = {"count": 0}

    async def handler(session, principal, call_id, **kwargs):
        called["count"] += 1
        return ToolResult(tool="echo_tool", data=kwargs)

    registry = ToolRegistry()
    registry.register(_spec(handler))
    result = await registry.execute("echo_tool", {"value": "x", "unexpected": 1})
    assert result.status is ToolStatus.ERROR
    assert "invalid arguments" in (result.error or "")
    assert called["count"] == 0


async def test_missing_argument_is_rejected():
    async def handler(session, principal, call_id, **kwargs):
        return ToolResult(tool="echo_tool", data=kwargs)

    registry = ToolRegistry()
    registry.register(_spec(handler))
    result = await registry.execute("echo_tool", {})
    assert result.status is ToolStatus.ERROR
    assert "invalid arguments" in (result.error or "")


async def test_tool_runs_and_returns_evidence():
    async def handler(session, principal, call_id, **kwargs):
        return ToolResult(
            tool="echo_tool",
            data={"echoed": kwargs["value"]},
            evidence=[
                Evidence(
                    entity_type="player",
                    entity_id="11111111-1111-1111-1111-111111111111",
                    entity_name="Test Player",
                    metric="minutes",
                    value=900,
                    unit="minutes",
                    season="2023",
                    competition="Premier League",
                    sample_size=34,
                )
            ],
        )

    registry = ToolRegistry()
    registry.register(_spec(handler))
    result = await registry.execute("echo_tool", {"value": "hello"})
    assert result.status is ToolStatus.OK
    assert result.data == {"echoed": "hello"}
    assert result.evidence[0].value == 900
    assert result.latency_ms >= 0


async def test_tool_timeout_is_enforced():
    async def handler(session, principal, call_id, **kwargs):
        await asyncio.sleep(5)
        return ToolResult(tool="echo_tool")

    registry = ToolRegistry()
    registry.register(_spec(handler, timeout_seconds=0.05))
    result = await registry.execute("echo_tool", {"value": "slow"})
    assert result.status is ToolStatus.ERROR
    assert "budget" in (result.error or "")


async def test_tool_exception_does_not_leak_internals():
    async def handler(session, principal, call_id, **kwargs):
        raise RuntimeError("secret dsn postgres://user:pw@host/db")

    registry = ToolRegistry()
    registry.register(_spec(handler))
    result = await registry.execute("echo_tool", {"value": "boom"})
    assert result.status is ToolStatus.ERROR
    assert "secret dsn" not in (result.error or "")
    assert "RuntimeError" in (result.error or "")


async def test_permission_is_required_when_declared():
    async def handler(session, principal, call_id, **kwargs):
        return ToolResult(tool="echo_tool")

    registry = ToolRegistry()
    registry.register(_spec(handler, permissions=("admin",)))

    class _Principal:
        permissions = frozenset({"viewer"})

    denied = await registry.execute("echo_tool", {"value": "x"}, principal=_Principal())
    assert denied.status is ToolStatus.ERROR
    assert "permission" in (denied.error or "")

    class _Admin:
        permissions = frozenset({"admin"})

    allowed = await registry.execute("echo_tool", {"value": "x"}, principal=_Admin())
    assert allowed.status is ToolStatus.OK


async def test_tool_error_carries_explicit_status():
    async def handler(session, principal, call_id, **kwargs):
        raise ToolError("no such capability", ToolStatus.UNSUPPORTED)

    registry = ToolRegistry()
    registry.register(_spec(handler))
    result = await registry.execute("echo_tool", {"value": "x"})
    assert result.status is ToolStatus.UNSUPPORTED
    assert result.error == "no such capability"


def test_catalogue_exposes_schema_and_service():
    async def handler(session, principal, call_id, **kwargs):
        return ToolResult(tool="echo_tool")

    registry = ToolRegistry()
    registry.register(_spec(handler))
    catalogue = registry.catalogue()
    assert catalogue[0]["name"] == "echo_tool"
    assert catalogue[0]["service"] == "test.service"
    assert "properties" in catalogue[0]["input"]


# ------------------------------------------------------------------ claim check
def test_claim_validation_flags_numbers_without_evidence():
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
    report = validate_answer("A. Player played 900 minutes and scored 17 goals.", evidence)
    assert "900" in report.supported_numbers
    assert "17" in report.unsupported_numbers
    assert report.grounded is False


def test_claim_validation_accepts_grounded_numbers():
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
    report = validate_answer("A. Player played 900 minutes.", evidence)
    assert report.unsupported_numbers == []
    assert report.grounded is True


def test_claim_validation_checks_entity_ids():
    known = "11111111-1111-1111-1111-111111111111"
    unknown = "22222222-2222-2222-2222-222222222222"
    evidence = [
        Evidence(entity_type="player", entity_id=known, entity_name="A. Player", metric="minutes", value=1)
    ]
    report = validate_answer(f"Player {known} and player {unknown}", evidence)
    assert report.known_entity_ids == [known]
    assert report.unknown_entity_ids == [unknown]
    assert report.grounded is False


def test_claim_validation_ignores_season_like_numbers_when_present():
    evidence = [
        Evidence(
            entity_type="player_season_stat",
            entity_id="11111111-1111-1111-1111-111111111111",
            metric="minutes",
            value=2702,
            unit="minutes",
            season="2023",
        )
    ]
    report = validate_answer("In 2023 the player logged 2702 minutes.", evidence)
    assert "2023" in report.supported_numbers
    assert "2702" in report.supported_numbers
    assert report.unsupported_numbers == []


# -------------------------------------------------------------------- documents
def test_documentation_index_is_built_from_the_repository():
    index = get_index()
    assert len(index) > 50
    assert any("VALUATION" in section.path.upper() for section in index)


def test_documentation_retrieval_returns_sections_with_provenance():
    passages = retrieve_documentation("valuation baseline comparable median")
    assert passages
    assert passages[0]["ref"]
    assert passages[0]["section"]
    assert passages[0]["text"]


def test_documentation_retrieval_returns_nothing_for_nonsense():
    assert retrieve_documentation("zzzqqqxyzzy") == []


# ------------------------------------------------------------------ FIO registry
def test_fio_registry_exposes_the_expected_families():
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    names = set(registry.names())
    assert "search_players" in names
    assert "get_player_profile" in names
    assert "search_matches" in names
    assert "get_data_coverage" in names
    assert "get_league_standings" in names  # present, but reports UNSUPPORTED
    assert len(names) >= 25


def test_fio_tools_are_read_only_by_default():
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    assert all(spec.read_only for spec in registry.specs())


def test_fio_tool_schemas_are_valid_json_schemas():
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    for schema in registry.schemas():
        function = schema["function"]
        assert function["name"]
        assert function["description"]
        assert function["parameters"]["type"] == "object"


def test_relevance_selection_always_offers_the_core_tools():
    """The provider rejects a call to a tool that was not offered."""
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    for question in (
        "Is the valuation of a Premier League striker justified by his performance?",
        "why did the team lose its last match",
        "how many players are in the database",
    ):
        selected = registry.select_relevant(question, limit=10)
        assert "search_players" in selected
        assert "get_player_profile" in selected
        assert "get_data_coverage" in selected


def test_fallback_router_only_uses_tools_that_run_without_arguments():
    """The fallback runs without the model, so it cannot supply a player id."""
    from app.llm.tools.fallback import plan_fallback_tools
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    for question in (
        "Is the valuation of a Premier League striker justified?",
        "why did the team lose its last match?",
        "how many players are in the database?",
        "is the squad balanced in a 4-3-3?",
        "compare two midfielders",
    ):
        for call in plan_fallback_tools(question):
            spec = registry.get(call.tool)
            assert spec is not None, call.tool
            # every argument the fallback passes must exist in the tool's input model
            assert set(call.arguments) <= set(spec.input_model.model_fields)


def test_fallback_router_maps_question_shapes_to_tools():
    from app.llm.tools.fallback import plan_fallback_tools

    assert "get_data_coverage" in {call.tool for call in plan_fallback_tools("how many players are stored?")}
    assert "search_matches" in {call.tool for call in plan_fallback_tools("why did the team lose its last match?")}
    assert "analyze_squad_balance" in {call.tool for call in plan_fallback_tools("is the squad balanced?")}


def test_compact_schemas_declare_nullable_parameters_without_duplicate_types():
    """The provider rejects the whole request when a schema is invalid.

    A duplicated type ("null" twice) is invalid JSON schema, so the compact
    schema must keep the type list unique.
    """
    from app.llm.tools.fio_tools import build_tool_registry

    registry = build_tool_registry()
    for schema in registry.schemas(compact=True):
        properties = schema["function"]["parameters"].get("properties") or {}
        for name, definition in properties.items():
            declared = definition.get("type")
            types = declared if isinstance(declared, list) else [declared]
            assert len(types) == len(set(types)), f"duplicate type for {name}"
            for item in types:
                assert item in (
                    "array", "boolean", "integer", "null", "number", "object", "string"
                ), f"unsupported type {item} for {name}"
