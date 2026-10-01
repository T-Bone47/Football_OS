# Football Intelligence OS

AI-powered football recruitment, valuation, tactical and match decision-intelligence platform. Architecture spec: `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (source of truth — not duplicated here).

## Status

**Latest phase**: Phase 17 — Live Football Intelligence Operations. Final state **`PHASE_17_RELEASE_BLOCKED`** (see `docs/PHASE_17_RELEASE_REPORT.md`).  
**Test suite (fresh checkout, real PostgreSQL)**: unit **641 passed**, 0 failed, 20 skipped (13 of them `NOT_TESTED` because they need gitignored Bronze evidence); integration **99 passed, 5 failed**, 1 skipped. The 5 failures are real Phase 7 recruitment defects (reconnaissance R22) and are left failing on purpose so CI blocks.  
**What is verified**: real ingestion from StatsBomb Open Data (511/511 jobs, 478 matches to Silver, SHA-256 provenance, idempotent replay). Operations API `/api/v1/ops` (45 authenticated operations: bearer tokens, organization/project authorization, append-only hash-chained audit). Gated match inference, incident drills, backup/restore, and the `/operations`, `/data-ops` and `/model-ops` pages.  
**What is not**: live operation. API-Football is blocked by this environment's egress policy, so there are no live fixtures, live predictions or live outcomes. The match model fails walk-forward validation on real data and stays unservable.  
**Earlier claims**: the Phase 16 certification (608 passing tests) did not reproduce from Git, and parts of it rested on hardcoded status and seeded data. Phase 17 reconnaissance (`docs/PHASE_17_RECONNAISSANCE.md`, R1–R24) lists the fabricated status, data and model paths that were removed or relabelled.

## Running locally (without Docker)

```bash
cp .env.example .env   # defaults to the local filesystem snapshot backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --app-dir apps/api
```

## Running with Docker (untested here — verify on a machine with Docker)

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health/ready
```

This brings up Postgres, Redis, MinIO (+ a one-shot `minio-init` that creates the `football-os-bronze` bucket), and the API — wired together with health checks so the API only starts once its dependencies report healthy, not just "container created."

## Using the ingestion API

```bash
curl -X POST http://localhost:8000/api/v1/ingestion/runs \
  -H "Content-Type: application/json" \
  -d '{"provider": "statsbomb", "resource": "competitions", "params": {}}'

curl http://localhost:8000/api/v1/ingestion/runs/<run_id>
```

`statsbomb`/`competitions` works with zero configuration (free, keyless, real data). `api-football` is the only active external provider (see ADR-008) and needs `API_FOOTBALL_KEY` in `.env` — get one from the dashboard at `https://dashboard.api-football.com/profile?access`, **not** from `https://www.api-football.com/`, which is the documentation/marketing site, not the API host. The API host is `https://v3.football.api-sports.io`, auth header `x-apisports-key`.

`football-data-org` is fully implemented and tested but not active by default — see ADR-008 for why, and `.env.example` for how to bring it back.

Run `python -m app.providers.diagnostics` (from `apps/api`, with `PYTHONPATH=apps/api`) any time you want a sanitized DNS/TLS/auth/quota report for the active provider without ever printing the key. In this project's own sandboxed dev environment, that command's honest answer is a sandbox-egress block, not a provider problem — see `docs/DEVELOPMENT_STATUS.md`.

## Tests

```bash
pytest                                          # unit + StatsBomb integration (needs internet)
TEST_DATABASE_URL=... pytest tests/integration  # needs a real Postgres
LIVE_PROVIDER_TESTS=1 API_FOOTBALL_KEY=... pytest -k live   # opt-in, needs a real key + network
```

## Repository layout

Matches architecture doc §47. `apps/web` and `apps/worker` don't exist yet — see `docs/ARCHITECTURE_DECISIONS.md` ADR-004 for why.
