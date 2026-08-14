from datetime import UTC, datetime, timedelta

from packages.backtest.probability_replay import (
    build_probability_episodes,
    structural_probability_features,
)
from packages.backtest.youniverse import OutcomeVideo, StructuralVideo
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralTopicState,
)

T0 = datetime(2019, 1, 1, 23, 59, 59, tzinfo=UTC)


def _structural(identifier: str, channel: str, uploaded_at: datetime) -> StructuralVideo:
    return StructuralVideo(
        video_id=identifier,
        channel_id=channel,
        title="TensorFlow new version released",
        description="",
        tags=(),
        category="Science & Technology",
        upload_date=uploaded_at,
    )


def _outcome(
    identifier: str,
    channel: str,
    uploaded_at: datetime,
    views: int,
) -> OutcomeVideo:
    return OutcomeVideo(
        video_id=identifier,
        channel_id=channel,
        upload_date=uploaded_at,
        crawl_date=uploaded_at + timedelta(days=20),
        final_view_count=views,
    )


def test_research_universe_is_independent_of_legacy_publish_gate() -> None:
    videos = [
        _structural("one", "c1", T0 - timedelta(days=2)),
        _structural("two", "c2", T0 - timedelta(days=1)),
    ]
    index = StructuralCandidateIndex(videos)
    evaluator = StructuralOutcomeEvaluator(videos, [], [])

    episode = build_probability_episodes(index, evaluator, [T0])[0]

    assert episode.state.eligible is False
    assert episode.state.research_eligible is True
    assert episode.features == structural_probability_features(episode.state)


def test_adoption_and_performance_outcomes_are_independent() -> None:
    prior = [
        _structural("prior-1", "prior-1", T0 - timedelta(days=3)),
        _structural("prior-2", "prior-2", T0 - timedelta(days=1)),
    ]
    adoption_future = [
        _structural(f"future-{index}", f"new-{index}", T0 + timedelta(days=index + 1))
        for index in range(4)
    ]
    all_structural = [*prior, *adoption_future]
    index = StructuralCandidateIndex(all_structural)
    state = next(iter(index.states_at(T0).values()))
    adoption_result = StructuralOutcomeEvaluator(all_structural, [], []).evaluate(state)

    assert adoption_result.adoption_fired is True
    assert adoption_result.performance_fired is False

    performance_future = [
        _structural(f"perf-{index}", f"perf-channel-{index}", T0 + timedelta(days=index + 1))
        for index in range(2)
    ]
    performance_outcomes = [
        _outcome(video.video_id, video.channel_id, video.upload_date, 1_000)
        for video in performance_future
    ]
    baselines = []
    for video in performance_future:
        for baseline_index in range(5):
            baselines.append(
                _outcome(
                    f"baseline-{video.video_id}-{baseline_index}",
                    video.channel_id,
                    video.upload_date - timedelta(days=baseline_index + 1),
                    100,
                )
            )
    performance_structural = [*prior, *performance_future]
    performance_state = next(
        iter(StructuralCandidateIndex(performance_structural).states_at(T0).values())
    )
    performance_result = StructuralOutcomeEvaluator(
        performance_structural,
        performance_outcomes,
        [*performance_outcomes, *baselines],
    ).evaluate(performance_state)

    assert performance_result.adoption_fired is False
    assert performance_result.performance_fired is True


def test_structural_features_never_include_future_engagement() -> None:
    state = StructuralTopicState(
        topic_key="topic",
        label="Topic",
        observed_at=T0,
        score=50,
        specificity_score=80,
        thesis_support_ratio=1,
        eligible=False,
        active_video_count=3,
        recent_video_count=2,
        previous_28d_video_count=2,
        distinct_channel_count=3,
        recent_channel_count=2,
        new_recent_channel_count=1,
        acceleration=1,
        large_channel_count=0,
        channel_size_bucket_count=2,
        member_video_ids=("one",),
        member_channel_ids=("channel",),
        evidence_titles=("Evidence",),
        research_eligible=True,
        channel_entropy=1,
        topic_age_days=10,
    )

    features = structural_probability_features(state)

    assert "views" not in " ".join(features)
    assert "outlier" not in " ".join(features)
