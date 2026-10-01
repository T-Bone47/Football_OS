"""Pure deterministic calculation engine for Player Contribution profiles (Phase 3.1E/F/G).
Provides rate-normalized, position-aware contribution metrics with explicit confidence gates.
"""
from __future__ import annotations

import math
from typing import Any

from app.contributions.schemas import ContributionDimensionItem


# Benchmark baseline rates per 90 by broad position group for relative scaling
POSITION_BENCHMARKS = {
    "GK": {
        "passes_p90": 25.0,
        "pass_acc": 65.0,
        "saves_p90": 3.0,
        "clean_sheet_rate": 0.30,
        "def_actions_p90": 1.0,
    },
    "DEF": {
        "passes_p90": 45.0,
        "pass_acc": 82.0,
        "tackles_p90": 2.0,
        "interceptions_p90": 1.5,
        "blocks_p90": 0.8,
        "duels_won_p90": 3.5,
        "duel_win_rate": 55.0,
        "key_passes_p90": 0.3,
    },
    "MID": {
        "passes_p90": 50.0,
        "pass_acc": 84.0,
        "key_passes_p90": 1.2,
        "tackles_p90": 1.8,
        "interceptions_p90": 1.2,
        "duels_won_p90": 4.0,
        "dribbles_succ_p90": 1.2,
        "shots_p90": 1.2,
    },
    "ATT": {
        "shots_p90": 2.5,
        "shots_on_target_p90": 1.1,
        "goals_p90": 0.35,
        "key_passes_p90": 1.4,
        "dribbles_succ_p90": 1.8,
        "duels_won_p90": 3.0,
        "passes_p90": 28.0,
    },
}


def _clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))


def determine_confidence(minutes: int, matches: int) -> tuple[str, str]:
    """Evaluates measurable sample evidence to assign confidence and status.
    Strictly gates insufficient samples (<270 mins).
    """
    if minutes <= 0 or matches <= 0:
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
    if minutes < 270:
        return "INSUFFICIENT_SAMPLE", "INSUFFICIENT_SAMPLE"
    if minutes < 600:
        return "LOW", "EVALUATED"
    if minutes < 900:
        return "MEDIUM", "EVALUATED"
    return "HIGH", "EVALUATED"


def compute_player_contribution_metrics(
    stats_list: list[Any],
    position_group: str,
) -> dict[str, Any]:
    """Computes rate-normalized metrics and position-aware contribution dimensions.
    Pure function — produces no side effects or mutations.
    """
    pos_group = position_group.upper() if position_group else "MID"
    if pos_group not in POSITION_BENCHMARKS:
        pos_group = "MID"

    total_matches = len(stats_list)
    total_minutes = sum(s.minutes or 0 for s in stats_list)

    confidence, status = determine_confidence(total_minutes, total_matches)

    # Accumulate raw totals
    raw_sums: dict[str, float] = {
        "minutes": float(total_minutes),
        "matches": float(total_matches),
        "goals": 0.0,
        "assists": 0.0,
        "shots_total": 0.0,
        "shots_on_target": 0.0,
        "passes_total": 0.0,
        "passes_key": 0.0,
        "tackles_total": 0.0,
        "interceptions": 0.0,
        "blocks": 0.0,
        "duels_total": 0.0,
        "duels_won": 0.0,
        "dribbles_attempts": 0.0,
        "dribbles_success": 0.0,
        "fouls_committed": 0.0,
        "fouls_drawn": 0.0,
        "saves": 0.0,
        "goals_conceded": 0.0,
    }

    acc_sum = 0.0
    acc_count = 0

    for s in stats_list:
        raw_sums["goals"] += s.goals or 0
        raw_sums["assists"] += s.assists or 0
        raw_sums["shots_total"] += s.shots_total or 0
        raw_sums["shots_on_target"] += s.shots_on_target or 0
        raw_sums["passes_total"] += s.passes_total or 0
        raw_sums["passes_key"] += s.passes_key or 0
        raw_sums["tackles_total"] += s.tackles_total or 0
        raw_sums["interceptions"] += s.interceptions or 0
        raw_sums["blocks"] += s.blocks or 0
        raw_sums["duels_total"] += s.duels_total or 0
        raw_sums["duels_won"] += s.duels_won or 0
        raw_sums["dribbles_attempts"] += s.dribbles_attempts or 0
        raw_sums["dribbles_success"] += s.dribbles_success or 0
        raw_sums["fouls_committed"] += s.fouls_committed or 0
        raw_sums["fouls_drawn"] += s.fouls_drawn or 0
        raw_sums["saves"] += s.saves or 0
        raw_sums["goals_conceded"] += s.goals_conceded or 0

        if s.pass_accuracy is not None:
            acc_sum += s.pass_accuracy
            acc_count += 1

    avg_pass_accuracy = (acc_sum / acc_count) if acc_count > 0 else None

    # Calculate per-90 rates safely (only when total_minutes > 0)
    per90_factor = 90.0 / total_minutes if total_minutes > 0 else 0.0
    p90: dict[str, float | None] = {}
    for k, v in raw_sums.items():
        if k in {"minutes", "matches"}:
            continue
        p90[f"{k}_p90"] = round(v * per90_factor, 2) if total_minutes > 0 else None

    duel_win_pct = (
        round((raw_sums["duels_won"] / raw_sums["duels_total"]) * 100.0, 1)
        if raw_sums["duels_total"] > 0
        else None
    )
    dribble_succ_pct = (
        round((raw_sums["dribbles_success"] / raw_sums["dribbles_attempts"]) * 100.0, 1)
        if raw_sums["dribbles_attempts"] > 0
        else None
    )

    # If insufficient sample, return placeholder dimensions without fabricating scores
    if status in {"INSUFFICIENT_SAMPLE", "INSUFFICIENT_DATA"}:
        empty_dims: dict[str, ContributionDimensionItem] = {}
        dimension_names = ["passing", "progression", "creation", "finishing", "defending", "duels", "retention"]
        if pos_group == "GK":
            dimension_names.append("goalkeeping")
        for dim in dimension_names:
            empty_dims[dim] = ContributionDimensionItem(
                dimension=dim,
                score=None,
                percentile=None,
                key_metrics={},
                confidence=confidence,
                summary="Insufficient match minutes to evaluate without bias.",
            )
        return {
            "confidence": confidence,
            "contribution_status": status,
            "sample_minutes": total_minutes,
            "sample_matches": total_matches,
            "dimensions": empty_dims,
            "raw_metrics": {**raw_sums, **p90, "avg_pass_accuracy": avg_pass_accuracy},
            "strengths": [],
            "weaknesses": [],
        }

    # Evaluate Dimensions for Evaluated Players
    benchmarks = POSITION_BENCHMARKS.get(pos_group, POSITION_BENCHMARKS["MID"])
    dimensions: dict[str, ContributionDimensionItem] = {}
    strengths: list[str] = []
    weaknesses: list[str] = []

    # 1. Passing Dimension
    p_vol = p90.get("passes_total_p90") or 0.0
    p_acc = avg_pass_accuracy or 75.0
    bm_p_vol = benchmarks.get("passes_p90", 45.0)
    bm_p_acc = benchmarks.get("pass_acc", 80.0)
    passing_score = _clamp(0.5 * (p_vol / max(1.0, bm_p_vol)) + 0.5 * (p_acc / max(1.0, bm_p_acc)))
    dimensions["passing"] = ContributionDimensionItem(
        dimension="passing",
        score=round(passing_score, 2),
        percentile=round(passing_score * 100.0, 1),
        key_metrics={"passes_p90": p_vol, "pass_accuracy": p_acc},
        confidence=confidence,
        summary=f"{p_vol} passes/90 with {p_acc}% accuracy.",
    )
    if passing_score >= 0.75:
        strengths.append(f"High-volume passing distribution ({p_vol}/90, {p_acc}% acc)")
    elif passing_score <= 0.35:
        weaknesses.append(f"Subdued passing circulation volume ({p_vol}/90)")

    # 2. Creation Dimension
    kp_vol = p90.get("passes_key_p90") or 0.0
    ast_vol = p90.get("assists_p90") or 0.0
    bm_kp = benchmarks.get("key_passes_p90", 1.0)
    creation_score = _clamp(0.7 * (kp_vol / max(0.5, bm_kp)) + 0.3 * (ast_vol / 0.25))
    dimensions["creation"] = ContributionDimensionItem(
        dimension="creation",
        score=round(creation_score, 2),
        percentile=round(creation_score * 100.0, 1),
        key_metrics={"key_passes_p90": kp_vol, "assists_p90": ast_vol},
        confidence=confidence,
        summary=f"{kp_vol} key passes/90, {ast_vol} assists/90.",
    )
    if creation_score >= 0.70:
        strengths.append(f"Decisive chance creation presence ({kp_vol} key passes/90)")

    # 3. Finishing / Shooting Dimension
    shots_vol = p90.get("shots_total_p90") or 0.0
    sot_vol = p90.get("shots_on_target_p90") or 0.0
    goals_vol = p90.get("goals_p90") or 0.0
    bm_shots = benchmarks.get("shots_p90", 1.5)
    finishing_score = _clamp(0.4 * (shots_vol / max(0.5, bm_shots)) + 0.6 * (goals_vol / 0.3))
    dimensions["finishing"] = ContributionDimensionItem(
        dimension="finishing",
        score=round(finishing_score, 2),
        percentile=round(finishing_score * 100.0, 1),
        key_metrics={"shots_p90": shots_vol, "shots_on_target_p90": sot_vol, "goals_p90": goals_vol},
        confidence=confidence,
        summary=f"{shots_vol} shots/90, {goals_vol} goals/90.",
    )
    if finishing_score >= 0.70:
        strengths.append(f"High goal threat output ({goals_vol} goals/90)")

    # 4. Defending Dimension
    tkl_vol = p90.get("tackles_total_p90") or 0.0
    int_vol = p90.get("interceptions_p90") or 0.0
    blk_vol = p90.get("blocks_p90") or 0.0
    def_actions = tkl_vol + int_vol + blk_vol
    bm_def = benchmarks.get("tackles_p90", 1.5) + benchmarks.get("interceptions_p90", 1.0)
    defending_score = _clamp(def_actions / max(1.0, bm_def))
    dimensions["defending"] = ContributionDimensionItem(
        dimension="defending",
        score=round(defending_score, 2),
        percentile=round(defending_score * 100.0, 1),
        key_metrics={"tackles_p90": tkl_vol, "interceptions_p90": int_vol, "blocks_p90": blk_vol},
        confidence=confidence,
        summary=f"{round(def_actions, 2)} defensive actions/90.",
    )
    if defending_score >= 0.75:
        strengths.append(f"Proactive defensive disruptions ({round(def_actions, 1)} actions/90)")
    elif defending_score <= 0.30 and pos_group in {"DEF", "MID"}:
        weaknesses.append(f"Limited ground defensive involvement ({round(def_actions, 1)} actions/90)")

    # 5. Duels Dimension
    d_won = p90.get("duels_won_p90") or 0.0
    d_rate = duel_win_pct or 50.0
    duels_score = _clamp(0.5 * (d_won / 4.0) + 0.5 * (d_rate / 60.0))
    dimensions["duels"] = ContributionDimensionItem(
        dimension="duels",
        score=round(duels_score, 2),
        percentile=round(duels_score * 100.0, 1),
        key_metrics={"duels_won_p90": d_won, "duel_win_pct": d_rate},
        confidence=confidence,
        summary=f"{d_won} duels won/90 at {d_rate}%.",
    )
    if duels_score >= 0.70:
        strengths.append(f"Commanding duel success rate ({d_rate}%)")

    # 6. Ball Retention & Dribble
    drb_succ = p90.get("dribbles_success_p90") or 0.0
    fl_drawn = p90.get("fouls_drawn_p90") or 0.0
    retention_score = _clamp(0.6 * (drb_succ / 2.0) + 0.4 * (fl_drawn / 1.5))
    dimensions["retention"] = ContributionDimensionItem(
        dimension="retention",
        score=round(retention_score, 2),
        percentile=round(retention_score * 100.0, 1),
        key_metrics={"dribbles_succ_p90": drb_succ, "fouls_drawn_p90": fl_drawn},
        confidence=confidence,
        summary=f"{drb_succ} successful dribbles/90, {fl_drawn} fouls drawn/90.",
    )

    # 7. Goalkeeping (for GKs only)
    if pos_group == "GK":
        saves_vol = p90.get("saves_p90") or 0.0
        conceded_vol = p90.get("goals_conceded_p90") or 1.0
        gk_score = _clamp(0.6 * (saves_vol / 3.5) + 0.4 * max(0.0, (2.0 - conceded_vol) / 2.0))
        dimensions["goalkeeping"] = ContributionDimensionItem(
            dimension="goalkeeping",
            score=round(gk_score, 2),
            percentile=round(gk_score * 100.0, 1),
            key_metrics={"saves_p90": saves_vol, "goals_conceded_p90": conceded_vol},
            confidence=confidence,
            summary=f"{saves_vol} saves/90, {conceded_vol} goals conceded/90.",
        )

    return {
        "confidence": confidence,
        "contribution_status": status,
        "sample_minutes": total_minutes,
        "sample_matches": total_matches,
        "dimensions": dimensions,
        "raw_metrics": {**raw_sums, **p90, "avg_pass_accuracy": avg_pass_accuracy, "duel_win_pct": duel_win_pct},
        "strengths": strengths[:4],
        "weaknesses": weaknesses[:4],
    }
