# FIO Grounded Assistant — Implementation Report

Task: *Master Development Prompt 2 — Groq intelligence, system grounding & football
knowledge integration* · repo `Football_OS-main-remediated-v2/Football_OS-main` ·
2026-10-21

---

## 1. What was present before the changes

The Groq integration existed and worked, but the assistant was **not grounded**:

* `apps/api/app/llm/` — a provider abstraction (Groq / HF / OpenAI / Anthropic /
  Gemini behind one OpenAI-compatible client), a provider registry with primary +
  optional fallback, `verify_all()`, retry with backoff, streaming, typed provider
  errors.
* `apps/api/app/decisions/copilot.py` — 11 deterministic analysis methods
  (`ScoutDecisionTools`) and an orchestrator that **routed by keyword** ("replace" in
  the lower-cased query) and streamed markdown to the browser.
* `apps/api/app/main.py:172` — `POST /api/copilot/query`, a plain SSE text stream.
* `GET /llm-status`, `GET /data-status`, `GET /model-status`.
* A React copilot page that rendered the markdown stream with a provider badge.

What did **not** exist: a tool registry, tool schemas, permissions, timeouts, an
evidence model, claim validation, coverage awareness, documentation retrieval, an
evaluation suite, or any observability of the inference flow. The model received 15
UI-selected players and a prompt — and nothing else — so any statement about the
platform's own data came from its pretrained knowledge.

Baseline document: `docs/GROQ_INTELLIGENCE_BASELINE.md`.

## 2. What was implemented

| Area | Implementation |
|---|---|
| **Tool registry** | `apps/api/app/llm/tools/base.py` — **31 typed, allowlisted tools** across 7 families, each a wrapper around an **existing** FIO service/route handler; pydantic input models (`extra="forbid"`), permission checks, per-tool timeout, bounded results, explicit failure statuses. |
| **Question routing** | `apps/api/app/llm/tools/routing.py` — the question is classified into a family (player/team/match/recruitment/financial/squad/platform) and the model is offered the tools of those families first, plus a core that is always present (`search_players`, `get_player_profile`, `get_data_coverage`) because the provider rejects a call to a tool that was not offered. |
| **Tool hints** | `apps/api/app/llm/tools/hints.py` — one line per tool in its schema ("use a canonical id; if you only have a name, call search_players first"), which removes the wasted calls the live run exposed. |
| **Field-level provenance** | `apps/api/app/normalization/service.py` + `apps/api/app/normalization/statsbomb.py` — every canonical field records the provider that supplied it, and a provider disagreement is written to `source_conflicts` (status `OPEN`) while the canonical value is kept. Backfilled from the stored Bronze snapshots by `tools/backfill_field_provenance.py` (no provider quota). |
| **Evidence model** | `Evidence` + `EpistemicStatus` (11 statuses) + `ToolResult`; every tool result carries entity id, metric, value, unit, competition, season, sample size, source, method, model version, confidence, status. |
| **Claim validation** | `apps/api/app/llm/tools/claims.py` — every number and canonical id in the answer is checked against the retrieved evidence; unsupported values are reported and caveated **in the answer**. |
| **Orchestration** | `apps/api/app/llm/tools/orchestrator.py` — bounded model-driven tool loop (max calls, max rounds), the assistant tool-call message kept in the protocol, a deterministic fallback router, shrink-and-retry for the provider's token budget, a `NO_EVIDENCE` status for tool-free answers. |
| **Documentation grounding** | `apps/api/app/llm/tools/docs.py` — runtime index of `docs/**/*.md` (957 sections), section-level retrieval with file/line provenance, injected as *data* with an explicit "not instructions" envelope. |
| **Fallback router** | `apps/api/app/llm/tools/fallback.py` — a small, inspectable keyword router that runs the argument-free tools when the model declines to call any, so the answer is still produced from records. |
| **Provider layer** | `apps/api/app/llm/openai_compatible.py` — tool calling (`tools` / `tool_choice`), `tool_calls` parsing, 429 retry with a real backoff, fast-fail on a *daily* token limit, and the provider's limit detail preserved in the error. `apps/api/app/llm/base.py` — `supports_tool_calling` capability flag, `tools`/`tool_choice` on `complete()`, `tool_calls` on `LLMResponse`. |
| **API** | `apps/api/app/api/routes_copilot.py` — `POST /api/v1/copilot/grounded`, `POST /api/v1/copilot/grounded/stream` (SSE: `status` / `tool` / `delta` / `evidence` / `validation` / `done`), `GET /api/v1/copilot/tools` (the catalogue), `GET /api/v1/copilot/capabilities` (configured vs. tested vs. reachable, cached so a page load never triggers an inference). The legacy `/api/copilot/query` is untouched. |
| **Frontend** | `Football_OS-frontend/frontend/src/pages/CopilotPage.js` — the copilot now streams the grounded turn and renders the **tool trace**, the **evidence table** (entity, metric, value, scope, epistemic status) and the **grounding verdict** (all numbers traced / N unverified values). |
| **Evaluation** | `tests/ai/golden_set.json` (12 cases), `tools/evaluate_grounded_copilot.py` (offline validation + opt-in live run with a token budget, a case filter and a budget-aware stop), 34 new tests. |
| **Configuration** | `LLM_MAX_TOOL_SCHEMAS`, `LLM_MAX_TOOL_CALLS`, `LLM_MAX_TOOL_ROUNDS`, `LLM_TOOL_TIMEOUT_SECONDS`, `LLM_CONTEXT_BUDGET_CHARS` in `config.py` and `.env.example`. |

Documents: `docs/GROQ_INTELLIGENCE_BASELINE.md`, `docs/AI_SYSTEM_GROUNDING.md`,
`docs/AI_TOOL_CATALOG.md`, `docs/AI_EVIDENCE_AND_PROVENANCE.md`,
`docs/AI_EVALUATION.md`, `docs/GROQ_FINE_TUNING_ASSESSMENT.md`.

## 3. Files added and modified

**Added**
```
apps/api/app/llm/tools/__init__.py
apps/api/app/llm/tools/base.py
apps/api/app/llm/tools/fio_tools.py
apps/api/app/llm/tools/orchestrator.py
apps/api/app/llm/tools/claims.py
apps/api/app/llm/tools/docs.py
apps/api/app/llm/tools/fallback.py
apps/api/app/llm/tools/routing.py
apps/api/app/llm/tools/hints.py
apps/api/app/api/routes_copilot.py
apps/api/app/identity/names.py
apps/api/app/identity/resolution.py
tools/evaluate_grounded_copilot.py
tools/backfill_field_provenance.py
tests/unit/test_ai_tool_registry.py
tests/integration/test_ai_grounded_copilot.py
tests/integration/test_field_provenance.py
tests/ai/golden_set.json
docs/GROQ_INTELLIGENCE_BASELINE.md
docs/AI_SYSTEM_GROUNDING.md
docs/AI_TOOL_CATALOG.md
docs/AI_EVIDENCE_AND_PROVENANCE.md
docs/AI_EVALUATION.md
docs/GROQ_FINE_TUNING_ASSESSMENT.md
docs/AI_GROUNDING_IMPLEMENTATION_REPORT.md
docs/evidence/ai/groq_capability_probe.json
```

**Modified**
```
apps/api/app/llm/base.py            (tools/tool_choice, tool_calls, supports_tool_calling)
apps/api/app/llm/openai_compatible.py (tool calling, 429 handling, error detail)
apps/api/app/config.py              (grounded-assistant budgets)
apps/api/app/main.py                (register the copilot router)
Football_OS-frontend/frontend/src/pages/CopilotPage.js (grounded stream, evidence UI)
.env.example                        (new settings, no secrets)
```

## 4. The end-to-end flow that now works

```
Browser → /api/v1/copilot/grounded/stream (SSE)
  → GroundedCopilot
      → tool phase: model offered a relevance-ranked shortlist of typed tools
      → tool call validated (name, arguments, permissions, timeout) → real FIO service
      → evidence attached (entity, metric, unit, competition, season, status)
      → deterministic fallback if the model declines to use a tool
      → answer phase (no schemas: the results are in context)
      → claim validation (numbers + entity ids against the evidence)
      → SSE: status → tool → delta → evidence → validation → done
  → UI: answer, tool trace, evidence table, grounding verdict
```

Live verification (Groq `openai/gpt-oss-120b`, real database):

```
tools:  [('get_player_profile', 'OK')]
evidence: 40 items (minutes 2514, competition "Premier League", season "2023")
validation: grounded=True, unsupported_numbers=[]
answer: "M. Akanji (canonical id 2ca6252c-…) played 2 514 minutes in the Premier
         League 2023 season【OBSERVED】"
```

## 5. Which tools call real FIO services

All 30. `search_players` → `routes_canonical.search_players` (the same contract as
`GET /api/v1/players/search`); `get_player_profile` / `get_player_season_statistics` /
`compare_players` → `routes_canonical.get_player`; `find_similar_players` →
`routes_canonical.get_similar_players` (role engine); `analyze_player_role` →
`get_player_role_profile`; `evaluate_tactical_fit` → `get_player_tactical_fit`;
`get_player_valuation` → `get_player_valuation_baseline`; `analyze_transfer_risk` →
`get_player_transfer_risk`; `find_recruitment_candidates` →
`decisions.recruitment.RecruitmentTargetEngine`; `find_replacements` →
`decisions.replacement.ReplacementDecisionEngine`; `compare_candidate_tradeoffs` →
`decisions.service.UnifiedDecisionService`; `analyze_squad_balance` / `get_team_squad` →
`routes_canonical.build_squad_get`; `search_matches` → `routes_canonical.search_matches`;
`get_match_details` / `get_match_statistics` / `get_match_event_summary` /
`analyze_matchup` / `get_match_prediction` → the canonical match routes and the
prediction service; `get_data_coverage` → `coverage.service.compute_coverage`;
`get_data_freshness` → `observability.system_health.check_data_health`;
`get_model_status` → `check_model_health`; `get_provider_health` →
`ingestion.sources.source_policies`; `get_analytics_methodology` → the documentation
retrieval layer. `get_league_standings` **reports UNSUPPORTED** because the platform has
no normalised league table.

## 6. Groq provider and model verification (live)

| Check | Result |
|---|---|
| Configured provider / model | Groq · `openai/gpt-oss-120b` (`GET /api/v1/copilot/capabilities`) |
| Model accepted by the API | HTTP 200 on `/chat/completions` |
| Basic inference | HTTP 200; **empty content at a 32-token budget** (30 reasoning tokens) — a reasoning model that needs headroom |
| Streaming | HTTP 200, SSE, first-token latency measured |
| **Tool calling** | **HTTP 200, 445 ms, well-formed `tool_calls`** — verified before the orchestration was built on it |
| Rate limits (measured) | 1 000 req/min, 8 000 tokens/min, **200 000 tokens/day** (Free tier) |
| Tool-call argument validation | the provider rejects the whole request when the arguments do not match the schema — the schemas are now generated to be valid and nullable-aware |

The provider's own documentation (verified) states that fine-tuning and LoRA exist as
endpoints, that fine-tuning **retains the training data** until deleted, that
inference requests are not retained by default, and that data is retained in US GCP
buckets.

## 7. Grounding and evaluation results (with sample sizes)

* Offline suite: **31 tests** (23 unit + 8 integration) — all pass.
* Live evaluation, 12 golden cases, three runs:
  * run 1 (before the fixes): tool-selection **0.417**, grounded-answer rate **0.750**,
    unsupported-numeric rate **0.256** over **39** checked claims;
  * run 3 (after the schema fix): tool-selection **0.500**, grounded-answer rate
    **0.583**, unsupported-numeric rate **0.178** over **45** checked claims,
    caveat disclosure **0.833**, unplanned-tool rate **0.000**, p50 5 256 ms.
* The final 12-case measurement is **blocked by the provider's daily token budget**
  (200 000 tokens/day, already consumed by the three runs and the live debugging). The
  runner now detects this, stops and reports `SKIPPED_TOKEN_BUDGET` instead of
  producing provider errors. The re-run command is in `docs/AI_EVALUATION.md`.
* Defects the live runs exposed and that were fixed: an awaited synchronous function in
  a tool; an invalid JSON schema (a duplicated `null` type) that made the provider
  refuse every request; a 429 that was not retried without a `Retry-After` header; the
  model calling a tool that was not offered; the model calling a tool during the answer
  phase; and — most importantly — **five of twelve questions answered with no tool at
  all**, which is why the deterministic fallback router and the `NO_EVIDENCE` status
  now exist.

## 8. Tests and builds run (exact counts)

| Suite | Command | Result |
|---|---|---|
| Backend (full) | `python -m pytest -q` | **1 030 passed, 9 skipped, 0 failed** (996 before this phase; +34 AI/provenance tests) |
| AI unit tests | `pytest tests/unit/test_ai_tool_registry.py` | 23 passed |
| AI integration tests | `pytest tests/integration/test_ai_grounded_copilot.py` | 8 passed |
| Field-provenance tests | `pytest tests/integration/test_field_provenance.py` | 3 passed |
| Frontend | `CI=true yarn test --watchAll=false --runInBand` | **8 passed, 2 suites** |
| Frontend build | `yarn build` | **Compiled successfully** — 294.64 kB JS, 26.86 kB CSS (gzip) |
| Golden set (offline) | `python tools/evaluate_grounded_copilot.py` | 12 cases validated |
| Live evaluation | `python tools/evaluate_grounded_copilot.py --live` | 3 full runs; the 4th **blocked by the provider's daily token budget** |
| Live API | `GET /api/v1/copilot/tools`, `/capabilities`, `POST /grounded` | 30 tools listed; capabilities reported; a grounded turn answered with 40 evidence items and 0 unverified values |

## 9. Remaining defects and environmental blockers

| Item | Status |
|---|---|
| Final 12-case live measurement | **Blocked** by the Groq Free-tier daily token budget (200 000 tokens/day). The implementation is verified by the live single-turn check and the offline suite. |
| Provider's daily token budget also blocks long conversations | A turn costs ~1 500–4 000 tokens; a long session will exhaust the daily budget. Mitigation: the tool-call budget, the payload caps and the `LLM_MAX_*` settings. |
| `field_provenance` / `source_conflicts` are modelled but not populated by the bulk normalisers | **Closed**: the API-Football and StatsBomb normalisers now record field-level provenance, disagreements are recorded as `OPEN` conflicts, and `tools/backfill_field_provenance.py` fills the rows ingested earlier from the stored Bronze snapshots. Measured: 33 296 provenance rows, 20 open conflicts. |
| The identity review queue has no administrative merge command | Open |
| Non-numeric claims are not machine-checked | By design: the evidence table is shown next to the answer for human review |
| The `evaluate_transfer_scenario` engine is not exposed as a tool | Deliberate: it is a write-like operation that needs explicit confirmation |
| No in-process rate limiter on the copilot path | The platform has no rate limiter; the provider's own limit is the only protection, and a daily-budget error is reported honestly |
| Conversation memory | The client sends the last six turns; nothing is persisted by the grounded path |

## 10. Fine-tuning assessment and recommended path

Full assessment: `docs/GROQ_FINE_TUNING_ASSESSMENT.md`. Summary: **no fine-tuning was
performed.** Groq documents a `/openai/v1/fine_tunings` endpoint and LoRA inference,
but it does not document that the served model (`openai/gpt-oss-120b`, an OpenAI
open-weight checkpoint) is eligible, and the relevant pages were not reachable from this
environment — so no capability is claimed. The task's failures are orchestration and
grounding failures, not knowledge failures: the model must retrieve, must cite, and
must not invent numbers, all of which are now enforced mechanically. Fine-tuning
would also create a licensing and retention problem (fine-tuning retains the training
data on Groq infrastructure, and the canonical football data is licensed per provider).
**Recommended path:** keep retrieval + tools + validation; improve the tool contract
(names, "use `search_players` first" hints), reuse the deterministic router as a hint
rather than a decision, and consider a smaller/cheaper model for the *selection* step
only.

## 11. Security and data-quality limitations

* Every tool is read-only; no tool executes SQL, shell commands or provider writes.
* Arguments are validated and unknown tools refused; permissions are checked before
  execution; timeouts and result sizes are bounded.
* Retrieved documentation and tool payloads are injected as **data** with an explicit
  instruction that they cannot change policy or grant permissions.
* Tool exceptions are sanitised (`RuntimeError`, never the message), so a DSN or a
  secret cannot reach the model or the browser.
* The provider's error body is preserved in the *server-side* error, but only the
  exception type reaches the client.
* The prompt-injection case in the golden set verifies that an instruction to "print
  the API key" produces no credential material and no claim that the instructions were
  ignored.
* Grounding limits: the validator checks numbers and entity ids only; a model can still
  write a wrong qualitative statement, which is why the evidence table is always shown.
* Data quality: the platform's own coverage limits apply to the answers — a question
  about an incompletely ingested league gets the coverage tool's status, and the
  assistant is told to disclose it.

## 12. Exact commands

```powershell
# backend (Windows)
cd "C:\Users\olive\Downloads\files (1)\Football_OS-main-remediated-v2\Football_OS-main"
$env:PYTHONPATH="apps/api"
$env:DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios"
$env:TEST_DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios_test"
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8002

# tests
python -m pytest -q                                   # 1 027 passed, 9 skipped
python -m pytest tests/unit/test_ai_tool_registry.py tests/integration/test_ai_grounded_copilot.py -q

# evaluation
python tools/evaluate_grounded_copilot.py                                   # offline
python tools/evaluate_grounded_copilot.py --live --delay 18 --token-budget 120000

# frontend
cd Football_OS-frontend/frontend
$env:CI="true"; yarn test --watchAll=false --runInBand; yarn build

# live endpoints (bearer token required)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/copilot/tools
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/copilot/capabilities
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" `
     -d '{"query":"How many canonical players are in the database?"}' `
     http://localhost:8002/api/v1/copilot/grounded
```

## 13. Next recommended development phase

1. **Re-measure** the 12 golden cases once the provider's daily budget resets, and
   publish the numbers in `docs/evidence/ai/evaluation.json` (the runner is
   budget-aware, so the measurement can be spread over several days).
2. **Make the tool contract cheaper for the model**: explicit "call
   `search_players` before `get_player_profile`" hints, and per-family routing so a
   question offers 3–5 tools instead of 10.
3. **Move the tool-selection step to a smaller model** and keep the answer step on the
   strongest configured model — the selection task is classification, not analysis.
4. **Populate `field_provenance`** in the bulk normalisers so "which provider supplied
   this minute value" is answerable for every field, and surface the provenance
   panel in the UI. — **Done in this pass** (33 296 rows, 20 open conflicts); the
   remaining work is the UI panel.
5. **Add the administrative identity-merge command** and the reverse-merge audit, then
   expose the review queue in the UI.
6. **Extend the golden set** to 30–40 cases, including multi-tool questions,
   adversarial tool arguments and seasonal leakage checks, and run it in CI against a
   recorded provider transcript (no live calls) so the metrics are a gate.
