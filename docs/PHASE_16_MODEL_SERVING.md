# Phase 16: Model Serving & Version Pinning

## 1. 4-Version Metadata Pinning
Every inference produced by the Model Serving Layer pins four distinct version identifiers to ensure exact reproducibility:
1. `model_version`: Semantic version of the trained model weights.
2. `feature_version`: Exact feature definition schema used to construct inputs.
3. `dataset_version`: Snapshot identifier of the training and calibration dataset.
4. `calculation_version`: Code engine release version executing the inference.

## 2. Champion / Challenger Topology
- **Active Champion**: Serves real-time decisions, valuation estimates, and recruitment recommendations.
- **Shadow Challenger**: Executes alongside the champion on live production traffic with isolated side effects. Latency, predictions, and calibration drift are monitored without impacting decisions.
- **Canary Promotion**: Model promotion requires `ADMIN` authorization. Promoted models run canary evaluations before being pinned as champion.

## 3. Out-Of-Distribution (OOD) Governance
- Predictions check input features against competition and positional distribution boundaries.
- When an OOD query is detected (e.g. querying an uncalibrated league), the response explicitly flags `is_ood = True` and sets `data_status = "OUT_OF_DISTRIBUTION"` with epistemic safety warnings.
