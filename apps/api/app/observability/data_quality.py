"""Data Quality & Decision Quality Monitoring Framework (Phase 8 Sections 6 & 8).

Features:
- Automated missingness & null-rate calculation per dimension
- Entity duplicate detection
- Domain boundary validation (invalid values: negative fees, impossible minutes, etc.)
- Stale data detection based on temporal freshness
- Provenance gap auditing
- Coverage calculation
- Schema drift detection
- Explicit Data & Decision Quality States:
  DATA_COMPLETE, PARTIAL_EVIDENCE, INSUFFICIENT_DATA,
  OUT_OF_DISTRIBUTION, HARD_CONSTRAINT_EXCLUDED, HIGH_UNCERTAINTY.
- Zero-fabrication enforcement policy: never replace missing data with fabricated values.
- Invariant: never convert incomplete evidence into a confident decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Sequence


class DataQualityState(str, Enum):
    DATA_COMPLETE = "DATA_COMPLETE"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    HARD_CONSTRAINT_EXCLUDED = "HARD_CONSTRAINT_EXCLUDED"
    HIGH_UNCERTAINTY = "HIGH_UNCERTAINTY"


@dataclass
class ColumnQualityReport:
    """Quality metrics for a single feature/column."""
    column_name: str
    total_records: int
    null_count: int
    null_rate: float
    invalid_count: int
    distinct_count: int


@dataclass
class DataQualityAuditReport:
    """Overall dataset quality assessment."""
    dataset_name: str
    total_records: int
    overall_missingness_rate: float
    quality_state: DataQualityState
    duplicate_entities_count: int
    stale_records_count: int
    provenance_gaps_count: int
    schema_drift_detected: bool
    schema_drift_details: list[str]
    column_reports: dict[str, ColumnQualityReport]
    audit_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["quality_state"] = self.quality_state.value
        return res


class DataQualityMonitor:
    """Monitors canonical and analytical datasets against strict quality standards."""

    @staticmethod
    def audit_tabular_data(
        records: Sequence[dict[str, Any]],
        dataset_name: str,
        required_fields: Sequence[str],
        identity_fields: Sequence[str] | None = None,
        validation_rules: dict[str, Callable[[Any], bool]] | None = None,
        max_age_days: int = 90,
        expected_schema: dict[str, type] | None = None,
    ) -> DataQualityAuditReport:
        """Executes full quality inspection over a collection of records."""
        total = len(records)
        if total == 0:
            return DataQualityAuditReport(
                dataset_name=dataset_name,
                total_records=0,
                overall_missingness_rate=1.0,
                quality_state=DataQualityState.INSUFFICIENT_DATA,
                duplicate_entities_count=0,
                stale_records_count=0,
                provenance_gaps_count=0,
                schema_drift_detected=False,
                schema_drift_details=["Empty dataset provided"],
                column_reports={},
            )

        identity_fields = identity_fields or []
        validation_rules = validation_rules or {}

        # 1. Column-level analysis
        column_reports: dict[str, ColumnQualityReport] = {}
        all_keys = set(required_fields)
        for r in records:
            all_keys.update(r.keys())

        total_null_entries = 0
        total_cells = total * len(all_keys)

        for col in all_keys:
            vals = [r.get(col) for r in records]
            nulls = sum(1 for v in vals if v is None or (isinstance(v, str) and not v.strip()))
            total_null_entries += nulls

            # Validate domain bounds
            invalid_count = 0
            if col in validation_rules:
                rule = validation_rules[col]
                for v in vals:
                    if v is not None and not rule(v):
                        invalid_count += 1

            distinct = len({str(v) for v in vals if v is not None})
            column_reports[col] = ColumnQualityReport(
                column_name=col,
                total_records=total,
                null_count=nulls,
                null_rate=round(nulls / total, 4),
                invalid_count=invalid_count,
                distinct_count=distinct,
            )

        overall_missingness = round(total_null_entries / max(1, total_cells), 4)

        # 2. Duplicate detection
        duplicate_count = 0
        if identity_fields:
            seen: set[tuple] = set()
            for r in records:
                ident = tuple(r.get(f) for f in identity_fields)
                if ident in seen:
                    duplicate_count += 1
                else:
                    seen.add(ident)

        # 3. Provenance gap detection
        prov_gaps = 0
        for r in records:
            has_prov = False
            for k in ("provenance", "source", "provider_id", "source_file"):
                if r.get(k):
                    has_prov = True
                    break
            if not has_prov:
                prov_gaps += 1

        # 4. Stale record detection
        stale_count = 0
        now = datetime.now(timezone.utc)
        for r in records:
            dt_val = r.get("updated_at") or r.get("created_at") or r.get("as_of")
            if dt_val:
                try:
                    if isinstance(dt_val, str):
                        dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
                    elif isinstance(dt_val, datetime):
                        dt = dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=timezone.utc)
                    else:
                        dt = None
                    if dt and (now - dt).days > max_age_days:
                        stale_count += 1
                except Exception:
                    pass

        # 5. Schema drift detection
        drift_details: list[str] = []
        if expected_schema:
            for field_name, expected_type in expected_schema.items():
                if field_name not in all_keys:
                    drift_details.append(f"Missing expected field: '{field_name}'")
                else:
                    # Sample non-null values for type check
                    non_nulls = [r[field_name] for r in records if r.get(field_name) is not None]
                    if non_nulls and not all(isinstance(v, expected_type) for v in non_nulls[:10]):
                        drift_details.append(f"Type drift in '{field_name}': expected {expected_type}")

        # 6. Synthesize Quality State
        if overall_missingness > 0.40 or any(column_reports[f].null_rate > 0.50 for f in required_fields):
            quality_state = DataQualityState.INSUFFICIENT_DATA
        elif overall_missingness > 0.15 or prov_gaps > 0:
            quality_state = DataQualityState.PARTIAL_EVIDENCE
        elif any(cr.invalid_count > 0 for cr in column_reports.values()):
            quality_state = DataQualityState.HIGH_UNCERTAINTY
        else:
            quality_state = DataQualityState.DATA_COMPLETE

        return DataQualityAuditReport(
            dataset_name=dataset_name,
            total_records=total,
            overall_missingness_rate=overall_missingness,
            quality_state=quality_state,
            duplicate_entities_count=duplicate_count,
            stale_records_count=stale_count,
            provenance_gaps_count=prov_gaps,
            schema_drift_detected=len(drift_details) > 0,
            schema_drift_details=drift_details,
            column_reports=column_reports,
        )


def enforce_decision_confidence_invariants(
    quality_state: DataQualityState | str,
    confidence_tier: str,
    decision_confidence: float,
) -> tuple[str, float]:
    """
    CRITICAL POLICY: Never convert incomplete or OOD evidence into a confident decision.
    If quality_state indicates partial/insufficient data or OOD, tier CANNOT be HIGH.
    """
    q_str = quality_state.value if isinstance(quality_state, DataQualityState) else str(quality_state)

    if q_str in (
        DataQualityState.INSUFFICIENT_DATA.value,
        DataQualityState.PARTIAL_EVIDENCE.value,
        DataQualityState.OUT_OF_DISTRIBUTION.value,
        DataQualityState.HIGH_UNCERTAINTY.value,
    ):
        if confidence_tier == "HIGH":
            # Demote tier to MODERATE or LOW
            confidence_tier = "MODERATE" if q_str == DataQualityState.PARTIAL_EVIDENCE.value else "LOW"
            decision_confidence = min(decision_confidence, 0.65)

    return confidence_tier, decision_confidence
