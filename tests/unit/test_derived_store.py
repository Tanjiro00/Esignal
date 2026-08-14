from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.derived_store import (
    RAW_SNAPSHOT_TTL,
    compute_input_fingerprint,
    project_raw_to_derived,
    record_raw_api_snapshot,
)
from apps.api.models import Base, DerivedMetricPoint, RawApiSnapshot, VideoFeature
from scripts.backfill_derived_metric_points import backfill_video_features


def test_compute_input_fingerprint_is_order_independent_and_stable() -> None:
    first = compute_input_fingerprint("snap-1", "snap-2", "2026-07-31T00:00:00+00:00")
    second = compute_input_fingerprint("snap-2", "snap-1", "2026-07-31T00:00:00+00:00")
    assert first == second
    assert len(first) == 64


def test_record_raw_api_snapshot_sets_30_day_ttl() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    fetched_at = datetime(2026, 7, 1, tzinfo=UTC)
    with Session(engine) as session:
        record_raw_api_snapshot(
            session,
            video_id="video-1",
            provider="youtube_official",
            payload={"view_count": 1000},
            fetched_at=fetched_at,
            provenance={"source": "official"},
        )
        session.commit()
        stored = session.scalar(select(RawApiSnapshot))
        assert stored is not None
        assert stored.expires_at.replace(tzinfo=UTC) == fetched_at + RAW_SNAPSHOT_TTL
        assert stored.expires_at - stored.fetched_at == timedelta(days=30)
        assert stored.provenance["source"] == "official"


def test_record_raw_api_snapshot_rejects_non_official_provider() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            record_raw_api_snapshot(
                session,
                video_id="video-1",
                provider="youtube_web",
                payload={},
                fetched_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        except ValueError as exc:
            assert "youtube_official" in str(exc)
        else:
            raise AssertionError("non-official raw snapshot provider was accepted")


def test_project_raw_to_derived_writes_versioned_points() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    computed_at = datetime(2026, 7, 31, tzinfo=UTC)
    with Session(engine) as session:
        points = project_raw_to_derived(
            session,
            subject_type="video",
            subject_id="video-1",
            window="latest",
            metrics={"outlier_ratio": 2.13, "view_velocity": 481.0},
            scoring_version="video-intelligence-v1",
            input_fingerprint=compute_input_fingerprint("snap-1", "snap-2"),
            computed_at=computed_at,
        )
        session.commit()
        assert len(points) == 2
        stored = list(session.scalars(select(DerivedMetricPoint)))
        assert {point.metric_name for point in stored} == {
            "outlier_ratio",
            "view_velocity",
        }
        assert all(point.scoring_version == "video-intelligence-v1" for point in stored)
        assert all(point.computed_at.replace(tzinfo=UTC) == computed_at for point in stored)


def test_video_feature_backfill_is_idempotent_and_uses_valid_ids() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    calculated_at = datetime(2026, 7, 31, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            VideoFeature(
                video_id="video-1",
                feature_version="video-intelligence-v1",
                language_probability=1,
                vertical_relevance=1,
                outlier_ratio=2.1,
                view_velocity=400,
                velocity_acceleration=30,
                engagement_rate=0.08,
                novelty_score=0,
                spam_probability=0,
                calculated_at=calculated_at,
            )
        )
        session.commit()

        assert backfill_video_features(session) == 4
        session.commit()
        assert backfill_video_features(session) == 0
        stored = list(session.scalars(select(DerivedMetricPoint)))
        assert len(stored) == 4
        assert all(len(point.id) == 36 for point in stored)
