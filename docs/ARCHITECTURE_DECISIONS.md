# Architecture Decision Records

Only decisions where we chose between real alternatives get an ADR (per build brief §61 — no ADRs for trivial implementation detail). Anything mandated directly by the architecture doc (e.g. "modular monolith, no microservices") isn't a decision we made, so it isn't listed here.

---

## ADR-001: Local filesystem for raw snapshots in Phase 0, not MinIO

**Context:** §12/§13/§41 of the architecture doc specify S3-compatible object storage, MinIO in development. Running a MinIO server requires either Docker (unavailable in this sandbox) or a binary download from a host outside the network allowlist.

**Decision:** Define a `SnapshotStore` protocol now; ship one implementation, `LocalFilesystemSnapshotStore`, using the exact `bronze/<provider>/<resource>/<sha256>.json` layout the spec already names. No second (S3) implementation yet — building it without anything to test it against is speculative.

**Trade-offs:** Local disk isn't what runs in production. Swapping in an S3/MinIO-backed implementation later is additive (new class implementing the same protocol), not a rewrite — the ingestion/validation code above it never touches the filesystem directly.

**Status:** Accepted for Phase 0. Revisit at start of Phase 1 once Docker/MinIO is reachable (i.e., outside this sandbox).

---

## ADR-002: Synchronous engine for Alembic, async engine for the app

**Context:** The FastAPI app uses `asyncpg` for request-path DB access (§6). Alembic's migration runner doesn't need to be async — it runs standalone, outside the request path, once per deploy.

**Decision:** `database/migrations/env.py` builds its own connection by stripping `+asyncpg` off `DATABASE_URL` (falling back to `psycopg2`), rather than making the whole migration run through `run_sync` on the async engine.

**Trade-offs:** One extra DB driver in requirements (`psycopg2-binary`) versus not having to reason about event loops inside a migration tool that already has its own execution model. This is a well-worn pattern, not a novelty.

**Status:** Accepted.

---

## ADR-003: Plain `requirements.txt` install, `pyproject.toml` only for tool config

**Context:** The repo layout in §47 names `pyproject.toml` at root. A full PEP 517/518 build-backend setup (for `pip install -e .`) is only useful once something needs to *import* this codebase as an installed package (e.g. the worker in Phase 1). Nothing does yet.

**Decision:** `pyproject.toml` exists (as the spec names it) but only holds `[tool.pytest.ini_options]` (`pythonpath = ["apps/api"]`, `asyncio_mode = "auto"`). Actual dependency installation is `pip install -r requirements.txt`.

**Trade-offs:** Have to remember to add build-backend config once `apps/worker` needs to import `apps/api`'s code, or once we containerize with a proper wheel build. Flagging it here so that's not a surprise.

**Status:** Accepted for Phase 0.

---

## ADR-004: Frontend and worker scaffolding deferred, not stubbed

**Context:** §47 names `apps/web/` and `apps/worker/` in the target tree. Nothing in Phase 0's vertical slice reads from either.

**Decision:** Don't create empty `apps/web/` or `apps/worker/` directories now. They appear when the phase that needs them starts (frontend once there's an API worth calling; worker once a job needs to run async).

**Trade-offs:** The repo tree doesn't yet visually match the target layout in full. Preferred over empty directories that exist only to "look complete" — ponytail: no scaffolding for later.

**Status:** Accepted.
