from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from packages.backtest.external_timeseries import ExternalVideo, ExternalViewSnapshot

US_TRENDING_ARCHIVE_VERSION = "kaggle-rsrishav-us-v1346"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass
class _VideoBuilder:
    video_id: str
    title: str
    description: str
    channel_id: str
    category: str
    published_at: datetime
    snapshots: dict[datetime, int] = field(default_factory=dict)

    def add_snapshot(self, *, observed_at: datetime, views: int) -> None:
        self.snapshots[observed_at] = max(views, self.snapshots.get(observed_at, 0))

    def build(self) -> ExternalVideo:
        return ExternalVideo(
            video_id=self.video_id,
            title=self.title,
            description=self.description,
            channel_id=self.channel_id,
            subscriber_count=0,
            category=self.category,
            duration_seconds=None,
            published_at_override=self.published_at,
            snapshots=tuple(
                ExternalViewSnapshot(views=views, observed_at=observed_at)
                for observed_at, views in sorted(self.snapshots.items())
            ),
        )


def load_us_trending_archive(path: Path) -> list[ExternalVideo]:
    """Load the public daily US Trending CSV without using future metadata edits.

    The first row observed for a video owns its title and description. Later rows
    contribute view snapshots only, so a title edit made after a checkpoint cannot
    leak into an earlier replay.
    """

    csv.field_size_limit(16 * 1024 * 1024)
    builders: dict[str, _VideoBuilder] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            video_id = row["video_id"].strip()
            channel_id = row["channelId"].strip()
            if not video_id or not channel_id:
                continue
            observed_at = _parse_timestamp(row["trending_date"])
            builder = builders.get(video_id)
            if builder is None:
                builder = _VideoBuilder(
                    video_id=video_id,
                    title=row["title"].strip(),
                    description=row["description"].strip(),
                    channel_id=channel_id,
                    category=row["categoryId"].strip(),
                    published_at=_parse_timestamp(row["publishedAt"]),
                )
                builders[video_id] = builder
            builder.add_snapshot(observed_at=observed_at, views=max(0, int(row["view_count"])))
    return [builder.build() for builder in builders.values() if builder.snapshots]


__all__ = ["US_TRENDING_ARCHIVE_VERSION", "load_us_trending_archive"]
