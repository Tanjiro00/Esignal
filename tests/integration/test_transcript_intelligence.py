import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    Base,
    TranscriptFetchRun,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.worker.transcript_intelligence import TranscriptIntelligenceService
from packages.provider_sdk.router import ProviderUnavailableError


def test_missing_transcript_is_recorded_without_blocking_pipeline(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)

    class UnavailableRouter:
        @staticmethod
        async def transcript(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise ProviderUnavailableError(
                "All transcript providers failed (youtube_transcript:unavailable)"
            )

    with Session(engine, expire_on_commit=False) as session:
        session.add(
            YoutubeChannel(
                id="channel-1",
                youtube_channel_id="UC_TRANSCRIPT_TEST",
                canonical_url="https://youtube.com/channel/UC_TRANSCRIPT_TEST",
                title="Transcript Test",
                description="",
                country="US",
                default_language="en",
                subscriber_count=1000,
                video_count=10,
                view_count=10000,
                published_at=now - timedelta(days=365),
                last_observed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        video = YoutubeVideo(
            id="video-1",
            youtube_video_id="transcript-test",
            channel_id="channel-1",
            canonical_url="https://youtube.com/watch?v=transcript-test",
            title="AI workflow without captions",
            description="",
            published_at=now - timedelta(hours=2),
            duration_seconds=600,
            default_language="en",
            category_id="28",
            is_short=False,
            is_live=False,
            thumbnail_url="https://example.com/thumb.jpg",
            first_discovered_at=now,
            discovery_lag_seconds=0,
            last_observed_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(video)
        session.commit()

        service = TranscriptIntelligenceService(
            session,
            Settings(raw_payload_directory=str(tmp_path)),
        )
        service._router = UnavailableRouter()  # type: ignore[assignment]
        status, segment_count = asyncio.run(service._fetch_video(video, force=False))

        run = session.scalar(select(TranscriptFetchRun))
        assert status == "unavailable"
        assert segment_count == 0
        assert run is not None
        assert run.status == "unavailable"
