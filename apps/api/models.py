from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now().astimezone()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(512))
    password_version: Mapped[str] = mapped_column(String(32), default="pbkdf2-sha256-v1")
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_expires", "user_id", "expires_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthLoginAttempt(Base):
    __tablename__ = "auth_login_attempts"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    plan: Mapped[str] = mapped_column(String(40), default="private_beta")
    timezone: Mapped[str] = mapped_column(String(80), default="America/Los_Angeles")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), default="owner")


class WorkspaceOnboarding(Base):
    __tablename__ = "workspace_onboarding"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), default="in_progress", index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    completed_steps_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class YoutubeChannel(Base):
    __tablename__ = "youtube_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(8), default="US")
    default_language: Mapped[str] = mapped_column(String(16), default="en")
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommentEmbedding(Base):
    """Comment vectors in the same space as video vectors.

    Sharing the space is what makes "does a video already answer this?" a
    nearest-neighbour lookup rather than a keyword match.
    """

    __tablename__ = "comment_embeddings"

    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), primary_key=True
    )
    embedding_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(80))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector_json: Mapped[list[float]] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DemandItem(Base):
    """A group of viewers asking the same unanswered question.

    This is the unit the product sells, so it is computed by a job and stored,
    not derived per request. Its evidence is real comments, linked below.
    """

    __tablename__ = "demand_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_key: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    question: Mapped[str] = mapped_column(Text)
    need: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(String(200), default="")
    distinct_askers: Mapped[int] = mapped_column(Integer)
    distinct_videos: Mapped[int] = mapped_column(Integer)
    distinct_channels: Mapped[int] = mapped_column(Integer)
    total_likes: Mapped[int] = mapped_column(Integer)
    first_asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mean_similarity: Mapped[float] = mapped_column(Float)
    volume_score: Mapped[float] = mapped_column(Float)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_video_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    anchors_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    centroid_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verifier_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemandItemComment(Base):
    __tablename__ = "demand_item_comments"

    demand_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("demand_items.id", ondelete="CASCADE"), primary_key=True
    )
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), primary_key=True
    )
    is_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class PanelMembership(Base):
    """The observed population, recorded as dated facts.

    Rows are append-only: a channel leaving sets ``left_at`` and keeps its
    original ``joined_at``, so the panel can be reconstructed exactly as it
    stood on any past date. That reconstruction is what makes a historical
    measurement honest — see `es_ingest/panel.py` for the rules.
    """

    __tablename__ = "panel_membership"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_channels.id"))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(40))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    owner_workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=True
    )
    niche_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkspaceChannel(Base):
    __tablename__ = "workspace_channels"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_channels.id"), primary_key=True
    )
    relationship: Mapped[str] = mapped_column(String(24))
    priority: Mapped[int] = mapped_column(Integer, default=2)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_ingestion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ChannelProfile(Base):
    __tablename__ = "channel_profiles"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_channels.id"), primary_key=True
    )
    profile_source: Mapped[str] = mapped_column(String(24), default="inferred")
    audience_description: Mapped[str] = mapped_column(Text, default="")
    geography: Mapped[str] = mapped_column(String(16), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en")
    topic_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_formats_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    creator_expertise_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    production_capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclusions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    strategic_goals_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    title_style_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    normal_duration_min_seconds: Mapped[int] = mapped_column(Integer, default=480)
    normal_duration_max_seconds: Mapped[int] = mapped_column(Integer, default=1_800)
    production_days_min: Mapped[int] = mapped_column(Integer, default=3)
    production_days_max: Mapped[int] = mapped_column(Integer, default=7)
    core_topics_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    adjacent_topics_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    legacy_topics_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    successful_formats_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    upload_cadence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audience_sophistication: Mapped[str] = mapped_column(
        String(24),
        default="intermediate",
    )
    creator_authority: Mapped[str] = mapped_column(String(24), default="practitioner")
    risk_tolerance: Mapped[str] = mapped_column(String(24), default="balanced")
    team_size: Mapped[int] = mapped_column(Integer, default=1)
    research_capacity_hours: Mapped[float] = mapped_column(Float, default=8)
    filming_required: Mapped[bool] = mapped_column(Boolean, default=False)
    external_guests_required: Mapped[bool] = mapped_column(Boolean, default=False)
    editing_complexity: Mapped[str] = mapped_column(String(24), default="medium")
    access_to_products_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    experiment_level: Mapped[str] = mapped_column(String(24), default="balanced")
    evergreen_trend_balance: Mapped[float] = mapped_column(Float, default=0.5)
    weekday_publish_only: Mapped[bool] = mapped_column(Boolean, default=False)
    content_calendar_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    inference_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    explicit_overrides_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    profile_version: Mapped[str] = mapped_column(String(48), default="channel-profile-v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class YoutubeOAuthConnection(Base):
    __tablename__ = "youtube_oauth_connections"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_channels.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    scopes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    encrypted_access_token: Mapped[str] = mapped_column(Text, default="")
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_encryption_version: Mapped[str] = mapped_column(String(32), default="fernet-v1")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_error: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class YoutubeOAuthState(Base):
    __tablename__ = "youtube_oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encrypted_code_verifier: Mapped[str] = mapped_column(Text)
    redirect_after: Mapped[str] = mapped_column(String(500), default="/settings")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class YoutubeOwnedAnalytics(Base):
    __tablename__ = "youtube_owned_analytics"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "youtube_video_id",
            "period_start",
            "period_end",
            "analytics_version",
            name="uq_owned_analytics_video_period_version",
        ),
        Index(
            "ix_owned_analytics_workspace_video_period",
            "workspace_id",
            "youtube_video_id",
            "period_end",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_channels.id"), index=True
    )
    video_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("youtube_videos.id"), index=True
    )
    youtube_video_id: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    watch_time_minutes: Mapped[float] = mapped_column(Float, default=0)
    average_view_duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    average_percentage_viewed: Mapped[float] = mapped_column(Float, default=0)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float | None] = mapped_column(Float)
    traffic_source_groups_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    geography_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    content_type: Mapped[str] = mapped_column(String(24), default="long")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    analytics_version: Mapped[str] = mapped_column(String(48))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class YoutubeOAuthAuditEvent(Base):
    __tablename__ = "youtube_oauth_audit_events"
    __table_args__ = (
        Index(
            "ix_youtube_oauth_audit_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    result: Mapped[str] = mapped_column(String(24))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiscoveryQueryRecord(Base):
    __tablename__ = "discovery_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), default="AI / tech")
    priority: Mapped[int] = mapped_column(Integer, default=2)
    country: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    minimum_interval_seconds: Mapped[int] = mapped_column(Integer, default=14_400)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    historical_yield: Mapped[float] = mapped_column(Float, default=0)
    cost_per_retained_video: Mapped[float] = mapped_column(Float, default=0)
    precision_score: Mapped[float] = mapped_column(Float, default=0)
    precision_sample_size: Mapped[int] = mapped_column(Integer, default=0)
    quality_status: Mapped[str] = mapped_column(String(24), default="unmeasured")
    last_precision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkspaceDiscoveryQuery(Base):
    __tablename__ = "workspace_discovery_queries"
    __table_args__ = (
        Index("ix_workspace_discovery_queries_workspace_active", "workspace_id", "active"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discovery_queries.id"), primary_key=True
    )
    source_type: Mapped[str] = mapped_column(String(48), default="channel_profile")
    rationale: Mapped[str] = mapped_column(Text)
    evidence_refs_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class QuerySuggestion(Base):
    __tablename__ = "query_suggestions"
    __table_args__ = (
        UniqueConstraint("normalized_query", name="uq_query_suggestions_normalized"),
        Index("ix_query_suggestions_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), index=True
    )
    query: Mapped[str] = mapped_column(String(300))
    normalized_query: Mapped[str] = mapped_column(String(300), index=True)
    status: Mapped[str] = mapped_column(String(24), default="suggested", index=True)
    source_type: Mapped[str] = mapped_column(String(48), index=True)
    source_entity: Mapped[str] = mapped_column(String(240))
    source_topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("topics.id"), index=True
    )
    source_evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    anchor_terms_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    quality_reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    broadness_score: Mapped[float] = mapped_column(Float)
    precision_score: Mapped[float] = mapped_column(Float, default=0)
    precision_sample_size: Mapped[int] = mapped_column(Integer, default=0)
    discovery_query_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("discovery_queries.id"), index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("discovery_queries.id"), index=True
    )
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("youtube_channels.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_video_count: Mapped[int] = mapped_column(Integer, default=0)
    retained_video_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class ChannelBaseline(Base):
    __tablename__ = "channel_baselines"
    __table_args__ = (UniqueConstraint("channel_id", "window", "metric_name", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_channels.id"))
    window: Mapped[str] = mapped_column(String(24))
    metric_name: Mapped[str] = mapped_column(String(80))
    metric_value: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[str] = mapped_column(String(40))


class YoutubeVideo(Base):
    __tablename__ = "youtube_videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_channels.id"))
    canonical_url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    default_language: Mapped[str] = mapped_column(String(16), default="en")
    category_id: Mapped[str] = mapped_column(String(16), default="28")
    is_short: Mapped[bool] = mapped_column(Boolean, default=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    thumbnail_url: Mapped[str] = mapped_column(String(500))
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    discovery_lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VideoDiscoveryOccurrence(Base):
    __tablename__ = "video_discovery_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "provider_fetch_id",
            "query_id",
            "position",
            name="uq_discovery_occurrence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"))
    query_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("discovery_queries.id"))
    provider_fetch_id: Mapped[str] = mapped_column(String(36), ForeignKey("provider_fetches.id"))
    position: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(16), default="en")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"
    __table_args__ = (UniqueConstraint("video_id", "observed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    video_age_seconds: Mapped[int] = mapped_column(Integer)
    view_count: Mapped[int] = mapped_column(Integer)
    like_count: Mapped[int] = mapped_column(Integer)
    comment_count: Mapped[int] = mapped_column(Integer)
    views_per_hour: Mapped[float] = mapped_column(Float)
    likes_per_1000_views: Mapped[float] = mapped_column(Float, default=0)
    comments_per_1000_views: Mapped[float] = mapped_column(Float, default=0)
    snapshot_quality: Mapped[str] = mapped_column(String(24), default="direct")
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_fetch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("provider_fetches.id")
    )


class VideoSnapshotJob(Base):
    __tablename__ = "video_snapshot_jobs"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "scheduled_age_seconds",
            name="uq_video_snapshot_job_age",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    scheduled_age_seconds: Mapped[int] = mapped_column(Integer)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_fetch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("provider_fetches.id")
    )
    skip_reason: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VideoFeature(Base):
    __tablename__ = "video_features"

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_videos.id"), primary_key=True
    )
    feature_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    language_probability: Mapped[float] = mapped_column(Float, default=0)
    vertical_relevance: Mapped[float] = mapped_column(Float, default=0)
    outlier_ratio: Mapped[float] = mapped_column(Float, default=1)
    view_velocity: Mapped[float] = mapped_column(Float, default=0)
    velocity_acceleration: Mapped[float] = mapped_column(Float, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0)
    spam_probability: Mapped[float] = mapped_column(Float, default=0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VideoEmbedding(Base):
    __tablename__ = "video_embeddings"

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_videos.id"), primary_key=True
    )
    embedding_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(80))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector_json: Mapped[list[float]] = mapped_column(JSON)
    entities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_hash: Mapped[str] = mapped_column(String(64))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_label: Mapped[str] = mapped_column(String(300))
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    entities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    centroid_embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(80), default="hashing-embedding-v1")
    embedding_version: Mapped[str] = mapped_column(String(40), default="topic-embedding-v1")
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lifecycle_stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="active")
    source_kind: Mapped[str] = mapped_column(String(16), default="demo", index=True)
    merged_into_topic_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("topics.id"))
    clustering_version: Mapped[str] = mapped_column(String(40), default="demo-v1")
    identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    specificity_score: Mapped[float] = mapped_column(Float, default=0)
    thesis_support_ratio: Mapped[float] = mapped_column(Float, default=0)
    visibility_reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class TopicContentPattern(Base):
    __tablename__ = "topic_content_patterns"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "video_id",
            "model_version",
            name="uq_topic_content_pattern_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    video_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("youtube_videos.id"),
        index=True,
    )
    pattern_key: Mapped[str] = mapped_column(String(160), index=True)
    pattern_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(48), index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TopicContentGap(Base):
    __tablename__ = "topic_content_gaps"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "topic_id",
            "gap_key",
            "model_version",
            name="uq_topic_content_gap_version",
        ),
        Index(
            "ix_topic_content_gaps_workspace_topic_rank",
            "workspace_id",
            "topic_id",
            "rank",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id"),
        index=True,
    )
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    gap_key: Mapped[str] = mapped_column(String(160), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    occupied_pattern_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    open_gap_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    score_components_json: Mapped[dict[str, float]] = mapped_column(JSON)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(48), index=True)
    ranking_version: Mapped[str] = mapped_column(String(48))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TopicVideoMembership(Base):
    __tablename__ = "topic_video_memberships"

    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_videos.id"), primary_key=True
    )
    membership_score: Mapped[float] = mapped_column(Float)
    assignment_method: Mapped[str] = mapped_column(String(40))
    evidence_role: Mapped[str] = mapped_column(String(40), default="supporting")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TopicVideoObservation(Base):
    """Append-safe first/last observation state for point-in-time adoption labels."""

    __tablename__ = "topic_video_observations"
    __table_args__ = (
        Index(
            "ix_topic_video_observations_topic_first",
            "topic_id",
            "first_observed_at",
        ),
        Index(
            "ix_topic_video_observations_topic_last",
            "topic_id",
            "last_observed_at",
        ),
    )

    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("topics.id"),
        primary_key=True,
    )
    video_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("youtube_videos.id"),
        primary_key=True,
    )
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observation_count: Mapped[int] = mapped_column(Integer, default=1)
    first_observation_quality: Mapped[str] = mapped_column(
        String(32),
        default="direct",
    )
    membership_score: Mapped[float] = mapped_column(Float)
    assignment_method: Mapped[str] = mapped_column(String(40))
    evidence_role: Mapped[str] = mapped_column(String(40), default="supporting")


class TopicSnapshot(Base):
    __tablename__ = "topic_snapshots"
    __table_args__ = (
        UniqueConstraint("topic_id", "observed_at"),
        Index(
            "ix_topic_snapshots_observed_topic",
            "observed_at",
            "topic_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    video_count_24h: Mapped[int] = mapped_column(Integer)
    video_count_72h: Mapped[int] = mapped_column(Integer)
    distinct_channels_72h: Mapped[int] = mapped_column(Integer)
    aggregate_view_velocity: Mapped[float] = mapped_column(Float)
    median_outlier_ratio: Mapped[float] = mapped_column(Float)
    large_channel_count: Mapped[int] = mapped_column(Integer)
    demand_score: Mapped[float] = mapped_column(Float)
    saturation_score: Mapped[float] = mapped_column(Float)
    fragility_score: Mapped[float] = mapped_column(Float)
    component_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class TopicLineageEdge(Base):
    __tablename__ = "topic_lineage_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_topic_id",
            "target_topic_id",
            "lineage_version",
            name="uq_topic_lineage_edge_version",
        ),
        CheckConstraint(
            "source_topic_id <> target_topic_id",
            name="ck_topic_lineage_distinct_topics",
        ),
        CheckConstraint(
            "relationship IN ('successor', 'split_successor')",
            name="ck_topic_lineage_relationship",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_topic_lineage_confidence",
        ),
        Index(
            "ix_topic_lineage_source_detected",
            "source_topic_id",
            "detected_at",
        ),
        Index(
            "ix_topic_lineage_target_detected",
            "target_topic_id",
            "detected_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("topics.id"),
        index=True,
    )
    target_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("topics.id"),
        index=True,
    )
    relationship: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    identity_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lineage_version: Mapped[str] = mapped_column(String(48))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicSnapshotBucket(Base):
    __tablename__ = "topic_snapshot_buckets"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "resolution",
            "bucket_start",
            name="uq_topic_snapshot_bucket",
        ),
        Index(
            "ix_topic_snapshot_buckets_topic_start",
            "topic_id",
            "bucket_start",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    resolution: Mapped[str] = mapped_column(String(12))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    last_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    min_json: Mapped[dict[str, float]] = mapped_column(JSON)
    max_json: Mapped[dict[str, float]] = mapped_column(JSON)
    avg_json: Mapped[dict[str, float]] = mapped_column(JSON)
    video_count: Mapped[int] = mapped_column(Integer)
    channel_count: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    momentum: Mapped[float] = mapped_column(Float)
    saturation: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(32))
    source_measurement_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    bucket_version: Mapped[str] = mapped_column(String(48))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TopicLifecycleTransition(Base):
    __tablename__ = "topic_lifecycle_transitions"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "transitioned_at",
            "to_stage",
            name="uq_topic_lifecycle_transition_event",
        ),
        UniqueConstraint(
            "topic_id",
            "measurement_id",
            name="uq_topic_lifecycle_transition_measurement",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("topics.id"),
        index=True,
    )
    from_stage: Mapped[str | None] = mapped_column(String(32))
    to_stage: Mapped[str] = mapped_column(String(32), index=True)
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    measurement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("topic_snapshots.id"),
    )
    score: Mapped[float | None] = mapped_column(Float)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    history_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicLifecycleSummary(Base):
    __tablename__ = "topic_lifecycle_summaries"

    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("topics.id"),
        primary_key=True,
    )
    first_video_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_topic_formed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_emerging_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_signal_visible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_breakout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_mass_market_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_saturated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_declining_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_large_channel_adoption_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    latest_measurement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    backfill_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class TopicPipelineRun(Base):
    __tablename__ = "topic_pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    clustering_version: Mapped[str] = mapped_column(String(40))
    embedding_version: Mapped[str] = mapped_column(String(40))
    source_video_count: Mapped[int] = mapped_column(Integer, default=0)
    eligible_video_count: Mapped[int] = mapped_column(Integer, default=0)
    topic_count: Mapped[int] = mapped_column(Integer, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    clustering_lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    signal_generation_lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    llm_policy_version: Mapped[str] = mapped_column(String(64), default="")
    llm_trace_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class LLMIntelligenceRun(Base):
    __tablename__ = "llm_intelligence_runs"
    __table_args__ = (
        UniqueConstraint(
            "task",
            "scope_kind",
            "scope_id",
            "input_hash",
            "prompt_version",
            "model",
            name="uq_llm_intelligence_run_input",
        ),
        Index(
            "ix_llm_intelligence_runs_task_created",
            "task",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task: Mapped[str] = mapped_column(String(48), index=True)
    scope_kind: Mapped[str] = mapped_column(String(32), index=True)
    scope_id: Mapped[str] = mapped_column(String(160), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(48))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), index=True)
    evidence_refs_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_response_id: Mapped[str | None] = mapped_column(String(160))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    source_kind: Mapped[str] = mapped_column(String(16), default="demo", index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(24))
    opportunity_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opportunity_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thesis: Mapped[str] = mapped_column(Text)
    why_emerging_json: Mapped[list[str]] = mapped_column(JSON)
    component_json: Mapped[dict[str, float]] = mapped_column(JSON)
    evidence_version: Mapped[str] = mapped_column(String(120))
    synthesis_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SignalReview(Base):
    __tablename__ = "signal_reviews"
    __table_args__ = (
        UniqueConstraint("workspace_id", "signal_id"),
        Index("ix_signal_reviews_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    primary_reason: Mapped[str | None] = mapped_column(String(48))
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    thesis_override: Mapped[str | None] = mapped_column(Text)
    opportunity_override_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_selection_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_version: Mapped[str] = mapped_column(String(40), default="signal-review-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SignalReviewEvent(Base):
    __tablename__ = "signal_review_events"
    __table_args__ = (Index("ix_signal_review_events_review_created", "review_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("signal_reviews.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    reviewer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    changes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceSignalScore(Base):
    __tablename__ = "workspace_signal_scores"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_channels.id"))
    channel_fit_score: Mapped[float] = mapped_column(Float)
    fit_component_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    recommended_angle_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    fit_version: Mapped[str] = mapped_column(String(40), default="channel-fit-v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class YoutubeComment(Base):
    __tablename__ = "youtube_comments"
    __table_args__ = (
        UniqueConstraint("provider_comment_id", "video_id"),
        Index("ix_comment_normalized_hash", "normalized_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_comment_id: Mapped[str] = mapped_column(String(100))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"))
    parent_comment_id: Mapped[str | None] = mapped_column(String(36))
    text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    like_count: Mapped[int] = mapped_column(Integer)
    reply_count: Mapped[int] = mapped_column(Integer)
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(16), default="en")
    author_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    fetched_order: Mapped[str] = mapped_column(String(16), default="relevance")
    normalized_hash: Mapped[str] = mapped_column(String(64))
    provider_fetch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("provider_fetches.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommentFeature(Base):
    __tablename__ = "comment_features"

    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), primary_key=True
    )
    taxonomy: Mapped[str] = mapped_column(String(80), index=True)
    demand_probability: Mapped[float] = mapped_column(Float)
    spam_probability: Mapped[float] = mapped_column(Float)
    sentiment: Mapped[str] = mapped_column(String(24))
    embedding_json: Mapped[list[float]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(40), index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CommentTopicRelevance(Base):
    __tablename__ = "comment_topic_relevance"
    __table_args__ = (
        UniqueConstraint(
            "comment_id",
            "topic_id",
            name="uq_comment_topic_relevance_comment_topic",
        ),
        Index(
            "ix_comment_topic_relevance_topic_effective",
            "topic_id",
            "is_relevant",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), index=True
    )
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    is_relevant: Mapped[bool] = mapped_column(Boolean, index=True)
    relevance_score: Mapped[float] = mapped_column(Float)
    comment_topic_semantic_similarity: Mapped[float] = mapped_column(Float)
    comment_video_semantic_similarity: Mapped[float] = mapped_column(Float)
    entity_overlap_score: Mapped[float] = mapped_column(Float)
    claim_support_score: Mapped[float] = mapped_column(Float)
    intent_actionability_score: Mapped[float] = mapped_column(Float)
    duplicate_or_echo_probability: Mapped[float] = mapped_column(Float)
    spam_probability: Mapped[float] = mapped_column(Float)
    intent: Mapped[str] = mapped_column(String(80), index=True)
    actionability: Mapped[str] = mapped_column(String(16), index=True)
    supported_entities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    supported_claims_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(48), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    override_decision: Mapped[bool | None] = mapped_column(Boolean)
    override_reason: Mapped[str | None] = mapped_column(String(240))
    reviewer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommentTopicRelevanceEvent(Base):
    __tablename__ = "comment_topic_relevance_events"
    __table_args__ = (
        Index(
            "ix_comment_topic_relevance_events_relevance_created",
            "relevance_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    relevance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("comment_topic_relevance.id"), index=True
    )
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    previous_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    model_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommentFetchRun(Base):
    __tablename__ = "comment_fetch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    order: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    retained_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_fetch_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class DemandPipelineRun(Base):
    __tablename__ = "demand_pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    classifier_version: Mapped[str] = mapped_column(String(40))
    clustering_version: Mapped[str] = mapped_column(String(40))
    candidate_video_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_video_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    classified_count: Mapped[int] = mapped_column(Integer, default=0)
    cluster_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_evaluated_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_model_version: Mapped[str | None] = mapped_column(String(48))
    provider_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class DemandCluster(Base):
    __tablename__ = "demand_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"))
    label: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    taxonomy: Mapped[str] = mapped_column(String(80))
    comment_count: Mapped[int] = mapped_column(Integer)
    distinct_commenter_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_video_count: Mapped[int] = mapped_column(Integer)
    distinct_channel_count: Mapped[int] = mapped_column(Integer)
    demand_score: Mapped[float] = mapped_column(Float)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(40), default="demo-rules-v1")
    visibility_status: Mapped[str] = mapped_column(String(24), default="legacy_visible", index=True)
    evidence_strength: Mapped[str] = mapped_column(String(16), default="Unverified")
    median_relevance_score: Mapped[float | None] = mapped_column(Float)
    high_actionability_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_model_version: Mapped[str | None] = mapped_column(String(48))


class DemandClusterComment(Base):
    __tablename__ = "demand_cluster_comments"

    demand_cluster_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("demand_clusters.id"), primary_key=True
    )
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("youtube_comments.id"), primary_key=True
    )
    membership_score: Mapped[float] = mapped_column(Float)
    is_representative: Mapped[bool] = mapped_column(Boolean, default=False)


class VideoTranscript(Base):
    __tablename__ = "video_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), unique=True)
    language: Mapped[str] = mapped_column(String(16))
    transcript_type: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(80))
    provider_fetch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("provider_fetches.id")
    )
    full_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    quality_score: Mapped[float] = mapped_column(Float)
    generated_cost: Mapped[float] = mapped_column(Float, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_name: Mapped[str | None] = mapped_column(String(80))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    entities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    key_claims_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    use_cases_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    comparisons_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    unanswered_questions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    narrative_angle: Mapped[str] = mapped_column(String(80), default="unknown")
    content_format: Mapped[str] = mapped_column(String(80), default="unknown")
    processing_version: Mapped[str] = mapped_column(String(40), default="transcript-processing-v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("video_transcripts.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    is_evidence: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    segment_hash: Mapped[str] = mapped_column(String(64))


class TranscriptFetchRun(Base):
    __tablename__ = "transcript_fetch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    transcript_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("video_transcripts.id")
    )
    provider_fetch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("provider_fetches.id")
    )
    language_policy: Mapped[str] = mapped_column(String(120))
    allow_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class TranscriptPipelineRun(Base):
    __tablename__ = "transcript_pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    processing_version: Mapped[str] = mapped_column(String(40))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    unavailable_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    segment_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_lag_seconds: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class SignalAction(Base):
    __tablename__ = "signal_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(80), default="")
    comment: Mapped[str | None] = mapped_column(Text)
    opportunity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    feedback_version: Mapped[str] = mapped_column(String(48), default="decision-feedback-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationLabel(Base):
    __tablename__ = "evaluation_labels"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "reviewer_id",
            "as_of",
            name="uq_evaluation_label_reviewer_point_in_time",
        ),
        Index("ix_evaluation_labels_as_of_label", "as_of", "label"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id"),
        index=True,
    )
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), index=True)
    signal_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("signals.id"),
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    label: Mapped[str] = mapped_column(String(48), index=True)
    additional_labels_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    notes: Mapped[str] = mapped_column(Text, default="")
    model_versions_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    label_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_backtest_runs_status",
        ),
        CheckConstraint(
            "source_kind IN ('live', 'demo')",
            name="ck_backtest_runs_source_kind",
        ),
        Index("ix_backtest_runs_status_started", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), index=True)
    source_kind: Mapped[str] = mapped_column(String(16), index=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    code_revision: Mapped[str] = mapped_column(String(80))
    code_dirty: Mapped[bool] = mapped_column(Boolean, default=False)
    migration_revision: Mapped[str | None] = mapped_column(String(64))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_versions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestCheckpoint(Base):
    __tablename__ = "backtest_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "checkpoint_at",
            name="uq_backtest_checkpoints_run_time",
        ),
        CheckConstraint(
            "status IN ('pending', 'success', 'failed')",
            name="ck_backtest_checkpoints_status",
        ),
        CheckConstraint(
            "eligible_video_count >= 0 AND snapshot_count >= 0 AND prediction_count >= 0",
            name="ck_backtest_checkpoints_nonnegative_counts",
        ),
        Index(
            "ix_backtest_checkpoints_run_status_time",
            "run_id",
            "status",
            "checkpoint_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        index=True,
    )
    checkpoint_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    manifest_version: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    eligible_video_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0)
    prediction_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestCohort(Base):
    __tablename__ = "backtest_cohorts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'frozen')",
            name="ck_backtest_cohorts_status",
        ),
        CheckConstraint(
            "source_kind IN ('live', 'demo')",
            name="ck_backtest_cohorts_source_kind",
        ),
        CheckConstraint(
            "checkpoint_count >= 0 AND train_checkpoint_count >= 0 "
            "AND holdout_checkpoint_count >= 0 "
            "AND checkpoint_count = train_checkpoint_count + holdout_checkpoint_count",
            name="ck_backtest_cohorts_checkpoint_counts",
        ),
        Index("ix_backtest_cohorts_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), index=True)
    source_kind: Mapped[str] = mapped_column(String(16), index=True)
    policy_version: Mapped[str] = mapped_column(String(64))
    split_policy_version: Mapped[str] = mapped_column(String(64))
    horizon_days: Mapped[int] = mapped_column(Integer)
    checkpoint_count: Mapped[int] = mapped_column(Integer)
    train_checkpoint_count: Mapped[int] = mapped_column(Integer)
    holdout_checkpoint_count: Mapped[int] = mapped_column(Integer)
    dataset_hash: Mapped[str] = mapped_column(String(64), index=True)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    repository_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestCohortCheckpoint(Base):
    __tablename__ = "backtest_cohort_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "cohort_id",
            "ordinal",
            name="uq_backtest_cohort_checkpoints_ordinal",
        ),
        CheckConstraint("ordinal > 0", name="ck_backtest_cohort_checkpoints_ordinal"),
        CheckConstraint(
            "split IN ('train', 'holdout')",
            name="ck_backtest_cohort_checkpoints_split",
        ),
        Index(
            "ix_backtest_cohort_checkpoints_cohort_split_time",
            "cohort_id",
            "split",
            "checkpoint_at",
        ),
    )

    cohort_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_cohorts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    checkpoint_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_checkpoints.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    split: Mapped[str] = mapped_column(String(16), index=True)
    checkpoint_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    outcome_ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BacktestPrediction(Base):
    __tablename__ = "backtest_predictions"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_id",
            "rank",
            name="uq_backtest_predictions_checkpoint_rank",
        ),
        UniqueConstraint(
            "checkpoint_id",
            "candidate_key",
            name="uq_backtest_predictions_checkpoint_candidate",
        ),
        CheckConstraint("rank > 0", name="ck_backtest_predictions_positive_rank"),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_backtest_predictions_score_range",
        ),
        Index(
            "ix_backtest_predictions_checkpoint_score",
            "checkpoint_id",
            "score",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_checkpoints.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_key: Mapped[str] = mapped_column(String(160))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    lifecycle_stage: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(24))
    algorithm_version: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestOutcome(Base):
    __tablename__ = "backtest_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_id",
            "candidate_key",
            name="uq_backtest_outcomes_checkpoint_candidate",
        ),
        CheckConstraint(
            "status IN ('evaluated', 'insufficient_followup', 'insufficient_evidence')",
            name="ck_backtest_outcomes_status",
        ),
        CheckConstraint(
            "supply_growth_ratio >= 0 AND peak_lift >= 0",
            name="ck_backtest_outcomes_nonnegative_metrics",
        ),
        Index(
            "ix_backtest_outcomes_checkpoint_status_fired",
            "checkpoint_id",
            "status",
            "fired",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_checkpoints.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_key: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    fired: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    label_method: Mapped[str] = mapped_column(String(64))
    supply_growth_ratio: Mapped[float] = mapped_column(Float, default=0)
    peak_lift: Mapped[float] = mapped_column(Float, default=0)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evaluation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestReport(Base):
    __tablename__ = "backtest_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'insufficient_data')",
            name="ck_backtest_reports_status",
        ),
        Index("ix_backtest_reports_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    report_version: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(64))
    label_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    checkpoint_ids_json: Mapped[list[str]] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    gate_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    markdown_report: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContentBrief(Base):
    __tablename__ = "content_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"))
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_channels.id"))
    opportunity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    evidence_version: Mapped[str] = mapped_column(String(80), default="unknown")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    title: Mapped[str] = mapped_column(String(400))
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SignalPackaging(Base):
    __tablename__ = "signal_packaging"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "signal_id",
            "opportunity_id",
            name="uq_signal_packaging_workspace_opportunity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(36), index=True)
    content_brief_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_briefs.id"), unique=True
    )
    packaging_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    regeneration_counts_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    packaging_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PublishedOutcome(Base):
    __tablename__ = "published_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"))
    content_brief_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_briefs.id")
    )
    youtube_video_id: Mapped[str] = mapped_column(String(32))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    baseline_definition: Mapped[str] = mapped_column(String(240))
    performance_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    success_status: Mapped[str] = mapped_column(String(32))
    user_notes: Mapped[str] = mapped_column(Text, default="")
    link_status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    association_version: Mapped[str] = mapped_column(String(48), default="outcome-association-v1")
    metrics_version: Mapped[str] = mapped_column(String(48), default="outcome-metrics-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OutcomeSuggestion(Base):
    __tablename__ = "outcome_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "video_id",
            name="uq_outcome_suggestion_workspace_video",
        ),
        Index("ix_outcome_suggestions_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.id"))
    suggested_brief_id: Mapped[str] = mapped_column(String(36), ForeignKey("content_briefs.id"))
    selected_brief_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_briefs.id")
    )
    outcome_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("published_outcomes.id"))
    status: Mapped[str] = mapped_column(String(24), default="suggested", index=True)
    match_confidence: Mapped[float] = mapped_column(Float)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    match_features_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(48))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProductEvent(Base):
    __tablename__ = "product_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    signal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("signals.id"), index=True)
    content_brief_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_briefs.id")
    )
    outcome_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("published_outcomes.id"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class DigestSubscription(Base):
    __tablename__ = "digest_subscriptions"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    cadence: Mapped[str] = mapped_column(String(24), default="twice_weekly")
    delivery_channel: Mapped[str] = mapped_column(String(24), default="in_app")
    destination: Mapped[str] = mapped_column(String(320), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DigestRun(Base):
    __tablename__ = "digest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="generated", index=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderFetch(Base):
    __tablename__ = "provider_fetches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    capability: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(String(160))
    request_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32))
    http_status: Mapped[int] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0)
    raw_payload_uri: Mapped[str] = mapped_column(String(500))
    raw_payload_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    linked_entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class FieldProvenance(Base):
    __tablename__ = "field_provenance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(80))
    field_name: Mapped[str] = mapped_column(String(120))
    provider_fetch_id: Mapped[str] = mapped_column(String(36), ForeignKey("provider_fetches.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    value_hash: Mapped[str] = mapped_column(String(64))


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    provider: Mapped[str] = mapped_column(String(80), primary_key=True)
    capability: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer)
    success_count: Mapped[int] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer)
    p50_latency_ms: Mapped[int] = mapped_column(Integer)
    p95_latency_ms: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    circuit_state: Mapped[str] = mapped_column(String(24), default="closed")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    half_open_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(160))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderBudget(Base):
    __tablename__ = "provider_budgets"

    provider: Mapped[str] = mapped_column(String(80), primary_key=True)
    capability: Mapped[str] = mapped_column(String(40), primary_key=True)
    daily_limit_usd: Mapped[float] = mapped_column(Float)
    monthly_limit_usd: Mapped[float] = mapped_column(Float)
    spent_today_usd: Mapped[float] = mapped_column(Float, default=0)
    spent_month_usd: Mapped[float] = mapped_column(Float, default=0)
    day_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    month_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderRoutingDecision(Base):
    __tablename__ = "provider_routing_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    capability: Mapped[str] = mapped_column(String(40), index=True)
    operation_key: Mapped[str] = mapped_column(String(180), index=True)
    selected_provider: Mapped[str | None] = mapped_column(String(80), index=True)
    attempted_providers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    skipped_providers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str] = mapped_column(String(160))
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderOperationsEvent(Base):
    __tablename__ = "provider_operations_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    capability: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str | None] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderBenchmarkRun(Base):
    __tablename__ = "provider_benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    benchmark_version: Mapped[str] = mapped_column(String(40), index=True)
    fixture_path: Mapped[str] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    live_case_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recommended_priorities_json: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    json_path: Mapped[str | None] = mapped_column(String(500))
    csv_path: Mapped[str | None] = mapped_column(String(500))
    markdown_path: Mapped[str | None] = mapped_column(String(500))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class RawPayloadLink(Base):
    __tablename__ = "raw_payload_links"

    provider_fetch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provider_fetches.id"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(80), primary_key=True)


class RawApiSnapshot(Base):
    """TTL-bound mirror of official YouTube Data API responses.

    Raw snapshots are kept separate from EarlySignal-computed metrics. Scoring,
    channel fit, clustering, and replay consume the derived ledger instead of
    reading this table directly.
    """

    __tablename__ = "raw_api_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("youtube_videos.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DerivedMetricPoint(Base):
    """Append-only, versioned ledger of EarlySignal-computed metrics."""

    __tablename__ = "derived_metric_points"
    __table_args__ = (
        Index(
            "ix_derived_metric_points_subject",
            "subject_type",
            "subject_id",
            "metric_name",
            "computed_at",
        ),
        Index(
            "uq_derived_metric_points_identity",
            "subject_type",
            "subject_id",
            "metric_name",
            "window",
            "scoring_version",
            "computed_at",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(36), index=True)
    metric_name: Mapped[str] = mapped_column(String(80))
    value: Mapped[float] = mapped_column(Float)
    window: Mapped[str] = mapped_column(String(24))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scoring_version: Mapped[str] = mapped_column(String(60), index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
