"""Build and store the demand feed.

Runs the `es_core` engine over stored comments and persists the result, so the
API reads rows instead of recomputing clustering per request.

The steps mirror the core exactly: embed what is new, cluster questions, check
whether any video already answers them, verify meaning with a grounded model,
then store. Anything the verifier rejects is not stored as publishable — a joke
that reaches ranking has already reached the customer.
"""

from __future__ import annotations

import json
import os
import struct
import urllib.request
from base64 import b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    CommentEmbedding,
    DemandItemComment,
    PanelMembership,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from apps.api.models import (
    DemandItem as DemandItemRow,
)
from es_core.demand_items import (
    DemandComment,
    DemandItem,
    DemandPolicy,
    attach_answers,
    build_items,
)
from es_core.verification import (
    VERIFIER_VERSION,
    build_request,
    parse_response,
)
from es_core.verification import (
    apply as apply_verifications,
)

EMBEDDING_VERSION = "comment-embedding-v1"
VIDEO_EMBEDDING_VERSION = "video-embedding-openai-v1"
"""Videos must live in the *same* space as questions.

Production still stores v1's 64-dimensional token-hash vectors under a
different version. Comparing a 256-dimensional question against those would be
meaningless, so answer detection uses only vectors written by this model.
"""
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 256
PIPELINE_VERSION = "demand-feed-v1"
VERIFY_BATCH = 60


@dataclass(frozen=True)
class DemandFeedResult:
    embedded: int
    clustered: int
    verified: int
    stored: int
    unanswered: int


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _openai_key(settings: Settings) -> str:
    """Read the key, unwrapping pydantic's SecretStr.

    Interpolating a SecretStr into a string yields "**********", which the API
    accepts as a well-formed header and rejects with 401 — a failure that looks
    like a credentials problem rather than a code one.
    """

    raw = getattr(settings, "openai_api_key", "")
    key = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    key = key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for the demand feed")
    return key


def _openai_model(settings: Settings) -> str:
    raw = getattr(settings, "openai_model", "")
    model = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    return model or "gpt-4.1-mini"


def _post(url: str, payload: dict[str, object], key: str, *, timeout: int = 120) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


class DemandFeedService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ---------------------------------------------------------------- embedding

    def _pending_comments(self, *, window_days: int, limit: int) -> list[YoutubeComment]:
        floor = datetime.now(tz=UTC) - timedelta(days=window_days)
        embedded = select(CommentEmbedding.comment_id).where(
            CommentEmbedding.embedding_version == EMBEDDING_VERSION
        )
        return list(
            self._session.scalars(
                select(YoutubeComment)
                .where(
                    YoutubeComment.published_at >= floor,
                    YoutubeComment.id.not_in(embedded),
                )
                .order_by(YoutubeComment.published_at.desc())
                .limit(limit)
            )
        )

    def embed_new_comments(self, *, window_days: int, limit: int) -> int:
        pending = self._pending_comments(window_days=window_days, limit=limit)
        if not pending:
            return 0
        key = _openai_key(self._settings)
        written = 0
        now = datetime.now(tz=UTC)
        for start in range(0, len(pending), 256):
            batch = pending[start : start + 256]
            texts = [comment.text[:400] for comment in batch]
            payload = _post(
                "https://api.openai.com/v1/embeddings",
                {
                    "model": EMBEDDING_MODEL,
                    "input": texts,
                    "dimensions": EMBEDDING_DIMENSIONS,
                },
                key,
            )
            ordered = sorted(payload["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in ordered]
            for comment, vector in zip(batch, vectors, strict=True):
                self._session.add(
                    CommentEmbedding(
                        comment_id=comment.id,
                        embedding_version=EMBEDDING_VERSION,
                        model_name=EMBEDDING_MODEL,
                        dimensions=EMBEDDING_DIMENSIONS,
                        vector_json=[round(value, 7) for value in vector],
                        source_hash=sha256(comment.text.encode()).hexdigest(),
                        calculated_at=now,
                    )
                )
                written += 1
            self._session.commit()
        return written

    def embed_new_videos(self, *, window_days: int, limit: int) -> int:
        """Embed panel uploads with the same model the questions use."""

        from apps.api.models import VideoEmbedding

        floor = datetime.now(tz=UTC) - timedelta(days=window_days)
        embedded = select(VideoEmbedding.video_id).where(
            VideoEmbedding.embedding_version == VIDEO_EMBEDDING_VERSION
        )
        pending = list(
            self._session.scalars(
                select(YoutubeVideo)
                .join(PanelMembership, PanelMembership.channel_id == YoutubeVideo.channel_id)
                .where(
                    PanelMembership.left_at.is_(None),
                    YoutubeVideo.published_at >= floor,
                    YoutubeVideo.id.not_in(embedded),
                )
                .order_by(YoutubeVideo.published_at.desc())
                .limit(limit)
            )
        )
        if not pending:
            return 0
        key = _openai_key(self._settings)
        now = datetime.now(tz=UTC)
        written = 0
        for start in range(0, len(pending), 256):
            batch = pending[start : start + 256]
            texts = [f"{video.title} {(video.description or '')[:300]}".strip() for video in batch]
            payload = _post(
                "https://api.openai.com/v1/embeddings",
                {
                    "model": EMBEDDING_MODEL,
                    "input": texts,
                    "dimensions": EMBEDDING_DIMENSIONS,
                },
                key,
            )
            ordered = sorted(payload["data"], key=lambda row: row["index"])
            for video, row in zip(batch, ordered, strict=True):
                self._session.add(
                    VideoEmbedding(
                        video_id=video.id,
                        embedding_version=VIDEO_EMBEDDING_VERSION,
                        model_name=EMBEDDING_MODEL,
                        dimensions=EMBEDDING_DIMENSIONS,
                        vector_json=[round(value, 7) for value in row["embedding"]],
                        entities_json=[],
                        source_hash=sha256(video.title.encode()).hexdigest(),
                        calculated_at=now,
                    )
                )
                written += 1
            self._session.commit()
        return written

    # ----------------------------------------------------------------- building

    def _load_comments(
        self, *, window_days: int
    ) -> tuple[list[DemandComment], dict[str, tuple[float, ...]]]:
        floor = datetime.now(tz=UTC) - timedelta(days=window_days)
        rows = self._session.execute(
            select(YoutubeComment, CommentEmbedding, YoutubeVideo, YoutubeChannel)
            .join(CommentEmbedding, CommentEmbedding.comment_id == YoutubeComment.id)
            .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
            .join(YoutubeChannel, YoutubeChannel.id == YoutubeVideo.channel_id)
            .where(
                YoutubeComment.published_at >= floor,
                CommentEmbedding.embedding_version == EMBEDDING_VERSION,
            )
        ).all()
        comments: list[DemandComment] = []
        embeddings: dict[str, tuple[float, ...]] = {}
        for comment, embedding, video, channel in rows:
            comments.append(
                DemandComment(
                    comment_id=comment.id,
                    video_id=video.youtube_video_id,
                    channel_id=channel.youtube_channel_id,
                    text=comment.text,
                    published_at=_aware(comment.published_at),
                    like_count=comment.like_count or 0,
                    author_hash=comment.author_hash or "",
                )
            )
            embeddings[comment.id] = tuple(embedding.vector_json)
        return comments, embeddings

    def _panel_videos(
        self, *, window_days: int
    ) -> tuple[dict[str, tuple[float, ...]], dict[str, tuple[str, datetime]]]:
        from apps.api.models import VideoEmbedding

        floor = datetime.now(tz=UTC) - timedelta(days=window_days)
        rows = self._session.execute(
            select(YoutubeVideo, VideoEmbedding)
            .join(VideoEmbedding, VideoEmbedding.video_id == YoutubeVideo.id)
            .join(PanelMembership, PanelMembership.channel_id == YoutubeVideo.channel_id)
            .where(
                PanelMembership.left_at.is_(None),
                YoutubeVideo.published_at >= floor,
                VideoEmbedding.embedding_version == VIDEO_EMBEDDING_VERSION,
            )
        ).all()
        vectors: dict[str, tuple[float, ...]] = {}
        meta: dict[str, tuple[str, datetime]] = {}
        for video, embedding in rows:
            vectors[video.youtube_video_id] = tuple(embedding.vector_json)
            meta[video.youtube_video_id] = (video.title, _aware(video.published_at))
        return vectors, meta

    # ------------------------------------------------------------- verification

    def _verify(self, items: tuple[DemandItem, ...]) -> tuple[DemandItem, ...]:
        if not items:
            return ()
        key = _openai_key(self._settings)
        model = _openai_model(self._settings)
        verdicts = []
        for item in items[:VERIFY_BATCH]:
            request = build_request(item)
            try:
                answer = _post(
                    "https://api.openai.com/v1/chat/completions",
                    {
                        "model": model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": _instructions()},
                            {"role": "user", "content": request.payload},
                        ],
                    },
                    key,
                )
                raw = answer["choices"][0]["message"]["content"]
            except Exception:  # noqa: BLE001 - a failed verdict simply drops the item
                continue
            verdicts.append(parse_response(item, raw))
        return apply_verifications(items, verdicts)

    # ------------------------------------------------------------------ storage

    def _store(self, items: tuple[DemandItem, ...], *, as_of: datetime) -> int:
        keys = [item.item_id[:32] for item in items]
        if keys:
            existing = self._session.scalars(
                select(DemandItemRow.id).where(
                    DemandItemRow.item_key.in_(keys), DemandItemRow.as_of == as_of
                )
            ).all()
            if existing:
                self._session.execute(
                    delete(DemandItemComment).where(DemandItemComment.demand_item_id.in_(existing))
                )
                self._session.execute(delete(DemandItemRow).where(DemandItemRow.id.in_(existing)))
        stored = 0
        for item in items:
            row_id = str(uuid4())
            self._session.add(
                DemandItemRow(
                    id=row_id,
                    item_key=item.item_id[:32],
                    as_of=as_of,
                    question=item.question,
                    need=item.need,
                    subject=item.subject,
                    distinct_askers=item.distinct_askers,
                    distinct_videos=item.distinct_videos,
                    distinct_channels=item.distinct_channels,
                    total_likes=item.total_likes,
                    first_asked_at=item.first_asked_at,
                    last_asked_at=item.last_asked_at,
                    mean_similarity=item.mean_similarity,
                    volume_score=item.volume_score,
                    answered=item.answered,
                    answer_video_ids_json=[answer.video_id for answer in item.answers],
                    anchors_json=[
                        {"term": anchor.term, "score": anchor.score} for anchor in item.anchors
                    ],
                    centroid_json=[round(value, 7) for value in item.centroid],
                    verified=bool(item.need),
                    verifier_version=VERIFIER_VERSION if item.need else None,
                    pipeline_version=PIPELINE_VERSION,
                    created_at=datetime.now(tz=UTC),
                )
            )
            evidence = set(item.comments[:3])
            for position, comment in enumerate(item.comments):
                self._session.add(
                    DemandItemComment(
                        demand_item_id=row_id,
                        comment_id=comment.comment_id,
                        is_evidence=comment in evidence,
                        position=position,
                    )
                )
            stored += 1
        self._session.commit()
        return stored

    # -------------------------------------------------------------------- entry

    def run(
        self,
        *,
        window_days: int = 30,
        embed_limit: int = 2000,
        verify: bool = True,
    ) -> DemandFeedResult:
        as_of = datetime.now(tz=UTC)
        embedded = self.embed_new_comments(window_days=window_days, limit=embed_limit)
        embedded += self.embed_new_videos(window_days=window_days, limit=embed_limit)
        comments, embeddings = self._load_comments(window_days=window_days)
        items = build_items(
            comments,
            embeddings,
            as_of=as_of,
            policy=DemandPolicy(window_days=window_days),
        )
        vectors, meta = self._panel_videos(window_days=120)
        items = attach_answers(items, vectors, meta, as_of=as_of)
        clustered = len(items)
        if verify:
            items = self._verify(items)
        stored = self._store(items, as_of=as_of)
        return DemandFeedResult(
            embedded=embedded,
            clustered=clustered,
            verified=len(items),
            stored=stored,
            unanswered=sum(1 for item in items if not item.answered),
        )


def _instructions() -> str:
    from es_core.verification import INSTRUCTIONS

    return INSTRUCTIONS


def encode_vector(values: list[float]) -> str:
    return b64encode(struct.pack(f"<{len(values)}f", *values)).decode()


__all__ = [
    "EMBEDDING_VERSION",
    "PIPELINE_VERSION",
    "DemandFeedResult",
    "DemandFeedService",
]
