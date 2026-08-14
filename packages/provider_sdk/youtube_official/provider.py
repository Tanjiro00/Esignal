from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from packages.domain import (
    ChannelMetadata,
    CommentRecord,
    DiscoveredVideo,
    DiscoveryQuery,
    ProviderRequest,
    VideoMetadata,
)
from packages.provider_sdk.base.observability import ProviderFetchRecorder

API_ROOT = "https://www.googleapis.com/youtube/v3"
PARSER_VERSION = "youtube-official-v1.0.0"
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?$"
)
_YOUTUBE_CHANNEL_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
}


def _channel_lookup(reference: str) -> tuple[str, str]:
    value = reference.strip()
    if not value:
        raise ValueError("YouTube channel reference cannot be empty")
    if value.startswith("@"):
        handle = value[1:].strip()
        if not handle:
            raise ValueError("YouTube handle cannot be empty")
        return "forHandle", handle

    url_value = value
    if "://" not in url_value and "youtube.com/" in url_value.lower():
        url_value = f"https://{url_value}"
    parsed = urlparse(url_value)
    if parsed.hostname:
        hostname = parsed.hostname.lower()
        if hostname not in _YOUTUBE_CHANNEL_HOSTS:
            raise ValueError("Only YouTube channel URLs are supported")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if not parts:
            raise ValueError("YouTube channel URL is incomplete")
        if parts[0].startswith("@"):
            return "forHandle", parts[0][1:]
        if len(parts) >= 2 and parts[0] == "channel":
            return "id", parts[1]
        if len(parts) >= 2 and parts[0] == "user":
            return "forUsername", parts[1]
        if len(parts) >= 2 and parts[0] == "c":
            return "forHandle", parts[1]
        raise ValueError("Use a YouTube @handle, /@handle URL, /channel/ URL, or channel ID")
    return "id", value


def _channel_metadata(
    payload: dict[str, Any],
    *,
    raw_ref: str,
) -> list[ChannelMetadata]:
    results: list[ChannelMetadata] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        results.append(
            ChannelMetadata(
                channel_id=str(item["id"]),
                title=str(snippet.get("title", "")),
                subscriber_count=_integer(statistics.get("subscriberCount")),
                country=str(snippet.get("country", "US")),
                language=str(snippet.get("defaultLanguage", "en")),
                raw_ref=raw_ref,
                description=str(snippet.get("description", "")),
                view_count=_integer(statistics.get("viewCount")),
                video_count=_integer(statistics.get("videoCount")),
                published_at=_timestamp(str(snippet["publishedAt"]))
                if snippet.get("publishedAt")
                else None,
            )
        )
    return results


class YoutubeOfficialProviderError(RuntimeError):
    def __init__(self, message: str, *, reason: str = "api_error") -> None:
        super().__init__(message)
        self.reason = reason


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_iso8601_duration(value: str) -> int:
    match = _DURATION.match(value)
    if match is None:
        return 0
    parts = {name: int(amount or 0) for name, amount in match.groupdict().items()}
    return (
        parts["days"] * 86_400 + parts["hours"] * 3_600 + parts["minutes"] * 60 + parts["seconds"]
    )


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _author_hash(snippet: dict[str, Any]) -> str | None:
    channel = snippet.get("authorChannelId", {})
    raw = (channel.get("value") if isinstance(channel, dict) else None) or snippet.get(
        "authorDisplayName"
    )
    normalized = str(raw or "").strip()
    if not normalized:
        return None
    return sha256(f"earlysignal-commenter:{normalized}".encode()).hexdigest()


def _safe_comment_item(item: dict[str, Any]) -> dict[str, Any]:
    snippet = item.get("snippet", {})
    top_level = snippet.get("topLevelComment", {}) if isinstance(snippet, dict) else {}
    top_snippet = top_level.get("snippet", {}) if isinstance(top_level, dict) else {}
    safe: dict[str, Any] = {
        "id": str(item.get("id", "")),
        "snippet": {
            "videoId": str(snippet.get("videoId", "")),
            "totalReplyCount": _integer(snippet.get("totalReplyCount")),
            "topLevelComment": {
                "id": str(top_level.get("id", "")),
                "snippet": {
                    "textOriginal": str(
                        top_snippet.get("textOriginal") or top_snippet.get("textDisplay") or ""
                    ),
                    "publishedAt": top_snippet.get("publishedAt"),
                    "updatedAt": top_snippet.get("updatedAt"),
                    "likeCount": _integer(top_snippet.get("likeCount")),
                    "authorHash": _author_hash(top_snippet),
                },
            },
        },
    }
    replies = item.get("replies", {})
    reply_items = replies.get("comments", []) if isinstance(replies, dict) else []
    if isinstance(reply_items, list):
        safe["replies"] = {
            "comments": [
                {
                    "id": str(reply.get("id", "")),
                    "snippet": {
                        "parentId": str(reply.get("snippet", {}).get("parentId", "")),
                        "textOriginal": str(
                            reply.get("snippet", {}).get("textOriginal")
                            or reply.get("snippet", {}).get("textDisplay")
                            or ""
                        ),
                        "publishedAt": reply.get("snippet", {}).get("publishedAt"),
                        "updatedAt": reply.get("snippet", {}).get("updatedAt"),
                        "likeCount": _integer(reply.get("snippet", {}).get("likeCount")),
                        "authorHash": _author_hash(reply.get("snippet", {})),
                    },
                }
                for reply in reply_items
                if isinstance(reply, dict)
            ]
        }
    return safe


def _safe_comment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "nextPageToken": payload.get("nextPageToken"),
        "pageInfo": payload.get("pageInfo", {}),
        "items": [
            _safe_comment_item(item) for item in payload.get("items", []) if isinstance(item, dict)
        ],
    }


class YoutubeOfficialProvider:
    name = "youtube_official"

    def __init__(
        self,
        *,
        api_key: str,
        recorder: ProviderFetchRecorder,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._recorder = recorder
        self._client = client

    async def search(self, query: DiscoveryQuery) -> Sequence[DiscoveredVideo]:
        parameters: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "q": query.query,
            "maxResults": max(1, min(query.max_results, 50)),
            "order": (
                query.sort
                if query.sort in {"date", "rating", "relevance", "title", "viewCount"}
                else "relevance"
            ),
            "relevanceLanguage": query.language,
            "regionCode": query.country,
        }
        if query.published_after is not None:
            parameters["publishedAfter"] = (
                query.published_after.astimezone(UTC).isoformat().replace("+00:00", "Z")
            )
        payload, raw_ref = await self._request(
            capability="discovery",
            endpoint="search.list",
            path="/search",
            parameters=parameters,
        )
        results: list[DiscoveredVideo] = []
        for position, item in enumerate(payload.get("items", []), start=1):
            if not isinstance(item, dict):
                continue
            identifier = item.get("id", {})
            snippet = item.get("snippet", {})
            video_id = identifier.get("videoId") if isinstance(identifier, dict) else None
            if not video_id or not isinstance(snippet, dict):
                continue
            published_at = snippet.get("publishedAt")
            results.append(
                DiscoveredVideo(
                    video_id=str(video_id),
                    title=str(snippet.get("title", "")) or None,
                    channel_id=str(snippet.get("channelId", "")) or None,
                    channel_title=str(snippet.get("channelTitle", "")) or None,
                    published_at=(_timestamp(str(published_at)) if published_at else None),
                    position=position,
                    query=query.query,
                    raw_ref=raw_ref,
                )
            )
        return results

    async def fetch_videos(self, video_ids: Sequence[str]) -> Sequence[VideoMetadata]:
        results: list[VideoMetadata] = []
        unique_ids = list(dict.fromkeys(video_ids))
        for offset in range(0, len(unique_ids), 50):
            batch_ids = unique_ids[offset : offset + 50]
            payload, raw_ref = await self._request(
                capability="metadata",
                endpoint="videos.list",
                path="/videos",
                parameters={
                    "part": "snippet,contentDetails,statistics,status",
                    "id": ",".join(batch_ids),
                    "maxResults": len(batch_ids),
                },
            )
            for item in payload.get("items", []):
                if not isinstance(item, dict):
                    continue
                snippet = item.get("snippet", {})
                details = item.get("contentDetails", {})
                statistics = item.get("statistics", {})
                live = snippet.get("liveBroadcastContent", "none")
                results.append(
                    VideoMetadata(
                        video_id=str(item["id"]),
                        channel_id=str(snippet["channelId"]),
                        title=str(snippet.get("title", "")),
                        description=str(snippet.get("description", "")),
                        published_at=_timestamp(str(snippet["publishedAt"])),
                        duration_seconds=parse_iso8601_duration(
                            str(details.get("duration", "PT0S"))
                        ),
                        view_count=_integer(statistics.get("viewCount")),
                        like_count=_integer(statistics.get("likeCount")),
                        comment_count=_integer(statistics.get("commentCount")),
                        thumbnail_url=str(
                            snippet.get("thumbnails", {})
                            .get("high", snippet.get("thumbnails", {}).get("default", {}))
                            .get("url", "")
                        ),
                        raw_ref=raw_ref,
                        channel_title=str(snippet.get("channelTitle", "")),
                        default_language=str(
                            snippet.get("defaultAudioLanguage")
                            or snippet.get("defaultLanguage")
                            or "en"
                        ),
                        category_id=str(snippet.get("categoryId", "28")),
                        is_live=live != "none",
                    )
                )
        return results

    async def fetch_channels(self, channel_ids: Sequence[str]) -> Sequence[ChannelMetadata]:
        results: list[ChannelMetadata] = []
        lookups = list(dict.fromkeys(_channel_lookup(value) for value in channel_ids))
        unique_ids = [value for parameter, value in lookups if parameter == "id"]
        for offset in range(0, len(unique_ids), 50):
            batch_ids = unique_ids[offset : offset + 50]
            payload, raw_ref = await self._request(
                capability="channels",
                endpoint="channels.list",
                path="/channels",
                parameters={
                    "part": "snippet,statistics",
                    "id": ",".join(batch_ids),
                    "maxResults": len(batch_ids),
                },
            )
            results.extend(_channel_metadata(payload, raw_ref=raw_ref))
        for parameter, value in lookups:
            if parameter == "id":
                continue
            payload, raw_ref = await self._request(
                capability="channels",
                endpoint="channels.list",
                path="/channels",
                parameters={
                    "part": "snippet,statistics",
                    parameter: value,
                    "maxResults": 1,
                },
            )
            results.extend(_channel_metadata(payload, raw_ref=raw_ref))
        return results

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]:
        parameters: dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "channelId": channel_id,
            "maxResults": max(1, min(limit, 50)),
            "order": "date",
        }
        if published_after is not None:
            parameters["publishedAfter"] = (
                published_after.astimezone(UTC).isoformat().replace("+00:00", "Z")
            )
        payload, raw_ref = await self._request(
            capability="channels",
            endpoint="search.list.channel",
            path="/search",
            parameters=parameters,
        )
        results: list[DiscoveredVideo] = []
        for position, item in enumerate(payload.get("items", []), start=1):
            if not isinstance(item, dict):
                continue
            identifier = item.get("id", {})
            snippet = item.get("snippet", {})
            video_id = identifier.get("videoId") if isinstance(identifier, dict) else None
            if not video_id or not isinstance(snippet, dict):
                continue
            published_at = snippet.get("publishedAt")
            results.append(
                DiscoveredVideo(
                    video_id=str(video_id),
                    title=str(snippet.get("title", "")) or None,
                    channel_id=str(snippet.get("channelId", channel_id)) or channel_id,
                    channel_title=str(snippet.get("channelTitle", "")) or None,
                    published_at=(_timestamp(str(published_at)) if published_at else None),
                    position=position,
                    query=f"uploads:{channel_id}",
                    raw_ref=raw_ref,
                )
            )
        return results

    async def fetch_comments(
        self,
        video_id: str,
        order: str,
        limit: int,
        include_replies: bool,
    ) -> Sequence[CommentRecord]:
        results: list[CommentRecord] = []
        requested_limit = max(1, min(limit, 300))
        page_token: str | None = None
        while len(results) < requested_limit:
            parameters: dict[str, Any] = {
                "part": "snippet,replies" if include_replies else "snippet",
                "videoId": video_id,
                "maxResults": min(100, requested_limit - len(results)),
                "order": "time" if order == "time" else "relevance",
                "textFormat": "plainText",
            }
            if page_token:
                parameters["pageToken"] = page_token
            payload, raw_ref = await self._request(
                capability="comments",
                endpoint="commentThreads.list",
                path="/commentThreads",
                parameters=parameters,
            )
            for item in payload.get("items", []):
                if not isinstance(item, dict):
                    continue
                thread = item.get("snippet", {})
                top_level = thread.get("topLevelComment", {})
                comment = self._parse_comment(
                    top_level,
                    video_id=video_id,
                    raw_ref=raw_ref,
                    reply_count=_integer(thread.get("totalReplyCount")),
                    parent_id=None,
                )
                if comment is not None:
                    results.append(comment)
                if include_replies:
                    replies = item.get("replies", {})
                    reply_items = replies.get("comments", []) if isinstance(replies, dict) else []
                    for reply in reply_items:
                        if not isinstance(reply, dict):
                            continue
                        parsed = self._parse_comment(
                            reply,
                            video_id=video_id,
                            raw_ref=raw_ref,
                            reply_count=0,
                            parent_id=str(reply.get("snippet", {}).get("parentId", "")) or None,
                        )
                        if parsed is not None:
                            results.append(parsed)
                if len(results) >= requested_limit:
                    break
            page_token = str(payload["nextPageToken"]) if payload.get("nextPageToken") else None
            if not page_token or not payload.get("items"):
                break
        return results[:requested_limit]

    def _parse_comment(
        self,
        item: dict[str, Any],
        *,
        video_id: str,
        raw_ref: str,
        reply_count: int,
        parent_id: str | None,
    ) -> CommentRecord | None:
        snippet = item.get("snippet", {})
        text = str(snippet.get("textOriginal") or snippet.get("textDisplay") or "").strip()
        published = snippet.get("publishedAt")
        if not text or not published:
            return None
        updated = snippet.get("updatedAt")
        return CommentRecord(
            comment_id=str(item.get("id", "")),
            video_id=video_id,
            text=text,
            published_at=_timestamp(str(published)),
            updated_at=_timestamp(str(updated)) if updated else None,
            like_count=_integer(snippet.get("likeCount")),
            reply_count=reply_count,
            parent_id=parent_id,
            raw_ref=raw_ref,
            author_hash=_author_hash(snippet),
            language="en",
            is_reply=parent_id is not None,
        )

    async def _request(
        self,
        *,
        capability: str,
        endpoint: str,
        path: str,
        parameters: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if not self._api_key:
            raise YoutubeOfficialProviderError("YOUTUBE_API_KEY is not configured")
        request = ProviderRequest(
            provider=self.name,
            capability=capability,
            endpoint=endpoint,
            parameters=parameters,
            parser_version=PARSER_VERSION,
            estimated_cost=0.0,
        )
        started_at = datetime.now(tz=UTC)
        client = self._client or httpx.AsyncClient(timeout=20)
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{API_ROOT}{path}",
                params={**parameters, "key": self._api_key},
            )
            completed_at = datetime.now(tz=UTC)
            try:
                payload = response.json()
            except ValueError:
                payload = {"response_text": response.text}
            if not isinstance(payload, dict):
                payload = {"response": payload}
            if response.status_code >= 400:
                error_reason = (
                    payload.get("error", {}).get("errors", [{}])[0].get("reason", "api_error")
                    if isinstance(payload.get("error"), dict)
                    else "api_error"
                )
                self._recorder.record_failure(
                    request,
                    payload=(
                        _safe_comment_payload(payload) if capability == "comments" else payload
                    ),
                    started_at=started_at,
                    completed_at=completed_at,
                    http_status=response.status_code,
                    error_code=str(error_reason),
                    error_message=f"YouTube API returned HTTP {response.status_code}",
                )
                if response.status_code == 429:
                    error_reason = "http_429"
                elif response.status_code >= 500:
                    error_reason = f"http_{response.status_code}"
                raise YoutubeOfficialProviderError(
                    f"YouTube API returned HTTP {response.status_code}",
                    reason=str(error_reason),
                )
            recorded = self._recorder.record_success(
                request,
                payload=(_safe_comment_payload(payload) if capability == "comments" else payload),
                started_at=started_at,
                completed_at=completed_at,
                http_status=response.status_code,
            )
            if capability == "comments":
                item_ids = [str(parameters["videoId"])]
            elif capability == "discovery" or endpoint == "search.list.channel":
                item_ids = [
                    str(item.get("id", {}).get("videoId"))
                    for item in payload.get("items", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("id"), dict)
                    and item.get("id", {}).get("videoId")
                ]
            else:
                item_ids = [
                    str(item["id"])
                    for item in payload.get("items", [])
                    if isinstance(item, dict) and "id" in item
                ]
            self._recorder.link_entities(
                recorded.fetch_id,
                entity_type=(
                    "youtube_video"
                    if capability in {"discovery", "metadata", "comments"}
                    or endpoint == "search.list.channel"
                    else "youtube_channel"
                ),
                entity_ids=item_ids,
            )
            return payload, recorded.raw_ref
        except httpx.HTTPError as error:
            completed_at = datetime.now(tz=UTC)
            self._recorder.record_failure(
                request,
                payload={"network_error": type(error).__name__},
                started_at=started_at,
                completed_at=completed_at,
                http_status=0,
                error_code="network_error",
                error_message=f"YouTube API network error: {type(error).__name__}",
            )
            raise YoutubeOfficialProviderError(
                "YouTube API is unavailable",
                reason="network_error",
            ) from error
        finally:
            if owns_client:
                await client.aclose()
