from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TextIO

from packages.backtest.external_timeseries import _looks_english

GLOBAL_TRENDING_DATASET_VERSION = "illinois-global-youtube-trending-v1"
STRICT_AI_TECH_CATEGORIES = frozenset({"25", "26", "27", "28"})
_HIGH_CONFIDENCE_AI_PRODUCT = re.compile(
    r"(?i)(?<![\w])(?:"
    r"artificial intelligence|generative ai|ai agents?|ai models?|ai video|"
    r"machine learning|deep learning|neural networks?|"
    r"llms?|chatgpt|openai|anthropic|claude code|"
    r"gpt-?[234](?:\.5|o)?|copilot|gemini(?: ai| [0-9](?:\.[0-9])?)?|"
    r"grok(?: [123])?|deepseek|qwen|cursor ai|windsurf ai|"
    r"sora(?: ai| video)?|veo(?: ai| video| [23])?|higgsfield|"
    r"midjourney|stable diffusion|comfyui|ollama"
    r")(?![\w])"
)
_STANDALONE_ENGLISH_AI = re.compile(r"(?<![\w])(?:AI|A\.I\.)(?![\w])")
_ENTERTAINMENT_MARKERS = re.compile(
    r"(?i)(?<![\w])(?:sketch|parody|song|music video|trailer|gameplay|movie|film)(?![\w])"
)
FILTERED_FIELDNAMES = (
    "collection_date",
    "region_code",
    "rank",
    "video_id",
    "title",
    "description",
    "published_at",
    "channel_id",
    "category_id",
    "default_language",
    "default_audio_language",
    "view_count",
)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _value(row: Mapping[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def _declares_english(row: Mapping[str, str | None]) -> bool:
    languages = (
        _value(row, "default_language").lower(),
        _value(row, "default_audio_language").lower(),
    )
    return any(value == "en" or value.startswith("en-") for value in languages)


def _declares_another_language(row: Mapping[str, str | None]) -> bool:
    languages = (
        _value(row, "default_language").lower(),
        _value(row, "default_audio_language").lower(),
    )
    return any(languages) and not any(
        value == "en" or value.startswith("en-") for value in languages
    )


def row_is_strict_ai_tech(row: Mapping[str, str | None]) -> tuple[bool, str]:
    title = _value(row, "title")
    if (
        not title
        or _declares_another_language(row)
        or (not _declares_english(row) and not _looks_english(title))
    ):
        return False, "language"
    if (
        _HIGH_CONFIDENCE_AI_PRODUCT.search(title) is None
        and _STANDALONE_ENGLISH_AI.search(title) is None
    ):
        return False, "vertical"
    if _value(row, "category_id") not in STRICT_AI_TECH_CATEGORIES and (
        _HIGH_CONFIDENCE_AI_PRODUCT.search(title) is None
        or _ENTERTAINMENT_MARKERS.search(title) is not None
    ):
        return False, "category"
    if not _value(row, "video_id") or not _value(row, "channel_id"):
        return False, "identity"
    if not _value(row, "region_code"):
        return False, "malformed"
    try:
        _parse_timestamp(_value(row, "collection_date"))
        _parse_timestamp(_value(row, "published_at"))
        if int(_value(row, "rank")) < 1 or int(_value(row, "view_count")) < 0:
            return False, "malformed"
    except (TypeError, ValueError):
        return False, "malformed"
    return True, "accepted"


@dataclass(frozen=True)
class GlobalTrendingObservation:
    observed_at: datetime
    region_code: str
    rank: int
    video_id: str
    title: str
    description: str
    published_at: datetime
    channel_id: str
    category_id: str
    default_language: str
    default_audio_language: str
    view_count: int


def filter_global_rows(
    source: TextIO,
    destination: TextIO,
    *,
    train_destination: TextIO | None = None,
    train_max_collection_at: datetime | None = None,
) -> dict[str, object]:
    if (train_destination is None) != (train_max_collection_at is None):
        raise ValueError("train destination and cutoff must be provided together")
    reader = csv.DictReader(source)
    missing = set(FILTERED_FIELDNAMES) - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"global archive is missing fields: {sorted(missing)}")
    writer = csv.DictWriter(destination, fieldnames=FILTERED_FIELDNAMES)
    writer.writeheader()
    train_writer = (
        csv.DictWriter(train_destination, fieldnames=FILTERED_FIELDNAMES)
        if train_destination is not None
        else None
    )
    if train_writer is not None:
        train_writer.writeheader()
    reasons: Counter[str] = Counter()
    regions: set[str] = set()
    videos: set[str] = set()
    channels: set[str] = set()
    first_collection: str | None = None
    last_collection: str | None = None
    for row in reader:
        reasons["total"] += 1
        accepted, reason = row_is_strict_ai_tech(row)
        reasons[reason] += 1
        if not accepted:
            continue
        collection_date = _value(row, "collection_date")
        first_collection = (
            min(first_collection, collection_date) if first_collection else collection_date
        )
        last_collection = (
            max(last_collection, collection_date) if last_collection else collection_date
        )
        regions.add(_value(row, "region_code"))
        videos.add(_value(row, "video_id"))
        channels.add(_value(row, "channel_id"))
        filtered = {
            "collection_date": collection_date,
            "region_code": _value(row, "region_code"),
            "rank": _value(row, "rank"),
            "video_id": _value(row, "video_id"),
            "title": " ".join(_value(row, "title").split()),
            "description": " ".join(_value(row, "description")[:1_200].split()),
            "published_at": _value(row, "published_at"),
            "channel_id": _value(row, "channel_id"),
            "category_id": _value(row, "category_id"),
            "default_language": _value(row, "default_language"),
            "default_audio_language": _value(row, "default_audio_language"),
            "view_count": _value(row, "view_count"),
        }
        writer.writerow(filtered)
        if (
            train_writer is not None
            and train_max_collection_at is not None
            and _parse_timestamp(collection_date) <= _aware_utc(train_max_collection_at)
        ):
            train_writer.writerow(filtered)
            reasons["train_accepted"] += 1
    return {
        "dataset_version": GLOBAL_TRENDING_DATASET_VERSION,
        "row_counts": dict(sorted(reasons.items())),
        "accepted_rows": reasons["accepted"],
        "train_accepted_rows": reasons["train_accepted"],
        "unique_regions": len(regions),
        "unique_videos": len(videos),
        "unique_channels": len(channels),
        "first_collection_at": first_collection,
        "last_collection_at": last_collection,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iter_filtered_observations(source: TextIO) -> Iterator[GlobalTrendingObservation]:
    reader = csv.DictReader(source)
    missing = set(FILTERED_FIELDNAMES) - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"filtered archive is missing fields: {sorted(missing)}")
    for row in reader:
        yield GlobalTrendingObservation(
            observed_at=_parse_timestamp(row["collection_date"]),
            region_code=row["region_code"].strip(),
            rank=max(1, int(row["rank"])),
            video_id=row["video_id"].strip(),
            title=row["title"].strip(),
            description=row["description"].strip(),
            published_at=_parse_timestamp(row["published_at"]),
            channel_id=row["channel_id"].strip(),
            category_id=row["category_id"].strip(),
            default_language=row["default_language"].strip(),
            default_audio_language=row["default_audio_language"].strip(),
            view_count=max(0, int(row["view_count"] or 0)),
        )


def observations_to_rows(
    observations: Iterable[GlobalTrendingObservation],
) -> Iterator[dict[str, str | int]]:
    for row in observations:
        yield {
            "collection_date": row.observed_at.isoformat(),
            "region_code": row.region_code,
            "rank": row.rank,
            "video_id": row.video_id,
            "title": row.title,
            "description": row.description,
            "published_at": row.published_at.isoformat(),
            "channel_id": row.channel_id,
            "category_id": row.category_id,
            "default_language": row.default_language,
            "default_audio_language": row.default_audio_language,
            "view_count": row.view_count,
        }


__all__ = [
    "FILTERED_FIELDNAMES",
    "GLOBAL_TRENDING_DATASET_VERSION",
    "STRICT_AI_TECH_CATEGORIES",
    "GlobalTrendingObservation",
    "filter_global_rows",
    "iter_filtered_observations",
    "observations_to_rows",
    "row_is_strict_ai_tech",
]
