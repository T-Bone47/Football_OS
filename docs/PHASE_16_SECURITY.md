# Phase 16: Security Architecture, RBAC & Append-Only Audit Trail

## 1. Role-Based Access Control (RBAC)
Authoritative backend role governance enforces permissions per persona:
- **`VIEWER`**: Read-only access to dashboards, player profiles, and published decisions.
- **`SCOUT`**: Search players, manage shortlists, create watchlists, evaluate scouting notes.
- **`ANALYST`**: Run scenarios, inspect tactical fit, query models, execute counterfactual simulations.
- **`DECISION_MAKER`**: Author and approve recruitment decisions, set transfer targets, modify squad budget allocations.
- **`DATA_ENGINEER`**: Trigger ingestion runs, configure provider credentials, manage data pipelines.
- **`ADMIN`**: Model promotion, system configuration, role assignments, audit chain inspection.

Unauthorized operations return HTTP 403 Forbidden with security audit logging.

## 2. Cryptographic Append-Only Audit Trail
- Every critical mutation produces an immutable `AuditEvent`.
- Events are chained using cryptographic SHA-256 hashes ($H_k = \text{SHA256}(E_k \parallel H_{k-1})$).
- Automated regex redaction scrubs sensitive keys (`api_key`, `token`, `password`, `secret`) from log details prior to hashing.
- Integrity verification detects any retrospective database record tampering.
