from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from packages.domain import (
    ChannelMetadata,
    CommentRecord,
    DiscoveredVideo,
    DiscoveryQuery,
    TranscriptResult,
    VideoMetadata,
)


class DiscoveryProvider(Protocol):
    name: str

    async def search(self, query: DiscoveryQuery) -> Sequence[DiscoveredVideo]: ...


class VideoMetadataProvider(Protocol):
    name: str

    async def fetch_videos(self, video_ids: Sequence[str]) -> Sequence[VideoMetadata]: ...


class ChannelProvider(Protocol):
    name: str

    async def fetch_channels(self, channel_ids: Sequence[str]) -> Sequence[ChannelMetadata]: ...

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]: ...


class RecentUploadProvider(Protocol):
    name: str

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]: ...


class CommentProvider(Protocol):
    name: str

    async def fetch_comments(
        self,
        video_id: str,
        order: str,
        limit: int,
        include_replies: bool,
    ) -> Sequence[CommentRecord]: ...


class TranscriptProvider(Protocol):
    name: str

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: Sequence[str],
        allow_generated: bool,
    ) -> TranscriptResult: ...
