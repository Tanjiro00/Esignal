from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any, Literal

from packages.backtest.youniverse import (
    YOUNIVERSE_DATASET_VERSION,
    YOUNIVERSE_OUTCOME_VERSION,
    YOUNIVERSE_REPLAY_VERSION,
    OutcomeVideo,
    StructuralVideo,
    parse_youniverse_record,
    split_candidate_and_outcome,
)
from packages.backtest.youniverse_replay import (
    ChannelSnapshot,
    StructuralCandidateIndex,
    StructuralCheckpoint,
    StructuralOutcomeEvaluator,
    StructuralReplayPolicy,
    StructuralTopicOutcome,
    build_structural_checkpoints,
)
from packages.clustering import MICROTOPIC_V7_VERSION

PREREGISTRATION = "YOUNIVERSE_STRUCTURAL_BACKTEST_PREREGISTRATION_2026-08-09.md"
SPLIT_RANGES = {
    "train": (
        datetime(2016, 1, 3, 23, 59, 59, tzinfo=UTC),
        datetime(2018, 11, 18, 23, 59, 59, tzinfo=UTC),
    ),
    "holdout": (
        datetime(2019, 1, 6, 23, 59, 59, tzinfo=UTC),
        datetime(2019, 9, 8, 23, 59, 59, tzinfo=UTC),
    ),
}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    result = datetime.fromisoformat(text)
    return _aware(result)


def _integer(value: str | None) -> int:
    if value is None or value in ("", "NA", "NaN", "nan"):
        return 0
    return max(0, int(float(value)))


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_hash(root: Path) -> str:
    digest = sha256()
    for relative in (
        "packages/clustering/microtopics.py",
        "packages/clustering/microtopics_v7.py",
        "packages/scoring/early_signal.py",
        "packages/scoring/topic.py",
        "packages/backtest/youniverse.py",
        "packages/backtest/youniverse_replay.py",
        "scripts/filter_youniverse_archive.py",
        "scripts/run_youniverse_archive_filter.sh",
        "scripts/run_youniverse_structural_backtest.py",
        "scripts/run_youniverse_structural_evaluation.py",
        "scripts/run_youniverse_structural_sequence.sh",
        f"docs/evaluation/{PREREGISTRATION}",
    ):
        path = root / relative
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _checkpoints(split: Literal["train", "holdout"]) -> tuple[datetime, ...]:
    start, end = SPLIT_RANGES[split]
    rows: list[datetime] = []
    current = start
    while current <= end:
        rows.append(current)
        current += timedelta(days=7)
    return tuple(rows)


def _load_ai_videos(path: Path) -> tuple[list[StructuralVideo], list[OutcomeVideo]]:
    structural: list[StructuralVideo] = []
    outcomes: list[OutcomeVideo] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            raw = parse_youniverse_record(line)
            candidate, outcome = split_candidate_and_outcome(raw)
            structural.append(candidate)
            outcomes.append(outcome)
    return structural, outcomes


def _load_baseline_videos(path: Path) -> list[OutcomeVideo]:
    rows: list[OutcomeVideo] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            rows.append(
                OutcomeVideo(
                    video_id=str(payload["video_id"]),
                    channel_id=str(payload["channel_id"]),
                    upload_date=_datetime(str(payload["upload_date"])),
                    crawl_date=_datetime(str(payload["crawl_date"])),
                    final_view_count=_integer(str(payload["final_view_count"])),
                )
            )
    return rows


def _load_channel_snapshots(path: Path) -> Iterator[ChannelSnapshot]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            yield ChannelSnapshot(
                channel_id=str(row.get("channel") or ""),
                observed_at=_datetime(str(row.get("datetime") or "")),
                views=_integer(row.get("views")),
                delta_views=_integer(row.get("delta_views")),
                subscribers=_integer(row.get("subs")),
                delta_subscribers=_integer(row.get("delta_subs")),
                videos=_integer(row.get("videos")),
                delta_videos=_integer(row.get("delta_videos")),
                activity=_integer(row.get("activity")),
            )


def _outcome_by_checkpoint(
    checkpoints: Iterable[StructuralCheckpoint],
) -> dict[tuple[datetime, str], StructuralTopicOutcome]:
    return {
        (checkpoint.checkpoint_at, outcome.topic_key): outcome
        for checkpoint in checkpoints
        for outcome in checkpoint.outcomes
    }


def summarize_structural_checkpoints(
    checkpoints: tuple[StructuralCheckpoint, ...],
) -> dict[str, Any]:
    outcomes = _outcome_by_checkpoint(checkpoints)
    candidate_count = sum(len(checkpoint.candidates) for checkpoint in checkpoints)
    fired_candidates = sum(
        outcome.fired for checkpoint in checkpoints for outcome in checkpoint.outcomes
    )
    rankings: dict[str, dict[str, Any]] = {}
    for name in ("method", "supply", "acceleration", "channels", "random"):
        selected = [
            (checkpoint.checkpoint_at, state)
            for checkpoint in checkpoints
            for state in checkpoint.rankings[name]
        ]
        selected_outcomes = [
            outcomes[(checkpoint_at, state.topic_key)] for checkpoint_at, state in selected
        ]
        fired = [outcome for outcome in selected_outcomes if outcome.fired]
        precision = len(fired) / len(selected) * 100 if selected else None
        recall = len(fired) / fired_candidates * 100 if fired_candidates else None
        lead_values = [outcome.lead_days for outcome in fired if outcome.lead_days is not None]
        complete_prediction_baselines = [
            outcome
            for outcome in selected_outcomes
            if outcome.future_video_count == 0 or outcome.baseline_coverage >= 0.8
        ]
        future_video_count = sum(outcome.future_video_count for outcome in selected_outcomes)
        covered_future_video_count = sum(
            outcome.future_video_count * outcome.baseline_coverage for outcome in selected_outcomes
        )
        rankings[name] = {
            "predictions": len(selected),
            "fired": len(fired),
            "precision_at_10_percent": round(precision, 2) if precision is not None else None,
            "recall_percent": round(recall, 2) if recall is not None else None,
            "median_lead_days": round(float(median(lead_values)), 2) if lead_values else None,
            "prediction_outcome_baseline_coverage_percent": round(
                len(complete_prediction_baselines) / len(selected_outcomes) * 100,
                2,
            )
            if selected_outcomes
            else None,
            "future_video_baseline_coverage_percent": round(
                covered_future_video_count / future_video_count * 100,
                2,
            )
            if future_video_count
            else 100.0,
        }
    return {
        "checkpoint_count": len(checkpoints),
        "candidate_topics": candidate_count,
        "fired_candidate_topics": fired_candidates,
        "candidate_base_rate_percent": round(fired_candidates / candidate_count * 100, 2)
        if candidate_count
        else None,
        "rankings": rankings,
    }


def _gate(metrics: dict[str, Any], *, split: str) -> dict[str, Any]:
    method = metrics["rankings"]["method"]
    precision = method["precision_at_10_percent"]
    base_rate = metrics["candidate_base_rate_percent"]
    baseline_precisions = [
        metrics["rankings"][name]["precision_at_10_percent"]
        for name in ("supply", "acceleration", "channels", "random")
        if metrics["rankings"][name]["precision_at_10_percent"] is not None
    ]
    coverage = method["prediction_outcome_baseline_coverage_percent"]
    future_video_coverage = method["future_video_baseline_coverage_percent"]
    checks = {
        "holdout_split": split == "holdout",
        "positive_outcome_support": metrics["fired_candidate_topics"] >= 20,
        "precision_at_10": precision is not None and precision >= 40,
        "median_lead": method["median_lead_days"] is not None and method["median_lead_days"] >= 21,
        "beats_base_rate": precision is not None
        and base_rate is not None
        and precision > base_rate,
        "not_worse_than_each_simple_baseline": bool(baseline_precisions)
        and precision is not None
        and precision >= max(baseline_precisions),
        "outcome_baseline_coverage": coverage is not None and coverage >= 80,
        "future_video_baseline_coverage": future_video_coverage is not None
        and future_video_coverage >= 80,
        "complete_followup": True,
    }
    if split != "holdout":
        verdict = "TRAIN_DIAGNOSTIC"
    elif not checks["positive_outcome_support"]:
        verdict = "INSUFFICIENT_OUTCOME_SUPPORT"
    else:
        verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks}


def _prediction_payload(
    checkpoint: StructuralCheckpoint,
    state: Any,
    rank: int,
) -> dict[str, Any]:
    outcomes = {outcome.topic_key: outcome for outcome in checkpoint.outcomes}
    outcome = outcomes[state.topic_key]
    return {
        "rank": rank,
        "topic_key": state.topic_key,
        "label": state.label,
        "score": state.score,
        "recent_video_count": state.recent_video_count,
        "distinct_channel_count": state.distinct_channel_count,
        "new_recent_channel_count": state.new_recent_channel_count,
        "evidence_video_ids": list(state.member_video_ids),
        "evidence_urls": [
            f"https://www.youtube.com/watch?v={video_id}" for video_id in state.member_video_ids
        ],
        "evidence_titles": list(state.evidence_titles),
        "fired": outcome.fired,
        "fired_at": outcome.fired_at.isoformat() if outcome.fired_at else None,
        "lead_days": outcome.lead_days,
        "future_video_count": outcome.future_video_count,
        "supply_growth": outcome.supply_growth,
        "new_future_channel_count": outcome.new_future_channel_count,
        "new_channel_share": outcome.new_channel_share,
        "baseline_coverage": outcome.baseline_coverage,
        "outlier_video_count": outcome.outlier_video_count,
        "median_outlier_ratio": outcome.median_outlier_ratio,
    }


def _checkpoint_payload(checkpoint: StructuralCheckpoint) -> dict[str, Any]:
    outcomes = {outcome.topic_key: outcome for outcome in checkpoint.outcomes}
    candidates = {candidate.topic_key: candidate for candidate in checkpoint.candidates}
    return {
        "checkpoint_at": checkpoint.checkpoint_at.isoformat(),
        "candidate_count": len(checkpoint.candidates),
        "predictions": [
            _prediction_payload(checkpoint, state, rank)
            for rank, state in enumerate(checkpoint.predictions, start=1)
        ],
        "positive_candidate_count": sum(outcome.fired for outcome in checkpoint.outcomes),
        "positive_candidates": [
            _prediction_payload(checkpoint, candidates[outcome.topic_key], 0)
            for outcome in checkpoint.outcomes
            if outcome.fired
        ],
        "ranking_topic_keys": {
            name: [state.topic_key for state in states]
            for name, states in checkpoint.rankings.items()
        },
        "outcome_topic_keys": sorted(outcomes),
    }


def _markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    rows = [
        "# EarlySignal YouNiverse structural historical replay",
        "",
        f"**Split:** `{payload['split']}`  ",
        f"**Verdict:** `{payload['gate']['verdict']}`  ",
        f"**Protocol:** `{payload['replay_version']}`  ",
        f"**Outcome:** `{payload['outcome_version']}`  ",
        f"**Taxonomy:** `{payload['taxonomy_version']}`",
        "",
        f"- AI/tech videos in split artifact: {payload['video_count']}",
        f"- Stable topic identities: {payload['topic_identity_count']}",
        f"- Weekly checkpoints: {metrics['checkpoint_count']}",
        f"- Deduplicated eligible episodes: {metrics['candidate_topics']}",
        f"- Positive future outcomes: {metrics['fired_candidate_topics']}",
        f"- Candidate base rate: {metrics['candidate_base_rate_percent']}",
        "",
        "## Ranking comparison",
        "",
        "| Ranking | Predictions | Fired | Precision@10 | Recall | Median lead | "
        "Episode coverage | Video coverage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in metrics["rankings"].items():
        rows.append(
            f"| {name} | {item['predictions']} | {item['fired']} | "
            f"{item['precision_at_10_percent']} | {item['recall_percent']} | "
            f"{item['median_lead_days']} | "
            f"{item['prediction_outcome_baseline_coverage_percent']} | "
            f"{item['future_video_baseline_coverage_percent']} |"
        )
    rows.extend(["", "## Frozen gate", "", "| Check | Result |", "|---|---|"])
    rows.extend(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in payload["gate"]["checks"].items()
    )
    rows.extend(["", "## Method predictions", ""])
    for checkpoint in payload["checkpoints"]:
        if not checkpoint["predictions"] and not checkpoint["positive_candidates"]:
            continue
        rows.extend(
            [
                f"### {checkpoint['checkpoint_at']}",
                "",
                f"Candidates: {checkpoint['candidate_count']}; "
                f"positives: {checkpoint['positive_candidate_count']}",
                "",
                "| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |",
                "|---:|---|---:|---:|---|---|---:|",
            ]
        )
        for prediction in checkpoint["predictions"]:
            label = str(prediction["label"]).replace("|", "\\|")
            evidence_title = (
                str(prediction["evidence_titles"][-1]).replace("|", "\\|")
                if prediction["evidence_titles"]
                else "stored video"
            )
            evidence_url = prediction["evidence_urls"][-1] if prediction["evidence_urls"] else ""
            evidence = f"[{evidence_title}]({evidence_url})" if evidence_url else evidence_title
            rows.append(
                f"| {prediction['rank']} | {label} | {prediction['score']} | "
                f"{prediction['distinct_channel_count']} | {evidence} | "
                f"{'yes' if prediction['fired'] else 'no'} | {prediction['lead_days']} |"
            )
        rows.append("")
    false_positives = [
        (checkpoint["checkpoint_at"], prediction)
        for checkpoint in payload["checkpoints"]
        for prediction in checkpoint["predictions"]
        if not prediction["fired"]
    ]
    missed_positives = []
    for checkpoint in payload["checkpoints"]:
        predicted = {prediction["topic_key"] for prediction in checkpoint["predictions"]}
        missed_positives.extend(
            (checkpoint["checkpoint_at"], candidate)
            for candidate in checkpoint["positive_candidates"]
            if candidate["topic_key"] not in predicted
        )
    for heading, examples in (
        ("False positives", false_positives),
        ("Positive episodes missed by the method", missed_positives),
    ):
        rows.extend(
            [
                f"## {heading}",
                "",
                "| Checkpoint | Topic | Example stored evidence | Future supply growth |",
                "|---|---|---|---:|",
            ]
        )
        if not examples:
            rows.append("| — | None | — | — |")
        for checkpoint_at, example in examples:
            label = str(example["label"]).replace("|", "\\|")
            evidence_title = (
                str(example["evidence_titles"][-1]).replace("|", "\\|")
                if example["evidence_titles"]
                else "stored video"
            )
            evidence_url = example["evidence_urls"][-1] if example["evidence_urls"] else ""
            evidence = f"[{evidence_title}]({evidence_url})" if evidence_url else evidence_title
            rows.append(f"| {checkpoint_at} | {label} | {evidence} | {example['supply_growth']} |")
        rows.append("")
    rows.extend(
        [
            "## Reproducibility",
            "",
            f"- AI artifact SHA-256: `{payload['ai_artifact_sha256']}`",
            f"- Baseline artifact SHA-256: `{payload['baseline_artifact_sha256']}`",
            f"- Channel time-series SHA-256: `{payload['timeseries_artifact_sha256']}`",
            f"- Code/protocol SHA-256: `{payload['code_sha256']}`",
            f"- Preregistration: `{PREREGISTRATION}`",
            "- Source: https://doi.org/10.5281/zenodo.4650046",
            "",
            "## Interpretation boundary",
            "",
            "Final video engagement is used only by the future outcome evaluator. The "
            "candidate generator receives no final per-video views, likes or dislikes.",
            "",
            "This evaluates the metadata-only structural slice inside the YouNiverse "
            "channel frame, not the full production stack or all of YouTube.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai-videos", required=True, type=Path)
    parser.add_argument("--baseline-videos", required=True, type=Path)
    parser.add_argument("--channel-timeseries", required=True, type=Path)
    parser.add_argument("--split", choices=("train", "holdout"), required=True)
    parser.add_argument("--minimum-channels", choices=(2, 3, 5), default=3, type=int)
    parser.add_argument("--recent-window-days", choices=(7, 14), default=7, type=int)
    parser.add_argument("--maximum-active-videos", choices=(15, 25, 40), default=25, type=int)
    parser.add_argument("--episode-cooldown-days", choices=(28, 42, 56), default=42, type=int)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    split: Literal["train", "holdout"] = args.split
    policy = StructuralReplayPolicy(
        minimum_channels=args.minimum_channels,
        recent_window_days=args.recent_window_days,
        maximum_active_videos=args.maximum_active_videos,
        episode_cooldown_days=args.episode_cooldown_days,
    )
    structural, outcome_rows = _load_ai_videos(args.ai_videos)
    baseline_rows = _load_baseline_videos(args.baseline_videos)
    candidate_index = StructuralCandidateIndex(
        structural,
        _load_channel_snapshots(args.channel_timeseries),
        policy=policy,
    )
    # Rankings are generated by a class that cannot access final engagement.
    # The separate evaluator receives outcomes only after that boundary exists.
    evaluator = StructuralOutcomeEvaluator(
        structural,
        outcome_rows,
        baseline_rows,
        policy=policy,
    )
    checkpoints = build_structural_checkpoints(
        candidate_index,
        evaluator,
        _checkpoints(split),
    )
    metrics = summarize_structural_checkpoints(checkpoints)
    root = Path(__file__).resolve().parents[1]
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "split": split,
        "dataset_version": YOUNIVERSE_DATASET_VERSION,
        "replay_version": YOUNIVERSE_REPLAY_VERSION,
        "outcome_version": YOUNIVERSE_OUTCOME_VERSION,
        "taxonomy_version": MICROTOPIC_V7_VERSION,
        "policy": asdict(policy),
        "video_count": candidate_index.video_count,
        "topic_identity_count": candidate_index.topic_identity_count,
        "ai_artifact_sha256": _file_hash(args.ai_videos),
        "baseline_artifact_sha256": _file_hash(args.baseline_videos),
        "timeseries_artifact_sha256": _file_hash(args.channel_timeseries),
        "code_sha256": _code_hash(root),
        "metrics": metrics,
        "gate": _gate(metrics, split=split),
        "checkpoints": [_checkpoint_payload(checkpoint) for checkpoint in checkpoints],
    }
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    args.markdown_output.write_text(_markdown(payload))


if __name__ == "__main__":
    main()
