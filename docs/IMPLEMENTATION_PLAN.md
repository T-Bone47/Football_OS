# Football Intelligence OS — Implementation Plan

**Spec:** `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (v2.0, provided by Oliver) is the source of truth. This plan does not restate it; it sequences it.

**Goal:** Build an evidence-driven football recruitment/valuation/tactical/match decision-intelligence platform, per the architecture doc's 57 sections, as a modular monolith.

**Tech stack:** FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL/pgvector + Redis + S3-compatible storage (backend); Next.js + React + TypeScript (frontend, deferred — see Scope below).

## Repository audit (this session)

| Check | Result |
|---|---|
| Existing repo | None — `/home/claude` was empty. Confirmed greenfield. |
| Git | `git init` run this session. |
| Python | 3.12.3, pip 24.0 — present |
| Node | v22.22.2, npm 10.9.7 — present, unused until the frontend slice |
| Docker | **Not available** in this sandbox (`docker: not found`) |
| PostgreSQL | Not preinstalled — apt-installed and started this session (16.15), verified with a live connection |
| Redis | Not preinstalled — apt-installed and started this session, verified with `PING` → `PONG` |
| Network | This sandbox can reach `raw.githubusercontent.com` (StatsBomb open data lives there) but **cannot** reach `api-football.com` or `football-data.org` — those domains aren't on the sandbox's egress allowlist |
| Provider credentials | No `API_FOOTBALL_KEY` / `FOOTBALL_DATA_ORG_KEY` supplied |

These three constraints (no Docker, no reach to two of the three providers, no keys) are environmental, not architectural — they don't change what gets built, only what gets *verified where*. See "Environment reality" below. (A follow-up session's prompt assumed these had lifted because "a real development machine" was now available; re-checked directly — same sandbox, same `docker: not found`, same `403` from both provider domains. Still true as of the Slice 2 session.)

## Scope check (per superpowers:writing-plans)

The spec covers 15+ largely-independent subsystems (ingestion, identity resolution, role discovery, similarity, valuation, tactical fit, replacement engine, development, transfer risk, match intelligence, squad builder, scenario engine, AI scout, frontend, security/observability). Writing one bite-sized task plan for all of it up front would be hundreds of tasks referencing code that doesn't exist yet — the "no placeholders" rule in writing-plans can't hold across that distance. So: **one plan per phase**, each producing working, independently-testable software, written when that phase starts (task lists for role discovery are only honest once the feature store they consume actually exists). This mirrors the architecture doc's own "vertical slice" instruction (§57 of the build brief) exactly.

This document carries the **phase-level roadmap**. A full bite-sized `Task N` plan (per superpowers:writing-plans) exists only for the slice actually built this session — see `docs/plans/0001-provenance-foundation.md`.

## Phase roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 — Data Foundation | Repo, config, provenance schema, ingestion-run model (now actually driving fetch→snapshot→validate), snapshot store (local + S3), provider registry, capability registry, Pandera/Pydantic validation, ingestion API, Alembic, CI skeleton | **Slice 1 + Slice 2 both done.** MinIO-backed / Docker-backed / live-API verification specifically still isn't — see Development Status |
| 1 — Data Platform | Full API-Football + football-data.org ingestion (live), StatsBomb bulk pull, validation (Pandera), identity resolution, normalization → canonical model | PLANNED |
| 2 — Player Intelligence | Feature store, role discovery (PCA/UMAP + clustering), embeddings, pgvector similarity | PLANNED |
| 3 — Valuation | Transfer-value dataset, baseline → XGBoost/LightGBM, SHAP, market-gap | PLANNED |
| 4 — Recruitment | Tactical fit, hidden gems, replacement engine, transfer risk | PLANNED |
| 5 — Development | Performance/role/value trajectory projection | PLANNED |
| 6 — Match Intelligence | Leakage-safe match dataset, prediction, calibration | PLANNED |
| 7 — Squad Intelligence | Squad builder (OR-Tools), transfer simulator, scenario engine | PLANNED |
| 8 — AI Scout | Typed tool contracts, intent parsing, grounded reports | PLANNED |
| 9 — Production | Auth/RBAC, observability, CI/CD, deployment | PLANNED |

## This session's slice: Phase 0, slice 1 — "Provenance Foundation"

Vertical slice per §57 of the build brief: **Provider → Raw Snapshot → Validation status → Postgres provenance record → API health check → test.**

Deliberately excluded from this slice (would be scaffolding-for-later, per ponytail): MinIO/S3 backend, Redis-backed job queue, identity resolution, canonical Player/Club/Match entities, the frontend, auth. Each shows up when the phase that needs it starts.

**Built and verified this session** (see `docs/DEVELOPMENT_STATUS.md` for the itemized PASS/FAIL/NOT RUN table):
- `DataSource` / `IngestionRun` / `DataSnapshot` tables, via a real Alembic migration against a real local Postgres 16 instance
- `FootballDataProvider` protocol
- StatsBomb adapter — **real**, tested against live open data on `raw.githubusercontent.com`
- API-Football / football-data.org adapters — structurally complete, auth wiring unit-tested against a mocked transport; **not** live-tested (network + keys both unavailable here)
- Content-addressed local-filesystem snapshot store (`bronze/<provider>/<resource>/<sha256>.json>`)
- FastAPI app with a `/health` endpoint
- `docker-compose.yml` + `Dockerfile` — written to the target shape, **not** executed (no Docker in this sandbox)
- GitHub Actions CI workflow — written, **not** executed (no CI runner here)

## Environment reality — what this means for how we continue

This sandbox is good for exactly what it did today: audit, plan, write real code, and verify anything that only needs Postgres/Redis/PyPI/public GitHub data. It cannot verify Docker Compose, cannot reach two of the three data providers, and its filesystem doesn't persist as an ongoing project the way a real clone of this repo would. For Phases 1 onward — live provider ingestion with real keys, Docker end-to-end, a codebase you keep iterating on across sessions — **Claude Code against a real local clone of this repo is the right tool**, not this chat. Recommendation card is attached below; this isn't a blocker, just where the long tail of this build belongs.

## Immediate next steps (not started)

1. On a machine with real Docker + network egress: `docker compose up -d --build`, confirm all 5 services healthy, re-run the full test suite pointed at the Dockerized Postgres, and add a genuine `test_minio_snapshot_store.py` integration test against the real MinIO bucket (the current one uses `moto`, which is a mock, not a substitute for this).
2. Get `API_FOOTBALL_KEY` / `FOOTBALL_DATA_ORG_KEY` and run `LIVE_PROVIDER_TESTS=1 pytest -k live` (already wired, currently skips) — then call `CapabilityRegistry.mark_verified` for whatever those calls actually confirm, don't hand-edit the seed data.
3. Phase 1 proper: bulk ingestion (not one-record-at-a-time), Silver normalization, canonical `Competition`/`Season`/`Club`/`Match`/`Player`, identity resolution. Per the scope-check in `docs/IMPLEMENTATION_PLAN.md`'s own opening, this gets its own `docs/plans/0002-data-platform.md` written when it starts, not now.
