"""Demand measured against supply.

The v1 outcome asked whether other creators would film a topic. For the person
using the product that is the wrong question: if everyone films it, you are
late and the competition is worse. What a creator needs is a topic where
*attention exceeds coverage* — where a video on the subject earns more views
than that channel normally gets.

That is measurable from the view snapshots we already collect. Two corrections
are required before views mean anything:

* **Age.** A video seen at 2 days and one seen at 20 days are not comparable.
  A global age curve projects every observation to a common reference age.
* **Channel size.** 40k views is a triumph for one channel and a failure for
  another. Every video is scored against its own channel's typical result.

What remains after both corrections is the part attributable to the topic.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from es_core.types import Video


@dataclass(frozen=True, slots=True)
class ViewObservation:
    video_id: str
    observed_at: datetime
    age_days: float
    view_count: int


@dataclass(frozen=True, slots=True)
class DemandPolicy:
    reference_age_days: float = 7.0
    minimum_age_days: float = 0.5
    maximum_age_days: float = 60.0
    minimum_channel_videos: int = 3
    """Below this a channel has no usable baseline and its videos are skipped."""
    age_bucket_days: float = 1.0


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


class DemandModel:
    """Channel-normalized view performance at a common video age.

    Built only from observations recorded at or before the checkpoint, so it is
    safe inside a replay.
    """

    def __init__(
        self,
        *,
        as_of: datetime,
        age_curve: dict[int, float],
        channel_baseline: dict[str, float],
        reference_views: dict[str, float],
        policy: DemandPolicy,
    ) -> None:
        self.as_of = as_of
        self._age_curve = age_curve
        self._channel_baseline = channel_baseline
        self._reference_views = reference_views
        self.policy = policy

    @classmethod
    def build(
        cls,
        videos: Iterable[Video],
        observations: Iterable[ViewObservation],
        *,
        as_of: datetime,
        policy: DemandPolicy | None = None,
    ) -> DemandModel:
        active = policy or DemandPolicy()
        channel_of = {video.video_id: video.channel_id for video in videos}

        usable: list[ViewObservation] = []
        for observation in observations:
            if observation.observed_at > as_of:
                continue
            if not active.minimum_age_days <= observation.age_days <= active.maximum_age_days:
                continue
            if observation.video_id in channel_of:
                usable.append(observation)

        # 1. Age curve: median views per age bucket, normalized to the reference.
        by_bucket: dict[int, list[float]] = {}
        for observation in usable:
            bucket = int(observation.age_days // active.age_bucket_days)
            by_bucket.setdefault(bucket, []).append(float(observation.view_count))
        bucket_median = {
            bucket: _median(values) for bucket, values in by_bucket.items() if len(values) >= 20
        }
        reference_bucket = int(active.reference_age_days // active.age_bucket_days)
        reference_level = bucket_median.get(reference_bucket) or _median(
            list(bucket_median.values())
        )
        age_curve = {
            bucket: (value / reference_level if reference_level else 1.0)
            for bucket, value in bucket_median.items()
            if value > 0
        }

        # 2. Project each video to reference-age equivalent views.
        best: dict[str, tuple[float, float]] = {}
        for observation in usable:
            distance = abs(observation.age_days - active.reference_age_days)
            current = best.get(observation.video_id)
            if current is None or distance < current[0]:
                bucket = int(observation.age_days // active.age_bucket_days)
                factor = age_curve.get(bucket, 1.0) or 1.0
                best[observation.video_id] = (distance, observation.view_count / factor)
        reference_views = {video_id: max(value, 0.0) for video_id, (_, value) in best.items()}

        # 3. Channel baseline: the channel's own median reference-age result.
        per_channel: dict[str, list[float]] = {}
        for video_id, value in reference_views.items():
            channel = channel_of.get(video_id)
            if channel is not None:
                per_channel.setdefault(channel, []).append(value)
        channel_baseline = {
            channel: _median(values)
            for channel, values in per_channel.items()
            if len(values) >= active.minimum_channel_videos and _median(values) > 0
        }
        return cls(
            as_of=as_of,
            age_curve=age_curve,
            channel_baseline=channel_baseline,
            reference_views=reference_views,
            policy=active,
        )

    @property
    def covered_channels(self) -> int:
        return len(self._channel_baseline)

    def normalized_lift(self, video_id: str, *, channel_id: str) -> float | None:
        """Log-ratio of this video's result to its channel's usual result.

        0.0 means exactly typical for the channel; +0.69 means twice as many
        views as usual; None means there is no comparable baseline yet, which is
        reported rather than guessed.
        """

        views = self._reference_views.get(video_id)
        baseline = self._channel_baseline.get(channel_id)
        if views is None or baseline is None or baseline <= 0:
            return None
        return round(math.log((views + 1.0) / (baseline + 1.0)), 6)

    def topic_lift(self, videos: Sequence[Video]) -> tuple[float | None, int]:
        """Median normalized lift across a topic's videos, and its support."""

        lifts = [
            value
            for video in videos
            if (value := self.normalized_lift(video.video_id, channel_id=video.channel_id))
            is not None
        ]
        if not lifts:
            return None, 0
        return round(_median(lifts), 6), len(lifts)


class ModelBaseline:
    """Adapter exposing a DemandModel through the core's ViewBaseline protocol."""

    def __init__(self, model: DemandModel, channel_of: dict[str, str]) -> None:
        self._model = model
        self._channel_of = channel_of

    def normalized_lift(self, video_id: str, *, as_of: datetime) -> float | None:
        channel = self._channel_of.get(video_id)
        if channel is None:
            return None
        return self._model.normalized_lift(video_id, channel_id=channel)


__all__ = [
    "DemandModel",
    "DemandPolicy",
    "ModelBaseline",
    "ViewObservation",
]
