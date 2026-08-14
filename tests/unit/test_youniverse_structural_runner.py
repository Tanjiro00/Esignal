from datetime import UTC, datetime

from packages.backtest.youniverse_replay import (
    StructuralCheckpoint,
    StructuralTopicOutcome,
    StructuralTopicState,
)
from scripts.run_youniverse_structural_backtest import summarize_structural_checkpoints


def _state(key: str, score: float) -> StructuralTopicState:
    return StructuralTopicState(
        topic_key=key,
        label=key,
        observed_at=datetime(2019, 1, 1, tzinfo=UTC),
        score=score,
        specificity_score=80,
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
        channel_size_bucket_count=2,
        member_video_ids=("one",),
        member_channel_ids=("channel",),
        evidence_titles=("Evidence",),
    )


def _outcome(key: str, fired: bool) -> StructuralTopicOutcome:
    return StructuralTopicOutcome(
        topic_key=key,
        fired=fired,
        fired_at=datetime(2019, 1, 30, tzinfo=UTC) if fired else None,
        lead_days=29 if fired else None,
        future_video_count=20,
        expected_future_supply=6,
        supply_growth=3.33,
        new_future_channel_count=10,
        new_channel_share=1,
        baseline_coverage=1,
        outlier_video_count=10,
        median_outlier_ratio=5,
    )


def test_runner_summary_compares_method_with_candidate_base_rate() -> None:
    winner = _state("winner", 80)
    loser = _state("loser", 20)
    checkpoint = StructuralCheckpoint(
        checkpoint_at=datetime(2019, 1, 1, tzinfo=UTC),
        candidates=(winner, loser),
        predictions=(winner,),
        rankings={
            "method": (winner,),
            "supply": (winner, loser),
            "acceleration": (loser,),
            "channels": (winner,),
            "random": (loser,),
        },
        outcomes=(_outcome("winner", True), _outcome("loser", False)),
    )

    metrics = summarize_structural_checkpoints((checkpoint,))

    assert metrics["candidate_base_rate_percent"] == 50
    assert metrics["rankings"]["method"]["precision_at_10_percent"] == 100
    assert metrics["rankings"]["supply"]["precision_at_10_percent"] == 50
    assert metrics["rankings"]["method"]["future_video_baseline_coverage_percent"] == 100
