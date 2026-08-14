from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.backtest.cross_market import (
    CrossMarketReplay,
    deduplicate_cross_market_episodes,
    summarize_cross_market,
)
from packages.backtest.global_trending import GlobalTrendingObservation


def _observation(
    *,
    video_id: str,
    channel_id: str,
    region: str,
    observed_at: datetime,
    title: str,
    views: int,
) -> GlobalTrendingObservation:
    return GlobalTrendingObservation(
        observed_at=observed_at,
        region_code=region,
        rank=5,
        video_id=video_id,
        title=title,
        description="A documented GPT-4 product capability release.",
        published_at=observed_at - timedelta(hours=12),
        channel_id=channel_id,
        category_id="28",
        default_language="en",
        default_audio_language="en-US",
        view_count=views,
    )


def _fixture() -> tuple[list[GlobalTrendingObservation], datetime]:
    checkpoint = datetime(2024, 1, 7, 23, 59, 59, tzinfo=UTC)
    rows = [
        _observation(
            video_id=f"baseline-{index}",
            channel_id=f"channel-{index}",
            region=region,
            observed_at=checkpoint - timedelta(days=2 - index / 2),
            title=(
                "GPT-4 Developer Livestream"
                if index == 0
                else "Introducing GPT-4: new model release"
            ),
            views=1_000 + index * 100,
        )
        for index, region in enumerate(("US", "GB", "CA"))
    ]
    future_regions = ("DE", "FR", "MX", "BR", "JP", "KR", "IN", "AE", "AU")
    for index, region in enumerate(future_regions):
        rows.append(
            _observation(
                video_id=f"future-{index}",
                channel_id=f"future-channel-{index}",
                region=region,
                observed_at=checkpoint + timedelta(days=7),
                title="GPT-4 launch explained: the new model capability",
                views=10_000 + index * 1_000,
            )
        )
    return rows, checkpoint


def test_cross_market_replay_fires_only_after_new_supply_and_countries() -> None:
    rows, checkpoint = _fixture()
    replay = CrossMarketReplay(rows)

    state = next(iter(replay.states_at(checkpoint).values()))
    result = replay.checkpoint(checkpoint)

    assert state.eligible is True
    assert state.video_count_7d == 3
    assert len(result.predictions) == 1
    assert result.outcomes[0].fired is True
    assert result.outcomes[0].lead_days == 7
    assert result.outcomes[0].max_new_countries >= 5


def test_future_rows_do_not_change_checkpoint_features() -> None:
    rows, checkpoint = _fixture()
    truncated = [row for row in rows if row.observed_at <= checkpoint]

    full_state = CrossMarketReplay(rows).states_at(checkpoint)
    truncated_state = CrossMarketReplay(truncated).states_at(checkpoint)

    assert full_state == truncated_state


def test_cross_market_summary_marks_empty_precision_as_undefined() -> None:
    summary = summarize_cross_market([], split="train")

    assert summary["rankings"]["method"]["precision_at_10_percent"] is None


def test_adjacent_weekly_checkpoints_do_not_duplicate_the_same_episode() -> None:
    rows, checkpoint = _fixture()
    replay = CrossMarketReplay(rows)

    result = deduplicate_cross_market_episodes(
        (
            replay.checkpoint(checkpoint),
            replay.checkpoint(checkpoint + timedelta(days=7)),
        ),
        cooldown_days=21,
    )

    assert result[0].candidate_count == 1
    assert result[1].candidate_count == 0
    assert len(result[1].predictions) == 0
