# Production Truth Remediation, Stages 1-5: Implementation Plan

**Spec:** `docs/PRODUCTION_TRUTH_AUDIT.md` (issue register) and `docs/DEVELOPMENT_STATUS.md` (status record). The user's stage list (environment -> truth fixes -> persistence -> ML rebuild -> end-to-end proof) is the binding scope.

**Global constraints**
- Do not weaken assertions; replace a test only when it asserts a fabricated value, and say why.
- Never simulate success. A step whose external dependency cannot be verified is recorded BLOCKED with the exact command and error.
- Release status advances only on evidence present in the repo. Models stay `MODEL_RELEASE_BLOCKED` / no artifact until every gate is PASS on real data.
- Test command in this environment: `python3 /home/claude/standin/run_tests.py <files>` (pytest is not installable: no network). Results are labelled "stand-in", never "pytest".
- Code that needs PostgreSQL/FastAPI/SQLAlchemy is written to be verified in CI and is labelled UNVERIFIED until a real run is recorded in `docs/verification/`.

**Interfaces**
- `app.security.tokens.Principal` (user_id, org_id, roles): consumed by Task 3 (ownership), Task 6 (revocation), Task 7 (repositories).
- Model manifest JSON (`registry_manifest.json`): produced by Task 5 (prediction registry), consumed by Task 8 (model card, gate).
- `tools/check_orm_migration_parity.py` (Task 2): consumed by Task 7 to check migration 0014 against its ORM models.

**Review focus:** blind-edited DB/HTTP code (routes, repositories, SQL); any place a missing value could still become 0/False/"HIGH"; any route that returns another tenant's object.

### Task 1: Stage 1 verification tooling and the recorded sandbox result
Files: `tools/record_verification.py`, `tools/verify_environment.sh`, `tests/unit/test_record_verification.py`, `docs/verification/2026-10-11-sandbox.md`.
- RED: tests for `parse_junit` (counts, failures with names, skips), `probe_tool` (version or NOT_FOUND, never a guess), `render_record` (BLOCKED steps carry the command and error, never "passed"). Expected: ImportError / collection failure.
- GREEN: implement; run the real probes in this sandbox and write the BLOCKED record.
- Commit: `tools: reproducible Stage 1 verification runner and recorded sandbox result`.
- Completion: `python3 /home/claude/standin/run_tests.py tests/unit/test_record_verification.py` all pass.

### Task 2: ORM <-> migration parity checker (R19 measured)
Files: `tools/check_orm_migration_parity.py`, `tests/unit/test_orm_migration_parity.py`.
- RED: tests on synthetic ORM/migration source strings (missing table, missing column, nullability, index) and on the real repo. Expected: import failure, then real-repo drift report.
- GREEN: static AST comparison (no SQLAlchemy needed). Record actual drift; fix by migration only if clear.
- Completion: stand-in run of `test_orm_migration_parity.py`.

### Task 3: Phase 10 recruitment truth and per-object authorization
Files: `apps/api/app/phase10/recruitment_projects.py`, `reports.py`, `scenarios.py`, `api/routes_phase10.py`, tests.
- RED: no invented candidate values; unknown risk/budget -> `None` and constraint `None` (unverified), never `True`; no seeded demo project; org/owner scoping (404 across tenants).
- Completion: stand-in run of the new Phase 10 recruitment tests.

### Task 4: Phase 13 squad baselines and Phase 14 outcomes: no seeded production data
Files: `apps/api/app/phase13/squad_baseline.py`, `phase14/*`, tests.
- RED: a fresh engine has no squads/outcomes; "verified" outcomes require evidence; seeds only via explicit test fixtures.

### Task 5: Phase 12 readiness, Phase 9 coverage constants, match-prediction registry from evidence
Files: `phase12/recruitment_discovery.py`, `phase9/coverage_audit.py`, `prediction/registry.py`, tests.
- RED: no `PRODUCTION_READY` literal in Phase 12; coverage reports unmeasured provenance/missingness as `None` and never `VALIDATED` without validation; prediction registry has no hand-typed metrics or `MODEL_VALIDATED` without an artifact record.

### Task 6: Token lifecycle, route ownership and the gateway decision
Files: `apps/api/app/security/*`, `Football_OS-frontend/backend/*`, `deploy/nginx.conf`, `docs/ADR-0xx`, frontend pages, tests.
- RED: revoked `jti` rejected; token carries `jti`; key id and issuer/audience pinned; dead frontend endpoints resolved or removed; gateway ownership table has no overlapping route.

### Task 7: Persist operational state (PostgreSQL migration 0014, ORM, repositories)
Files: `database/migrations/versions/0014_*.py`, `apps/api/app/db/models/operational.py`, `apps/api/app/persistence/*`, tests.
- RED: repository contract tests (survive "restart" = new repository instance on the same store; tenant/user isolation; append-only audit with hash chain) run against the in-memory implementation; the PostgreSQL variant is skipped without `TEST_DATABASE_URL` and is UNVERIFIED here.

### Task 8: Point-in-time feature pipeline, dataset manifest, model card, truthful gate (ML groundwork; data BLOCKED)
Files: `apps/api/app/market/ml/pit_features.py`, `dataset_manifest.py`, `model_card.py`, tests.
- RED: features at `as_of` use only earlier records; training and serving call the same function; missing data stays missing; stale history is flagged; manifest hashes detect tampering.

### Task 9: Failure-mode tests and release-status record (end-to-end proof BLOCKED)
Files: tests, `docs/verification/`, `docs/DEVELOPMENT_STATUS.md`.
- Failure modes with executable tests: corrupted artifact, OOD/insufficient request, stale/missing features, authorization failures, restart persistence (in-memory contract). Provider/DB failure and the verified-data workflow are recorded BLOCKED.
