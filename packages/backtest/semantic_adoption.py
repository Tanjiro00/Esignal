from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import numpy as np
import numpy.typing as npt
from sklearn.cluster import HDBSCAN  # type: ignore[import-untyped]

from packages.backtest.probability_replay import structural_probability_features
from packages.backtest.youniverse import StructuralVideo
from packages.backtest.youniverse_replay import StructuralTopicState
from packages.clustering.embedding_provider import decode_embedding
from packages.clustering.evidence_quality import (
    COPY_RESISTANT_EVIDENCE_POLICY,
    EvidenceQualityPolicy,
    assess_evidence_quality,
    collapse_near_duplicate_evidence,
)
from packages.clustering.microtopics_v7 import normalize_format_neutral_title

SEMANTIC_ADOPTION_REPLAY_VERSION = "semantic-adoption-replay-v1"
FloatMatrix = npt.NDArray[np.float32]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalized(vector: npt.ArrayLike) -> FloatMatrix:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


@dataclass(frozen=True)
class SemanticReplayPolicy:
    structural_lookback_days: int = 180
    active_window_days: int = 35
    recent_window_days: int = 7
    outcome_horizon_days: int = 42
    episode_cooldown_days: int = 42
    minimum_videos: int = 2
    maximum_active_videos: int = 60
    minimum_channels: int = 2
    minimum_recent_videos: int = 1
    minimum_cluster_size: int = 2
    minimum_samples: int = 2
    cluster_selection_method: str = "leaf"
    minimum_mean_similarity: float = 0.72
    minimum_member_similarity: float = 0.62
    future_centroid_similarity: float = 0.74
    future_exemplar_similarity: float = 0.78
    track_centroid_similarity: float = 0.84
    track_minimum_jaccard: float = 0.1
    adoption_supply_growth_threshold: float = 1.25
    adoption_minimum_future_videos: int = 4
    adoption_minimum_new_future_channels: int = 2
    adoption_minimum_new_channel_share: float = 0.4


@dataclass(frozen=True)
class SemanticTopicState:
    topic_key: str
    observed_at: datetime
    label: str
    evidence_video_ids: tuple[str, ...]
    evidence_titles: tuple[str, ...]
    active_video_ids: tuple[str, ...]
    active_channel_ids: tuple[str, ...]
    prior_channel_ids: tuple[str, ...]
    centroid: tuple[float, ...]
    exemplars: tuple[tuple[float, ...], ...]
    active_video_count: int
    recent_video_count: int
    previous_28d_video_count: int
    distinct_channel_count: int
    recent_channel_count: int
    new_recent_channel_count: int
    acceleration: float
    channel_entropy: float
    topic_age_days: float
    mean_similarity: float
    minimum_similarity: float

    def probability_features(self) -> dict[str, float]:
        compatibility = StructuralTopicState(
            topic_key=self.topic_key,
            label=self.label,
            observed_at=self.observed_at,
            score=0,
            specificity_score=self.mean_similarity * 100,
            thesis_support_ratio=1,
            eligible=True,
            active_video_count=self.active_video_count,
            recent_video_count=self.recent_video_count,
            previous_28d_video_count=self.previous_28d_video_count,
            distinct_channel_count=self.distinct_channel_count,
            recent_channel_count=self.recent_channel_count,
            new_recent_channel_count=self.new_recent_channel_count,
            acceleration=self.acceleration,
            large_channel_count=0,
            channel_size_bucket_count=0,
            member_video_ids=self.active_video_ids,
            member_channel_ids=self.active_channel_ids,
            evidence_titles=self.evidence_titles,
            research_eligible=True,
            channel_entropy=self.channel_entropy,
            topic_age_days=self.topic_age_days,
        )
        features = structural_probability_features(compatibility)
        features["semantic_mean_similarity"] = self.mean_similarity
        features["semantic_minimum_similarity"] = self.minimum_similarity
        return features


@dataclass(frozen=True)
class SemanticTopicOutcome:
    fired: bool
    fired_at: datetime | None
    lead_days: float | None
    future_video_count: int
    expected_future_supply: float
    new_future_channel_count: int
    new_channel_share: float
    future_video_ids: tuple[str, ...]


@dataclass(frozen=True)
class SemanticEpisode:
    checkpoint_at: datetime
    state: SemanticTopicState
    outcome: SemanticTopicOutcome

    @property
    def adoption_label(self) -> bool:
        return self.outcome.fired

    @property
    def features(self) -> dict[str, float]:
        return self.state.probability_features()


def load_embedding_map(path: Path) -> dict[str, FloatMatrix]:
    embeddings: dict[str, FloatMatrix] = {}
    expected_model: str | None = None
    expected_dimensions: int | None = None
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            model = str(row["model"])
            dimensions = int(row["dimensions"])
            if expected_model is None:
                expected_model = model
                expected_dimensions = dimensions
            if model != expected_model or dimensions != expected_dimensions:
                raise ValueError(f"mixed embedding schema at line {line_number}")
            vector = decode_embedding(str(row["embedding_base64"]), dimensions=dimensions)
            embeddings[str(row["video_id"])] = _normalized(vector)
    return embeddings


class SemanticCandidateBuilder:
    def __init__(
        self,
        videos: Iterable[StructuralVideo],
        embeddings: dict[str, FloatMatrix],
        *,
        policy: SemanticReplayPolicy | None = None,
    ) -> None:
        self.policy = policy or SemanticReplayPolicy()
        self.videos = tuple(
            sorted(
                (video for video in videos if video.video_id in embeddings),
                key=lambda video: (_aware(video.upload_date), video.video_id),
            )
        )
        self.embeddings = embeddings

    def _prepare_candidate_videos(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return tuple(videos)

    def _prepare_history_videos(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return tuple(videos)

    def _prepare_future_videos(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return tuple(videos)

    def _accept_cluster(self, members: Sequence[StructuralVideo]) -> bool:
        return True

    def states_at(self, observed_at: datetime) -> tuple[SemanticTopicState, ...]:
        cutoff = _aware(observed_at)
        active_floor = cutoff - timedelta(days=self.policy.active_window_days)
        history_floor = cutoff - timedelta(days=self.policy.structural_lookback_days)
        recent_floor = cutoff - timedelta(days=self.policy.recent_window_days)
        active = self._prepare_candidate_videos(
            tuple(
                video
                for video in self.videos
                if active_floor <= _aware(video.upload_date) <= cutoff
            )
        )
        if len(active) < self.policy.minimum_cluster_size:
            return ()
        matrix = np.stack([self.embeddings[video.video_id] for video in active])
        labels = HDBSCAN(
            min_cluster_size=self.policy.minimum_cluster_size,
            min_samples=self.policy.minimum_samples,
            metric="euclidean",
            cluster_selection_method=self.policy.cluster_selection_method,
            n_jobs=-1,
            copy=True,
        ).fit_predict(matrix)
        history = self._prepare_history_videos(
            tuple(
                video
                for video in self.videos
                if history_floor <= _aware(video.upload_date) <= cutoff
            )
        )
        history_matrix = np.stack([self.embeddings[video.video_id] for video in history])
        states: list[SemanticTopicState] = []
        for cluster_label in sorted(set(int(value) for value in labels if value >= 0)):
            indexes = np.flatnonzero(labels == cluster_label)
            members = tuple(active[int(index)] for index in indexes)
            if not self.policy.minimum_videos <= len(members) <= self.policy.maximum_active_videos:
                continue
            if not self._accept_cluster(members):
                continue
            channels = {video.channel_id for video in members}
            recent = tuple(video for video in members if _aware(video.upload_date) >= recent_floor)
            if len(channels) < self.policy.minimum_channels or len(recent) < 1:
                continue
            member_matrix = matrix[indexes]
            centroid = _normalized(member_matrix.mean(axis=0))
            similarities = member_matrix @ centroid
            mean_similarity = float(similarities.mean())
            minimum_similarity = float(similarities.min())
            if (
                mean_similarity < self.policy.minimum_mean_similarity
                or minimum_similarity < self.policy.minimum_member_similarity
            ):
                continue
            representative_indexes = np.argsort(-similarities)[: min(5, len(members))]
            representatives = tuple(members[int(index)] for index in representative_indexes)
            exemplars = tuple(
                tuple(float(value) for value in member_matrix[int(index)])
                for index in representative_indexes
            )
            history_matches = self._matches(history_matrix, centroid, np.asarray(exemplars))
            topic_history = tuple(
                history[index] for index in np.flatnonzero(history_matches).tolist()
            )
            prior_channels = {video.channel_id for video in topic_history}
            earlier_channels = {
                video.channel_id
                for video in topic_history
                if _aware(video.upload_date) < recent_floor
            }
            recent_channels = {video.channel_id for video in recent}
            previous_28 = tuple(
                video
                for video in members
                if cutoff - timedelta(days=35) <= _aware(video.upload_date) < recent_floor
            )
            previous_weekly = len(previous_28) / 4
            acceleration = (len(recent) - previous_weekly) / max(previous_weekly, 1)
            counts = Counter(video.channel_id for video in members)
            entropy = 0.0
            if len(counts) > 1:
                entropy = -sum(
                    (count / len(members)) * math.log(count / len(members))
                    for count in counts.values()
                ) / math.log(len(counts))
            evidence_titles = tuple(video.title for video in representatives)
            label = normalize_format_neutral_title(evidence_titles[0])[:160]
            topic_key = (
                "semantic-"
                + sha256(
                    "|".join(sorted(video.video_id for video in members)).encode()
                ).hexdigest()[:18]
            )
            states.append(
                SemanticTopicState(
                    topic_key=topic_key,
                    observed_at=cutoff,
                    label=label,
                    evidence_video_ids=tuple(video.video_id for video in representatives),
                    evidence_titles=evidence_titles,
                    active_video_ids=tuple(video.video_id for video in members),
                    active_channel_ids=tuple(sorted(channels)),
                    prior_channel_ids=tuple(sorted(prior_channels)),
                    centroid=tuple(float(value) for value in centroid),
                    exemplars=exemplars,
                    active_video_count=len(members),
                    recent_video_count=len(recent),
                    previous_28d_video_count=len(previous_28),
                    distinct_channel_count=len(channels),
                    recent_channel_count=len(recent_channels),
                    new_recent_channel_count=len(recent_channels - earlier_channels),
                    acceleration=round(acceleration, 6),
                    channel_entropy=round(entropy, 6),
                    topic_age_days=round(
                        (
                            cutoff - min(_aware(video.upload_date) for video in topic_history)
                        ).total_seconds()
                        / 86_400,
                        3,
                    ),
                    mean_similarity=round(mean_similarity, 6),
                    minimum_similarity=round(minimum_similarity, 6),
                )
            )
        return tuple(sorted(states, key=lambda state: state.topic_key))

    def _matches(
        self,
        matrix: FloatMatrix,
        centroid: FloatMatrix,
        exemplars: FloatMatrix,
    ) -> npt.NDArray[np.bool_]:
        centroid_similarity = matrix @ centroid
        exemplar_similarity = (matrix @ exemplars.T).max(axis=1)
        return (centroid_similarity >= self.policy.future_centroid_similarity) & (
            exemplar_similarity >= self.policy.future_exemplar_similarity
        )

    def outcomes(
        self,
        states: Sequence[SemanticTopicState],
    ) -> dict[str, SemanticTopicOutcome]:
        if not states:
            return {}
        cutoff = states[0].observed_at
        if any(state.observed_at != cutoff for state in states):
            raise ValueError("semantic outcomes require one common checkpoint")
        future_end = cutoff + timedelta(days=self.policy.outcome_horizon_days)
        future = self._prepare_future_videos(
            tuple(
                video for video in self.videos if cutoff < _aware(video.upload_date) <= future_end
            )
        )
        assignments: dict[str, list[StructuralVideo]] = {state.topic_key: [] for state in states}
        if future:
            matrix = np.stack([self.embeddings[video.video_id] for video in future])
            scores = np.full((len(future), len(states)), -np.inf, dtype=np.float32)
            for state_index, state in enumerate(states):
                centroid_similarity = matrix @ np.asarray(state.centroid, dtype=np.float32)
                exemplar_similarity = (
                    matrix @ np.asarray(state.exemplars, dtype=np.float32).T
                ).max(axis=1)
                valid = (centroid_similarity >= self.policy.future_centroid_similarity) & (
                    exemplar_similarity >= self.policy.future_exemplar_similarity
                )
                combined = (centroid_similarity + exemplar_similarity) / 2
                scores[:, state_index] = np.where(valid, combined, -np.inf)
            nearest = scores.argmax(axis=1)
            best = scores.max(axis=1)
            for video_index in np.flatnonzero(np.isfinite(best)).tolist():
                state = states[int(nearest[video_index])]
                assignments[state.topic_key].append(future[video_index])
        return {
            state.topic_key: self._outcome_from_future(
                state,
                tuple(assignments[state.topic_key]),
            )
            for state in states
        }

    def outcome(self, state: SemanticTopicState) -> SemanticTopicOutcome:
        return self.outcomes((state,))[state.topic_key]

    def _outcome_from_future(
        self,
        state: SemanticTopicState,
        topic_future: tuple[StructuralVideo, ...],
    ) -> SemanticTopicOutcome:
        cutoff = state.observed_at
        prior_channels = set(state.prior_channel_ids)
        expected_supply = max(state.previous_28d_video_count / 4 * 6, 2.0)
        required_supply = max(
            self.policy.adoption_minimum_future_videos,
            math.ceil(expected_supply * self.policy.adoption_supply_growth_threshold),
        )
        fired_at: datetime | None = None
        for index in range(len(topic_future)):
            prefix = topic_future[: index + 1]
            new_channels = {video.channel_id for video in prefix} - prior_channels
            new_share = sum(video.channel_id in new_channels for video in prefix) / len(prefix)
            if (
                len(prefix) >= required_supply
                and len(new_channels) >= self.policy.adoption_minimum_new_future_channels
                and new_share >= self.policy.adoption_minimum_new_channel_share
            ):
                fired_at = _aware(prefix[-1].upload_date)
                break
        final_new_channels = {video.channel_id for video in topic_future} - prior_channels
        final_new_share = (
            sum(video.channel_id in final_new_channels for video in topic_future)
            / len(topic_future)
            if topic_future
            else 0
        )
        return SemanticTopicOutcome(
            fired=fired_at is not None,
            fired_at=fired_at,
            lead_days=(
                round((fired_at - cutoff).total_seconds() / 86_400, 3) if fired_at else None
            ),
            future_video_count=len(topic_future),
            expected_future_supply=round(expected_supply, 3),
            new_future_channel_count=len(final_new_channels),
            new_channel_share=round(final_new_share, 6),
            future_video_ids=tuple(video.video_id for video in topic_future),
        )


class QualityGatedSemanticCandidateBuilder(SemanticCandidateBuilder):
    """Experimental challenger that fails closed on copied or vague evidence.

    The class is intentionally separate from the frozen v1 builder. It can be
    developed on training data without silently changing the completed replay.
    """

    def __init__(
        self,
        videos: Iterable[StructuralVideo],
        embeddings: dict[str, FloatMatrix],
        *,
        policy: SemanticReplayPolicy | None = None,
        quality_policy: EvidenceQualityPolicy | None = None,
    ) -> None:
        super().__init__(videos, embeddings, policy=policy)
        self.quality_policy = quality_policy or COPY_RESISTANT_EVIDENCE_POLICY

    def _collapse(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return collapse_near_duplicate_evidence(videos, policy=self.quality_policy)

    def _prepare_candidate_videos(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return self._collapse(videos)

    def _prepare_future_videos(
        self,
        videos: Sequence[StructuralVideo],
    ) -> tuple[StructuralVideo, ...]:
        return self._collapse(videos)

    def _accept_cluster(self, members: Sequence[StructuralVideo]) -> bool:
        return assess_evidence_quality(members, policy=self.quality_policy).accepted


def _same_track(
    first: SemanticTopicState,
    second: SemanticTopicState,
    policy: SemanticReplayPolicy,
) -> bool:
    similarity = float(
        np.dot(
            np.asarray(first.centroid, dtype=np.float32),
            np.asarray(second.centroid, dtype=np.float32),
        )
    )
    first_members = set(first.active_video_ids)
    second_members = set(second.active_video_ids)
    jaccard = len(first_members & second_members) / max(len(first_members | second_members), 1)
    return similarity >= policy.track_centroid_similarity and (
        jaccard >= policy.track_minimum_jaccard or bool(first_members & second_members)
    )


def build_semantic_episodes(
    builder: SemanticCandidateBuilder,
    checkpoints: Sequence[datetime],
) -> tuple[SemanticEpisode, ...]:
    last_episodes: list[SemanticTopicState] = []
    episodes: list[SemanticEpisode] = []
    cooldown = timedelta(days=builder.policy.episode_cooldown_days)
    for checkpoint in checkpoints:
        states = builder.states_at(checkpoint)
        outcomes = builder.outcomes(states)
        for state in states:
            outcome = outcomes[state.topic_key]
            matches = [
                prior for prior in last_episodes if _same_track(state, prior, builder.policy)
            ]
            latest = max(matches, key=lambda item: item.observed_at) if matches else None
            if latest is not None and state.observed_at - latest.observed_at < cooldown:
                continue
            if latest is not None:
                state = replace(state, topic_key=latest.topic_key)
            last_episodes.append(state)
            episodes.append(
                SemanticEpisode(
                    checkpoint_at=state.observed_at,
                    state=state,
                    outcome=outcome,
                )
            )
    return tuple(episodes)


__all__ = [
    "SEMANTIC_ADOPTION_REPLAY_VERSION",
    "SemanticCandidateBuilder",
    "SemanticEpisode",
    "SemanticReplayPolicy",
    "SemanticTopicOutcome",
    "SemanticTopicState",
    "QualityGatedSemanticCandidateBuilder",
    "build_semantic_episodes",
    "load_embedding_map",
]
