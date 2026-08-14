import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps.api.models import EvaluationLabel, SignalAction
from packages.evaluation import (
    build_evaluation_report,
    evaluation_export_records,
    feedback_export_records,
    records_as_csv,
    records_as_jsonl,
    validate_decision_reason,
)
from scripts.generate_manual_evaluation_fixture import records as fixture_records

REPO_ROOT = Path(__file__).resolve().parents[2]


def _label(
    *,
    id: str,
    topic_id: str,
    label: str,
    additional: list[str],
    signal_rank: int | None,
) -> EvaluationLabel:
    now = datetime(2026, 7, 28, 12, tzinfo=UTC)
    return EvaluationLabel(
        id=id,
        workspace_id="workspace-1",
        topic_id=topic_id,
        signal_id=f"signal-{topic_id}" if signal_rank is not None else None,
        reviewer_id="reviewer-1",
        as_of=now,
        label=label,
        additional_labels_json=additional,
        evidence_snapshot_json={
            "signal": (
                {"id": f"signal-{topic_id}", "score": 80} if signal_rank is not None else None
            ),
            "signal_rank": signal_rank or 99,
            "point_in_time": True,
        },
        notes="Expert judgment.",
        model_versions_json={"score": "v1"},
        label_version="manual-topic-evaluation-v1",
        created_at=now,
        updated_at=now,
    )


def test_decision_reason_taxonomy_is_action_specific_and_optional() -> None:
    assert validate_decision_reason("act", None) == ""
    assert validate_decision_reason("act", "clear_angle") == "clear_angle"
    assert validate_decision_reason("watch", "too_early") == "too_early"
    assert validate_decision_reason("skip", "weak_evidence") == "weak_evidence"
    with pytest.raises(ValueError):
        validate_decision_reason("act", "not_relevant")


def test_evaluation_report_and_exports_are_reproducible() -> None:
    labels = [
        _label(
            id="label-1",
            topic_id="topic-1",
            label="true_early_signal",
            additional=["demand_relevant", "opportunity_actionable", "fit_correct"],
            signal_rank=1,
        ),
        _label(
            id="label-2",
            topic_id="topic-2",
            label="false_signal",
            additional=["demand_irrelevant", "opportunity_generic", "fit_incorrect"],
            signal_rank=2,
        ),
        _label(
            id="label-3",
            topic_id="topic-3",
            label="true_early_signal",
            additional=["demand_relevant", "opportunity_actionable"],
            signal_rank=None,
        ),
    ]

    report = build_evaluation_report(labels)

    assert report["reviewed_topics"] == 3
    assert report["metrics"]["precision"] == 50
    assert report["metrics"]["recall_reviewed_candidate_universe"] == 50
    assert report["metrics"]["precision_at_3"] == 50
    assert report["metrics"]["false_positive_rate"] == 50
    assert report["metrics"]["demand_relevance_precision"] == pytest.approx(66.7)
    assert report["production_weights_changed"] is False

    records = evaluation_export_records(labels)
    assert [record["topic_id"] for record in records] == [
        "topic-1",
        "topic-2",
        "topic-3",
    ]
    assert '"topic_id": "topic-1"' in records_as_jsonl(records)
    assert "additional_labels" in records_as_csv(records)


def test_feedback_export_contains_reason_comment_and_opportunity() -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=UTC)
    action = SignalAction(
        id="action-1",
        workspace_id="workspace-1",
        signal_id="signal-1",
        user_id="user-1",
        action="act",
        reason="clear_angle",
        comment="Test it on one real project.",
        opportunity_id="opportunity-1",
        feedback_version="decision-feedback-v1",
        created_at=now,
    )
    record = feedback_export_records([action])[0]

    assert record["reason"] == "clear_angle"
    assert record["comment"] == "Test it on one real project."
    assert record["opportunity_id"] == "opportunity-1"


def test_manual_evaluation_fixture_contains_100_reproducible_point_in_time_topics() -> None:
    path = REPO_ROOT / "fixtures" / "evaluation" / "manual-topic-labels-v1.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]

    assert rows == fixture_records()
    assert len(rows) == 100
    assert len({row["topic_id"] for row in rows}) == 100
    assert set(Counter(row["label"] for row in rows).values()) == {10}
    assert all(row["evidence_snapshot"]["point_in_time"] is True for row in rows)
    assert all(row["evidence_snapshot"]["future_measurements_included"] is False for row in rows)
