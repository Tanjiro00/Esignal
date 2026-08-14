from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

SNAPSHOT_BUCKET_VERSION = "topic-snapshot-buckets-v1"


@dataclass(frozen=True)
class SnapshotMeasurement:
    id: str
    observed_at: datetime
    video_count: int
    channel_count: int
    score: float
    momentum: float
    saturation: float
    stage: str
    values: dict[str, float]


@dataclass(frozen=True)
class SnapshotBucket:
    resolution: str
    bucket_start: datetime
    bucket_end: datetime
    first: dict[str, object]
    last: dict[str, object]
    minimum: dict[str, float]
    maximum: dict[str, float]
    average: dict[str, float]
    video_count: int
    channel_count: int
    score: float
    momentum: float
    saturation: float
    stage: str
    source_measurement_ids: tuple[str, ...]
    version: str = SNAPSHOT_BUCKET_VERSION


def _aware(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _resolution(observed_at: datetime, captured_at: datetime) -> tuple[str, int]:
    age = max(timedelta(), _aware(captured_at) - _aware(observed_at))
    if age <= timedelta(hours=6):
        return "15m", 15 * 60
    if age <= timedelta(hours=72):
        return "1h", 60 * 60
    if age <= timedelta(days=14):
        return "6h", 6 * 60 * 60
    return "1d", 24 * 60 * 60


def _floor(value: datetime, seconds: int) -> datetime:
    timestamp = int(_aware(value).timestamp())
    return datetime.fromtimestamp(timestamp - timestamp % seconds, tz=UTC)


def _record(measurement: SnapshotMeasurement) -> dict[str, object]:
    return {
        **asdict(measurement),
        "observed_at": _aware(measurement.observed_at).isoformat(),
    }


def bucket_snapshot_measurements(
    measurements: list[SnapshotMeasurement],
    *,
    captured_at: datetime,
) -> list[SnapshotBucket]:
    grouped: defaultdict[tuple[str, datetime, int], list[SnapshotMeasurement]] = defaultdict(list)
    for measurement in measurements:
        resolution, seconds = _resolution(measurement.observed_at, captured_at)
        start = _floor(measurement.observed_at, seconds)
        grouped[(resolution, start, seconds)].append(measurement)

    buckets: list[SnapshotBucket] = []
    for (resolution, start, seconds), rows in grouped.items():
        ordered = sorted(rows, key=lambda row: (_aware(row.observed_at), row.id))
        keys = sorted({key for row in ordered for key in row.values})
        minimum = {
            key: round(min(float(row.values.get(key, 0)) for row in ordered), 4) for key in keys
        }
        maximum = {
            key: round(max(float(row.values.get(key, 0)) for row in ordered), 4) for key in keys
        }
        average = {
            key: round(
                sum(float(row.values.get(key, 0)) for row in ordered) / len(ordered),
                4,
            )
            for key in keys
        }
        last = ordered[-1]
        buckets.append(
            SnapshotBucket(
                resolution=resolution,
                bucket_start=start,
                bucket_end=start + timedelta(seconds=seconds),
                first=_record(ordered[0]),
                last=_record(last),
                minimum=minimum,
                maximum=maximum,
                average=average,
                video_count=last.video_count,
                channel_count=last.channel_count,
                score=last.score,
                momentum=last.momentum,
                saturation=last.saturation,
                stage=last.stage,
                source_measurement_ids=tuple(row.id for row in ordered),
            )
        )
    return sorted(buckets, key=lambda bucket: (bucket.bucket_start, bucket.resolution))
