# Model Governance & Regulatory Integrity Architecture

## Overview
Phase 8 establishes a centralized, authoritative **Model Governance Subsystem** (`app.observability.model_governance`). The platform strictly prohibits silent model fallbacks, opaque shadow promotions, and the deployment of uncalibrated analytical pipelines.

---

## 1. Authoritative Model Registry

All production analytical models must be registered in the singleton `governance_registry` with a formal metadata record specifying:
- **Model Name & Version Identifier**
- **Model Family** (e.g., `BIVARIATE_POISSON`, `GRADIENT_BOOSTED_REGRESSOR`, `COSINE_VECTOR_EMBEDDING`)
- **Validation Status**
- **Benchmark Evaluation Metrics**
- **Training Temporal Cutoff Date**

### Canonical Production Registry

```python
{
    "match_prediction_engine": {
        "version": "BivariatePoisson_v1",
        "family": "BIVARIATE_POISSON",
        "status": "MODEL_VALIDATED",
        "metrics": {"brier_score": 0.188, "ece": 0.042, "log_loss": 0.941},
        "training_cutoff": "2026-05-31",
    },
    "player_valuation_engine": {
        "version": "GBR_ValuationEngine_v1.0",
        "family": "GRADIENT_BOOSTED_REGRESSOR",
        "status": "MODEL_VALIDATED",
        "metrics": {"mape": 0.142, "r2_score": 0.812},
        "training_cutoff": "2026-06-30",
    },
    "tactical_fit_engine": {
        "version": "TacticalFitCalculator_v1.0",
        "family": "WEIGHTED_TACTICAL_ALIGNMENT",
        "status": "MODEL_VALIDATED",
        "metrics": {"role_coverage": 0.965},
        "training_cutoff": "2026-06-30",
    },
    "player_contribution_engine": {
        "version": "PlayerContribution_v1.2",
        "family": "ATTRIBUTION_INDEX",
        "status": "MODEL_VALIDATED",
        "metrics": {"correlation_with_points": 0.74},
        "training_cutoff": "2026-06-30",
    },
}
```

---

## 2. Model Lifecycle States

A model version transitions through strictly defined lifecycle phases:

```
[ CANDIDATE ] ──(Benchmarked & Calibrated)──► [ MODEL_VALIDATED ]
                                                     │
                                                     ├──► [ SHADOW ] (Parallel evaluation)
                                                     │
                                                     └──► [ DEPRECATED ] (Superseded or drifted)
```

1. **`CANDIDATE`**: Model under active development or training. Forbidden from production inference.
2. **`MODEL_VALIDATED`**: Validated against historical holdout data, calibrated, and officially promoted to serve live traffic.
3. **`SHADOW`**: Operates alongside the primary model for live telemetry comparison; outputs are logged but do not serve client responses.
4. **`DEPRECATED`**: Retained for historical replay auditing, but blocked from evaluating new decisions.

---

## 3. Zero Silent Fallback Policy

A foundational requirement of the Football Intelligence OS is that **no unvalidated model may be silently invoked**:
- Invoking an unregistered model name raises `ModelGovernanceError`.
- Requesting an unvalidated version raises `ModelGovernanceError` indicating the model's actual status.
- Attempting to evaluate inference when a model is deprecated raises `ModelGovernanceError`.

```python
# Enforcement in app.observability.model_governance:
def verify_inference_eligibility(self, model_name: str, version: str) -> RegisteredModel:
    model = self.get_model(model_name, version)
    if model.status != ModelStatus.MODEL_VALIDATED:
        raise ModelGovernanceError(
            f"Model {model_name}:{version} is in status {model.status.value}, "
            f"not MODEL_VALIDATED. Inference rejected."
        )
    return model
```

---

## 4. Drift & Calibration Monitoring

The governance subsystem continuously audits predictions against live match and transfer outcomes:
- **Expected Calibration Error (ECE)**: Evaluated in probability bins [0.0 - 1.0]. If empirical frequency diverges by > 8%, model status is flagged for re-calibration.
- **Population Stability Index (PSI)**: Monitors continuous feature drift in tactical and player contribution distributions. PSI > 0.25 triggers automatic alerting.
- **Brier Score Tracking**: Evaluated across rolling 50-match windows to ensure continuous probabilistic fidelity.
