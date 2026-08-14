from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestCohort,
    BacktestCohortCheckpoint,
    BacktestOutcome,
    Topic,
    TopicSnapshot,
    VideoSnapshot,
    VideoSnapshotJob,
    YoutubeVideo,
)
from packages.backtest.checkpoint import AsOfContext, PointInTimeCheckpointService
from packages.backtest.harness import ReplayPolicy, TemporalReplayService, load_candidate_universe

COHORT_POLICY_VERSION = "direct-observation-cohort-v1"
COHORT_SPLIT_POLICY_VERSION = "chronological-last-n-holdout-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CohortPolicy:
    checkpoint_count: int = 8
    holdout_count: int = 2
    horizon_days: int = 42
    candidate_days: int = 120
    max_snapshot_age_days: int = 7
    target_age_seconds: int = 86_400
    minimum_eligible_videos: int = 1
    minimum_direct_snapshots: int = 1
    minimum_prediction_candidates: int = 1
    policy_version: str = COHORT_POLICY_VERSION
    split_policy_version: str = COHORT_SPLIT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.checkpoint_count < 2:
            raise ValueError("checkpoint_count must be at least 2")
        if not 0 < self.holdout_count < self.checkpoint_count:
            raise ValueError("holdout_count must be between 1 and checkpoint_count - 1")
        for value in (
            self.horizon_days,
            self.candidate_days,
            self.max_snapshot_age_days,
            self.target_age_seconds,
            self.minimum_eligible_videos,
            self.minimum_direct_snapshots,
            self.minimum_prediction_candidates,
        ):
            if value <= 0:
                raise ValueError("cohort policy numeric values must be positive")


@dataclass(frozen=True)
class CheckpointCoverage:
    checkpoint_at: datetime
    horizon_end: datetime
    eligible_video_count: int
    direct_snapshot_count: int
    videos_with_direct_snapshot: int
    successful_target_age_jobs: int
    topic_candidate_count: int
    prediction_candidate_count: int
    direct_video_coverage_percent: float
    complete_outcome_window: bool
    eligible: bool
    rejection_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checkpoint_at"] = _iso(self.checkpoint_at)
        payload["horizon_end"] = _iso(self.horizon_end)
        payload["rejection_reasons"] = list(self.rejection_reasons)
        return payload


@dataclass(frozen=True)
class FrozenCohortResult:
    cohort_id: str
    dataset_hash: str
    checkpoint_ids: tuple[str, ...]
    train_checkpoint_ids: tuple[str, ...]
    holdout_checkpoint_ids: tuple[str, ...]
    markdown_report: str


class InsufficientCohortData(RuntimeError):
    def __init__(self, required: int, available: int, coverage: list[CheckpointCoverage]) -> None:
        super().__init__(
            f"Only {available} eligible checkpoint dates are available; {required} are required"
        )
        self.required = required
        self.available = available
        self.coverage = coverage


class HistoricalCohortService:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _video_source_clause(source_kind: Literal["live", "demo"]) -> Any:
        if source_kind == "demo":
            return YoutubeVideo.youtube_video_id.startswith("esdemo")
        return ~YoutubeVideo.youtube_video_id.startswith("esdemo")

    def candidate_cutoffs(
        self,
        *,
        freeze_at: datetime,
        source_kind: Literal["live", "demo"],
        candidate_days: int,
    ) -> list[datetime]:
        earliest = _aware(freeze_at) - timedelta(days=candidate_days)
        rows = self._session.execute(
            select(
                func.date(TopicSnapshot.observed_at).label("observed_date"),
                func.max(TopicSnapshot.observed_at).label("checkpoint_at"),
            )
            .join(Topic, Topic.id == TopicSnapshot.topic_id)
            .where(
                Topic.source_kind == source_kind,
                TopicSnapshot.observed_at >= earliest,
                TopicSnapshot.observed_at <= _aware(freeze_at),
            )
            .group_by(func.date(TopicSnapshot.observed_at))
            .order_by(func.date(TopicSnapshot.observed_at))
        ).all()
        return [_aware(checkpoint_at) for _observed_date, checkpoint_at in rows]

    def coverage_for_checkpoint(
        self,
        *,
        checkpoint_at: datetime,
        freeze_at: datetime,
        source_kind: Literal["live", "demo"],
        policy: CohortPolicy,
    ) -> CheckpointCoverage:
        cutoff = _aware(checkpoint_at)
        source_clause = self._video_source_clause(source_kind)
        eligible_video_ids = select(YoutubeVideo.id).where(
            source_clause,
            YoutubeVideo.first_discovered_at <= cutoff,
        )
        eligible_video_count = int(
            self._session.scalar(select(func.count()).select_from(eligible_video_ids.subquery()))
            or 0
        )
        direct_snapshot_clause = (
            VideoSnapshot.video_id.in_(eligible_video_ids),
            VideoSnapshot.observed_at <= cutoff,
            VideoSnapshot.snapshot_quality == "direct",
            VideoSnapshot.is_estimated.is_(False),
        )
        direct_snapshot_count = int(
            self._session.scalar(
                select(func.count(VideoSnapshot.id)).where(*direct_snapshot_clause)
            )
            or 0
        )
        videos_with_direct_snapshot = int(
            self._session.scalar(
                select(func.count(func.distinct(VideoSnapshot.video_id))).where(
                    *direct_snapshot_clause
                )
            )
            or 0
        )
        successful_target_age_jobs = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(
                    VideoSnapshotJob.video_id.in_(eligible_video_ids),
                    VideoSnapshotJob.scheduled_age_seconds == policy.target_age_seconds,
                    VideoSnapshotJob.status == "success",
                    VideoSnapshotJob.completed_at.is_not(None),
                    VideoSnapshotJob.completed_at <= cutoff,
                )
            )
            or 0
        )
        replay_policy = ReplayPolicy(
            top_k=10,
            max_snapshot_age_days=policy.max_snapshot_age_days,
        )
        candidates = load_candidate_universe(
            self._session,
            checkpoint_at=cutoff,
            source_kind=source_kind,
            policy=replay_policy,
        )
        prediction_candidates = sum(candidate.visible_signal for candidate in candidates)
        reasons: list[str] = []
        if eligible_video_count < policy.minimum_eligible_videos:
            reasons.append("insufficient_eligible_videos")
        if direct_snapshot_count < policy.minimum_direct_snapshots:
            reasons.append("insufficient_direct_snapshots")
        if prediction_candidates < policy.minimum_prediction_candidates:
            reasons.append("insufficient_prediction_candidates")
        horizon_end = cutoff + timedelta(days=policy.horizon_days)
        return CheckpointCoverage(
            checkpoint_at=cutoff,
            horizon_end=horizon_end,
            eligible_video_count=eligible_video_count,
            direct_snapshot_count=direct_snapshot_count,
            videos_with_direct_snapshot=videos_with_direct_snapshot,
            successful_target_age_jobs=successful_target_age_jobs,
            topic_candidate_count=len(candidates),
            prediction_candidate_count=prediction_candidates,
            direct_video_coverage_percent=(
                round(videos_with_direct_snapshot / eligible_video_count * 100, 2)
                if eligible_video_count
                else 0.0
            ),
            complete_outcome_window=_aware(freeze_at) >= horizon_end,
            eligible=not reasons,
            rejection_reasons=tuple(reasons),
        )

    def inspect(
        self,
        *,
        freeze_at: datetime,
        source_kind: Literal["live", "demo"] = "live",
        policy: CohortPolicy | None = None,
        checkpoint_times: list[datetime] | None = None,
    ) -> list[CheckpointCoverage]:
        freeze_cutoff = _aware(freeze_at)
        if freeze_cutoff > datetime.now(tz=UTC):
            raise ValueError(
                "freeze_at cannot be in the future; a cohort may only use evidence "
                "that already exists when inspection starts"
            )
        selected_policy = policy or CohortPolicy()
        cutoffs = checkpoint_times or self.candidate_cutoffs(
            freeze_at=freeze_cutoff,
            source_kind=source_kind,
            candidate_days=selected_policy.candidate_days,
        )
        return [
            self.coverage_for_checkpoint(
                checkpoint_at=cutoff,
                freeze_at=freeze_cutoff,
                source_kind=source_kind,
                policy=selected_policy,
            )
            for cutoff in sorted({_aware(value) for value in cutoffs})
        ]

    @staticmethod
    def select_checkpoints(
        coverage: list[CheckpointCoverage],
        *,
        policy: CohortPolicy,
    ) -> list[CheckpointCoverage]:
        eligible = [row for row in coverage if row.eligible]
        if len(eligible) < policy.checkpoint_count:
            raise InsufficientCohortData(policy.checkpoint_count, len(eligible), coverage)
        return eligible[-policy.checkpoint_count :]

    def freeze(
        self,
        *,
        name: str,
        freeze_at: datetime,
        source_environment: str,
        source_kind: Literal["live", "demo"] = "live",
        policy: CohortPolicy | None = None,
        checkpoint_times: list[datetime] | None = None,
    ) -> FrozenCohortResult:
        selected_policy = policy or CohortPolicy()
        coverage = self.inspect(
            freeze_at=freeze_at,
            source_kind=source_kind,
            policy=selected_policy,
            checkpoint_times=checkpoint_times,
        )
        selected = self.select_checkpoints(coverage, policy=selected_policy)
        manifest_service = PointInTimeCheckpointService(self._session)
        replay_service = TemporalReplayService(self._session)
        checkpoint_rows: list[BacktestCheckpoint] = []
        manifest_hashes: list[str] = []
        prediction_hashes: list[list[str]] = []
        repository: dict[str, Any] | None = None
        for item in selected:
            manifest = manifest_service.build_manifest(
                AsOfContext(as_of=item.checkpoint_at, source_kind=source_kind),
                source_environment=source_environment,
                repository_state=repository,
            )
            repository = dict(manifest["repository"])
            _run, checkpoint = manifest_service.persist_manifest(
                manifest,
                name=f"{name}: {_iso(item.checkpoint_at)}",
                recorded_at=freeze_at,
            )
            if self._session.scalar(
                select(func.count(BacktestOutcome.id)).where(
                    BacktestOutcome.checkpoint_id == checkpoint.id
                )
            ):
                raise RuntimeError("Cannot freeze a prediction cohort after outcomes were opened")
            predictions, _universe = replay_service.replay_checkpoint(
                checkpoint,
                policy=ReplayPolicy(
                    top_k=10,
                    max_snapshot_age_days=selected_policy.max_snapshot_age_days,
                ),
            )
            checkpoint_rows.append(checkpoint)
            manifest_hashes.append(str(manifest["content_sha256"]))
            prediction_hashes.append([row.evidence_hash for row in predictions])

        dataset_contract = {
            "checkpoint_manifest_hashes": manifest_hashes,
            "checkpoint_times": [_iso(row.checkpoint_at) for row in checkpoint_rows],
            "cohort_policy": asdict(selected_policy),
            "prediction_evidence_hashes": prediction_hashes,
            "source_kind": source_kind,
        }
        dataset_hash = _canonical_hash(dataset_contract)
        cohort_id = str(uuid5(NAMESPACE_URL, f"earlysignal:backtest-cohort:{dataset_hash}"))
        existing = self._session.get(BacktestCohort, cohort_id)
        if existing is not None:
            links = list(
                self._session.scalars(
                    select(BacktestCohortCheckpoint)
                    .where(BacktestCohortCheckpoint.cohort_id == existing.id)
                    .order_by(BacktestCohortCheckpoint.ordinal)
                )
            )
            return self._result(existing, links)

        holdout_start = len(checkpoint_rows) - selected_policy.holdout_count
        frozen_at = _aware(freeze_at)
        cohort = BacktestCohort(
            id=cohort_id,
            idempotency_key=f"backtest-cohort:{dataset_hash}",
            name=name[:160],
            status="frozen",
            source_kind=source_kind,
            policy_version=selected_policy.policy_version,
            split_policy_version=selected_policy.split_policy_version,
            horizon_days=selected_policy.horizon_days,
            checkpoint_count=len(checkpoint_rows),
            train_checkpoint_count=holdout_start,
            holdout_checkpoint_count=selected_policy.holdout_count,
            dataset_hash=dataset_hash,
            coverage_json={
                "all_candidates": [row.as_dict() for row in coverage],
                "limitations": [
                    "No checkpoint has a complete 42-day outcome window yet.",
                    "Current replay uses historically recorded topic scores; full raw "
                    "re-clustering is a stricter future validation layer.",
                    "Historical channel-size strata are unavailable because subscriber "
                    "counts were not snapshotted point-in-time.",
                ],
                "selected": [row.as_dict() for row in selected],
            },
            repository_json=repository or {},
            frozen_at=frozen_at,
            created_at=frozen_at,
        )
        links = [
            BacktestCohortCheckpoint(
                cohort_id=cohort_id,
                checkpoint_id=checkpoint.id,
                ordinal=index + 1,
                split="train" if index < holdout_start else "holdout",
                checkpoint_at=_aware(checkpoint.checkpoint_at),
                horizon_end=_aware(checkpoint.checkpoint_at)
                + timedelta(days=selected_policy.horizon_days),
                outcome_ready_at=_aware(checkpoint.checkpoint_at)
                + timedelta(days=selected_policy.horizon_days),
                coverage_json=selected[index].as_dict(),
                frozen_at=frozen_at,
            )
            for index, checkpoint in enumerate(checkpoint_rows)
        ]
        self._session.add(cohort)
        self._session.flush()
        self._session.add_all(links)
        self._session.commit()
        return self._result(cohort, links)

    @staticmethod
    def _result(
        cohort: BacktestCohort,
        links: list[BacktestCohortCheckpoint],
    ) -> FrozenCohortResult:
        ordered = sorted(links, key=lambda item: item.ordinal)
        markdown = render_cohort_markdown(cohort=cohort, links=ordered)
        return FrozenCohortResult(
            cohort_id=cohort.id,
            dataset_hash=cohort.dataset_hash,
            checkpoint_ids=tuple(row.checkpoint_id for row in ordered),
            train_checkpoint_ids=tuple(
                row.checkpoint_id for row in ordered if row.split == "train"
            ),
            holdout_checkpoint_ids=tuple(
                row.checkpoint_id for row in ordered if row.split == "holdout"
            ),
            markdown_report=markdown,
        )


def render_cohort_markdown(
    *,
    cohort: BacktestCohort,
    links: list[BacktestCohortCheckpoint],
) -> str:
    complete = sum(bool(row.coverage_json.get("complete_outcome_window")) for row in links)
    rows = [
        "# EarlySignal frozen historical cohort",
        "",
        f"**Cohort:** {cohort.name}",
        f"**Status:** {cohort.status.upper()}",
        f"**Dataset hash:** `{cohort.dataset_hash}`",
        f"**Checkpoints:** {cohort.checkpoint_count}",
        f"**Train / holdout:** {cohort.train_checkpoint_count} / {cohort.holdout_checkpoint_count}",
        f"**Complete 42-day outcomes:** {complete}/{cohort.checkpoint_count}",
        "",
        "| # | Split | Checkpoint | Outcome ready | Direct video coverage | Predictions |",
        "|---:|---|---|---|---:|---:|",
    ]
    for link in links:
        coverage = link.coverage_json
        rows.append(
            f"| {link.ordinal} | {link.split} | {_iso(link.checkpoint_at)} | "
            f"{_iso(link.outcome_ready_at)} | "
            f"{coverage.get('direct_video_coverage_percent', 0)}% | "
            f"{coverage.get('prediction_candidate_count', 0)} |"
        )
    rows.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Predictions are frozen before blind outcomes are evaluated.",
            "- The last checkpoints are holdout and must not be used for threshold tuning.",
            "- No quality claim is allowed until the 42-day windows mature.",
            "- Historical search cannot reconstruct views-at-age and is not accepted as "
            "direct point-in-time evidence.",
            "- The current replay uses recorded topic scores; full raw re-clustering remains "
            "a stricter validation layer.",
            "",
        ]
    )
    return "\n".join(rows)


__all__ = [
    "COHORT_POLICY_VERSION",
    "COHORT_SPLIT_POLICY_VERSION",
    "CheckpointCoverage",
    "CohortPolicy",
    "FrozenCohortResult",
    "HistoricalCohortService",
    "InsufficientCohortData",
    "render_cohort_markdown",
]
