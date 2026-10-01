"""Match outcome model: reproducible dataset, training, artifact and evaluation.

Phase 18 (R8, R18, R20). The previous "trained" model was five hand-typed
weights with no artifact and no training code. This module is the whole
lifecycle, deterministic end to end:

    Silver matches -> pre-match features (history strictly before kickoff)
    -> dataset (stable provider ids, canonical JSON, SHA-256)
    -> chronological train / validation / test windows
    -> standardised multinomial logistic regression (lbfgs, fixed seed)
    -> temperature fitted on the validation window only
    -> canonical JSON artifact (SHA-256)
    -> test metrics against a class-prior baseline, overall and per competition

Rows whose features cannot be computed are excluded and counted, never
imputed. A competition is supported only if its own test slice beats its own
baseline; nothing is inherited.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from app.prediction.features import FEATURE_SET_VERSION, PreMatchFeatureBuilder

MODEL_ID = "match_outcome_logit"
MODEL_VERSION = "2.0.0"
DOMAIN = "match_outcome"
FEATURES = ["elo_diff", "points_diff_l5", "home_goal_diff_l5", "away_goal_diff_l5",
            "home_venue_points_l5", "away_venue_points_l5", "rest_days_diff"]
CLASSES = ["H", "D", "A"]
MIN_HISTORY = 5
FINISHED = ("FINISHED", "FT", "AET", "PEN")
DECIMALS = 8
RANDOM_SEED = 20151  # recorded; lbfgs is deterministic, the seed guards any stochastic path
C_REGULARISATION = 1.0
TEMPERATURE_GRID = [round(0.50 + 0.01 * i, 2) for i in range(151)]  # 0.50 .. 2.00
MIN_TEST_ROWS = 300
MIN_COMPETITION_TEST_ROWS = 50
OOD_Z_LIMIT = 4.0  # serving refuses a feature more than 4 training SDs from the training mean


@dataclass(frozen=True)
class Windows:
    train_end: str = "2016-02-01"       # train: kickoff < train_end
    validation_end: str = "2016-04-01"  # validation: train_end <= kickoff < validation_end; test: after


@dataclass
class DatasetRow:
    provider: str
    provider_fixture_id: str
    kickoff: str
    competition: str
    features: dict[str, float]
    label: str


@dataclass
class Dataset:
    rows: list[DatasetRow]
    excluded: dict[str, int] = field(default_factory=dict)

    def canonical_lines(self) -> list[bytes]:
        return [canonical({"provider": r.provider, "fixture": r.provider_fixture_id, "kickoff": r.kickoff,
                           "competition": r.competition, "features": r.features, "label": r.label})
                for r in self.rows]

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        for line in self.canonical_lines():
            h.update(line + b"\n")
        return h.hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _r(x: float) -> float:
    return float(round(float(x), DECIMALS))


def _label(home: int, away: int) -> str:
    return "H" if home > away else "A" if home < away else "D"


def build_dataset(matches: Iterable[Any], competition_of: dict[Any, str]) -> Dataset:
    """`matches`: Silver Match rows (any competition). `competition_of` maps a
    competition_season_id to a competition key for rows that belong to the
    dataset scope. History for each team is every finished match strictly
    before the kickoff being described."""
    finished = sorted((m for m in matches if m.status in FINISHED and m.home_score is not None
                       and m.away_score is not None), key=lambda m: (m.date, str(m.provider_fixture_id)))
    builder = PreMatchFeatureBuilder()
    by_club: dict[Any, list[Any]] = {}
    rows: list[DatasetRow] = []
    excluded = {"insufficient_history": 0, "missing_feature": 0}
    for m in finished:
        comp = competition_of.get(m.competition_season_id)
        if comp is not None:
            hist = sorted({id(x): x for x in by_club.get(m.home_club_id, []) + by_club.get(m.away_club_id, [])}.values(),
                          key=lambda x: x.date)
            hist = [h for h in hist if h.date < m.date]
            snap = builder.build_features(match_id=m.id, home_club_id=m.home_club_id, away_club_id=m.away_club_id,
                                          kickoff_time=m.date, historical_matches=hist, as_of=m.date,
                                          competition_id=m.competition_season_id)
            if min(snap.home_sample_size, snap.away_sample_size) < MIN_HISTORY:
                excluded["insufficient_history"] += 1
            elif any(snap.features.get(f) is None for f in FEATURES):
                excluded["missing_feature"] += 1
            else:
                rows.append(DatasetRow(provider=m.provider, provider_fixture_id=str(m.provider_fixture_id),
                                       kickoff=m.date.astimezone(timezone.utc).isoformat(), competition=comp,
                                       features={f: _r(snap.features[f]) for f in FEATURES},
                                       label=_label(m.home_score, m.away_score)))
        by_club.setdefault(m.home_club_id, []).append(m)
        by_club.setdefault(m.away_club_id, []).append(m)
    return Dataset(rows=rows, excluded=excluded)


def split(ds: Dataset, w: Windows) -> dict[str, list[DatasetRow]]:
    out: dict[str, list[DatasetRow]] = {"train": [], "validation": [], "test": []}
    for r in ds.rows:
        day = r.kickoff[:10]
        key = "train" if day < w.train_end else "validation" if day < w.validation_end else "test"
        out[key].append(r)
    return out


def _xy(rows: list[DatasetRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features[f] for f in FEATURES] for r in rows], dtype=float)
    y = np.array([CLASSES.index(r.label) for r in rows], dtype=int)
    return x, y


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def logits(artifact: dict[str, Any], x: np.ndarray) -> np.ndarray:
    mean, scale = np.array(artifact["mean"]), np.array(artifact["scale"])
    coef, intercept = np.array(artifact["coef"]), np.array(artifact["intercept"])
    return ((x - mean) / scale) @ coef.T + intercept


def predict_proba(artifact: dict[str, Any], x: np.ndarray) -> np.ndarray:
    return _softmax(logits(artifact, x) / artifact["temperature"])


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-15
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], eps, 1.0))))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    onehot = np.eye(len(CLASSES))[y]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = p.max(axis=1), p.argmax(axis=1)
    total, err = len(y), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            err += mask.sum() / total * abs(float((pred[mask] == y[mask]).mean()) - float(conf[mask].mean()))
    return float(err)


BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 7


def paired_bootstrap_ci(p: np.ndarray, q: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """95% CI of mean(log loss of p) - mean(log loss of q) over matches,
    resampling matches with replacement (fixed seed, deterministic)."""
    eps = 1e-15
    lp = -np.log(np.clip(p[np.arange(len(y)), y], eps, 1.0))
    lq = -np.log(np.clip(q[np.arange(len(y)), y], eps, 1.0))
    d = lp - lq
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    idx = rng.integers(0, len(d), size=(BOOTSTRAP_RESAMPLES, len(d)))
    means = d[idx].mean(axis=1)
    return {"mean_difference": _r(float(d.mean())), "ci95_low": _r(float(np.percentile(means, 2.5))),
            "ci95_high": _r(float(np.percentile(means, 97.5))), "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED}


def metrics(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    return {"n": int(len(y)), "log_loss": _r(log_loss(p, y)), "brier": _r(brier(p, y)),
            "accuracy": _r(float((p.argmax(axis=1) == y).mean())), "ece": _r(ece(p, y))}


def train(ds: Dataset, w: Windows) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (artifact, evaluation). Deterministic for a given dataset."""
    from sklearn.linear_model import LogisticRegression

    parts = split(ds, w)
    xtr, ytr = _xy(parts["train"])
    xva, yva = _xy(parts["validation"])
    xte, yte = _xy(parts["test"])
    mean = xtr.mean(axis=0)
    scale = xtr.std(axis=0)
    scale[scale == 0] = 1.0
    clf = LogisticRegression(C=C_REGULARISATION, max_iter=2000, solver="lbfgs", random_state=RANDOM_SEED)
    clf.fit((xtr - mean) / scale, ytr)
    artifact = {
        "model_id": MODEL_ID, "model_version": MODEL_VERSION, "domain": DOMAIN,
        "feature_set_version": FEATURE_SET_VERSION, "features": FEATURES, "classes": CLASSES,
        "mean": [_r(v) for v in mean], "scale": [_r(v) for v in scale],
        "coef": [[_r(v) for v in row] for row in clf.coef_], "intercept": [_r(v) for v in clf.intercept_],
        "temperature": 1.0, "min_history_matches": MIN_HISTORY,
    }
    # temperature: fitted on the validation window only (never on test)
    best_t, best_ll = 1.0, math.inf
    for t in TEMPERATURE_GRID:
        artifact["temperature"] = t
        ll = log_loss(predict_proba(artifact, xva), yva)
        if ll < best_ll - 1e-12:
            best_t, best_ll = t, ll
    artifact["temperature"] = best_t

    prior = np.bincount(ytr, minlength=len(CLASSES)) / len(ytr)
    prior_p = lambda n: np.tile(prior, (n, 1))  # noqa: E731
    test_p = predict_proba(artifact, xte)
    overall = {"model": metrics(test_p, yte), "baseline_class_prior": metrics(prior_p(len(yte)), yte),
               "log_loss_difference_vs_baseline": paired_bootstrap_ci(test_p, prior_p(len(yte)), yte)}
    per_comp: dict[str, Any] = {}
    for comp in sorted({r.competition for r in parts["test"]}):
        idx = np.array([i for i, r in enumerate(parts["test"]) if r.competition == comp])
        m, b = metrics(test_p[idx], yte[idx]), metrics(prior_p(len(idx)), yte[idx])
        ci = paired_bootstrap_ci(test_p[idx], prior_p(len(idx)), yte[idx])
        supported = m["n"] >= MIN_COMPETITION_TEST_ROWS and ci["ci95_high"] < 0
        per_comp[comp] = {"model": m, "baseline_class_prior": b, "log_loss_difference_vs_baseline": ci,
                          "supported": supported,
                          "reason": "beats its own baseline (95% CI below zero)" if supported else
                          ("too few test matches" if m["n"] < MIN_COMPETITION_TEST_ROWS
                           else "improvement over its own baseline not established (95% CI reaches zero)")}
    # Validated only when the whole 95% CI of the log-loss difference is below zero.
    beats = overall["log_loss_difference_vs_baseline"]["ci95_high"] < 0
    # The same OOD gate serving applies: metrics on the subset it would answer.
    z = (xte - np.array(artifact["mean"])) / np.array(artifact["scale"])
    in_dist = np.abs(z).max(axis=1) <= OOD_Z_LIMIT
    overall["served_subset"] = {"refused_ood": int((~in_dist).sum()),
                                "model": metrics(test_p[in_dist], yte[in_dist]),
                                "baseline_class_prior": metrics(prior_p(int(in_dist.sum())), yte[in_dist])}
    verdict = ("VALIDATED" if beats and len(yte) >= MIN_TEST_ROWS else
               "VALIDATION_FAILED" if len(yte) >= MIN_TEST_ROWS else "INSUFFICIENT_TEST_DATA")
    evaluation = {
        "windows": {"train": f"< {w.train_end}", "validation": f"[{w.train_end}, {w.validation_end})",
                    "test": f">= {w.validation_end}"},
        "rows": {k: len(v) for k, v in parts.items()},
        "class_prior_from_train": {c: _r(v) for c, v in zip(CLASSES, prior)},
        "validation_log_loss_at_fitted_temperature": _r(best_ll),
        "test": overall, "per_competition": per_comp, "verdict": verdict,
        "supported_competitions": sorted(c for c, v in per_comp.items() if v["supported"]) if verdict == "VALIDATED" else [],
    }
    return artifact, evaluation


def artifact_bytes(artifact: dict[str, Any]) -> bytes:
    return canonical(artifact)


def artifact_sha256(artifact: dict[str, Any]) -> str:
    return hashlib.sha256(artifact_bytes(artifact)).hexdigest()


def features_vector(artifact: dict[str, Any], features: dict[str, Any]) -> np.ndarray | None:
    """Feature vector in the artifact's order, or None if any is missing."""
    vals = [features.get(f) for f in artifact["features"]]
    if any(v is None for v in vals):
        return None
    return np.array([vals], dtype=float)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dataset_from_jsonl(data: bytes) -> Dataset:
    """Rebuilds a Dataset from the committed canonical dataset file."""
    rows = []
    for line in data.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append(DatasetRow(provider=r["provider"], provider_fixture_id=r["fixture"], kickoff=r["kickoff"],
                               competition=r["competition"], features=r["features"], label=r["label"]))
    return Dataset(rows=rows)
