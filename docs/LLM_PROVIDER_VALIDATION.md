# LLM Provider Validation

**Date:** 2026-10-21 · **Primary provider:** Groq · **Model:** `openai/gpt-oss-120b` · **Base URL:** `https://api.groq.com/openai/v1`

Everything below was executed against the live provider. No mock, no configuration-only check,
no secret printed.

## 1. Live inference acceptance test

Prompt: `Reply with exactly: FIO_GROQ_OK`, executed through the application's own provider code
path (`app.llm.registry` → `GroqProvider` → `OpenAICompatibleProvider`), i.e. the same path the
copilot uses.

### 1.1 Non-streaming

```json
{
  "provider": "Groq",
  "model": "openai/gpt-oss-120b",
  "base_url": "https://api.groq.com/openai/v1",
  "non_streaming": {
    "ok": true,
    "duration_ms": 478,
    "text": "FIO_GROQ_OK",
    "model": "openai/gpt-oss-120b",
    "usage": {
      "prompt_tokens": 81,
      "completion_tokens": 52,
      "total_tokens": 133,
      "completion_tokens_details": { "reasoning_tokens": 35 },
      "queue_time": 0.212140738,
      "total_time": 0.10709679
    }
  }
}
```

Observed across three consecutive runs: 478 ms / 612 ms / 706 ms, text `FIO_GROQ_OK` every time.
`model` in the response body is the configured model, confirming the account can serve it.

> Note: `openai/gpt-oss-120b` is a **reasoning** model. With `max_tokens=32` the response text
> was empty because 30 of the 32 tokens were consumed as reasoning tokens. This is provider
> behaviour, not a defect — the copilot's own token budget must leave room for the answer.

### 1.2 Streaming

```json
{
  "streaming": {
    "ok": true,
    "chunks": 6,
    "time_to_first_token_ms": 379,
    "duration_ms": 379,
    "assembled": "FIO_GROQ_OK"
  }
}
```

Six ordered chunks, no duplication, no reordering, assembled text matches the non-streaming answer.

### 1.3 Health verification (the call behind `/llm-status`)

```json
{ "status": "AVAILABLE", "provider": "Groq", "model": "openai/gpt-oss-120b", "streaming_verified": true }
```

## 2. `/llm-status` (live)

```json
{
  "active": {
    "provider": "Groq",
    "model": "openai/gpt-oss-120b",
    "configured": true,
    "status": "AVAILABLE",
    "last_check": "2026-10-20T20:34:45Z",
    "last_error": null,
    "latency_ms": null,
    "streaming_verified": true,
    "fallback_used": false
  },
  "providers": [ { "provider": "Groq", "status": "AVAILABLE", "streaming_verified": true, "fallback_used": false } ],
  "fallback_enabled": false
}
```

**Defect fixed here:** `LLMRegistry.get_active_status()` looked the provider status up by
`provider.provider_name` (`"Groq"`) while `verify_all()` wrote it under the settings key
(`"groq"`), so the *active* status was permanently `CONFIGURED_UNVERIFIED` and the dashboard /
copilot badge could never show a verified provider. The registry now tracks the primary and
fallback keys explicitly (`apps/api/app/llm/registry.py`), and the status object is keyed and
labelled consistently. Regression test: `tests/unit/test_llm_registry.py`.

**Frontend defect fixed here:** `getLLMStatus()` requested `/api/v1/llm-status`, but the route is
mounted at the application root (`/llm-status`), so the dashboard and copilot always showed
"NOT_CONFIGURED". Fixed in `src/lib/footballApi.js`.

The endpoint separates `configured`, `reachable` (`status`), `inference_verified`
(`streaming_verified` plus a successful completion) and `ready` (no error, fallback not used).
It never exposes a key, an environment value or a stack trace — the failure field carries the
provider's sanitised error category only.

## 3. End-to-end through the product

The copilot page (`/copilot`) issued a real streaming request to `POST /api/copilot/query` and
rendered a grounded answer:

- The page showed `GROQ (OPENAI/GPT-OSS-120B) · AVAILABLE · STREAMING VERIFIED`.
- The context line read **“Context passed to the model: 15 of 109 canonical players (server
  total; the model receives a bounded sample, not the whole index)”** — the model is told the
  size of the sample, and the sample size follows the backend total (not a fixed 50).
- The answer contained a recruitment decision for **A. Danjuma** (Inside Forward, tactical fit
  68.0 %, estimated fee €13,200,000, risk MEDIUM, evidence status `DECISION_AVAILABLE`) and a
  summary of the ten players visible to the model, with excluded candidates and their reasons.
- The copilot did not answer from pretrained knowledge: the players it named are the ones in the
  connected canonical index, and it was explicit about what it could not see.

Streaming path exercised end to end: `Browser → Frontend fetch (stream) → /api/copilot/query →
LLM registry → Groq → SSE/stream chunks → browser`. Cancellation was exercised by navigating
away mid-generation in the browser sweep; the request was abandoned without corrupting the
transcript.

## 4. Fallback providers

| Provider | State | Evidence |
|---|---|---|
| Groq | **AVAILABLE** (primary) | live completion + streaming above |
| Hugging Face | **DEGRADED / not usable** | previously reported HTTP 402 (no credits). A 402 is a billing failure, not an inference fallback; it is not presented as healthy. |
| Gemini | **UNAVAILABLE** | previously reported HTTP 404 for the configured model id. The model id was not swapped to a different one to hide the error. |
| Anthropic | configured but not exercised | no key-driven live call was made in this session; the code path is present in `app/llm/anthropic.py`. |

`fallback_enabled` is **false**: paid and local fallbacks are disabled by configuration, and the
status endpoint exposes that fact so a fallback can never hide a primary-provider failure.

Provider errors are classified separately by `app/providers/errors.py` and the LLM layer
(`LLMAuthenticationError`, `LLMRateLimitError`, `LLMProviderError` with a status code) so a
401, a 429, a timeout and a malformed body are not conflated.

## 5. Prompt-injection and grounding posture

- Tool/allowlist separation: the copilot orchestrator (`app/decisions/copilot.py`) resolves
  entities and calls typed services; the model is never allowed to author SQL against the
  production database.
- The existing Phase 8 security suite contains the injection/grounding tests. Two of them fail
  today for reasons unrelated to this session's changes (see `KNOWN_LIMITATIONS.md`, L2) and are
  **not** counted as verified here.
- Provider payloads are treated as data: the copilot's system prompt forbids following
  instructions embedded in provider content, and the tests that assert this exist.

## 6. Reproduction

```powershell
# live provider probe (no secret printed)
python C:\Users\olive\AppData\Local\Temp\opencode\live_groq_probe.py

# status endpoint (signed admin JWT required)
python C:\Users\olive\AppData\Local\Temp\opencode\llm_status_probe.py

# registry regression
pytest tests/unit/test_llm_registry.py
```

## 7. Honest gaps

| Gap | Status |
|---|---|
| "Last successful inference time" is not persisted across restarts | The status shows `last_check` (health probe time) and `streaming_verified`, but the timestamp of the last *successful completion* is not stored in the database. |
| Token-budget headroom for reasoning models | `openai/gpt-oss-120b` spends reasoning tokens from the same budget; a small `max_tokens` yields an empty answer. The copilot's budget is adequate, but this is not guarded by a test. |
| Cancellation is not asserted by an automated test | It was exercised manually in the browser. |
| Per-error-category automated LLM tests (401/429/timeout/empty/malformed) | The unit-level provider tests exist for the *analytics* provider layer (`test_provider_errors.py`); the LLM provider matrix requested by the master prompt is **not** fully covered yet. |
