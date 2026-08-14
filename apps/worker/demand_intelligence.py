from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from statistics import median
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    CommentFeature,
    CommentFetchRun,
    CommentTopicRelevance,
    CommentTopicRelevanceEvent,
    DemandCluster,
    DemandClusterComment,
    DemandPipelineRun,
    FieldProvenance,
    PanelMembership,
    ProviderFetch,
    Signal,
    Topic,
    TopicVideoMembership,
    VideoEmbedding,
    VideoFeature,
    VideoSnapshot,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from apps.api.provider_operations import (
    SqlAlchemyProviderFetchRecorder,
    SqlAlchemyProviderRoutingPolicy,
)
from apps.worker.video_intelligence import FEATURE_VERSION
from packages.clustering import cosine_similarity, mean_embedding, normalize_entities
from packages.clustering.semantic import PRODUCT_ENTITIES
from packages.demand import (
    CLASSIFIER_VERSION,
    RELEVANCE_MODEL_VERSION,
    CommentTopicRelevanceInput,
    classify_comment,
    classify_comment_topic_relevance,
    normalized_comment_fingerprint,
    taxonomy_label,
)
from packages.domain import CommentRecord
from packages.provider_sdk.base.interfaces import CommentProvider
from packages.provider_sdk.router import ProviderRouter, ProviderUnavailableError
from packages.provider_sdk.youtube_comments_web import YoutubeWebCommentProvider
from packages.provider_sdk.youtube_official import YoutubeOfficialProvider

LEGACY_DEMAND_CLUSTERING_VERSION = "demand-intent-clustering-v2"
DEMAND_CLUSTERING_VERSION = "demand-intent-clustering-v3-relevance"
PIPELINE_INTERVAL_SECONDS = 15 * 60
RELEVANCE_CLASSIFICATION_LOCK_KEY = 726_031_001
DEMAND_CLUSTERING_LOCK_KEY = 726_031_002
DEMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "learning": (
        "request_for_explanation",
        "request_for_tutorial",
    ),
    "evaluation": (
        "comparison_request",
        "test_or_proof_request",
        "skepticism",
        "objection",
        "correction",
    ),
    "adoption": (
        "missing_use_case",
        "regional_request",
        "pricing_request",
        "privacy_safety_concern",
    ),
    "updates": ("request_for_update",),
}


@dataclass(frozen=True)
class DemandRunResult:
    run_id: str
    reused: bool
    candidate_videos: int
    fetched_videos: int
    comments: int
    classified: int
    relevance_evaluated: int
    relevance_accepted: int
    relevance_rejected: int
    clusters: int
    provider_failures: int


@dataclass(frozen=True)
class RelevanceReplayResult:
    evaluated: int
    accepted: int
    rejected: int
    changed: int
    clusters: int = 0


@dataclass(frozen=True)
class ClusterComment:
    comment: YoutubeComment
    feature: CommentFeature
    video: YoutubeVideo
    channel: YoutubeChannel
    relevance: CommentTopicRelevance | None = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _stable_id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"earlysignal:{kind}:{value}"))


def _fetch_id(raw_ref: str) -> str:
    if not raw_ref.startswith("fetch://"):
        raise ValueError(f"Unsupported provider evidence reference: {raw_ref}")
    return raw_ref.removeprefix("fetch://")


def _normalized_text(value: str) -> str:
    return " ".join(html.unescape(value).replace("\x00", " ").split())[:10_000]


def _normalized_hash(text: str, published_at: datetime) -> str:
    bucket = int(_aware(published_at).timestamp()) // 3600
    return sha256(f"{text.lower()}:{bucket}".encode()).hexdigest()


def _group_for_taxonomy(taxonomy: str) -> str | None:
    for group, taxonomies in DEMAND_GROUPS.items():
        if taxonomy in taxonomies:
            return group
    return None


def _effective_relevance(row: CommentTopicRelevance) -> bool:
    return row.override_decision if row.override_decision is not None else row.is_relevant


def _postgres_transaction_lock(session: Session, key: int) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": key},
        )


def _relevance_state(row: CommentTopicRelevance) -> dict[str, object]:
    return {
        "is_relevant": row.is_relevant,
        "effective_relevant": _effective_relevance(row),
        "relevance_score": row.relevance_score,
        "intent": row.intent,
        "actionability": row.actionability,
        "reason_codes": list(row.reason_codes_json),
        "supported_entities": list(row.supported_entities_json),
        "supported_claims": list(row.supported_claims_json),
        "override_decision": row.override_decision,
        "override_reason": row.override_reason,
        "model_version": row.model_version,
        "input_hash": row.input_hash,
    }


class DemandIntelligenceService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        recorder = SqlAlchemyProviderFetchRecorder(session, settings)
        providers: dict[str, CommentProvider] = {
            "youtube_official": YoutubeOfficialProvider(
                api_key=settings.youtube_api_key,
                recorder=recorder,
            ),
            "youtube_web_comments": YoutubeWebCommentProvider(recorder=recorder),
        }
        priority = [
            name.strip()
            for name in settings.comment_provider_priority.split(",")
            if name.strip() in providers
        ]
        if not priority:
            priority = ["youtube_web_comments"]
        self._router = ProviderRouter(
            discovery=[],
            metadata=[],
            channels=[],
            comments=[providers[name] for name in priority],
            transcripts=[],
            policy=SqlAlchemyProviderRoutingPolicy(session, settings),
            retry_attempts=settings.provider_retry_attempts,
            retry_base_seconds=settings.provider_retry_base_seconds,
        )

    async def run(
        self,
        *,
        force: bool = False,
        limit: int | None = None,
        selection: str = "signal",
    ) -> DemandRunResult:
        started_at = datetime.now(tz=UTC)
        bucket = int(started_at.timestamp()) // PIPELINE_INTERVAL_SECONDS
        suffix = f":manual:{uuid4()}" if force else ""
        clustering_version = (
            DEMAND_CLUSTERING_VERSION
            if self._settings.feature_comment_topic_relevance
            else LEGACY_DEMAND_CLUSTERING_VERSION
        )
        relevance_version = (
            RELEVANCE_MODEL_VERSION
            if self._settings.feature_comment_topic_relevance
            else "disabled"
        )
        idempotency_key = (
            f"demand:{CLASSIFIER_VERSION}:{clustering_version}:{relevance_version}:{bucket}{suffix}"
        )
        existing = self._session.scalar(
            select(DemandPipelineRun).where(DemandPipelineRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return self._result(existing, reused=True)
        run = DemandPipelineRun(
            id=str(uuid4()),
            idempotency_key=idempotency_key,
            started_at=started_at,
            completed_at=None,
            status="running",
            classifier_version=CLASSIFIER_VERSION,
            clustering_version=clustering_version,
            candidate_video_count=0,
            fetched_video_count=0,
            comment_count=0,
            classified_count=0,
            cluster_count=0,
            relevance_evaluated_count=0,
            relevance_accepted_count=0,
            relevance_rejected_count=0,
            relevance_model_version=(
                RELEVANCE_MODEL_VERSION if self._settings.feature_comment_topic_relevance else None
            ),
            provider_failure_count=0,
            processing_lag_seconds=0,
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            chooser = (
                self.select_panel_candidates if selection == "panel" else self.select_candidates
            )
            candidates = chooser(limit=limit or self._settings.comment_candidate_limit)
            run.candidate_video_count = len(candidates)
            fetched_videos = 0
            for video in candidates:
                fetched = False
                for order in ("relevance", "time"):
                    changed = await self._fetch_video_comments(
                        video,
                        order=order,
                        force=force,
                        observed_at=started_at,
                    )
                    fetched = fetched or changed
                fetched_videos += int(fetched)
            classified = self.classify_comments()
            relevance = (
                self.classify_comment_relevance()
                if self._settings.feature_comment_topic_relevance
                else RelevanceReplayResult(
                    evaluated=0,
                    accepted=0,
                    rejected=0,
                    changed=0,
                )
            )
            clusters = self.cluster_demand(observed_at=datetime.now(tz=UTC))
            comment_count = self._live_comment_count()
            completed_at = datetime.now(tz=UTC)
            run.completed_at = completed_at
            run.status = "success"
            run.fetched_video_count = fetched_videos
            run.comment_count = comment_count
            run.classified_count = classified
            run.cluster_count = clusters
            run.relevance_evaluated_count = relevance.evaluated
            run.relevance_accepted_count = relevance.accepted
            run.relevance_rejected_count = relevance.rejected
            run.provider_failure_count = self._provider_failures_since(started_at)
            newest_comment = self._session.scalar(select(func.max(YoutubeComment.published_at)))
            run.processing_lag_seconds = (
                max(0, round((completed_at - _aware(newest_comment)).total_seconds()))
                if newest_comment is not None
                else 0
            )
            self._session.commit()
            return self._result(run, reused=False)
        except Exception as error:
            self._session.rollback()
            failed_run = self._session.get(DemandPipelineRun, run.id)
            if failed_run is None:
                raise
            failed_run.completed_at = datetime.now(tz=UTC)
            failed_run.status = "failed"
            failed_run.error_code = type(error).__name__
            failed_run.error_message = str(error)[:1000]
            failed_run.provider_failure_count = self._provider_failures_since(started_at)
            self._session.commit()
            raise

    def select_panel_candidates(self, *, limit: int) -> list[YoutubeVideo]:
        """Recent panel uploads that have comments, ranked by reach.

        The original selection required a video to belong to an active v1
        signal. That is why only 13k comments were ever collected: comment
        coverage was gated behind a scorer that never worked, so the demand
        evidence the product sells could only exist where the broken score had
        already fired.

        Demand items need the opposite — broad coverage of what the observed
        population actually published, with reach deciding the order.
        """

        latest = (
            select(
                VideoSnapshot.video_id,
                func.max(VideoSnapshot.view_count).label("view_count"),
                func.max(VideoSnapshot.comment_count).label("comment_count"),
            )
            .group_by(VideoSnapshot.video_id)
            .subquery()
        )
        return list(
            self._session.scalars(
                select(YoutubeVideo)
                .join(PanelMembership, PanelMembership.channel_id == YoutubeVideo.channel_id)
                .outerjoin(latest, latest.c.video_id == YoutubeVideo.id)
                .where(
                    PanelMembership.left_at.is_(None),
                    YoutubeVideo.published_at >= datetime.now(tz=UTC) - timedelta(days=30),
                    func.coalesce(latest.c.comment_count, 0) > 0,
                )
                .order_by(
                    desc(func.coalesce(latest.c.view_count, 0)),
                    desc(YoutubeVideo.published_at),
                )
                .limit(max(1, limit))
            )
        )

    def select_candidates(self, *, limit: int) -> list[YoutubeVideo]:
        latest_comments = (
            select(
                VideoSnapshot.video_id,
                func.max(VideoSnapshot.comment_count).label("comment_count"),
            )
            .group_by(VideoSnapshot.video_id)
            .subquery()
        )
        live_signal_score = (
            select(func.max(Signal.score))
            .select_from(TopicVideoMembership)
            .join(Topic, Topic.id == TopicVideoMembership.topic_id)
            .join(Signal, Signal.topic_id == Topic.id)
            .where(
                TopicVideoMembership.video_id == YoutubeVideo.id,
                Topic.source_kind == "live",
                Topic.status == "active",
                Signal.status == "active",
            )
            .correlate(YoutubeVideo)
            .scalar_subquery()
        )
        return list(
            self._session.scalars(
                select(YoutubeVideo)
                .join(
                    VideoFeature,
                    (VideoFeature.video_id == YoutubeVideo.id)
                    & (VideoFeature.feature_version == FEATURE_VERSION),
                )
                .outerjoin(
                    latest_comments,
                    latest_comments.c.video_id == YoutubeVideo.id,
                )
                .where(
                    live_signal_score.is_not(None),
                    YoutubeVideo.published_at >= datetime.now(tz=UTC) - timedelta(days=30),
                    func.coalesce(latest_comments.c.comment_count, 0) > 0,
                )
                .order_by(
                    desc(live_signal_score),
                    desc(VideoFeature.outlier_ratio),
                    desc(YoutubeVideo.published_at),
                )
                .limit(max(1, limit))
            )
        )

    async def _fetch_video_comments(
        self,
        video: YoutubeVideo,
        *,
        order: str,
        force: bool,
        observed_at: datetime,
    ) -> bool:
        interval = max(1, self._settings.comment_refresh_hours) * 3600
        bucket = int(observed_at.timestamp()) // interval
        suffix = f":manual:{uuid4()}" if force else ""
        key = f"comments:auto:{video.id}:{order}:{bucket}{suffix}"
        existing = self._session.scalar(
            select(CommentFetchRun).where(CommentFetchRun.idempotency_key == key)
        )
        if existing is not None:
            return False
        run = CommentFetchRun(
            id=str(uuid4()),
            video_id=video.id,
            provider="auto",
            order=order,
            idempotency_key=key,
            started_at=datetime.now(tz=UTC),
            completed_at=None,
            status="running",
            result_count=0,
            retained_count=0,
            comments_disabled=False,
            provider_fetch_ids_json=[],
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            comments = list(
                await self._router.comments(
                    video.youtube_video_id,
                    order=order,
                    limit=self._settings.comment_sample_limit,
                    include_replies=False,
                )
            )
            fetch_ids = sorted({_fetch_id(comment.raw_ref) for comment in comments})
            providers = list(
                self._session.scalars(
                    select(ProviderFetch.provider).where(ProviderFetch.id.in_(fetch_ids))
                )
            )
            retained = self._upsert_comments(video, comments, order=order)
            run.provider = providers[0] if providers else "unknown"
            run.provider_fetch_ids_json = fetch_ids
            run.result_count = len(comments)
            run.retained_count = retained
            run.status = "success"
            run.completed_at = datetime.now(tz=UTC)
            self._session.commit()
            return True
        except ProviderUnavailableError as error:
            message = str(error)
            run.comments_disabled = "disabled" in message.lower()
            run.status = "skipped" if run.comments_disabled else "failed"
            run.error_code = "comments_disabled" if run.comments_disabled else "providers_failed"
            run.error_message = message[:1000]
            run.completed_at = datetime.now(tz=UTC)
            self._session.commit()
            return False

    def _upsert_comments(
        self,
        video: YoutubeVideo,
        comments: list[CommentRecord],
        *,
        order: str,
    ) -> int:
        retained = 0
        for record in comments:
            text = _normalized_text(record.text)
            if not text:
                continue
            normalized_hash = _normalized_hash(text, record.published_at)
            row = self._session.scalar(
                select(YoutubeComment).where(
                    YoutubeComment.video_id == video.id,
                    (YoutubeComment.provider_comment_id == record.comment_id)
                    | (YoutubeComment.normalized_hash == normalized_hash),
                )
            )
            fetch_id = _fetch_id(record.raw_ref)
            needs_provenance = row is None
            if row is None:
                row = YoutubeComment(
                    id=_stable_id(
                        "comment",
                        f"{video.id}:{record.comment_id or normalized_hash}",
                    ),
                    provider_comment_id=record.comment_id or normalized_hash,
                    video_id=video.id,
                    parent_comment_id=(record.parent_id or "")[:36] or None,
                    text=text,
                    published_at=_aware(record.published_at),
                    updated_at=(
                        _aware(record.updated_at) if record.updated_at is not None else None
                    ),
                    like_count=max(0, record.like_count),
                    reply_count=max(0, record.reply_count),
                    is_reply=record.is_reply,
                    language=record.language,
                    author_hash=record.author_hash,
                    fetched_order=order,
                    normalized_hash=normalized_hash,
                    provider_fetch_id=fetch_id,
                    created_at=datetime.now(tz=UTC),
                )
                self._session.add(row)
                retained += 1
            else:
                row.text = text
                row.updated_at = (
                    _aware(record.updated_at) if record.updated_at is not None else row.updated_at
                )
                row.like_count = max(row.like_count, record.like_count)
                row.reply_count = max(row.reply_count, record.reply_count)
                row.author_hash = row.author_hash or record.author_hash
                row.provider_fetch_id = fetch_id
                needs_provenance = (
                    self._session.scalar(
                        select(FieldProvenance.id)
                        .where(
                            FieldProvenance.entity_type == "comment",
                            FieldProvenance.entity_id == row.id,
                        )
                        .limit(1)
                    )
                    is None
                )
            if needs_provenance:
                self._record_comment_provenance(row, fetch_id)
        self._session.commit()
        return retained

    def _record_comment_provenance(
        self,
        comment: YoutubeComment,
        fetch_id: str,
    ) -> None:
        observed_at = datetime.now(tz=UTC)
        fields = {
            "text": comment.text,
            "published_at": comment.published_at,
            "like_count": comment.like_count,
            "reply_count": comment.reply_count,
        }
        for field_name, value in fields.items():
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            self._session.add(
                FieldProvenance(
                    id=str(uuid4()),
                    entity_type="comment",
                    entity_id=comment.id,
                    field_name=field_name,
                    provider_fetch_id=fetch_id,
                    observed_at=observed_at,
                    confidence=1.0,
                    value_hash=sha256(encoded.encode()).hexdigest(),
                )
            )

    def classify_comments(self) -> int:
        comments = list(
            self._session.scalars(
                select(YoutubeComment)
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == YoutubeComment.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
                .distinct()
            )
        )
        now = datetime.now(tz=UTC)
        for comment in comments:
            analysis = classify_comment(comment.text)
            row = self._session.get(CommentFeature, comment.id)
            if row is None:
                self._session.add(
                    CommentFeature(
                        comment_id=comment.id,
                        taxonomy=analysis.taxonomy,
                        demand_probability=analysis.demand_probability,
                        spam_probability=analysis.spam_probability,
                        sentiment=analysis.sentiment,
                        embedding_json=analysis.embedding,
                        model_version=CLASSIFIER_VERSION,
                        calculated_at=now,
                    )
                )
            else:
                row.taxonomy = analysis.taxonomy
                row.demand_probability = analysis.demand_probability
                row.spam_probability = analysis.spam_probability
                row.sentiment = analysis.sentiment
                row.embedding_json = analysis.embedding
                row.model_version = CLASSIFIER_VERSION
                row.calculated_at = now
        self._session.commit()
        return len(comments)

    def classify_comment_relevance(
        self,
        *,
        topic_id: str | None = None,
    ) -> RelevanceReplayResult:
        _postgres_transaction_lock(
            self._session,
            RELEVANCE_CLASSIFICATION_LOCK_KEY,
        )
        query = (
            select(
                YoutubeComment,
                CommentFeature,
                YoutubeVideo,
                Topic,
            )
            .join(
                TopicVideoMembership,
                TopicVideoMembership.video_id == YoutubeComment.video_id,
            )
            .join(
                CommentFeature,
                CommentFeature.comment_id == YoutubeComment.id,
            )
            .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
            .join(Topic, Topic.id == TopicVideoMembership.topic_id)
            .where(Topic.source_kind == "live")
        )
        if topic_id is not None:
            query = query.where(Topic.id == topic_id)
        rows = list(self._session.execute(query))
        duplicate_counts = Counter(
            (
                topic.id,
                normalized_comment_fingerprint(comment.text),
                comment.author_hash or comment.id,
            )
            for comment, _feature, _video, topic in rows
        )
        evaluated = 0
        changed = 0
        now = datetime.now(tz=UTC)
        for comment, feature, video, topic in rows:
            embedding = self._session.scalar(
                select(VideoEmbedding)
                .where(VideoEmbedding.video_id == video.id)
                .order_by(desc(VideoEmbedding.calculated_at))
                .limit(1)
            )
            video_entities = tuple(
                dict.fromkeys(
                    (
                        *(embedding.entities_json if embedding is not None else []),
                        *normalize_entities(video.title, video.description),
                    )
                )
            )
            duplicate_count = duplicate_counts[
                (
                    topic.id,
                    normalized_comment_fingerprint(comment.text),
                    comment.author_hash or comment.id,
                )
            ]
            classifier_input = CommentTopicRelevanceInput(
                comment_text=comment.text,
                intent=feature.taxonomy,
                demand_probability=feature.demand_probability,
                spam_probability=feature.spam_probability,
                topic_label=topic.canonical_label,
                topic_entities=tuple(topic.entities_json),
                video_title=video.title,
                video_description=video.description,
                video_entities=video_entities,
                duplicate_count=duplicate_count,
            )
            result = classify_comment_topic_relevance(classifier_input)
            input_payload = {
                "comment_id": comment.id,
                "comment_hash": normalized_comment_fingerprint(comment.text),
                "comment_feature_version": feature.model_version,
                "topic_id": topic.id,
                "topic_label": topic.canonical_label,
                "topic_entities": list(topic.entities_json),
                "topic_embedding_version": topic.embedding_version,
                "video_id": video.id,
                "video_title": video.title,
                "video_entities": list(video_entities),
                "duplicate_count": duplicate_count,
                "model_version": RELEVANCE_MODEL_VERSION,
            }
            input_hash = sha256(
                json.dumps(
                    input_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            relevance_id = _stable_id(
                "comment-topic-relevance",
                f"{topic.id}:{comment.id}",
            )
            row = self._session.get(CommentTopicRelevance, relevance_id)
            previous = _relevance_state(row) if row is not None else {}
            previous_updated_at = (
                row.updated_at.isoformat()
                if row is not None and row.updated_at is not None
                else "new"
            )
            if (
                row is not None
                and row.input_hash == input_hash
                and row.model_version == RELEVANCE_MODEL_VERSION
            ):
                evaluated += 1
                continue
            if row is None:
                row = CommentTopicRelevance(
                    id=relevance_id,
                    comment_id=comment.id,
                    topic_id=topic.id,
                    video_id=video.id,
                    is_relevant=result.is_relevant,
                    relevance_score=result.relevance_score,
                    comment_topic_semantic_similarity=(result.comment_topic_semantic_similarity),
                    comment_video_semantic_similarity=(result.comment_video_semantic_similarity),
                    entity_overlap_score=result.entity_overlap_score,
                    claim_support_score=result.claim_support_score,
                    intent_actionability_score=result.intent_actionability_score,
                    duplicate_or_echo_probability=(result.duplicate_or_echo_probability),
                    spam_probability=result.spam_probability,
                    intent=result.intent,
                    actionability=result.actionability,
                    supported_entities_json=list(result.supported_entities),
                    supported_claims_json=list(result.supported_claims),
                    reason_codes_json=list(result.reason_codes),
                    evidence_json=input_payload,
                    model_version=result.model_version,
                    input_hash=input_hash,
                    override_decision=None,
                    override_reason=None,
                    reviewer_id=None,
                    reviewed_at=None,
                    calculated_at=now,
                    updated_at=now,
                )
                self._session.add(row)
                event_type = "classified"
            else:
                row.video_id = video.id
                row.is_relevant = result.is_relevant
                row.relevance_score = result.relevance_score
                row.comment_topic_semantic_similarity = result.comment_topic_semantic_similarity
                row.comment_video_semantic_similarity = result.comment_video_semantic_similarity
                row.entity_overlap_score = result.entity_overlap_score
                row.claim_support_score = result.claim_support_score
                row.intent_actionability_score = result.intent_actionability_score
                row.duplicate_or_echo_probability = result.duplicate_or_echo_probability
                row.spam_probability = result.spam_probability
                row.intent = result.intent
                row.actionability = result.actionability
                row.supported_entities_json = list(result.supported_entities)
                row.supported_claims_json = list(result.supported_claims)
                row.reason_codes_json = list(result.reason_codes)
                row.evidence_json = input_payload
                row.model_version = result.model_version
                row.input_hash = input_hash
                row.calculated_at = now
                row.updated_at = now
                event_type = "reclassified"
            self._session.flush()
            current = _relevance_state(row)
            transition_hash = sha256(
                (f"{row.id}:{RELEVANCE_MODEL_VERSION}:{previous_updated_at}:{input_hash}").encode()
            ).hexdigest()
            self._session.add(
                CommentTopicRelevanceEvent(
                    id=str(uuid4()),
                    relevance_id=row.id,
                    topic_id=topic.id,
                    comment_id=comment.id,
                    event_type=event_type,
                    previous_result_json=previous,
                    result_json=current,
                    actor_id=None,
                    note="Deterministic comment-to-topic relevance evaluation.",
                    idempotency_key=(f"comment-topic-relevance:{row.id}:{transition_hash}"),
                    model_version=RELEVANCE_MODEL_VERSION,
                    created_at=now,
                )
            )
            evaluated += 1
            changed += 1
        self._session.commit()
        relevance_query = (
            select(CommentTopicRelevance)
            .join(Topic, Topic.id == CommentTopicRelevance.topic_id)
            .where(Topic.source_kind == "live")
        )
        if topic_id is not None:
            relevance_query = relevance_query.where(CommentTopicRelevance.topic_id == topic_id)
        relevance_rows = list(self._session.scalars(relevance_query))
        accepted = sum(_effective_relevance(row) for row in relevance_rows)
        return RelevanceReplayResult(
            evaluated=evaluated,
            accepted=accepted,
            rejected=max(0, len(relevance_rows) - accepted),
            changed=changed,
        )

    def replay_relevance(
        self,
        *,
        topic_id: str | None = None,
    ) -> RelevanceReplayResult:
        self.classify_comments()
        relevance = self.classify_comment_relevance(topic_id=topic_id)
        clusters = self.cluster_demand(observed_at=datetime.now(tz=UTC))
        return RelevanceReplayResult(
            evaluated=relevance.evaluated,
            accepted=relevance.accepted,
            rejected=relevance.rejected,
            changed=relevance.changed,
            clusters=clusters,
        )

    def override_relevance(
        self,
        relevance_id: str,
        *,
        decision: bool | None,
        reason: str,
        reviewer_id: str,
        idempotency_key: str,
    ) -> CommentTopicRelevance:
        row = self._session.get(CommentTopicRelevance, relevance_id)
        if row is None:
            raise ValueError("Comment relevance record not found")
        existing = self._session.scalar(
            select(CommentTopicRelevanceEvent).where(
                CommentTopicRelevanceEvent.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return row
        previous = _relevance_state(row)
        now = datetime.now(tz=UTC)
        row.override_decision = decision
        row.override_reason = reason
        row.reviewer_id = reviewer_id
        row.reviewed_at = now
        row.updated_at = now
        self._session.add(
            CommentTopicRelevanceEvent(
                id=str(uuid4()),
                relevance_id=row.id,
                topic_id=row.topic_id,
                comment_id=row.comment_id,
                event_type="override_cleared" if decision is None else "manual_override",
                previous_result_json=previous,
                result_json=_relevance_state(row),
                actor_id=reviewer_id,
                note=reason,
                idempotency_key=idempotency_key,
                model_version=row.model_version,
                created_at=now,
            )
        )
        self._session.commit()
        self.cluster_demand(observed_at=now)
        self._session.refresh(row)
        return row

    def relevance_for_topic(
        self,
        topic_id: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, object]]:
        rows = list(
            self._session.execute(
                select(
                    CommentTopicRelevance,
                    YoutubeComment,
                    YoutubeVideo,
                    YoutubeChannel,
                )
                .join(
                    YoutubeComment,
                    YoutubeComment.id == CommentTopicRelevance.comment_id,
                )
                .join(
                    YoutubeVideo,
                    YoutubeVideo.id == CommentTopicRelevance.video_id,
                )
                .join(
                    YoutubeChannel,
                    YoutubeChannel.id == YoutubeVideo.channel_id,
                )
                .where(CommentTopicRelevance.topic_id == topic_id)
                .order_by(
                    desc(CommentTopicRelevance.override_decision.is_not(None)),
                    desc(CommentTopicRelevance.relevance_score),
                    desc(YoutubeComment.like_count),
                )
                .limit(max(1, limit))
            )
        )
        return [
            {
                "id": relevance.id,
                "comment_id": comment.id,
                "comment_text": comment.text,
                "video_id": video.id,
                "video_title": video.title,
                "video_url": video.canonical_url,
                "channel": channel.title,
                "intent": relevance.intent,
                "actionability": relevance.actionability,
                "is_relevant": relevance.is_relevant,
                "effective_relevant": _effective_relevance(relevance),
                "relevance_score": relevance.relevance_score,
                "comment_topic_semantic_similarity": (relevance.comment_topic_semantic_similarity),
                "comment_video_semantic_similarity": (relevance.comment_video_semantic_similarity),
                "entity_overlap_score": relevance.entity_overlap_score,
                "claim_support_score": relevance.claim_support_score,
                "duplicate_or_echo_probability": (relevance.duplicate_or_echo_probability),
                "supported_entities": relevance.supported_entities_json,
                "supported_claims": relevance.supported_claims_json,
                "reason_codes": relevance.reason_codes_json,
                "override_decision": relevance.override_decision,
                "override_reason": relevance.override_reason,
                "reviewer_id": relevance.reviewer_id,
                "reviewed_at": relevance.reviewed_at,
                "model_version": relevance.model_version,
            }
            for relevance, comment, video, channel in rows
        ]

    def cluster_demand(self, *, observed_at: datetime) -> int:
        _postgres_transaction_lock(
            self._session,
            DEMAND_CLUSTERING_LOCK_KEY,
        )
        live_topic_ids = list(
            self._session.scalars(select(Topic.id).where(Topic.source_kind == "live"))
        )
        cluster_ids = select(DemandCluster.id).where(DemandCluster.topic_id.in_(live_topic_ids))
        self._session.execute(
            delete(DemandClusterComment).where(
                DemandClusterComment.demand_cluster_id.in_(cluster_ids)
            )
        )
        self._session.execute(
            delete(DemandCluster).where(DemandCluster.topic_id.in_(live_topic_ids))
        )
        self._session.flush()
        cluster_count = 0
        for topic_id in live_topic_ids:
            topic = self._session.get(Topic, topic_id)
            if topic is None:
                continue
            relevance_by_comment = (
                {
                    row.comment_id: row
                    for row in self._session.scalars(
                        select(CommentTopicRelevance).where(
                            CommentTopicRelevance.topic_id == topic_id
                        )
                    )
                }
                if self._settings.feature_comment_topic_relevance
                else {}
            )
            raw_rows = [
                ClusterComment(
                    comment,
                    feature,
                    video,
                    channel,
                    relevance_by_comment.get(comment.id),
                )
                for comment, feature, video, channel in self._session.execute(
                    select(
                        YoutubeComment,
                        CommentFeature,
                        YoutubeVideo,
                        YoutubeChannel,
                    )
                    .join(
                        TopicVideoMembership,
                        TopicVideoMembership.video_id == YoutubeComment.video_id,
                    )
                    .join(
                        CommentFeature,
                        CommentFeature.comment_id == YoutubeComment.id,
                    )
                    .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
                    .join(YoutubeChannel, YoutubeChannel.id == YoutubeVideo.channel_id)
                    .where(
                        TopicVideoMembership.topic_id == topic_id,
                        CommentFeature.demand_probability >= 0.5,
                        CommentFeature.spam_probability < 0.5,
                    )
                )
            ]
            if self._settings.feature_comment_topic_relevance:
                rows = [
                    row
                    for row in raw_rows
                    if row.relevance is not None and _effective_relevance(row.relevance)
                ]
            else:
                rows = raw_rows
            grouped: dict[str, list[ClusterComment]] = defaultdict(list)
            for row in rows:
                group = _group_for_taxonomy(row.feature.taxonomy)
                if group is not None:
                    grouped[group].append(row)
            for group, members in grouped.items():
                distinct_videos = {item.video.id for item in members}
                distinct_channels = {item.channel.id for item in members}
                distinct_commenters = {
                    item.comment.author_hash or item.comment.id for item in members
                }
                if (
                    len(members) < 2
                    or len(distinct_videos) < 2
                    or len(distinct_channels) < 2
                    or len(distinct_commenters) < 2
                ):
                    continue
                relevance_scores = [
                    item.relevance.relevance_score for item in members if item.relevance is not None
                ]
                median_relevance = (
                    round(float(median(relevance_scores)), 4) if relevance_scores else None
                )
                high_actionability_count = sum(
                    item.relevance is not None and item.relevance.actionability == "high"
                    for item in members
                )
                product_anchors = set(topic.entities_json) & PRODUCT_ENTITIES
                entity_claim_coverage = not product_anchors or any(
                    item.relevance is not None
                    and (
                        bool(set(item.relevance.supported_entities_json) & product_anchors)
                        or item.relevance.claim_support_score >= 0.7
                    )
                    for item in members
                )
                user_visible = not self._settings.feature_comment_topic_relevance or (
                    len(members) >= 3
                    and len(distinct_videos) >= 2
                    and len(distinct_channels) >= 2
                    and len(distinct_commenters) >= 3
                    and (median_relevance or 0) >= 0.70
                    and high_actionability_count >= 1
                    and entity_claim_coverage
                )
                visibility_status = (
                    "legacy_visible"
                    if not self._settings.feature_comment_topic_relevance
                    else "user_visible"
                    if user_visible
                    else "internal_candidate"
                )
                evidence_strength = (
                    "Unverified"
                    if not self._settings.feature_comment_topic_relevance
                    else "Strong"
                    if user_visible
                    and (median_relevance or 0) >= 0.82
                    and len(members) >= 5
                    and len(distinct_channels) >= 3
                    else "Moderate"
                    if user_visible
                    else "Weak"
                )
                taxonomy_counts = Counter(item.feature.taxonomy for item in members)
                taxonomy = taxonomy_counts.most_common(1)[0][0]
                label = taxonomy_label(taxonomy)
                cluster_id = _stable_id("demand-cluster", f"{topic_id}:{group}")
                first_observed = min(_aware(item.comment.published_at) for item in members)
                last_observed = max(_aware(item.comment.published_at) for item in members)
                score = self._demand_score(
                    members,
                    observed_at=observed_at,
                    videos=len(distinct_videos),
                    channels=len(distinct_channels),
                    commenters=len(distinct_commenters),
                )
                comment_kind = (
                    "relevant" if self._settings.feature_comment_topic_relevance else "stored"
                )
                self._session.add(
                    DemandCluster(
                        id=cluster_id,
                        topic_id=topic_id,
                        label=label,
                        summary=(
                            f"{len(members)} {comment_kind} comments across "
                            f"{len(distinct_videos)} videos and "
                            f"{len(distinct_channels)} channels repeat a "
                            f"{taxonomy.replace('_', ' ')} intent."
                        ),
                        taxonomy=taxonomy,
                        comment_count=len(members),
                        distinct_commenter_count=len(distinct_commenters),
                        distinct_video_count=len(distinct_videos),
                        distinct_channel_count=len(distinct_channels),
                        demand_score=score,
                        first_observed_at=first_observed,
                        last_observed_at=last_observed,
                        model_version=(
                            DEMAND_CLUSTERING_VERSION
                            if self._settings.feature_comment_topic_relevance
                            else LEGACY_DEMAND_CLUSTERING_VERSION
                        ),
                        visibility_status=visibility_status,
                        evidence_strength=evidence_strength,
                        median_relevance_score=median_relevance,
                        high_actionability_count=high_actionability_count,
                        relevance_model_version=(
                            RELEVANCE_MODEL_VERSION
                            if self._settings.feature_comment_topic_relevance
                            else None
                        ),
                    )
                )
                centroid = mean_embedding([item.feature.embedding_json for item in members])
                ranked = sorted(
                    members,
                    key=lambda item: (
                        (
                            item.relevance.relevance_score
                            if item.relevance is not None
                            else item.feature.demand_probability
                        )
                        + min(math.log1p(item.comment.like_count) / 10, 0.3),
                        item.comment.like_count,
                    ),
                    reverse=True,
                )
                representatives = {item.comment.id for item in ranked[:3]}
                for item in members:
                    similarity = (
                        item.relevance.relevance_score
                        if item.relevance is not None
                        else max(
                            0.0,
                            cosine_similarity(item.feature.embedding_json, centroid),
                        )
                    )
                    self._session.add(
                        DemandClusterComment(
                            demand_cluster_id=cluster_id,
                            comment_id=item.comment.id,
                            membership_score=round(
                                min(1.0, 0.55 + similarity * 0.45),
                                4,
                            ),
                            is_representative=item.comment.id in representatives,
                        )
                    )
                cluster_count += 1
        self._session.commit()
        return cluster_count

    def _demand_score(
        self,
        members: list[ClusterComment],
        *,
        observed_at: datetime,
        videos: int,
        channels: int,
        commenters: int,
    ) -> float:
        count_score = min(len(members) / 10, 1)
        video_score = min(videos / 4, 1)
        channel_score = min(channels / 4, 1)
        commenter_score = min(commenters / 8, 1)
        recent = sum(
            1
            for item in members
            if _aware(item.comment.published_at) >= observed_at - timedelta(days=14)
        ) / max(len(members), 1)
        engagement = min(
            sum(math.log1p(item.comment.like_count) for item in members) / max(len(members) * 4, 1),
            1,
        )
        return round(
            min(
                100,
                (
                    count_score * 25
                    + video_score * 20
                    + channel_score * 20
                    + commenter_score * 10
                    + recent * 15
                    + engagement * 10
                ),
            ),
            1,
        )

    def _live_comment_count(self) -> int:
        return int(
            self._session.scalar(
                select(func.count(func.distinct(YoutubeComment.id)))
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == YoutubeComment.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )

    def _provider_failures_since(self, started_at: datetime) -> int:
        return int(
            self._session.scalar(
                select(func.count(ProviderFetch.id)).where(
                    ProviderFetch.capability == "comments",
                    ProviderFetch.status == "failed",
                    ProviderFetch.started_at >= started_at,
                )
            )
            or 0
        )

    def operational_metrics(self) -> dict[str, int | float | str | None]:
        latest = self._session.scalar(
            select(DemandPipelineRun).order_by(desc(DemandPipelineRun.started_at))
        )
        sampled_videos = int(
            self._session.scalar(
                select(func.count(func.distinct(YoutubeComment.video_id)))
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == YoutubeComment.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        feature_count = int(
            self._session.scalar(
                select(func.count(CommentFeature.comment_id))
                .join(
                    YoutubeComment,
                    YoutubeComment.id == CommentFeature.comment_id,
                )
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == YoutubeComment.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        clusters = int(
            self._session.scalar(
                select(func.count(DemandCluster.id))
                .join(Topic, Topic.id == DemandCluster.topic_id)
                .where(
                    Topic.source_kind == "live",
                    DemandCluster.visibility_status != "internal_candidate",
                )
            )
            or 0
        )
        internal_clusters = int(
            self._session.scalar(
                select(func.count(DemandCluster.id))
                .join(Topic, Topic.id == DemandCluster.topic_id)
                .where(
                    Topic.source_kind == "live",
                    DemandCluster.visibility_status == "internal_candidate",
                )
            )
            or 0
        )
        topics_with_demand = int(
            self._session.scalar(
                select(func.count(func.distinct(DemandCluster.topic_id)))
                .join(Topic, Topic.id == DemandCluster.topic_id)
                .where(
                    Topic.source_kind == "live",
                    DemandCluster.visibility_status != "internal_candidate",
                )
            )
            or 0
        )
        relevance_rows = list(
            self._session.scalars(
                select(CommentTopicRelevance)
                .join(Topic, Topic.id == CommentTopicRelevance.topic_id)
                .where(Topic.source_kind == "live")
            )
        )
        relevance_accepted = sum(_effective_relevance(row) for row in relevance_rows)
        relevance_rejected = len(relevance_rows) - relevance_accepted
        relevance_scores = [row.relevance_score for row in relevance_rows]
        failed_fetches = int(
            self._session.scalar(
                select(func.count(CommentFetchRun.id)).where(CommentFetchRun.status == "failed")
            )
            or 0
        )
        disabled_videos = int(
            self._session.scalar(
                select(func.count(func.distinct(CommentFetchRun.video_id))).where(
                    CommentFetchRun.comments_disabled.is_(True)
                )
            )
            or 0
        )
        return {
            "sampled_videos": sampled_videos,
            "comment_count": self._live_comment_count(),
            "classified_count": feature_count,
            "cluster_count": clusters,
            "internal_cluster_count": internal_clusters,
            "topics_with_demand": topics_with_demand,
            "relevance_evaluated_count": len(relevance_rows),
            "relevance_accepted_count": relevance_accepted,
            "relevance_rejected_count": relevance_rejected,
            "demand_evidence_rejection_rate": (
                round(relevance_rejected / len(relevance_rows) * 100, 1) if relevance_rows else 0
            ),
            "demand_relevance_median": (
                round(float(median(relevance_scores)), 4) if relevance_scores else None
            ),
            "relevance_model_version": (
                RELEVANCE_MODEL_VERSION if self._settings.feature_comment_topic_relevance else None
            ),
            "failed_fetches": failed_fetches,
            "comments_disabled_videos": disabled_videos,
            "latest_run_status": latest.status if latest is not None else None,
            "latest_run_at": (
                _aware(latest.completed_at or latest.started_at).isoformat()
                if latest is not None
                else None
            ),
            "processing_lag_seconds": (latest.processing_lag_seconds if latest is not None else 0),
        }

    def _result(
        self,
        run: DemandPipelineRun,
        *,
        reused: bool,
    ) -> DemandRunResult:
        return DemandRunResult(
            run_id=run.id,
            reused=reused,
            candidate_videos=run.candidate_video_count,
            fetched_videos=run.fetched_video_count,
            comments=run.comment_count,
            classified=run.classified_count,
            relevance_evaluated=run.relevance_evaluated_count,
            relevance_accepted=run.relevance_accepted_count,
            relevance_rejected=run.relevance_rejected_count,
            clusters=run.cluster_count,
            provider_failures=run.provider_failure_count,
        )
