# PHASE 13 — REPOSITORY RECONNAISSANCE & ARCHITECTURE VERIFICATION
## Football Decision Intelligence 2.0: Tactical Simulation, Squad Construction & Counterfactual Governance

**Date**: 2026-09-26  
**Auditor**: Antigravity Lead Decision Intelligence & Systems Architect  
**Certified Baseline**: Phase 12 — `CONTINUOUS_INTELLIGENCE_VALIDATED`  
**Verified Test Suite**: 503 passed, 0 failures, 0 regressions  

---

## 1. Verified Baseline Architecture

The Football Intelligence OS currently operates on an evidence-backed foundation:
1. **Bronze & Silver Core**: Deterministic ingestion, SHA-256 snapshots, canonical schema normalization.
2. **Feature & Model Registries**: Temporal point-in-time features, calibrated multinomial logit match prediction, GBR valuation engine (`GBR_ValuationEngine_v1.0`), associative transfer risk (`TransferRiskEngine_v2`), and action-value vectors.
3. **Phase 10/11 Operational Governance**: Immutable decision records, persistent recruitment projects, candidate shortlists, watchlists, cross-competition readiness matrix, immutable dataset registry, model shadow mode, continuous drift monitoring (PSI), and deterministic Copilot.
4. **Phase 12 Continuous Intelligence**: Continuous data impact propagation, decision freshness assessments, governed continuous learning loop with Champion vs Challenger comparative evaluations, longitudinal player trajectories (`OBSERVED`/`MODELLED`/`PROJECTED`), breakout detection, empirical tactical role transitions, market value gap discovery, versioned benchmark profiles, multi-mode recruitment discovery, retrospective decision outcome feedback, and 10-tier Player Evidence Graphs.

---

## 2. Inventory of Reusable Components vs Limitations

| Engine / Component | Current Implementation | Reusability in Phase 13 | Identified Limitations & Gaps |
|:---|:---|:---|:---|
| **Squad Service & Simulator** | `app/squad/service.py`, `app/squad/simulator.py` | Highly reusable for roster transition mechanics | Limited to single transfer pairs (outgoing vs incoming); lacks multi-player combinations, academy pathways, and fixture congestion stress testing. |
| **Tactical Fit Engine** | `app/tactical/service.py`, `app/tactical/calculator.py` | Core 4-dimensional fit calculation (Position, Role, Dimension, System) | Evaluates individual players against a tactical context; lacks squad-level formation simulations across multiple formations simultaneously and role dependency graphs. |
| **Match Prediction Boundary** | `app/prediction/registry.py`, `app/prediction/service.py` | Strictly calibrated multinomial logit engine | Evaluates match probability impact for individual rosters; lacks clear counterfactual simulation tagging (`COUNTERFACTUAL_MODELLED`) and explicit scenario parameter boundaries. |
| **Persistent Scenarios** | `app/phase10/scenarios.py` | Roster movements and basic net spend | Scenarios are isolated records; lacks unified Scenario Graph connecting Club $\to$ Squad $\to$ Tactical System $\to$ Financials $\to$ Match Model $\to$ Evidence DAG; no Pareto frontier optimization. |
| **Recruitment Discovery** | `app/phase12/recruitment_discovery.py` | 7-mode candidate discovery | Discovers candidates, but lacks direct feeder mechanics into multi-transfer scenario comparison and Pareto trade-off analysis. |
| **Decision Records** | `app/phase10/decision_records.py` | Immutable signed decision snapshots | Captures chosen candidate, but lacks Decision Record V2 schema capturing multi-scenario alternatives considered and sensitivity intervals. |

---

## 3. Epistemic Separation & Counterfactual Model Boundary (§7, §36)

Phase 13 establishes the **Absolute Epistemic Rule**:
- **`OBSERVED`**: Empirically recorded past facts (matches played, realized transfer fees, contracts).
- **`MODELLED`**: Current statistical model estimates (tactical fit index, GBR valuation, contribution percentile).
- **`COUNTERFACTUAL`**: Modelled outcomes under hypothetical alterations to the roster or system (e.g. estimated squad rating change if Player A is replaced by Player B).
- **`SCENARIO`**: Explicit scout or club assumptions (assumed transfer fee, wage, contract length).
- **`ASSUMPTION`**: External context (e.g. expected fixture count, European qualification).

### Epistemic Boundary Constraint:
Counterfactual model outputs must NEVER make causal assertions such as:
> *"Signing Player Y will guarantee European qualification."*  
Instead, the system enforces:
> *"Under the specified scenario assumptions (assumed fee €35M, starter minutes), the model estimates a +0.07 shift in the squad progression vector with moderate confidence."*

---

## 4. Phase 13 Implementation Plan & Boundaries

Phase 13 will be built modularly in `apps/api/app/phase13/`:
1. `scenario_graph.py`: Unified Scenario Graph (`Club` $\to$ `Squad` $\to$ `Tactical System` $\to$ `Financials` $\to$ `Counterfactual Outputs` $\to$ `Evidence Lineage`).
2. `squad_construction.py`: Constrained optimization engine over formation, position requirements, budget, and squad registration rules with Pareto frontier extraction.
3. `tactical_simulator.py`: Multi-formation tactical system simulator (4-3-3, 4-2-3-1, 3-5-2, 3-4-3, 4-4-2, 5-3-2, 4-1-4-1, 3-4-2-1) detecting tactical gaps, role undercoverage, and role overloads.
4. `role_dependencies.py`: Role Dependency Graph modeling structural interactions (e.g. Ball Playing CB build-up $\to$ Midfield receiving structure $\to$ Fullback release).
5. `player_replacement.py`: Multi-dimensional player replacement simulator with explicit delta metrics.
6. `budget_depth_simulator.py`: Budget allocation across 8 pitch zones, squad depth stress testing (injuries, suspensions, congestion), and academy candidate integration.
7. `sensitivity_robustness.py`: Parameter perturbation testing (fee $\pm 10\%$, contribution $\pm 10\%$) classifying scenarios as `STABLE`, `SENSITIVE`, or `HIGHLY_SENSITIVE`.
8. `decision_record_v2.py`: Decision Record V2 capturing multi-scenario trade-offs, Pareto alternatives, and post-decision realization follow-up.
9. `copilot_v3.py`: Deterministic Scout Copilot V3 supporting counterfactual queries.
10. `routes_phase13.py`: REST API endpoints mounted in FastAPI.
11. Frontend Decision Lab (`DecisionLabPage.js`): Interactive professional decision workstation mounted at `/decision-lab`.
12. Comprehensive unit test suite (`test_phase13_decision_simulation.py`) ensuring zero regressions across all 503 baseline tests.

Reconnaissance complete. Proceeding to implementation.
