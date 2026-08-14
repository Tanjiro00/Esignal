from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
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
    TopicSnapshot,
)
from packages.backtest import ShortHorizonObservation, ShortHorizonPolicy, label_short_horizon


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for position in range(index, end):
            result[ordered[position][0]] = average_rank
        index = end
    return result


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_item - left_mean) * (right_item - right_mean)
        for left_item, right_item in zip(left, right, strict=True)
    )
    left_scale = math.sqrt(sum((item - left_mean) ** 2 for item in left))
    right_scale = math.sqrt(sum((item - right_mean) ** 2 for item in right))
    if not left_scale or not right_scale:
        return None
    return numerator / (left_scale * right_scale)


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _numeric_features(
    prediction: BacktestPrediction,
    baseline: TopicSnapshot,
) -> dict[str, float]:
    components = baseline.component_json
    features = {
        "aggregate_view_velocity": float(baseline.aggregate_view_velocity),
        "baseline_lift": float(baseline.median_outlier_ratio),
        "baseline_supply_72h": float(baseline.video_count_72h),
        "demand_score": float(baseline.demand_score),
        "fragility_score": float(baseline.fragility_score),
        "prediction_rank": float(prediction.rank),
        "prediction_score": float(prediction.score),
        "saturation_score": float(baseline.saturation_score),
    }
    for key, value in components.items():
        if isinstance(value, int | float) and not isinstance(value, bool):
            features[f"component.{key}"] = float(value)
    return features


def analyze(
    session: Session,
    *,
    cohort_id: str,
    horizons_days: tuple[int, ...],
) -> dict[str, Any]:
    cohort = session.get(BacktestCohort, cohort_id)
    if cohort is None:
        raise ValueError(f"Backtest cohort not found: {cohort_id}")
    cutoff = session.scalar(select(func.max(TopicSnapshot.observed_at)))
    if cutoff is None:
        raise ValueError("No topic snapshots are available")
    cutoff = _aware(cutoff)

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
    checkpoints = {
        row.id: row
        for row in session.scalars(
            select(BacktestCheckpoint).where(
                BacktestCheckpoint.id.in_([link.checkpoint_id for link in links])
            )
        )
    }
    output: dict[str, Any] = {
        "protocol": "train-ranking-continuous-outcome-diagnostic-v1",
        "cohort_id": cohort_id,
        "cohort_dataset_hash": cohort.dataset_hash,
        "evaluation_as_of": cutoff.isoformat(),
        "split": "train",
        "holdout_opened": False,
        "warning": (
            "Exploratory direct-topic follow-up only. Small samples and repeated topics make "
            "correlations descriptive, not causal or sufficient for a scoring change."
        ),
        "horizons": [],
    }

    for horizon_days in horizons_days:
        policy = ShortHorizonPolicy(horizons_days=(horizon_days,))
        rows: list[dict[str, Any]] = []
        for link in links:
            checkpoint = checkpoints[link.checkpoint_id]
            checkpoint_at = _aware(checkpoint.checkpoint_at)
            end = checkpoint_at + timedelta(days=horizon_days)
            if end > cutoff:
                continue
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
                snapshot.id: snapshot
                for snapshot in session.scalars(
                    select(TopicSnapshot).where(TopicSnapshot.id.in_(baseline_ids))
                )
            }
            future_by_topic: dict[str, list[TopicSnapshot]] = defaultdict(list)
            for snapshot in session.scalars(
                select(TopicSnapshot)
                .where(
                    TopicSnapshot.topic_id.in_(
                        [prediction.candidate_key for prediction in predictions]
                    ),
                    TopicSnapshot.observed_at > checkpoint_at,
                    TopicSnapshot.observed_at <= end,
                )
                .order_by(TopicSnapshot.observed_at, TopicSnapshot.id)
            ):
                future_by_topic[snapshot.topic_id].append(snapshot)

            for prediction in predictions:
                baseline_id = prediction.evidence_json["historical_snapshot"]["id"]
                baseline = baselines[baseline_id]
                observations = [
                    ShortHorizonObservation(
                        snapshot_id=snapshot.id,
                        observed_at=snapshot.observed_at,
                        supply_72h=snapshot.video_count_72h,
                        median_outlier_lift=snapshot.median_outlier_ratio,
                    )
                    for snapshot in future_by_topic.get(prediction.candidate_key, [])
                ]
                label = label_short_horizon(
                    baseline_supply_72h=baseline.video_count_72h,
                    checkpoint_at=checkpoint_at,
                    horizon_days=horizon_days,
                    observations=observations,
                    policy=policy,
                )
                rows.append(
                    {
                        "best_joint_fraction_of_gate": label.best_joint_fraction_of_gate,
                        "evaluated": label.status == "evaluated",
                        "features": _numeric_features(prediction, baseline),
                        "followup_count": label.followup_count,
                        "rank": prediction.rank,
                    }
                )

        observed = [row for row in rows if row["followup_count"] > 0]
        outcome = [float(row["best_joint_fraction_of_gate"]) for row in observed]
        feature_names = sorted(
            set.intersection(*(set(row["features"]) for row in observed)) if observed else set()
        )
        correlations = []
        for feature_name in feature_names:
            coefficient = _spearman(
                [float(row["features"][feature_name]) for row in observed],
                outcome,
            )
            if coefficient is not None:
                correlations.append(
                    {
                        "feature": feature_name,
                        "spearman": round(coefficient, 4),
                    }
                )
        correlations.sort(key=lambda item: abs(item["spearman"]), reverse=True)

        def group_median(
            observed_rows: list[dict[str, Any]],
            ranks: set[int],
        ) -> float | None:
            values = [
                float(row["best_joint_fraction_of_gate"])
                for row in observed_rows
                if row["rank"] in ranks
            ]
            return round(float(median(values)), 4) if values else None

        output["horizons"].append(
            {
                "horizon_days": horizon_days,
                "predictions": len(rows),
                "with_direct_followup": len(observed),
                "evaluated_predictions": sum(bool(row["evaluated"]) for row in rows),
                "median_joint_gate_fraction": (
                    round(float(median(outcome)), 4) if outcome else None
                ),
                "rank_group_median_joint_gate_fraction": {
                    "ranks_1_to_3": group_median(observed, {1, 2, 3}),
                    "ranks_4_to_7": group_median(observed, {4, 5, 6, 7}),
                    "ranks_8_to_10": group_median(observed, {8, 9, 10}),
                },
                "strongest_descriptive_correlations": correlations[:12],
                "prediction_score_spearman": next(
                    (
                        item["spearman"]
                        for item in correlations
                        if item["feature"] == "prediction_score"
                    ),
                    None,
                ),
            }
        )
    return output


def _horizons(value: str) -> tuple[int, ...]:
    parsed = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",")))
    if not parsed or any(item <= 0 for item in parsed):
        raise argparse.ArgumentTypeError("horizons must be positive integers")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze train-only ranking calibration.")
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--horizons", type=_horizons, default=(1, 3, 5))
    args = parser.parse_args()
    settings = Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as session:
        result = analyze(
            session,
            cohort_id=args.cohort_id,
            horizons_days=args.horizons,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
