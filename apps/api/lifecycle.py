from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import (
    Signal,
    Topic,
    TopicLifecycleSummary,
    TopicLifecycleTransition,
    TopicSnapshot,
    TopicVideoMembership,
    WorkspaceSignalScore,
    YoutubeVideo,
)
from apps.api.schemas import (
    LifecycleMilestone,
    LifecycleTransitionEvidence,
    SignalEarlynessResponse,
    SignalEarlynessSummary,
)

HISTORY_VERSION = "topic-lifecycle-history-v1"
BACKFILL_VERSION = "topic-lifecycle-backfill-v1"
LARGE_CHANNEL_THRESHOLD_SUBSCRIBERS = 100_000
LIFECYCLE_STAGES = (
    "Seed",
    "Emerging",
    "Breakout",
    "Mass Market",
    "Saturated",
    "Declining",
)


@dataclass(frozen=True)
class HistoricalLifecycleMeasurement:
    measurement_id: str
    observed_at: datetime
    video_count_24h: int
    video_count_72h: int
    previous_video_count_24h: int
    distinct_channels: int
    distinct_channels_72h: int
    aggregate_view_velocity: float
    large_channel_count: int
    saturation_score: float
    score: float | None


@dataclass(frozen=True)
class LifecycleBackfillResult:
    topics_processed: int
    transitions_created: int
    summaries_created: int


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _bounded(value: float) -> float:
    return min(100.0, max(0.0, value))


def historical_momentum(measurement: HistoricalLifecycleMeasurement) -> float:
    acceleration = (measurement.video_count_24h - measurement.previous_video_count_24h) / max(
        measurement.previous_video_count_24h, 1
    )
    return _bounded(
        measurement.video_count_24h * 13
        + measurement.video_count_72h * 4
        + math.log10(measurement.aggregate_view_velocity + 1) * 11
        + max(-10, min(20, acceleration * 18))
    )


def classify_historical_lifecycle(
    measurement: HistoricalLifecycleMeasurement,
) -> str:
    momentum = historical_momentum(measurement)
    if measurement.saturation_score >= 78:
        return "Saturated"
    if measurement.video_count_24h == 0 and measurement.video_count_72h == 0:
        return "Declining"
    if measurement.large_channel_count >= 3 and measurement.distinct_channels >= 7:
        return "Mass Market"
    if momentum >= 72 and measurement.distinct_channels >= 5:
        return "Breakout"
    if measurement.distinct_channels >= 3 and (measurement.video_count_24h >= 2 or momentum >= 46):
        return "Emerging"
    return "Seed"


def measurement_from_snapshot(snapshot: TopicSnapshot) -> HistoricalLifecycleMeasurement:
    components = snapshot.component_json
    return HistoricalLifecycleMeasurement(
        measurement_id=snapshot.id,
        observed_at=_aware(snapshot.observed_at),
        video_count_24h=snapshot.video_count_24h,
        video_count_72h=snapshot.video_count_72h,
        previous_video_count_24h=int(components.get("previous_video_count_24h", 0)),
        distinct_channels=int(components.get("distinct_channels", snapshot.distinct_channels_72h)),
        distinct_channels_72h=snapshot.distinct_channels_72h,
        aggregate_view_velocity=snapshot.aggregate_view_velocity,
        large_channel_count=snapshot.large_channel_count,
        saturation_score=snapshot.saturation_score,
        score=(
            float(components["score"]) if isinstance(components.get("score"), int | float) else None
        ),
    )


def snapshot_supports_visible_signal(
    snapshot: TopicSnapshot,
    lifecycle_stage: str,
) -> bool:
    components = snapshot.component_json
    required = (
        "distinct_channels",
        "baseline_coverage",
        "top_outlier_ratio",
        "top_velocity_share",
        "specificity_score",
        "score",
    )
    if any(not isinstance(components.get(key), int | float) for key in required):
        return False
    return bool(
        float(components["specificity_score"]) >= 65
        and snapshot.video_count_72h >= 2
        and int(components["distinct_channels"]) >= 3
        and snapshot.distinct_channels_72h >= 2
        and float(components["baseline_coverage"]) >= 0.5
        and (
            snapshot.median_outlier_ratio >= 1.1
            or (
                float(components["top_outlier_ratio"]) >= 1.8
                and float(components["top_velocity_share"]) <= 0.75
            )
        )
        and float(components["score"]) >= 30
        and lifecycle_stage not in {"Saturated", "Declining"}
    )


def lifecycle_reason_codes(
    stage: str,
    measurement: HistoricalLifecycleMeasurement,
    *,
    backfilled: bool,
) -> list[str]:
    reasons = ["backfilled_from_topic_snapshot"] if backfilled else ["new_topic_measurement"]
    if stage == "Seed":
        reasons.append("independent_growth_below_emerging_floor")
    elif stage == "Emerging":
        reasons.extend(["independent_channels_3_plus", "recent_publication_growth"])
    elif stage == "Breakout":
        reasons.extend(["momentum_72_plus", "independent_channels_5_plus"])
    elif stage == "Mass Market":
        reasons.extend(["large_channels_3_plus", "independent_channels_7_plus"])
    elif stage == "Saturated":
        reasons.append("saturation_78_plus")
    elif stage == "Declining":
        reasons.append("no_recent_publications_72h")
    if measurement.large_channel_count:
        reasons.append("large_channel_100k_plus_present")
    return reasons


def _transition_id(
    topic_id: str,
    transitioned_at: datetime,
    stage: str,
    measurement_id: str | None,
) -> str:
    key = (
        f"earlysignal:lifecycle:{topic_id}:{_aware(transitioned_at).isoformat()}:"
        f"{stage}:{measurement_id or 'none'}"
    )
    return str(uuid5(NAMESPACE_URL, key))


def _insert_transition(
    session: Session,
    *,
    topic_id: str,
    from_stage: str | None,
    to_stage: str,
    transitioned_at: datetime,
    measurement_id: str | None,
    score: float | None,
    reason_codes: list[str],
) -> bool:
    transition_id = _transition_id(
        topic_id,
        transitioned_at,
        to_stage,
        measurement_id,
    )
    if session.get(TopicLifecycleTransition, transition_id) is not None:
        return False
    if measurement_id is not None:
        existing_measurement = session.scalar(
            select(TopicLifecycleTransition).where(
                TopicLifecycleTransition.topic_id == topic_id,
                TopicLifecycleTransition.measurement_id == measurement_id,
            )
        )
        if existing_measurement is not None:
            return False
    session.add(
        TopicLifecycleTransition(
            id=transition_id,
            topic_id=topic_id,
            from_stage=from_stage,
            to_stage=to_stage,
            transitioned_at=_aware(transitioned_at),
            measurement_id=measurement_id,
            score=score,
            reason_codes_json=reason_codes,
            history_version=HISTORY_VERSION,
            created_at=datetime.now(tz=UTC),
        )
    )
    return True


def _set_earliest(
    summary: TopicLifecycleSummary,
    field_name: str,
    candidate: datetime | None,
) -> bool:
    if candidate is None:
        return False
    current = getattr(summary, field_name)
    if current is None or _aware(candidate) < _aware(current):
        setattr(summary, field_name, _aware(candidate))
        return True
    return False


def refresh_lifecycle_summary(
    session: Session,
    topic_id: str,
    *,
    signal_visible_at: datetime | None = None,
    signal_visibility_measurement_id: str | None = None,
    infer_signal_visibility_from_snapshots: bool = True,
) -> bool:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise RuntimeError(f"Topic {topic_id} does not exist")
    summary = session.get(TopicLifecycleSummary, topic_id)
    created = summary is None
    if summary is None:
        summary = TopicLifecycleSummary(
            topic_id=topic_id,
            first_video_published_at=None,
            first_discovered_at=None,
            first_topic_formed_at=None,
            first_seed_at=None,
            first_emerging_at=None,
            first_signal_visible_at=None,
            first_breakout_at=None,
            first_mass_market_at=None,
            first_saturated_at=None,
            first_declining_at=None,
            first_large_channel_adoption_at=None,
            latest_measurement_at=None,
            evidence_json={},
            backfill_version=BACKFILL_VERSION,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        session.add(summary)

    videos = list(
        session.scalars(
            select(YoutubeVideo)
            .join(
                TopicVideoMembership,
                TopicVideoMembership.video_id == YoutubeVideo.id,
            )
            .where(TopicVideoMembership.topic_id == topic_id)
        )
    )
    snapshots = list(
        session.scalars(
            select(TopicSnapshot)
            .where(TopicSnapshot.topic_id == topic_id)
            .order_by(TopicSnapshot.observed_at, TopicSnapshot.id)
        )
    )
    transitions = list(
        session.scalars(
            select(TopicLifecycleTransition)
            .where(TopicLifecycleTransition.topic_id == topic_id)
            .order_by(
                TopicLifecycleTransition.transitioned_at,
                TopicLifecycleTransition.id,
            )
        )
    )
    evidence: dict[str, Any] = dict(summary.evidence_json)
    if videos:
        first_published_video = min(videos, key=lambda item: _aware(item.published_at))
        first_discovered_video = min(
            videos,
            key=lambda item: _aware(item.first_discovered_at),
        )
        if _set_earliest(
            summary,
            "first_video_published_at",
            first_published_video.published_at,
        ):
            evidence["first_video_id"] = first_published_video.id
        if _set_earliest(
            summary,
            "first_discovered_at",
            first_discovered_video.first_discovered_at,
        ):
            evidence["first_discovered_video_id"] = first_discovered_video.id

    if snapshots:
        first_snapshot = snapshots[0]
        if _set_earliest(
            summary,
            "first_topic_formed_at",
            first_snapshot.observed_at,
        ):
            evidence["first_topic_measurement_id"] = first_snapshot.id
        latest_snapshot = snapshots[-1]
        if summary.latest_measurement_at is None or _aware(latest_snapshot.observed_at) > _aware(
            summary.latest_measurement_at
        ):
            summary.latest_measurement_at = _aware(latest_snapshot.observed_at)
            evidence["latest_measurement_id"] = latest_snapshot.id

        first_large = next(
            (snapshot for snapshot in snapshots if snapshot.large_channel_count > 0),
            None,
        )
        if first_large is not None and _set_earliest(
            summary,
            "first_large_channel_adoption_at",
            first_large.observed_at,
        ):
            evidence["first_large_channel_measurement_id"] = first_large.id

        if infer_signal_visibility_from_snapshots:
            first_visible: TopicSnapshot | None = None
            for snapshot in snapshots:
                stage = classify_historical_lifecycle(measurement_from_snapshot(snapshot))
                if snapshot_supports_visible_signal(snapshot, stage):
                    first_visible = snapshot
                    break
            if first_visible is not None and _set_earliest(
                summary,
                "first_signal_visible_at",
                first_visible.observed_at,
            ):
                evidence["first_signal_visible_measurement_id"] = first_visible.id

    transition_fields = {
        "Seed": "first_seed_at",
        "Emerging": "first_emerging_at",
        "Breakout": "first_breakout_at",
        "Mass Market": "first_mass_market_at",
        "Saturated": "first_saturated_at",
        "Declining": "first_declining_at",
    }
    for transition in transitions:
        field_name = transition_fields.get(transition.to_stage)
        if field_name is None:
            continue
        if _set_earliest(summary, field_name, transition.transitioned_at):
            evidence[f"{field_name}_transition_id"] = transition.id

    if signal_visible_at is not None and _set_earliest(
        summary,
        "first_signal_visible_at",
        signal_visible_at,
    ):
        evidence["first_signal_visible_measurement_id"] = signal_visibility_measurement_id
        evidence["first_signal_visible_evidence_id"] = signal_visibility_measurement_id

    evidence["large_channel_threshold_subscribers"] = LARGE_CHANNEL_THRESHOLD_SUBSCRIBERS
    evidence["history_version"] = HISTORY_VERSION
    summary.evidence_json = evidence
    summary.backfill_version = BACKFILL_VERSION
    summary.updated_at = datetime.now(tz=UTC)
    session.flush()
    return created


def backfill_lifecycle_history(
    session: Session,
    *,
    source_kind: str | None = None,
) -> LifecycleBackfillResult:
    query = select(Topic).where(Topic.status == "active").order_by(Topic.id)
    if source_kind is not None:
        query = query.where(Topic.source_kind == source_kind)
    topics = list(session.scalars(query))
    transitions_created = 0
    summaries_created = 0
    for topic in topics:
        snapshots = list(
            session.scalars(
                select(TopicSnapshot)
                .where(TopicSnapshot.topic_id == topic.id)
                .order_by(TopicSnapshot.observed_at, TopicSnapshot.id)
            )
        )
        previous_stage: str | None = None
        for snapshot in snapshots:
            measurement = measurement_from_snapshot(snapshot)
            stage = classify_historical_lifecycle(measurement)
            if stage != previous_stage:
                transitions_created += int(
                    _insert_transition(
                        session,
                        topic_id=topic.id,
                        from_stage=previous_stage,
                        to_stage=stage,
                        transitioned_at=measurement.observed_at,
                        measurement_id=measurement.measurement_id,
                        score=measurement.score,
                        reason_codes=lifecycle_reason_codes(
                            stage,
                            measurement,
                            backfilled=True,
                        ),
                    )
                )
            previous_stage = stage
        session.flush()
        summaries_created += int(refresh_lifecycle_summary(session, topic.id))
    return LifecycleBackfillResult(
        topics_processed=len(topics),
        transitions_created=transitions_created,
        summaries_created=summaries_created,
    )


def record_lifecycle_measurement(
    session: Session,
    *,
    topic_id: str,
    snapshot: TopicSnapshot,
    stage: str,
    score: float,
    signal_visible: bool,
    review_gated: bool = False,
) -> bool:
    last_transition = session.scalar(
        select(TopicLifecycleTransition)
        .where(TopicLifecycleTransition.topic_id == topic_id)
        .order_by(
            TopicLifecycleTransition.transitioned_at.desc(),
            TopicLifecycleTransition.id.desc(),
        )
        .limit(1)
    )
    measurement = measurement_from_snapshot(snapshot)
    created = False
    if last_transition is None or last_transition.to_stage != stage:
        created = _insert_transition(
            session,
            topic_id=topic_id,
            from_stage=(last_transition.to_stage if last_transition is not None else None),
            to_stage=stage,
            transitioned_at=snapshot.observed_at,
            measurement_id=snapshot.id,
            score=score,
            reason_codes=lifecycle_reason_codes(
                stage,
                measurement,
                backfilled=False,
            ),
        )
    session.flush()
    refresh_lifecycle_summary(
        session,
        topic_id,
        signal_visible_at=(snapshot.observed_at if signal_visible else None),
        signal_visibility_measurement_id=(snapshot.id if signal_visible else None),
        infer_signal_visibility_from_snapshots=not review_gated,
    )
    return created


def record_review_signal_visibility(
    session: Session,
    *,
    topic_id: str,
    approved_at: datetime,
    review_event_id: str,
) -> None:
    refresh_lifecycle_summary(
        session,
        topic_id,
        signal_visible_at=approved_at,
        signal_visibility_measurement_id=review_event_id,
        infer_signal_visibility_from_snapshots=False,
    )


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((_aware(end) - _aware(start)).total_seconds() / 3600, 1)


def _duration_label(hours: float) -> str:
    absolute_hours = abs(hours)
    if absolute_hours >= 48:
        days = max(1, round(absolute_hours / 24))
        return f"{days} day" if days == 1 else f"{days} days"
    rounded_hours = max(1, round(absolute_hours))
    return f"{rounded_hours} hour" if rounded_hours == 1 else f"{rounded_hours} hours"


def build_earlyness_claim(
    *,
    current_stage: str,
    first_signal_visible_at: datetime | None,
    first_breakout_at: datetime | None,
    first_large_channel_adoption_at: datetime | None,
) -> tuple[str, str, str, float | None, float | None]:
    breakout_lead = _hours_between(first_signal_visible_at, first_breakout_at)
    large_channel_lead = _hours_between(
        first_signal_visible_at,
        first_large_channel_adoption_at,
    )
    if first_signal_visible_at is None:
        return (
            "unverified",
            f"Currently {current_stage}",
            (
                "The first user-visible timestamp is unavailable, so no early "
                "lead-time claim is shown."
            ),
            breakout_lead,
            large_channel_lead,
        )
    if first_breakout_at is None:
        supporting = "Breakout not detected yet."
        if first_large_channel_adoption_at is None:
            supporting += " Large-channel adoption not detected."
        return (
            "pending",
            f"Currently {current_stage}",
            supporting,
            breakout_lead,
            large_channel_lead,
        )
    if breakout_lead is not None and breakout_lead > 0:
        return (
            "early",
            f"Detected {_duration_label(breakout_lead)} before breakout",
            (
                "Lead time is measured from the first stored visible-signal "
                "measurement to the first stored Breakout transition."
            ),
            breakout_lead,
            large_channel_lead,
        )
    if breakout_lead == 0:
        headline = "Signal became visible at breakout"
    else:
        headline = "Signal became visible after breakout"
    return (
        "late",
        headline,
        "No early lead-time claim is shown for this signal.",
        breakout_lead,
        large_channel_lead,
    )


def _earlyness_summary(
    signal: Signal,
    topic: Topic,
    summary: TopicLifecycleSummary,
) -> SignalEarlynessSummary:
    claim_kind, headline, supporting, breakout_lead, large_lead = build_earlyness_claim(
        current_stage=topic.lifecycle_stage,
        first_signal_visible_at=summary.first_signal_visible_at,
        first_breakout_at=summary.first_breakout_at,
        first_large_channel_adoption_at=summary.first_large_channel_adoption_at,
    )
    return SignalEarlynessSummary(
        claim_kind=claim_kind,
        headline=headline,
        supporting_text=supporting,
        current_stage=topic.lifecycle_stage,
        lead_time_to_breakout_hours=breakout_lead,
        lead_time_to_large_channel_hours=large_lead,
    )


def earlyness_summary_for_signal(
    session: Session,
    signal: Signal,
    topic: Topic,
) -> SignalEarlynessSummary | None:
    summary = session.get(TopicLifecycleSummary, topic.id)
    if summary is None:
        return None
    return _earlyness_summary(signal, topic, summary)


def _milestone_status(
    *,
    stage: str | None,
    current_stage: str,
    occurred_at: datetime | None,
) -> str:
    if occurred_at is not None:
        return "current" if stage == current_stage else "reached"
    if stage is None:
        return "not_observed"
    stage_order = {
        "Seed": 0,
        "Emerging": 1,
        "Breakout": 2,
        "Mass Market": 3,
        "Saturated": 4,
    }
    if (
        current_stage in stage_order
        and stage in stage_order
        and stage_order[stage] > stage_order[current_stage]
    ):
        return "pending"
    return "not_observed"


def get_signal_earlyness(
    session: Session,
    workspace_id: str,
    signal_id: str,
) -> SignalEarlynessResponse:
    row = session.execute(
        select(Signal, Topic)
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
    signal, topic = row
    summary = session.get(TopicLifecycleSummary, topic.id)
    if summary is None:
        raise HTTPException(404, "Earlyness history is not ready")
    transitions = list(
        session.scalars(
            select(TopicLifecycleTransition)
            .where(TopicLifecycleTransition.topic_id == topic.id)
            .order_by(
                TopicLifecycleTransition.transitioned_at,
                TopicLifecycleTransition.id,
            )
        )
    )
    summary_claim = _earlyness_summary(signal, topic, summary)
    evidence = summary.evidence_json
    transition_by_stage: dict[str, TopicLifecycleTransition] = {}
    for transition in transitions:
        transition_by_stage.setdefault(transition.to_stage, transition)

    milestone_specs = (
        (
            "first_detected",
            "First detected",
            None,
            summary.first_discovered_at,
            evidence.get("first_discovered_video_id"),
        ),
        (
            "seed",
            "Seed",
            "Seed",
            summary.first_seed_at,
            transition_by_stage.get("Seed"),
        ),
        (
            "emerging",
            "Emerging",
            "Emerging",
            summary.first_emerging_at,
            transition_by_stage.get("Emerging"),
        ),
        (
            "signal_visible",
            "Signal visible",
            None,
            summary.first_signal_visible_at,
            evidence.get("first_signal_visible_evidence_id")
            or evidence.get("first_signal_visible_measurement_id"),
        ),
        (
            "breakout",
            "Breakout",
            "Breakout",
            summary.first_breakout_at,
            transition_by_stage.get("Breakout"),
        ),
        (
            "mass_market",
            "Mass Market",
            "Mass Market",
            summary.first_mass_market_at,
            transition_by_stage.get("Mass Market"),
        ),
        (
            "saturated",
            "Saturation",
            "Saturated",
            summary.first_saturated_at,
            transition_by_stage.get("Saturated"),
        ),
        (
            "large_channel",
            "Large-channel entry",
            None,
            summary.first_large_channel_adoption_at,
            evidence.get("first_large_channel_measurement_id"),
        ),
    )
    milestones: list[LifecycleMilestone] = []
    for key, label, stage, occurred_at, raw_evidence in milestone_specs:
        evidence_id = (
            raw_evidence.measurement_id
            if isinstance(raw_evidence, TopicLifecycleTransition)
            else str(raw_evidence)
            if raw_evidence is not None
            else None
        )
        milestones.append(
            LifecycleMilestone(
                key=key,
                label=label,
                occurred_at=occurred_at,
                status=_milestone_status(
                    stage=stage,
                    current_stage=topic.lifecycle_stage,
                    occurred_at=occurred_at,
                ),
                evidence_id=evidence_id,
            )
        )

    latest_measurement = summary.latest_measurement_at
    current_transition = next(
        (
            transition
            for transition in reversed(transitions)
            if transition.to_stage == topic.lifecycle_stage
        ),
        None,
    )
    return SignalEarlynessResponse(
        **summary_claim.model_dump(),
        topic_id=topic.id,
        signal_id=signal.id,
        first_video_published_at=summary.first_video_published_at,
        first_discovered_at=summary.first_discovered_at,
        first_topic_formed_at=summary.first_topic_formed_at,
        first_seed_at=summary.first_seed_at,
        first_emerging_at=summary.first_emerging_at,
        first_signal_visible_at=summary.first_signal_visible_at,
        first_breakout_at=summary.first_breakout_at,
        first_mass_market_at=summary.first_mass_market_at,
        first_saturated_at=summary.first_saturated_at,
        first_declining_at=summary.first_declining_at,
        first_large_channel_adoption_at=summary.first_large_channel_adoption_at,
        latest_measurement_at=latest_measurement,
        visible_age_hours=(
            max(
                0.0,
                _hours_between(summary.first_signal_visible_at, latest_measurement) or 0.0,
            )
            if summary.first_signal_visible_at is not None and latest_measurement is not None
            else None
        ),
        time_in_current_stage_hours=(
            max(
                0.0,
                _hours_between(current_transition.transitioned_at, latest_measurement) or 0.0,
            )
            if current_transition is not None and latest_measurement is not None
            else None
        ),
        large_channel_threshold_subscribers=LARGE_CHANNEL_THRESHOLD_SUBSCRIBERS,
        backfill_version=summary.backfill_version,
        milestones=milestones,
        transitions=[
            LifecycleTransitionEvidence(
                id=transition.id,
                from_stage=transition.from_stage,
                to_stage=transition.to_stage,
                transitioned_at=_aware(transition.transitioned_at),
                measurement_id=transition.measurement_id,
                score=transition.score,
                reason_codes=transition.reason_codes_json,
                history_version=transition.history_version,
            )
            for transition in transitions
        ],
        data_mode=signal.source_kind,
    )
