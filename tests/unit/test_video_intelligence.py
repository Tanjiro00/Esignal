from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    Base,
    ChannelBaseline,
    VideoFeature,
    VideoSnapshot,
    VideoSnapshotJob,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.worker.video_intelligence import (
    BASELINE_VERSION,
    FEATURE_VERSION,
    VideoIntelligenceService,
)
from packages.domain import VideoMetadata


def _channel(now: datetime) -> YoutubeChannel:
    return YoutubeChannel(
        id="channel-1",
        youtube_channel_id="UC_REAL_CHANNEL",
        canonical_url="https://www.youtube.com/channel/UC_REAL_CHANNEL",
        title="Test channel",
        description="",
        country="US",
        default_language="en",
        subscriber_count=1000,
        video_count=3,
        view_count=10000,
        published_at=now - timedelta(days=365),
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def _video(
    video_id: str,
    now: datetime,
    *,
    published_at: datetime | None = None,
    discovered_at: datetime | None = None,
) -> YoutubeVideo:
    published = published_at or now - timedelta(hours=1)
    discovered = discovered_at or now
    return YoutubeVideo(
        id=video_id,
        youtube_video_id=f"youtube-{video_id}",
        channel_id="channel-1",
        canonical_url=f"https://www.youtube.com/watch?v=youtube-{video_id}",
        title=f"AI agent test {video_id}",
        description="coding automation",
        published_at=published,
        duration_seconds=600,
        default_language="en",
        category_id="28",
        is_short=False,
        is_live=False,
        thumbnail_url="https://example.com/thumb.jpg",
        first_discovered_at=discovered,
        discovery_lag_seconds=0,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def _service(session: Session, tmp_path: object) -> VideoIntelligenceService:
    return VideoIntelligenceService(
        session,
        Settings(
            youtube_api_key="test-only",
            raw_payload_directory=str(tmp_path),
        ),
    )


def test_snapshot_schedule_skips_unobservable_ages_and_is_idempotent(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(_channel(now))
        video = _video(
            "video-1",
            now,
            published_at=now - timedelta(hours=2),
            discovered_at=now - timedelta(minutes=45),
        )
        session.add(video)
        session.commit()

        service = _service(session, tmp_path)
        assert service.schedule_video(video, now=now) == 11
        session.commit()
        assert service.schedule_video(video, now=now) == 0

        jobs = list(
            session.scalars(
                select(VideoSnapshotJob).order_by(VideoSnapshotJob.scheduled_age_seconds)
            )
        )
        assert video.discovery_lag_seconds == 75 * 60
        assert [job.status for job in jobs[:2]] == ["skipped", "skipped"]
        assert all(job.status == "pending" for job in jobs[2:])
        assert len({job.idempotency_key for job in jobs}) == len(jobs)


def test_snapshots_are_immutable_and_features_use_channel_baselines(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(_channel(now))
        videos = [_video(f"video-{index}", now) for index in range(1, 4)]
        session.add_all(videos)
        session.flush()
        for video, views in zip(videos, (100, 200, 500), strict=True):
            session.add(
                VideoSnapshot(
                    id=f"snapshot-{video.id}",
                    video_id=video.id,
                    observed_at=now,
                    video_age_seconds=3600,
                    view_count=views,
                    like_count=views // 10,
                    comment_count=views // 100,
                    views_per_hour=float(views),
                    likes_per_1000_views=100,
                    comments_per_1000_views=10,
                    snapshot_quality="direct",
                    is_estimated=False,
                    provider_fetch_id=None,
                )
            )
        session.commit()

        service = _service(session, tmp_path)
        assert service.recalculate_channel_baselines(["channel-1"]) > 0
        session.commit()
        assert service.calculate_video_features([videos[-1].id]) == 1
        session.commit()

        baseline = session.scalar(
            select(ChannelBaseline).where(
                ChannelBaseline.channel_id == "channel-1",
                ChannelBaseline.window == "1h",
                ChannelBaseline.metric_name == "median_views_at_1h",
                ChannelBaseline.version == BASELINE_VERSION,
            )
        )
        feature = session.get(VideoFeature, (videos[-1].id, FEATURE_VERSION))
        assert baseline is not None
        assert baseline.metric_value == pytest.approx(200)
        assert feature is not None
        assert feature.outlier_ratio == pytest.approx(2.5)
        assert feature.view_velocity == pytest.approx(500)
        assert feature.engagement_rate == pytest.approx(110)

        metadata = VideoMetadata(
            video_id=videos[0].youtube_video_id,
            channel_id="UC_REAL_CHANNEL",
            title=videos[0].title,
            description=videos[0].description,
            published_at=videos[0].published_at,
            duration_seconds=videos[0].duration_seconds,
            view_count=150,
            like_count=15,
            comment_count=2,
            thumbnail_url=videos[0].thumbnail_url,
            raw_ref="fetch://immutable-fetch",
        )
        first = service.record_snapshot_from_metadata(
            videos[0],
            metadata,
            observed_at=now + timedelta(minutes=10),
        )
        second = service.record_snapshot_from_metadata(
            videos[0],
            metadata,
            observed_at=now + timedelta(minutes=20),
        )
        session.commit()
        assert first is not None
        assert second is None
        assert (
            session.scalar(
                select(func.count(VideoSnapshot.id)).where(VideoSnapshot.video_id == videos[0].id)
            )
            == 2
        )


def test_stale_snapshot_jobs_are_skipped_before_they_consume_provider_capacity(
    tmp_path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(_channel(now))
        video = _video("stale-video", now, published_at=now - timedelta(hours=4))
        current_video = _video("current-video", now, published_at=now - timedelta(hours=2))
        session.add_all((video, current_video))
        session.flush()
        session.add_all(
            [
                VideoSnapshotJob(
                    id="stale-job",
                    video_id=video.id,
                    scheduled_age_seconds=3600,
                    run_at=now - timedelta(hours=3),
                    status="pending",
                    idempotency_key="snapshot:stale",
                    attempt_count=0,
                    started_at=None,
                    completed_at=None,
                    provider_fetch_id=None,
                    skip_reason=None,
                    error_code=None,
                    error_message=None,
                    created_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=3),
                ),
                VideoSnapshotJob(
                    id="current-job",
                    video_id=current_video.id,
                    scheduled_age_seconds=3600,
                    run_at=now - timedelta(minutes=10),
                    status="pending",
                    idempotency_key="snapshot:current",
                    attempt_count=0,
                    started_at=None,
                    completed_at=None,
                    provider_fetch_id=None,
                    skip_reason=None,
                    error_code=None,
                    error_message=None,
                    created_at=now - timedelta(minutes=10),
                    updated_at=now - timedelta(minutes=10),
                ),
            ]
        )
        session.commit()

        skipped = _service(session, tmp_path).expire_stale_jobs(now=now)

        assert skipped == 1
        assert session.get(VideoSnapshotJob, "stale-job").status == "skipped"
        assert session.get(VideoSnapshotJob, "stale-job").skip_reason == "missed_snapshot_window"
        assert session.get(VideoSnapshotJob, "current-job").status == "pending"
