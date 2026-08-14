from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIMARY_LABELS = (
    "true_early_signal",
    "true_but_late",
    "weak_signal",
    "false_signal",
    "too_broad",
    "too_narrow",
    "duplicate",
    "saturated",
    "declining",
    "insufficient_evidence",
)


def _additional(label: str) -> list[str]:
    if label == "true_early_signal":
        return ["demand_relevant", "opportunity_actionable", "fit_correct"]
    if label == "true_but_late":
        return ["demand_relevant", "opportunity_actionable", "fit_incorrect"]
    if label in {"too_broad", "duplicate", "insufficient_evidence"}:
        return ["demand_irrelevant", "opportunity_generic", "fit_incorrect"]
    return ["demand_relevant", "opportunity_generic", "fit_incorrect"]


def _prediction(label: str, index: int, *, current: bool) -> dict[str, object]:
    true_early = label == "true_early_signal"
    if current:
        visible = true_early or (label in {"weak_signal", "too_broad"} and index % 3 == 0)
        rank = 1 + index % 3 if true_early else 3
    else:
        visible = label not in {"declining", "insufficient_evidence"} or index % 2 == 0
        rank = 4 + index % 4 if true_early else 1 + index % 3
    return {
        "visible_signal": visible,
        "rank": rank if visible else None,
        "predicted_at": "2026-07-20T12:00:00Z",
    }


def records() -> list[dict[str, object]]:
    captured_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(100):
        label = PRIMARY_LABELS[index % len(PRIMARY_LABELS)]
        topic_number = index + 1
        as_of = captured_at + timedelta(minutes=index)
        rows.append(
            {
                "topic_id": f"expert-topic-{topic_number:03d}",
                "as_of": as_of.isoformat().replace("+00:00", "Z"),
                "label": label,
                "additional_labels": _additional(label),
                "reviewer": "expert-fixture-panel-v1",
                "evidence_snapshot": {
                    "topic_identity": {
                        "domain": "AI / technology",
                        "audience": "English-language AI creators",
                        "problem": f"expert-reviewed scenario {topic_number:03d}",
                    },
                    "video_ids": [
                        f"expert-video-{topic_number:03d}-1",
                        f"expert-video-{topic_number:03d}-2",
                        f"expert-video-{topic_number:03d}-3",
                    ],
                    "independent_channels": 3,
                    "measurement_at": as_of.isoformat().replace("+00:00", "Z"),
                    "point_in_time": True,
                    "future_measurements_included": False,
                },
                "notes": (
                    "Curated regression scenario; the label is fixed for repeatable "
                    "model comparison and does not mutate production data."
                ),
                "model_versions": {
                    "baseline": "live-microtopic-clustering-v4",
                    "current": "microtopic-clustering-v5",
                    "label": "manual-topic-evaluation-v1",
                },
                "predictions": {
                    "baseline": _prediction(label, index, current=False),
                    "current": _prediction(label, index, current=True),
                },
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fixtures/evaluation/manual-topic-labels-v1.jsonl"),
    )
    args = parser.parse_args()
    payload = "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(f"Wrote {len(records())} expert-labelled topic fixtures to {args.output}")


if __name__ == "__main__":
    main()
