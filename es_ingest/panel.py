"""The panel: the population we observe, defined explicitly and versioned.

Until now the set of watched channels was whatever nine hand-written search
queries happened to return. That has two consequences the audit made concrete:
the universe cannot be reconstructed as it stood on a past date, and everything
in it arrived because it already ranked in search — so there are no negative
examples and no honest measurement.

A panel fixes both. Membership is a dated fact with a reason, so the population
on any past day can be replayed exactly, and joining is decided by rules that
look only at what was known at the time.

This module is pure: rules and scheduling, no database and no network. The
repository that persists membership and the crawler that polls feeds live
alongside it and depend on these decisions, not the other way round.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

MembershipReason = Literal[
    "seed",
    "neighbourhood",
    "topic_cooccurrence",
    "dormant",
    "off_niche",
    "template_channel",
]


@dataclass(frozen=True, slots=True)
class PanelRules:
    recent_window_days: int = 90
    minimum_recent_uploads: int = 3
    minimum_niche_share: float = 0.50
    """Share of a channel's recent uploads that must sit inside the niche."""
    dormant_days: int = 120
    exit_niche_share: float = 0.30
    """Leaving is deliberately easier than joining is hard, to avoid churn."""
    maximum_template_share: float = 0.80


@dataclass(frozen=True, slots=True)
class ChannelEvidence:
    """What was known about a channel at one moment — never anything later."""

    channel_id: str
    observed_at: datetime
    uploads_in_window: int
    niche_share: float
    last_upload_at: datetime | None
    template_share: float = 0.0

    def dormant_days(self, as_of: datetime) -> float:
        if self.last_upload_at is None:
            return float("inf")
        return (as_of - self.last_upload_at).total_seconds() / 86_400


@dataclass(frozen=True, slots=True)
class Membership:
    channel_id: str
    joined_at: datetime
    reason: MembershipReason
    left_at: datetime | None = None
    left_reason: MembershipReason | None = None
    owner_workspace_id: str | None = None
    """Whose neighbourhood brought this channel in; None for the niche core."""

    def active_at(self, as_of: datetime) -> bool:
        if self.joined_at > as_of:
            return False
        return self.left_at is None or self.left_at > as_of


@dataclass(frozen=True, slots=True)
class MembershipChange:
    channel_id: str
    at: datetime
    joining: bool
    reason: MembershipReason


def admits(evidence: ChannelEvidence, *, rules: PanelRules | None = None) -> bool:
    """Whether a channel qualifies to join, judged only on past evidence."""

    active = rules or PanelRules()
    if evidence.uploads_in_window < active.minimum_recent_uploads:
        return False
    if evidence.niche_share < active.minimum_niche_share:
        return False
    return evidence.template_share < active.maximum_template_share


def expels(
    evidence: ChannelEvidence,
    *,
    as_of: datetime,
    rules: PanelRules | None = None,
) -> MembershipReason | None:
    """Why a member should leave, or None to keep it."""

    active = rules or PanelRules()
    if evidence.dormant_days(as_of) > active.dormant_days:
        return "dormant"
    if evidence.niche_share < active.exit_niche_share:
        return "off_niche"
    if evidence.template_share >= active.maximum_template_share:
        return "template_channel"
    return None


def reconcile(
    memberships: Sequence[Membership],
    evidence: Iterable[ChannelEvidence],
    *,
    as_of: datetime,
    joining_reason: MembershipReason = "neighbourhood",
    rules: PanelRules | None = None,
) -> tuple[MembershipChange, ...]:
    """Decide today's joins and departures without mutating history."""

    active = rules or PanelRules()
    current = {membership.channel_id for membership in memberships if membership.active_at(as_of)}
    changes: list[MembershipChange] = []
    for item in evidence:
        if item.observed_at > as_of:
            raise ValueError(
                f"evidence for {item.channel_id} postdates the checkpoint {as_of.isoformat()}"
            )
        if item.channel_id in current:
            reason = expels(item, as_of=as_of, rules=active)
            if reason is not None:
                changes.append(MembershipChange(item.channel_id, as_of, False, reason))
        elif admits(item, rules=active):
            changes.append(MembershipChange(item.channel_id, as_of, True, joining_reason))
    return tuple(sorted(changes, key=lambda change: (change.channel_id, change.joining)))


def apply_changes(
    memberships: Sequence[Membership],
    changes: Sequence[MembershipChange],
) -> tuple[Membership, ...]:
    """Fold changes into membership records, keeping every past row intact."""

    result = list(memberships)
    for change in changes:
        if change.joining:
            result.append(
                Membership(
                    channel_id=change.channel_id,
                    joined_at=change.at,
                    reason=change.reason,
                )
            )
            continue
        for index, membership in enumerate(result):
            if membership.channel_id == change.channel_id and membership.left_at is None:
                result[index] = Membership(
                    channel_id=membership.channel_id,
                    joined_at=membership.joined_at,
                    reason=membership.reason,
                    left_at=change.at,
                    left_reason=change.reason,
                    owner_workspace_id=membership.owner_workspace_id,
                )
    return tuple(result)


def members_at(memberships: Sequence[Membership], as_of: datetime) -> frozenset[str]:
    """The panel exactly as it stood on a past date."""

    return frozenset(
        membership.channel_id for membership in memberships if membership.active_at(as_of)
    )


@dataclass(frozen=True, slots=True)
class CrawlPolicy:
    daily_capacity: int = 8_000
    """RSS polls per day. Free and outside the API quota, so this is generous."""
    stale_after_hours: float = 20.0
    prioritise_workspace_channels: bool = True


def plan_crawl(
    memberships: Sequence[Membership],
    last_polled: dict[str, datetime],
    *,
    as_of: datetime,
    policy: CrawlPolicy | None = None,
) -> tuple[str, ...]:
    """Order today's feed polls: never-seen first, then longest unpolled.

    A channel nobody has polled yet may be publishing the thing we exist to
    find, so it outranks a channel whose feed is merely a few hours old.
    """

    active = policy or CrawlPolicy()
    stale_before = as_of - timedelta(hours=active.stale_after_hours)
    due: list[tuple[float, int, str]] = []
    for membership in memberships:
        if not membership.active_at(as_of):
            continue
        polled = last_polled.get(membership.channel_id)
        if polled is not None and polled > stale_before:
            continue
        age = float("inf") if polled is None else (as_of - polled).total_seconds()
        owned = 0 if active.prioritise_workspace_channels and membership.owner_workspace_id else 1
        due.append((-age, owned, membership.channel_id))
    due.sort(key=lambda row: (row[1], row[0], row[2]))
    return tuple(channel_id for _, _, channel_id in due[: active.daily_capacity])


def coverage(
    memberships: Sequence[Membership],
    last_polled: dict[str, datetime],
    *,
    as_of: datetime,
    window_hours: float = 24.0,
) -> float:
    """Share of the panel polled inside the window — the etap-1 gate metric."""

    members = members_at(memberships, as_of)
    if not members:
        return 0.0
    floor = as_of - timedelta(hours=window_hours)
    fresh = sum(
        1
        for channel_id in members
        if (polled := last_polled.get(channel_id)) is not None and polled >= floor
    )
    return round(fresh / len(members), 4)


__all__ = [
    "ChannelEvidence",
    "CrawlPolicy",
    "Membership",
    "MembershipChange",
    "MembershipReason",
    "PanelRules",
    "admits",
    "apply_changes",
    "coverage",
    "expels",
    "members_at",
    "plan_crawl",
    "reconcile",
]
