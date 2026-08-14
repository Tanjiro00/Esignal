from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.backtest.external_timeseries import (
    ExternalTimeseriesReplay,
    ExternalVideo,
    ExternalViewSnapshot,
    summarize_external_results,
)


def _video(
    *,
    video_id: str,
    title: str,
    channel: str,
    first_observed: datetime,
    views: int,
    future_views: int | None = None,
    future_days: int = 1,
) -> ExternalVideo:
    snapshots = [ExternalViewSnapshot(views=views, observed_at=first_observed)]
    if future_views is not None:
        snapshots.append(
            ExternalViewSnapshot(
                views=future_views,
                observed_at=first_observed + timedelta(days=future_days),
            )
        )
    return ExternalVideo(
        video_id=video_id,
        title=title,
        channel_id=channel,
        subscriber_count=20_000,
        category="28",
        duration_seconds=600,
        snapshots=tuple(snapshots),
    )


def _fixture(*, include_future: bool) -> tuple[list[ExternalVideo], datetime]:
    checkpoint = datetime(2024, 10, 14, 23, 59, 59, tzinfo=UTC)
    videos = []
    for channel_index in range(3):
        channel = f"channel-{channel_index}"
        for history_index in range(5):
            videos.append(
                _video(
                    video_id=f"history-{channel_index}-{history_index}",
                    title=f"Weekly camera notes {history_index}",
                    channel=channel,
                    first_observed=checkpoint - timedelta(days=20 - history_index),
                    views=100,
                )
            )
        videos.append(
            _video(
                video_id=f"baseline-topic-{channel_index}",
                title="ChatGPT AI agents for recurring business workflow",
                channel=channel,
                first_observed=checkpoint - timedelta(days=1),
                views=300,
                future_views=600 if include_future else None,
                future_days=20,
            )
        )
        if include_future:
            for future_index in range(3):
                videos.append(
                    _video(
                        video_id=f"future-topic-{channel_index}-{future_index}",
                        title="ChatGPT AI agents for recurring business workflow",
                        channel=channel,
                        first_observed=checkpoint + timedelta(days=22, hours=-future_index),
                        views=3_000,
                    )
                )
    return videos, checkpoint


def test_external_video_uses_source_collectors_previous_day_rule() -> None:
    first = datetime(2024, 10, 10, 9, tzinfo=UTC)
    video = _video(
        video_id="one",
        title="ChatGPT AI agent workflow",
        channel="channel",
        first_observed=first,
        views=100,
    )

    assert video.published_at == first - timedelta(days=1)


def test_precision_is_undefined_when_method_emits_no_predictions() -> None:
    summary = summarize_external_results([], split="all")

    assert summary["rankings"]["method"]["precision_at_10_percent"] is None


def test_external_video_prefers_explicit_publication_timestamp() -> None:
    first = datetime(2024, 10, 10, 9, tzinfo=UTC)
    published = datetime(2024, 10, 6, 12, tzinfo=UTC)
    video = ExternalVideo(
        video_id="explicit",
        title="ChatGPT AI agent workflow",
        channel_id="channel",
        subscriber_count=20_000,
        category="28",
        duration_seconds=600,
        snapshots=(ExternalViewSnapshot(views=100, observed_at=first),),
        published_at_override=published,
    )

    assert video.published_at == published


def test_future_snapshots_do_not_change_checkpoint_features() -> None:
    full_videos, checkpoint = _fixture(include_future=True)
    truncated_videos, _ = _fixture(include_future=False)

    full_states = ExternalTimeseriesReplay(full_videos).states_at(checkpoint)
    truncated_states = ExternalTimeseriesReplay(truncated_videos).states_at(checkpoint)

    assert full_states == truncated_states
    state = next(iter(full_states.values()))
    assert state.actionable is True
    assert state.video_count_72h == 3


def test_replay_can_scope_topic_admission_without_removing_channel_baselines() -> None:
    videos, checkpoint = _fixture(include_future=False)
    videos.append(
        ExternalVideo(
            video_id="out-of-scope",
            title="GPT-4 product and capability release",
            channel_id="channel-0",
            subscriber_count=20_000,
            category="24",
            duration_seconds=600,
            snapshots=(
                ExternalViewSnapshot(
                    views=1_000,
                    observed_at=checkpoint - timedelta(hours=2),
                ),
            ),
        )
    )

    replay = ExternalTimeseriesReplay(videos, eligible_categories=frozenset({"28"}))

    assert "out-of-scope" not in replay._topic_key_by_video
    assert replay.states_at(checkpoint)


def test_blind_outcome_requires_joint_future_supply_and_lift() -> None:
    videos, checkpoint = _fixture(include_future=True)
    result, _ = ExternalTimeseriesReplay(videos).label_checkpoint(checkpoint)

    assert len(result.predictions) == 1
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.fired is True
    assert outcome.lead_days is not None
    assert outcome.lead_days >= 21
    assert outcome.max_supply_growth >= 3
    assert outcome.peak_lift >= 3
