from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models import (
    ContentBrief,
    OutcomeSuggestion,
    PublishedOutcome,
    Signal,
    VideoSnapshot,
    WorkspaceChannel,
    YoutubeOwnedAnalytics,
    YoutubeVideo,
)
from packages.outcome_tracking import (
    ASSOCIATION_MODEL_VERSION,
    METRICS_MODEL_VERSION,
    BaselineCandidate,
    BriefCandidate,
    SnapshotPoint,
    build_associated_metrics,
    build_comparable_baseline,
    match_upload_to_brief,
)


@dataclass(frozen=True)
class OutcomeAutomationResult:
    suggestions_created: int
    outcomes_updated: int
    workspaces_scanned: int


def _snapshot_points(session: Session, video_id: str) -> tuple[SnapshotPoint, ...]:
    rows = list(
        session.scalars(
            select(VideoSnapshot)
            .where(VideoSnapshot.video_id == video_id)
            .order_by(VideoSnapshot.video_age_seconds)
        )
    )
    points = [
        SnapshotPoint(
            age_hours=row.video_age_seconds / 3600,
            views=row.view_count,
        )
        for row in rows
    ]
    analytics = session.scalar(
        select(YoutubeOwnedAnalytics)
        .where(YoutubeOwnedAnalytics.video_id == video_id)
        .order_by(desc(YoutubeOwnedAnalytics.observed_at))
        .limit(1)
    )
    video = session.get(YoutubeVideo, video_id)
    if analytics is not None and video is not None:
        points.append(
            SnapshotPoint(
                age_hours=max(
                    0,
                    (_aware(analytics.observed_at) - _aware(video.published_at)).total_seconds()
                    / 3600,
                ),
                views=analytics.views,
                watch_time_minutes=analytics.watch_time_minutes,
                average_view_duration_seconds=(analytics.average_view_duration_seconds),
                average_percentage_viewed=analytics.average_percentage_viewed,
                subscribers_gained=analytics.subscribers_gained,
                revenue=analytics.revenue,
            )
        )
    return tuple(sorted(points, key=lambda point: point.age_hours))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _baseline_candidate(session: Session, video: YoutubeVideo) -> BaselineCandidate:
    return BaselineCandidate(
        video_id=video.id,
        title=video.title,
        description=video.description,
        published_at=video.published_at,
        duration_seconds=video.duration_seconds,
        is_short=video.is_short,
        is_live=video.is_live,
        snapshots=_snapshot_points(session, video.id),
    )


def _brief_text(brief: ContentBrief) -> str:
    return " ".join(
        (
            brief.title,
            json.dumps(brief.brief_json, ensure_ascii=False, sort_keys=True),
        )
    )


class OutcomeAutomationService:
    """Detect, confirm, and refresh non-causal signal-to-publication associations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def run(self, workspace_id: str | None = None) -> OutcomeAutomationResult:
        workspace_rows = list(
            self._session.execute(
                select(WorkspaceChannel.workspace_id, WorkspaceChannel.channel_id).where(
                    WorkspaceChannel.relationship == "owned",
                    WorkspaceChannel.active.is_(True),
                    *((WorkspaceChannel.workspace_id == workspace_id,) if workspace_id else ()),
                )
            )
        )
        suggestions_created = 0
        outcomes_updated = 0
        for current_workspace_id, channel_id in workspace_rows:
            suggestions_created += self._detect_for_channel(
                current_workspace_id,
                channel_id,
            )
            outcomes_updated += self._update_for_channel(
                current_workspace_id,
                channel_id,
            )
        self._session.commit()
        return OutcomeAutomationResult(
            suggestions_created=suggestions_created,
            outcomes_updated=outcomes_updated,
            workspaces_scanned=len({row[0] for row in workspace_rows}),
        )

    def _detect_for_channel(self, workspace_id: str, channel_id: str) -> int:
        briefs = list(
            self._session.scalars(
                select(ContentBrief)
                .where(
                    ContentBrief.workspace_id == workspace_id,
                    ContentBrief.channel_id == channel_id,
                    ContentBrief.status.in_(("draft", "approved", "published")),
                )
                .order_by(desc(ContentBrief.created_at))
                .limit(100)
            )
        )
        if not briefs:
            return 0
        uploads = list(
            self._session.scalars(
                select(YoutubeVideo)
                .where(YoutubeVideo.channel_id == channel_id)
                .order_by(desc(YoutubeVideo.published_at))
                .limit(80)
            )
        )
        created = 0
        for video in uploads:
            existing_outcome = self._session.scalar(
                select(PublishedOutcome.id).where(
                    PublishedOutcome.workspace_id == workspace_id,
                    PublishedOutcome.youtube_video_id == video.youtube_video_id,
                    PublishedOutcome.link_status == "active",
                )
            )
            existing_suggestion = self._session.scalar(
                select(OutcomeSuggestion.id).where(
                    OutcomeSuggestion.workspace_id == workspace_id,
                    OutcomeSuggestion.video_id == video.id,
                )
            )
            if existing_outcome or existing_suggestion:
                continue
            eligible_briefs = [brief for brief in briefs if brief.created_at <= video.published_at]
            match = match_upload_to_brief(
                upload_title=video.title,
                upload_description=video.description,
                published_at=video.published_at,
                candidates=[
                    BriefCandidate(
                        brief_id=brief.id,
                        signal_id=brief.signal_id,
                        title=brief.title,
                        evidence_text=_brief_text(brief),
                        created_at=brief.created_at,
                    )
                    for brief in eligible_briefs
                ],
            )
            if match is None:
                continue
            history = [
                _baseline_candidate(self._session, item)
                for item in uploads
                if item.published_at < video.published_at
            ]
            baseline = build_comparable_baseline(
                target=_baseline_candidate(self._session, video),
                history=history,
            )
            now = datetime.now(tz=UTC)
            self._session.add(
                OutcomeSuggestion(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    video_id=video.id,
                    signal_id=match.signal_id,
                    suggested_brief_id=match.brief_id,
                    selected_brief_id=None,
                    outcome_id=None,
                    status="suggested",
                    match_confidence=match.confidence,
                    reason_codes_json=list(match.reason_codes),
                    match_features_json=match.features,
                    baseline_json=baseline,
                    metrics_json={},
                    model_version=ASSOCIATION_MODEL_VERSION,
                    detected_at=now,
                    decided_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._session.flush()
            created += 1
        return created

    def _update_for_channel(self, workspace_id: str, channel_id: str) -> int:
        videos = {
            video.youtube_video_id: video
            for video in self._session.scalars(
                select(YoutubeVideo).where(YoutubeVideo.channel_id == channel_id)
            )
        }
        history = list(videos.values())
        outcomes = list(
            self._session.scalars(
                select(PublishedOutcome).where(
                    PublishedOutcome.workspace_id == workspace_id,
                    PublishedOutcome.link_status == "active",
                )
            )
        )
        updated = 0
        for outcome in outcomes:
            video = videos.get(outcome.youtube_video_id)
            if video is None or outcome.content_brief_id is None:
                continue
            brief = self._session.get(ContentBrief, outcome.content_brief_id)
            signal = self._session.get(Signal, outcome.signal_id)
            if brief is None or signal is None:
                continue
            baseline = build_comparable_baseline(
                target=_baseline_candidate(self._session, video),
                history=[
                    _baseline_candidate(self._session, item)
                    for item in history
                    if item.published_at < video.published_at
                ],
            )
            metrics = build_associated_metrics(
                target_snapshots=_snapshot_points(self._session, video.id),
                baseline=baseline,
                signal_detected_at=signal.generated_at,
                brief_created_at=brief.created_at,
                published_at=video.published_at,
            )
            previous = dict(outcome.performance_json)
            outcome.performance_json = metrics
            outcome.baseline_definition = (
                "Median performance of comparable owned uploads: same content "
                "type, similar duration, topic-family proximity, sponsorship class, "
                "and the previous six months."
            )
            outcome.metrics_version = METRICS_MODEL_VERSION
            outcome.updated_at = datetime.now(tz=UTC)
            first_ratio = next(
                (
                    (key.removeprefix("channel_relative_uplift_"), float(value))
                    for key, value in metrics.items()
                    if key.startswith("channel_relative_uplift_")
                    and isinstance(value, (float, int))
                ),
                None,
            )
            stable_ratio = None
            if first_ratio is not None:
                horizon_key, ratio = first_ratio
                sample_size = baseline.get(f"sample_size_{horizon_key}", 0)
                minimum_sample = baseline.get("minimum_stable_sample_size", 5)
                if (
                    isinstance(sample_size, int)
                    and isinstance(minimum_sample, int)
                    and sample_size >= minimum_sample
                ):
                    stable_ratio = ratio
            outcome.success_status = (
                "pending"
                if stable_ratio is None
                else "successful"
                if stable_ratio >= 1.2
                else "mixed"
                if stable_ratio >= 0.85
                else "unsuccessful"
            )
            suggestion = self._session.scalar(
                select(OutcomeSuggestion).where(OutcomeSuggestion.outcome_id == outcome.id)
            )
            if suggestion is not None:
                suggestion.baseline_json = baseline
                suggestion.metrics_json = metrics
                suggestion.updated_at = outcome.updated_at
            if previous != metrics:
                updated += 1
        return updated
