from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models import (
    DemandCluster,
    EvaluationLabel,
    Signal,
    SignalAction,
    Topic,
    TopicSnapshot,
    TopicVideoMembership,
    WorkspaceSignalScore,
)

LABEL_VERSION = "manual-topic-evaluation-v1"
FEEDBACK_VERSION = "decision-feedback-v1"

PRIMARY_LABELS = (
    "true_early_signal",
    "true_but_late",
    "weak_signal",
    "false_signal",
    "too_broad",
    "too_narrow",
    "duplicate",
    "saturated",
    "declining",
    "insufficient_evidence",
)

ADDITIONAL_LABELS = (
    "demand_relevant",
    "demand_irrelevant",
    "opportunity_actionable",
    "opportunity_generic",
    "fit_correct",
    "fit_incorrect",
)

DECISION_REASONS: dict[str, tuple[str, ...]] = {
    "act": (
        "strong_fit",
        "great_timing",
        "clear_angle",
        "already_planned",
        "high_audience_interest",
        "other",
    ),
    "watch": (
        "need_more_evidence",
        "too_early",
        "waiting_for_product_release",
        "production_capacity",
        "unclear_angle",
        "other",
    ),
    "skip": (
        "not_relevant",
        "too_late",
        "too_broad",
        "too_narrow",
        "weak_evidence",
        "brand_mismatch",
        "already_covered",
        "production_too_expensive",
        "audience_not_interested",
        "bad_timing",
        "other",
    ),
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def validate_decision_reason(action: str, reason: str | None) -> str:
    normalized = (reason or "").strip()
    if not normalized:
        return ""
    allowed = DECISION_REASONS.get(action)
    if allowed is not None and normalized not in allowed:
        raise ValueError(f"Unsupported {action} reason: {normalized}")
    return normalized


def build_label_evidence_snapshot(
    session: Session,
    *,
    topic_id: str,
    as_of: datetime,
) -> dict[str, Any]:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise ValueError("Topic not found")
    cutoff = _aware(as_of)
    latest = session.scalar(
        select(TopicSnapshot)
        .where(
            TopicSnapshot.topic_id == topic_id,
            TopicSnapshot.observed_at <= cutoff,
        )
        .order_by(desc(TopicSnapshot.observed_at), desc(TopicSnapshot.id))
        .limit(1)
    )
    memberships = list(
        session.scalars(
            select(TopicVideoMembership)
            .where(
                TopicVideoMembership.topic_id == topic_id,
                TopicVideoMembership.assigned_at <= cutoff,
            )
            .order_by(TopicVideoMembership.video_id)
        )
    )
    signal = session.scalar(
        select(Signal)
        .where(
            Signal.topic_id == topic_id,
            Signal.generated_at <= cutoff,
        )
        .order_by(desc(Signal.generated_at), desc(Signal.id))
        .limit(1)
    )
    demand = list(
        session.scalars(
            select(DemandCluster)
            .where(
                DemandCluster.topic_id == topic_id,
                DemandCluster.first_observed_at <= cutoff,
            )
            .order_by(DemandCluster.id)
        )
    )
    scores = (
        list(
            session.scalars(
                select(WorkspaceSignalScore)
                .where(
                    WorkspaceSignalScore.signal_id == signal.id,
                    WorkspaceSignalScore.calculated_at <= cutoff,
                )
                .order_by(
                    desc(WorkspaceSignalScore.channel_fit_score),
                    WorkspaceSignalScore.workspace_id,
                )
            )
        )
        if signal is not None
        else []
    )
    return {
        "topic": {
            "id": topic.id,
            "label": topic.canonical_label,
            "identity": topic.identity_json,
            "specificity_score": topic.specificity_score,
            "thesis_support_ratio": topic.thesis_support_ratio,
            "lifecycle_stage": topic.lifecycle_stage,
            "clustering_version": topic.clustering_version,
        },
        "as_of": cutoff.isoformat(),
        "latest_measurement": (
            {
                "id": latest.id,
                "observed_at": _aware(latest.observed_at).isoformat(),
                "video_count_24h": latest.video_count_24h,
                "video_count_72h": latest.video_count_72h,
                "distinct_channels_72h": latest.distinct_channels_72h,
                "aggregate_view_velocity": latest.aggregate_view_velocity,
                "demand_score": latest.demand_score,
                "saturation_score": latest.saturation_score,
                "fragility_score": latest.fragility_score,
                "components": latest.component_json,
            }
            if latest is not None
            else None
        ),
        "evidence_memberships": [
            {
                "video_id": row.video_id,
                "membership_score": row.membership_score,
                "evidence_role": row.evidence_role,
                "assigned_at": _aware(row.assigned_at).isoformat(),
            }
            for row in memberships
        ],
        "demand_clusters": [
            {
                "id": row.id,
                "score": row.demand_score,
                "evidence_strength": row.evidence_strength,
                "visibility_status": row.visibility_status,
                "model_version": row.model_version,
            }
            for row in demand
        ],
        "signal": (
            {
                "id": signal.id,
                "score": signal.score,
                "confidence": signal.confidence,
                "stage": signal.lifecycle_stage,
                "generated_at": _aware(signal.generated_at).isoformat(),
                "components": signal.component_json,
                "evidence_version": signal.evidence_version,
            }
            if signal is not None
            else None
        ),
        "workspace_scores": [
            {
                "workspace_id": row.workspace_id,
                "channel_fit_score": row.channel_fit_score,
                "fit_version": row.fit_version,
                "calculated_at": _aware(row.calculated_at).isoformat(),
                "opportunities": row.recommended_angle_json,
            }
            for row in scores
        ],
        "point_in_time": True,
        "future_measurements_included": False,
    }


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def build_evaluation_report(labels: list[EvaluationLabel]) -> dict[str, Any]:
    primary = Counter(row.label for row in labels)
    additional = Counter(label for row in labels for label in row.additional_labels_json)
    visible = [row for row in labels if row.evidence_snapshot_json.get("signal") is not None]
    true_early_visible = sum(row.label == "true_early_signal" for row in visible)
    false_positive_labels = {
        "weak_signal",
        "false_signal",
        "too_broad",
        "too_narrow",
        "duplicate",
        "saturated",
        "declining",
        "insufficient_evidence",
    }
    false_visible = sum(row.label in false_positive_labels for row in visible)
    actual_early = primary["true_early_signal"]
    top_three = [
        row for row in visible if int(row.evidence_snapshot_json.get("signal_rank", 99)) <= 3
    ]
    top_three_correct = sum(row.label == "true_early_signal" for row in top_three)
    split_errors = primary["too_broad"] + primary["too_narrow"] + primary["duplicate"]
    demand_total = additional["demand_relevant"] + additional["demand_irrelevant"]
    opportunity_total = additional["opportunity_actionable"] + additional["opportunity_generic"]
    return {
        "reviewed_topics": len(labels),
        "label_counts": dict(sorted(primary.items())),
        "additional_label_counts": dict(sorted(additional.items())),
        "metrics": {
            "precision": _percent(true_early_visible, len(visible)),
            "recall_reviewed_candidate_universe": _percent(
                true_early_visible,
                actual_early,
            ),
            "precision_at_3": _percent(top_three_correct, len(top_three)),
            "late_signal_rate": _percent(primary["true_but_late"], len(visible)),
            "false_positive_rate": _percent(false_visible, len(visible)),
            "topic_split_error_rate": _percent(split_errors, len(labels)),
            "demand_relevance_precision": _percent(
                additional["demand_relevant"],
                demand_total,
            ),
            "opportunity_actionability_rate": _percent(
                additional["opportunity_actionable"],
                opportunity_total,
            ),
        },
        "versions": {"label": LABEL_VERSION},
        "production_weights_changed": False,
    }


def evaluation_export_records(labels: list[EvaluationLabel]) -> list[dict[str, Any]]:
    return [
        {
            "topic_id": row.topic_id,
            "signal_id": row.signal_id,
            "workspace_id": row.workspace_id,
            "as_of": _aware(row.as_of).isoformat(),
            "label": row.label,
            "additional_labels": row.additional_labels_json,
            "reviewer": row.reviewer_id,
            "evidence_snapshot": row.evidence_snapshot_json,
            "notes": row.notes,
            "model_versions": row.model_versions_json,
            "label_version": row.label_version,
        }
        for row in sorted(labels, key=lambda item: (_aware(item.as_of), item.topic_id, item.id))
    ]


def feedback_export_records(actions: list[SignalAction]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "signal_id": row.signal_id,
            "user_id": row.user_id,
            "action": row.action,
            "reason": row.reason or "",
            "comment": row.comment or "",
            "opportunity_id": row.opportunity_id or "",
            "feedback_version": row.feedback_version,
            "created_at": _aware(row.created_at).isoformat(),
        }
        for row in sorted(actions, key=lambda item: (_aware(item.created_at), item.id))
    ]


def records_as_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
    ) + ("\n" if records else "")


def records_as_csv(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    stream = io.StringIO()
    fieldnames = list(records[0])
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in record.items()
            }
        )
    return stream.getvalue()
