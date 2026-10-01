"""Provider contract drift detection (§39).

A contract is (a) code-reviewed key fields and enum domains per
provider/resource and (b) the field types observed in a real registered
snapshot. A new payload is compared against both before it may reach
Silver. Breaking drift returns INGESTION_BLOCKED; the Bronze bytes are kept
(raw capture is never gated) but nothing is normalized from them.

Blocking: a key field missing from any record, a key field changing type,
a key field becoming null where the contract never saw null, or a key enum
taking a value outside its registered domain.
Warning only: new fields, non-key type changes, non-key fields absent
(event streams are heterogeneous: a match without a red card has no card
fields, and that is not drift).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import ContractFingerprint


class ContractStatus(str, Enum):
    CONTRACT_OK = "CONTRACT_OK"
    CONTRACT_WARN = "CONTRACT_WARN"
    INGESTION_BLOCKED = "INGESTION_BLOCKED"
    NO_CONTRACT = "NO_CONTRACT"


@dataclass(frozen=True)
class ContractSpec:
    record_path: str  # "" = payload is a list of records; "lineup[]" = nested list
    key_fields: tuple[str, ...]
    enums: dict[str, frozenset] = field(default_factory=dict)


CONTRACT_SPECS: dict[tuple[str, str], ContractSpec] = {
    ("statsbomb", "competitions"): ContractSpec(
        "", ("competition_id", "season_id", "competition_name", "season_name", "country_name"),
    ),
    ("statsbomb", "matches"): ContractSpec(
        "",
        ("match_id", "match_date", "home_score", "away_score", "home_team.home_team_id",
         "home_team.home_team_name", "away_team.away_team_id", "away_team.away_team_name",
         "competition.competition_id", "season.season_name"),
        {"match_status": frozenset({"available"})},
    ),
    ("statsbomb", "lineups"): ContractSpec(
        "", ("team_id", "team_name", "lineup", "lineup[].player_id", "lineup[].player_name"),
    ),
    ("statsbomb", "events"): ContractSpec(
        "", ("id", "index", "period", "minute", "type.name", "team.id"),
        {"period": frozenset({1, 2, 3, 4, 5})},
    ),
}


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def _walk(obj: Any, prefix: str, out: dict[str, set[str]], depth: int) -> None:
    if not isinstance(obj, dict) or depth > 3:
        return
    for k, v in obj.items():
        path = f"{prefix}{k}"
        out.setdefault(path, set()).add(_type_name(v))
        if isinstance(v, dict):
            _walk(v, f"{path}.", out, depth + 1)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            for item in v:
                _walk(item, f"{path}[].", out, depth + 1)


def observe_field_types(payload: Any) -> dict[str, list[str]]:
    records = payload if isinstance(payload, list) else [payload]
    seen: dict[str, set[str]] = {}
    for r in records:
        _walk(r, "", seen, 0)
    return {k: sorted(v) for k, v in sorted(seen.items())}


def _get_path(record: dict[str, Any], path: str) -> list[Any]:
    """Values at a dotted path; '[]' fans out over list items. Missing -> []."""
    current: list[Any] = [record]
    for part in path.split("."):
        is_list = part.endswith("[]")
        key = part[:-2] if is_list else part
        nxt: list[Any] = []
        for c in current:
            if not isinstance(c, dict) or key not in c:
                return [_MISSING]
            v = c[key]
            if is_list:
                nxt.extend(v if isinstance(v, list) else [_MISSING])
            else:
                nxt.append(v)
        current = nxt
    return current


_MISSING = object()


def fingerprint(spec: ContractSpec, field_types: dict[str, list[str]]) -> str:
    keyed = {k: field_types.get(k, ["<absent>"]) for k in spec.key_fields}
    return hashlib.sha256(json.dumps(keyed, sort_keys=True).encode()).hexdigest()


@dataclass
class ContractCheck:
    provider: str
    resource: str
    status: ContractStatus
    findings: list[dict[str, Any]] = field(default_factory=list)
    observed_fingerprint: str | None = None
    registered_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "resource": self.resource,
            "status": self.status.value,
            "findings": self.findings,
            "observed_fingerprint": self.observed_fingerprint,
            "registered_fingerprint": self.registered_fingerprint,
        }


def check_contract(
    provider: str,
    resource: str,
    payload: Any,
    registered_types: dict[str, list[str]] | None,
) -> ContractCheck:
    spec = CONTRACT_SPECS.get((provider, resource))
    if spec is None:
        return ContractCheck(provider, resource, ContractStatus.NO_CONTRACT,
                             [{"severity": "WARN", "kind": "NO_CONTRACT",
                               "detail": "no contract registered; Silver promotion not contract-gated"}])
    records = payload if isinstance(payload, list) else None
    if records is None:
        return ContractCheck(provider, resource, ContractStatus.INGESTION_BLOCKED,
                             [{"severity": "BLOCK", "kind": "ENVELOPE_CHANGED",
                               "detail": f"expected a JSON list, got {_type_name(payload)}"}])

    observed = observe_field_types(records)
    findings: list[dict[str, Any]] = []

    for key in spec.key_fields:
        missing = 0
        nulls = 0
        for r in records:
            values = _get_path(r, key)
            if any(v is _MISSING for v in values):
                missing += 1
            elif any(v is None for v in values):
                nulls += 1
        if missing:
            findings.append({"severity": "BLOCK", "kind": "MISSING_FIELD", "field": key, "records": missing})
        if nulls and registered_types is not None and "null" not in registered_types.get(key, []):
            findings.append({"severity": "BLOCK", "kind": "UNEXPECTED_NULL", "field": key, "records": nulls})

    for enum_field, domain in spec.enums.items():
        values = {v for r in records for v in _get_path(r, enum_field) if v is not _MISSING}
        unexpected = sorted(str(v) for v in values - set(domain))
        if unexpected:
            findings.append({"severity": "BLOCK", "kind": "ENUM_CHANGED", "field": enum_field, "values": unexpected})

    if registered_types is not None:
        for key in spec.key_fields:
            before = {t for t in registered_types.get(key, []) if t != "null"}
            after = {t for t in observed.get(key, []) if t != "null"}
            if before and after and not after <= before and not (after <= {"int", "float"} and before <= {"int", "float"}):
                findings.append({"severity": "BLOCK", "kind": "TYPE_CHANGED", "field": key,
                                 "registered": sorted(before), "observed": sorted(after)})
        missing_keys = [k for k in spec.key_fields if any(f["field"] == k and f["kind"] == "MISSING_FIELD"
                                                          for f in findings if "field" in f)]
        new_fields = sorted(set(observed) - set(registered_types))
        for nf in new_fields:
            findings.append({"severity": "WARN", "kind": "NEW_FIELD", "field": nf})
        # A rename looks like a missing key field plus a new field of the same
        # parent and type. Report it; the block already comes from MISSING_FIELD.
        for mk in missing_keys:
            parent = mk.rsplit(".", 1)[0] if "." in mk else ""
            for nf in new_fields:
                nf_parent = nf.rsplit(".", 1)[0] if "." in nf else ""
                if nf_parent == parent and observed.get(nf) == registered_types.get(mk):
                    findings.append({"severity": "BLOCK", "kind": "POSSIBLE_RENAME", "from": mk, "to": nf})

    status = (
        ContractStatus.INGESTION_BLOCKED if any(f["severity"] == "BLOCK" for f in findings)
        else ContractStatus.CONTRACT_WARN if findings
        else ContractStatus.CONTRACT_OK
    )
    return ContractCheck(
        provider, resource, status, findings,
        observed_fingerprint=fingerprint(spec, observed),
        registered_fingerprint=fingerprint(spec, registered_types) if registered_types is not None else None,
    )


async def get_registered_types(session: AsyncSession, provider: str, resource: str) -> dict[str, list[str]] | None:
    row = (
        await session.execute(
            select(ContractFingerprint).where(
                ContractFingerprint.provider == provider, ContractFingerprint.resource == resource
            )
        )
    ).scalar_one_or_none()
    return row.field_types if row else None


async def register_contract(
    session: AsyncSession, provider: str, resource: str, payload: Any, snapshot_sha256: str
) -> ContractFingerprint:
    """Registers the observed field types of a snapshot that has passed the
    code-defined key-field check. Only called when no contract exists yet."""
    spec = CONTRACT_SPECS[(provider, resource)]
    observed = observe_field_types(payload)
    row = ContractFingerprint(
        provider=provider, resource=resource, fingerprint=fingerprint(spec, observed),
        field_types=observed, registered_from_snapshot=snapshot_sha256,
    )
    session.add(row)
    await session.flush()
    return row
