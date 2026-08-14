from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from statistics import median
from typing import Literal

from packages.backtest.global_trending import GlobalTrendingObservation
from packages.clustering import MicrotopicDocument, cluster_microtopics_v6, normalize_entities
from packages.scoring import TopicMeasurements, score_topic

CROSS_MARKET_REPLAY_VERSION = "global-cross-market-replay-v1"
CROSS_MARKET_OUTCOME_VERSION = "cross-market-new-supply-country-diffusion-21d-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class CrossMarketPolicy:
    lookback_days: int = 30
    recent_supply_days: int = 7
    outcome_horizon_days: int = 21
    top_k: int = 10
    minimum_videos: int = 3
    minimum_channels: int = 3
    minimum_recent_channels: int = 2
    supply_growth_threshold: float = 3
    minimum_new_channels: int = 3
    minimum_new_countries: int = 5
    minimum_total_countries: int = 8
    minimum_new_video_share: float = 0.5


@dataclass(frozen=True)
class CrossMarketVideo:
    video_id: str
    title: str
    description: str
    channel_id: str
    category_id: str
    published_at: datetime
    first_seen_at: datetime
    observations: tuple[GlobalTrendingObservation, ...]


@dataclass(frozen=True)
class CrossMarketTopicState:
    topic_key: str
    label: str
    observed_at: datetime
    score: float
    specificity_score: float
    eligible: bool
    video_count_30d: int
    video_count_7d: int
    distinct_channels_30d: int
    distinct_channels_7d: int
    country_count_30d: int
    aggregate_view_velocity: float
    median_view_growth: float
    member_video_ids: tuple[str, ...]
    member_channel_ids: tuple[str, ...]
    country_codes: tuple[str, ...]
    evidence_titles: tuple[str, ...]


@dataclass(frozen=True)
class CrossMarketOutcome:
    topic_key: str
    fired: bool
    fired_at: datetime | None
    lead_days: float | None
    max_supply_growth: float
    max_new_channels: int
    max_new_countries: int
    max_country_count: int
    max_new_video_share: float


@dataclass(frozen=True)
class CrossMarketCheckpoint:
    checkpoint_at: datetime
    candidate_count: int
    candidates: tuple[CrossMarketTopicState, ...]
    predictions: tuple[CrossMarketTopicState, ...]
    outcomes: tuple[CrossMarketOutcome, ...]
    rankings: dict[str, tuple[CrossMarketTopicState, ...]]
    full_rankings: dict[str, tuple[CrossMarketTopicState, ...]]


class CrossMarketReplay:
    """Point-in-time replay over global Trending observations.

    Topic features read only observations at or before a checkpoint. Future rows
    are accessed only by `_outcome`, after baseline states and rankings exist.
    """

    def __init__(
        self,
        observations: Iterable[GlobalTrendingObservation],
        *,
        policy: CrossMarketPolicy | None = None,
    ) -> None:
        self.policy = policy or CrossMarketPolicy()
        grouped: defaultdict[str, list[GlobalTrendingObservation]] = defaultdict(list)
        for row in observations:
            grouped[row.video_id].append(row)
        self._videos: dict[str, CrossMarketVideo] = {}
        self._documents: dict[str, MicrotopicDocument] = {}
        self._topic_key_by_video: dict[str, str] = {}
        self._topic_videos: defaultdict[str, list[CrossMarketVideo]] = defaultdict(list)
        observation_times: set[datetime] = set()
        for video_id, raw_rows in grouped.items():
            rows = tuple(sorted(raw_rows, key=lambda item: _aware(item.observed_at)))
            first = rows[0]
            video = CrossMarketVideo(
                video_id=video_id,
                title=first.title,
                description=first.description,
                channel_id=first.channel_id,
                category_id=first.category_id,
                published_at=_aware(first.published_at),
                first_seen_at=_aware(first.observed_at),
                observations=rows,
            )
            document = MicrotopicDocument(
                id=video_id,
                title=video.title,
                description=video.description,
                entities=tuple(normalize_entities(video.title, video.description)),
            )
            clusters = cluster_microtopics_v6([document])
            if not clusters:
                continue
            key = clusters[0].key
            self._videos[video_id] = video
            self._documents[video_id] = document
            self._topic_key_by_video[video_id] = key
            self._topic_videos[key].append(video)
            observation_times.update(_aware(row.observed_at) for row in rows)
        self._observation_times = tuple(sorted(observation_times))
        self._state_cache: dict[datetime, dict[str, CrossMarketTopicState]] = {}

    @property
    def video_count(self) -> int:
        return len(self._videos)

    @property
    def topic_identity_count(self) -> int:
        return len(self._topic_videos)

    @property
    def first_observed_at(self) -> datetime | None:
        return self._observation_times[0] if self._observation_times else None

    @property
    def last_observed_at(self) -> datetime | None:
        return self._observation_times[-1] if self._observation_times else None

    @staticmethod
    def _rows_at(
        video: CrossMarketVideo,
        cutoff: datetime,
        *,
        earliest: datetime | None = None,
    ) -> tuple[GlobalTrendingObservation, ...]:
        return tuple(
            row
            for row in video.observations
            if _aware(row.observed_at) <= cutoff
            and (earliest is None or _aware(row.observed_at) >= earliest)
        )

    def _video_view_features(
        self,
        video: CrossMarketVideo,
        cutoff: datetime,
    ) -> tuple[float, float]:
        by_time: dict[datetime, int] = {}
        for row in self._rows_at(video, cutoff):
            observed = _aware(row.observed_at)
            by_time[observed] = max(row.view_count, by_time.get(observed, 0))
        ordered = sorted(by_time.items())
        if not ordered:
            return 0.0, 1.0
        first_views = max(ordered[0][1], 1)
        growth = ordered[-1][1] / first_views
        if len(ordered) < 2:
            return 0.0, growth
        elapsed_hours = max((ordered[-1][0] - ordered[-2][0]).total_seconds() / 3_600, 0.01)
        velocity = max(0.0, (ordered[-1][1] - ordered[-2][1]) / elapsed_hours)
        return velocity, growth

    def states_at(self, observed_at: datetime) -> dict[str, CrossMarketTopicState]:
        cutoff = _aware(observed_at)
        cached = self._state_cache.get(cutoff)
        if cached is not None:
            return cached
        earliest = cutoff - timedelta(days=self.policy.lookback_days)
        recent_floor = cutoff - timedelta(days=self.policy.recent_supply_days)
        states: dict[str, CrossMarketTopicState] = {}
        for key, topic_videos in self._topic_videos.items():
            members = [
                video
                for video in topic_videos
                if earliest <= video.published_at <= cutoff and video.first_seen_at <= cutoff
            ]
            if not members:
                continue
            documents = [self._documents[video.video_id] for video in members]
            cluster = next(
                (
                    candidate
                    for candidate in cluster_microtopics_v6(documents)
                    if candidate.key == key
                ),
                None,
            )
            if cluster is None or not cluster.visible:
                continue
            recent = [video for video in members if video.first_seen_at >= recent_floor]
            channels = {video.channel_id for video in members}
            recent_channels = {video.channel_id for video in recent}
            countries = {
                row.region_code
                for video in members
                for row in self._rows_at(video, cutoff, earliest=earliest)
            }
            view_features = [self._video_view_features(video, cutoff) for video in members]
            velocities = [row[0] for row in view_features]
            growth_values = [row[1] for row in view_features]
            velocity_total = sum(velocities)
            channel_counts = Counter(video.channel_id for video in members)
            measurements = TopicMeasurements(
                video_count=len(members),
                video_count_24h=sum(
                    video.first_seen_at >= cutoff - timedelta(hours=24) for video in members
                ),
                video_count_72h=sum(
                    video.first_seen_at >= cutoff - timedelta(hours=72) for video in members
                ),
                previous_video_count_24h=sum(
                    cutoff - timedelta(hours=48)
                    <= video.first_seen_at
                    < cutoff - timedelta(hours=24)
                    for video in members
                ),
                distinct_channels=len(channels),
                distinct_channels_72h=len(
                    {
                        video.channel_id
                        for video in members
                        if video.first_seen_at >= cutoff - timedelta(hours=72)
                    }
                ),
                channel_size_bucket_count=1,
                large_channel_count=0,
                aggregate_view_velocity=velocity_total,
                top_velocity_share=max(velocities, default=0) / max(velocity_total, 1),
                top_channel_share=max(channel_counts.values(), default=0) / len(members),
                median_outlier_ratio=1,
                top_outlier_ratio=1,
                search_appearances_24h=sum(
                    video.first_seen_at >= cutoff - timedelta(hours=24) for video in members
                ),
                previous_search_appearances_24h=sum(
                    cutoff - timedelta(hours=48)
                    <= video.first_seen_at
                    < cutoff - timedelta(hours=24)
                    for video in members
                ),
                provider_coverage_count=min(3, len(countries)),
                snapshot_coverage=1,
                entity_count=len(
                    {entity for document in documents for entity in document.entities}
                ),
                audience_demand=0,
                baseline_coverage=0,
                transcript_coverage=0,
                specificity_score=cluster.specificity_score,
                topic_age_days=max(
                    0,
                    (cutoff - min(video.first_seen_at for video in members)).total_seconds()
                    / 86_400,
                ),
            )
            scored = score_topic(measurements)
            eligible = (
                len(members) >= self.policy.minimum_videos
                and len(channels) >= self.policy.minimum_channels
                and len(recent_channels) >= self.policy.minimum_recent_channels
                and cluster.specificity_score >= 70
                and cluster.thesis_support_ratio >= 0.8
            )
            states[key] = CrossMarketTopicState(
                topic_key=key,
                label=cluster.label,
                observed_at=cutoff,
                score=scored.score,
                specificity_score=cluster.specificity_score,
                eligible=eligible,
                video_count_30d=len(members),
                video_count_7d=len(recent),
                distinct_channels_30d=len(channels),
                distinct_channels_7d=len(recent_channels),
                country_count_30d=len(countries),
                aggregate_view_velocity=round(velocity_total, 2),
                median_view_growth=round(float(median(growth_values)), 4),
                member_video_ids=tuple(sorted(video.video_id for video in members)),
                member_channel_ids=tuple(sorted(channels)),
                country_codes=tuple(sorted(countries)),
                evidence_titles=tuple(video.title for video in members[:5]),
            )
        self._state_cache[cutoff] = states
        return states

    def _outcome(
        self,
        baseline: CrossMarketTopicState,
    ) -> CrossMarketOutcome:
        checkpoint = baseline.observed_at
        future_limit = checkpoint + timedelta(days=self.policy.outcome_horizon_days)
        earliest_future = checkpoint + timedelta(hours=24)
        future_times = [
            observed
            for observed in self._observation_times
            if earliest_future <= observed <= future_limit
        ]
        baseline_videos = set(baseline.member_video_ids)
        baseline_channels = set(baseline.member_channel_ids)
        baseline_countries = set(baseline.country_codes)
        baseline_supply = max(baseline.video_count_7d, 1)
        fired_at: datetime | None = None
        max_supply_growth = 0.0
        max_new_channels = 0
        max_new_countries = 0
        max_country_count = baseline.country_count_30d
        max_new_video_share = 0.0
        for future in future_times:
            earliest = future - timedelta(days=self.policy.lookback_days)
            recent_floor = future - timedelta(days=self.policy.recent_supply_days)
            members = [
                video
                for video in self._topic_videos[baseline.topic_key]
                if earliest <= video.published_at <= future and video.first_seen_at <= future
            ]
            recent = [video for video in members if video.first_seen_at >= recent_floor]
            recent_ids = {video.video_id for video in recent}
            current_channels = {video.channel_id for video in members}
            current_countries = {
                row.region_code
                for video in members
                for row in self._rows_at(video, future, earliest=earliest)
            }
            supply_growth = len(recent_ids) / baseline_supply
            new_channels = len(current_channels - baseline_channels)
            new_countries = len(current_countries - baseline_countries)
            new_video_share = (
                len(recent_ids - baseline_videos) / len(recent_ids) if recent_ids else 0
            )
            max_supply_growth = max(max_supply_growth, supply_growth)
            max_new_channels = max(max_new_channels, new_channels)
            max_new_countries = max(max_new_countries, new_countries)
            max_country_count = max(max_country_count, len(current_countries))
            max_new_video_share = max(max_new_video_share, new_video_share)
            if (
                fired_at is None
                and supply_growth >= self.policy.supply_growth_threshold
                and new_channels >= self.policy.minimum_new_channels
                and new_countries >= self.policy.minimum_new_countries
                and len(current_countries) >= self.policy.minimum_total_countries
                and new_video_share >= self.policy.minimum_new_video_share
            ):
                fired_at = future
        return CrossMarketOutcome(
            topic_key=baseline.topic_key,
            fired=fired_at is not None,
            fired_at=fired_at,
            lead_days=(
                round((fired_at - checkpoint).total_seconds() / 86_400, 2)
                if fired_at is not None
                else None
            ),
            max_supply_growth=round(max_supply_growth, 4),
            max_new_channels=max_new_channels,
            max_new_countries=max_new_countries,
            max_country_count=max_country_count,
            max_new_video_share=round(max_new_video_share, 4),
        )

    @staticmethod
    def _random_order(
        candidates: list[CrossMarketTopicState],
        checkpoint: datetime,
    ) -> list[CrossMarketTopicState]:
        return sorted(
            candidates,
            key=lambda row: sha256(
                f"{checkpoint.isoformat()}|{row.topic_key}".encode()
            ).hexdigest(),
        )

    def checkpoint(self, checkpoint_at: datetime) -> CrossMarketCheckpoint:
        checkpoint = _aware(checkpoint_at)
        candidates = [row for row in self.states_at(checkpoint).values() if row.eligible]
        top_k = self.policy.top_k
        full_rankings = {
            "method": tuple(sorted(candidates, key=lambda row: (-row.score, row.topic_key))),
            "supply": tuple(
                sorted(
                    candidates,
                    key=lambda row: (-row.video_count_7d, -row.video_count_30d, row.topic_key),
                )
            ),
            "countries": tuple(
                sorted(candidates, key=lambda row: (-row.country_count_30d, row.topic_key))
            ),
            "velocity": tuple(
                sorted(candidates, key=lambda row: (-row.aggregate_view_velocity, row.topic_key))
            ),
            "view_growth": tuple(
                sorted(candidates, key=lambda row: (-row.median_view_growth, row.topic_key))
            ),
            "random": tuple(self._random_order(candidates, checkpoint)),
        }
        rankings = {name: rows[:top_k] for name, rows in full_rankings.items()}
        outcomes = tuple(self._outcome(row) for row in candidates)
        return CrossMarketCheckpoint(
            checkpoint_at=checkpoint,
            candidate_count=len(candidates),
            candidates=tuple(sorted(candidates, key=lambda row: row.topic_key)),
            predictions=rankings["method"],
            outcomes=outcomes,
            rankings=rankings,
            full_rankings=full_rankings,
        )


def deduplicate_cross_market_episodes(
    checkpoints: Iterable[CrossMarketCheckpoint],
    *,
    cooldown_days: int,
    top_k: int = 10,
) -> tuple[CrossMarketCheckpoint, ...]:
    """Keep one candidate opportunity per topic within a matured outcome window."""

    if cooldown_days < 1:
        raise ValueError("cooldown_days must be positive")
    last_episode: dict[str, datetime] = {}
    deduplicated: list[CrossMarketCheckpoint] = []
    for checkpoint in sorted(checkpoints, key=lambda row: row.checkpoint_at):
        candidates = tuple(
            candidate
            for candidate in checkpoint.candidates
            if candidate.topic_key not in last_episode
            or checkpoint.checkpoint_at - last_episode[candidate.topic_key]
            >= timedelta(days=cooldown_days)
        )
        candidate_keys = {candidate.topic_key for candidate in candidates}
        for candidate in candidates:
            last_episode[candidate.topic_key] = checkpoint.checkpoint_at
        full_rankings = {
            name: tuple(row for row in ranking if row.topic_key in candidate_keys)
            for name, ranking in checkpoint.full_rankings.items()
        }
        rankings = {name: rows[:top_k] for name, rows in full_rankings.items()}
        outcomes = tuple(
            outcome for outcome in checkpoint.outcomes if outcome.topic_key in candidate_keys
        )
        deduplicated.append(
            CrossMarketCheckpoint(
                checkpoint_at=checkpoint.checkpoint_at,
                candidate_count=len(candidates),
                candidates=candidates,
                predictions=rankings["method"],
                outcomes=outcomes,
                rankings=rankings,
                full_rankings=full_rankings,
            )
        )
    return tuple(deduplicated)


def summarize_cross_market(
    checkpoints: Iterable[CrossMarketCheckpoint],
    *,
    split: Literal["train", "holdout", "all"],
) -> dict[str, object]:
    rows = tuple(checkpoints)
    methods = ("method", "supply", "countries", "velocity", "view_growth", "random")
    fired_candidates = sum(outcome.fired for row in rows for outcome in row.outcomes)
    candidate_count = sum(len(row.outcomes) for row in rows)
    rankings: dict[str, object] = {}
    for method in methods:
        selected = 0
        fired = 0
        lead_days: list[float] = []
        for checkpoint in rows:
            outcomes = {row.topic_key: row for row in checkpoint.outcomes}
            selected_rows = checkpoint.rankings[method]
            selected += len(selected_rows)
            for prediction in selected_rows:
                outcome = outcomes[prediction.topic_key]
                if outcome.fired:
                    fired += 1
                    if outcome.lead_days is not None:
                        lead_days.append(outcome.lead_days)
        rankings[method] = {
            "predictions": selected,
            "fired": fired,
            "precision_at_10_percent": (round(fired / selected * 100, 1) if selected else None),
            "recall_percent": (
                round(fired / fired_candidates * 100, 1) if fired_candidates else None
            ),
            "median_lead_days": (round(float(median(lead_days)), 2) if lead_days else None),
        }
    return {
        "split": split,
        "checkpoint_count": len(rows),
        "candidate_topics": candidate_count,
        "fired_candidate_topics": fired_candidates,
        "candidate_base_rate_percent": (
            round(fired_candidates / candidate_count * 100, 1) if candidate_count else None
        ),
        "rankings": rankings,
    }


__all__ = [
    "CROSS_MARKET_OUTCOME_VERSION",
    "CROSS_MARKET_REPLAY_VERSION",
    "CrossMarketCheckpoint",
    "CrossMarketOutcome",
    "CrossMarketPolicy",
    "CrossMarketReplay",
    "CrossMarketTopicState",
    "deduplicate_cross_market_episodes",
    "summarize_cross_market",
]
