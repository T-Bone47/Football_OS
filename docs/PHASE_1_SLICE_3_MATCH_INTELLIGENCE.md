# Phase 1 — Slice 3: Match Events, Lineups & Match Statistics Normalization

## 1. Scope
Phase 1 Slice 3 elevates the canonical `Match` entity from a score/result container into a granular match intelligence foundation. This slice implements deterministic Bronze → Silver normalization for:
- **Match Events**: In-game occurrences including goals, penalties, yellow/red cards, substitutions, and VAR decisions with precise minute, extra time, player, assist, and detail attribution.
- **Match Lineups**: Team starting XI and substitute rosters, positions, jersey numbers, formation grid layouts, formation schemes, captain identification, and coach attribution.
- **Match Statistics**: Team-level operational performance metrics (possession percentage, total shots, shots on/off target, blocked shots, passes, accurate passes, pass accuracy, fouls, corners, offsides, cards, goalkeeper saves, free kicks, xG) while maintaining strict semantic separation between explicit numeric zero (`0`) and unavailable/missing data (`NULL`).

---

## 2. Data Sources
- **Provider**: API-Football (`v3.football.api-sports.io`).
- **Endpoints & Payloads**:
  - `fixtures/events`: Event timeline array with `time` (`elapsed`, `extra`), `team` (`id`, `name`), `player` (`id`, `name`), `assist` (`id`, `name`), `type` (`Goal`, `Card`, `subst`, `Var`), `detail` (`Penalty`, `Yellow Card`, `Substitution 1`, etc.), and `comments`.
  - `fixtures/lineups`: Team lineup array with `team` (`id`, `name`), `formation` (e.g., `3-4-2-1`), `coach` (`id`, `name`), `startXI` player items (`id`, `name`, `number`, `pos`, `grid`), and `substitutes` player items.
  - `fixtures/statistics`: Team statistics array with `team` (`id`, `name`), and `statistics` name/value list (`Ball Possession`, `Total Shots`, `Shots on Goal`, `Passes accurate`, `Fouls`, `Corner Kicks`, `Red Cards`, `Yellow Cards`, `Goalkeeper Saves`, `expected_goals`).
- **Real Source Provenance**:
  - Events Snapshot: `a3e8810b-437d-4b06-ae3c-b8457b42ee80` (SHA-256: `c9282a45814b457e...`)
  - Lineups Snapshot: `e005adfb-76fc-4fd6-b9a6-834aa724ac8f` (SHA-256: `9dd99be4ae12f534...`)
  - Statistics Snapshot: `214828f3-fe64-42e6-ac5b-f4f9ca605ada` (SHA-256: `f5223e99c100449f...`)
  - Source Fixture: API-Football Fixture ID `1492387` (Sao Paulo vs Internacional).

---

## 3. Bronze → Silver Architecture Flow
The pipeline follows strict content-addressed immutable storage and validation before normalization:
```
API-Football Endpoint
         ↓
IngestionService (HTTP + Retry + Backoff)
         ↓
LocalFilesystemSnapshotStore (SHA-256 Content-Addressed JSON in data/bronze/)
         ↓
DataSnapshot & IngestionRun (Validation: ApiFootballEnvelope VALID)
         ↓
NormalizationService (Pure Transformers: transform_api_football_*)
         ↓
Identity Resolution (Match, Club, and Player via DIRECT_PROVIDER_ID)
         ↓
Silver Database Models (MatchEvent, MatchLineup, MatchStatistics)
         ↓
Canonical REST API (GET /api/v1/matches/{id}/events, /lineups, /statistics)
```

No provider payload ever bypasses the Bronze layer or directly surfaces in the frontend.

---

## 4. MatchEvent Canonical Model
- **Table**: `match_events`
- **Columns**:
  - `id`: UUID (Primary Key)
  - `match_id`: UUID (FK to `matches.id` ON DELETE CASCADE, Indexed)
  - `club_id`: UUID (FK to `clubs.id` ON DELETE CASCADE, Indexed)
  - `player_id`: UUID (FK to `players.id` ON DELETE SET NULL, Indexed, Nullable)
  - `assist_player_id`: UUID (FK to `players.id` ON DELETE SET NULL, Indexed, Nullable)
  - `event_type`: VARCHAR(32) (`GOAL`, `CARD`, `SUBSTITUTION`, `VAR`, `OTHER`)
  - `event_detail`: VARCHAR(64) (`Normal Goal`, `Penalty`, `Yellow Card`, `Red Card`, `Substitution 1`, etc.)
  - `minute`: INTEGER (Elapsed match minute, Indexed)
  - `extra_minute`: INTEGER (Stoppage/extra minute, Nullable)
  - `comments`: VARCHAR(255) (Contextual provider remark, e.g., `Foul`, `Dissent`)
  - `event_key`: VARCHAR(255) (Deterministic natural key for idempotency)
  - `provider_event_id`: VARCHAR(128) (Optional provider event identifier, Indexed)
  - `snapshot_id`: UUID (FK to `data_snapshots.id` ON DELETE SET NULL, Indexed)
  - `created_at`: TIMESTAMPTZ
  - `updated_at`: TIMESTAMPTZ
- **Constraints & Indexes**:
  - Unique constraint: `uq_match_event_match_key` on `(match_id, event_key)`
  - Composite index: `ix_match_events_match_minute` on `(match_id, minute)`

---

## 5. MatchLineup Canonical Model
- **Table**: `match_lineups`
- **Columns**:
  - `id`: UUID (Primary Key)
  - `match_id`: UUID (FK to `matches.id` ON DELETE CASCADE, Indexed)
  - `club_id`: UUID (FK to `clubs.id` ON DELETE CASCADE, Indexed)
  - `player_id`: UUID (FK to `players.id` ON DELETE CASCADE, Indexed)
  - `is_starter`: BOOLEAN (True for starting XI, False for substitutes)
  - `jersey_number`: INTEGER (Shirt number, Nullable)
  - `position`: VARCHAR(16) (`G`, `D`, `M`, `F`, Nullable)
  - `formation_position`: VARCHAR(16) (Tactical formation grid coordinate, e.g., `1:1`, `2:4`)
  - `formation`: VARCHAR(32) (Team formation string, e.g., `3-4-2-1`)
  - `is_captain`: BOOLEAN (Default False)
  - `coach_name`: VARCHAR(128) (Head coach at match kickoff)
  - `snapshot_id`: UUID (FK to `data_snapshots.id` ON DELETE SET NULL, Indexed)
  - `created_at`: TIMESTAMPTZ
  - `updated_at`: TIMESTAMPTZ
- **Constraints & Indexes**:
  - Unique constraint: `uq_match_lineup_player` on `(match_id, club_id, player_id)`

---

## 6. MatchStatistics Canonical Model
- **Table**: `match_statistics`
- **Columns**:
  - `id`: UUID (Primary Key)
  - `match_id`: UUID (FK to `matches.id` ON DELETE CASCADE, Indexed)
  - `club_id`: UUID (FK to `clubs.id` ON DELETE CASCADE, Indexed)
  - `possession_pct`: FLOAT (Possession percentage, e.g., `44.0`)
  - `shots_total`: INTEGER
  - `shots_on_target`: INTEGER
  - `shots_off_target`: INTEGER
  - `blocked_shots`: INTEGER
  - `shots_inside_box`: INTEGER
  - `shots_outside_box`: INTEGER
  - `fouls`: INTEGER
  - `corners`: INTEGER
  - `offsides`: INTEGER
  - `yellow_cards`: INTEGER
  - `red_cards`: INTEGER
  - `saves`: INTEGER
  - `passes_total`: INTEGER
  - `passes_accurate`: INTEGER
  - `pass_accuracy_pct`: FLOAT
  - `expected_goals`: FLOAT (xG when provided by provider, Nullable)
  - `free_kicks`: INTEGER
  - `raw_stats`: JSONB (Complete verbatim provider statistics dictionary)
  - `snapshot_id`: UUID (FK to `data_snapshots.id` ON DELETE SET NULL, Indexed)
  - `created_at`: TIMESTAMPTZ
  - `updated_at`: TIMESTAMPTZ
- **Constraints & Indexes**:
  - Unique constraint: `uq_match_statistics_match_club` on `(match_id, club_id)`

---

## 7. Player Identity Handling
When normalizing events or lineups:
1. Provider player ID is extracted (e.g., `47368` for Jonathan Calleri).
2. The service queries `player_identities` for `(provider, provider_player_id)`.
3. If the identity exists, the canonical `Player.id` is returned.
4. If absent, a canonical `Player` is created with available metadata (`name`, `primary_position`), and a `PlayerIdentity` is linked with `resolution_method="DIRECT_PROVIDER_ID"` and `confidence=1.0`.
5. Assist players in events (e.g., substitution partner or goal assister) are resolved using the exact same deterministic resolution protocol.

---

## 8. Provider Identity Handling
- All external provider IDs (`provider_fixture_id`, `provider_club_id`, `provider_player_id`) remain explicitly recorded.
- Club resolution uses `ClubIdentity` with `DIRECT_PROVIDER_ID`.
- Matches are resolved using `(provider, provider_fixture_id)`.
- No raw provider schema artifacts bleed into canonical queries or REST API models.

---

## 9. Provenance
Every entity in the match intelligence graph retains explicit reference to the exact `DataSnapshot` from which it was derived:
- `MatchEvent.snapshot_id` &rarr; `DataSnapshot.id`
- `MatchLineup.snapshot_id` &rarr; `DataSnapshot.id`
- `MatchStatistics.snapshot_id` &rarr; `DataSnapshot.id`

When distinct snapshots provide events, lineups, and statistics for the same match, each table records its exact source snapshot UUID. Provenance is never copied from `Match.snapshot_id`.

---

## 10. Idempotency Proof
API-Football events do not provide a global unique event identifier. To ensure strict idempotency:
- A deterministic `event_key` is calculated from:
  `f"{elapsed}_{extra or 0}_{event_type}_{detail}_{club_id}_{player_id}_{assist_id}"`
- `MatchEvent` uniqueness is enforced by `uq_match_event_match_key`.
- `MatchLineup` uniqueness is enforced by `(match_id, club_id, player_id)`.
- `MatchStatistics` uniqueness is enforced by `(match_id, club_id)`.

### Live Verification on PostgreSQL `fios`:
Repeated normalization of the same Bronze snapshots produced:
| Table | Before Repeat | After Repeat | Difference | Duplicates |
|---|---|---|---|---|
| `matches` | 1,154 | 1,154 | 0 | 0 |
| `match_teams` | 2,308 | 2,308 | 0 | 0 |
| `match_events` | 15 | 15 | 0 | 0 |
| `match_lineups` | 44 | 44 | 0 | 0 |
| `match_statistics` | 2 | 2 | 0 | 0 |
| `players` | 64 | 64 | 0 | 0 |

Primary key arrays (`[id for id in ...]`): **100% Identical before and after**.

---

## 11. Data-Quality Rules
1. **Event Elapsed Time**: Events without an elapsed minute or team ID are rejected as malformed.
2. **Event Type Normalization**: Mapped to canonical enum representations (`GOAL`, `CARD`, `SUBSTITUTION`, `VAR`, `OTHER`).
3. **Lineup Starter Identification**: Explicit boolean `is_starter` separates Starting XI from bench substitutes.
4. **Player Completeness**: Lineup items without player ID or name are skipped.
5. **Score Non-Fabrication**: Missing match values remain `NULL`.

---

## 12. Missing-Value Semantics: Explicit 0 vs NULL
The normalization transformers strictly preserve the semantic difference between explicit zero and missing data:
- `0`: The provider explicitly reported zero (e.g., `Red Cards: 0`, `Goalkeeper Saves: 0`).
- `NULL`: The provider did not supply this metric for the competition/fixture (e.g., `expected_goals: NULL`, `fouls: NULL` for historical fixtures).

The system never replaces missing metrics with 0.0 or 0.

---

## 13. REST API
Canonical endpoints added under `/api/v1`:

### 1. `GET /api/v1/matches/{match_id}/events`
- Chronologically ordered match timeline (`minute asc`, `extra_minute asc nulls first`).
- Includes player name, assist player name, club name, event type, and detail.

### 2. `GET /api/v1/matches/{match_id}/lineups`
- Returns full match roster (Starters and Substitutes).
- Includes club name, jersey number, position, grid position, formation, captain status, and coach.

### 3. `GET /api/v1/matches/{match_id}/statistics`
- Returns team-level comparative match statistics for both competing clubs.
- Preserves explicit 0 vs null.

### Error & Edge Case Handling:
- Non-existent match UUID &rarr; `404 Not Found` (`{"detail": "Match not found"}`).
- Valid match UUID with no intelligence data ingested &rarr; `200 OK` with `[]`.

---

## 14. PostgreSQL Verification
- Migration: `0005_match_intelligence_models.py` applied cleanly via Alembic.
- Foreign keys: Cascade deletion from matches and clubs; set-null deletion on players and snapshots.
- Seeded capabilities: `fixtures/events`, `fixtures/lineups`, `fixtures/statistics` added to `provider_capabilities` table for `api-football`.
- Verified live against PostgreSQL 16 `fios` database:
  - 1,154 Matches
  - 2,308 MatchTeams
  - 15 MatchEvents
  - 44 MatchLineups
  - 2 MatchStatistics
  - 64 Players

---

## 15. Tests
- **Unit Tests**: `tests/unit/test_match_intelligence_transformers.py` (4 tests)
- **Integration Tests**:
  - `tests/integration/test_match_intelligence_normalization.py` (1 test: full ingestion, normalization, provenance, and idempotency)
  - `tests/integration/test_canonical_match_intelligence_api.py` (5 tests: events, lineups, statistics, 404 handling, empty list handling)
- **Full Suite**: 90 passed, 1 skipped (opt-in S3 moto), 0 failures.

---

## 16. Known Limitations
- Coach entities are stored as strings on lineups rather than full canonical `Coach` models with independent identities (deferred to future slice).
- Formation grid coordinates (e.g., `1:1`) are preserved as provider strings; pitch visualization coordinate translation will be handled in the visualization layer.

---

## 17. Future Intelligence Use Cases
With MatchEvents, MatchLineups, and MatchStatistics canonically normalized:
1. **Form & Momentum Analysis**: Rolling club statistics, momentum curves, shot quality trends.
2. **Player Performance & Minutes**: Exact minutes played computed from starter status and substitution events.
3. **Tactical Intelligence**: Formation matchups (e.g., 3-4-2-1 vs 4-3-3), substitution impact on scoreline.
4. **Expected Threat & Goal Analytics**: Baseline for xG and xThreat calculation engines.
