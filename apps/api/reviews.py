from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.lifecycle import record_review_signal_visibility
from apps.api.models import (
    Signal,
    SignalReview,
    SignalReviewEvent,
    Topic,
    TopicVideoMembership,
    User,
    WorkspaceMember,
    WorkspaceSignalScore,
)
from apps.api.schemas import (
    ReviewAction,
    ReviewReason,
    ReviewStatus,
    SignalDetail,
    SignalReviewActionCreate,
    SignalReviewEventResponse,
    SignalReviewMetrics,
    SignalReviewQueueResponse,
    SignalReviewSummary,
)

REVIEW_VERSION = "signal-review-v1"
REVIEW_STATUSES: tuple[ReviewStatus, ...] = (
    "internal_candidate",
    "needs_review",
    "approved",
    "rejected",
    "needs_changes",
    "published",
    "expired",
)
VISIBLE_REVIEW_STATUSES = ("approved", "published")
REASON_CODES: tuple[ReviewReason, ...] = (
    "false_topic_merge",
    "too_broad",
    "too_narrow",
    "late_signal",
    "single_channel_dependency",
    "single_video_dependency",
    "weak_outlier",
    "weak_demand",
    "irrelevant_comments",
    "low_channel_fit",
    "saturated",
    "insufficient_evidence",
    "duplicate_signal",
    "other",
)

ACTION_DEFAULT_REASONS: dict[ReviewAction, ReviewReason] = {
    "request_split": "too_broad",
    "request_merge": "false_topic_merge",
    "mark_late": "late_signal",
    "mark_weak_evidence": "weak_outlier",
    "mark_irrelevant_demand": "irrelevant_comments",
}
ACTION_TARGET_STATUS: dict[ReviewAction, ReviewStatus] = {
    "approve": "approved",
    "reject": "rejected",
    "request_split": "needs_changes",
    "request_merge": "needs_changes",
    "mark_late": "needs_changes",
    "mark_weak_evidence": "needs_changes",
    "mark_irrelevant_demand": "needs_changes",
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"earlysignal:{kind}:{key}"))


def _workspace_reviewer(session: Session, workspace_id: str) -> tuple[str, str]:
    row = session.execute(
        select(User.id, User.name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.role, User.created_at)
        .limit(1)
    ).one_or_none()
    if row is None:
        raise HTTPException(422, "Workspace has no reviewer")
    return row.id, row.name


def workspace_reviewer(session: Session, workspace_id: str) -> tuple[str, str]:
    return _workspace_reviewer(session, workspace_id)


def get_signal_review(
    session: Session,
    workspace_id: str,
    signal_id: str,
) -> SignalReview | None:
    return session.scalar(
        select(SignalReview).where(
            SignalReview.workspace_id == workspace_id,
            SignalReview.signal_id == signal_id,
        )
    )


def ensure_signal_review(
    session: Session,
    workspace_id: str,
    signal: Signal,
) -> SignalReview:
    existing = get_signal_review(session, workspace_id, signal.id)
    if existing is not None:
        return existing

    auto_approved = signal.source_kind == "demo"
    reviewer_id = None
    reviewer_name = None
    if auto_approved:
        reviewer_id, reviewer_name = _workspace_reviewer(session, workspace_id)
    now = datetime.now(tz=UTC)
    status = "approved" if auto_approved else "needs_review"
    review = SignalReview(
        id=_stable_id("signal-review", f"{workspace_id}:{signal.id}"),
        workspace_id=workspace_id,
        signal_id=signal.id,
        status=status,
        reviewer_id=reviewer_id,
        primary_reason="other" if auto_approved else None,
        reason_codes_json=["other"] if auto_approved else [],
        notes="Deterministic synthetic signal auto-approved for demo mode."
        if auto_approved
        else None,
        thesis_override=None,
        opportunity_override_json={},
        evidence_selection_json=[],
        submitted_at=_aware(signal.generated_at),
        first_reviewed_at=now if auto_approved else None,
        decided_at=now if auto_approved else None,
        review_version=REVIEW_VERSION,
        created_at=now,
        updated_at=now,
    )
    session.add(review)
    session.flush()
    event_type = "auto_approved_demo" if auto_approved else "queued_for_review"
    session.add(
        SignalReviewEvent(
            id=_stable_id("signal-review-event", f"{review.id}:{event_type}"),
            review_id=review.id,
            workspace_id=workspace_id,
            signal_id=signal.id,
            event_type=event_type,
            from_status=None,
            to_status=status,
            reviewer_id=reviewer_id,
            reason_codes_json=["other"] if auto_approved else [],
            note=review.notes,
            changes_json={},
            provenance_json={
                "review_version": REVIEW_VERSION,
                "source_kind": signal.source_kind,
                "reviewer_name": reviewer_name,
            },
            idempotency_key=f"review-bootstrap:{workspace_id}:{signal.id}:{status}",
            created_at=now,
        )
    )
    session.flush()
    return review


def ensure_workspace_reviews(
    session: Session,
    workspace_id: str,
    *,
    source_kind: str | None = None,
) -> int:
    query = (
        select(Signal)
        .join(WorkspaceSignalScore, WorkspaceSignalScore.signal_id == Signal.id)
        .where(
            WorkspaceSignalScore.workspace_id == workspace_id,
            Signal.status == "active",
        )
    )
    if source_kind is not None:
        query = query.where(Signal.source_kind == source_kind)
    created = 0
    for signal in session.scalars(query):
        if get_signal_review(session, workspace_id, signal.id) is None:
            ensure_signal_review(session, workspace_id, signal)
            created += 1
    return created


def signal_is_visible(
    session: Session,
    workspace_id: str,
    signal_id: str,
) -> bool:
    status = session.scalar(
        select(SignalReview.status).where(
            SignalReview.workspace_id == workspace_id,
            SignalReview.signal_id == signal_id,
        )
    )
    return status in VISIBLE_REVIEW_STATUSES


def _reviewer_name(session: Session, reviewer_id: str | None) -> str | None:
    if reviewer_id is None:
        return None
    return session.scalar(select(User.name).where(User.id == reviewer_id))


def review_event_response(
    session: Session,
    event: SignalReviewEvent,
) -> SignalReviewEventResponse:
    return SignalReviewEventResponse(
        id=event.id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        reviewer_id=event.reviewer_id,
        reviewer_name=_reviewer_name(session, event.reviewer_id),
        reason_codes=event.reason_codes_json,
        note=event.note,
        changes=event.changes_json,
        provenance=event.provenance_json,
        idempotency_key=event.idempotency_key,
        created_at=_aware(event.created_at),
    )


def review_summary(
    session: Session,
    review: SignalReview,
) -> SignalReviewSummary:
    row = session.execute(
        select(Signal, Topic, WorkspaceSignalScore)
        .join(Topic, Topic.id == Signal.topic_id)
        .join(
            WorkspaceSignalScore,
            WorkspaceSignalScore.signal_id == Signal.id,
        )
        .where(
            Signal.id == review.signal_id,
            WorkspaceSignalScore.workspace_id == review.workspace_id,
        )
    ).one()
    signal, topic, workspace_score = row
    return SignalReviewSummary(
        id=review.id,
        workspace_id=review.workspace_id,
        signal_id=review.signal_id,
        topic_label=topic.canonical_label,
        lifecycle_stage=signal.lifecycle_stage,
        signal_score=signal.score,
        channel_fit=workspace_score.channel_fit_score,
        status=review.status,
        reviewer_id=review.reviewer_id,
        reviewer_name=_reviewer_name(session, review.reviewer_id),
        primary_reason=review.primary_reason,
        reason_codes=review.reason_codes_json,
        submitted_at=_aware(review.submitted_at),
        first_reviewed_at=(_aware(review.first_reviewed_at) if review.first_reviewed_at else None),
        decided_at=_aware(review.decided_at) if review.decided_at else None,
        updated_at=_aware(review.updated_at),
        source_kind=signal.source_kind,
    )


def _metrics(
    summaries: list[SignalReviewSummary],
    events: list[SignalReviewEvent],
) -> SignalReviewMetrics:
    status_counts = Counter(item.status for item in summaries)
    decided = status_counts["approved"] + status_counts["published"] + status_counts["rejected"]
    approved = status_counts["approved"] + status_counts["published"]
    rejection_reasons: Counter[str] = Counter()
    for event in events:
        if event.to_status == "rejected":
            rejection_reasons.update(event.reason_codes_json)
    review_times = [
        (item.decided_at - item.submitted_at).total_seconds() / 3600
        for item in summaries
        if item.decided_at is not None
    ]
    stage_distribution: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for item in summaries:
        if item.status in {"approved", "published", "rejected"}:
            bucket = "approved" if item.status in {"approved", "published"} else "rejected"
            stage_distribution[bucket][item.lifecycle_stage] += 1
    return SignalReviewMetrics(
        total=len(summaries),
        status_counts={status: status_counts[status] for status in REVIEW_STATUSES},
        approval_rate=round(approved / decided * 100, 1) if decided else 0,
        rejection_reasons=dict(sorted(rejection_reasons.items())),
        average_review_time_hours=(
            round(sum(review_times) / len(review_times), 2) if review_times else None
        ),
        stage_distribution={
            bucket: dict(sorted(counts.items())) for bucket, counts in stage_distribution.items()
        },
    )


def list_signal_reviews(
    session: Session,
    workspace_id: str,
    *,
    status: str | None = None,
    source_kind: str | None = None,
) -> SignalReviewQueueResponse:
    ensure_workspace_reviews(session, workspace_id, source_kind=source_kind)
    session.flush()
    all_reviews = list(
        session.scalars(
            select(SignalReview)
            .join(Signal, Signal.id == SignalReview.signal_id)
            .where(
                SignalReview.workspace_id == workspace_id,
                *([Signal.source_kind == source_kind] if source_kind else []),
            )
            .order_by(
                SignalReview.status != "needs_review",
                SignalReview.submitted_at,
            )
        )
    )
    summaries = [review_summary(session, review) for review in all_reviews]
    events = list(
        session.scalars(
            select(SignalReviewEvent).where(SignalReviewEvent.workspace_id == workspace_id)
        )
    )
    visible = [item for item in summaries if status is None or item.status == status]
    session.commit()
    return SignalReviewQueueResponse(
        items=visible,
        total=len(visible),
        metrics=_metrics(summaries, events),
        filters={
            "statuses": list(REVIEW_STATUSES),
            "reasons": list(REASON_CODES),
            "sources": sorted({item.source_kind for item in summaries}),
        },
    )


def review_audit_history(
    session: Session,
    review_id: str,
) -> list[SignalReviewEventResponse]:
    return [
        review_event_response(session, event)
        for event in session.scalars(
            select(SignalReviewEvent)
            .where(SignalReviewEvent.review_id == review_id)
            .order_by(desc(SignalReviewEvent.created_at))
        )
    ]


def _validate_evidence_selection(
    session: Session,
    signal: Signal,
    video_ids: list[str],
) -> None:
    allowed = set(
        session.scalars(
            select(TopicVideoMembership.video_id).where(
                TopicVideoMembership.topic_id == signal.topic_id,
                TopicVideoMembership.video_id.in_(video_ids),
            )
        )
    )
    invalid = sorted(set(video_ids) - allowed)
    if invalid:
        raise HTTPException(422, f"Evidence videos are outside the signal topic: {invalid}")


def apply_review_action(
    session: Session,
    workspace_id: str,
    signal_id: str,
    payload: SignalReviewActionCreate,
) -> SignalReviewEventResponse:
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "Signal not found")
    review = get_signal_review(session, workspace_id, signal_id)
    if review is None:
        if session.get(WorkspaceSignalScore, (workspace_id, signal_id)) is None:
            raise HTTPException(404, "Signal is not scored for this workspace")
        review = ensure_signal_review(session, workspace_id, signal)

    idempotency_key = payload.idempotency_key or (
        f"review-action:{review.id}:{payload.action}:{uuid4()}"
    )
    existing = session.scalar(
        select(SignalReviewEvent).where(SignalReviewEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return review_event_response(session, existing)

    if review.status == "expired":
        raise HTTPException(409, "Expired reviews cannot be changed")
    if payload.action == "reject" and not payload.reason_codes:
        raise HTTPException(422, "Reject requires at least one reason code")
    if payload.action == "request_merge" and not payload.merge_target_signal_id:
        raise HTTPException(422, "Request merge requires a target signal")
    if payload.action == "edit_thesis" and payload.thesis is None:
        raise HTTPException(422, "Edit thesis requires thesis text")
    if payload.action == "edit_opportunity" and payload.opportunity is None:
        raise HTTPException(422, "Edit opportunity requires an opportunity payload")
    if payload.action == "edit_evidence_selection" and payload.evidence_video_ids is None:
        raise HTTPException(422, "Edit evidence selection requires video IDs")

    reasons = list(payload.reason_codes)
    default_reason = ACTION_DEFAULT_REASONS.get(payload.action)
    if default_reason and default_reason not in reasons:
        reasons.insert(0, default_reason)
    if payload.action == "approve" and not reasons:
        reasons = ["other"]

    changes: dict[str, Any] = {}
    if payload.thesis is not None:
        review.thesis_override = payload.thesis
        changes["thesis"] = payload.thesis
    if payload.opportunity is not None:
        review.opportunity_override_json = payload.opportunity
        changes["opportunity"] = payload.opportunity
    if payload.evidence_video_ids is not None:
        _validate_evidence_selection(session, signal, payload.evidence_video_ids)
        review.evidence_selection_json = payload.evidence_video_ids
        changes["evidence_video_ids"] = payload.evidence_video_ids
    if payload.merge_target_signal_id is not None:
        if session.get(Signal, payload.merge_target_signal_id) is None:
            raise HTTPException(422, "Merge target signal does not exist")
        changes["merge_target_signal_id"] = payload.merge_target_signal_id

    previous_status = review.status
    target_status = ACTION_TARGET_STATUS.get(payload.action)
    if target_status is None:
        current_status = cast(ReviewStatus, review.status)
        target_status = (
            "needs_changes" if current_status in VISIBLE_REVIEW_STATUSES else current_status
        )
    reviewer_id, reviewer_name = _workspace_reviewer(session, workspace_id)
    now = datetime.now(tz=UTC)
    review.status = target_status
    review.reviewer_id = reviewer_id
    review.primary_reason = reasons[0] if reasons else None
    review.reason_codes_json = [str(reason) for reason in reasons]
    review.notes = payload.note
    review.first_reviewed_at = review.first_reviewed_at or now
    review.decided_at = now if target_status in {"approved", "rejected", "published"} else None
    review.updated_at = now
    event = SignalReviewEvent(
        id=str(uuid4()),
        review_id=review.id,
        workspace_id=workspace_id,
        signal_id=signal_id,
        event_type=payload.action,
        from_status=previous_status,
        to_status=target_status,
        reviewer_id=reviewer_id,
        reason_codes_json=reasons,
        note=payload.note,
        changes_json=changes,
        provenance_json={
            "review_version": REVIEW_VERSION,
            "signal_evidence_version": signal.evidence_version,
            "reviewer_name": reviewer_name,
        },
        idempotency_key=idempotency_key,
        created_at=now,
    )
    session.add(event)
    session.flush()
    if target_status == "approved":
        record_review_signal_visibility(
            session,
            topic_id=signal.topic_id,
            approved_at=now,
            review_event_id=event.id,
        )
    session.commit()
    session.refresh(event)
    return review_event_response(session, event)


def signal_review_overrides(
    session: Session,
    workspace_id: str,
    signal_id: str,
) -> SignalReview | None:
    return get_signal_review(session, workspace_id, signal_id)


def record_review_published(
    session: Session,
    workspace_id: str,
    signal_id: str,
    *,
    outcome_id: str,
    occurred_at: datetime,
) -> None:
    review = get_signal_review(session, workspace_id, signal_id)
    if review is None or review.status == "published":
        return
    previous_status = review.status
    review.status = "published"
    review.decided_at = occurred_at
    review.updated_at = occurred_at
    session.add(
        SignalReviewEvent(
            id=_stable_id("signal-review-event", f"published:{outcome_id}"),
            review_id=review.id,
            workspace_id=workspace_id,
            signal_id=signal_id,
            event_type="published",
            from_status=previous_status,
            to_status="published",
            reviewer_id=review.reviewer_id,
            reason_codes_json=review.reason_codes_json,
            note="Published outcome linked to approved signal.",
            changes_json={"outcome_id": outcome_id},
            provenance_json={
                "review_version": REVIEW_VERSION,
                "source": "published_outcome",
            },
            idempotency_key=f"review-published:{outcome_id}",
            created_at=occurred_at,
        )
    )
    session.flush()


def false_positive_risks(detail: SignalDetail) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    evidence = detail.evidence_videos
    channel_counts = Counter(item.channel for item in evidence)
    if len(channel_counts) < 3:
        risks.append(
            {
                "reason_code": "single_channel_dependency",
                "severity": "high",
                "explanation": "Stored evidence spans fewer than three independent channels.",
                "evidence_refs": [item.id for item in evidence],
            }
        )
    if len(evidence) < 3:
        risks.append(
            {
                "reason_code": "single_video_dependency",
                "severity": "high",
                "explanation": "Stored evidence contains fewer than three videos.",
                "evidence_refs": [item.id for item in evidence],
            }
        )
    if evidence and median(item.outlier_ratio for item in evidence) < 1.1:
        risks.append(
            {
                "reason_code": "weak_outlier",
                "severity": "medium",
                "explanation": "Median stored channel-relative outlier is below 1.1×.",
                "evidence_refs": [item.id for item in evidence],
            }
        )
    if not detail.demand_clusters:
        risks.append(
            {
                "reason_code": "weak_demand",
                "severity": "medium",
                "explanation": "No stored demand cluster meets the evidence floor.",
                "evidence_refs": [],
            }
        )
    if detail.evidence_quality.transcript_coverage_percent < 30:
        risks.append(
            {
                "reason_code": "insufficient_evidence",
                "severity": "medium",
                "explanation": "Transcript coverage is below 30% of stored evidence.",
                "evidence_refs": [item.video_id for item in detail.transcript_evidence],
            }
        )
    if float(detail.saturation.get("score", 0)) >= 70:
        risks.append(
            {
                "reason_code": "saturated",
                "severity": "high",
                "explanation": "Stored saturation score is at or above 70.",
                "evidence_refs": [],
            }
        )
    if detail.earlyness is not None and detail.earlyness.claim_kind == "late":
        risks.append(
            {
                "reason_code": "late_signal",
                "severity": "high",
                "explanation": detail.earlyness.supporting_text,
                "evidence_refs": [event.id for event in detail.earlyness.transitions],
            }
        )
    return risks


def decision_card_preview(detail: SignalDetail) -> dict[str, Any]:
    opportunity = detail.content_angles[0] if detail.content_angles else None
    return {
        "topic_label": detail.topic["label"],
        "lifecycle_stage": detail.topic["stage"],
        "earlyness": detail.earlyness,
        "thesis": detail.thesis,
        "signal_score": detail.score,
        "channel_fit": detail.channel_fit,
        "publishing_window": detail.opportunity_window,
        "independent_channels": len({item.channel for item in detail.evidence_videos}),
        "evidence_videos": len(detail.evidence_videos),
        "strongest_demand": (detail.demand_clusters[0] if detail.demand_clusters else None),
        "primary_opportunity": opportunity,
        "saturation": detail.saturation,
    }
