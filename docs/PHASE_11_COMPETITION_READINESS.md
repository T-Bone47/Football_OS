# Phase 11 — Competition Readiness Matrix & Operational Status

## 1. Global Competition Readiness Matrix

As of Phase 11, the Football Intelligence OS manages 8 competitions across three governed tiers:

| Competition Code | League / Competition Name | Tier | Matches Available | Readiness State | Calibration Status | Active Production Model | Limitations & Epistemic Boundaries |
|:---|:---|:---:|:---:|:---:|:---:|:---|:---|
| **`GB-PL`** | English Premier League | Baseline | 760 | `PRODUCTION_READY` | `CALIBRATED` | `calibrated_multinomial_logit_v1` | Verified 2-season temporal depth; authoritative across all recruitment & match simulation tools. |
| **`ES-L1`** | Spanish La Liga | Tier 1 | 380 | `MODEL_VALIDATED` | `CALIBRATION_PENDING` | `laliga_logit_candidate_v1` (Shadow) | Shadow candidate active; local calibration pending validation review; recruitment tools display `LOW_CONFIDENCE`. |
| **`IT-SA`** | Italian Serie A | Tier 1 | 380 | `MODEL_VALIDATED` | `CALIBRATION_PENDING` | `seriea_logit_candidate_v1` (Shadow) | Shadow candidate active; tactical fit requires localized tactical system calibration. |
| **`DE-BL`** | German Bundesliga | Tier 1 | 306 | `MODEL_VALIDATED` | `CALIBRATION_PENDING` | `bundesliga_logit_candidate_v1` (Shadow) | 18-club schedule (306 matches); press-intensity feature distribution differs from EPL baseline; zero-inheritance enforced. |
| **`FR-L1`** | French Ligue 1 | Tier 1 | 306 | `MODEL_VALIDATED` | `CALIBRATION_PENDING` | `ligue1_logit_candidate_v1` (Shadow) | 18-club schedule; youth talent emergence volatility requires wider confidence bounds. |
| **`EU-CL`** | UEFA Champions League | Tier 2 | 125 | `VALIDATION_READY` | `UNCALIBRATED` | None (Evaluation Only) | Small tournament sample size ($N=125$); high inter-league opponent variance; match prediction uncalibrated. |
| **`EU-EL`** | UEFA Europa League | Tier 2 | 141 | `VALIDATION_READY` | `UNCALIBRATED` | None (Evaluation Only) | High rotation and group stage variance; insufficient domestic continuity for full production readiness. |
| **`US-MLS`** | Major League Soccer | Tier 3 | 493 | `DATA_INGESTED` | `UNCALIBRATED` | None | Initial Bronze ingestion complete; Silver entity resolution and squad feature normalization in progress; inference blocked. |

---

## 2. Recruitment Cross-Competition Safety Policy (§26)

When recruitment analysts build cross-competition candidate shortlists (e.g. comparing an EPL winger with a La Liga winger):
1. **Explicit Confidence Tagging**:
   - EPL candidate: `Confidence: HIGH`, `Status: PRODUCTION_READY`
   - La Liga candidate: `Confidence: MODERATE`, `Status: MODEL_VALIDATED (SHADOW)`
   - MLS candidate: `Confidence: INSUFFICIENT_DATA`, `Status: DATA_INGESTED`
2. **Visual & Analytical Asymmetry**: The UI explicitly disallows rendering identical certainty bars for players evaluated under unequal evidence.
3. **Exploration Permitted, Decisions Gated**: Scouts may explore, filter, and review non-EPL candidates, but system-generated contract valuation bids and risk assessments require explicit acknowledgement of foreign validation status.
