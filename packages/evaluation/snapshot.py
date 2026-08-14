from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import distinct, inspect, select, text
from sqlalchemy.orm import Session

from apps.api.models import (
    ChannelBaseline,
    CommentFeature,
    DemandCluster,
    Signal,
    Topic,
    TopicSnapshot,
    TopicVideoMembership,
    VideoEmbedding,
    VideoFeature,
    VideoTranscript,
    WorkspaceSignalScore,
    YoutubeVideo,
)
from apps.worker.demand_intelligence import DEMAND_CLUSTERING_VERSION
from apps.worker.digests import DIGEST_VERSION
from apps.worker.topic_intelligence import CLUSTERING_VERSION, SCORING_VERSION
from apps.worker.video_intelligence import BASELINE_VERSION, FEATURE_VERSION
from packages.channel_fit import FIT_VERSION
from packages.clustering import EMBEDDING_MODEL, EMBEDDING_VERSION
from packages.demand import CLASSIFIER_VERSION
from packages.transcripts import PROCESSING_VERSION

FIXTURE_VERSION = "earlysignal-evaluation-snapshot-v1"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _distinct_strings(session: Session, column: Any) -> list[str]:
    values = session.scalars(select(distinct(column)).where(column.is_not(None)))
    return sorted(str(value) for value in values)


def code_model_versions() -> dict[str, str]:
    """Versions that define the current deterministic production behavior."""

    return {
        "channel_baseline": BASELINE_VERSION,
        "channel_fit": FIT_VERSION,
        "comment_demand_classifier": CLASSIFIER_VERSION,
        "demand_clustering": DEMAND_CLUSTERING_VERSION,
        "digest": DIGEST_VERSION,
        "early_signal_score": SCORING_VERSION,
        "microtopic_clustering": CLUSTERING_VERSION,
        "transcript_processing": PROCESSING_VERSION,
        "video_embedding": EMBEDDING_VERSION,
        "video_embedding_model": EMBEDDING_MODEL,
        "video_features": FEATURE_VERSION,
    }


def _database_revision(session: Session) -> str | None:
    bind = session.get_bind()
    if not inspect(bind).has_table("alembic_version"):
        return None
    revision = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return str(revision) if revision is not None else None


def _observed_model_versions(session: Session) -> dict[str, list[str]]:
    return {
        "channel_baseline": _distinct_strings(session, ChannelBaseline.version),
        "channel_fit": _distinct_strings(session, WorkspaceSignalScore.fit_version),
        "comment_features": _distinct_strings(session, CommentFeature.model_version),
        "demand_clusters": _distinct_strings(session, DemandCluster.model_version),
        "signal_evidence": _distinct_strings(session, Signal.evidence_version),
        "topic_clustering": _distinct_strings(session, Topic.clustering_version),
        "topic_embedding": _distinct_strings(session, Topic.embedding_version),
        "topic_embedding_model": _distinct_strings(session, Topic.embedding_model),
        "transcripts": _distinct_strings(session, VideoTranscript.processing_version),
        "video_embeddings": _distinct_strings(session, VideoEmbedding.embedding_version),
        "video_features": _distinct_strings(session, VideoFeature.feature_version),
    }


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def snapshot_content_hash(payload: dict[str, Any]) -> str:
    unhashed = {key: value for key, value in payload.items() if key != "content_sha256"}
    return sha256(_canonical_bytes(unhashed)).hexdigest()


def verify_snapshot_content_hash(payload: dict[str, Any]) -> bool:
    expected = payload.get("content_sha256")
    return isinstance(expected, str) and expected == snapshot_content_hash(payload)


def build_evaluation_snapshot(
    session: Session,
    *,
    captured_at: datetime,
    source_kind: str,
    source_environment: str,
) -> dict[str, Any]:
    """Build a point-in-time, evidence-safe regression snapshot.

    The export intentionally excludes raw comments, commenter hashes, provider
    payloads, and credentials. Stable IDs are retained so future evaluations can
    resolve every aggregate back to stored evidence.
    """

    topics = list(
        session.scalars(
            select(Topic)
            .where(
                Topic.source_kind == source_kind,
                Topic.status == "active",
            )
            .order_by(Topic.canonical_label, Topic.id)
        )
    )
    topic_ids = [topic.id for topic in topics]

    snapshots_by_topic: dict[str, TopicSnapshot] = {}
    memberships_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    demand_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    signals_by_topic: dict[str, Signal] = {}
    scores_by_signal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    transcript_video_ids: set[str] = set()

    if topic_ids:
        snapshot_rows = session.scalars(
            select(TopicSnapshot)
            .where(TopicSnapshot.topic_id.in_(topic_ids))
            .order_by(TopicSnapshot.topic_id, TopicSnapshot.observed_at, TopicSnapshot.id)
        )
        for row in snapshot_rows:
            snapshots_by_topic[row.topic_id] = row

        membership_rows = session.execute(
            select(TopicVideoMembership, YoutubeVideo.channel_id)
            .join(YoutubeVideo, YoutubeVideo.id == TopicVideoMembership.video_id)
            .where(TopicVideoMembership.topic_id.in_(topic_ids))
            .order_by(
                TopicVideoMembership.topic_id,
                TopicVideoMembership.video_id,
            )
        )
        for membership, channel_id in membership_rows:
            memberships_by_topic[membership.topic_id].append(
                {
                    "assignment_method": membership.assignment_method,
                    "channel_id": channel_id,
                    "evidence_role": membership.evidence_role,
                    "membership_score": membership.membership_score,
                    "video_id": membership.video_id,
                }
            )

        evidence_video_ids = sorted(
            {
                membership["video_id"]
                for memberships in memberships_by_topic.values()
                for membership in memberships
            }
        )
        if evidence_video_ids:
            transcript_video_ids = set(
                session.scalars(
                    select(VideoTranscript.video_id).where(
                        VideoTranscript.video_id.in_(evidence_video_ids)
                    )
                )
            )

        demand_rows = session.scalars(
            select(DemandCluster)
            .where(DemandCluster.topic_id.in_(topic_ids))
            .order_by(DemandCluster.topic_id, DemandCluster.id)
        )
        for cluster in demand_rows:
            demand_by_topic[cluster.topic_id].append(
                {
                    "comment_count": cluster.comment_count,
                    "demand_score": cluster.demand_score,
                    "distinct_channels": cluster.distinct_channel_count,
                    "distinct_commenters": cluster.distinct_commenter_count,
                    "distinct_videos": cluster.distinct_video_count,
                    "id": cluster.id,
                    "label": cluster.label,
                    "model_version": cluster.model_version,
                    "taxonomy": cluster.taxonomy,
                }
            )

        signals = session.scalars(
            select(Signal)
            .where(
                Signal.topic_id.in_(topic_ids),
                Signal.source_kind == source_kind,
                Signal.status == "active",
            )
            .order_by(Signal.id)
        )
        for signal_row in signals:
            signals_by_topic[signal_row.topic_id] = signal_row

        signal_ids = sorted(signal_row.id for signal_row in signals_by_topic.values())
        if signal_ids:
            score_rows = session.scalars(
                select(WorkspaceSignalScore)
                .where(WorkspaceSignalScore.signal_id.in_(signal_ids))
                .order_by(
                    WorkspaceSignalScore.signal_id,
                    WorkspaceSignalScore.workspace_id,
                )
            )
            for score in score_rows:
                scores_by_signal[score.signal_id].append(
                    {
                        "calculated_at": _iso(score.calculated_at),
                        "channel_fit_score": score.channel_fit_score,
                        "channel_id": score.channel_id,
                        "fit_components": score.fit_component_json,
                        "fit_version": score.fit_version,
                        "opportunities": score.recommended_angle_json,
                        "workspace_id": score.workspace_id,
                    }
                )

    topic_records: list[dict[str, Any]] = []
    for topic in topics:
        memberships = memberships_by_topic[topic.id]
        latest = snapshots_by_topic.get(topic.id)
        topic_signal = signals_by_topic.get(topic.id)
        signal_record = (
            {
                "components": topic_signal.component_json,
                "confidence": topic_signal.confidence,
                "evidence_version": topic_signal.evidence_version,
                "expires_at": _iso(topic_signal.expires_at),
                "generated_at": _iso(topic_signal.generated_at),
                "id": topic_signal.id,
                "lifecycle_stage": topic_signal.lifecycle_stage,
                "opportunity_end": _iso(topic_signal.opportunity_end),
                "opportunity_start": _iso(topic_signal.opportunity_start),
                "score": topic_signal.score,
                "status": topic_signal.status,
                "thesis": topic_signal.thesis,
                "why_emerging": topic_signal.why_emerging_json,
                "workspace_scores": scores_by_signal[topic_signal.id],
            }
            if topic_signal is not None
            else None
        )
        latest_record = (
            {
                "aggregate_view_velocity": latest.aggregate_view_velocity,
                "components": latest.component_json,
                "demand_score": latest.demand_score,
                "distinct_channels_72h": latest.distinct_channels_72h,
                "fragility_score": latest.fragility_score,
                "id": latest.id,
                "large_channel_count": latest.large_channel_count,
                "median_outlier_ratio": latest.median_outlier_ratio,
                "observed_at": _iso(latest.observed_at),
                "saturation_score": latest.saturation_score,
                "video_count_24h": latest.video_count_24h,
                "video_count_72h": latest.video_count_72h,
            }
            if latest is not None
            else None
        )
        topic_records.append(
            {
                "aliases": topic.aliases_json,
                "canonical_label": topic.canonical_label,
                "clustering_version": topic.clustering_version,
                "demand_clusters": demand_by_topic[topic.id],
                "embedding_model": topic.embedding_model,
                "embedding_version": topic.embedding_version,
                "entities": topic.entities_json,
                "evidence": {
                    "distinct_channels": len(
                        {membership["channel_id"] for membership in memberships}
                    ),
                    "memberships": memberships,
                    "transcript_videos": sum(
                        membership["video_id"] in transcript_video_ids for membership in memberships
                    ),
                    "videos": len(memberships),
                },
                "first_confirmed_at": _iso(topic.first_confirmed_at),
                "first_observed_at": _iso(topic.first_observed_at),
                "id": topic.id,
                "latest_measurement": latest_record,
                "lifecycle_stage": topic.lifecycle_stage,
                "signal": signal_record,
                "status": topic.status,
            }
        )

    visible_signal_count = sum(topic["signal"] is not None for topic in topic_records)
    payload: dict[str, Any] = {
        "captured_at": _iso(captured_at),
        "counts": {
            "demand_clusters": sum(len(topic["demand_clusters"]) for topic in topic_records),
            "evidence_memberships": sum(
                int(topic["evidence"]["videos"]) for topic in topic_records
            ),
            "topic_candidates": len(topic_records),
            "visible_signals": visible_signal_count,
            "workspace_signal_scores": sum(
                len(topic["signal"]["workspace_scores"])
                for topic in topic_records
                if topic["signal"] is not None
            ),
        },
        "database_revision": _database_revision(session),
        "fixture_version": FIXTURE_VERSION,
        "model_versions": {
            "code": code_model_versions(),
            "observed": _observed_model_versions(session),
        },
        "privacy": {
            "comment_text_included": False,
            "commenter_hashes_included": False,
            "provider_payloads_included": False,
            "secrets_included": False,
        },
        "source_environment": source_environment,
        "source_kind": source_kind,
        "topics": topic_records,
    }
    payload["content_sha256"] = snapshot_content_hash(payload)
    return payload
