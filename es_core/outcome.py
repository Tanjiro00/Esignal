"""Frozen outcome definitions.

The adoption rule is carried over unchanged from the v1 replay that produced the
first real signal, with one correction: "new channels" are counted against the
panel as it was frozen at ``t0``. In v1 the comparison set was the channels the
system monitors *today*, which is the survivorship bias its own verdict flagged.

Copy families are collapsed before counting, so a template reposted by eight
accounts is one piece of evidence rather than eight.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from es_core.anchors import BackgroundCorpus
from es_core.evidence import EvidencePolicy, copy_families
from es_core.types import Video, sorted_videos


@dataclass(frozen=True, slots=True)
class AdoptionPolicy:
    horizon_days: int = 42
    minimum_future_families: int = 4
    supply_growth: float = 1.25
    expected_supply_floor: float = 2.0
    minimum_new_channels: int = 2
    minimum_new_channel_share: float = 0.40


@dataclass(frozen=True, slots=True)
class AdoptionOutcome:
    fired: bool
    fired_at: datetime | None
    lead_days: float | None
    future_family_count: int
    expected_supply: float
    new_channel_count: int
    new_channel_share: float
    credited_video_ids: tuple[str, ...]


def evaluate_adoption(
    *,
    as_of: datetime,
    prior_channel_ids: frozenset[str],
    previous_28d_video_count: int,
    future_videos: Sequence[Video],
    corpus: BackgroundCorpus,
    panel_at_t0: frozenset[str] | None = None,
    policy: AdoptionPolicy | None = None,
    evidence_policy: EvidencePolicy | None = None,
) -> AdoptionOutcome:
    """Decide whether a topic was adopted by additional independent creators."""

    active = policy or AdoptionPolicy()
    horizon = as_of + timedelta(days=active.horizon_days)
    eligible = tuple(
        video
        for video in sorted_videos(future_videos)
        if as_of < video.published_at <= horizon
        and (panel_at_t0 is None or video.channel_id in panel_at_t0)
    )
    families = copy_families(eligible, corpus, policy=evidence_policy or EvidencePolicy())
    heads = tuple(family[0] for family in families)

    expected = max(previous_28d_video_count / 4 * 6, active.expected_supply_floor)
    required = max(
        active.minimum_future_families,
        int(-(-expected * active.supply_growth // 1)),  # ceil without importing math
    )

    fired_at: datetime | None = None
    for index in range(len(heads)):
        prefix = heads[: index + 1]
        new_channels = {video.channel_id for video in prefix} - prior_channel_ids
        share = sum(video.channel_id in new_channels for video in prefix) / len(prefix)
        if (
            len(prefix) >= required
            and len(new_channels) >= active.minimum_new_channels
            and share >= active.minimum_new_channel_share
        ):
            fired_at = prefix[-1].published_at
            break

    final_new = {video.channel_id for video in heads} - prior_channel_ids
    final_share = (
        sum(video.channel_id in final_new for video in heads) / len(heads) if heads else 0.0
    )
    return AdoptionOutcome(
        fired=fired_at is not None,
        fired_at=fired_at,
        lead_days=(round((fired_at - as_of).total_seconds() / 86_400, 3) if fired_at else None),
        future_family_count=len(heads),
        expected_supply=round(expected, 3),
        new_channel_count=len(final_new),
        new_channel_share=round(final_share, 6),
        credited_video_ids=tuple(video.video_id for video in heads),
    )


@dataclass(frozen=True, slots=True)
class DemandGapPolicy:
    horizon_days: int = 21
    minimum_supported_videos: int = 3
    minimum_median_lift: float = 0.405
    """Log-ratio threshold; 0.405 is 1.5x the channel's usual result."""


@dataclass(frozen=True, slots=True)
class DemandGapOutcome:
    fired: bool
    median_lift: float | None
    supported_videos: int
    future_video_count: int
    early_lift: float | None
    late_lift: float | None
    credited_video_ids: tuple[str, ...]

    @property
    def saturating(self) -> bool:
        """Later videos doing worse than earlier ones: supply is catching up."""

        if self.early_lift is None or self.late_lift is None:
            return False
        return self.late_lift < self.early_lift - 0.2


def evaluate_demand_gap(
    *,
    as_of: datetime,
    future_videos: Sequence[Video],
    lift_of: Callable[[Video], float | None],
    policy: DemandGapPolicy | None = None,
) -> DemandGapOutcome:
    """Did videos published on this topic outperform their own channels?

    This is the creator-relevant outcome: attention exceeding coverage. It is
    deliberately independent of how many other creators joined in — adoption by
    others is competition, not payoff.
    """

    active = policy or DemandGapPolicy()
    horizon = as_of + timedelta(days=active.horizon_days)
    eligible = tuple(
        video for video in sorted_videos(future_videos) if as_of < video.published_at <= horizon
    )
    scored = [(video, lift_of(video)) for video in eligible]
    supported = [(video, value) for video, value in scored if value is not None]
    if not supported:
        return DemandGapOutcome(False, None, 0, len(eligible), None, None, ())

    values = [value for _, value in supported]
    median = _median(values)
    half = max(1, len(supported) // 2)
    early = _median([value for _, value in supported[:half]])
    late = _median([value for _, value in supported[-half:]])
    return DemandGapOutcome(
        fired=(
            len(supported) >= active.minimum_supported_videos
            and median >= active.minimum_median_lift
        ),
        median_lift=round(median, 6),
        supported_videos=len(supported),
        future_video_count=len(eligible),
        early_lift=round(early, 6),
        late_lift=round(late, 6),
        credited_video_ids=tuple(video.video_id for video, _ in supported),
    )


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


__all__ = [
    "AdoptionOutcome",
    "AdoptionPolicy",
    "DemandGapOutcome",
    "DemandGapPolicy",
    "evaluate_adoption",
    "evaluate_demand_gap",
]
