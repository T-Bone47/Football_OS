# Development Status

Updated at the end of each session. Statuses: PLANNED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED / BLOCKED. IMPLEMENTED and VERIFIED are never used interchangeably (build brief §54/§55) — VERIFIED means an actual run happened and I saw the result; IMPLEMENTED means the code exists and is unit-tested but the specific real-world thing it targets (a live provider, a real MinIO bucket, a real Docker network) hasn't been hit yet.

## Phase 0 — Slice 1: Provenance Foundation (unchanged from last session)

| Feature | Status |
|---|---|
| Repo scaffold, config, `.gitignore` | VERIFIED |
| `DataSource`/`IngestionRun`/`DataSnapshot` schema + migration 0001 | VERIFIED — real Alembic run, real local Postgres 16 |
| `FootballDataProvider` protocol | VERIFIED |
| StatsBomb adapter | VERIFIED — real network call, both sessions |
| API-Football / football-data.org adapters | IMPLEMENTED — mocked-transport tests only |
| Local `SnapshotStore` | VERIFIED |
| FastAPI `/health` | VERIFIED |

## Phase 0 — Slice 2: Real Ingestion Foundation (this session)

| Feature | Status | Evidence |
|---|---|---|
| Retry/backoff (`providers/http.py`, tenacity-based) | VERIFIED | Unit tests prove retry-on-429/5xx, no-retry-on-401 |
| Provider registry | VERIFIED | Unit tests |
| `provider_capabilities` table + migration 0002, seeded from the architecture doc's own §7/§8/§9 claims | VERIFIED | Real migration against real Postgres; seed queried back and matches exactly (StatsBomb/competitions is the only `last_verified` row, because it's the only one a live call has actually confirmed) |
| `CapabilityRegistry` service (`supports` / `mark_verified`) | VERIFIED | Real-Postgres integration test |
| `IngestionService` (QUEUED→RUNNING→SUCCESS/FAILED lifecycle) | **VERIFIED end-to-end** | Real HTTP: `POST /api/v1/ingestion/runs` (statsbomb/competitions) → `SUCCESS`, `GET .../runs/{id}` round-trips it, and Postgres shows the joined `ingestion_runs`+`data_snapshots` row with `VALID` validation status and a real sha256 |
| Capability gate rejecting unsupported requests | VERIFIED | Integration test: fresh/unseeded schema correctly fails the run with a clear error instead of attempting the fetch |
| Provider-failure handling (network error → `FAILED`, not a crash) | VERIFIED | Integration test with an injected always-fails provider |
| Pydantic envelope DTOs (API-Football, football-data.org) | IMPLEMENTED — structural shape only, built from what the architecture doc already asserts these providers return; **not validated against a real response**, since neither domain is reachable here |
| Pandera schema (StatsBomb `competitions`) | VERIFIED | Validated against the actual live StatsBomb payload, not a guessed shape |
| Validation dispatcher | VERIFIED | Unit tests, incl. the "no schema yet → PENDING, not fabricated VALID" case |
| `S3SnapshotStore` (boto3, same content-addressed key layout) | **IMPLEMENTED — NOT VERIFIED against real MinIO/S3.** Unit-tested against a mocked S3 (moto): content-addressing and idempotency logic is proven; talking to an actual bucket over the network is not | No Docker/MinIO in this sandbox |
| `docker-compose.yml` (health checks, `minio-init` bootstrap, Docker-service-name-aware `api` env) | IMPLEMENTED — YAML validated to parse and contain the right services. **`docker compose up` itself: NOT RUN.** | No Docker in this sandbox |
| Ingestion API (`POST /runs`, `GET /runs/{id}`) | VERIFIED | Real HTTP round-trip, see IngestionService row above |
| `/health/ready` (checks Postgres, not just process-up) | VERIFIED | Curled it for real, got `{"status":"ready"}` |
| Live API-Football / football-data.org calls | **BLOCKED** — domains return HTTP 403 from this sandbox's egress proxy, and no keys are configured either. Opt-in test exists (`LIVE_PROVIDER_TESTS=1` + a real key) and correctly skips without either. | — |
| Existing 7-test baseline from Slice 1 | VERIFIED — still 7/7, unmodified, after all of the above | Ran before and after this session's changes |
| Full suite (Slice 1 + Slice 2) | VERIFIED — 24 passed, 1 skipped (the opt-in live test) | — |

### Phase 1 entry criteria (build brief §59), scored honestly

| Category | Item | Status |
|---|---|---|
| Infrastructure | Postgres | PASS (local, not Docker) |
| | Redis | PASS (local, not Docker) |
| | MinIO | **NOT RUN** |
| | API | PASS |
| Database | Alembic / FKs / constraints / indexes | PASS |
| Providers | StatsBomb | VERIFIED |
| | API-Football | IMPLEMENTED, not live-verified |
| | football-data.org | IMPLEMENTED, not live-verified |
| Storage | Local Bronze | VERIFIED |
| | MinIO Bronze | **NOT RUN** |
| | Content SHA / idempotency | VERIFIED (both backends) |
| Ingestion | QUEUED/RUNNING/SUCCESS/FAILED | PASS |
| Validation | Valid / invalid / raw-preservation | PASS |
| Tests | Unit / integration | PASS |
| | Docker | **NOT RUN** |
| | Migration | PASS |

**Not met yet, and can't be met in this sandbox:** MinIO end-to-end, Docker end-to-end, both live provider calls. Everything else on this list is genuinely met.

## Deferred, still (unchanged reasoning from Slice 1, ADR-004)

Frontend, worker/Celery-Dramatiq, canonical football entities, identity resolution — none of these are needed by Slice 2 and building them now would be exactly the "infrastructure for its own sake" the brief's §63 warns against.

## Provider connectivity forensics (this session)

Real credentials were supplied (via an uploaded `.env`, merged into the local `.env` — never committed, never printed, `.env` confirmed absent from `git status` throughout). Diagnosis, not assumption:

| Check | API-Football | football-data.org |
|---|---|---|
| DNS | PASS (resolves to real IPs) | PASS |
| TLS to the responding host | PASS | PASS |
| HTTP reachability (request actually reaches the provider) | **FAIL** | **FAIL** |
| Root cause | `x-deny-reason: host_not_allowed` — this sandbox's own egress proxy, confirmed identical with and without the real key | same |
| Credential | SET (real key loaded, never live-tested — can't be, given the above) | SET (same) |
| Authentication / Authorization / Quota | UNKNOWN — request never reached far enough to test these | UNKNOWN |

This is **not** "API-Football is blocked" (the thing the brief explicitly says not to write) — it's a specific, verified layer: this sandbox's own network allowlist, not DNS, not TLS, not the provider's WAF, not the credential, not an IP/domain restriction on the API-Football dashboard side. `python -m app.providers.diagnostics` (built this session) reproduces this classification live and is exactly what will report differently — genuinely, not by assumption — the moment this runs somewhere with these two hosts allowlisted.

**Added this session, all real and tested:**
- `ProviderNetworkError` / `ProviderAuthenticationError` / `ProviderAuthorizationError` / `ProviderRateLimitError` / `ProviderBadRequestError` / `ProviderServerError` / `ProviderSchemaError` / `ProviderUnavailableError` — VERIFIED (unit tests cover every classification branch, including the sandbox-specific one)
- Diagnostics CLI (`app/providers/diagnostics.py`) — VERIFIED as logic (mocked-transport tests cover 401/403-IP-restriction/429/200 cases this sandbox can't safely trigger live) and VERIFIED as a real run against real credentials in this environment (output captured in the session's forensic report)
- API-Football envelope-errors check (HTTP 200 with non-empty `errors[]` → `ProviderBadRequestError`) — VERIFIED, unit-tested
- Configurable base URLs (`API_FOOTBALL_BASE_URL`, `FOOTBALL_DATA_BASE_URL`) instead of hardcoded constants — VERIFIED (existing StatsBomb path still passes; API-Football/football-data.org paths still pass their mocked tests)
- Renamed `football_data_org_key` → `football_data_token` to match the real credential's actual env var name — VERIFIED (existing + new tests pass)

**Caught by actually running the suite, not by review** (two real bugs, both fixed): pydantic-settings reads a real `.env` file as a source independent of `monkeypatch.delenv`, so a test that assumed "delete the env var = no key" broke the moment a real `.env` existed on disk; and `from app.config import get_settings` binds a local name in `api_football.py` that patching `app.config.get_settings` doesn't reach. Both are now fixed at the actual test, not worked around.
