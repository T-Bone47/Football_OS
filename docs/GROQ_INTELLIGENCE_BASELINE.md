# Groq Intelligence Baseline

**Phase 0 audit — FIO grounded assistant** · audited 2026-10-21 · repo
`Football_OS-main-remediated-v2/Football_OS-main`

This document records what the Groq integration looked like *before* this work, what
the platform could actually answer, and what was missing. Every statement is backed
by a file reference, a query or a live provider probe.

---

## 1. Architecture and request flow (before)

```
Browser → dev_gateway (8004) → FIO API (8002)
                             ├─ /api/copilot/query            (SSE, plain text deltas)
                             ├─ /api/v1/players/...           (canonical read APIs)
                             └─ /llm-status, /data-status, /model-status

/api/copilot/query
  └─ app.main:172  CopilotQueryRequest
       └─ app/decisions/copilot.py:332  orchestrate_copilot_decision()
            ├─ ScoutDecisionTools (deterministic engines)   ← 11 methods
            ├─ keyword intent routing ("replace" in query?)  ← NOT model-driven
            ├─ _llm_generate() → LLMRegistry.complete_with_fallback()
            │    └─ app/llm/openai_compatible.py  (Groq, OpenAI-compatible)
            └─ yields markdown deltas; the client renders them
```

**What existed**

| Component | File | State |
|---|---|---|
| Provider abstraction | `app/llm/base.py` | `LLMProvider`, `LLMMessage`, `LLMResponse`, `LLMStreamChunk`, typed provider errors |
| OpenAI-compatible client | `app/llm/openai_compatible.py` | Groq / HF / OpenAI / Anthropic / Gemini adapters, retry with backoff, `x-ratelimit` aware error mapping |
| Provider registry | `app/llm/registry.py` | primary + optional fallback, `verify_all()`, per-provider status with `last_success_at` |
| Deterministic tools | `app/decisions/copilot.py:85` | `ScoutDecisionTools`: player intelligence, similarity, tactical fit, market context, valuation, transfer risk, squad, transfer simulation, match prediction, candidate comparison, evidence retrieval |
| Intent routing | `app/decisions/copilot.py:332` | **keyword matching** on the lower-cased query (`"replace" in q_lower`), not tool calling |
| Streaming | `app/llm/openai_compatible.py:203` | SSE parsing, first-token latency measured |
| Status endpoint | `app/main.py:125` | `/llm-status` → active provider, model, status, fallback flag |
| Frontend | `Football_OS-frontend/frontend/src/pages/CopilotPage.js` | SSE consumer, markdown rendering, provider badge, cancel, retry |

**What did not exist**

* No tool *registry*: the model could not choose a tool, and tools were not
  discoverable, typed, allowlisted, permission-checked or time-bounded.
* No evidence envelope: tool results were rendered as markdown text. Nothing recorded
  the entity id, competition, season, unit, sample size or epistemic status of a value.
* No claim validation: a number the model invented was indistinguishable from a number
  the database returned.
* No coverage awareness: the assistant could not state that a league was only partly
  ingested.
* No documentation retrieval: the model had no access to FIO's own methodology.
* No evaluation suite, no golden set, no grounding metrics.
* No observability of the inference flow (no tool trace, no retrieval counts, no
  evidence-validation outcome).

## 2. Groq configuration as found (verified live)

From `.env` (values redacted) and `app/config.py`:

| Setting | Value |
|---|---|
| `LLM_PROVIDER` | `groq` |
| `LLM_MODEL` | `openai/gpt-oss-120b` |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` |
| `LLM_FALLBACK_PROVIDER` | `huggingface` / `openai/gpt-oss-120b` (fallback **disabled**: `LLM_ALLOW_PAID_FALLBACK=false`) |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` / `LLM_MAX_OUTPUT_TOKENS` | 45 / 2 / 1200 |
| `LLM_ENABLE_STREAMING` | true |

### Live capability probe (2026-10-21, `GET {GROQ_BASE_URL}/chat/completions`)

| Check | Result |
|---|---|
| Plain completion | HTTP 200, 622 ms, **empty content** with 30 reasoning tokens of a 32-token budget — a reasoning model that spends the whole budget on reasoning |
| Streaming | HTTP 200, **0 content chunks** at a 32-token budget (same reasoning exhaustion) |
| **Tool calling** | **HTTP 200, 445 ms, well-formed `tool_calls`** — `finish_reason = "tool_calls"`, function name and JSON arguments parsed correctly |
| Account | plan **Free**, `x-ratelimit-limit: 10` req/min, **TPM limit 8 000 tokens/minute** |

Two facts shaped the implementation:

1. **Tool calling works on the configured model** — the orchestration could be built on
   real tool calls rather than keyword routing.
2. **The model needs token headroom.** With a small `max_tokens` it returns reasoning
   and no content. The existing `_llm_generate` already handled an empty answer
   honestly; the grounded path uses larger budgets and treats an empty answer as a
   visible `EMPTY_ANSWER` outcome.
3. **The 8 000 TPM limit is shared by a whole turn.** A turn makes at least two
   requests (tool planning + answer), so every payload is bounded: compact tool
   schemas, a relevance-ranked shortlist of tools, truncated tool results, and a
   shrink-and-retry when the provider refuses a request as too large.

The probe also showed the model hallucinating a name (`"M. Akangi"` for *M. Akanji*)
inside a tool argument — the concrete reason the tools resolve entities against the
canonical index and refuse to guess.

## 3. Analytics capabilities that genuinely existed

| Family | Real service | Endpoint |
|---|---|---|
| Player discovery | `routes_canonical.search_players` (filters before pagination, true total) | `GET /api/v1/players/search` |
| Player profile | `routes_canonical.get_player` | `GET /api/v1/players/{id}` |
| Roles | `app/roles/service.py` (role profiles, similarity) | `/players/roles`, `/players/{id}/similar` |
| Tactical fit | `app/tactical/service.py` | `/players/{id}/tactical-fit` |
| Market | `app/market/valuation.py`, `risk.py`, `context.py` | `/players/{id}/valuation-baseline`, `/transfer-risk`, `/market-context` |
| Recruitment | `app/decisions/recruitment.py` | `GET /decisions/recruitment` |
| Replacement | `app/decisions/replacement.py` | `POST /decisions/replacement` |
| Squad | `app/squad/service.py` | `GET /squads/build` |
| Match | `app/prediction/service.py` | `/matches/{id}/prediction` |
| Coverage (added in the previous phase) | `app/coverage/service.py` | `GET /api/v1/coverage/*` |
| Data freshness | `app/observability/system_health.py` | `GET /data-status` |
| Model registry | `app/observability/system_health.py` | `GET /model-status` |

**Not implemented (and therefore not offered as tools):** league standings (the
provider endpoint is not normalised into the canonical model), salary/contract data,
injuries as a canonical table, live (in-play) data, and a semantic/vector store.

## 4. Database and retrieval capabilities (as found)

* PostgreSQL 16.15, 39 tables after the expansion phase: 2 334 canonical players,
  4 744 player-season rows, 1 228 player-match-stat rows, 116 018 match events, 599
  clubs, 1 247 competitions, 220 transfers, 2 021→2 334 provider identities across
  two providers (`api-football`, `statsbomb`).
* Retrieval was **relational only**. There is no `pgvector` column, no embedding
  table and no document index; FIO's documentation was only readable by a human.
* Provenance existed at the *record* level (`data_snapshots`, `ingestion_runs`,
  `player_identities`) but not at the *field* level: there was no way to ask "which
  provider supplied this minute value, for which competition-season, measured when".

## 5. Chat functionality and limitations (as found)

* The copilot answered, streamed and rendered markdown.
* The answer was assembled by a keyword router over a fixed set of engines; the model
  could not ask for a capability the router did not anticipate.
* The model received the 15 players selected in the UI plus a system prompt, and
  nothing else. Any statement about the platform's data, coverage, models or
  methodology came from the model's pretrained knowledge.
* A missing value could be presented as a fact; there was no validator.
* Provider failure was reported as a string in the answer body
  (`**LLM Error**: ...`), not as a distinct status the client could act on.

## 6. Test state before this work

| Suite | Result |
|---|---|
| Backend (`pytest -q`) | 996 passed, 9 skipped, 0 failed |
| Frontend (`yarn test`) | 8 passed, 2 suites |
| Frontend build | compiled successfully |
| Live provider test | opt-in (`LIVE_PROVIDER_TESTS=1`), not run in CI |
| AI/grounding tests | **none existed** |

## 7. Security and privacy concerns found

* `app/decisions/copilot.py` interpolated the provider exception text straight into the
  answer (`**LLM Error**: {e}`), which could surface internal details.
* The copilot had no authorization concept: the engines were called with the request's
  session and returned the data the session could reach, but nothing recorded or
  bounded *which* engines ran.
* No rate limiting on the LLM path, and the provider's own limit was the only
  protection.
* User text and retrieved text were concatenated into the prompt without a boundary
  that marked retrieved content as data.
* The legacy copilot endpoint bypassed the canonical player API and therefore the
  platform's pagination and coverage rules.

## 8. Recommended implementation sequence (and what was executed)

1. **Tool registry** — typed, allowlisted wrappers over the existing services
   (30 tools across 7 families), with permission, timeout and result-size budgets.
2. **Evidence + claim validation** — an evidence envelope with epistemic status, and a
   deterministic check of the answer's numbers and entity ids against the retrieved
   evidence.
3. **Model-driven orchestration** — a bounded tool-calling loop against the *verified*
   Groq capability, with a shrink-and-retry path for the TPM limit.
4. **Documentation grounding** — retrieval over `docs/**/*.md` with section metadata,
   injected as *data* into the system prompt.
5. **Coverage-aware answers** — the coverage service exposed as a tool, and the
   system prompt instructing the model to disclose partial coverage.
6. **Frontend** — the copilot page now streams the grounded turn and renders the tool
   trace, the evidence table and the grounding verdict.
7. **Evaluation** — a 12-case golden set with an opt-in live runner that measures
   tool-selection accuracy, grounded-answer rate, unsupported-numeric rate and
   latency.
8. **Fine-tuning assessment** — evaluated, not performed; see
   `docs/GROQ_FINE_TUNING_ASSESSMENT.md`.
