"""Anchor extraction: what a topic is actually about, learned from the corpus.

This replaces `packages/clustering/semantic.py` (25 hardcoded brands) and the
several hundred hand-written noise words in `packages/clustering/*`. Three
corpus statistics do the same job without any domain knowledge in the code:

* **lift** — how much more this term concentrates in the cluster than in the
  panel background. Generic words concentrate no more than chance.
* **idf** — how rare the term is across the panel. "tutorial" and "best" score
  low automatically, so no stop list is needed or written.
* **novelty** — how recently the term first appeared anywhere in the panel.
  This is what makes brand-new products recognizable on day one: an unknown
  tool name is precisely a term with a very recent first-seen date and a high
  lift, and it needs no prior registration to stand out.

Every statistic is computed from documents observable at the checkpoint, so the
extractor is safe to run inside a point-in-time replay.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from es_core.text import terms
from es_core.types import Anchor, Video


@dataclass(frozen=True, slots=True)
class AnchorPolicy:
    background_days: int = 365
    novelty_weight: float = 1.0
    minimum_channel_support: int = 2
    minimum_anchor_score: float = 1.5
    maximum_anchors: int = 3
    maximum_background_share: float = 0.10
    """A term present in more than this share of the panel cannot anchor a topic."""
    minimum_component_idf: float = 4.0
    """Every token of a multi-word anchor must clear this idf.

    Without it the extractor rewards rare *fragments* of common phrases —
    production data produced anchors like "memory for" and "court over", where
    the bigram is rare but half of it is a function word.

    The threshold is measured, not guessed. On the 2026-08-09 panel snapshot
    (35,871 titles): "for" idf 3.40, "claude" 4.04, "openai" 5.45, "studio"
    6.25, "ecc" 10.39. A floor of 4.0 removes function words while keeping
    product names. Capitalization was tested as an alternative signal and
    rejected: YouTube titles are Title Case, so "away" is capitalized in 77% of
    its occurrences and carries no proper-noun information.

    Some surviving anchors still read awkwardly ("away its" — both tokens are
    genuinely rare). That is a naming problem, not a detection problem: the
    anchor's job is to prove the cluster is about something specific, and the
    user-facing label comes from the evidence-grounded Taxonomist.
    """


@dataclass(frozen=True, slots=True)
class TermStats:
    document_frequency: int
    first_seen_at: datetime


class BackgroundCorpus:
    """Panel-wide term statistics as of one checkpoint.

    Built only from documents whose ``published_at`` is inside the background
    window and not after ``as_of``; nothing from the future can enter.
    """

    def __init__(self, as_of: datetime, stats: dict[str, TermStats], document_count: int) -> None:
        self.as_of = as_of
        self._stats = stats
        self.document_count = document_count

    @classmethod
    def build(
        cls,
        videos: Iterable[Video],
        *,
        as_of: datetime,
        policy: AnchorPolicy | None = None,
    ) -> BackgroundCorpus:
        return cls.from_documents(
            ((video.title, video.published_at) for video in videos if video.observable_at(as_of)),
            as_of=as_of,
            policy=policy,
        )

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[tuple[str, datetime]],
        *,
        as_of: datetime,
        policy: AnchorPolicy | None = None,
    ) -> BackgroundCorpus:
        """Term statistics over any dated text — titles, comments, posts.

        The same statistics that separate a product name from a generic word in
        video titles do the job for comments: "is it free" is made of terms
        everyone uses, while "consistent character" is not.
        """

        active = policy or AnchorPolicy()
        floor = as_of - timedelta(days=active.background_days)
        stats: dict[str, TermStats] = {}
        document_count = 0
        for text, at in documents:
            if at > as_of or at < floor:
                continue
            document_count += 1
            for term in set(terms(text)):
                current = stats.get(term)
                if current is None:
                    stats[term] = TermStats(1, at)
                else:
                    stats[term] = TermStats(
                        current.document_frequency + 1,
                        min(current.first_seen_at, at),
                    )
        return cls(as_of, stats, document_count)

    def document_frequency(self, term: str) -> int:
        entry = self._stats.get(term)
        return entry.document_frequency if entry else 0

    def idf(self, term: str) -> float:
        """Smoothed inverse document frequency; unseen terms get the maximum."""

        return math.log((self.document_count + 1) / (self.document_frequency(term) + 1)) + 1.0

    def background_share(self, term: str) -> float:
        """Add-half smoothed share, so an unseen term does not imply infinite lift."""

        if self.document_count == 0:
            return 0.0
        return (self.document_frequency(term) + 0.5) / (self.document_count + 0.5)

    def novelty(self, term: str) -> float:
        """1.0 for a term first seen today, decaying with the log of its age."""

        entry = self._stats.get(term)
        if entry is None:
            return 1.0
        age_days = max((self.as_of - entry.first_seen_at).total_seconds() / 86_400, 0.0)
        return 1.0 / math.log(math.e + age_days)

    def first_seen_at(self, term: str) -> datetime | None:
        entry = self._stats.get(term)
        return entry.first_seen_at if entry else None


class AnchorExtractor:
    def __init__(
        self,
        corpus: BackgroundCorpus,
        *,
        policy: AnchorPolicy | None = None,
    ) -> None:
        self.corpus = corpus
        self.policy = policy or AnchorPolicy()

    def score(self, term: str, *, cluster_share: float) -> float:
        lift = cluster_share / self.corpus.background_share(term)
        idf = self.corpus.idf(term)
        novelty = self.corpus.novelty(term)
        return math.log1p(max(lift, 0.0)) * idf * (1.0 + self.policy.novelty_weight * novelty)

    def _names_something(self, term: str) -> bool:
        """Reject multi-word terms whose components are individually common."""

        parts = term.split()
        if len(parts) < 2:
            return True
        return all(self.corpus.idf(part) >= self.policy.minimum_component_idf for part in parts)

    def extract(self, members: Sequence[Video]) -> tuple[Anchor, ...]:
        """Rank the cluster's terms and return the strongest supported anchors."""

        return self.extract_documents([(video.title, video.channel_id) for video in members])

    def extract_documents(self, documents: Sequence[tuple[str, str]]) -> tuple[Anchor, ...]:
        """Anchors for any grouped text: (text, independence key) pairs.

        The independence key is whatever makes two pieces of evidence count
        separately — a channel for videos, a channel or asker for comments.
        """

        if not documents:
            return ()
        members = documents
        document_hits: Counter[str] = Counter()
        channel_hits: dict[str, set[str]] = {}
        for text, support_key in documents:
            for term in set(terms(text)):
                document_hits[term] += 1
                channel_hits.setdefault(term, set()).add(support_key)

        scored: list[Anchor] = []
        for term, hits in document_hits.items():
            support = len(channel_hits[term])
            if support < self.policy.minimum_channel_support:
                continue
            if self.corpus.background_share(term) > self.policy.maximum_background_share:
                continue
            if not self._names_something(term):
                continue
            cluster_share = hits / len(members)
            background = self.corpus.background_share(term)
            scored.append(
                Anchor(
                    term=term,
                    score=round(self.score(term, cluster_share=cluster_share), 6),
                    lift=round(cluster_share / background, 6),
                    idf=round(self.corpus.idf(term), 6),
                    novelty=round(self.corpus.novelty(term), 6),
                    channel_support=support,
                )
            )
        ranked = sorted(scored, key=lambda anchor: (-anchor.score, anchor.term))
        return tuple(self._deduplicate(ranked)[: self.policy.maximum_anchors])

    @staticmethod
    def _deduplicate(anchors: Sequence[Anchor]) -> list[Anchor]:
        """Drop unigrams already carried by a higher-ranked bigram."""

        kept: list[Anchor] = []
        covered: set[str] = set()
        for anchor in anchors:
            parts = set(anchor.term.split())
            if parts & covered and len(parts) == 1:
                continue
            kept.append(anchor)
            covered |= parts
        return kept

    def anchored(self, anchors: Sequence[Anchor]) -> bool:
        """Whether the cluster is about something specific enough to publish."""

        return any(anchor.score >= self.policy.minimum_anchor_score for anchor in anchors)


__all__ = [
    "AnchorExtractor",
    "AnchorPolicy",
    "BackgroundCorpus",
    "TermStats",
]
