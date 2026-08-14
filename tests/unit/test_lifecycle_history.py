from datetime import UTC, datetime, timedelta

from apps.api.lifecycle import (
    HistoricalLifecycleMeasurement,
    build_earlyness_claim,
    classify_historical_lifecycle,
)


def _measurement(**overrides: int | float) -> HistoricalLifecycleMeasurement:
    values: dict[str, str | datetime | int | float | None] = {
        "measurement_id": "measurement-1",
        "observed_at": datetime(2026, 7, 20, tzinfo=UTC),
        "video_count_24h": 3,
        "video_count_72h": 6,
        "previous_video_count_24h": 1,
        "distinct_channels": 6,
        "distinct_channels_72h": 6,
        "aggregate_view_velocity": 4_000,
        "large_channel_count": 1,
        "saturation_score": 30,
        "score": 72,
    }
    values.update(overrides)
    return HistoricalLifecycleMeasurement(**values)  # type: ignore[arg-type]


def test_historical_lifecycle_is_derived_from_point_in_time_measurement() -> None:
    assert classify_historical_lifecycle(_measurement()) == "Breakout"
    assert (
        classify_historical_lifecycle(
            _measurement(
                distinct_channels=3,
                distinct_channels_72h=3,
                video_count_24h=2,
                video_count_72h=3,
                aggregate_view_velocity=500,
            )
        )
        == "Emerging"
    )
    assert (
        classify_historical_lifecycle(
            _measurement(
                distinct_channels=8,
                large_channel_count=3,
            )
        )
        == "Mass Market"
    )
    assert classify_historical_lifecycle(_measurement(saturation_score=78)) == "Saturated"


def test_positive_lead_time_is_reported_as_early() -> None:
    visible_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    claim, headline, _, lead_hours, _ = build_earlyness_claim(
        current_stage="Breakout",
        first_signal_visible_at=visible_at,
        first_breakout_at=visible_at + timedelta(days=3),
        first_large_channel_adoption_at=None,
    )
    assert claim == "early"
    assert headline == "Detected 3 days before breakout"
    assert lead_hours == 72


def test_negative_lead_time_never_becomes_an_early_claim() -> None:
    breakout_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    claim, headline, supporting, lead_hours, _ = build_earlyness_claim(
        current_stage="Breakout",
        first_signal_visible_at=breakout_at + timedelta(hours=8),
        first_breakout_at=breakout_at,
        first_large_channel_adoption_at=None,
    )
    assert claim == "late"
    assert headline == "Signal became visible after breakout"
    assert "before breakout" not in headline.lower()
    assert "no early lead-time claim" in supporting.lower()
    assert lead_hours == -8


def test_missing_breakout_is_an_explicit_pending_state() -> None:
    claim, headline, supporting, lead_hours, large_lead = build_earlyness_claim(
        current_stage="Emerging",
        first_signal_visible_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        first_breakout_at=None,
        first_large_channel_adoption_at=None,
    )
    assert claim == "pending"
    assert headline == "Currently Emerging"
    assert supporting == ("Breakout not detected yet. Large-channel adoption not detected.")
    assert lead_hours is None
    assert large_lead is None
