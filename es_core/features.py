"""Point-in-time features.

Every value here is computable from what was observable at the checkpoint. The
module refuses to look at anything later: `build` raises if it is handed an
upload published after `as_of`, so a leak becomes a test failure rather than a
silently optimistic backtest.

Beyond the v1 supply/creator features this adds two groups that were missing:

* **burst state** — a two-state Kleinberg model over the publication stream,
  which separates a real burst from noise far better than `(recent-prev)/prev`;
* **audience response** — channel-normalized view lift at comparable video age.
  v1 measured only how many people *filmed* a topic, never whether anyone
  watched it, which is the difference between supply and demand.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from es_core.types import Anchor, Cluster, EvidenceVerdict, Video


class ViewBaseline(Protocol):
    """Channel-relative view performance, supplied by the data layer.

    Returns the log-ratio between a video's views at a comparable age and the
    channel's own median at that age, or None when no comparable baseline was
    observed by ``as_of``.
    """

    def normalized_lift(self, video_id: str, *, as_of: datetime) -> float | None: ...


class NoBaseline:
    def normalized_lift(self, video_id: str, *, as_of: datetime) -> float | None:
        return None


@dataclass(frozen=True, slots=True)
class FeaturePolicy:
    recent_window_days: int = 7
    previous_window_days: int = 28
    burst_scale: float = 2.0
    burst_transition_cost: float = 1.0


class LeakageError(ValueError):
    """Raised when a feature input postdates the checkpoint."""


def burst_state(
    published_at: Sequence[datetime],
    *,
    as_of: datetime,
    window_days: int = 28,
    policy: FeaturePolicy | None = None,
) -> float:
    """Share of recent days the stream spent in the elevated Kleinberg state.

    A compact two-state version of Kleinberg (2002): state 0 emits at the window
    mean rate, state 1 at ``burst_scale`` times that rate, and switching costs
    ``burst_transition_cost``. Viterbi over daily counts gives the cheapest
    explanation of the stream, which is robust to a single loud day.
    """

    active = policy or FeaturePolicy()
    if not published_at:
        return 0.0
    floor = as_of - timedelta(days=window_days)
    counts = Counter((as_of - moment).days for moment in published_at if floor <= moment <= as_of)
    if not counts:
        return 0.0
    days = list(range(window_days, -1, -1))
    observed = [counts.get(day, 0) for day in days]
    total = sum(observed)
    base_rate = max(total / len(days), 1e-6)
    rates = (base_rate, base_rate * active.burst_scale)

    def cost(rate: float, count: int) -> float:
        return rate - count * math.log(rate)

    previous = [cost(rates[state], observed[0]) for state in (0, 1)]
    paths: list[list[int]] = [[0], [1]]
    for count in observed[1:]:
        current: list[float] = []
        updated: list[list[int]] = []
        for state in (0, 1):
            options = [
                previous[origin]
                + (0.0 if origin == state else active.burst_transition_cost)
                + cost(rates[state], count)
                for origin in (0, 1)
            ]
            best = 0 if options[0] <= options[1] else 1
            current.append(options[best])
            updated.append([*paths[best], state])
        previous = current
        paths = updated
    best_path = paths[0] if previous[0] <= previous[1] else paths[1]
    recent = best_path[-active.recent_window_days :]
    return round(sum(recent) / len(recent), 6)


def _entropy(channel_ids: Sequence[str]) -> float:
    counts = Counter(channel_ids)
    if len(counts) <= 1:
        return 0.0
    total = len(channel_ids)
    raw = -sum((count / total) * math.log(count / total) for count in counts.values())
    return round(raw / math.log(len(counts)), 6)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def build(
    cluster: Cluster,
    *,
    as_of: datetime,
    history: Sequence[Video],
    anchors: Sequence[Anchor],
    evidence: EvidenceVerdict,
    topic_age_days: float,
    baseline: ViewBaseline | None = None,
    policy: FeaturePolicy | None = None,
) -> dict[str, float]:
    """Build the feature vector for one topic observation."""

    active = policy or FeaturePolicy()
    for video in (*cluster.members, *history):
        if not video.observable_at(as_of):
            raise LeakageError(f"video {video.video_id} is not observable at {as_of.isoformat()}")

    members = cluster.members
    recent_floor = as_of - timedelta(days=active.recent_window_days)
    previous_floor = as_of - timedelta(days=active.previous_window_days)

    recent = [video for video in members if video.published_at >= recent_floor]
    previous = [video for video in members if previous_floor <= video.published_at < recent_floor]
    previous_weekly = len(previous) / (active.previous_window_days / active.recent_window_days)
    acceleration = (len(recent) - previous_weekly) / max(previous_weekly, 1.0)

    channels = [video.channel_id for video in members]
    distinct_channels = set(channels)
    recent_channels = {video.channel_id for video in recent}
    historic_channels = {video.channel_id for video in history if video.published_at < recent_floor}

    lifts: list[float] = []
    if baseline is not None:
        for video in members:
            value = baseline.normalized_lift(video.video_id, as_of=as_of)
            if value is not None:
                lifts.append(value)

    features: dict[str, float] = {
        # supply
        "log_active_supply": round(math.log1p(len(members)), 6),
        "log_recent_supply": round(math.log1p(len(recent)), 6),
        "log_previous_weekly_supply": round(math.log1p(previous_weekly), 6),
        "supply_acceleration": round(min(6.0, max(-2.0, acceleration)), 6),
        "burst_state": burst_state(
            [video.published_at for video in members], as_of=as_of, policy=active
        ),
        # creators
        "log_distinct_creators": round(math.log1p(len(distinct_channels)), 6),
        "creator_diversity": round(len(distinct_channels) / max(len(members), 1), 6),
        "recent_creator_share": round(len(recent_channels) / max(len(distinct_channels), 1), 6),
        "new_creator_share": round(
            len(recent_channels - historic_channels) / max(len(recent_channels), 1), 6
        ),
        "channel_entropy": _entropy(channels),
        # semantics
        "mean_similarity": round(cluster.mean_similarity, 6),
        "minimum_similarity": round(cluster.minimum_similarity, 6),
        "anchor_score_max": round(max((anchor.score for anchor in anchors), default=0.0), 6),
        "anchor_novelty_max": round(max((anchor.novelty for anchor in anchors), default=0.0), 6),
        "anchor_channel_support": float(
            max((anchor.channel_support for anchor in anchors), default=0)
        ),
        # evidence quality
        "angle_diversity": round(evidence.angle_diversity, 6),
        "copy_family_ratio": round(evidence.copy_family_ratio, 6),
        "independent_channels": float(evidence.independent_channels),
        # audience response
        "has_view_baseline": 1.0 if lifts else 0.0,
        "median_normalized_lift": round(_median(lifts), 6) if lifts else 0.0,
        "positive_lift_share": (
            round(sum(1 for value in lifts if value > 0) / len(lifts), 6) if lifts else 0.0
        ),
        # time
        "log_topic_age_days": round(math.log1p(max(topic_age_days, 0.0)), 6),
    }
    return features


FEATURE_NAMES: tuple[str, ...] = (
    "anchor_channel_support",
    "anchor_novelty_max",
    "anchor_score_max",
    "angle_diversity",
    "burst_state",
    "channel_entropy",
    "copy_family_ratio",
    "creator_diversity",
    "has_view_baseline",
    "independent_channels",
    "log_active_supply",
    "log_distinct_creators",
    "log_previous_weekly_supply",
    "log_recent_supply",
    "log_topic_age_days",
    "mean_similarity",
    "median_normalized_lift",
    "minimum_similarity",
    "new_creator_share",
    "positive_lift_share",
    "recent_creator_share",
    "supply_acceleration",
)


__all__ = [
    "FEATURE_NAMES",
    "FeaturePolicy",
    "LeakageError",
    "NoBaseline",
    "ViewBaseline",
    "build",
    "burst_state",
]
