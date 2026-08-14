"""Evidence quality gates.

Two failure modes were found in the v1 audit and both are handled here:

1. Copy farms. Near-identical titles from different channels looked like broad
   cross-creator adoption when they were one template being reposted.
2. Over-broad clusters. "how to make an AI video" style groups are semantically
   close but are not one micro-movement.

The copy-family idea is ported from `packages/clustering/evidence_quality.py`,
which was sound. What changed: similarity is computed over *informative* tokens
selected by corpus idf instead of a hand-written noise list, so the gate works
in any niche without new code.

The third possible outcome, ``watch``, is a first-class result: the candidate is
kept for observation but never shown to a user. Abstention is a normal outcome.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from es_core.anchors import BackgroundCorpus
from es_core.text import containment, jaccard, tokenize
from es_core.types import EvidenceStatus, EvidenceVerdict, Video, sorted_videos


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    copy_jaccard: float = 0.86
    copy_containment: float = 0.92
    minimum_informative_idf: float = 2.0
    minimum_family_heads: int = 2
    minimum_independent_channels: int = 2
    minimum_angle_diversity: float = 0.15
    maximum_copy_family_ratio: float = 0.60
    template_channel_share: float = 0.80


def informative_tokens(title: str, corpus: BackgroundCorpus, policy: EvidencePolicy) -> set[str]:
    """Tokens rare enough in the panel to carry identity."""

    return {
        token for token in tokenize(title) if corpus.idf(token) >= policy.minimum_informative_idf
    }


def copy_families(
    videos: Sequence[Video],
    corpus: BackgroundCorpus,
    *,
    policy: EvidencePolicy | None = None,
) -> tuple[tuple[Video, ...], ...]:
    """Group near-duplicate titles; the earliest upload leads each family.

    Videos are processed oldest first so the family head is the original rather
    than whichever copy happened to be seen first.
    """

    active = policy or EvidencePolicy()
    ordered = sorted_videos(videos)
    heads: list[list[Video]] = []
    signatures: list[set[str]] = []
    for video in ordered:
        signature = informative_tokens(video.title, corpus, active) or set(tokenize(video.title))
        placed = False
        for index, existing in enumerate(signatures):
            if (
                jaccard(signature, existing) >= active.copy_jaccard
                or containment(signature, existing) >= active.copy_containment
            ):
                heads[index].append(video)
                placed = True
                break
        if not placed:
            heads.append([video])
            signatures.append(signature)
    return tuple(tuple(family) for family in heads)


def angle_diversity(
    family_heads: Sequence[Video],
    corpus: BackgroundCorpus,
    policy: EvidencePolicy,
) -> float:
    """1 - mean pairwise token overlap between distinct framings of the topic.

    A cluster where every creator phrases the subject the same way is a template
    being repeated; a real micro-trend shows several angles on one subject.
    """

    if len(family_heads) < 2:
        return 0.0
    signatures = [informative_tokens(video.title, corpus, policy) for video in family_heads]
    overlaps: list[float] = []
    for index, left in enumerate(signatures):
        for right in signatures[index + 1 :]:
            overlaps.append(jaccard(left, right))
    if not overlaps:
        return 0.0
    return round(1.0 - sum(overlaps) / len(overlaps), 6)


def template_channels(
    videos: Sequence[Video],
    corpus: BackgroundCorpus,
    *,
    policy: EvidencePolicy | None = None,
) -> frozenset[str]:
    """Channels whose own uploads are mostly copies of each other.

    Detected from behaviour rather than from a blocklist, so it generalizes.
    """

    active = policy or EvidencePolicy()
    by_channel: dict[str, list[Video]] = {}
    for video in videos:
        by_channel.setdefault(video.channel_id, []).append(video)
    flagged: set[str] = set()
    for channel_id, uploads in by_channel.items():
        if len(uploads) < 3:
            continue
        families = copy_families(uploads, corpus, policy=active)
        duplicate_share = 1.0 - len(families) / len(uploads)
        if duplicate_share >= active.template_channel_share:
            flagged.add(channel_id)
    return frozenset(flagged)


def assess(
    members: Sequence[Video],
    corpus: BackgroundCorpus,
    *,
    policy: EvidencePolicy | None = None,
    known_template_channels: frozenset[str] = frozenset(),
) -> EvidenceVerdict:
    """Decide whether a cluster's evidence can support a user-facing claim."""

    active = policy or EvidencePolicy()
    if not members:
        return EvidenceVerdict("rejected", ("empty_cluster",), (), 0, 0.0, 0.0)

    families = copy_families(members, corpus, policy=active)
    heads = tuple(family[0] for family in families)
    copy_ratio = round(1.0 - len(families) / len(members), 6)
    independent = {
        video.channel_id for video in heads if video.channel_id not in known_template_channels
    }
    diversity = angle_diversity(heads, corpus, active)

    reasons: list[str] = []
    if len(heads) < active.minimum_family_heads:
        reasons.append("insufficient_independent_evidence")
    if len(independent) < active.minimum_independent_channels:
        reasons.append("insufficient_independent_channels")
    if diversity < active.minimum_angle_diversity:
        reasons.append("single_repeated_angle")
    if copy_ratio > active.maximum_copy_family_ratio:
        reasons.append("dominated_by_copies")

    status: EvidenceStatus = "accepted"
    if reasons:
        status = "rejected" if len(reasons) >= 2 else "watch"
    return EvidenceVerdict(
        status=status,
        reasons=tuple(reasons),
        family_head_ids=tuple(video.video_id for video in heads),
        independent_channels=len(independent),
        copy_family_ratio=copy_ratio,
        angle_diversity=diversity,
    )


__all__ = [
    "EvidencePolicy",
    "angle_diversity",
    "assess",
    "copy_families",
    "informative_tokens",
    "template_channels",
]
