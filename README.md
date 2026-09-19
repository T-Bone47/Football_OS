# Football Intelligence OS

AI-powered football recruitment, valuation, tactical and match decision-intelligence platform. Architecture spec: `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (source of truth — not duplicated here).

## Status

Phase 0 Slice 2 ("Real Ingestion Foundation") is built. See `docs/DEVELOPMENT_STATUS.md` for the itemized VERIFIED vs IMPLEMENTED-not-verified state — MinIO and Docker end-to-end and both live provider APIs still need an environment with real Docker + network egress to those two domains.

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
