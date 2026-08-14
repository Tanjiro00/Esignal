from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralTopicOutcome,
    StructuralTopicState,
)

PROBABILITY_REPLAY_VERSION = "youniverse-dual-outcome-probability-replay-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ProbabilityEpisode:
    checkpoint_at: datetime
    state: StructuralTopicState
    outcome: StructuralTopicOutcome
    features: Mapping[str, float]

    @property
    def key(self) -> str:
        return f"{_aware(self.checkpoint_at).isoformat()}|{self.state.topic_key}"

    @property
    def adoption_label(self) -> bool:
        return self.outcome.adoption_fired

    @property
    def performance_label(self) -> bool | None:
        policy_floor = 0.6
        if self.outcome.future_video_count < 2:
            return None
        if self.outcome.baseline_coverage < policy_floor:
            return None
        return self.outcome.performance_fired


def structural_probability_features(state: StructuralTopicState) -> dict[str, float]:
    previous_weekly_supply = state.previous_28d_video_count / 4
    recent_channel_share = state.recent_channel_count / max(
        state.distinct_channel_count,
        1,
    )
    new_creator_share = state.new_recent_channel_count / max(state.recent_channel_count, 1)
    return {
        "log_active_supply": math.log1p(state.active_video_count),
        "log_recent_supply": math.log1p(state.recent_video_count),
        "log_previous_weekly_supply": math.log1p(previous_weekly_supply),
        "supply_acceleration": min(6.0, max(-2.0, state.acceleration)),
        "log_distinct_creators": math.log1p(state.distinct_channel_count),
        "creator_diversity": state.distinct_channel_count / max(state.active_video_count, 1),
        "recent_creator_share": recent_channel_share,
        "new_creator_share": new_creator_share,
        "channel_entropy": state.channel_entropy,
        "channel_size_coverage": min(1.0, state.channel_size_bucket_count / 4),
        "large_creator_share": state.large_channel_count / max(state.distinct_channel_count, 1),
        "log_topic_age_days": math.log1p(state.topic_age_days),
        "specificity": state.specificity_score / 100,
    }


def build_probability_episodes(
    candidate_index: StructuralCandidateIndex,
    outcome_evaluator: StructuralOutcomeEvaluator,
    checkpoints: Iterable[datetime],
) -> tuple[ProbabilityEpisode, ...]:
    """Build the score-independent topic-week universe used by the v2 heads."""

    last_episode: dict[str, datetime] = {}
    cooldown = timedelta(days=candidate_index.policy.episode_cooldown_days)
    episodes: list[ProbabilityEpisode] = []
    for checkpoint_at in checkpoints:
        cutoff = _aware(checkpoint_at)
        states = candidate_index.states_at(cutoff)
        candidates = sorted(
            (
                state
                for state in states.values()
                if state.research_eligible
                and (
                    state.topic_key not in last_episode
                    or cutoff - last_episode[state.topic_key] >= cooldown
                )
            ),
            key=lambda state: state.topic_key,
        )
        for state in candidates:
            last_episode[state.topic_key] = cutoff
            episodes.append(
                ProbabilityEpisode(
                    checkpoint_at=cutoff,
                    state=state,
                    outcome=outcome_evaluator.evaluate(state),
                    features=structural_probability_features(state),
                )
            )
    return tuple(episodes)


__all__ = [
    "PROBABILITY_REPLAY_VERSION",
    "ProbabilityEpisode",
    "build_probability_episodes",
    "structural_probability_features",
]
