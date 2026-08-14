"""Loading a point-in-time dataset for replay.

The loader keeps event time and observation time separate. `observed_at` comes
from `youtube_videos.first_discovered_at` — when the crawler actually saw the
upload — which is the only defensible basis for a historical replay. The v1
runs used publication time as if it were observation time; on this database that
is wrong for roughly two thirds of the rows, because the pre-July history was
backfilled from channel back-catalogs in July and August 2026.
"""

from __future__ import annotations

import base64
import csv
import gzip
import json
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from es_core.types import Video


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def load_discovery(path: Path) -> dict[str, datetime]:
    """video_id -> first observation time, exported from production."""

    discovered: dict[str, datetime] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) >= 4 and row[3]:
                discovered[row[0]] = _parse(row[3])
    return discovered


def load_videos(
    cohort_path: Path,
    discovery: dict[str, datetime],
    *,
    treat_publication_as_observation: bool = False,
) -> tuple[Video, ...]:
    """Read the exported cohort, attaching real observation times.

    With ``treat_publication_as_observation`` the loader reproduces the v1
    assumption, which is useful only for comparing algorithms on identical
    inputs — never for claiming predictive validity.
    """

    opener = gzip.open if cohort_path.suffix == ".gz" else open
    videos: list[Video] = []
    with opener(cohort_path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            video_id = str(row["video_id"])
            published = _parse(str(row["upload_date"]))
            if treat_publication_as_observation:
                observed = published
            else:
                observed = discovery.get(video_id)
                if observed is None:
                    continue
            videos.append(
                Video(
                    video_id=video_id,
                    channel_id=str(row["channel_id"]),
                    title=str(row["title"]),
                    published_at=published,
                    discovered_at=observed,
                    description=str(row.get("description") or "")[:800],
                )
            )
    return tuple(sorted(videos, key=lambda video: (video.published_at, video.video_id)))


def load_embeddings(path: Path) -> dict[str, tuple[float, ...]]:
    """Decode the base64 float32 cache written by the embedding job."""

    vectors: dict[str, tuple[float, ...]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            raw = base64.b64decode(str(row["embedding_base64"]))
            dimensions = int(row["dimensions"])
            values = struct.unpack(f"<{dimensions}f", raw)
            vectors[str(row["video_id"])] = values
    return vectors


@dataclass(frozen=True, slots=True)
class Dataset:
    videos: tuple[Video, ...]
    embeddings: dict[str, tuple[float, ...]]

    @property
    def embedded(self) -> tuple[Video, ...]:
        return tuple(video for video in self.videos if video.video_id in self.embeddings)

    def observable(self, as_of: datetime) -> Iterator[Video]:
        for video in self.videos:
            if video.observable_at(as_of):
                yield video


def load(
    *,
    cohort: Path,
    embeddings: Path,
    discovery: Path,
    treat_publication_as_observation: bool = False,
) -> Dataset:
    discovered = load_discovery(discovery)
    return Dataset(
        videos=load_videos(
            cohort,
            discovered,
            treat_publication_as_observation=treat_publication_as_observation,
        ),
        embeddings=load_embeddings(embeddings),
    )


__all__ = ["Dataset", "load", "load_discovery", "load_embeddings", "load_videos"]
