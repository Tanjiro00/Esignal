from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SCORE_BUCKET_VERSION = "score-to-user-bucket-v1"
DECISION_VERSION = "signal-decision-v1"

BucketLabel = Literal["Low", "Moderate", "High", "Very high"]
DecisionLabel = Literal["Act", "Watch", "Skip"]

_LABELS: tuple[BucketLabel, ...] = ("Low", "Moderate", "High", "Very high")


@dataclass(frozen=True)
class UserFacingBucket:
    label: BucketLabel
    reason_codes: tuple[str, ...]
    version: str = SCORE_BUCKET_VERSION


@dataclass(frozen=True)
class DecisionAssessment:
    decision: DecisionLabel
    reason_codes: tuple[str, ...]
    version: str = DECISION_VERSION


def _base_bucket_index(score: float) -> int:
    bounded = min(100.0, max(0.0, float(score)))
    if bounded >= 85:
        return 3
    if bounded >= 70:
        return 2
    if bounded >= 45:
        return 1
    return 0


def score_to_user_bucket_v1(
    score: float,
    *,
    fragility_penalty: float = 0,
    baseline_coverage_percent: float = 100,
    specificity_score: float = 100,
) -> UserFacingBucket:
    """Convert an internal score into a conservative, explainable user bucket.

    Raw scores stay available for admin and evaluation. The customer-facing
    bucket is downgraded when the stored evidence is too fragile to support the
    apparent precision of the raw value.
    """

    base_index = _base_bucket_index(score)
    downgrade = 0
    reasons: list[str] = []

    if fragility_penalty >= 75:
        downgrade = max(downgrade, 2)
        reasons.append("very_high_fragility")
    elif fragility_penalty >= 55:
        downgrade = max(downgrade, 1)
        reasons.append("high_fragility")

    if baseline_coverage_percent < 40:
        downgrade = max(downgrade, 2)
        reasons.append("very_weak_baseline_coverage")
    elif baseline_coverage_percent < 70:
        downgrade = max(downgrade, 1)
        reasons.append("weak_baseline_coverage")

    if specificity_score < 55:
        downgrade = max(downgrade, 2)
        reasons.append("weak_topic_specificity")
    elif specificity_score < 70:
        downgrade = max(downgrade, 1)
        reasons.append("limited_topic_specificity")

    final_index = max(0, base_index - downgrade)
    if downgrade == 0:
        reasons.append("evidence_supports_raw_band")
    return UserFacingBucket(label=_LABELS[final_index], reason_codes=tuple(reasons))


def assess_decision(
    *,
    signal_bucket: BucketLabel,
    fit_bucket: BucketLabel,
    evidence_bucket: BucketLabel,
    lifecycle_stage: str,
    saturation_penalty: float,
    production_feasible: bool = True,
    insight_ready: bool = True,
) -> DecisionAssessment:
    """Produce one deterministic Act / Watch / Skip assessment."""

    stage = lifecycle_stage.strip().lower()
    reasons: list[str] = []
    if not insight_ready:
        return DecisionAssessment(
            decision="Skip",
            reason_codes=("no_evidence_backed_insight",),
        )
    if not production_feasible:
        return DecisionAssessment(
            decision="Skip",
            reason_codes=("production_window_infeasible",),
        )
    if stage in {"saturated", "declining"} or saturation_penalty >= 90:
        return DecisionAssessment(
            decision="Skip",
            reason_codes=("topic_too_late",),
        )

    signal_rank = _LABELS.index(signal_bucket)
    fit_rank = _LABELS.index(fit_bucket)
    evidence_rank = _LABELS.index(evidence_bucket)
    if stage == "seed":
        return DecisionAssessment(
            decision="Watch",
            reason_codes=("early_evidence_watch",),
        )
    if signal_rank >= 2 and fit_rank >= 2 and evidence_rank >= 1:
        reasons.extend(("strong_signal", "strong_channel_fit", "supported_evidence"))
        if saturation_penalty >= 65:
            return DecisionAssessment(
                decision="Watch",
                reason_codes=(*reasons, "rising_saturation"),
            )
        return DecisionAssessment(decision="Act", reason_codes=tuple(reasons))

    if signal_rank >= 1 and fit_rank >= 1 and evidence_rank >= 1:
        return DecisionAssessment(
            decision="Watch",
            reason_codes=("promising_but_not_decisive",),
        )
    if signal_rank >= 2 and evidence_rank >= 1:
        return DecisionAssessment(
            decision="Watch",
            reason_codes=("signal_stronger_than_channel_fit",),
        )
    return DecisionAssessment(
        decision="Skip",
        reason_codes=("insufficient_actionability",),
    )
