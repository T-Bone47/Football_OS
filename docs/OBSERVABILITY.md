# Observability & Diagnostic Telemetry Architecture

## Overview
Phase 8 implements an enterprise-grade observability and telemetry subsystem designed for auditability, traceability, and high operational reliability.

---

## 1. Structured JSON Logging Architecture

All logging across application layers is standardized using `JSONLogFormatter` in `app.observability.logging`.

### Log Record Schema
```json
{
  "timestamp": "2026-09-26T03:30:00.123456Z",
  "level": "INFO",
  "logger": "app.decisions.recruitment",
  "message": "Candidate evaluation completed for pos=MF, limit=5",
  "correlation_id": "c9a41b7e-9081-4b11-97ea-1678229df831",
  "environment": "production",
  "extra_context": {
    "candidates_evaluated": 20,
    "passed_constraints": 14
  }
}
```

### Sensitive Data Redaction Policies
To prevent credential leakage in logs, `RedactingFormatter` automatically scrubs all fields matching sensitive patterns before emission:
- **Redacted Tokens**: `api_key`, `token`, `password`, `secret`, `authorization`, `cookie`, `database_url`.
- **Masking Format**: Replaced with `[REDACTED]`.
- Verified in `tests/unit/test_observability.py::TestStructuredLoggingAndRedaction`.

---

## 2. Distributed Correlation & Request Tracing

Correlation tracking ensures that every incoming request, background task, and analytical calculation shares a unified trace ID.

- **Middleware**: `CorrelationIdMiddleware` in `app.observability.correlation`.
- **Header Propagation**:
  - Inbound: Accepts `X-Correlation-ID` or `X-Request-ID`.
  - Generation: If neither header is present, generates a canonical UUIDv4.
  - Outbound: Emits `X-Correlation-ID` on every HTTP response.
- **Context Storage**: Stored in a Python `contextvars.ContextVar[str]`, ensuring thread-safe, task-safe propagation across asynchronous calls.

---

## 3. Production Diagnostic & Health Endpoints

The API exposes four dedicated health endpoints adhering to the **Truthful State Surface** requirement:

### 3.1 Application Health (`GET /health`)
Verifies process liveness, uptime, and host operating conditions:
- Process uptime in seconds.
- Memory usage (RSS and VMS) via `psutil`.
- CPU utilization percentage.
- Active Python and platform runtime version.

### 3.2 Infrastructure Readiness (`GET /readiness`)
Verifies upstream and persistent dependencies:
- Executes `SELECT 1` against PostgreSQL via SQLAlchemy async session.
- Validates connection pool health.
- Emits HTTP 503 if the database or core storage is unreachable.

### 3.3 Model Health & Governance Status (`GET /model-status`)
Surfaces registered models and calibration readiness:
- Lists all active models in `governance_registry`.
- Reports validation status (`MODEL_VALIDATED`, `SHADOW`, `DEPRECATED`).
- Displays benchmark metrics (Brier Score, ECE, Log Loss, Training Cutoff).

### 3.4 Data Quality & Ingestion Status (`GET /data-status`)
Audits dataset integrity, missingness, and cadence:
- Verifies player, club, match, and feature dataset row counts.
- Evaluates null rates and missingness across required feature columns.
- Flags data status as `HEALTHY`, `DEGRADED`, or `UNHEALTHY`.
- Enforces zero synthetic green checks.

---

## 4. Telemetry Metrics & Quality Drift Indicators

The platform computes real-time operational metrics for model and decision quality:

| Metric | Purpose | Threshold Alert |
|---|---|---|
| **Population Stability Index (PSI)** | Quantifies distribution shift in player ratings and probabilities | PSI > 0.25 (Drift Detected) |
| **Brier Score** | Mean squared difference between predicted probabilities and binary outcomes | Brier > 0.22 (Calibration Drift) |
| **Expected Calibration Error (ECE)** | Absolute divergence between confidence bins and empirical win rates | ECE > 0.08 (Miscalibration) |
| **Log Loss** | Probabilistic penalty penalizing overconfident false predictions | Log Loss > 1.05 |
| **Evidence DAG Hash Mismatch** | Detects non-deterministic graph construction or mutation | Any difference (Reproducibility Alert) |
