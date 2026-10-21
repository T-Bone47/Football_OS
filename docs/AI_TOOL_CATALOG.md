# AI Tool Catalogue

Every tool the FIO assistant can call. The catalogue is generated from the code —
`GET /api/v1/copilot/tools` returns the same structure — so this document cannot drift
silently from the implementation.

Registry: `apps/api/app/llm/tools/fio_tools.py` · execution: `apps/api/app/llm/tools/base.py`
Catalogue size: **31 tools** (30 analytical + `get_field_provenance`).

**How the model is offered them.** The question is classified into a family
(`app/llm/tools/routing.py`: player, team, match, recruitment, financial, squad,
platform) and the model receives a relevance-ranked shortlist of the tools of those
families, plus a core that is always present (`search_players`,
`get_player_profile`, `get_data_coverage`) — the provider rejects a generation that
calls a tool which was not offered. Each schema also carries a one-line usage hint
(`app/llm/tools/hints.py`), e.g. *"Use a canonical id; if you only have a name, call
search_players first"*, which removes the wasted calls the live run exposed.

**Rules that apply to every tool**

* Read-only. No tool writes to the database, calls a provider, or mutates state.
* Every tool is a **wrapper around an existing FIO service or route handler**. No tool
  re-implements analytics: a tool answer and the matching page answer come from the
  same code.
* Arguments are validated (pydantic, `extra="forbid"`) before execution; an unknown
  tool or a malformed argument is an explicit error.
* Permissions are checked against the caller's principal before execution.
* Each tool has a timeout (default 20 s) and a bounded result.
* Every result carries evidence: entity id, entity name, metric, value, unit,
  competition, season, sample size, source, method and epistemic status.
* A missing capability returns `UNSUPPORTED`; a missing entity returns `NOT_FOUND`;
  an ambiguous reference returns `AMBIGUOUS` with the candidates.

---

## A. Player intelligence

### `search_players`
* **Purpose:** search the canonical player index with filters and server-side pagination.
* **Input:** `q`, `position`, `nationality`, `club_id`, `competition_season_id`, `page`, `page_size` (≤ 50 per call).
* **Output:** `{items, total, page, page_size, total_pages, has_next}` — the same contract as `GET /api/v1/players/search`.
* **Service:** `routes_canonical.search_players` · **Source:** canonical players, player_season_stats.
* **Failure modes:** unknown position/nationality → empty result (not an error); `page_size` above the cap → 422-equivalent error.
* **Tests:** `test_ai_tool_registry.py`, `test_ai_grounded_copilot.py::test_real_fio_tool_reads_real_rows`.

### `get_player_profile`
* **Purpose:** one canonical player with identity and stored season statistics.
* **Input:** `player_id` **or** `name`.
* **Output:** the player record + evidence per statistic, each with competition and season names resolved from the canonical tables.
* **Service:** `routes_canonical.get_player` (+ identity resolution).
* **Failure modes:** `NOT_FOUND` (no canonical player), `AMBIGUOUS` (several players share the name — the candidates are listed).
* **Note:** the live provider probe produced the argument `"M. Akangi"` for M. Akanji; resolution against the canonical index is what makes that answerable.

### `get_player_season_statistics`
* **Purpose:** the stored season statistics of one player.
* **Input:** `player_id`, optional `competition_season_id`.
* **Output:** `{player_id, player_name, season_stats[]}`; missing statistics are `null`, never `0`.
* **Failure modes:** `INSUFFICIENT_DATA` when the player has no stored statistics in the scope.

### `compare_players`
* **Purpose:** 2–5 canonical players side by side.
* **Input:** `player_ids` (2–5).
* **Output:** `{players: [...]}` with per-player evidence.
* **Service:** `routes_canonical.get_player` (one call per player).

### `find_similar_players`
* **Purpose:** model-based comparable players.
* **Input:** `player_id`, `limit` (≤ 25), `mode` (composite/contribution/role/tactical/replacement).
* **Output:** results with a similarity score — epistemic status `MODELLED`.
* **Failure modes:** empty result with a message when the reference player has no qualified role profile.

### `analyze_player_role`
* **Purpose:** the stored role archetype, its sample depth and confidence.
* **Output:** the role profile; evidence status `MODELLED` with `sample_size` = the minutes behind it.

### `get_player_career_history`
* **Purpose:** time-bounded club registrations and stored transfers.
* **Output:** memberships (club, competition-season, current flag, season) and transfers.
* **Failure modes:** `INSUFFICIENT_DATA` when neither exists.

## B. Team and competition intelligence

### `search_teams` — clubs by name fragment and country. Returns canonical club ids.
### `get_team_profile` — one canonical club record.
### `get_team_squad` — the squad engine's selection for a formation (epistemic status `MODELLED`; it is an allocation, not an observed lineup).
### `get_competition_overview` — measured player coverage per competition-season, with the status per row. Use this before claiming a league is covered.
### `get_league_standings` — **UNSUPPORTED.** FIO does not persist a normalised league table; the tool says so and points at `get_competition_overview` and `search_matches`.

## C. Match intelligence

### `search_matches` — fixtures by competition, season, club, status and date range (server-side pagination).
### `get_match_details` — the canonical fixture (teams, score, kick-off, competition, season).
### `get_match_statistics` — stored team statistics (possession, shots, passes, xG, cards). `INSUFFICIENT_DATA` when a fixture has none — never zeros.
### `analyze_matchup` — fixture + stored statistics + stored prediction in one call; observed statistics and model output are labelled separately.
### `get_match_prediction` — the stored pre-match prediction with `data_status` (`INSUFFICIENT_DATA`, `OUT_OF_DISTRIBUTION`, …) and the model version.
### `get_match_event_summary` — the stored event stream (goals, cards, substitutions).

## D. Recruitment and scouting

### `find_recruitment_candidates` — the recruitment engine for a position/role/formation/budget; returns the candidates, the hard constraints and the excluded candidates with their reasons.
### `find_replacements` — scored replacement candidates for a departing player.
### `evaluate_tactical_fit` — the stored tactical fit with `fit_status` and confidence.
### `compare_candidate_tradeoffs` — dimension-by-dimension comparison of a shortlist.

## E. Transfer and financial intelligence

### `get_player_valuation` — the comparable-median valuation baseline with its sufficiency status. `INSUFFICIENT_DATA` when the comparable sample is too small — never a zero.
### `analyze_transfer_risk` — the multi-dimensional transfer risk with its data-quality state.

## F. Squad and tactical intelligence

### `analyze_squad_balance` — squad quality, role coverage, depth risk and position gaps for a formation (epistemic status `MODELLED`).
### `get_team_squad` — the selected XI and bench for the same formation.

## G. Platform intelligence

### `get_data_coverage` — canonical counts, per competition-season coverage, profile/statistic completeness, priority-country coverage with its denominator and the ranking snapshot.
### `get_data_freshness` — data-layer status, schema version and the age of the last successful ingestion.
### `get_model_status` — registered model artifacts, release status and blockers.
### `get_provider_health` — the data-source registry: licence, attribution, enablement, terms-review date.
### `get_analytics_methodology` — how a FIO metric or engine is actually computed, retrieved from `docs/**/*.md` with section provenance.
### `get_field_provenance` — which provider supplied each field of a canonical entity, the transformation applied, and the values that conflict between providers.

---

## Coverage of the requested families

| Requested family | Tools | Gap |
|---|---|---|
| Player intelligence | 7 / 7 | — |
| Team and competition | 4 / 7 | `get_league_standings` (no canonical table), `get_team_season_statistics` (covered by `analyze_squad_balance` + `search_players` with a club filter), `compare_teams` (covered by `compare_players` on the club's players) |
| Match intelligence | 6 / 6 | — |
| Recruitment and scouting | 4 / 6 | `find_role_similar_players` → `find_similar_players` with `mode="role"`; `analyze_scouting_shortlist` → `compare_candidate_tradeoffs` |
| Transfer and financial | 3 / 4 | `compare_player_valuations` → two `get_player_valuation` calls; `evaluate_transfer_scenario` is not exposed because the scenario engine is a write-like operation that needs explicit confirmation |
| Squad and tactical | 2 / 5 | `identify_position_gaps` → `analyze_squad_balance`; `evaluate_squad_depth` → `analyze_squad_balance`; `analyze_succession_options` → `find_replacements`; `evaluate_tactical_requirements` → `evaluate_tactical_fit` |
| Platform intelligence | 6 / 6 | — |

Where a requested capability is a composition of existing tools, the composition is used
rather than a new wrapper; where the capability does not exist, the tool says so.

## The deterministic fallback

The model is the primary planner, but a reasoning model sometimes answers a data
question without calling any tool (measured live: 5 of 12 golden cases in the first
evaluation run). An answer produced that way is an ungrounded statement about the
platform's own data.

`apps/api/app/llm/tools/fallback.py` therefore provides a small, inspectable keyword
router that runs **only** when the model chose no tool at all, and only with tools whose
arguments are all optional (it cannot supply a player id):

| Question shape | Fallback tool |
|---|---|
| coverage / how many players / data quality | `get_data_coverage` |
| providers / ingestion / freshness | `get_provider_health`, `get_data_freshness` |
| model status / release / blocker | `get_model_status` |
| methodology / how does X work | `get_analytics_methodology` |
| squad / balance / formation / depth / gaps | `analyze_squad_balance` |
| match / fixture / last game / score | `search_matches` |
| player / valuation / risk / replacement / similar / compare / role | `search_players` |

The fallback never overrides the model: the model's own tool calls run first, and the
fallback only runs when it made none. The results are handed to the model as a user
message ("TOOL RESULTS … use these values, and only these values"), so the answer is
still produced from retrieved records.

## Observability

Each turn returns a tool trace: name, status, latency, evidence count and message.
Failures are categorised (`NOT_FOUND`, `AMBIGUOUS`, `INSUFFICIENT_DATA`,
`UNSUPPORTED`, `ERROR`) so a failure is never indistinguishable from a success.
