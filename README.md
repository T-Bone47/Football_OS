# Football Intelligence OS

AI-powered football recruitment, valuation, tactical and match decision-intelligence platform. Architecture spec: `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (source of truth — not duplicated here).

## Status

Phase 0, slice 1 ("Provenance Foundation") is built and verified. See `docs/DEVELOPMENT_STATUS.md` for the itemized state and `docs/IMPLEMENTATION_PLAN.md` for the roadmap.

## Running locally

```bash
cp .env.example .env
docker compose up -d postgres redis minio   # or run Postgres/Redis natively
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --app-dir apps/api
```

Tests:

```bash
pytest                    # unit + StatsBomb integration test (needs internet)
TEST_DATABASE_URL=... pytest tests/integration/test_provenance_models.py  # needs a real Postgres
```

## Repository layout

Matches architecture doc §47. `apps/web` and `apps/worker` don't exist yet — see `docs/ARCHITECTURE_DECISIONS.md` ADR-004 for why.
