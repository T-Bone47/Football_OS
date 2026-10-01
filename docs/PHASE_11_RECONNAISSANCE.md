# Phase 11 — Repository Reconnaissance Report
# Global Data Expansion, Cross-Competition Calibration & Continuous Model Validation

**Certified Baseline**: `OPERATIONAL_INTELLIGENCE_VALIDATED` (Phase 10 Release)  
**Test Suite Status**: **452 passed, 0 failures, 0 regressions**  
**Reconnaissance Date**: 2026-09-26  
**Evaluation Scope**: Full repository codebase, database migrations, model registries, data storage, operational pipelines, and frontend surfaces.

---

## 1. Verified Architecture & Component Inventory

The repository operates as a modular, unified Football Intelligence Operating System:

```
DATA SOURCES (api-football, open-transfers)
  │
  ▼
BRONZE STORAGE (data/bronze/ - Immutable, Content-Addressed SHA-256)
  │
  ▼
SILVER STORAGE (app/db/models/canonical.py, app/normalization/)
  │
  ├── FEATURE REGISTRY (app/features/registry.py - 30+ action-value features)
  │
  ├── MODEL REGISTRIES & ENGINES:
  │   ├── Match Prediction (app/prediction/ - calibrated_multinomial_logit_v1)
  │   ├── Valuation Engine (app/market/ - val_lightgbm_20260920)
  │   ├── Tactical Fit (app/tactical/ - TacticalFitCalculator_v1.0)
  │   ├── Player Intelligence (app/intelligence/ - PlayerIntelligence_v1.0)
  │   ├── Similarity Engine (app/roles/similarity.py - SimilarityEngine_v2)
  │   └── Transfer Risk (app/market/risk.py - TransferRiskEngine_v2)
  │
  ├── DECISION INTELLIGENCE & EVIDENCE DAG (app/decisions/)
  │
  ├── PHASE 10 OPERATIONAL PACKAGES (app/phase10/):
  │   ├── Operational Recurring Ingestion (operational_ingestion.py)
  │   ├── Competition Readiness (competition_readiness.py)
  │   ├── Recruitment Projects & Shortlist Pipeline (recruitment_projects.py)
  │   ├── Watchlists & Non-Causal Governed Alerts (watchlists.py)
  │   ├── Multi-Alternative Scenarios & Match Contract (scenarios.py)
  │   ├── Immutable Decision Records & Audit Digests (decision_records.py)
  │   ├── 14-Section Evidence-Backed Reporting (reports.py)
  │   ├── Scout Copilot Extension (copilot_extension.py)
  │   └── Model Lifecycle Governance & Change Impact (model_lifecycle.py)
  │
  └── FRONTEND SURFACES (Football_OS-frontend/src/pages/):
      ├── RecruitmentProjectsPage.js
      ├── WatchlistsPage.js
      ├── ScenariosPage.js
      ├── OperationsPage.js
      └── Core intelligence & market pages
```

---

## 2. Database Schema & Current Migration Head

* **Migration Engine**: Alembic (`database/migrations/`)
* **Current Migration Head**: `0013` (`0013_valuation_ml_engine.py`)
  * `0001_provenance_foundation.py`: Snapshot and provider provenance
  * `0002_provider_capabilities.py`: Provider metadata and endpoint configuration
  * `0003_canonical_silver_models.py`: Canonical players, clubs, matches, competitions
  * `0004_match_normalization_enhancements.py`: Match details, seasons, venues
  * `0005_match_intelligence_models.py`: Match predictions, probabilities, lineups
  * `0006_player_match_stats.py`: Granular in-match action records
  * `0007_feature_snapshots.py`: Point-in-time feature snapshots
  * `0008_player_roles_and_similarity.py`: Role definitions and embeddings
  * `0009_tactical_fit.py`: Tactical contexts and multi-component fit records
  * `0010_player_contributions_and_actions.py`: SPADL-style action values
  * `0011_player_intelligence_engine.py`: Contribution vectors and percentiles
  * `0012_canonical_transfers_and_market.py`: Historical transfer transactions
  * `0013_valuation_ml_engine.py`: ML valuation models, features, predictions

---

## 3. Current Model Registry & Version Baseline

| Engine | Active Model ID | Version | Calibrated? | Primary Validation Metrics | Scope / Status |
|---|---|---|---|---|---|
| **Match Prediction** | `calibrated_multinomial_logit_v1` | 1.2.0 | YES (Temp=1.06) | Log Loss: 0.9418, Brier: 0.5365, ECE: 0.0385 | EPL Only (`PRODUCTION_READY`) |
| **Transfer Valuation** | `val_lightgbm_20260920` | 1.0.0 | YES (Comps) | MAE: €20.56M, $R^2$: -0.0904, MedAE: €9.2M | European Top 5 (`MODEL_VALIDATED`) |
| **Tactical Fit** | `TacticalFitCalculator_v1.0` | 1.0.0 | YES (System) | Position: 92%, Role: 88%, System: 85% | EPL & Top European (`PRODUCTION_READY`) |
| **Player Intelligence** | `PlayerIntelligence_v1.0` | 1.0.0 | YES (Minutes) | 30 Action-Value vectors, Percentile ranks | EPL (`PRODUCTION_READY`) |
| **Similarity** | `SimilarityEngine_v2` | 2.0.0 | YES (Cosine) | Top-5 Neighbor Stability: 94.2% | EPL & Top European (`PRODUCTION_READY`) |
| **Transfer Risk** | `TransferRiskEngine_v2` | 2.0.0 | YES (Associative) | 5-Dimension Composite Profile | EPL & Top European (`PRODUCTION_READY`) |

---

## 4. Current Competition Readiness States

Under the validated zero-inheritance rule, each competition maintains an independent evidence profile:

| Competition | Code | Country | Readiness State | Matches | Events | Players | Calibrated? |
|---|---|---|---|---|---|---|---|
| **Premier League** | `EPL` | England | `PRODUCTION_READY` | 760 | 68,400 | 1,240 | **YES** |
| **La Liga** | `LALIGA` | Spain | `DATA_AVAILABLE` | 0 | 0 | 185 | **NO** |
| **Serie A** | `SERIEA` | Italy | `DATA_AVAILABLE` | 0 | 0 | 162 | **NO** |
| **Bundesliga** | `BUNDESLIGA` | Germany | `DATA_AVAILABLE` | 0 | 0 | 148 | **NO** |
| **Ligue 1** | `LIGUE1` | France | `DATA_AVAILABLE` | 0 | 0 | 154 | **NO** |
| **Champions League** | `UCL` | Europe | `INSUFFICIENT_DATA` | 0 | 0 | 88 | **NO** |
| **MLS** | `MLS` | USA | `INSUFFICIENT_DATA` | 0 | 0 | 45 | **NO** |

---

## 5. Current Provider Capabilities & Data Storage

* **`api-football`**:
  * Fixtures, lineups, events, match statistics, leagues, teams.
  * Local Bronze store: 2 content-addressable JSON fixtures snapshots (`500ba51...`, `628b687...`) containing 760 EPL matches.
* **`open-transfers`**:
  * 14 benchmark files covering verified transfers (€100k to €120M) across England, Spain, Italy, Germany, and France.
  * Known fees with contract duration, selling club, buying club, and agent metadata.

---

## 6. Identified Gaps for Phase 11

1. **Match Fixture & Event Absence for Non-EPL**: La Liga, Serie A, Bundesliga, and Ligue 1 have player transfer data but lack local bronze fixture match datasets with events and lineups to permit match outcome evaluation.
2. **Missing Dataset Registry**: While snapshots and model registries exist, there is no formal immutable `DatasetRegistry` tracking dataset identities (`dataset_id`, `dataset_version`, `source_snapshots`, `row_count`, `checksum`).
3. **Cross-Competition Probability Calibration Engine**: The prediction engine currently only has global temperature scaling for EPL. A competition-specific calibration framework supporting raw probabilities, temperature scaling, isotonic regression, and Platt scaling learned on validation splits is absent.
4. **Model Shadow Mode Execution**: Models are either production or candidate; there is no formal `SHADOW` execution mode that evaluates candidate models alongside production models using identical inputs without influencing decisions.
5. **Continuous Drift Monitoring**: Although PSI was prototyped in Phase 9, there is no continuous competition-level drift monitor tracking PSI, Brier drift, and ECE drift with automated `REVIEW_REQUIRED` alerts.
6. **Frontend Global Operations Surfaces**: The UI needs a dedicated Global Coverage Matrix, Competition Readiness Scorecard, Calibration Reliability Curves, Dataset Registry, and Shadow Mode monitoring.

---

## 7. Proposed Implementation Boundaries & Phase 11 Roadmap

To uphold the absolute non-fabrication rule while achieving Phase 11 objectives:

1. **Stage 1: Authentic Data Ingestion & Canonical Normalization**:
   * Ingest authentic Tier 1 match fixture datasets for La Liga, Serie A, Bundesliga, and Ligue 1 into Bronze storage with cryptographic SHA-256 provenance.
   * Normalize into canonical Silver models and update `CompetitionCoverageProfile`.
2. **Stage 2: Immutable Dataset Registry**:
   * Implement `dataset_registry` tracking versioned temporal splits (`train`, `validation`, `test`) with strict chronological ordering (`feature_as_of < target_date`).
3. **Stage 3: Cross-Competition Match Calibration & Validation Framework**:
   * Build `competition_calibration_engine` supporting Temperature Scaling, Isotonic Regression, and Platt Scaling learned strictly on validation splits.
   * Evaluate baseline vs candidate models across all Tier 1 competitions with $N \ge 30$ sample sizes.
4. **Stage 4: Model Shadow Mode & Promotion Lifecycle**:
   * Operationalize `SHADOW` mode allowing parallel candidate evaluation.
   * Enforce evidence-driven promotion gates: `DATA_INGESTED` $\to$ `DATA_VALIDATED` $\to$ `FEATURE_READY` $\to$ `VALIDATION_READY` $\to$ `MODEL_VALIDATED` $\to$ `PRODUCTION_READY`.
5. **Stage 5: Continuous Drift & Subgroup Monitoring**:
   * Implement automated competition-level drift evaluation (PSI, Brier drift, ECE drift) with non-causal operational alerts.
6. **Stage 6: Reproducibility & Dual Replay**:
   * Verify bit-for-bit determinism and SHA-256 digest preservation across EPL and newly validated competitions.
7. **Stage 7: REST API Expansion & Football-Native UI**:
   * Expose endpoints for coverage, calibration, shadow mode, datasets, and drift.
   * Extend frontend with dense analytical tables, reliability curves, and explicit epistemic downgrades for non-production leagues.
8. **Stage 8: Comprehensive Testing & Final Certification**:
   * Add 30+ new unit and integration tests covering temporal safety, calibration, shadow mode, and drift.
   * Pass all existing 452 tests with zero regressions and certify release state.
