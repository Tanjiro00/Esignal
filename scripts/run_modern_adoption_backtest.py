from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any

from packages.backtest.modern_adoption import (
    MODERN_ADOPTION_REPLAY_VERSION,
    build_temporal_adoption_episodes,
    load_structural_cohort,
    maximum_complete_checkpoint,
    temporal_fit_calibration_split,
)
from packages.backtest.probability_replay import ProbabilityEpisode
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralReplayPolicy,
)
from packages.clustering import MICROTOPIC_V7_VERSION
from packages.evaluation import ProbabilityObservation, calculate_probability_metrics
from packages.scoring import (
    LogisticProbabilityModel,
    ProbabilityTrainingExample,
    fit_logistic_probability_model,
)

PROTOCOL = "MODERN_ADOPTION_DEVELOPMENT_PROTOCOL_2026-08-13.md"
REPORT_NAME = "MODERN_ADOPTION_DEVELOPMENT_2026-08-13"
TOP_FRACTION = 0.2


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ScoredEpisode:
    episode: ProbabilityEpisode
    probability: float


def _examples(episodes: Sequence[ProbabilityEpisode]) -> list[ProbabilityTrainingExample]:
    return [
        ProbabilityTrainingExample(
            features=episode.features,
            label=episode.adoption_label,
        )
        for episode in episodes
    ]


def _selection_count(rows: Sequence[ScoredEpisode]) -> int:
    return max(1, math.ceil(len(rows) * TOP_FRACTION)) if rows else 0


def _selected(
    rows: Sequence[ScoredEpisode],
    score: Callable[[ScoredEpisode], float],
) -> list[ScoredEpisode]:
    return sorted(
        rows,
        key=lambda row: (
            -score(row),
            row.episode.checkpoint_at,
            row.episode.state.topic_key,
        ),
    )[: _selection_count(rows)]


def _ranking(
    rows: Sequence[ScoredEpisode],
    score: Callable[[ScoredEpisode], float],
) -> dict[str, float | int | None]:
    selected = _selected(rows, score)
    positives = sum(row.episode.adoption_label for row in rows)
    selected_positives = sum(row.episode.adoption_label for row in selected)
    precision = selected_positives / len(selected) if selected else None
    base_rate = positives / len(rows) if rows else 0
    lead_days = [
        float(row.episode.outcome.adoption_lead_days)
        for row in selected
        if row.episode.adoption_label and row.episode.outcome.adoption_lead_days is not None
    ]
    return {
        "predictions": len(selected),
        "positives": selected_positives,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(selected_positives / positives, 6) if positives else None,
        "lift": round(precision / base_rate, 6) if precision is not None and base_rate else None,
        "median_lead_days": round(float(median(lead_days)), 3) if lead_days else None,
    }


def _bootstrap_lift_interval(rows: Sequence[ScoredEpisode]) -> dict[str, float | int | None]:
    by_topic: defaultdict[str, list[ScoredEpisode]] = defaultdict(list)
    for row in rows:
        by_topic[row.episode.state.topic_key].append(row)
    topic_keys = sorted(by_topic)
    if len(topic_keys) < 2:
        return {"resamples": 0, "lower": None, "median": None, "upper": None}
    rng = random.Random(20260813)
    lifts: list[float] = []
    for _ in range(500):
        sample: list[ScoredEpisode] = []
        for _ in topic_keys:
            sample.extend(by_topic[rng.choice(topic_keys)])
        summary = _ranking(sample, lambda row: row.probability)
        if summary["lift"] is not None:
            lifts.append(float(summary["lift"]))
    if not lifts:
        return {"resamples": 0, "lower": None, "median": None, "upper": None}
    lifts.sort()

    def percentile(fraction: float) -> float:
        return lifts[min(len(lifts) - 1, round((len(lifts) - 1) * fraction))]

    return {
        "resamples": len(lifts),
        "lower": round(percentile(0.025), 6),
        "median": round(percentile(0.5), 6),
        "upper": round(percentile(0.975), 6),
    }


def _checkpoint_rows(rows: Sequence[ScoredEpisode]) -> list[dict[str, Any]]:
    grouped: defaultdict[datetime, list[ScoredEpisode]] = defaultdict(list)
    for row in rows:
        grouped[row.episode.checkpoint_at].append(row)
    return [
        {
            "checkpoint_at": checkpoint.isoformat(),
            "episodes": len(items),
            "positives": sum(item.episode.adoption_label for item in items),
            "base_rate": round(
                sum(item.episode.adoption_label for item in items) / len(items),
                6,
            ),
        }
        for checkpoint, items in sorted(grouped.items())
    ]


def _report(
    train: Sequence[ProbabilityEpisode],
    test: Sequence[ProbabilityEpisode],
    model: LogisticProbabilityModel,
) -> dict[str, Any]:
    rows = [ScoredEpisode(episode, model.predict(episode.features)) for episode in test]
    observations = [
        ProbabilityObservation(
            key=episode.episode.key,
            probability=episode.probability,
            label=episode.episode.adoption_label,
        )
        for episode in rows
    ]
    probability_metrics = calculate_probability_metrics(
        observations,
        top_k=_selection_count(rows),
    )
    rankings = {
        "probability_model": _ranking(rows, lambda row: row.probability),
        "legacy_score": _ranking(rows, lambda row: row.episode.state.score),
        "recent_supply": _ranking(rows, lambda row: row.episode.state.recent_video_count),
        "acceleration": _ranking(rows, lambda row: row.episode.state.acceleration),
        "creator_breadth": _ranking(
            rows,
            lambda row: row.episode.state.distinct_channel_count,
        ),
    }
    method = rankings["probability_model"]
    baseline_precisions = [
        float(summary["precision"])
        for name, summary in rankings.items()
        if name != "probability_model" and summary["precision"] is not None
    ]
    checks = {
        "positive_support": probability_metrics["positives"] >= 20,
        "lift_at_top_quintile": method["lift"] is not None and float(method["lift"]) >= 1.5,
        "average_precision_beats_base_rate": (
            probability_metrics["average_precision"] is not None
            and probability_metrics["base_rate"] is not None
            and probability_metrics["average_precision"] > probability_metrics["base_rate"]
        ),
        "brier_beats_constant": (
            probability_metrics["brier_score"] is not None
            and probability_metrics["constant_brier_score"] is not None
            and probability_metrics["brier_score"] < probability_metrics["constant_brier_score"]
        ),
        "calibration_error": (
            probability_metrics["expected_calibration_error"] is not None
            and probability_metrics["expected_calibration_error"] <= 0.15
        ),
        "median_lead": (
            method["median_lead_days"] is not None and float(method["median_lead_days"]) >= 7
        ),
        "not_worse_than_simple_rankings": (
            method["precision"] is not None
            and bool(baseline_precisions)
            and float(method["precision"]) >= max(baseline_precisions)
        ),
    }
    if probability_metrics["positives"] < 20:
        verdict = "INSUFFICIENT_OUTCOME_SUPPORT"
    elif all(checks.values()):
        verdict = "DIRECTIONAL_PASS_REQUIRES_FUTURE_CONFIRMATION"
    else:
        verdict = "FAIL"
    predictions = [
        {
            "checkpoint_at": row.episode.checkpoint_at.isoformat(),
            "topic_key": row.episode.state.topic_key,
            "label": row.episode.state.label,
            "probability": row.probability,
            "outcome": row.episode.adoption_label,
            "lead_days": row.episode.outcome.adoption_lead_days,
            "future_video_count": row.episode.outcome.future_video_count,
            "new_future_channel_count": row.episode.outcome.new_future_channel_count,
            "evidence": [
                {
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": title,
                }
                for video_id, title in zip(
                    row.episode.state.member_video_ids[-5:],
                    row.episode.state.evidence_titles[-5:],
                    strict=False,
                )
            ],
        }
        for row in _selected(rows, lambda item: item.probability)
    ]
    return {
        "verdict": verdict,
        "checks": checks,
        "train_episode_count": len(train),
        "train_positive_count": sum(episode.adoption_label for episode in train),
        "test_episode_count": len(test),
        "test_topic_count": len({episode.state.topic_key for episode in test}),
        "probability_metrics": probability_metrics,
        "rankings": rankings,
        "lift_topic_bootstrap_95": _bootstrap_lift_interval(rows),
        "test_checkpoints": _checkpoint_rows(rows),
        "predictions": predictions,
    }


def _markdown(payload: dict[str, Any]) -> str:
    metrics = payload["result"]["probability_metrics"]
    rows = [
        "# Modern YouTube adoption development replay",
        "",
        f"**Verdict:** `{payload['result']['verdict']}`  ",
        f"**Train episodes:** {payload['result']['train_episode_count']} "
        f"({payload['result']['train_positive_count']} positives)  ",
        f"**Test episodes:** {payload['result']['test_episode_count']} "
        f"({metrics['positives']} positives)  ",
        "**Boundary:** selection-biased development cohort; never a blind product claim.",
        "",
        "| Ranking | Precision | Recall | Lift | Median lead days |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, summary in payload["result"]["rankings"].items():
        rows.append(
            f"| {name} | {summary['precision']} | {summary['recall']} | "
            f"{summary['lift']} | {summary['median_lead_days']} |"
        )
    rows.extend(
        [
            "",
            "## Probability quality",
            "",
            f"- Base rate: `{metrics['base_rate']}`",
            f"- Average precision: `{metrics['average_precision']}`",
            f"- Brier / constant Brier: `{metrics['brier_score']}` / "
            f"`{metrics['constant_brier_score']}`",
            f"- Expected calibration error: `{metrics['expected_calibration_error']}`",
            f"- Topic bootstrap lift 95%: `{payload['result']['lift_topic_bootstrap_95']}`",
            "",
            "## Gate",
            "",
            "| Check | Result |",
            "|---|---|",
        ]
    )
    rows.extend(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in payload["result"]["checks"].items()
    )
    rows.extend(
        [
            "",
            "## Reproducibility",
            "",
            f"- Cohort SHA-256: `{payload['cohort_sha256']}`",
            f"- Protocol SHA-256: `{payload['protocol_sha256']}`",
            f"- Replay: `{payload['replay_version']}`",
            f"- Taxonomy: `{payload['taxonomy_version']}`",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-start", default="2026-03-01T23:59:59+00:00")
    parser.add_argument("--train-end", default="2026-05-25T23:59:59+00:00")
    parser.add_argument("--test-start", default="2026-06-01T23:59:59+00:00")
    parser.add_argument("--test-end", default="2026-07-02T00:00:00+00:00")
    args = parser.parse_args()

    videos = load_structural_cohort(args.input)
    policy = StructuralReplayPolicy()
    test_end = _date(args.test_end)
    complete_through = maximum_complete_checkpoint(
        videos,
        outcome_horizon_days=policy.outcome_horizon_days,
    )
    if test_end > complete_through:
        raise ValueError(
            f"test end {test_end.isoformat()} exceeds complete outcome horizon "
            f"{complete_through.isoformat()}"
        )
    candidate_index = StructuralCandidateIndex(videos, policy=policy)
    outcome_evaluator = StructuralOutcomeEvaluator(videos, (), (), policy=policy)
    train, test = build_temporal_adoption_episodes(
        candidate_index,
        outcome_evaluator,
        train_start=_date(args.train_start),
        train_end=_date(args.train_end),
        test_start=_date(args.test_start),
        test_end=test_end,
    )
    fitting, calibration, calibration_boundary = temporal_fit_calibration_split(train)
    model = fit_logistic_probability_model(
        _examples(fitting),
        calibration=_examples(calibration),
    )
    root = Path(__file__).resolve().parents[1]
    protocol_path = root / "docs" / "evaluation" / PROTOCOL
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "cohort_path": str(args.input),
        "cohort_sha256": _hash(args.input),
        "protocol_sha256": _hash(protocol_path),
        "selection_bias": "current-monitoring-universe-retrospective-development",
        "replay_version": MODERN_ADOPTION_REPLAY_VERSION,
        "taxonomy_version": MICROTOPIC_V7_VERSION,
        "policy": asdict(policy),
        "video_count": len(videos),
        "channel_count": len({video.channel_id for video in videos}),
        "topic_identity_count": candidate_index.topic_identity_count,
        "complete_outcomes_through": complete_through.isoformat(),
        "train_range": [args.train_start, args.train_end],
        "test_range": [args.test_start, args.test_end],
        "calibration_boundary": calibration_boundary.isoformat(),
        "model": model.payload(),
        "result": _report(train, test, model),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{REPORT_NAME}.json"
    markdown_path = args.output_dir / f"{REPORT_NAME}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(_markdown(payload))
    print(json.dumps(payload["result"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
