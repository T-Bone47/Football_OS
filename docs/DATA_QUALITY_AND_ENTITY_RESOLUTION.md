# Data Quality and Entity Resolution

**Phase 5/6 — conservative resolution, source authority, provenance**

The rules in this document are enforced in code, not just described:
`apps/api/app/identity/names.py`, `apps/api/app/identity/resolution.py`,
`apps/api/app/normalization/service.py`, `apps/api/app/ingestion/sources.py`.

---

## 1. The problem this solves

Before the expansion, one provider (`api-football`) and one identity mechanism
existed: a provider id, or — in the transfer path — **exact name string equality**
(`normalization/service.py`, `NAME_EXACT_MATCH`). Name equality is not an identity
proof: two different players can share a name, and a player's name changes. The
expansion therefore adds a mapping table per entity type, an alias store, a
conservative matcher and a review queue.

## 2. Identity model

| Layer | Table | Rule |
|---|---|---|
| Canonical entity | `players`, `clubs`, `competitions` | Provider-neutral. One row per real-world entity. |
| Provider mapping | `player_identities`, `club_identities`, `competition_identities` | `(provider, provider_<entity>_id)` is unique. A provider id **never** equals a canonical id, and never equals another provider's id. |
| Name history | `player_aliases` | Every observed spelling, per provider, with confidence and first/last seen. |
| Time-aware club history | `player_club_memberships` | One row per (player, club, competition-season) registration. A later club never overwrites an earlier one. `players.club_id` stays a denormalised "current club" pointer. |
| Ambiguity | `identity_review_queue` | Candidates that are plausible but not provable. Nothing is merged from this table automatically. |

**Resolution ladder** (`IdentityResolver.resolve`):

1. `DIRECT_PROVIDER_ID` — the provider id is already mapped (confidence 1.0).
2. `VERIFIED_ALIAS` — the record matches a previously verified alias.
3. `STRONG_EVIDENCE` — same normalised name **and** a non-contradicting date of
   birth / nationality, or a shared club, and no competing candidate within 0.05.
4. `AMBIGUOUS` — a plausible candidate that is not provable → **review queue**, no merge.
5. `NO_MATCH` / `NEW` — no candidate; a new canonical player is created.

### Hard rules (enforced in `score_candidates`)

* A **name match alone never auto-merges**. The score is capped below the
  auto-merge threshold when there is no supporting evidence (no DOB, no
  nationality, no shared club).
* A **contradicting** date of birth or nationality **never auto-merges**.
* The auto-merge threshold is 0.92 and the runner-up must be at least 0.05 behind.
* Two candidates with equal scores are ambiguous, not merged.

These rules are exercised by `tests/unit/test_database_expansion.py` and
`tests/integration/test_expansion_pipeline.py`.

## 3. Name normalisation

`name_key` is the comparison key: accent-folded, lower-cased, punctuation-free,
name particles dropped (`de`, `van`, `da`, …) and tokens sorted. Sorting makes
"Akanji, Manuel" and "Manuel Akanji" comparable; folding keeps "Ángel Di María"
comparable to "Angel Di Maria" **without** rewriting the stored name.

`names_are_close` additionally accepts an abbreviation that expands to the same
token ("M. Akanji" ≈ "Manuel Akanji") — but "M. Akanji" vs "M. Aké" is *not* close.

**The original spelling is never destroyed.** `players.name` and every
`player_aliases.alias` keep the provider's own Unicode.

## 4. Source authority and conflicts

There is no single global "provider priority". Authority is **field-specific**:

| Field | Primary source | Fallback |
|---|---|---|
| Provider player id, season statistics | the provider that supplied the record | none (never derived) |
| Match events | the provider that published the events | — |
| Profile fields (DOB, height, weight, photo) | a provider that reports the field | left null |
| Club / competition identity | the provider's own identity mapping | — |

When two providers disagree the canonical row keeps the value it has, the
disagreement is written to `source_conflicts` with every candidate, and the row's
`field_provenance` records which provider supplied which value with the
transformation applied. Nothing is silently overwritten.

`field_provenance` records, per (entity, field, provider): the source value, the
transformation, a source hash, a confidence and the retrieval time. Together with
the content-addressed Bronze snapshot (`data_snapshots.sha256` →
`data/bronze/<provider>/<resource>/<sha256>.json`) this answers, for any canonical
value: *which provider, which provider id, when, which competition and season,
what the original value was, what transformation was applied, and which source
record supports it.*

## 5. Known data-quality checks

| Check | Where | Behaviour |
|---|---|---|
| Duplicate provider ids | `uq_player_identity_provider_id` + `GET /api/v1/coverage/data-quality` | impossible at the DB level; the endpoint still counts groups as a regression guard |
| Players without a provider identity | coverage endpoint | reported (baseline: 0) |
| Unknown statistics | `player_season_stats` nullable metrics + `raw_stats` | unknown stays `null`; a measured zero stays `0` |
| Conflicting DOB / nationality | identity resolver | blocks the merge, queues for review |
| Overlapping impossible memberships | `player_club_memberships` | one row per (player, club, competition-season); the current flag marks the newest observed season |
| Inconsistent positions | `players.primary_position` / `secondary_position` | the first observed position is kept; a second distinct position is stored as the secondary position, never overwriting the primary |
| Profile completeness | `players.data_completeness` | share of eight tracked fields that are known; recomputed on every upsert |
| Source exclusion | `data_sources.enabled` | a disabled source is never ingested from |

## 6. The four "unknown" rules that this phase enforces

1. **A statistic the provider did not report is `null`, never `0`.**
   Enforced in the transformer, in the schema (nullable columns) and in the
   migration backfill.
2. **A financial value that was never estimated is `null`, never `0` and never a
   cohort average.** The recruitment and replacement engines now read the canonical
   `valuation_predictions` row and report `affordability_status = UNAVAILABLE`
   otherwise.
3. **A missing sample is not a zero sample.** The engines no longer substitute
   900 minutes / 10 appearances; the candidate is excluded by the sample gate and
   the assessment says `evidence_status = INSUFFICIENT_DATA`.
4. **A provider being reachable is not completeness.** Coverage endpoints report a
   status (`PARTIAL`, `IN_PROGRESS`, `COMPLETE_FOR_DECLARED_SCOPE`, `BLOCKED`,
   `UNKNOWN_SCOPE`) and only report a percentage when the denominator is defined.

## 7. Review queue workflow

1. The resolver writes a row to `identity_review_queue` with the score and the
   evidence (`name_match`, `dob_match`, `nationality_match`, `shared_clubs`).
2. A reviewer inspects the candidate and decides.
3. An approved row is applied by an **explicit merge operation** that moves the
   provider mapping onto the canonical player and records the decision. The merge
   is reversible: the provider mapping and the aliases are retained, and the
   canonical id that was merged away is recorded.

*Implementation status: the queue, the scoring and the audit fields are implemented
and tested; the interactive merge tool (step 3) is not yet exposed as an
administrative command and is listed as an open item in the implementation
document.*
