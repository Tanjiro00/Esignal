"""The per-channel feed.

Ranking keeps the three measurements apart to the end. They are shown as three
numbers, not folded into one: a question asked by forty people that has nothing
to do with this channel is not "medium relevance", it is high volume and no fit,
and the creator should see exactly that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from es_core.channel_profile import ChannelProfile, ProfilePolicy, covered_by
from es_core.demand_items import DemandItem


@dataclass(frozen=True, slots=True)
class FeedPolicy:
    minimum_fit: float = 0.343
    """Floor for question-to-channel fit, measured on the right distribution.

    A channel's radius is computed in video space and cannot be reused here:
    questions and video titles sit systematically further apart than two videos
    do. Measured on the 2026-08-14 panel, questions asked under a channel's own
    videos — relevant to it by construction — sit at p25 0.343 and p50 0.429,
    while questions from elsewhere sit at p25 0.296 and p50 0.376.

    The floor only removes what is plainly off-subject; ordering does the rest.
    """
    freshness_half_life_days: float = 14.0
    maximum_items: int = 20
    fit_weight: float = 0.60
    volume_weight: float = 0.25
    freshness_weight: float = 0.15


@dataclass(frozen=True, slots=True)
class FeedEntry:
    item: DemandItem
    fit: float
    volume: float
    freshness: float
    covered_by_own_videos: tuple[str, ...]
    answered_elsewhere: bool
    rank: float = 0.0

    @property
    def actionable(self) -> bool:
        return not self.covered_by_own_videos and not self.answered_elsewhere


def _percentiles(values: Sequence[float]) -> list[float]:
    """Rank-based normalization to [0, 1]; ties share their average rank."""

    if not values:
        return []
    if len(values) == 1:
        return [1.0]
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        share = (position + end) / 2 / (len(values) - 1)
        for index in range(position, end + 1):
            result[order[index]] = share
        position = end + 1
    return result


def build_feed(
    profile: ChannelProfile,
    items: Sequence[DemandItem],
    video_embeddings: Mapping[str, Sequence[float]],
    *,
    as_of: datetime,
    policy: FeedPolicy | None = None,
    profile_policy: ProfilePolicy | None = None,
) -> tuple[FeedEntry, ...]:
    """Rank demand items for one channel and mark what it has already answered.

    Components are combined as percentile ranks rather than as a product. The
    first version multiplied the raw values and was dominated by whichever had
    the widest scale — volume ranged 5–15 while fit ranged 0.35–0.55, so volume
    decided everything and every channel got nearly the same list: 56% overlap
    where random selection would give 18%. On one scale, the declared weights
    are the actual weights.
    """

    active = policy or FeedPolicy()
    entries: list[FeedEntry] = []
    for item in items:
        fit = profile.question_fit(item.centroid)
        if fit < active.minimum_fit:
            continue
        freshness = 0.5 ** (item.age_days(as_of) / active.freshness_half_life_days)
        entries.append(
            FeedEntry(
                item=item,
                fit=fit,
                volume=item.volume_score,
                freshness=round(freshness, 6),
                covered_by_own_videos=covered_by(
                    profile, item.centroid, video_embeddings, policy=profile_policy
                ),
                answered_elsewhere=item.answered,
            )
        )
    if not entries:
        return ()

    fit_rank = _percentiles([entry.fit for entry in entries])
    volume_rank = _percentiles([entry.volume for entry in entries])
    freshness_rank = _percentiles([entry.freshness for entry in entries])
    scored = [
        replace(
            entry,
            rank=round(
                active.fit_weight * fit_rank[index]
                + active.volume_weight * volume_rank[index]
                + active.freshness_weight * freshness_rank[index],
                6,
            ),
        )
        for index, entry in enumerate(entries)
    ]
    ranked = sorted(scored, key=lambda entry: (not entry.actionable, -entry.rank))
    return tuple(ranked[: active.maximum_items])


def overlap(left: Sequence[FeedEntry], right: Sequence[FeedEntry]) -> float:
    """Share of items two feeds have in common — the personalization check.

    Two different channels producing the same feed means there is no
    personalization and nothing worth paying for.
    """

    first = {entry.item.item_id for entry in left}
    second = {entry.item.item_id for entry in right}
    if not first or not second:
        return 0.0
    return round(len(first & second) / min(len(first), len(second)), 4)


def overlap_vs_chance(
    left: Sequence[FeedEntry],
    right: Sequence[FeedEntry],
    *,
    pool_size: int,
) -> float:
    """Observed overlap divided by the overlap two random feeds would show.

    A raw percentage cannot be compared across runs: drawing 20 items from a
    pool of 109 collides 18% of the time by chance, and from a pool of 50 it
    collides 40% of the time. Filtering the pool therefore *raises* raw overlap
    while personalization is unchanged or better.

    1.0 means the feeds are no more alike than chance — the target. Above 1.0
    means something shared is driving both feeds.
    """

    if pool_size <= 0 or not left or not right:
        return 0.0
    expected = min(len(left), len(right)) / pool_size
    if expected <= 0:
        return 0.0
    return round(overlap(left, right) / min(expected, 1.0), 4)


__all__ = ["FeedEntry", "FeedPolicy", "build_feed", "overlap"]
