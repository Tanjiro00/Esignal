"""Unanswered demand: the thing we actually sell.

A demand item is a group of viewers asking the same question, plus the finding
that nothing answers it. Unlike a trend prediction it needs no belief in our
model — the customer clicks through and reads the real comments.

The pipeline is deliberately the same machinery as topic clustering: questions
are embedded with the same model as videos, so "is there a video that answers
this?" is a nearest-neighbour lookup in one shared space rather than a keyword
search.

Three scores are kept separate and never averaged into one number:

* **volume** — how many distinct people asked, and how loudly;
* **fit** — how close the question is to a particular channel's subject;
* **answered** — whether a video already covers it.

Averaging them would hide a weak component behind a strong one, which is the
mistake the v1 score made.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256

import numpy as np
import numpy.typing as npt
from sklearn.cluster import HDBSCAN

from es_core.anchors import AnchorExtractor, AnchorPolicy, BackgroundCorpus
from es_core.types import Anchor

FloatArray = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class DemandComment:
    comment_id: str
    video_id: str
    channel_id: str
    text: str
    published_at: datetime
    like_count: int = 0
    taxonomy: str = ""
    author_hash: str = ""

    @property
    def asker(self) -> str:
        """Distinct-person key; falls back to the comment itself when unknown."""

        return self.author_hash or self.comment_id


@dataclass(frozen=True, slots=True)
class DemandPolicy:
    window_days: int = 30
    minimum_askers: int = 3
    minimum_videos: int = 2
    minimum_channels: int = 2
    minimum_cluster_size: int = 3
    minimum_samples: int = 2
    minimum_mean_similarity: float = 0.62
    minimum_anchor_score: float = 8.0
    """A demand item must be about something specific.

    The first run on production comments showed why: "Is it free?" and "How much
    does it cost?" cluster more strongly than anything else, precisely because
    they are generic — everyone asks them, under every video, about every tool.
    They score highest on volume and are worth nothing as video topics.

    The same corpus statistics that separate a product name from a stop word in
    video titles fix this: a question needs at least one term that is rare in
    the comment background. "consistent character" survives, "is it free" does
    not, and no list of banned phrases is written anywhere.
    """
    answer_similarity: float = 0.614
    """Cosine between a question cluster and a video that answers it.

    Anchored on a natural negative control rather than guessed: the video a
    question was asked *under* demonstrably failed to answer it, since the
    viewer asked anyway. Measured on the 2026-08-14 panel snapshot, carrier
    videos sit at p50 0.407 and p90 0.614 from their question clusters, while
    unrelated videos sit at p50 0.290.

    The threshold is that carrier p90: a video counts as an answer only when it
    is closer to the question than 90% of the videos that provably were not.
    """
    answer_window_days: int = 120


@dataclass(frozen=True, slots=True)
class AnsweringVideo:
    video_id: str
    title: str
    published_at: datetime
    similarity: float


@dataclass(frozen=True, slots=True)
class DemandItem:
    item_id: str
    question: str
    comments: tuple[DemandComment, ...]
    centroid: tuple[float, ...]
    distinct_askers: int
    distinct_videos: int
    distinct_channels: int
    total_likes: int
    first_asked_at: datetime
    last_asked_at: datetime
    mean_similarity: float
    answers: tuple[AnsweringVideo, ...]
    anchors: tuple[Anchor, ...] = ()
    need: str = ""
    """Neutral one-line statement of what viewers want, from the verifier.

    Empty until verification runs. The raw `question` is the loudest comment,
    which is often badly phrased or partial; `need` is what goes on screen.
    """

    @property
    def headline(self) -> str:
        """What the user reads. Falls back to the clearest raw comment."""

        return self.need or self.question

    @property
    def subject(self) -> str:
        """What the question is about, from corpus statistics."""

        return ", ".join(anchor.term for anchor in self.anchors[:2])

    @property
    def answered(self) -> bool:
        return bool(self.answers)

    @property
    def volume_score(self) -> float:
        """People, not comments: one person asking twice is one person."""

        return round(
            self.distinct_askers + math.log1p(self.total_likes) + 0.5 * self.distinct_channels,
            4,
        )

    def age_days(self, as_of: datetime) -> float:
        return round((as_of - self.last_asked_at).total_seconds() / 86_400, 2)

    def fit(self, channel_centroid: Sequence[float]) -> float:
        """Cosine between the question and a specific channel's subject."""

        left = np.asarray(self.centroid, dtype=np.float32)
        right = np.asarray(channel_centroid, dtype=np.float32)
        if left.size != right.size or not left.size:
            return 0.0
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return round(float(left @ right) / denominator, 6) if denominator else 0.0


def _normalize(vector: npt.ArrayLike) -> FloatArray:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def _is_question(comment: DemandComment) -> bool:
    """Structural check only — punctuation, not vocabulary.

    Keeps the gate language-general: no English word list is involved, so the
    same code works when the product moves to another niche or language.
    """

    return "?" in comment.text or comment.taxonomy in {
        "request_for_tutorial",
        "request_for_explanation",
        "comparison_request",
        "pricing_request",
    }


def build_items(
    comments: Sequence[DemandComment],
    embeddings: Mapping[str, Sequence[float]],
    *,
    as_of: datetime,
    policy: DemandPolicy | None = None,
) -> tuple[DemandItem, ...]:
    """Cluster questions asked inside the window into demand items."""

    active = policy or DemandPolicy()
    floor = as_of - timedelta(days=active.window_days)
    usable = [
        comment
        for comment in comments
        if floor <= comment.published_at <= as_of
        and comment.comment_id in embeddings
        and _is_question(comment)
    ]
    if len(usable) < active.minimum_cluster_size:
        return ()

    # Background statistics over every comment in the window, so "specific" is
    # measured against how people actually write comments, not video titles.
    corpus = BackgroundCorpus.from_documents(
        ((comment.text, comment.published_at) for comment in comments),
        as_of=as_of,
        policy=AnchorPolicy(background_days=max(active.window_days * 6, 180)),
    )
    extractor = AnchorExtractor(
        corpus,
        policy=AnchorPolicy(
            minimum_channel_support=2,
            minimum_anchor_score=active.minimum_anchor_score,
        ),
    )

    matrix = np.stack([_normalize(embeddings[c.comment_id]) for c in usable]).astype(np.float32)
    labels = HDBSCAN(
        min_cluster_size=active.minimum_cluster_size,
        min_samples=active.minimum_samples,
        metric="euclidean",
        cluster_selection_method="leaf",
        copy=True,
    ).fit_predict(matrix)

    items: list[DemandItem] = []
    for label in sorted({int(value) for value in labels if value >= 0}):
        indexes = np.flatnonzero(labels == label)
        members = [usable[int(index)] for index in indexes]
        askers = {comment.asker for comment in members}
        videos = {comment.video_id for comment in members}
        channels = {comment.channel_id for comment in members}
        if (
            len(askers) < active.minimum_askers
            or len(videos) < active.minimum_videos
            or len(channels) < active.minimum_channels
        ):
            continue

        member_matrix = matrix[indexes]
        centroid = _normalize(member_matrix.mean(axis=0))
        similarities = member_matrix @ centroid
        mean_similarity = float(similarities.mean())
        if mean_similarity < active.minimum_mean_similarity:
            continue

        anchors = extractor.extract_documents(
            [(comment.text, comment.asker) for comment in members]
        )
        if not extractor.anchored(anchors):
            continue

        # The comment closest to the centre is the clearest phrasing of the ask.
        representative = members[int(np.argmax(similarities))]
        items.append(
            DemandItem(
                item_id="d_"
                + sha256("|".join(sorted(c.comment_id for c in members)).encode()).hexdigest()[:16],
                question=representative.text.strip()[:300],
                comments=tuple(sorted(members, key=lambda c: (-c.like_count, c.published_at))),
                centroid=tuple(float(value) for value in centroid),
                distinct_askers=len(askers),
                distinct_videos=len(videos),
                distinct_channels=len(channels),
                total_likes=sum(c.like_count for c in members),
                first_asked_at=min(c.published_at for c in members),
                last_asked_at=max(c.published_at for c in members),
                mean_similarity=round(mean_similarity, 6),
                answers=(),
                anchors=anchors,
            )
        )
    return tuple(items)


def attach_answers(
    items: Sequence[DemandItem],
    video_embeddings: Mapping[str, Sequence[float]],
    video_meta: Mapping[str, tuple[str, datetime]],
    *,
    as_of: datetime,
    policy: DemandPolicy | None = None,
) -> tuple[DemandItem, ...]:
    """Find videos that already answer each question.

    Videos the questions were asked *under* are excluded: the question exists
    despite that video, so it plainly did not answer it.
    """

    active = policy or DemandPolicy()
    if not items or not video_embeddings:
        return tuple(items)

    floor = as_of - timedelta(days=active.answer_window_days)
    candidates = [
        video_id
        for video_id in video_embeddings
        if video_id in video_meta and floor <= video_meta[video_id][1] <= as_of
    ]
    if not candidates:
        return tuple(items)
    matrix = np.stack([_normalize(video_embeddings[v]) for v in candidates]).astype(np.float32)

    resolved: list[DemandItem] = []
    for item in items:
        carriers = {comment.video_id for comment in item.comments}
        similarity = matrix @ np.asarray(item.centroid, dtype=np.float32)
        hits = [
            AnsweringVideo(
                video_id=candidates[index],
                title=video_meta[candidates[index]][0],
                published_at=video_meta[candidates[index]][1],
                similarity=round(float(similarity[index]), 6),
            )
            for index in np.flatnonzero(similarity >= active.answer_similarity).tolist()
            if candidates[index] not in carriers
        ]
        hits.sort(key=lambda answer: -answer.similarity)
        resolved.append(replace(item, answers=tuple(hits[:5])))
    return tuple(resolved)


__all__ = [
    "AnsweringVideo",
    "DemandComment",
    "DemandItem",
    "DemandPolicy",
    "attach_answers",
    "build_items",
]
