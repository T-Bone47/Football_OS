# Phase 17 — Security

Evidence: `tests/integration/test_phase17_adversarial.py` (30/30), `tests/unit/test_phase17_api_contract.py`, `docs/evidence/phase17/secret_scan.json`, `workflow_e2e.json` (`authorization_checks`), `frontend_validation.json`. This is **not** a third-party penetration test or a security certification.

## 1. Authentication and authorization (§22, §38)

Before Phase 17, identity was a `user_id` field in the request body, two listing endpoints had no access check at all, and `/api/auth/me` returned a hardcoded user (reconnaissance R9).

Phase 17 (`app/phase17/auth.py`):
- **Bearer tokens**: 32 random bytes, shown once at issuance (`POST /api/v1/ops/users`, ADMIN only). Only the SHA-256 is stored, and a token can be revoked (`is_active`).
- **Organization boundary**: no user sees another organization's projects, decisions, watchlists or alerts.
- **Project visibility**: PRIVATE projects are visible to the owner and the organization's ADMINs; ORGANIZATION projects to the whole organization. Modification needs the owner or an ADMIN.
- **Roles**: ADMIN, DATA_ENGINEER, ANALYST, SCOUT, RESEARCHER, VIEWER, each with an explicit permission set.
- **No enumeration**: a resource the caller may not see answers 404, like one that does not exist.
- **Per-identity API rate limit**: keyed on the authenticated user, held in Redis with a process-local fallback. Changing IPs, headers or body fields does not reset it.
- **Replay protection**: `Idempotency-Key` on decision creation returns the original record, not a duplicate.
- **Phase 16 routes**: the body-asserted-identity routes (projects, watchlists, jobs, alerts ack, promote, predict) still work in development/test for their own tests, and answer **410 Gone in staging/production**. Their seeded demo users are never created in hardened environments.

Measured over real HTTP (`workflow_e2e.json`): anonymous → 401; another organization's ADMIN reading a private project → 404, reading its decision → 404; SCOUT promoting a model → 403; ADMIN promoting without live evidence → 409. The contract test verifies that **all 45** `/api/v1/ops` operations refuse an anonymous caller.

## 2. Adversarial results (§38, §58)

| # | Attack | Result |
|---|---|---|
| 14 | Unauthorized project access / IDOR | 404 for same-org non-owner and other-org admin; 403 for viewer write; 401 without or with a forged token |
| 15 | Unauthorized model promotion | 403 plus audit event; ADMIN without evidence gets 409 plus audit event |
| 16 | Prompt injection | Copilot REFUSED, zero tool calls; no tool that writes exists |
| 17 | Secret exfiltration | key, tokens and secrets absent from every Copilot answer; tokens stored hashed |
| 18 | Fake alert insertion | no endpoint (405); DB CHECK rejects an alert without evidence |
| 19 | Fake operational status | status is probed; a broken store gives UNAVAILABLE / not HEALTHY |
| 28 | Configuration secret leakage | secrets absent from system status and error bodies; errors carry no connection strings |
| 29 | Audit log tampering | UPDATE/DELETE rejected by trigger; a superuser who disables the trigger is caught by the hash chain (first broken sequence number reported) |
| – | Injection (SQL) | all queries are SQLAlchemy-parameterized; Copilot query text never reaches a tool parameter |
| – | Malformed requests | Pydantic validation gives 422; UUID path parameters are validated |

The full list of 30 is in `PHASE_17_RELEASE_REPORT.md` §33.

## 3. Audit trail (§34, §43)

`ops_audit_events` is append-only (trigger) and hash-chained (`prev_hash` → `event_hash`). Appends are serialized with a transaction-scoped advisory lock, so concurrent writers cannot fork the chain. Details are redacted recursively by key name and by value; bearer tokens embedded in strings are redacted too. That last case was a bug the unit tests caught: the Phase 8 redactor removed `authorization:` but left the token. `GET /api/v1/ops/audit/verify` result at the end of the evidence runs: valid, 55 events.

## 4. Secret handling (§46)

| Check | Result |
|---|---|
| Configured API key value in tracked files, files to be committed, full git history, evidence JSON, API server logs, frontend production bundle | **0 occurrences** |
| Generic credential patterns (AWS keys, private keys, key/token assignments, bearer tokens) | 0 after allowlisting documented test fixtures (Emergent template test sessions `test_ui_football…`) and one library false positive (axios `decodeURIComponent` in the source map) |
| `.env` ignored by git | yes |
| `.env` copied into the Docker image | no (Dockerfile copies `apps/api/app` only; `.dockerignore` added) |
| Key printed during the session | no (only presence and length were checked) |

The API-Football key reached this session as an uploaded `.env` file. Recommended: store it for future sessions as an environment credential or variable in the cloud environment settings, and rotate it if its exposure in the session upload is a concern.

## 5. Configuration (§46)

- **CORS**: origins come from `CORS_ALLOWED_ORIGINS`. The previous list contained `*` together with `allow_credentials=True` (R17). `*` and localhost origins are rejected in staging/production.
- **Startup policy**: staging/production refuse to start with default or empty secrets or local Bronze storage.
- **Database URLs, provider keys and S3 secrets**: never returned by any endpoint. System status exposes component state and latency only.

## 6. Dependency audit (§47)

| Scope | Tool | Result |
|---|---|---|
| Python (`requirements.txt`) | pip-audit | **No known vulnerabilities** |
| Frontend production dependencies | yarn audit (`--groups dependencies`) | **79 advisories: 60 high, 19 moderate** across 1,492 packages. 62 arrive via `react-scripts` (build toolchain); **17 are in runtime dependencies**: `axios` 1.18.0 (12) and `react-router-dom` (5). The CI gate blocks on high. |

## 7. Other findings

- The template's `index.html` loads a third-party analytics script (`ap.emergent.sh`) and assets (`assets.emergent.sh`), plus Google Fonts. A production build should remove or self-host these. In this sandbox they fail to load, which is the only source of browser console errors.
- The Phase 16 endpoints `/api/auth/me` and `/api/copilot/query` remain unauthenticated (pre-existing; outside the Phase 17 ops surface).
- Rate-limit Redis calls are synchronous with 0.2 s timeouts inside async request handling. This is acceptable at measured volume and recorded as a limitation.

## 8. Not tested
- External penetration test; TLS termination; WAF; session or cookie flows of the Emergent Google login (not part of this backend).
- Token expiry and rotation policy (tokens are revocable, not time-limited).
