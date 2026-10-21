"""Typed tool registry for the grounded FIO assistant.

Design rules (from the platform's own architecture, not from a generic
"agent framework"):

* A tool is a **typed wrapper around an existing FIO service or route handler**.
  Tools never re-implement analytics; they call the same code the API and the
  frontend use, so a tool answer and a page answer can never disagree.
* A tool is **read-only by default** and must declare the service it depends on,
  the data source, the permissions it needs and its timeout.
* Arguments are **validated before execution**; an unknown tool or a malformed
  argument is a clean, explicit error - never a partial execution.
* Every result carries **evidence**: entity ids, competition/season, units,
  sample sizes and an epistemic status, so the answer can be checked later.
* Failures are explicit: ``UNSUPPORTED`` (the capability does not exist),
  ``NOT_FOUND`` (the entity does not exist), ``AMBIGUOUS`` (several entities
  match - the caller must ask), ``INSUFFICIENT_DATA`` (the evidence exists but
  is too thin), ``ERROR`` (the service failed).
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from app.llm.tools.routing import CORE_TOOLS

logger = logging.getLogger(__name__)


class EpistemicStatus(str, enum.Enum):
    """How a piece of evidence must be read.

    ``OBSERVED`` is a stored measurement, ``MODELLED`` is a model output,
    ``COUNTERFACTUAL``/``SCENARIO`` are what-if results, ``ASSUMPTION``/``HYPOTHESIS``
    are reasoning, and the remaining three are explicit "we cannot answer this".
    """

    OBSERVED = "OBSERVED"
    MODELLED = "MODELLED"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    SCENARIO = "SCENARIO"
    ASSUMPTION = "ASSUMPTION"
    ANALYSIS = "ANALYSIS"
    HYPOTHESIS = "HYPOTHESIS"
    UNVERIFIED = "UNVERIFIED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    MODEL_UNCALIBRATED = "MODEL_UNCALIBRATED"


class ToolStatus(str, enum.Enum):
    OK = "OK"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


@dataclass
class Evidence:
    """One verifiable fact, with everything needed to check it."""

    entity_type: str
    entity_id: str | None
    entity_name: str | None = None
    metric: str | None = None
    value: Any = None
    unit: str | None = None
    competition: str | None = None
    season: str | None = None
    sample_size: int | None = None
    source: str | None = None
    data_period: str | None = None
    method: str | None = None
    model_version: str | None = None
    confidence: float | None = None
    epistemic_status: EpistemicStatus = EpistemicStatus.OBSERVED
    provenance_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "competition": self.competition,
            "season": self.season,
            "sample_size": self.sample_size,
            "source": self.source,
            "data_period": self.data_period,
            "method": self.method,
            "model_version": self.model_version,
            "confidence": self.confidence,
            "epistemic_status": self.epistemic_status.value,
            "provenance_ref": self.provenance_ref,
        }


@dataclass
class ToolResult:
    """The result of one tool execution."""

    tool: str
    status: ToolStatus = ToolStatus.OK
    data: Any = None
    evidence: list[Evidence] = field(default_factory=list)
    message: str | None = None
    error: str | None = None
    latency_ms: int = 0
    arguments: dict[str, Any] = field(default_factory=dict)
    service: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status.value,
            "data": self.data,
            "evidence": [item.to_dict() for item in self.evidence],
            "message": self.message,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "arguments": self.arguments,
            "service": self.service,
        }

    def compact(self, max_chars: int = 1200, max_evidence: int = 15) -> dict[str, Any]:
        """The version handed to the model: bounded, structured, no stack traces.

        The provider's per-minute token budget is shared by every request of a turn, so
        both the payload and the evidence list are capped.
        """
        import json

        payload: dict[str, Any] = {
            "tool": self.tool,
            "status": self.status.value,
            "message": self.message,
        }
        if self.ok:
            try:
                serialised = json.dumps(self.data, default=str)
            except (TypeError, ValueError):
                serialised = str(self.data)
            if len(serialised) > max_chars:
                serialised = serialised[:max_chars] + "... [truncated]"
            payload["data"] = serialised
            if self.evidence:
                payload["evidence"] = [
                    {
                        "id": item.entity_id,
                        "name": item.entity_name,
                        "metric": item.metric,
                        "value": item.value,
                        "unit": item.unit,
                        "competition": item.competition,
                        "season": item.season,
                        "status": item.epistemic_status.value,
                    }
                    for item in self.evidence[:max_evidence]
                ]
        else:
            payload["error"] = self.error or self.status.value
        return payload


class ToolError(Exception):
    """Raised by a tool handler to signal a specific, non-fatal outcome."""

    def __init__(self, message: str, status: ToolStatus = ToolStatus.ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


ToolHandler = Callable[..., Awaitable[ToolResult]]


@dataclass
class ToolSpec:
    """The contract of one tool."""

    name: str
    summary: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    service: str
    data_source: str
    permissions: tuple[str, ...] = ()
    timeout_seconds: float = 20.0
    read_only: bool = True
    max_items: int = 50
    family: str = "platform"
    hint: str | None = None
    """One line telling the model when (or when not) to call this tool."""

    def schema(self) -> dict[str, Any]:
        """The OpenAI-compatible function schema sent to the model."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }

    def compact_schema(self) -> dict[str, Any]:
        """A token-bounded schema.

        The provider's per-minute token budget is the binding constraint on how much
        context the model can receive, so the model sees the parameter names and types
        (and one line of purpose) instead of the full documentation. The complete
        contract stays in ``catalogue()`` and in the API.
        """
        parameters = self.input_model.model_json_schema()
        properties = {}
        for name, definition in (parameters.get("properties") or {}).items():
            entry: dict[str, Any] = {}
            types: list[str] = []
            if definition.get("anyOf"):
                types = [item.get("type") for item in definition["anyOf"] if item.get("type")]
            elif definition.get("type"):
                types = [definition["type"]]
            if not types:
                types = ["string"]
            # The provider validates the model's arguments against this schema and
            # rejects the whole generation when a nullable parameter is sent as
            # null, so a nullable property must declare null as a valid type.
            # The list must stay unique: a repeated type is an invalid JSON schema
            # and the provider refuses the entire request.
            if definition.get("default", "") is None or "null" in types:
                types = list(dict.fromkeys(types + ["null"]))
            entry["type"] = types[0] if len(types) == 1 else types
            if definition.get("default") is not None:
                entry["default"] = definition["default"]
            properties[name] = entry
        compact = {
            "type": "object",
            "properties": properties,
            "required": parameters.get("required", []),
        }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"{self.summary} {self.hint}".strip(),
                "parameters": compact,
            },
        }


class ToolRegistry:
    """An allowlisted registry of typed tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[name] for name in self.names()]

    def schemas(self, names: list[str] | None = None, *, compact: bool = False) -> list[dict[str, Any]]:
        selected = self.specs() if names is None else [
            spec for spec in self.specs() if spec.name in set(names)
        ]
        return [
            (spec.compact_schema() if compact else spec.schema()) for spec in selected
        ]

    def select_relevant(
        self,
        query: str,
        *,
        limit: int = 12,
        always: tuple[str, ...] = CORE_TOOLS,
    ) -> list[str]:
        """The tools most likely to answer a question.

        The question is classified into families first (routing.select_families), so
        the model is offered the tools that can answer it, and only then filled up
        with the most relevant of the rest. Offering every tool costs context the
        provider's token budget may not have (the Groq Free tier allows 8 000 tokens
        per minute), and the provider rejects a generation that calls a tool which
        was not offered - so the core (player resolution + coverage) is always
        present.
        """
        from app.llm.tools.docs import _tokenise
        from app.llm.tools.routing import select_families

        query_tokens = _tokenise(query)
        families = select_families(query)
        # The most specific family counts most: a valuation question is a financial
        # question first and a player question second.
        family_weight = {family: 1.5 - 0.4 * index for index, family in enumerate(families)}
        scored: list[tuple[float, str]] = []
        for spec in self.specs():
            tokens = _tokenise(f"{spec.name} {spec.summary} {spec.family}")
            overlap = len(query_tokens & tokens)
            score = overlap / (len(query_tokens) ** 0.5) if query_tokens else 0.0
            score += family_weight.get(spec.family, 0.0)
            scored.append((score, spec.name))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected: list[str] = []
        for name in always:
            if name in self._tools and name not in selected:
                selected.append(name)
        for score, name in scored:
            if len(selected) >= limit:
                break
            if name not in selected:
                selected.append(name)
        return selected

    def catalogue(self) -> list[dict[str, Any]]:
        """The human- and model-readable catalogue of this registry."""
        return [
            {
                "name": spec.name,
                "family": spec.family,
                "summary": spec.summary,
                "service": spec.service,
                "data_source": spec.data_source,
                "permissions": list(spec.permissions),
                "read_only": spec.read_only,
                "timeout_seconds": spec.timeout_seconds,
                "max_items": spec.max_items,
                "input": spec.input_model.model_json_schema(),
            }
            for spec in self.specs()
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        principal: Any = None,
        session: Any = None,
    ) -> ToolResult:
        """Validate, authorise and run one tool. Never raises for tool problems."""
        started = time.perf_counter()
        arguments = arguments or {}
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(
                tool=name,
                status=ToolStatus.ERROR,
                error=f"unknown tool '{name}'",
                arguments=arguments,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        try:
            validated = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(
                tool=name,
                status=ToolStatus.ERROR,
                error=f"invalid arguments for '{name}': {exc.error_count()} problem(s)",
                message=exc.errors()[0].get("msg") if exc.errors() else None,
                arguments=arguments,
                service=spec.service,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        if spec.permissions:
            granted = set(getattr(principal, "permissions", frozenset()) or frozenset())
            missing = [item for item in spec.permissions if item not in granted]
            if missing:
                return ToolResult(
                    tool=name,
                    status=ToolStatus.ERROR,
                    error=f"missing permission(s): {', '.join(missing)}",
                    arguments=validated.model_dump(),
                    service=spec.service,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )

        call_id = str(uuid.uuid4())
        try:
            result = await asyncio.wait_for(
                spec.handler(
                    session=session,
                    principal=principal,
                    call_id=call_id,
                    **validated.model_dump(),
                ),
                timeout=spec.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool=name,
                status=ToolStatus.ERROR,
                error=f"tool '{name}' exceeded its {spec.timeout_seconds:.0f}s budget",
                arguments=validated.model_dump(),
                service=spec.service,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except ToolError as exc:
            return ToolResult(
                tool=name,
                status=exc.status,
                error=exc.message,
                arguments=validated.model_dump(),
                service=spec.service,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - a tool failure must not leak internals
            logger.warning("tool %s failed: %s: %s", name, type(exc).__name__, exc)
            return ToolResult(
                tool=name,
                status=ToolStatus.ERROR,
                error=f"tool '{name}' failed ({type(exc).__name__})",
                arguments=validated.model_dump(),
                service=spec.service,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        result.latency_ms = int((time.perf_counter() - started) * 1000)
        result.tool = name
        result.service = result.service or spec.service
        result.arguments = validated.model_dump()
        return result
