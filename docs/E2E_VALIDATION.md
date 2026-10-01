# End-to-End Decision & Intelligence Validation (Phase 8 Section 2)

## Overview
Phase 8 validates the complete execution pipelines for four foundational football intelligence workflows. Every workflow produces auditable decision objects anchored to deterministic evidence graphs with cryptographic hashes.

---

## 1. Workflow A: Recruitment Target Analysis

### Execution Pipeline
$$\text{User Requirement} \longrightarrow \text{Hard Constraints} \longrightarrow \text{Candidate Universe} \longrightarrow \text{Tactical Fit} \longrightarrow \text{Similarity} \longrightarrow \text{Valuation} \longrightarrow \text{Risk} \longrightarrow \text{Squad Impact} \longrightarrow \text{Evidence DAG} \longrightarrow \text{Decision Assessment}$$

### Implementation & Verification
- **Engine**: `RecruitmentTargetEngine` via `UnifiedDecisionService.analyze_recruitment_targets`.
- **Constraint Filtering**: Hard constraints on age, minutes floor, position, and budget ceiling eliminate non-qualifying candidates prior to ranking.
- **Evidence DAG Structure**:
  - Contains nodes for `PLAYER`, `CONTRIBUTION`, `ROLE`, `TACTICAL_FIT`, `VALUATION`, `RISK`, `SQUAD`, and `DECISION`.
  - Computes a canonical SHA-256 `evidence_hash` invariant to collection order.
- **Verification Test**: `tests/unit/test_phase8_e2e_workflows.py::TestWorkflowARecruitment`.

---

## 2. Workflow B: Player Replacement Decision

### Execution Pipeline
$$\text{Departing Player} \longrightarrow \text{Replacement Profile} \longrightarrow \text{Candidate Pool} \longrightarrow \text{Stylistic Comparison} \longrightarrow \text{Market Feasibility} \longrightarrow \text{Adaptation Risk} \longrightarrow \text{Evidence Graph}$$

### Implementation & Verification
- **Engine**: `ReplacementDecisionEngine` via `UnifiedDecisionService.analyze_replacement`.
- **Stylistic Parity**: Measures multi-dimensional similarity to the departing player across roles and tactical attributes.
- **Provenance Preservation**: Links the departing player ID and replacement candidates to the final decision assessment.
- **Verification Test**: `tests/unit/test_phase8_e2e_workflows.py::TestWorkflowBReplacement`.

---

## 3. Workflow C: Transfer Scenario Modeling

### Execution Pipeline
$$\text{Current Squad} \longrightarrow \text{Transfers In/Out} \longrightarrow \text{Depth & Balance Analysis} \longrightarrow \text{Financial Feasibility} \longrightarrow \text{Tactical Transition} \longrightarrow \text{Match Simulation}$$

### Implementation & Verification
- **Engine**: `DecisionTransferScenarioEngine` via `UnifiedDecisionService.simulate_transfer_scenario`.
- **Financial Balance**: Computes gross expenditure, player sales income, and net transfer spend against club budget limits.
- **Squad Transition**: Quantifies before-and-after squad depth, age profile, and tactical role distribution.
- **Verification Test**: `tests/unit/test_phase8_e2e_workflows.py::TestWorkflowCTransferScenario`.

---

## 4. Workflow D: Match Intelligence & Feature Attribution

### Execution Pipeline
$$\text{Match Fixture} \longrightarrow \text{Pre-Match Features} \longrightarrow \text{Model Governance} \longrightarrow \text{Dixon-Coles xG} \longrightarrow \text{Scoreline Distribution} \longrightarrow \text{Feature Attribution}$$

### Implementation & Verification
- **Governance Gate**: Verifies model eligibility (`MODEL_VALIDATED`) via `governance_registry`.
- **Pre-Match xG & Scorelines**: Evaluates Dixon-Coles adjusted bivariate Poisson distributions over scorelines $[0..6] \times [0..6]$ with strict probability normalization ($\sum P = 1.0$).
- **Explainable Attribution**: `MatchExplanationEngine` decomposes key factors using non-causal phrasing grounded strictly in verified pre-match metrics.
- **Verification Test**: `tests/unit/test_phase8_e2e_workflows.py::TestWorkflowDMatchIntelligence`.

---

## 5. Decision Reproducibility & Cryptographic Evidence Hashing

To ensure immutable decision provenance:
1. **Deterministic Decision IDs**: Derived using `uuid.uuid5` with a DNS namespace and canonical parameter seed when `as_of` is provided.
2. **Canonical Evidence Hash**: Generated via SHA-256 over lexically sorted nodes and edges:
   $$\text{Hash} = \text{SHA256}\left(\sum \text{node}_{i} + \sum \text{edge}_{j}\right)$$
3. **Replay Invariance**: Replaying an evaluation with identical historical context yields an identical evidence hash down to the bit level.
- **Verification Test**: `tests/unit/test_phase8_reproducibility.py::TestDecisionReproducibility`.
