# Phase 10 — Operational Intelligence Architecture & Production Guide

## 1. Executive Mission & Continuous Intelligence Architecture

Phase 10 transforms the validated Football Intelligence OS into a continuous, real-time operational platform. Rather than training disconnected models or altering Phase 8/9 validated intelligence architectures, Phase 10 operationalizes the existing engines into production-grade decision workflows:

```
LIVE / SCHEDULED DATA (Provider Ingestion)
        ↓
CONTROLLED 11-STAGE RECURRING INGESTION (Provenance & SHA-256)
        ↓
CONTINUOUS INTELLIGENCE & FEATURE REFRESH
        ↓
COMPETITION READINESS GATES (Zero EPL Inheritance)
        ↓
RECRUITMENT PROJECTS (Hard Constraints → Soft Scoring)
        ↓
CANDIDATE SHORTLISTS (6-Stage Discrete Lifecycle)
        ↓
WATCHLISTS & GOVERNED ALERTS (Non-Causal Epistemic Guardrails)
        ↓
MULTI-ALTERNATIVE SCENARIOS (OBSERVED / MODELLED / SCENARIO Separation)
        ↓
MATCH PREDICTION CONTRACT ENFORCEMENT (SCENARIO_UNSUPPORTED Boundary)
        ↓
IMMUTABLE AUDIT DECISION RECORDS (SHA-256 Cryptographic Digest)
        ↓
14-SECTION EVIDENCE-BACKED REPORTING
```

---

## 2. 11-Stage Controlled Recurring Ingestion Pipeline (§2, §3)

Operational ingestion executes through an 11-stage immutable lifecycle managed by `operational_pipeline` in `app/phase10/operational_ingestion.py`:

1. **Provider Authentication**: Verification of credentials and active subscription headers (`api-football`, `open-transfers`).
2. **Capability Check**: Schema negotiation and resource capability verification.
3. **Rate Limiting Guard**: Token bucket verification preventing quota exhaustion.
4. **Raw Snapshot Capture**: In-flight payload capture before transformation.
5. **SHA-256 Cryptographic Checksum**: Content-addressable hash computation.
6. **Ingestion Gate Validation**: Verification against 9 Phase 9 quality gates (schema conformance, date ordering, coordinate boundaries, identifier integrity).
7. **Bronze Immutable Persistence**: Stored under content-addressed snapshots. Bronze records are never overwritten.
8. **Normalization & Identity Resolution**: Deterministic resolution via `(provider, provider_record_id)` into canonical entities.
9. **Silver Curated Storage**: Versioned atomic updates with schema validation.
10. **Feature Registry Refresh**: Selective cache invalidation for affected players.
11. **Model Readiness & Impact Telemetry**: Emitting run records with status, seen/accepted/rejected counts, and downstream impact signals.

### Ingestion Run Telemetry Schema
Every cycle generates an immutable run record:
- `ingestion_run_id`: Unique run identifier (`run_ops_YYYYMMDD_...`)
- `provider`: Data vendor (`api-football`, `open-transfers`)
- `resource`: Data resource (`fixtures`, `players`, `transfers`, `lineups`)
- `requested_at` / `completed_at`: UTC timestamps
- `status`: `COMPLETED`, `FAILED`, `DRY_RUN`
- `records_seen` / `records_accepted` / `records_rejected`
- `validation_status`: `PASSED`, `REJECTED`, `QUARANTINED`
- `snapshot_id`: Pointer to Bronze artifact
- `checksum`: Cryptographic SHA-256 digest
- `error_summary`: Diagnostic errors for gate rejections

---

## 3. Competition Readiness & Coverage Monitoring (§4, §5)

To prevent uncalibrated cross-competition extrapolation, Phase 10 introduces formal **Competition Readiness States**:

| State | Definition | Permitted Analytical Operations |
|---|---|---|
| `NOT_AVAILABLE` | No ingestion adapter or raw data available. | None. Ingestion disabled. |
| `INSUFFICIENT_DATA` | Sample size below validation threshold ($N < 30$). | Ingestion & profiling only. Model inference blocked. |
| `DATA_AVAILABLE` | Bronze & Silver storage populated, basic stats compiled. | Feature inspection, raw metric comparison. Match prediction blocked. |
| `MODEL_VALIDATED` | Out-of-sample calibration verified on target league. | Shadow and candidate model execution. |
| `PRODUCTION_READY` | Full calibration, Brier score $< 0.55$, data gates verified. | Authoritative model execution and scout reporting. |

### Strict Zero-Inheritance Rule
A non-EPL competition (e.g. La Liga, Serie A, MLS) **never automatically inherits English Premier League model validity**. The system maintains competition-specific evidence profiles and explicitly marks uncalibrated leagues as uncalibrated rather than fabricating predictions.

---

## 4. Persistent Recruitment Projects & Candidate Shortlists (§6, §7, §8)

Recruitment workflows are structured around persistent projects managed by `recruitment_manager`:

### Project Structure
- `project_id`: Unique identifier (e.g. `proj_cb_summer_2027`)
- `name`: Human-readable label ("Summer 2027 CB Recruitment")
- `club`: Target club ("Arsenal")
- `season`: Planning horizon ("2024/2025" or "Summer 2027")
- `position`: Target position ("CB")
- `target_role`: Target tactical role ("Ball Playing Defender")
- `formation`: Club primary system ("4-3-3")
- `budget_eur`: Financial ceiling (€40.0M)
- `hard_constraints`: Max age (26), max transfer fee (€40M), min observed minutes (1,200)
- `risk_tolerance`: Maximum acceptable risk category

### Pipeline Execution Order
1. **Hard Constraints**: Filter candidate universe strictly before soft scoring. Candidates failing hard gates (budget, age, minutes) are disqualified immediately.
2. **Candidate Universe**: Filtered pool of eligible players.
3. **Multi-Dimensional Analytics**: Parallel evaluation of:
   - Player Intelligence (contribution percentiles)
   - Role Discovery (primary tactical role)
   - Tactical Fit (compatibility with club formation)
   - Similarity (distance to benchmark profiles)
   - Market Valuation (LightGBM estimate + comp range)
   - Transfer Risk (5-dimension associative risk vectors)
   - Squad Impact (projected rating & wage delta)
4. **No Opaque Collapse**: The workflow **never collapses these dimensions into a single opaque score**. Scouts inspect each axis independently.

### 6-Stage Discrete Shortlist States
Candidates advance through discrete workflow stages:
`DISCOVERED` $\to$ `REVIEWING` $\to$ `SHORTLISTED` $\to$ `SCENARIO_TESTED` $\to$ `DECISION_RECORDED` $\to$ `ARCHIVED`

Manual scout annotations and tags are stored strictly in metadata and **never alter analytical model results**.

---

## 5. Watchlist Engine & Non-Causal Alert Governance (§9, §10)

Continuous intelligence monitors tracked entities (players, clubs, positions, roles) and triggers alerts on:
- Performance metric shifts (contribution percentiles)
- Tactical role transitions
- Playing time and minutes accumulation
- Transfer valuation movements
- Injury/risk profile changes
- Tactical fit changes under manager adjustments

### Alert Governance & Non-Causal Epistemic Guardrail
All generated alerts must pass `validate_non_causal_phrasing()`:
- **VALID**: *"Player contribution percentile increased from 82.0 to 88.5."*
- **VALID**: *"Player valuation shifted from €34.0M to €38.0M."*
- **INVALID (REJECTED)**: *"Player has become a better player."*
- **INVALID (REJECTED)**: *"Tactical maturity improved due to coaching changes."*

Causal speculation is strictly rejected at the validation boundary. Every alert contains pre/post values, delta, model version, provider source, confidence tier, and evidence nodes.

---

## 6. Multi-Alternative Scenario Engine & Match Prediction Contract (§11, §12)

Scouts can build and simulate multiple roster alternatives:
- **Scenario A**: Sell Player X / Buy Target Y
- **Scenario B**: Retain Player X / Buy Target Y (via credit headroom)
- **Scenario C**: Sell Player X / Promote Academy Player Z

### Strict Modality Separation
Every output explicitly identifies its epistemic nature:
- `OBSERVED`: Grounded in historical facts (observed wages, contract dates, actual fees).
- `MODELLED`: Generated by validated analytical engines (tactical fit score, valuation range).
- `SCENARIO`: Contingent planning assumption (amortization schedule, negotiated fee).

### Match Prediction Contract Boundary
When scenario squad modifications exceed the calibrated domain of the multinomial logit match prediction engine (e.g. $> 5$ net squad additions/removals), the engine returns:
```json
{
  "status": "SCENARIO_UNSUPPORTED",
  "reason": "Net squad movements (6) exceed validated model calibration boundary (max 5)."
}
```
This prevents fabricating match win probability distributions in uncalibrated regime shifts.

---

## 7. Immutable Decision Records (§13)

When a recruitment decision is finalized, it is stored in `decision_store` as an immutable record:
- `decision_id`: Unique identifier
- `project_id`: Parent recruitment project
- `chosen_candidate`: Selected target
- `candidate_set`: Full shortlisted comparative pool
- `project_constraints`: Budget, age, and role constraints at time of decision
- `scenario_assumptions`: Financial and tactical assumptions
- `model_versions`: Snapshot of all active model versions
- `evidence_dag`: Complete evidence nodes supporting the decision
- `audit_digest`: Cryptographic SHA-256 hash computed over canonical JSON representation

Once recorded, a decision cannot be updated or overwritten. Any subsequent data arrival records a change impact event without mutating historical decisions.

---

## 8. Evidence-Backed 14-Section Reporting (§14)

The reporting engine compiles evidence-backed dossiers:
1. Executive Summary
2. Recruitment Requirement & System Scope
3. Candidate Universe & Constraints
4. Candidate Comparative Matrix
5. Player Intelligence & Contribution Vectors
6. Tactical Fit & System Synergy
7. Market Valuation & Contract Headroom
8. Transfer Risk & Stability Profile
9. Squad Impact & Payroll Dynamics
10. Multi-Alternative Scenarios
11. Evidence DAG & Audit Lineage
12. Data Quality & Coverage Summary
13. Limitations & Material Epistemic Boundaries
14. Formal Decision Record & Cryptographic Sign-Off

Reports render in both structured JSON and high-contrast Markdown for executive export.

---

## 9. Scout Copilot Integration (§15)

The natural language Copilot is extended via `copilot_dispatcher` to handle operational queries:
- *"Show me the current shortlist for Summer 2027 CB"*
- *"What changed about William Saliba?"*
- *"Why was Gonçalo Inácio shortlisted?"*
- *"Simulate selling Partey and buying Inácio"*
- *"What evidence supports this candidate?"*

The Copilot strictly queries deterministic tool registries and never invents metrics or fabricates historical records.
