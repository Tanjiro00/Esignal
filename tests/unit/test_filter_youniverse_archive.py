import io
import json

import pytest

from scripts.filter_youniverse_archive import (
    filter_ai_metadata,
    filter_channel_baselines,
    filter_channel_table,
    filter_grouped_metadata,
)


def _record(
    video_id: str,
    channel_id: str,
    title: str,
    upload_date: str,
) -> str:
    return json.dumps(
        {
            "display_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "description": "",
            "tags": [],
            "categories": "Science & Technology",
            "upload_date": upload_date,
            "crawl_date": "2019-11-02 00:00:00",
            "view_count": 100,
        }
    )


def test_filter_writes_physically_separate_train_and_holdout_rows() -> None:
    train = io.StringIO()
    holdout = io.StringIO()
    stats, train_channels, holdout_channels = filter_ai_metadata(
        [
            _record("train", "c1", "TensorFlow release", "2018-01-01 00:00:00"),
            _record("holdout", "c2", "BERT research paper", "2019-05-01 00:00:00"),
            _record("reject", "c3", "Thailand travel trail", "2019-05-01 00:00:00"),
        ],
        train_output=train,
        holdout_output=holdout,
    )

    assert '"video_id":"train"' in train.getvalue()
    assert '"video_id":"holdout"' not in train.getvalue()
    assert '"video_id":"holdout"' in holdout.getvalue()
    assert train_channels == {"c1"}
    assert holdout_channels == {"c2"}
    assert stats["accepted_ai_records_all_dates"] == 2


def test_baseline_filter_keeps_all_videos_for_ai_channels() -> None:
    train = io.StringIO()
    holdout = io.StringIO()
    stats = filter_channel_baselines(
        [
            _record("ordinary", "c1", "A normal upload", "2018-01-01 00:00:00"),
            _record("other", "c9", "Unrelated", "2018-01-01 00:00:00"),
        ],
        train_channels={"c1"},
        holdout_channels=set(),
        train_output=train,
        holdout_output=holdout,
    )

    assert '"video_id":"ordinary"' in train.getvalue()
    assert '"video_id":"other"' not in train.getvalue()
    assert stats["train_baseline_records"] == 1


def test_baseline_fast_channel_scan_falls_back_for_compact_json() -> None:
    train = io.StringIO()
    compact = json.dumps(
        json.loads(_record("ordinary", "c1", "Normal", "2018-01-01 00:00:00")),
        separators=(",", ":"),
    )

    stats = filter_channel_baselines(
        [compact, "not json"],
        train_channels={"c1"},
        holdout_channels=set(),
        train_output=train,
        holdout_output=io.StringIO(),
    )

    assert '"video_id":"ordinary"' in train.getvalue()
    assert stats["invalid_records"] == 1


def test_channel_table_filter_preserves_header_and_selected_rows() -> None:
    train = io.StringIO()
    holdout = io.StringIO()
    stats = filter_channel_table(
        ["channel\tdatetime\tsubs\n", "c1\t2018-01-01\t1000\n", "c2\t2018-01-01\t2000\n"],
        train_channels={"c1"},
        holdout_channels={"c2"},
        train_output=train,
        holdout_output=holdout,
    )

    assert "c1" in train.getvalue()
    assert "c2" not in train.getvalue()
    assert "c2" in holdout.getvalue()
    assert stats == {"train_channel_rows": 1, "holdout_channel_rows_sealed": 1}


def test_channel_table_filter_supports_channel_column_after_other_fields() -> None:
    train = io.StringIO()

    filter_channel_table(
        ["category\tjoined\tchannel\tname\n", "Tech\t2018-01-01\tc1\tCreator\n"],
        train_channels={"c1"},
        holdout_channels=set(),
        train_output=train,
        holdout_output=io.StringIO(),
    )

    assert train.getvalue() == ("category\tjoined\tchannel\tname\nTech\t2018-01-01\tc1\tCreator\n")


def test_grouped_filter_extracts_ai_and_ordinary_baselines_in_one_pass() -> None:
    train_ai = io.StringIO()
    holdout_ai = io.StringIO()
    train_baseline = io.StringIO()
    holdout_baseline = io.StringIO()
    stats, train_channels, holdout_channels = filter_grouped_metadata(
        [
            _record("ordinary-c1", "c1", "Ordinary upload", "2018-01-01 00:00:00"),
            _record("ai-c1", "c1", "TensorFlow released", "2018-02-01 00:00:00"),
            _record("ordinary-c2", "c2", "Ordinary upload", "2019-01-01 00:00:00"),
            _record("ai-c2", "c2", "BERT research paper", "2019-02-01 00:00:00"),
        ],
        train_ai_output=train_ai,
        holdout_ai_output=holdout_ai,
        train_baseline_output=train_baseline,
        holdout_baseline_output=holdout_baseline,
    )

    assert '"video_id":"ai-c1"' in train_ai.getvalue()
    assert '"video_id":"ordinary-c1"' in train_baseline.getvalue()
    assert '"video_id":"ai-c2"' in holdout_ai.getvalue()
    assert '"video_id":"ordinary-c2"' in holdout_baseline.getvalue()
    assert train_channels == {"c1"}
    assert holdout_channels == {"c2"}
    assert stats["channel_runs"] == 2


def test_grouped_filter_rejects_non_contiguous_channel_runs() -> None:
    with pytest.raises(ValueError, match="not contiguous"):
        filter_grouped_metadata(
            [
                _record("one", "c1", "Ordinary", "2018-01-01 00:00:00"),
                _record("two", "c2", "Ordinary", "2018-01-01 00:00:00"),
                _record("three", "c1", "Ordinary", "2018-01-01 00:00:00"),
            ],
            train_ai_output=io.StringIO(),
            holdout_ai_output=io.StringIO(),
            train_baseline_output=io.StringIO(),
            holdout_baseline_output=io.StringIO(),
        )
