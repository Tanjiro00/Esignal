"""What a channel is about, and what it has already covered.

A generic niche feed does not sell: the buyer runs "AI video for product ads",
not "AI in general". Relevance is the thing being paid for, so the profile is
what turns one shared pool of demand into a feed per customer.

The profile is three measurements over the channel's own uploads:

* **centroid** — the middle of everything it publishes;
* **radius** — how wide it ranges, taken as the distance covering most of its
  uploads rather than a fixed constant, because a single-topic channel and a
  broad one need different fits;
* **coverage** — what it has already made, so the feed can drop questions this
  channel answered itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt

from es_core.anchors import AnchorExtractor, AnchorPolicy, BackgroundCorpus
from es_core.types import Anchor, Video

FloatArray = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    lookback_days: int = 180
    minimum_videos: int = 5
    coverage_quantile: float = 0.80
    """Share of a channel's uploads the radius must contain."""
    minimum_radius: float = 0.35
    maximum_radius: float = 0.85
    covered_similarity: float = 0.614
    """Same anchor as the answer threshold: closer than 90% of carrier videos."""


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    channel_id: str
    centroid: tuple[float, ...]
    radius: float
    anchors: tuple[Anchor, ...]
    video_count: int
    recent_video_ids: tuple[str, ...]
    video_vectors: tuple[tuple[float, ...], ...] = ()
    """The channel's own uploads, kept so fit can be multi-modal.

    A centroid averages a channel that covers three subjects into a point that
    matches none of them. Measured against questions asked under a channel's
    own videos, max-similarity-to-any-upload separates relevant from irrelevant
    at 0.95 sd versus 0.71 sd for the centroid.
    """

    @property
    def subject(self) -> str:
        return ", ".join(anchor.term for anchor in self.anchors[:3])

    def fit(self, centroid: Sequence[float]) -> float:
        """Cosine between this channel's subject and something else."""

        left = np.asarray(self.centroid, dtype=np.float32)
        right = np.asarray(centroid, dtype=np.float32)
        if left.size != right.size or not left.size:
            return 0.0
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return round(float(left @ right) / denominator, 6) if denominator else 0.0

    def question_fit(self, centroid: Sequence[float]) -> float:
        """Closeness to the nearest thing this channel actually made.

        Used for ranking questions; `fit` stays centroid-based for comparing
        whole channels to each other.
        """

        if not self.video_vectors:
            return self.fit(centroid)
        target = _normalize(centroid)
        matrix = np.asarray(self.video_vectors, dtype=np.float32)
        return round(float((matrix @ target).max()), 6)

    def in_scope(self, centroid: Sequence[float]) -> bool:
        """Whether a subject sits inside what this channel actually covers."""

        return self.fit(centroid) >= self.radius


def _normalize(vector: npt.ArrayLike) -> FloatArray:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def build(
    channel_id: str,
    videos: Sequence[Video],
    embeddings: Mapping[str, Sequence[float]],
    *,
    as_of: datetime,
    corpus: BackgroundCorpus | None = None,
    policy: ProfilePolicy | None = None,
) -> ChannelProfile | None:
    """Build a profile from a channel's own uploads; None when too little data."""

    active = policy or ProfilePolicy()
    floor = as_of - timedelta(days=active.lookback_days)
    own = [
        video
        for video in videos
        if video.channel_id == channel_id
        and video.observable_at(as_of)
        and video.published_at >= floor
        and video.video_id in embeddings
    ]
    if len(own) < active.minimum_videos:
        return None

    matrix = np.stack([_normalize(embeddings[video.video_id]) for video in own]).astype(np.float32)
    centroid = _normalize(matrix.mean(axis=0))
    similarities = matrix @ centroid
    # The radius is where most of the channel's own work sits, not a constant.
    radius = float(np.quantile(similarities, 1.0 - active.coverage_quantile))
    radius = min(max(radius, active.minimum_radius), active.maximum_radius)

    anchors: tuple[Anchor, ...] = ()
    if corpus is not None:
        anchors = AnchorExtractor(
            corpus, policy=AnchorPolicy(minimum_channel_support=1, maximum_anchors=5)
        ).extract_documents([(video.title, video.video_id) for video in own])

    recent_ids = [
        video.video_id
        for video in sorted(own, key=lambda item: -item.published_at.timestamp())[:50]
    ]
    return ChannelProfile(
        channel_id=channel_id,
        centroid=tuple(float(value) for value in centroid),
        radius=round(radius, 6),
        anchors=anchors,
        video_count=len(own),
        recent_video_ids=tuple(recent_ids),
        video_vectors=tuple(
            tuple(float(value) for value in _normalize(embeddings[video_id]))
            for video_id in recent_ids
        ),
    )


def covered_by(
    profile: ChannelProfile,
    subject_centroid: Sequence[float],
    embeddings: Mapping[str, Sequence[float]],
    *,
    policy: ProfilePolicy | None = None,
) -> tuple[str, ...]:
    """The channel's own videos that already cover a subject."""

    active = policy or ProfilePolicy()
    target = _normalize(subject_centroid)
    covered: list[tuple[float, str]] = []
    for video_id in profile.recent_video_ids:
        vector = embeddings.get(video_id)
        if vector is None:
            continue
        similarity = float(_normalize(vector) @ target)
        if similarity >= active.covered_similarity:
            covered.append((similarity, video_id))
    covered.sort(reverse=True)
    return tuple(video_id for _, video_id in covered)


def neighbourhood(
    profile: ChannelProfile,
    profiles: Sequence[ChannelProfile],
    *,
    limit: int = 300,
) -> tuple[ChannelProfile, ...]:
    """Channels working on the same subject — where this channel's viewers are.

    Their comment sections are the demand this creator can actually serve, which
    is why collection is pointed here rather than spread evenly over the panel.
    """

    scored = [
        (profile.fit(other.centroid), other)
        for other in profiles
        if other.channel_id != profile.channel_id
    ]
    scored.sort(key=lambda pair: -pair[0])
    return tuple(other for score, other in scored[:limit] if score >= profile.radius)


__all__ = [
    "ChannelProfile",
    "ProfilePolicy",
    "build",
    "covered_by",
    "neighbourhood",
]
