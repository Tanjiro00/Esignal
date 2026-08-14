from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
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

IDENTITY_FIELDS = (
    "domain",
    "facet",
    "primary_entity",
    "audience",
    "user_problem",
    "core_claim",
    "workflow_context",
)


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return json.dumps(value, sort_keys=True, separators=(",", ":")).casefold()


def exact_identity_key(payload: dict[str, Any]) -> tuple[str, ...] | None:
    """Return a conservative diagnostic key; never fall back to labels."""

    if payload.get("source") == "workspace_discovery":
        workspace_id = _normalize(payload.get("workspace_id"))
        query_id = _normalize(payload.get("query_id"))
        if workspace_id and query_id:
            return ("workspace-discovery", workspace_id, query_id)
        return None

    values = tuple(_normalize(payload.get(field)) for field in IDENTITY_FIELDS)
    if not values[0] or not values[2] or not (values[4] or values[5]):
        return None
    return ("microtopic-v5", *values)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def diagnose(
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
    checkpoint_ids = [link.checkpoint_id for link in links]
    checkpoints = {
        row.id: row
        for row in session.scalars(
            select(BacktestCheckpoint).where(BacktestCheckpoint.id.in_(checkpoint_ids))
        )
    }
    predictions = list(
        session.scalars(
            select(BacktestPrediction)
            .where(BacktestPrediction.checkpoint_id.in_(checkpoint_ids))
            .order_by(BacktestPrediction.checkpoint_id, BacktestPrediction.rank)
        )
    )
    predictions_by_checkpoint: dict[str, list[BacktestPrediction]] = defaultdict(list)
    for prediction in predictions:
        predictions_by_checkpoint[prediction.checkpoint_id].append(prediction)

    topics = list(session.scalars(select(Topic).where(Topic.source_kind == "live")))
    topic_by_id = {topic.id: topic for topic in topics}
    topics_by_identity: dict[tuple[str, ...], list[Topic]] = defaultdict(list)
    for topic in topics:
        key = exact_identity_key(topic.identity_json or {})
        if key is not None:
            topics_by_identity[key].append(topic)

    output: dict[str, Any] = {
        "protocol": "exploratory-current-topic-identity-lineage-v1",
        "warning": (
            "Current Topic.identity_json is mutable and was not frozen into the historical "
            "prediction. These results diagnose lineage loss only; they are not formal labels."
        ),
        "cohort_id": cohort_id,
        "cohort_dataset_hash": cohort.dataset_hash,
        "evaluation_as_of": cutoff.isoformat(),
        "split": "train",
        "holdout_opened": False,
        "train_checkpoints": len(links),
        "train_predictions": len(predictions),
        "topics": len(topics),
        "exact_identity_groups": len(topics_by_identity),
        "prediction_evidence_keys": (
            sorted((predictions[0].evidence_json or {}).keys()) if predictions else []
        ),
        "horizons": [],
    }

    for horizon_days in horizons_days:
        matured = 0
        direct = 0
        exact = 0
        missing_identity = 0
        no_window_successor = 0
        ambiguous = 0
        merged_links = 0
        statuses: Counter[str] = Counter()
        recovered_examples: list[dict[str, Any]] = []
        lost_examples: list[dict[str, Any]] = []

        for link in links:
            checkpoint = checkpoints[link.checkpoint_id]
            checkpoint_at = _aware(checkpoint.checkpoint_at)
            horizon_end = checkpoint_at + timedelta(days=horizon_days)
            if horizon_end > cutoff:
                continue

            for prediction in predictions_by_checkpoint[checkpoint.id]:
                matured += 1
                original = topic_by_id.get(prediction.candidate_key)
                if original is not None:
                    statuses[original.status] += 1
                    if original.merged_into_topic_id:
                        merged_links += 1

                direct_id = session.scalar(
                    select(TopicSnapshot.id)
                    .where(
                        TopicSnapshot.topic_id == prediction.candidate_key,
                        TopicSnapshot.observed_at > checkpoint_at,
                        TopicSnapshot.observed_at <= horizon_end,
                    )
                    .limit(1)
                )
                if direct_id is not None:
                    direct += 1
                    exact += 1
                    continue

                identity_key = exact_identity_key(
                    (original.identity_json if original is not None else {}) or {}
                )
                if identity_key is None:
                    missing_identity += 1
                    if len(lost_examples) < 5:
                        lost_examples.append(
                            {
                                "candidate_key": prediction.candidate_key,
                                "label": original.canonical_label if original else None,
                                "reason": "no_exact_identity",
                            }
                        )
                    continue

                successor_ids = [
                    topic.id
                    for topic in topics_by_identity.get(identity_key, [])
                    if topic.id != prediction.candidate_key
                ]
                observed_ids = set(
                    session.scalars(
                        select(TopicSnapshot.topic_id).where(
                            TopicSnapshot.topic_id.in_(successor_ids),
                            TopicSnapshot.observed_at > checkpoint_at,
                            TopicSnapshot.observed_at <= horizon_end,
                        )
                    )
                )
                if not observed_ids:
                    no_window_successor += 1
                    if len(lost_examples) < 5:
                        lost_examples.append(
                            {
                                "candidate_key": prediction.candidate_key,
                                "label": original.canonical_label if original else None,
                                "reason": "no_exact_identity_successor_in_window",
                            }
                        )
                    continue

                exact += 1
                if len(observed_ids) > 1:
                    ambiguous += 1
                if len(recovered_examples) < 5:
                    recovered_examples.append(
                        {
                            "old_candidate_key": prediction.candidate_key,
                            "old_label": original.canonical_label if original else None,
                            "successor_ids": sorted(observed_ids),
                            "successor_labels": sorted(
                                topic_by_id[item].canonical_label
                                for item in observed_ids
                                if item in topic_by_id
                            ),
                        }
                    )

        output["horizons"].append(
            {
                "horizon_days": horizon_days,
                "matured_predictions": matured,
                "direct_followup": direct,
                "direct_coverage_percent": round(direct / matured * 100, 1) if matured else None,
                "exact_identity_followup": exact,
                "exact_identity_coverage_percent": (
                    round(exact / matured * 100, 1) if matured else None
                ),
                "recovered_by_exact_identity": exact - direct,
                "missing_identity": missing_identity,
                "no_window_successor": no_window_successor,
                "ambiguous_successor_predictions": ambiguous,
                "stored_merged_into_links": merged_links,
                "original_topic_statuses": dict(statuses),
                "recovered_examples": recovered_examples,
                "lost_examples": lost_examples,
            }
        )

    return output


def _parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",")))
    if not horizons or any(item <= 0 for item in horizons):
        raise argparse.ArgumentTypeError("horizons must be positive integers")
    return horizons


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose exact-identity topic lineage loss on frozen train predictions."
    )
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--horizons", type=_parse_horizons, default=(1, 3, 5))
    args = parser.parse_args()
    settings = Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(engine) as session:
        result = diagnose(
            session,
            cohort_id=args.cohort_id,
            horizons_days=args.horizons,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
