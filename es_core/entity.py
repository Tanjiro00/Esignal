"""Entities: the unit the product should actually track.

A cluster of two videos is not a thing in the world — it is a coincidence of
wording. The thing in the world is an *entity*: a product, a model, a project,
an event. Entities are what have release dates, GitHub repositories, Hacker News
threads and, eventually, YouTube videos.

Making the entity the unit of prediction fixes three problems at once:

* identity becomes trivial and stable — "ECC" is one entity across every
  checkpoint and every source, instead of a new cluster hash each week;
* evidence from different platforms can be joined, because they share the name;
* phrase fragments are filtered out for free — nobody registers a repository or
  writes a headline called "away its".

Promotion is evidence-based, not vocabulary-based: a term becomes an entity when
something outside YouTube *names* it — a repository name or a story headline —
rather than merely containing it in running text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

STRUCTURAL_POSITIONS = frozenset({"title", "name"})


@dataclass(frozen=True, slots=True)
class EntityEvidence:
    source: str
    at: datetime
    weight: float
    position: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class Entity:
    term: str
    first_named_at: datetime | None
    sources: tuple[str, ...]
    structural_mentions: int
    incidental_mentions: int
    evidence: tuple[EntityEvidence, ...]

    @property
    def confirmed(self) -> bool:
        """Named by at least one source outside YouTube."""

        return self.structural_mentions >= 1

    @property
    def corroborated(self) -> bool:
        """Named by two independent sources — the strongest cheap signal."""

        return (
            len({item.source for item in self.evidence if item.position in STRUCTURAL_POSITIONS})
            >= 2
        )

    def momentum(self, *, as_of: datetime, window_days: int = 30) -> float:
        """Weighted upstream activity in the window before the checkpoint."""

        floor = as_of - timedelta(days=window_days)
        return round(
            sum(item.weight for item in self.evidence if floor <= item.at <= as_of),
            6,
        )

    def lead_days(self, first_video_at: datetime) -> float | None:
        """How long the entity existed upstream before the first video."""

        if self.first_named_at is None:
            return None
        return round((first_video_at - self.first_named_at).total_seconds() / 86_400, 3)


def resolve(
    term: str,
    mentions: Sequence[EntityEvidence],
    *,
    as_of: datetime | None = None,
) -> Entity:
    """Build the entity view of a term from dated upstream evidence."""

    visible = tuple(mention for mention in mentions if as_of is None or mention.at <= as_of)
    structural = [item for item in visible if item.position in STRUCTURAL_POSITIONS]
    return Entity(
        term=term,
        first_named_at=min((item.at for item in structural), default=None),
        sources=tuple(sorted({item.source for item in visible})),
        structural_mentions=len(structural),
        incidental_mentions=len(visible) - len(structural),
        evidence=tuple(sorted(visible, key=lambda item: item.at)),
    )


__all__ = ["Entity", "EntityEvidence", "STRUCTURAL_POSITIONS", "resolve"]
