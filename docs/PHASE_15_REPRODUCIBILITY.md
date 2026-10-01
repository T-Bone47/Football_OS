# PHASE 15 — RESEARCH REPRODUCIBILITY & CRYPTOGRAPHIC LINEAGE
## Bit-for-Bit Deterministic Replay and Immutable Lineage Graphs

---

### 1. Cryptographic Lineage Guarantees

Phase 15 guarantees that every research finding, cohort, experiment, and evaluation is cryptographically verifiable:
- **`cohort_hash`**: SHA-256 fingerprint computed from canonicalized criteria, sorted entity IDs, and version string.
- **`experiment_hash`**: SHA-256 fingerprint linking dataset ID, cohort hash, feature candidate list, methodology, evaluation window, and results.
- **`graph_digest`**: SHA-256 digest of the entire research lineage graph connecting Question $\to$ Hypothesis $\to$ Cohort $\to$ Experiment $\to$ Validation $\to$ Candidate.

---

### 2. Deterministic Replay Protocol

To replay any historical experiment:
1. Load dataset corresponding to `dataset_id` with cutoff $\le T$.
2. Resolve cohort by `cohort_id` verifying that `cohort_hash` matches original ledger.
3. Apply identical feature list and methodology.
4. Execute evaluation; verify that computed output digest matches historical `experiment_hash`.

Any discrepancy indicates environment contamination, feature drift, or non-deterministic calculation, which immediately triggers an audit failure.
