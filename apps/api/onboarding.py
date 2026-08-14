from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    ChannelProfile,
    DigestRun,
    DigestSubscription,
    DiscoveryQueryRecord,
    ProviderHealth,
    Workspace,
    WorkspaceChannel,
    WorkspaceDiscoveryQuery,
    WorkspaceOnboarding,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.product_analytics import record_product_event
from apps.worker.digests import DigestService

STEPS = (
    ("workspace", "Workspace", "/onboarding"),
    ("owned_channel", "Owned channel", "/onboarding"),
    ("channel_profile", "Channel profile", "/settings"),
    ("topic_universe", "Topic universe", "/admin/providers"),
    ("digest", "Digest", "/digest"),
)
PROFILE_CONFIRMATION_FIELDS = {
    "core_topics",
    "exclusions",
    "production_days_min",
    "production_days_max",
    "team_size",
    "research_capacity_hours",
    "experiment_level",
    "evergreen_trend_balance",
    "risk_tolerance",
}
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}")
REFERENCE_STOPWORDS = {
    "about",
    "channel",
    "from",
    "have",
    "into",
    "more",
    "that",
    "their",
    "this",
    "video",
    "with",
    "your",
}
REFERENCE_GENERIC_ANCHORS = {
    "channel",
    "content",
    "tech",
    "technology",
    "video",
    "videos",
    "youtube",
}
REFERENCE_AI_TECH_TOKENS = {
    "ai",
    "agent",
    "agents",
    "anthropic",
    "artificial",
    "automation",
    "chatgpt",
    "claude",
    "code",
    "coder",
    "coding",
    "developer",
    "developers",
    "engineering",
    "gpu",
    "intelligence",
    "llm",
    "llms",
    "machine",
    "model",
    "models",
    "nvidia",
    "openai",
    "programming",
    "saas",
    "software",
    "startup",
    "startups",
}
REFERENCE_CREATOR_TOKENS = {
    "build",
    "builder",
    "developer",
    "engineer",
    "explained",
    "guide",
    "learn",
    "practical",
    "tutorial",
    "workflow",
    "workflows",
}
REFERENCE_BROADCASTER_TOKENS = {
    "broadcast",
    "breaking",
    "finance",
    "media",
    "network",
    "politics",
    "sports",
    "television",
}


def slugify(value: str) -> str:
    return SLUG_PATTERN.sub("-", value.lower()).strip("-")[:150] or "workspace"


def _reference_tokens(value: str) -> set[str]:
    return {
        token for token in TOKEN_PATTERN.findall(value.lower()) if token not in REFERENCE_STOPWORDS
    }


def _reference_rank(
    channel: YoutubeChannel,
    *,
    anchors: set[str],
    recent_titles: list[str],
) -> tuple[float, int, int, int] | None:
    """Rank evidence-rich creator channels without falling back to popularity."""

    if len(recent_titles) < 3:
        return None
    title_tokens = [_reference_tokens(title) for title in recent_titles]
    domain_title_count = sum(bool(tokens & REFERENCE_AI_TECH_TOKENS) for tokens in title_tokens)
    minimum_domain_titles = max(3, ceil(len(title_tokens) * 0.45))
    if domain_title_count < minimum_domain_titles:
        return None

    descriptor_tokens = _reference_tokens(f"{channel.title} {channel.description}")
    evidence_tokens = descriptor_tokens | set().union(*title_tokens)
    meaningful_anchors = anchors - REFERENCE_GENERIC_ANCHORS
    anchor_overlap = len(meaningful_anchors & evidence_tokens)
    ai_tech_overlap = len(REFERENCE_AI_TECH_TOKENS & evidence_tokens)
    creator_signals = len(REFERENCE_CREATOR_TOKENS & evidence_tokens)
    broadcaster_penalty = len(REFERENCE_BROADCASTER_TOKENS & descriptor_tokens)
    domain_ratio = domain_title_count / len(title_tokens)
    relevance = (
        anchor_overlap * 12
        + ai_tech_overlap
        + creator_signals * 2
        + domain_ratio * 20
        - broadcaster_penalty * 8
    )
    if relevance < 20:
        return None
    return (
        relevance,
        creator_signals,
        channel.subscriber_count,
        channel.video_count,
    )


def _profile_is_ready(profile: ChannelProfile | None, *, demo_mode: bool) -> bool:
    if profile is None:
        return False
    if demo_mode:
        return True
    overrides = set(profile.explicit_overrides_json)
    if PROFILE_CONFIRMATION_FIELDS.issubset(overrides):
        return True
    return bool((profile.inference_json or {}).get("discovery_plan"))


class OnboardingService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def ensure(self, workspace_id: str) -> WorkspaceOnboarding:
        row = self._session.get(WorkspaceOnboarding, workspace_id)
        if row is not None:
            return row
        now = datetime.now(tz=UTC)
        row = WorkspaceOnboarding(
            workspace_id=workspace_id,
            status="in_progress",
            current_step=1,
            completed_steps_json=[],
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def status(self, workspace_id: str) -> dict[str, object]:
        workspace = self._session.get(Workspace, workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")
        row = self.ensure(workspace_id)
        owned = self._session.execute(
            select(WorkspaceChannel, YoutubeChannel)
            .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
            .where(
                WorkspaceChannel.workspace_id == workspace_id,
                WorkspaceChannel.relationship == "owned",
                WorkspaceChannel.active.is_(True),
            )
            .order_by(WorkspaceChannel.priority)
            .limit(1)
        ).first()
        reference_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(WorkspaceChannel)
                .where(
                    WorkspaceChannel.workspace_id == workspace_id,
                    WorkspaceChannel.relationship.in_(("competitor", "reference")),
                    WorkspaceChannel.active.is_(True),
                )
            )
            or 0
        )
        workspace_query_count = int(
            self._session.scalar(
                select(func.count(WorkspaceDiscoveryQuery.query_id)).where(
                    WorkspaceDiscoveryQuery.workspace_id == workspace_id,
                    WorkspaceDiscoveryQuery.active.is_(True),
                )
            )
            or 0
        )
        global_query_count = int(
            self._session.scalar(
                select(func.count(DiscoveryQueryRecord.id)).where(
                    DiscoveryQueryRecord.active.is_(True)
                )
            )
            or 0
        )
        query_count = workspace_query_count or global_query_count
        subscription = self._session.get(DigestSubscription, workspace_id)
        digest_count = int(
            self._session.scalar(
                select(func.count(DigestRun.id)).where(DigestRun.workspace_id == workspace_id)
            )
            or 0
        )
        profile = (
            self._session.get(ChannelProfile, (workspace_id, owned[0].channel_id))
            if owned
            else None
        )
        profile_confirmed = _profile_is_ready(profile, demo_mode=self._settings.demo_mode)
        completion = {
            "workspace": bool(workspace.name and workspace.timezone),
            "owned_channel": owned is not None,
            "channel_profile": profile_confirmed,
            "topic_universe": query_count >= 3 or self._settings.demo_mode,
            "digest": bool(subscription and subscription.enabled),
        }
        completed = [key for key, is_complete in completion.items() if is_complete]
        first_incomplete = next(
            (
                index
                for index, (key, _label, _href) in enumerate(STEPS, start=1)
                if not completion[key]
            ),
            len(STEPS),
        )
        row.completed_steps_json = completed
        row.current_step = first_incomplete
        row.status = "completed" if len(completed) == len(STEPS) else "in_progress"
        row.completed_at = row.completed_at or (
            datetime.now(tz=UTC) if row.status == "completed" else None
        )
        row.updated_at = datetime.now(tz=UTC)
        channel_preview = self._channel_preview(owned[1], workspace_id) if owned else None
        provider_rows = list(self._session.scalars(select(ProviderHealth)))
        provider_ready = self._settings.demo_mode or any(
            item.enabled and item.circuit_state != "open" for item in provider_rows
        )
        readiness = [
            {
                "key": "provider_access",
                "label": "Provider access",
                "complete": provider_ready,
                "detail": (
                    "Demo providers ready"
                    if self._settings.demo_mode
                    else f"{sum(item.enabled for item in provider_rows)} providers enabled"
                ),
            },
            {
                "key": "workspace_profile",
                "label": "Channel profile",
                "complete": profile_confirmed,
                "detail": (
                    "Strategy and production limits confirmed"
                    if profile_confirmed
                    else "Review strategy and production limits"
                ),
            },
            {
                "key": "discovery_queries",
                "label": "Discovery queries",
                "complete": query_count >= 3 or self._settings.demo_mode,
                "detail": (
                    "Demo query universe ready"
                    if self._settings.demo_mode and query_count < 3
                    else f"{query_count} active queries"
                ),
            },
            {
                "key": "first_digest",
                "label": "First digest",
                "complete": digest_count > 0,
                "detail": f"{digest_count} generated",
            },
        ]
        self._session.commit()
        return {
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "workspace_slug": workspace.slug,
            "timezone": workspace.timezone,
            "status": row.status,
            "current_step": row.current_step,
            "completed_steps": completed,
            "progress_percent": round(len(completed) / len(STEPS) * 100),
            "steps": [
                {
                    "key": key,
                    "label": label,
                    "href": href,
                    "complete": completion[key],
                    "active": index == first_incomplete,
                }
                for index, (key, label, href) in enumerate(STEPS, start=1)
            ],
            "owned_channel": channel_preview,
            "reference_channel_count": reference_count,
            "active_query_count": query_count,
            "digest_enabled": bool(subscription and subscription.enabled),
            "readiness": readiness,
        }

    def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str,
        timezone: str,
    ) -> dict[str, object]:
        workspace = self._session.get(Workspace, workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")
        workspace.name = name
        workspace.timezone = timezone
        workspace.slug = slugify(name)
        self._session.commit()
        return self.status(workspace_id)

    def complete(self, workspace_id: str) -> dict[str, object]:
        status = self.status(workspace_id)
        if status["progress_percent"] != 100:
            raise ValueError("Complete all onboarding steps first")
        row = self.ensure(workspace_id)
        now = datetime.now(tz=UTC)
        row.status = "completed"
        row.completed_at = row.completed_at or now
        row.updated_at = now
        record_product_event(
            self._session,
            workspace_id=workspace_id,
            event_type="onboarding_completed",
            event_key=f"onboarding:{workspace_id}:completed",
            metadata={"completed_steps": row.completed_steps_json},
            occurred_at=now,
        )
        self._session.commit()
        return self.status(workspace_id)

    def prepare_digest(self, workspace_id: str) -> dict[str, object]:
        service = DigestService(self._session, self._settings)
        service.ensure_subscription(workspace_id)
        service.ensure_latest(workspace_id)
        self._session.commit()
        return self.status(workspace_id)

    def seed_reference_channels(self, workspace_id: str, *, limit: int = 5) -> int:
        owned = self._session.execute(
            select(WorkspaceChannel, YoutubeChannel)
            .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
            .where(
                WorkspaceChannel.workspace_id == workspace_id,
                WorkspaceChannel.relationship == "owned",
                WorkspaceChannel.active.is_(True),
            )
            .limit(1)
        ).first()
        if owned is None:
            return 0
        profile = self._session.get(ChannelProfile, (workspace_id, owned[0].channel_id))
        anchor_text = " ".join(
            (
                owned[1].title,
                owned[1].description,
                " ".join(profile.core_topics_json if profile else []),
                " ".join(profile.topic_keywords_json if profile else []),
            )
        )
        anchors = _reference_tokens(anchor_text)
        existing_ids = set(
            self._session.scalars(
                select(WorkspaceChannel.channel_id).where(
                    WorkspaceChannel.workspace_id == workspace_id
                )
            )
        )
        candidates = list(
            self._session.scalars(
                select(YoutubeChannel)
                .where(
                    YoutubeChannel.id.not_in(existing_ids),
                    ~YoutubeChannel.youtube_channel_id.startswith("UCESDEMO"),
                    YoutubeChannel.default_language.like("en%"),
                )
                .order_by(YoutubeChannel.subscriber_count.desc())
                .limit(250)
            )
        )
        recent_titles: defaultdict[str, list[str]] = defaultdict(list)
        candidate_ids = [channel.id for channel in candidates]
        if candidate_ids:
            for channel_id, title in self._session.execute(
                select(YoutubeVideo.channel_id, YoutubeVideo.title)
                .where(YoutubeVideo.channel_id.in_(candidate_ids))
                .order_by(YoutubeVideo.channel_id, YoutubeVideo.published_at.desc())
            ):
                if len(recent_titles[channel_id]) < 15:
                    recent_titles[channel_id].append(title)

        ranked_candidates = [
            (channel, rank)
            for channel in candidates
            if (
                rank := _reference_rank(
                    channel,
                    anchors=anchors,
                    recent_titles=recent_titles[channel.id],
                )
            )
            is not None
        ]
        ranked = [
            channel
            for channel, _rank in sorted(
                ranked_candidates,
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        selected = ranked[:limit]
        if not selected:
            return 0
        for channel in selected:
            self._session.add(
                WorkspaceChannel(
                    workspace_id=workspace_id,
                    channel_id=channel.id,
                    relationship="reference",
                    priority=1,
                    active=True,
                    last_ingested_at=None,
                    next_ingestion_at=None,
                )
            )
        self._session.commit()
        return len(selected)

    def _channel_preview(
        self,
        channel: YoutubeChannel,
        workspace_id: str,
    ) -> dict[str, object]:
        videos = list(
            self._session.scalars(
                select(YoutubeVideo)
                .where(YoutubeVideo.channel_id == channel.id)
                .order_by(YoutubeVideo.published_at.desc())
                .limit(5)
            )
        )
        profile = self._session.get(ChannelProfile, (workspace_id, channel.id))
        return {
            "channel_id": channel.id,
            "youtube_channel_id": channel.youtube_channel_id,
            "title": channel.title,
            "canonical_url": channel.canonical_url,
            "subscriber_count": channel.subscriber_count,
            "video_count": channel.video_count,
            "recent_uploads": [
                {
                    "id": video.id,
                    "title": video.title,
                    "published_at": video.published_at,
                    "duration_seconds": video.duration_seconds,
                }
                for video in videos
            ],
            "topic_keywords": profile.topic_keywords_json[:10] if profile else [],
            "normal_duration_min_seconds": (profile.normal_duration_min_seconds if profile else 0),
            "normal_duration_max_seconds": (profile.normal_duration_max_seconds if profile else 0),
            "profile_version": profile.profile_version if profile else None,
            "profile_confirmed": bool(
                _profile_is_ready(profile, demo_mode=self._settings.demo_mode)
            ),
            "core_topics": profile.core_topics_json[:8] if profile else [],
            "exclusions": profile.exclusions_json[:8] if profile else [],
            "production_days_min": profile.production_days_min if profile else 0,
            "production_days_max": profile.production_days_max if profile else 0,
            "team_size": profile.team_size if profile else 0,
            "research_capacity_hours": profile.research_capacity_hours if profile else 0,
            "experiment_level": profile.experiment_level if profile else "",
            "evergreen_trend_balance": (profile.evergreen_trend_balance if profile else 0.5),
            "risk_tolerance": profile.risk_tolerance if profile else "",
        }
