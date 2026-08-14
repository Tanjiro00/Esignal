from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DiscoveryQuery:
    query: str
    country: str = "US"
    language: str = "en"
    published_after: datetime | None = None
    max_results: int = 100
    sort: str = "relevance"


@dataclass(frozen=True)
class DiscoveredVideo:
    video_id: str
    title: str | None
    channel_id: str | None
    channel_title: str | None
    published_at: datetime | None
    position: int | None
    query: str
    raw_ref: str


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    channel_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int
    view_count: int
    like_count: int
    comment_count: int
    thumbnail_url: str
    raw_ref: str
    channel_title: str = ""
    default_language: str = "en"
    category_id: str = "28"
    is_live: bool = False


@dataclass(frozen=True)
class ChannelMetadata:
    channel_id: str
    title: str
    subscriber_count: int
    country: str
    language: str
    raw_ref: str
    description: str = ""
    view_count: int = 0
    video_count: int = 0
    published_at: datetime | None = None


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    capability: str
    endpoint: str
    parameters: dict[str, Any]
    parser_version: str
    estimated_cost: float = 0.0


@dataclass(frozen=True)
class RecordedPayload:
    fetch_id: str
    raw_ref: str
    payload_hash: str


@dataclass(frozen=True)
class ProviderBatch[T]:
    items: tuple[T, ...]
    fetch_id: str
    raw_ref: str


@dataclass(frozen=True)
class CommentRecord:
    comment_id: str
    video_id: str
    text: str
    published_at: datetime
    updated_at: datetime | None
    like_count: int
    reply_count: int
    parent_id: str | None
    raw_ref: str
    author_hash: str | None = None
    language: str = "en"
    is_reply: bool = False


@dataclass(frozen=True)
class TranscriptResult:
    video_id: str
    language: str
    transcript_type: str
    text: str
    segments: tuple[tuple[float, float, str], ...]
    raw_ref: str
    quality_score: float
    model_name: str | None = None
    generated_cost: float = 0
