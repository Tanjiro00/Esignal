from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from statistics import median
from typing import cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from apps.api.channel_profiles import ensure_channel_profile
from apps.api.config import Settings
from apps.api.lifecycle import (
    backfill_lifecycle_history,
    record_lifecycle_measurement,
)
from apps.api.models import (
    ChannelBaseline,
    ChannelProfile,
    DemandCluster,
    DemandClusterComment,
    DiscoveryQueryRecord,
    ProviderFetch,
    Signal,
    Topic,
    TopicContentGap,
    TopicContentPattern,
    TopicPipelineRun,
    TopicSnapshot,
    TopicVideoMembership,
    TopicVideoObservation,
    TranscriptSegment,
    VideoDiscoveryOccurrence,
    VideoEmbedding,
    VideoFeature,
    VideoSnapshot,
    VideoTranscript,
    WorkspaceChannel,
    WorkspaceDiscoveryQuery,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from apps.api.reviews import ensure_signal_review
from apps.api.snapshot_buckets import rebuild_topic_snapshot_buckets
from apps.worker.channel_fit import ChannelFitService
from apps.worker.llm_intelligence import LLM_POLICY_VERSION, LLMIntelligenceService
from apps.worker.video_intelligence import FEATURE_VERSION
from packages.channel_fit import (
    FIT_VERSION,
    DiscoveryOccurrenceEvidence,
    assess_workspace_relevance,
    relevance_overlap,
    relevance_tokens,
)
from packages.clustering import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    MICROTOPIC_V6_VERSION,
    MicrotopicDocument,
    cluster_microtopics,
    cluster_microtopics_v6,
    embed_video_text,
    mean_embedding,
    normalize_entities,
    source_hash,
)
from packages.content_gap import (
    CONTENT_GAP_VERSION,
    CONTENT_PATTERN_VERSION,
    OPPORTUNITY_RANKING_VERSION,
)
from packages.llm_intelligence import (
    EvidenceInsightSynthesis,
    EvidenceItem,
    GroundingAudit,
    InsightReleaseAudit,
    LLMProvider,
    TopicCandidate,
    TopicReconciliation,
    TopicSynthesis,
)
from packages.scoring import TopicMeasurements, TopicScore, score_topic
from packages.topic_lineage import persist_topic_lineage_edges, topic_identity_payload

CLUSTERING_VERSION = "live-microtopic-clustering-v4"
SCORING_VERSION = "early-signal-score-v3-quality"
PIPELINE_INTERVAL_SECONDS = 15 * 60
TOPIC_PIPELINE_LOCK_KEY = 726_031_003


@dataclass(frozen=True)
class TopicDefinition:
    key: str
    label: str
    aliases: tuple[str, ...]
    entities: tuple[str, ...]
    specificity_score: float
    facet: str
    identity: dict[str, object] | None = field(default=None, compare=False, hash=False)
    thesis: str = ""
    thesis_support_ratio: float = 0
    visibility_reason_codes: tuple[str, ...] = ()
    why_growing: tuple[dict[str, object], ...] = field(
        default=(),
        compare=False,
        hash=False,
    )
    llm_provenance: dict[str, object] | None = field(
        default=None,
        compare=False,
        hash=False,
    )


@dataclass
class ClusterVideo:
    video: YoutubeVideo
    channel: YoutubeChannel
    feature: VideoFeature
    snapshot: VideoSnapshot
    embedding: list[float]
    entities: list[str]
    semantic_text: str
    assignment_score: float = 0


@dataclass(frozen=True)
class TopicPipelineResult:
    run_id: str
    reused: bool
    source_videos: int
    eligible_videos: int
    topics: int
    signals: int
    assigned_videos: int


@dataclass(frozen=True)
class WorkspaceEnrichmentResult:
    workspace_id: str
    signals_processed: int
    evidence_insights_released: int
    llm_trace: dict[str, object]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"earlysignal:{kind}:{key}"))


@contextmanager
def _topic_pipeline_lock(session: Session) -> Iterator[None]:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    engine = bind.engine if isinstance(bind, Connection) else bind
    with engine.connect() as lock_connection:
        lock_connection.execute(
            text("SELECT pg_advisory_lock(:lock_key)"),
            {"lock_key": TOPIC_PIPELINE_LOCK_KEY},
        )
        try:
            yield
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": TOPIC_PIPELINE_LOCK_KEY},
            )


def _upsert_topic_membership(
    session: Session,
    *,
    topic_id: str,
    video_id: str,
    membership_score: float,
    assignment_method: str,
    evidence_role: str,
    assigned_at: datetime,
) -> None:
    _upsert_topic_video_observation(
        session,
        topic_id=topic_id,
        video_id=video_id,
        membership_score=membership_score,
        assignment_method=assignment_method,
        evidence_role=evidence_role,
        observed_at=assigned_at,
    )
    values = {
        "topic_id": topic_id,
        "video_id": video_id,
        "membership_score": membership_score,
        "assignment_method": assignment_method,
        "evidence_role": evidence_role,
        "assigned_at": assigned_at,
    }
    if session.get_bind().dialect.name == "postgresql":
        statement = postgresql_insert(TopicVideoMembership).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    TopicVideoMembership.topic_id,
                    TopicVideoMembership.video_id,
                ],
                set_={
                    "membership_score": statement.excluded.membership_score,
                    "assignment_method": statement.excluded.assignment_method,
                    "evidence_role": statement.excluded.evidence_role,
                    "assigned_at": statement.excluded.assigned_at,
                },
            )
        )
        return
    row = session.get(TopicVideoMembership, (topic_id, video_id))
    if row is None:
        session.add(TopicVideoMembership(**values))
        return
    row.membership_score = membership_score
    row.assignment_method = assignment_method
    row.evidence_role = evidence_role
    row.assigned_at = assigned_at


def _upsert_topic_video_observation(
    session: Session,
    *,
    topic_id: str,
    video_id: str,
    membership_score: float,
    assignment_method: str,
    evidence_role: str,
    observed_at: datetime,
) -> None:
    values = {
        "topic_id": topic_id,
        "video_id": video_id,
        "first_observed_at": observed_at,
        "last_observed_at": observed_at,
        "observation_count": 1,
        "first_observation_quality": "direct",
        "membership_score": membership_score,
        "assignment_method": assignment_method,
        "evidence_role": evidence_role,
    }
    if session.get_bind().dialect.name == "postgresql":
        statement = postgresql_insert(TopicVideoObservation).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    TopicVideoObservation.topic_id,
                    TopicVideoObservation.video_id,
                ],
                set_={
                    "last_observed_at": statement.excluded.last_observed_at,
                    "observation_count": TopicVideoObservation.observation_count + 1,
                    "membership_score": statement.excluded.membership_score,
                    "assignment_method": statement.excluded.assignment_method,
                    "evidence_role": statement.excluded.evidence_role,
                },
            )
        )
        return
    row = session.get(TopicVideoObservation, (topic_id, video_id))
    if row is None:
        session.add(TopicVideoObservation(**values))
        return
    row.last_observed_at = observed_at
    row.observation_count += 1
    row.membership_score = membership_score
    row.assignment_method = assignment_method
    row.evidence_role = evidence_role


def _bounded(value: float) -> float:
    return min(100.0, max(0.0, value))


def _channel_bucket(subscribers: int) -> str:
    if subscribers < 10_000:
        return "small"
    if subscribers < 100_000:
        return "medium"
    if subscribers < 1_000_000:
        return "large"
    return "major"


def _second_independent_publication(videos: list[ClusterVideo]) -> datetime:
    ordered = sorted(videos, key=lambda item: _aware(item.video.published_at))
    seen: set[str] = set()
    for item in ordered:
        seen.add(item.channel.id)
        if len(seen) >= 2:
            return _aware(item.video.published_at)
    return _aware(ordered[0].video.published_at)


class TopicIntelligenceService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        llm_provider: LLMProvider | None = None,
        llm_auditor_provider: LLMProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._llm = LLMIntelligenceService(
            session,
            settings,
            provider=llm_provider,
            auditor_provider=llm_auditor_provider,
        )

    @property
    def _clustering_version(self) -> str:
        return (
            MICROTOPIC_V6_VERSION
            if self._settings.feature_microtopic_content_gap
            else CLUSTERING_VERSION
        )

    def reconcile_stale_runs(self, *, now: datetime | None = None) -> int:
        checked_at = now or datetime.now(tz=UTC)
        cutoff = checked_at - timedelta(minutes=max(1, self._settings.topic_pipeline_stale_minutes))
        stale_runs = list(
            self._session.scalars(
                select(TopicPipelineRun).where(
                    TopicPipelineRun.status == "running",
                    TopicPipelineRun.started_at < cutoff,
                )
            )
        )
        for stale_run in stale_runs:
            stale_run.status = "failed"
            stale_run.completed_at = checked_at
            stale_run.error_code = "stale_run_recovered"
            stale_run.error_message = (
                "The worker stopped before completing this run; the stale lease "
                "was recovered automatically."
            )
        if stale_runs:
            self._session.commit()
        return len(stale_runs)

    def run(self, *, force: bool = False) -> TopicPipelineResult:
        with _topic_pipeline_lock(self._session):
            return self._run_locked(force=force)

    def _run_locked(self, *, force: bool = False) -> TopicPipelineResult:
        started_at = datetime.now(tz=UTC)
        self.reconcile_stale_runs(now=started_at)
        bucket = int(started_at.timestamp()) // PIPELINE_INTERVAL_SECONDS
        key = f"topic-intelligence:{self._clustering_version}:{bucket}"
        if not force:
            existing = self._session.scalar(
                select(TopicPipelineRun).where(TopicPipelineRun.idempotency_key == key)
            )
            if existing is not None and existing.status in {"running", "success"}:
                assigned = int(
                    self._session.scalar(
                        select(func.count(TopicVideoMembership.video_id))
                        .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                        .where(Topic.source_kind == "live")
                    )
                    or 0
                )
                return TopicPipelineResult(
                    run_id=existing.id,
                    reused=True,
                    source_videos=existing.source_video_count,
                    eligible_videos=existing.eligible_video_count,
                    topics=existing.topic_count,
                    signals=existing.signal_count,
                    assigned_videos=assigned,
                )
            if existing is not None:
                key = f"{key}:retry:{uuid4()}"
        else:
            key = f"{key}:force:{uuid4()}"
        run = TopicPipelineRun(
            id=str(uuid4()),
            idempotency_key=key,
            started_at=started_at,
            completed_at=None,
            status="running",
            clustering_version=self._clustering_version,
            embedding_version=EMBEDDING_VERSION,
            source_video_count=0,
            eligible_video_count=0,
            topic_count=0,
            signal_count=0,
            clustering_lag_seconds=0,
            signal_generation_lag_seconds=0,
            llm_policy_version=LLM_POLICY_VERSION,
            llm_trace_json={},
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        self._llm.start_trace(run.id)
        try:
            if self._settings.feature_earlyness_timeline:
                backfill_lifecycle_history(
                    self._session,
                    source_kind="live",
                )
                self._session.commit()
            source_count, eligible = self._load_eligible_videos(started_at)
            groups = self._assign_topics(eligible)
            topics, signals, assigned = self._persist_topics(
                groups,
                observed_at=started_at,
            )
            completed_at = datetime.now(tz=UTC)
            newest_video = max(
                (_aware(item.video.first_discovered_at) for item in eligible),
                default=started_at,
            )
            run.source_video_count = source_count
            run.eligible_video_count = len(eligible)
            run.topic_count = topics
            run.signal_count = signals
            run.clustering_lag_seconds = max(
                0,
                round((started_at - newest_video).total_seconds()),
            )
            run.signal_generation_lag_seconds = max(
                0,
                round((completed_at - started_at).total_seconds()),
            )
            run.llm_trace_json = self._llm.trace_summary()
            run.completed_at = completed_at
            run.status = "success"
            self._session.commit()
            return TopicPipelineResult(
                run_id=run.id,
                reused=False,
                source_videos=source_count,
                eligible_videos=len(eligible),
                topics=topics,
                signals=signals,
                assigned_videos=assigned,
            )
        except Exception as error:
            self._session.rollback()
            failed = self._session.get(TopicPipelineRun, run.id)
            if failed is not None:
                failed.status = "failed"
                failed.completed_at = datetime.now(tz=UTC)
                failed.error_code = type(error).__name__
                failed.error_message = str(error)[:1000]
                failed.llm_trace_json = self._llm.trace_summary()
                self._session.commit()
            raise

    def enrich_workspace(
        self,
        workspace_id: str,
        *,
        limit: int = 12,
    ) -> WorkspaceEnrichmentResult:
        """Rebuild personalized insights with an isolated LLM budget."""

        trace_id = f"workspace-enrichment:{workspace_id}:{uuid4()}"
        self._llm.start_trace(trace_id)
        observed_at = datetime.now(tz=UTC)
        self._session.execute(
            update(TopicContentGap)
            .where(
                TopicContentGap.workspace_id == workspace_id,
                TopicContentGap.status == "active",
                TopicContentGap.model_version != CONTENT_GAP_VERSION,
            )
            .values(status="superseded")
        )
        rows = self._session.execute(
            select(Signal, Topic)
            .join(Topic, Topic.id == Signal.topic_id)
            .join(
                WorkspaceSignalScore,
                WorkspaceSignalScore.signal_id == Signal.id,
            )
            .where(
                WorkspaceSignalScore.workspace_id == workspace_id,
                Signal.source_kind == "live",
                Signal.status == "active",
                Topic.source_kind == "live",
                Topic.status == "active",
            )
            .order_by(
                desc(WorkspaceSignalScore.channel_fit_score),
                desc(Signal.score),
            )
            .limit(max(1, limit))
        ).all()
        processed = 0
        released = 0
        try:
            for signal, topic in rows:
                videos = self._load_topic_videos(topic.id)
                if not videos:
                    continue
                definition = self._definition_from_persisted_topic(topic, signal)
                self._upsert_workspace_score(
                    signal,
                    definition,
                    videos,
                    observed_at,
                    workspace_id=workspace_id,
                    enrich_with_llm=True,
                )
                self._session.flush()
                score = self._session.get(
                    WorkspaceSignalScore,
                    (workspace_id, signal.id),
                )
                processed += 1
                if score is not None and any(
                    bool(angle.get("release_ready"))
                    and str(angle.get("insight_type", "")).startswith("audited_")
                    for angle in score.recommended_angle_json
                ):
                    released += 1
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return WorkspaceEnrichmentResult(
            workspace_id=workspace_id,
            signals_processed=processed,
            evidence_insights_released=released,
            llm_trace=self._llm.trace_summary(),
        )

    def enrich_active_workspaces(
        self,
        *,
        limit: int = 20,
        signals_per_workspace: int = 12,
    ) -> list[WorkspaceEnrichmentResult]:
        workspace_ids = list(
            self._session.scalars(
                select(WorkspaceChannel.workspace_id)
                .where(
                    WorkspaceChannel.relationship == "owned",
                    WorkspaceChannel.active.is_(True),
                )
                .distinct()
                .limit(max(1, limit))
            )
        )
        return [
            self.enrich_workspace(
                workspace_id,
                limit=signals_per_workspace,
            )
            for workspace_id in workspace_ids
        ]

    @staticmethod
    def _definition_from_persisted_topic(
        topic: Topic,
        signal: Signal,
    ) -> TopicDefinition:
        identity = dict(topic.identity_json)
        synthesis = dict(signal.synthesis_json)
        raw_claims = synthesis.get("why_growing", [])
        why_growing = (
            tuple(dict(claim) for claim in raw_claims if isinstance(claim, dict))
            if isinstance(raw_claims, list)
            else ()
        )
        raw_provenance = synthesis.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else None
        return TopicDefinition(
            key=f"persisted:{topic.id}",
            label=topic.canonical_label,
            aliases=tuple(topic.aliases_json),
            entities=tuple(topic.entities_json),
            specificity_score=topic.specificity_score,
            facet=str(identity.get("facet") or identity.get("source") or "subject"),
            identity=identity,
            thesis=signal.thesis,
            thesis_support_ratio=topic.thesis_support_ratio,
            visibility_reason_codes=tuple(topic.visibility_reason_codes_json),
            why_growing=why_growing,
            llm_provenance=provenance,
        )

    def _load_topic_videos(self, topic_id: str) -> list[ClusterVideo]:
        rows = self._session.execute(
            select(
                TopicVideoMembership,
                YoutubeVideo,
                YoutubeChannel,
                VideoFeature,
            )
            .join(
                YoutubeVideo,
                YoutubeVideo.id == TopicVideoMembership.video_id,
            )
            .join(
                YoutubeChannel,
                YoutubeChannel.id == YoutubeVideo.channel_id,
            )
            .join(
                VideoFeature,
                (VideoFeature.video_id == YoutubeVideo.id)
                & (VideoFeature.feature_version == FEATURE_VERSION),
            )
            .where(TopicVideoMembership.topic_id == topic_id)
        ).all()
        videos: list[ClusterVideo] = []
        for membership, video, channel, feature in rows:
            snapshot = self._session.scalar(
                select(VideoSnapshot)
                .where(VideoSnapshot.video_id == video.id)
                .order_by(desc(VideoSnapshot.observed_at))
                .limit(1)
            )
            if snapshot is None:
                continue
            transcript = self._session.scalar(
                select(VideoTranscript).where(VideoTranscript.video_id == video.id)
            )
            transcript_summary = (
                str(transcript.summary_json.get("text", "")) if transcript is not None else ""
            )
            transcript_entities = list(transcript.entities_json) if transcript is not None else []
            semantic_description = " ".join(
                part
                for part in (
                    video.description,
                    f"Transcript summary: {transcript_summary}" if transcript_summary else "",
                )
                if part
            )
            entities = list(
                dict.fromkeys(
                    (
                        *normalize_entities(video.title, semantic_description),
                        *transcript_entities,
                    )
                )
            )
            embedding_row = self._session.get(
                VideoEmbedding,
                (video.id, EMBEDDING_VERSION),
            )
            embedding = (
                list(embedding_row.vector_json)
                if embedding_row is not None
                else embed_video_text(video.title, semantic_description, entities)
            )
            videos.append(
                ClusterVideo(
                    video=video,
                    channel=channel,
                    feature=feature,
                    snapshot=snapshot,
                    embedding=embedding,
                    entities=(
                        list(embedding_row.entities_json) if embedding_row is not None else entities
                    ),
                    semantic_text=semantic_description,
                    assignment_score=membership.membership_score,
                )
            )
        return sorted(
            videos,
            key=lambda item: item.feature.view_velocity,
            reverse=True,
        )

    def _load_eligible_videos(
        self,
        observed_at: datetime,
    ) -> tuple[int, list[ClusterVideo]]:
        source_count = int(
            self._session.scalar(
                select(func.count(YoutubeVideo.id)).where(
                    ~YoutubeVideo.youtube_video_id.startswith("esdemo")
                )
            )
            or 0
        )
        rows = self._session.execute(
            select(YoutubeVideo, YoutubeChannel, VideoFeature)
            .join(YoutubeChannel, YoutubeChannel.id == YoutubeVideo.channel_id)
            .join(
                VideoFeature,
                (VideoFeature.video_id == YoutubeVideo.id)
                & (VideoFeature.feature_version == FEATURE_VERSION),
            )
            .where(
                ~YoutubeVideo.youtube_video_id.startswith("esdemo"),
                YoutubeVideo.published_at >= observed_at - timedelta(days=30),
                VideoFeature.language_probability >= 0.7,
                VideoFeature.vertical_relevance >= 0.5,
                VideoFeature.spam_probability <= 0.5,
            )
        ).all()
        eligible: list[ClusterVideo] = []
        for video, channel, feature in rows:
            snapshot = self._session.scalar(
                select(VideoSnapshot)
                .where(VideoSnapshot.video_id == video.id)
                .order_by(desc(VideoSnapshot.observed_at))
                .limit(1)
            )
            if snapshot is None:
                continue
            transcript = self._session.scalar(
                select(VideoTranscript).where(VideoTranscript.video_id == video.id)
            )
            transcript_summary = (
                str(transcript.summary_json.get("text", "")) if transcript is not None else ""
            )
            transcript_entities = list(transcript.entities_json) if transcript is not None else []
            semantic_description = " ".join(
                part
                for part in (
                    video.description,
                    f"Transcript summary: {transcript_summary}" if transcript_summary else "",
                )
                if part
            )
            entities = list(
                dict.fromkeys(
                    (
                        *normalize_entities(video.title, semantic_description),
                        *transcript_entities,
                    )
                )
            )
            digest = source_hash(video.title, semantic_description, entities)
            embedding_row = self._session.get(
                VideoEmbedding,
                (video.id, EMBEDDING_VERSION),
            )
            if embedding_row is None or embedding_row.source_hash != digest:
                vector = embed_video_text(video.title, semantic_description, entities)
                if embedding_row is None:
                    embedding_row = VideoEmbedding(
                        video_id=video.id,
                        embedding_version=EMBEDDING_VERSION,
                        model_name=EMBEDDING_MODEL,
                        dimensions=EMBEDDING_DIMENSIONS,
                        vector_json=vector,
                        entities_json=entities,
                        source_hash=digest,
                        calculated_at=observed_at,
                    )
                    self._session.add(embedding_row)
                else:
                    embedding_row.model_name = EMBEDDING_MODEL
                    embedding_row.dimensions = EMBEDDING_DIMENSIONS
                    embedding_row.vector_json = vector
                    embedding_row.entities_json = entities
                    embedding_row.source_hash = digest
                    embedding_row.calculated_at = observed_at
            eligible.append(
                ClusterVideo(
                    video=video,
                    channel=channel,
                    feature=feature,
                    snapshot=snapshot,
                    embedding=list(embedding_row.vector_json),
                    entities=list(embedding_row.entities_json),
                    semantic_text=semantic_description,
                )
            )
        self._session.flush()
        return source_count, eligible

    def _assign_topics(
        self,
        videos: list[ClusterVideo],
    ) -> dict[TopicDefinition, list[ClusterVideo]]:
        by_id = {item.video.id: item for item in videos}
        documents = [
            MicrotopicDocument(
                id=item.video.id,
                title=item.video.title,
                description=item.semantic_text,
                entities=tuple(item.entities),
            )
            for item in videos
        ]
        clusters = (
            cluster_microtopics_v6(documents)
            if self._settings.feature_microtopic_content_gap
            else cluster_microtopics(documents)
        )
        groups: dict[TopicDefinition, list[ClusterVideo]] = {}
        for cluster in clusters:
            if self._settings.feature_microtopic_content_gap and not cluster.visible:
                continue
            members = [by_id[video_id] for video_id in cluster.document_ids if video_id in by_id]
            if not members:
                continue
            definition = TopicDefinition(
                key=cluster.key,
                label=cluster.label,
                aliases=cluster.aliases,
                entities=cluster.entities,
                specificity_score=cluster.specificity_score,
                facet=cluster.facet,
                identity=(
                    {
                        "domain": cluster.domain,
                        "facet": cluster.facet,
                        "primary_entity": cluster.primary_entity,
                        "secondary_entities": list(cluster.secondary_entities),
                        "audience": cluster.audience,
                        "user_problem": cluster.user_problem,
                        "core_claim": cluster.core_claim,
                        "workflow_context": cluster.workflow_context,
                        "format_distribution": dict(cluster.format_distribution),
                    }
                    if self._settings.feature_microtopic_content_gap
                    else None
                ),
                thesis=cluster.thesis,
                thesis_support_ratio=cluster.thesis_support_ratio,
                visibility_reason_codes=cluster.reason_codes,
            )
            for item in members:
                item.assignment_score = round(cluster.specificity_score / 100, 4)
            groups[definition] = members
        reconciled = self._reconcile_topic_groups(groups)
        reconciled.update(self._workspace_discovery_groups(videos))
        return reconciled

    def _workspace_discovery_groups(
        self,
        videos: list[ClusterVideo],
    ) -> dict[TopicDefinition, list[ClusterVideo]]:
        by_id = {item.video.id: item for item in videos}
        if not by_id:
            return {}
        rows = self._session.execute(
            select(
                WorkspaceDiscoveryQuery.workspace_id,
                DiscoveryQueryRecord.id,
                DiscoveryQueryRecord.query,
                VideoDiscoveryOccurrence.video_id,
            )
            .join(
                DiscoveryQueryRecord,
                DiscoveryQueryRecord.id == WorkspaceDiscoveryQuery.query_id,
            )
            .join(
                VideoDiscoveryOccurrence,
                VideoDiscoveryOccurrence.query_id == DiscoveryQueryRecord.id,
            )
            .where(
                WorkspaceDiscoveryQuery.active.is_(True),
                DiscoveryQueryRecord.active.is_(True),
                VideoDiscoveryOccurrence.video_id.in_(list(by_id)),
            )
        ).all()
        lanes: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
        for workspace_id, query_id, query, video_id in rows:
            item = by_id.get(video_id)
            if item is None or relevance_overlap(query, item.video.title) < 30:
                continue
            lanes[(workspace_id, query_id, query)].add(video_id)

        groups: dict[TopicDefinition, list[ClusterVideo]] = {}
        for (workspace_id, query_id, query), video_ids in lanes.items():
            members = [by_id[video_id] for video_id in sorted(video_ids)]
            if len(members) < 3 or len({item.channel.id for item in members}) < 3:
                continue
            query_tokens = relevance_tokens(query)
            specificity = round(min(95.0, 70.0 + len(query_tokens) * 4), 1)
            for item in members:
                item.assignment_score = max(
                    item.assignment_score,
                    round(relevance_overlap(query, item.video.title) / 100, 4),
                )
            key_hash = sha256(f"{workspace_id}:{query_id}".encode()).hexdigest()[:18]
            groups[
                TopicDefinition(
                    key=f"workspace-query-{key_hash}",
                    label=query,
                    aliases=(query,),
                    entities=tuple(normalize_entities(query, "")),
                    specificity_score=specificity,
                    facet="workspace_discovery",
                    identity={
                        "workspace_id": workspace_id,
                        "query_id": query_id,
                        "query": query,
                        "source": "workspace_discovery_query",
                    },
                    thesis=(
                        f"{len(members)} stored videos from independent YouTube search "
                        f"evidence track the specific topic: {query}."
                    ),
                    thesis_support_ratio=1.0,
                    visibility_reason_codes=("workspace_discovery_lane",),
                )
            ] = members
        return groups

    @staticmethod
    def _topic_candidate(
        definition: TopicDefinition,
        evidence_refs: list[str],
    ) -> TopicCandidate:
        identity = definition.identity or {}
        bounded_evidence_refs = list(dict.fromkeys(evidence_refs))[:24]
        return TopicCandidate(
            key=definition.key,
            current_label=definition.label,
            aliases=list(definition.aliases),
            facet=definition.facet,
            domain=str(identity.get("domain", "")),
            primary_entity=str(identity.get("primary_entity", "")),
            audience=str(identity.get("audience", "")),
            user_problem=str(identity.get("user_problem", "")),
            core_claim=str(identity.get("core_claim", "")),
            evidence_refs=bounded_evidence_refs,
        )

    @staticmethod
    def _merge_is_compatible(definitions: list[TopicDefinition]) -> bool:
        if len(definitions) < 2:
            return True
        if len({definition.facet for definition in definitions}) != 1:
            return False
        identities = [definition.identity or {} for definition in definitions]
        domains = {str(identity.get("domain", "")) for identity in identities}
        domains.discard("")
        if len(domains) > 1:
            return False
        products = {
            str(identity.get("primary_entity", ""))
            for identity in identities
            if str(identity.get("primary_entity", ""))
        }
        if len(products) > 1:
            return False
        for identity_field in ("audience", "user_problem", "core_claim"):
            values = {
                " ".join(str(identity.get(identity_field, "")).casefold().split())
                for identity in identities
                if str(identity.get(identity_field, "")).strip()
            }
            if len(values) > 1:
                return False
        if not identities[0]:
            entity_sets = [set(definition.entities) for definition in definitions]
            if not set.intersection(*entity_sets):
                return False
        return True

    @staticmethod
    def _audit_supports_target(audit: GroundingAudit, target: str) -> bool:
        return any(
            check.target == target and check.verdict == "supported" for check in audit.checks
        )

    def _reconcile_topic_groups(
        self,
        groups: dict[TopicDefinition, list[ClusterVideo]],
    ) -> dict[TopicDefinition, list[ClusterVideo]]:
        if not self._llm.enabled or len(groups) < 2:
            return groups

        compatible_batches: dict[tuple[str, str, str, str], list[TopicDefinition]] = defaultdict(
            list
        )
        for definition in groups:
            identity = definition.identity or {}
            domain = str(identity.get("domain", "")).strip().casefold()
            primary_entity = str(identity.get("primary_entity", "")).strip().casefold()
            fallback_entity = (
                definition.entities[0].strip().casefold()
                if not domain and not primary_entity and definition.entities
                else ""
            )
            compatible_batches[
                (
                    definition.facet.strip().casefold(),
                    domain,
                    primary_entity,
                    fallback_entity,
                )
            ].append(definition)

        reconciled: dict[TopicDefinition, list[ClusterVideo]] = {}
        for bucket in sorted(compatible_batches):
            definitions = sorted(
                compatible_batches[bucket],
                key=lambda definition: definition.key,
            )
            for start in range(0, len(definitions), 12):
                batch = definitions[start : start + 12]
                if len(batch) < 2:
                    definition = batch[0]
                    reconciled[definition] = groups[definition]
                    continue
                reconciled.update(self._reconcile_topic_batch(groups, batch))
        return reconciled

    def _reconcile_topic_batch(
        self,
        groups: dict[TopicDefinition, list[ClusterVideo]],
        definitions: list[TopicDefinition],
    ) -> dict[TopicDefinition, list[ClusterVideo]]:
        evidence: list[EvidenceItem] = []
        candidates: list[TopicCandidate] = []
        for definition in definitions:
            refs: list[str] = []
            for item in sorted(
                groups[definition],
                key=lambda member: member.feature.view_velocity,
                reverse=True,
            )[:6]:
                reference = f"video:{item.video.id}"
                refs.append(reference)
                evidence.append(
                    EvidenceItem(
                        ref=reference,
                        kind="video",
                        title=item.video.title,
                        text=" ".join(
                            part
                            for part in (
                                item.video.title,
                                item.video.description[:600],
                            )
                            if part
                        )[:2_000],
                    )
                )
            candidates.append(self._topic_candidate(definition, refs))
        fingerprint = sha256(
            "|".join(sorted(candidate.key for candidate in candidates)).encode()
        ).hexdigest()[:24]
        stored = self._llm.reconcile_topics(
            scope_id=fingerprint,
            candidates=candidates,
            evidence=list({item.ref: item for item in evidence}.values()),
        )
        if stored is None:
            return {definition: groups[definition] for definition in definitions}
        reconciliation = cast(TopicReconciliation, stored.value)
        by_key = {definition.key: definition for definition in definitions}
        reconciled: dict[TopicDefinition, list[ClusterVideo]] = {}
        for proposed in reconciliation.topics:
            members = [by_key[key] for key in proposed.member_keys]
            if not self._merge_is_compatible(members):
                for definition in members:
                    reconciled[definition] = groups[definition]
                continue
            primary = members[0]
            combined_videos = list(
                {
                    item.video.id: item for definition in members for item in groups[definition]
                }.values()
            )
            combined_key = (
                primary.key
                if len(members) == 1
                else "llm-merge-"
                + sha256("|".join(sorted(proposed.member_keys)).encode()).hexdigest()[:18]
            )
            combined_aliases = tuple(
                dict.fromkeys(
                    (
                        *proposed.aliases,
                        *(definition.label for definition in members),
                        *(alias for definition in members for alias in definition.aliases),
                    )
                )
            )[:12]
            combined_entities = tuple(
                dict.fromkeys(entity for definition in members for entity in definition.entities)
            )
            provenance: dict[str, object] = {
                "method": "llm",
                "task": "topic-reconciliation",
                "run_id": stored.run_id,
                "provider": stored.provider,
                "model": stored.model,
                "prompt_version": stored.prompt_version,
                "policy_version": LLM_POLICY_VERSION,
                "evidence_refs": proposed.evidence_refs,
                "member_keys": proposed.member_keys,
                "rationale": proposed.rationale,
            }
            definition = replace(
                primary,
                key=combined_key,
                label=proposed.canonical_label,
                aliases=combined_aliases,
                entities=combined_entities,
                specificity_score=min(item.specificity_score for item in members),
                llm_provenance=provenance,
            )
            reconciled[definition] = combined_videos
        return reconciled

    def _topic_evidence(
        self,
        *,
        topic_id: str,
        videos: list[ClusterVideo],
    ) -> list[EvidenceItem]:
        ordered = sorted(
            videos,
            key=lambda item: item.feature.view_velocity,
            reverse=True,
        )[:8]
        evidence: list[EvidenceItem] = []
        video_titles = {item.video.id: item.video.title for item in ordered}
        for item in ordered:
            evidence.append(
                EvidenceItem(
                    ref=f"video:{item.video.id}",
                    kind="video",
                    title=item.video.title,
                    text=" ".join(
                        part
                        for part in (
                            item.video.title,
                            item.video.description[:900],
                        )
                        if part
                    )[:2_000],
                )
            )
            evidence.append(
                EvidenceItem(
                    ref=f"video-snapshot:{item.snapshot.id}",
                    kind="metric",
                    title=f"Stored snapshot for {item.video.title}",
                    text=(
                        f"Observed views/hour {item.snapshot.views_per_hour:.1f}; "
                        f"channel-relative outlier {item.feature.outlier_ratio:.2f}x; "
                        f"published {_aware(item.video.published_at).isoformat()}; "
                        f"channel {item.channel.title}."
                    ),
                )
            )
        video_ids = list(video_titles)
        if video_ids:
            segments = list(
                self._session.scalars(
                    select(TranscriptSegment)
                    .join(
                        VideoTranscript,
                        VideoTranscript.id == TranscriptSegment.transcript_id,
                    )
                    .where(
                        VideoTranscript.video_id.in_(video_ids),
                        TranscriptSegment.is_evidence.is_(True),
                    )
                    .order_by(TranscriptSegment.start_seconds)
                    .limit(10)
                )
            )
            transcript_video_by_id = {
                transcript.id: transcript.video_id
                for transcript in self._session.scalars(
                    select(VideoTranscript).where(VideoTranscript.video_id.in_(video_ids))
                )
            }
            for segment in segments:
                if not segment.text.strip():
                    continue
                video_id = transcript_video_by_id.get(segment.transcript_id, "")
                evidence.append(
                    EvidenceItem(
                        ref=f"transcript-segment:{segment.id}",
                        kind="transcript",
                        title=video_titles.get(video_id, "Stored public transcript"),
                        text=segment.text[:2_000],
                    )
                )
        comments = list(
            self._session.scalars(
                select(YoutubeComment)
                .join(
                    DemandClusterComment,
                    DemandClusterComment.comment_id == YoutubeComment.id,
                )
                .join(
                    DemandCluster,
                    DemandCluster.id == DemandClusterComment.demand_cluster_id,
                )
                .where(
                    DemandCluster.topic_id == topic_id,
                    DemandCluster.visibility_status != "internal_candidate",
                    DemandClusterComment.is_representative.is_(True),
                )
                .order_by(desc(YoutubeComment.like_count))
                .limit(6)
            )
        )
        for comment in comments:
            if not comment.text.strip():
                continue
            evidence.append(
                EvidenceItem(
                    ref=f"comment:{comment.id}",
                    kind="comment",
                    title=video_titles.get(comment.video_id, "Stored audience comment"),
                    text=comment.text[:2_000],
                )
            )
        return list({item.ref: item for item in evidence}.values())

    def _synthesize_topic_definition(
        self,
        *,
        topic: Topic,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        measurements: TopicMeasurements,
    ) -> TopicDefinition:
        if not self._llm.enabled:
            return definition
        format_neutral_label_locked = definition.facet == "workspace_discovery"
        evidence = self._topic_evidence(topic_id=topic.id, videos=videos)
        candidate = self._topic_candidate(
            definition,
            [item.ref for item in evidence],
        )
        deterministic_metrics: dict[str, object] = {
            "video_count_24h": measurements.video_count_24h,
            "video_count_72h": measurements.video_count_72h,
            "distinct_channels": measurements.distinct_channels,
            "distinct_channels_72h": measurements.distinct_channels_72h,
            "aggregate_view_velocity": measurements.aggregate_view_velocity,
            "median_outlier_ratio": measurements.median_outlier_ratio,
            "top_channel_share": measurements.top_channel_share,
            "baseline_coverage": measurements.baseline_coverage,
            "transcript_coverage": measurements.transcript_coverage,
        }
        stored = self._llm.synthesize_topic(
            topic_id=topic.id,
            candidate=candidate,
            evidence=evidence,
            deterministic_metrics=deterministic_metrics,
        )
        if stored is None:
            self._llm.record_gate(
                stage="topic-synthesis-release",
                scope_id=topic.id,
                decision="fallback",
                reason="synthesis_unavailable",
            )
            return definition
        synthesis = cast(TopicSynthesis, stored.value)
        audit_stored = (
            self._llm.audit_topic_synthesis(
                topic_id=topic.id,
                candidate=candidate,
                synthesis=synthesis,
                evidence=evidence,
                deterministic_metrics=deterministic_metrics,
                parent_run_id=stored.run_id,
            )
            if self._settings.llm_require_grounding_audit
            else None
        )
        audit = cast(GroundingAudit, audit_stored.value) if audit_stored is not None else None
        provenance: dict[str, object] = {
            "method": "llm",
            "task": "topic-synthesis",
            "run_id": stored.run_id,
            "provider": stored.provider,
            "model": stored.model,
            "prompt_version": stored.prompt_version,
            "cached": stored.cached,
            "policy_version": LLM_POLICY_VERSION,
            "label_policy": (
                "deterministic_workspace_query"
                if format_neutral_label_locked
                else "evidence_bound_llm"
            ),
            "audit": (
                {
                    "run_id": audit_stored.run_id,
                    "provider": audit_stored.provider,
                    "model": audit_stored.model,
                    "prompt_version": audit_stored.prompt_version,
                    "decision": audit.decision,
                    "summary": audit.summary,
                    "cached": audit_stored.cached,
                }
                if audit_stored is not None and audit is not None
                else {"required": False}
            ),
        }
        if self._settings.llm_require_grounding_audit and (
            audit is None or audit.decision != "accept"
        ):
            if audit is not None and self._audit_supports_target(audit, "canonical_label"):
                self._llm.record_gate(
                    stage="topic-synthesis-release",
                    scope_id=topic.id,
                    decision="partial_accept",
                    reason="canonical_label_supported",
                    parent_run_id=stored.run_id,
                )
                enriched = replace(
                    definition,
                    label=(
                        definition.label
                        if format_neutral_label_locked
                        else synthesis.canonical_label
                    ),
                    aliases=tuple(
                        dict.fromkeys(
                            (
                                *synthesis.aliases,
                                definition.label,
                                *definition.aliases,
                            )
                        )
                    )[:12],
                    llm_provenance={
                        **provenance,
                        "released_fields": (
                            ["aliases"]
                            if format_neutral_label_locked
                            else ["canonical_label", "aliases"]
                        ),
                        "rejected_fields": ["thesis", "why_growing"],
                    },
                )
                topic.canonical_label = enriched.label
                topic.aliases_json = list(enriched.aliases)
                topic.identity_json = {
                    **dict(topic.identity_json),
                    "llm_synthesis": enriched.llm_provenance,
                }
                return enriched
            self._llm.record_gate(
                stage="topic-synthesis-release",
                scope_id=topic.id,
                decision="fallback",
                reason=("audit_unavailable" if audit is None else "audit_rejected"),
                parent_run_id=stored.run_id,
            )
            return definition
        self._llm.record_gate(
            stage="topic-synthesis-release",
            scope_id=topic.id,
            decision="accept",
            reason=("grounding_audit_passed" if audit is not None else "audit_not_required"),
            parent_run_id=stored.run_id,
        )
        enriched = replace(
            definition,
            label=(definition.label if format_neutral_label_locked else synthesis.canonical_label),
            aliases=tuple(
                dict.fromkeys(
                    (
                        *synthesis.aliases,
                        definition.label,
                        *definition.aliases,
                    )
                )
            )[:12],
            thesis=synthesis.thesis,
            why_growing=tuple(claim.model_dump(mode="json") for claim in synthesis.why_growing),
            llm_provenance=provenance,
        )
        topic.canonical_label = enriched.label
        topic.aliases_json = list(enriched.aliases)
        topic.identity_json = {
            **dict(topic.identity_json),
            "llm_synthesis": provenance,
        }
        return enriched

    def _persist_topics(
        self,
        groups: dict[TopicDefinition, list[ClusterVideo]],
        *,
        observed_at: datetime,
    ) -> tuple[int, int, int]:
        groups = self._coalesce_persistence_groups(groups)
        groups = {
            definition: videos
            for definition, videos in groups.items()
            if len(videos) >= 3 and len({item.channel.id for item in videos}) >= 3
        }
        live_topics = list(self._session.scalars(select(Topic).where(Topic.source_kind == "live")))
        previous_active_topics = [topic for topic in live_topics if topic.status == "active"]
        live_topic_ids = [topic.id for topic in live_topics]
        if live_topic_ids:
            self._session.execute(
                delete(TopicVideoMembership).where(
                    TopicVideoMembership.topic_id.in_(live_topic_ids)
                )
            )
        for topic in live_topics:
            topic.status = "archived"
        for signal in self._session.scalars(select(Signal).where(Signal.source_kind == "live")):
            signal.status = "archived"

        topic_count = 0
        signal_count = 0
        assigned_count = 0
        current_identities: dict[str, dict[str, object]] = {}
        for definition, videos in groups.items():
            topic = self._upsert_topic(definition, videos, observed_at)
            current_identities[topic.id] = dict(topic.identity_json["lineage"])
            self._session.flush()
            ordered = sorted(
                videos,
                key=lambda item: item.feature.view_velocity,
                reverse=True,
            )
            for index, item in enumerate(ordered):
                _upsert_topic_membership(
                    self._session,
                    topic_id=topic.id,
                    video_id=item.video.id,
                    membership_score=item.assignment_score,
                    assignment_method=(
                        "microtopic_identity_v5"
                        if self._settings.feature_microtopic_content_gap
                        else "entity_embedding_v2_transcript"
                    ),
                    evidence_role=(
                        "driver" if index < 2 else "amplifier" if index < 5 else "supporting"
                    ),
                    assigned_at=observed_at,
                )
            measurements = self._measure_topic(
                topic,
                definition,
                videos,
                observed_at,
            )
            score = score_topic(measurements)
            if self._is_actionable(definition, measurements, score):
                definition = self._synthesize_topic_definition(
                    topic=topic,
                    definition=definition,
                    videos=videos,
                    measurements=measurements,
                )
            topic.lifecycle_stage = score.lifecycle_stage
            topic.status = "active"
            snapshot = self._add_snapshot(topic, measurements, score, observed_at)
            created_signal = self._upsert_signal(
                topic,
                definition,
                videos,
                measurements,
                score,
                observed_at,
            )
            if self._settings.feature_earlyness_timeline:
                record_lifecycle_measurement(
                    self._session,
                    topic_id=topic.id,
                    snapshot=snapshot,
                    stage=score.lifecycle_stage,
                    score=score.score,
                    signal_visible=(
                        created_signal and not self._settings.feature_signal_review_queue
                    ),
                    review_gated=self._settings.feature_signal_review_queue,
                )
            if self._settings.feature_topic_snapshot_buckets:
                rebuild_topic_snapshot_buckets(
                    self._session,
                    topic_id=topic.id,
                    captured_at=observed_at,
                )
            topic_count += 1
            signal_count += int(created_signal)
            assigned_count += len(videos)
        persist_topic_lineage_edges(
            self._session,
            previous_topics=previous_active_topics,
            current_identities=current_identities,
            detected_at=observed_at,
        )
        return topic_count, signal_count, assigned_count

    @staticmethod
    def _coalesce_persistence_groups(
        groups: dict[TopicDefinition, list[ClusterVideo]],
    ) -> dict[TopicDefinition, list[ClusterVideo]]:
        """Enforce one persisted group and one membership per canonical identity."""

        combined: dict[str, tuple[TopicDefinition, dict[str, ClusterVideo]]] = {}
        for definition, videos in groups.items():
            topic_id = _stable_id("live-topic", definition.key)
            existing = combined.get(topic_id)
            if existing is None:
                canonical = definition
                by_video: dict[str, ClusterVideo] = {}
            else:
                canonical, by_video = existing
                canonical = replace(
                    canonical,
                    aliases=tuple(dict.fromkeys((*canonical.aliases, *definition.aliases)))[:12],
                    entities=tuple(dict.fromkeys((*canonical.entities, *definition.entities))),
                )
            for item in videos:
                previous = by_video.get(item.video.id)
                if previous is None or (
                    item.assignment_score,
                    item.feature.view_velocity,
                ) > (
                    previous.assignment_score,
                    previous.feature.view_velocity,
                ):
                    by_video[item.video.id] = item
            combined[topic_id] = (canonical, by_video)
        return {definition: list(by_video.values()) for definition, by_video in combined.values()}

    def _upsert_topic(
        self,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        observed_at: datetime,
    ) -> Topic:
        topic_id = _stable_id("live-topic", definition.key)
        topic = self._session.get(Topic, topic_id)
        first_observed = min(_aware(item.video.published_at) for item in videos)
        observed_entities = Counter(entity for item in videos for entity in item.entities)
        entities = list(
            dict.fromkeys(
                (
                    *definition.entities,
                    *(entity for entity, _ in observed_entities.most_common(8)),
                )
            )
        )
        centroid = mean_embedding([item.embedding for item in videos])
        identity_payload = dict(definition.identity or {})
        if definition.llm_provenance is not None:
            identity_payload["llm_reconciliation"] = definition.llm_provenance
        identity_payload["lineage"] = topic_identity_payload(
            identity_payload,
            definition_key=definition.key,
        )
        if topic is None:
            topic = Topic(
                id=topic_id,
                canonical_label=definition.label,
                aliases_json=list(definition.aliases),
                entities_json=entities,
                centroid_embedding=centroid,
                embedding_model=EMBEDDING_MODEL,
                embedding_version=EMBEDDING_VERSION,
                first_observed_at=first_observed,
                first_confirmed_at=_second_independent_publication(videos),
                lifecycle_stage="Seed",
                status="active",
                source_kind="live",
                merged_into_topic_id=None,
                clustering_version=self._clustering_version,
                identity_json=identity_payload,
                specificity_score=definition.specificity_score,
                thesis_support_ratio=definition.thesis_support_ratio,
                visibility_reason_codes_json=list(definition.visibility_reason_codes),
            )
            self._session.add(topic)
        else:
            topic.canonical_label = definition.label
            topic.aliases_json = list(definition.aliases)
            topic.entities_json = entities
            topic.centroid_embedding = centroid
            topic.embedding_model = EMBEDDING_MODEL
            topic.embedding_version = EMBEDDING_VERSION
            topic.first_observed_at = min(
                _aware(topic.first_observed_at),
                first_observed,
            )
            topic.first_confirmed_at = _second_independent_publication(videos)
            topic.status = "active"
            topic.source_kind = "live"
            topic.merged_into_topic_id = None
            topic.clustering_version = self._clustering_version
            topic.identity_json = identity_payload
            topic.specificity_score = definition.specificity_score
            topic.thesis_support_ratio = definition.thesis_support_ratio
            topic.visibility_reason_codes_json = list(definition.visibility_reason_codes)
        return topic

    def _measure_topic(
        self,
        topic: Topic,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        observed_at: datetime,
    ) -> TopicMeasurements:
        recent_24 = [
            item
            for item in videos
            if _aware(item.video.published_at) >= observed_at - timedelta(hours=24)
        ]
        recent_72 = [
            item
            for item in videos
            if _aware(item.video.published_at) >= observed_at - timedelta(hours=72)
        ]
        previous_24 = [
            item
            for item in videos
            if observed_at - timedelta(hours=48)
            <= _aware(item.video.published_at)
            < observed_at - timedelta(hours=24)
        ]
        velocities = [max(0.0, item.feature.view_velocity) for item in videos]
        velocity_median = median(velocities) if velocities else 0
        cap = max(velocity_median * 4, 1)
        aggregate_velocity = sum(min(value, cap) for value in velocities)
        total_velocity = sum(velocities)
        channel_counts = Counter(item.channel.id for item in videos)
        video_ids = [item.video.id for item in videos]
        current_search = int(
            self._session.scalar(
                select(func.count(VideoDiscoveryOccurrence.id)).where(
                    VideoDiscoveryOccurrence.video_id.in_(video_ids),
                    VideoDiscoveryOccurrence.discovered_at >= observed_at - timedelta(hours=24),
                )
            )
            or 0
        )
        previous_search = int(
            self._session.scalar(
                select(func.count(VideoDiscoveryOccurrence.id)).where(
                    VideoDiscoveryOccurrence.video_id.in_(video_ids),
                    VideoDiscoveryOccurrence.discovered_at >= observed_at - timedelta(hours=48),
                    VideoDiscoveryOccurrence.discovered_at < observed_at - timedelta(hours=24),
                )
            )
            or 0
        )
        provider_count = int(
            self._session.scalar(
                select(func.count(func.distinct(ProviderFetch.provider)))
                .join(
                    VideoDiscoveryOccurrence,
                    VideoDiscoveryOccurrence.provider_fetch_id == ProviderFetch.id,
                )
                .where(VideoDiscoveryOccurrence.video_id.in_(video_ids))
            )
            or 0
        )
        channel_ids = {item.channel.id for item in videos}
        calibrated_channels = int(
            self._session.scalar(
                select(func.count(func.distinct(ChannelBaseline.channel_id))).where(
                    ChannelBaseline.channel_id.in_(channel_ids),
                    ChannelBaseline.metric_name == "median_views_age_curve_coefficient",
                    ChannelBaseline.sample_size >= 5,
                )
            )
            or 0
        )
        transcript_count = int(
            self._session.scalar(
                select(func.count(func.distinct(VideoTranscript.video_id))).where(
                    VideoTranscript.video_id.in_(video_ids)
                )
            )
            or 0
        )
        entity_count = len({entity for item in videos for entity in item.entities})
        return TopicMeasurements(
            video_count=len(videos),
            video_count_24h=len(recent_24),
            video_count_72h=len(recent_72),
            previous_video_count_24h=len(previous_24),
            distinct_channels=len(channel_counts),
            distinct_channels_72h=len({item.channel.id for item in recent_72}),
            channel_size_bucket_count=len(
                {_channel_bucket(item.channel.subscriber_count) for item in videos}
            ),
            large_channel_count=len(
                {item.channel.id for item in videos if item.channel.subscriber_count >= 100_000}
            ),
            aggregate_view_velocity=round(aggregate_velocity, 2),
            top_velocity_share=max(velocities, default=0) / max(total_velocity, 1),
            top_channel_share=max(channel_counts.values(), default=0) / max(len(videos), 1),
            median_outlier_ratio=median([item.feature.outlier_ratio for item in videos]),
            top_outlier_ratio=max(
                (item.feature.outlier_ratio for item in videos),
                default=1,
            ),
            search_appearances_24h=current_search,
            previous_search_appearances_24h=previous_search,
            provider_coverage_count=provider_count,
            snapshot_coverage=sum(item.snapshot is not None for item in videos)
            / max(len(videos), 1),
            entity_count=entity_count,
            audience_demand=float(
                self._session.scalar(
                    select(func.max(DemandCluster.demand_score)).where(
                        DemandCluster.topic_id == topic.id,
                        DemandCluster.visibility_status != "internal_candidate",
                    )
                )
                or 0
            ),
            baseline_coverage=calibrated_channels / max(len(channel_ids), 1),
            transcript_coverage=transcript_count / max(len(videos), 1),
            specificity_score=definition.specificity_score,
            topic_age_days=max(
                0.0,
                (observed_at - _aware(topic.first_observed_at)).total_seconds() / 86_400,
            ),
        )

    def _add_snapshot(
        self,
        topic: Topic,
        measurements: TopicMeasurements,
        score: TopicScore,
        observed_at: datetime,
    ) -> TopicSnapshot:
        components = score.components.normalized()
        snapshot = TopicSnapshot(
            id=str(uuid4()),
            topic_id=topic.id,
            observed_at=observed_at,
            video_count_24h=measurements.video_count_24h,
            video_count_72h=measurements.video_count_72h,
            distinct_channels_72h=measurements.distinct_channels_72h,
            aggregate_view_velocity=measurements.aggregate_view_velocity,
            median_outlier_ratio=round(
                measurements.median_outlier_ratio,
                4,
            ),
            large_channel_count=measurements.large_channel_count,
            demand_score=components.audience_demand,
            saturation_score=components.saturation_penalty,
            fragility_score=components.fragility_penalty,
            component_json={
                "video_count": measurements.video_count,
                "video_count_24h": measurements.video_count_24h,
                "video_count_72h": measurements.video_count_72h,
                "previous_video_count_24h": (measurements.previous_video_count_24h),
                "distinct_channels": measurements.distinct_channels,
                "top_outlier_ratio": measurements.top_outlier_ratio,
                "top_velocity_share": measurements.top_velocity_share,
                "top_channel_share": measurements.top_channel_share,
                "search_appearances_24h": (measurements.search_appearances_24h),
                "provider_coverage_count": (measurements.provider_coverage_count),
                "snapshot_coverage": measurements.snapshot_coverage,
                "baseline_coverage": measurements.baseline_coverage,
                "transcript_coverage": measurements.transcript_coverage,
                "specificity_score": measurements.specificity_score,
                "topic_age_days": round(measurements.topic_age_days, 2),
                "topic_identity": dict(topic.identity_json["lineage"]),
                "score": score.score,
            },
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def _is_actionable(
        self,
        definition: TopicDefinition,
        measurements: TopicMeasurements,
        score: TopicScore,
    ) -> bool:
        fresh_confirmation = (
            measurements.video_count_72h >= 2 and measurements.distinct_channels_72h >= 2
        )
        personal_lane = getattr(definition, "facet", "") == "workspace_discovery"
        personal_early_watch = (
            personal_lane
            and score.lifecycle_stage == "Seed"
            and measurements.video_count_72h >= 1
            and measurements.video_count >= 5
            and measurements.distinct_channels >= 4
            and measurements.baseline_coverage >= 0.5
            and score.score >= 30
        )
        if personal_lane:
            return (
                definition.specificity_score >= 75
                and definition.thesis_support_ratio >= 0.8
                and (fresh_confirmation or personal_early_watch)
                and measurements.distinct_channels >= 3
                and score.score >= 30
                and score.lifecycle_stage not in {"Saturated", "Declining"}
            )
        evidence_backed_watch = (
            score.lifecycle_stage == "Seed"
            and measurements.video_count_72h >= 1
            and measurements.video_count >= 3
            and measurements.distinct_channels >= 3
        )
        return (
            definition.specificity_score
            >= (70 if self._settings.feature_microtopic_content_gap else 65)
            and (
                not self._settings.feature_microtopic_content_gap
                or definition.thesis_support_ratio >= 0.8
            )
            and (fresh_confirmation or evidence_backed_watch)
            and measurements.distinct_channels >= 3
            and measurements.baseline_coverage >= 0.5
            and (
                measurements.median_outlier_ratio >= 1.1
                or (
                    measurements.top_outlier_ratio >= 1.8
                    and measurements.top_velocity_share <= 0.75
                )
            )
            and (score.score >= 30 or (evidence_backed_watch and score.score >= 25))
            and score.lifecycle_stage not in {"Saturated", "Declining"}
        )

    def _upsert_signal(
        self,
        topic: Topic,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        measurements: TopicMeasurements,
        score: TopicScore,
        observed_at: datetime,
    ) -> bool:
        if not self._is_actionable(definition, measurements, score):
            return False
        signal_id = _stable_id("live-signal", definition.key)
        signal = self._session.get(Signal, signal_id)
        window_start, window_end = self._opportunity_window(
            score.lifecycle_stage,
            observed_at,
        )
        components = {
            **score.components.normalized().__dict__,
            "baseline_coverage": round(measurements.baseline_coverage * 100, 1),
            "transcript_coverage": round(measurements.transcript_coverage * 100, 1),
            "specificity_score": definition.specificity_score,
        }
        thesis = (
            definition.thesis
            if (
                self._settings.feature_microtopic_content_gap
                or self._settings.feature_llm_intelligence
            )
            and definition.thesis
            else (
                f"{definition.label} is confirmed by {measurements.distinct_channels} "
                f"independent channels overall, including "
                f"{measurements.distinct_channels_72h} channels and "
                f"{measurements.video_count_72h} videos in the last 72 hours. "
                f"Median channel-relative performance is "
                f"{measurements.median_outlier_ratio:.2f}× baseline, with a capped "
                f"aggregate velocity of "
                f"{measurements.aggregate_view_velocity:,.0f} views/hour."
            )
        )
        strongest_demand = self._session.scalar(
            select(DemandCluster)
            .where(
                DemandCluster.topic_id == topic.id,
                DemandCluster.visibility_status != "internal_candidate",
            )
            .order_by(desc(DemandCluster.demand_score))
        )
        transcript_count = int(
            self._session.scalar(
                select(func.count(VideoTranscript.id)).where(
                    VideoTranscript.video_id.in_([item.video.id for item in videos])
                )
            )
            or 0
        )
        deterministic_why = [
            (
                f"{measurements.video_count_24h} videos were published in 24h "
                f"and {measurements.video_count_72h} in 72h."
            ),
            (
                f"Evidence spans {measurements.distinct_channels} channels; "
                f"the largest channel contributes "
                f"{measurements.top_channel_share:.0%} of videos."
            ),
            (
                f"Median channel-relative outlier is "
                f"{measurements.median_outlier_ratio:.2f}×; "
                + (
                    f"the strongest stored demand cluster scores "
                    f"{strongest_demand.demand_score:.1f}/100 from "
                    f"{strongest_demand.comment_count} comments."
                    if strongest_demand is not None
                    else "no stored demand cluster meets the cross-video evidence floor."
                )
            ),
            (
                f"{measurements.baseline_coverage:.0%} of evidence channels have "
                "a calibrated historical baseline and "
                f"{transcript_count} of {len(videos)} videos have transcript enrichment."
            ),
        ]
        deterministic_refs = [f"video:{item.video.id}" for item in videos[:5]]
        why_claims = (
            [dict(claim) for claim in definition.why_growing]
            if definition.why_growing
            else [
                {
                    "text": reason,
                    "evidence_refs": deterministic_refs,
                }
                for reason in deterministic_why
            ]
        )
        why = [str(claim.get("text", "")) for claim in why_claims]
        synthesis = {
            "method": "llm" if definition.why_growing else "deterministic",
            "why_growing": why_claims,
            "provenance": definition.llm_provenance or {},
        }
        if signal is None:
            signal = Signal(
                id=signal_id,
                topic_id=topic.id,
                status="active",
                source_kind="live",
                lifecycle_stage=score.lifecycle_stage,
                score=score.score,
                confidence=score.confidence,
                opportunity_start=window_start,
                opportunity_end=window_end,
                thesis=thesis,
                why_emerging_json=why,
                component_json=components,
                evidence_version=f"{self._clustering_version}:{SCORING_VERSION}",
                synthesis_json=synthesis,
                generated_at=observed_at,
                expires_at=observed_at + timedelta(hours=6),
            )
            self._session.add(signal)
        else:
            signal.status = "active"
            signal.source_kind = "live"
            signal.lifecycle_stage = score.lifecycle_stage
            signal.score = score.score
            signal.confidence = score.confidence
            signal.opportunity_start = window_start
            signal.opportunity_end = window_end
            signal.thesis = thesis
            signal.why_emerging_json = why
            signal.component_json = components
            signal.evidence_version = f"{self._clustering_version}:{SCORING_VERSION}"
            signal.synthesis_json = synthesis
            signal.generated_at = observed_at
            signal.expires_at = observed_at + timedelta(hours=6)
        self._upsert_workspace_score(signal, definition, videos, observed_at)
        return True

    def _upsert_workspace_score(
        self,
        signal: Signal,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        observed_at: datetime,
        *,
        workspace_id: str | None = None,
        enrich_with_llm: bool = False,
    ) -> None:
        owned_query = select(WorkspaceChannel).where(
            WorkspaceChannel.relationship == "owned",
            WorkspaceChannel.active.is_(True),
        )
        identity = definition.identity or {}
        target_workspace_id = (
            str(identity.get("workspace_id", ""))
            if identity.get("source") == "workspace_discovery_query"
            else ""
        )
        if target_workspace_id:
            owned_query = owned_query.where(
                WorkspaceChannel.workspace_id == target_workspace_id,
            )
        if workspace_id:
            if target_workspace_id and target_workspace_id != workspace_id:
                return
            owned_query = owned_query.where(
                WorkspaceChannel.workspace_id == workspace_id,
            )
        owned_channels = list(self._session.scalars(owned_query))
        evidence_ids = [item.video.id for item in videos[:5]]
        transcript_segment_ids = list(
            self._session.scalars(
                select(TranscriptSegment.id)
                .join(
                    VideoTranscript,
                    VideoTranscript.id == TranscriptSegment.transcript_id,
                )
                .where(
                    VideoTranscript.video_id.in_(evidence_ids),
                    TranscriptSegment.is_evidence.is_(True),
                )
                .order_by(TranscriptSegment.start_seconds)
                .limit(3)
            )
        )
        topic_values = [
            definition.label,
            *definition.aliases,
            *definition.entities,
        ]
        evidence_videos = [item.video for item in videos]
        all_evidence_ids = [item.video.id for item in videos]
        vertical_relevance = [item.feature.vertical_relevance for item in videos]
        fit_service = ChannelFitService(
            self._session,
            content_gap_enabled=self._settings.feature_microtopic_content_gap,
            feasibility_v2_enabled=(self._settings.feature_channel_profile_feasibility_v2),
            verified_analytics_enabled=self._settings.feature_youtube_oauth_analytics,
        )
        for owned in owned_channels:
            row = self._session.get(
                WorkspaceSignalScore,
                (owned.workspace_id, signal.id),
            )
            strongest_demand = self._session.scalar(
                select(DemandCluster)
                .where(
                    DemandCluster.topic_id == signal.topic_id,
                    DemandCluster.visibility_status != "internal_candidate",
                )
                .order_by(desc(DemandCluster.demand_score))
            )
            demand_comment_ids = (
                list(
                    self._session.scalars(
                        select(DemandClusterComment.comment_id)
                        .where(
                            DemandClusterComment.demand_cluster_id == strongest_demand.id,
                            DemandClusterComment.is_representative.is_(True),
                        )
                        .limit(3)
                    )
                )
                if strongest_demand is not None
                else []
            )
            provisional_angles = self._provisional_angles(
                definition,
                evidence_ids,
                strongest_demand,
                demand_comment_ids,
                transcript_segment_ids,
            )
            profile = ensure_channel_profile(self._session, owned)
            plan_query_count = int(
                self._session.scalar(
                    select(func.count(WorkspaceDiscoveryQuery.query_id)).where(
                        WorkspaceDiscoveryQuery.workspace_id == owned.workspace_id,
                        WorkspaceDiscoveryQuery.active.is_(True),
                    )
                )
                or 0
            )
            occurrence_rows = (
                self._session.execute(
                    select(
                        VideoDiscoveryOccurrence.video_id,
                        DiscoveryQueryRecord.id,
                        DiscoveryQueryRecord.query,
                    )
                    .join(
                        WorkspaceDiscoveryQuery,
                        WorkspaceDiscoveryQuery.query_id == VideoDiscoveryOccurrence.query_id,
                    )
                    .join(
                        DiscoveryQueryRecord,
                        DiscoveryQueryRecord.id == VideoDiscoveryOccurrence.query_id,
                    )
                    .where(
                        WorkspaceDiscoveryQuery.workspace_id == owned.workspace_id,
                        WorkspaceDiscoveryQuery.active.is_(True),
                        VideoDiscoveryOccurrence.video_id.in_(all_evidence_ids),
                    )
                ).all()
                if plan_query_count and all_evidence_ids
                else []
            )
            relevance_topic_values = (
                [str((definition.identity or {}).get("query", definition.label))]
                if (definition.identity or {}).get("source") == "workspace_discovery_query"
                else [definition.label]
            )
            relevance = assess_workspace_relevance(
                topic_values=relevance_topic_values,
                core_topic_values=list(
                    dict.fromkeys(
                        [
                            *profile.topic_keywords_json,
                            *profile.creator_expertise_json,
                            *profile.core_topics_json,
                            *profile.adjacent_topics_json,
                        ]
                    )
                ),
                evidence_video_ids=all_evidence_ids,
                plan_query_count=plan_query_count,
                occurrences=[
                    DiscoveryOccurrenceEvidence(
                        video_id=video_id,
                        query_id=query_id,
                        query=query,
                    )
                    for video_id, query_id, query in occurrence_rows
                ],
            )
            fit = fit_service.score(
                profile=profile,
                signal=signal,
                topic_values=topic_values,
                evidence_videos=evidence_videos,
                vertical_relevance=vertical_relevance,
                provisional_angles=provisional_angles,
                observed_at=observed_at,
                demand_supported=strongest_demand is not None,
            )
            fit_components = {
                **fit.components,
                "workspace_relevance": relevance,
            }
            eligible = bool(relevance["eligible"])
            channel_fit_score = fit.score if eligible else min(fit.score, 19.9)
            recommended_angles = fit.opportunities if eligible else []
            content_gap_map = fit.content_gap_map
            if content_gap_map is not None and eligible and enrich_with_llm:
                recommended_angles, content_gap_map = self._enrich_content_gap_map(
                    workspace_id=owned.workspace_id,
                    signal=signal,
                    definition=definition,
                    videos=videos,
                    profile=profile,
                    recommended_angles=recommended_angles,
                    content_gap_map=content_gap_map,
                )
            if row is None:
                self._session.add(
                    WorkspaceSignalScore(
                        workspace_id=owned.workspace_id,
                        signal_id=signal.id,
                        channel_id=owned.channel_id,
                        channel_fit_score=channel_fit_score,
                        fit_component_json=fit_components,
                        recommended_angle_json=recommended_angles,
                        fit_version=FIT_VERSION,
                        calculated_at=observed_at,
                    )
                )
            else:
                row.channel_id = owned.channel_id
                row.channel_fit_score = channel_fit_score
                row.fit_component_json = fit_components
                row.recommended_angle_json = recommended_angles
                row.fit_version = FIT_VERSION
                row.calculated_at = observed_at
            if content_gap_map is not None and eligible:
                self._persist_content_gap_map(
                    workspace_id=owned.workspace_id,
                    topic_id=signal.topic_id,
                    content_gap_map=content_gap_map,
                    observed_at=observed_at,
                )
            if self._settings.feature_signal_review_queue:
                ensure_signal_review(self._session, owned.workspace_id, signal)

    def _enrich_content_gap_map(
        self,
        *,
        workspace_id: str,
        signal: Signal,
        definition: TopicDefinition,
        videos: list[ClusterVideo],
        profile: ChannelProfile,
        recommended_angles: list[dict[str, object]],
        content_gap_map: dict[str, object],
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        if not self._llm.enabled:
            return recommended_angles, content_gap_map
        raw_gaps = content_gap_map.get("opportunities", [])
        gaps = (
            [dict(item) for item in raw_gaps if isinstance(item, dict)]
            if isinstance(raw_gaps, list)
            else []
        )
        if not gaps:
            return recommended_angles, content_gap_map
        evidence = self._topic_evidence(topic_id=signal.topic_id, videos=videos)
        deterministic_metrics: dict[str, object] = {
            "signal_score": signal.score,
            "signal_confidence": signal.confidence,
            "lifecycle_stage": signal.lifecycle_stage,
            "evidence_video_count": len(videos),
            "independent_channels": len({item.channel.id for item in videos}),
            "occupied_pattern": content_gap_map.get("occupied_pattern", {}),
            "candidate_performance_pattern": dict(
                dict(gaps[0].get("insight_metrics", {})).get(
                    "performance_pattern",
                    {},
                )
            ),
        }
        stored = self._llm.synthesize_evidence_insight(
            workspace_id=workspace_id,
            topic_id=signal.topic_id,
            topic_label=definition.label,
            channel_profile={
                "audience": profile.audience_description,
                "core_topics": profile.core_topics_json,
                "adjacent_topics": profile.adjacent_topics_json,
                "preferred_formats": profile.preferred_formats_json,
                "successful_formats": profile.successful_formats_json,
                "creator_expertise": profile.creator_expertise_json,
                "strategic_goals": profile.strategic_goals_json,
                "production_days_min": profile.production_days_min,
                "production_days_max": profile.production_days_max,
                "research_capacity_hours": profile.research_capacity_hours,
                "editing_complexity": profile.editing_complexity,
            },
            deterministic_metrics=deterministic_metrics,
            evidence=evidence,
        )
        if stored is None:
            self._llm.record_gate(
                stage="evidence-insight-release",
                scope_id=f"{workspace_id}:{signal.topic_id}",
                decision="fallback",
                reason="synthesis_unavailable",
            )
            return recommended_angles, content_gap_map
        synthesis = cast(EvidenceInsightSynthesis, stored.value)
        if synthesis.insight is None:
            self._llm.record_gate(
                stage="evidence-insight-release",
                scope_id=f"{workspace_id}:{signal.topic_id}",
                decision="fallback",
                reason="no_non_obvious_insight",
                parent_run_id=stored.run_id,
            )
            return recommended_angles, content_gap_map
        audit_stored = (
            self._llm.audit_evidence_insight(
                workspace_id=workspace_id,
                topic_id=signal.topic_id,
                topic_label=definition.label,
                insight=synthesis.insight,
                deterministic_metrics=deterministic_metrics,
                evidence=evidence,
                parent_run_id=stored.run_id,
            )
            if self._settings.llm_require_grounding_audit
            else None
        )
        audit = cast(InsightReleaseAudit, audit_stored.value) if audit_stored is not None else None
        if self._settings.llm_require_grounding_audit and (
            audit is None or audit.decision != "accept"
        ):
            self._llm.record_gate(
                stage="evidence-insight-release",
                scope_id=f"{workspace_id}:{signal.topic_id}",
                decision="fallback",
                reason=("audit_unavailable" if audit is None else "audit_rejected"),
                parent_run_id=stored.run_id,
            )
            return recommended_angles, content_gap_map
        self._llm.record_gate(
            stage="evidence-insight-release",
            scope_id=f"{workspace_id}:{signal.topic_id}",
            decision="accept",
            reason=("insight_release_audit_passed" if audit is not None else "audit_not_required"),
            parent_run_id=stored.run_id,
        )
        insight = synthesis.insight
        provenance: dict[str, object] = {
            "method": "llm",
            "task": "evidence-insight-synthesis",
            "run_id": stored.run_id,
            "provider": stored.provider,
            "model": stored.model,
            "prompt_version": stored.prompt_version,
            "cached": stored.cached,
            "policy_version": LLM_POLICY_VERSION,
            "audit": (
                {
                    "run_id": audit_stored.run_id,
                    "provider": audit_stored.provider,
                    "model": audit_stored.model,
                    "prompt_version": audit_stored.prompt_version,
                    "decision": audit.decision,
                    "summary": audit.summary,
                    "non_obviousness": audit.non_obviousness,
                    "decision_value": audit.decision_value,
                    "specificity": audit.specificity,
                    "decision_change": audit.decision_change,
                    "cached": audit_stored.cached,
                }
                if audit_stored is not None and audit is not None
                else {"required": False}
            ),
        }
        primary_key = str(gaps[0].get("gap_key", ""))
        enriched_gaps = [
            (
                {
                    **gap,
                    "title": insight.topic,
                    "audience_promise": insight.statement,
                    "why_now": insight.statement,
                    "differentiation": insight.why_non_obvious,
                    "title_directions": [
                        insight.topic,
                        insight.creator_question,
                    ],
                    "evidence": insight.evidence_refs,
                    "llm": provenance,
                    "release_ready": True,
                    "insight_status": "evidence_backed",
                    "insight_type": f"audited_{insight.insight_kind}",
                    "insight_statement": insight.statement,
                    "insight_reason_codes": [
                        "llm_grounding_audit_passed",
                        "llm_non_obviousness_audit_passed",
                        "creator_decision_change_identified",
                        "multiple_independent_evidence_refs",
                        "format_neutral_subject_insight",
                    ],
                    "insight_evidence": insight.evidence_refs,
                }
                if str(gap.get("gap_key", "")) == primary_key
                else gap
            )
            for gap in gaps
        ]
        by_key = {str(gap["gap_key"]): gap for gap in enriched_gaps}
        enriched_angles = [
            {
                **angle,
                **{
                    field: by_key[str(angle.get("gap_key", ""))][field]
                    for field in (
                        "title",
                        "audience_promise",
                        "why_now",
                        "differentiation",
                        "title_directions",
                        "evidence",
                        "llm",
                        "release_ready",
                        "insight_status",
                        "insight_type",
                        "insight_statement",
                        "insight_reason_codes",
                        "insight_evidence",
                    )
                    if str(angle.get("gap_key", "")) in by_key
                    and field in by_key[str(angle.get("gap_key", ""))]
                },
            }
            for angle in recommended_angles
        ]
        return (
            enriched_angles,
            {
                **content_gap_map,
                "opportunities": enriched_gaps,
                "llm": provenance,
            },
        )

    def _persist_content_gap_map(
        self,
        *,
        workspace_id: str,
        topic_id: str,
        content_gap_map: dict[str, object],
        observed_at: datetime,
    ) -> None:
        raw_patterns = content_gap_map.get("patterns", [])
        if isinstance(raw_patterns, list):
            for raw_pattern in raw_patterns:
                if not isinstance(raw_pattern, dict):
                    continue
                video_id = str(raw_pattern.get("video_id", ""))
                pattern_key = str(raw_pattern.get("pattern_key", ""))
                if not video_id or not pattern_key:
                    continue
                row_id = _stable_id(
                    "topic-content-pattern",
                    f"{topic_id}:{video_id}:{CONTENT_PATTERN_VERSION}",
                )
                pattern_row = self._session.get(TopicContentPattern, row_id)
                if pattern_row is None:
                    pattern_row = next(
                        (
                            pending
                            for pending in self._session.new
                            if isinstance(pending, TopicContentPattern) and pending.id == row_id
                        ),
                        None,
                    )
                evidence = [str(reference) for reference in raw_pattern.get("evidence_refs", [])]
                if pattern_row is None:
                    pattern_row = TopicContentPattern(
                        id=row_id,
                        topic_id=topic_id,
                        video_id=video_id,
                        pattern_key=pattern_key,
                        pattern_json=dict(raw_pattern),
                        evidence_json=evidence,
                        model_version=CONTENT_PATTERN_VERSION,
                        calculated_at=observed_at,
                    )
                    self._session.add(pattern_row)
                else:
                    pattern_row.pattern_key = pattern_key
                    pattern_row.pattern_json = dict(raw_pattern)
                    pattern_row.evidence_json = evidence
                    pattern_row.calculated_at = observed_at

        raw_opportunities = content_gap_map.get("opportunities", [])
        if not isinstance(raw_opportunities, list):
            return
        active_gap_keys: set[str] = set()
        for raw_gap in raw_opportunities[:3]:
            if not isinstance(raw_gap, dict):
                continue
            gap_key = str(raw_gap.get("gap_key", ""))
            if not gap_key:
                continue
            active_gap_keys.add(gap_key)
            row_id = _stable_id(
                "topic-content-gap",
                f"{workspace_id}:{topic_id}:{gap_key}:{CONTENT_GAP_VERSION}",
            )
            gap_row = self._session.get(TopicContentGap, row_id)
            evidence = [str(reference) for reference in raw_gap.get("evidence", [])]
            score_components = {
                str(key): float(value)
                for key, value in dict(raw_gap.get("score_components", {})).items()
            }
            values = {
                "rank": int(raw_gap.get("rank", 1)),
                "status": "active",
                "occupied_pattern_json": dict(raw_gap.get("occupied_pattern", {})),
                "open_gap_json": dict(raw_gap.get("open_gap", {})),
                "score_components_json": score_components,
                "evidence_json": evidence,
                "calculated_at": observed_at,
            }
            if gap_row is None:
                gap_row = TopicContentGap(
                    id=row_id,
                    workspace_id=workspace_id,
                    topic_id=topic_id,
                    gap_key=gap_key,
                    model_version=CONTENT_GAP_VERSION,
                    ranking_version=OPPORTUNITY_RANKING_VERSION,
                    **values,
                )
                self._session.add(gap_row)
            else:
                for key, value in values.items():
                    setattr(gap_row, key, value)
                gap_row.ranking_version = OPPORTUNITY_RANKING_VERSION
        for stale in self._session.scalars(
            select(TopicContentGap).where(
                TopicContentGap.workspace_id == workspace_id,
                TopicContentGap.topic_id == topic_id,
                TopicContentGap.status == "active",
            )
        ):
            if stale.model_version != CONTENT_GAP_VERSION or stale.gap_key not in active_gap_keys:
                stale.status = "superseded"

    def _provisional_angles(
        self,
        definition: TopicDefinition,
        evidence_ids: list[str],
        strongest_demand: DemandCluster | None,
        demand_comment_ids: list[str],
        transcript_segment_ids: list[str],
    ) -> list[dict[str, object]]:
        evidence = [f"video:{video_id}" for video_id in evidence_ids]
        demand_evidence = [f"comment:{comment_id}" for comment_id in demand_comment_ids]
        transcript_evidence = [
            f"transcript-segment:{segment_id}" for segment_id in transcript_segment_ids
        ]
        return [
            {
                "title": f"Open questions around {definition.label.lower()}",
                "audience_promise": (
                    f"Cover a recurring audience question found in "
                    f"{strongest_demand.comment_count} stored comments."
                    if strongest_demand is not None
                    else "Clarify the observed change, affected audience, and uncertainty."
                ),
                "why_now": (
                    f"The strongest demand cluster spans "
                    f"{strongest_demand.distinct_video_count} videos and "
                    f"{strongest_demand.distinct_channel_count} channels."
                    if strongest_demand is not None
                    else "Recent independent uploads support a timely update."
                ),
                "evidence": [
                    *evidence[:3],
                    *demand_evidence,
                    *transcript_evidence[:2],
                ],
                "unanswered_question": (
                    strongest_demand.summary
                    if strongest_demand is not None
                    else (
                        f"What is observably changing in {definition.label.lower()}, "
                        "who is affected, and what remains uncertain?"
                    )
                ),
                "format": "Creator’s choice",
                "effort": "Medium",
                "timing_risk": "The lifecycle can change as new snapshots arrive.",
                "title_directions": [
                    f"{definition.label}: observed changes and evidence",
                    f"{definition.label}: affected users and open questions",
                ],
                "avoid": (
                    "Quote only the stored verbatim snippets and do not "
                    "generalize beyond the sampled comments."
                    if strongest_demand is not None
                    else "Do not claim audience demand before comments are sampled."
                ),
            },
            {
                "title": "Unverified claims in current coverage",
                "audience_promise": (
                    "Separate repeated claims from facts supported by stored evidence."
                ),
                "why_now": "The topic has multiple independent evidence videos.",
                "evidence": [*evidence[:4], *transcript_evidence[:2]],
                "unanswered_question": (
                    "Which repeated claims are supported, contradicted, or still unverified?"
                ),
                "format": "Creator’s choice",
                "effort": "Medium–high",
                "timing_risk": "New evidence can change which claims remain unresolved.",
                "title_directions": [
                    f"{definition.label}: supported and unverified claims",
                    f"{definition.label}: what the current evidence establishes",
                ],
                "avoid": "Do not infer results that are absent from stored evidence.",
            },
            {
                "title": "Differences across current approaches",
                "audience_promise": (
                    "Help viewers understand how independent creators frame the shift."
                ),
                "why_now": "Coverage is diffusing across distinct channels.",
                "evidence": [*evidence, *transcript_evidence],
                "unanswered_question": ("Where do the current approaches materially differ?"),
                "format": "Creator’s choice",
                "effort": "Medium",
                "timing_risk": "New entrants can quickly change the comparison.",
                "title_directions": [
                    f"{definition.label}: where current approaches differ",
                    f"{definition.label}: shared claims and open disagreements",
                ],
                "avoid": "Do not present provisional channel fit as personalized proof.",
            },
        ]

    def _opportunity_window(
        self,
        lifecycle: str,
        observed_at: datetime,
    ) -> tuple[datetime, datetime]:
        offsets = {
            "Seed": (2, 10),
            "Emerging": (1, 7),
            "Breakout": (0, 4),
            "Mass Market": (0, 2),
            "Saturated": (0, 1),
            "Declining": (0, 1),
        }
        start_days, end_days = offsets.get(lifecycle, (1, 5))
        return (
            observed_at + timedelta(days=start_days),
            observed_at + timedelta(days=end_days),
        )

    def operational_metrics(self) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        stale_pipeline_runs = int(
            self._session.scalar(
                select(func.count(TopicPipelineRun.id)).where(
                    TopicPipelineRun.status == "running",
                    TopicPipelineRun.started_at
                    < now - timedelta(minutes=max(1, self._settings.topic_pipeline_stale_minutes)),
                )
            )
            or 0
        )
        latest_run = self._session.scalar(
            select(TopicPipelineRun).order_by(desc(TopicPipelineRun.started_at)).limit(1)
        )
        topics = int(
            self._session.scalar(
                select(func.count(Topic.id)).where(
                    Topic.source_kind == "live",
                    Topic.status == "active",
                )
            )
            or 0
        )
        signals = int(
            self._session.scalar(
                select(func.count(Signal.id)).where(
                    Signal.source_kind == "live",
                    Signal.status == "active",
                )
            )
            or 0
        )
        assigned = int(
            self._session.scalar(
                select(func.count(func.distinct(TopicVideoMembership.video_id)))
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(
                    Topic.source_kind == "live",
                    Topic.status == "active",
                )
            )
            or 0
        )
        embeddings = int(
            self._session.scalar(
                select(func.count(VideoEmbedding.video_id)).where(
                    VideoEmbedding.embedding_version == EMBEDDING_VERSION
                )
            )
            or 0
        )
        stale = int(
            self._session.scalar(
                select(func.count(Signal.id)).where(
                    Signal.source_kind == "live",
                    Signal.status == "active",
                    Signal.expires_at < now,
                )
            )
            or 0
        )
        llm_metrics = self._llm.operational_metrics()
        return {
            "active_topics": topics,
            "active_signals": signals,
            "assigned_videos": assigned,
            "embedding_count": embeddings,
            "stale_signals": stale,
            "stale_pipeline_runs": stale_pipeline_runs,
            "latest_run_status": latest_run.status if latest_run else None,
            "latest_run_at": (
                _aware(latest_run.completed_at).isoformat()
                if latest_run and latest_run.completed_at
                else None
            ),
            "source_video_count": latest_run.source_video_count if latest_run else 0,
            "eligible_video_count": (latest_run.eligible_video_count if latest_run else 0),
            "clustering_lag_seconds": (latest_run.clustering_lag_seconds if latest_run else 0),
            "signal_generation_lag_seconds": (
                latest_run.signal_generation_lag_seconds if latest_run else 0
            ),
            "llm_feature_enabled": llm_metrics["feature_enabled"],
            "llm_configured": llm_metrics["configured"],
            "llm_provider": llm_metrics["provider"],
            "llm_model": llm_metrics["model"],
            "llm_auditor_model": llm_metrics["auditor_model"],
            "llm_policy_version": llm_metrics["policy_version"],
            "llm_audit_required": llm_metrics["audit_required"],
            "llm_audit_run_count": llm_metrics["audit_run_count"],
            "llm_audit_acceptance_rate": llm_metrics["audit_acceptance_rate"],
            "llm_latest_trace_decisions": (
                {
                    str(key): int(value)
                    for key, value in dict(latest_run.llm_trace_json.get("decisions", {})).items()
                    if isinstance(value, int)
                }
                if latest_run
                and isinstance(latest_run.llm_trace_json, dict)
                and isinstance(
                    latest_run.llm_trace_json.get("decisions", {}),
                    dict,
                )
                else {}
            ),
            "llm_circuit_open": llm_metrics["circuit_open"],
            "llm_run_count": llm_metrics["run_count"],
            "llm_successful_runs": llm_metrics["successful_runs"],
            "llm_failed_or_rejected_runs": (llm_metrics["failed_or_rejected_runs"]),
            "llm_daily_tokens_used": llm_metrics["daily_tokens_used"],
            "llm_daily_token_budget": llm_metrics["daily_token_budget"],
            "llm_stale_runs": llm_metrics["stale_runs"],
            "llm_latest_status": llm_metrics["latest_status"],
            "llm_latest_run_at": llm_metrics["latest_run_at"],
        }
