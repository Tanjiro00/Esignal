from __future__ import annotations

from datetime import UTC, datetime, timedelta

from es_core.demand import DemandModel, DemandPolicy, ViewObservation
from es_core.entity import EntityEvidence, resolve
from es_core.outcome import DemandGapPolicy, evaluate_demand_gap
from es_core.types import Video

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def video(video_id: str, channel_id: str, *, days_ago: float) -> Video:
    moment = NOW - timedelta(days=days_ago)
    return Video(video_id, channel_id, f"title {video_id}", moment, moment)


def observation(video_id: str, *, age_days: float, views: int) -> ViewObservation:
    return ViewObservation(video_id, NOW, age_days, views)


def channel_history(channel_id: str, *, base_views: int, count: int = 5) -> tuple[list, list]:
    videos = [
        video(f"{channel_id}_h{index}", channel_id, days_ago=40 + index * 5)
        for index in range(count)
    ]
    observations = [observation(item.video_id, age_days=7.0, views=base_views) for item in videos]
    return videos, observations


# ---------------------------------------------------------------------- demand


def test_lift_is_relative_to_the_channel_not_the_absolute_view_count() -> None:
    """40k views is a triumph for one channel and a failure for another."""

    small_videos, small_observations = channel_history("small", base_views=1_000)
    large_videos, large_observations = channel_history("large", base_views=100_000)
    small_hit = video("small_hit", "small", days_ago=8)
    large_miss = video("large_miss", "large", days_ago=8)

    model = DemandModel.build(
        [*small_videos, *large_videos, small_hit, large_miss],
        [
            *small_observations,
            *large_observations,
            observation("small_hit", age_days=7.0, views=40_000),
            observation("large_miss", age_days=7.0, views=40_000),
        ],
        as_of=NOW,
    )

    small_lift = model.normalized_lift("small_hit", channel_id="small")
    large_lift = model.normalized_lift("large_miss", channel_id="large")

    assert small_lift is not None and small_lift > 3.0
    assert large_lift is not None and large_lift < 0.0


def test_missing_baseline_is_reported_not_guessed() -> None:
    lonely = video("lonely", "unknown", days_ago=3)
    model = DemandModel.build(
        [lonely], [observation("lonely", age_days=3.0, views=5_000)], as_of=NOW
    )

    assert model.normalized_lift("lonely", channel_id="unknown") is None


def test_future_observations_never_enter_the_model() -> None:
    videos, observations = channel_history("chan", base_views=1_000)
    late = ViewObservation("chan_h0", NOW + timedelta(days=5), 7.0, 999_999)

    model = DemandModel.build(videos, [*observations, late], as_of=NOW, policy=DemandPolicy())

    assert model.normalized_lift("chan_h0", channel_id="chan") == 0.0


# --------------------------------------------------------------------- outcome


def test_demand_gap_fires_only_when_videos_beat_their_own_channels() -> None:
    future = [video(f"f{index}", f"c{index}", days_ago=-index - 1) for index in range(4)]
    strong = evaluate_demand_gap(
        as_of=NOW,
        future_videos=future,
        lift_of=lambda _video: 1.2,
        policy=DemandGapPolicy(horizon_days=21),
    )
    weak = evaluate_demand_gap(
        as_of=NOW,
        future_videos=future,
        lift_of=lambda _video: 0.1,
        policy=DemandGapPolicy(horizon_days=21),
    )

    assert strong.fired
    assert not weak.fired


def test_demand_gap_detects_saturation() -> None:
    future = [video(f"f{index}", f"c{index}", days_ago=-index - 1) for index in range(6)]
    lifts = {"f0": 1.5, "f1": 1.4, "f2": 1.3, "f3": 0.2, "f4": 0.1, "f5": 0.0}

    outcome = evaluate_demand_gap(
        as_of=NOW,
        future_videos=future,
        lift_of=lambda item: lifts[item.video_id],
        policy=DemandGapPolicy(horizon_days=21),
    )

    assert outcome.saturating


# ---------------------------------------------------------------------- entity


def test_only_structurally_named_terms_become_entities() -> None:
    """A term inside a comment body is a mention; a headline is a naming."""

    incidental = resolve(
        "26b",
        [
            EntityEvidence("hackernews", NOW, 1.0, "body", "Running Gemma 4 26B locally", ""),
        ],
    )
    named = resolve(
        "ecc",
        [
            EntityEvidence("github", NOW, 5.0, "name", "org/ecc", ""),
            EntityEvidence("hackernews", NOW, 2.0, "title", "ECC agent OS hits 235k stars", ""),
        ],
    )

    assert not incidental.confirmed
    assert named.confirmed
    assert named.corroborated


def test_entity_evidence_respects_the_checkpoint() -> None:
    entity = resolve(
        "astra",
        [
            EntityEvidence("hackernews", NOW - timedelta(days=2), 1.0, "title", "Astra", ""),
            EntityEvidence("hackernews", NOW + timedelta(days=2), 1.0, "title", "Astra", ""),
        ],
        as_of=NOW,
    )

    assert entity.structural_mentions == 1
    assert entity.lead_days(NOW + timedelta(days=1)) == 3.0
