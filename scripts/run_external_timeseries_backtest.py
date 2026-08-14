from __future__ import annotations

import argparse
import json
import pickle
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.backtest.external_timeseries import (
    EXTERNAL_REPLAY_VERSION,
    OUTCOME_VERSION,
    ExternalReplayPolicy,
    ExternalTimeseriesReplay,
    ExternalVideo,
    ExternalViewSnapshot,
    summarize_external_results,
)

EXPECTED_DATASET_SHA256 = "be74d041d5bada889015682e9d69e88f61e2b37c9b41ca7fb9adcc72ae9768f8"
CHECKPOINTS = (
    ("2024-10-14T23:59:59+00:00", "train"),
    ("2024-10-19T23:59:59+00:00", "train"),
    ("2024-10-24T23:59:59+00:00", "train"),
    ("2024-10-29T23:59:59+00:00", "train"),
    ("2024-11-03T23:59:59+00:00", "train"),
    ("2024-11-08T23:59:59+00:00", "train"),
    ("2024-11-13T23:59:59+00:00", "holdout"),
    ("2024-11-18T23:59:59+00:00", "holdout"),
)

_ALLOWED_PICKLE_GLOBALS = {
    ("builtins", "slice"),
    ("datetime", "datetime"),
    ("datetime", "timedelta"),
    ("datetime", "timezone"),
    ("numpy", "dtype"),
    ("numpy", "ndarray"),
    ("numpy._core.multiarray", "_reconstruct"),
    ("pandas._libs.internals", "_unpickle_block"),
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.base", "_new_Index"),
    ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.internals.managers", "BlockManager"),
}


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if (module, name) not in _ALLOWED_PICKLE_GLOBALS:
            raise pickle.UnpicklingError(f"blocked pickle global: {module}.{name}")
        return super().find_class(module, name)


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_dataset(path: Path) -> list[ExternalVideo]:
    with path.open("rb") as handle:
        frame = _RestrictedUnpickler(handle).load()
    videos = []
    for row in frame.to_dict(orient="records"):
        if row.get("blacklisted") is True:
            continue
        raw_snapshots = row.get("view_timeseries")
        if not isinstance(raw_snapshots, list) or not raw_snapshots:
            continue
        snapshots = tuple(
            ExternalViewSnapshot(views=int(views), observed_at=observed_at)
            for views, observed_at in sorted(raw_snapshots, key=lambda item: item[1])
        )
        duration = row.get("duration")
        videos.append(
            ExternalVideo(
                video_id=str(row["video_id"]),
                title=str(row["title"]),
                channel_id=str(row["channel_title"]),
                subscriber_count=int(row["subscribers"]),
                category=str(row["category"]),
                duration_seconds=(
                    float(duration)
                    if isinstance(duration, int | float) and duration == duration
                    else None
                ),
                snapshots=snapshots,
            )
        )
    return videos


def _checkpoint_payload(result: Any, rankings: dict[str, Any], split: str) -> dict[str, Any]:
    outcome_map = {row.topic_key: row for row in result.outcomes}
    predicted: list[dict[str, Any]] = []
    for row in result.predictions:
        outcome = outcome_map[row.topic_key]
        predicted.append(
            {
                "topic_key": row.topic_key,
                "label": row.label,
                "rank": len(predicted) + 1,
                "score": row.score,
                "fired": outcome.fired,
                "lead_days": outcome.lead_days,
                "max_supply_growth": outcome.max_supply_growth,
                "peak_lift": outcome.peak_lift,
                "video_count_72h": row.video_count_72h,
                "distinct_channels": row.distinct_channels,
                "evidence_titles": list(row.member_titles[:5]),
            }
        )
    fired_candidates: list[dict[str, Any]] = []
    state_by_key = {row.topic_key: row for method_rows in rankings.values() for row in method_rows}
    for outcome in result.outcomes:
        if not outcome.fired:
            continue
        state = state_by_key.get(outcome.topic_key)
        fired_candidates.append(
            {
                "topic_key": outcome.topic_key,
                "label": state.label if state is not None else outcome.topic_key,
                "selected_by_method": any(
                    row.topic_key == outcome.topic_key for row in result.predictions
                ),
                "lead_days": outcome.lead_days,
                "max_supply_growth": outcome.max_supply_growth,
                "peak_lift": outcome.peak_lift,
            }
        )
    return {
        "checkpoint_at": result.checkpoint_at.isoformat(),
        "split": split,
        "candidate_count": result.candidate_count,
        "predictions": predicted,
        "fired_candidates": fired_candidates,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    all_metrics = payload["metrics"]["all"]
    method = all_metrics["rankings"]["method"]
    method_precision = method["precision_at_10_percent"]
    has_predictions = method["predictions"] > 0
    has_positive_outcomes = all_metrics["fired_candidate_topics"] > 0
    gate_checks = {
        "checkpoints": all_metrics["checkpoint_count"] >= 6,
        "has_actionable_predictions": has_predictions,
        "has_positive_outcomes": has_positive_outcomes,
        "precision_at_10": method_precision is not None and method_precision >= 40,
        "median_lead": (
            method["median_lead_days"] is not None and method["median_lead_days"] >= 21
        ),
        "beats_base_rate": (
            method_precision is not None
            and method_precision > all_metrics["candidate_base_rate_percent"]
        ),
        "not_worse_than_all_simple_baselines": (
            method_precision is not None
            and method_precision
            >= min(
                all_metrics["rankings"][name]["precision_at_10_percent"]
                for name in ("supply", "velocity", "outlier")
            )
        ),
    }
    gate_passed = all(gate_checks.values())
    rows = [
        "# EarlySignal external 30-day historical backtest",
        "",
        f"**Verdict:** {'PASS' if gate_passed else 'FAIL'}  ",
        f"**Dataset SHA-256:** `{payload['dataset_sha256']}`  ",
        f"**Protocol:** `{payload['protocol_version']}`  ",
        f"**Outcome:** `{payload['outcome_version']}`  ",
        f"**Eligible AI/tech videos:** {payload['eligible_video_count']}  ",
        f"**Stable topic identities:** {payload['topic_identity_count']}",
        "",
        "## Primary result",
        "",
        "| Split | Method | Predictions | Fired | Precision@10 | Median lead |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for split in ("train", "holdout", "all"):
        metrics = payload["metrics"][split]
        for name in ("method", "supply", "velocity", "outlier"):
            item = metrics["rankings"][name]
            lead = item["median_lead_days"]
            precision = item["precision_at_10_percent"]
            rows.append(
                f"| {split} | {name} | {item['predictions']} | {item['fired']} | "
                f"{f'{precision}%' if precision is not None else 'N/A'} | "
                f"{lead if lead is not None else 'N/A'} |"
            )
        rows.append(
            f"| {split} | random expected | {metrics['candidate_topics']} | "
            f"{metrics['fired_candidate_topics']} | "
            f"{metrics['candidate_base_rate_percent']}% | N/A |"
        )
    rows.extend(
        [
            "",
            "## Gate",
            "",
            "| Check | Result |",
            "|---|---|",
            *[
                f"| {name} | {'PASS' if passed else 'FAIL'} |"
                for name, passed in gate_checks.items()
            ],
            "",
            "## Historical predictions",
            "",
        ]
    )
    for checkpoint in payload["checkpoints"]:
        rows.extend(
            [
                f"### {checkpoint['checkpoint_at']} — {checkpoint['split']}",
                "",
                f"Candidates: {checkpoint['candidate_count']}",
                "",
                "| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |",
                "|---:|---|---:|---|---:|---:|---:|",
            ]
        )
        for prediction in checkpoint["predictions"]:
            rows.append(
                f"| {prediction['rank']} | {prediction['label']} | {prediction['score']} | "
                f"{'yes' if prediction['fired'] else 'no'} | "
                f"{prediction['lead_days'] if prediction['lead_days'] is not None else 'N/A'} | "
                f"{prediction['max_supply_growth']}x | {prediction['peak_lift']}x |"
            )
        if not checkpoint["predictions"]:
            rows.append("| — | No actionable topic | — | — | — | — | — |")
        rows.extend(["", "Fired candidate topics:", ""])
        if checkpoint["fired_candidates"]:
            rows.extend(
                f"- {row['label']} — lead {row['lead_days']}d; selected: "
                f"{'yes' if row['selected_by_method'] else 'no'}"
                for row in checkpoint["fired_candidates"]
            )
        else:
            rows.append("- None")
        rows.append("")
    rows.extend(
        [
            "## Interpretation boundary",
            "",
            "- Feature code never reads post-checkpoint snapshots; only the blind outcome "
            "pass does.",
            "- The result tests the deterministic topic/score core, not comments, transcripts, "
            "creator fit, or provider diversity, which the external archive does not contain.",
            "- Exact publication timestamps are approximated as first observation minus one day, "
            "matching the source collector's previous-day selection rule.",
            "- The source archive and its collection code are independent of EarlySignal.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()

    dataset_hash = _file_hash(args.dataset)
    if dataset_hash != EXPECTED_DATASET_SHA256:
        parser.error(
            f"dataset SHA-256 mismatch: expected {EXPECTED_DATASET_SHA256}, got {dataset_hash}"
        )
    videos = _load_dataset(args.dataset)
    replay = ExternalTimeseriesReplay(videos)
    policy = ExternalReplayPolicy()
    results = []
    checkpoints = []
    for raw_checkpoint, split in CHECKPOINTS:
        checkpoint_at = datetime.fromisoformat(raw_checkpoint).astimezone(UTC)
        result, rankings = replay.label_checkpoint(checkpoint_at, policy=policy)
        results.append((result, rankings, split))
        checkpoints.append(_checkpoint_payload(result, rankings, split))

    train_rows = [(result, rankings) for result, rankings, split in results if split == "train"]
    holdout_rows = [(result, rankings) for result, rankings, split in results if split == "holdout"]
    all_rows = [(result, rankings) for result, rankings, _ in results]
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "dataset_sha256": dataset_hash,
        "dataset_video_count": len(videos),
        "eligible_video_count": replay.eligible_video_count,
        "topic_identity_count": replay.topic_identity_count,
        "protocol_version": EXTERNAL_REPLAY_VERSION,
        "outcome_version": OUTCOME_VERSION,
        "policy": policy.__dict__,
        "metrics": {
            "train": summarize_external_results(train_rows, split="train"),
            "holdout": summarize_external_results(holdout_rows, split="holdout"),
            "all": summarize_external_results(all_rows, split="all"),
        },
        "checkpoints": checkpoints,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(_render_markdown(payload) + "\n", encoding="utf-8")
    print(json.dumps(payload["metrics"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
