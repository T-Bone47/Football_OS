"""Market Benchmarks and Baseline Valuation Engine (Phase 4.1L, 4.1M, 4.1N, 4.1O).
Implements transparent statistical cohorts, deterministic baseline player valuation,
and uncertainty interval foundations without black-box ML or LLM hallucinations.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import statistics
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Player, Transfer
from app.market.comparables import ComparableTransferEngine
from app.market.context import build_player_market_context
from app.market.schemas import (
    ComparableTransferItem,
    MarketBenchmarkResponse,
    ValuationBaselineResponse,
)
from app.market.universe import get_temporal_transfers


class MarketBenchmarkEngine:
    """Calculates distribution benchmarks for comparable player cohorts."""

    @staticmethod
    def calculate_benchmarks(
        fees_eur: list[float],
        position_group: str = "ALL",
        time_window: str = "all_historical",
        min_sample: int = 3,
    ) -> MarketBenchmarkResponse:
        """Computes sample-gated percentiles and dispersion metrics."""
        clean_fees = sorted([f for f in fees_eur if f is not None and f >= 0])
        n = len(clean_fees)

        if n < min_sample:
            return MarketBenchmarkResponse(
                position_group=position_group,
                time_window=time_window,
                sample_size=n,
                data_status="INSUFFICIENT_DATA",
                median_fee_eur=None,
                q1_fee_eur=None,
                q3_fee_eur=None,
                iqr_fee_eur=None,
                min_fee_eur=None,
                max_fee_eur=None,
                population_definition=f"Historical permanent transfers in {position_group} cohort (n={n} < min_sample={min_sample})",
                calculation_version="market_benchmark_v1",
            )

        med = statistics.median(clean_fees)
        min_fee = clean_fees[0]
        max_fee = clean_fees[-1]

        # Calculate quartiles
        if n >= 4:
            mid = n // 2
            lower_half = clean_fees[:mid]
            upper_half = clean_fees[mid + (1 if n % 2 != 0 else 0):]
            q1 = statistics.median(lower_half)
            q3 = statistics.median(upper_half)
            iqr = round(q3 - q1, 2)
        else:
            q1 = min_fee
            q3 = max_fee
            iqr = round(q3 - q1, 2)

        return MarketBenchmarkResponse(
            position_group=position_group,
            time_window=time_window,
            sample_size=n,
            data_status="EVALUATED",
            median_fee_eur=round(med, 2),
            q1_fee_eur=round(q1, 2),
            q3_fee_eur=round(q3, 2),
            iqr_fee_eur=iqr,
            min_fee_eur=round(min_fee, 2),
            max_fee_eur=round(max_fee, 2),
            population_definition=f"Historical permanent transfers in {position_group} cohort",
            calculation_version="market_benchmark_v1",
        )


class BaselineValuationEngine:
    """Deterministic Comparable Median Baseline Valuation Engine (Phase 4.1M & 4.1O)."""

    def __init__(self, comparable_engine: ComparableTransferEngine | None = None) -> None:
        self.comparable_engine = comparable_engine or ComparableTransferEngine()

    @staticmethod
    def get_age_adjustment(age: float | None) -> float:
        """Empirical age curve multiplier based on historical football valuation trajectory."""
        if age is None:
            return 1.0
        if age < 21.0:
            return 1.15  # High developmental upside
        elif age < 24.0:
            return 1.10  # Prime pre-peak value
        elif age <= 28.5:
            return 1.00  # Peak career maturity
        elif age <= 31.0:
            return 0.85  # Moderate contract duration discount
        else:
            return 0.65  # Veteran contract depreciation

    async def compute_valuation_baseline(
        self,
        session: AsyncSession,
        player_id: uuid.UUID,
        as_of: datetime | date | None = None,
        min_sample_size: int = 3,
        min_range_sample_size: int = 5,
    ) -> ValuationBaselineResponse:
        """Computes deterministic baseline valuation anchored on comparable transfer median."""
        eval_time = as_of or datetime.now(timezone.utc)
        eval_datetime = eval_time if isinstance(eval_time, datetime) else datetime.combine(eval_time, datetime.min.time(), tzinfo=timezone.utc)

        # 1. Fetch market context & comparables
        context = await build_player_market_context(session, player_id, as_of=eval_time)
        comp_res = await self.comparable_engine.find_comparables(session, player_id, as_of=eval_time, top_k=10)

        player_name = comp_res.target_player_name if comp_res else "Unknown"

        # 2. Extract usable normalized fees from comparables
        usable_fees = [
            c.fee_eur_normalized
            for c in comp_res.comparables
            if c.fee_eur_normalized is not None and c.fee_eur_normalized > 0
        ]
        sample_size = len(usable_fees)

        # 3. Hard Sufficiency Gate (Principle 6)
        if sample_size < min_sample_size or not context:
            return ValuationBaselineResponse(
                player_id=player_id,
                player_name=player_name,
                as_of=eval_datetime,
                valuation_status="VALUATION_UNAVAILABLE",
                range_status="RANGE_NOT_AVAILABLE",
                confidence="INSUFFICIENT_DATA",
                estimated_value_eur=None,
                lower_bound_eur=None,
                upper_bound_eur=None,
                comparable_sample_size=sample_size,
                cohort_median_fee_eur=None,
                adjustments={},
                methodology="Deterministic Comparable Median with Empirical Age Curve",
                calculation_version="valuation_baseline_v1",
            )

        # 4. Cohort Baseline Anchor
        cohort_median = statistics.median(usable_fees)

        # 5. Deterministic Adjustments
        age_factor = self.get_age_adjustment(context.age_at_as_of)

        estimated_val = round(cohort_median * age_factor, 2)

        # 6. Uncertainty Range Foundation (Phase 4.1O)
        # Only compute bounds if sample size is sufficient to form an empirical IQR
        lower_bound = None
        upper_bound = None
        range_status = "RANGE_NOT_AVAILABLE"

        if sample_size >= min_range_sample_size:
            clean_sorted = sorted(usable_fees)
            mid = sample_size // 2
            q1 = statistics.median(clean_sorted[:mid])
            q3 = statistics.median(clean_sorted[mid + (1 if sample_size % 2 != 0 else 0):])
            lower_bound = round(q1 * age_factor, 2)
            upper_bound = round(q3 * age_factor, 2)
            range_status = "RANGE_AVAILABLE"

        confidence = "HIGH" if sample_size >= 6 else "MEDIUM" if sample_size >= 3 else "LOW"

        return ValuationBaselineResponse(
            player_id=player_id,
            player_name=player_name,
            as_of=eval_datetime,
            valuation_status="VALUATION_AVAILABLE",
            range_status=range_status,
            confidence=confidence,
            estimated_value_eur=estimated_val,
            lower_bound_eur=lower_bound,
            upper_bound_eur=upper_bound,
            comparable_sample_size=sample_size,
            cohort_median_fee_eur=round(cohort_median, 2),
            adjustments={
                "age_at_as_of": context.age_at_as_of,
                "age_curve_factor": round(age_factor, 3),
                "position_group": context.position_group,
            },
            methodology="Deterministic Comparable Median with Empirical Age Curve",
            calculation_version="valuation_baseline_v1",
        )


def evaluate_temporal_baseline(
    transfers: list[Transfer],
    split_date: date,
) -> dict[str, Any]:
    """Evaluates the deterministic baseline on historical data using strict temporal separation (Phase 4.1N)."""
    # Separate past training universe from test transactions
    train_pool = [t for t in transfers if t.transfer_date and t.transfer_date < split_date and t.fee_eur_normalized]
    test_pool = [t for t in transfers if t.transfer_date and t.transfer_date >= split_date and t.fee_eur_normalized]

    if not train_pool or not test_pool:
        return {
            "status": "INSUFFICIENT_DATA",
            "train_size": len(train_pool),
            "test_size": len(test_pool),
            "mae": None,
            "rmse": None,
            "med_ae": None,
        }

    def _extract_pos(t: Any) -> str:
        pg = getattr(t, "position_group", None)
        if pg in ("GK", "DEF", "MID", "ATT"):
            return pg
        if hasattr(t, "player") and t.player and getattr(t.player, "primary_position", None):
            prim = t.player.primary_position
            if "Goalkeeper" in prim:
                return "GK"
            if "Defender" in prim:
                return "DEF"
            if "Attacker" in prim or "Forward" in prim:
                return "ATT"
        return "MID"

    # Group train pool by position group
    train_medians: dict[str, float] = {}
    for pos in ("GK", "DEF", "MID", "ATT"):
        fees = [
            t.fee_eur_normalized
            for t in train_pool
            if t.fee_eur_normalized and _extract_pos(t) == pos
        ]
        if fees:
            train_medians[pos] = statistics.median(fees)
        else:
            all_fees = [t.fee_eur_normalized for t in train_pool if t.fee_eur_normalized]
            train_medians[pos] = statistics.median(all_fees) if all_fees else 10_000_000.0

    errors: list[float] = []
    abs_errors: list[float] = []
    sq_errors: list[float] = []
    log_errors: list[float] = []

    pos_abs_errors: dict[str, list[float]] = {"GK": [], "DEF": [], "MID": [], "ATT": []}
    band_abs_errors: dict[str, list[float]] = {"<10M": [], "10M-30M": [], "30M-70M": [], ">70M": []}

    for t in test_pool:
        actual = t.fee_eur_normalized
        if not actual or actual <= 0:
            continue
        pos = _extract_pos(t)
        pred = train_medians.get(pos, 10_000_000.0)
        diff = pred - actual
        abs_diff = abs(diff)

        errors.append(diff)
        abs_errors.append(abs_diff)
        sq_errors.append(diff * diff)
        log_errors.append(abs(math.log(max(pred, 1.0)) - math.log(max(actual, 1.0))))

        pos_abs_errors[pos].append(abs_diff)

        m_eur = actual / 1_000_000.0
        if m_eur < 10.0:
            band_abs_errors["<10M"].append(abs_diff)
        elif m_eur < 30.0:
            band_abs_errors["10M-30M"].append(abs_diff)
        elif m_eur < 70.0:
            band_abs_errors["30M-70M"].append(abs_diff)
        else:
            band_abs_errors[">70M"].append(abs_diff)

    mae = statistics.mean(abs_errors) if abs_errors else 0.0
    rmse = math.sqrt(statistics.mean(sq_errors)) if sq_errors else 0.0
    med_ae = statistics.median(abs_errors) if abs_errors else 0.0
    log_mae = statistics.mean(log_errors) if log_errors else 0.0

    by_position = {
        p: {"mae": round(statistics.mean(errs), 2), "count": len(errs)}
        for p, errs in pos_abs_errors.items()
        if errs
    }
    by_fee_band = {
        b: {"mae": round(statistics.mean(errs), 2), "count": len(errs)}
        for b, errs in band_abs_errors.items()
        if errs
    }

    return {
        "status": "EVALUATED",
        "train_size": len(train_pool),
        "test_size": len(test_pool),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "med_ae": round(med_ae, 2),
        "log_mae": round(log_mae, 4),
        "by_position": by_position,
        "by_fee_band": by_fee_band,
    }
