import json
from dataclasses import fields

from packages.backtest.youniverse import (
    StructuralVideo,
    detect_historical_ai_anchor,
    is_historical_ai_title,
    parse_youniverse_record,
    split_candidate_and_outcome,
)


def test_historical_admission_is_title_only_and_token_aware() -> None:
    assert detect_historical_ai_anchor("TensorFlow neural network tutorial") == "neural_network"
    assert detect_historical_ai_anchor("BERT for NLP") == "bert"
    assert is_historical_ai_title("A.I. safety and ethics") is True
    assert is_historical_ai_title("A beautiful trail in Thailand") is False
    assert is_historical_ai_title("Bert and Ernie compilation") is False
    assert is_historical_ai_title("Data science project") is False


def test_adapter_separates_final_engagement_from_candidate_fields() -> None:
    row = parse_youniverse_record(
        json.dumps(
            {
                "display_id": "abc123",
                "channel_id": "channel-1",
                "title": "TensorFlow 2 released",
                "description": "AI framework",
                "tags": ["AI", "code"],
                "categories": "Science & Technology",
                "upload_date": "2019-01-02 00:00:00",
                "crawl_date": "2019-11-02 09:01:05.328421",
                "view_count": 125000,
                "like_count": 4000,
                "dislike_count": 12,
            }
        )
    )

    structural, outcome = split_candidate_and_outcome(row)

    assert structural.video_id == "abc123"
    assert outcome.final_view_count == 125000
    assert "final_view_count" not in {field.name for field in fields(StructuralVideo)}
    assert outcome.exposure_age_days > 0


def test_adapter_keeps_video_when_optional_engagement_is_nan() -> None:
    row = parse_youniverse_record(
        json.dumps(
            {
                "display_id": "nan-video",
                "channel_id": "channel-1",
                "title": "BERT research result",
                "upload_date": "2019-01-02",
                "crawl_date": "2019-11-02",
                "view_count": 100,
                "like_count": float("nan"),
                "dislike_count": None,
            }
        )
    )

    assert row.final_view_count == 100
    assert row.final_like_count == 0


def test_adapter_reads_provenance_preserving_filtered_engagement_fields() -> None:
    row = parse_youniverse_record(
        json.dumps(
            {
                "video_id": "filtered-video",
                "channel_id": "channel-1",
                "title": "TensorFlow release",
                "upload_date": "2019-01-02",
                "crawl_date": "2019-11-02",
                "final_view_count": 125000,
                "final_like_count": 4000,
                "final_dislike_count": 12,
            }
        )
    )

    assert row.final_view_count == 125000
    assert row.final_like_count == 4000
    assert row.final_dislike_count == 12
