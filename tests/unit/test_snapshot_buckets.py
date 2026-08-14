from datetime import UTC, datetime, timedelta

from packages.timeline import SnapshotMeasurement, bucket_snapshot_measurements


def _measurement(index: int, observed_at: datetime, velocity: float) -> SnapshotMeasurement:
    return SnapshotMeasurement(
        id=f"measurement-{index}",
        observed_at=observed_at,
        video_count=index + 1,
        channel_count=index + 2,
        score=40 + index,
        momentum=velocity,
        saturation=10 + index,
        stage="Emerging",
        values={
            "aggregate_view_velocity": velocity,
            "video_count_24h": float(index + 1),
        },
    )


def test_bucketed_timeline_is_deterministic_and_removes_duplicate_points() -> None:
    captured_at = datetime(2026, 7, 28, 18, tzinfo=UTC)
    measurements = [
        _measurement(0, captured_at - timedelta(minutes=14), 100),
        _measurement(1, captured_at - timedelta(minutes=8), 140),
        _measurement(2, captured_at - timedelta(hours=7, minutes=5), 220),
        _measurement(3, captured_at - timedelta(days=4, hours=1), 300),
        _measurement(4, captured_at - timedelta(days=20), 360),
    ]

    first = bucket_snapshot_measurements(measurements, captured_at=captured_at)
    second = bucket_snapshot_measurements(
        list(reversed(measurements)),
        captured_at=captured_at,
    )

    assert first == second
    assert len(first) == 4
    assert [bucket.resolution for bucket in first] == ["1d", "6h", "1h", "15m"]
    recent = first[-1]
    assert recent.source_measurement_ids == ("measurement-0", "measurement-1")
    assert recent.first["id"] == "measurement-0"
    assert recent.last["id"] == "measurement-1"
    assert recent.minimum["aggregate_view_velocity"] == 100
    assert recent.maximum["aggregate_view_velocity"] == 140
    assert recent.average["aggregate_view_velocity"] == 120
    assert recent.momentum == 140
