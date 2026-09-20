# Phase 1 — Slice 4: Player-Match Performance + Canonical Match Context

## 1. Scope
Phase 1 Slice 4 establishes the canonical **Player-Match Performance** intelligence layer on top of the verified Bronze → Silver normalization foundation. This slice implements deterministic Bronze → Silver normalization for:
- **Player Match Participation**: Minutes played, starting vs. substitute status, captaincy, jersey number, and position.
- **Match Lineup Context Integration**: Seamless cross-referencing with `MatchLineup` records to resolve starter status and tactical formation grid positions without overwriting raw performance metrics.
- **Player Match Performance Metrics**: Attacking (goals, assists, shots, shots on target, offsides), passing (total passes, key passes, accuracy percentage), defending (tackles, blocks, interceptions), duels (total, won), dribbles (attempts, success, past), discipline (fouls drawn/committed, yellow/red cards), penalties (won, committed, scored, missed, saved), and goalkeeping (saves, goals conceded, clean sheets).
- **Strict Null vs. Zero Semantics**: Absolute preservation of explicit zero (`0`) vs. missing/unrecorded (`NULL`).
- **Deterministic Identity & Idempotency**: Natural key on `(match_id, club_id, player_id)` ensuring zero duplicate records and stable UUID primary keys across repeated runs.
- **End-to-End Bronze Provenance**: Full lineage tracking back to `DataSnapshot.id` and `IngestionRun.id`.

---

## 2. Data Sources
- **Provider**: API-Football (`v3.football.api-sports.io`).
- **Endpoint**: `fixtures/players?fixture={id}`
- **Payload Structure**:
  - Array grouped by team (`team`: `{id, name, logo, update}`)
  - Team player roster (`players`: `[{player: {id, name, photo}, statistics: [...]}]`)
  - Granular player match stats:
    - `games`: `{minutes, number, position, rating, captain, substitute}`
    - `shots`: `{total, on}`
    - `goals`: `{total, conceded, assists, saves}`
    - `passes`: `{total, key, accuracy}`
    - `tackles`: `{total, blocks, interceptions}`
    - `duels`: `{total, won}`
    - `dribbles`: `{attempts, success, past}`
    - `fouls`: `{drawn, committed}`
    - `cards`: `{yellow, red}`
    - `penalty`: `{won, commited, scored, missed, saved}`
    - `offsides`: integer or null
- **Verified Source Provenance**:
  - Fixture: API-Football Fixture `1492387` (Sao Paulo vs Internacional).
  - DataSnapshot ID: `cce167ca-3f18-4646-9ec0-5f366ed61309`
  - IngestionRun ID: `62506042-c1e3-4ba1-8ca7-7331ea18bc67`
  - Storage Location: `data/bronze/api-football/fixtures/players/14c84cad4fbf32d3257639c8c88a8e04a0856dc0b6f3467a575bb10fda073d34.json` (29,329 bytes, SHA-256 content-addressed).

---

## 3. Bronze → Silver Architecture Flow
```
API-Football fixtures/players
              ↓
IngestionService (Capability check + HTTP fetch + retry)
              ↓
LocalFilesystemSnapshotStore (data/bronze/...json, SHA-256)
              ↓
DataSnapshot & IngestionRun (Validation: ApiFootballEnvelope VALID)
              ↓
NormalizationService (Pure transformer: transform_api_football_player_statistics)
              ↓
Identity Resolution (Match by fixture_id, Club by provider_club_id, Player by provider_player_id)
              ↓
Lineup Cross-Reference (Merge MatchLineup starter/substitute & formation grid context)
              ↓
Silver Database Model: PlayerMatchStats (table player_match_stats)
              ↓
Canonical REST API (GET /api/v1/matches/{id}/player-stats, /players/{id}/matches)
```

---

## 4. PlayerMatchStats Canonical Model
- **Table**: `player_match_stats`
- **Columns**:
  - `id`: UUID (Primary Key)
  - `match_id`: UUID (FK to `matches.id` ON DELETE CASCADE, Indexed, Non-null)
  - `club_id`: UUID (FK to `clubs.id` ON DELETE CASCADE, Indexed, Non-null)
  - `player_id`: UUID (FK to `players.id` ON DELETE CASCADE, Indexed, Non-null)
  - `provider`: VARCHAR(64) (`api-football`, Non-null)
  - `provider_player_id`: VARCHAR(128) (Indexed, Nullable)
  - `provider_fixture_id`: VARCHAR(128) (Indexed, Nullable)
  - `provider_club_id`: VARCHAR(128) (Indexed, Nullable)
  - `is_starter`: BOOLEAN (Nullable)
  - `is_substitute`: BOOLEAN (Nullable)
  - `position`: VARCHAR(16) (`G`, `D`, `M`, `F`, Nullable)
  - `jersey_number`: INTEGER (Nullable)
  - `formation_position`: VARCHAR(16) (Formation grid, e.g., `1:1`, `4:1`, Nullable)
  - `is_captain`: BOOLEAN (Non-null, Default `false`)
  - `minutes`: INTEGER (Minutes played, Nullable)
  - `rating`: FLOAT (Normalized player match rating, Nullable)
  - `goals`: INTEGER (Nullable)
  - `assists`: INTEGER (Nullable)
  - `shots_total`: INTEGER (Nullable)
  - `shots_on_target`: INTEGER (Nullable)
  - `offsides`: INTEGER (Nullable)
  - `passes_total`: INTEGER (Nullable)
  - `passes_key`: INTEGER (Nullable)
  - `pass_accuracy`: FLOAT (Percentage, Nullable)
  - `tackles_total`: INTEGER (Nullable)
  - `blocks`: INTEGER (Nullable)
  - `interceptions`: INTEGER (Nullable)
  - `duels_total`: INTEGER (Nullable)
  - `duels_won`: INTEGER (Nullable)
  - `dribbles_attempts`: INTEGER (Nullable)
  - `dribbles_success`: INTEGER (Nullable)
  - `dribbles_past`: INTEGER (Nullable)
  - `fouls_drawn`: INTEGER (Nullable)
  - `fouls_committed`: INTEGER (Nullable)
  - `yellow_cards`: INTEGER (Nullable)
  - `red_cards`: INTEGER (Nullable)
  - `penalties_won`: INTEGER (Nullable)
  - `penalties_committed`: INTEGER (Nullable)
  - `penalties_scored`: INTEGER (Nullable)
  - `penalties_missed`: INTEGER (Nullable)
  - `penalties_saved`: INTEGER (Nullable)
  - `saves`: INTEGER (Nullable)
  - `goals_conceded`: INTEGER (Nullable)
  - `clean_sheet`: BOOLEAN (Nullable)
  - `raw_stats`: JSONB (Verbatim raw provider statistics object, Default `{}`)
  - `snapshot_id`: UUID (FK to `data_snapshots.id` ON DELETE SET NULL, Indexed, Nullable)
  - `created_at`: TIMESTAMPTZ (Non-null)
  - `updated_at`: TIMESTAMPTZ (Non-null)
- **Constraints & Indexes**:
  - Unique constraint: `uq_player_match_stats` on `(match_id, club_id, player_id)`
  - Index: `ix_player_match_stats_match_id`
  - Index: `ix_player_match_stats_club_id`
  - Index: `ix_player_match_stats_player_id`
  - Index: `ix_player_match_stats_snapshot_id`
  - Composite Index: `ix_player_match_stats_match_club` on `(match_id, club_id)`
  - Composite Index: `ix_player_match_stats_match_player` on `(match_id, player_id)`

---

## 5. Strict Null vs. Zero Semantics
The database schema and pure transformer strictly preserve the difference between an explicit zero and an unrecorded/missing metric:
- If provider returns `shots: {total: 0}`, stored value is `0`.
- If provider returns `penalty: {won: null}`, stored value is `NULL`.
- Missing fields or empty strings parse to `NULL`.
- Ratings:
  - String rating `"7.45"` -> `7.45`
  - Unrated placeholder `"0"` for players with 0 minutes -> `NULL`
  - Malformed strings (`"-"`, `"N/A"`, `""`) -> `NULL`
- Pass accuracy:
  - Percent string `"78%"` or integer string `"19"` -> `78.0` / `19.0`
  - Null or missing -> `NULL`

---

## 6. Identity Resolution
- **Player Identity**:
  - Primary resolution mechanism: `(provider, provider_player_id)`.
  - Looked up in `PlayerIdentity` table.
  - If existing: returns `Player.id`.
  - If new: creates canonical `Player` and `PlayerIdentity` with `resolution_method = "DIRECT_PROVIDER_ID"` and `confidence = 1.0`.
  - No fuzzy or ungrounded name matching.
- **Club Identity**:
  - Resolved via `(provider, provider_club_id)` in `ClubIdentity`.
- **Match Identity**:
  - Resolved via `(provider, provider_fixture_id)` in `Match`.

---

## 7. Lineup & Event Context Integration
- `MatchLineup` records are cross-checked for each `(match_id, club_id, player_id)`.
  - In API-Football's `fixtures/players` endpoint, `games.substitute` is often unreliably reported as `False` across all squad players.
  - The normalization service cross-references the verified `MatchLineup` records created in Slice 3:
    - If `lineup.is_starter == True`, `is_starter = True`, `is_substitute = False`.
    - If `lineup.is_starter == False`, `is_starter = False`, `is_substitute = True`.
    - Grid position from `MatchLineup.formation_position` is populated into `formation_position`.
    - Captain status from `MatchLineup.is_captain` is merged.
  - Explicit performance stats (goals, assists, shots, passes, etc.) are never overwritten.
- `MatchEvent` records remain the canonical source of truth for individual match events (goals, cards, substitutions, VAR). Event data is not duplicated within `PlayerMatchStats`.

---

## 8. Idempotency & Database Migration
- **Migration**: `database/migrations/versions/0006_player_match_stats.py`
  - Successfully applied against PostgreSQL.
  - Seeds `provider_capabilities` with `{"provider": "api-football", "resource": "fixtures/players", "available": True}`.
- **PostgreSQL Idempotency Verification**:
  - Ingested and normalized Bronze snapshot for fixture `1492387`.
  - Re-normalized the exact same snapshot a second time.
  - Result:
    - `player_match_stats` delta: 0
    - `players` delta: 0
    - `clubs` delta: 0
    - Primary key stability: 100% (all UUIDs remained identical).

---

## 9. REST API Endpoints
Following existing project patterns:

### 1. `GET /api/v1/matches/{match_id}/player-stats`
- **Alias**: `GET /api/v1/matches/{match_id}/players`
- Returns array of `PlayerMatchStatsResponse` for the match.
- Ordered by club, starting status (starters first), and minutes played.
- Includes player name, club name, position, formation grid, minutes, rating, attacking, passing, defending, discipline, and goalkeeping stats.

### 2. `GET /api/v1/players/{player_id}/matches`
- Returns match performance history for a specific player.
- Query parameters:
  - `club_id`: Optional UUID filter.
  - `limit`: Pagination limit (default 50, max 100).
  - `offset`: Pagination offset (default 0).

---

## 10. Data Quality Report (Real PostgreSQL Verification)
```
============================================================
DATA QUALITY REPORT — SLICE 4 (Fixture 1492387)
============================================================
Players received:           45
Players normalized:         45
Players skipped:            0
Players failed:             0
Starters:                   23
Substitutes:                22
Players with minutes:       32
Players without minutes:    13
Ratings present:            32
Ratings missing:            13
Explicit zero goals preserved:       44
Explicit zero shots preserved:       32
NULL penalties_won preserved:        45
NULL dribbles_past preserved:        45
Provenance links verified:           45 / 45
============================================================
```

---

## 11. Test Verification
- **Total Tests**: **98 passed, 1 skipped, 0 failures, 0 regressions**.
- **Previous Baseline**: 90 passed, 1 skipped.
- **New Tests Added**:
  - `tests/unit/test_player_match_transformers.py` (4 tests)
  - `tests/integration/test_player_match_normalization.py` (1 comprehensive test)
  - `tests/integration/test_canonical_player_match_api.py` (3 tests)
