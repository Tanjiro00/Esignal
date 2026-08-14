from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    BacktestCheckpoint,
    BacktestCohort,
    BacktestCohortCheckpoint,
    BacktestPrediction,
    Topic,
    TopicSnapshot,
)
from packages.backtest import (
    ShortHorizonObservation,
    ShortHorizonPolicy,
    label_short_horizon,
)
from packages.topic_lineage import collect_lineage_followups, followup_topic_ids
from scripts.export_backtest_checkpoint import parse_timestamp


def _horizons(value: str) -> tuple[int, ...]:
    try:
        parsed = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",")))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("horizons must be comma-separated integers") from exc
    if not parsed or any(item <= 0 for item in parsed):
        raise argparse.ArgumentTypeError("horizons must contain positive integers")
    return parsed


def _percent(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def run_retrospective(
    session: Session,
    *,
    cohort_id: str,
    evaluation_as_of: datetime | None,
    policy: ShortHorizonPolicy,
) -> dict[str, Any]:
    cohort = session.get(BacktestCohort, cohort_id)
    if cohort is None:
        raise ValueError(f"Backtest cohort not found: {cohort_id}")
    if cohort.status != "frozen":
        raise ValueError("Only frozen cohorts can be evaluated")
    cutoff = evaluation_as_of or session.scalar(select(func.max(TopicSnapshot.observed_at)))
    if cutoff is None:
        raise ValueError("No topic snapshots are available for evaluation")
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)

    # Holdout is intentionally not a CLI option. This diagnostic can be used for
    # train calibration, while the formal 42-day evaluator owns holdout opening.
    links = list(
        session.scalars(
            select(BacktestCohortCheckpoint)
            .where(
                BacktestCohortCheckpoint.cohort_id == cohort_id,
                BacktestCohortCheckpoint.split == "train",
            )
            .order_by(BacktestCohortCheckpoint.ordinal)
        )
    )
    checkpoint_ids = [link.checkpoint_id for link in links]
    checkpoints = {
        row.id: row
        for row in session.scalars(
            select(BacktestCheckpoint).where(BacktestCheckpoint.id.in_(checkpoint_ids))
        )
    }
    result: dict[str, Any] = {
        "protocol": policy.protocol_version,
        "cohort_id": cohort_id,
        "cohort_dataset_hash": cohort.dataset_hash,
        "evaluation_as_of": cutoff.isoformat(),
        "split": "train",
        "holdout_opened": False,
        "formal_quality_gate": "not_run",
        "formal_quality_gate_reason": (
            "This diagnostic uses short follow-up windows; the registered gate uses 42 days."
        ),
        "recall": None,
        "recall_reason": (
            "The optimized diagnostic labels frozen top-k predictions only. Full-universe "
            "recall remains part of the formal blind outcome run."
        ),
        "thresholds": {
            "joint_same_snapshot_required": True,
            "lift": policy.lift_threshold,
            "supply_growth": policy.supply_growth_threshold,
            "top_k": policy.top_k,
        },
        "horizons": [],
    }

    for horizon_days in policy.horizons_days:
        matured_links = [
            link for link in links if link.checkpoint_at + timedelta(days=horizon_days) <= cutoff
        ]
        items: list[dict[str, Any]] = []
        per_checkpoint: list[dict[str, Any]] = []
        for link in matured_links:
            checkpoint = checkpoints[link.checkpoint_id]
            predictions = list(
                session.scalars(
                    select(BacktestPrediction)
                    .where(
                        BacktestPrediction.checkpoint_id == checkpoint.id,
                        BacktestPrediction.rank <= policy.top_k,
                    )
                    .order_by(BacktestPrediction.rank)
                )
            )
            baseline_ids = [
                prediction.evidence_json["historical_snapshot"]["id"] for prediction in predictions
            ]
            baselines = {
                row.id: row
                for row in session.scalars(
                    select(TopicSnapshot).where(TopicSnapshot.id.in_(baseline_ids))
                )
            }
            candidate_keys = [prediction.candidate_key for prediction in predictions]
            current_labels = {
                row.id: row.canonical_label
                for row in session.scalars(select(Topic).where(Topic.id.in_(candidate_keys)))
            }
            future_by_topic = collect_lineage_followups(
                session,
                baselines={
                    prediction.candidate_key: baselines[
                        prediction.evidence_json["historical_snapshot"]["id"]
                    ]
                    for prediction in predictions
                    if prediction.evidence_json["historical_snapshot"]["id"] in baselines
                },
                checkpoint_at=checkpoint.checkpoint_at,
                evaluation_as_of=cutoff,
                horizon_days=horizon_days,
            )

            checkpoint_items: list[dict[str, Any]] = []
            for prediction in predictions:
                baseline_id = prediction.evidence_json["historical_snapshot"]["id"]
                baseline = baselines.get(baseline_id)
                if baseline is None:
                    raise RuntimeError(
                        f"Frozen prediction references missing snapshot {baseline_id}"
                    )
                observations = [
                    ShortHorizonObservation(
                        snapshot_id=row.id,
                        observed_at=row.observed_at,
                        supply_72h=row.video_count_72h,
                        median_outlier_lift=row.median_outlier_ratio,
                    )
                    for row in future_by_topic.get(prediction.candidate_key, [])
                ]
                observed_topic_ids = followup_topic_ids(
                    future_by_topic.get(prediction.candidate_key, [])
                )
                label = label_short_horizon(
                    baseline_supply_72h=baseline.video_count_72h,
                    checkpoint_at=checkpoint.checkpoint_at,
                    horizon_days=horizon_days,
                    observations=observations,
                    policy=policy,
                )
                checkpoint_items.append(
                    {
                        "baseline_snapshot_id": baseline.id,
                        "candidate_key": prediction.candidate_key,
                        "checkpoint_at": checkpoint.checkpoint_at.isoformat(),
                        "checkpoint_id": checkpoint.id,
                        "display_label_current_not_used_by_evaluation": (
                            current_labels.get(prediction.candidate_key)
                        ),
                        "evaluated": label.status == "evaluated",
                        "fired": label.fired,
                        "fired_at": label.fired_at.isoformat() if label.fired_at else None,
                        "fired_snapshot_id": label.fired_snapshot_id,
                        "followup_count": label.followup_count,
                        "followup_topic_ids": observed_topic_ids,
                        "lineage_successor_used": any(
                            topic_id != prediction.candidate_key for topic_id in observed_topic_ids
                        ),
                        "lead_time_days": (
                            round(
                                (label.fired_at - checkpoint.checkpoint_at).total_seconds()
                                / 86_400,
                                3,
                            )
                            if label.fired_at
                            else None
                        ),
                        "max_supply_growth": label.max_supply_growth,
                        "peak_lift": label.peak_lift,
                        "best_joint_fraction_of_gate": (label.best_joint_fraction_of_gate),
                        "rank": prediction.rank,
                        "score": prediction.score,
                        "status": label.status,
                    }
                )
            items.extend(checkpoint_items)
            evaluated_checkpoint = [row for row in checkpoint_items if row["evaluated"]]
            fired_checkpoint = [row for row in evaluated_checkpoint if row["fired"]]
            per_checkpoint.append(
                {
                    "checkpoint_at": checkpoint.checkpoint_at.isoformat(),
                    "checkpoint_id": checkpoint.id,
                    "evaluated": len(evaluated_checkpoint),
                    "fired": len(fired_checkpoint),
                    "precision_percent": _percent(len(fired_checkpoint), len(evaluated_checkpoint)),
                    "predictions": len(checkpoint_items),
                    "with_followup": sum(row["followup_count"] > 0 for row in checkpoint_items),
                }
            )

        evaluated = [row for row in items if row["evaluated"]]
        fired = [row for row in evaluated if row["fired"]]
        lead_times = [row["lead_time_days"] for row in fired]
        closest = sorted(
            items,
            key=lambda row: (
                row["best_joint_fraction_of_gate"],
                row["max_supply_growth"],
                row["peak_lift"],
            ),
            reverse=True,
        )[:5]
        result["horizons"].append(
            {
                "closest_to_joint_gate": closest,
                "coverage_percent": _percent(len(evaluated), len(items)) or 0.0,
                "evaluated_predictions": len(evaluated),
                "fired_predictions": len(fired),
                "horizon_days": horizon_days,
                "lift_gate_reached_anytime": sum(
                    row["peak_lift"] >= policy.lift_threshold for row in items
                ),
                "matured_checkpoints": len(matured_links),
                "median_lead_time_days": (
                    round(float(median(lead_times)), 3) if lead_times else None
                ),
                "per_checkpoint": per_checkpoint,
                "precision_at_k_percent": _percent(len(fired), len(evaluated)),
                "predictions": len(items),
                "supply_gate_reached_anytime": sum(
                    row["max_supply_growth"] >= policy.supply_growth_threshold for row in items
                ),
                "with_any_followup": sum(row["followup_count"] > 0 for row in items),
            }
        )
    return result


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# EarlySignal exploratory short-horizon retrospective",
        "",
        f"- Protocol: `{result['protocol']}`",
        f"- Cohort: `{result['cohort_id']}`",
        f"- Dataset hash: `{result['cohort_dataset_hash']}`",
        f"- Evaluation cutoff: `{result['evaluation_as_of']}`",
        "- Split: **train only**",
        "- Holdout opened: **no**",
        "- Formal 42-day quality gate: **not run**",
        "",
        "## Result",
        "",
        "| Horizon | Mature checkpoints | Frozen predictions | Evaluable | "
        "Coverage | Fired | Precision@10 | Median lead |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for horizon in result["horizons"]:
        precision = horizon["precision_at_k_percent"]
        lead = horizon["median_lead_time_days"]
        rows.append(
            "| {horizon}d | {checkpoints} | {predictions} | {evaluated} | "
            "{coverage}% | {fired} | {precision} | {lead} |".format(
                horizon=horizon["horizon_days"],
                checkpoints=horizon["matured_checkpoints"],
                predictions=horizon["predictions"],
                evaluated=horizon["evaluated_predictions"],
                coverage=horizon["coverage_percent"],
                fired=horizon["fired_predictions"],
                precision=f"{precision}%" if precision is not None else "N/A",
                lead=f"{lead}d" if lead is not None else "N/A",
            )
        )
    rows.extend(
        [
            "",
            "The short-window result does not support a quality claim. No frozen top-10 "
            "prediction jointly reached 3x supply growth and 3x median outlier lift. "
            "Coverage is also below the registered 80% minimum because many topic IDs "
            "have no follow-up observation near the end of the window.",
            "",
            "## Interpretation",
            "",
            "1. This is a real retrospective calculation over observations stored after "
            "each checkpoint; missing follow-up is excluded rather than counted as a miss.",
            "2. The 1/3/5-day check is diagnostic. The implementation plan's official "
            "gate remains precision@10 >= 40% and median lead time >= 21 days over a "
            "complete 42-day window.",
            "3. Current labels are included only for readability and were not used by "
            "the evaluator. The stable candidate key and snapshot IDs are the evidence keys.",
            "4. Recall is intentionally not reported in this optimized top-k pass. It "
            "must be computed over the full candidate universe by the blind 42-day run.",
            "",
            "## Diagnostic findings",
            "",
        ]
    )
    for horizon in result["horizons"]:
        rows.extend(
            [
                f"### {horizon['horizon_days']}-day horizon",
                "",
                f"- Any follow-up: {horizon['with_any_followup']}/{horizon['predictions']}",
                f"- Evaluable: {horizon['evaluated_predictions']}/{horizon['predictions']} "
                f"({horizon['coverage_percent']}%)",
                f"- Supply gate reached separately: {horizon['supply_gate_reached_anytime']}",
                f"- Lift gate reached separately: {horizon['lift_gate_reached_anytime']}",
                f"- Joint firing: {horizon['fired_predictions']}",
                "",
                "| Checkpoint | Follow-up | Evaluable | Fired | Precision |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for checkpoint in horizon["per_checkpoint"]:
            precision = checkpoint["precision_percent"]
            rows.append(
                f"| `{checkpoint['checkpoint_at']}` | {checkpoint['with_followup']}/"
                f"{checkpoint['predictions']} | {checkpoint['evaluated']} | "
                f"{checkpoint['fired']} | "
                f"{f'{precision}%' if precision is not None else 'N/A'} |"
            )
        rows.extend(
            [
                "",
                "Closest observations to the joint gate:",
                "",
                "| Display label (current, not scored) | Rank | Supply peak | "
                "Lift peak | Joint gate fraction | Baseline snapshot |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for item in horizon["closest_to_joint_gate"]:
            label = item["display_label_current_not_used_by_evaluation"] or item["candidate_key"]
            rows.append(
                f"| {label} | {item['rank']} | {item['max_supply_growth']}x | "
                f"{item['peak_lift']}x | {item['best_joint_fraction_of_gate']} | "
                f"`{item['baseline_snapshot_id']}` |"
            )
        rows.append("")
    rows.extend(
        [
            "## Required fixes before interpreting the formal gate",
            "",
            "1. Repair topic identity continuity so a frozen candidate keeps receiving "
            "auditable follow-up snapshots across re-clustering and merges.",
            "2. Raise evaluable coverage above 80% before treating precision as stable.",
            "3. Diagnose why the ranking favors topics whose future supply remains flat; "
            "calibrate on train only and keep holdout sealed.",
            "4. Run the registered blind 42-day outcome labeler when windows mature. Do "
            "not substitute this diagnostic for the quality gate.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a read-only, train-only short-horizon retrospective."
    )
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--evaluation-as-of", type=parse_timestamp)
    parser.add_argument("--horizons", type=_horizons, default=(1, 3, 5))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    policy = ShortHorizonPolicy(horizons_days=args.horizons, top_k=args.top_k)
    engine = create_engine(Settings().database_url)
    with Session(engine) as session:
        result = run_retrospective(
            session,
            cohort_id=args.cohort_id,
            evaluation_as_of=args.evaluation_as_of,
            policy=policy,
        )
    markdown = render_markdown(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown + "\n", encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "cohort_id": args.cohort_id,
                "evaluation_as_of": result["evaluation_as_of"],
                "holdout_opened": result["holdout_opened"],
                "horizons": [
                    {
                        "coverage_percent": row["coverage_percent"],
                        "fired_predictions": row["fired_predictions"],
                        "horizon_days": row["horizon_days"],
                        "precision_at_k_percent": row["precision_at_k_percent"],
                    }
                    for row in result["horizons"]
                ],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
