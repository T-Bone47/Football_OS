# Unified Decision Intelligence Architecture (Phase 7)

## 1. Executive Summary & Mission
Phase 7 elevates Football Intelligence OS from isolated, modular analytical silos into an interconnected, evidence-driven football decision-intelligence platform.

Prior phases validated individual capabilities:
- **Phase 1–2**: Ingestion, normalization, schema integrity, and temporal feature snapshots.
- **Phase 3**: Player Action Values, Contribution Vectors, Role Discovery, and Stylistic Similarity.
- **Phase 4**: Transfer Market Datasets, Baseline Valuations, Comparable Transfers, and Transfer Risk Assessment.
- **Phase 5**: Squad Depth Modeling and Transfer Sandbox Simulator.
- **Phase 6**: Probabilistic, Calibrated Match Prediction and Total-Goal Distribution.

Phase 7 establishes a canonical **Decision Intelligence Layer** that synthesizes these engines into explainable, non-causal, auditable recruitment and transfer decisions.

---

## 2. Core Architectural Principles

### 2.1 The Canonical `DecisionAssessment` Object
The platform rejects opaque "AI aggregate scores". Decisions must remain decomposable:

```
DecisionAssessment
├── decision_id: UUID
├── decision_type: RECRUITMENT | REPLACEMENT | TRANSFER_SCENARIO | COMPARISON
├── subject_type: POSITION | PLAYER | SQUAD | FIXTURE
├── subject_id: Optional[UUID]
├── as_of: datetime (UTC)
├── summary: str
├── candidates: List[MultiDimensionalCandidateAssessment]
│   ├── candidate_id: UUID
│   ├── player_name: str
│   ├── primary_position: str
│   ├── target_role: str
│   ├── performance: DimensionPerformance
│   ├── tactical: DimensionTactical
│   ├── similarity: DimensionSimilarity
│   ├── market: DimensionMarket
│   ├── risk: DimensionRisk
│   ├── squad_impact: DimensionSquadImpact
│   ├── prediction_impact: Optional[DimensionPredictionImpact]
│   ├── confidence: ConfidenceDecomposition
│   ├── why_matches: List[str]
│   └── where_differs: List[str]
├── confidence: ConfidenceDecomposition
│   ├── data_confidence: float [0, 1]
│   ├── model_confidence: float [0, 1]
│   ├── decision_confidence: float [0, 1]
│   ├── confidence_tier: HIGH | MODERATE | LOW | VERY_LOW
│   ├── data_status: DECISION_AVAILABLE | LOW_CONFIDENCE | INSUFFICIENT_DATA | OUT_OF_DISTRIBUTION | PARTIAL_EVIDENCE
│   ├── sufficiency_factors: List[str]
│   └── uncertainty_drivers: List[str]
├── evidence_graph: DecisionEvidenceGraph
└── provenance: Dict[str, Any]
```

### 2.2 Strict Non-Causal Policy
No recommendation or scenario prediction claims causal certainty. 
- Real-world match outcomes, player adaptation, and transfer ROI are contingent on unobserved environmental, tactical, and interpersonal variables.
- All scenario outputs are explicitly classified as:
  1. `OBSERVED`: Historical matches, recorded transfer fees, logged minutes.
  2. `ESTIMATED`: Conformal valuation ranges, peer percentile ratings.
  3. `MODELED`: Calibrated win probabilities, tactical fit scores.
  4. `SCENARIO ASSUMPTION`: Counterfactual additions or subtractions to squads.

---

## 3. Tripartite Confidence Architecture
Confidence is never a single monolithic percentage. The platform explicitly separates three distinct confidence vectors:

1. **Data Confidence ($C_{data}$)**:
   Measures sample completeness, minutes played, appearance frequency, and statistical history.
   $$C_{data} = \min\left(1.0, \frac{\text{minutes}}{1500} \cdot 0.70 + \frac{\text{matches}}{15} \cdot 0.30\right)$$
   A player with 250 minutes cannot exceed $0.40$ data confidence, regardless of how cleanly models perform.

2. **Model Confidence ($C_{model}$)**:
   Reflects the calibration, cross-validation stability, and out-of-distribution (OOD) status of underlying sub-models.
   Penalized if features fall outside training feature bounds or if conformal prediction intervals are wide.

3. **Decision Confidence ($C_{decision}$)**:
   The harmonic composite of data confidence and model confidence:
   $$C_{decision} = \frac{2 \cdot C_{data} \cdot C_{model}}{C_{data} + C_{model}}$$
   Guarantees that a low-confidence data sample halts the entire decision confidence from reaching `HIGH` or `MODERATE`.

---

## 4. Temporal Safety Guarantees
Decision assessments must be reproducible at any historical timestamp $T$:
$$\text{feature\_as\_of} \le T_{\text{decision}}$$
$$\text{transfer\_info\_as\_of} \le T_{\text{decision}}$$
$$\text{match\_results\_as\_of} \le T_{\text{decision}}$$

Automated regression tests verify that injecting future match events, transfers, or statistics does not alter retrospective decision outputs or candidate rankings.
