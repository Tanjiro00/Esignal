"""The checkpoint pipeline.

One function turns a point-in-time view of the panel into candidates. Production
calls it with ``as_of=now``; a replay calls it with a past timestamp. There is no
separate backtest implementation, which is what makes the evaluation honest: the
thing measured is the thing that ships.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from es_core import evidence as evidence_gate
from es_core import features as feature_builder
from es_core.anchors import AnchorExtractor, AnchorPolicy, BackgroundCorpus
from es_core.clustering import ClusterPolicy, cluster_videos
from es_core.evidence import EvidencePolicy
from es_core.features import FeaturePolicy, NoBaseline, ViewBaseline
from es_core.identity import TopicRegistry
from es_core.types import Candidate, PanelMember, Video

PIPELINE_VERSION = "es-core-pipeline-v2"


@dataclass(frozen=True, slots=True)
class PipelinePolicy:
    active_window_days: int = 35
    history_window_days: int = 180
    anchors: AnchorPolicy = AnchorPolicy()
    clustering: ClusterPolicy = ClusterPolicy()
    evidence: EvidencePolicy = EvidencePolicy()
    features: FeaturePolicy = FeaturePolicy()


def panel_at(members: Sequence[PanelMember], as_of: datetime) -> frozenset[str]:
    """Channel set as it was defined at the checkpoint, not as it is today."""

    return frozenset(member.channel_id for member in members if member.active_at(as_of))


def observable(
    videos: Sequence[Video],
    *,
    as_of: datetime,
    panel: frozenset[str] | None = None,
) -> tuple[Video, ...]:
    """Uploads visible at the checkpoint from channels in the frozen panel."""

    return tuple(
        video
        for video in videos
        if video.observable_at(as_of) and (panel is None or video.channel_id in panel)
    )


def label_for(members: Sequence[Video], anchors: Sequence[object]) -> str:
    """Neutral placeholder label derived from stored evidence.

    A generated, user-facing name is the Taxonomist LLM's job and is always
    grounded in specific evidence ids; the core never invents one.
    """

    anchor_terms = [getattr(anchor, "term", "") for anchor in anchors]
    if anchor_terms:
        return " / ".join(term for term in anchor_terms if term)[:160]
    return members[0].title[:160] if members else ""


def build_candidates(
    videos: Sequence[Video],
    embeddings: Mapping[str, Sequence[float]],
    *,
    as_of: datetime,
    registry: TopicRegistry,
    panel: Sequence[PanelMember] | None = None,
    baseline: ViewBaseline | None = None,
    policy: PipelinePolicy | None = None,
) -> tuple[Candidate, ...]:
    """Produce every candidate observable at ``as_of``, including abstentions."""

    active = policy or PipelinePolicy()
    frozen_panel = panel_at(panel, as_of) if panel is not None else None
    visible = observable(videos, as_of=as_of, panel=frozen_panel)
    if not visible:
        return ()

    active_floor = as_of - timedelta(days=active.active_window_days)
    history_floor = as_of - timedelta(days=active.history_window_days)
    window = tuple(video for video in visible if video.published_at >= active_floor)
    history = tuple(video for video in visible if video.published_at >= history_floor)

    corpus = BackgroundCorpus.build(visible, as_of=as_of, policy=active.anchors)
    extractor = AnchorExtractor(corpus, policy=active.anchors)
    templates = evidence_gate.template_channels(history, corpus, policy=active.evidence)

    candidates: list[Candidate] = []
    for cluster in cluster_videos(window, embeddings, policy=active.clustering):
        anchors = extractor.extract(cluster.members)
        topic = registry.assign(cluster, anchors, as_of=as_of)
        verdict = evidence_gate.assess(
            cluster.members,
            corpus,
            policy=active.evidence,
            known_template_channels=templates,
        )
        topic_history = tuple(
            video for video in history if video.video_id in topic.member_video_ids
        )
        vector = feature_builder.build(
            cluster,
            as_of=as_of,
            history=topic_history,
            anchors=anchors,
            evidence=verdict,
            topic_age_days=registry.age_days(topic.topic_id, as_of),
            baseline=baseline or NoBaseline(),
            policy=active.features,
        )
        candidates.append(
            Candidate(
                topic_id=topic.topic_id,
                as_of=as_of,
                label=label_for(cluster.members, anchors),
                anchors=anchors,
                evidence=verdict,
                features=vector,
                evidence_video_ids=verdict.family_head_ids,
                member_video_ids=tuple(video.video_id for video in cluster.members),
                channel_ids=tuple(sorted(cluster.channel_ids)),
                first_seen_at=topic.first_seen_at,
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.topic_id))


__all__ = [
    "PIPELINE_VERSION",
    "PipelinePolicy",
    "build_candidates",
    "label_for",
    "observable",
    "panel_at",
]
