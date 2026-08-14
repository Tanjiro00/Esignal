from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestCohort,
    BacktestCohortCheckpoint,
    BacktestOutcome,
    BacktestPrediction,
    Base,
    Topic,
    TopicSnapshot,
    VideoSnapshot,
    VideoSnapshotJob,
    YoutubeChannel,
    YoutubeVideo,
)
from packages.backtest import CohortPolicy, HistoricalCohortService, InsufficientCohortData

START = datetime(2026, 7, 1, 12, tzinfo=UTC)
FREEZE_AT = START + timedelta(days=9)


def _session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session, *, days: int = 8) -> list[datetime]:
    channel = YoutubeChannel(
        id="channel-1",
        youtube_channel_id="UCcohort",
        canonical_url="https://youtube.com/channel/UCcohort",
        title="Cohort Channel",
        description="",
        country="US",
        default_language="en",
        subscriber_count=10_000,
        video_count=1,
        view_count=1_000_000,
        published_at=START - timedelta(days=365),
        last_observed_at=START,
        created_at=START,
        updated_at=START,
    )
    video = YoutubeVideo(
        id="video-1",
        youtube_video_id="cohort-video",
        channel_id=channel.id,
        canonical_url="https://youtube.com/watch?v=cohort-video",
        title="A direct observation",
        description="",
        published_at=START - timedelta(days=3),
        duration_seconds=600,
        default_language="en",
        category_id="28",
        is_short=False,
        is_live=False,
        thumbnail_url="",
        first_discovered_at=START - timedelta(days=2),
        discovery_lag_seconds=86_400,
        last_observed_at=FREEZE_AT,
        created_at=START - timedelta(days=2),
        updated_at=START,
    )
    snapshot = VideoSnapshot(
        id="video-snapshot-1",
        video_id=video.id,
        observed_at=START - timedelta(days=1),
        video_age_seconds=172_800,
        view_count=5_000,
        like_count=200,
        comment_count=30,
        views_per_hour=104,
        likes_per_1000_views=40,
        comments_per_1000_views=6,
        snapshot_quality="direct",
        is_estimated=False,
        provider_fetch_id=None,
    )
    snapshot_job = VideoSnapshotJob(
        id="snapshot-job-1",
        video_id=video.id,
        scheduled_age_seconds=86_400,
        run_at=START - timedelta(days=2),
        status="success",
        idempotency_key="snapshot-job-1",
        attempt_count=1,
        started_at=START - timedelta(days=2),
        completed_at=START - timedelta(days=2),
        provider_fetch_id=None,
        skip_reason=None,
        error_code=None,
        error_message=None,
        created_at=START - timedelta(days=2),
        updated_at=START - timedelta(days=2),
    )
    topic = Topic(
        id="topic-1",
        canonical_label="Frozen topic",
        aliases_json=[],
        entities_json=["frozen"],
        centroid_embedding=[0.1],
        embedding_model="test",
        embedding_version="test",
        first_observed_at=START,
        first_confirmed_at=START,
        lifecycle_stage="Emerging",
        status="active",
        source_kind="live",
        merged_into_topic_id=None,
        clustering_version="test",
        identity_json={},
        specificity_score=90,
        thesis_support_ratio=1,
        visibility_reason_codes_json=[],
    )
    session.add(channel)
    session.flush()
    session.add(video)
    session.flush()
    session.add_all((snapshot, snapshot_job, topic))
    session.flush()
    cutoffs: list[datetime] = []
    for offset in range(days):
        observed_at = START + timedelta(days=offset)
        cutoffs.append(observed_at)
        session.add(
            TopicSnapshot(
                id=f"topic-snapshot-{offset}",
                topic_id=topic.id,
                observed_at=observed_at,
                video_count_24h=4 + offset,
                video_count_72h=6 + offset,
                distinct_channels_72h=5,
                aggregate_view_velocity=2_000 + offset,
                median_outlier_ratio=2.5,
                large_channel_count=0,
                demand_score=70,
                saturation_score=20,
                fragility_score=10,
                component_json={
                    "baseline_coverage": 0.9,
                    "distinct_channels": 5,
                    "previous_video_count_24h": 2,
                    "score": 80 + offset,
                    "snapshot_coverage": 1,
                    "specificity_score": 90,
                    "top_channel_share": 0.3,
                    "top_outlier_ratio": 3.5,
                    "top_velocity_share": 0.4,
                    "transcript_coverage": 0.5,
                    "video_count": 8 + offset,
                },
            )
        )
    session.commit()
    return cutoffs


def test_freeze_creates_immutable_chronological_train_holdout_cohort() -> None:
    with _session() as session:
        cutoffs = _seed(session)
        service = HistoricalCohortService(session)
        policy = CohortPolicy(checkpoint_count=8, holdout_count=2)

        result = service.freeze(
            name="test frozen cohort",
            freeze_at=FREEZE_AT,
            source_environment="test",
            policy=policy,
            checkpoint_times=cutoffs,
        )
        repeated = service.freeze(
            name="test frozen cohort",
            freeze_at=FREEZE_AT,
            source_environment="test",
            policy=policy,
            checkpoint_times=cutoffs,
        )

        cohort = session.get(BacktestCohort, result.cohort_id)
        links = list(
            session.scalars(
                select(BacktestCohortCheckpoint)
                .where(BacktestCohortCheckpoint.cohort_id == result.cohort_id)
                .order_by(BacktestCohortCheckpoint.ordinal)
            )
        )
        assert cohort is not None
        assert cohort.status == "frozen"
        assert cohort.train_checkpoint_count == 6
        assert cohort.holdout_checkpoint_count == 2
        assert [row.split for row in links] == ["train"] * 6 + ["holdout"] * 2
        assert tuple(result.checkpoint_ids) == tuple(repeated.checkpoint_ids)
        assert result.dataset_hash == repeated.dataset_hash
        assert "Complete 42-day outcomes:** 0/8" in result.markdown_report
        assert session.scalar(select(func.count(BacktestCohort.id))) == 1
        assert session.scalar(select(func.count(BacktestCheckpoint.id))) == 8
        assert session.scalar(select(func.count(BacktestPrediction.id))) == 8
        assert session.scalar(select(func.count(BacktestOutcome.id))) == 0


def test_freeze_refuses_to_invent_missing_checkpoint_history() -> None:
    with _session() as session:
        cutoffs = _seed(session, days=7)
        service = HistoricalCohortService(session)

        with pytest.raises(InsufficientCohortData) as raised:
            service.freeze(
                name="insufficient",
                freeze_at=FREEZE_AT,
                source_environment="test",
                policy=CohortPolicy(checkpoint_count=8, holdout_count=2),
                checkpoint_times=cutoffs,
            )

        assert raised.value.available == 7
        assert session.scalar(select(func.count(BacktestCohort.id))) == 0
        assert session.scalar(select(func.count(BacktestCheckpoint.id))) == 0


def test_inspect_rejects_future_freeze_time() -> None:
    with _session() as session:
        service = HistoricalCohortService(session)

        with pytest.raises(ValueError, match="freeze_at cannot be in the future"):
            service.inspect(
                freeze_at=datetime.now(tz=UTC) + timedelta(minutes=1),
                checkpoint_times=[],
            )
