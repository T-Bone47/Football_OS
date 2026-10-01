# Phase 17 — Backup, Restore and Rollback

Evidence: `docs/evidence/phase17/dr_drill.json` (`tools/phase17/dr_drill.py`), `rollback_drill.json` (`tools/phase17/rollback_drill.py`), adversarial test 30.

## 1. Backup → restore → verify (§37)

Performed for real on the live-ingested database (`fios_p17_live`, PostgreSQL 16.14, local disk):

| Step | Measured |
|---|---|
| `pg_dump -Fc` | 0.31 s, 1.83 MB (dump SHA-256 recorded) |
| `pg_restore` into a new database | 0.91 s, exit 0 |
| Verification | 47 tables, 27,212 rows: **0 row-count mismatches**. Audit chain valid on the restore with an **identical head hash**. Decision content hashes equal. Model registry rows equal. All 3 immutability triggers present. Migration head `0014`. |
| Bronze archive (tar.gz) | 506 files, 7.76 MB compressed; backup 4.2 s, restore 0.3 s; **every file re-hashed to its own name** (0 mismatches) |
| Configuration | templates and migrations hashed into a manifest. `.env` is deliberately **not** backed up; production secrets belong to the secret manager's own backup |
| Measured recovery time (dump + restore + verify + Bronze restore) | **≈1.8 s** at this data volume |

| Component | Status |
|---|---|
| PostgreSQL | VERIFIED (local) |
| Bronze snapshots (local filesystem) | VERIFIED |
| Configuration (templates) | VERIFIED (hash manifest) |
| Model registry | VERIFIED (inside PostgreSQL) |
| Critical audit records | VERIFIED (chain valid, head hash equal) |
| Object storage (S3/MinIO) | **NOT_TESTED**: no object store reachable here (no Docker daemon) |
| Production-scale RTO/RPO | **NOT_TESTED**: no production deployment |

## 2. Rollback (§48)

| Kind | Procedure | Result |
|---|---|---|
| Application | Run the previous release against the current schema. Migration 0014 is additive (new tables plus nullable columns), so N-1 code runs on the N schema | **VERIFIED**: commit `eb2ad0d` started from a git worktree against the migrated live database. `/health/ready`, `/api/v1/players`, `/api/v1/matches` and `/api/v1/competitions` all returned 200 with data |
| Migration | `alembic downgrade 0013` then `upgrade head` | **VERIFIED on a data-bearing copy**: canonical data preserved (478 matches, 18,275 lineups, 360 events, 1,802 players, 527 snapshots unchanged). **Operational evidence is dropped** by the downgrade. Schema after re-upgrade is identical to head, including triggers (adversarial 30) |
| Model | `POST /api/v1/ops/models/{id}/demote` (ACTIVE → SHADOW → REGISTERED), audited | **VERIFIED**: SHADOW → REGISTERED; second demote 409; `MODEL_DEMOTED` audit event |
| Configuration | revert `deploy/env/*.env.example` in git and redeploy | **NOT_TESTED**: no deployed configuration store |

### Migration policy
- **Never** roll back 0014 in production: `downgrade` drops the immutable operational tables (inference log, decisions, audit). Roll the application back instead (N-1 is compatible) and forward-fix the migration.
- The downgrade exists for development databases only, and its docstring says so.
- Restoring a pre-0014 backup and then running `upgrade head` should leave the new tables empty and the new snapshot columns null for old rows (`provider_retrieved_at` would be null, never backfilled with a guess). This path is **NOT_TESTED**.
