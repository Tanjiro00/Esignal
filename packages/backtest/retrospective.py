from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

SHORT_HORIZON_PROTOCOL_VERSION = "exploratory-short-horizon-retrospective-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ShortHorizonPolicy:
    """Pre-registered policy for a train-only, non-gating retrospective check."""

    horizons_days: tuple[int, ...] = (1, 3, 5)
    top_k: int = 10
    supply_growth_threshold: float = 3
    lift_threshold: float = 3
    grace_fraction: float = 0.25
    minimum_grace_days: float = 0.25
    maximum_grace_days: float = 1
    protocol_version: str = SHORT_HORIZON_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not self.horizons_days or any(value <= 0 for value in self.horizons_days):
            raise ValueError("horizons_days must contain positive values")
        if len(set(self.horizons_days)) != len(self.horizons_days):
            raise ValueError("horizons_days must not contain duplicates")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.supply_growth_threshold <= 1:
            raise ValueError("supply_growth_threshold must be greater than one")
        if self.lift_threshold <= 0:
            raise ValueError("lift_threshold must be positive")
        if not 0 < self.grace_fraction < 1:
            raise ValueError("grace_fraction must be within 0..1")
        if not 0 < self.minimum_grace_days <= self.maximum_grace_days:
            raise ValueError("grace day bounds are invalid")
        if not self.protocol_version.strip():
            raise ValueError("protocol_version must not be empty")

    def grace_days(self, horizon_days: int) -> float:
        if horizon_days not in self.horizons_days:
            raise ValueError("horizon_days must be registered in the policy")
        return max(
            self.minimum_grace_days,
            min(self.maximum_grace_days, horizon_days * self.grace_fraction),
        )


@dataclass(frozen=True)
class ShortHorizonObservation:
    snapshot_id: str
    observed_at: datetime
    supply_72h: int
    median_outlier_lift: float

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must not be empty")
        if self.supply_72h < 0 or self.median_outlier_lift < 0:
            raise ValueError("observation metrics must be nonnegative")


@dataclass(frozen=True)
class ShortHorizonLabel:
    status: Literal["evaluated", "insufficient_evidence"]
    fired: bool
    fired_snapshot_id: str | None
    fired_at: datetime | None
    latest_snapshot_id: str | None
    followup_count: int
    max_supply_growth: float
    peak_lift: float
    best_joint_fraction_of_gate: float
    supply_gate_reached: bool
    lift_gate_reached: bool


def label_short_horizon(
    *,
    baseline_supply_72h: int,
    checkpoint_at: datetime,
    horizon_days: int,
    observations: list[ShortHorizonObservation],
    policy: ShortHorizonPolicy | None = None,
) -> ShortHorizonLabel:
    """Apply the outcome rule without reading prediction score or rank.

    Supply and lift must cross their thresholds in the same stored observation.
    A non-firing topic is only evaluated when evidence reaches the end of the
    requested horizon. Missing follow-up is never converted into a false positive.
    """

    selected_policy = policy or ShortHorizonPolicy()
    grace_days = selected_policy.grace_days(horizon_days)
    checkpoint = _aware(checkpoint_at)
    horizon_end = checkpoint + timedelta(days=horizon_days)
    ordered = sorted(
        (row for row in observations if checkpoint < _aware(row.observed_at) <= horizon_end),
        key=lambda row: (_aware(row.observed_at), row.snapshot_id),
    )
    baseline_supply = max(baseline_supply_72h, 1)

    def supply_growth(row: ShortHorizonObservation) -> float:
        return row.supply_72h / baseline_supply

    fired = next(
        (
            row
            for row in ordered
            if supply_growth(row) >= selected_policy.supply_growth_threshold
            and row.median_outlier_lift >= selected_policy.lift_threshold
        ),
        None,
    )
    latest = ordered[-1] if ordered else None
    max_supply_growth = max((supply_growth(row) for row in ordered), default=0.0)
    peak_lift = max((row.median_outlier_lift for row in ordered), default=0.0)
    best_joint = max(
        (
            min(
                supply_growth(row) / selected_policy.supply_growth_threshold,
                row.median_outlier_lift / selected_policy.lift_threshold,
            )
            for row in ordered
        ),
        default=0.0,
    )
    evidence_floor = horizon_end - timedelta(days=grace_days)
    evaluated = fired is not None or (
        latest is not None and _aware(latest.observed_at) >= evidence_floor
    )
    return ShortHorizonLabel(
        status="evaluated" if evaluated else "insufficient_evidence",
        fired=fired is not None,
        fired_snapshot_id=fired.snapshot_id if fired is not None else None,
        fired_at=_aware(fired.observed_at) if fired is not None else None,
        latest_snapshot_id=latest.snapshot_id if latest is not None else None,
        followup_count=len(ordered),
        max_supply_growth=round(max_supply_growth, 4),
        peak_lift=round(peak_lift, 4),
        best_joint_fraction_of_gate=round(best_joint, 4),
        supply_gate_reached=max_supply_growth >= selected_policy.supply_growth_threshold,
        lift_gate_reached=peak_lift >= selected_policy.lift_threshold,
    )


__all__ = [
    "SHORT_HORIZON_PROTOCOL_VERSION",
    "ShortHorizonLabel",
    "ShortHorizonObservation",
    "ShortHorizonPolicy",
    "label_short_horizon",
]
