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
