# Football Intelligence OS

AI-powered football recruitment, valuation, tactical and match decision-intelligence platform. Architecture spec: `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (intended source of truth — **not present in this checkout**; ADRs are in `docs/ARCHITECTURE_DECISIONS.md`).

## Status

**Pre-production prototype.** An independent audit (2026-10-11, `docs/PRODUCTION_TRUTH_AUDIT.md`) found fabricated outputs, an unauthenticated API and a valuation model that fails its own release gate; the first remediation pass is in this tree. The earlier "certified release" and `564 passed` claims were **not reproduced** — run `pytest -v` (see the audit doc §7) and record the real result in `docs/DEVELOPMENT_STATUS.md`.

- Valuation model: `MODEL_RELEASE_BLOCKED` — served with labels by the exploratory market API, refused by the production serving path.
- Match prediction: no trained artifact exists.
- All API routes except `/health`, `/readiness`, `/health/ready` and `/api/status` require a bearer token (`AUTH_JWT_SECRET`, see `.env.example`).
- Phase 9–16 operational state is in memory and is lost on restart.

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
