# Development Status

Updated at the end of each session. Statuses: PLANNED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED / BLOCKED.

## Phase 0 — Data Foundation

| Feature | Status | Tests | Known issues | Next step |
|---|---|---|---|---|
| Repo scaffold (`apps/api`, `database/migrations`, `docs`) | VERIFIED | — | `apps/web`, `apps/worker` intentionally absent (ADR-004) | Add when their phase starts |
| Config (`app/config.py`, `.env.example`) | VERIFIED | Imported successfully during app boot | — | Add provider-specific rate-limit config in Phase 1 |
| `DataSource` / `IngestionRun` / `DataSnapshot` schema | VERIFIED | `alembic upgrade head` ran against real local Postgres 16; round-trip test passing | Enum columns stored as CHECK-constrained VARCHAR, not native Postgres ENUM (ADR intentionally not written — this is a one-line implementation detail, not a real alternative) | Extend with `Player`/`Club`/etc. in Phase 1 |
| `FootballDataProvider` protocol | VERIFIED | Unit test | — | — |
| StatsBomb adapter | VERIFIED | Integration test hit real `raw.githubusercontent.com/statsbomb/open-data` | — | Add `matches`/`events`/`lineups` beyond `competitions` once Phase 1 needs them |
| API-Football adapter | IMPLEMENTED | Unit test against mocked transport only | **Not live-verified** — sandbox can't reach `api-football.com`, no key configured | Live-test once a key + reachable environment exist |
| football-data.org adapter | IMPLEMENTED | Unit test against mocked transport only | **Not live-verified** — sandbox can't reach `football-data.org`, no key configured | Same as above |
| `SnapshotStore` (local filesystem) | VERIFIED | Unit test (content-addressing + idempotency) | Sync file I/O inside an async function (flagged `# ponytail:` in code) — fine at Phase-0 volume, revisit if ingestion throughput becomes real | S3/MinIO backend in Phase 1 (ADR-001) |
| FastAPI app + `/health` | VERIFIED | Started locally, `curl`'d for real | — | Real routes arrive with Phase 1 endpoints |
| `docker-compose.yml` + `Dockerfile` | IMPLEMENTED | **NOT RUN** — no Docker in this sandbox | Written to target shape only | Verify `docker compose up` in a real dev environment |
| CI workflow (`.github/workflows/ci.yml`) | IMPLEMENTED | **NOT RUN** — no GitHub Actions runner here | — | Verify on first push to a real GitHub repo |
| Ingestion-run lifecycle (state machine actually driving fetch→snapshot→validate) | PLANNED | — | Only the schema exists, not the runner | Slice 2 |
| Provider capability registry (§7) | PLANNED | — | — | Slice 2 |
| Pandera validation | PLANNED | — | — | Slice 2 / Phase 1 |
| Identity resolution | PLANNED | — | — | Phase 1 |

## Phases 1–9

All PLANNED. Not started. See `docs/IMPLEMENTATION_PLAN.md` for the roadmap and why each gets its own plan doc when it starts rather than one plan up front.
