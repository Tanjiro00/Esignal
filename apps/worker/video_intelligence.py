from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from uuid import uuid4

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.derived_store import (
    compute_input_fingerprint,
    project_raw_to_derived,
    record_raw_api_snapshot,
)
from apps.api.models import (
    ChannelBaseline,
    VideoFeature,
    VideoSnapshot,
    VideoSnapshotJob,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.provider_operations import SqlAlchemyProviderFetchRecorder
from packages.domain import VideoMetadata
from packages.provider_sdk.youtube_official import YoutubeOfficialProvider

SNAPSHOT_AGES_SECONDS: tuple[int, ...] = (
    30 * 60,
    60 * 60,
    3 * 60 * 60,
    6 * 60 * 60,
    12 * 60 * 60,
    24 * 60 * 60,
    48 * 60 * 60,
    72 * 60 * 60,
    7 * 24 * 60 * 60,
    14 * 24 * 60 * 60,
    30 * 24 * 60 * 60,
)
FEATURE_VERSION = "video-intelligence-v1"
BASELINE_VERSION = "channel-baseline-v1"
AGE_CURVE_EXPONENT: float = 0.65
MINIMUM_SNAPSHOT_GRACE_SECONDS = 15 * 60
SNAPSHOT_GRACE_RATIO = 0.75


@dataclass(frozen=True)
class SnapshotRunResult:
    requested_jobs: int
    completed_jobs: int
    failed_jobs: int
    snapshots_created: int
    features_updated: int
    baselines_updated: int
    stale_jobs_skipped: int = 0


@dataclass(frozen=True)
class ManualRefreshResult:
    requested_videos: int
    snapshots_created: int
    features_updated: int
    baselines_updated: int


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _fetch_id(raw_ref: str) -> str:
    if not raw_ref.startswith("fetch://"):
        raise ValueError(f"Unsupported provider evidence reference: {raw_ref}")
    return raw_ref.removeprefix("fetch://")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


class VideoIntelligenceService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        metadata_provider: YoutubeOfficialProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        recorder = SqlAlchemyProviderFetchRecorder(session, settings)
        self._metadata = metadata_provider or YoutubeOfficialProvider(
            api_key=settings.youtube_api_key,
            recorder=recorder,
        )

    def schedule_video(
        self,
        video: YoutubeVideo,
        *,
        now: datetime | None = None,
    ) -> int:
        observed_at = now or datetime.now(tz=UTC)
        published_at = _aware(video.published_at)
        discovered_at = _aware(video.first_discovered_at)
        discovery_lag = max(
            0,
            round((discovered_at - published_at).total_seconds()),
        )
        video.discovery_lag_seconds = discovery_lag
        created = 0
        for target_age in SNAPSHOT_AGES_SECONDS:
            existing = self._session.scalar(
                select(VideoSnapshotJob.id).where(
                    VideoSnapshotJob.video_id == video.id,
                    VideoSnapshotJob.scheduled_age_seconds == target_age,
                )
            )
            if existing is not None:
                continue
            run_at = published_at + timedelta(seconds=target_age)
            skipped = target_age < discovery_lag
            status = "skipped" if skipped else "pending"
            completed_at = observed_at if skipped else None
            self._session.add(
                VideoSnapshotJob(
                    id=str(uuid4()),
                    video_id=video.id,
                    scheduled_age_seconds=target_age,
                    run_at=run_at,
                    status=status,
                    idempotency_key=f"video_snapshot:{video.id}:{target_age}",
                    attempt_count=0,
                    started_at=None,
                    completed_at=completed_at,
                    provider_fetch_id=None,
                    skip_reason="discovered_after_target" if skipped else None,
                    error_code=None,
                    error_message=None,
                    created_at=observed_at,
                    updated_at=observed_at,
                )
            )
            created += 1
        return created

    def schedule_all(self, *, limit: int = 500) -> int:
        videos = list(
            self._session.scalars(
                select(YoutubeVideo)
                .where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
                .order_by(desc(YoutubeVideo.first_discovered_at))
                .limit(limit)
            )
        )
        created = sum(self.schedule_video(video) for video in videos)
        self._session.commit()
        return created

    def record_snapshot_from_metadata(
        self,
        video: YoutubeVideo,
        metadata: VideoMetadata,
        *,
        observed_at: datetime | None = None,
        quality: str = "direct",
        job: VideoSnapshotJob | None = None,
    ) -> VideoSnapshot | None:
        fetch_id = _fetch_id(metadata.raw_ref)
        existing = self._session.scalar(
            select(VideoSnapshot).where(
                VideoSnapshot.video_id == video.id,
                VideoSnapshot.provider_fetch_id == fetch_id,
            )
        )
        if existing is not None:
            if job is not None:
                self._complete_job(job, fetch_id=fetch_id)
            return None
        captured_at = observed_at or datetime.now(tz=UTC)
        age_seconds = max(
            1,
            round((captured_at - _aware(video.published_at)).total_seconds()),
        )
        views = max(metadata.view_count, 0)
        denominator = max(views, 1)
        snapshot = VideoSnapshot(
            id=str(uuid4()),
            video_id=video.id,
            observed_at=captured_at,
            video_age_seconds=age_seconds,
            view_count=views,
            like_count=max(metadata.like_count, 0),
            comment_count=max(metadata.comment_count, 0),
            views_per_hour=round(views / max(age_seconds / 3600, 0.01), 2),
            likes_per_1000_views=round(metadata.like_count / denominator * 1000, 3),
            comments_per_1000_views=round(
                metadata.comment_count / denominator * 1000,
                3,
            ),
            snapshot_quality=quality,
            is_estimated=False,
            provider_fetch_id=fetch_id,
        )
        self._session.add(snapshot)
        video.last_observed_at = captured_at
        video.updated_at = captured_at
        record_raw_api_snapshot(
            self._session,
            video_id=video.id,
            provider="youtube_official",
            payload={
                "view_count": metadata.view_count,
                "like_count": metadata.like_count,
                "comment_count": metadata.comment_count,
                "duration_seconds": metadata.duration_seconds,
                "default_language": metadata.default_language,
                "category_id": metadata.category_id,
                "is_live": metadata.is_live,
            },
            fetched_at=captured_at,
            provenance={"source": "official", "fetch_id": fetch_id, "quality": quality},
        )
        if job is not None:
            self._complete_job(job, fetch_id=fetch_id)
        return snapshot

    async def refresh_recent(
        self,
        *,
        limit: int = 50,
        video_ids: Iterable[str] | None = None,
    ) -> ManualRefreshResult:
        statement = select(YoutubeVideo).where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
        requested_ids = list(video_ids or ())
        if requested_ids:
            statement = statement.where(YoutubeVideo.id.in_(requested_ids))
        videos = list(
            self._session.scalars(
                statement.order_by(desc(YoutubeVideo.first_discovered_at)).limit(limit)
            )
        )
        if not videos:
            return ManualRefreshResult(0, 0, 0, 0)
        metadata = list(
            await self._metadata.fetch_videos([video.youtube_video_id for video in videos])
        )
        video_by_external_id = {video.youtube_video_id: video for video in videos}
        created = 0
        channel_ids: set[str] = set()
        for item in metadata:
            video = video_by_external_id.get(item.video_id)
            if video is None:
                continue
            self.schedule_video(video)
            if (
                self.record_snapshot_from_metadata(
                    video,
                    item,
                    quality="manual",
                )
                is not None
            ):
                created += 1
            channel_ids.add(video.channel_id)
        self._session.commit()
        baselines = self.recalculate_channel_baselines(channel_ids)
        features = self.calculate_video_features([video.id for video in videos])
        self._session.commit()
        return ManualRefreshResult(
            requested_videos=len(videos),
            snapshots_created=created,
            features_updated=features,
            baselines_updated=baselines,
        )

    async def run_due(self, *, limit: int = 50) -> SnapshotRunResult:
        now = datetime.now(tz=UTC)
        stale_jobs_skipped = self.expire_stale_jobs(now=now)
        jobs = list(
            self._session.scalars(
                select(VideoSnapshotJob)
                .where(
                    VideoSnapshotJob.status == "pending",
                    VideoSnapshotJob.run_at <= now,
                )
                .order_by(VideoSnapshotJob.run_at)
                .limit(limit)
            )
        )
        if not jobs:
            return SnapshotRunResult(0, 0, 0, 0, 0, 0, stale_jobs_skipped)
        for job in jobs:
            job.status = "running"
            job.started_at = now
            job.attempt_count += 1
            job.updated_at = now
        self._session.commit()
        videos = {
            video.id: video
            for video in self._session.scalars(
                select(YoutubeVideo).where(YoutubeVideo.id.in_([job.video_id for job in jobs]))
            )
        }
        try:
            metadata = list(
                await self._metadata.fetch_videos(
                    [
                        videos[job.video_id].youtube_video_id
                        for job in jobs
                        if job.video_id in videos
                    ]
                )
            )
        except Exception as error:
            self._session.rollback()
            for job_id in [job.id for job in jobs]:
                failed_job = self._session.get(VideoSnapshotJob, job_id)
                if failed_job is None:
                    continue
                failed_job.status = "failed"
                failed_job.completed_at = datetime.now(tz=UTC)
                failed_job.error_code = type(error).__name__
                failed_job.error_message = str(error)[:1000]
                failed_job.updated_at = datetime.now(tz=UTC)
            self._session.commit()
            raise
        metadata_by_id = {item.video_id: item for item in metadata}
        completed = 0
        failed_count = 0
        created = 0
        channel_ids: set[str] = set()
        touched_video_ids: list[str] = []
        for job in jobs:
            video = videos.get(job.video_id)
            item = metadata_by_id.get(video.youtube_video_id) if video is not None else None
            if video is None or item is None:
                job.status = "failed"
                job.completed_at = datetime.now(tz=UTC)
                job.error_code = "not_found"
                job.error_message = "Video metadata was unavailable"
                job.updated_at = datetime.now(tz=UTC)
                failed_count += 1
                continue
            if (
                self.record_snapshot_from_metadata(
                    video,
                    item,
                    observed_at=datetime.now(tz=UTC),
                    job=job,
                )
                is not None
            ):
                created += 1
            completed += 1
            channel_ids.add(video.channel_id)
            touched_video_ids.append(video.id)
        self._session.commit()
        baselines = self.recalculate_channel_baselines(channel_ids)
        features = self.calculate_video_features(touched_video_ids)
        self._session.commit()
        return SnapshotRunResult(
            requested_jobs=len(jobs),
            completed_jobs=completed,
            failed_jobs=failed_count,
            snapshots_created=created,
            features_updated=features,
            baselines_updated=baselines,
            stale_jobs_skipped=stale_jobs_skipped,
        )

    def expire_stale_jobs(self, *, now: datetime | None = None) -> int:
        """Skip target-age jobs that can no longer produce a valid age-window sample."""

        checked_at = now or datetime.now(tz=UTC)
        skipped = 0
        for target_age in SNAPSHOT_AGES_SECONDS:
            grace_seconds = max(
                MINIMUM_SNAPSHOT_GRACE_SECONDS,
                round(target_age * SNAPSHOT_GRACE_RATIO),
            )
            result = self._session.execute(
                update(VideoSnapshotJob)
                .where(
                    VideoSnapshotJob.status == "pending",
                    VideoSnapshotJob.scheduled_age_seconds == target_age,
                    VideoSnapshotJob.run_at < checked_at - timedelta(seconds=grace_seconds),
                )
                .values(
                    status="skipped",
                    completed_at=checked_at,
                    skip_reason="missed_snapshot_window",
                    error_code=None,
                    error_message=None,
                    updated_at=checked_at,
                )
            )
            skipped += int(getattr(result, "rowcount", 0) or 0)
        if skipped:
            self._session.commit()
        return skipped

    def _complete_job(
        self,
        job: VideoSnapshotJob,
        *,
        fetch_id: str,
    ) -> None:
        now = datetime.now(tz=UTC)
        job.status = "success"
        job.completed_at = now
        job.provider_fetch_id = fetch_id
        job.error_code = None
        job.error_message = None
        job.updated_at = now

    def recalculate_channel_baselines(
        self,
        channel_ids: Iterable[str] | None = None,
    ) -> int:
        requested = list(dict.fromkeys(channel_ids or ()))
        statement = select(YoutubeChannel)
        if requested:
            statement = statement.where(YoutubeChannel.id.in_(requested))
        else:
            statement = statement.where(~YoutubeChannel.youtube_channel_id.startswith("UCESDEMO"))
        channels = list(self._session.scalars(statement))
        updated = 0
        now = datetime.now(tz=UTC)
        for channel in channels:
            videos = list(
                self._session.scalars(
                    select(YoutubeVideo).where(YoutubeVideo.channel_id == channel.id)
                )
            )
            if not videos:
                continue
            snapshots_by_video = {
                video.id: list(
                    self._session.scalars(
                        select(VideoSnapshot)
                        .where(VideoSnapshot.video_id == video.id)
                        .order_by(VideoSnapshot.video_age_seconds)
                    )
                )
                for video in videos
            }
            self._session.execute(
                delete(ChannelBaseline).where(
                    ChannelBaseline.channel_id == channel.id,
                    ChannelBaseline.version == BASELINE_VERSION,
                    ChannelBaseline.metric_name != "history_backfill_marker",
                )
            )
            window_targets = {
                "1h": 3600,
                "6h": 6 * 3600,
                "24h": 24 * 3600,
                "72h": 72 * 3600,
                "7d": 7 * 24 * 3600,
            }
            for window, target_age in window_targets.items():
                samples: list[float] = []
                for rows in snapshots_by_video.values():
                    candidates = [
                        row
                        for row in rows
                        if target_age * 0.5 <= row.video_age_seconds <= target_age * 1.75
                    ]
                    if not candidates:
                        continue
                    closest = min(
                        candidates,
                        key=lambda row: abs(row.video_age_seconds - target_age),
                    )
                    samples.append(float(closest.view_count))
                if samples:
                    self._add_baseline(
                        channel_id=channel.id,
                        window=window,
                        metric_name=f"median_views_at_{window}",
                        value=median(samples),
                        sample_size=len(samples),
                        calculated_at=now,
                    )
                    updated += 1
            latest = [rows[-1] for rows in snapshots_by_video.values() if rows]
            if latest:
                age_curve_samples = [
                    float(row.view_count)
                    / max(row.video_age_seconds / 3600, 1) ** AGE_CURVE_EXPONENT
                    for row in latest
                    if row.video_age_seconds >= 3 * 3600
                ]
                metrics = (
                    (
                        "median_views_per_hour",
                        median([row.views_per_hour for row in latest]),
                    ),
                    (
                        "median_engagement_per_1000",
                        median(
                            [
                                row.likes_per_1000_views + row.comments_per_1000_views
                                for row in latest
                            ]
                        ),
                    ),
                    (
                        "top_quartile_latest_views",
                        _percentile(
                            [float(row.view_count) for row in latest],
                            0.75,
                        ),
                    ),
                    (
                        "top_decile_latest_views",
                        _percentile(
                            [float(row.view_count) for row in latest],
                            0.9,
                        ),
                    ),
                )
                for metric_name, value in metrics:
                    self._add_baseline(
                        channel_id=channel.id,
                        window="rolling_30d",
                        metric_name=metric_name,
                        value=value,
                        sample_size=len(latest),
                        calculated_at=now,
                    )
                    updated += 1
                if age_curve_samples:
                    self._add_baseline(
                        channel_id=channel.id,
                        window="rolling_180d",
                        metric_name="median_views_age_curve_coefficient",
                        value=median(age_curve_samples),
                        sample_size=len(age_curve_samples),
                        calculated_at=now,
                    )
                    updated += 1
            recent_uploads = sum(
                1 for video in videos if _aware(video.published_at) >= now - timedelta(days=30)
            )
            rolling_metrics = (
                ("upload_frequency_per_day_30d", recent_uploads / 30),
                (
                    "median_duration_seconds",
                    median([float(video.duration_seconds) for video in videos]),
                ),
            )
            for metric_name, value in rolling_metrics:
                self._add_baseline(
                    channel_id=channel.id,
                    window="rolling_30d",
                    metric_name=metric_name,
                    value=value,
                    sample_size=len(videos),
                    calculated_at=now,
                )
                updated += 1
        self._session.flush()
        return updated

    def _add_baseline(
        self,
        *,
        channel_id: str,
        window: str,
        metric_name: str,
        value: float,
        sample_size: int,
        calculated_at: datetime,
    ) -> None:
        self._session.add(
            ChannelBaseline(
                id=str(uuid4()),
                channel_id=channel_id,
                window=window,
                metric_name=metric_name,
                metric_value=round(value, 4),
                sample_size=sample_size,
                calculated_at=calculated_at,
                version=BASELINE_VERSION,
            )
        )
        project_raw_to_derived(
            self._session,
            subject_type="channel",
            subject_id=channel_id,
            window=window,
            metrics={metric_name: round(value, 4)},
            scoring_version=BASELINE_VERSION,
            input_fingerprint=compute_input_fingerprint(
                channel_id, window, metric_name, str(sample_size), calculated_at.isoformat()
            ),
            computed_at=calculated_at,
        )

    def calculate_video_features(
        self,
        video_ids: Iterable[str] | None = None,
    ) -> int:
        requested = list(dict.fromkeys(video_ids or ()))
        statement = select(YoutubeVideo)
        if requested:
            statement = statement.where(YoutubeVideo.id.in_(requested))
        else:
            statement = statement.where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
        videos = list(self._session.scalars(statement))
        updated = 0
        now = datetime.now(tz=UTC)
        for video in videos:
            snapshots = list(
                self._session.scalars(
                    select(VideoSnapshot)
                    .where(VideoSnapshot.video_id == video.id)
                    .order_by(VideoSnapshot.observed_at)
                )
            )
            if not snapshots:
                continue
            latest = snapshots[-1]
            velocity = latest.views_per_hour
            previous_velocity = velocity
            if len(snapshots) >= 2:
                previous = snapshots[-2]
                hours = max(
                    (_aware(latest.observed_at) - _aware(previous.observed_at)).total_seconds()
                    / 3600,
                    0.01,
                )
                velocity = max(
                    0,
                    (latest.view_count - previous.view_count) / hours,
                )
            if len(snapshots) >= 3:
                first = snapshots[-3]
                previous = snapshots[-2]
                hours = max(
                    (_aware(previous.observed_at) - _aware(first.observed_at)).total_seconds()
                    / 3600,
                    0.01,
                )
                previous_velocity = max(
                    0,
                    (previous.view_count - first.view_count) / hours,
                )
            acceleration = (velocity - previous_velocity) / max(previous_velocity, 1) * 100
            acceleration = max(-500, min(500, acceleration))
            outlier_ratio = self._outlier_ratio(video, latest)
            language_probability = 1.0 if video.default_language.lower().startswith("en") else 0.4
            text = f"{video.title} {video.description}".lower()
            relevance_terms = (
                "ai",
                "agent",
                "model",
                "claude",
                "gpt",
                "coding",
                "automation",
                "robot",
            )
            matches = sum(term in text for term in relevance_terms)
            vertical_relevance = min(1.0, 0.35 + matches * 0.15)
            feature = self._session.get(
                VideoFeature,
                (video.id, FEATURE_VERSION),
            )
            engagement_rate = round(
                latest.likes_per_1000_views + latest.comments_per_1000_views,
                3,
            )
            if feature is None:
                feature = VideoFeature(
                    video_id=video.id,
                    feature_version=FEATURE_VERSION,
                    language_probability=language_probability,
                    vertical_relevance=vertical_relevance,
                    outlier_ratio=round(outlier_ratio, 4),
                    view_velocity=round(velocity, 2),
                    velocity_acceleration=round(acceleration, 2),
                    engagement_rate=engagement_rate,
                    novelty_score=0.0,
                    spam_probability=0.0,
                    calculated_at=now,
                )
                self._session.add(feature)
            else:
                feature.language_probability = language_probability
                feature.vertical_relevance = vertical_relevance
                feature.outlier_ratio = round(outlier_ratio, 4)
                feature.view_velocity = round(velocity, 2)
                feature.velocity_acceleration = round(acceleration, 2)
                feature.engagement_rate = engagement_rate
                feature.novelty_score = 0.0
                feature.spam_probability = 0.0
                feature.calculated_at = now
            project_raw_to_derived(
                self._session,
                subject_type="video",
                subject_id=video.id,
                window="latest",
                metrics={
                    "outlier_ratio": round(outlier_ratio, 4),
                    "view_velocity": round(velocity, 2),
                    "velocity_acceleration": round(acceleration, 2),
                    "engagement_rate": engagement_rate,
                },
                scoring_version=FEATURE_VERSION,
                input_fingerprint=compute_input_fingerprint(
                    *(snapshot.id for snapshot in snapshots[-3:]), now.isoformat()
                ),
                computed_at=now,
            )
            updated += 1
        return updated

    def _outlier_ratio(
        self,
        video: YoutubeVideo,
        snapshot: VideoSnapshot,
    ) -> float:
        targets = (
            ("1h", 3600),
            ("6h", 6 * 3600),
            ("24h", 24 * 3600),
            ("72h", 72 * 3600),
            ("7d", 7 * 24 * 3600),
        )
        window, _ = min(
            targets,
            key=lambda item: abs(item[1] - snapshot.video_age_seconds),
        )
        baseline = self._session.scalar(
            select(ChannelBaseline).where(
                ChannelBaseline.channel_id == video.channel_id,
                ChannelBaseline.window == window,
                ChannelBaseline.metric_name == f"median_views_at_{window}",
                ChannelBaseline.version == BASELINE_VERSION,
                ChannelBaseline.sample_size >= 3,
            )
        )
        if baseline is not None and baseline.metric_value > 0:
            return snapshot.view_count / baseline.metric_value
        curve = self._session.scalar(
            select(ChannelBaseline).where(
                ChannelBaseline.channel_id == video.channel_id,
                ChannelBaseline.window == "rolling_180d",
                ChannelBaseline.metric_name == "median_views_age_curve_coefficient",
                ChannelBaseline.version == BASELINE_VERSION,
                ChannelBaseline.sample_size >= 5,
            )
        )
        if curve is not None and curve.metric_value > 0:
            age_hours = max(snapshot.video_age_seconds / 3600, 1)
            expected_views = float(curve.metric_value) * age_hours**AGE_CURVE_EXPONENT
            return float(snapshot.view_count) / max(float(expected_views), 1.0)
        fallback = self._session.scalar(
            select(ChannelBaseline).where(
                ChannelBaseline.channel_id == video.channel_id,
                ChannelBaseline.window == "rolling_30d",
                ChannelBaseline.metric_name == "top_quartile_latest_views",
                ChannelBaseline.version == BASELINE_VERSION,
                ChannelBaseline.sample_size >= 5,
            )
        )
        if fallback is not None and fallback.metric_value > 0:
            return snapshot.view_count / fallback.metric_value
        return 1.0

    def operational_metrics(self) -> dict[str, int | float | str | None]:
        now = datetime.now(tz=UTC)
        live_videos = int(
            self._session.scalar(
                select(func.count(YoutubeVideo.id)).where(
                    ~YoutubeVideo.youtube_video_id.startswith("esdemo")
                )
            )
            or 0
        )
        videos_with_snapshots = int(
            self._session.scalar(
                select(func.count(func.distinct(VideoSnapshot.video_id)))
                .join(YoutubeVideo, YoutubeVideo.id == VideoSnapshot.video_id)
                .where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
            )
            or 0
        )
        latest_snapshot = self._session.scalar(
            select(func.max(VideoSnapshot.observed_at))
            .join(YoutubeVideo, YoutubeVideo.id == VideoSnapshot.video_id)
            .where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
        )
        pending_jobs = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(VideoSnapshotJob.status == "pending")
            )
            or 0
        )
        due_jobs = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(
                    VideoSnapshotJob.status == "pending",
                    VideoSnapshotJob.run_at <= now,
                )
            )
            or 0
        )
        failed_jobs = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(VideoSnapshotJob.status == "failed")
            )
            or 0
        )
        skipped_jobs = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(VideoSnapshotJob.status == "skipped")
            )
            or 0
        )
        oldest_due = self._session.scalar(
            select(func.min(VideoSnapshotJob.run_at)).where(
                VideoSnapshotJob.status == "pending",
                VideoSnapshotJob.run_at <= now,
            )
        )
        snapshot_lag_seconds = (
            max(0, round((now - _aware(oldest_due)).total_seconds())) if oldest_due else 0
        )
        feature_count = int(
            self._session.scalar(
                select(func.count(VideoFeature.video_id)).where(
                    VideoFeature.feature_version == FEATURE_VERSION
                )
            )
            or 0
        )
        baseline_count = int(
            self._session.scalar(
                select(func.count(ChannelBaseline.id)).where(
                    ChannelBaseline.version == BASELINE_VERSION
                )
            )
            or 0
        )
        return {
            "live_videos": live_videos,
            "videos_with_snapshots": videos_with_snapshots,
            "snapshot_coverage_percent": round(
                videos_with_snapshots / max(live_videos, 1) * 100,
                1,
            ),
            "pending_jobs": pending_jobs,
            "due_jobs": due_jobs,
            "failed_jobs": failed_jobs,
            "skipped_jobs": skipped_jobs,
            "snapshot_lag_seconds": snapshot_lag_seconds,
            "feature_count": feature_count,
            "baseline_count": baseline_count,
            "latest_snapshot_at": _aware(latest_snapshot).isoformat() if latest_snapshot else None,
        }
