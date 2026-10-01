"""Model operations: registry, gated inference, outcomes, calibration,
drift and health (§13, §15, §19, §20, §42, §51, §52).

Inference refuses rather than guesses. In order, a request is refused with:
  MODEL_UNAVAILABLE    no servable model is registered for the domain
  TEMPORAL_VIOLATION   pre-match cutoff at/after kickoff, or a feature input
                       dated at/after the cutoff
  OUT_OF_DISTRIBUTION  competition not validated for this model, or the
                       existing OOD gate fires (extreme Elo gap, invalid rates)
  STALE_DATA           LIVE mode with Bronze older than the model's freshness
                       limit, or team features out of sync with Silver
  INSUFFICIENT_DATA    fewer prior matches than the model requires
Every request — served or refused — is an immutable ops_inference_log row.

Outcomes never edit a prediction. Whether an outcome counts as LIVE is
derived from timestamps: the prediction must have been logged before
kickoff. A prediction made after the match (a backtest) is
HISTORICAL_REPLAY, and live calibration ignores it.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Competition, CompetitionSeason, Match, Season
from app.db.models.operations import InferenceLog, ModelRegistryEntry, OutcomeRecord
from app.db.models.provenance import DataSnapshot
from app.phase17 import DriftClass, InferenceStatus, PredictionType
from app.ml.serving import ArtifactRefused, load_registered_artifact
from app.phase17.feature_refresh import feature_staleness
from app.prediction.features import FEATURE_SET_VERSION, PreMatchFeatureBuilder
from app.prediction.gating import PredictionGatingEngine
from app.prediction.models import (
    CLASS_PRIOR_AWAY,
    CLASS_PRIOR_DRAW,
    CLASS_PRIOR_HOME,
    determine_match_target,
    target_to_index,
)

MATCH_DOMAIN = "match_outcome"
MATCH_MODEL_ID = "match_outcome_logit"
MATCH_MODEL_VERSION = "2.0.0"
# Phase 18 registry vocabulary. Served to users: PRODUCTION, CANARY, SHADOW
# (labelled). Offline validation backtests may also use VALIDATED/CANDIDATE.
SERVABLE_STATES = ("PRODUCTION", "CANARY", "SHADOW")
VALIDATION_STATES = SERVABLE_STATES + ("VALIDATED", "CANDIDATE")
from app.ml.match_outcome import OOD_Z_LIMIT  # noqa: E402  (one definition for training and serving)
FINISHED = ("FINISHED", "FT", "AET", "PEN")

MIN_CALIBRATION_OUTCOMES = 100
MIN_SUBGROUP_OUTCOMES = 50
MIN_DRIFT_WINDOW = 50
PSI_MONITOR, PSI_DRIFT, PSI_CRITICAL = 0.10, 0.25, 0.50

MODE_LIVE = "LIVE"
LIVE_BACKDATE_TOLERANCE = timedelta(minutes=5)
MODE_REPLAY = "HISTORICAL_REPLAY"
MODE_VALIDATION = "VALIDATION_BACKTEST"


def competition_key(comp: Competition) -> str:
    return f"{comp.name} ({comp.country})"


async def match_context(session: AsyncSession, match_id: uuid.UUID) -> tuple[Match, Competition, Season] | None:
    row = (await session.execute(
        select(Match, Competition, Season)
        .join(CompetitionSeason, Match.competition_season_id == CompetitionSeason.id)
        .join(Competition, CompetitionSeason.competition_id == Competition.id)
        .join(Season, CompetitionSeason.season_id == Season.id)
        .where(Match.id == match_id)
    )).one_or_none()
    return tuple(row) if row else None


def _committed_manifests() -> tuple[dict[str, Any], dict[str, Any]] | None:
    from app.ml.serving import artifact_root

    d = artifact_root() / "match_outcome" / f"{MATCH_MODEL_ID}-{MATCH_MODEL_VERSION}"
    try:
        return (json.loads((d / "model_manifest.json").read_text()),
                json.loads((d / "evaluation_manifest.json").read_text()))
    except (OSError, ValueError):
        return None


async def ensure_match_model_registered(session: AsyncSession) -> ModelRegistryEntry:
    """Registers the trained, committed match model from its manifests if the
    registry does not hold it. State follows the evidence: VALIDATED only when
    the evaluation verdict is VALIDATED and dataset lineage is VERIFIED,
    otherwise BLOCKED. Never a serving state: SHADOW and above are human
    promotions. Without manifests there is nothing to register."""
    row = (await session.execute(select(ModelRegistryEntry).where(
        ModelRegistryEntry.model_id == MATCH_MODEL_ID, ModelRegistryEntry.model_version == MATCH_MODEL_VERSION
    ))).scalar_one_or_none()
    if row is not None:
        return row
    found = _committed_manifests()
    if found is None:
        raise RuntimeError("match model manifests not found; run scripts/train_match_model.py")
    manifest, evaluation = found
    validated = manifest["verdict"] == "VALIDATED" and manifest["lineage_status"] == "VERIFIED"
    row = ModelRegistryEntry(
        domain=MATCH_DOMAIN, model_id=MATCH_MODEL_ID, model_version=MATCH_MODEL_VERSION,
        feature_version=FEATURE_SET_VERSION, dataset_version=f"statsbomb-2015-16-top5@{manifest['dataset_sha256'][:12]}",
        artifact_sha256=manifest["artifact_sha256"], artifact_uri=manifest["artifact_uri"],
        dataset_sha256=manifest["dataset_sha256"], windows=evaluation["windows"],
        supported_competitions=evaluation["supported_competitions"] if validated else [],
        supported_horizons=["PRE_MATCH"], deployment_state="VALIDATED" if validated else "BLOCKED",
        validation_metrics=evaluation, lineage_status=manifest["lineage_status"],
        status_reason=f"registered from committed manifests (verdict {manifest['verdict']})",
        min_history_matches=5, max_feature_age_hours=72.0,
    )
    session.add(row)
    await session.flush()
    return row


async def servable_model(session: AsyncSession, domain: str, validation: bool = False) -> ModelRegistryEntry | None:
    states = VALIDATION_STATES if validation else SERVABLE_STATES
    rows = (await session.execute(select(ModelRegistryEntry).where(
        ModelRegistryEntry.domain == domain, ModelRegistryEntry.deployment_state.in_(states)
    ))).scalars().all()
    return sorted(rows, key=lambda r: VALIDATION_STATES.index(r.deployment_state))[0] if rows else None


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


async def infer_match(
    session: AsyncSession,
    match_id: uuid.UUID,
    as_of: datetime | None = None,
    mode: str = MODE_LIVE,
    now: datetime | None = None,
) -> InferenceLog:
    t0 = time.perf_counter()
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    ctx = await match_context(session, match_id)
    validation = mode == MODE_VALIDATION
    model = await servable_model(session, MATCH_DOMAIN, validation=validation)
    cutoff = as_of or now
    base = dict(domain=MATCH_DOMAIN, prediction_type=PredictionType.PRE_MATCH.value, subject_id=str(match_id),
                input_digest=_digest({"match_id": str(match_id), "cutoff": cutoff.isoformat(), "mode": mode}),
                data_cutoff=cutoff, output={}, features_used={}, missing_features=[], evidence={"mode": mode})

    def refuse(status: InferenceStatus, why: str, **extra: Any) -> InferenceLog:
        reasons.append(why)
        row = InferenceLog(**{**base, **extra}, status=status.value, reasons=reasons, is_ood=status == InferenceStatus.OUT_OF_DISTRIBUTION,
                           latency_ms=round((time.perf_counter() - t0) * 1000, 2))
        session.add(row)
        return row

    if ctx is None:
        row = refuse(InferenceStatus.INSUFFICIENT_DATA, f"match {match_id} not in Silver")
        await session.flush()
        return row
    match, comp, season = ctx
    comp_key = competition_key(comp)
    base["competition"] = comp_key
    if model is None:
        row = refuse(InferenceStatus.MODEL_UNAVAILABLE, f"no servable {MATCH_DOMAIN} model registered")
        await session.flush()
        return row
    base.update(model_id=model.model_id, model_version=model.model_version,
                feature_version=model.feature_version, dataset_version=model.dataset_version)
    try:
        artifact = load_registered_artifact(model)
    except ArtifactRefused as refused:
        row = refuse(InferenceStatus(refused.status), refused.reason)
        await session.flush()
        return row
    base["evidence"] = {"mode": mode, "artifact_sha256": model.artifact_sha256,
                        "deployment_state": model.deployment_state}

    if mode == MODE_LIVE and cutoff < now - LIVE_BACKDATE_TOLERANCE:
        row = refuse(InferenceStatus.TEMPORAL_VIOLATION,
                     f"LIVE requests cannot be backdated (as_of {cutoff.isoformat()}); use HISTORICAL_REPLAY")
        await session.flush()
        return row
    if cutoff >= match.date:
        row = refuse(InferenceStatus.TEMPORAL_VIOLATION,
                     f"pre-match cutoff {cutoff.isoformat()} is not before kickoff {match.date.isoformat()}")
        await session.flush()
        return row
    if not validation and comp_key not in (model.supported_competitions or []):
        row = refuse(InferenceStatus.OUT_OF_DISTRIBUTION,
                     f"{comp_key} has no validation evidence for {model.model_id}; competitions do not inherit support")
        await session.flush()
        return row

    if mode == MODE_LIVE and model.max_feature_age_hours is not None:
        latest = (await session.execute(
            select(DataSnapshot.provider_retrieved_at, DataSnapshot.sha256)
            .join(Match, Match.snapshot_id == DataSnapshot.id).where(Match.id == match.id))).one_or_none()
        retrieved = latest[0] if latest else None
        source_age_h = (now - retrieved).total_seconds() / 3600 if retrieved else None
        if source_age_h is None or source_age_h > model.max_feature_age_hours:
            row = refuse(InferenceStatus.STALE_DATA,
                         f"fixture snapshot retrieved {source_age_h and round(source_age_h, 1)} h ago "
                         f"(limit {model.max_feature_age_hours} h)")
            await session.flush()
            return row

    for club in (match.home_club_id, match.away_club_id):
        st = await feature_staleness(session, club, match.competition_season_id)
        if st["state"] != "FRESH":
            row = refuse(InferenceStatus.STALE_DATA, f"feature team_form_v1 {st['state']} for {st['entity_id']}",
                         evidence={"mode": mode, "feature_staleness": st})
            await session.flush()
            return row

    history = list((await session.execute(
        select(Match).where(Match.date < cutoff, Match.id != match.id, Match.status.in_(FINISHED),
                            or_(Match.home_club_id.in_([match.home_club_id, match.away_club_id]),
                                Match.away_club_id.in_([match.home_club_id, match.away_club_id])))
        .order_by(Match.date.asc())
    )).scalars().all())
    if any(h.date >= cutoff for h in history):
        row = refuse(InferenceStatus.TEMPORAL_VIOLATION, "history contains a match at/after the cutoff")
        await session.flush()
        return row

    snapshot = PreMatchFeatureBuilder().build_features(
        match_id=match.id, home_club_id=match.home_club_id, away_club_id=match.away_club_id,
        kickoff_time=match.date, historical_matches=history, as_of=cutoff,
        competition_id=match.competition_season_id,
    )
    features = {k: v for k, v in snapshot.features.items()}
    missing = sorted(k for k, v in features.items() if v is None)
    base.update(features_used=features, missing_features=missing)
    evidence = {"mode": mode, "history_match_ids": [str(h.id) for h in history],
                "history_max_date": history[-1].date.isoformat() if history else None,
                "home_sample": snapshot.home_sample_size, "away_sample": snapshot.away_sample_size}
    base["evidence"] = {**base["evidence"], **evidence}
    if min(snapshot.home_sample_size, snapshot.away_sample_size) < model.min_history_matches:
        row = refuse(InferenceStatus.INSUFFICIENT_DATA,
                     f"history {snapshot.home_sample_size}/{snapshot.away_sample_size} matches "
                     f"< required {model.min_history_matches}")
        await session.flush()
        return row

    gate = PredictionGatingEngine().evaluate(snapshot.features, snapshot.home_sample_size,
                                            snapshot.away_sample_size, snapshot.h2h_sample_size)
    if gate.status == "OUT_OF_DISTRIBUTION":
        for r in gate.reasons:
            reasons.append(r)
        row = refuse(InferenceStatus.OUT_OF_DISTRIBUTION, "feature-level OOD gate fired")
        await session.flush()
        return row

    from app.ml import match_outcome as mo

    x = mo.features_vector(artifact, snapshot.features)
    if x is None:
        missing_model = [f for f in artifact["features"] if snapshot.features.get(f) is None]
        row = refuse(InferenceStatus.INSUFFICIENT_DATA, f"model features unavailable: {', '.join(missing_model)}")
        await session.flush()
        return row
    z = (x[0] - artifact["mean"]) / artifact["scale"]
    far = [f"{f} (z={zi:+.1f})" for f, zi in zip(artifact["features"], z) if abs(zi) > OOD_Z_LIMIT]
    if far:
        row = refuse(InferenceStatus.OUT_OF_DISTRIBUTION,
                     f"outside the training distribution (|z| > {OOD_Z_LIMIT}): {', '.join(far)}")
        await session.flush()
        return row
    p = mo.predict_proba(artifact, x)[0]
    probs = {"home_win": round(float(p[0]), 6), "draw": round(float(p[1]), 6), "away_win": round(float(p[2]), 6)}
    top = int(p.argmax())
    contributions = sorted(((f, float(artifact["coef"][top][j]) * float(z[j])) for j, f in enumerate(artifact["features"])),
                           key=lambda kv: -abs(kv[1]))
    reasons.extend(gate.reasons)
    base["output"] = {**probs, "gate": gate.status, "kickoff": match.date.isoformat(), "modality": "MODELLED",
                      "deployment_state": model.deployment_state,
                      "explanation": {"predicted_class": mo.CLASSES[top],
                                      "logit_contributions": [{"feature": f, "contribution": round(c, 4)}
                                                              for f, c in contributions],
                                      "method": "coefficient x standardised feature (non-causal)"}}
    row = InferenceLog(
        **base, status=InferenceStatus.SERVED.value, reasons=reasons, is_ood=False,
        confidence=max(probs.values()),
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
    )
    session.add(row)
    await session.flush()
    return row


async def record_outcome(session: AsyncSession, inference: InferenceLog) -> OutcomeRecord | None:
    """Links a served prediction to its real result. Returns None until the
    match is FINISHED in Silver. Never modifies `inference`."""
    if inference.status != InferenceStatus.SERVED.value:
        return None
    existing = (await session.execute(select(OutcomeRecord).where(OutcomeRecord.inference_id == inference.id))).scalar_one_or_none()
    if existing:
        return existing
    match = await session.get(Match, uuid.UUID(inference.subject_id))
    if match is None or match.status not in FINISHED or match.home_score is None:
        return None
    target = determine_match_target(match.home_score, match.away_score)
    y = target_to_index(target)
    p = [inference.output["home_win"], inference.output["draw"], inference.output["away_win"]]
    snap = await session.get(DataSnapshot, match.snapshot_id) if match.snapshot_id else None
    created = inference.created_at or datetime.now(timezone.utc)
    observation = MODE_LIVE if created < match.date else MODE_REPLAY
    row = OutcomeRecord(
        inference_id=inference.id, realized={"result": target, "home_score": match.home_score, "away_score": match.away_score},
        outcome_source=f"silver.matches:{match.provider}:{match.provider_fixture_id}",
        outcome_snapshot_sha256=snap.sha256 if snap else None, observation_mode=observation,
        observed_at=match.updated_at or datetime.now(timezone.utc),
        evaluation={"log_loss": round(-math.log(max(p[y], 1e-15)), 6),
                    "brier": round(sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3)), 6),
                    "correct": int(max(range(3), key=lambda k: p[k]) == y)},
    )
    session.add(row)
    await session.flush()
    return row


def calibration_metrics(probs: list[list[float]], ys: list[int], n_bins: int = 10) -> dict[str, Any]:
    n = len(ys)
    log_loss = sum(-math.log(max(p[y], 1e-15)) for p, y in zip(probs, ys)) / n
    brier = sum(sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3)) for p, y in zip(probs, ys)) / n
    bins: list[dict[str, Any]] = []
    ece = mce = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, p in enumerate(probs) if lo <= max(p) < hi or (b == n_bins - 1 and max(p) == 1.0)]
        if not idx:
            continue
        conf = sum(max(probs[i]) for i in idx) / len(idx)
        acc = sum(1 for i in idx if max(range(3), key=lambda k: probs[i][k]) == ys[i]) / len(idx)
        gap = abs(acc - conf)
        ece += len(idx) / n * gap
        mce = max(mce, gap)
        bins.append({"bin": [round(lo, 2), round(hi, 2)], "n": len(idx), "mean_confidence": round(conf, 4),
                     "accuracy": round(acc, 4)})
    prior = [CLASS_PRIOR_HOME, CLASS_PRIOR_DRAW, CLASS_PRIOR_AWAY]
    baseline_ll = sum(-math.log(prior[y]) for y in ys) / n
    return {"n": n, "log_loss": round(log_loss, 4), "brier": round(brier, 4), "ece": round(ece, 4),
            "mce": round(mce, 4), "accuracy": round(sum(1 for p, y in zip(probs, ys)
                                                        if max(range(3), key=lambda k: p[k]) == y) / n, 4),
            "baseline_class_prior_log_loss": round(baseline_ll, 4),
            "beats_class_prior_baseline": log_loss < baseline_ll, "calibration_curve": bins}


async def _outcome_rows(session: AsyncSession, observation_mode: str | None, domain: str = MATCH_DOMAIN,
                        model_id: str | None = None) -> list[tuple[InferenceLog, OutcomeRecord]]:
    stmt = select(InferenceLog, OutcomeRecord).join(OutcomeRecord, OutcomeRecord.inference_id == InferenceLog.id) \
        .where(InferenceLog.domain == domain)
    if observation_mode:
        stmt = stmt.where(OutcomeRecord.observation_mode == observation_mode)
    if model_id:
        stmt = stmt.where(InferenceLog.model_id == model_id)
    return list((await session.execute(stmt)).all())


async def calibration_report(session: AsyncSession, observation_mode: str, model_id: str | None = None,
                             evidence_mode: str | None = None) -> dict[str, Any]:
    rows = await _outcome_rows(session, observation_mode, model_id=model_id)
    if evidence_mode:
        rows = [r for r in rows if (r[0].evidence or {}).get("mode") == evidence_mode]
    label = "NOT_ENOUGH_LIVE_OUTCOMES" if observation_mode == MODE_LIVE else "NOT_ENOUGH_OUTCOMES"
    if len(rows) < MIN_CALIBRATION_OUTCOMES:
        return {"status": label, "observation_mode": observation_mode, "n": len(rows),
                "minimum_required": MIN_CALIBRATION_OUTCOMES}
    probs = [[i.output["home_win"], i.output["draw"], i.output["away_win"]] for i, _ in rows]
    ys = [target_to_index(o.realized["result"]) for _, o in rows]
    overall = calibration_metrics(probs, ys)
    subgroups: dict[str, Any] = {}
    by_comp: dict[str, list[int]] = {}
    for idx, (i, _) in enumerate(rows):
        by_comp.setdefault(i.competition or "UNKNOWN", []).append(idx)
    for comp, idxs in by_comp.items():
        if len(idxs) < MIN_SUBGROUP_OUTCOMES:
            subgroups[comp] = {"status": "NOT_ENOUGH_OUTCOMES", "n": len(idxs), "minimum_required": MIN_SUBGROUP_OUTCOMES}
        else:
            m = calibration_metrics([probs[k] for k in idxs], [ys[k] for k in idxs])
            m.pop("calibration_curve")
            subgroups[comp] = m
    return {"status": "MEASURED", "observation_mode": observation_mode, **overall, "subgroups": subgroups}


def psi(reference: list[float], current: list[float], bins: int = 10) -> float:
    lo, hi = min(reference + current), max(reference + current)
    if hi == lo:
        return 0.0
    def dist(xs: list[float]) -> list[float]:
        counts = [0] * bins
        for x in xs:
            k = min(bins - 1, int((x - lo) / (hi - lo) * bins))
            counts[k] += 1
        return [max(c / len(xs), 1e-4) for c in counts]

    r, c = dist(reference), dist(current)
    return round(sum((ci - ri) * math.log(ci / ri) for ri, ci in zip(r, c)), 4)


def classify_psi(value: float) -> DriftClass:
    if value >= PSI_CRITICAL:
        return DriftClass.CRITICAL_DRIFT
    if value >= PSI_DRIFT:
        return DriftClass.DRIFT
    if value >= PSI_MONITOR:
        return DriftClass.MONITOR
    return DriftClass.STABLE


DRIFT_FEATURES = ("elo_diff", "points_diff_l5", "home_goal_diff_l5", "away_goal_diff_l5")


async def drift_report(session: AsyncSession, evidence_mode: str, domain: str = MATCH_DOMAIN) -> dict[str, Any]:
    """Splits served inferences of one evidence mode at the median kickoff
    into reference and current windows and computes PSI per feature and on
    prediction confidence. Never retrains; DRIFT routes to RETRAIN_RECOMMENDED."""
    rows = (await session.execute(select(InferenceLog).where(
        InferenceLog.domain == domain, InferenceLog.status == InferenceStatus.SERVED.value))).scalars().all()
    rows = sorted([r for r in rows if (r.evidence or {}).get("mode") == evidence_mode],
                  key=lambda r: r.output.get("kickoff", ""))
    half = len(rows) // 2
    ref, cur = rows[:half], rows[half:]
    if min(len(ref), len(cur)) < MIN_DRIFT_WINDOW:
        return {"status": DriftClass.NOT_ENOUGH_OBSERVATIONS.value, "evidence_mode": evidence_mode,
                "reference_n": len(ref), "current_n": len(cur), "minimum_per_window": MIN_DRIFT_WINDOW,
                "retrain_recommended": False}
    per_feature = {}
    for f in DRIFT_FEATURES:
        a = [r.features_used[f] for r in ref if r.features_used.get(f) is not None]
        b = [r.features_used[f] for r in cur if r.features_used.get(f) is not None]
        if min(len(a), len(b)) < MIN_DRIFT_WINDOW:
            per_feature[f] = {"status": DriftClass.NOT_ENOUGH_OBSERVATIONS.value, "n": [len(a), len(b)]}
        else:
            v = psi(a, b)
            per_feature[f] = {"psi": v, "class": classify_psi(v).value}
    conf_psi = psi([r.confidence for r in ref], [r.confidence for r in cur])
    classes = [classify_psi(v["psi"]) for v in per_feature.values() if "psi" in v] + [classify_psi(conf_psi)]
    order = [DriftClass.STABLE, DriftClass.MONITOR, DriftClass.DRIFT, DriftClass.CRITICAL_DRIFT]
    worst = max(classes, key=order.index)
    return {"status": worst.value, "evidence_mode": evidence_mode,
            "reference_window": [ref[0].output.get("kickoff"), ref[-1].output.get("kickoff")],
            "current_window": [cur[0].output.get("kickoff"), cur[-1].output.get("kickoff")],
            "reference_n": len(ref), "current_n": len(cur), "features": per_feature,
            "confidence_psi": {"psi": conf_psi, "class": classify_psi(conf_psi).value},
            "retrain_recommended": worst in (DriftClass.DRIFT, DriftClass.CRITICAL_DRIFT),
            "action": "RETRAIN_RECOMMENDED -> governed challenger workflow (no automatic retraining)"
            if worst in (DriftClass.DRIFT, DriftClass.CRITICAL_DRIFT) else "NONE"}


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return round(s[f] + (s[c] - s[f]) * (k - f), 3)


async def model_health_snapshot(session: AsyncSession, domain: str = MATCH_DOMAIN,
                                since: datetime | None = None) -> dict[str, Any]:
    """LiveModelHealthSnapshot (§19), computed from the inference log only."""
    stmt = select(InferenceLog).where(InferenceLog.domain == domain)
    if since:
        stmt = stmt.where(InferenceLog.created_at >= since)
    rows = (await session.execute(stmt)).scalars().all()
    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        mode = (r.evidence or {}).get("mode", "UNKNOWN")
        by_mode[mode] = by_mode.get(mode, 0) + 1
    served = [r for r in rows if r.status == InferenceStatus.SERVED.value]
    lat = [r.latency_ms for r in rows]
    conf = [r.confidence for r in served if r.confidence is not None]
    hist = [0] * 10
    for c in conf:
        hist[min(9, int(c * 10))] += 1
    n = len(rows)
    live_cal = await calibration_report(session, MODE_LIVE)
    return {
        "domain": domain, "computed_at": datetime.now(timezone.utc).isoformat(),
        "inference_volume": n, "by_status": by_status, "by_evidence_mode": by_mode,
        "live_inference_volume": by_mode.get(MODE_LIVE, 0),
        "refusal_rate": round(1 - len(served) / n, 4) if n else None,
        "ood_rate": round(sum(1 for r in rows if r.is_ood) / n, 4) if n else None,
        "missing_feature_rate": round(sum(1 for r in served if r.missing_features) / len(served), 4) if served else None,
        "latency_ms": {"p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95), "p99": _percentile(lat, 0.99)},
        "confidence_histogram": {f"{k / 10:.1f}-{(k + 1) / 10:.1f}": v for k, v in enumerate(hist)} if conf else None,
        "live_calibration": live_cal,
        "status": "NOT_ENOUGH_OBSERVATIONS" if n == 0 else "MEASURED",
    }


async def historical_backtest(session: AsyncSession, competition_season_id: uuid.UUID) -> dict[str, Any]:
    """Walk-forward validation on real Silver results: each match predicted
    with a cutoff one second before kickoff, using only earlier matches.
    Logged as VALIDATION_BACKTEST; outcomes are HISTORICAL_REPLAY by
    construction (logged after the match)."""
    matches = (await session.execute(select(Match).where(
        Match.competition_season_id == competition_season_id, Match.status.in_(FINISHED)
    ).order_by(Match.date.asc()))).scalars().all()
    statuses: dict[str, int] = {}
    outcomes = 0
    for m in matches:
        inf = await infer_match(session, m.id, as_of=m.date - timedelta(seconds=1), mode=MODE_VALIDATION)
        statuses[inf.status] = statuses.get(inf.status, 0) + 1
        if await record_outcome(session, inf) is not None:
            outcomes += 1
    await session.commit()
    return {"competition_season_id": str(competition_season_id), "matches": len(matches),
            "inference_statuses": statuses, "outcomes_linked": outcomes}


async def validate_competition_support(session: AsyncSession, competition: str) -> dict[str, Any]:
    """Adds `competition` to the model's supported list only when its own
    backtest has enough outcomes and beats the class-prior baseline. The
    model's deployment state never rises above SHADOW here: ACTIVE needs
    live outcomes and a human promotion."""
    model = await ensure_match_model_registered(session)
    rows = [r for r in await _outcome_rows(session, MODE_REPLAY, model_id=model.model_id)
            if r[0].competition == competition and (r[0].evidence or {}).get("mode") == MODE_VALIDATION]
    if len(rows) < MIN_SUBGROUP_OUTCOMES:
        verdict = {"competition": competition, "status": "NOT_ENOUGH_OUTCOMES", "n": len(rows),
                   "minimum_required": MIN_SUBGROUP_OUTCOMES}
    else:
        probs = [[i.output["home_win"], i.output["draw"], i.output["away_win"]] for i, _ in rows]
        ys = [target_to_index(o.realized["result"]) for _, o in rows]
        m = calibration_metrics(probs, ys)
        verdict = {"competition": competition, "status": "MODEL_VALIDATED" if m["beats_class_prior_baseline"]
                   else "VALIDATION_FAILED", **{k: v for k, v in m.items() if k != "calibration_curve"}}
    metrics = dict(model.validation_metrics or {})
    metrics[competition] = verdict
    model.validation_metrics = metrics
    supported = list(model.supported_competitions or [])
    if verdict["status"] == "MODEL_VALIDATED" and competition not in supported:
        supported.append(competition)
    elif verdict["status"] != "MODEL_VALIDATED" and competition in supported:
        supported.remove(competition)
    model.supported_competitions = supported
    # Phase 18: support follows evidence; the deployment state never changes
    # here. Every promotion (VALIDATED -> SHADOW -> CANARY -> PRODUCTION) is human.
    await session.commit()
    return verdict
