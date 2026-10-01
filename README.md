# Football Intelligence OS

AI-powered football recruitment, valuation, tactical and match decision-intelligence platform. Architecture spec: `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (source of truth — not duplicated here).

## Status

**Certified Release**: `ADAPTIVE_INTELLIGENCE_VALIDATED` (Phase 15)  
**Test Suite**: **564 passed**, 0 failures, 0 regressions (+20 Phase 15 unit & adversarial tests)  
**Operational Capabilities**: Global Football Research, Adaptive Intelligence & Cross-Competition Generalization. Includes Governed Global Research Data Model (ResearchQuestion, ResearchHypothesis, ResearchCohort, ResearchExperiment, ResearchResult, ResearchValidation, FeatureCandidate, ResearchPromotionRecord), 8-State Research Lifecycle (DISCOVERED -> HYPOTHESIS -> TESTING -> VALIDATED / REJECTED / INSUFFICIENT_EVIDENCE -> PRODUCTION_CANDIDATE -> PROMOTED), Pattern Discovery across 10 pattern families under sample gating, immutable versioned research cohorts with SHA-256 fingerprinting, Cross-Competition Generalization Engine evaluating train-same, cross-league, and held-out transferability without silent pooling, descriptive League Translation Intelligence tracking 8 operational transition dimensions under non-causal policy, multi-tier Player Trajectory Research separating PAST_OBSERVED, CURRENT_OBSERVED, MODELLED_TREND, and PROJECTED_RANGE with breakout detection, evidence-gated Role Transition Engine (450-min / 5-app gating), Tactical Pattern Research strictly segregating observed structures from modelled interpretations and counterfactual scenarios, Transfer Market Research preserving strict 9-state fee taxonomy with zero fee fabrication, Unified Model Error Research disaggregated across 8 contextual slices preventing silent aggregate smoothing, Governed Feature Discovery and Adaptive Model Candidate review with human promotion authorization, automated Causality Guardrail enforcing associative terminology, Global Validation Matrix tracking operational boundaries across 9 dimensions, Scout Copilot V5 Dispatcher deterministically handling 12 research query classes, and the Global Scout Research Workspace (`/research`) delivering 12 distinct analytical views in the frontend. See `docs/PHASE_15_RELEASE_REPORT.md` for full certification details.

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
