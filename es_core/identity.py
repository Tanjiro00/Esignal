"""Persistent topic identity.

v1 derived ``topic_key`` from a hash of the member video ids, so a single new
upload produced a completely different topic, and a helper then tried to sew the
fragments back together by centroid similarity. Without stable identity you
cannot measure lead time from first observation, cannot suppress repeat alerts
and cannot model a lifecycle.

Here a topic is an entity that persists across checkpoints. Matching combines
semantic proximity with concrete overlap (shared members or shared anchors), so
two different subjects that merely sound alike do not collapse into one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256

from es_core.types import Anchor, Cluster, LineageEvent, TopicIdentity


@dataclass(frozen=True, slots=True)
class IdentityPolicy:
    match_similarity: float = 0.84
    minimum_jaccard: float = 0.10
    centroid_decay: float = 0.30
    """Weight of the new observation when updating a topic centroid."""


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _blend(
    current: Sequence[float],
    observed: Sequence[float],
    alpha: float,
) -> tuple[float, ...]:
    blended = [(1 - alpha) * a + alpha * b for a, b in zip(current, observed, strict=True)]
    norm = math.sqrt(sum(value * value for value in blended))
    if norm == 0.0:
        return tuple(blended)
    return tuple(value / norm for value in blended)


def _new_topic_id(cluster: Cluster, anchors: Sequence[Anchor], at: datetime) -> str:
    seed = "|".join(
        (
            at.isoformat(),
            ",".join(sorted(video.video_id for video in cluster.members)),
            ",".join(anchor.term for anchor in anchors),
        )
    )
    return f"t_{sha256(seed.encode()).hexdigest()[:16]}"


class TopicRegistry:
    """In-memory registry; a repository persists the same state in `es_data`."""

    def __init__(self, *, policy: IdentityPolicy | None = None) -> None:
        self.policy = policy or IdentityPolicy()
        self._topics: dict[str, TopicIdentity] = {}
        self._lineage: list[LineageEvent] = []

    @property
    def topics(self) -> tuple[TopicIdentity, ...]:
        return tuple(
            sorted(
                (topic for topic in self._topics.values() if topic.merged_into is None),
                key=lambda topic: topic.topic_id,
            )
        )

    @property
    def lineage(self) -> tuple[LineageEvent, ...]:
        return tuple(self._lineage)

    def get(self, topic_id: str) -> TopicIdentity | None:
        return self._topics.get(topic_id)

    def load(self, topics: Sequence[TopicIdentity]) -> None:
        for topic in topics:
            self._topics[topic.topic_id] = topic

    def _matches(self, cluster: Cluster, anchors: Sequence[Anchor]) -> list[TopicIdentity]:
        member_ids = {video.video_id for video in cluster.members}
        anchor_terms = {anchor.term for anchor in anchors}
        matched: list[TopicIdentity] = []
        for topic in self.topics:
            if cosine(cluster.centroid, topic.centroid) < self.policy.match_similarity:
                continue
            union = member_ids | topic.member_video_ids
            overlap = len(member_ids & topic.member_video_ids) / max(len(union), 1)
            if overlap >= self.policy.minimum_jaccard or (anchor_terms & set(topic.anchor_terms)):
                matched.append(topic)
        return sorted(matched, key=lambda topic: (-len(topic.member_video_ids), topic.topic_id))

    def assign(
        self,
        cluster: Cluster,
        anchors: Sequence[Anchor],
        *,
        as_of: datetime,
    ) -> TopicIdentity:
        """Resolve a cluster to a persistent topic, recording lineage."""

        matches = self._matches(cluster, anchors)
        member_ids = frozenset(video.video_id for video in cluster.members)
        channel_ids = frozenset(video.channel_id for video in cluster.members)
        anchor_terms = tuple(anchor.term for anchor in anchors)

        if not matches:
            topic = TopicIdentity(
                topic_id=_new_topic_id(cluster, anchors, as_of),
                first_seen_at=as_of,
                last_seen_at=as_of,
                centroid=tuple(cluster.centroid),
                anchor_terms=anchor_terms,
                member_video_ids=member_ids,
                channel_ids=channel_ids,
            )
            self._topics[topic.topic_id] = topic
            self._lineage.append(LineageEvent("created", topic.topic_id, as_of))
            return topic

        winner = matches[0]
        for loser in matches[1:]:
            self._topics[loser.topic_id] = replace(loser, merged_into=winner.topic_id)
            self._lineage.append(LineageEvent("merge", winner.topic_id, as_of, (loser.topic_id,)))
            member_ids |= loser.member_video_ids
            channel_ids |= loser.channel_ids

        updated = replace(
            winner,
            last_seen_at=as_of,
            centroid=_blend(winner.centroid, cluster.centroid, self.policy.centroid_decay),
            anchor_terms=anchor_terms or winner.anchor_terms,
            member_video_ids=winner.member_video_ids | member_ids,
            channel_ids=winner.channel_ids | channel_ids,
        )
        self._topics[updated.topic_id] = updated
        if len(matches) == 1:
            self._lineage.append(LineageEvent("continue", updated.topic_id, as_of))
        return updated

    def age_days(self, topic_id: str, as_of: datetime) -> float:
        topic = self._topics.get(topic_id)
        if topic is None:
            return 0.0
        return round((as_of - topic.first_seen_at).total_seconds() / 86_400, 3)


__all__ = ["IdentityPolicy", "TopicRegistry", "cosine"]
