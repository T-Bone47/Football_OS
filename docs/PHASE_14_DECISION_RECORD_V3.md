# Phase 14 — Decision Record V3 Architecture

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Current Phase**: Phase 14 — `OUTCOME_AWARE_DECISION_INTELLIGENCE`  
**Core Architectural Doctrine**: The Decision Record evolves from a frozen simulation artifact (V2) into an **outcome-aware retrospective instrument (V3)** while guaranteeing the strict immutability of historical decision data.

---

### 1. Dual-Section Architecture

Decision Record V3 is architected into two strictly segregated zones:

```
┌────────────────────────────────────────────────────────┐
│ DECISION RECORD V3                                     │
├────────────────────────────────────────────────────────┤
│ 1. HISTORICAL CORE SECTION (Strictly Immutable)        │
│   • decision_id: "dec_rec_timber_2023"                │
│   • project_id / project_name                          │
│   • final_decision: "EXECUTE_SCENARIO"                 │
│   • chosen_scenario_id / chosen_scenario_name          │
│   • candidate_set (Frozen player profiles)             │
│   • alternatives_considered (Rejected scenarios)       │
│   • scenario_assumptions (Explicit priors)             │
│   • constraints (Budget, wages, role requirements)     │
│   • model_versions & dataset_versions                  │
│   • historical_audit_digest (SHA-256)                  │
├────────────────────────────────────────────────────────┤
│ 2. RETROSPECTIVE SECTION (Append-Only)                 │
│   • evaluation_id: "eval_timber_2023"                  │
│   • realization_status: "EVALUATED"                    │
│   • overall_alignment: "ALIGNED"                       │
│   • evaluated_at (ISO timestamp)                       │
│   • realized_outcomes_count (Ledger links)             │
│   • divergence_metrics (e.g. ["minutes_played"])       │
│   • learning_signal_ids (Institutional alerts)         │
│   • process_quality_state: "WELL_SUPPORTED"            │
│   • freshness_state: "REQUIRES_REVIEW"                 │
│   • temporal_isolation_verified: true                  │
├────────────────────────────────────────────────────────┤
│ V3 AUDIT DIGEST: SHA-256(historical + retrospective)   │
└────────────────────────────────────────────────────────┘
```

---

### 2. Cryptographic Immutability Contract

1. **Historical Immutability Invariant**:
   - The historical section cannot be edited. Any attempt to modify historical attributes produces a digest mismatch.
   - The `historical_record.audit_digest` remains unchanged regardless of post-decision developments.
2. **Deterministic V3 Digest**:
   - The overall `v3_audit_digest` is computed over the historical audit digest combined with the serialized retrospective section.
   - This provides end-to-end cryptographic non-repudiation: analysts can verify exactly what was believed at decision time and what was subsequently evaluated.
