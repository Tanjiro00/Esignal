from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    ContentBrief,
    DiscoveryRun,
    ProductEvent,
    ProviderHealth,
    PublishedOutcome,
    Signal,
    SignalAction,
    VideoSnapshot,
    VideoSnapshotJob,
    WorkspaceMember,
)

PRODUCT_EVENT_TYPES = {
    "signal_impression",
    "signal_open",
    "evidence_interaction",
    "signal_saved",
    "signal_dismissed",
    "signal_act",
    "signal_watch",
    "signal_skip",
    "brief_created",
    "outcome_linked",
    "outcome_successful",
    "signal_outcome_confirmed",
    "outcome_suggestion_rejected",
    "outcome_unlinked",
    "packaging_copy",
    "digest_generated",
    "onboarding_completed",
    "today_opened",
    "opportunity_card_viewed",
    "opportunity_opened",
    "why_recommended_opened",
    "evidence_opened",
    "technical_details_opened",
    "act_clicked",
    "watch_clicked",
    "skip_clicked",
    "decision_reason_selected",
    "brief_shared",
    "production_started",
    "result_opened",
    "onboarding_started",
    "onboarding_step_completed",
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def workspace_user_id(session: Session, workspace_id: str) -> str | None:
    return session.scalar(
        select(WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.role)
        .limit(1)
    )


def record_product_event(
    session: Session,
    *,
    workspace_id: str,
    event_type: str,
    event_key: str,
    signal_id: str | None = None,
    content_brief_id: str | None = None,
    outcome_id: str | None = None,
    metadata: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> ProductEvent:
    if event_type not in PRODUCT_EVENT_TYPES:
        raise ValueError(f"Unsupported product event: {event_type}")
    existing = session.scalar(select(ProductEvent).where(ProductEvent.event_key == event_key[:180]))
    if existing is not None:
        return existing
    row = ProductEvent(
        id=str(uuid4()),
        event_key=event_key[:180],
        workspace_id=workspace_id,
        user_id=workspace_user_id(session, workspace_id),
        event_type=event_type,
        signal_id=signal_id,
        content_brief_id=content_brief_id,
        outcome_id=outcome_id,
        metadata_json=metadata or {},
        occurred_at=occurred_at or datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return row


class ProductAnalyticsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def summary(self, workspace_id: str, *, days: int = 30) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        since = now - timedelta(days=days)
        event_counts: dict[str, int] = {
            event_type: int(count)
            for event_type, count in self._session.execute(
                select(ProductEvent.event_type, func.count(ProductEvent.id))
                .where(
                    ProductEvent.workspace_id == workspace_id,
                    ProductEvent.occurred_at >= since,
                )
                .group_by(ProductEvent.event_type)
            )
        }
        action_counts: dict[str, int] = {
            action: int(count)
            for action, count in self._session.execute(
                select(SignalAction.action, func.count(SignalAction.id))
                .where(
                    SignalAction.workspace_id == workspace_id,
                    SignalAction.created_at >= since,
                )
                .group_by(SignalAction.action)
            )
        }
        briefs = int(
            self._session.scalar(
                select(func.count(ContentBrief.id)).where(
                    ContentBrief.workspace_id == workspace_id,
                    ContentBrief.created_at >= since,
                )
            )
            or 0
        )
        outcomes = int(
            self._session.scalar(
                select(func.count(PublishedOutcome.id)).where(
                    PublishedOutcome.workspace_id == workspace_id,
                    PublishedOutcome.published_at >= since,
                )
            )
            or 0
        )
        successful = int(
            self._session.scalar(
                select(func.count(PublishedOutcome.id)).where(
                    PublishedOutcome.workspace_id == workspace_id,
                    PublishedOutcome.published_at >= since,
                    PublishedOutcome.success_status == "successful",
                )
            )
            or 0
        )
        impressions = int(event_counts.get("signal_impression", 0))
        opened = int(event_counts.get("signal_open", 0))
        saved = int(action_counts.get("save", 0))
        dismissed = int(action_counts.get("dismiss", 0))
        funnel = [
            {"key": "impressions", "label": "Impressions", "value": impressions},
            {"key": "opened", "label": "Opened", "value": opened},
            {"key": "saved", "label": "Saved", "value": saved},
            {"key": "dismissed", "label": "Dismissed", "value": dismissed},
            {"key": "briefs", "label": "Briefs", "value": briefs},
            {"key": "published", "label": "Published", "value": outcomes},
            {"key": "successful", "label": "Successful", "value": successful},
        ]
        trend = self._trend(workspace_id, now=now)
        ux_event_keys = (
            "today_opened",
            "opportunity_card_viewed",
            "opportunity_opened",
            "why_recommended_opened",
            "evidence_opened",
            "technical_details_opened",
            "act_clicked",
            "watch_clicked",
            "skip_clicked",
            "decision_reason_selected",
            "brief_created",
            "brief_shared",
            "production_started",
            "result_opened",
            "onboarding_started",
            "onboarding_step_completed",
            "onboarding_completed",
        )
        ux_counts = {key: int(event_counts.get(key, 0)) for key in ux_event_keys}
        ux_rows = list(
            self._session.scalars(
                select(ProductEvent).where(
                    ProductEvent.workspace_id == workspace_id,
                    ProductEvent.occurred_at >= since,
                    ProductEvent.event_type.in_(ux_event_keys),
                )
            )
        )

        def median_metadata(key: str) -> int | None:
            values = [
                int(value)
                for row in ux_rows
                if isinstance((value := row.metadata_json.get(key)), (int, float)) and value > 0
            ]
            return round(median(values)) if values else None

        return {
            "period_days": days,
            "north_star": {
                "key": "published_videos_from_signals_per_active_workspace_per_month",
                "value": outcomes,
                "successful_value": successful,
                "label": "Published from signals / active workspace / month",
            },
            "funnel": funnel,
            "open_rate": round(opened / impressions * 100, 1) if impressions else 0,
            "trend": trend,
            "freshness": self._freshness(now),
            "recent_activity": self._recent_activity(workspace_id),
            "ux": {
                "events": ux_counts,
                "decision_funnel": [
                    {"key": "cards_viewed", "value": ux_counts["opportunity_card_viewed"]},
                    {"key": "opened", "value": ux_counts["opportunity_opened"]},
                    {
                        "key": "decided",
                        "value": (
                            ux_counts["act_clicked"]
                            + ux_counts["watch_clicked"]
                            + ux_counts["skip_clicked"]
                        ),
                    },
                    {"key": "briefs", "value": ux_counts["brief_created"]},
                    {"key": "production", "value": ux_counts["production_started"]},
                ],
                "onboarding_funnel": [
                    {"key": "started", "value": ux_counts["onboarding_started"]},
                    {
                        "key": "steps_completed",
                        "value": ux_counts["onboarding_step_completed"],
                    },
                    {"key": "completed", "value": ux_counts["onboarding_completed"]},
                ],
                "timing": {
                    "median_time_to_opportunity_ms": median_metadata("time_from_today_ms"),
                    "median_time_to_decision_ms": median_metadata("decision_elapsed_ms"),
                    "median_time_to_brief_ms": median_metadata("decision_elapsed_ms"),
                    "median_onboarding_elapsed_ms": median_metadata("onboarding_elapsed_ms"),
                },
            },
        }

    def _trend(
        self,
        workspace_id: str,
        *,
        now: datetime,
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for offset in range(6, -1, -1):
            day = (now - timedelta(days=offset)).date()
            start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
            end = start + timedelta(days=1)
            impressions = int(
                self._session.scalar(
                    select(func.count(ProductEvent.id)).where(
                        ProductEvent.workspace_id == workspace_id,
                        ProductEvent.event_type == "signal_impression",
                        ProductEvent.occurred_at >= start,
                        ProductEvent.occurred_at < end,
                    )
                )
                or 0
            )
            opened = int(
                self._session.scalar(
                    select(func.count(ProductEvent.id)).where(
                        ProductEvent.workspace_id == workspace_id,
                        ProductEvent.event_type == "signal_open",
                        ProductEvent.occurred_at >= start,
                        ProductEvent.occurred_at < end,
                    )
                )
                or 0
            )
            published = int(
                self._session.scalar(
                    select(func.count(PublishedOutcome.id)).where(
                        PublishedOutcome.workspace_id == workspace_id,
                        PublishedOutcome.published_at >= start,
                        PublishedOutcome.published_at < end,
                    )
                )
                or 0
            )
            result.append(
                {
                    "date": day.isoformat(),
                    "impressions": impressions,
                    "opened": opened,
                    "published": published,
                }
            )
        return result

    def _freshness(self, now: datetime) -> dict[str, object]:
        latest_signal = self._session.scalar(select(func.max(Signal.generated_at)))
        latest_snapshot = self._session.scalar(select(func.max(VideoSnapshot.observed_at)))
        latest_discovery = self._session.scalar(select(func.max(DiscoveryRun.completed_at)))
        stale_signals = int(
            self._session.scalar(
                select(func.count(Signal.id)).where(
                    Signal.status == "active",
                    Signal.expires_at < now,
                )
            )
            or 0
        )
        dead_letters = int(
            self._session.scalar(
                select(func.count(VideoSnapshotJob.id)).where(VideoSnapshotJob.status == "failed")
            )
            or 0
        )
        provider_rows = list(self._session.scalars(select(ProviderHealth)))
        healthy = sum(
            row.enabled and row.circuit_state != "open" and row.consecutive_failures < 3
            for row in provider_rows
        )
        return {
            "last_signal_at": latest_signal,
            "last_snapshot_at": latest_snapshot,
            "last_discovery_at": latest_discovery,
            "stale_signals": stale_signals,
            "dead_letters": dead_letters,
            "healthy_providers": healthy,
            "provider_count": len(provider_rows),
        }

    def _recent_activity(self, workspace_id: str) -> list[dict[str, object]]:
        rows = list(
            self._session.scalars(
                select(ProductEvent)
                .where(ProductEvent.workspace_id == workspace_id)
                .order_by(desc(ProductEvent.occurred_at))
                .limit(12)
            )
        )
        return [
            {
                "id": row.id,
                "event_type": row.event_type,
                "signal_id": row.signal_id,
                "content_brief_id": row.content_brief_id,
                "outcome_id": row.outcome_id,
                "metadata": row.metadata_json,
                "occurred_at": _aware(row.occurred_at),
            }
            for row in rows
        ]
