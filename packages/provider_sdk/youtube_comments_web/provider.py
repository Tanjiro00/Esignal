from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from itertools import islice
from typing import Any

from youtube_comment_downloader import (  # type: ignore[import-untyped]
    SORT_BY_POPULAR,
    SORT_BY_RECENT,
    YoutubeCommentDownloader,
)

from packages.domain import CommentRecord, ProviderRequest
from packages.provider_sdk.base.observability import ProviderFetchRecorder

PARSER_VERSION = "youtube-web-comments-v1.0.0"


class YoutubeWebCommentProviderError(RuntimeError):
    pass


def _author_hash(value: object) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return sha256(f"earlysignal-commenter:{normalized}".encode()).hexdigest()


def _integer(value: object) -> int:
    normalized = str(value or "0").strip().lower().replace(",", "")
    multiplier = 1
    if normalized.endswith("k"):
        multiplier = 1_000
        normalized = normalized[:-1]
    elif normalized.endswith("m"):
        multiplier = 1_000_000
        normalized = normalized[:-1]
    try:
        return max(0, round(float(normalized) * multiplier))
    except ValueError:
        return 0


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    """Drop public profile data before durable storage."""

    return {
        "cid": str(row.get("cid", "")),
        "text": str(row.get("text", "")),
        "time_parsed": float(row.get("time_parsed") or 0),
        "votes": str(row.get("votes", "0")),
        "replies": str(row.get("replies", "0")),
        "reply": bool(row.get("reply", False)),
        "author_hash": _author_hash(row.get("channel") or row.get("author")),
    }


class YoutubeWebCommentProvider:
    name = "youtube_web_comments"

    def __init__(self, *, recorder: ProviderFetchRecorder) -> None:
        self._recorder = recorder

    async def fetch_comments(
        self,
        video_id: str,
        order: str,
        limit: int,
        include_replies: bool,
    ) -> Sequence[CommentRecord]:
        requested_limit = max(1, min(limit, 300))
        request = ProviderRequest(
            provider=self.name,
            capability="comments",
            endpoint="youtubei.comments",
            parameters={
                "video_id": video_id,
                "order": order,
                "limit": requested_limit,
                "include_replies": include_replies,
                "language": "en",
            },
            parser_version=PARSER_VERSION,
            estimated_cost=0,
        )
        started_at = datetime.now(tz=UTC)

        def collect() -> list[dict[str, Any]]:
            downloader = YoutubeCommentDownloader()
            sort_by = SORT_BY_RECENT if order == "time" else SORT_BY_POPULAR
            rows = downloader.get_comments(
                video_id,
                sort_by=sort_by,
                language="en",
                sleep=0.05,
            )
            return list(islice(rows, requested_limit))

        try:
            raw_rows = await asyncio.to_thread(collect)
            safe_rows = [
                _safe_row(row)
                for row in raw_rows
                if isinstance(row, dict) and (include_replies or not bool(row.get("reply")))
            ]
            completed_at = datetime.now(tz=UTC)
            recorded = self._recorder.record_success(
                request,
                payload={
                    "video_id": video_id,
                    "order": order,
                    "comments": safe_rows,
                },
                started_at=started_at,
                completed_at=completed_at,
                http_status=200,
            )
            self._recorder.link_entities(
                recorded.fetch_id,
                entity_type="youtube_video",
                entity_ids=[video_id],
            )
            results: list[CommentRecord] = []
            for row in safe_rows:
                if float(row["time_parsed"]) <= 0:
                    continue
                published_at = datetime.fromtimestamp(
                    float(row["time_parsed"]),
                    tz=UTC,
                )
                comment_id = (
                    str(row["cid"]).strip()
                    or sha256(
                        f"{video_id}:{row['text']}:{published_at.isoformat()}".encode()
                    ).hexdigest()
                )
                text = str(row["text"]).strip()
                if not text:
                    continue
                results.append(
                    CommentRecord(
                        comment_id=comment_id,
                        video_id=video_id,
                        text=text,
                        published_at=published_at,
                        updated_at=None,
                        like_count=_integer(row["votes"]),
                        reply_count=_integer(row["replies"]),
                        parent_id=None,
                        raw_ref=recorded.raw_ref,
                        author_hash=(
                            str(row["author_hash"]) if row["author_hash"] is not None else None
                        ),
                        language="en",
                        is_reply=bool(row["reply"]),
                    )
                )
            return results
        except Exception as error:
            completed_at = datetime.now(tz=UTC)
            self._recorder.record_failure(
                request,
                payload={"video_id": video_id, "error": type(error).__name__},
                started_at=started_at,
                completed_at=completed_at,
                http_status=0,
                error_code="scraper_error",
                error_message=f"Comment scraper failed: {type(error).__name__}",
            )
            raise YoutubeWebCommentProviderError("Web comments are unavailable") from error
