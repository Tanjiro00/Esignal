"""Replay harness and metrics.

The harness runs the production pipeline (`es_core.pipeline.build_candidates`)
at a series of checkpoints and scores the frozen adoption outcome afterwards.
There is no separate backtest algorithm — that separation is what made the v1
numbers unverifiable.

Every run reports the simple rankings alongside the model. A model that cannot
beat recent supply, acceleration, creator breadth and semantic cohesion has not
earned the extra complexity.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from es_core.anchors import BackgroundCorpus
from es_core.identity import TopicRegistry
from es_core.outcome import AdoptionOutcome, AdoptionPolicy, evaluate_adoption
from es_core.pipeline import PipelinePolicy, build_candidates, observable
from es_core.types import Candidate
from es_eval.dataset import Dataset


@dataclass(frozen=True, slots=True)
class Episode:
    candidate: Candidate
    outcome: AdoptionOutcome

    @property
    def label(self) -> bool:
        return self.outcome.fired


@dataclass(frozen=True, slots=True)
class ReplayResult:
    episodes: tuple[Episode, ...]
    checkpoints: tuple[datetime, ...]
    observation_floor: datetime | None
    policy_horizon_days: int
    rejected_by_evidence: int = 0
    rejected_by_anchor: int = 0
    diagnostics: dict[str, float] = field(default_factory=dict)

    @property
    def base_rate(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(1 for episode in self.episodes if episode.label) / len(self.episodes)


def weekly_checkpoints(start: datetime, end: datetime) -> tuple[datetime, ...]:
    checkpoints: list[datetime] = []
    current = start
    while current <= end:
        checkpoints.append(current)
        current += timedelta(days=7)
    return tuple(checkpoints)


def run(
    dataset: Dataset,
    checkpoints: Sequence[datetime],
    *,
    pipeline_policy: PipelinePolicy | None = None,
    adoption_policy: AdoptionPolicy | None = None,
    publishable_only: bool = True,
) -> ReplayResult:
    """Build candidates at every checkpoint and evaluate their outcomes."""

    pipeline = pipeline_policy or PipelinePolicy()
    adoption = adoption_policy or AdoptionPolicy()
    registry = TopicRegistry()
    episodes: list[Episode] = []
    rejected_evidence = 0
    rejected_anchor = 0
    seen_topics: dict[str, datetime] = {}

    for checkpoint in checkpoints:
        candidates = build_candidates(
            dataset.videos,
            dataset.embeddings,
            as_of=checkpoint,
            registry=registry,
            policy=pipeline,
        )
        visible = observable(dataset.videos, as_of=checkpoint)
        corpus = BackgroundCorpus.build(visible, as_of=checkpoint, policy=pipeline.anchors)
        future = tuple(
            video
            for video in dataset.videos
            if checkpoint < video.published_at <= checkpoint + timedelta(days=adoption.horizon_days)
        )
        for candidate in candidates:
            # One episode per topic per outcome window, as in the frozen protocol.
            previous = seen_topics.get(candidate.topic_id)
            if previous is not None and checkpoint - previous < timedelta(
                days=adoption.horizon_days
            ):
                continue
            if not candidate.anchors:
                rejected_anchor += 1
                if publishable_only:
                    continue
            if candidate.evidence.status != "accepted":
                rejected_evidence += 1
                if publishable_only:
                    continue
            seen_topics[candidate.topic_id] = checkpoint
            prior_channels = frozenset(candidate.channel_ids)
            outcome = evaluate_adoption(
                as_of=checkpoint,
                prior_channel_ids=prior_channels,
                previous_28d_video_count=int(
                    round(math.expm1(candidate.features.get("log_previous_weekly_supply", 0.0)) * 4)
                ),
                future_videos=_topic_future(candidate, future, dataset),
                corpus=corpus,
                policy=adoption,
            )
            episodes.append(Episode(candidate=candidate, outcome=outcome))

    floor = min((video.discovered_at for video in dataset.videos), default=None)
    return ReplayResult(
        episodes=tuple(episodes),
        checkpoints=tuple(checkpoints),
        observation_floor=floor,
        policy_horizon_days=adoption.horizon_days,
        rejected_by_evidence=rejected_evidence,
        rejected_by_anchor=rejected_anchor,
    )


def _topic_future(
    candidate: Candidate,
    future: Sequence[object],
    dataset: Dataset,
    *,
    centroid_similarity: float = 0.74,
    exemplar_similarity: float = 0.78,
) -> tuple:
    """Future uploads close enough to the topic to count as the same topic.

    Both radii from the frozen v1 protocol apply: proximity to the centroid and
    to at least one exemplar. The centroid alone admits anything vaguely on
    theme and inflates the base rate.
    """

    centroid = _centroid(candidate, dataset)
    if centroid is None:
        return ()
    exemplars = [
        dataset.embeddings[video_id]
        for video_id in candidate.evidence_video_ids or candidate.member_video_ids
        if video_id in dataset.embeddings
    ]
    matched = []
    for video in future:
        vector = dataset.embeddings.get(getattr(video, "video_id", ""))
        if vector is None:
            continue
        if _cosine(vector, centroid) < centroid_similarity:
            continue
        if exemplars and max(_cosine(vector, item) for item in exemplars) < exemplar_similarity:
            continue
        matched.append(video)
    return tuple(matched)


def _centroid(candidate: Candidate, dataset: Dataset) -> tuple[float, ...] | None:
    vectors = [
        dataset.embeddings[video_id]
        for video_id in candidate.member_video_ids
        if video_id in dataset.embeddings
    ]
    if not vectors:
        return None
    dimensions = len(vectors[0])
    mean = [sum(vector[index] for vector in vectors) / len(vectors) for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in mean))
    return tuple(value / norm for value in mean) if norm else tuple(mean)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


# ------------------------------------------------------------------ metrics


def top_quintile_precision(scores: Sequence[float], labels: Sequence[bool]) -> tuple[float, int]:
    if not scores:
        return 0.0, 0
    count = max(1, len(scores) // 5)
    order = sorted(range(len(scores)), key=lambda index: -scores[index])[:count]
    hits = sum(1 for index in order if labels[index])
    return hits / count, count


def average_precision(scores: Sequence[float], labels: Sequence[bool]) -> float:
    if not scores or not any(labels):
        return 0.0
    order = sorted(range(len(scores)), key=lambda index: -scores[index])
    hits = 0
    total = 0.0
    for rank, index in enumerate(order, start=1):
        if labels[index]:
            hits += 1
            total += hits / rank
    return total / hits if hits else 0.0


def bootstrap_lift(
    scores: Sequence[float],
    labels: Sequence[bool],
    *,
    resamples: int = 500,
    seed: int = 17,
) -> tuple[float, float, float]:
    """Percentile bootstrap over episodes for the top-quintile lift."""

    if not scores or not any(labels):
        return 0.0, 0.0, 0.0
    generator = random.Random(seed)
    lifts: list[float] = []
    indexes = range(len(scores))
    for _ in range(resamples):
        sample = [generator.choice(indexes) for _ in indexes]
        sampled_scores = [scores[index] for index in sample]
        sampled_labels = [labels[index] for index in sample]
        base = sum(sampled_labels) / len(sampled_labels)
        if base <= 0:
            continue
        precision, _ = top_quintile_precision(sampled_scores, sampled_labels)
        lifts.append(precision / base)
    if not lifts:
        return 0.0, 0.0, 0.0
    lifts.sort()
    return (
        lifts[int(0.025 * len(lifts))],
        lifts[len(lifts) // 2],
        lifts[min(len(lifts) - 1, int(0.975 * len(lifts)))],
    )


def median_lead_days(episodes: Sequence[Episode]) -> float:
    leads = [
        episode.outcome.lead_days
        for episode in episodes
        if episode.label and episode.outcome.lead_days is not None
    ]
    if not leads:
        return 0.0
    leads.sort()
    middle = len(leads) // 2
    if len(leads) % 2 == 1:
        return leads[middle]
    return (leads[middle - 1] + leads[middle]) / 2


BASELINES: dict[str, str] = {
    "recent_supply": "log_recent_supply",
    "acceleration": "supply_acceleration",
    "creator_breadth": "log_distinct_creators",
    "semantic_cohesion": "mean_similarity",
    "burst_state": "burst_state",
}


__all__ = [
    "BASELINES",
    "Episode",
    "ReplayResult",
    "average_precision",
    "bootstrap_lift",
    "median_lead_days",
    "run",
    "top_quintile_precision",
    "weekly_checkpoints",
]
