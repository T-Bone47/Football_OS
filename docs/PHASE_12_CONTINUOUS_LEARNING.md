# Phase 12 — Continuous Learning & Governed Model Retraining

## 1. Executive Summary & Epistemic Principle

Phase 12 transforms the **Football Intelligence OS** into a continuous decision intelligence platform:

> **"NEW DATA MUST CREATE EVIDENCE. NEW DATA MUST NOT AUTOMATICALLY CREATE NEW BELIEFS."**  
> Under no circumstances may a model update or promote itself automatically to production simply because new match or transfer records arrive. All model promotions require explicit, audited human-in-the-loop approval.

---

## 2. Governed Continuous Learning Lifecycle (§5, §28)

The system implements an 11-step immutable learning pipeline:

```mermaid
flowchart TD
    D1[New Match / Transfer Data] --> D2[Bronze Ingestion & Provenance SHA-256]
    D2 --> D3[Population Stability & Drift Verification (PSI)]
    D3 --> D4[Continuous Data Impact Propagation Graph]
    D4 --> D5{Retraining Trigger Evaluation?}
    D5 -- NO_RETRAIN_REQUIRED --> D6[Maintain Current Champion Model]
    D5 -- RETRAIN_RECOMMENDED --> D7[Train Candidate Model on Chronological Split]
    D7 --> D8[Out-of-Sample Holdout Validation]
    D8 --> D9[Independent Probability Calibration (Zero Test Leakage)]
    D9 --> D10[Parallel Shadow Mode Execution]
    D10 --> D11[Champion vs Challenger Multi-Metric Comparison]
    D11 --> D12{Audited Promotion Approval?}
    D12 -- REJECTED --> D13[Candidate Retired]
    D12 -- APPROVED --> D14[Promote Challenger & Register in Model Registry]
```

---

## 3. Retraining Triggers & Thresholds (§6)

The `RetrainingTriggerEngine` (`app/phase12/retraining_triggers.py`) deterministically evaluates active model telemetry against empirical gates:

| Trigger Signal | Threshold | Recommendation | Action |
|:---|:---:|:---:|:---|
| **Population Stability Index (PSI)** | $\text{PSI} \ge 0.25$ | `RETRAIN_RECOMMENDED` | Trigger isolated challenger training pipeline |
| **Warning Drift** | $0.20 \le \text{PSI} < 0.25$ | `REVIEW_REQUIRED` | Enhanced operational logging & engineer alert |
| **Brier Score Degradation** | $\Delta \text{Brier} \ge 0.05$ | `RETRAIN_RECOMMENDED` | Retrain on recent rolling observation window |
| **ECE Miscalibration** | $\Delta \text{ECE} \ge 0.04$ | `RETRAIN_RECOMMENDED` | Recalibrate temperature scaling on validation split |
| **Accumulated Observations** | $N \ge 100$ matches | `REVIEW_REQUIRED` | Evaluate sample expansion benefit |
| **Seasonal Staleness** | $\ge 180$ days since training cutoff | `RETRAIN_RECOMMENDED` | Ingest complete seasonal transfer & tactical update |

---

## 4. Continuous Data Impact Propagation Graph (§3)

When new match records are ingested, the `ContinuousDataImpactEngine` traverses downstream analytical dependencies:
```
Match Ingestion
  ↓
Player Match Stats (Silver Aggregations)
  ↓
Player Features (Feature Registry v1)
  ↓
Player Intelligence (Action Value v2)
  ↓
Role Classification (Clustering)
  ↓
Player Similarity (Position-Gated Cosine)
  ↓
Tactical Fit (4D Engine)
  ↓
Transfer Valuation (GBR v1.0)
  ↓
Recruitment Projects & Watchlists
  ↓
Historical Decision Records (Audited for Freshness; Preserved Immutably)
```

### Strict Immutability Guarantee
No historical decision record (`DecisionRecord`) is ever modified or rewritten during data impact propagation. Decisions are independently evaluated by the `DecisionStalenessEngine` and tagged with a non-destructive `DecisionFreshnessAssessment`.
