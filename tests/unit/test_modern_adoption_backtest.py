from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from packages.backtest.modern_adoption import (
    load_structural_cohort,
    maximum_complete_checkpoint,
    temporal_fit_calibration_split,
    weekly_checkpoints,
)
from packages.backtest.probability_replay import ProbabilityEpisode
from packages.backtest.youniverse_replay import StructuralTopicOutcome, StructuralTopicState


def test_structural_cohort_rejects_engagement_fields(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        json.dumps(
            {
                "video_id": "video-1",
                "channel_id": "channel-1",
                "title": "A precise AI topic",
                "description": "",
                "upload_date": "2026-01-01T00:00:00Z",
                "view_count": 100,
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="outcome fields"):
        load_structural_cohort(path)


def test_structural_cohort_and_complete_checkpoint(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    rows = [
        {
            "video_id": f"video-{index}",
            "channel_id": f"channel-{index}",
            "title": "A precise AI topic",
            "description": "Evidence",
            "upload_date": f"2026-0{index + 1}-01T00:00:00Z",
        }
        for index in range(2)
    ]
    path.write_text("\n".join(json.dumps(row) for row in reversed(rows)) + "\n")

    videos = load_structural_cohort(path)

    assert [video.video_id for video in videos] == ["video-0", "video-1"]
    assert maximum_complete_checkpoint(videos, outcome_horizon_days=42) == datetime(
        2025,
        12,
        21,
        tzinfo=UTC,
    )


def _episode(checkpoint_at: datetime, key: str) -> ProbabilityEpisode:
    state = StructuralTopicState(
        topic_key=key,
        label=key,
        observed_at=checkpoint_at,
        score=0,
        specificity_score=90,
        thesis_support_ratio=1,
        eligible=True,
        active_video_count=3,
        recent_video_count=2,
        previous_28d_video_count=1,
        distinct_channel_count=3,
        recent_channel_count=2,
        new_recent_channel_count=2,
        acceleration=1,
        large_channel_count=0,
        channel_size_bucket_count=0,
        member_video_ids=(),
        member_channel_ids=(),
        evidence_titles=(),
    )
    outcome = StructuralTopicOutcome(
        topic_key=key,
        fired=False,
        fired_at=None,
        lead_days=None,
        future_video_count=0,
        expected_future_supply=0,
        supply_growth=0,
        new_future_channel_count=0,
        new_channel_share=0,
        baseline_coverage=0,
        outlier_video_count=0,
        median_outlier_ratio=None,
    )
    return ProbabilityEpisode(checkpoint_at, state, outcome, {})


def test_weekly_and_fit_calibration_splits_are_temporal() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    checkpoints = weekly_checkpoints(start, start + timedelta(days=35))
    episodes = tuple(
        _episode(checkpoint, str(index)) for index, checkpoint in enumerate(checkpoints)
    )

    fitting, calibration, boundary = temporal_fit_calibration_split(episodes)

    assert len(checkpoints) == 6
    assert max(episode.checkpoint_at for episode in fitting) < boundary
    assert min(episode.checkpoint_at for episode in calibration) == boundary
