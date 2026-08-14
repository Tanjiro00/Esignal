from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestRun,
    Base,
    DiscoveryRun,
    FieldProvenance,
    ProviderFetch,
    RawApiSnapshot,
    RawPayloadLink,
    VideoDiscoveryOccurrence,
    VideoSnapshot,
    VideoSnapshotJob,
    VideoTranscript,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from packages.backtest import (
    AsOfContext,
    PointInTimeCheckpointService,
    verify_checkpoint_content_hash,
)
from scripts.export_backtest_checkpoint import parse_timestamp

CUTOFF = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _provider_fetch(
    fetch_id: str,
    *,
    completed_at: datetime,
    provider: str = "youtube_official",
) -> ProviderFetch:
    return ProviderFetch(
        id=fetch_id,
        provider=provider,
        capability="metadata",
        endpoint="videos.list",
        request_fingerprint=f"request-{fetch_id}",
        started_at=completed_at - timedelta(seconds=1),
        completed_at=completed_at,
        status="success",
        http_status=200,
        attempt_number=1,
        latency_ms=100,
        estimated_cost=0,
        actual_cost=0,
        raw_payload_uri=f"raw://{fetch_id}",
        raw_payload_hash=f"payload-{fetch_id}",
        parser_version="test-v1",
        error_code=None,
        error_message=None,
        linked_entity_ids=[],
    )


def _channel(channel_id: str, *, youtube_id: str) -> YoutubeChannel:
    return YoutubeChannel(
        id=channel_id,
        youtube_channel_id=youtube_id,
        canonical_url=f"https://youtube.com/channel/{youtube_id}",
        title=youtube_id,
        description="",
        country="US",
        default_language="en",
        subscriber_count=1_000,
        video_count=10,
        view_count=100_000,
        published_at=CUTOFF - timedelta(days=500),
        last_observed_at=CUTOFF - timedelta(hours=1),
        created_at=CUTOFF - timedelta(days=30),
        updated_at=CUTOFF - timedelta(hours=1),
    )


def _video(
    video_id: str,
    *,
    youtube_id: str,
    channel_id: str,
    discovered_at: datetime,
) -> YoutubeVideo:
    return YoutubeVideo(
        id=video_id,
        youtube_video_id=youtube_id,
        channel_id=channel_id,
        canonical_url=f"https://youtube.com/watch?v={youtube_id}",
        title=f"title {youtube_id}",
        description=f"description {youtube_id}",
        published_at=CUTOFF - timedelta(days=2),
        duration_seconds=600,
        default_language="en",
        category_id="28",
        is_short=False,
        is_live=False,
        thumbnail_url="https://img.example/test.jpg",
        first_discovered_at=discovered_at,
        discovery_lag_seconds=100,
        last_observed_at=discovered_at,
        created_at=discovered_at,
        updated_at=discovered_at,
    )


def _seed_point_in_time_fixture(session: Session) -> None:
    past = CUTOFF - timedelta(hours=2)
    future = CUTOFF + timedelta(hours=2)
    live_channel = _channel("channel-live", youtube_id="UC_LIVE")
    demo_channel = _channel("channel-demo", youtube_id="UC_DEMO")
    live_video = _video(
        "video-live-1",
        youtube_id="live-video-1",
        channel_id=live_channel.id,
        discovered_at=past,
    )
    transcript_future_video = _video(
        "video-live-2",
        youtube_id="live-video-2",
        channel_id=live_channel.id,
        discovered_at=past,
    )
    demo_video = _video(
        "video-demo-1",
        youtube_id="esdemo-video-1",
        channel_id=demo_channel.id,
        discovered_at=past,
    )
    past_fetch = _provider_fetch("fetch-past", completed_at=past)
    future_fetch = _provider_fetch("fetch-future", completed_at=future)
    demo_fetch = _provider_fetch("fetch-demo", completed_at=past, provider="mock_metadata")
    session.add_all(
        (
            live_channel,
            demo_channel,
            live_video,
            transcript_future_video,
            demo_video,
            past_fetch,
            future_fetch,
            demo_fetch,
        )
    )
    session.flush()
    session.add_all(
        (
            RawPayloadLink(
                provider_fetch_id=past_fetch.id,
                entity_type="normalized_entity",
                entity_id=live_video.id,
            ),
            RawPayloadLink(
                provider_fetch_id=future_fetch.id,
                entity_type="normalized_entity",
                entity_id=transcript_future_video.id,
            ),
            RawPayloadLink(
                provider_fetch_id=demo_fetch.id,
                entity_type="normalized_entity",
                entity_id=demo_video.id,
            ),
            RawApiSnapshot(
                id="raw-snapshot-past",
                video_id=live_video.id,
                provider="youtube_official",
                fetched_at=past,
                expires_at=past + timedelta(days=30),
                payload={"view_count": 1_000},
                provenance={"fetch_id": past_fetch.id},
            ),
            RawApiSnapshot(
                id="raw-snapshot-future",
                video_id=live_video.id,
                provider="youtube_official",
                fetched_at=future,
                expires_at=future + timedelta(days=30),
                payload={"view_count": 10_000},
                provenance={"fetch_id": future_fetch.id},
            ),
            DiscoveryRun(
                id="run-past",
                query_id=None,
                channel_id=live_channel.id,
                provider="youtube_web",
                idempotency_key="discovery-run-past",
                started_at=past - timedelta(minutes=1),
                completed_at=past,
                status="success",
                result_count=1,
                unique_video_count=1,
                retained_video_count=1,
                estimated_cost=0,
                error_code=None,
                error_message=None,
            ),
            DiscoveryRun(
                id="run-future",
                query_id=None,
                channel_id=live_channel.id,
                provider="youtube_web",
                idempotency_key="discovery-run-future",
                started_at=future - timedelta(minutes=1),
                completed_at=future,
                status="success",
                result_count=1,
                unique_video_count=1,
                retained_video_count=1,
                estimated_cost=0,
                error_code=None,
                error_message=None,
            ),
            DiscoveryRun(
                id="run-demo",
                query_id=None,
                channel_id=demo_channel.id,
                provider="mock_discovery",
                idempotency_key="discovery-run-demo",
                started_at=past - timedelta(minutes=1),
                completed_at=past,
                status="success",
                result_count=1,
                unique_video_count=1,
                retained_video_count=1,
                estimated_cost=0,
                error_code=None,
                error_message=None,
            ),
            VideoDiscoveryOccurrence(
                id="occurrence-past",
                video_id=live_video.id,
                query_id=None,
                provider_fetch_id=past_fetch.id,
                position=1,
                country="US",
                language="en",
                discovered_at=past,
            ),
            VideoDiscoveryOccurrence(
                id="occurrence-future",
                video_id=transcript_future_video.id,
                query_id=None,
                provider_fetch_id=future_fetch.id,
                position=1,
                country="US",
                language="en",
                discovered_at=future,
            ),
            VideoDiscoveryOccurrence(
                id="occurrence-demo",
                video_id=demo_video.id,
                query_id=None,
                provider_fetch_id=demo_fetch.id,
                position=1,
                country="US",
                language="en",
                discovered_at=past,
            ),
            VideoSnapshot(
                id="snapshot-past",
                video_id=live_video.id,
                observed_at=past,
                video_age_seconds=86_400,
                view_count=1_000,
                like_count=100,
                comment_count=10,
                views_per_hour=41.67,
                likes_per_1000_views=100,
                comments_per_1000_views=10,
                snapshot_quality="direct",
                is_estimated=False,
                provider_fetch_id=past_fetch.id,
            ),
            VideoSnapshot(
                id="snapshot-future",
                video_id=live_video.id,
                observed_at=future,
                video_age_seconds=100_000,
                view_count=10_000,
                like_count=1_000,
                comment_count=100,
                views_per_hour=360,
                likes_per_1000_views=100,
                comments_per_1000_views=10,
                snapshot_quality="direct",
                is_estimated=False,
                provider_fetch_id=future_fetch.id,
            ),
            VideoSnapshotJob(
                id="job-past",
                video_id=live_video.id,
                scheduled_age_seconds=86_400,
                run_at=past,
                status="success",
                idempotency_key="snapshot-job-past",
                attempt_count=1,
                started_at=past - timedelta(minutes=1),
                completed_at=past,
                provider_fetch_id=past_fetch.id,
                skip_reason=None,
                error_code=None,
                error_message=None,
                created_at=past,
                updated_at=past,
            ),
            VideoSnapshotJob(
                id="job-future",
                video_id=live_video.id,
                scheduled_age_seconds=172_800,
                run_at=future,
                status="success",
                idempotency_key="snapshot-job-future",
                attempt_count=1,
                started_at=future - timedelta(minutes=1),
                completed_at=future,
                provider_fetch_id=future_fetch.id,
                skip_reason=None,
                error_code=None,
                error_message=None,
                created_at=future,
                updated_at=future,
            ),
            YoutubeComment(
                id="comment-past",
                provider_comment_id="yt-comment-past",
                video_id=live_video.id,
                parent_comment_id=None,
                text="secret past comment text",
                published_at=past - timedelta(hours=1),
                updated_at=None,
                like_count=5,
                reply_count=0,
                is_reply=False,
                language="en",
                author_hash="author-past",
                fetched_order="relevance",
                normalized_hash="comment-content-past",
                provider_fetch_id=past_fetch.id,
                created_at=past,
            ),
            YoutubeComment(
                id="comment-future",
                provider_comment_id="yt-comment-future",
                video_id=live_video.id,
                parent_comment_id=None,
                text="secret future comment text",
                published_at=past - timedelta(days=1),
                updated_at=None,
                like_count=50,
                reply_count=0,
                is_reply=False,
                language="en",
                author_hash="author-future",
                fetched_order="relevance",
                normalized_hash="comment-content-future",
                provider_fetch_id=future_fetch.id,
                created_at=future,
            ),
            VideoTranscript(
                id="transcript-past",
                video_id=live_video.id,
                language="en",
                transcript_type="native",
                provider="youtube_transcript",
                provider_fetch_id=past_fetch.id,
                full_text="secret past transcript text",
                content_hash="transcript-content-past",
                quality_score=0.9,
                generated_cost=0,
                fetched_at=past,
                model_name=None,
                summary_json={},
                entities_json=[],
                key_claims_json=[],
                use_cases_json=[],
                comparisons_json=[],
                unanswered_questions_json=[],
                narrative_angle="unknown",
                content_format="unknown",
                processing_version="test-v1",
                created_at=past,
            ),
            VideoTranscript(
                id="transcript-future",
                video_id=transcript_future_video.id,
                language="en",
                transcript_type="native",
                provider="youtube_transcript",
                provider_fetch_id=future_fetch.id,
                full_text="secret future transcript text",
                content_hash="transcript-content-future",
                quality_score=0.9,
                generated_cost=0,
                fetched_at=future,
                model_name=None,
                summary_json={},
                entities_json=[],
                key_claims_json=[],
                use_cases_json=[],
                comparisons_json=[],
                unanswered_questions_json=[],
                narrative_angle="unknown",
                content_format="unknown",
                processing_version="test-v1",
                created_at=future,
            ),
            FieldProvenance(
                id="provenance-past",
                entity_type="video",
                entity_id=live_video.id,
                field_name="title",
                provider_fetch_id=past_fetch.id,
                observed_at=past,
                confidence=1,
                value_hash="title-value-past",
            ),
            FieldProvenance(
                id="provenance-future",
                entity_type="video",
                entity_id=transcript_future_video.id,
                field_name="title",
                provider_fetch_id=future_fetch.id,
                observed_at=future,
                confidence=1,
                value_hash="title-value-future",
            ),
        )
    )
    session.commit()


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as active_session:
        _seed_point_in_time_fixture(active_session)
        yield active_session


def _manifest(session: Session, *, source_kind: str = "live") -> dict[str, object]:
    return PointInTimeCheckpointService(session).build_manifest(
        AsOfContext(as_of=CUTOFF, source_kind=source_kind),  # type: ignore[arg-type]
        source_environment="test",
        repository_state={"dirty": False, "revision": "test-revision"},
    )


def test_as_of_context_requires_timezone_and_normalizes_providers() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AsOfContext(as_of=datetime(2026, 8, 1, 12))

    context = AsOfContext(
        as_of=CUTOFF,
        allowed_providers=("youtube_web", "youtube_official", "youtube_web"),
    )

    assert context.allowed_providers == ("youtube_official", "youtube_web")
    assert context.includes(CUTOFF)
    assert not context.includes(CUTOFF + timedelta(seconds=1))


def test_checkpoint_excludes_future_evidence_and_raw_private_text(session: Session) -> None:
    manifest = _manifest(session)
    tables = manifest["input_tables"]

    assert tables["videos"]["count"] == 2
    assert tables["provider_fetches"]["count"] == 1
    assert tables["raw_api_snapshots"]["count"] == 1
    assert tables["discovery_runs"]["count"] == 1
    assert tables["discovery_occurrences"]["count"] == 1
    assert tables["video_snapshots"]["count"] == 1
    assert tables["snapshot_jobs"]["count"] == 1
    assert tables["youtube_comments"]["count"] == 1
    assert tables["video_transcripts"]["count"] == 1
    assert tables["field_provenance"]["count"] == 1
    assert manifest["eligibility"]["successful_snapshot_jobs_by_target_age_seconds"] == {"86400": 1}
    serialized = json.dumps(manifest)
    assert "secret past comment text" not in serialized
    assert "secret past transcript text" not in serialized
    assert '"view_count": 1000' not in serialized
    assert verify_checkpoint_content_hash(manifest)


def test_future_rows_do_not_change_checkpoint_but_past_rows_do(session: Session) -> None:
    before = _manifest(session)
    future = CUTOFF + timedelta(days=1)
    session.add(
        VideoSnapshot(
            id="snapshot-even-later",
            video_id="video-live-1",
            observed_at=future,
            video_age_seconds=200_000,
            view_count=50_000,
            like_count=5_000,
            comment_count=500,
            views_per_hour=900,
            likes_per_1000_views=100,
            comments_per_1000_views=10,
            snapshot_quality="direct",
            is_estimated=False,
            provider_fetch_id="fetch-future",
        )
    )
    session.commit()
    after_future = _manifest(session)
    assert after_future == before

    session.add(
        VideoSnapshot(
            id="snapshot-second-past",
            video_id="video-live-2",
            observed_at=CUTOFF - timedelta(minutes=30),
            video_age_seconds=90_000,
            view_count=2_000,
            like_count=200,
            comment_count=20,
            views_per_hour=80,
            likes_per_1000_views=100,
            comments_per_1000_views=10,
            snapshot_quality="direct",
            is_estimated=False,
            provider_fetch_id="fetch-past",
        )
    )
    session.commit()
    after_past = _manifest(session)
    assert after_past["input_hash"] != before["input_hash"]
    assert after_past["input_tables"]["video_snapshots"]["count"] == 2


def test_mutable_normalized_video_metadata_does_not_rewrite_history(
    session: Session,
) -> None:
    before = _manifest(session)
    video = session.get(YoutubeVideo, "video-live-1")
    assert video is not None

    video.channel_id = "channel-demo"
    video.title = "provider corrected title"
    video.description = "provider corrected description"
    video.published_at = video.published_at + timedelta(minutes=5)
    video.updated_at = CUTOFF + timedelta(days=1)
    session.commit()

    after = _manifest(session)
    assert after == before


def test_live_and_demo_sources_are_isolated(session: Session) -> None:
    live = _manifest(session, source_kind="live")
    demo = _manifest(session, source_kind="demo")

    assert live["input_tables"]["videos"]["count"] == 2
    assert live["input_tables"]["provider_fetches"]["count"] == 1
    assert demo["input_tables"]["videos"]["count"] == 1
    assert demo["input_tables"]["provider_fetches"]["count"] == 1
    assert demo["input_tables"]["discovery_runs"]["count"] == 1


def test_persist_manifest_is_idempotent(session: Session) -> None:
    service = PointInTimeCheckpointService(session)
    manifest = _manifest(session)

    first_run, first_checkpoint = service.persist_manifest(
        manifest,
        name="test checkpoint",
        recorded_at=CUTOFF,
    )
    second_run, second_checkpoint = service.persist_manifest(
        manifest,
        name="test checkpoint",
        recorded_at=CUTOFF + timedelta(minutes=1),
    )

    assert first_run.id == second_run.id
    assert first_checkpoint.id == second_checkpoint.id
    assert session.scalar(select(func.count()).select_from(BacktestRun)) == 1
    assert session.scalar(select(func.count()).select_from(BacktestCheckpoint)) == 1
    assert first_checkpoint.prediction_count == 0


def test_cli_timestamp_parser_rejects_naive_values() -> None:
    assert parse_timestamp("2026-08-01T12:00:00Z") == CUTOFF
    with pytest.raises(Exception, match="timezone"):
        parse_timestamp("2026-08-01T12:00:00")
