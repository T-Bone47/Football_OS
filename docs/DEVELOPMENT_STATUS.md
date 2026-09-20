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

## Provider finalization: API-Football as sole active provider (this session)

Per ADR-008. `football-data.org`'s adapter, config, and capability-registry rows are untouched — it's registerable via `register_optional_providers()`, just not in `default_registry`.

| Item | Status |
|---|---|
| `default_registry` (statsbomb + api-football only) | VERIFIED |
| `register_optional_providers()` re-adds football-data.org | VERIFIED (unit test) |
| Diagnostics: football-data.org shows `OPTIONAL / DISABLED` when unconfigured, doesn't fail overall health | VERIFIED (unit test with no token; also confirmed live in this session — this sandbox's own `.env` has a real token, so diagnostics correctly ran the full check instead of short-circuiting, and reported the same sandbox-egress-block reason as API-Football) |
| `.env.example` — football-data.org vars commented out of the active section, with a note on how to re-enable | VERIFIED |
| Adapter-level (not just classifier-level) error wiring: 401/429/500/timeout through the real `ApiFootballProvider.fetch()` | VERIFIED — 4 new tests |
| Full suite | **45 passed, 1 skipped** (unchanged: the opt-in live test) |
| Live API-Football verification | Still **BLOCKED** in this sandbox for the same reason as every prior session — a diagnostic run reported from Oliver's own machine showed a genuine PASS across DNS/TLS/HTTP/auth/authz/quota, which I'm reporting as *his* result, not mine; I have not independently observed a successful live call from anywhere I control |

One process note worth being direct about: a reconnaissance `grep` in this session wasn't scoped away from `.env` and printed the real `FOOTBALL_DATA_TOKEN` value in a tool-output line — caught and disclosed immediately, `.env` itself was never at risk (still untracked, still absent from git history), but it's a real lapse against the "never print the key" rule both this project's docs and I have held to everywhere else. Token rotation was recommended as a precaution.

## Live endpoint verification script (this session)

Built `app/providers/verify_live_endpoints.py` — routes through the existing `IngestionService` (no parallel infrastructure), checks `/leagues`, `/teams`, `/players`, `/fixtures` sequentially, stops immediately on AUTHORIZATION/QUOTA failure, only calls `CapabilityRegistry.mark_verified()` on a genuine `SUCCESS`.

| Item | Status |
|---|---|
| Classification logic (`classify()`) | VERIFIED — 8 parametrized unit tests cover every outcome category |
| "Not configured" path | VERIFIED — unit test |
| Live run against real local Postgres + real API-Football | **VERIFIED LIVE on local host.** `/leagues` (1238 results), `/teams` (20 results, 2023 season), `/players` (20 results, 2023 season), `/fixtures` (1154 results, 2026-09-20 date) all returned genuine HTTP 200 SUCCESS responses. All 4 capabilities confirmed with real `last_verified` timestamps in PostgreSQL `provider_capabilities` table. |
| Full suite | **56 passed, 0 skipped** (with `LIVE_PROVIDER_TESTS=1`) / **55 passed, 1 skipped** (default) |
| Live success on `/leagues`, `/teams`, `/players`, and `/fixtures` | **VERIFIED.** Genuinely achieved against live API-Football endpoints. Free tier parameter constraints discovered and documented. |

## Phase 0 — Live Verification Complete (Local Machine Execution)

Executed on local machine with real Docker PostgreSQL 16, live network access, and valid `API_FOOTBALL_KEY`.

### Provider Verification Summary
- **Diagnostics**: DNS, TLS, HTTP Reachability, Credential, Authentication, Authorization, Quota — ALL PASS.
- **`/leagues`**: VERIFIED (`params={'current': 'true'}` -> 1238 results, Bronze snapshot saved, validated).
- **`/teams`**: VERIFIED (`params={'league': 39, 'season': 2023}` -> 20 results, Bronze snapshot saved, validated).
- **`/players`**: VERIFIED (`params={'league': 39, 'season': 2023, 'page': 1}` -> 20 results, Bronze snapshot saved, validated).
- **`/fixtures`**: VERIFIED (`params={'date': '2026-09-20'}` -> 1154 results, Bronze snapshot saved, validated).

### Real Provider Discoveries (API-Football Free Tier Constraints)
1. **Season Limitation**: Free plans only permit seasons 2022 to 2024 (`{'plan': 'Free plans do not have access to this season, try from 2022 to 2024.'}`).
2. **Parameter Limitation**: `last` parameter is forbidden on Free plans (`{'plan': 'Free plans do not have access to the Last parameter.'}`).
3. **Date Limitation on Fixtures**: Free plans restrict `date` queries to ±1 day of current date (`{'plan': 'Free plans do not have access to this date, try from ...'}`).

### Code & Architecture Fixes
1. **Transactional Capability Commit**: Fixed `IngestionService.run` to call `mark_verified` before `self._session.commit()` so capability verification is atomically committed with run and snapshot records.
2. **Test Environment**: Added `fios_test` database to Postgres container; enabled `load_dotenv()` in `tests/conftest.py`; updated `test_api_football_live` to mark `status` capability before running.

## Phase 1 — Slice 1: Bronze to Silver Normalization Engine (this session)

Vertical slice per §18–§22 of architecture specification: **Bronze Snapshots → Transformers → Identity Resolution → Canonical Silver Entities (`Competition`, `Season`, `Club`, `Player`, `PlayerSeasonStats`) in PostgreSQL → REST API → Tests.**

| Feature | Status | Evidence |
|---|---|---|
| Migration `0003_canonical_silver_models.py` | VERIFIED | Real Alembic migration executed against Docker Postgres 16; 9 new tables created with FKs and unique constraints |
| SQLAlchemy Canonical Models (`canonical.py`) | VERIFIED | `Competition`, `Season`, `CompetitionSeason`, `Club`, `ClubIdentity`, `Player`, `PlayerIdentity`, `PlayerSeasonStats`, `Match` |
| Pure Transformers (`transformers.py`) | VERIFIED | Unit-tested with dirty input handling (string unit stripping, date parsing, float parsing) |
| Normalization Service (`service.py`) | VERIFIED | Idempotent upserts for clubs and players; full provenance link to `DataSnapshot.id` |
| Identity Resolution (§21) | VERIFIED | Explicit `ClubIdentity` and `PlayerIdentity` records with `DIRECT_PROVIDER_ID` resolution method and confidence 1.0 |
| Canonical API (`routes_canonical.py`) | VERIFIED | `/api/v1/competitions`, `/api/v1/clubs`, `/api/v1/players`, `/api/v1/normalization/snapshots/{id}` |
| Live Data Ingestion & Normalization | **VERIFIED LIVE** | Real Premier League 2023 Bronze snapshots normalized into 20 canonical clubs and 20 canonical players with season stats in local PostgreSQL |
| Full Test Suite | **VERIFIED** | **65 passed, 0 failed, 0 skipped** across unit, integration, and live provider tests |

## Phase 1 — Slice 2: Match Intelligence + Data Foundation (this session)

Vertical slice per §18–§22: **Bronze Fixture Snapshots → Pure Transformers → Controlled Status & Score Mapping → Idempotent Normalization Service → Canonical `Match` + `MatchTeam` in PostgreSQL → Canonical Match REST API → Full Verification.**

| Feature | Status | Evidence |
|---|---|---|
| Migration `0004_match_normalization_enhancements.py` | VERIFIED | Real Alembic migration executed against PostgreSQL 16; added 17 enhancement columns + indexes to `matches`, created `match_teams` table with composite unique constraint `(match_id, club_id)` |
| Canonical Models (`Match`, `MatchTeam` in `canonical.py`) | VERIFIED | Canonical `Match` with score breakdown (halftime, fulltime, extratime, penalty), timezone-aware kickoff, venue, referee, round, stage, winner club FK; canonical `MatchTeam` capturing home/away club perspectives, match results (`WIN`/`LOSS`/`DRAW`), goals for/against, and points (`3`/`1`/`0`) |
| Pure Fixture Transformers (`transformers.py`) | VERIFIED | 6 unit tests covering timestamp parsing, timezone awareness, status mapping (`SCHEDULED`, `LIVE`, `FINISHED`, `POSTPONED`, `CANCELLED`, `SUSPENDED`, `ABANDONED`, `AWARDED`, `UNKNOWN`), score extraction, and data quality rejections (missing ID, missing date, `home == away`) |
| Normalization Service Match Extension (`service.py`) | VERIFIED | `normalize_fixtures_payload` and `normalize_snapshot` (for `fixtures`, `fixtures_round`, `fixture` endpoints); club identity resolution via `DIRECT_PROVIDER_ID`; automated winner calculation; full snapshot provenance attribution (`snapshot_id`) |
| Idempotency Engine | **VERIFIED LIVE** | Repeated normalization of real 1154-fixture Bronze snapshot on live PostgreSQL resulted in exactly 1154 matches, 2308 match teams, 0 duplicate records, identical primary keys |
| Canonical Match REST API (`routes_canonical.py`) | VERIFIED | `GET /api/v1/matches` with filtering (`competition_id`, `season_id`, `competition_season_id`, `club_id`, `status`, `date_from`, `date_to`, pagination); `GET /api/v1/matches/{id}` returning match detail with club summaries, scores, and match teams perspective |
| Real Bronze Snapshot Normalization | **VERIFIED LIVE** | 1,154 matches and 2,308 match teams populated in PostgreSQL from API-Football snapshot `a33904b9-44cd-4cca-b360-06e385cd2ae4` |
| Full Test Suite | **VERIFIED** | **80 passed, 1 skipped, 0 failed** across all unit and integration test suites |


