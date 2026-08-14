from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    CommentTopicRelevance,
    DiscoveryQueryRecord,
    DiscoveryRun,
    QuerySuggestion,
    Topic,
    TopicVideoMembership,
    VideoTranscript,
    WorkspaceChannel,
    YoutubeVideo,
)
from packages.query_expansion import (
    MAX_NEW_SUGGESTIONS_PER_RUN,
    MAX_PENDING_SUGGESTIONS,
    QUERY_EXPANSION_VERSION,
    QueryCandidate,
    evaluate_query_candidate,
    normalize_query,
    query_precision,
    should_demote_query,
)

RELEASE_PATTERN = re.compile(r"\b(?:v?\d+(?:\.\d+)+|release|released|launch)\b", re.I)


@dataclass(frozen=True)
class QueryExpansionResult:
    candidates_evaluated: int
    suggestions_created: int
    duplicates_skipped: int
    low_value_queries_demoted: int
    pending_suggestions: int
    capped: bool


class QueryExpansionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def run(self) -> QueryExpansionResult:
        demoted = self.update_precision()
        pending = int(
            self._session.scalar(
                select(func.count(QuerySuggestion.id)).where(QuerySuggestion.status == "suggested")
            )
            or 0
        )
        available = max(
            0,
            min(
                MAX_NEW_SUGGESTIONS_PER_RUN,
                MAX_PENDING_SUGGESTIONS - pending,
            ),
        )
        candidates = self._candidates()
        existing_queries = {
            normalize_query(value)
            for value in self._session.scalars(select(DiscoveryQueryRecord.query))
        }
        existing_suggestions = set(self._session.scalars(select(QuerySuggestion.normalized_query)))
        created = 0
        duplicates = 0
        now = datetime.now(tz=UTC)
        for candidate in candidates:
            if created >= available:
                break
            quality = evaluate_query_candidate(candidate)
            if not quality.accepted:
                continue
            if (
                quality.normalized_query in existing_queries
                or quality.normalized_query in existing_suggestions
            ):
                duplicates += 1
                continue
            self._session.add(
                QuerySuggestion(
                    id=str(uuid4()),
                    workspace_id=candidate.workspace_id,
                    query=candidate.query[:300],
                    normalized_query=quality.normalized_query,
                    status="suggested",
                    source_type=candidate.source_type,
                    source_entity=candidate.source_entity[:240],
                    source_topic_id=candidate.source_topic_id,
                    source_evidence_ids_json=list(candidate.source_evidence_ids),
                    rationale=candidate.rationale,
                    anchor_terms_json=list(quality.anchor_terms),
                    quality_reason_codes_json=list(quality.reason_codes),
                    broadness_score=quality.broadness_score,
                    precision_score=0,
                    precision_sample_size=0,
                    discovery_query_id=None,
                    reviewed_by=None,
                    reviewed_at=None,
                    model_version=QUERY_EXPANSION_VERSION,
                    created_at=now,
                    updated_at=now,
                )
            )
            existing_suggestions.add(quality.normalized_query)
            created += 1
        self._session.commit()
        return QueryExpansionResult(
            candidates_evaluated=len(candidates),
            suggestions_created=created,
            duplicates_skipped=duplicates,
            low_value_queries_demoted=demoted,
            pending_suggestions=pending + created,
            capped=available == 0 or created >= available < len(candidates),
        )

    def _candidates(self) -> list[QueryCandidate]:
        topics = list(
            self._session.scalars(
                select(Topic)
                .where(
                    Topic.status == "active",
                    Topic.lifecycle_stage.in_(
                        ("Candidate", "Seed", "Emerging", "Accelerating", "Breakout")
                    ),
                )
                .order_by(desc(Topic.first_observed_at))
                .limit(40)
            )
        )
        candidates: list[QueryCandidate] = []
        for topic in topics:
            identity = topic.identity_json
            primary = str(
                identity.get("primary_entity")
                or (topic.entities_json[0] if topic.entities_json else "")
            ).strip()
            problem = str(
                identity.get("user_problem")
                or identity.get("workflow_context")
                or topic.canonical_label
            ).strip()
            if primary and problem:
                candidates.append(
                    QueryCandidate(
                        query=f"{primary} {problem}",
                        source_type="new_product_entity",
                        source_entity=primary,
                        source_topic_id=topic.id,
                        source_evidence_ids=(f"topic:{topic.id}",),
                        rationale=(
                            f"{primary} is anchored to the specific viewer problem "
                            f"“{problem}” in an active {topic.lifecycle_stage} topic."
                        ),
                        product_anchors=(primary,),
                        problem_anchors=(problem,),
                    )
                )
            if topic.aliases_json and problem:
                alias = topic.aliases_json[0]
                candidates.append(
                    QueryCandidate(
                        query=f"{alias} {problem}",
                        source_type="related_term",
                        source_entity=alias,
                        source_topic_id=topic.id,
                        source_evidence_ids=(f"topic:{topic.id}",),
                        rationale=(
                            f"Related phrase “{alias}” co-occurs with the stored "
                            f"problem anchor “{problem}”."
                        ),
                        product_anchors=(alias,),
                        problem_anchors=(problem,),
                    )
                )
            secondary = [
                str(value) for value in identity.get("secondary_entities", []) if str(value).strip()
            ]
            if secondary and problem:
                candidates.append(
                    QueryCandidate(
                        query=f"{secondary[0]} {problem}",
                        source_type="title_phrase_cooccurrence",
                        source_entity=secondary[0],
                        source_topic_id=topic.id,
                        source_evidence_ids=(f"topic:{topic.id}",),
                        rationale=(
                            f"Secondary entity “{secondary[0]}” repeatedly appears "
                            f"inside the same evidence-backed problem cluster."
                        ),
                        product_anchors=(secondary[0],),
                        problem_anchors=(problem,),
                    )
                )
            candidates.extend(self._transcript_candidates(topic, primary, problem))
            candidates.extend(self._comment_candidates(topic, primary, problem))
            candidates.extend(self._release_candidates(topic, primary, problem))
            candidates.extend(self._watchlist_candidates(topic, primary, problem))
        return candidates

    def _transcript_candidates(
        self,
        topic: Topic,
        primary: str,
        problem: str,
    ) -> list[QueryCandidate]:
        rows = list(
            self._session.scalars(
                select(VideoTranscript)
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == VideoTranscript.video_id,
                )
                .where(TopicVideoMembership.topic_id == topic.id)
                .order_by(desc(VideoTranscript.fetched_at))
                .limit(3)
            )
        )
        candidates: list[QueryCandidate] = []
        for transcript in rows:
            entity = next(
                (
                    value
                    for value in transcript.entities_json
                    if normalize_query(value) not in normalize_query(primary)
                ),
                None,
            )
            if not entity:
                continue
            candidates.append(
                QueryCandidate(
                    query=f"{entity} {problem}",
                    source_type="transcript_entity",
                    source_entity=entity,
                    source_topic_id=topic.id,
                    source_evidence_ids=(f"transcript:{transcript.id}",),
                    rationale=(
                        f"Transcript entity “{entity}” appears in evidence for "
                        f"the anchored problem “{problem}”."
                    ),
                    product_anchors=(entity,),
                    problem_anchors=(problem,),
                )
            )
        return candidates

    def _comment_candidates(
        self,
        topic: Topic,
        primary: str,
        problem: str,
    ) -> list[QueryCandidate]:
        rows = list(
            self._session.scalars(
                select(CommentTopicRelevance)
                .where(
                    CommentTopicRelevance.topic_id == topic.id,
                    CommentTopicRelevance.is_relevant.is_(True),
                    CommentTopicRelevance.actionability == "high",
                )
                .order_by(desc(CommentTopicRelevance.relevance_score))
                .limit(2)
            )
        )
        candidates: list[QueryCandidate] = []
        for row in rows:
            entity = next(
                (
                    value
                    for value in row.supported_entities_json
                    if normalize_query(value) not in normalize_query(primary)
                ),
                None,
            )
            if entity:
                candidates.append(
                    QueryCandidate(
                        query=f"{entity} {problem}",
                        source_type="comment_demand",
                        source_entity=entity,
                        source_topic_id=topic.id,
                        source_evidence_ids=(f"comment-relevance:{row.id}",),
                        rationale=(
                            f"Actionable comments connect “{entity}” with "
                            f"the stored viewer problem “{problem}”."
                        ),
                        product_anchors=(entity,),
                        problem_anchors=(problem,),
                    )
                )
        return candidates

    def _release_candidates(
        self,
        topic: Topic,
        primary: str,
        problem: str,
    ) -> list[QueryCandidate]:
        videos = list(
            self._session.scalars(
                select(YoutubeVideo)
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == YoutubeVideo.id,
                )
                .where(TopicVideoMembership.topic_id == topic.id)
                .order_by(desc(YoutubeVideo.published_at))
                .limit(8)
            )
        )
        candidates: list[QueryCandidate] = []
        for video in videos:
            release = RELEASE_PATTERN.search(video.title)
            if release and primary:
                release_name = f"{primary} {release.group(0)}"
                candidates.append(
                    QueryCandidate(
                        query=f"{release_name} {problem}",
                        source_type="product_release_name",
                        source_entity=release_name,
                        source_topic_id=topic.id,
                        source_evidence_ids=(f"video:{video.id}",),
                        rationale=(
                            f"A named release marker appears in recent evidence "
                            f"and is constrained by “{problem}”."
                        ),
                        product_anchors=(release_name,),
                        problem_anchors=(problem,),
                    )
                )
                break
        return candidates

    def _watchlist_candidates(
        self,
        topic: Topic,
        primary: str,
        problem: str,
    ) -> list[QueryCandidate]:
        if not primary or not problem:
            return []
        watched_video = self._session.scalar(
            select(YoutubeVideo)
            .join(
                WorkspaceChannel,
                WorkspaceChannel.channel_id == YoutubeVideo.channel_id,
            )
            .where(
                WorkspaceChannel.relationship.in_(("reference", "competitor")),
                WorkspaceChannel.active.is_(True),
                YoutubeVideo.title.ilike(f"%{primary.split()[0]}%"),
            )
            .order_by(desc(YoutubeVideo.published_at))
            .limit(1)
        )
        if watched_video is None:
            return []
        workspace_id = self._session.scalar(
            select(WorkspaceChannel.workspace_id)
            .where(WorkspaceChannel.channel_id == watched_video.channel_id)
            .limit(1)
        )
        return [
            QueryCandidate(
                query=f"{primary} {problem} workflow",
                source_type="user_watchlist",
                source_entity=primary,
                source_topic_id=topic.id,
                source_evidence_ids=(f"video:{watched_video.id}",),
                rationale=(
                    "A monitored reference channel published into this anchored "
                    "product/problem cluster."
                ),
                product_anchors=(primary,),
                problem_anchors=(problem, "workflow"),
                workspace_id=workspace_id,
            )
        ]

    def update_precision(self) -> int:
        demoted = 0
        now = datetime.now(tz=UTC)
        for query in self._session.scalars(select(DiscoveryQueryRecord)):
            result_count, retained_count = self._session.execute(
                select(
                    func.coalesce(func.sum(DiscoveryRun.result_count), 0),
                    func.coalesce(func.sum(DiscoveryRun.retained_video_count), 0),
                ).where(
                    DiscoveryRun.query_id == query.id,
                    DiscoveryRun.status.in_(("success", "completed")),
                )
            ).one()
            sample_size = int(result_count)
            precision = query_precision(
                retained_results=int(retained_count),
                total_results=sample_size,
            )
            query.precision_score = precision
            query.precision_sample_size = sample_size
            query.last_precision_at = now
            if should_demote_query(precision=precision, sample_size=sample_size):
                query.quality_status = "low_value"
                query.active = False
                suggestion = self._session.scalar(
                    select(QuerySuggestion).where(QuerySuggestion.discovery_query_id == query.id)
                )
                if suggestion is not None:
                    suggestion.status = "low_value"
                    suggestion.precision_score = precision
                    suggestion.precision_sample_size = sample_size
                    suggestion.updated_at = now
                demoted += 1
            elif sample_size:
                query.quality_status = "healthy"
        self._session.flush()
        return demoted

    def transition(
        self,
        suggestion: QuerySuggestion,
        action: str,
        *,
        reviewer_id: str | None,
    ) -> QuerySuggestion:
        now = datetime.now(tz=UTC)
        query = (
            self._session.get(DiscoveryQueryRecord, suggestion.discovery_query_id)
            if suggestion.discovery_query_id
            else None
        )
        if action == "approve":
            if suggestion.status not in {"suggested", "paused"}:
                raise ValueError("Only suggested or paused queries can be approved")
            if query is None:
                query = DiscoveryQueryRecord(
                    id=str(uuid4()),
                    query=suggestion.query,
                    category="AI / tech",
                    priority=2,
                    country="US",
                    language="en",
                    active=False,
                    source="query_expansion",
                    minimum_interval_seconds=14_400,
                    expires_at=None,
                    last_run_at=None,
                    next_run_at=now,
                    historical_yield=0,
                    cost_per_retained_video=0,
                    precision_score=0,
                    precision_sample_size=0,
                    quality_status="unmeasured",
                    last_precision_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(query)
                self._session.flush()
                suggestion.discovery_query_id = query.id
            suggestion.status = "approved"
        elif action == "activate":
            if suggestion.status != "approved" or query is None:
                raise ValueError("Approve the query before activation")
            query.active = True
            query.next_run_at = now
            query.updated_at = now
            suggestion.status = "active"
        elif action == "pause":
            if query is not None:
                query.active = False
                query.updated_at = now
            suggestion.status = "paused"
        elif action == "retire":
            if query is not None:
                query.active = False
                query.expires_at = now
                query.updated_at = now
            suggestion.status = "retired"
        else:
            raise ValueError("Unsupported query suggestion action")
        suggestion.reviewed_by = reviewer_id
        suggestion.reviewed_at = now
        suggestion.updated_at = now
        self._session.commit()
        return suggestion
