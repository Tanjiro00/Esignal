from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from packages.clustering.microtopics import MicrotopicDocument
from packages.clustering.microtopics_v7 import normalize_format_neutral_title
from packages.clustering.microtopics_v8 import infer_microtopic_identity_v8, topic_key_v8


class TitleEvidence(Protocol):
    @property
    def video_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def channel_id(self) -> str: ...

    @property
    def upload_date(self) -> datetime: ...


_TOKEN = re.compile(r"[a-z0-9]+")
_TITLE_NOISE = frozenset(
    {
        "a",
        "an",
        "and",
        "ai",
        "are",
        "create",
        "for",
        "free",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "make",
        "of",
        "on",
        "the",
        "this",
        "to",
        "tool",
        "tools",
        "using",
        "video",
        "videos",
        "with",
        "you",
        "your",
    }
)

_RELEASE_ANCHOR_NOISE = _TITLE_NOISE | frozenset(
    {
        "agent",
        "agents",
        "all",
        "alternative",
        "any",
        "app",
        "apps",
        "available",
        "best",
        "better",
        "breaking",
        "changes",
        "chinese",
        "china",
        "course",
        "crushes",
        "every",
        "everything",
        "finally",
        "filmmaking",
        "generate",
        "generator",
        "generators",
        "guide",
        "hours",
        "insane",
        "into",
        "kill",
        "limits",
        "manually",
        "masterclass",
        "model",
        "models",
        "monthly",
        "new",
        "news",
        "no",
        "now",
        "one",
        "open",
        "own",
        "paid",
        "prepare",
        "reason",
        "replaced",
        "review",
        "reviews",
        "right",
        "saved",
        "see",
        "shocked",
        "source",
        "stop",
        "tested",
        "that",
        "time",
        "times",
        "today",
        "top",
        "trap",
        "try",
        "tutorial",
        "tutorials",
        "unlimited",
        "updates",
        "viral",
        "ways",
        "week",
        "weeks",
        "why",
        "winner",
        "workflow",
        "workflows",
    }
)

_CONCEPT_ALIASES = {
    "dub": "dubbing",
    "dubbed": "dubbing",
    "dubs": "dubbing",
    "economics": "economy",
    "economic": "economy",
    "film": "filmmaking",
    "films": "filmmaking",
    "movie": "filmmaking",
    "movies": "filmmaking",
    "layoff": "layoffs",
    "locally": "local",
    "pricing": "price",
    "storyboards": "storyboard",
    "subscriptions": "subscription",
    "translate": "translation",
    "translated": "translation",
    "translator": "translation",
    "voices": "voice",
}

_EXPLICIT_NON_ENGLISH = re.compile(
    r"\b(?:arabic|bengali|deutsch|espa(?:n|ñ)ol|fran(?:c|ç)ais|hindi|indonesian|"
    r"italiano|japanese|korean|portugu(?:e|ê)s|russian|tamil|telugu|thai|turkish|"
    r"urdu|vietnamese)\b",
    re.IGNORECASE,
)
_ROMANIZED_HINDI_MARKERS = frozenset(
    {"aap", "aur", "hai", "kaise", "karo", "ke", "ko", "liye", "mein", "wala", "wali"}
)


@dataclass(frozen=True)
class EvidenceQualityPolicy:
    near_duplicate_jaccard: float = 0.86
    near_duplicate_containment: float = 0.92
    minimum_title_families: int = 2
    minimum_concrete_identity_videos: int = 2
    minimum_concrete_identity_share: float = 0.5


COPY_RESISTANT_EVIDENCE_POLICY = EvidenceQualityPolicy(
    minimum_concrete_identity_videos=0,
    minimum_concrete_identity_share=0,
)


@dataclass(frozen=True)
class EvidenceQualityAssessment:
    accepted: bool
    reason_codes: tuple[str, ...]
    raw_video_count: int
    independent_video_count: int
    independent_channel_count: int
    title_family_count: int
    dominant_identity_key: str | None
    dominant_identity_label: str | None
    dominant_identity_videos: int
    concrete_identity_share: float
    representative_video_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceReleasePolicy:
    near_duplicate_jaccard: float = 0.72
    near_duplicate_containment: float = 0.82
    minimum_title_families: int = 2
    minimum_independent_channels: int = 2
    minimum_anchor_families: int = 2
    maximum_non_english_share: float = 0.34


@dataclass(frozen=True)
class EvidenceReleaseAssessment:
    pre_audit_passed: bool
    reason_codes: tuple[str, ...]
    raw_video_count: int
    title_family_count: int
    independent_channel_count: int
    shared_anchor_concepts: tuple[str, ...]
    strongest_anchor_family_count: int
    non_english_family_count: int
    non_english_share: float
    representative_video_ids: tuple[str, ...]


def normalized_title_tokens(title: str) -> frozenset[str]:
    """Return deterministic substantive tokens for copy-family detection."""

    ascii_title = unicodedata.normalize("NFKD", normalize_format_neutral_title(title))
    ascii_title = ascii_title.encode("ascii", "ignore").decode("ascii").lower()
    return frozenset(token for token in _TOKEN.findall(ascii_title) if token not in _TITLE_NOISE)


def _release_anchor_concepts(title: str) -> frozenset[str]:
    return frozenset(
        _CONCEPT_ALIASES.get(token, token)
        for token in normalized_title_tokens(title)
        if token not in _RELEASE_ANCHOR_NOISE and not token.isdigit()
    )


def _looks_non_english(title: str) -> bool:
    if _EXPLICIT_NON_ENGLISH.search(title):
        return True
    letters = [character for character in title if character.isalpha()]
    if letters:
        latin_letters = sum("LATIN" in unicodedata.name(character, "") for character in letters)
        if latin_letters / len(letters) < 0.85:
            return True
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    tokens = set(_TOKEN.findall(normalized))
    return len(tokens & _ROMANIZED_HINDI_MARKERS) >= 2


def titles_are_near_duplicates(
    first: str,
    second: str,
    *,
    policy: EvidenceQualityPolicy | None = None,
) -> bool:
    selected = policy or EvidenceQualityPolicy()
    first_tokens = normalized_title_tokens(first)
    second_tokens = normalized_title_tokens(second)
    if not first_tokens or not second_tokens:
        return first_tokens == second_tokens
    return _token_sets_are_near_duplicates(first_tokens, second_tokens, policy=selected)


def _token_sets_are_near_duplicates(
    first_tokens: frozenset[str],
    second_tokens: frozenset[str],
    *,
    policy: EvidenceQualityPolicy,
) -> bool:
    if not first_tokens or not second_tokens:
        return first_tokens == second_tokens
    overlap = len(first_tokens & second_tokens)
    jaccard = overlap / len(first_tokens | second_tokens)
    containment = overlap / min(len(first_tokens), len(second_tokens))
    return (
        jaccard >= policy.near_duplicate_jaccard or containment >= policy.near_duplicate_containment
    )


def title_family_groups[EvidenceT: TitleEvidence](
    evidence: Sequence[EvidenceT],
    *,
    policy: EvidenceQualityPolicy | None = None,
) -> tuple[tuple[EvidenceT, ...], ...]:
    """Group copied or near-copied titles with an order-independent union-find."""

    selected = policy or EvidenceQualityPolicy()
    rows = tuple(sorted(evidence, key=lambda item: item.video_id))
    token_sets = tuple(normalized_title_tokens(row.title) for row in rows)
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    postings: dict[str, set[int]] = {}
    empty_indexes: list[int] = []
    for second, second_tokens in enumerate(token_sets):
        candidates: set[int] = set()
        if second_tokens:
            for token in second_tokens:
                candidates.update(postings.get(token, ()))
        else:
            candidates.update(empty_indexes)
        for first in candidates:
            if _token_sets_are_near_duplicates(
                token_sets[first],
                second_tokens,
                policy=selected,
            ):
                union(first, second)
        if second_tokens:
            for token in second_tokens:
                postings.setdefault(token, set()).add(second)
        else:
            empty_indexes.append(second)

    grouped: dict[int, list[EvidenceT]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append(row)
    return tuple(
        tuple(grouped[root])
        for root in sorted(grouped, key=lambda value: grouped[value][0].video_id)
    )


def collapse_near_duplicate_evidence[EvidenceT: TitleEvidence](
    evidence: Sequence[EvidenceT],
    *,
    policy: EvidenceQualityPolicy | None = None,
) -> tuple[EvidenceT, ...]:
    """Credit at most one deterministic representative per copied-title family."""

    families = title_family_groups(evidence, policy=policy)
    return tuple(
        min(family, key=lambda item: (item.upload_date, item.video_id)) for family in families
    )


def assess_evidence_quality[EvidenceT: TitleEvidence](
    evidence: Sequence[EvidenceT],
    *,
    policy: EvidenceQualityPolicy | None = None,
) -> EvidenceQualityAssessment:
    selected = policy or EvidenceQualityPolicy()
    representatives = collapse_near_duplicate_evidence(evidence, policy=selected)
    identities: list[tuple[str, str]] = []
    for row in representatives:
        identity = infer_microtopic_identity_v8(
            MicrotopicDocument(
                id=row.video_id,
                title=row.title,
                description="",
                entities=(),
            )
        )
        if identity is not None:
            identities.append(
                (
                    topic_key_v8(identity),
                    f"{identity.primary_entity} — {identity.workflow_context}",
                )
            )
    counts = Counter(key for key, _label in identities)
    dominant_key = None
    dominant_label = None
    dominant_count = 0
    if counts:
        dominant_key, dominant_count = min(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        dominant_label = next(label for key, label in identities if key == dominant_key)
    identity_share = dominant_count / max(len(representatives), 1)
    reasons: list[str] = []
    if len(representatives) < selected.minimum_title_families:
        reasons.append("insufficient_independent_title_families")
    if dominant_count < selected.minimum_concrete_identity_videos:
        reasons.append("insufficient_concrete_identity_evidence")
    if identity_share < selected.minimum_concrete_identity_share:
        reasons.append("inconsistent_concrete_identity")
    return EvidenceQualityAssessment(
        accepted=not reasons,
        reason_codes=tuple(reasons) if reasons else ("quality_gate_passed",),
        raw_video_count=len(evidence),
        independent_video_count=len(representatives),
        independent_channel_count=len({row.channel_id for row in representatives}),
        title_family_count=len(representatives),
        dominant_identity_key=dominant_key,
        dominant_identity_label=dominant_label,
        dominant_identity_videos=dominant_count,
        concrete_identity_share=round(identity_share, 6),
        representative_video_ids=tuple(row.video_id for row in representatives),
    )


def assess_evidence_release[EvidenceT: TitleEvidence](
    evidence: Sequence[EvidenceT],
    *,
    policy: EvidenceReleasePolicy | None = None,
) -> EvidenceReleaseAssessment:
    """Pre-audit evidence without changing or endorsing an adoption score.

    Passing means only that the evidence is diverse and concrete enough to send
    to the Taxonomist and Skeptic. It never makes a candidate user-visible by
    itself.
    """

    selected = policy or EvidenceReleasePolicy()
    family_policy = EvidenceQualityPolicy(
        near_duplicate_jaccard=selected.near_duplicate_jaccard,
        near_duplicate_containment=selected.near_duplicate_containment,
        minimum_title_families=selected.minimum_title_families,
        minimum_concrete_identity_videos=0,
        minimum_concrete_identity_share=0,
    )
    representatives = collapse_near_duplicate_evidence(evidence, policy=family_policy)
    anchors = Counter(
        concept for row in representatives for concept in _release_anchor_concepts(row.title)
    )
    shared_anchors = tuple(
        sorted(
            concept
            for concept, count in anchors.items()
            if count >= selected.minimum_anchor_families
        )
    )
    strongest_anchor_count = max(anchors.values(), default=0)
    independent_channels = len({row.channel_id for row in representatives})
    non_english_count = sum(_looks_non_english(row.title) for row in representatives)
    non_english_share = non_english_count / max(len(representatives), 1)
    reasons: list[str] = []
    if len(representatives) < selected.minimum_title_families:
        reasons.append("insufficient_independent_title_families")
    if independent_channels < selected.minimum_independent_channels:
        reasons.append("insufficient_independent_channels")
    if strongest_anchor_count < selected.minimum_anchor_families:
        reasons.append("no_shared_concrete_anchor")
    if non_english_share > selected.maximum_non_english_share:
        reasons.append("non_english_evidence_majority")
    return EvidenceReleaseAssessment(
        pre_audit_passed=not reasons,
        reason_codes=tuple(reasons) if reasons else ("eligible_for_taxonomist_and_skeptic",),
        raw_video_count=len(evidence),
        title_family_count=len(representatives),
        independent_channel_count=independent_channels,
        shared_anchor_concepts=shared_anchors,
        strongest_anchor_family_count=strongest_anchor_count,
        non_english_family_count=non_english_count,
        non_english_share=round(non_english_share, 6),
        representative_video_ids=tuple(row.video_id for row in representatives),
    )


__all__ = [
    "COPY_RESISTANT_EVIDENCE_POLICY",
    "EvidenceQualityAssessment",
    "EvidenceQualityPolicy",
    "EvidenceReleaseAssessment",
    "EvidenceReleasePolicy",
    "assess_evidence_release",
    "assess_evidence_quality",
    "collapse_near_duplicate_evidence",
    "normalized_title_tokens",
    "title_family_groups",
    "titles_are_near_duplicates",
]
