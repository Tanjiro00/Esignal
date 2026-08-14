from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from apps.api.lifecycle import (
    classify_historical_lifecycle,
    measurement_from_snapshot,
    snapshot_supports_visible_signal,
)
from apps.api.models import (
    BacktestCheckpoint,
    BacktestPrediction,
    BacktestRun,
    Topic,
    TopicSnapshot,
)

REPLAY_ALGORITHM_VERSION = "temporal-recorded-score-replay-v2-lineage"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ReplayPolicy:
    top_k: int = 10
    max_snapshot_age_days: int = 7
    algorithm_version: str = REPLAY_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.max_snapshot_age_days <= 0:
            raise ValueError("max_snapshot_age_days must be positive")
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must not be empty")


@dataclass(frozen=True)
class ReplayCandidate:
    candidate_key: str
    checkpoint_at: datetime
    snapshot_id: str
    snapshot_at: datetime
    score: float
    lifecycle_stage: str
    confidence: str
    visible_signal: bool
    evidence: dict[str, Any]


def _confidence(snapshot: TopicSnapshot) -> str:
    components = snapshot.component_json
    video_count = int(components.get("video_count", 0))
    distinct_channels = int(components.get("distinct_channels", 0))
    snapshot_coverage = float(components.get("snapshot_coverage", 0))
    baseline_coverage = float(components.get("baseline_coverage", 0))
    specificity = float(components.get("specificity_score", 0))
    if (
        video_count >= 6
        and distinct_channels >= 5
        and snapshot_coverage >= 0.9
        and baseline_coverage >= 0.7
        and specificity >= 70
    ):
        return "High"
    if (
        video_count >= 3
        and distinct_channels >= 3
        and snapshot_coverage >= 0.7
        and baseline_coverage >= 0.5
        and specificity >= 65
    ):
        return "Medium"
    return "Low"


def load_candidate_universe(
    session: Session,
    *,
    checkpoint_at: datetime,
    source_kind: str,
    policy: ReplayPolicy,
) -> list[ReplayCandidate]:
    """Load only candidates recorded by the checkpoint time.

    Topic labels and current signal rows are intentionally not read: both are
    mutable and could leak later synthesis into a historical run. The replay
    uses the score and components recorded with the historical topic snapshot.
    """

    cutoff = _aware(checkpoint_at)
    earliest_snapshot = cutoff - timedelta(days=policy.max_snapshot_age_days)
    latest_snapshot = (
        select(
            TopicSnapshot.topic_id.label("topic_id"),
            func.max(TopicSnapshot.observed_at).label("observed_at"),
        )
        .join(Topic, Topic.id == TopicSnapshot.topic_id)
        .where(
            Topic.source_kind == source_kind,
            TopicSnapshot.observed_at <= cutoff,
            TopicSnapshot.observed_at >= earliest_snapshot,
        )
        .group_by(TopicSnapshot.topic_id)
        .subquery()
    )
    rows = session.scalars(
        select(TopicSnapshot)
        .join(
            latest_snapshot,
            and_(
                latest_snapshot.c.topic_id == TopicSnapshot.topic_id,
                latest_snapshot.c.observed_at == TopicSnapshot.observed_at,
            ),
        )
        .order_by(TopicSnapshot.topic_id)
    )

    candidates: list[ReplayCandidate] = []
    for snapshot in rows:
        topic_id = snapshot.topic_id
        raw_score = snapshot.component_json.get("score")
        if not isinstance(raw_score, int | float):
            continue
        raw_topic_identity = snapshot.component_json.get("topic_identity")
        topic_identity = dict(raw_topic_identity) if isinstance(raw_topic_identity, dict) else None
        measurement = measurement_from_snapshot(snapshot)
        lifecycle_stage = classify_historical_lifecycle(measurement)
        visible = snapshot_supports_visible_signal(snapshot, lifecycle_stage)
        evidence = {
            "candidate_key": topic_id,
            "checkpoint_at": cutoff.isoformat(),
            "historical_snapshot": {
                "aggregate_view_velocity": snapshot.aggregate_view_velocity,
                "component_json": dict(snapshot.component_json),
                "demand_score": snapshot.demand_score,
                "distinct_channels_72h": snapshot.distinct_channels_72h,
                "fragility_score": snapshot.fragility_score,
                "id": snapshot.id,
                "large_channel_count": snapshot.large_channel_count,
                "median_outlier_ratio": snapshot.median_outlier_ratio,
                "observed_at": _aware(snapshot.observed_at).isoformat(),
                "saturation_score": snapshot.saturation_score,
                "topic_identity": topic_identity,
                "video_count_24h": snapshot.video_count_24h,
                "video_count_72h": snapshot.video_count_72h,
            },
            "topic_lineage_snapshot_bound": topic_identity is not None,
            "point_in_time": True,
            "production_score_reused": True,
            "mutable_topic_copy_excluded": True,
            "mutable_signal_copy_excluded": True,
            "temporal_predicates": [
                "topic_snapshot.observed_at <= checkpoint_at",
                "topic_snapshot.observed_at >= checkpoint_at - max_snapshot_age",
            ],
        }
        candidates.append(
            ReplayCandidate(
                candidate_key=topic_id,
                checkpoint_at=cutoff,
                snapshot_id=snapshot.id,
                snapshot_at=_aware(snapshot.observed_at),
                score=round(min(100.0, max(0.0, float(raw_score))), 2),
                lifecycle_stage=lifecycle_stage,
                confidence=_confidence(snapshot),
                visible_signal=visible,
                evidence=evidence,
            )
        )
    return candidates


class TemporalReplayService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replay_checkpoint(
        self,
        checkpoint: BacktestCheckpoint,
        *,
        policy: ReplayPolicy | None = None,
        persist: bool = True,
    ) -> tuple[list[BacktestPrediction], list[ReplayCandidate]]:
        selected_policy = policy or ReplayPolicy()
        run = self._session.get(BacktestRun, checkpoint.run_id)
        if run is None:
            raise ValueError("Backtest checkpoint has no run")
        if checkpoint.status != "success":
            raise ValueError("Only successful checkpoints can be replayed")
        candidates = load_candidate_universe(
            self._session,
            checkpoint_at=checkpoint.checkpoint_at,
            source_kind=run.source_kind,
            policy=selected_policy,
        )
        ranked = sorted(
            (candidate for candidate in candidates if candidate.visible_signal),
            key=lambda item: (-item.score, item.candidate_key),
        )[: selected_policy.top_k]
        now = datetime.now(tz=UTC)
        predictions = [
            BacktestPrediction(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"earlysignal:backtest-prediction:{checkpoint.id}:{candidate.candidate_key}",
                    )
                ),
                checkpoint_id=checkpoint.id,
                candidate_key=candidate.candidate_key,
                rank=rank,
                score=candidate.score,
                lifecycle_stage=candidate.lifecycle_stage,
                confidence=candidate.confidence,
                algorithm_version=selected_policy.algorithm_version,
                evidence_json=candidate.evidence,
                evidence_hash=_canonical_hash(candidate.evidence),
                created_at=now,
            )
            for rank, candidate in enumerate(ranked, start=1)
        ]
        if persist:
            self._persist(checkpoint, predictions)
        return predictions, candidates

    def _persist(
        self,
        checkpoint: BacktestCheckpoint,
        predictions: list[BacktestPrediction],
    ) -> None:
        existing = list(
            self._session.scalars(
                select(BacktestPrediction)
                .where(BacktestPrediction.checkpoint_id == checkpoint.id)
                .order_by(BacktestPrediction.rank)
            )
        )
        if existing:
            existing_identity = [
                (
                    row.candidate_key,
                    row.rank,
                    row.score,
                    row.lifecycle_stage,
                    row.confidence,
                    row.algorithm_version,
                    row.evidence_hash,
                )
                for row in existing
            ]
            requested_identity = [
                (
                    row.candidate_key,
                    row.rank,
                    row.score,
                    row.lifecycle_stage,
                    row.confidence,
                    row.algorithm_version,
                    row.evidence_hash,
                )
                for row in predictions
            ]
            if existing_identity != requested_identity:
                raise RuntimeError(
                    "Checkpoint predictions are immutable; use a new checkpoint "
                    "or algorithm version"
                )
            checkpoint.prediction_count = len(existing)
            self._session.commit()
            return
        self._session.add_all(predictions)
        checkpoint.prediction_count = len(predictions)
        self._session.commit()


__all__ = [
    "REPLAY_ALGORITHM_VERSION",
    "ReplayCandidate",
    "ReplayPolicy",
    "TemporalReplayService",
    "load_candidate_universe",
]
