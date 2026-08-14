"""Poll the panel's upload feeds.

Replaces query-driven discovery as the way new videos enter the system. The
difference matters: a search query returns what already ranks, while polling a
fixed population returns everything it published — including the videos that
went nowhere, which is what makes precision measurable at all.

Feeds are free and outside the API quota, so the whole panel fits in one daily
pass.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from apps.api.config import Settings, get_settings
from apps.api.database import SessionLocal
from apps.api.models import PanelMembership, YoutubeChannel
from apps.worker.ingestion import IngestionService
from es_ingest.panel import CrawlPolicy, Membership, coverage, plan_crawl


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def crawl(settings: Settings, *, limit: int, max_results: int, dry_run: bool) -> None:
    now = datetime.now(tz=UTC)
    with SessionLocal() as session:
        rows = session.scalars(select(PanelMembership)).all()
        memberships = [
            Membership(
                channel_id=row.channel_id,
                joined_at=_aware(row.joined_at) or now,
                reason=row.reason,  # type: ignore[arg-type]
                left_at=_aware(row.left_at),
                left_reason=row.left_reason,  # type: ignore[arg-type]
                owner_workspace_id=row.owner_workspace_id,
            )
            for row in rows
        ]
        last_polled = {
            row.channel_id: polled
            for row in rows
            if (polled := _aware(row.last_polled_at)) is not None
        }
        plan = plan_crawl(
            memberships,
            last_polled,
            as_of=now,
            policy=CrawlPolicy(daily_capacity=limit),
        )
        print(
            f"panel={len(memberships)} due={len(plan)} "
            f"coverage_24h={coverage(memberships, last_polled, as_of=now) * 100:.1f}%"
        )
        if dry_run or not plan:
            print("dry run; pass --apply to poll")
            return

        by_id = {row.channel_id: row for row in rows}
        channels = {
            channel.id: channel
            for channel in session.scalars(
                select(YoutubeChannel).where(YoutubeChannel.id.in_(plan))
            ).all()
        }
        service = IngestionService(session, settings)
        polled = 0
        retained = 0
        failures = 0
        for channel_id in plan:
            channel = channels.get(channel_id)
            if channel is None:
                continue
            try:
                result = await service.ingest_panel_channel(channel, max_results=max_results)
                retained += result.retained_video_count
            except Exception as error:  # noqa: BLE001 - one bad feed must not stop the pass
                failures += 1
                print(f"  failed {channel.youtube_channel_id}: {type(error).__name__}: {error}")
            else:
                polled += 1
                row = by_id.get(channel_id)
                if row is not None:
                    row.last_polled_at = datetime.now(tz=UTC)
                    session.commit()
            if polled and polled % 25 == 0:
                print(f"  polled {polled}/{len(plan)} retained={retained}", flush=True)

        print(f"polled={polled} failed={failures} retained_videos={retained}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--max-results", type=int, default=15)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    asyncio.run(
        crawl(
            get_settings(),
            limit=args.limit,
            max_results=args.max_results,
            dry_run=not args.apply,
        )
    )


if __name__ == "__main__":
    main()
