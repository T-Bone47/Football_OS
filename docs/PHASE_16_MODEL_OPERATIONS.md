# Phase 16: Model Operations & SLA Monitoring

## 1. Operational SLAs
Models in production are governed by strict service-level agreements:
- **P95 Latency SLA**: $< 250$ ms for real-time inference.
- **P99 Latency SLA**: $< 500$ ms.
- **Availability Target**: $99.9\%$.
- **Maximum Drift Threshold**: PSI $\le 0.15$ or Brier score degradation $\le 0.05$.

## 2. Health & Degradation Signals
The Model Operations engine monitors four real-time operational indicators:
1. `DRIFT_DETECTED`: Population stability index exceeds threshold.
2. `OOD_SPIKE`: Unusually high proportion of out-of-distribution queries.
3. `CALIBRATION_LOSS`: Expected calibration error exceeds baseline tolerance.
4. `CHALLENGER_GAP`: Challenger demonstrates statistically significant superior accuracy in shadow mode, nominating it for governed promotion.
