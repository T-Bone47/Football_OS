# Match Prediction Data Documentation (Phase 6)

## 1. Overview & Data Provenance
The Football Intelligence OS Match Prediction Engine relies on pre-match historical fixtures, rolling performance metrics, and contextual match indicators strictly partitioned as of kickoff. 

Data sources and pipeline provenance:
- **Bronze Layer**: Raw match fixtures and event feeds ingested from API-Football and StatsBomb open feeds (e.g. `bronze/api_football/fixtures/date=2026-09-20/fixtures.json`).
- **Canonical Models**: Database models `Match`, `Club`, `MatchTeam`, `MatchStatistics`, `MatchLineup`, and `MatchEvent` with UUID foreign keys and temporal timestamps.
- **Pre-Match Cutoff Rule**: Strict temporal boundary $t_{\text{cutoff}} = \min(\text{kickoff}, \text{as\_of})$. Every feature query strictly filters matches by `date < cutoff` and `id != match_id`.

---

## 2. Dataset Partitioning & Coverage
The dataset audited in Phase 6.1 (`docs/MATCH_PREDICTION_DATA_AUDIT.md`) covers historical European, domestic, and international fixtures:

| Split | Time Window | Fixtures Count | Purpose |
|---|---|---|---|
| **Training Set** | 2026-08-01 to 2026-08-31 | 1,520 fixtures | Feature engineering, Elo calibration, Logit weight estimation |
| **Validation Set** | 2026-09-01 to 2026-09-10 | 388 fixtures | Temperature scaling optimization, threshold tuning |
| **Test Set** | 2026-09-11 to 2026-09-20 | 400 fixtures | Final untouched temporal evaluation & calibration verification |

### Competition Coverage
- Premier League (England)
- La Liga (Spain)
- Serie A (Italy)
- Bundesliga (Germany)
- Ligue 1 (France)
- UEFA Champions League & Europa League fixtures

---

## 3. Missing Data Policies & Fallback Truthfulness
Under Non-Negotiable Principle 6 (No Fabrication):
- **Odds**: Betting market odds are not present in the canonical database and are **never** fabricated.
- **Lineups**: If official starting lineups are not announced prior to prediction time, the system uses historical rolling squad metrics with no fabricated rosters.
- **Injuries**: No synthetic injury lists are created; availability reflects actual recorded squad minutes.
- **Zero-History Clubs**: If a club has zero matches prior to cutoff, the system outputs `INSUFFICIENT_DATA` and falls back to global empirical league priors (`P(Home)=0.442, P(Draw)=0.260, P(Away)=0.298`).

---

## 4. Leakage Prevention Protocol
1. **Target Leakage**: Final match scores (`home_score`, `away_score`), winner club, and match events are forbidden from the pre-match feature vector.
2. **Future Match Leakage**: Matches with `date >= cutoff` are filtered out before feature aggregation.
3. **In-Game Statistics**: Shots, possession, xG, and fouls occurring during the target fixture are never accessible to pre-match predictors.
4. **Automated Verification**: `tests/unit/test_match_prediction_leakage.py` validates bit-for-bit invariance when future matches are injected into the repository.
