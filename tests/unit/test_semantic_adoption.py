from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from packages.backtest.semantic_adoption import (
    QualityGatedSemanticCandidateBuilder,
    SemanticCandidateBuilder,
    SemanticReplayPolicy,
    SemanticTopicState,
)
from packages.backtest.youniverse import StructuralVideo

T0 = datetime(2026, 3, 1, tzinfo=UTC)


def _video(
    identifier: str,
    channel: str,
    days: int,
    title: str | None = None,
) -> StructuralVideo:
    return StructuralVideo(
        video_id=identifier,
        channel_id=channel,
        title=title or identifier,
        description="",
        tags=(),
        category="Science & Technology",
        upload_date=T0 + timedelta(days=days),
    )


def _state(key: str, centroid: tuple[float, float]) -> SemanticTopicState:
    return SemanticTopicState(
        topic_key=key,
        observed_at=T0,
        label=key,
        evidence_video_ids=(key,),
        evidence_titles=(key,),
        active_video_ids=(f"prior-{key}",),
        active_channel_ids=(f"prior-{key}",),
        prior_channel_ids=(f"prior-{key}",),
        centroid=centroid,
        exemplars=(centroid,),
        active_video_count=2,
        recent_video_count=1,
        previous_28d_video_count=1,
        distinct_channel_count=2,
        recent_channel_count=1,
        new_recent_channel_count=1,
        acceleration=0.75,
        channel_entropy=1,
        topic_age_days=10,
        mean_similarity=0.9,
        minimum_similarity=0.8,
    )


def test_future_video_is_assigned_to_only_one_nearest_topic() -> None:
    future = _video("future", "new", 3)
    builder = SemanticCandidateBuilder(
        [future],
        {"future": np.asarray((0.99, 0.1), dtype=np.float32)},
        policy=SemanticReplayPolicy(
            future_centroid_similarity=0.5,
            future_exemplar_similarity=0.5,
        ),
    )
    states = (
        _state("closest", (1.0, 0.0)),
        _state("also-valid", (0.8, 0.6)),
    )

    outcomes = builder.outcomes(states)

    assert outcomes["closest"].future_video_ids == ("future",)
    assert outcomes["also-valid"].future_video_ids == ()
    assert sum(outcome.future_video_count for outcome in outcomes.values()) == 1


def test_outcomes_require_a_common_checkpoint() -> None:
    state = _state("first", (1.0, 0.0))
    later = replace(state, topic_key="later", observed_at=T0 + timedelta(days=1))
    builder = SemanticCandidateBuilder([], {})

    with pytest.raises(ValueError, match="common checkpoint"):
        builder.outcomes((state, later))


def test_quality_gated_builder_does_not_count_copied_titles_as_adoption() -> None:
    copied = [
        _video(
            f"copy-{index}",
            f"channel-{index}",
            index + 1,
            "Claude Code memory tutorial",
        )
        for index in range(4)
    ]
    builder = QualityGatedSemanticCandidateBuilder(
        copied,
        {video.video_id: np.asarray((1.0, 0.0), dtype=np.float32) for video in copied},
    )
    state = _state("memory", (1.0, 0.0))

    outcome = builder.outcome(state)

    assert outcome.future_video_count == 1
    assert outcome.fired is False
