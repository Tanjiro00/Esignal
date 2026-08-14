from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from statistics import median
from typing import Literal

from packages.backtest.youniverse import OutcomeVideo, StructuralVideo
from packages.clustering import (
    MicrotopicCluster,
    MicrotopicDocument,
    MicrotopicIdentity,
    cluster_microtopics_v7,
    cluster_microtopics_v8,
    infer_microtopic_identity_v7,
    infer_microtopic_identity_v8,
    topic_key_v7,
    topic_key_v8,
)
from packages.scoring import TopicMeasurements, score_topic


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class StructuralReplayPolicy:
    structural_lookback_days: int = 180
    active_window_days: int = 35
    recent_window_days: int = 7
    outcome_horizon_days: int = 42
    episode_cooldown_days: int = 42
    top_k: int = 10
    minimum_videos: int = 3
    minimum_channels: int = 3
    minimum_recent_videos: int = 2
    minimum_recent_channels: int = 2
    minimum_new_recent_channels: int = 2
    maximum_active_videos: int = 25
    minimum_specificity: float = 70
    minimum_thesis_support: float = 0.8
    supply_growth_threshold: float = 3
    minimum_future_videos: int = 3
    minimum_new_future_channels: int = 3
    minimum_new_channel_share: float = 0.5
    minimum_outlier_videos: int = 3
    minimum_outlier_ratio: float = 3
    minimum_median_outlier_ratio: float = 2
    minimum_outcome_baseline_coverage: float = 0.8
    research_minimum_videos: int = 2
    research_minimum_channels: int = 2
    research_minimum_recent_videos: int = 1
    research_maximum_active_videos: int = 60
    adoption_supply_growth_threshold: float = 1.25
    adoption_minimum_future_videos: int = 4
    adoption_minimum_new_future_channels: int = 2
    adoption_minimum_new_channel_share: float = 0.4
    performance_minimum_future_videos: int = 2
    performance_minimum_outlier_videos: int = 1
    performance_minimum_outlier_ratio: float = 2
    performance_minimum_median_outlier_ratio: float = 1.25
    performance_minimum_baseline_coverage: float = 0.6


@dataclass(frozen=True)
class ChannelSnapshot:
    channel_id: str
    observed_at: datetime
    views: int
    delta_views: int
    subscribers: int
    delta_subscribers: int
    videos: int
    delta_videos: int
    activity: int


@dataclass(frozen=True)
class StructuralTopicState:
    topic_key: str
    label: str
    observed_at: datetime
    score: float
    specificity_score: float
    thesis_support_ratio: float
    eligible: bool
    active_video_count: int
    recent_video_count: int
    previous_28d_video_count: int
    distinct_channel_count: int
    recent_channel_count: int
    new_recent_channel_count: int
    acceleration: float
    large_channel_count: int
    channel_size_bucket_count: int
    member_video_ids: tuple[str, ...]
    member_channel_ids: tuple[str, ...]
    evidence_titles: tuple[str, ...]
    research_eligible: bool = False
    channel_entropy: float = 0
    topic_age_days: float = 0


@dataclass(frozen=True)
class StructuralTopicOutcome:
    topic_key: str
    fired: bool
    fired_at: datetime | None
    lead_days: float | None
    future_video_count: int
    expected_future_supply: float
    supply_growth: float
    new_future_channel_count: int
    new_channel_share: float
    baseline_coverage: float
    outlier_video_count: int
    median_outlier_ratio: float | None
    adoption_fired: bool = False
    adoption_fired_at: datetime | None = None
    adoption_lead_days: float | None = None
    performance_fired: bool = False
    performance_fired_at: datetime | None = None
    performance_lead_days: float | None = None
    adoption_expected_supply: float = 0
    adoption_supply_growth: float = 0


@dataclass(frozen=True)
class StructuralCheckpoint:
    checkpoint_at: datetime
    candidates: tuple[StructuralTopicState, ...]
    predictions: tuple[StructuralTopicState, ...]
    rankings: dict[str, tuple[StructuralTopicState, ...]]
    outcomes: tuple[StructuralTopicOutcome, ...]


def _document(video: StructuralVideo) -> MicrotopicDocument:
    return MicrotopicDocument(
        id=video.video_id,
        title=video.title,
        description=video.description,
        entities=(),
    )


StructuralTaxonomy = Literal["v7", "v8"]


def _infer_identity(
    document: MicrotopicDocument,
    taxonomy: StructuralTaxonomy,
) -> MicrotopicIdentity | None:
    if taxonomy == "v8":
        return infer_microtopic_identity_v8(document)
    return infer_microtopic_identity_v7(document)


def _topic_key(identity: MicrotopicIdentity, taxonomy: StructuralTaxonomy) -> str:
    if taxonomy == "v8":
        return topic_key_v8(identity)
    return topic_key_v7(identity)


def _cluster_documents(
    documents: list[MicrotopicDocument],
    taxonomy: StructuralTaxonomy,
) -> list[MicrotopicCluster]:
    if taxonomy == "v8":
        return cluster_microtopics_v8(documents)
    return cluster_microtopics_v7(documents)


class StructuralCandidateIndex:
    """Candidate generator that never receives final per-video engagement."""

    def __init__(
        self,
        videos: Iterable[StructuralVideo],
        channel_snapshots: Iterable[ChannelSnapshot] = (),
        *,
        policy: StructuralReplayPolicy | None = None,
        taxonomy: StructuralTaxonomy = "v7",
    ) -> None:
        self.policy = policy or StructuralReplayPolicy()
        self.taxonomy = taxonomy
        self._topic_videos: defaultdict[str, list[StructuralVideo]] = defaultdict(list)
        self._documents: dict[str, MicrotopicDocument] = {}
        for video in videos:
            document = _document(video)
            identity = _infer_identity(document, self.taxonomy)
            if identity is None:
                continue
            key = _topic_key(identity, self.taxonomy)
            self._topic_videos[key].append(video)
            self._documents[video.video_id] = document
        for topic_videos in self._topic_videos.values():
            topic_videos.sort(key=lambda video: (_aware(video.upload_date), video.video_id))

        snapshot_rows: defaultdict[str, list[ChannelSnapshot]] = defaultdict(list)
        for snapshot in channel_snapshots:
            snapshot_rows[snapshot.channel_id].append(snapshot)
        self._snapshot_times: dict[str, tuple[datetime, ...]] = {}
        self._snapshots: dict[str, tuple[ChannelSnapshot, ...]] = {}
        for channel_id, rows in snapshot_rows.items():
            ordered = tuple(sorted(rows, key=lambda row: _aware(row.observed_at)))
            self._snapshots[channel_id] = ordered
            self._snapshot_times[channel_id] = tuple(_aware(row.observed_at) for row in ordered)

    @property
    def video_count(self) -> int:
        return sum(len(videos) for videos in self._topic_videos.values())

    @property
    def topic_identity_count(self) -> int:
        return len(self._topic_videos)

    def _channel_snapshot(self, channel_id: str, cutoff: datetime) -> ChannelSnapshot | None:
        times = self._snapshot_times.get(channel_id, ())
        index = bisect.bisect_right(times, cutoff) - 1
        if index < 0:
            return None
        return self._snapshots[channel_id][index]

    @staticmethod
    def _size_bucket(subscribers: int) -> str:
        if subscribers < 10_000:
            return "micro"
        if subscribers < 100_000:
            return "small"
        if subscribers < 1_000_000:
            return "medium"
        return "large"

    def states_at(self, observed_at: datetime) -> dict[str, StructuralTopicState]:
        cutoff = _aware(observed_at)
        history_floor = cutoff - timedelta(days=self.policy.structural_lookback_days)
        active_floor = cutoff - timedelta(days=self.policy.active_window_days)
        recent_floor = cutoff - timedelta(days=self.policy.recent_window_days)
        previous_28_floor = recent_floor - timedelta(days=28)
        states: dict[str, StructuralTopicState] = {}
        for key, topic_videos in self._topic_videos.items():
            history = [
                video
                for video in topic_videos
                if history_floor <= _aware(video.upload_date) <= cutoff
            ]
            active = [video for video in history if _aware(video.upload_date) >= active_floor]
            if not active:
                continue
            recent = [video for video in active if _aware(video.upload_date) >= recent_floor]
            previous_28 = [
                video
                for video in active
                if previous_28_floor <= _aware(video.upload_date) < recent_floor
            ]
            prior_channels = {
                video.channel_id for video in history if _aware(video.upload_date) < recent_floor
            }
            recent_channels = {video.channel_id for video in recent}
            new_recent_channels = recent_channels - prior_channels
            channels = {video.channel_id for video in active}
            cluster = next(
                (
                    candidate
                    for candidate in _cluster_documents(
                        [self._documents[video.video_id] for video in active],
                        self.taxonomy,
                    )
                    if candidate.key == key
                ),
                None,
            )
            if cluster is None:
                continue
            channel_counts = Counter(video.channel_id for video in active)
            channel_entropy = 0.0
            if len(channel_counts) > 1:
                channel_entropy = -sum(
                    (count / len(active)) * math.log(count / len(active))
                    for count in channel_counts.values()
                ) / math.log(len(channel_counts))
            channel_rows = [
                snapshot
                for channel in channels
                if (snapshot := self._channel_snapshot(channel, cutoff)) is not None
            ]
            buckets = {self._size_bucket(snapshot.subscribers) for snapshot in channel_rows}
            large_channels = {
                snapshot.channel_id for snapshot in channel_rows if snapshot.subscribers >= 250_000
            }
            previous_rate = len(previous_28) / 4
            recent_rate = len(recent)
            acceleration = (recent_rate - previous_rate) / max(previous_rate, 1)
            measurements = TopicMeasurements(
                video_count=len(active),
                video_count_24h=sum(
                    _aware(video.upload_date) >= cutoff - timedelta(hours=24) for video in active
                ),
                video_count_72h=sum(
                    _aware(video.upload_date) >= cutoff - timedelta(hours=72) for video in active
                ),
                previous_video_count_24h=sum(
                    cutoff - timedelta(hours=48)
                    <= _aware(video.upload_date)
                    < cutoff - timedelta(hours=24)
                    for video in active
                ),
                distinct_channels=len(channels),
                distinct_channels_72h=len(
                    {
                        video.channel_id
                        for video in active
                        if _aware(video.upload_date) >= cutoff - timedelta(hours=72)
                    }
                ),
                channel_size_bucket_count=len(buckets),
                large_channel_count=len(large_channels),
                aggregate_view_velocity=0,
                top_velocity_share=0,
                top_channel_share=max(channel_counts.values(), default=0) / len(active),
                median_outlier_ratio=1,
                top_outlier_ratio=1,
                search_appearances_24h=sum(
                    _aware(video.upload_date) >= cutoff - timedelta(hours=24) for video in active
                ),
                previous_search_appearances_24h=sum(
                    cutoff - timedelta(hours=48)
                    <= _aware(video.upload_date)
                    < cutoff - timedelta(hours=24)
                    for video in active
                ),
                provider_coverage_count=1,
                snapshot_coverage=0,
                entity_count=len(cluster.entities),
                audience_demand=0,
                baseline_coverage=0,
                transcript_coverage=0,
                specificity_score=cluster.specificity_score,
                topic_age_days=max(
                    0,
                    (cutoff - min(_aware(video.upload_date) for video in history)).total_seconds()
                    / 86_400,
                ),
            )
            scored = score_topic(measurements)
            research_eligible = (
                self.policy.research_minimum_videos
                <= len(active)
                <= self.policy.research_maximum_active_videos
                and len(channels) >= self.policy.research_minimum_channels
                and len(recent) >= self.policy.research_minimum_recent_videos
                and cluster.specificity_score >= self.policy.minimum_specificity
                and cluster.thesis_support_ratio >= self.policy.minimum_thesis_support
                and cluster.visible
            )
            eligible = (
                self.policy.minimum_videos <= len(active) <= self.policy.maximum_active_videos
                and len(channels) >= self.policy.minimum_channels
                and len(recent) >= self.policy.minimum_recent_videos
                and len(recent_channels) >= self.policy.minimum_recent_channels
                and len(new_recent_channels) >= self.policy.minimum_new_recent_channels
                and cluster.specificity_score >= self.policy.minimum_specificity
                and cluster.thesis_support_ratio >= self.policy.minimum_thesis_support
                and cluster.visible
            )
            states[key] = StructuralTopicState(
                topic_key=key,
                label=cluster.label,
                observed_at=cutoff,
                score=scored.score,
                specificity_score=cluster.specificity_score,
                thesis_support_ratio=cluster.thesis_support_ratio,
                eligible=eligible,
                active_video_count=len(active),
                recent_video_count=len(recent),
                previous_28d_video_count=len(previous_28),
                distinct_channel_count=len(channels),
                recent_channel_count=len(recent_channels),
                new_recent_channel_count=len(new_recent_channels),
                acceleration=round(acceleration, 4),
                large_channel_count=len(large_channels),
                channel_size_bucket_count=len(buckets),
                member_video_ids=tuple(video.video_id for video in active),
                member_channel_ids=tuple(sorted(channels)),
                evidence_titles=tuple(video.title for video in active[-5:]),
                research_eligible=research_eligible,
                channel_entropy=round(channel_entropy, 4),
                topic_age_days=round(measurements.topic_age_days, 3),
            )
        return states

    def rankings_at(
        self,
        observed_at: datetime,
        *,
        blocked_topics: set[str] | None = None,
    ) -> dict[str, tuple[StructuralTopicState, ...]]:
        blocked = blocked_topics or set()
        candidates = [
            state
            for state in self.states_at(observed_at).values()
            if state.eligible and state.topic_key not in blocked
        ]
        random_key = lambda state: sha256(  # noqa: E731 - compact deterministic rank key.
            f"{_aware(observed_at).isoformat()}|{state.topic_key}".encode()
        ).hexdigest()
        rankings = {
            "method": sorted(candidates, key=lambda state: (-state.score, state.topic_key)),
            "supply": sorted(
                candidates,
                key=lambda state: (-state.recent_video_count, state.topic_key),
            ),
            "acceleration": sorted(
                candidates,
                key=lambda state: (-state.acceleration, state.topic_key),
            ),
            "channels": sorted(
                candidates,
                key=lambda state: (-state.distinct_channel_count, state.topic_key),
            ),
            "random": sorted(candidates, key=random_key),
        }
        return {name: tuple(rows[: self.policy.top_k]) for name, rows in rankings.items()}


def _exposure_band(days: int) -> tuple[int, int | None]:
    for lower, upper in (
        (0, 7),
        (8, 14),
        (15, 30),
        (31, 60),
        (61, 120),
        (121, 240),
        (241, None),
    ):
        if days >= lower and (upper is None or days <= upper):
            return lower, upper
    raise AssertionError("unreachable exposure band")


class StructuralOutcomeEvaluator:
    """Future evaluator instantiated only after candidate rankings are frozen."""

    def __init__(
        self,
        ai_videos: Iterable[StructuralVideo],
        ai_outcomes: Iterable[OutcomeVideo],
        baseline_videos: Iterable[OutcomeVideo],
        *,
        policy: StructuralReplayPolicy | None = None,
        taxonomy: StructuralTaxonomy = "v7",
    ) -> None:
        self.policy = policy or StructuralReplayPolicy()
        self.taxonomy = taxonomy
        self._topic_videos: defaultdict[str, list[StructuralVideo]] = defaultdict(list)
        for video in ai_videos:
            identity = _infer_identity(_document(video), self.taxonomy)
            if identity is not None:
                self._topic_videos[_topic_key(identity, self.taxonomy)].append(video)
        for rows in self._topic_videos.values():
            rows.sort(key=lambda video: (_aware(video.upload_date), video.video_id))
        self._outcomes = {video.video_id: video for video in ai_outcomes}
        self._baseline_by_channel: defaultdict[str, list[OutcomeVideo]] = defaultdict(list)
        for baseline_video in baseline_videos:
            self._baseline_by_channel[baseline_video.channel_id].append(baseline_video)
        for baseline_rows in self._baseline_by_channel.values():
            baseline_rows.sort(key=lambda video: (_aware(video.upload_date), video.video_id))

    def _outlier_ratio(self, video: OutcomeVideo) -> float | None:
        band = _exposure_band(video.exposure_age_days)
        floor = _aware(video.upload_date) - timedelta(days=365)
        comparisons = [
            candidate.final_view_count
            for candidate in self._baseline_by_channel.get(video.channel_id, ())
            if candidate.video_id != video.video_id
            and floor <= _aware(candidate.upload_date) < _aware(video.upload_date)
            and _exposure_band(candidate.exposure_age_days) == band
        ]
        if len(comparisons) < 5:
            return None
        return video.final_view_count / max(float(median(comparisons)), 1)

    def evaluate(
        self,
        state: StructuralTopicState,
    ) -> StructuralTopicOutcome:
        cutoff = _aware(state.observed_at)
        future_end = cutoff + timedelta(days=self.policy.outcome_horizon_days)
        topic_videos = self._topic_videos.get(state.topic_key, ())
        prior = [
            video
            for video in topic_videos
            if cutoff - timedelta(days=180) <= _aware(video.upload_date) <= cutoff
        ]
        future = [
            video for video in topic_videos if cutoff < _aware(video.upload_date) <= future_end
        ]
        prior_channels = {video.channel_id for video in prior}
        previous_28_count = sum(
            _aware(video.upload_date) >= cutoff - timedelta(days=28) for video in prior
        )
        expected_supply = max(previous_28_count / 4, 1.0) * 6
        adoption_expected_supply = max(previous_28_count / 4 * 6, 2.0)
        required_supply = expected_supply * self.policy.supply_growth_threshold
        ratios: dict[str, float | None] = {
            video.video_id: self._outlier_ratio(self._outcomes[video.video_id])
            if video.video_id in self._outcomes
            else None
            for video in future
        }

        fired_at: datetime | None = None
        adoption_fired_at: datetime | None = None
        performance_fired_at: datetime | None = None
        for index in range(len(future)):
            prefix = future[: index + 1]
            prefix_ratios = [
                ratio for video in prefix if (ratio := ratios[video.video_id]) is not None
            ]
            new_channels = {video.channel_id for video in prefix} - prior_channels
            new_share = (
                sum(video.channel_id in new_channels for video in prefix) / len(prefix)
                if prefix
                else 0
            )
            coverage = len(prefix_ratios) / len(prefix) if prefix else 0
            if adoption_fired_at is None and (
                len(prefix)
                >= max(
                    self.policy.adoption_minimum_future_videos,
                    math.ceil(
                        adoption_expected_supply * self.policy.adoption_supply_growth_threshold
                    ),
                )
                and len(new_channels) >= self.policy.adoption_minimum_new_future_channels
                and new_share >= self.policy.adoption_minimum_new_channel_share
            ):
                adoption_fired_at = _aware(prefix[-1].upload_date)
            if performance_fired_at is None and (
                len(prefix) >= self.policy.performance_minimum_future_videos
                and coverage >= self.policy.performance_minimum_baseline_coverage
                and sum(
                    ratio >= self.policy.performance_minimum_outlier_ratio
                    for ratio in prefix_ratios
                )
                >= self.policy.performance_minimum_outlier_videos
                and prefix_ratios
                and median(prefix_ratios) >= self.policy.performance_minimum_median_outlier_ratio
            ):
                performance_fired_at = _aware(prefix[-1].upload_date)
            if (
                len(prefix) >= max(self.policy.minimum_future_videos, math.ceil(required_supply))
                and len(new_channels) >= self.policy.minimum_new_future_channels
                and new_share >= self.policy.minimum_new_channel_share
                and coverage >= self.policy.minimum_outcome_baseline_coverage
                and sum(ratio >= self.policy.minimum_outlier_ratio for ratio in prefix_ratios)
                >= self.policy.minimum_outlier_videos
                and prefix_ratios
                and median(prefix_ratios) >= self.policy.minimum_median_outlier_ratio
            ):
                fired_at = _aware(prefix[-1].upload_date)
                break

        valid_ratios = [ratio for ratio in ratios.values() if ratio is not None]
        new_future_channels = {video.channel_id for video in future} - prior_channels
        new_channel_share = (
            sum(video.channel_id in new_future_channels for video in future) / len(future)
            if future
            else 0
        )
        return StructuralTopicOutcome(
            topic_key=state.topic_key,
            fired=fired_at is not None,
            fired_at=fired_at,
            lead_days=round((fired_at - cutoff).total_seconds() / 86_400, 2) if fired_at else None,
            future_video_count=len(future),
            expected_future_supply=round(expected_supply, 3),
            supply_growth=round(len(future) / max(expected_supply, 1), 3),
            new_future_channel_count=len(new_future_channels),
            new_channel_share=round(new_channel_share, 4),
            baseline_coverage=round(len(valid_ratios) / len(future), 4) if future else 0,
            outlier_video_count=sum(
                ratio >= self.policy.minimum_outlier_ratio for ratio in valid_ratios
            ),
            median_outlier_ratio=round(float(median(valid_ratios)), 4) if valid_ratios else None,
            adoption_fired=adoption_fired_at is not None,
            adoption_fired_at=adoption_fired_at,
            adoption_lead_days=(
                round((adoption_fired_at - cutoff).total_seconds() / 86_400, 2)
                if adoption_fired_at
                else None
            ),
            performance_fired=performance_fired_at is not None,
            performance_fired_at=performance_fired_at,
            performance_lead_days=(
                round((performance_fired_at - cutoff).total_seconds() / 86_400, 2)
                if performance_fired_at
                else None
            ),
            adoption_expected_supply=round(adoption_expected_supply, 3),
            adoption_supply_growth=round(
                len(future) / max(adoption_expected_supply, 1),
                3,
            ),
        )


def build_structural_checkpoints(
    candidate_index: StructuralCandidateIndex,
    outcome_evaluator: StructuralOutcomeEvaluator,
    checkpoints: Iterable[datetime],
) -> tuple[StructuralCheckpoint, ...]:
    last_episode: dict[str, datetime] = {}
    rows: list[StructuralCheckpoint] = []
    cooldown = timedelta(days=candidate_index.policy.episode_cooldown_days)
    for checkpoint_at in checkpoints:
        cutoff = _aware(checkpoint_at)
        blocked = {
            topic_key for topic_key, last_at in last_episode.items() if cutoff - last_at < cooldown
        }
        rankings = candidate_index.rankings_at(cutoff, blocked_topics=blocked)
        candidates_by_key = {
            state.topic_key: state
            for state in candidate_index.states_at(cutoff).values()
            if state.eligible and state.topic_key not in blocked
        }
        candidates = tuple(sorted(candidates_by_key.values(), key=lambda state: state.topic_key))
        for candidate in candidates:
            last_episode[candidate.topic_key] = cutoff
        outcomes = tuple(outcome_evaluator.evaluate(candidate) for candidate in candidates)
        rows.append(
            StructuralCheckpoint(
                checkpoint_at=cutoff,
                candidates=candidates,
                predictions=rankings["method"],
                rankings=rankings,
                outcomes=outcomes,
            )
        )
    return tuple(rows)


__all__ = [
    "ChannelSnapshot",
    "StructuralCandidateIndex",
    "StructuralCheckpoint",
    "StructuralOutcomeEvaluator",
    "StructuralReplayPolicy",
    "StructuralTopicOutcome",
    "StructuralTopicState",
    "StructuralTaxonomy",
    "build_structural_checkpoints",
]
