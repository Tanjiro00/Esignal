from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from packages.domain import (
    ChannelMetadata,
    CommentRecord,
    DiscoveredVideo,
    DiscoveryQuery,
    TranscriptResult,
    VideoMetadata,
)


class MockProvider:
    name = "mock_provider"

    @staticmethod
    def _raw_ref(capability: str, key: str) -> str:
        digest = sha256(f"{capability}:{key}".encode()).hexdigest()[:16]
        return f"fixture://demo/{capability}/{digest}.json"

    async def search(self, query: DiscoveryQuery) -> Sequence[DiscoveredVideo]:
        now = datetime(2026, 7, 26, 18, tzinfo=UTC)
        limit = min(query.max_results, 5)
        return [
            DiscoveredVideo(
                video_id=f"demo{i:08d}",
                title=f"{query.query}: evidence video {i + 1}",
                channel_id=f"UCDEMO{i:018d}",
                channel_title=f"Demo Tech Channel {i + 1}",
                published_at=now - timedelta(hours=3 * i),
                position=i + 1,
                query=query.query,
                raw_ref=self._raw_ref("discovery", f"{query.query}:{i}"),
            )
            for i in range(limit)
        ]

    async def fetch_videos(self, video_ids: Sequence[str]) -> Sequence[VideoMetadata]:
        now = datetime(2026, 7, 26, 18, tzinfo=UTC)
        return [
            VideoMetadata(
                video_id=video_id,
                channel_id=f"UC{sha256(video_id.encode()).hexdigest()[:22]}",
                title=f"Evidence for {video_id}",
                description="Deterministic AI/technology demo metadata.",
                published_at=now - timedelta(hours=index + 1),
                duration_seconds=720 + index * 30,
                view_count=24_000 + index * 3_100,
                like_count=1_200 + index * 110,
                comment_count=180 + index * 9,
                thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                raw_ref=self._raw_ref("metadata", video_id),
            )
            for index, video_id in enumerate(video_ids)
        ]

    async def fetch_channels(self, channel_ids: Sequence[str]) -> Sequence[ChannelMetadata]:
        return [
            ChannelMetadata(
                channel_id=channel_id,
                title=f"Demo AI Channel {index + 1}",
                subscriber_count=100_000 + index * 52_000,
                country="US",
                language="en",
                raw_ref=self._raw_ref("channels", channel_id),
            )
            for index, channel_id in enumerate(channel_ids)
        ]

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]:
        query = DiscoveryQuery(query=f"uploads:{channel_id}", max_results=limit)
        return await self.search(query)

    async def fetch_comments(
        self,
        video_id: str,
        order: str,
        limit: int,
        include_replies: bool,
    ) -> Sequence[CommentRecord]:
        del order, include_replies
        now = datetime(2026, 7, 26, 18, tzinfo=UTC)
        comments = (
            "How can I run this safely on a private repository?",
            "Can you compare the setup cost with the hosted option?",
            "Please show the failure cases, not only the happy path.",
        )
        return [
            CommentRecord(
                comment_id=f"mock-{video_id}-{index}",
                video_id=video_id,
                text=text,
                published_at=now - timedelta(minutes=index * 17),
                updated_at=None,
                like_count=42 - index * 7,
                reply_count=5 - index,
                parent_id=None,
                raw_ref=self._raw_ref("comments", f"{video_id}:{index}"),
            )
            for index, text in enumerate(comments[:limit])
        ]

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: Sequence[str],
        allow_generated: bool,
    ) -> TranscriptResult:
        del allow_generated
        language = preferred_languages[0] if preferred_languages else "en"
        text = (
            "This deterministic demo transcript describes an end-to-end AI workflow, "
            "its evidence, limitations, cost, and safety checks."
        )
        return TranscriptResult(
            video_id=video_id,
            language=language,
            transcript_type="native",
            text=text,
            segments=((0.0, 8.0, text),),
            raw_ref=self._raw_ref("transcripts", video_id),
            quality_score=0.97,
        )
