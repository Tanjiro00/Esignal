from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DemoContext(BaseModel):
    demo: bool
    workspace_id: str
    workspace_name: str
    owned_channel_id: str
    owned_channel_name: str
    user_id: str
    user_name: str
    user_email: str
    role: str
    is_admin: bool
    onboarding_status: str
    features: dict[str, bool]
    fresh_at: datetime


class WorkspaceSetupCreate(BaseModel):
    workspace_name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)
    owner_email: str = Field(min_length=5, max_length=320)
    owner_name: str = Field(min_length=2, max_length=160)


class WorkspaceSetupResponse(BaseModel):
    workspace_id: str
    user_id: str
    onboarding_url: str


class OnboardingWorkspaceUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(min_length=2, max_length=80)


class OnboardingAutoSetupRequest(BaseModel):
    youtube_channel: str = Field(min_length=3, max_length=500)


class OnboardingStatusResponse(BaseModel):
    workspace_id: str
    workspace_name: str
    workspace_slug: str
    timezone: str
    status: str
    current_step: int
    completed_steps: list[str]
    progress_percent: int
    steps: list[dict[str, Any]]
    owned_channel: dict[str, Any] | None
    reference_channel_count: int
    active_query_count: int
    digest_enabled: bool
    readiness: list[dict[str, Any]]


class ProductEventCreate(BaseModel):
    event_type: Literal[
        "signal_impression",
        "signal_open",
        "evidence_interaction",
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
    ]
    event_key: str = Field(min_length=8, max_length=180)
    signal_id: str | None = Field(default=None, min_length=36, max_length=36)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductEventResponse(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    period_days: int
    north_star: dict[str, Any]
    funnel: list[dict[str, Any]]
    open_rate: float
    trend: list[dict[str, Any]]
    freshness: dict[str, Any]
    recent_activity: list[dict[str, Any]]
    ux: dict[str, Any] = Field(default_factory=dict)


class OperationsReadinessResponse(BaseModel):
    status: str
    checked_at: datetime
    alerts: list[dict[str, Any]]
    dead_letters: list[dict[str, Any]]
    pipeline: dict[str, Any]
    backup: dict[str, Any]


class DigestSubscriptionUpdate(BaseModel):
    cadence: Literal["daily", "twice_weekly", "weekly"]
    delivery_channel: Literal["in_app"]
    destination: str = Field(min_length=2, max_length=320)
    enabled: bool


class DigestSubscriptionResponse(BaseModel):
    workspace_id: str
    cadence: str
    delivery_channel: str
    destination: str
    enabled: bool
    next_run_at: datetime
    last_generated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DigestRunResponse(BaseModel):
    id: str
    workspace_id: str
    period_start: datetime
    period_end: datetime
    status: str
    content: dict[str, Any]
    generated_at: datetime
    delivered_at: datetime | None


class ChannelProfileUpdate(BaseModel):
    audience_description: str = Field(max_length=2000)
    geography: str = Field(min_length=2, max_length=16)
    language: str = Field(min_length=2, max_length=16)
    topic_keywords: list[str] = Field(max_length=40)
    preferred_formats: list[str] = Field(max_length=20)
    creator_expertise: list[str] = Field(max_length=30)
    production_capabilities: list[str] = Field(max_length=30)
    exclusions: list[str] = Field(max_length=30)
    strategic_goals: list[str] = Field(max_length=20)
    normal_duration_min_seconds: int = Field(ge=60, le=14_400)
    normal_duration_max_seconds: int = Field(ge=60, le=28_800)
    production_days_min: int = Field(ge=0, le=60)
    production_days_max: int = Field(ge=1, le=90)
    core_topics: list[str] | None = Field(default=None, max_length=20)
    adjacent_topics: list[str] | None = Field(default=None, max_length=20)
    audience_sophistication: Literal["beginner", "intermediate", "advanced"] | None = None
    creator_authority: str | None = Field(default=None, max_length=80)
    risk_tolerance: Literal["conservative", "balanced", "experimental"] | None = None
    team_size: int | None = Field(default=None, ge=1, le=100)
    research_capacity_hours: float | None = Field(default=None, ge=0, le=168)
    filming_required: bool | None = None
    external_guests_required: bool | None = None
    editing_complexity: Literal["low", "medium", "high"] | None = None
    access_to_products: list[str] | None = Field(default=None, max_length=40)
    experiment_level: Literal["conservative", "balanced", "experimental"] | None = None
    evergreen_trend_balance: float | None = Field(default=None, ge=0, le=1)
    weekday_publish_only: bool | None = None
    content_calendar: list[dict[str, Any]] | None = Field(default=None, max_length=90)


class ChannelProfileResponse(BaseModel):
    workspace_id: str
    channel_id: str
    channel_title: str
    youtube_channel_id: str
    profile_source: str
    audience_description: str
    geography: str
    language: str
    topic_keywords: list[str]
    preferred_formats: list[str]
    creator_expertise: list[str]
    production_capabilities: list[str]
    exclusions: list[str]
    strategic_goals: list[str]
    title_style: dict[str, Any]
    normal_duration_min_seconds: int
    normal_duration_max_seconds: int
    production_days_min: int
    production_days_max: int
    core_topics: list[str]
    adjacent_topics: list[str]
    legacy_topics: list[str]
    successful_formats: list[str]
    upload_cadence: dict[str, Any]
    audience_sophistication: str
    creator_authority: str
    risk_tolerance: str
    team_size: int
    research_capacity_hours: float
    filming_required: bool
    external_guests_required: bool
    editing_complexity: str
    access_to_products: list[str]
    experiment_level: str
    evergreen_trend_balance: float
    weekday_publish_only: bool
    content_calendar: list[dict[str, Any]]
    inference: dict[str, Any]
    explicit_overrides: dict[str, Any]
    profile_version: str
    updated_at: datetime


class YoutubeOAuthStatusResponse(BaseModel):
    feature_enabled: bool
    configured: bool
    connected: bool
    status: str
    verified: bool
    scopes: list[str]
    token_expires_at: datetime | None
    verified_at: datetime | None
    last_synced_at: datetime | None
    last_refresh_error: str | None
    analytics_video_count: int
    audit_events: list[dict[str, Any]]


class YoutubeOAuthStartRequest(BaseModel):
    redirect_after: str = Field(default="/settings", min_length=1, max_length=500)


class YoutubeOAuthStartResponse(BaseModel):
    authorization_url: str


class YoutubeAnalyticsSyncResponse(BaseModel):
    updated_videos: int
    status: str


class OpportunityWindow(BaseModel):
    start: datetime
    end: datetime
    label: str


class MomentumSummary(BaseModel):
    change_24h: float
    change_72h: float
    sparkline: list[float]


class DemandSummary(BaseModel):
    available: bool = True
    label: str
    question: str
    comment_count: int
    distinct_channels: int
    distinct_videos: int = 0
    distinct_commenters: int = 0
    evidence_strength: str = "Unverified"


class EvidenceQuality(BaseModel):
    baseline_coverage_percent: float
    transcript_coverage_percent: float
    specificity_score: float
    calibrated: bool


class SignalEarlynessSummary(BaseModel):
    claim_kind: Literal["early", "pending", "late", "unverified"]
    headline: str
    supporting_text: str
    current_stage: str
    lead_time_to_breakout_hours: float | None
    lead_time_to_large_channel_hours: float | None


class LifecycleMilestone(BaseModel):
    key: str
    label: str
    occurred_at: datetime | None
    status: Literal["reached", "current", "pending", "not_observed"]
    evidence_id: str | None


class LifecycleTransitionEvidence(BaseModel):
    id: str
    from_stage: str | None
    to_stage: str
    transitioned_at: datetime
    measurement_id: str | None
    score: float | None
    reason_codes: list[str]
    history_version: str


class SignalEarlynessResponse(SignalEarlynessSummary):
    topic_id: str
    signal_id: str
    first_video_published_at: datetime | None
    first_discovered_at: datetime | None
    first_topic_formed_at: datetime | None
    first_seed_at: datetime | None
    first_emerging_at: datetime | None
    first_signal_visible_at: datetime | None
    first_breakout_at: datetime | None
    first_mass_market_at: datetime | None
    first_saturated_at: datetime | None
    first_declining_at: datetime | None
    first_large_channel_adoption_at: datetime | None
    latest_measurement_at: datetime | None
    visible_age_hours: float | None
    time_in_current_stage_hours: float | None
    large_channel_threshold_subscribers: int
    backfill_version: str
    milestones: list[LifecycleMilestone]
    transitions: list[LifecycleTransitionEvidence]
    data_mode: str


class UserFacingBucket(BaseModel):
    label: Literal["Low", "Moderate", "High", "Very high"]
    reason_codes: list[str]
    version: str


class SignalDecisionCard(BaseModel):
    decision: Literal["Act", "Watch", "Skip"]
    decision_label: str
    decision_reason_codes: list[str]
    decision_version: str
    topic: str
    thesis: str
    why_now: str
    why_this_channel: str
    open_angle: str
    recommended_video: str
    release_ready: bool = False
    insight_status: Literal["evidence_backed", "candidate"] = "candidate"
    insight_type: str = "unavailable"
    insight_statement: str = ""
    insight_reason_codes: list[str] = Field(default_factory=list)
    publishing_window: OpportunityWindow
    production_effort: str
    production_days_min: int
    production_days_max: int
    recommended_publish_by: datetime | None = None
    recommended_publish_by_label: str | None = None
    feasibility: str | None = None
    infeasibility_reasons: list[str] = Field(default_factory=list)
    decay_version: str | None = None
    fit_verification: Literal["estimated", "verified"] = "estimated"
    signal_strength: UserFacingBucket
    channel_fit: UserFacingBucket
    confidence: UserFacingBucket
    evidence_strength: UserFacingBucket
    main_risk: str


class SignalEvidenceLink(BaseModel):
    id: str
    title: str
    canonical_url: str
    channel: str
    published_at: datetime


class SignalListItem(BaseModel):
    id: str
    topic_label: str
    category: str
    lifecycle_stage: str
    score: float
    confidence: str
    channel_fit: float
    opportunity_window: OpportunityWindow
    momentum: MomentumSummary
    independent_channels: int
    evidence_videos: int
    evidence_preview: list[SignalEvidenceLink] = Field(default_factory=list)
    evidence_quality: EvidenceQuality
    strongest_demand: DemandSummary
    thesis: str
    current_action: str | None
    generated_at: datetime
    data_mode: str
    earlyness: SignalEarlynessSummary | None = None
    decision_card: SignalDecisionCard | None = None


class SignalListResponse(BaseModel):
    items: list[SignalListItem]
    total: int
    data_freshness: datetime
    data_mode: str
    available_modes: list[str]


class EvidenceVideo(BaseModel):
    id: str
    youtube_video_id: str
    title: str
    canonical_url: str
    thumbnail_url: str
    channel: str
    channel_subscribers: int
    published_at: datetime
    age_label: str
    views: int
    view_velocity: float
    outlier_ratio: float
    role: str
    freshness: str
    transcript_status: str
    comment_sample_status: str
    sparkline: list[float]


class TranscriptSegmentEvidence(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    text: str
    video_url: str


class TranscriptEvidence(BaseModel):
    video_id: str
    youtube_video_id: str
    video_title: str
    language: str
    transcript_type: str
    quality_score: float
    summary: str
    entities: list[str]
    content_format: str
    narrative_angle: str
    fetched_at: datetime
    segments: list[TranscriptSegmentEvidence]


class DemandEvidence(BaseModel):
    id: str
    label: str
    summary: str
    taxonomy: str
    comment_count: int
    distinct_commenters: int
    distinct_videos: int
    distinct_channels: int
    score: float
    date_range: tuple[datetime, datetime]
    snippets: list[dict[str, Any]]
    confidence: str
    evidence_strength: str = "Unverified"
    limitation: str


class TimelinePoint(BaseModel):
    observed_at: datetime
    video_count_24h: int
    distinct_channels_72h: int
    aggregate_view_velocity: float


class DiffusionPoint(BaseModel):
    channel: str
    subscribers: int
    published_at: datetime
    role: str


class GroundedWhyClaim(BaseModel):
    text: str
    evidence_refs: list[str]


class SignalDetail(BaseModel):
    id: str
    topic: dict[str, Any]
    score: float
    confidence: str
    channel_fit: float
    opportunity_window: OpportunityWindow
    thesis: str
    why_emerging: list[str]
    why_emerging_evidence: list[GroundedWhyClaim] = Field(default_factory=list)
    intelligence_provenance: dict[str, Any] = Field(default_factory=dict)
    score_components: dict[str, float]
    evidence_quality: EvidenceQuality
    evidence_videos: list[EvidenceVideo]
    transcript_evidence: list[TranscriptEvidence]
    demand_clusters: list[DemandEvidence]
    timeline: list[TimelinePoint]
    diffusion: list[DiffusionPoint]
    saturation: dict[str, Any]
    channel_fit_detail: dict[str, Any]
    content_angles: list[dict[str, Any]]
    current_action: str | None
    data_freshness: dict[str, datetime]
    provenance: list[dict[str, Any]]
    data_mode: str
    earlyness: SignalEarlynessResponse | None = None
    decision_card: SignalDecisionCard | None = None
    content_gap_map: dict[str, Any] | None = None


ReviewStatus = Literal[
    "internal_candidate",
    "needs_review",
    "approved",
    "rejected",
    "needs_changes",
    "published",
    "expired",
]

ReviewReason = Literal[
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
]

ReviewAction = Literal[
    "approve",
    "reject",
    "request_split",
    "request_merge",
    "mark_late",
    "mark_weak_evidence",
    "mark_irrelevant_demand",
    "edit_thesis",
    "edit_opportunity",
    "edit_evidence_selection",
]


class SignalReviewActionCreate(BaseModel):
    action: ReviewAction
    reason_codes: list[ReviewReason] = Field(default_factory=list, max_length=6)
    note: str | None = Field(default=None, max_length=2_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    thesis: str | None = Field(default=None, min_length=12, max_length=4_000)
    opportunity: dict[str, Any] | None = None
    evidence_video_ids: list[str] | None = Field(default=None, max_length=30)
    merge_target_signal_id: str | None = Field(default=None, min_length=36, max_length=36)


class SignalReviewEventResponse(BaseModel):
    id: str
    event_type: str
    from_status: str | None
    to_status: str
    reviewer_id: str | None
    reviewer_name: str | None
    reason_codes: list[str]
    note: str | None
    changes: dict[str, Any]
    provenance: dict[str, Any]
    idempotency_key: str
    created_at: datetime


class SignalReviewSummary(BaseModel):
    id: str
    workspace_id: str
    signal_id: str
    topic_label: str
    lifecycle_stage: str
    signal_score: float
    channel_fit: float
    status: ReviewStatus
    reviewer_id: str | None
    reviewer_name: str | None
    primary_reason: str | None
    reason_codes: list[str]
    submitted_at: datetime
    first_reviewed_at: datetime | None
    decided_at: datetime | None
    updated_at: datetime
    source_kind: str


class SignalReviewMetrics(BaseModel):
    total: int
    status_counts: dict[str, int]
    approval_rate: float
    rejection_reasons: dict[str, int]
    average_review_time_hours: float | None
    stage_distribution: dict[str, dict[str, int]]


class SignalReviewQueueResponse(BaseModel):
    items: list[SignalReviewSummary]
    total: int
    metrics: SignalReviewMetrics
    filters: dict[str, list[str]]


class SignalReviewDetail(BaseModel):
    review: SignalReviewSummary
    signal: SignalDetail
    false_positive_risks: list[dict[str, Any]]
    decision_card_preview: dict[str, Any]
    thesis_override: str | None
    opportunity_override: dict[str, Any]
    evidence_selection: list[str]
    comment_relevance: list["CommentTopicRelevanceResponse"] = Field(default_factory=list)
    audit_history: list[SignalReviewEventResponse]


class CommentTopicRelevanceResponse(BaseModel):
    id: str
    comment_id: str
    comment_text: str
    video_id: str
    video_title: str
    video_url: str
    channel: str
    intent: str
    actionability: str
    is_relevant: bool
    effective_relevant: bool
    relevance_score: float
    comment_topic_semantic_similarity: float
    comment_video_semantic_similarity: float
    entity_overlap_score: float
    claim_support_score: float
    duplicate_or_echo_probability: float
    supported_entities: list[str]
    supported_claims: list[str]
    reason_codes: list[str]
    override_decision: bool | None
    override_reason: str | None
    reviewer_id: str | None
    reviewed_at: datetime | None
    model_version: str


class DemandReclassifyRequest(BaseModel):
    topic_id: str | None = Field(default=None, min_length=36, max_length=36)


class DemandReclassifyResponse(BaseModel):
    evaluated: int
    accepted: int
    rejected: int
    changed: int
    clusters: int
    model_version: str


class CommentTopicRelevanceOverrideRequest(BaseModel):
    decision: bool | None
    reason: str = Field(min_length=3, max_length=240)
    idempotency_key: str = Field(min_length=8, max_length=180)


class SignalActionCreate(BaseModel):
    action: Literal["act", "watch", "skip", "save", "dismiss"]
    reason: str | None = Field(default=None, min_length=2, max_length=80)
    comment: str | None = Field(default=None, max_length=300)
    opportunity_id: str | None = Field(default=None, min_length=36, max_length=36)
    production_days: int | None = Field(default=None, ge=1, le=60)
    target_publish_date: datetime | None = None


class SignalActionResponse(BaseModel):
    id: str
    signal_id: str
    action: str
    reason: str | None
    comment: str | None = None
    opportunity_id: str | None = None
    feedback_version: str = "decision-feedback-v1"
    created_at: datetime


class EvaluationLabelCreate(BaseModel):
    workspace_id: str | None = Field(default=None, min_length=36, max_length=36)
    as_of: datetime | None = None
    label: Literal[
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
    ]
    additional_labels: list[
        Literal[
            "demand_relevant",
            "demand_irrelevant",
            "opportunity_actionable",
            "opportunity_generic",
            "fit_correct",
            "fit_incorrect",
        ]
    ] = Field(default_factory=list, max_length=6)
    notes: str = Field(default="", max_length=2_000)


class EvaluationLabelResponse(BaseModel):
    id: str
    workspace_id: str | None
    topic_id: str
    signal_id: str | None
    reviewer_id: str
    as_of: datetime
    label: str
    additional_labels: list[str]
    evidence_snapshot: dict[str, Any]
    notes: str
    model_versions: dict[str, Any]
    label_version: str
    created_at: datetime
    updated_at: datetime


class EvaluationCandidate(BaseModel):
    topic_id: str
    topic_label: str
    source_kind: str
    lifecycle_stage: str
    specificity_score: float
    signal_id: str | None
    signal_score: float | None
    evidence_videos: int
    reviewed: bool
    evaluation: EvaluationLabelResponse | None


class EvaluationCandidateList(BaseModel):
    items: list[EvaluationCandidate]
    total: int
    reviewed: int
    primary_labels: list[str]
    additional_labels: list[str]


class EvaluationReportResponse(BaseModel):
    reviewed_topics: int
    label_counts: dict[str, int]
    additional_label_counts: dict[str, int]
    metrics: dict[str, float]
    versions: dict[str, str]
    production_weights_changed: bool
    decision_feedback: dict[str, Any] = Field(default_factory=dict)


class BriefCreate(BaseModel):
    angle_index: int = Field(default=0, ge=0, le=4)
    opportunity_id: str | None = Field(default=None, min_length=36, max_length=36)


class BriefUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=400)
    status: Literal["draft", "approved", "in_production", "published", "archived"] | None = None
    brief_json: dict[str, Any] | None = None


class BriefResponse(BaseModel):
    id: str
    workspace_id: str
    signal_id: str
    channel_id: str
    opportunity_id: str | None
    evidence_version: str
    status: str
    title: str
    brief_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SignalPackagingResponse(BaseModel):
    id: str
    workspace_id: str
    signal_id: str
    opportunity_id: str
    content_brief_id: str
    packaging: dict[str, Any]
    evidence_ids: list[str]
    regeneration_counts: dict[str, int]
    packaging_version: str
    created_at: datetime
    updated_at: datetime


class SignalPackagingRegenerate(BaseModel):
    section: Literal[
        "audience_promise",
        "core_tension",
        "hook_directions",
        "title_directions",
        "thumbnail_directions",
        "proof_requirements",
        "clickbait_mismatch_risks",
        "opening_structure",
    ]


class SignalPackagingCopyEvent(BaseModel):
    section: Literal[
        "audience_promise",
        "core_tension",
        "hook_directions",
        "title_directions",
        "thumbnail_directions",
        "proof_requirements",
        "clickbait_mismatch_risks",
        "opening_structure",
    ]
    item_index: int | None = Field(default=None, ge=0, le=20)


class OutcomeCreate(BaseModel):
    signal_id: str
    content_brief_id: str | None = None
    youtube_video_id: str = Field(min_length=6, max_length=32)
    published_at: datetime
    baseline_definition: str = Field(min_length=3, max_length=240)
    performance_json: dict[str, Any] = Field(default_factory=dict)
    success_status: Literal["pending", "successful", "mixed", "unsuccessful"]
    user_notes: str = ""


class OutcomeResponse(BaseModel):
    id: str
    workspace_id: str
    signal_id: str
    content_brief_id: str | None
    youtube_video_id: str
    published_at: datetime
    baseline_definition: str
    performance_json: dict[str, Any]
    success_status: str
    user_notes: str
    link_status: str
    association_version: str
    metrics_version: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutcomeSuggestionDecision(BaseModel):
    content_brief_id: str | None = Field(default=None, min_length=36, max_length=36)


class OutcomeSuggestionResponse(BaseModel):
    id: str
    workspace_id: str
    status: str
    youtube_video_id: str
    video_title: str
    video_url: str
    published_at: datetime
    signal_id: str
    suggested_brief_id: str
    selected_brief_id: str | None
    brief_title: str
    match_confidence: float
    reason_codes: list[str]
    match_features: dict[str, Any]
    baseline: dict[str, Any]
    metrics: dict[str, Any]
    model_version: str
    outcome_id: str | None
    alternatives: list[dict[str, Any]]
    detected_at: datetime
    decided_at: datetime | None


class OutcomeCorrection(BaseModel):
    content_brief_id: str = Field(min_length=36, max_length=36)
    user_notes: str | None = Field(default=None, max_length=2000)


class ProviderHealthResponse(BaseModel):
    provider: str
    capability: str
    enabled: bool
    priority: int
    status: str
    circuit_state: str
    consecutive_failures: int
    circuit_opened_at: datetime | None
    half_open_probe_at: datetime | None
    disabled_reason: str | None
    request_count: int
    request_count_hour: int
    request_count_day: int
    success_rate: float
    error_rate: float
    p50_latency_ms: int
    p95_latency_ms: int
    estimated_cost: float
    spent_today_usd: float
    daily_limit_usd: float
    spent_month_usd: float
    monthly_limit_usd: float
    fallback_rate: float
    last_error: str | None
    updated_at: datetime
    demo: bool = True


class ProviderUpdate(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=20)


class ProviderRoutingDecisionResponse(BaseModel):
    id: str
    capability: str
    operation_key: str
    selected_provider: str | None
    attempted_providers: list[dict[str, Any]]
    skipped_providers: list[dict[str, Any]]
    fallback_used: bool
    status: str
    reason: str
    created_at: datetime


class ProviderOperationsEventResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    capability: str
    provider: str | None
    message: str
    context: dict[str, Any]
    created_at: datetime


class ProviderRoutingMetrics(BaseModel):
    decisions: int
    successful: int
    failed: int
    fallback_count: int
    fallback_rate: float
    open_circuits: int
    disabled_capabilities: int
    budget_skips: int


class ProviderBenchmarkResponse(BaseModel):
    id: str
    benchmark_version: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    live_case_count: int
    result: dict[str, Any]
    recommended_priorities: dict[str, list[str]]
    json_path: str | None
    csv_path: str | None
    markdown_path: str | None
    error_code: str | None
    error_message: str | None


class ProviderFetchListItem(BaseModel):
    id: str
    provider: str
    capability: str
    endpoint: str
    started_at: datetime
    latency_ms: int
    status: str
    http_status: int
    raw_payload_uri: str
    raw_payload_hash: str


class ProviderFetchDetail(ProviderFetchListItem):
    request_fingerprint: str
    completed_at: datetime
    attempt_number: int
    estimated_cost: float
    actual_cost: float
    parser_version: str
    error_code: str | None
    error_message: str | None
    linked_entity_ids: list[str]
    raw_payload: dict[str, Any]


class DiscoveryQueryCreate(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    category: str = Field(default="AI / tech", min_length=2, max_length=80)
    priority: int = Field(default=2, ge=0, le=3)
    country: str = Field(default="US", min_length=2, max_length=8)
    language: str = Field(default="en", min_length=2, max_length=16)


class DiscoveryQueryResponse(BaseModel):
    id: str
    query: str
    category: str
    priority: int
    country: str
    language: str
    active: bool
    source: str
    minimum_interval_seconds: int
    expires_at: datetime | None
    last_run_at: datetime | None
    next_run_at: datetime
    historical_yield: float
    cost_per_retained_video: float
    precision_score: float
    precision_sample_size: int
    quality_status: str
    last_precision_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class QuerySuggestionResponse(BaseModel):
    id: str
    workspace_id: str | None
    query: str
    normalized_query: str
    status: str
    source_type: str
    source_entity: str
    source_topic_id: str | None
    source_evidence_ids: list[str]
    rationale: str
    anchor_terms: list[str]
    quality_reason_codes: list[str]
    broadness_score: float
    precision_score: float
    precision_sample_size: int
    discovery_query_id: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    model_version: str
    created_at: datetime
    updated_at: datetime


class QuerySuggestionAction(BaseModel):
    action: Literal["approve", "activate", "pause", "retire"]


class QueryExpansionRunResponse(BaseModel):
    candidates_evaluated: int
    suggestions_created: int
    duplicates_skipped: int
    low_value_queries_demoted: int
    pending_suggestions: int
    capped: bool


class IngestionRunResponse(BaseModel):
    id: str
    query_id: str | None
    channel_id: str | None
    provider: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    result_count: int
    unique_video_count: int
    retained_video_count: int
    estimated_cost: float
    error_code: str | None
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class RunIngestionRequest(BaseModel):
    force: bool = False
    max_results: int = Field(default=20, ge=1, le=50)


class MonitorChannelCreate(BaseModel):
    workspace_id: str
    youtube_channel_id: str = Field(min_length=3, max_length=200)
    relationship: Literal["owned", "competitor", "reference"] = "competitor"
    priority: int = Field(default=1, ge=0, le=3)


class WorkspaceChannelCreate(BaseModel):
    youtube_channel_id: str = Field(min_length=3, max_length=200)
    relationship: Literal["owned", "competitor", "reference"] = "reference"
    priority: int = Field(default=1, ge=0, le=3)


class MonitoredChannelUpdate(BaseModel):
    active: bool


class MonitoredChannelResponse(BaseModel):
    workspace_id: str
    channel_id: str
    youtube_channel_id: str
    title: str
    relationship: str
    priority: int
    active: bool
    last_ingested_at: datetime | None
    next_ingestion_at: datetime | None


class VideoIntelligenceMetrics(BaseModel):
    live_videos: int
    videos_with_snapshots: int
    snapshot_coverage_percent: float
    pending_jobs: int
    due_jobs: int
    failed_jobs: int
    skipped_jobs: int
    snapshot_lag_seconds: int
    feature_count: int
    baseline_count: int
    latest_snapshot_at: datetime | None


class VideoIntelligenceItem(BaseModel):
    video_id: str
    youtube_video_id: str
    title: str
    channel: str
    published_at: datetime
    discovery_lag_seconds: int
    snapshot_count: int
    latest_snapshot_at: datetime | None
    latest_views: int | None
    view_velocity: float | None
    velocity_acceleration: float | None
    outlier_ratio: float | None
    engagement_per_1000: float | None
    next_snapshot_at: datetime | None
    freshness: str


class VideoIntelligenceRunRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    force_refresh: bool = False


class VideoIntelligenceRunResponse(BaseModel):
    requested_jobs: int = 0
    requested_videos: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    snapshots_created: int = 0
    features_updated: int = 0
    baselines_updated: int = 0


class SnapshotScheduleResponse(BaseModel):
    jobs_created: int


class TopicIntelligenceMetrics(BaseModel):
    active_topics: int
    active_signals: int
    assigned_videos: int
    embedding_count: int
    stale_signals: int
    stale_pipeline_runs: int = 0
    latest_run_status: str | None
    latest_run_at: datetime | None
    source_video_count: int
    eligible_video_count: int
    clustering_lag_seconds: int
    signal_generation_lag_seconds: int
    llm_feature_enabled: bool = False
    llm_configured: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_auditor_model: str | None = None
    llm_policy_version: str = ""
    llm_audit_required: bool = True
    llm_audit_run_count: int = 0
    llm_audit_acceptance_rate: float = 0
    llm_latest_trace_decisions: dict[str, int] = Field(default_factory=dict)
    llm_circuit_open: bool = False
    llm_run_count: int = 0
    llm_successful_runs: int = 0
    llm_failed_or_rejected_runs: int = 0
    llm_daily_tokens_used: int = 0
    llm_daily_token_budget: int = 0
    llm_stale_runs: int = 0
    llm_latest_status: str | None = None
    llm_latest_run_at: datetime | None = None


class TopicIntelligenceRunResponse(BaseModel):
    run_id: str
    reused: bool
    source_videos: int
    eligible_videos: int
    topics: int
    signals: int
    assigned_videos: int


class DemandIntelligenceMetrics(BaseModel):
    sampled_videos: int
    comment_count: int
    classified_count: int
    cluster_count: int
    internal_cluster_count: int = 0
    topics_with_demand: int
    relevance_evaluated_count: int = 0
    relevance_accepted_count: int = 0
    relevance_rejected_count: int = 0
    demand_evidence_rejection_rate: float = 0
    demand_relevance_median: float | None = None
    relevance_model_version: str | None = None
    failed_fetches: int
    comments_disabled_videos: int
    latest_run_status: str | None
    latest_run_at: datetime | None
    processing_lag_seconds: int


class DemandIntelligenceRunResponse(BaseModel):
    run_id: str
    reused: bool
    candidate_videos: int
    fetched_videos: int
    comments: int
    classified: int
    relevance_evaluated: int = 0
    relevance_accepted: int = 0
    relevance_rejected: int = 0
    clusters: int
    provider_failures: int


class TranscriptIntelligenceMetrics(BaseModel):
    eligible_videos: int
    transcript_count: int
    coverage_percent: float
    native_count: int
    auto_caption_count: int
    generated_count: int
    segment_count: int
    evidence_segment_count: int
    topics_with_transcript: int
    unavailable_videos: int
    failed_fetches: int
    latest_run_status: str | None
    latest_run_at: datetime | None
    processing_lag_seconds: int


class TranscriptIntelligenceRunResponse(BaseModel):
    run_id: str
    reused: bool
    candidates: int
    fetched: int
    unavailable: int
    failed: int
    segments: int
