from dataclasses import fields
from datetime import UTC, datetime, timedelta

from packages.backtest.youniverse import OutcomeVideo, StructuralVideo
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralTopicState,
)

T0 = datetime(2019, 1, 1, 23, 59, 59, tzinfo=UTC)


def _structural(
    identifier: str,
    channel: str,
    uploaded_at: datetime,
    *,
    title: str = "TensorFlow new version released",
) -> StructuralVideo:
    return StructuralVideo(
        video_id=identifier,
        channel_id=channel,
        title=title,
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
    *,
    crawl_at: datetime,
) -> OutcomeVideo:
    return OutcomeVideo(
        video_id=identifier,
        channel_id=channel,
        upload_date=uploaded_at,
        crawl_date=crawl_at,
        final_view_count=views,
    )


def test_candidate_state_has_no_final_engagement_fields_and_ignores_future() -> None:
    videos = [
        _structural("one", "c1", T0 - timedelta(days=2)),
        _structural("two", "c2", T0 - timedelta(days=1)),
        _structural("three", "c3", T0 - timedelta(hours=12)),
        _structural("future", "c4", T0 + timedelta(days=1)),
    ]
    index = StructuralCandidateIndex(videos)
    states = index.states_at(T0)

    state = next(iter(states.values()))
    assert state.eligible is True
    assert state.active_video_count == 3
    assert "final_view_count" not in {field.name for field in fields(StructuralTopicState)}


def test_future_supply_and_channel_outliers_can_fire_without_feature_leakage() -> None:
    prior = [
        _structural("prior-1", "prior-1", T0 - timedelta(days=3)),
        _structural("prior-2", "prior-2", T0 - timedelta(days=2)),
        _structural("prior-3", "prior-3", T0 - timedelta(days=1)),
    ]
    future: list[StructuralVideo] = []
    outcomes: list[OutcomeVideo] = []
    baselines: list[OutcomeVideo] = []
    for index in range(18):
        uploaded_at = T0 + timedelta(days=21 + index)
        crawl_at = uploaded_at + timedelta(days=20)
        channel = f"future-channel-{index}"
        identifier = f"future-{index}"
        future.append(_structural(identifier, channel, uploaded_at))
        outcomes.append(_outcome(identifier, channel, uploaded_at, 1_000, crawl_at=crawl_at))
        for baseline_index in range(5):
            baseline_at = uploaded_at - timedelta(days=baseline_index + 1)
            baselines.append(
                _outcome(
                    f"baseline-{index}-{baseline_index}",
                    channel,
                    baseline_at,
                    100,
                    crawl_at=crawl_at,
                )
            )

    candidate_index = StructuralCandidateIndex([*prior, *future])
    state = next(state for state in candidate_index.states_at(T0).values() if state.eligible)
    evaluator = StructuralOutcomeEvaluator(
        [*prior, *future],
        outcomes,
        [*outcomes, *baselines],
    )

    result = evaluator.evaluate(state)

    assert result.fired is True
    assert result.lead_days is not None and result.lead_days >= 21
    assert result.future_video_count == 18
    assert result.outlier_video_count == 18
    assert result.baseline_coverage == 1
