"""Idempotently project existing features and baselines into the derived ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.database import SessionLocal
from apps.api.derived_store import compute_input_fingerprint
from apps.api.models import ChannelBaseline, DerivedMetricPoint, VideoFeature

BACKFILL_TAG = "backfill"
MetricKey = tuple[str, str, str, str, str, datetime]


def _metric_key(
    subject_type: str,
    subject_id: str,
    metric_name: str,
    window: str,
    scoring_version: str,
    computed_at: datetime,
) -> MetricKey:
    return (
        subject_type,
        subject_id,
        metric_name,
        window,
        scoring_version,
        computed_at,
    )


def _existing_metric_keys(session: Session) -> set[MetricKey]:
    return set(
        session.execute(
            select(
                DerivedMetricPoint.subject_type,
                DerivedMetricPoint.subject_id,
                DerivedMetricPoint.metric_name,
                DerivedMetricPoint.window,
                DerivedMetricPoint.scoring_version,
                DerivedMetricPoint.computed_at,
            )
        ).tuples()
    )


def _backfill_id(key: MetricKey) -> str:
    serialized = "|".join((*key[:5], key[5].isoformat()))
    return str(uuid5(NAMESPACE_URL, f"earlysignal:derived-backfill:{serialized}"))


def backfill_video_features(session: Session) -> int:
    existing = _existing_metric_keys(session)
    written = 0
    for feature in session.scalars(select(VideoFeature)):
        metrics = {
            "outlier_ratio": feature.outlier_ratio,
            "view_velocity": feature.view_velocity,
            "velocity_acceleration": feature.velocity_acceleration,
            "engagement_rate": feature.engagement_rate,
        }
        for metric_name, value in metrics.items():
            key = _metric_key(
                "video",
                feature.video_id,
                metric_name,
                "latest",
                feature.feature_version,
                feature.calculated_at,
            )
            if key in existing:
                continue
            session.add(
                DerivedMetricPoint(
                    id=_backfill_id(key),
                    subject_type="video",
                    subject_id=feature.video_id,
                    metric_name=metric_name,
                    value=value,
                    window="latest",
                    computed_at=feature.calculated_at,
                    scoring_version=feature.feature_version,
                    input_fingerprint=compute_input_fingerprint(
                        BACKFILL_TAG,
                        feature.video_id,
                        metric_name,
                        feature.calculated_at.isoformat(),
                    ),
                )
            )
            existing.add(key)
            written += 1
    return written


def backfill_channel_baselines(session: Session) -> int:
    existing = _existing_metric_keys(session)
    written = 0
    for baseline in session.scalars(select(ChannelBaseline)):
        key = _metric_key(
            "channel",
            baseline.channel_id,
            baseline.metric_name,
            baseline.window,
            baseline.version,
            baseline.calculated_at,
        )
        if key in existing:
            continue
        session.add(
            DerivedMetricPoint(
                id=_backfill_id(key),
                subject_type="channel",
                subject_id=baseline.channel_id,
                metric_name=baseline.metric_name,
                value=baseline.metric_value,
                window=baseline.window,
                computed_at=baseline.calculated_at,
                scoring_version=baseline.version,
                input_fingerprint=compute_input_fingerprint(
                    BACKFILL_TAG,
                    baseline.id,
                    baseline.metric_name,
                    baseline.calculated_at.isoformat(),
                ),
            )
        )
        existing.add(key)
        written += 1
    return written


def main() -> None:
    started_at = datetime.now(tz=UTC)
    with SessionLocal() as session:
        features_written = backfill_video_features(session)
        baselines_written = backfill_channel_baselines(session)
        session.commit()
    duration = (datetime.now(tz=UTC) - started_at).total_seconds()
    print(
        "backfilled derived_metric_points: "
        f"{features_written} video-feature points, "
        f"{baselines_written} channel-baseline points in {duration:.1f}s"
    )


if __name__ == "__main__":
    main()
