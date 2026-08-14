from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.config import Settings, get_settings
from apps.api.models import (
    DigestRun,
    DigestSubscription,
    Workspace,
    WorkspaceMember,
)
from apps.api.product_analytics import record_product_event
from apps.api.reviews import signal_is_visible
from apps.api.services import get_signal_detail, list_signals, resolve_signal_source

DIGEST_VERSION = "evidence-digest-v4-insight-gate"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _next_run(now: datetime, cadence: str) -> datetime:
    days = {"daily": 1, "twice_weekly": 3, "weekly": 7}.get(cadence, 7)
    return now + timedelta(days=days)


def _legacy_decision(score: float, fit: float, saturation: float) -> str:
    if score >= 70 and fit >= 55 and saturation < 75:
        return "Act"
    if score >= 50 and saturation < 90:
        return "Watch"
    return "Skip"


def _excerpt(value: str, *, limit: int = 220) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


class DigestService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    def ensure_subscription(self, workspace_id: str) -> DigestSubscription:
        row = self._session.get(DigestSubscription, workspace_id)
        if row is not None:
            return row
        user_id = self._session.scalar(
            select(WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .limit(1)
        )
        if user_id is None:
            raise RuntimeError("Workspace has no member for digest delivery")
        workspace = self._session.get(Workspace, workspace_id)
        now = datetime.now(tz=UTC)
        row = DigestSubscription(
            workspace_id=workspace_id,
            user_id=user_id,
            cadence="twice_weekly",
            delivery_channel="in_app",
            destination=f"{workspace.name if workspace else 'Workspace'} team",
            enabled=True,
            next_run_at=_next_run(now, "twice_weekly"),
            last_generated_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update_subscription(
        self,
        workspace_id: str,
        *,
        cadence: str,
        delivery_channel: str,
        destination: str,
        enabled: bool,
    ) -> DigestSubscription:
        row = self.ensure_subscription(workspace_id)
        now = datetime.now(tz=UTC)
        row.cadence = cadence
        row.delivery_channel = delivery_channel
        row.destination = destination
        row.enabled = enabled
        row.next_run_at = _next_run(now, cadence)
        row.updated_at = now
        self._session.commit()
        return row

    def latest(self, workspace_id: str) -> DigestRun | None:
        return self._session.scalar(
            select(DigestRun)
            .where(DigestRun.workspace_id == workspace_id)
            .order_by(desc(DigestRun.generated_at))
        )

    def ensure_latest(self, workspace_id: str) -> DigestRun:
        latest = self.latest(workspace_id)
        if (
            latest is not None
            and self._settings.feature_decision_experience
            and (
                latest.content_json.get("version") != DIGEST_VERSION
                or any(
                    not item.get("decision_card") for item in latest.content_json.get("items", [])
                )
            )
        ):
            latest = None
        if latest is not None and self._settings.feature_signal_review_queue:
            signal_ids = [
                str(item.get("signal_id"))
                for item in latest.content_json.get("items", [])
                if item.get("signal_id")
            ]
            if any(
                not signal_is_visible(self._session, workspace_id, signal_id)
                for signal_id in signal_ids
            ):
                latest = None
        if latest is not None:
            return latest
        return self.generate(workspace_id)

    def generate(self, workspace_id: str) -> DigestRun:
        subscription = self.ensure_subscription(workspace_id)
        source, _modes = resolve_signal_source(
            self._session,
            workspace_id,
            "auto",
            require_review_approval=self._settings.feature_signal_review_queue,
        )
        signals = list_signals(
            self._session,
            workspace_id,
            source_kind=source,
            include_earlyness=self._settings.feature_earlyness_timeline,
            include_decision=self._settings.feature_decision_experience,
            use_feasibility_v2=(self._settings.feature_channel_profile_feasibility_v2),
            require_review_approval=self._settings.feature_signal_review_queue,
        )
        if self._settings.feature_decision_experience:
            signals = [
                signal
                for signal in signals
                if signal.decision_card is not None and signal.decision_card.release_ready
            ]
        ranked = sorted(
            signals,
            key=lambda item: item.score * 0.65 + item.channel_fit * 0.35,
            reverse=True,
        )[:3]
        items: list[dict[str, object]] = []
        for rank, signal in enumerate(ranked, start=1):
            detail = get_signal_detail(
                self._session,
                workspace_id,
                signal.id,
                include_earlyness=self._settings.feature_earlyness_timeline,
                include_decision=self._settings.feature_decision_experience,
                use_feasibility_v2=(self._settings.feature_channel_profile_feasibility_v2),
                require_review_approval=self._settings.feature_signal_review_queue,
            )
            angle = detail.content_angles[0] if detail.content_angles else {}
            demand = signal.strongest_demand
            items.append(
                {
                    "rank": rank,
                    "signal_id": signal.id,
                    "topic_label": signal.topic_label,
                    "lifecycle_stage": signal.lifecycle_stage,
                    "score": signal.score,
                    "confidence": signal.confidence,
                    "channel_fit": signal.channel_fit,
                    "suggested_decision": (
                        detail.decision_card.decision
                        if detail.decision_card is not None
                        else _legacy_decision(
                            signal.score,
                            signal.channel_fit,
                            float(detail.saturation.get("score", 0)),
                        )
                    ),
                    "decision_card": (
                        detail.decision_card.model_dump(mode="json")
                        if detail.decision_card is not None
                        else None
                    ),
                    "why_emerging": detail.why_emerging[:3],
                    "evidence_videos": [
                        {
                            "id": video.id,
                            "title": video.title,
                            "channel": video.channel,
                            "channel_subscribers": video.channel_subscribers,
                            "views": video.views,
                            "outlier_ratio": video.outlier_ratio,
                            "canonical_url": video.canonical_url,
                        }
                        for video in detail.evidence_videos[:3]
                    ],
                    "demand": {
                        "available": demand.available,
                        "label": demand.label,
                        "question": _excerpt(demand.question),
                        "comment_count": demand.comment_count,
                        "distinct_channels": demand.distinct_channels,
                    },
                    "saturation": detail.saturation,
                    "opportunity_window": {
                        "start": signal.opportunity_window.start.isoformat(),
                        "end": signal.opportunity_window.end.isoformat(),
                        "label": signal.opportunity_window.label,
                    },
                    "recommended_angle": angle,
                    "data_mode": signal.data_mode,
                }
            )
        now = datetime.now(tz=UTC)
        workspace = self._session.get(Workspace, workspace_id)
        row = DigestRun(
            id=str(uuid4()),
            workspace_id=workspace_id,
            period_start=now - timedelta(days=7),
            period_end=now,
            status="delivered" if subscription.delivery_channel == "in_app" else "generated",
            content_json={
                "version": DIGEST_VERSION,
                "workspace_name": workspace.name if workspace else "Workspace",
                "source_mode": source,
                "items": items,
            },
            generated_at=now,
            delivered_at=now if subscription.delivery_channel == "in_app" else None,
        )
        self._session.add(row)
        subscription.last_generated_at = now
        subscription.next_run_at = _next_run(now, subscription.cadence)
        subscription.updated_at = now
        record_product_event(
            self._session,
            workspace_id=workspace_id,
            event_type="digest_generated",
            event_key=f"digest:{row.id}",
            metadata={"digest_id": row.id, "signal_count": len(items)},
            occurred_at=now,
        )
        self._session.commit()
        return row

    def generate_due(self, *, limit: int = 20) -> list[DigestRun]:
        now = datetime.now(tz=UTC)
        subscriptions = list(
            self._session.scalars(
                select(DigestSubscription)
                .where(
                    DigestSubscription.enabled.is_(True),
                    DigestSubscription.next_run_at <= now,
                )
                .order_by(DigestSubscription.next_run_at)
                .limit(limit)
            )
        )
        return [self.generate(row.workspace_id) for row in subscriptions]
