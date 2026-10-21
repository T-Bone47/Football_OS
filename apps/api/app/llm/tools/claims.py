"""Deterministic claim validation.

The model's prose is checked against the evidence that was actually retrieved.
Two classes of claim are checked:

* **Numerical claims** - any number in the answer is compared with the numbers that
  appear in the evidence (or in the tool payloads). A number that appears nowhere in
  the retrieved evidence is *unsupported*: it is either a typo, a hallucination, or a
  value the model derived and did not label.
* **Entity references** - a canonical id that is mentioned in the answer must exist in
  the retrieved evidence.

The validator never rewrites the answer. It produces a report that the API returns
alongside the answer and that the frontend can surface, so a user can see exactly
which numbers were checked and which were not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.llm.tools.base import Evidence

# Numbers as they appear in prose: 12, 12.5, 1,200, 4-3-3 is not a number we check.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w])")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass
class ClaimValidationReport:
    """The outcome of checking an answer against its evidence."""

    supported_numbers: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    unsupported_values: list[dict[str, Any]] = field(default_factory=list)
    unknown_entity_ids: list[str] = field(default_factory=list)
    known_entity_ids: list[str] = field(default_factory=list)
    evidence_count: int = 0
    tool_count: int = 0
    checked: bool = True

    @property
    def grounded(self) -> bool:
        """True when nothing in the answer contradicts the retrieved evidence."""
        return not self.unsupported_numbers and not self.unknown_entity_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "grounded": self.grounded,
            "evidence_count": self.evidence_count,
            "tool_count": self.tool_count,
            "supported_numbers": sorted(self.supported_numbers)[:60],
            "unsupported_numbers": sorted(self.unsupported_numbers)[:60],
            "unsupported_values": self.unsupported_values[:30],
            "unknown_entity_ids": self.unknown_entity_ids[:20],
            "known_entity_ids": self.known_entity_ids[:40],
        }


def _normalise_number(raw: str) -> str:
    cleaned = raw.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return cleaned
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _evidence_numbers(evidence: Iterable[Evidence]) -> set[str]:
    numbers: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            numbers.add(_normalise_number(str(value)))
            return
        if isinstance(value, str):
            for match in _NUMBER.findall(value):
                numbers.add(_normalise_number(match))
            return
        if isinstance(value, dict):
            for item in value.values():
                add(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)

    for item in evidence:
        add(item.value)
        if item.sample_size is not None:
            add(item.sample_size)
        # The season/competition a measurement belongs to is part of its provenance:
        # quoting that season is a grounded statement, not an invented number.
        if item.season:
            add(item.season)
        if item.competition:
            for match in _NUMBER.findall(item.competition):
                numbers.add(_normalise_number(match))
    return numbers


def _payload_numbers(payloads: Iterable[Any]) -> set[str]:
    numbers: set[str] = set()

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            numbers.add(_normalise_number(str(node)))
        elif isinstance(node, str):
            for match in _NUMBER.findall(node):
                numbers.add(_normalise_number(match))
        elif isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str):
                    for match in _NUMBER.findall(key):
                        numbers.add(_normalise_number(match))
                walk(value, depth + 1)
        elif isinstance(node, (list, tuple, set)):
            for value in node:
                walk(value, depth + 1)

    for payload in payloads:
        walk(payload)
    return numbers


def _merge_space_thousands(answer: str, available: set[str]) -> str:
    """Join ``2 514`` into ``2514`` when that value is in the evidence.

    The model writes large numbers with a space separator; the evidence stores them
    as plain integers. Only a merge that matches a known value is applied, so
    "2023 2024" is never turned into one number.
    """
    pattern = re.compile(r"(?<![\w.])(\d{1,3})[   ](\d{3})(?![\w])")
    result = answer
    for match in pattern.finditer(answer):
        merged = match.group(1) + match.group(2)
        if merged in available:
            result = result.replace(match.group(0), merged)
    return result


def validate_answer(
    answer: str,
    evidence: list[Evidence],
    tool_payloads: list[Any] | None = None,
    *,
    known_entity_ids: Iterable[str] | None = None,
) -> ClaimValidationReport:
    """Check the numbers and entity ids in an answer against the retrieved evidence."""
    report = ClaimValidationReport(
        evidence_count=len(evidence),
        tool_count=len(tool_payloads or []),
    )
    if not answer or not answer.strip():
        report.checked = False
        return report

    available = _evidence_numbers(evidence) | _payload_numbers(tool_payloads or [])
    text = _merge_space_thousands(answer, available)

    for raw in _NUMBER.findall(text):
        normalised = _normalise_number(raw)
        if normalised in available:
            report.supported_numbers.append(normalised)
            continue
        # 1 234 written as 1234, or 87.0 written as 87: try the numeric value too.
        try:
            value = float(normalised)
        except ValueError:
            value = None
        if value is not None and any(
            abs(value - float(candidate)) < 0.0001
            for candidate in available
            if _is_number(candidate)
        ):
            report.supported_numbers.append(normalised)
            continue
        report.unsupported_numbers.append(normalised)
        report.unsupported_values.append({"value": normalised, "kind": "number"})

    evidence_ids = {item.entity_id for item in evidence if item.entity_id}
    extra_ids = set(known_entity_ids or [])
    for identifier in _UUID.findall(answer):
        if identifier in evidence_ids or identifier in extra_ids:
            report.known_entity_ids.append(identifier)
        else:
            report.unknown_entity_ids.append(identifier)
    return report


def _is_number(candidate: str) -> bool:
    try:
        float(candidate)
    except (TypeError, ValueError):
        return False
    return True
