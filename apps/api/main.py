from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from apps.api.auth import AccountAuthMiddleware
from apps.api.auth import router as auth_router
from apps.api.channel_profiles import ensure_channel_profile, primary_owned_channel
from apps.api.config import get_settings
from apps.api.database import get_db
from apps.api.demo import (
    DEMO_WORKSPACE_ID,
)
from apps.api.lifecycle import get_signal_earlyness
from apps.api.models import (
    ChannelProfile,
    ContentBrief,
    DemandPipelineRun,
    DigestRun,
    DigestSubscription,
    DiscoveryQueryRecord,
    DiscoveryRun,
    EvaluationLabel,
    OutcomeSuggestion,
    ProviderBenchmarkRun,
    ProviderBudget,
    ProviderFetch,
    ProviderHealth,
    ProviderOperationsEvent,
    ProviderRoutingDecision,
    PublishedOutcome,
    QuerySuggestion,
    Signal,
    SignalAction,
    SignalPackaging,
    Topic,
    TopicPipelineRun,
    TopicVideoMembership,
    TranscriptPipelineRun,
    User,
    VideoFeature,
    VideoSnapshot,
    VideoSnapshotJob,
    Workspace,
    WorkspaceChannel,
    WorkspaceMember,
    WorkspaceOnboarding,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.onboarding import OnboardingService, slugify
from apps.api.packaging import ensure_signal_packaging, regenerate_signal_packaging
from apps.api.product_analytics import ProductAnalyticsService, record_product_event
from apps.api.reviews import (
    apply_review_action,
    decision_card_preview,
    ensure_workspace_reviews,
    false_positive_risks,
    get_signal_review,
    list_signal_reviews,
    record_review_published,
    review_audit_history,
    review_summary,
    signal_is_visible,
    workspace_reviewer,
)
from apps.api.schemas import (
    AnalyticsSummaryResponse,
    BriefCreate,
    BriefResponse,
    BriefUpdate,
    ChannelProfileResponse,
    ChannelProfileUpdate,
    CommentTopicRelevanceOverrideRequest,
    CommentTopicRelevanceResponse,
    DemandIntelligenceMetrics,
    DemandIntelligenceRunResponse,
    DemandReclassifyRequest,
    DemandReclassifyResponse,
    DemoContext,
    DigestRunResponse,
    DigestSubscriptionResponse,
    DigestSubscriptionUpdate,
    DiscoveryQueryCreate,
    DiscoveryQueryResponse,
    EvaluationCandidate,
    EvaluationCandidateList,
    EvaluationLabelCreate,
    EvaluationLabelResponse,
    EvaluationReportResponse,
    IngestionRunResponse,
    MonitorChannelCreate,
    MonitoredChannelResponse,
    MonitoredChannelUpdate,
    OnboardingAutoSetupRequest,
    OnboardingStatusResponse,
    OnboardingWorkspaceUpdate,
    OperationsReadinessResponse,
    OutcomeCorrection,
    OutcomeCreate,
    OutcomeResponse,
    OutcomeSuggestionDecision,
    OutcomeSuggestionResponse,
    ProductEventCreate,
    ProductEventResponse,
    ProviderBenchmarkResponse,
    ProviderFetchDetail,
    ProviderFetchListItem,
    ProviderHealthResponse,
    ProviderOperationsEventResponse,
    ProviderRoutingDecisionResponse,
    ProviderRoutingMetrics,
    ProviderUpdate,
    QueryExpansionRunResponse,
    QuerySuggestionAction,
    QuerySuggestionResponse,
    RunIngestionRequest,
    SignalActionCreate,
    SignalActionResponse,
    SignalDecisionCard,
    SignalDetail,
    SignalEarlynessResponse,
    SignalListResponse,
    SignalPackagingCopyEvent,
    SignalPackagingRegenerate,
    SignalPackagingResponse,
    SignalReviewActionCreate,
    SignalReviewDetail,
    SignalReviewEventResponse,
    SignalReviewQueueResponse,
    SnapshotScheduleResponse,
    TopicIntelligenceMetrics,
    TopicIntelligenceRunResponse,
    TranscriptIntelligenceMetrics,
    TranscriptIntelligenceRunResponse,
    VideoIntelligenceItem,
    VideoIntelligenceMetrics,
    VideoIntelligenceRunRequest,
    VideoIntelligenceRunResponse,
    WorkspaceChannelCreate,
    WorkspaceSetupCreate,
    WorkspaceSetupResponse,
    YoutubeAnalyticsSyncResponse,
    YoutubeOAuthStartRequest,
    YoutubeOAuthStartResponse,
    YoutubeOAuthStatusResponse,
)
from apps.api.services import (
    get_signal_detail,
    list_signals,
    resolve_signal_source,
)
from apps.api.youtube_oauth import (
    YoutubeOAuthService,
    YoutubeOwnedAnalyticsService,
)
from apps.worker.channel_discovery import ChannelDiscoveryService
from apps.worker.demand_intelligence import DemandIntelligenceService
from apps.worker.digests import DigestService
from apps.worker.ingestion import IngestionService
from apps.worker.outcome_tracking import OutcomeAutomationService
from apps.worker.query_expansion import QueryExpansionService
from apps.worker.topic_intelligence import TopicIntelligenceService
from apps.worker.transcript_intelligence import TranscriptIntelligenceService
from apps.worker.video_intelligence import VideoIntelligenceService
from packages.channel_profile import CHANNEL_PROFILE_VERSION
from packages.demand import RELEVANCE_MODEL_VERSION
from packages.evaluation import (
    ADDITIONAL_LABELS,
    FEEDBACK_VERSION,
    LABEL_VERSION,
    PRIMARY_LABELS,
    build_evaluation_report,
    build_label_evidence_snapshot,
    code_model_versions,
    evaluation_export_records,
    feedback_export_records,
    records_as_csv,
    records_as_jsonl,
    validate_decision_reason,
)
from packages.outcome_tracking import METRICS_MODEL_VERSION
from packages.provider_benchmark import ProviderBenchmarkService

logger = logging.getLogger(__name__)
settings = get_settings()
settings.validate_runtime()
DbSession = Annotated[Session, Depends(get_db)]
app = FastAPI(
    title="EarlySignal API",
    version="0.1.0",
    description="Provider-independent evidence contracts for the YouTube trend MVP.",
)
app.add_middleware(AccountAuthMiddleware, settings=settings)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "demo_mode": settings.demo_mode}


@app.get("/health/ready", include_in_schema=False)
def health_ready(session: DbSession) -> Response:
    checked_at = datetime.now(tz=UTC)
    try:
        session.execute(text("SELECT 1"))
        latest_completed = session.scalar(
            select(func.max(TopicPipelineRun.completed_at)).where(
                TopicPipelineRun.status == "success"
            )
        )
        stale_runs = int(
            session.scalar(
                select(func.count(TopicPipelineRun.id)).where(
                    TopicPipelineRun.status == "running",
                    TopicPipelineRun.started_at
                    < checked_at - timedelta(minutes=max(1, settings.topic_pipeline_stale_minutes)),
                )
            )
            or 0
        )
    except Exception:
        logger.exception("Readiness dependency check failed")
        return JSONResponse(
            {"status": "not_ready", "database": "unavailable"},
            status_code=503,
        )
    worker_fresh = latest_completed is not None and checked_at - _aware(
        latest_completed
    ) <= timedelta(hours=6)
    ready = stale_runs == 0 and (worker_fresh or settings.demo_mode)
    return JSONResponse(
        {
            "status": "ready" if ready else "not_ready",
            "database": "ready",
            "worker_fresh": worker_fresh,
            "stale_topic_runs": stale_runs,
            "checked_at": checked_at.isoformat(),
        },
        status_code=200 if ready else 503,
    )


def _workspace_context(session: Session, user_id: str | None = None) -> DemoContext:
    member = (
        session.scalar(
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(WorkspaceMember.workspace_id)
            .limit(1)
        )
        if user_id
        else None
    )
    workspace = (
        session.get(Workspace, member.workspace_id)
        if member is not None
        else (
            session.get(Workspace, DEMO_WORKSPACE_ID)
            if settings.demo_mode
            else session.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))
        )
    )
    if workspace is None:
        raise HTTPException(503, "No workspace is configured")
    member = member or session.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.role)
        .limit(1)
    )
    owned = primary_owned_channel(session, workspace.id)
    channel = session.get(YoutubeChannel, owned.channel_id) if owned is not None else None
    if member is None:
        raise HTTPException(503, "Workspace has no member")
    user = session.get(User, member.user_id)
    if user is None:
        raise HTTPException(503, "Workspace member has no user")
    onboarding = session.get(WorkspaceOnboarding, workspace.id)
    return DemoContext(
        demo=settings.demo_mode,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        owned_channel_id=channel.id if channel is not None else "",
        owned_channel_name=channel.title if channel is not None else "Your channel",
        user_id=member.user_id,
        user_name=user.name,
        user_email=user.email,
        role=member.role,
        is_admin=(
            user.is_platform_admin
            if user_id is not None and settings.auth_required
            else member.role in {"owner", "admin"}
        ),
        onboarding_status=onboarding.status if onboarding else "in_progress",
        features=settings.improvement_features.as_dict(),
        fresh_at=datetime.now(tz=UTC),
    )


@app.get("/api/v1/context", response_model=DemoContext)
def workspace_context(request: Request, session: DbSession) -> DemoContext:
    return _workspace_context(session, getattr(request.state, "auth_user_id", None))


@app.get("/api/v1/demo/context", response_model=DemoContext)
def demo_context(session: DbSession) -> DemoContext:
    if not settings.demo_mode:
        raise HTTPException(404, "Demo mode is disabled")
    return _workspace_context(session)


@app.post(
    "/api/v1/admin/workspaces",
    response_model=WorkspaceSetupResponse,
    status_code=201,
)
def create_private_beta_workspace(
    payload: WorkspaceSetupCreate,
    session: DbSession,
) -> WorkspaceSetupResponse:
    existing_user = session.scalar(select(User).where(User.email == payload.owner_email))
    now = datetime.now(tz=UTC)
    user = existing_user or User(
        id=str(uuid4()),
        email=payload.owner_email,
        name=payload.owner_name,
        created_at=now,
    )
    if existing_user is None:
        session.add(user)
    base_slug = slugify(payload.workspace_name)
    candidate = base_slug
    suffix = 2
    while session.scalar(select(Workspace.id).where(Workspace.slug == candidate)):
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    workspace = Workspace(
        id=str(uuid4()),
        name=payload.workspace_name,
        slug=candidate,
        plan="private_beta",
        timezone=payload.timezone,
        created_at=now,
    )
    session.add(workspace)
    session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
    )
    session.add(
        WorkspaceOnboarding(
            workspace_id=workspace.id,
            status="in_progress",
            current_step=1,
            completed_steps_json=[],
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return WorkspaceSetupResponse(
        workspace_id=workspace.id,
        user_id=user.id,
        onboarding_url=f"/onboarding?workspace={workspace.id}",
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/onboarding",
    response_model=OnboardingStatusResponse,
)
def onboarding_status(
    workspace_id: str,
    session: DbSession,
) -> dict[str, object]:
    try:
        return OnboardingService(session, settings).status(workspace_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@app.patch(
    "/api/v1/workspaces/{workspace_id}/onboarding/workspace",
    response_model=OnboardingStatusResponse,
)
def update_onboarding_workspace(
    workspace_id: str,
    payload: OnboardingWorkspaceUpdate,
    session: DbSession,
) -> dict[str, object]:
    try:
        return OnboardingService(session, settings).update_workspace(
            workspace_id,
            name=payload.name,
            timezone=payload.timezone,
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@app.post(
    "/api/v1/workspaces/{workspace_id}/onboarding/auto-setup",
    response_model=OnboardingStatusResponse,
)
async def auto_setup_onboarding(
    workspace_id: str,
    payload: OnboardingAutoSetupRequest,
    session: DbSession,
) -> dict[str, object]:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found")
    ingestion = IngestionService(session, settings)
    try:
        channel = await ingestion.monitor_channel(
            workspace_id=workspace_id,
            youtube_channel_id=payload.youtube_channel.strip(),
            relationship="owned",
            priority=0,
        )
        workspace_channel = session.get(WorkspaceChannel, (workspace_id, channel.id))
        if workspace_channel is None:
            raise RuntimeError("Connected channel was not persisted")
        try:
            await ingestion.ingest_monitored_channel(
                workspace_channel,
                force=True,
                max_results=30,
            )
        except Exception:
            # Channel metadata is enough for a useful fallback plan. A transient
            # uploads failure must not turn zero-configuration setup into a dead end.
            logger.exception("Initial owned-channel history ingest failed")
        ChannelDiscoveryService(session, settings).build(workspace_id)
        onboarding = OnboardingService(session, settings)
        onboarding.seed_reference_channels(workspace_id)
        onboarding.prepare_digest(workspace_id)
        return onboarding.complete(workspace_id)
    except (LookupError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Automatic onboarding failed")
        raise HTTPException(502, f"Channel analysis failed: {error}") from error


@app.post(
    "/api/v1/workspaces/{workspace_id}/onboarding/prepare-digest",
    response_model=OnboardingStatusResponse,
)
def prepare_onboarding_digest(
    workspace_id: str,
    session: DbSession,
) -> dict[str, object]:
    return OnboardingService(session, settings).prepare_digest(workspace_id)


@app.post(
    "/api/v1/workspaces/{workspace_id}/onboarding/complete",
    response_model=OnboardingStatusResponse,
)
def complete_onboarding(
    workspace_id: str,
    session: DbSession,
) -> dict[str, object]:
    try:
        return OnboardingService(session, settings).complete(workspace_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post(
    "/api/v1/workspaces/{workspace_id}/analytics/events",
    response_model=ProductEventResponse,
    status_code=201,
)
def create_product_event(
    workspace_id: str,
    payload: ProductEventCreate,
    session: DbSession,
) -> ProductEventResponse:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found")
    if payload.signal_id and session.get(Signal, payload.signal_id) is None:
        raise HTTPException(404, "Signal not found")
    row = record_product_event(
        session,
        workspace_id=workspace_id,
        event_type=payload.event_type,
        event_key=f"client:{workspace_id}:{payload.event_key}",
        signal_id=payload.signal_id,
        metadata=payload.metadata,
    )
    session.commit()
    return ProductEventResponse(
        id=row.id,
        event_type=row.event_type,
        occurred_at=row.occurred_at,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/analytics/summary",
    response_model=AnalyticsSummaryResponse,
)
def analytics_summary(
    workspace_id: str,
    session: DbSession,
    days: int = Query(default=30, ge=7, le=90),
) -> dict[str, object]:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found")
    return ProductAnalyticsService(session).summary(workspace_id, days=days)


def _digest_response(row: DigestRun) -> DigestRunResponse:
    return DigestRunResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        period_start=row.period_start,
        period_end=row.period_end,
        status=row.status,
        content=row.content_json,
        generated_at=row.generated_at,
        delivered_at=row.delivered_at,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/digest/subscription",
    response_model=DigestSubscriptionResponse,
)
def digest_subscription(
    workspace_id: str,
    session: DbSession,
) -> DigestSubscription:
    row = DigestService(session, settings).ensure_subscription(workspace_id)
    session.commit()
    return row


@app.put(
    "/api/v1/workspaces/{workspace_id}/digest/subscription",
    response_model=DigestSubscriptionResponse,
)
def update_digest_subscription(
    workspace_id: str,
    payload: DigestSubscriptionUpdate,
    session: DbSession,
) -> DigestSubscription:
    return DigestService(session, settings).update_subscription(
        workspace_id,
        cadence=payload.cadence,
        delivery_channel=payload.delivery_channel,
        destination=payload.destination,
        enabled=payload.enabled,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/digest/latest",
    response_model=DigestRunResponse,
)
def latest_digest(
    workspace_id: str,
    session: DbSession,
) -> DigestRunResponse:
    return _digest_response(DigestService(session, settings).ensure_latest(workspace_id))


@app.post(
    "/api/v1/workspaces/{workspace_id}/digest/generate",
    response_model=DigestRunResponse,
    status_code=201,
)
def generate_digest(
    workspace_id: str,
    session: DbSession,
) -> DigestRunResponse:
    return _digest_response(DigestService(session, settings).generate(workspace_id))


def _channel_profile_response(
    session: Session,
    profile: ChannelProfile,
) -> ChannelProfileResponse:
    channel = session.get(YoutubeChannel, profile.channel_id)
    if channel is None:
        raise HTTPException(500, "Channel profile has no channel")
    return ChannelProfileResponse(
        workspace_id=profile.workspace_id,
        channel_id=profile.channel_id,
        channel_title=channel.title,
        youtube_channel_id=channel.youtube_channel_id,
        profile_source=profile.profile_source,
        audience_description=profile.audience_description,
        geography=profile.geography,
        language=profile.language,
        topic_keywords=profile.topic_keywords_json,
        preferred_formats=profile.preferred_formats_json,
        creator_expertise=profile.creator_expertise_json,
        production_capabilities=profile.production_capabilities_json,
        exclusions=profile.exclusions_json,
        strategic_goals=profile.strategic_goals_json,
        title_style=profile.title_style_json,
        normal_duration_min_seconds=profile.normal_duration_min_seconds,
        normal_duration_max_seconds=profile.normal_duration_max_seconds,
        production_days_min=profile.production_days_min,
        production_days_max=profile.production_days_max,
        core_topics=profile.core_topics_json,
        adjacent_topics=profile.adjacent_topics_json,
        legacy_topics=profile.legacy_topics_json,
        successful_formats=profile.successful_formats_json,
        upload_cadence=profile.upload_cadence_json,
        audience_sophistication=profile.audience_sophistication,
        creator_authority=profile.creator_authority,
        risk_tolerance=profile.risk_tolerance,
        team_size=profile.team_size,
        research_capacity_hours=profile.research_capacity_hours,
        filming_required=profile.filming_required,
        external_guests_required=profile.external_guests_required,
        editing_complexity=profile.editing_complexity,
        access_to_products=profile.access_to_products_json,
        experiment_level=profile.experiment_level,
        evergreen_trend_balance=profile.evergreen_trend_balance,
        weekday_publish_only=profile.weekday_publish_only,
        content_calendar=profile.content_calendar_json,
        inference=profile.inference_json,
        explicit_overrides=profile.explicit_overrides_json,
        profile_version=profile.profile_version,
        updated_at=profile.updated_at,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/channel-profile",
    response_model=ChannelProfileResponse,
)
def channel_profile(
    workspace_id: str,
    session: DbSession,
) -> ChannelProfileResponse:
    owned = primary_owned_channel(session, workspace_id)
    if owned is None:
        raise HTTPException(404, "Configure an owned channel first")
    profile = ensure_channel_profile(session, owned)
    session.commit()
    return _channel_profile_response(session, profile)


@app.put(
    "/api/v1/workspaces/{workspace_id}/channel-profile",
    response_model=ChannelProfileResponse,
)
def update_channel_profile(
    workspace_id: str,
    payload: ChannelProfileUpdate,
    session: DbSession,
) -> ChannelProfileResponse:
    if payload.normal_duration_min_seconds > payload.normal_duration_max_seconds:
        raise HTTPException(422, "Minimum duration cannot exceed maximum duration")
    if payload.production_days_min > payload.production_days_max:
        raise HTTPException(422, "Minimum production time cannot exceed maximum")
    owned = primary_owned_channel(session, workspace_id)
    if owned is None:
        raise HTTPException(404, "Configure an owned channel first")
    profile = ensure_channel_profile(session, owned)
    profile.profile_source = "user"
    profile.audience_description = payload.audience_description
    profile.geography = payload.geography
    profile.language = payload.language
    profile.topic_keywords_json = payload.topic_keywords
    profile.preferred_formats_json = payload.preferred_formats
    profile.creator_expertise_json = payload.creator_expertise
    profile.production_capabilities_json = payload.production_capabilities
    profile.exclusions_json = payload.exclusions
    profile.strategic_goals_json = payload.strategic_goals
    profile.normal_duration_min_seconds = payload.normal_duration_min_seconds
    profile.normal_duration_max_seconds = payload.normal_duration_max_seconds
    profile.production_days_min = payload.production_days_min
    profile.production_days_max = payload.production_days_max
    profile.core_topics_json = payload.core_topics or payload.topic_keywords
    profile.adjacent_topics_json = payload.adjacent_topics or []
    profile.audience_sophistication = (
        payload.audience_sophistication or profile.audience_sophistication
    )
    profile.creator_authority = payload.creator_authority or profile.creator_authority
    profile.risk_tolerance = payload.risk_tolerance or profile.risk_tolerance
    profile.team_size = payload.team_size or profile.team_size
    profile.research_capacity_hours = (
        payload.research_capacity_hours
        if payload.research_capacity_hours is not None
        else profile.research_capacity_hours
    )
    profile.filming_required = (
        payload.filming_required
        if payload.filming_required is not None
        else profile.filming_required
    )
    profile.external_guests_required = (
        payload.external_guests_required
        if payload.external_guests_required is not None
        else profile.external_guests_required
    )
    profile.editing_complexity = payload.editing_complexity or profile.editing_complexity
    profile.access_to_products_json = (
        payload.access_to_products
        if payload.access_to_products is not None
        else profile.access_to_products_json
    )
    profile.experiment_level = payload.experiment_level or profile.experiment_level
    profile.evergreen_trend_balance = (
        payload.evergreen_trend_balance
        if payload.evergreen_trend_balance is not None
        else profile.evergreen_trend_balance
    )
    profile.weekday_publish_only = (
        payload.weekday_publish_only
        if payload.weekday_publish_only is not None
        else profile.weekday_publish_only
    )
    profile.content_calendar_json = (
        payload.content_calendar
        if payload.content_calendar is not None
        else profile.content_calendar_json
    )
    profile.explicit_overrides_json = {
        **profile.explicit_overrides_json,
        **{
            field: getattr(payload, field)
            for field in payload.model_fields_set
            if field
            in {
                "audience_description",
                "topic_keywords",
                "preferred_formats",
                "creator_expertise",
                "production_capabilities",
                "exclusions",
                "strategic_goals",
                "production_days_min",
                "production_days_max",
                "core_topics",
                "adjacent_topics",
                "audience_sophistication",
                "creator_authority",
                "risk_tolerance",
                "team_size",
                "research_capacity_hours",
                "filming_required",
                "external_guests_required",
                "editing_complexity",
                "access_to_products",
                "experiment_level",
                "evergreen_trend_balance",
                "weekday_publish_only",
                "content_calendar",
            }
        },
    }
    profile.profile_version = CHANNEL_PROFILE_VERSION
    profile.updated_at = datetime.now(tz=UTC)
    session.commit()
    try:
        TopicIntelligenceService(session, settings).run(force=True)
    except Exception as error:
        # Profile changes are authoritative and already committed. A global
        # intelligence refresh is follow-up work and must not block onboarding.
        session.rollback()
        logger.exception(
            "Topic intelligence refresh failed after channel profile update",
            extra={
                "workspace_id": workspace_id,
                "error_type": type(error).__name__,
            },
        )
    session.refresh(profile)
    return _channel_profile_response(session, profile)


@app.get(
    "/api/v1/workspaces/{workspace_id}/oauth/youtube",
    response_model=YoutubeOAuthStatusResponse,
)
def youtube_oauth_status(
    workspace_id: str,
    session: DbSession,
) -> YoutubeOAuthStatusResponse:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found")
    return YoutubeOAuthStatusResponse(**YoutubeOAuthService(session, settings).status(workspace_id))


@app.post(
    "/api/v1/workspaces/{workspace_id}/oauth/youtube/start",
    response_model=YoutubeOAuthStartResponse,
)
def start_youtube_oauth(
    workspace_id: str,
    payload: YoutubeOAuthStartRequest,
    session: DbSession,
) -> YoutubeOAuthStartResponse:
    try:
        authorization_url = YoutubeOAuthService(
            session,
            settings,
        ).begin_authorization(
            workspace_id,
            redirect_after=payload.redirect_after,
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    return YoutubeOAuthStartResponse(authorization_url=authorization_url)


@app.get("/api/v1/oauth/youtube/callback", response_model=None)
async def youtube_oauth_callback(
    session: DbSession,
    state: str = Query(min_length=20, max_length=500),
    code: str | None = Query(default=None, min_length=2, max_length=4000),
    error: str | None = Query(default=None, max_length=160),
) -> Response:
    if error or not code:
        raise HTTPException(400, "YouTube authorization was not completed")
    try:
        connection, redirect_after = await YoutubeOAuthService(
            session,
            settings,
        ).complete_authorization(state=state, code=code)
        await YoutubeOwnedAnalyticsService(session, settings).sync(connection.workspace_id)
    except (LookupError, ValueError):
        raise HTTPException(400, "YouTube authorization could not be verified") from None
    separator = "&" if "?" in redirect_after else "?"
    return RedirectResponse(
        f"{settings.web_origin.rstrip('/')}{redirect_after}{separator}youtube=connected",
        status_code=303,
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/oauth/youtube/sync",
    response_model=YoutubeAnalyticsSyncResponse,
)
async def sync_youtube_analytics(
    workspace_id: str,
    session: DbSession,
) -> YoutubeAnalyticsSyncResponse:
    if not settings.feature_youtube_oauth_analytics:
        raise HTTPException(404, "YouTube analytics is disabled")
    updated = await YoutubeOwnedAnalyticsService(session, settings).sync(workspace_id)
    status = YoutubeOAuthService(session, settings).status(workspace_id)
    return YoutubeAnalyticsSyncResponse(
        updated_videos=updated,
        status=str(status["status"]),
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/oauth/youtube/disconnect",
    response_model=YoutubeOAuthStatusResponse,
)
async def disconnect_youtube_oauth(
    workspace_id: str,
    session: DbSession,
) -> YoutubeOAuthStatusResponse:
    service = YoutubeOAuthService(session, settings)
    await service.disconnect(workspace_id)
    return YoutubeOAuthStatusResponse(**service.status(workspace_id))


@app.get(
    "/api/v1/workspaces/{workspace_id}/signals",
    response_model=SignalListResponse,
)
def signal_feed(
    workspace_id: str,
    session: DbSession,
    stage: str | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=100),
    action: str | None = Query(default=None),
    source: str = Query(default="auto", pattern="^(auto|live|demo)$"),
) -> SignalListResponse:
    resolved_source, available_modes = resolve_signal_source(
        session,
        workspace_id,
        source,
        require_review_approval=settings.feature_signal_review_queue,
    )
    items = list_signals(
        session,
        workspace_id,
        source_kind=resolved_source,
        include_earlyness=settings.feature_earlyness_timeline,
        include_decision=settings.feature_decision_experience,
        use_snapshot_buckets=settings.feature_topic_snapshot_buckets,
        use_feasibility_v2=settings.feature_channel_profile_feasibility_v2,
        require_review_approval=settings.feature_signal_review_queue,
    )
    if stage:
        items = [item for item in items if item.lifecycle_stage.lower() == stage.lower()]
    if min_score is not None:
        items = [item for item in items if item.score >= min_score]
    if action == "new":
        items = [item for item in items if item.current_action is None]
    elif action:
        items = [item for item in items if item.current_action == action]
    freshness = max((item.generated_at for item in items), default=datetime.now(tz=UTC))
    return SignalListResponse(
        items=items,
        total=len(items),
        data_freshness=freshness,
        data_mode=resolved_source,
        available_modes=available_modes,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}",
    response_model=SignalDetail,
)
def signal_detail(
    workspace_id: str,
    signal_id: str,
    session: DbSession,
) -> SignalDetail:
    return get_signal_detail(
        session,
        workspace_id,
        signal_id,
        include_earlyness=settings.feature_earlyness_timeline,
        include_decision=settings.feature_decision_experience,
        include_content_gap=settings.feature_microtopic_content_gap,
        use_snapshot_buckets=settings.feature_topic_snapshot_buckets,
        use_feasibility_v2=settings.feature_channel_profile_feasibility_v2,
        require_review_approval=settings.feature_signal_review_queue,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/opportunities/{signal_id}/decision-card",
    response_model=SignalDecisionCard,
)
def opportunity_decision_card(
    workspace_id: str,
    signal_id: str,
    session: DbSession,
) -> SignalDecisionCard:
    detail = get_signal_detail(
        session,
        workspace_id,
        signal_id,
        include_earlyness=settings.feature_earlyness_timeline,
        include_decision=True,
        include_content_gap=settings.feature_microtopic_content_gap,
        use_snapshot_buckets=settings.feature_topic_snapshot_buckets,
        use_feasibility_v2=settings.feature_channel_profile_feasibility_v2,
        require_review_approval=settings.feature_signal_review_queue,
    )
    if detail.decision_card is None:
        raise HTTPException(404, "Decision card is not available")
    return detail.decision_card


@app.get(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/earlyness",
    response_model=SignalEarlynessResponse,
)
def signal_earlyness(
    workspace_id: str,
    signal_id: str,
    session: DbSession,
) -> SignalEarlynessResponse:
    if not settings.feature_earlyness_timeline:
        raise HTTPException(404, "Earlyness timeline is disabled")
    if settings.feature_signal_review_queue and not signal_is_visible(
        session,
        workspace_id,
        signal_id,
    ):
        raise HTTPException(404, "Signal not found")
    return get_signal_earlyness(session, workspace_id, signal_id)


def _require_review_queue() -> None:
    if not settings.feature_signal_review_queue:
        raise HTTPException(404, "Signal review queue is disabled")


def _admin_review_detail(
    session: Session,
    workspace_id: str,
    signal_id: str,
) -> SignalReviewDetail:
    ensure_workspace_reviews(session, workspace_id)
    review = get_signal_review(session, workspace_id, signal_id)
    if review is None:
        raise HTTPException(404, "Signal review not found")
    detail = get_signal_detail(
        session,
        workspace_id,
        signal_id,
        include_earlyness=settings.feature_earlyness_timeline,
        require_review_approval=False,
    )
    session.commit()
    return SignalReviewDetail(
        review=review_summary(session, review),
        signal=detail,
        false_positive_risks=false_positive_risks(detail),
        decision_card_preview=decision_card_preview(detail),
        thesis_override=review.thesis_override,
        opportunity_override=review.opportunity_override_json,
        evidence_selection=review.evidence_selection_json,
        comment_relevance=(
            DemandIntelligenceService(session, settings).relevance_for_topic(
                str(detail.topic["id"])
            )
            if settings.feature_comment_topic_relevance
            else []
        ),
        audit_history=review_audit_history(session, review.id),
    )


@app.get(
    "/api/v1/admin/review/signals",
    response_model=SignalReviewQueueResponse,
)
def admin_signal_review_queue(
    workspace_id: str,
    session: DbSession,
    status: str | None = Query(default=None),
    source: str | None = Query(default=None, pattern="^(live|demo)$"),
) -> SignalReviewQueueResponse:
    _require_review_queue()
    return list_signal_reviews(
        session,
        workspace_id,
        status=status,
        source_kind=source,
    )


@app.get(
    "/api/v1/admin/review/signals/{signal_id}",
    response_model=SignalReviewDetail,
)
def admin_signal_review_detail(
    signal_id: str,
    workspace_id: str,
    session: DbSession,
) -> SignalReviewDetail:
    _require_review_queue()
    return _admin_review_detail(session, workspace_id, signal_id)


@app.post(
    "/api/v1/admin/review/signals/{signal_id}/actions",
    response_model=SignalReviewEventResponse,
)
def admin_signal_review_action(
    signal_id: str,
    workspace_id: str,
    payload: SignalReviewActionCreate,
    session: DbSession,
) -> SignalReviewEventResponse:
    _require_review_queue()
    return apply_review_action(session, workspace_id, signal_id, payload)


def _review_action_with_type(
    session: Session,
    workspace_id: str,
    signal_id: str,
    payload: SignalReviewActionCreate,
    action: str,
) -> SignalReviewEventResponse:
    return apply_review_action(
        session,
        workspace_id,
        signal_id,
        payload.model_copy(update={"action": action}),
    )


@app.post(
    "/api/v1/admin/review/signals/{signal_id}/approve",
    response_model=SignalReviewEventResponse,
)
def admin_signal_review_approve(
    signal_id: str,
    workspace_id: str,
    payload: SignalReviewActionCreate,
    session: DbSession,
) -> SignalReviewEventResponse:
    _require_review_queue()
    return _review_action_with_type(
        session,
        workspace_id,
        signal_id,
        payload,
        "approve",
    )


@app.post(
    "/api/v1/admin/review/signals/{signal_id}/reject",
    response_model=SignalReviewEventResponse,
)
def admin_signal_review_reject(
    signal_id: str,
    workspace_id: str,
    payload: SignalReviewActionCreate,
    session: DbSession,
) -> SignalReviewEventResponse:
    _require_review_queue()
    return _review_action_with_type(
        session,
        workspace_id,
        signal_id,
        payload,
        "reject",
    )


@app.post(
    "/api/v1/admin/review/signals/{signal_id}/request-split",
    response_model=SignalReviewEventResponse,
)
def admin_signal_review_split(
    signal_id: str,
    workspace_id: str,
    payload: SignalReviewActionCreate,
    session: DbSession,
) -> SignalReviewEventResponse:
    _require_review_queue()
    return _review_action_with_type(
        session,
        workspace_id,
        signal_id,
        payload,
        "request_split",
    )


@app.post(
    "/api/v1/admin/review/signals/{signal_id}/request-merge",
    response_model=SignalReviewEventResponse,
)
def admin_signal_review_merge(
    signal_id: str,
    workspace_id: str,
    payload: SignalReviewActionCreate,
    session: DbSession,
) -> SignalReviewEventResponse:
    _require_review_queue()
    return _review_action_with_type(
        session,
        workspace_id,
        signal_id,
        payload,
        "request_merge",
    )


def _require_feedback_evaluation() -> None:
    if not settings.feature_feedback_evaluation:
        raise HTTPException(404, "Feedback evaluation is disabled")


def _evaluation_label_response(row: EvaluationLabel) -> EvaluationLabelResponse:
    return EvaluationLabelResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        topic_id=row.topic_id,
        signal_id=row.signal_id,
        reviewer_id=row.reviewer_id,
        as_of=row.as_of,
        label=row.label,
        additional_labels=row.additional_labels_json,
        evidence_snapshot=row.evidence_snapshot_json,
        notes=row.notes,
        model_versions=row.model_versions_json,
        label_version=row.label_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.get(
    "/api/v1/admin/evaluation/candidates",
    response_model=EvaluationCandidateList,
)
def evaluation_candidates(
    session: DbSession,
    source: str | None = Query(default=None, pattern="^(live|demo)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> EvaluationCandidateList:
    _require_feedback_evaluation()
    filters = [Topic.source_kind == source] if source else []
    total = int(session.scalar(select(func.count(Topic.id)).where(*filters)) or 0)
    topics = list(
        session.scalars(
            select(Topic)
            .where(*filters)
            .order_by(desc(Topic.first_observed_at), Topic.id)
            .offset(offset)
            .limit(limit)
        )
    )
    items: list[EvaluationCandidate] = []
    reviewed_total = int(
        session.scalar(
            select(func.count(func.distinct(EvaluationLabel.topic_id)))
            .join(Topic, Topic.id == EvaluationLabel.topic_id)
            .where(*filters)
        )
        or 0
    )
    for topic in topics:
        signal = session.scalar(
            select(Signal)
            .where(Signal.topic_id == topic.id)
            .order_by(desc(Signal.generated_at))
            .limit(1)
        )
        evaluation = session.scalar(
            select(EvaluationLabel)
            .where(EvaluationLabel.topic_id == topic.id)
            .order_by(desc(EvaluationLabel.updated_at), desc(EvaluationLabel.id))
            .limit(1)
        )
        evidence_videos = int(
            session.scalar(
                select(func.count(TopicVideoMembership.video_id)).where(
                    TopicVideoMembership.topic_id == topic.id
                )
            )
            or 0
        )
        items.append(
            EvaluationCandidate(
                topic_id=topic.id,
                topic_label=topic.canonical_label,
                source_kind=topic.source_kind,
                lifecycle_stage=topic.lifecycle_stage,
                specificity_score=topic.specificity_score,
                signal_id=signal.id if signal is not None else None,
                signal_score=signal.score if signal is not None else None,
                evidence_videos=evidence_videos,
                reviewed=evaluation is not None,
                evaluation=(
                    _evaluation_label_response(evaluation) if evaluation is not None else None
                ),
            )
        )
    return EvaluationCandidateList(
        items=items,
        total=total,
        reviewed=reviewed_total,
        primary_labels=list(PRIMARY_LABELS),
        additional_labels=list(ADDITIONAL_LABELS),
    )


@app.post(
    "/api/v1/admin/evaluation/topics/{topic_id}/label",
    response_model=EvaluationLabelResponse,
)
def label_evaluation_topic(
    topic_id: str,
    payload: EvaluationLabelCreate,
    session: DbSession,
) -> EvaluationLabelResponse:
    _require_feedback_evaluation()
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "Topic not found")
    resolved_reviewer_id = (
        workspace_reviewer(session, payload.workspace_id)[0]
        if payload.workspace_id
        else session.scalar(select(User.id).order_by(User.id).limit(1))
    )
    if resolved_reviewer_id is None:
        raise HTTPException(404, "Reviewer not found")
    reviewer_id = resolved_reviewer_id
    existing = session.scalar(
        select(EvaluationLabel)
        .where(
            EvaluationLabel.topic_id == topic_id,
            EvaluationLabel.reviewer_id == reviewer_id,
        )
        .order_by(desc(EvaluationLabel.updated_at), desc(EvaluationLabel.id))
        .limit(1)
    )
    now = datetime.now(tz=UTC)
    if existing is None:
        as_of = payload.as_of or now
        evidence_snapshot = build_label_evidence_snapshot(
            session,
            topic_id=topic_id,
            as_of=as_of,
        )
        signal_payload = evidence_snapshot.get("signal")
        signal_id = (
            str(signal_payload["id"])
            if isinstance(signal_payload, dict) and signal_payload.get("id")
            else None
        )
        if payload.workspace_id and signal_id:
            ranked_signal_ids = list(
                session.scalars(
                    select(Signal.id)
                    .join(
                        WorkspaceSignalScore,
                        WorkspaceSignalScore.signal_id == Signal.id,
                    )
                    .where(
                        WorkspaceSignalScore.workspace_id == payload.workspace_id,
                        WorkspaceSignalScore.calculated_at <= as_of,
                        Signal.generated_at <= as_of,
                    )
                    .order_by(desc(Signal.score), Signal.id)
                )
            )
            if signal_id in ranked_signal_ids:
                evidence_snapshot["signal_rank"] = ranked_signal_ids.index(signal_id) + 1
        existing = EvaluationLabel(
            id=str(uuid4()),
            workspace_id=payload.workspace_id,
            topic_id=topic_id,
            signal_id=signal_id,
            reviewer_id=reviewer_id,
            as_of=as_of,
            label=payload.label,
            additional_labels_json=list(dict.fromkeys(payload.additional_labels)),
            evidence_snapshot_json=evidence_snapshot,
            notes=payload.notes,
            model_versions_json={
                **code_model_versions(),
                "topic_clustering_observed": topic.clustering_version,
                "signal_evidence_observed": (
                    str(signal_payload.get("evidence_version", ""))
                    if isinstance(signal_payload, dict)
                    else ""
                ),
            },
            label_version=LABEL_VERSION,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.label = payload.label
        existing.additional_labels_json = list(dict.fromkeys(payload.additional_labels))
        existing.notes = payload.notes
        existing.updated_at = now
    session.commit()
    session.refresh(existing)
    return _evaluation_label_response(existing)


@app.get(
    "/api/v1/admin/evaluation/report",
    response_model=EvaluationReportResponse,
)
def evaluation_report(
    session: DbSession,
    workspace_id: str | None = Query(default=None),
) -> EvaluationReportResponse:
    _require_feedback_evaluation()
    label_query = select(EvaluationLabel)
    action_query = select(SignalAction)
    if workspace_id:
        label_query = label_query.where(EvaluationLabel.workspace_id == workspace_id)
        action_query = action_query.where(SignalAction.workspace_id == workspace_id)
    labels = list(session.scalars(label_query))
    actions = list(session.scalars(action_query))
    report = build_evaluation_report(labels)
    action_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for action in actions:
        action_counts[action.action] = action_counts.get(action.action, 0) + 1
        if action.reason:
            reason_counts[action.reason] = reason_counts.get(action.reason, 0) + 1
    return EvaluationReportResponse(
        **report,
        decision_feedback={
            "total": len(actions),
            "action_counts": dict(sorted(action_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
            "comments": sum(bool(action.comment) for action in actions),
            "feedback_version": FEEDBACK_VERSION,
        },
    )


@app.get("/api/v1/admin/evaluation/export")
def export_evaluation_labels(
    session: DbSession,
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
    workspace_id: str | None = Query(default=None),
) -> Response:
    _require_feedback_evaluation()
    query = select(EvaluationLabel)
    if workspace_id:
        query = query.where(EvaluationLabel.workspace_id == workspace_id)
    records = evaluation_export_records(list(session.scalars(query)))
    content = records_as_jsonl(records) if format == "jsonl" else records_as_csv(records)
    media_type = "application/x-ndjson" if format == "jsonl" else "text/csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="earlysignal-evaluation.{format}"'},
    )


@app.get("/api/v1/admin/evaluation/feedback/export")
def export_decision_feedback(
    session: DbSession,
    format: str = Query(default="csv", pattern="^(jsonl|csv)$"),
    workspace_id: str | None = Query(default=None),
) -> Response:
    _require_feedback_evaluation()
    query = select(SignalAction)
    if workspace_id:
        query = query.where(SignalAction.workspace_id == workspace_id)
    records = feedback_export_records(list(session.scalars(query)))
    content = records_as_jsonl(records) if format == "jsonl" else records_as_csv(records)
    media_type = "application/x-ndjson" if format == "jsonl" else "text/csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="earlysignal-feedback.{format}"'},
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/actions",
    response_model=SignalActionResponse,
    status_code=201,
)
def create_signal_action(
    workspace_id: str,
    signal_id: str,
    payload: SignalActionCreate,
    session: DbSession,
) -> SignalActionResponse:
    if session.get(Signal, signal_id) is None:
        raise HTTPException(404, "Signal not found")
    if settings.feature_signal_review_queue and not signal_is_visible(
        session,
        workspace_id,
        signal_id,
    ):
        raise HTTPException(404, "Signal not found")
    user_id = session.scalar(
        select(WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.role)
        .limit(1)
    )
    if user_id is None:
        raise HTTPException(404, "Workspace member not found")
    try:
        reason = (
            validate_decision_reason(payload.action, payload.reason)
            if settings.feature_feedback_evaluation
            else (payload.reason or "").strip()
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    comment = payload.comment.strip() if payload.comment else None
    action = SignalAction(
        id=str(uuid4()),
        workspace_id=workspace_id,
        signal_id=signal_id,
        user_id=user_id,
        action=payload.action,
        reason=reason,
        comment=comment,
        opportunity_id=payload.opportunity_id,
        feedback_version=FEEDBACK_VERSION,
        created_at=datetime.now(tz=UTC),
    )
    session.add(action)
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type={
            "act": "signal_act",
            "watch": "signal_watch",
            "skip": "signal_skip",
            "save": "signal_saved",
            "dismiss": "signal_dismissed",
        }[payload.action],
        event_key=f"action:{action.id}",
        signal_id=signal_id,
        metadata={
            "reason": reason or None,
            "comment": comment,
            "opportunity_id": payload.opportunity_id,
            "production_days": payload.production_days,
            "target_publish_date": (
                payload.target_publish_date.isoformat() if payload.target_publish_date else None
            ),
            "feedback_version": FEEDBACK_VERSION,
        },
        occurred_at=action.created_at,
    )
    session.commit()
    return SignalActionResponse(
        id=action.id,
        signal_id=action.signal_id,
        action=action.action,
        reason=action.reason or None,
        comment=action.comment,
        opportunity_id=action.opportunity_id,
        feedback_version=action.feedback_version,
        created_at=action.created_at,
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/briefs",
    response_model=BriefResponse,
    status_code=201,
)
def create_brief(
    workspace_id: str,
    signal_id: str,
    payload: BriefCreate,
    session: DbSession,
) -> ContentBrief:
    detail = get_signal_detail(
        session,
        workspace_id,
        signal_id,
        require_review_approval=settings.feature_signal_review_queue,
    )
    if payload.opportunity_id:
        angle_index = next(
            (
                index
                for index, angle in enumerate(detail.content_angles)
                if angle.get("opportunity_id") == payload.opportunity_id
            ),
            -1,
        )
    else:
        angle_index = payload.angle_index
    if angle_index < 0 or angle_index >= len(detail.content_angles):
        raise HTTPException(422, "Angle index is not available")
    angle = detail.content_angles[angle_index]
    workspace_score = session.get(WorkspaceSignalScore, (workspace_id, signal_id))
    signal = session.get(Signal, signal_id)
    if workspace_score is None or signal is None:
        raise HTTPException(404, "Workspace signal score not found")
    opportunity_id = str(angle.get("opportunity_id") or "") or None
    if opportunity_id:
        existing = session.scalar(
            select(ContentBrief).where(
                ContentBrief.workspace_id == workspace_id,
                ContentBrief.opportunity_id == opportunity_id,
                ContentBrief.status != "archived",
            )
        )
        if existing is not None:
            return existing
    title_directions = angle.get("title_directions", [])
    title = str(title_directions[0] if title_directions else angle["title"])
    brief = ContentBrief(
        id=str(uuid4()),
        workspace_id=workspace_id,
        signal_id=signal_id,
        channel_id=workspace_score.channel_id,
        opportunity_id=opportunity_id,
        evidence_version=f"{signal.evidence_version}:{workspace_score.fit_version}",
        status="draft",
        title=title,
        brief_json=angle,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(brief)
    session.flush()
    if settings.feature_signal_packaging:
        ensure_signal_packaging(session, brief)
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type="brief_created",
        event_key=f"brief:{brief.id}:created",
        signal_id=signal_id,
        content_brief_id=brief.id,
        metadata={
            "title": brief.title,
            "opportunity_id": brief.opportunity_id or "",
        },
        occurred_at=brief.created_at,
    )
    session.commit()
    return brief


@app.get(
    "/api/v1/workspaces/{workspace_id}/briefs",
    response_model=list[BriefResponse],
)
def briefs(workspace_id: str, session: DbSession) -> list[ContentBrief]:
    return list(
        session.scalars(
            select(ContentBrief)
            .where(ContentBrief.workspace_id == workspace_id)
            .order_by(desc(ContentBrief.updated_at))
        )
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/briefs/{brief_id}",
    response_model=BriefResponse,
)
def brief_detail(
    workspace_id: str,
    brief_id: str,
    session: DbSession,
) -> ContentBrief:
    brief = session.scalar(
        select(ContentBrief).where(
            ContentBrief.id == brief_id,
            ContentBrief.workspace_id == workspace_id,
        )
    )
    if brief is None:
        raise HTTPException(404, "Brief not found")
    return brief


@app.patch(
    "/api/v1/workspaces/{workspace_id}/briefs/{brief_id}",
    response_model=BriefResponse,
)
def update_brief(
    workspace_id: str,
    brief_id: str,
    payload: BriefUpdate,
    session: DbSession,
) -> ContentBrief:
    brief = session.scalar(
        select(ContentBrief).where(
            ContentBrief.id == brief_id,
            ContentBrief.workspace_id == workspace_id,
        )
    )
    if brief is None:
        raise HTTPException(404, "Brief not found")
    previous_status = brief.status
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(brief, field, value)
    brief.updated_at = datetime.now(tz=UTC)
    if previous_status != "in_production" and brief.status == "in_production":
        record_product_event(
            session,
            workspace_id=workspace_id,
            event_type="production_started",
            event_key=f"brief:{brief.id}:production-started",
            signal_id=brief.signal_id,
            content_brief_id=brief.id,
            metadata={"previous_status": previous_status},
            occurred_at=brief.updated_at,
        )
    session.commit()
    return brief


def _signal_packaging_response(row: SignalPackaging) -> SignalPackagingResponse:
    return SignalPackagingResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        signal_id=row.signal_id,
        opportunity_id=row.opportunity_id,
        content_brief_id=row.content_brief_id,
        packaging=row.packaging_json,
        evidence_ids=row.evidence_ids_json,
        regeneration_counts=row.regeneration_counts_json,
        packaging_version=row.packaging_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _selected_packaging(
    session: Session,
    *,
    workspace_id: str,
    signal_id: str,
    opportunity_id: str,
) -> SignalPackaging:
    brief = session.scalar(
        select(ContentBrief).where(
            ContentBrief.workspace_id == workspace_id,
            ContentBrief.signal_id == signal_id,
            ContentBrief.opportunity_id == opportunity_id,
            ContentBrief.status != "archived",
        )
    )
    if brief is None:
        raise HTTPException(404, "Select this opportunity and create a brief first")
    try:
        row = ensure_signal_packaging(session, brief)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    session.commit()
    return row


@app.get(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/packaging",
    response_model=SignalPackagingResponse,
)
def signal_packaging(
    workspace_id: str,
    signal_id: str,
    session: DbSession,
    opportunity_id: str = Query(min_length=36, max_length=36),
) -> SignalPackagingResponse:
    if not settings.feature_signal_packaging:
        raise HTTPException(404, "Signal packaging is disabled")
    row = _selected_packaging(
        session,
        workspace_id=workspace_id,
        signal_id=signal_id,
        opportunity_id=opportunity_id,
    )
    return _signal_packaging_response(row)


@app.post(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/packaging/regenerate",
    response_model=SignalPackagingResponse,
)
def regenerate_packaging(
    workspace_id: str,
    signal_id: str,
    opportunity_id: str,
    payload: SignalPackagingRegenerate,
    session: DbSession,
) -> SignalPackagingResponse:
    if not settings.feature_signal_packaging:
        raise HTTPException(404, "Signal packaging is disabled")
    row = _selected_packaging(
        session,
        workspace_id=workspace_id,
        signal_id=signal_id,
        opportunity_id=opportunity_id,
    )
    regenerate_signal_packaging(session, row, payload.section)
    session.commit()
    return _signal_packaging_response(row)


@app.post(
    "/api/v1/workspaces/{workspace_id}/signals/{signal_id}/packaging/copy",
    status_code=204,
)
def record_packaging_copy(
    workspace_id: str,
    signal_id: str,
    opportunity_id: str,
    payload: SignalPackagingCopyEvent,
    session: DbSession,
) -> Response:
    if not settings.feature_signal_packaging:
        raise HTTPException(404, "Signal packaging is disabled")
    row = _selected_packaging(
        session,
        workspace_id=workspace_id,
        signal_id=signal_id,
        opportunity_id=opportunity_id,
    )
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type="packaging_copy",
        event_key=(
            f"packaging:{row.id}:copy:{payload.section}:"
            f"{payload.item_index if payload.item_index is not None else 'all'}:{uuid4()}"
        ),
        signal_id=signal_id,
        content_brief_id=row.content_brief_id,
        metadata={
            "section": payload.section,
            "item_index": (payload.item_index if payload.item_index is not None else -1),
            "packaging_version": row.packaging_version,
        },
    )
    session.commit()
    return Response(status_code=204)


@app.get(
    "/api/v1/workspaces/{workspace_id}/outcomes",
    response_model=list[OutcomeResponse],
)
def outcomes(workspace_id: str, session: DbSession) -> list[PublishedOutcome]:
    return list(
        session.scalars(
            select(PublishedOutcome)
            .where(
                PublishedOutcome.workspace_id == workspace_id,
                PublishedOutcome.link_status == "active",
            )
            .order_by(desc(PublishedOutcome.created_at))
        )
    )


@app.post(
    "/api/v1/workspaces/{workspace_id}/outcomes",
    response_model=OutcomeResponse,
    status_code=201,
)
def create_outcome(
    workspace_id: str,
    payload: OutcomeCreate,
    session: DbSession,
) -> PublishedOutcome:
    if session.get(Signal, payload.signal_id) is None:
        raise HTTPException(404, "Signal not found")
    if settings.feature_signal_review_queue and not signal_is_visible(
        session,
        workspace_id,
        payload.signal_id,
    ):
        raise HTTPException(404, "Signal not found")
    if payload.content_brief_id is not None:
        brief = session.scalar(
            select(ContentBrief).where(
                ContentBrief.id == payload.content_brief_id,
                ContentBrief.workspace_id == workspace_id,
                ContentBrief.signal_id == payload.signal_id,
            )
        )
        if brief is None:
            raise HTTPException(422, "Content brief does not match this workspace and signal")
    outcome = PublishedOutcome(
        id=str(uuid4()),
        workspace_id=workspace_id,
        signal_id=payload.signal_id,
        content_brief_id=payload.content_brief_id,
        youtube_video_id=payload.youtube_video_id,
        published_at=payload.published_at,
        baseline_definition=payload.baseline_definition,
        performance_json=payload.performance_json,
        success_status=payload.success_status,
        user_notes=payload.user_notes,
        link_status="active",
        association_version="outcome-association-v1",
        metrics_version=METRICS_MODEL_VERSION,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(outcome)
    session.flush()
    if settings.feature_signal_review_queue:
        record_review_published(
            session,
            workspace_id,
            payload.signal_id,
            outcome_id=outcome.id,
            occurred_at=outcome.created_at,
        )
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type=(
            "outcome_successful" if outcome.success_status == "successful" else "outcome_linked"
        ),
        event_key=f"outcome:{outcome.id}:created",
        signal_id=outcome.signal_id,
        content_brief_id=outcome.content_brief_id,
        outcome_id=outcome.id,
        metadata={
            "youtube_video_id": outcome.youtube_video_id,
            "success_status": outcome.success_status,
        },
        occurred_at=outcome.created_at,
    )
    session.commit()
    return outcome


def _outcome_suggestion_response(
    session: Session,
    suggestion: OutcomeSuggestion,
) -> OutcomeSuggestionResponse:
    video = session.get(YoutubeVideo, suggestion.video_id)
    brief = session.get(ContentBrief, suggestion.selected_brief_id or suggestion.suggested_brief_id)
    if video is None or brief is None:
        raise HTTPException(500, "Outcome suggestion evidence is incomplete")
    alternatives = list(
        session.scalars(
            select(ContentBrief)
            .where(
                ContentBrief.workspace_id == suggestion.workspace_id,
                ContentBrief.channel_id == video.channel_id,
                ContentBrief.status.in_(("draft", "approved", "published")),
                ContentBrief.id != brief.id,
            )
            .order_by(desc(ContentBrief.updated_at))
            .limit(5)
        )
    )
    return OutcomeSuggestionResponse(
        id=suggestion.id,
        workspace_id=suggestion.workspace_id,
        status=suggestion.status,
        youtube_video_id=video.youtube_video_id,
        video_title=video.title,
        video_url=video.canonical_url,
        published_at=video.published_at,
        signal_id=suggestion.signal_id,
        suggested_brief_id=suggestion.suggested_brief_id,
        selected_brief_id=suggestion.selected_brief_id,
        brief_title=brief.title,
        match_confidence=suggestion.match_confidence,
        reason_codes=suggestion.reason_codes_json,
        match_features=suggestion.match_features_json,
        baseline=suggestion.baseline_json,
        metrics=suggestion.metrics_json,
        model_version=suggestion.model_version,
        outcome_id=suggestion.outcome_id,
        alternatives=[
            {
                "id": item.id,
                "signal_id": item.signal_id,
                "title": item.title,
            }
            for item in alternatives
        ],
        detected_at=suggestion.detected_at,
        decided_at=suggestion.decided_at,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/outcomes/suggestions",
    response_model=list[OutcomeSuggestionResponse],
)
def outcome_suggestions(
    workspace_id: str,
    session: DbSession,
    status: str = Query(
        default="suggested", pattern="^(suggested|confirmed|rejected|unlinked|all)$"
    ),
) -> list[OutcomeSuggestionResponse]:
    if not settings.feature_outcome_suggestions:
        return []
    statement = select(OutcomeSuggestion).where(OutcomeSuggestion.workspace_id == workspace_id)
    if status != "all":
        statement = statement.where(OutcomeSuggestion.status == status)
    rows = list(session.scalars(statement.order_by(desc(OutcomeSuggestion.detected_at))))
    return [_outcome_suggestion_response(session, row) for row in rows]


@app.post(
    "/api/v1/workspaces/{workspace_id}/outcomes/suggestions/{suggestion_id}/confirm",
    response_model=OutcomeSuggestionResponse,
)
def confirm_outcome_suggestion(
    workspace_id: str,
    suggestion_id: str,
    payload: OutcomeSuggestionDecision,
    session: DbSession,
) -> OutcomeSuggestionResponse:
    if not settings.feature_outcome_suggestions:
        raise HTTPException(404, "Outcome suggestions are disabled")
    suggestion = session.scalar(
        select(OutcomeSuggestion).where(
            OutcomeSuggestion.id == suggestion_id,
            OutcomeSuggestion.workspace_id == workspace_id,
        )
    )
    if suggestion is None:
        raise HTTPException(404, "Outcome suggestion not found")
    if suggestion.status == "confirmed":
        return _outcome_suggestion_response(session, suggestion)
    if suggestion.status != "suggested":
        raise HTTPException(409, "Outcome suggestion is already resolved")
    brief_id = payload.content_brief_id or suggestion.suggested_brief_id
    brief = session.scalar(
        select(ContentBrief).where(
            ContentBrief.id == brief_id,
            ContentBrief.workspace_id == workspace_id,
            ContentBrief.status != "archived",
        )
    )
    video = session.get(YoutubeVideo, suggestion.video_id)
    if brief is None or video is None or brief.channel_id != video.channel_id:
        raise HTTPException(422, "Selected brief cannot be linked to this upload")
    now = datetime.now(tz=UTC)
    outcome = PublishedOutcome(
        id=str(uuid4()),
        workspace_id=workspace_id,
        signal_id=brief.signal_id,
        content_brief_id=brief.id,
        youtube_video_id=video.youtube_video_id,
        published_at=video.published_at,
        baseline_definition=(
            "Median performance of comparable owned uploads: same content "
            "type, similar duration, topic-family proximity, sponsorship class, "
            "and the previous six months."
        ),
        performance_json=suggestion.metrics_json,
        success_status="pending",
        user_notes="Automatically associated after user confirmation.",
        link_status="active",
        association_version=suggestion.model_version,
        metrics_version=METRICS_MODEL_VERSION,
        created_at=now,
        updated_at=now,
    )
    session.add(outcome)
    session.flush()
    suggestion.signal_id = brief.signal_id
    suggestion.selected_brief_id = brief.id
    suggestion.outcome_id = outcome.id
    suggestion.status = "confirmed"
    suggestion.decided_at = now
    suggestion.updated_at = now
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type="signal_outcome_confirmed",
        event_key=f"outcome-suggestion:{suggestion.id}:confirmed",
        signal_id=brief.signal_id,
        content_brief_id=brief.id,
        outcome_id=outcome.id,
        metadata={
            "youtube_video_id": video.youtube_video_id,
            "association_model": suggestion.model_version,
            "alternative_selected": brief.id != suggestion.suggested_brief_id,
        },
        occurred_at=now,
    )
    session.commit()
    OutcomeAutomationService(session).run(workspace_id)
    session.refresh(suggestion)
    return _outcome_suggestion_response(session, suggestion)


@app.post(
    "/api/v1/workspaces/{workspace_id}/outcomes/suggestions/{suggestion_id}/reject",
    response_model=OutcomeSuggestionResponse,
)
def reject_outcome_suggestion(
    workspace_id: str,
    suggestion_id: str,
    session: DbSession,
) -> OutcomeSuggestionResponse:
    if not settings.feature_outcome_suggestions:
        raise HTTPException(404, "Outcome suggestions are disabled")
    suggestion = session.scalar(
        select(OutcomeSuggestion).where(
            OutcomeSuggestion.id == suggestion_id,
            OutcomeSuggestion.workspace_id == workspace_id,
        )
    )
    if suggestion is None:
        raise HTTPException(404, "Outcome suggestion not found")
    if suggestion.status == "rejected":
        return _outcome_suggestion_response(session, suggestion)
    if suggestion.status != "suggested":
        raise HTTPException(409, "Outcome suggestion is already resolved")
    now = datetime.now(tz=UTC)
    suggestion.status = "rejected"
    suggestion.decided_at = now
    suggestion.updated_at = now
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type="outcome_suggestion_rejected",
        event_key=f"outcome-suggestion:{suggestion.id}:rejected",
        signal_id=suggestion.signal_id,
        content_brief_id=suggestion.suggested_brief_id,
        metadata={"youtube_video_id": suggestion.video_id},
        occurred_at=now,
    )
    session.commit()
    return _outcome_suggestion_response(session, suggestion)


@app.patch(
    "/api/v1/workspaces/{workspace_id}/outcomes/{outcome_id}/association",
    response_model=OutcomeResponse,
)
def correct_outcome_association(
    workspace_id: str,
    outcome_id: str,
    payload: OutcomeCorrection,
    session: DbSession,
) -> PublishedOutcome:
    outcome = session.scalar(
        select(PublishedOutcome).where(
            PublishedOutcome.id == outcome_id,
            PublishedOutcome.workspace_id == workspace_id,
            PublishedOutcome.link_status == "active",
        )
    )
    brief = session.scalar(
        select(ContentBrief).where(
            ContentBrief.id == payload.content_brief_id,
            ContentBrief.workspace_id == workspace_id,
            ContentBrief.status != "archived",
        )
    )
    if outcome is None:
        raise HTTPException(404, "Outcome not found")
    if brief is None:
        raise HTTPException(422, "Brief not found")
    outcome.content_brief_id = brief.id
    outcome.signal_id = brief.signal_id
    outcome.association_version = "outcome-association-v1:user-corrected"
    if payload.user_notes is not None:
        outcome.user_notes = payload.user_notes
    outcome.updated_at = datetime.now(tz=UTC)
    session.commit()
    OutcomeAutomationService(session).run(workspace_id)
    session.refresh(outcome)
    return outcome


@app.post(
    "/api/v1/workspaces/{workspace_id}/outcomes/{outcome_id}/unlink",
    response_model=OutcomeResponse,
)
def unlink_outcome(
    workspace_id: str,
    outcome_id: str,
    session: DbSession,
) -> PublishedOutcome:
    outcome = session.scalar(
        select(PublishedOutcome).where(
            PublishedOutcome.id == outcome_id,
            PublishedOutcome.workspace_id == workspace_id,
        )
    )
    if outcome is None:
        raise HTTPException(404, "Outcome not found")
    if outcome.link_status == "unlinked":
        return outcome
    now = datetime.now(tz=UTC)
    outcome.link_status = "unlinked"
    outcome.updated_at = now
    suggestion = session.scalar(
        select(OutcomeSuggestion).where(OutcomeSuggestion.outcome_id == outcome.id)
    )
    if suggestion is not None:
        suggestion.status = "unlinked"
        suggestion.updated_at = now
    record_product_event(
        session,
        workspace_id=workspace_id,
        event_type="outcome_unlinked",
        event_key=f"outcome:{outcome.id}:unlinked",
        signal_id=outcome.signal_id,
        content_brief_id=outcome.content_brief_id,
        outcome_id=outcome.id,
        metadata={"association_version": outcome.association_version},
        occurred_at=now,
    )
    session.commit()
    return outcome


def _provider_response(session: Session, row: ProviderHealth) -> ProviderHealthResponse:
    now = datetime.now(tz=UTC)
    rate = (row.success_count / row.request_count * 100) if row.request_count else 0
    if not row.enabled:
        status = "Disabled"
    elif row.circuit_state == "open":
        status = "Circuit open"
    else:
        status = "Healthy" if rate >= 98 else "Degraded" if rate >= 90 else "Unhealthy"
    request_count_hour = int(
        session.scalar(
            select(func.count(ProviderFetch.id)).where(
                ProviderFetch.provider == row.provider,
                ProviderFetch.capability == row.capability,
                ProviderFetch.started_at >= now - timedelta(hours=1),
            )
        )
        or 0
    )
    request_count_day = int(
        session.scalar(
            select(func.count(ProviderFetch.id)).where(
                ProviderFetch.provider == row.provider,
                ProviderFetch.capability == row.capability,
                ProviderFetch.started_at >= now - timedelta(days=1),
            )
        )
        or 0
    )
    budget = session.get(ProviderBudget, (row.provider, row.capability))
    selected_decisions = list(
        session.scalars(
            select(ProviderRoutingDecision).where(
                ProviderRoutingDecision.capability == row.capability,
                ProviderRoutingDecision.selected_provider == row.provider,
                ProviderRoutingDecision.created_at >= now - timedelta(days=1),
            )
        )
    )
    fallback_rate = (
        sum(item.fallback_used for item in selected_decisions) / len(selected_decisions) * 100
        if selected_decisions
        else 0
    )
    return ProviderHealthResponse(
        provider=row.provider,
        capability=row.capability,
        enabled=row.enabled,
        priority=row.priority,
        status=status,
        circuit_state=row.circuit_state,
        consecutive_failures=row.consecutive_failures,
        circuit_opened_at=row.circuit_opened_at,
        half_open_probe_at=row.half_open_probe_at,
        disabled_reason=row.disabled_reason,
        request_count=row.request_count,
        request_count_hour=request_count_hour,
        request_count_day=request_count_day,
        success_rate=round(rate, 1),
        error_rate=round(100 - rate, 1) if row.request_count else 0,
        p50_latency_ms=row.p50_latency_ms,
        p95_latency_ms=row.p95_latency_ms,
        estimated_cost=row.estimated_cost,
        spent_today_usd=round(budget.spent_today_usd, 4) if budget else 0,
        daily_limit_usd=budget.daily_limit_usd if budget else 0,
        spent_month_usd=round(budget.spent_month_usd, 4) if budget else 0,
        monthly_limit_usd=budget.monthly_limit_usd if budget else 0,
        fallback_rate=round(fallback_rate, 1),
        last_error=row.last_error,
        updated_at=row.updated_at,
        demo=row.provider.startswith("mock_"),
    )


@app.get("/api/v1/admin/providers", response_model=list[ProviderHealthResponse])
def providers(session: DbSession) -> list[ProviderHealthResponse]:
    rows = list(
        session.scalars(
            select(ProviderHealth).order_by(ProviderHealth.priority, ProviderHealth.capability)
        )
    )
    return [_provider_response(session, row) for row in rows]


@app.patch(
    "/api/v1/admin/providers/{provider}/{capability}",
    response_model=ProviderHealthResponse,
)
def update_provider(
    provider: str,
    capability: str,
    payload: ProviderUpdate,
    session: DbSession,
) -> ProviderHealthResponse:
    row = session.get(ProviderHealth, (provider, capability))
    if row is None:
        raise HTTPException(404, "Provider capability not found")
    if payload.enabled is not None:
        row.enabled = payload.enabled
        row.manual_disabled_at = None if payload.enabled else datetime.now(tz=UTC)
        row.disabled_reason = None if payload.enabled else "Disabled by administrator"
    if payload.priority is not None:
        row.priority = payload.priority
    row.updated_at = datetime.now(tz=UTC)
    session.commit()
    return _provider_response(session, row)


@app.post(
    "/api/v1/admin/providers/{provider}/{capability}/reset-circuit",
    response_model=ProviderHealthResponse,
)
def reset_provider_circuit(
    provider: str,
    capability: str,
    session: DbSession,
) -> ProviderHealthResponse:
    row = session.get(ProviderHealth, (provider, capability))
    if row is None:
        raise HTTPException(404, "Provider capability not found")
    row.circuit_state = "closed"
    row.consecutive_failures = 0
    row.circuit_opened_at = None
    row.half_open_probe_at = None
    row.updated_at = datetime.now(tz=UTC)
    session.add(
        ProviderOperationsEvent(
            id=str(uuid4()),
            event_type="circuit_reset",
            severity="info",
            capability=capability,
            provider=provider,
            message=f"Circuit reset for {provider}/{capability}",
            context_json={"actor": "admin"},
            created_at=datetime.now(tz=UTC),
        )
    )
    session.commit()
    return _provider_response(session, row)


@app.post("/api/v1/admin/providers/health-check", response_model=list[ProviderHealthResponse])
def run_health_check(session: DbSession) -> list[ProviderHealthResponse]:
    rows = list(session.scalars(select(ProviderHealth)))
    return [_provider_response(session, row) for row in rows]


@app.get(
    "/api/v1/admin/provider-routing/metrics",
    response_model=ProviderRoutingMetrics,
)
def provider_routing_metrics(session: DbSession) -> ProviderRoutingMetrics:
    since = datetime.now(tz=UTC) - timedelta(days=1)
    decisions = list(
        session.scalars(
            select(ProviderRoutingDecision).where(ProviderRoutingDecision.created_at >= since)
        )
    )
    skipped = [item for decision in decisions for item in decision.skipped_providers_json]
    successful = sum(item.status == "success" for item in decisions)
    fallback_count = sum(item.fallback_used for item in decisions)
    return ProviderRoutingMetrics(
        decisions=len(decisions),
        successful=successful,
        failed=sum(item.status == "failed" for item in decisions),
        fallback_count=fallback_count,
        fallback_rate=round(fallback_count / successful * 100, 1) if successful else 0,
        open_circuits=int(
            session.scalar(
                select(func.count())
                .select_from(ProviderHealth)
                .where(ProviderHealth.circuit_state == "open")
            )
            or 0
        ),
        disabled_capabilities=int(
            session.scalar(
                select(func.count())
                .select_from(ProviderHealth)
                .where(ProviderHealth.enabled.is_(False))
            )
            or 0
        ),
        budget_skips=sum(
            str(item.get("reason", "")).endswith("budget_exhausted") for item in skipped
        ),
    )


@app.get(
    "/api/v1/admin/provider-routing/decisions",
    response_model=list[ProviderRoutingDecisionResponse],
)
def provider_routing_decisions(
    session: DbSession,
    limit: int = Query(default=30, ge=1, le=200),
) -> list[ProviderRoutingDecisionResponse]:
    rows = list(
        session.scalars(
            select(ProviderRoutingDecision)
            .order_by(desc(ProviderRoutingDecision.created_at))
            .limit(limit)
        )
    )
    return [
        ProviderRoutingDecisionResponse(
            id=row.id,
            capability=row.capability,
            operation_key=row.operation_key,
            selected_provider=row.selected_provider,
            attempted_providers=row.attempted_providers_json,
            skipped_providers=row.skipped_providers_json,
            fallback_used=row.fallback_used,
            status=row.status,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.get(
    "/api/v1/admin/provider-routing/events",
    response_model=list[ProviderOperationsEventResponse],
)
def provider_operations_events(
    session: DbSession,
    limit: int = Query(default=30, ge=1, le=200),
) -> list[ProviderOperationsEventResponse]:
    rows = list(
        session.scalars(
            select(ProviderOperationsEvent)
            .order_by(desc(ProviderOperationsEvent.created_at))
            .limit(limit)
        )
    )
    return [
        ProviderOperationsEventResponse(
            id=row.id,
            event_type=row.event_type,
            severity=row.severity,
            capability=row.capability,
            provider=row.provider,
            message=row.message,
            context=row.context_json,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.get(
    "/api/v1/admin/operations/readiness",
    response_model=OperationsReadinessResponse,
)
def operations_readiness(session: DbSession) -> OperationsReadinessResponse:
    now = datetime.now(tz=UTC)
    alerts: list[dict[str, object]] = []
    dead_letters: list[dict[str, object]] = []
    stale_topic_runs = int(
        session.scalar(
            select(func.count(TopicPipelineRun.id)).where(
                TopicPipelineRun.status == "running",
                TopicPipelineRun.started_at
                < now - timedelta(minutes=max(1, settings.topic_pipeline_stale_minutes)),
            )
        )
        or 0
    )
    if stale_topic_runs:
        alerts.append(
            {
                "severity": "critical",
                "code": "topic_pipeline_stale_runs",
                "message": (f"{stale_topic_runs} topic pipeline runs exceeded the active lease."),
            }
        )

    evaluation_labels = int(session.scalar(select(func.count(EvaluationLabel.id))) or 0)
    if evaluation_labels < settings.evaluation_minimum_labels:
        alerts.append(
            {
                "severity": "warning",
                "code": "evaluation_sample_insufficient",
                "message": (
                    f"Only {evaluation_labels}/{settings.evaluation_minimum_labels} "
                    "human quality labels are available; recommendation precision "
                    "is not release-validated."
                ),
            }
        )

    provider_rows = list(session.scalars(select(ProviderHealth)))
    ready_providers = [
        row
        for row in provider_rows
        if row.enabled and row.circuit_state != "open" and row.consecutive_failures < 3
    ]
    if provider_rows and not ready_providers:
        alerts.append(
            {
                "severity": "critical",
                "code": "providers_unavailable",
                "message": "No provider capability is currently ready.",
            }
        )
    elif len(ready_providers) < len(provider_rows):
        alerts.append(
            {
                "severity": "warning",
                "code": "providers_degraded",
                "message": (
                    f"{len(provider_rows) - len(ready_providers)} provider "
                    "capabilities are disabled or degraded."
                ),
            }
        )

    latest_signal = session.scalar(select(func.max(Signal.generated_at)))
    if latest_signal is None or now - _aware(latest_signal) > timedelta(hours=6):
        alerts.append(
            {
                "severity": "warning",
                "code": "signals_stale",
                "message": "No signal has been generated in the last six hours.",
            }
        )

    for budget in session.scalars(select(ProviderBudget)):
        daily_ratio = (
            budget.spent_today_usd / budget.daily_limit_usd if budget.daily_limit_usd else 0
        )
        monthly_ratio = (
            budget.spent_month_usd / budget.monthly_limit_usd if budget.monthly_limit_usd else 0
        )
        ratio = max(daily_ratio, monthly_ratio)
        if ratio >= 0.8:
            alerts.append(
                {
                    "severity": "critical" if ratio >= 0.95 else "warning",
                    "code": "provider_budget",
                    "message": (
                        f"{budget.provider}/{budget.capability} has used "
                        f"{round(ratio * 100)}% of its active budget."
                    ),
                }
            )

    failed_snapshots = list(
        session.scalars(
            select(VideoSnapshotJob)
            .where(VideoSnapshotJob.status == "failed")
            .order_by(desc(VideoSnapshotJob.updated_at))
            .limit(20)
        )
    )
    active_failure_count = len(failed_snapshots)
    dead_letters.extend(
        {
            "job_type": "snapshot",
            "id": row.id,
            "failed_at": _aware(row.updated_at),
            "error_code": row.error_code,
            "error_message": row.error_message,
            "attempt_count": row.attempt_count,
        }
        for row in failed_snapshots
    )

    pipeline_models: list[tuple[str, Any]] = [
        ("discovery", DiscoveryRun),
        ("topic", TopicPipelineRun),
        ("demand", DemandPipelineRun),
        ("transcript", TranscriptPipelineRun),
    ]
    pipeline: dict[str, object] = {}
    for name, model in pipeline_models:
        latest = session.scalar(select(model).order_by(desc(model.started_at)).limit(1))
        failed = list(
            session.scalars(
                select(model)
                .where(model.status == "failed")
                .order_by(desc(model.started_at))
                .limit(10)
            )
        )
        pipeline[name] = {
            "status": latest.status if latest is not None else "not_run",
            "last_started_at": (_aware(latest.started_at) if latest is not None else None),
            "last_completed_at": (
                _aware(latest.completed_at)
                if latest is not None and latest.completed_at is not None
                else None
            ),
            "failed_runs": len(failed),
        }
        if latest is not None and latest.status == "failed":
            active_failure_count += 1
        dead_letters.extend(
            {
                "job_type": name,
                "id": row.id,
                "failed_at": _aware(row.completed_at or row.started_at),
                "error_code": row.error_code,
                "error_message": row.error_message,
                "attempt_count": None,
            }
            for row in failed
        )

    dead_letters.sort(
        key=lambda item: cast(datetime, item["failed_at"]),
        reverse=True,
    )
    dead_letters = dead_letters[:30]
    if active_failure_count:
        alerts.append(
            {
                "severity": "warning",
                "code": "dead_letters",
                "message": f"{active_failure_count} current jobs need review.",
            }
        )

    raw_payload_path = Path(settings.raw_payload_directory)
    if not raw_payload_path.exists():
        alerts.append(
            {
                "severity": "warning",
                "code": "raw_payload_storage",
                "message": "Raw payload storage directory is not available.",
            }
        )

    backup_path = Path("var/backups")
    backup_files = (
        sorted(
            (
                path
                for path in backup_path.iterdir()
                if path.is_file()
                and not path.name.endswith(".sha256")
                and ".pre-restore-" not in path.name
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if backup_path.exists()
        else []
    )
    latest_backup = backup_files[0] if backup_files else None
    backup_at = (
        datetime.fromtimestamp(latest_backup.stat().st_mtime, tz=UTC)
        if latest_backup is not None
        else None
    )
    backup_age_hours = (
        round((now - backup_at).total_seconds() / 3600, 1) if backup_at is not None else None
    )
    backup_healthy = backup_age_hours is not None and backup_age_hours <= 26
    if not backup_healthy:
        alerts.append(
            {
                "severity": "warning",
                "code": "backup_stale",
                "message": "No verified backup is available from the last 26 hours.",
            }
        )

    status = (
        "critical"
        if any(item["severity"] == "critical" for item in alerts)
        else "degraded"
        if alerts
        else "ready"
    )
    return OperationsReadinessResponse(
        status=status,
        checked_at=now,
        alerts=alerts,
        dead_letters=dead_letters,
        pipeline=pipeline,
        backup={
            "healthy": backup_healthy,
            "latest_file": latest_backup.name if latest_backup is not None else None,
            "created_at": backup_at,
            "age_hours": backup_age_hours,
            "checksum_present": (
                Path(f"{latest_backup}.sha256").exists() if latest_backup is not None else False
            ),
        },
    )


def _benchmark_response(row: ProviderBenchmarkRun) -> ProviderBenchmarkResponse:
    return ProviderBenchmarkResponse(
        id=row.id,
        benchmark_version=row.benchmark_version,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=row.status,
        live_case_count=row.live_case_count,
        result=row.result_json,
        recommended_priorities=row.recommended_priorities_json,
        json_path=row.json_path,
        csv_path=row.csv_path,
        markdown_path=row.markdown_path,
        error_code=row.error_code,
        error_message=row.error_message,
    )


@app.post(
    "/api/v1/admin/providers/benchmark",
    response_model=ProviderBenchmarkResponse,
)
async def run_provider_benchmark(
    session: DbSession,
    live: bool = Query(default=False),
    limit: int = Query(default=3, ge=1, le=20),
) -> ProviderBenchmarkResponse:
    row = await ProviderBenchmarkService(session, settings).run(
        live=live,
        limit=limit,
    )
    return _benchmark_response(row)


@app.get(
    "/api/v1/admin/providers/benchmark/latest",
    response_model=ProviderBenchmarkResponse,
)
def latest_provider_benchmark(session: DbSession) -> ProviderBenchmarkResponse:
    row = session.scalar(
        select(ProviderBenchmarkRun).order_by(desc(ProviderBenchmarkRun.started_at))
    )
    if row is None:
        raise HTTPException(404, "No provider benchmark has been run")
    return _benchmark_response(row)


@app.get(
    "/api/v1/admin/provider-fetches",
    response_model=list[ProviderFetchListItem],
)
def provider_fetches(session: DbSession) -> list[ProviderFetch]:
    return list(session.scalars(select(ProviderFetch).order_by(desc(ProviderFetch.started_at))))


def _read_raw_payload(uri: str) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    path = (root / uri).resolve()
    fixtures_root = (root / "fixtures" / "demo" / "raw_payloads").resolve()
    provider_root = (root / settings.raw_payload_directory).resolve()
    if not any(
        allowed == path or allowed in path.parents for allowed in (fixtures_root, provider_root)
    ):
        raise HTTPException(403, "Raw payload path is outside the configured stores")
    if not path.exists():
        raise HTTPException(404, "Raw payload not found")
    content = (
        gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz" else path.read_text()
    )
    return cast(dict[str, object], json.loads(content))


def _fetch_detail(row: ProviderFetch) -> ProviderFetchDetail:
    raw_payload = _read_raw_payload(row.raw_payload_uri)
    if row.capability == "transcripts":
        segments = raw_payload.get("segments", [])
        raw_payload = {key: value for key, value in raw_payload.items() if key != "segments"}
        raw_payload["segment_count"] = len(segments) if isinstance(segments, list) else 0
        raw_payload["text_redacted"] = True
    return ProviderFetchDetail(
        id=row.id,
        provider=row.provider,
        capability=row.capability,
        endpoint=row.endpoint,
        started_at=row.started_at,
        latency_ms=row.latency_ms,
        status=row.status,
        http_status=row.http_status,
        raw_payload_uri=row.raw_payload_uri,
        raw_payload_hash=row.raw_payload_hash,
        request_fingerprint=row.request_fingerprint,
        completed_at=row.completed_at,
        attempt_number=row.attempt_number,
        estimated_cost=row.estimated_cost,
        actual_cost=row.actual_cost,
        parser_version=row.parser_version,
        error_code=row.error_code,
        error_message=row.error_message,
        linked_entity_ids=row.linked_entity_ids,
        raw_payload=raw_payload,
    )


@app.get(
    "/api/v1/admin/provider-fetches/{fetch_id}",
    response_model=ProviderFetchDetail,
)
def provider_fetch_detail(
    fetch_id: str,
    session: DbSession,
) -> ProviderFetchDetail:
    row = session.get(ProviderFetch, fetch_id)
    if row is None:
        raise HTTPException(404, "Provider fetch not found")
    return _fetch_detail(row)


@app.post(
    "/api/v1/admin/provider-fetches/{fetch_id}/replay",
    response_model=ProviderFetchDetail,
    status_code=201,
)
def replay_provider_fetch(
    fetch_id: str,
    session: DbSession,
) -> ProviderFetchDetail:
    source = session.get(ProviderFetch, fetch_id)
    if source is None:
        raise HTTPException(404, "Provider fetch not found")
    now = datetime.now(tz=UTC)
    replay = ProviderFetch(
        id=str(uuid4()),
        provider=source.provider,
        capability=source.capability,
        endpoint=f"{source.endpoint}:replay",
        request_fingerprint=source.request_fingerprint,
        started_at=now,
        completed_at=now + timedelta(milliseconds=8),
        status="success",
        http_status=200,
        attempt_number=source.attempt_number + 1,
        latency_ms=8,
        estimated_cost=0,
        actual_cost=0,
        raw_payload_uri=source.raw_payload_uri,
        raw_payload_hash=source.raw_payload_hash,
        parser_version=source.parser_version,
        error_code=None,
        error_message=None,
        linked_entity_ids=source.linked_entity_ids,
    )
    session.add(replay)
    session.commit()
    return _fetch_detail(replay)


@app.get(
    "/api/v1/admin/discovery-queries",
    response_model=list[DiscoveryQueryResponse],
)
def discovery_queries(session: DbSession) -> list[DiscoveryQueryRecord]:
    return list(
        session.scalars(
            select(DiscoveryQueryRecord).order_by(
                DiscoveryQueryRecord.priority,
                DiscoveryQueryRecord.query,
            )
        )
    )


def _query_suggestion_response(
    row: QuerySuggestion,
) -> QuerySuggestionResponse:
    return QuerySuggestionResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        query=row.query,
        normalized_query=row.normalized_query,
        status=row.status,
        source_type=row.source_type,
        source_entity=row.source_entity,
        source_topic_id=row.source_topic_id,
        source_evidence_ids=row.source_evidence_ids_json,
        rationale=row.rationale,
        anchor_terms=row.anchor_terms_json,
        quality_reason_codes=row.quality_reason_codes_json,
        broadness_score=row.broadness_score,
        precision_score=row.precision_score,
        precision_sample_size=row.precision_sample_size,
        discovery_query_id=row.discovery_query_id,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        model_version=row.model_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.post(
    "/api/v1/admin/query-expansion/run",
    response_model=QueryExpansionRunResponse,
)
def run_query_expansion(session: DbSession) -> QueryExpansionRunResponse:
    if not settings.feature_query_expansion:
        raise HTTPException(404, "Query expansion is disabled")
    return QueryExpansionRunResponse(**QueryExpansionService(session).run().__dict__)


@app.get(
    "/api/v1/admin/query-suggestions",
    response_model=list[QuerySuggestionResponse],
)
def query_suggestions(
    session: DbSession,
    status: str = Query(
        default="all",
        pattern="^(suggested|approved|active|low_value|paused|retired|all)$",
    ),
) -> list[QuerySuggestionResponse]:
    if not settings.feature_query_expansion:
        return []
    statement = select(QuerySuggestion)
    if status != "all":
        statement = statement.where(QuerySuggestion.status == status)
    rows = list(
        session.scalars(
            statement.order_by(
                QuerySuggestion.status,
                desc(QuerySuggestion.created_at),
            )
        )
    )
    return [_query_suggestion_response(row) for row in rows]


@app.post(
    "/api/v1/admin/query-suggestions/{suggestion_id}/actions",
    response_model=QuerySuggestionResponse,
)
def transition_query_suggestion(
    suggestion_id: str,
    payload: QuerySuggestionAction,
    session: DbSession,
) -> QuerySuggestionResponse:
    if not settings.feature_query_expansion:
        raise HTTPException(404, "Query expansion is disabled")
    suggestion = session.get(QuerySuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(404, "Query suggestion not found")
    reviewer_id = (
        workspace_reviewer(session, suggestion.workspace_id)[0] if suggestion.workspace_id else None
    )
    try:
        QueryExpansionService(session).transition(
            suggestion,
            payload.action,
            reviewer_id=reviewer_id,
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return _query_suggestion_response(suggestion)


@app.post(
    "/api/v1/admin/discovery-queries",
    response_model=DiscoveryQueryResponse,
    status_code=201,
)
def create_discovery_query(
    payload: DiscoveryQueryCreate,
    session: DbSession,
) -> DiscoveryQueryRecord:
    service = IngestionService(session, settings)
    return service.create_query(**payload.model_dump())


@app.post(
    "/api/v1/admin/discovery-queries/{query_id}/run",
    response_model=IngestionRunResponse,
)
async def run_discovery_query(
    query_id: str,
    payload: RunIngestionRequest,
    session: DbSession,
) -> DiscoveryRun:
    row = session.get(DiscoveryQueryRecord, query_id)
    if row is None:
        raise HTTPException(404, "Discovery query not found")
    service = IngestionService(session, settings)
    try:
        result = await service.run_query(
            row,
            force=payload.force,
            max_results=payload.max_results,
        )
    except Exception as error:
        raise HTTPException(502, f"Ingestion failed: {error}") from error
    run = session.get(DiscoveryRun, result.run_id)
    if run is None:
        raise HTTPException(500, "Ingestion run was not persisted")
    TopicIntelligenceService(session, settings).run(force=True)
    return run


@app.get(
    "/api/v1/admin/discovery-runs",
    response_model=list[IngestionRunResponse],
)
def discovery_runs(session: DbSession) -> list[DiscoveryRun]:
    return list(
        session.scalars(select(DiscoveryRun).order_by(desc(DiscoveryRun.started_at)).limit(100))
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/channels",
    response_model=list[MonitoredChannelResponse],
)
def workspace_channels(
    workspace_id: str,
    session: DbSession,
) -> list[MonitoredChannelResponse]:
    rows = session.execute(
        select(WorkspaceChannel, YoutubeChannel)
        .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
        .where(WorkspaceChannel.workspace_id == workspace_id)
        .order_by(
            WorkspaceChannel.priority,
            WorkspaceChannel.relationship,
            YoutubeChannel.title,
        )
    ).all()
    return [
        MonitoredChannelResponse(
            workspace_id=workspace_channel.workspace_id,
            channel_id=channel.id,
            youtube_channel_id=channel.youtube_channel_id,
            title=channel.title,
            relationship=workspace_channel.relationship,
            priority=workspace_channel.priority,
            active=workspace_channel.active,
            last_ingested_at=workspace_channel.last_ingested_at,
            next_ingestion_at=workspace_channel.next_ingestion_at,
        )
        for workspace_channel, channel in rows
    ]


@app.post(
    "/api/v1/workspaces/{workspace_id}/channels",
    response_model=MonitoredChannelResponse,
    status_code=201,
)
async def add_workspace_channel(
    workspace_id: str,
    payload: WorkspaceChannelCreate,
    session: DbSession,
) -> MonitoredChannelResponse:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(404, "Workspace not found")
    service = IngestionService(session, settings)
    try:
        channel = await service.monitor_channel(
            workspace_id=workspace_id,
            youtube_channel_id=payload.youtube_channel_id,
            relationship=payload.relationship,
            priority=payload.priority,
        )
    except Exception as error:
        raise HTTPException(502, f"Channel setup failed: {error}") from error
    workspace_channel = session.get(WorkspaceChannel, (workspace_id, channel.id))
    if workspace_channel is None:
        raise HTTPException(500, "Monitored channel was not persisted")
    if payload.relationship == "owned":
        OnboardingService(session, settings).seed_reference_channels(workspace_id)
    return MonitoredChannelResponse(
        workspace_id=workspace_channel.workspace_id,
        channel_id=channel.id,
        youtube_channel_id=channel.youtube_channel_id,
        title=channel.title,
        relationship=workspace_channel.relationship,
        priority=workspace_channel.priority,
        active=workspace_channel.active,
        last_ingested_at=workspace_channel.last_ingested_at,
        next_ingestion_at=workspace_channel.next_ingestion_at,
    )


@app.patch(
    "/api/v1/workspaces/{workspace_id}/channels/{channel_id}",
    response_model=MonitoredChannelResponse,
)
def update_workspace_channel(
    workspace_id: str,
    channel_id: str,
    payload: MonitoredChannelUpdate,
    session: DbSession,
) -> MonitoredChannelResponse:
    workspace_channel = session.get(WorkspaceChannel, (workspace_id, channel_id))
    channel = session.get(YoutubeChannel, channel_id)
    if workspace_channel is None or channel is None:
        raise HTTPException(404, "Monitored channel not found")
    if workspace_channel.relationship == "owned" and not payload.active:
        raise HTTPException(409, "The owned channel cannot be paused")
    workspace_channel.active = payload.active
    session.commit()
    return MonitoredChannelResponse(
        workspace_id=workspace_channel.workspace_id,
        channel_id=channel.id,
        youtube_channel_id=channel.youtube_channel_id,
        title=channel.title,
        relationship=workspace_channel.relationship,
        priority=workspace_channel.priority,
        active=workspace_channel.active,
        last_ingested_at=workspace_channel.last_ingested_at,
        next_ingestion_at=workspace_channel.next_ingestion_at,
    )


@app.get(
    "/api/v1/admin/monitored-channels",
    response_model=list[MonitoredChannelResponse],
)
def monitored_channels(session: DbSession) -> list[MonitoredChannelResponse]:
    rows = session.execute(
        select(WorkspaceChannel, YoutubeChannel)
        .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
        .where(~YoutubeChannel.youtube_channel_id.startswith("UCESDEMO"))
        .order_by(WorkspaceChannel.priority, YoutubeChannel.title)
    ).all()
    return [
        MonitoredChannelResponse(
            workspace_id=workspace_channel.workspace_id,
            channel_id=channel.id,
            youtube_channel_id=channel.youtube_channel_id,
            title=channel.title,
            relationship=workspace_channel.relationship,
            priority=workspace_channel.priority,
            active=workspace_channel.active,
            last_ingested_at=workspace_channel.last_ingested_at,
            next_ingestion_at=workspace_channel.next_ingestion_at,
        )
        for workspace_channel, channel in rows
    ]


@app.post(
    "/api/v1/admin/monitored-channels",
    response_model=MonitoredChannelResponse,
    status_code=201,
)
async def add_monitored_channel(
    payload: MonitorChannelCreate,
    session: DbSession,
) -> MonitoredChannelResponse:
    service = IngestionService(session, settings)
    try:
        channel = await service.monitor_channel(
            workspace_id=payload.workspace_id,
            youtube_channel_id=payload.youtube_channel_id,
            relationship=payload.relationship,
            priority=payload.priority,
        )
    except Exception as error:
        raise HTTPException(502, f"Channel setup failed: {error}") from error
    workspace_channel = session.get(
        WorkspaceChannel,
        (payload.workspace_id, channel.id),
    )
    if workspace_channel is None:
        raise HTTPException(500, "Monitored channel was not persisted")
    return MonitoredChannelResponse(
        workspace_id=workspace_channel.workspace_id,
        channel_id=channel.id,
        youtube_channel_id=channel.youtube_channel_id,
        title=channel.title,
        relationship=workspace_channel.relationship,
        priority=workspace_channel.priority,
        active=workspace_channel.active,
        last_ingested_at=workspace_channel.last_ingested_at,
        next_ingestion_at=workspace_channel.next_ingestion_at,
    )


@app.post(
    "/api/v1/admin/monitored-channels/{channel_id}/run",
    response_model=IngestionRunResponse,
)
async def run_monitored_channel(
    channel_id: str,
    payload: RunIngestionRequest,
    session: DbSession,
) -> DiscoveryRun:
    workspace_channel = session.scalar(
        select(WorkspaceChannel).where(WorkspaceChannel.channel_id == channel_id)
    )
    if workspace_channel is None:
        raise HTTPException(404, "Monitored channel not found")
    service = IngestionService(session, settings)
    try:
        result = await service.ingest_monitored_channel(
            workspace_channel,
            force=payload.force,
            max_results=payload.max_results,
        )
    except Exception as error:
        raise HTTPException(502, f"Channel ingestion failed: {error}") from error
    run = session.get(DiscoveryRun, result.run_id)
    if run is None:
        raise HTTPException(500, "Ingestion run was not persisted")
    TopicIntelligenceService(session, settings).run(force=True)
    return run


@app.get(
    "/api/v1/admin/video-intelligence/metrics",
    response_model=VideoIntelligenceMetrics,
)
def video_intelligence_metrics(
    session: DbSession,
) -> dict[str, int | float | str | None]:
    service = VideoIntelligenceService(session, settings)
    return service.operational_metrics()


@app.get(
    "/api/v1/admin/video-intelligence/videos",
    response_model=list[VideoIntelligenceItem],
)
def video_intelligence_videos(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[VideoIntelligenceItem]:
    videos = list(
        session.scalars(
            select(YoutubeVideo)
            .where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
            .order_by(desc(YoutubeVideo.first_discovered_at))
            .limit(limit)
        )
    )
    items: list[VideoIntelligenceItem] = []
    now = datetime.now(tz=UTC)
    for video in videos:
        channel = session.get(YoutubeChannel, video.channel_id)
        latest = session.scalar(
            select(VideoSnapshot)
            .where(VideoSnapshot.video_id == video.id)
            .order_by(desc(VideoSnapshot.observed_at))
            .limit(1)
        )
        snapshot_count = int(
            session.scalar(
                select(func.count(VideoSnapshot.id)).where(VideoSnapshot.video_id == video.id)
            )
            or 0
        )
        feature = session.get(
            VideoFeature,
            (video.id, "video-intelligence-v1"),
        )
        next_snapshot = session.scalar(
            select(VideoSnapshotJob.run_at)
            .where(
                VideoSnapshotJob.video_id == video.id,
                VideoSnapshotJob.status == "pending",
            )
            .order_by(VideoSnapshotJob.run_at)
            .limit(1)
        )
        snapshot_age_minutes = (
            (now - _aware(latest.observed_at)).total_seconds() / 60 if latest else None
        )
        freshness = (
            "No snapshot"
            if snapshot_age_minutes is None
            else "Very fresh"
            if snapshot_age_minutes < 60
            else "Fresh"
            if snapshot_age_minutes < 360
            else "Stale"
        )
        items.append(
            VideoIntelligenceItem(
                video_id=video.id,
                youtube_video_id=video.youtube_video_id,
                title=video.title,
                channel=channel.title if channel else "Unknown channel",
                published_at=_aware(video.published_at),
                discovery_lag_seconds=video.discovery_lag_seconds,
                snapshot_count=snapshot_count,
                latest_snapshot_at=_aware(latest.observed_at) if latest else None,
                latest_views=latest.view_count if latest else None,
                view_velocity=feature.view_velocity if feature else None,
                velocity_acceleration=feature.velocity_acceleration if feature else None,
                outlier_ratio=feature.outlier_ratio if feature else None,
                engagement_per_1000=feature.engagement_rate if feature else None,
                next_snapshot_at=_aware(next_snapshot) if next_snapshot else None,
                freshness=freshness,
            )
        )
    return items


@app.post(
    "/api/v1/admin/video-intelligence/schedule",
    response_model=SnapshotScheduleResponse,
)
def schedule_video_snapshots(
    session: DbSession,
) -> SnapshotScheduleResponse:
    service = VideoIntelligenceService(session, settings)
    return SnapshotScheduleResponse(jobs_created=service.schedule_all())


@app.post(
    "/api/v1/admin/video-intelligence/run",
    response_model=VideoIntelligenceRunResponse,
)
async def run_video_intelligence(
    payload: VideoIntelligenceRunRequest,
    session: DbSession,
) -> VideoIntelligenceRunResponse:
    service = VideoIntelligenceService(session, settings)
    try:
        if payload.force_refresh:
            refresh_result = await service.refresh_recent(limit=payload.limit)
            return VideoIntelligenceRunResponse(
                requested_videos=refresh_result.requested_videos,
                snapshots_created=refresh_result.snapshots_created,
                features_updated=refresh_result.features_updated,
                baselines_updated=refresh_result.baselines_updated,
            )
        snapshot_result = await service.run_due(limit=payload.limit)
        return VideoIntelligenceRunResponse(
            requested_jobs=snapshot_result.requested_jobs,
            completed_jobs=snapshot_result.completed_jobs,
            failed_jobs=snapshot_result.failed_jobs,
            snapshots_created=snapshot_result.snapshots_created,
            features_updated=snapshot_result.features_updated,
            baselines_updated=snapshot_result.baselines_updated,
        )
    except Exception as error:
        raise HTTPException(502, f"Video intelligence run failed: {error}") from error


@app.get(
    "/api/v1/admin/topic-intelligence/metrics",
    response_model=TopicIntelligenceMetrics,
)
def topic_intelligence_metrics(
    session: DbSession,
) -> dict[str, object]:
    return TopicIntelligenceService(session, settings).operational_metrics()


@app.post(
    "/api/v1/admin/topic-intelligence/run",
    response_model=TopicIntelligenceRunResponse,
)
def run_topic_intelligence(session: DbSession) -> TopicIntelligenceRunResponse:
    try:
        result = TopicIntelligenceService(session, settings).run(force=True)
    except Exception as error:
        raise HTTPException(502, f"Topic intelligence run failed: {error}") from error
    return TopicIntelligenceRunResponse(
        run_id=result.run_id,
        reused=result.reused,
        source_videos=result.source_videos,
        eligible_videos=result.eligible_videos,
        topics=result.topics,
        signals=result.signals,
        assigned_videos=result.assigned_videos,
    )


@app.get(
    "/api/v1/admin/demand-intelligence/metrics",
    response_model=DemandIntelligenceMetrics,
)
def demand_intelligence_metrics(
    session: DbSession,
) -> dict[str, int | float | str | None]:
    return DemandIntelligenceService(session, settings).operational_metrics()


@app.post(
    "/api/v1/admin/demand-intelligence/run",
    response_model=DemandIntelligenceRunResponse,
)
async def run_demand_intelligence(
    session: DbSession,
    limit: int = Query(default=12, ge=1, le=50),
) -> DemandIntelligenceRunResponse:
    try:
        result = await DemandIntelligenceService(session, settings).run(
            force=True,
            limit=limit,
        )
        TopicIntelligenceService(session, settings).run(force=True)
    except Exception as error:
        raise HTTPException(502, f"Demand intelligence run failed: {error}") from error
    return DemandIntelligenceRunResponse(
        run_id=result.run_id,
        reused=result.reused,
        candidate_videos=result.candidate_videos,
        fetched_videos=result.fetched_videos,
        comments=result.comments,
        classified=result.classified,
        relevance_evaluated=result.relevance_evaluated,
        relevance_accepted=result.relevance_accepted,
        relevance_rejected=result.relevance_rejected,
        clusters=result.clusters,
        provider_failures=result.provider_failures,
    )


def _require_comment_relevance() -> None:
    if not settings.feature_comment_topic_relevance:
        raise HTTPException(404, "Comment-to-topic relevance is disabled")


@app.post(
    "/api/v1/admin/demand/reclassify",
    response_model=DemandReclassifyResponse,
)
def reclassify_comment_demand(
    payload: DemandReclassifyRequest,
    session: DbSession,
) -> DemandReclassifyResponse:
    _require_comment_relevance()
    if payload.topic_id is not None and session.get(Topic, payload.topic_id) is None:
        raise HTTPException(404, "Topic not found")
    result = DemandIntelligenceService(session, settings).replay_relevance(
        topic_id=payload.topic_id
    )
    TopicIntelligenceService(session, settings).run(force=True)
    return DemandReclassifyResponse(
        evaluated=result.evaluated,
        accepted=result.accepted,
        rejected=result.rejected,
        changed=result.changed,
        clusters=result.clusters,
        model_version=RELEVANCE_MODEL_VERSION,
    )


@app.post(
    "/api/v1/admin/demand/relevance/{relevance_id}/override",
    response_model=CommentTopicRelevanceResponse,
)
def override_comment_relevance(
    relevance_id: str,
    workspace_id: str,
    payload: CommentTopicRelevanceOverrideRequest,
    session: DbSession,
) -> CommentTopicRelevanceResponse:
    _require_comment_relevance()
    reviewer_id, _reviewer_name = workspace_reviewer(session, workspace_id)
    service = DemandIntelligenceService(session, settings)
    try:
        row = service.override_relevance(
            relevance_id,
            decision=payload.decision,
            reason=payload.reason,
            reviewer_id=reviewer_id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    TopicIntelligenceService(session, settings).run(force=True)
    item = next(
        (
            candidate
            for candidate in service.relevance_for_topic(row.topic_id, limit=100)
            if candidate["id"] == row.id
        ),
        None,
    )
    if item is None:
        raise HTTPException(404, "Comment relevance record not found")
    return CommentTopicRelevanceResponse(**item)


@app.get(
    "/api/v1/admin/transcript-intelligence/metrics",
    response_model=TranscriptIntelligenceMetrics,
)
def transcript_intelligence_metrics(
    session: DbSession,
) -> dict[str, int | float | str | None]:
    return TranscriptIntelligenceService(session, settings).operational_metrics()


@app.post(
    "/api/v1/admin/transcript-intelligence/run",
    response_model=TranscriptIntelligenceRunResponse,
)
async def run_transcript_intelligence(
    session: DbSession,
    limit: int = Query(default=8, ge=1, le=24),
) -> TranscriptIntelligenceRunResponse:
    try:
        result = await TranscriptIntelligenceService(session, settings).run(
            force=True,
            limit=limit,
        )
        if result.fetched:
            TopicIntelligenceService(session, settings).run(force=True)
    except Exception as error:
        raise HTTPException(502, f"Transcript intelligence run failed: {error}") from error
    return TranscriptIntelligenceRunResponse(
        run_id=result.run_id,
        reused=result.reused,
        candidates=result.candidates,
        fetched=result.fetched,
        unavailable=result.unavailable,
        failed=result.failed,
        segments=result.segments,
    )
