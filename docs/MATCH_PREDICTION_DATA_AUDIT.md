# Match Prediction & Calibration Data Audit (Phase 6.1)

## Executive Summary
This document provides an exhaustive, grounded audit of all match-level, team-level, and player-level data available within Football Intelligence OS for pre-match outcome prediction and probability calibration. In strict adherence to **Principle 6 (No Fabrication)**, this audit documents actual available entities, missing variables, temporal scope, and operational limitations without speculation or synthetic inflation.

---

## 1. Available Data Sources

### A. Bronze Raw Ingestion (`data/bronze/api-football/`)
1. **Fixtures Snapshot (`fixtures/`)**:
   - Total fixtures in raw Bronze storage: **2,308 fixtures** (across 2 JSON snapshots, e.g. `500ba51b...json` and `628b6872...json`).
   - Covered date: `2026-09-20`.
   - Distinct competitions/leagues: **325 leagues** (e.g. Premier League, Serie A, MLS, Liga MX, J3 League, USL Championship, etc.).
   - Distinct clubs: **2,302 unique clubs**.
   - Completed match results (`FT` / `AET` / `PEN`): **78 matches** with verified full-time, half-time, extra-time, and penalty scores.
   - Fixture status vocabulary: `NS` (Not Started), `FT` (Finished), `1H` (First Half), `HT` (Half Time), `2H` (Second Half), `PST` (Postponed), `CANC` (Cancelled), `SUSP` (Suspended).

2. **Match Statistics Snapshot (`fixtures/statistics/`)**:
   - Granular team-level statistics for completed fixtures:
     - `Ball Possession` (percentage)
     - `Total Shots`, `Shots on Goal`, `Shots off Goal`, `Blocked Shots`, `Shots insidebox`, `Shots outsidebox`
     - `Total passes`, `Passes accurate`, `Pass accuracy percentage`
     - `Corner Kicks`, `Offsides`, `Fouls`
     - `Yellow Cards`, `Red Cards`
     - `Goalkeeper Saves`, `Free Kicks`
     - `expected_goals` (where available from provider)

3. **Match Lineups Snapshot (`fixtures/lineups/`)**:
   - Tactical formations (e.g. `4-3-3`, `4-2-3-1`, `3-4-2-1`).
   - Starting XI (11 players with nominal position, jersey number, and grid coordinates).
   - Substitutes bench (up to 12 players).
   - Team coaches.

4. **Match Events Snapshot (`fixtures/events/`)**:
   - Minute-by-minute timeline (goals, assists, substitutions, yellow/red cards, VAR decisions).

### B. Silver Canonical Database (`apps/api/app/db/models/canonical.py`)
1. `Match`:
   - `id`, `provider`, `provider_fixture_id`, `competition_season_id`, `home_club_id`, `away_club_id`, `date`, `status`, `round`, `stage`, `venue_name`, `venue_city`, `referee`.
   - Targets: `home_score`, `away_score`, `halftime_home_score`, `halftime_away_score`, `fulltime_home_score`, `fulltime_away_score`, `winner_club_id`.
2. `MatchTeam`:
   - Normalized perspective for each team: `match_id`, `club_id`, `opponent_club_id`, `is_home`, `result` (`WIN`, `DRAW`, `LOSS`), `goals_for`, `goals_against`, `points` (3, 1, 0).
3. `MatchStatistics`:
   - Relational team match stats linked to `matches.id` and `clubs.id`.
4. `PlayerMatchStats`:
   - Individual player performance in match (minutes, goals, assists, shots, passes, duels, tackles, rating).
5. `FeatureSnapshot`:
   - Pre-computed rolling features stored with explicit temporal `as_of` timestamp.

---

## 2. Missing Data & Unexposed Variables

In accordance with strict system integrity rules:
1. **Betting Odds**:
   - Neither closing odds, opening odds, nor exchange price distributions exist in the database.
   - **Policy**: NEVER synthesize or fabricate betting odds. Baseline predictors must rely purely on historical outcomes, home advantage, and deterministic ratings.
2. **Injury & Suspension Registries**:
   - Dedicated medical suspension tables are not present; player availability must be evaluated from recent match lineups and squad registrations.
   - If a player was absent from previous match squads, availability status is treated with uncertainty (`UNKNOWN`), never fabricated.
3. **Historical Multi-Year Match Depth for All Clubs**:
   - While major leagues and test fixtures have temporal sequences, newly promoted or lower-tier clubs may have fewer than 3 historical matches.
   - **Policy**: When team history is `< 3 matches`, models must output `INSUFFICIENT_DATA` or `LOW_CONFIDENCE` rather than ungrounded high-confidence probabilities.

---

## 3. Temporal Coverage & Leakage Surface

1. **Temporal Boundaries**:
   - Historical test set covers 2023–2024 seasons (Premier League, European benchmarks).
   - Bronze live dataset covers 2026-09-20 global fixtures.
2. **Pre-Match Cutoff Policy**:
   - For any fixture kicking off at time $T$, feature calculation must strictly enforce:
     $$\text{match.date} < T$$
   - The fixture itself ($t = T$) and any subsequent fixtures ($t > T$) MUST BE STRICTLY EXCLUDED from rolling points, goals, form, Elo ratings, and team statistics.
3. **Target Variable Separation**:
   - The prediction target (Home Win / Draw / Away Win, Final Score, Total Goals) is derived solely from completed match outcomes and is NEVER accessible to feature transformers.

---

## 4. Team & Competition Coverage Matrix

| Competition Tier | Typical Match History Available | Team Strength Estimator | Reliability Status |
| :--- | :--- | :--- | :--- |
| **Tier 1 Leagues** (Premier League, Serie A, La Liga, MLS) | 10–38 matches / season | Rolling Form (L3, L5), Elo Rating, Attack/Def Strength | `PREDICTION_AVAILABLE` |
| **Tier 2 / Domestic Cups** (USL, Segunda, Taça de Portugal) | 3–15 matches / season | Rolling Form (L3), Group Elo, Class Frequency | `LOW_CONFIDENCE` if $N < 5$ |
| **Cup / International / Single-Fixture** | 0–2 matches in DB | Baseline League Class Frequency | `INSUFFICIENT_DATA` / `OUT_OF_DISTRIBUTION` |

---

## 5. Feature Coverage

| Feature Category | Source Entity | Availability | Pre-Match Calculation Formula |
| :--- | :--- | :--- | :--- |
| **Home Advantage** | `MatchTeam.is_home` | 100% | Discrete indicator (1 for home, 0 for away) + historical home win rate |
| **Team Elo Rating** | `matches` (chronological) | 100% where $N \ge 1$ | $R_{\text{new}} = R_{\text{old}} + K \times (S - E)$, frozen at $T$ |
| **Rolling Points Rate** | `MatchTeam.points` | 100% where $N \ge 1$ | $\sum \text{points} / N$ over windows (L3, L5, L10) |
| **Attack Strength** | `MatchTeam.goals_for` | 100% where $N \ge 1$ | Rolling goals scored per match / league average |
| **Defense Strength** | `MatchTeam.goals_against` | 100% where $N \ge 1$ | Rolling goals conceded per match / league average |
| **Days of Rest / Fatigue**| `Match.date` | 100% where $N \ge 2$ | $(T_{\text{match}} - T_{\text{prev\_match}})_{\text{days}}$ |
| **Head-to-Head Context**| `matches` (pairwise) | Where $N_{\text{H2H}} \ge 1$ | Pairwise win/draw/loss record strictly before $T$ |
| **Expected Goals ($\lambda_H, \mu_A$)**| Pre-match Model | 100% computed | Pre-match Poisson intensity based on attack/defense parameters |

---

## 6. Known Limitations & Audit Findings

1. **Small Sample Warnings**: In single-date Bronze batches, intra-season depth for certain clubs is limited; the model must fall back gracefully to competition priors and deterministic baselines.
2. **Probability Calibration Requirement**: Overconfident probability outputs on small samples are prohibited. Brier score and Expected Calibration Error (ECE) must guide model selection.
3. **No Target Leakage Guarantee**: Pre-match feature snapshots must be immutable, reproducible, and verifiable via automated bit-for-bit regression tests.
