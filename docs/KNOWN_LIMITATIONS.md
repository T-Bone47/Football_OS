# Known Limitations

**Date:** 2026-10-21. Every item below is reproducible and states what is missing, what the
system does instead, and what would close it. Nothing here is presented as a working capability.

## L1 — Provider plan caps the player universe (`BLOCKED_BY_PROVIDER`)

- **Scope:** API-Football, `GET /players?league=39&season=2023`. The provider declares
  `paging.total = 51` pages (1,020 records). The free plan caps the `page` parameter at 3:
  `Free plans are limited to a maximum value of 3 for the Page parameter`.
- **What we did:** fetched and normalised pages 1–3 (60 records), stored one Bronze snapshot per
  page, recorded the failed page-4 run, and reported the scope as `BLOCKED_BY_PLAN` through
  `GET /api/v1/players/coverage` (`declared_total_pages=51`, `completed_pages=3`,
  `accessible_pages=3`, `provider_plan_limit.page_max=3`).
- **What we did not do:** we did not narrow league/season filters to make the number look
  complete, we did not synthesise rows, and we did not bypass the limit.
- **Closes when:** the account has a plan that allows `page > 3`, or the CLI is pointed at a
  scope whose page count is within the plan. `python tools/ingest_api_football.py players
  --league 39 --season 2023 --resume` continues from page 4 automatically.

## L2 — Four sidebar modules are demo-gated (`NOT_IMPLEMENTED` on canonical data)

- **Scope:** Phase 11 (Global operations), Phase 12 (Continuous learning), Phase 13 (Decision
  Lab 2.0), Phase 14 (Outcome intelligence). Their routers are mounted with
  `Depends(require_demo_data)` and answer `409 {"code":"DEMO_ONLY"}` outside demo mode.
- **State now:** the UI states this explicitly. The Decision Lab and Continuous learning pages
  additionally had a **wrong base URL** (`REACT_APP_API_URL`, undefined) that hid the refusal
  behind empty panels; both now reach the API and render a truthful banner.
- **Closes when:** each phase is rebuilt on the canonical store (the same rebuild that produced
  the Phase 10 surfaces), and its own release report is re-issued.

## L3 — No transfer data, so the market family is data-starved (`INSUFFICIENT_DATA`)

- `transfers` holds 0 rows and `valuation_predictions` holds 0 rows. The API-Football free plan
  exposes no transfer endpoint.
- Consequently: `valuation-baseline` answers `VALUATION_UNAVAILABLE` /
  `RANGE_NOT_AVAILABLE` / `INSUFFICIENT_DATA` with `estimated_value_eur = null`; comparables
  answer `comparables_count = 0`; opportunities, replacements and transfer risk have nothing to
  rank. **Unknown fees stay unknown** — nothing is coerced to 0.
- The market module is also affected by the missing live-ingredient table, but the code path is
  implemented and returns honest empty states.

## L4 — The `roles` page issues 85 HTTP requests per load (performance)

`/players/roles` samples 80 players and calls `GET /api/v1/players/{id}/role` for each one
(80 + 1 search + facets + auth). This is an N+1 fan-out over the API rather than a batch
endpoint. The page is correct but slow and chatty. **Closes when:** a batch role endpoint
(`GET /api/v1/players/roles?ids=…`) is added.

## L5 — `matches` has no total and no pagination

`GET /api/v1/matches?limit=50` is a bounded list with no total, so the Matches module cannot
show "showing X of Y" and cannot page. The players module was fixed to a paginated contract; the
matches module has not had the same treatment yet.

## L6 — The data-quality page reports a 5-row sample next to a `HEALTHY` badge

`/system/data-quality` probes `/api/v1/players?limit=5` and renders "5 records" under a
`HEALTHY` label. That is a probe, not a census, and can be misread as the row count. The players
total (109) is available from `/api/v1/players/search` and should be used instead.

## L7 — Write paths were not exercised against the production database

Recruitment projects, watchlists/alerts, shortlists and decision records were read (all empty
or 200) but **not written** in this session, to avoid creating records in the live `fios`
database during a verification pass. Their create/update/delete behaviour therefore rests on the
existing unit tests (`test_phase10_operations.py`, `test_phase10_recruitment_truth.py`,
`test_persistence_contract.py`), not on this session's evidence.

## L8 — Remaining failing tests (exact, reproducible)

Full-suite result after this pass: **8 failed, 938 passed, 10 skipped, 0 errors** (was
`9 failed, 902 passed, 27 skipped, 18 errors` before the isolation fix).

| Test | Cause | Status |
|---|---|---|
| `tests/unit/test_decision_api_contracts.py::test_copilot_decision_orchestrator_mocked` | the mock in the test no longer matches the orchestrator's call contract | open |
| `tests/unit/test_phase8_security_and_performance.py::TestCopilotSecurityAndSandboxing::test_copilot_handles_malicious_injections_safely` | copilot injection expectation | open |
| `tests/unit/test_phase8_security_and_performance.py::TestCopilotGroundingAndZeroFabrication::test_copilot_replacement_truthful_grounding` | copilot replacement grounding expectation | open |
| `tests/unit/test_transfer_completion_4_1d.py` (5 tests) | the transfer fixtures under `data/bronze/open-transfers/` are absent, so the phase cannot be rebuilt | open |

These are **not** hidden by skips: they fail. They are unrelated to the player-pagination and
squad/market repairs made in this pass (the targeted regression set around those changes is
green), but they are release-blocking for a "production truth" claim.

One failure was closed by this pass:
`tests/unit/test_persistence_contract.py::test_postgres_rejects_update_and_delete_on_the_ledger_at_the_database_level`
now passes, because the schema guard restores the **migrated** schema (which includes the
append-only ledger trigger) instead of the `create_all` schema that lacks it.

## L9 — Test isolation was broken until this pass

`tests/integration/test_ingestion_lifecycle.py` created the schema with `create_all` and dropped
it with `drop_all` in teardown **on the shared test database**. Any suite that ran after it
errored with `UndefinedTableError` (18 errors in the first full-suite run), and the leftover
`alembic_version` row made `alembic upgrade head` a no-op on a database whose tables were gone.
The same pattern existed in 15 further integration files.

Fixed so far:

- `tests/integration/test_ingestion_lifecycle.py` and `tests/integration/test_capability_registry.py`
  now use the shared transaction-rollback fixture and state their preconditions explicitly.
- `tests/conftest.py` gained an autouse **schema guard**: before every test it checks that the
  migrated schema is present and, if a legacy suite has removed it, rebuilds it from the
  migration history. A destructive suite can no longer break the suites that follow it.

Still open: 13 integration files still call `create_all`/`drop_all` in their own fixtures. The
guard contains the damage, but each of those files should be migrated to transaction rollback.
The guard also re-runs the migration history, so it costs a few seconds whenever it has to
repair the schema.

## L10 — LLM provider matrix is not fully covered by automated tests

Live Groq completion and streaming are verified (§ `LLM_PROVIDER_VALIDATION.md`), and the
analytics provider layer has error-classification tests, but the requested LLM matrix (invalid
key, quota, rate limit, timeout, connection failure, unsupported model, malformed output, empty
completion, fallback, all-providers-down, tool-call validation, cancellation, secret redaction)
is not yet an automated suite.

## L11 — `last successful inference` is not persisted

`/llm-status` reports the health-probe timestamp and a `streaming_verified` flag, but the
timestamp of the last successful *completion* is not stored in the database, so it resets on
restart.

## L12 — Reasoner-model token budget

`openai/gpt-oss-120b` spends reasoning tokens from the same `max_tokens` budget (35 of 52 tokens
in the acceptance run). A small budget yields an empty answer even though the call succeeded.
The copilot's budget is sufficient, but this is not guarded by a test.

## L13 — Similarity and roles are thin on data

`feature_snapshots` holds 7 rows and `player_contribution_snapshots` 21, of which 7 dimension
scores are unknown (`null`). The similarity, role and tactical-fit surfaces therefore rank a
very small eligible population; several players legitimately report `INSUFFICIENT_SAMPLE` and
withhold percentiles. This is correct behaviour on thin data, not a crash.

## L14 — Only the free API-Football plan is available in this environment

Hugging Face returned HTTP 402 (no credits) and Gemini returned HTTP 404 for the configured
model id. Neither is a usable inference fallback, and the platform is configured with
`fallback_enabled = false` so a fallback can never hide a primary-provider failure. Groq is the
only verified inference provider.
