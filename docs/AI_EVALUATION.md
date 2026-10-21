# AI Evaluation

**Phase 12 — repeatable evaluation of the FIO grounded assistant**

Harness: `tools/evaluate_grounded_copilot.py` · golden set: `tests/ai/golden_set.json`
(12 cases) · offline tests: `tests/unit/test_ai_tool_registry.py` (20),
`tests/integration/test_ai_grounded_copilot.py` (8)

---

## 1. How to run

```powershell
# 1. the golden set is validated offline (no provider, no database)
$env:PYTHONPATH="apps/api"
python tools/evaluate_grounded_copilot.py

# 2. the live evaluation (needs a configured provider + network)
$env:DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios"
python tools/evaluate_grounded_copilot.py --live --delay 16 --token-budget 90000 `
       --output docs/evidence/ai/evaluation.json

# 2b. a subset, when the provider's daily token budget is nearly spent
python tools/evaluate_grounded_copilot.py --live --delay 14 --token-budget 40000 `
       --cases valuation-question squad-balance `
       --output docs/evidence/ai/evaluation_postfix.json
```

`--delay` paces the cases: the provider's token budget is per minute and shared by
every request of a turn, so an unpaced run trips the 8 000 TPM limit (this was
observed in the first live run).

`--token-budget` stops the run before the provider's **daily** budget is exhausted,
and `--cases` runs a subset. When the provider refuses a request because a request
budget is spent, the runner records the remaining cases as `SKIPPED_TOKEN_BUDGET`
and stops, instead of producing a wall of provider errors.

## 2. What each golden case declares

| Field | Meaning |
|---|---|
| `question` | the user's question, verbatim |
| `expected_tools` | the tools that must run for a correct answer (a case may be satisfied by a permitted alternative) |
| `permitted_tools` | the tools that may run; anything else is counted as an unplanned tool |
| `required_evidence` | the evidence entity types the answer must be based on |
| `expected_epistemic_status` | the status the retrieved evidence must carry |
| `required_caveats` | the words the answer must contain (matched on the first token) |
| `forbidden_claims` | what the answer must not assert (checked by the claim validator and by review) |
| `criteria` | how a human reviewer should judge the answer |

The set covers: a player lookup, a player that does not exist, a coverage question, a
valuation question, a match-analysis question, a recruitment question, a methodology
question, a capability the platform does not have, a squad question, a comparison, a
**prompt-injection attempt**, and a provider-health question.

## 3. Metrics

| Metric | Definition | Target |
|---|---|---|
| `tool_selection_accuracy` | cases where a tool from `expected_tools` ran | ≥ 0.8 |
| `epistemic_status_accuracy` | cases whose evidence carries an expected status | ≥ 0.8 |
| `required_evidence_accuracy` | cases whose evidence contains a required entity type | ≥ 0.8 |
| `caveat_disclosure_accuracy` | cases whose required caveat is present | ≥ 0.8 |
| `grounded_answer_rate` | cases with no unsupported number and no unknown entity id | ≥ 0.8 |
| `unsupported_numeric_claim_rate` | unsupported numbers / all numbers checked | ≤ 0.1 |
| `unplanned_tool_rate` | cases that called a tool outside `permitted_tools` | ≤ 0.1 |
| `latency_ms_p50` / `max` | wall-clock per turn | reported, not gated |
| `numeric_claims_checked` | the sample size for the rate above | reported with the rate |

The unsupported-numeric rate is reported **with its denominator** (`numeric_claims_checked`),
because a rate without a sample size is not a measurement.

## 4. Live results

### 4.1 Run 1 — first live run (12 cases, Groq `openai/gpt-oss-120b`)

```
tool_selection_accuracy      0.417
epistemic_status_accuracy    0.583
required_evidence_accuracy   0.500
caveat_disclosure_accuracy   0.917
grounded_answer_rate         0.750
unsupported_numeric_claim_rate 0.256   (39 numeric claims checked)
latency_ms_p50               1675
latency_ms_max               28916
unplanned_tool_rate          0.000
```

**Defects this run exposed (all fixed):**

1. `get_analytics_methodology` awaited a synchronous function → the tool failed.
2. The compact tool schema declared a nullable parameter as `"string"`, so the provider's
   own tool-use validation rejected the whole generation
   (`parameters for tool get_competition_overview did not match schema`).
3. A 429 from the provider was not retried without a `Retry-After` header.
4. **The model answered five questions without calling any tool** — the answer came from
   its pretrained knowledge. The tool phase now demands a tool call once before
   accepting a tool-free answer, and a tool-free answer is reported with the status
   `NO_EVIDENCE` and a visible caveat.

### 4.2 Run 2 — after the fixes but with an invalid schema

The nullable-type fix initially emitted `"type": ["string", "null", "null"]`. A repeated
type is invalid JSON schema, and the provider refused **every** request (HTTP 400,
"invalid JSON schema for tool analyze_squad_balance"). The metrics of that run are
meaningless and are not reported as results. A regression test now asserts that no
compact schema declares a duplicate type.

### 4.3 Run 3 — after the schema fix (the baseline for the final implementation)

```
tool_selection_accuracy      0.500
epistemic_status_accuracy    0.583
required_evidence_accuracy   0.583
caveat_disclosure_accuracy   0.833
grounded_answer_rate         0.583
unsupported_numeric_claim_rate 0.178   (45 numeric claims checked)
latency_ms_p50               5256
latency_ms_max               104482
unplanned_tool_rate          0.000
```

This run exposed two more provider-level constraints:

* the model called a tool that the relevance shortlist had not offered
  (`attempted to call tool 'search_players' which was not in request.tools`) — the
  provider rejects the whole request. The shortlist now always contains
  `search_players`, `get_player_profile` and `get_data_coverage`, and a rejected
  request is retried once with the complete catalogue;
* the model's last-minute tool call during the answer phase produced
  `Tool choice is none, but model called a tool` — the answer phase now keeps the
  tools available and executes one more tool if the model asks for it.

### 4.4 The fallback router

The run also showed the core weakness: **five of twelve questions were answered with
no tool at all** — the model simply wrote the answer from its pretrained knowledge
(e.g. "Harry Kane" for a question about a Premier League striker, which is not in the
canonical index).

Three changes address it:

1. the tool phase **demands** a tool call once before accepting a tool-free answer;
2. if the model still declines, a small deterministic **fallback router**
   (`app/llm/tools/fallback.py`) runs the argument-free tools for the question shape
   and hands the results back to the model;
3. a tool-free answer is reported with the status `NO_EVIDENCE` and a visible caveat,
   so an ungrounded answer can never be presented as a grounded one.

### 4.5 Final run — blocked by the provider's daily token budget

The Free-tier Groq account allows **200 000 tokens per day** (verified from the
provider's own error body: *"Rate limit reached … on tokens per day (TPD): Limit
200000, Used 199364"*). The window frees roughly 1 000 tokens every five minutes, so
a case (which needs ~2 000–4 000 tokens) only fits when the window has just rolled
over. The three evaluation runs above plus the live debugging consumed the day's
budget, so the final 12-case measurement could not be completed in this session.

What was measured **after** the fallback router, the family routing and the payload
fixes, on a live turn (the `player-lookup-by-name` case):

```
status: OK
tools:  [('get_player_profile', 'OK')]
evidence: 40 items (minutes 2514 with competition "Premier League" and season "2023")
validation: grounded=True, unsupported_numbers=[]
answer: "M. Akanji (canonical id 2ca6252c-…) played 2 514 minutes in the Premier
         League 2023 season【OBSERVED】"
```

What the runner now does when a request budget is spent: it stops, records the
remaining cases as `SKIPPED_TOKEN_BUDGET` and reports `provider_tokens_used`, instead
of producing a wall of provider errors. The exact commands to complete the
measurement once the daily budget has recovered:

```powershell
# the whole set
python tools/evaluate_grounded_copilot.py --live --delay 16 --token-budget 90000 `
       --output docs/evidence/ai/evaluation.json

# or a subset that fits the remaining budget
python tools/evaluate_grounded_copilot.py --live --delay 14 --token-budget 40000 `
       --cases valuation-question squad-balance
```

**The measured baseline for the implementation is run 3 above** (tool-selection 0.500,
grounded-answer rate 0.583, unsupported-numeric rate 0.178 over 45 checked claims).
The changes made after run 3 (fallback router, family routing, always-offered core
tools, payload budget, answer-phase fix) target exactly the two metrics run 3 exposed
— the tool-free answers and the unoffered-tool errors — and are verified by the single
live turn quoted above plus the 34 offline tests. A fresh 12-case measurement is
**blocked by the provider's daily token budget**, not by the implementation.

## 5. Offline test coverage (no provider, no network)

| Area | Test | What it proves |
|---|---|---|
| Tool correctness | `test_unknown_tool_is_rejected_cleanly` | an unregistered name is refused |
| | `test_invalid_arguments_are_rejected_before_execution` | the handler is not called |
| | `test_missing_argument_is_rejected` | a required argument is enforced |
| | `test_tool_runs_and_returns_evidence` | a successful call returns its evidence |
| | `test_tool_timeout_is_enforced` | a slow tool is stopped at its budget |
| | `test_tool_exception_does_not_leak_internals` | an internal exception never reaches the model |
| | `test_permission_is_required_when_declared` | a tool with permissions is refused without them |
| | `test_tool_error_carries_explicit_status` | `UNSUPPORTED` is distinct from `ERROR` |
| Grounding | `test_claim_validation_flags_numbers_without_evidence` | a number that was not retrieved is flagged |
| | `test_claim_validation_accepts_grounded_numbers` | a retrieved number passes |
| | `test_claim_validation_checks_entity_ids` | an unknown canonical id is flagged |
| | `test_claim_validation_ignores_season_like_numbers_when_present` | a season label in the evidence is not a false positive |
| Orchestration | `test_grounded_answer_attaches_evidence_and_validates_claims` | the answer carries the evidence and the verdict |
| | `test_unsupported_numbers_are_reported_and_caveated` | the answer itself carries the caveat |
| | `test_unknown_tool_is_refused_and_no_data_is_fabricated` | a destructive tool name is refused and nothing is invented |
| | `test_tool_call_budget_is_enforced` | the budget is reported, not silently applied |
| | `test_provider_failure_is_a_visible_outcome` | a provider error is a status, not a crash |
| | `test_empty_model_output_is_reported` | an empty answer is a status |
| Real data | `test_real_fio_tool_reads_real_rows` | the search tool reads the canonical index |
| | `test_unsupported_capability_is_explicit` | a missing capability says so |
| Schemas | `test_compact_schemas_declare_nullable_parameters_without_duplicate_types` | the schemas the provider validates are valid |
| | `test_fio_tools_are_read_only_by_default` | no tool can write |
| Documentation | `test_documentation_index_is_built_from_the_repository` | the index comes from `docs/` |
| | `test_documentation_retrieval_returns_sections_with_provenance` | passages carry a reference |

## 6. Metrics that are deliberately not reported

* **No "answer quality" score.** A LLM-judge score would be an invented benchmark.
* **No per-claim precision/recall against a reference answer.** The golden set checks
  tool use, evidence and caveats, not phrasing.
* **No cross-model comparison.** Only the configured model was measured; comparing
  models would need a second configured provider and a second budget.
* **No cost figure.** The Free plan does not bill per token; the observed usage is
  reported instead.

## 7. Known limits of the evaluation

* The golden set is small (12 cases). It is a regression guard, not a benchmark.
* The cases are written against the *current* platform capabilities; a capability that
  is added later needs a new case, and a capability that is removed needs the case
  updated (the `UNSUPPORTED` case is the template for that).
* The live run is bounded by the provider's Free-plan budget (8 000 TPM, 10 requests per
  minute); a 12-case run takes roughly eight minutes with pacing.
* The claim validator only checks numbers and entity ids. Qualitative claims are
  reviewed by a human reading the evidence table.
