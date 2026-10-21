# AI Evidence and Provenance

How a FIO answer is tied back to the records it came from, and what each piece of
evidence means.

Implementation: `apps/api/app/llm/tools/base.py` (evidence model),
`apps/api/app/llm/tools/claims.py` (validation), `apps/api/app/llm/tools/fio_tools.py`
(evidence construction).

---

## 1. The evidence envelope

Every tool result carries a list of evidence items. One item describes one verifiable
fact:

| Field | Meaning | Example |
|---|---|---|
| `entity_type` | what kind of thing the value belongs to | `player_season_stat` |
| `entity_id` | the canonical id (uuid) | `2ca6252c-…` |
| `entity_name` | the display name | `M. Akanji` |
| `metric` | what the value is | `minutes` |
| `value` | the value (or a small object) | `2514` |
| `unit` | the unit | `minutes` |
| `competition` | the competition the value belongs to | `Premier League` |
| `season` | the season the value belongs to | `2023` |
| `sample_size` | the sample behind the value (e.g. minutes behind a rating) | `2514` |
| `source` | which provider/service supplied it | `fio-canonical` |
| `data_period` | the period the data covers | `2023/24` |
| `method` | how it was computed | `canonical player_season_stats row` |
| `model_version` | the model version, for modelled values | `role_feature_set_v1` |
| `confidence` | a legitimate calibration/confidence value | `0.61` (archetype confidence) |
| `epistemic_status` | **how the value must be read** | `OBSERVED` |
| `provenance_ref` | a pointer to the source record | the season-stat row id |

The evidence is returned to the client with the answer, rendered in the copilot's
evidence table, and checked by the validator. It is not persisted separately: the
canonical rows it points at *are* the persistence.

## 2. Epistemic statuses

| Status | Use it for | Do not use it for |
|---|---|---|
| `OBSERVED` | a value stored in the canonical database (season statistics, match events, a fixture score) | anything the model inferred |
| `MODELLED` | similarity, role archetype, tactical fit, valuation, transfer risk, match prediction | stored measurements |
| `COUNTERFACTUAL` | the outcome of a what-if that was actually evaluated | a scenario that was never run |
| `SCENARIO` | a projected or hypothetical outcome (transfer simulation, squad impact) | measured data |
| `ASSUMPTION` | a stated premise the analysis rests on | evidence |
| `ANALYSIS` | reasoning over retrieved evidence (a comparison, a trade-off) | a raw measurement |
| `HYPOTHESIS` | a plausible explanation without sufficient evidence | a conclusion |
| `UNVERIFIED` | a claim that could not be tied to retrieved evidence | anything else |
| `INSUFFICIENT_DATA` | the evidence exists but is too thin (too few comparables, no stored statistics) | a zero value |
| `OUT_OF_DISTRIBUTION` | the model was asked about something outside its training distribution | a low confidence |
| `MODEL_UNCALIBRATED` | the model produced a value it is not calibrated for | a normal estimate |

Two rules follow from the table and are enforced mechanically:

* a missing statistic is `null` with the metric simply absent from the evidence — it is
  never written as `0`;
* a modelled value is never labelled `OBSERVED`, so a valuation cannot be read as a
  transfer fee.

## 3. Claim validation

`validate_answer(answer, evidence, tool_payloads)` produces a
`ClaimValidationReport`:

| Field | Meaning |
|---|---|
| `supported_numbers` | numbers in the answer that exist in the evidence or the tool payloads |
| `unsupported_numbers` | numbers in the answer that exist nowhere in the retrieved data |
| `unknown_entity_ids` | canonical ids mentioned in the answer that are not in the evidence |
| `known_entity_ids` | canonical ids mentioned in the answer that are in the evidence |
| `evidence_count` / `tool_count` | how much was actually retrieved |
| `grounded` | `true` when there is no unsupported number and no unknown entity id |

The comparison is numeric, not textual: `2 514` (a space-separated thousands form in
prose) matches the stored `2514`, but only when the merged value exists in the
evidence. A season label that the model inferred (for example writing "2023/24" when the
evidence only carries "2023") is correctly reported as unsupported.

**What the report does:** it does not rewrite the answer. It (a) is returned with the
answer, (b) is rendered in the UI, and (c) causes the assistant to append an explicit
caveat to the answer text when unsupported values are present:

> **Grounding check**: 2 value(s) in this answer were not found in the retrieved evidence
> (2023, 24). Treat them as unverified until a tool confirms them.

**What it cannot check:** non-numeric claims ("he is quick over 30 metres"), causal
claims, and statements that are true but irrelevant. Those remain the reviewer's job —
which is why the evidence table is always shown next to the answer.

## 4. Where the evidence comes from

| Tool family | Evidence source | Epistemic status |
|---|---|---|
| Player search / profile / statistics | canonical `players` + `player_season_stats` rows | `OBSERVED` |
| Career history | `player_club_memberships` + `transfers` | `OBSERVED` |
| Similar players / role archetype | `player_role_profiles` | `MODELLED` |
| Tactical fit | `player_tactical_fits` | `MODELLED` |
| Valuation | `market.valuation` comparable median | `MODELLED` (or `INSUFFICIENT_DATA`) |
| Transfer risk | `market.risk` | `MODELLED` |
| Recruitment / replacement / comparison | decision engines | `MODELLED` |
| Squad | squad engine | `MODELLED` |
| Match details / statistics / events | canonical `matches`, `match_statistics`, `match_events` | `OBSERVED` |
| Match prediction | prediction service | `MODELLED` (or `INSUFFICIENT_DATA` / `OUT_OF_DISTRIBUTION`) |
| Coverage / freshness / providers / models | coverage + observability services | `OBSERVED` |
| Methodology | `docs/**/*.md` | `OBSERVED` (a document is a fact about the platform) |

## 5. Record-level provenance (already in the platform)

The evidence envelope sits on top of the platform's existing provenance chain, which the
assistant does not duplicate:

```
canonical row  ←  player_season_stats.snapshot_id  →  data_snapshots
                                                      (sha256, storage_location,
                                                       retrieved_at, validation_status)
                                      ←  ingestion_run  →  data_source (provider,
                                                              licence, attribution,
                                                              terms_reviewed_at)
```

The canonical `providers` are registered in `data_sources` with their licence,
attribution, redistribution permission and enablement state, and the tool
`get_provider_health` exposes that register to the assistant.

## 6. Field-level provenance (now populated)

`field_provenance` and `source_conflicts` answer "which provider supplied this field,
and what did the other providers say?".

* The normalisers write one row per (entity, field, provider) with the source value,
  the transformation, the confidence and the retrieval time.
* When a second provider supplies a **different** value for a field the canonical row
  already has, the canonical value is kept (the first authoritative source wins for
  that field) and the disagreement is written to `source_conflicts` with both
  candidates and the status `OPEN`. Nothing is silently overwritten.
* `GET /api/v1/coverage/provenance` returns the summary;
  `GET /api/v1/coverage/provenance?entity_type=player&entity_id=<uuid>` returns the
  fields of one entity; the assistant can read both through the
  `get_field_provenance` tool.

**Live example (measured).** For *Aaron Ramsey* the platform holds a conflict on
`primary_position`: API-Football says `ATT`, StatsBomb says `MID`. Both are
defensible for a player who filled both roles — the platform now keeps the canonical
value, records the disagreement as `OPEN` and lets a reviewer resolve it, instead of
silently preferring one provider.

**Backfill.** Rows ingested before the recorder existed have no field provenance. They
are filled from the **stored Bronze snapshots** — no provider request, no quota:

```powershell
python tools/backfill_field_provenance.py --provider api-football --resource players
```

Measured on the live database: 90 snapshots, 1 628 player records re-normalised,
31 265 provenance rows (9 893 player fields + 21 372 season-statistic metrics),
0 errors.

## 7. Documentation provenance

Retrieved documentation carries its file, section title and line range
(`docs/VALUATION_BASELINE_METHODOLOGY.md#L42:2. Baseline Mathematical Formulation`).
The assistant cites the section reference, and the retrieval is injected as *data* with
an explicit instruction that it cannot change policy or grant permissions.

## 8. Audit and reproducibility

* Every turn is reproducible from its evidence: the same tool call against the same
  database returns the same values.
* The tool trace (name, status, latency, evidence count) is returned with the answer
  and shown in the UI.
* Provider requests carry the platform's correlation id middleware
  (`CorrelationIdMiddleware`), so a turn can be correlated with the API logs.
* No secret, credential or configuration value is ever part of an evidence item, a tool
  payload or a tool error message.
