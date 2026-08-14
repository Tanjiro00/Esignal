from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

from packages.backtest.global_trending import (
    FILTERED_FIELDNAMES,
    filter_global_rows,
    iter_filtered_observations,
)

SOURCE_FIELDS = (
    "collection_date",
    "region_code",
    "rank",
    "video_id",
    "title",
    "description",
    "published_at",
    "channel_id",
    "channel_title",
    "category_id",
    "default_language",
    "default_audio_language",
    "live_broadcast_content",
    "view_count",
    "comment_count",
)


def _source() -> StringIO:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
    writer.writeheader()
    base = {
        "collection_date": "2024-01-01 00:00:00",
        "region_code": "US",
        "rank": "4",
        "published_at": "2023-12-31 12:00:00.000",
        "channel_title": "Creator",
        "category_id": "28",
        "default_language": "en",
        "default_audio_language": "en-US",
        "live_broadcast_content": "none",
        "comment_count": "2",
    }
    writer.writerow(
        {
            **base,
            "video_id": "accepted",
            "title": "GPT-4 launch explained",
            "description": "First line\nsecond line",
            "channel_id": "channel-a",
            "view_count": "100",
        }
    )
    writer.writerow(
        {
            **base,
            "video_id": "substring",
            "title": "Laine performs live",
            "description": "Not artificial intelligence",
            "channel_id": "channel-b",
            "view_count": "200",
        }
    )
    writer.writerow(
        {
            **base,
            "video_id": "category",
            "title": "ChatGPT comedy sketch",
            "description": "Entertainment",
            "channel_id": "channel-c",
            "category_id": "24",
            "view_count": "300",
        }
    )
    stream.seek(0)
    return stream


def test_stream_filter_is_csv_safe_and_token_aware() -> None:
    output = StringIO(newline="")

    stats = filter_global_rows(_source(), output)

    assert stats["row_counts"] == {
        "accepted": 1,
        "category": 1,
        "total": 3,
        "vertical": 1,
    }
    assert stats["unique_videos"] == 1
    output.seek(0)
    rows = list(csv.DictReader(output))
    assert tuple(rows[0]) == FILTERED_FIELDNAMES
    assert rows[0]["description"] == "First line second line"


def test_filtered_observation_loader_preserves_point_in_time_fields() -> None:
    output = StringIO(newline="")
    filter_global_rows(_source(), output)
    output.seek(0)

    observation = next(iter_filtered_observations(output))

    assert observation.video_id == "accepted"
    assert observation.region_code == "US"
    assert observation.channel_id == "channel-a"
    assert observation.view_count == 100
    assert observation.observed_at.isoformat() == "2024-01-01T00:00:00+00:00"


def test_modern_named_ai_products_pass_token_aware_admission() -> None:
    for title in (
        "DeepSeek changed open models",
        "Gemini 1.5 Pro benchmark",
        "Claude Code for a real codebase",
        "OpenAI Sora video test",
    ):
        source = _source()
        rows = list(csv.DictReader(source))
        rows[0]["title"] = title
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
        writer.writeheader()
        writer.writerow(rows[0])
        stream.seek(0)
        output = StringIO(newline="")

        stats = filter_global_rows(stream, output)

        assert stats["accepted_rows"] == 1


def test_high_confidence_product_can_override_platform_category() -> None:
    source = _source()
    row = next(csv.DictReader(source))
    row["title"] = "Claude Code reviewed on a real codebase"
    row["category_id"] = "24"
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
    writer.writeheader()
    writer.writerow(row)
    stream.seek(0)
    output = StringIO(newline="")

    stats = filter_global_rows(stream, output)

    assert stats["accepted_rows"] == 1


def test_declared_non_english_language_cannot_pass_ascii_fallback() -> None:
    source = _source()
    row = next(csv.DictReader(source))
    row["title"] = "J'ai demandé à ChatGPT"
    row["default_language"] = "fr"
    row["default_audio_language"] = "fr-FR"
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
    writer.writeheader()
    writer.writerow(row)
    stream.seek(0)
    output = StringIO(newline="")

    stats = filter_global_rows(stream, output)

    assert stats["accepted_rows"] == 0
    assert stats["row_counts"]["language"] == 1


def test_lowercase_foreign_ai_word_is_not_an_ai_signal() -> None:
    source = _source()
    row = next(csv.DictReader(source))
    row["title"] = "Mesazhi qe i erdhi Elvisit ja cfare i tha ai"
    row["default_language"] = ""
    row["default_audio_language"] = "en"
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SOURCE_FIELDS)
    writer.writeheader()
    writer.writerow(row)
    stream.seek(0)
    output = StringIO(newline="")

    stats = filter_global_rows(stream, output)

    assert stats["accepted_rows"] == 0
    assert stats["row_counts"]["vertical"] == 1


def test_filter_writes_a_physically_separate_train_slice() -> None:
    source_rows = list(csv.DictReader(_source()))
    early = source_rows[0]
    late = {
        **early,
        "collection_date": "2025-01-01 00:00:00",
        "video_id": "holdout-video",
    }
    source = StringIO(newline="")
    writer = csv.DictWriter(source, fieldnames=SOURCE_FIELDS)
    writer.writeheader()
    writer.writerows((early, late))
    source.seek(0)
    output = StringIO(newline="")
    train_output = StringIO(newline="")

    stats = filter_global_rows(
        source,
        output,
        train_destination=train_output,
        train_max_collection_at=datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC),
    )

    train_output.seek(0)
    train_rows = list(csv.DictReader(train_output))
    assert stats["accepted_rows"] == 2
    assert stats["train_accepted_rows"] == 1
    assert [row["video_id"] for row in train_rows] == ["accepted"]
