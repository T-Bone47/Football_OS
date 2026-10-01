# Phase 16: Data Quality Engine & Incident Management

## 1. Automated Validation Checks
All ingested data batches pass through deterministic validation checks:
1. **Pitch Coordinate Validity**:
   - $x \in [0.0, 120.0]$
   - $y \in [0.0, 80.0]$
   - Out-of-bounds coordinates trigger check failure and row rejection.
2. **Temporal Event Bounds**:
   - Minute must be within $0 \le t \le 130$.
   - Negative minutes or excessive injury times are rejected.
3. **Identifier Integrity**:
   - Every entity must possess a unique identifier or deterministic composite key.
4. **Referential Integrity**:
   - Match events must reference known fixtures and registered player rosters.

## 2. Incident Lifecycle
- Violations automatically create a tracked Incident (`report_incident`).
- Incident fields: `incident_id`, `severity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `source`, `resource`, `affected_records`, `diagnosis`, `remediation`, `status`.
- Incidents remain `OPEN` until verified remediation is performed, transitioning to `RESOLVED` with root-cause attribution.
