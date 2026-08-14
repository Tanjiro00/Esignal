from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apps.api.models import Signal, Topic, TopicSnapshot, TopicSnapshotBucket
from packages.timeline import (
    SNAPSHOT_BUCKET_VERSION,
    SnapshotMeasurement,
    bucket_snapshot_measurements,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _measurement(snapshot: TopicSnapshot, stage: str) -> SnapshotMeasurement:
    components = snapshot.component_json
    return SnapshotMeasurement(
        id=snapshot.id,
        observed_at=_aware(snapshot.observed_at),
        video_count=int(components.get("video_count", snapshot.video_count_72h)),
        channel_count=int(components.get("distinct_channels", snapshot.distinct_channels_72h)),
        score=float(components.get("score", 0)),
        momentum=float(components.get("momentum", snapshot.aggregate_view_velocity)),
        saturation=float(snapshot.saturation_score),
        stage=stage,
        values={
            "aggregate_view_velocity": snapshot.aggregate_view_velocity,
            "video_count_24h": float(snapshot.video_count_24h),
            "video_count_72h": float(snapshot.video_count_72h),
            "distinct_channels_72h": float(snapshot.distinct_channels_72h),
            "median_outlier_ratio": snapshot.median_outlier_ratio,
            "demand_score": snapshot.demand_score,
            "saturation_score": snapshot.saturation_score,
            "fragility_score": snapshot.fragility_score,
            "large_channel_count": float(snapshot.large_channel_count),
        },
    )


def rebuild_topic_snapshot_buckets(
    session: Session,
    *,
    topic_id: str,
    captured_at: datetime,
) -> int:
    topic = session.get(Topic, topic_id)
    if topic is None:
        return 0
    snapshots = list(
        session.scalars(
            select(TopicSnapshot)
            .where(TopicSnapshot.topic_id == topic_id)
            .order_by(TopicSnapshot.observed_at, TopicSnapshot.id)
        )
    )
    signal = session.scalar(
        select(Signal)
        .where(Signal.topic_id == topic_id)
        .order_by(Signal.generated_at.desc())
        .limit(1)
    )
    stage = signal.lifecycle_stage if signal is not None else topic.lifecycle_stage
    buckets = bucket_snapshot_measurements(
        [_measurement(snapshot, stage) for snapshot in snapshots],
        captured_at=_aware(captured_at),
    )
    session.execute(delete(TopicSnapshotBucket).where(TopicSnapshotBucket.topic_id == topic_id))
    for bucket in buckets:
        stable_key = (
            f"{topic_id}:{bucket.resolution}:{bucket.bucket_start.isoformat()}:"
            f"{SNAPSHOT_BUCKET_VERSION}"
        )
        session.add(
            TopicSnapshotBucket(
                id=str(uuid5(NAMESPACE_URL, f"earlysignal:snapshot-bucket:{stable_key}")),
                topic_id=topic_id,
                resolution=bucket.resolution,
                bucket_start=bucket.bucket_start,
                bucket_end=bucket.bucket_end,
                first_json=bucket.first,
                last_json=bucket.last,
                min_json=bucket.minimum,
                max_json=bucket.maximum,
                avg_json=bucket.average,
                video_count=bucket.video_count,
                channel_count=bucket.channel_count,
                score=bucket.score,
                momentum=bucket.momentum,
                saturation=bucket.saturation,
                stage=bucket.stage,
                source_measurement_ids_json=list(bucket.source_measurement_ids),
                bucket_version=bucket.version,
                calculated_at=_aware(captured_at),
            )
        )
    session.flush()
    return len(buckets)


def backfill_snapshot_buckets(
    session: Session,
    *,
    captured_at: datetime,
    source_kind: str,
) -> dict[str, int | str]:
    topic_ids = list(
        session.scalars(select(Topic.id).where(Topic.source_kind == source_kind).order_by(Topic.id))
    )
    bucket_count = 0
    for topic_id in topic_ids:
        bucket_count += rebuild_topic_snapshot_buckets(
            session,
            topic_id=topic_id,
            captured_at=captured_at,
        )
    return {
        "topics": len(topic_ids),
        "buckets": bucket_count,
        "version": SNAPSHOT_BUCKET_VERSION,
    }
