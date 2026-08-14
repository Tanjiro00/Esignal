from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import inspect, or_, select, text, union
from sqlalchemy.orm import Session, aliased

from apps.api.models import (
    BacktestCheckpoint,
    BacktestRun,
    DiscoveryRun,
    FieldProvenance,
    ProviderFetch,
    RawApiSnapshot,
    RawPayloadLink,
    VideoDiscoveryOccurrence,
    VideoSnapshot,
    VideoSnapshotJob,
    VideoTranscript,
    YoutubeComment,
    YoutubeVideo,
)
from packages.evaluation import code_model_versions

CHECKPOINT_MANIFEST_VERSION = "point-in-time-checkpoint-v1"
TEMPORAL_POLICY_VERSION = "as-of-evidence-policy-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat().replace("+00:00", "Z")


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _payload_hash(payload: dict[str, Any]) -> str:
    return sha256(_canonical_bytes(payload)).hexdigest()


def checkpoint_content_hash(payload: dict[str, Any]) -> str:
    unhashed = {key: value for key, value in payload.items() if key != "content_sha256"}
    return _payload_hash(unhashed)


def verify_checkpoint_content_hash(payload: dict[str, Any]) -> bool:
    expected = payload.get("content_sha256")
    return isinstance(expected, str) and expected == checkpoint_content_hash(payload)


@dataclass(frozen=True)
class AsOfContext:
    as_of: datetime
    source_kind: Literal["live", "demo"] = "live"
    allowed_providers: tuple[str, ...] = ()
    include_comments: bool = True
    include_transcripts: bool = True
    temporal_policy_version: str = TEMPORAL_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        if self.source_kind not in {"live", "demo"}:
            raise ValueError("source_kind must be live or demo")
        normalized_providers = tuple(
            sorted({provider.strip() for provider in self.allowed_providers if provider.strip()})
        )
        object.__setattr__(self, "as_of", self.as_of.astimezone(UTC))
        object.__setattr__(self, "allowed_providers", normalized_providers)

    def includes(self, observed_at: datetime) -> bool:
        return _aware(observed_at) <= self.as_of

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed_providers": list(self.allowed_providers),
            "as_of": _iso(self.as_of),
            "include_comments": self.include_comments,
            "include_transcripts": self.include_transcripts,
            "source_kind": self.source_kind,
            "temporal_policy_version": self.temporal_policy_version,
        }


class _DigestAccumulator:
    def __init__(self) -> None:
        self._hash = sha256()
        self.count = 0
        self.first_observed_at: datetime | None = None
        self.last_observed_at: datetime | None = None

    def add(self, payload: dict[str, Any], *, observed_at: datetime | None = None) -> None:
        encoded = _canonical_bytes(payload)
        self._hash.update(len(encoded).to_bytes(8, "big"))
        self._hash.update(encoded)
        self.count += 1
        if observed_at is None:
            return
        observed = _aware(observed_at)
        if self.first_observed_at is None or observed < self.first_observed_at:
            self.first_observed_at = observed
        if self.last_observed_at is None or observed > self.last_observed_at:
            self.last_observed_at = observed

    def result(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "first_observed_at": _iso(self.first_observed_at),
            "last_observed_at": _iso(self.last_observed_at),
            "sha256": self._hash.hexdigest(),
        }


def _database_revision(session: Session) -> str | None:
    bind = session.get_bind()
    if not inspect(bind).has_table("alembic_version"):
        return None
    revision = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return str(revision) if revision is not None else None


def _repository_state() -> dict[str, Any]:
    revision = "uncommitted"
    dirty = True
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        revision = completed.stdout.strip() or "uncommitted"
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        dirty = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    root = Path(__file__).resolve().parents[2]
    source_paths = sorted(
        {
            *(
                path
                for base in ("apps", "packages", "migrations")
                for path in root.glob(f"{base}/**/*.py")
            ),
            *(root / filename for filename in ("pyproject.toml", "uv.lock")),
        }
    )
    working_tree = sha256()
    for path in source_paths:
        if not path.is_file():
            continue
        relative = str(path.relative_to(root)).encode()
        content = path.read_bytes()
        working_tree.update(len(relative).to_bytes(8, "big"))
        working_tree.update(relative)
        working_tree.update(len(content).to_bytes(8, "big"))
        working_tree.update(content)
    return {
        "dirty": dirty,
        "revision": revision,
        "working_tree_sha256": working_tree.hexdigest(),
    }


class PointInTimeCheckpointService:
    """Build immutable manifests from evidence that existed by a cutoff.

    Derived tables are deliberately excluded from the input hash. Later slices
    replay features, clustering, scoring, and fit from these source-evidence
    manifests rather than trusting mutable present-day derived rows.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _video_source_clause(context: AsOfContext) -> Any:
        if context.source_kind == "demo":
            return YoutubeVideo.youtube_video_id.startswith("esdemo")
        return ~YoutubeVideo.youtube_video_id.startswith("esdemo")

    @staticmethod
    def _provider_clause(context: AsOfContext, provider_column: Any) -> Any | None:
        if not context.allowed_providers:
            return None
        return provider_column.in_(context.allowed_providers)

    def _eligible_entity_ids(self, context: AsOfContext) -> Any:
        return select(YoutubeVideo.id).where(
            self._video_source_clause(context),
            YoutubeVideo.first_discovered_at <= context.as_of,
        )

    def _relevant_fetch_ids(self, context: AsOfContext) -> Any:
        eligible_entities = self._eligible_entity_ids(context)
        linked = select(RawPayloadLink.provider_fetch_id).where(
            RawPayloadLink.entity_id.in_(eligible_entities)
        )
        occurrences = (
            select(VideoDiscoveryOccurrence.provider_fetch_id)
            .join(YoutubeVideo, YoutubeVideo.id == VideoDiscoveryOccurrence.video_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                VideoDiscoveryOccurrence.discovered_at <= context.as_of,
            )
        )
        snapshots = (
            select(VideoSnapshot.provider_fetch_id)
            .join(YoutubeVideo, YoutubeVideo.id == VideoSnapshot.video_id)
            .where(
                self._video_source_clause(context),
                VideoSnapshot.provider_fetch_id.is_not(None),
                VideoSnapshot.observed_at <= context.as_of,
            )
        )
        comments = (
            select(YoutubeComment.provider_fetch_id)
            .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
            .where(
                self._video_source_clause(context),
                YoutubeComment.provider_fetch_id.is_not(None),
                YoutubeComment.created_at <= context.as_of,
            )
        )
        transcripts = (
            select(VideoTranscript.provider_fetch_id)
            .join(YoutubeVideo, YoutubeVideo.id == VideoTranscript.video_id)
            .where(
                self._video_source_clause(context),
                VideoTranscript.provider_fetch_id.is_not(None),
                VideoTranscript.fetched_at <= context.as_of,
            )
        )
        return union(linked, occurrences, snapshots, comments, transcripts)

    def _provider_fetches(self, context: AsOfContext) -> dict[str, Any]:
        statement = select(ProviderFetch).where(
            ProviderFetch.id.in_(self._relevant_fetch_ids(context)),
            ProviderFetch.completed_at <= context.as_of,
        )
        if not context.include_comments:
            statement = statement.where(ProviderFetch.capability != "comments")
        if not context.include_transcripts:
            statement = statement.where(ProviderFetch.capability != "transcripts")
        provider_clause = self._provider_clause(context, ProviderFetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.scalars(statement.order_by(ProviderFetch.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row in rows:
            digest.add(
                {
                    "attempt_number": row.attempt_number,
                    "capability": row.capability,
                    "completed_at": _iso(row.completed_at),
                    "endpoint": row.endpoint,
                    "http_status": row.http_status,
                    "id": row.id,
                    "parser_version": row.parser_version,
                    "provider": row.provider,
                    "raw_payload_hash": row.raw_payload_hash,
                    "request_fingerprint": row.request_fingerprint,
                    "status": row.status,
                },
                observed_at=row.completed_at,
            )
        return digest.result()

    def _raw_payload_links(self, context: AsOfContext) -> dict[str, Any]:
        statement = (
            select(RawPayloadLink, ProviderFetch.completed_at)
            .join(ProviderFetch, ProviderFetch.id == RawPayloadLink.provider_fetch_id)
            .where(
                RawPayloadLink.entity_id.in_(self._eligible_entity_ids(context)),
                ProviderFetch.completed_at <= context.as_of,
            )
        )
        if not context.include_comments:
            statement = statement.where(ProviderFetch.capability != "comments")
        if not context.include_transcripts:
            statement = statement.where(ProviderFetch.capability != "transcripts")
        provider_clause = self._provider_clause(context, ProviderFetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(
            statement.order_by(
                RawPayloadLink.provider_fetch_id,
                RawPayloadLink.entity_type,
                RawPayloadLink.entity_id,
            )
        ).yield_per(1_000)
        digest = _DigestAccumulator()
        for row, completed_at in rows:
            digest.add(
                {
                    "entity_id": row.entity_id,
                    "entity_type": row.entity_type,
                    "provider_fetch_id": row.provider_fetch_id,
                },
                observed_at=completed_at,
            )
        return digest.result()

    def _raw_api_snapshots(self, context: AsOfContext) -> dict[str, Any]:
        statement = (
            select(RawApiSnapshot)
            .join(YoutubeVideo, YoutubeVideo.id == RawApiSnapshot.video_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                RawApiSnapshot.fetched_at <= context.as_of,
            )
        )
        provider_clause = self._provider_clause(context, RawApiSnapshot.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.scalars(statement.order_by(RawApiSnapshot.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row in rows:
            digest.add(
                {
                    "expires_at": _iso(row.expires_at),
                    "fetched_at": _iso(row.fetched_at),
                    "id": row.id,
                    "payload_sha256": _payload_hash(dict(row.payload)),
                    "provenance_sha256": _payload_hash(dict(row.provenance)),
                    "provider": row.provider,
                    "video_id": row.video_id,
                },
                observed_at=row.fetched_at,
            )
        return digest.result()

    def _videos(self, context: AsOfContext) -> dict[str, Any]:
        statement = (
            select(YoutubeVideo)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
            )
            .order_by(YoutubeVideo.id)
        )
        rows = self._session.scalars(statement).yield_per(1_000)
        digest = _DigestAccumulator()
        for row in rows:
            digest.add(
                {
                    "first_discovered_at": _iso(row.first_discovered_at),
                    "id": row.id,
                    "youtube_video_id": row.youtube_video_id,
                },
                observed_at=row.first_discovered_at,
            )
        return digest.result()

    def _discovery_runs(self, context: AsOfContext) -> dict[str, Any]:
        statement = select(DiscoveryRun).where(
            DiscoveryRun.started_at <= context.as_of,
            DiscoveryRun.completed_at.is_not(None),
            DiscoveryRun.completed_at <= context.as_of,
        )
        if context.source_kind == "demo":
            statement = statement.where(DiscoveryRun.provider.startswith("mock"))
        else:
            statement = statement.where(~DiscoveryRun.provider.startswith("mock"))
        provider_clause = self._provider_clause(context, DiscoveryRun.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.scalars(statement.order_by(DiscoveryRun.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row in rows:
            digest.add(
                {
                    "channel_id": row.channel_id,
                    "completed_at": _iso(row.completed_at),
                    "id": row.id,
                    "provider": row.provider,
                    "query_id": row.query_id,
                    "result_count": row.result_count,
                    "retained_video_count": row.retained_video_count,
                    "status": row.status,
                    "unique_video_count": row.unique_video_count,
                },
                observed_at=row.completed_at,
            )
        return digest.result()

    def _discovery_occurrences(self, context: AsOfContext) -> dict[str, Any]:
        statement = (
            select(VideoDiscoveryOccurrence, ProviderFetch.completed_at)
            .join(YoutubeVideo, YoutubeVideo.id == VideoDiscoveryOccurrence.video_id)
            .join(ProviderFetch, ProviderFetch.id == VideoDiscoveryOccurrence.provider_fetch_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                VideoDiscoveryOccurrence.discovered_at <= context.as_of,
                ProviderFetch.completed_at <= context.as_of,
            )
        )
        provider_clause = self._provider_clause(context, ProviderFetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(statement.order_by(VideoDiscoveryOccurrence.id)).yield_per(
            1_000
        )
        digest = _DigestAccumulator()
        for row, _completed_at in rows:
            digest.add(
                {
                    "discovered_at": _iso(row.discovered_at),
                    "id": row.id,
                    "position": row.position,
                    "provider_fetch_id": row.provider_fetch_id,
                    "query_id": row.query_id,
                    "video_id": row.video_id,
                },
                observed_at=row.discovered_at,
            )
        return digest.result()

    def _snapshots(self, context: AsOfContext) -> tuple[dict[str, Any], dict[str, Any]]:
        fetch = aliased(ProviderFetch)
        statement = (
            select(VideoSnapshot, fetch.provider, fetch.completed_at)
            .join(YoutubeVideo, YoutubeVideo.id == VideoSnapshot.video_id)
            .outerjoin(fetch, fetch.id == VideoSnapshot.provider_fetch_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                VideoSnapshot.observed_at <= context.as_of,
                or_(
                    VideoSnapshot.provider_fetch_id.is_(None),
                    fetch.completed_at <= context.as_of,
                ),
            )
        )
        provider_clause = self._provider_clause(context, fetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(
            statement.order_by(VideoSnapshot.video_id, VideoSnapshot.observed_at, VideoSnapshot.id)
        ).yield_per(1_000)
        digest = _DigestAccumulator()
        video_ids: set[str] = set()
        quality_counts: Counter[str] = Counter()
        estimated_count = 0
        for row, provider, _completed_at in rows:
            digest.add(
                {
                    "comment_count": row.comment_count,
                    "id": row.id,
                    "is_estimated": row.is_estimated,
                    "like_count": row.like_count,
                    "observed_at": _iso(row.observed_at),
                    "provider": provider,
                    "provider_fetch_id": row.provider_fetch_id,
                    "snapshot_quality": row.snapshot_quality,
                    "video_age_seconds": row.video_age_seconds,
                    "video_id": row.video_id,
                    "view_count": row.view_count,
                },
                observed_at=row.observed_at,
            )
            video_ids.add(row.video_id)
            quality_counts[row.snapshot_quality] += 1
            estimated_count += int(row.is_estimated)
        coverage = {
            "estimated_snapshot_count": estimated_count,
            "quality_counts": dict(sorted(quality_counts.items())),
            "videos_with_snapshot": len(video_ids),
        }
        return digest.result(), coverage

    def _snapshot_jobs(self, context: AsOfContext) -> tuple[dict[str, Any], dict[str, int]]:
        statement = (
            select(VideoSnapshotJob)
            .join(YoutubeVideo, YoutubeVideo.id == VideoSnapshotJob.video_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                VideoSnapshotJob.completed_at.is_not(None),
                VideoSnapshotJob.completed_at <= context.as_of,
            )
            .order_by(
                VideoSnapshotJob.video_id,
                VideoSnapshotJob.scheduled_age_seconds,
            )
        )
        rows = self._session.scalars(statement).yield_per(1_000)
        digest = _DigestAccumulator()
        successful_by_age: Counter[int] = Counter()
        for row in rows:
            digest.add(
                {
                    "completed_at": _iso(row.completed_at),
                    "id": row.id,
                    "provider_fetch_id": row.provider_fetch_id,
                    "scheduled_age_seconds": row.scheduled_age_seconds,
                    "skip_reason": row.skip_reason,
                    "status": row.status,
                    "video_id": row.video_id,
                },
                observed_at=row.completed_at,
            )
            if row.status == "success":
                successful_by_age[row.scheduled_age_seconds] += 1
        return digest.result(), {
            str(age): count for age, count in sorted(successful_by_age.items())
        }

    def _comments(self, context: AsOfContext) -> dict[str, Any]:
        if not context.include_comments:
            return _DigestAccumulator().result()
        fetch = aliased(ProviderFetch)
        statement = (
            select(YoutubeComment, fetch.provider)
            .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
            .outerjoin(fetch, fetch.id == YoutubeComment.provider_fetch_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                YoutubeComment.published_at <= context.as_of,
                YoutubeComment.created_at <= context.as_of,
                or_(
                    YoutubeComment.provider_fetch_id.is_(None),
                    fetch.completed_at <= context.as_of,
                ),
            )
        )
        provider_clause = self._provider_clause(context, fetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(statement.order_by(YoutubeComment.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row, provider in rows:
            digest.add(
                {
                    "created_at": _iso(row.created_at),
                    "fetched_order": row.fetched_order,
                    "id": row.id,
                    "like_count": row.like_count,
                    "normalized_hash": row.normalized_hash,
                    "provider": provider,
                    "provider_fetch_id": row.provider_fetch_id,
                    "published_at": _iso(row.published_at),
                    "reply_count": row.reply_count,
                    "video_id": row.video_id,
                },
                observed_at=row.created_at,
            )
        return digest.result()

    def _transcripts(self, context: AsOfContext) -> dict[str, Any]:
        if not context.include_transcripts:
            return _DigestAccumulator().result()
        fetch = aliased(ProviderFetch)
        statement = (
            select(VideoTranscript, fetch.provider)
            .join(YoutubeVideo, YoutubeVideo.id == VideoTranscript.video_id)
            .outerjoin(fetch, fetch.id == VideoTranscript.provider_fetch_id)
            .where(
                self._video_source_clause(context),
                YoutubeVideo.first_discovered_at <= context.as_of,
                VideoTranscript.fetched_at <= context.as_of,
                or_(
                    VideoTranscript.provider_fetch_id.is_(None),
                    fetch.completed_at <= context.as_of,
                ),
            )
        )
        provider_clause = self._provider_clause(context, fetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(statement.order_by(VideoTranscript.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row, provider in rows:
            digest.add(
                {
                    "content_hash": row.content_hash,
                    "fetched_at": _iso(row.fetched_at),
                    "id": row.id,
                    "language": row.language,
                    "processing_version": row.processing_version,
                    "provider": provider,
                    "provider_fetch_id": row.provider_fetch_id,
                    "quality_score": row.quality_score,
                    "transcript_type": row.transcript_type,
                    "video_id": row.video_id,
                },
                observed_at=row.fetched_at,
            )
        return digest.result()

    def _field_provenance(self, context: AsOfContext) -> dict[str, Any]:
        statement = (
            select(FieldProvenance, ProviderFetch.completed_at)
            .join(ProviderFetch, ProviderFetch.id == FieldProvenance.provider_fetch_id)
            .where(
                FieldProvenance.entity_id.in_(self._eligible_entity_ids(context)),
                FieldProvenance.observed_at <= context.as_of,
                ProviderFetch.completed_at <= context.as_of,
            )
        )
        provider_clause = self._provider_clause(context, ProviderFetch.provider)
        if provider_clause is not None:
            statement = statement.where(provider_clause)
        rows = self._session.execute(statement.order_by(FieldProvenance.id)).yield_per(1_000)
        digest = _DigestAccumulator()
        for row, _completed_at in rows:
            digest.add(
                {
                    "confidence": row.confidence,
                    "entity_id": row.entity_id,
                    "entity_type": row.entity_type,
                    "field_name": row.field_name,
                    "id": row.id,
                    "observed_at": _iso(row.observed_at),
                    "provider_fetch_id": row.provider_fetch_id,
                    "value_hash": row.value_hash,
                },
                observed_at=row.observed_at,
            )
        return digest.result()

    def build_manifest(
        self,
        context: AsOfContext,
        *,
        source_environment: str,
        repository_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshots, snapshot_coverage = self._snapshots(context)
        snapshot_jobs, successful_jobs_by_age = self._snapshot_jobs(context)
        input_tables = {
            "discovery_occurrences": self._discovery_occurrences(context),
            "discovery_runs": self._discovery_runs(context),
            "field_provenance": self._field_provenance(context),
            "provider_fetches": self._provider_fetches(context),
            "raw_api_snapshots": self._raw_api_snapshots(context),
            "raw_payload_links": self._raw_payload_links(context),
            "snapshot_jobs": snapshot_jobs,
            "video_snapshots": snapshots,
            "videos": self._videos(context),
            "youtube_comments": self._comments(context),
            "video_transcripts": self._transcripts(context),
        }
        versions = code_model_versions()
        input_contract = {
            "context": context.as_dict(),
            "input_tables": input_tables,
            "model_versions": versions,
        }
        manifest: dict[str, Any] = {
            "context": context.as_dict(),
            "database_revision": _database_revision(self._session),
            "derived_tables_policy": {
                "excluded_from_input_hash": [
                    "channel_baselines",
                    "comment_features",
                    "comment_topic_relevance",
                    "demand_clusters",
                    "derived_metric_points",
                    "llm_intelligence_runs",
                    "signals",
                    "topic_snapshots",
                    "topic_video_memberships",
                    "topics",
                    "video_embeddings",
                    "video_features",
                    "workspace_signal_scores",
                ],
                "reason": (
                    "Derived or mutable present-day rows must be recomputed from evidence "
                    "available by the checkpoint cutoff."
                ),
            },
            "eligibility": {
                **snapshot_coverage,
                "successful_snapshot_jobs_by_target_age_seconds": successful_jobs_by_age,
            },
            "input_hash": _payload_hash(input_contract),
            "input_tables": input_tables,
            "limitations": [
                (
                    "Mutable normalized video metadata, including channel and publication "
                    "fields, is not hashed as historical truth; replay must resolve as-of "
                    "values from raw payloads and field provenance."
                ),
                (
                    "Current channel subscriber counters are mutable and are not valid "
                    "point-in-time inputs; historical baselines must be recomputed."
                ),
                (
                    "Backfilled topic snapshots and current memberships are audit artifacts, "
                    "not source evidence for prediction replay."
                ),
            ],
            "manifest_version": CHECKPOINT_MANIFEST_VERSION,
            "model_versions": versions,
            "repository": repository_state or _repository_state(),
            "source_environment": source_environment,
        }
        manifest["content_sha256"] = checkpoint_content_hash(manifest)
        return manifest

    def persist_manifest(
        self,
        manifest: dict[str, Any],
        *,
        name: str,
        recorded_at: datetime | None = None,
    ) -> tuple[BacktestRun, BacktestCheckpoint]:
        if not verify_checkpoint_content_hash(manifest):
            raise ValueError("Checkpoint manifest hash is invalid")
        input_hash = str(manifest["input_hash"])
        idempotency_key = f"backtest-checkpoint:{manifest['content_sha256']}"
        existing = self._session.scalar(
            select(BacktestRun).where(BacktestRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            checkpoint = self._session.scalar(
                select(BacktestCheckpoint).where(BacktestCheckpoint.run_id == existing.id)
            )
            if checkpoint is None:
                raise RuntimeError("Persisted backtest run has no checkpoint")
            return existing, checkpoint

        now = _aware(recorded_at or datetime.now(tz=UTC))
        context = manifest["context"]
        checkpoint_at = datetime.fromisoformat(str(context["as_of"]).replace("Z", "+00:00"))
        repository = manifest["repository"]
        run_id = str(uuid5(NAMESPACE_URL, f"earlysignal:{idempotency_key}"))
        checkpoint_id = str(
            uuid5(NAMESPACE_URL, f"earlysignal:{idempotency_key}:{context['as_of']}")
        )
        revision = str(repository["revision"])
        if revision == "uncommitted" and repository.get("working_tree_sha256"):
            revision = f"tree:{repository['working_tree_sha256']}"
        run = BacktestRun(
            id=run_id,
            idempotency_key=idempotency_key,
            name=name[:160],
            status="success",
            source_kind=str(context["source_kind"]),
            dataset_version=str(manifest["manifest_version"]),
            code_revision=revision[:80],
            code_dirty=bool(repository["dirty"]),
            migration_revision=manifest.get("database_revision"),
            config_json=dict(context),
            model_versions_json=dict(manifest["model_versions"]),
            started_at=now,
            completed_at=now,
            error_code=None,
            error_message=None,
            created_at=now,
        )
        checkpoint = BacktestCheckpoint(
            id=checkpoint_id,
            run_id=run_id,
            checkpoint_at=checkpoint_at,
            status="success",
            manifest_version=str(manifest["manifest_version"]),
            manifest_json=manifest,
            input_hash=input_hash,
            eligible_video_count=int(manifest["input_tables"]["videos"]["count"]),
            snapshot_count=int(manifest["input_tables"]["video_snapshots"]["count"]),
            prediction_count=0,
            completed_at=now,
            created_at=now,
        )
        self._session.add(run)
        self._session.flush()
        self._session.add(checkpoint)
        self._session.commit()
        return run, checkpoint
