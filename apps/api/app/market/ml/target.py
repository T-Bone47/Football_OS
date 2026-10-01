"""Supervised Valuation Target Definition & Transformation (Phase 4.2B & 4.2C).

Enforces:
- Strict target eligibility: ONLY KNOWN_FEE and verified REPORTED_FEE permanent transfers.
- Strict exclusions: LOAN, ESTIMATED_FEE, UNKNOWN_FEE, UNDISCLOSED, FREE_TRANSFER.
- Statistical transformation: y = log1p(fee) to address heavy-tailed skewness and heteroscedasticity.
- Retransformation methodology: Duan's smearing estimator for unbiased back-transformation.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence
from pydantic import BaseModel, Field

from app.market.taxonomy import TransferFeeStatus


class TargetDistributionStats(BaseModel):
    """Statistical summary of the target distribution before and after transformation."""
    sample_size: int
    mean: float
    median: float
    std_dev: float
    min_val: float
    max_val: float
    q1: float
    q3: float
    iqr: float
    skewness: float
    kurtosis: float


class SupervisedValuationTarget:
    """Supervised target handler for transfer valuation models."""

    TARGET_NAME = "transfer_fee_eur"
    TRANSFORMED_TARGET_NAME = "log_transfer_fee_eur"

    ELIGIBLE_STATUSES = {
        TransferFeeStatus.KNOWN_FEE.value,
        TransferFeeStatus.REPORTED_FEE.value,
    }

    EXCLUDED_STATUSES = {
        TransferFeeStatus.UNKNOWN_FEE.value: "NON_TARGET_FEE_STATUS",
        TransferFeeStatus.UNDISCLOSED.value: "NON_TARGET_FEE_STATUS",
        TransferFeeStatus.ESTIMATED_FEE.value: "ESTIMATED_FEE_EXCLUDED_BY_DEFAULT",
        TransferFeeStatus.FREE_TRANSFER.value: "FREE_TRANSFERS_SEPARATE_CLASS",
    }

    @classmethod
    def check_eligibility(
        cls,
        fee_status: str,
        is_loan: bool,
        fee_eur: float | None,
    ) -> tuple[bool, str]:
        """Determines whether a transfer record qualifies as an eligible supervised regression target."""
        if is_loan:
            return False, "LOANS_EXCLUDED_FROM_PERMANENT_FEE_REGRESSION"

        if fee_status in cls.EXCLUDED_STATUSES:
            return False, cls.EXCLUDED_STATUSES[fee_status]

        if fee_status not in cls.ELIGIBLE_STATUSES:
            return False, f"UNSUPPORTED_STATUS_{fee_status}"

        if fee_eur is None or fee_eur <= 0:
            return False, "INVALID_OR_NON_POSITIVE_FEE"

        return True, "ELIGIBLE"

    @staticmethod
    def transform(fee_eur: float | Sequence[float]) -> float | list[float]:
        """Applies log1p transformation to fee target: y_log = ln(1 + fee_eur)."""
        if isinstance(fee_eur, (int, float)):
            if fee_eur < 0:
                raise ValueError(f"Transfer fee cannot be negative, got {fee_eur}")
            return math.log1p(float(fee_eur))
        return [math.log1p(max(0.0, float(f))) for f in fee_eur]

    @staticmethod
    def inverse_transform(
        log_pred: float | Sequence[float],
        smearing_factor: float = 1.0,
    ) -> float | list[float]:
        """Applies smearing-corrected exponential back-transformation:
        hat{y} = max(0.0, exp(y_log) * smearing_factor - 1.0)
        """
        factor = max(0.1, smearing_factor)
        if isinstance(log_pred, (int, float)):
            val = math.expm1(float(log_pred)) * factor
            return max(0.0, round(val, 2))
        return [max(0.0, round(math.expm1(float(p)) * factor, 2)) for p in log_pred]

    @staticmethod
    def calculate_duan_smearing_factor(y_true_log: Sequence[float], y_pred_log: Sequence[float]) -> float:
        """Calculates Duan's (1983) non-parametric smearing estimate:
        S = (1 / N) * sum(exp(e_i)), where e_i = y_true_log_i - y_pred_log_i.
        Corrects for retransformation bias of logarithmic regression models.
        """
        if len(y_true_log) == 0 or len(y_true_log) != len(y_pred_log):
            return 1.0

        residuals = [t - p for t, p in zip(y_true_log, y_pred_log)]
        # Clip residuals to prevent numerical overflow in exp
        clipped_residuals = [max(-10.0, min(10.0, r)) for r in residuals]
        smearing = statistics.mean(math.exp(r) for r in clipped_residuals)
        return float(round(smearing, 4))

    @staticmethod
    def compute_distribution_stats(values: Sequence[float]) -> TargetDistributionStats:
        """Computes comprehensive distribution statistics including skewness and kurtosis."""
        clean = sorted([float(v) for v in values if v is not None])
        n = len(clean)
        if n < 3:
            raise ValueError(f"At least 3 observations required for distribution stats, got {n}")

        mean_val = statistics.mean(clean)
        median_val = statistics.median(clean)
        std_val = statistics.stdev(clean) if n > 1 else 0.0
        min_val = clean[0]
        max_val = clean[-1]

        # Quartiles
        mid = n // 2
        q1 = statistics.median(clean[:mid])
        q3 = statistics.median(clean[mid + (1 if n % 2 != 0 else 0):])
        iqr = q3 - q1

        # Fisher-Pearson coefficient of skewness
        if std_val > 1e-9:
            m3 = sum((x - mean_val) ** 3 for x in clean) / n
            skewness = m3 / (std_val ** 3)
            m4 = sum((x - mean_val) ** 4 for x in clean) / n
            kurtosis = (m4 / (std_val ** 4)) - 3.0  # excess kurtosis
        else:
            skewness = 0.0
            kurtosis = 0.0

        return TargetDistributionStats(
            sample_size=n,
            mean=round(mean_val, 4),
            median=round(median_val, 4),
            std_dev=round(std_val, 4),
            min_val=round(min_val, 4),
            max_val=round(max_val, 4),
            q1=round(q1, 4),
            q3=round(q3, 4),
            iqr=round(iqr, 4),
            skewness=round(skewness, 4),
            kurtosis=round(kurtosis, 4),
        )
