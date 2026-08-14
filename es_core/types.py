"""Value types for the EarlySignal v2 core.

Everything here is frozen, hashable and free of I/O. The core never reads a
clock, a database or the network: callers pass the observation time explicitly
so that a production run and a historical replay are the same code path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EvidenceStatus = Literal["accepted", "watch", "rejected"]
LineageKind = Literal["created", "continue", "merge", "split"]


@dataclass(frozen=True, slots=True)
class Video:
    """A panel upload as it was known at ``discovered_at``.

    ``published_at`` is event time and ``discovered_at`` is observation time.
    Point-in-time views filter on ``discovered_at``; feature windows use
    ``published_at``.
    """

    video_id: str
    channel_id: str
    title: str
    published_at: datetime
    discovered_at: datetime
    description: str = ""

    def observable_at(self, as_of: datetime) -> bool:
        return self.discovered_at <= as_of and self.published_at <= as_of


@dataclass(frozen=True, slots=True)
class PanelMember:
    """Membership of a channel in the observed population.

    Membership is versioned so the panel can be reconstructed exactly as it was
    on any past date, which is what removes survivorship bias from outcomes.
    """

    channel_id: str
    joined_at: datetime
    left_at: datetime | None = None

    def active_at(self, as_of: datetime) -> bool:
        if self.joined_at > as_of:
            return False
        return self.left_at is None or self.left_at > as_of


@dataclass(frozen=True, slots=True)
class Anchor:
    """A term that makes a cluster about something specific."""

    term: str
    score: float
    lift: float
    idf: float
    novelty: float
    channel_support: int


@dataclass(frozen=True, slots=True)
class EvidenceVerdict:
    status: EvidenceStatus
    reasons: tuple[str, ...]
    family_head_ids: tuple[str, ...]
    independent_channels: int
    copy_family_ratio: float
    angle_diversity: float


@dataclass(frozen=True, slots=True)
class Cluster:
    """A semantic cluster of uploads inside the active window."""

    members: tuple[Video, ...]
    centroid: tuple[float, ...]
    exemplars: tuple[tuple[float, ...], ...]
    mean_similarity: float
    minimum_similarity: float

    @property
    def channel_ids(self) -> frozenset[str]:
        return frozenset(video.channel_id for video in self.members)


@dataclass(frozen=True, slots=True)
class TopicIdentity:
    """A persistent topic, stable across checkpoints."""

    topic_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    centroid: tuple[float, ...]
    anchor_terms: tuple[str, ...]
    member_video_ids: frozenset[str]
    channel_ids: frozenset[str]
    merged_into: str | None = None


@dataclass(frozen=True, slots=True)
class LineageEvent:
    kind: LineageKind
    topic_id: str
    at: datetime
    related_topic_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Candidate:
    """A scored topic observation at one checkpoint."""

    topic_id: str
    as_of: datetime
    label: str
    anchors: tuple[Anchor, ...]
    evidence: EvidenceVerdict
    features: dict[str, float] = field(default_factory=dict)
    evidence_video_ids: tuple[str, ...] = ()
    member_video_ids: tuple[str, ...] = ()
    channel_ids: tuple[str, ...] = ()
    first_seen_at: datetime | None = None

    @property
    def publishable(self) -> bool:
        return self.evidence.status == "accepted"


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: Candidate
    rank_score: float
    probability: float | None
    abstained: bool
    reason_codes: tuple[str, ...]


def sorted_videos(videos: Sequence[Video]) -> tuple[Video, ...]:
    """Deterministic ordering; identical input always yields identical output."""

    return tuple(sorted(videos, key=lambda video: (video.published_at, video.video_id)))


__all__ = [
    "Anchor",
    "Candidate",
    "Cluster",
    "EvidenceStatus",
    "EvidenceVerdict",
    "LineageEvent",
    "LineageKind",
    "PanelMember",
    "ScoredCandidate",
    "TopicIdentity",
    "Video",
    "sorted_videos",
]
