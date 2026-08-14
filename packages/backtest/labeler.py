from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestOutcome,
    BacktestRun,
    Topic,
    TopicSnapshot,
)
from packages.topic_lineage import (
    collect_lineage_followups,
    followup_topic_ids,
    snapshot_topic_identity,
)

OUTCOME_LABEL_VERSION = "blind-supply-lift-outcome-v2-lineage"


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
class OutcomeLabelPolicy:
    horizon_days: int = 42
    supply_growth_threshold: float = 3
    lift_threshold: float = 3
    max_baseline_age_days: int = 7
    negative_followup_grace_days: int = 3
    label_version: str = OUTCOME_LABEL_VERSION

    def __post_init__(self) -> None:
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if self.supply_growth_threshold <= 1:
            raise ValueError("supply_growth_threshold must be greater than one")
        if self.lift_threshold <= 0:
            raise ValueError("lift_threshold must be positive")
        if self.max_baseline_age_days <= 0:
            raise ValueError("max_baseline_age_days must be positive")
        if not 0 <= self.negative_followup_grace_days < self.horizon_days:
            raise ValueError("negative_followup_grace_days must be within the outcome horizon")


class BlindOutcomeLabeler:
    """Label outcomes without querying or accepting backtest predictions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def label_checkpoint(
        self,
        checkpoint: BacktestCheckpoint,
        *,
        evaluation_as_of: datetime,
        policy: OutcomeLabelPolicy | None = None,
        persist: bool = True,
    ) -> list[BacktestOutcome]:
        selected_policy = policy or OutcomeLabelPolicy()
        evaluation_cutoff = _aware(evaluation_as_of)
        checkpoint_at = _aware(checkpoint.checkpoint_at)
        if evaluation_cutoff <= checkpoint_at:
            raise ValueError("evaluation_as_of must be after checkpoint_at")
        run = self._session.get(BacktestRun, checkpoint.run_id)
        if run is None:
            raise ValueError("Backtest checkpoint has no run")
        baselines = self._baseline_snapshots(
            checkpoint_at=checkpoint_at,
            source_kind=run.source_kind,
            max_age_days=selected_policy.max_baseline_age_days,
        )
        futures = self._future_snapshots(
            baselines=baselines,
            checkpoint_at=checkpoint_at,
            evaluation_as_of=evaluation_cutoff,
            horizon_days=selected_policy.horizon_days,
        )
        now = datetime.now(tz=UTC)
        outcomes = [
            self._label_one(
                checkpoint=checkpoint,
                baseline=baseline,
                future_snapshots=futures.get(topic_id, []),
                evaluation_as_of=evaluation_cutoff,
                policy=selected_policy,
                created_at=now,
            )
            for topic_id, baseline in sorted(baselines.items())
        ]
        if persist:
            self._persist(checkpoint, outcomes)
        return outcomes

    def _baseline_snapshots(
        self,
        *,
        checkpoint_at: datetime,
        source_kind: str,
        max_age_days: int,
    ) -> dict[str, TopicSnapshot]:
        rows = self._session.scalars(
            select(TopicSnapshot)
            .join(Topic, Topic.id == TopicSnapshot.topic_id)
            .where(
                Topic.source_kind == source_kind,
                TopicSnapshot.observed_at <= checkpoint_at,
                TopicSnapshot.observed_at >= checkpoint_at - timedelta(days=max_age_days),
            )
            .order_by(
                TopicSnapshot.topic_id,
                desc(TopicSnapshot.observed_at),
                desc(TopicSnapshot.id),
            )
        )
        latest: dict[str, TopicSnapshot] = {}
        for snapshot in rows:
            if isinstance(snapshot.component_json.get("score"), int | float):
                latest.setdefault(snapshot.topic_id, snapshot)
        return latest

    def _future_snapshots(
        self,
        *,
        baselines: dict[str, TopicSnapshot],
        checkpoint_at: datetime,
        evaluation_as_of: datetime,
        horizon_days: int,
    ) -> dict[str, list[TopicSnapshot]]:
        return collect_lineage_followups(
            self._session,
            baselines=baselines,
            checkpoint_at=checkpoint_at,
            evaluation_as_of=evaluation_as_of,
            horizon_days=horizon_days,
        )

    @staticmethod
    def _label_one(
        *,
        checkpoint: BacktestCheckpoint,
        baseline: TopicSnapshot,
        future_snapshots: list[TopicSnapshot],
        evaluation_as_of: datetime,
        policy: OutcomeLabelPolicy,
        created_at: datetime,
    ) -> BacktestOutcome:
        checkpoint_at = _aware(checkpoint.checkpoint_at)
        horizon_end = checkpoint_at + timedelta(days=policy.horizon_days)
        baseline_supply = max(baseline.video_count_72h, 1)

        def supply_ratio(snapshot: TopicSnapshot) -> float:
            return snapshot.video_count_72h / baseline_supply

        first_fired = next(
            (
                snapshot
                for snapshot in future_snapshots
                if supply_ratio(snapshot) >= policy.supply_growth_threshold
                and snapshot.median_outlier_ratio >= policy.lift_threshold
            ),
            None,
        )
        peak_supply_snapshot = max(
            future_snapshots,
            key=lambda row: (supply_ratio(row), _aware(row.observed_at), row.id),
            default=None,
        )
        peak_lift_snapshot = max(
            future_snapshots,
            key=lambda row: (row.median_outlier_ratio, _aware(row.observed_at), row.id),
            default=None,
        )
        max_supply_ratio = (
            max(supply_ratio(snapshot) for snapshot in future_snapshots)
            if future_snapshots
            else 0.0
        )
        peak_lift = (
            max(snapshot.median_outlier_ratio for snapshot in future_snapshots)
            if future_snapshots
            else 0.0
        )
        latest_future = future_snapshots[-1] if future_snapshots else None
        negative_coverage_floor = horizon_end - timedelta(days=policy.negative_followup_grace_days)
        if first_fired is not None:
            status = "evaluated"
            fired = True
        elif evaluation_as_of < horizon_end:
            status = "insufficient_followup"
            fired = False
        elif latest_future is None or _aware(latest_future.observed_at) < negative_coverage_floor:
            status = "insufficient_evidence"
            fired = False
        else:
            status = "evaluated"
            fired = False

        def snapshot_ref(snapshot: TopicSnapshot | None) -> dict[str, Any] | None:
            if snapshot is None:
                return None
            return {
                "id": snapshot.id,
                "lift": snapshot.median_outlier_ratio,
                "observed_at": _aware(snapshot.observed_at).isoformat(),
                "supply_72h": snapshot.video_count_72h,
                "supply_growth_ratio": round(supply_ratio(snapshot), 4),
                "topic_id": snapshot.topic_id,
            }

        baseline_identity = snapshot_topic_identity(baseline)
        observed_topic_ids = followup_topic_ids(future_snapshots)
        evidence = {
            "baseline": {
                "id": baseline.id,
                "identity": baseline_identity,
                "lift": baseline.median_outlier_ratio,
                "observed_at": _aware(baseline.observed_at).isoformat(),
                "supply_72h": baseline.video_count_72h,
                "topic_id": baseline.topic_id,
            },
            "blind_label": True,
            "candidate_key": baseline.topic_id,
            "checkpoint_at": checkpoint_at.isoformat(),
            "evaluation_as_of": evaluation_as_of.isoformat(),
            "first_firing_snapshot": snapshot_ref(first_fired),
            "followup_observation_count": len(future_snapshots),
            "followup_topic_ids": observed_topic_ids,
            "horizon_end": horizon_end.isoformat(),
            "latest_followup_snapshot": snapshot_ref(latest_future),
            "peak_lift_snapshot": snapshot_ref(peak_lift_snapshot),
            "peak_supply_snapshot": snapshot_ref(peak_supply_snapshot),
            "prediction_fields_read": False,
            "lineage_resolution": {
                "snapshot_identity_available": baseline_identity is not None,
                "successor_topic_used": any(
                    topic_id != baseline.topic_id for topic_id in observed_topic_ids
                ),
                "version": "snapshot-identity-and-stored-edge-v1",
            },
            "status": status,
            "thresholds": {
                "lift": policy.lift_threshold,
                "negative_followup_grace_days": policy.negative_followup_grace_days,
                "supply_growth": policy.supply_growth_threshold,
            },
        }
        return BacktestOutcome(
            id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"earlysignal:backtest-outcome:{checkpoint.id}:{baseline.topic_id}:{policy.label_version}",
                )
            ),
            checkpoint_id=checkpoint.id,
            candidate_key=baseline.topic_id,
            status=status,
            fired=fired,
            label_method=policy.label_version,
            supply_growth_ratio=round(max_supply_ratio, 4),
            peak_lift=round(peak_lift, 4),
            fired_at=_aware(first_fired.observed_at) if first_fired is not None else None,
            horizon_end=horizon_end,
            evaluation_as_of=evaluation_as_of,
            evidence_json=evidence,
            evidence_hash=_canonical_hash(evidence),
            created_at=created_at,
        )

    def _persist(
        self,
        checkpoint: BacktestCheckpoint,
        outcomes: list[BacktestOutcome],
    ) -> None:
        existing = {
            row.candidate_key: row
            for row in self._session.scalars(
                select(BacktestOutcome).where(BacktestOutcome.checkpoint_id == checkpoint.id)
            )
        }
        for requested in outcomes:
            current = existing.get(requested.candidate_key)
            if current is None:
                self._session.add(requested)
                continue
            if current.evidence_hash == requested.evidence_hash:
                continue
            if current.status == "evaluated":
                raise RuntimeError(
                    "Evaluated outcomes are immutable; use a new checkpoint or label version"
                )
            if _aware(requested.evaluation_as_of) < _aware(current.evaluation_as_of):
                raise RuntimeError("Outcome follow-up cannot move backwards in time")
            current.status = requested.status
            current.fired = requested.fired
            current.label_method = requested.label_method
            current.supply_growth_ratio = requested.supply_growth_ratio
            current.peak_lift = requested.peak_lift
            current.fired_at = requested.fired_at
            current.horizon_end = requested.horizon_end
            current.evaluation_as_of = requested.evaluation_as_of
            current.evidence_json = requested.evidence_json
            current.evidence_hash = requested.evidence_hash
        self._session.commit()


__all__ = [
    "OUTCOME_LABEL_VERSION",
    "BlindOutcomeLabeler",
    "OutcomeLabelPolicy",
]
