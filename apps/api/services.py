from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.demo import DEMO_REFERENCE_AT
from apps.api.lifecycle import (
    earlyness_summary_for_signal,
    get_signal_earlyness,
)
from apps.api.models import (
    ChannelProfile,
    DemandCluster,
    DemandClusterComment,
    FieldProvenance,
    ProviderFetch,
    Signal,
    SignalAction,
    SignalReview,
    Topic,
    TopicContentGap,
    TopicContentPattern,
    TopicLifecycleSummary,
    TopicSnapshot,
    TopicSnapshotBucket,
    TopicVideoMembership,
    TranscriptSegment,
    VideoFeature,
    VideoSnapshot,
    VideoTranscript,
    WorkspaceDiscoveryQuery,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from apps.api.schemas import (
    DemandEvidence,
    DemandSummary,
    DiffusionPoint,
    EvidenceQuality,
    EvidenceVideo,
    MomentumSummary,
    OpportunityWindow,
    SignalDecisionCard,
    SignalDetail,
    SignalEvidenceLink,
    SignalListItem,
    TimelinePoint,
    TranscriptEvidence,
    TranscriptSegmentEvidence,
    UserFacingBucket,
)
from packages.decision_experience import (
    assess_decision,
    score_to_user_bucket_v1,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _demo_reference_time(signal: Signal) -> datetime | None:
    if signal.source_kind != "demo":
        return None
    return DEMO_REFERENCE_AT


def _signal_decision_time(signal: Signal) -> datetime:
    return _demo_reference_time(signal) or _now()


def _signal_response_time(signal: Signal, value: datetime) -> datetime:
    observed = _aware(value)
    reference = _demo_reference_time(signal)
    if reference is None:
        return observed
    return observed + (_now().replace(microsecond=0) - reference)


def _day_label(value: datetime) -> str:
    return _aware(value).strftime("%B %d").replace(" 0", " ")


def _days_label(start: datetime, end: datetime) -> str:
    now = _now()
    start_days = max(0, round((_aware(start) - now).total_seconds() / 86_400))
    end_days = max(start_days, round((_aware(end) - now).total_seconds() / 86_400))
    if start_days == 0:
        return f"Now–{end_days} days"
    return f"{start_days}–{end_days} days"


def _age_label(value: datetime) -> str:
    delta = _now() - _aware(value)
    hours = max(1, round(delta.total_seconds() / 3600))
    if hours < 48:
        return f"{hours}h"
    return f"{round(hours / 24)}d"


def _current_action(session: Session, workspace_id: str, signal_id: str) -> str | None:
    return session.scalar(
        select(SignalAction.action)
        .where(
            SignalAction.workspace_id == workspace_id,
            SignalAction.signal_id == signal_id,
        )
        .order_by(desc(SignalAction.created_at))
        .limit(1)
    )


def _bucket_schema(
    score: float,
    *,
    fragility: float,
    baseline: float,
    specificity: float,
) -> UserFacingBucket:
    bucket = score_to_user_bucket_v1(
        score,
        fragility_penalty=fragility,
        baseline_coverage_percent=baseline,
        specificity_score=specificity,
    )
    return UserFacingBucket(
        label=bucket.label,
        reason_codes=list(bucket.reason_codes),
        version=bucket.version,
    )


def _insight_release_ready(angle: dict[str, object]) -> bool:
    if angle.get("release_ready") is not True:
        return False
    if angle.get("insight_status") != "evidence_backed":
        return False
    insight_type = str(angle.get("insight_type") or "")
    reasons_raw = angle.get("insight_reason_codes")
    reasons = {str(reason) for reason in reasons_raw} if isinstance(reasons_raw, list) else set()
    evidence_raw = angle.get("insight_evidence")
    evidence = (
        {str(reference) for reference in evidence_raw} if isinstance(evidence_raw, list) else set()
    )
    audited = (
        insight_type.startswith("audited_")
        and "llm_grounding_audit_passed" in reasons
        and "llm_non_obviousness_audit_passed" in reasons
    )
    confirmed_demand = (
        insight_type == "audience_demand"
        and "confirmed_cross_video_audience_demand" in reasons
        and len(evidence) >= 2
    )
    return audited or confirmed_demand


def _decision_card(
    session: Session,
    workspace_id: str,
    signal: Signal,
    topic: Topic,
    workspace_score: WorkspaceSignalScore,
    *,
    thesis: str,
    content_angles: list[dict[str, object]],
    evidence_video_count: int,
    independent_channel_count: int,
    use_feasibility_v2: bool = False,
) -> SignalDecisionCard:
    components = signal.component_json
    baseline = float(components.get("baseline_coverage", 0))
    specificity = float(components.get("specificity_score", 0))
    transcript = float(components.get("transcript_coverage", 0))
    fragility = float(components.get("fragility_penalty", 0))
    saturation = float(components.get("saturation_penalty", 0))
    fit_components = workspace_score.fit_component_json
    angle = content_angles[0] if content_angles else {}
    release_ready = _insight_release_ready(angle)
    insight_status: Literal["evidence_backed", "candidate"] = (
        "evidence_backed"
        if release_ready and angle.get("insight_status") == "evidence_backed"
        else "candidate"
    )
    insight_type = str(angle.get("insight_type") or "unavailable")
    insight_statement = str(
        angle.get("insight_statement")
        or ("The stored evidence supports a trend, but not a non-obvious video insight yet.")
    )
    insight_reason_codes_raw = angle.get("insight_reason_codes")
    insight_reason_codes = (
        [str(reason) for reason in insight_reason_codes_raw]
        if isinstance(insight_reason_codes_raw, list)
        else ["missing_insight_provenance"]
    )

    signal_bucket = _bucket_schema(
        signal.score,
        fragility=fragility,
        baseline=baseline,
        specificity=specificity,
    )
    fit_bucket = _bucket_schema(
        workspace_score.channel_fit_score,
        fragility=fragility,
        baseline=baseline,
        specificity=specificity,
    )
    confidence_score = {"high": 88, "medium": 66, "low": 38}.get(
        signal.confidence.lower(),
        45,
    )
    confidence_bucket = _bucket_schema(
        confidence_score,
        fragility=fragility,
        baseline=baseline,
        specificity=specificity,
    )
    evidence_score = (
        baseline * 0.38
        + specificity * 0.32
        + transcript * 0.14
        + min(100, independent_channel_count * 14) * 0.16
    )
    evidence_bucket = _bucket_schema(
        evidence_score,
        fragility=fragility,
        baseline=baseline,
        specificity=specificity,
    )

    production_days = angle.get("production_time_days")
    if not isinstance(production_days, dict):
        profile = session.scalar(
            select(ChannelProfile)
            .where(ChannelProfile.workspace_id == workspace_id)
            .order_by(ChannelProfile.updated_at.desc())
            .limit(1)
        )
        production_days = {
            "min": profile.production_days_min if profile else 3,
            "max": profile.production_days_max if profile else 7,
        }
    production_min = int(production_days.get("min", 3))
    production_max = int(production_days.get("max", max(production_min, 7)))
    remaining_days = max(
        0,
        round(
            (_aware(signal.opportunity_end) - _signal_decision_time(signal)).total_seconds()
            / 86_400
        ),
    )
    feasibility_value = str(angle.get("feasibility") or "")
    feasibility_reasons = angle.get("infeasibility_reasons")
    if not isinstance(feasibility_reasons, list):
        feasibility_reasons = []
    production_feasible = (
        bool(angle.get("feasible_for_act"))
        if use_feasibility_v2 and "feasible_for_act" in angle
        else remaining_days >= production_min
    )
    publish_by_raw = angle.get("recommended_publish_by")
    publish_by = (
        datetime.fromisoformat(str(publish_by_raw).replace("Z", "+00:00"))
        if use_feasibility_v2 and publish_by_raw
        else None
    )
    publish_by_label = (
        str(angle.get("recommended_publish_by_label"))
        if angle.get("recommended_publish_by_label")
        else None
    )
    response_publish_by = (
        _signal_response_time(signal, publish_by) if publish_by is not None else None
    )
    if response_publish_by is not None and _demo_reference_time(signal) is not None:
        publish_by_label = _day_label(response_publish_by)
    response_start = _signal_response_time(signal, signal.opportunity_start)
    response_end = _signal_response_time(signal, signal.opportunity_end)
    assessment = assess_decision(
        signal_bucket=signal_bucket.label,
        fit_bucket=fit_bucket.label,
        evidence_bucket=evidence_bucket.label,
        lifecycle_stage=signal.lifecycle_stage,
        saturation_penalty=saturation,
        production_feasible=production_feasible,
        insight_ready=release_ready,
    )

    open_angle = (
        str(angle.get("unanswered_question") or angle.get("title") or insight_statement)
        if release_ready
        else "No evidence-backed video angle yet."
    )
    recommended_video = open_angle
    why_now = (
        str(signal.why_emerging_json[0])
        if signal.why_emerging_json
        else (
            f"{evidence_video_count} recent videos across "
            f"{independent_channel_count} independent channels support the shift."
        )
    )
    if fit_bucket.label in {"High", "Very high"}:
        why_channel = (
            "The topic matches the channel’s audience, formats, and practical production strengths."
        )
    elif fit_bucket.label == "Moderate":
        why_channel = (
            "The topic has a plausible audience and format fit, but the channel match "
            "still needs validation against future performance."
        )
    else:
        why_channel = (
            "The stored channel history does not yet show a strong enough audience "
            "and format match for a confident recommendation."
        )

    if not release_ready:
        main_risk = (
            "The trend is real enough to monitor, but the stored evidence does "
            "not yet support a non-obvious angle worth recommending."
        )
    elif not production_feasible:
        main_risk = str(
            angle.get("infeasibility_explanation")
            or (
                f"The channel needs at least {production_min} production days, "
                f"which exceeds the evidence-backed publish-by date"
                f"{f' ({publish_by_label})' if publish_by_label else ''}."
            )
        )
    elif saturation >= 70:
        main_risk = "Established channels are entering quickly, so the open angle may close."
    elif fragility >= 60:
        main_risk = "The signal still depends on a narrow evidence base and may reverse."
    elif baseline < 70:
        main_risk = (
            "Some evidence channels lack a strong historical baseline, so relative "
            "performance remains uncertain."
        )
    else:
        main_risk = str(
            angle.get("timing_risk") or "New snapshots may change the timing and evidence strength."
        )

    decision_label = {
        "Act": "ACT NOW",
        "Watch": "WATCH",
        "Skip": "SKIP",
    }[assessment.decision]
    effort = str(angle.get("effort") or "Medium")
    return SignalDecisionCard(
        decision=assessment.decision,
        decision_label=decision_label,
        decision_reason_codes=list(assessment.reason_codes),
        decision_version=assessment.version,
        topic=topic.canonical_label,
        thesis=thesis,
        why_now=why_now,
        why_this_channel=why_channel,
        open_angle=open_angle,
        recommended_video=recommended_video,
        release_ready=release_ready,
        insight_status=insight_status,
        insight_type=insight_type,
        insight_statement=insight_statement,
        insight_reason_codes=insight_reason_codes,
        publishing_window=OpportunityWindow(
            start=response_start,
            end=response_publish_by or response_end,
            label=(
                f"By {publish_by_label} · "
                f"{_days_label(response_start, response_publish_by or response_end)}"
                if publish_by_label
                else _days_label(response_start, response_end)
            ),
        ),
        production_effort=effort,
        production_days_min=production_min,
        production_days_max=production_max,
        recommended_publish_by=response_publish_by,
        recommended_publish_by_label=publish_by_label,
        feasibility=feasibility_value or None,
        infeasibility_reasons=[str(reason) for reason in feasibility_reasons],
        decay_version=(str(angle.get("decay_version")) if angle.get("decay_version") else None),
        fit_verification=(
            "verified" if fit_components.get("fit_verification") == "verified" else "estimated"
        ),
        signal_strength=signal_bucket,
        channel_fit=fit_bucket,
        confidence=confidence_bucket,
        evidence_strength=evidence_bucket,
        main_risk=main_risk,
    )


def _topic_snapshots(
    session: Session,
    topic_id: str,
    *,
    use_buckets: bool = False,
) -> list[TopicSnapshot]:
    if use_buckets:
        buckets = list(
            session.scalars(
                select(TopicSnapshotBucket)
                .where(TopicSnapshotBucket.topic_id == topic_id)
                .order_by(TopicSnapshotBucket.bucket_start)
            )
        )
        if buckets:
            return [
                TopicSnapshot(
                    id=f"bucket:{bucket.id}",
                    topic_id=topic_id,
                    observed_at=bucket.bucket_start,
                    video_count_24h=int(
                        bucket.last_json.get("values", {}).get("video_count_24h", 0)
                    ),
                    video_count_72h=int(
                        bucket.last_json.get("values", {}).get("video_count_72h", 0)
                    ),
                    distinct_channels_72h=int(
                        bucket.last_json.get("values", {}).get(
                            "distinct_channels_72h",
                            bucket.channel_count,
                        )
                    ),
                    aggregate_view_velocity=float(
                        bucket.last_json.get("values", {}).get(
                            "aggregate_view_velocity",
                            bucket.momentum,
                        )
                    ),
                    median_outlier_ratio=float(
                        bucket.last_json.get("values", {}).get("median_outlier_ratio", 0)
                    ),
                    large_channel_count=int(
                        bucket.last_json.get("values", {}).get("large_channel_count", 0)
                    ),
                    demand_score=float(bucket.last_json.get("values", {}).get("demand_score", 0)),
                    saturation_score=bucket.saturation,
                    fragility_score=float(
                        bucket.last_json.get("values", {}).get("fragility_score", 0)
                    ),
                    component_json={
                        **dict(bucket.last_json.get("values", {})),
                        "score": bucket.score,
                        "stage": bucket.stage,
                        "resolution": bucket.resolution,
                        "source_measurement_ids": bucket.source_measurement_ids_json,
                    },
                )
                for bucket in buckets
            ]
    return list(
        session.scalars(
            select(TopicSnapshot)
            .where(TopicSnapshot.topic_id == topic_id)
            .order_by(TopicSnapshot.observed_at)
        )
    )


def _evidence_quality(signal: Signal) -> EvidenceQuality:
    baseline = float(signal.component_json.get("baseline_coverage", 0))
    transcripts = float(signal.component_json.get("transcript_coverage", 0))
    specificity = float(signal.component_json.get("specificity_score", 0))
    return EvidenceQuality(
        baseline_coverage_percent=baseline,
        transcript_coverage_percent=transcripts,
        specificity_score=specificity,
        calibrated=baseline >= 70 and specificity >= 70,
    )


def _momentum(snapshots: list[TopicSnapshot]) -> MomentumSummary:
    values = [round(row.aggregate_view_velocity, 1) for row in snapshots]
    if len(values) < 2:
        return MomentumSummary(change_24h=0, change_72h=0, sparkline=values)
    previous = max(values[-2], 1)
    early = max(values[max(0, len(values) - 4)], 1)
    return MomentumSummary(
        change_24h=round((values[-1] / previous - 1) * 100, 1),
        change_72h=round((values[-1] / early - 1) * 100, 1),
        sparkline=values,
    )


def _strongest_demand(
    session: Session,
    topic_id: str,
) -> DemandSummary:
    cluster = session.scalar(
        select(DemandCluster)
        .where(
            DemandCluster.topic_id == topic_id,
            DemandCluster.visibility_status != "internal_candidate",
        )
        .order_by(desc(DemandCluster.demand_score))
        .limit(1)
    )
    if cluster is None:
        return DemandSummary(
            available=False,
            label="No confirmed demand cluster",
            question=(
                "No stored comment cluster currently spans enough independent videos and channels."
            ),
            comment_count=0,
            distinct_channels=0,
            distinct_videos=0,
            distinct_commenters=0,
            evidence_strength="Unavailable",
        )
    comment = session.scalar(
        select(YoutubeComment)
        .join(
            DemandClusterComment,
            DemandClusterComment.comment_id == YoutubeComment.id,
        )
        .where(
            DemandClusterComment.demand_cluster_id == cluster.id,
            DemandClusterComment.is_representative.is_(True),
        )
        .order_by(desc(YoutubeComment.like_count))
        .limit(1)
    )
    if comment is None:
        return DemandSummary(
            available=False,
            label=cluster.label,
            question="No representative comment is stored for this cluster.",
            comment_count=cluster.comment_count,
            distinct_channels=cluster.distinct_channel_count,
            distinct_videos=cluster.distinct_video_count,
            distinct_commenters=cluster.distinct_commenter_count,
            evidence_strength=cluster.evidence_strength,
        )
    return DemandSummary(
        available=True,
        label=cluster.label,
        question=comment.text,
        comment_count=cluster.comment_count,
        distinct_channels=cluster.distinct_channel_count,
        distinct_videos=cluster.distinct_video_count,
        distinct_commenters=cluster.distinct_commenter_count,
        evidence_strength=cluster.evidence_strength,
    )


def _signal_evidence_preview(
    session: Session,
    topic_id: str,
    *,
    limit: int = 3,
) -> list[SignalEvidenceLink]:
    rows = session.execute(
        select(YoutubeVideo, YoutubeChannel)
        .join(TopicVideoMembership, TopicVideoMembership.video_id == YoutubeVideo.id)
        .join(YoutubeChannel, YoutubeChannel.id == YoutubeVideo.channel_id)
        .where(TopicVideoMembership.topic_id == topic_id)
        .order_by(desc(YoutubeVideo.published_at))
        .limit(limit)
    ).all()
    return [
        SignalEvidenceLink(
            id=video.id,
            title=video.title,
            canonical_url=video.canonical_url,
            channel=channel.title,
            published_at=_aware(video.published_at),
        )
        for video, channel in rows
    ]


def available_signal_sources(
    session: Session,
    workspace_id: str,
    *,
    require_review_approval: bool = False,
) -> list[str]:
    query = (
        select(Signal.source_kind)
        .join(
            WorkspaceSignalScore,
            WorkspaceSignalScore.signal_id == Signal.id,
        )
        .where(
            WorkspaceSignalScore.workspace_id == workspace_id,
            Signal.status == "active",
        )
    )
    if require_review_approval:
        query = query.join(
            SignalReview,
            (SignalReview.signal_id == Signal.id)
            & (SignalReview.workspace_id == WorkspaceSignalScore.workspace_id),
        ).where(SignalReview.status.in_(("approved", "published")))
    values = list(session.scalars(query.distinct()))
    return [mode for mode in ("live", "demo") if mode in values]


def resolve_signal_source(
    session: Session,
    workspace_id: str,
    requested: str,
    *,
    require_review_approval: bool = False,
) -> tuple[str, list[str]]:
    available = available_signal_sources(
        session,
        workspace_id,
        require_review_approval=require_review_approval,
    )
    if requested in {"live", "demo"}:
        return requested, available
    return ("live" if "live" in available else "demo"), available


def list_signals(
    session: Session,
    workspace_id: str,
    *,
    source_kind: str,
    include_earlyness: bool = False,
    include_decision: bool = False,
    use_snapshot_buckets: bool = False,
    use_feasibility_v2: bool = False,
    require_review_approval: bool = False,
) -> list[SignalListItem]:
    query = (
        select(Signal, Topic, WorkspaceSignalScore)
        .join(Topic, Topic.id == Signal.topic_id)
        .join(
            WorkspaceSignalScore,
            WorkspaceSignalScore.signal_id == Signal.id,
        )
        .where(
            WorkspaceSignalScore.workspace_id == workspace_id,
            Signal.status == "active",
            Signal.source_kind == source_kind,
        )
        .order_by(
            desc(WorkspaceSignalScore.channel_fit_score),
            desc(Signal.score),
        )
    )
    if require_review_approval:
        query = query.join(
            SignalReview,
            (SignalReview.signal_id == Signal.id)
            & (SignalReview.workspace_id == WorkspaceSignalScore.workspace_id),
        ).where(SignalReview.status.in_(("approved", "published")))
    rows = session.execute(query).all()
    require_personal_relevance = source_kind == "live" and bool(
        session.scalar(
            select(func.count(WorkspaceDiscoveryQuery.query_id)).where(
                WorkspaceDiscoveryQuery.workspace_id == workspace_id,
                WorkspaceDiscoveryQuery.active.is_(True),
            )
        )
    )
    items: list[SignalListItem] = []
    for signal, topic, workspace_score in rows:
        relevance = workspace_score.fit_component_json.get("workspace_relevance", {})
        if require_personal_relevance and not (
            isinstance(relevance, dict)
            and relevance.get("has_personal_discovery_plan") is True
            and relevance.get("eligible") is True
        ):
            continue
        review = session.scalar(
            select(SignalReview).where(
                SignalReview.workspace_id == workspace_id,
                SignalReview.signal_id == signal.id,
            )
        )
        snapshots = _topic_snapshots(
            session,
            topic.id,
            use_buckets=use_snapshot_buckets,
        )
        demand = _strongest_demand(session, topic.id)
        counts = session.execute(
            select(
                func.count(TopicVideoMembership.video_id),
                func.count(func.distinct(YoutubeVideo.channel_id)),
            )
            .join(YoutubeVideo, YoutubeVideo.id == TopicVideoMembership.video_id)
            .where(TopicVideoMembership.topic_id == topic.id)
        ).one()
        thesis = (
            review.thesis_override
            if review is not None and review.thesis_override
            else signal.thesis
        )
        content_angles = [dict(item) for item in workspace_score.recommended_angle_json]
        if review is not None and review.opportunity_override_json and content_angles:
            content_angles[0] = {
                **content_angles[0],
                **review.opportunity_override_json,
            }
        items.append(
            SignalListItem(
                id=signal.id,
                topic_label=topic.canonical_label,
                category=str(topic.entities_json[0] if topic.entities_json else "AI / tech"),
                lifecycle_stage=signal.lifecycle_stage,
                score=signal.score,
                confidence=signal.confidence,
                channel_fit=workspace_score.channel_fit_score,
                opportunity_window=OpportunityWindow(
                    start=_signal_response_time(signal, signal.opportunity_start),
                    end=_signal_response_time(signal, signal.opportunity_end),
                    label=_days_label(
                        _signal_response_time(signal, signal.opportunity_start),
                        _signal_response_time(signal, signal.opportunity_end),
                    ),
                ),
                momentum=_momentum(snapshots),
                independent_channels=int(counts[1] or 0),
                evidence_videos=int(counts[0] or 0),
                evidence_preview=_signal_evidence_preview(session, topic.id),
                evidence_quality=_evidence_quality(signal),
                strongest_demand=demand,
                thesis=thesis,
                current_action=_current_action(session, workspace_id, signal.id),
                generated_at=_aware(signal.generated_at),
                data_mode=signal.source_kind,
                earlyness=(
                    earlyness_summary_for_signal(session, signal, topic)
                    if include_earlyness
                    else None
                ),
                decision_card=(
                    _decision_card(
                        session,
                        workspace_id,
                        signal,
                        topic,
                        workspace_score,
                        thesis=thesis,
                        content_angles=content_angles,
                        evidence_video_count=int(counts[0] or 0),
                        independent_channel_count=int(counts[1] or 0),
                        use_feasibility_v2=use_feasibility_v2,
                    )
                    if include_decision
                    else None
                ),
            )
        )
    return items


def _latest_snapshot(session: Session, video_id: str) -> VideoSnapshot:
    snapshot = session.scalar(
        select(VideoSnapshot)
        .where(VideoSnapshot.video_id == video_id)
        .order_by(desc(VideoSnapshot.observed_at))
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(500, "Evidence video has no historical snapshot")
    return snapshot


def _sparkline(session: Session, video_id: str) -> list[float]:
    return [
        row.views_per_hour
        for row in session.scalars(
            select(VideoSnapshot)
            .where(VideoSnapshot.video_id == video_id)
            .order_by(VideoSnapshot.observed_at)
        )
    ]


def _evidence_videos(
    session: Session,
    topic_id: str,
) -> tuple[list[EvidenceVideo], list[DiffusionPoint]]:
    rows = session.execute(
        select(TopicVideoMembership, YoutubeVideo, YoutubeChannel)
        .join(YoutubeVideo, YoutubeVideo.id == TopicVideoMembership.video_id)
        .join(YoutubeChannel, YoutubeChannel.id == YoutubeVideo.channel_id)
        .where(TopicVideoMembership.topic_id == topic_id)
        .order_by(desc(YoutubeVideo.published_at))
    ).all()
    evidence: list[EvidenceVideo] = []
    diffusion: list[DiffusionPoint] = []
    for membership, video, channel in rows:
        snapshot = _latest_snapshot(session, video.id)
        feature = session.scalar(
            select(VideoFeature)
            .where(VideoFeature.video_id == video.id)
            .order_by(desc(VideoFeature.calculated_at))
            .limit(1)
        )
        transcript = session.scalar(
            select(VideoTranscript).where(VideoTranscript.video_id == video.id)
        )
        comment_count = session.scalar(
            select(func.count(YoutubeComment.id)).where(YoutubeComment.video_id == video.id)
        )
        freshness_minutes = (_now() - _aware(snapshot.observed_at)).total_seconds() / 60
        freshness = (
            "Very fresh"
            if freshness_minutes < 120
            else "Fresh"
            if freshness_minutes < 360
            else "Stale"
        )
        evidence.append(
            EvidenceVideo(
                id=video.id,
                youtube_video_id=video.youtube_video_id,
                title=video.title,
                canonical_url=video.canonical_url,
                thumbnail_url=video.thumbnail_url,
                channel=channel.title,
                channel_subscribers=channel.subscriber_count,
                published_at=_aware(video.published_at),
                age_label=_age_label(video.published_at),
                views=snapshot.view_count,
                view_velocity=snapshot.views_per_hour,
                outlier_ratio=round(feature.outlier_ratio, 2) if feature else 1,
                role=membership.evidence_role,
                freshness=freshness,
                transcript_status=(
                    transcript.transcript_type.replace("-", " ").title()
                    if transcript is not None
                    else "Not fetched"
                ),
                comment_sample_status="Sampled" if comment_count else "Candidate",
                sparkline=_sparkline(session, video.id),
            )
        )
        diffusion.append(
            DiffusionPoint(
                channel=channel.title,
                subscribers=channel.subscriber_count,
                published_at=_aware(video.published_at),
                role=membership.evidence_role,
            )
        )
    diffusion.sort(key=lambda item: item.published_at)
    return evidence, diffusion


def _transcript_evidence(
    session: Session,
    topic_id: str,
) -> list[TranscriptEvidence]:
    rows = session.execute(
        select(VideoTranscript, YoutubeVideo)
        .join(YoutubeVideo, YoutubeVideo.id == VideoTranscript.video_id)
        .join(
            TopicVideoMembership,
            TopicVideoMembership.video_id == YoutubeVideo.id,
        )
        .where(TopicVideoMembership.topic_id == topic_id)
        .order_by(desc(VideoTranscript.quality_score), desc(VideoTranscript.fetched_at))
        .limit(4)
    ).all()
    response: list[TranscriptEvidence] = []
    for transcript, video in rows:
        segments = list(
            session.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.transcript_id == transcript.id,
                    TranscriptSegment.is_evidence.is_(True),
                )
                .order_by(TranscriptSegment.start_seconds)
                .limit(3)
            )
        )
        response.append(
            TranscriptEvidence(
                video_id=video.id,
                youtube_video_id=video.youtube_video_id,
                video_title=video.title,
                language=transcript.language,
                transcript_type=transcript.transcript_type,
                quality_score=transcript.quality_score,
                summary=str(transcript.summary_json.get("text", ""))[:480],
                entities=list(transcript.entities_json)[:8],
                content_format=transcript.content_format,
                narrative_angle=transcript.narrative_angle,
                fetched_at=_aware(transcript.fetched_at),
                segments=[
                    TranscriptSegmentEvidence(
                        id=segment.id,
                        start_seconds=segment.start_seconds,
                        end_seconds=segment.end_seconds,
                        text=segment.text[:280],
                        video_url=(
                            f"{video.canonical_url}&t={round(segment.start_seconds)}s"
                            if "?" in video.canonical_url
                            else f"{video.canonical_url}?t={round(segment.start_seconds)}s"
                        ),
                    )
                    for segment in segments
                ],
            )
        )
    return response


def _demand_evidence(session: Session, topic_id: str) -> list[DemandEvidence]:
    clusters = list(
        session.scalars(
            select(DemandCluster)
            .where(
                DemandCluster.topic_id == topic_id,
                DemandCluster.visibility_status != "internal_candidate",
            )
            .order_by(desc(DemandCluster.demand_score))
        )
    )
    response: list[DemandEvidence] = []
    for cluster in clusters:
        rows = session.execute(
            select(YoutubeComment, YoutubeVideo)
            .join(
                DemandClusterComment,
                DemandClusterComment.comment_id == YoutubeComment.id,
            )
            .join(YoutubeVideo, YoutubeVideo.id == YoutubeComment.video_id)
            .where(
                DemandClusterComment.demand_cluster_id == cluster.id,
                DemandClusterComment.is_representative.is_(True),
            )
            .order_by(desc(YoutubeComment.like_count))
        ).all()
        response.append(
            DemandEvidence(
                id=cluster.id,
                label=cluster.label,
                summary=cluster.summary,
                taxonomy=cluster.taxonomy,
                comment_count=cluster.comment_count,
                distinct_commenters=cluster.distinct_commenter_count,
                distinct_videos=cluster.distinct_video_count,
                distinct_channels=cluster.distinct_channel_count,
                score=cluster.demand_score,
                date_range=(
                    _aware(cluster.first_observed_at),
                    _aware(cluster.last_observed_at),
                ),
                snippets=[
                    {
                        "comment_id": comment.id,
                        "text": comment.text,
                        "likes": comment.like_count,
                        "video_id": video.id,
                        "video_title": video.title,
                        "video_url": video.canonical_url,
                    }
                    for comment, video in rows
                ],
                confidence=(
                    "High"
                    if cluster.demand_score >= 80
                    else "Medium"
                    if cluster.demand_score >= 55
                    else "Low"
                ),
                evidence_strength=cluster.evidence_strength,
                limitation=(
                    "Only comments that pass the stored relevance gate are counted; "
                    "top and newest comments are still a sample."
                    if cluster.relevance_model_version
                    else "Top and newest comments are sampled; counts describe the stored sample."
                ),
            )
        )
    return response


def get_signal_detail(
    session: Session,
    workspace_id: str,
    signal_id: str,
    *,
    include_earlyness: bool = False,
    include_decision: bool = False,
    include_content_gap: bool = False,
    use_snapshot_buckets: bool = False,
    use_feasibility_v2: bool = False,
    require_review_approval: bool = False,
) -> SignalDetail:
    row = session.execute(
        select(Signal, Topic, WorkspaceSignalScore)
        .join(Topic, Topic.id == Signal.topic_id)
        .join(
            WorkspaceSignalScore,
            WorkspaceSignalScore.signal_id == Signal.id,
        )
        .where(
            Signal.id == signal_id,
            WorkspaceSignalScore.workspace_id == workspace_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Signal not found")
    signal, topic, workspace_score = row
    review = session.scalar(
        select(SignalReview).where(
            SignalReview.workspace_id == workspace_id,
            SignalReview.signal_id == signal.id,
        )
    )
    if require_review_approval and (
        review is None or review.status not in {"approved", "published"}
    ):
        raise HTTPException(404, "Signal not found")
    snapshots = _topic_snapshots(
        session,
        topic.id,
        use_buckets=use_snapshot_buckets,
    )
    evidence, diffusion = _evidence_videos(session, topic.id)
    if review is not None and review.evidence_selection_json:
        selected = set(review.evidence_selection_json)
        evidence = [item for item in evidence if item.id in selected]
    transcript_evidence = _transcript_evidence(session, topic.id)
    demand = _demand_evidence(session, topic.id)
    provider_rows = session.execute(
        select(FieldProvenance, ProviderFetch)
        .join(ProviderFetch, ProviderFetch.id == FieldProvenance.provider_fetch_id)
        .where(FieldProvenance.entity_id == signal.id)
    ).all()
    if not provider_rows:
        evidence_ids = [video.id for video in evidence]
        provider_rows = session.execute(
            select(FieldProvenance, ProviderFetch)
            .join(
                ProviderFetch,
                ProviderFetch.id == FieldProvenance.provider_fetch_id,
            )
            .where(
                FieldProvenance.entity_type == "video",
                FieldProvenance.entity_id.in_(
                    [
                        f"youtube:{video.youtube_video_id}"
                        for video in session.scalars(
                            select(YoutubeVideo).where(YoutubeVideo.id.in_(evidence_ids))
                        )
                    ]
                ),
            )
            .order_by(desc(FieldProvenance.observed_at))
            .limit(30)
        ).all()
    demand_comment_ids = list(
        session.scalars(
            select(DemandClusterComment.comment_id)
            .join(
                DemandCluster,
                DemandCluster.id == DemandClusterComment.demand_cluster_id,
            )
            .where(DemandCluster.topic_id == topic.id)
            .where(DemandCluster.visibility_status != "internal_candidate")
        )
    )
    if demand_comment_ids:
        comment_provider_rows = session.execute(
            select(FieldProvenance, ProviderFetch)
            .join(
                ProviderFetch,
                ProviderFetch.id == FieldProvenance.provider_fetch_id,
            )
            .where(
                FieldProvenance.entity_type == "comment",
                FieldProvenance.entity_id.in_(demand_comment_ids),
            )
            .order_by(desc(FieldProvenance.observed_at))
            .limit(15)
        ).all()
        provider_rows = [*comment_provider_rows, *provider_rows][:30]
    transcript_ids = [
        transcript.id
        for transcript in session.scalars(
            select(VideoTranscript)
            .join(
                TopicVideoMembership,
                TopicVideoMembership.video_id == VideoTranscript.video_id,
            )
            .where(TopicVideoMembership.topic_id == topic.id)
        )
    ]
    if transcript_ids:
        transcript_provider_rows = session.execute(
            select(FieldProvenance, ProviderFetch)
            .join(
                ProviderFetch,
                ProviderFetch.id == FieldProvenance.provider_fetch_id,
            )
            .where(
                FieldProvenance.entity_type == "transcript",
                FieldProvenance.entity_id.in_(transcript_ids),
            )
            .order_by(desc(FieldProvenance.observed_at))
            .limit(12)
        ).all()
        provider_rows = [*transcript_provider_rows, *provider_rows][:30]
    freshness_candidates = [video.published_at for video in evidence]
    last_snapshot = max(
        (_latest_snapshot(session, video.id).observed_at for video in evidence),
        default=signal.generated_at,
    )
    data_freshness = {
        "last_video_snapshot_at": _aware(last_snapshot),
        "last_discovery_at": _aware(max(freshness_candidates, default=signal.generated_at)),
    }
    if demand:
        last_comment_fetch = session.scalar(
            select(func.max(ProviderFetch.completed_at))
            .join(
                YoutubeComment,
                YoutubeComment.provider_fetch_id == ProviderFetch.id,
            )
            .join(
                TopicVideoMembership,
                TopicVideoMembership.video_id == YoutubeComment.video_id,
            )
            .where(TopicVideoMembership.topic_id == topic.id)
        )
        if last_comment_fetch is not None:
            data_freshness["last_comment_fetch_at"] = _aware(last_comment_fetch)
    if transcript_evidence:
        data_freshness["last_transcript_fetch_at"] = max(
            item.fetched_at for item in transcript_evidence
        )
    content_angles = [dict(item) for item in workspace_score.recommended_angle_json]
    if review is not None and review.opportunity_override_json and content_angles:
        content_angles[0] = {
            **content_angles[0],
            **review.opportunity_override_json,
        }
    thesis = (
        review.thesis_override if review is not None and review.thesis_override else signal.thesis
    )
    content_gap_map: dict[str, object] | None = None
    if include_content_gap:
        content_patterns = list(
            session.scalars(
                select(TopicContentPattern)
                .where(TopicContentPattern.topic_id == topic.id)
                .order_by(TopicContentPattern.calculated_at.desc())
            )
        )
        content_gaps = list(
            session.scalars(
                select(TopicContentGap)
                .where(
                    TopicContentGap.workspace_id == workspace_id,
                    TopicContentGap.topic_id == topic.id,
                    TopicContentGap.status == "active",
                )
                .order_by(TopicContentGap.rank)
            )
        )
        content_gap_map = {
            "pattern_version": (
                content_patterns[0].model_version if content_patterns else "unavailable"
            ),
            "gap_version": (content_gaps[0].model_version if content_gaps else "unavailable"),
            "ranking_version": (content_gaps[0].ranking_version if content_gaps else "unavailable"),
            "patterns": [item.pattern_json for item in content_patterns],
            "gaps": [
                {
                    "gap_key": item.gap_key,
                    "rank": item.rank,
                    "occupied_pattern": item.occupied_pattern_json,
                    "open_gap": item.open_gap_json,
                    "score_components": item.score_components_json,
                    "evidence": item.evidence_json,
                }
                for item in content_gaps
            ],
        }
    return SignalDetail(
        id=signal.id,
        topic={
            "id": topic.id,
            "label": topic.canonical_label,
            "stage": topic.lifecycle_stage,
            "aliases": topic.aliases_json,
            "entities": topic.entities_json,
            "first_observed_at": _aware(topic.first_observed_at),
            "first_confirmed_at": _aware(topic.first_confirmed_at),
            **(
                {
                    "identity": topic.identity_json,
                    "specificity_score": topic.specificity_score,
                    "thesis_support_ratio": topic.thesis_support_ratio,
                    "visibility_reason_codes": (topic.visibility_reason_codes_json),
                    "clustering_version": topic.clustering_version,
                }
                if include_content_gap
                else {}
            ),
        },
        score=signal.score,
        confidence=signal.confidence,
        channel_fit=workspace_score.channel_fit_score,
        opportunity_window=OpportunityWindow(
            start=_signal_response_time(signal, signal.opportunity_start),
            end=_signal_response_time(signal, signal.opportunity_end),
            label=_days_label(
                _signal_response_time(signal, signal.opportunity_start),
                _signal_response_time(signal, signal.opportunity_end),
            ),
        ),
        thesis=thesis,
        why_emerging=signal.why_emerging_json,
        why_emerging_evidence=[
            {
                "text": str(item.get("text", "")),
                "evidence_refs": [
                    str(reference)
                    for reference in item.get("evidence_refs", [])
                    if isinstance(reference, str)
                ],
            }
            for item in signal.synthesis_json.get("why_growing", [])
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ],
        intelligence_provenance=(
            dict(signal.synthesis_json.get("provenance", {}))
            if isinstance(signal.synthesis_json.get("provenance"), dict)
            else {}
        ),
        score_components=signal.component_json,
        evidence_quality=_evidence_quality(signal),
        evidence_videos=evidence,
        transcript_evidence=transcript_evidence,
        demand_clusters=demand,
        timeline=[
            TimelinePoint(
                observed_at=_aware(item.observed_at),
                video_count_24h=item.video_count_24h,
                distinct_channels_72h=item.distinct_channels_72h,
                aggregate_view_velocity=item.aggregate_view_velocity,
            )
            for item in snapshots
        ],
        diffusion=diffusion,
        saturation={
            "score": signal.component_json["saturation_penalty"],
            "label": "Low"
            if signal.component_json["saturation_penalty"] < 35
            else "Moderate"
            if signal.component_json["saturation_penalty"] < 70
            else "High",
            "large_channel_count": snapshots[-1].large_channel_count if snapshots else 0,
            "analysis": (
                "Large channels remain a minority of recent evidence."
                if signal.component_json["saturation_penalty"] < 50
                else "Established channels are taking a growing share of recent coverage."
            ),
        },
        channel_fit_detail=workspace_score.fit_component_json,
        content_angles=content_angles,
        current_action=_current_action(session, workspace_id, signal.id),
        data_freshness=data_freshness,
        provenance=[
            {
                "field_name": provenance.field_name,
                "provider": fetch.provider,
                "provider_fetch_id": fetch.id,
                "observed_at": _aware(provenance.observed_at),
                "confidence": provenance.confidence,
                "raw_payload_hash": fetch.raw_payload_hash,
            }
            for provenance, fetch in provider_rows
        ],
        data_mode=signal.source_kind,
        earlyness=(
            get_signal_earlyness(session, workspace_id, signal.id)
            if include_earlyness and session.get(TopicLifecycleSummary, topic.id) is not None
            else None
        ),
        decision_card=(
            _decision_card(
                session,
                workspace_id,
                signal,
                topic,
                workspace_score,
                thesis=thesis,
                content_angles=content_angles,
                evidence_video_count=len(evidence),
                independent_channel_count=len({item.channel for item in evidence}),
                use_feasibility_v2=use_feasibility_v2,
            )
            if include_decision
            else None
        ),
        content_gap_map=content_gap_map,
    )
