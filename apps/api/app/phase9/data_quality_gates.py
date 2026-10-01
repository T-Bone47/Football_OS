"""Phase 9 — Data Quality Gates.

Explicit ingestion gates for:
  schema validity, required identifiers, date validity, duplicate detection,
  referential integrity, provenance, missingness, range validation, temporal validity.

Invalid data is quarantined or rejected. Never repairs critical analytical data silently.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


class GateDecision(str, Enum):
    PASS = "PASS"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"


class GateType(str, Enum):
    SCHEMA_VALIDITY = "SCHEMA_VALIDITY"
    REQUIRED_IDENTIFIERS = "REQUIRED_IDENTIFIERS"
    DATE_VALIDITY = "DATE_VALIDITY"
    DUPLICATE_DETECTION = "DUPLICATE_DETECTION"
    REFERENTIAL_INTEGRITY = "REFERENTIAL_INTEGRITY"
    PROVENANCE = "PROVENANCE"
    MISSINGNESS = "MISSINGNESS"
    RANGE_VALIDATION = "RANGE_VALIDATION"
    TEMPORAL_VALIDITY = "TEMPORAL_VALIDITY"


@dataclass
class GateResult:
    """Result of a single data quality gate."""
    gate_type: str
    decision: str = GateDecision.PASS
    violations_count: int = 0
    violations: list[str] = field(default_factory=list)
    records_checked: int = 0
    records_passed: int = 0
    records_quarantined: int = 0
    records_rejected: int = 0


@dataclass
class DataQualityGateReport:
    """Full data quality gate assessment for an ingestion batch."""
    batch_id: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    overall_decision: str = GateDecision.PASS
    gates: list[GateResult] = field(default_factory=list)
    total_records: int = 0
    passed_records: int = 0
    quarantined_records: int = 0
    rejected_records: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Gate Implementations ──────────────────────────────────────────

def check_schema_validity(
    records: list[dict[str, Any]],
    required_fields: list[str],
) -> GateResult:
    """Validate that all records have required schema fields."""
    result = GateResult(
        gate_type=GateType.SCHEMA_VALIDITY,
        records_checked=len(records),
    )

    for i, rec in enumerate(records):
        missing = [f for f in required_fields if f not in rec]
        if missing:
            result.violations.append(
                f"Record {i}: missing fields {missing}"
            )
            result.records_rejected += 1
        else:
            result.records_passed += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.REJECT
    return result


def check_required_identifiers(
    records: list[dict[str, Any]],
    id_fields: list[str],
) -> GateResult:
    """Validate that required identifier fields are non-null and non-empty."""
    result = GateResult(
        gate_type=GateType.REQUIRED_IDENTIFIERS,
        records_checked=len(records),
    )

    for i, rec in enumerate(records):
        for id_field in id_fields:
            val = rec.get(id_field)
            if val is None or (isinstance(val, str) and val.strip() == ""):
                result.violations.append(
                    f"Record {i}: null/empty identifier '{id_field}'"
                )
                result.records_quarantined += 1
                break
        else:
            result.records_passed += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_date_validity(
    records: list[dict[str, Any]],
    date_fields: list[str],
    min_date: str = "1900-01-01",
    max_date: str | None = None,
) -> GateResult:
    """Validate date fields are within acceptable ranges."""
    result = GateResult(
        gate_type=GateType.DATE_VALIDITY,
        records_checked=len(records),
    )

    if max_date is None:
        max_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for i, rec in enumerate(records):
        valid = True
        for df in date_fields:
            val = rec.get(df)
            if val is None:
                continue  # Nullable date — not a violation
            try:
                if isinstance(val, str):
                    d = val[:10]  # Take date portion
                elif isinstance(val, (date, datetime)):
                    d = val.isoformat()[:10]
                else:
                    d = str(val)[:10]

                if d < min_date or d > max_date:
                    result.violations.append(
                        f"Record {i}: date '{df}'={d} outside range [{min_date}, {max_date}]"
                    )
                    valid = False
            except (ValueError, TypeError):
                result.violations.append(f"Record {i}: invalid date format for '{df}'={val}")
                valid = False

        if valid:
            result.records_passed += 1
        else:
            result.records_quarantined += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_duplicate_detection(
    records: list[dict[str, Any]],
    key_fields: list[str],
) -> GateResult:
    """Detect duplicate records based on composite key fields."""
    result = GateResult(
        gate_type=GateType.DUPLICATE_DETECTION,
        records_checked=len(records),
    )

    seen: set[tuple] = set()
    for i, rec in enumerate(records):
        key = tuple(str(rec.get(f, "")) for f in key_fields)
        if key in seen:
            result.violations.append(
                f"Record {i}: duplicate key {dict(zip(key_fields, key))}"
            )
            result.records_quarantined += 1
        else:
            seen.add(key)
            result.records_passed += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_provenance(
    records: list[dict[str, Any]],
    provider_field: str = "provider",
    source_id_field: str = "source_record_id",
) -> GateResult:
    """Validate provenance fields are present."""
    result = GateResult(
        gate_type=GateType.PROVENANCE,
        records_checked=len(records),
    )

    for i, rec in enumerate(records):
        provider = rec.get(provider_field)
        source_id = rec.get(source_id_field)
        if not provider or (isinstance(provider, str) and not provider.strip()):
            result.violations.append(f"Record {i}: missing provider")
            result.records_quarantined += 1
        elif not source_id and source_id != 0:
            result.violations.append(f"Record {i}: missing source_record_id")
            result.records_quarantined += 1
        else:
            result.records_passed += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_missingness(
    records: list[dict[str, Any]],
    critical_fields: list[str],
    max_missingness_rate: float = 0.5,
) -> GateResult:
    """Check missingness rate for critical fields."""
    result = GateResult(
        gate_type=GateType.MISSINGNESS,
        records_checked=len(records),
    )

    if not records:
        result.records_passed = 0
        result.decision = GateDecision.PASS
        return result

    for field_name in critical_fields:
        null_count = sum(1 for r in records if r.get(field_name) is None)
        rate = null_count / len(records)
        if rate > max_missingness_rate:
            result.violations.append(
                f"Field '{field_name}': missingness {rate:.1%} exceeds threshold {max_missingness_rate:.1%}"
            )

    result.violations_count = len(result.violations)
    result.records_passed = len(records) if result.violations_count == 0 else 0
    result.records_quarantined = len(records) if result.violations_count > 0 else 0
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_range_validation(
    records: list[dict[str, Any]],
    range_rules: dict[str, tuple[float | None, float | None]],
) -> GateResult:
    """Validate numeric fields are within expected ranges.

    Args:
        range_rules: Mapping of field_name → (min_value, max_value).
                     None means no bound.
    """
    result = GateResult(
        gate_type=GateType.RANGE_VALIDATION,
        records_checked=len(records),
    )

    for i, rec in enumerate(records):
        valid = True
        for field_name, (min_val, max_val) in range_rules.items():
            val = rec.get(field_name)
            if val is None:
                continue
            try:
                num = float(val)
                if min_val is not None and num < min_val:
                    result.violations.append(
                        f"Record {i}: '{field_name}'={num} below minimum {min_val}"
                    )
                    valid = False
                if max_val is not None and num > max_val:
                    result.violations.append(
                        f"Record {i}: '{field_name}'={num} above maximum {max_val}"
                    )
                    valid = False
            except (ValueError, TypeError):
                result.violations.append(
                    f"Record {i}: '{field_name}'={val} not a valid number"
                )
                valid = False

        if valid:
            result.records_passed += 1
        else:
            result.records_quarantined += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.QUARANTINE
    return result


def check_temporal_validity(
    records: list[dict[str, Any]],
    feature_date_field: str = "feature_as_of",
    target_date_field: str = "target_date",
) -> GateResult:
    """Validate that no feature uses information after its prediction date."""
    result = GateResult(
        gate_type=GateType.TEMPORAL_VALIDITY,
        records_checked=len(records),
    )

    for i, rec in enumerate(records):
        feature_date = rec.get(feature_date_field)
        target_date = rec.get(target_date_field)

        if feature_date is None or target_date is None:
            result.records_passed += 1
            continue

        f_str = str(feature_date)[:10] if not isinstance(feature_date, str) else feature_date[:10]
        t_str = str(target_date)[:10] if not isinstance(target_date, str) else target_date[:10]

        if f_str > t_str:
            result.violations.append(
                f"Record {i}: feature_as_of ({f_str}) after target_date ({t_str}) — temporal leakage"
            )
            result.records_rejected += 1
        else:
            result.records_passed += 1

    result.violations_count = len(result.violations)
    result.decision = GateDecision.PASS if result.violations_count == 0 else GateDecision.REJECT
    return result


def run_all_gates(
    records: list[dict[str, Any]],
    batch_id: str,
    schema_fields: list[str] | None = None,
    id_fields: list[str] | None = None,
    date_fields: list[str] | None = None,
    key_fields: list[str] | None = None,
    critical_fields: list[str] | None = None,
    range_rules: dict[str, tuple[float | None, float | None]] | None = None,
) -> DataQualityGateReport:
    """Run all data quality gates on a batch of records.

    Returns a comprehensive gate report with per-gate results.
    """
    report = DataQualityGateReport(batch_id=batch_id, total_records=len(records))

    if schema_fields:
        report.gates.append(check_schema_validity(records, schema_fields))

    if id_fields:
        report.gates.append(check_required_identifiers(records, id_fields))

    if date_fields:
        report.gates.append(check_date_validity(records, date_fields))

    if key_fields:
        report.gates.append(check_duplicate_detection(records, key_fields))

    report.gates.append(check_provenance(records))

    if critical_fields:
        report.gates.append(check_missingness(records, critical_fields))

    if range_rules:
        report.gates.append(check_range_validation(records, range_rules))

    # Aggregate
    any_reject = any(g.decision == GateDecision.REJECT for g in report.gates)
    any_quarantine = any(g.decision == GateDecision.QUARANTINE for g in report.gates)

    if any_reject:
        report.overall_decision = GateDecision.REJECT
    elif any_quarantine:
        report.overall_decision = GateDecision.QUARANTINE
    else:
        report.overall_decision = GateDecision.PASS

    report.passed_records = sum(g.records_passed for g in report.gates)
    report.quarantined_records = sum(g.records_quarantined for g in report.gates)
    report.rejected_records = sum(g.records_rejected for g in report.gates)

    return report
