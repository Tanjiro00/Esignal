from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any, Literal

from packages.backtest.probability_replay import (
    PROBABILITY_REPLAY_VERSION,
    ProbabilityEpisode,
    build_probability_episodes,
)
from packages.backtest.youniverse import YOUNIVERSE_DATASET_VERSION
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralReplayPolicy,
)
from packages.clustering import MICROTOPIC_V7_VERSION
from packages.evaluation import ProbabilityObservation, calculate_probability_metrics
from packages.scoring import (
    InsufficientTrainingData,
    LogisticProbabilityModel,
    ProbabilityTrainingExample,
    fit_logistic_probability_model,
)
from scripts.run_youniverse_structural_backtest import (
    SPLIT_RANGES,
    _checkpoints,
    _file_hash,
    _load_ai_videos,
    _load_baseline_videos,
    _load_channel_snapshots,
)

PROTOCOL = "YOUNIVERSE_DUAL_OUTCOME_V2_PROTOCOL_2026-08-10.md"
REPORT_NAME = "YOUNIVERSE_DUAL_OUTCOME_V2_DEVELOPMENT_2026-08-10"
TOP_FRACTION = 0.2
Head = Literal["adoption", "performance"]


@dataclass(frozen=True)
class ScoredEpisode:
    episode: ProbabilityEpisode
    probability: float


def _label(episode: ProbabilityEpisode, head: Head) -> bool | None:
    return episode.adoption_label if head == "adoption" else episode.performance_label


def _head_examples(
    episodes: Sequence[ProbabilityEpisode],
    head: Head,
) -> list[ProbabilityTrainingExample]:
    return [
        ProbabilityTrainingExample(features=episode.features, label=label)
        for episode in episodes
        if (label := _label(episode, head)) is not None
    ]


def _temporal_train_calibration_split(
    episodes: Sequence[ProbabilityEpisode],
) -> tuple[list[ProbabilityEpisode], list[ProbabilityEpisode], datetime]:
    checkpoints = sorted({episode.checkpoint_at for episode in episodes})
    if len(checkpoints) < 4:
        raise InsufficientTrainingData("at least four train checkpoints are required")
    boundary_index = min(len(checkpoints) - 1, max(1, int(len(checkpoints) * 0.75)))
    boundary = checkpoints[boundary_index]
    fitting = [episode for episode in episodes if episode.checkpoint_at < boundary]
    calibration = [episode for episode in episodes if episode.checkpoint_at >= boundary]
    return fitting, calibration, boundary


def _fit_head(
    train_episodes: Sequence[ProbabilityEpisode],
    head: Head,
) -> tuple[LogisticProbabilityModel, datetime]:
    fitting, calibration, boundary = _temporal_train_calibration_split(train_episodes)
    model = fit_logistic_probability_model(
        _head_examples(fitting, head),
        calibration=_head_examples(calibration, head),
    )
    return model, boundary


def _score_head(
    episodes: Sequence[ProbabilityEpisode],
    model: LogisticProbabilityModel,
    head: Head,
) -> list[ScoredEpisode]:
    return [
        ScoredEpisode(episode=episode, probability=model.predict(episode.features))
        for episode in episodes
        if _label(episode, head) is not None
    ]


def _top_fraction(
    rows: Sequence[ScoredEpisode],
    *,
    score: Callable[[ScoredEpisode], float],
) -> list[ScoredEpisode]:
    selection_count = max(1, math.ceil(len(rows) * TOP_FRACTION)) if rows else 0
    return sorted(
        rows,
        key=lambda row: (
            -score(row),
            row.episode.checkpoint_at,
            row.episode.state.topic_key,
        ),
    )[:selection_count]


def _observations(rows: Iterable[ScoredEpisode], head: Head) -> list[ProbabilityObservation]:
    return [
        ProbabilityObservation(
            key=row.episode.key,
            probability=row.probability,
            label=bool(_label(row.episode, head)),
        )
        for row in rows
    ]


def _ranking_summary(
    rows: Sequence[ScoredEpisode],
    head: Head,
    *,
    score: Callable[[ScoredEpisode], float],
) -> dict[str, float | int | None]:
    selected = _top_fraction(rows, score=score)
    positives = sum(bool(_label(row.episode, head)) for row in rows)
    selected_positives = sum(bool(_label(row.episode, head)) for row in selected)
    base_rate = positives / len(rows) if rows else 0
    precision = selected_positives / len(selected) if selected else None
    lead_values = [
        (
            row.episode.outcome.adoption_lead_days
            if head == "adoption"
            else row.episode.outcome.performance_lead_days
        )
        for row in selected
        if bool(_label(row.episode, head))
    ]
    complete_leads = [float(value) for value in lead_values if value is not None]
    return {
        "predictions": len(selected),
        "positives": selected_positives,
        "precision": round(precision, 6) if precision is not None else None,
        "lift": round(precision / base_rate, 6) if precision is not None and base_rate else None,
        "median_lead_days": (round(float(median(complete_leads)), 3) if complete_leads else None),
    }


def _head_report(
    episodes: Sequence[ProbabilityEpisode],
    model: LogisticProbabilityModel,
    head: Head,
) -> dict[str, Any]:
    rows = _score_head(episodes, model, head)
    all_metrics = calculate_probability_metrics(
        _observations(rows, head),
        top_k=max(1, math.ceil(len(rows) * TOP_FRACTION)),
    )
    selected = _top_fraction(rows, score=lambda row: row.probability)
    selected_metrics = calculate_probability_metrics(
        _observations(selected, head),
        top_k=len(selected) or 1,
    )
    rankings = {
        "probability_model": _ranking_summary(
            rows,
            head,
            score=lambda row: row.probability,
        ),
        "legacy_score": _ranking_summary(
            rows,
            head,
            score=lambda row: row.episode.state.score,
        ),
        "recent_supply": _ranking_summary(
            rows,
            head,
            score=lambda row: row.episode.state.recent_video_count,
        ),
        "acceleration": _ranking_summary(
            rows,
            head,
            score=lambda row: row.episode.state.acceleration,
        ),
        "creator_breadth": _ranking_summary(
            rows,
            head,
            score=lambda row: row.episode.state.distinct_channel_count,
        ),
    }
    method = rankings["probability_model"]
    baseline_precisions = [
        float(item["precision"])
        for name, item in rankings.items()
        if name != "probability_model" and item["precision"] is not None
    ]
    checks = {
        "positive_support": all_metrics["positives"] >= 20,
        "lift_at_top_quintile": (method["lift"] is not None and float(method["lift"]) >= 1.5),
        "average_precision_beats_base_rate": (
            all_metrics["average_precision"] is not None
            and all_metrics["base_rate"] is not None
            and all_metrics["average_precision"] > all_metrics["base_rate"]
        ),
        "brier_beats_constant": (
            all_metrics["brier_score"] is not None
            and all_metrics["constant_brier_score"] is not None
            and all_metrics["brier_score"] < all_metrics["constant_brier_score"]
        ),
        "calibration_error": (
            all_metrics["expected_calibration_error"] is not None
            and all_metrics["expected_calibration_error"] <= 0.15
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
    verdict = (
        "INSUFFICIENT_OUTCOME_SUPPORT"
        if not checks["positive_support"]
        else "PASS"
        if all(checks.values())
        else "FAIL"
    )
    predictions = [
        {
            "checkpoint_at": row.episode.checkpoint_at.isoformat(),
            "topic_key": row.episode.state.topic_key,
            "label": row.episode.state.label,
            "probability": row.probability,
            "outcome": bool(_label(row.episode, head)),
            "lead_days": (
                row.episode.outcome.adoption_lead_days
                if head == "adoption"
                else row.episode.outcome.performance_lead_days
            ),
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
        for row in selected
    ]
    return {
        "verdict": verdict,
        "checks": checks,
        "all_episode_metrics": all_metrics,
        "selected_metrics": selected_metrics,
        "rankings": rankings,
        "predictions": predictions,
    }


def _load_split(
    artifacts: Path,
    split: Literal["train", "holdout"],
    policy: StructuralReplayPolicy,
) -> tuple[ProbabilityEpisode, ...]:
    suffix = "_sealed" if split == "holdout" else ""
    structural, outcomes = _load_ai_videos(artifacts / f"youniverse_ai_{split}{suffix}.jsonl.gz")
    baselines = _load_baseline_videos(artifacts / f"youniverse_baselines_{split}{suffix}.jsonl.gz")
    index = StructuralCandidateIndex(
        structural,
        _load_channel_snapshots(artifacts / f"youniverse_timeseries_{split}{suffix}.tsv.gz"),
        policy=policy,
    )
    evaluator = StructuralOutcomeEvaluator(
        structural,
        outcomes,
        baselines,
        policy=policy,
    )
    return build_probability_episodes(index, evaluator, _checkpoints(split))


def _hash_files(paths: Sequence[Path]) -> str:
    digest = sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _markdown(payload: dict[str, Any]) -> str:
    rows = [
        "# EarlySignal dual-outcome probability replay",
        "",
        f"**Development verdict:** `{payload['verdict']}`  ",
        f"**Train episodes:** {payload['train_episode_count']}  ",
        f"**Temporal test episodes:** {payload['holdout_episode_count']}  ",
        "**Boundary:** development temporal test; the 2019 partition is not a new blind holdout.",
        "",
        "| Head | Verdict | Positives | Base rate | Precision@top-20% | Lift | AP | Brier | Lead |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for head in ("adoption", "performance"):
        report = payload["heads"][head]
        metrics = report["all_episode_metrics"]
        method = report["rankings"]["probability_model"]
        rows.append(
            f"| {head} | {report['verdict']} | {metrics['positives']} | "
            f"{metrics['base_rate']} | {method['precision']} | {method['lift']} | "
            f"{metrics['average_precision']} | {metrics['brier_score']} | "
            f"{method['median_lead_days']} |"
        )
    rows.extend(
        [
            "",
            "## Interpretation",
            "",
            "The adoption and performance heads are intentionally independent. A passing "
            "global head still cannot issue `Act`: channel opportunity and a fresh untouched "
            "future cohort remain required.",
            "",
            "## Reproducibility",
            "",
            f"- Protocol: `{PROTOCOL}`",
            f"- Replay: `{payload['replay_version']}`",
            f"- Taxonomy: `{payload['taxonomy_version']}`",
            f"- Input hash: `{payload['input_hash']}`",
            f"- Code/protocol hash: `{payload['code_protocol_hash']}`",
            "",
        ]
    )
    for head in ("adoption", "performance"):
        rows.extend([f"## {head.title()} gate", "", "| Check | Result |", "|---|---|"])
        rows.extend(
            f"| {name} | {'PASS' if passed else 'FAIL'} |"
            for name, passed in payload["heads"][head]["checks"].items()
        )
        rows.append("")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    artifacts = args.eval_dir / "artifacts"
    policy = StructuralReplayPolicy()
    train = _load_split(artifacts, "train", policy)
    holdout = _load_split(artifacts, "holdout", policy)
    models: dict[str, LogisticProbabilityModel] = {}
    calibration_boundaries: dict[str, str] = {}
    heads: dict[str, Any] = {}
    for head in ("adoption", "performance"):
        model, boundary = _fit_head(train, head)
        models[head] = model
        calibration_boundaries[head] = boundary.isoformat()
        heads[head] = _head_report(holdout, model, head)
    verdict = "PASS" if all(report["verdict"] == "PASS" for report in heads.values()) else "FAIL"
    input_paths = [
        artifacts / "youniverse_ai_train.jsonl.gz",
        artifacts / "youniverse_baselines_train.jsonl.gz",
        artifacts / "youniverse_timeseries_train.tsv.gz",
        artifacts / "youniverse_ai_holdout_sealed.jsonl.gz",
        artifacts / "youniverse_baselines_holdout_sealed.jsonl.gz",
        artifacts / "youniverse_timeseries_holdout_sealed.tsv.gz",
    ]
    root = Path(__file__).resolve().parents[1]
    code_paths = [
        root / "packages/backtest/probability_replay.py",
        root / "packages/backtest/youniverse_replay.py",
        root / "packages/scoring/probability.py",
        root / "packages/evaluation/probability.py",
        root / "scripts/run_youniverse_probability_backtest.py",
        root / "docs/evaluation" / PROTOCOL,
    ]
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "verdict": verdict,
        "dataset_version": YOUNIVERSE_DATASET_VERSION,
        "replay_version": PROBABILITY_REPLAY_VERSION,
        "taxonomy_version": MICROTOPIC_V7_VERSION,
        "policy": asdict(policy),
        "train_range": [value.isoformat() for value in SPLIT_RANGES["train"]],
        "holdout_range": [value.isoformat() for value in SPLIT_RANGES["holdout"]],
        "holdout_status": "reused_development_temporal_test_not_blind",
        "train_episode_count": len(train),
        "holdout_episode_count": len(holdout),
        "calibration_boundaries": calibration_boundaries,
        "models": {head: model.payload() for head, model in models.items()},
        "heads": heads,
        "input_files": {path.name: _file_hash(path) for path in input_paths},
        "input_hash": _hash_files(input_paths),
        "code_protocol_hash": _hash_files(code_paths),
    }
    json_output = args.json_output or artifacts / f"{REPORT_NAME}.json"
    markdown_output = args.markdown_output or artifacts / f"{REPORT_NAME}.md"
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(_markdown(payload))


if __name__ == "__main__":
    main()
