from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Literal

from packages.clustering import MicrotopicDocument, cluster_microtopics_v6, normalize_entities
from packages.scoring import TopicMeasurements, score_topic

EXTERNAL_REPLAY_VERSION = "external-youtube-timeseries-replay-v3-v6-taxonomy"
OUTCOME_VERSION = "external-blind-supply-lift-30d-v1"

_RELEVANCE_PATTERN = re.compile(
    r"(?i)(?<![\w])(?:"
    r"ai|a\.i\.|llm|large language model|chatgpt|openai|"
    r"gpt-?[234](?:\.5|o)?|o1(?:-preview)?|copilot|"
    r"google gemini|gemini(?: ai| [0-9](?:\.[0-9])?)?|"
    r"claude (?:ai|[23](?:\.5)?|sonnet|opus|haiku)|anthropic|"
    r"claude code|grok(?: [123])?|deepseek|qwen|"
    r"cursor ai|cursor agent|windsurf ai|openclaw|comfyui|ollama|"
    r"sora(?: ai| video)?|veo(?: ai| video| [23])?|higgsfield|"
    r"midjourney|stable diffusion|artificial intelligence|"
    r"machine learning|deep learning|neural networks?|generative ai|ai agents?|"
    r"text-to-video|image-to-video|deepfakes?"
    r")(?![\w])"
)
_WINDOWS_SECONDS = {
    "1h": 3_600,
    "6h": 6 * 3_600,
    "24h": 24 * 3_600,
    "72h": 72 * 3_600,
    "7d": 7 * 24 * 3_600,
}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ExternalViewSnapshot:
    views: int
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.views < 0:
            raise ValueError("views must be nonnegative")


@dataclass(frozen=True)
class ExternalVideo:
    video_id: str
    title: str
    channel_id: str
    subscriber_count: int
    category: str
    duration_seconds: float | None
    snapshots: tuple[ExternalViewSnapshot, ...]
    description: str = ""
    published_at_override: datetime | None = None

    def __post_init__(self) -> None:
        if not self.video_id.strip() or not self.channel_id.strip():
            raise ValueError("video and channel ids must not be empty")
        if self.subscriber_count < 0:
            raise ValueError("subscriber_count must be nonnegative")
        if not self.snapshots:
            raise ValueError("at least one snapshot is required")
        ordered = tuple(sorted(self.snapshots, key=lambda row: _aware(row.observed_at)))
        if ordered != self.snapshots:
            raise ValueError("snapshots must be chronological")

    @property
    def published_at(self) -> datetime:
        if self.published_at_override is not None:
            return _aware(self.published_at_override)
        # The source collector selects videos published on the previous UTC day.
        # It did not persist the exact publishedAt value, so the first observation
        # minus one day is the conservative, documented approximation.
        return _aware(self.snapshots[0].observed_at) - timedelta(days=1)


@dataclass(frozen=True)
class ExternalTopicState:
    topic_key: str
    label: str
    observed_at: datetime
    score: float
    lifecycle_stage: str
    confidence: str
    actionable: bool
    specificity_score: float
    video_count: int
    video_count_72h: int
    distinct_channels: int
    distinct_channels_72h: int
    aggregate_view_velocity: float
    median_outlier_ratio: float
    top_outlier_ratio: float
    member_video_ids: tuple[str, ...]
    member_titles: tuple[str, ...]


@dataclass(frozen=True)
class ExternalTopicOutcome:
    topic_key: str
    fired: bool
    fired_at: datetime | None
    lead_days: float | None
    max_supply_growth: float
    peak_lift: float


@dataclass(frozen=True)
class ExternalCheckpointResult:
    checkpoint_at: datetime
    candidate_count: int
    predictions: tuple[ExternalTopicState, ...]
    outcomes: tuple[ExternalTopicOutcome, ...]


@dataclass(frozen=True)
class ExternalReplayPolicy:
    history_window_days: int = 30
    outcome_horizon_days: int = 30
    top_k: int = 10
    supply_growth_threshold: float = 3
    lift_threshold: float = 3


def _looks_english(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(char.isascii() for char in letters)
    return ascii_letters / len(letters) >= 0.8


def _matches_vertical(value: str) -> bool:
    # A raw substring check for "ai" silently matches unrelated words such as
    # "Laine". Keep vertical admission token-aware; archive-specific language
    # and category validation belongs in the dataset adapter/protocol.
    return _RELEVANCE_PATTERN.search(value) is not None


def _channel_bucket(subscribers: int) -> str:
    if subscribers < 10_000:
        return "small"
    if subscribers < 100_000:
        return "medium"
    if subscribers < 1_000_000:
        return "large"
    return "mega"


def _latest_snapshots(
    video: ExternalVideo, observed_at: datetime
) -> tuple[ExternalViewSnapshot, ...]:
    cutoff = _aware(observed_at)
    return tuple(row for row in video.snapshots if _aware(row.observed_at) <= cutoff)


class ExternalTimeseriesReplay:
    """Leakage-safe replay of the deterministic production topic method.

    Titles, channel metadata and view observations at or before a checkpoint are
    feature inputs. Later view observations and later-published videos are read
    only by the blind outcome pass.
    """

    def __init__(
        self,
        videos: Iterable[ExternalVideo],
        *,
        eligible_categories: frozenset[str] | None = None,
    ) -> None:
        self._videos = tuple(videos)
        self._eligible_categories = eligible_categories
        self._by_id = {video.video_id: video for video in self._videos}
        self._by_channel: dict[str, tuple[ExternalVideo, ...]] = {
            channel_id: tuple(rows)
            for channel_id, rows in self._group_by_channel(self._videos).items()
        }
        self._documents: dict[str, MicrotopicDocument] = {}
        self._topic_key_by_video: dict[str, str] = {}
        self._topic_first_seen: dict[str, datetime] = {}
        self._prepare_topic_memberships()
        self._state_cache: dict[datetime, dict[str, ExternalTopicState]] = {}
        self._outlier_cache: dict[tuple[str, datetime], tuple[float, bool]] = {}
        self._age_baseline_cache: dict[tuple[str, str, datetime], tuple[float | None, int]] = {}
        self._age_curve_cache: dict[tuple[str, datetime], tuple[float | None, int]] = {}

    @staticmethod
    def _group_by_channel(
        videos: Iterable[ExternalVideo],
    ) -> defaultdict[str, list[ExternalVideo]]:
        grouped: defaultdict[str, list[ExternalVideo]] = defaultdict(list)
        for video in videos:
            grouped[video.channel_id].append(video)
        return grouped

    def _prepare_topic_memberships(self) -> None:
        for video in self._videos:
            if (
                self._eligible_categories is not None
                and video.category not in self._eligible_categories
            ):
                continue
            if not _looks_english(video.title) or not _matches_vertical(video.title):
                continue
            entities = tuple(normalize_entities(video.title, ""))
            document = MicrotopicDocument(
                id=video.video_id,
                title=video.title,
                description=video.description,
                entities=entities,
            )
            clusters = cluster_microtopics_v6([document])
            if not clusters:
                continue
            key = clusters[0].key
            self._documents[video.video_id] = document
            self._topic_key_by_video[video.video_id] = key
            first_seen = self._topic_first_seen.get(key)
            if first_seen is None or video.published_at < first_seen:
                self._topic_first_seen[key] = video.published_at

    @property
    def eligible_video_count(self) -> int:
        return len(self._documents)

    @property
    def topic_identity_count(self) -> int:
        return len(set(self._topic_key_by_video.values()))

    def _closest_age_sample(
        self,
        video: ExternalVideo,
        *,
        target_age_seconds: int,
        observed_at: datetime,
    ) -> ExternalViewSnapshot | None:
        candidates = []
        for row in _latest_snapshots(video, observed_at):
            age = (_aware(row.observed_at) - video.published_at).total_seconds()
            if target_age_seconds * 0.5 <= age <= target_age_seconds * 1.75:
                candidates.append((abs(age - target_age_seconds), row))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def _channel_age_baseline(
        self,
        channel_id: str,
        *,
        window: str,
        observed_at: datetime,
    ) -> tuple[float | None, int]:
        cache_key = (channel_id, window, _aware(observed_at))
        cached = self._age_baseline_cache.get(cache_key)
        if cached is not None:
            return cached
        samples = []
        for video in self._by_channel.get(channel_id, ()):
            if video.published_at > _aware(observed_at):
                continue
            row = self._closest_age_sample(
                video,
                target_age_seconds=_WINDOWS_SECONDS[window],
                observed_at=observed_at,
            )
            if row is not None:
                samples.append(float(row.views))
        result = (median(samples), len(samples)) if samples else (None, 0)
        self._age_baseline_cache[cache_key] = result
        return result

    def _channel_age_curve(
        self,
        channel_id: str,
        *,
        observed_at: datetime,
    ) -> tuple[float | None, int]:
        cache_key = (channel_id, _aware(observed_at))
        cached = self._age_curve_cache.get(cache_key)
        if cached is not None:
            return cached
        samples = []
        for video in self._by_channel.get(channel_id, ()):
            rows = _latest_snapshots(video, observed_at)
            if not rows:
                continue
            latest = rows[-1]
            age_hours = max(
                (_aware(latest.observed_at) - video.published_at).total_seconds() / 3_600,
                1,
            )
            if age_hours >= 3:
                samples.append(latest.views / age_hours**0.72)
        result = (median(samples), len(samples)) if samples else (None, 0)
        self._age_curve_cache[cache_key] = result
        return result

    def _video_feature(
        self,
        video: ExternalVideo,
        observed_at: datetime,
    ) -> tuple[float, float, bool] | None:
        cutoff = _aware(observed_at)
        cache_key = (video.video_id, cutoff)
        cached = self._outlier_cache.get(cache_key)
        rows = _latest_snapshots(video, cutoff)
        if not rows:
            return None
        latest = rows[-1]
        velocity = 0.0
        if len(rows) >= 2:
            previous = rows[-2]
            hours = max(
                (_aware(latest.observed_at) - _aware(previous.observed_at)).total_seconds() / 3_600,
                0.01,
            )
            velocity = max(0.0, (latest.views - previous.views) / hours)
        if cached is not None:
            return velocity, cached[0], cached[1]

        age_seconds = max(
            (_aware(latest.observed_at) - video.published_at).total_seconds(),
            1,
        )
        window, _ = min(
            _WINDOWS_SECONDS.items(),
            key=lambda item: abs(item[1] - age_seconds),
        )
        baseline, sample_size = self._channel_age_baseline(
            video.channel_id,
            window=window,
            observed_at=cutoff,
        )
        calibrated = False
        if baseline is not None and baseline > 0 and sample_size >= 3:
            ratio = latest.views / baseline
            calibrated = True
        else:
            curve, curve_size = self._channel_age_curve(
                video.channel_id,
                observed_at=cutoff,
            )
            if curve is not None and curve > 0 and curve_size >= 5:
                ratio = latest.views / max(curve * (age_seconds / 3_600) ** 0.72, 1)
                calibrated = True
            else:
                ratio = 1.0
        self._outlier_cache[cache_key] = (ratio, calibrated)
        return velocity, ratio, calibrated

    def states_at(self, observed_at: datetime) -> dict[str, ExternalTopicState]:
        cutoff = _aware(observed_at)
        cached = self._state_cache.get(cutoff)
        if cached is not None:
            return cached
        earliest = cutoff - timedelta(days=30)
        grouped: defaultdict[str, list[ExternalVideo]] = defaultdict(list)
        for video_id, key in self._topic_key_by_video.items():
            video = self._by_id[video_id]
            if earliest <= video.published_at <= cutoff and _latest_snapshots(video, cutoff):
                grouped[key].append(video)

        states: dict[str, ExternalTopicState] = {}
        for key, members in grouped.items():
            documents = [self._documents[video.video_id] for video in members]
            clusters = cluster_microtopics_v6(documents)
            cluster = next((row for row in clusters if row.key == key), None)
            if cluster is None or not cluster.visible:
                continue
            features = [(video, self._video_feature(video, cutoff)) for video in members]
            prepared = [(video, feature) for video, feature in features if feature is not None]
            if not prepared:
                continue
            recent_24 = [
                video for video, _ in prepared if video.published_at >= cutoff - timedelta(hours=24)
            ]
            recent_72 = [
                video for video, _ in prepared if video.published_at >= cutoff - timedelta(hours=72)
            ]
            previous_24 = [
                video
                for video, _ in prepared
                if cutoff - timedelta(hours=48) <= video.published_at < cutoff - timedelta(hours=24)
            ]
            velocities = [feature[0] for _, feature in prepared]
            outliers = [feature[1] for _, feature in prepared]
            velocity_median = median(velocities) if velocities else 0
            velocity_cap = max(velocity_median * 4, 1)
            aggregate_velocity = sum(min(value, velocity_cap) for value in velocities)
            total_velocity = sum(velocities)
            channel_counts = Counter(video.channel_id for video, _ in prepared)
            channel_ids = set(channel_counts)
            calibrated_channels = {
                channel_id
                for channel_id in channel_ids
                if self._channel_age_curve(channel_id, observed_at=cutoff)[1] >= 5
            }
            measurements = TopicMeasurements(
                video_count=len(prepared),
                video_count_24h=len(recent_24),
                video_count_72h=len(recent_72),
                previous_video_count_24h=len(previous_24),
                distinct_channels=len(channel_ids),
                distinct_channels_72h=len({video.channel_id for video in recent_72}),
                channel_size_bucket_count=len(
                    {_channel_bucket(video.subscriber_count) for video, _ in prepared}
                ),
                large_channel_count=len(
                    {video.channel_id for video, _ in prepared if video.subscriber_count >= 100_000}
                ),
                aggregate_view_velocity=aggregate_velocity,
                top_velocity_share=max(velocities, default=0) / max(total_velocity, 1),
                top_channel_share=max(channel_counts.values(), default=0) / max(len(prepared), 1),
                median_outlier_ratio=median(outliers),
                top_outlier_ratio=max(outliers, default=1),
                search_appearances_24h=len(recent_24),
                previous_search_appearances_24h=len(previous_24),
                provider_coverage_count=1,
                snapshot_coverage=1,
                entity_count=len(
                    {entity for document in documents for entity in document.entities}
                ),
                audience_demand=0,
                baseline_coverage=len(calibrated_channels) / max(len(channel_ids), 1),
                transcript_coverage=0,
                specificity_score=cluster.specificity_score,
                topic_age_days=max(
                    0,
                    (cutoff - self._topic_first_seen[key]).total_seconds() / 86_400,
                ),
            )
            scored = score_topic(measurements)
            fresh_confirmation = (
                measurements.video_count_72h >= 2 and measurements.distinct_channels_72h >= 2
            )
            evidence_backed_watch = (
                scored.lifecycle_stage == "Seed"
                and measurements.video_count_72h >= 1
                and measurements.video_count >= 3
                and measurements.distinct_channels >= 3
            )
            actionable = (
                cluster.specificity_score >= 70
                and cluster.thesis_support_ratio >= 0.8
                and (fresh_confirmation or evidence_backed_watch)
                and measurements.distinct_channels >= 3
                and measurements.baseline_coverage >= 0.5
                and (
                    measurements.median_outlier_ratio >= 1.1
                    or (
                        measurements.top_outlier_ratio >= 1.8
                        and measurements.top_velocity_share <= 0.75
                    )
                )
                and (scored.score >= 30 or (evidence_backed_watch and scored.score >= 25))
                and scored.lifecycle_stage not in {"Saturated", "Declining"}
            )
            states[key] = ExternalTopicState(
                topic_key=key,
                label=cluster.label,
                observed_at=cutoff,
                score=scored.score,
                lifecycle_stage=scored.lifecycle_stage,
                confidence=scored.confidence,
                actionable=actionable,
                specificity_score=cluster.specificity_score,
                video_count=len(prepared),
                video_count_72h=len(recent_72),
                distinct_channels=len(channel_ids),
                distinct_channels_72h=measurements.distinct_channels_72h,
                aggregate_view_velocity=round(aggregate_velocity, 2),
                median_outlier_ratio=round(measurements.median_outlier_ratio, 4),
                top_outlier_ratio=round(measurements.top_outlier_ratio, 4),
                member_video_ids=tuple(video.video_id for video, _ in prepared),
                member_titles=tuple(video.title for video, _ in prepared),
            )
        self._state_cache[cutoff] = states
        return states

    def label_checkpoint(
        self,
        checkpoint_at: datetime,
        *,
        policy: ExternalReplayPolicy | None = None,
    ) -> tuple[ExternalCheckpointResult, dict[str, tuple[ExternalTopicState, ...]]]:
        selected = policy or ExternalReplayPolicy()
        checkpoint = _aware(checkpoint_at)
        baseline_states = self.states_at(checkpoint)
        visible_candidates = list(baseline_states.values())
        candidates = [row for row in baseline_states.values() if row.actionable]
        rankings: dict[str, tuple[ExternalTopicState, ...]] = {
            "method": tuple(
                sorted(candidates, key=lambda row: (-row.score, row.topic_key))[: selected.top_k]
            ),
            "supply": tuple(
                sorted(
                    visible_candidates,
                    key=lambda row: (
                        -row.video_count_72h,
                        -row.distinct_channels_72h,
                        row.topic_key,
                    ),
                )[: selected.top_k]
            ),
            "velocity": tuple(
                sorted(
                    visible_candidates,
                    key=lambda row: (-row.aggregate_view_velocity, row.topic_key),
                )[: selected.top_k]
            ),
            "outlier": tuple(
                sorted(
                    visible_candidates,
                    key=lambda row: (-row.median_outlier_ratio, row.topic_key),
                )[: selected.top_k]
            ),
        }
        observations = [
            self.states_at(checkpoint + timedelta(days=offset))
            for offset in range(1, selected.outcome_horizon_days + 1)
        ]
        outcomes = []
        for baseline in visible_candidates:
            baseline_supply = max(baseline.video_count_72h, 1)
            fired_at = None
            max_supply_growth = 0.0
            peak_lift = 0.0
            for daily_states in observations:
                future = daily_states.get(baseline.topic_key)
                if future is None:
                    continue
                supply_growth = future.video_count_72h / baseline_supply
                max_supply_growth = max(max_supply_growth, supply_growth)
                peak_lift = max(peak_lift, future.median_outlier_ratio)
                if (
                    fired_at is None
                    and supply_growth >= selected.supply_growth_threshold
                    and future.median_outlier_ratio >= selected.lift_threshold
                ):
                    fired_at = future.observed_at
            outcomes.append(
                ExternalTopicOutcome(
                    topic_key=baseline.topic_key,
                    fired=fired_at is not None,
                    fired_at=fired_at,
                    lead_days=(
                        round((fired_at - checkpoint).total_seconds() / 86_400, 2)
                        if fired_at is not None
                        else None
                    ),
                    max_supply_growth=round(max_supply_growth, 4),
                    peak_lift=round(peak_lift, 4),
                )
            )
        return (
            ExternalCheckpointResult(
                checkpoint_at=checkpoint,
                candidate_count=len(candidates),
                predictions=rankings["method"],
                outcomes=tuple(outcomes),
            ),
            rankings,
        )


def summarize_external_results(
    results: Iterable[tuple[ExternalCheckpointResult, dict[str, tuple[ExternalTopicState, ...]]]],
    *,
    split: Literal["train", "holdout", "all"],
) -> dict[str, object]:
    rows = list(results)
    method_names = ("method", "supply", "velocity", "outlier")
    aggregate: dict[str, object] = {
        "split": split,
        "checkpoint_count": len(rows),
        "candidate_topics": sum(len(result.outcomes) for result, _ in rows),
        "actionable_topics": sum(result.candidate_count for result, _ in rows),
    }
    all_fired = 0
    all_candidates = 0
    ranking_metrics: dict[str, object] = {}
    for method in method_names:
        selected = 0
        fired = 0
        lead_days = []
        for result, rankings in rows:
            outcome_map = {row.topic_key: row for row in result.outcomes}
            selected_rows = result.predictions if method == "method" else rankings[method]
            selected += len(selected_rows)
            for prediction in selected_rows:
                outcome = outcome_map[prediction.topic_key]
                if outcome.fired:
                    fired += 1
                    if outcome.lead_days is not None:
                        lead_days.append(outcome.lead_days)
        ranking_metrics[method] = {
            "predictions": selected,
            "fired": fired,
            "precision_at_10_percent": (round(fired / selected * 100, 1) if selected else None),
            "median_lead_days": round(float(median(lead_days)), 2) if lead_days else None,
        }
    for result, _ in rows:
        all_candidates += len(result.outcomes)
        all_fired += sum(row.fired for row in result.outcomes)
    aggregate["rankings"] = ranking_metrics
    aggregate["candidate_base_rate_percent"] = (
        round(all_fired / all_candidates * 100, 1) if all_candidates else 0
    )
    aggregate["fired_candidate_topics"] = all_fired
    return aggregate


__all__ = [
    "EXTERNAL_REPLAY_VERSION",
    "OUTCOME_VERSION",
    "ExternalCheckpointResult",
    "ExternalReplayPolicy",
    "ExternalTimeseriesReplay",
    "ExternalTopicOutcome",
    "ExternalTopicState",
    "ExternalVideo",
    "ExternalViewSnapshot",
    "summarize_external_results",
]
