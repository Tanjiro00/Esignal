"""Seed and refresh the observed panel.

Reads what each channel actually published, applies the entry and exit rules
from `es_ingest.panel`, and writes the resulting dated facts. Existing rows are
never rewritten, so every run leaves the past reconstructable.

The first run turns the channels the legacy query-driven crawler happened to
find into an explicit, versioned population. From then on the panel grows by
customer neighbourhoods rather than by search queries.
"""

from __future__ import annotations

import argparse
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.database import SessionLocal
from apps.api.models import PanelMembership, YoutubeChannel, YoutubeVideo
from es_ingest.panel import (
    ChannelEvidence,
    Membership,
    PanelRules,
    coverage,
    members_at,
    reconcile,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def collect_evidence(
    session: Session,
    *,
    as_of: datetime,
    rules: PanelRules,
) -> list[ChannelEvidence]:
    """Summarize each channel from its own uploads inside the recent window."""

    floor = as_of - timedelta(days=rules.recent_window_days)
    rows = session.execute(
        select(YoutubeVideo.channel_id, YoutubeVideo.published_at).where(
            YoutubeVideo.published_at >= floor,
            YoutubeVideo.published_at <= as_of,
        )
    ).all()

    uploads: dict[str, int] = defaultdict(int)
    latest: dict[str, datetime] = {}
    for channel_id, published_at in rows:
        moment = _aware(published_at)
        if moment is None:
            continue
        uploads[channel_id] += 1
        if channel_id not in latest or moment > latest[channel_id]:
            latest[channel_id] = moment

    evidence: list[ChannelEvidence] = []
    for channel_id in session.scalars(select(YoutubeChannel.id)).all():
        evidence.append(
            ChannelEvidence(
                channel_id=channel_id,
                observed_at=as_of,
                uploads_in_window=uploads.get(channel_id, 0),
                # Everything currently stored reached us through the niche
                # crawler, so membership starts from observed activity. A
                # measured share replaces this once profiles are computed.
                niche_share=1.0 if uploads.get(channel_id, 0) else 0.0,
                last_upload_at=latest.get(channel_id),
            )
        )
    return evidence


def load_memberships(session: Session) -> list[Membership]:
    return [
        Membership(
            channel_id=row.channel_id,
            joined_at=_aware(row.joined_at) or datetime.now(tz=UTC),
            reason=row.reason,  # type: ignore[arg-type]
            left_at=_aware(row.left_at),
            left_reason=row.left_reason,  # type: ignore[arg-type]
            owner_workspace_id=row.owner_workspace_id,
        )
        for row in session.scalars(select(PanelMembership)).all()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--reason", default="seed")
    parser.add_argument("--apply", action="store_true", help="write changes")
    args = parser.parse_args()

    as_of = (
        datetime.fromisoformat(args.as_of).replace(tzinfo=UTC)
        if args.as_of
        else datetime.now(tz=UTC)
    )
    rules = PanelRules()

    with SessionLocal() as session:
        memberships = load_memberships(session)
        evidence = collect_evidence(session, as_of=as_of, rules=rules)
        changes = reconcile(
            memberships, evidence, as_of=as_of, joining_reason=args.reason, rules=rules
        )
        joining = [change for change in changes if change.joining]
        leaving = [change for change in changes if not change.joining]
        print(
            f"channels={len(evidence)} members_before={len(members_at(memberships, as_of))} "
            f"joining={len(joining)} leaving={len(leaving)}"
        )
        if not args.apply:
            print("dry run; pass --apply to write")
            return

        rows = {row.channel_id: row for row in session.scalars(select(PanelMembership)).all()}
        for change in joining:
            session.add(
                PanelMembership(
                    id=str(uuid.uuid4()),
                    channel_id=change.channel_id,
                    joined_at=change.at,
                    reason=change.reason,
                )
            )
        for change in leaving:
            row = rows.get(change.channel_id)
            if row is not None and row.left_at is None:
                row.left_at = change.at
                row.left_reason = change.reason
        session.commit()

        updated = load_memberships(session)
        polled = {
            row.channel_id: moment
            for row in session.scalars(select(PanelMembership)).all()
            if (moment := _aware(row.last_polled_at)) is not None
        }
        print(
            f"members_after={len(members_at(updated, as_of))} "
            f"poll_coverage_24h={coverage(updated, polled, as_of=as_of) * 100:.1f}%"
        )


if __name__ == "__main__":
    main()
