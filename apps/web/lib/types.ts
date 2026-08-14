export type DemoContext = {
  demo: boolean;
  workspace_id: string;
  workspace_name: string;
  owned_channel_id: string;
  owned_channel_name: string;
  user_id: string;
  user_name: string;
  user_email: string;
  role: string;
  is_admin: boolean;
  onboarding_status: string;
  features: Record<string, boolean>;
  fresh_at: string;
};

export type AuthWorkspace = {
  id: string;
  name: string;
  slug: string;
  role: string;
  onboarding_status: string;
};

export type AuthSession = {
  user: {
    id: string;
    name: string;
    email: string;
    is_platform_admin: boolean;
  };
  workspace: AuthWorkspace;
  workspaces: AuthWorkspace[];
  onboarding_url: string;
};

export type AnalyticsSummary = {
  period_days: number;
  north_star: {
    key: string;
    value: number;
    successful_value: number;
    label: string;
  };
  funnel: Array<{ key: string; label: string; value: number }>;
  open_rate: number;
  trend: Array<{
    date: string;
    impressions: number;
    opened: number;
    published: number;
  }>;
  freshness: {
    last_signal_at: string | null;
    last_snapshot_at: string | null;
    last_discovery_at: string | null;
    stale_signals: number;
    dead_letters: number;
    healthy_providers: number;
    provider_count: number;
  };
  recent_activity: Array<{
    id: string;
    event_type: string;
    signal_id: string | null;
    content_brief_id: string | null;
    outcome_id: string | null;
    metadata: Record<string, string | number>;
    occurred_at: string;
  }>;
  ux: {
    events: Record<string, number>;
    decision_funnel: Array<{ key: string; value: number }>;
    onboarding_funnel: Array<{ key: string; value: number }>;
    timing: Record<string, number | null>;
  };
};

export type OperationsReadiness = {
  status: "ready" | "degraded" | "critical";
  checked_at: string;
  alerts: Array<{
    severity: "warning" | "critical";
    code: string;
    message: string;
  }>;
  dead_letters: Array<{
    job_type: string;
    id: string;
    failed_at: string;
    error_code: string | null;
    error_message: string | null;
    attempt_count: number | null;
  }>;
  pipeline: Record<
    string,
    {
      status: string;
      last_started_at: string | null;
      last_completed_at: string | null;
      failed_runs: number;
    }
  >;
  backup: {
    healthy: boolean;
    latest_file: string | null;
    created_at: string | null;
    age_hours: number | null;
    checksum_present: boolean;
  };
};

export type DigestSubscription = {
  workspace_id: string;
  cadence: "daily" | "twice_weekly" | "weekly";
  delivery_channel: "in_app";
  destination: string;
  enabled: boolean;
  next_run_at: string;
  last_generated_at: string | null;
};

export type DigestItem = {
  rank: number;
  signal_id: string;
  topic_label: string;
  lifecycle_stage: string;
  score: number;
  confidence: string;
  channel_fit: number;
  suggested_decision: "Act" | "Watch" | "Skip";
  decision_card: SignalDecisionCard | null;
  why_emerging: string[];
  evidence_videos: Array<{
    id: string;
    title: string;
    channel: string;
    channel_subscribers: number;
    views: number;
    outlier_ratio: number;
    canonical_url: string;
  }>;
  demand: {
    available: boolean;
    label: string;
    question: string;
    comment_count: number;
    distinct_channels: number;
  };
  saturation: {
    score: number;
    label: string;
    large_channel_count: number;
    analysis: string;
  };
  opportunity_window: OpportunityWindow;
  recommended_angle: ContentAngle;
  data_mode: string;
};

export type DigestRun = {
  id: string;
  workspace_id: string;
  period_start: string;
  period_end: string;
  status: string;
  content: {
    version: string;
    workspace_name: string;
    source_mode: string;
    items: DigestItem[];
  };
  generated_at: string;
  delivered_at: string | null;
};

export type OnboardingStatus = {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  timezone: string;
  status: string;
  current_step: number;
  completed_steps: string[];
  progress_percent: number;
  steps: Array<{
    key: string;
    label: string;
    href: string;
    complete: boolean;
    active: boolean;
  }>;
  owned_channel: {
    channel_id: string;
    youtube_channel_id: string;
    title: string;
    canonical_url: string;
    subscriber_count: number;
    video_count: number;
    recent_uploads: Array<{
      id: string;
      title: string;
      published_at: string;
      duration_seconds: number;
    }>;
    topic_keywords: string[];
    normal_duration_min_seconds: number;
    normal_duration_max_seconds: number;
    profile_version: string | null;
    profile_confirmed: boolean;
    core_topics: string[];
    exclusions: string[];
    production_days_min: number;
    production_days_max: number;
    team_size: number;
    research_capacity_hours: number;
    experiment_level: string;
    evergreen_trend_balance: number;
    risk_tolerance: string;
  } | null;
  reference_channel_count: number;
  active_query_count: number;
  digest_enabled: boolean;
  readiness: Array<{
    key: string;
    label: string;
    complete: boolean;
    detail: string;
  }>;
};

export type ChannelProfile = {
  workspace_id: string;
  channel_id: string;
  channel_title: string;
  youtube_channel_id: string;
  profile_source: string;
  audience_description: string;
  geography: string;
  language: string;
  topic_keywords: string[];
  preferred_formats: string[];
  creator_expertise: string[];
  production_capabilities: string[];
  exclusions: string[];
  strategic_goals: string[];
  title_style: Record<string, string | string[]>;
  normal_duration_min_seconds: number;
  normal_duration_max_seconds: number;
  production_days_min: number;
  production_days_max: number;
  core_topics: string[];
  adjacent_topics: string[];
  legacy_topics: string[];
  successful_formats: string[];
  upload_cadence: Record<string, string | number>;
  audience_sophistication: "beginner" | "intermediate" | "advanced";
  creator_authority: string;
  risk_tolerance: "conservative" | "balanced" | "experimental";
  team_size: number;
  research_capacity_hours: number;
  filming_required: boolean;
  external_guests_required: boolean;
  editing_complexity: "low" | "medium" | "high";
  access_to_products: string[];
  experiment_level: "conservative" | "balanced" | "experimental";
  evergreen_trend_balance: number;
  weekday_publish_only: boolean;
  content_calendar: Array<Record<string, string | number | boolean>>;
  inference: Record<string, unknown>;
  explicit_overrides: Record<string, unknown>;
  profile_version: string;
  updated_at: string;
};

export type YoutubeOAuthStatus = {
  feature_enabled: boolean;
  configured: boolean;
  connected: boolean;
  status: string;
  verified: boolean;
  scopes: string[];
  token_expires_at: string | null;
  verified_at: string | null;
  last_synced_at: string | null;
  last_refresh_error: string | null;
  analytics_video_count: number;
  audit_events: Array<{
    event_type: string;
    result: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
};

export type OpportunityWindow = {
  start: string;
  end: string;
  label: string;
};

export type UserFacingBucket = {
  label: "Low" | "Moderate" | "High" | "Very high";
  reason_codes: string[];
  version: string;
};

export type SignalDecisionCard = {
  decision: "Act" | "Watch" | "Skip";
  decision_label: string;
  decision_reason_codes: string[];
  decision_version: string;
  topic: string;
  thesis: string;
  why_now: string;
  why_this_channel: string;
  open_angle: string;
  recommended_video: string;
  release_ready: boolean;
  insight_status: "evidence_backed" | "candidate";
  insight_type: string;
  insight_statement: string;
  insight_reason_codes: string[];
  publishing_window: OpportunityWindow;
  production_effort: string;
  production_days_min: number;
  production_days_max: number;
  recommended_publish_by?: string;
  recommended_publish_by_label?: string;
  feasibility?: string;
  infeasibility_reasons?: string[];
  decay_version?: string;
  fit_verification?: "estimated" | "verified";
  signal_strength: UserFacingBucket;
  channel_fit: UserFacingBucket;
  confidence: UserFacingBucket;
  evidence_strength: UserFacingBucket;
  main_risk: string;
};

export type EvidenceQuality = {
  baseline_coverage_percent: number;
  transcript_coverage_percent: number;
  specificity_score: number;
  calibrated: boolean;
};

export type SignalEarlynessSummary = {
  claim_kind: "early" | "pending" | "late" | "unverified";
  headline: string;
  supporting_text: string;
  current_stage: string;
  lead_time_to_breakout_hours: number | null;
  lead_time_to_large_channel_hours: number | null;
};

export type LifecycleMilestone = {
  key: string;
  label: string;
  occurred_at: string | null;
  status: "reached" | "current" | "pending" | "not_observed";
  evidence_id: string | null;
};

export type SignalEarlyness = SignalEarlynessSummary & {
  topic_id: string;
  signal_id: string;
  first_video_published_at: string | null;
  first_discovered_at: string | null;
  first_topic_formed_at: string | null;
  first_seed_at: string | null;
  first_emerging_at: string | null;
  first_signal_visible_at: string | null;
  first_breakout_at: string | null;
  first_mass_market_at: string | null;
  first_saturated_at: string | null;
  first_declining_at: string | null;
  first_large_channel_adoption_at: string | null;
  latest_measurement_at: string | null;
  visible_age_hours: number | null;
  time_in_current_stage_hours: number | null;
  large_channel_threshold_subscribers: number;
  backfill_version: string;
  milestones: LifecycleMilestone[];
  transitions: Array<{
    id: string;
    from_stage: string | null;
    to_stage: string;
    transitioned_at: string;
    measurement_id: string | null;
    score: number | null;
    reason_codes: string[];
    history_version: string;
  }>;
  data_mode: string;
};

export type SignalListItem = {
  id: string;
  topic_label: string;
  category: string;
  lifecycle_stage: string;
  score: number;
  confidence: string;
  channel_fit: number;
  opportunity_window: OpportunityWindow;
  momentum: {
    change_24h: number;
    change_72h: number;
    sparkline: number[];
  };
  independent_channels: number;
  evidence_videos: number;
  evidence_preview: Array<{
    id: string;
    title: string;
    canonical_url: string;
    channel: string;
    published_at: string;
  }>;
  evidence_quality: EvidenceQuality;
  strongest_demand: {
    available: boolean;
    label: string;
    question: string;
    comment_count: number;
    distinct_channels: number;
    distinct_videos: number;
    distinct_commenters: number;
    evidence_strength: string;
  };
  thesis: string;
  current_action: string | null;
  generated_at: string;
  data_mode: string;
  earlyness: SignalEarlynessSummary | null;
  decision_card: SignalDecisionCard | null;
};

export type SignalFeedResponse = {
  items: SignalListItem[];
  total: number;
  data_freshness: string;
  data_mode: string;
  available_modes: string[];
};

export type EvidenceVideo = {
  id: string;
  youtube_video_id: string;
  title: string;
  canonical_url: string;
  thumbnail_url: string;
  channel: string;
  channel_subscribers: number;
  published_at: string;
  age_label: string;
  views: number;
  view_velocity: number;
  outlier_ratio: number;
  role: string;
  freshness: string;
  transcript_status: string;
  comment_sample_status: string;
  sparkline: number[];
};

export type TranscriptEvidence = {
  video_id: string;
  youtube_video_id: string;
  video_title: string;
  language: string;
  transcript_type: string;
  quality_score: number;
  summary: string;
  entities: string[];
  content_format: string;
  narrative_angle: string;
  fetched_at: string;
  segments: Array<{
    id: string;
    start_seconds: number;
    end_seconds: number;
    text: string;
    video_url: string;
  }>;
};

export type DemandCluster = {
  id: string;
  label: string;
  summary: string;
  taxonomy: string;
  comment_count: number;
  distinct_commenters: number;
  distinct_videos: number;
  distinct_channels: number;
  score: number;
  date_range: [string, string];
  snippets: Array<{
    comment_id: string;
    text: string;
    likes: number;
    video_id: string;
    video_title: string;
    video_url: string;
  }>;
  confidence: string;
  evidence_strength: string;
  limitation: string;
};

export type SignalDetail = {
  id: string;
  topic: {
    id: string;
    label: string;
    stage: string;
    aliases: string[];
    entities: string[];
    first_observed_at: string;
    first_confirmed_at: string;
    identity?: {
      domain: string;
      facet: string;
      primary_entity: string;
      secondary_entities: string[];
      audience: string;
      user_problem: string;
      core_claim: string;
      workflow_context: string;
      format_distribution: Record<string, number>;
    };
    specificity_score?: number;
    thesis_support_ratio?: number;
    visibility_reason_codes?: string[];
    clustering_version?: string;
  };
  score: number;
  confidence: string;
  channel_fit: number;
  opportunity_window: OpportunityWindow;
  thesis: string;
  why_emerging: string[];
  why_emerging_evidence: Array<{
    text: string;
    evidence_refs: string[];
  }>;
  intelligence_provenance: {
    method?: string;
    task?: string;
    run_id?: string;
    provider?: string;
    model?: string;
    prompt_version?: string;
    cached?: boolean;
  };
  score_components: Record<string, number>;
  evidence_quality: EvidenceQuality;
  evidence_videos: EvidenceVideo[];
  transcript_evidence: TranscriptEvidence[];
  demand_clusters: DemandCluster[];
  timeline: Array<{
    observed_at: string;
    video_count_24h: number;
    distinct_channels_72h: number;
    aggregate_view_velocity: number;
  }>;
  diffusion: Array<{
    channel: string;
    subscribers: number;
    published_at: string;
    role: string;
  }>;
  saturation: {
    score: number;
    label: string;
    large_channel_count: number;
    analysis: string;
  };
  channel_fit_detail: Record<string, string | number>;
  content_angles: ContentAngle[];
  current_action: string | null;
  data_freshness: Record<string, string>;
  provenance: Array<Record<string, string | number>>;
  data_mode: string;
  earlyness: SignalEarlyness | null;
  decision_card: SignalDecisionCard | null;
  content_gap_map: {
    pattern_version: string;
    gap_version: string;
    ranking_version: string;
    patterns: Array<Record<string, unknown>>;
    gaps: Array<{
      gap_key: string;
      rank: number;
      title?: string;
      occupied_pattern: Record<string, { value: string; share: number }>;
      open_gap: Record<string, string | boolean>;
      score_components: Record<string, number>;
      evidence: string[];
    }>;
  } | null;
};

export type SignalReviewStatus =
  | "internal_candidate"
  | "needs_review"
  | "approved"
  | "rejected"
  | "needs_changes"
  | "published"
  | "expired";

export type SignalReviewReason =
  | "false_topic_merge"
  | "too_broad"
  | "too_narrow"
  | "late_signal"
  | "single_channel_dependency"
  | "single_video_dependency"
  | "weak_outlier"
  | "weak_demand"
  | "irrelevant_comments"
  | "low_channel_fit"
  | "saturated"
  | "insufficient_evidence"
  | "duplicate_signal"
  | "other";

export type SignalReviewAction =
  | "approve"
  | "reject"
  | "request_split"
  | "request_merge"
  | "mark_late"
  | "mark_weak_evidence"
  | "mark_irrelevant_demand"
  | "edit_thesis"
  | "edit_opportunity"
  | "edit_evidence_selection";

export type SignalReviewSummary = {
  id: string;
  workspace_id: string;
  signal_id: string;
  topic_label: string;
  lifecycle_stage: string;
  signal_score: number;
  channel_fit: number;
  status: SignalReviewStatus;
  reviewer_id: string | null;
  reviewer_name: string | null;
  primary_reason: string | null;
  reason_codes: string[];
  submitted_at: string;
  first_reviewed_at: string | null;
  decided_at: string | null;
  updated_at: string;
  source_kind: string;
};

export type SignalReviewEvent = {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string;
  reviewer_id: string | null;
  reviewer_name: string | null;
  reason_codes: string[];
  note: string | null;
  changes: Record<string, unknown>;
  provenance: Record<string, unknown>;
  idempotency_key: string;
  created_at: string;
};

export type SignalReviewQueue = {
  items: SignalReviewSummary[];
  total: number;
  metrics: {
    total: number;
    status_counts: Record<string, number>;
    approval_rate: number;
    rejection_reasons: Record<string, number>;
    average_review_time_hours: number | null;
    stage_distribution: Record<string, Record<string, number>>;
  };
  filters: {
    statuses: string[];
    reasons: string[];
    sources: string[];
  };
};

export type SignalReviewDetail = {
  review: SignalReviewSummary;
  signal: SignalDetail;
  false_positive_risks: Array<{
    reason_code: string;
    severity: string;
    explanation: string;
    evidence_refs: string[];
  }>;
  decision_card_preview: Record<string, unknown>;
  thesis_override: string | null;
  opportunity_override: Record<string, unknown>;
  evidence_selection: string[];
  comment_relevance: CommentTopicRelevance[];
  audit_history: SignalReviewEvent[];
};

export type CommentTopicRelevance = {
  id: string;
  comment_id: string;
  comment_text: string;
  video_id: string;
  video_title: string;
  video_url: string;
  channel: string;
  intent: string;
  actionability: string;
  is_relevant: boolean;
  effective_relevant: boolean;
  relevance_score: number;
  comment_topic_semantic_similarity: number;
  comment_video_semantic_similarity: number;
  entity_overlap_score: number;
  claim_support_score: number;
  duplicate_or_echo_probability: number;
  supported_entities: string[];
  supported_claims: string[];
  reason_codes: string[];
  override_decision: boolean | null;
  override_reason: string | null;
  reviewer_id: string | null;
  reviewed_at: string | null;
  model_version: string;
};

export type ContentAngle = {
  title: string;
  audience_promise: string;
  why_now: string;
  evidence: string[];
  unanswered_question: string;
  format: string;
  effort: string;
  timing_risk: string;
  title_directions: string[];
  avoid: string;
  opportunity_id?: string;
  rank?: number;
  status?: string;
  channel_fit_score?: number;
  opportunity_confidence?: string;
  best_publish_window?: { start: string; end: string; label: string };
  expected_breakout_window?: { start: string; end: string };
  expected_saturation_window?: { start: string; end: string };
  production_time_days?: { min: number; max: number };
  fit_reasons?: string[];
  gap_key?: string;
  occupied_pattern?: Record<string, { value: string; share: number }>;
  open_gap?: Record<string, string | boolean>;
  differentiation?: string;
  ranking_score?: number;
  score_components?: Record<string, number>;
  content_gap_version?: string;
  opportunity_ranking_version?: string;
  release_ready?: boolean;
  insight_status?: "evidence_backed" | "candidate";
  insight_type?: string;
  insight_statement?: string;
  insight_reason_codes?: string[];
  insight_evidence?: string[];
  insight_metrics?: Record<string, unknown>;
  why_primary?: string;
  why_ranked_below_primary?: string;
  recommended_publish_by?: string;
  recommended_publish_by_label?: string;
  feasibility?: string;
  feasible_for_act?: boolean;
  infeasibility_reasons?: string[];
  decay_days?: number;
  decay_version?: string;
  timezone?: string;
};

export type BriefOutlineStep = {
  start: string;
  end: string;
  label: string;
};

export type BriefProofItem = {
  id: string;
  text: string;
  completed: boolean;
};

export type BriefDocument = ContentAngle & {
  owner?: string;
  target_publish_date?: string;
  audience_takeaway?: string;
  required_proof_checklist?: BriefProofItem[];
  production_notes?: string;
  suggested_opening?: BriefOutlineStep[];
  full_outline?: BriefOutlineStep[];
  brief_document_version?: string;
};

export type Brief = {
  id: string;
  workspace_id: string;
  signal_id: string;
  channel_id: string;
  opportunity_id: string | null;
  evidence_version: string;
  status: string;
  title: string;
  brief_json: BriefDocument;
  created_at: string;
  updated_at: string;
};

export type SignalPackaging = {
  id: string;
  workspace_id: string;
  signal_id: string;
  opportunity_id: string;
  content_brief_id: string;
  packaging: {
    audience_promise: string;
    core_tension: string;
    hook_directions: Array<{ strategy: string; direction: string }>;
    title_directions: Array<{ strategy: string; text: string }>;
    thumbnail_directions: Array<{
      strategy: string;
      main_visual: string;
      emotion: string;
      contrast: string;
      text: string;
      proof_object: string;
      avoid: string;
    }>;
    proof_requirements: string[];
    clickbait_mismatch_risks: string[];
    opening_structure: string[];
    claims_policy: {
      allowed: string[];
      requires_new_proof: string[];
    };
    full_script_generated: boolean;
    revision: number;
    version: string;
  };
  evidence_ids: string[];
  regeneration_counts: Record<string, number>;
  packaging_version: string;
  created_at: string;
  updated_at: string;
};

export type OutcomeComparatorFilters = {
  content_type?: string;
  duration_ratio?: string;
  topic_family?: string;
  upload_period_days?: number;
  sponsored?: boolean;
};

export type OutcomeComparator = {
  version?: string;
  sample_size?: number;
  minimum_stable_sample_size?: number;
  stability?: string;
  video_ids?: string[];
  filters?: OutcomeComparatorFilters;
  views_24h?: number | null;
  sample_size_24h?: number;
  stability_24h?: string;
  views_48h?: number | null;
  sample_size_48h?: number;
  stability_48h?: string;
  views_72h?: number | null;
  sample_size_72h?: number;
  stability_72h?: string;
  views_7d?: number | null;
  sample_size_7d?: number;
  stability_7d?: string;
  views_30d?: number | null;
  sample_size_30d?: number;
  stability_30d?: string;
  [key: string]: unknown;
};

export type OutcomePerformance = {
  version?: string;
  interpretation?: string;
  comparator?: OutcomeComparator;
  performance_ratio?: number;
  channel_relative_ratio?: number;
  views_24h?: number | null;
  baseline_views_24h?: number | null;
  channel_relative_uplift_24h?: number | null;
  views_48h?: number | null;
  baseline_views_48h?: number | null;
  views_72h?: number | null;
  baseline_views_72h?: number | null;
  channel_relative_uplift_72h?: number | null;
  views_7d?: number | null;
  views_168h?: number | null;
  baseline_views_7d?: number | null;
  channel_relative_uplift_7d?: number | null;
  views_30d?: number | null;
  baseline_views_30d?: number | null;
  channel_relative_uplift_30d?: number | null;
  average_view_duration_seconds?: number | null;
  average_view_duration?: number | null;
  [key: string]: unknown;
};

export type Outcome = {
  id: string;
  workspace_id: string;
  signal_id: string;
  content_brief_id: string | null;
  youtube_video_id: string;
  published_at: string;
  baseline_definition: string;
  performance_json: OutcomePerformance;
  success_status: string;
  user_notes: string;
  link_status: string;
  association_version: string;
  metrics_version: string;
  created_at: string;
  updated_at: string;
};

export type OutcomeSuggestion = {
  id: string;
  workspace_id: string;
  status: string;
  youtube_video_id: string;
  video_title: string;
  video_url: string;
  published_at: string;
  signal_id: string;
  suggested_brief_id: string;
  selected_brief_id: string | null;
  brief_title: string;
  match_confidence: number;
  reason_codes: string[];
  match_features: Record<string, string | number>;
  baseline: Record<string, unknown>;
  metrics: Record<string, unknown>;
  model_version: string;
  outcome_id: string | null;
  alternatives: Array<{
    id: string;
    signal_id: string;
    title: string;
  }>;
  detected_at: string;
  decided_at: string | null;
};

export type EvaluationLabel = {
  id: string;
  workspace_id: string | null;
  topic_id: string;
  signal_id: string | null;
  reviewer_id: string;
  as_of: string;
  label: string;
  additional_labels: string[];
  evidence_snapshot: Record<string, unknown>;
  notes: string;
  model_versions: Record<string, string>;
  label_version: string;
  created_at: string;
  updated_at: string;
};

export type EvaluationCandidate = {
  topic_id: string;
  topic_label: string;
  source_kind: string;
  lifecycle_stage: string;
  specificity_score: number;
  signal_id: string | null;
  signal_score: number | null;
  evidence_videos: number;
  reviewed: boolean;
  evaluation: EvaluationLabel | null;
};

export type EvaluationCandidateList = {
  items: EvaluationCandidate[];
  total: number;
  reviewed: number;
  primary_labels: string[];
  additional_labels: string[];
};

export type EvaluationReport = {
  reviewed_topics: number;
  label_counts: Record<string, number>;
  additional_label_counts: Record<string, number>;
  metrics: Record<string, number>;
  versions: Record<string, string>;
  production_weights_changed: boolean;
  decision_feedback: {
    total?: number;
    action_counts?: Record<string, number>;
    reason_counts?: Record<string, number>;
    comments?: number;
    feedback_version?: string;
  };
};

export type ProviderHealth = {
  provider: string;
  capability: string;
  enabled: boolean;
  priority: number;
  status: string;
  circuit_state: string;
  consecutive_failures: number;
  circuit_opened_at: string | null;
  half_open_probe_at: string | null;
  disabled_reason: string | null;
  request_count: number;
  request_count_hour: number;
  request_count_day: number;
  success_rate: number;
  error_rate: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  estimated_cost: number;
  spent_today_usd: number;
  daily_limit_usd: number;
  spent_month_usd: number;
  monthly_limit_usd: number;
  fallback_rate: number;
  last_error: string | null;
  updated_at: string;
  demo: boolean;
};

export type ProviderRoutingMetrics = {
  decisions: number;
  successful: number;
  failed: number;
  fallback_count: number;
  fallback_rate: number;
  open_circuits: number;
  disabled_capabilities: number;
  budget_skips: number;
};

export type ProviderRoutingDecision = {
  id: string;
  capability: string;
  operation_key: string;
  selected_provider: string | null;
  attempted_providers: Array<{
    provider: string;
    attempt: number;
    status: string;
    reason: string;
    latency_ms: number;
  }>;
  skipped_providers: Array<{ provider: string; reason: string }>;
  fallback_used: boolean;
  status: string;
  reason: string;
  created_at: string;
};

export type ProviderBenchmark = {
  id: string;
  benchmark_version: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  live_case_count: number;
  result: {
    mode?: string;
    fixture?: { query_count: number };
    metrics?: Array<Record<string, string | number>>;
    caveats?: string[];
  };
  recommended_priorities: Record<string, string[]>;
  json_path: string | null;
  csv_path: string | null;
  markdown_path: string | null;
  error_code: string | null;
  error_message: string | null;
};

export type ProviderFetch = {
  id: string;
  provider: string;
  capability: string;
  endpoint: string;
  started_at: string;
  latency_ms: number;
  status: string;
  http_status: number;
  raw_payload_uri: string;
  raw_payload_hash: string;
};

export type ProviderFetchDetail = ProviderFetch & {
  request_fingerprint: string;
  completed_at: string;
  attempt_number: number;
  estimated_cost: number;
  actual_cost: number;
  parser_version: string;
  error_code: string | null;
  error_message: string | null;
  linked_entity_ids: string[];
  raw_payload: Record<string, unknown>;
};

export type DiscoveryQuery = {
  id: string;
  query: string;
  category: string;
  priority: number;
  country: string;
  language: string;
  active: boolean;
  source: string;
  minimum_interval_seconds: number;
  expires_at: string | null;
  last_run_at: string | null;
  next_run_at: string;
  historical_yield: number;
  cost_per_retained_video: number;
  precision_score: number;
  precision_sample_size: number;
  quality_status: string;
  last_precision_at: string | null;
};

export type QuerySuggestion = {
  id: string;
  workspace_id: string | null;
  query: string;
  normalized_query: string;
  status:
    "suggested" | "approved" | "active" | "low_value" | "paused" | "retired";
  source_type: string;
  source_entity: string;
  source_topic_id: string | null;
  source_evidence_ids: string[];
  rationale: string;
  anchor_terms: string[];
  quality_reason_codes: string[];
  broadness_score: number;
  precision_score: number;
  precision_sample_size: number;
  discovery_query_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  model_version: string;
  created_at: string;
  updated_at: string;
};

export type IngestionRun = {
  id: string;
  query_id: string | null;
  channel_id: string | null;
  provider: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  result_count: number;
  unique_video_count: number;
  retained_video_count: number;
  estimated_cost: number;
  error_code: string | null;
  error_message: string | null;
};

export type MonitoredChannel = {
  workspace_id: string;
  channel_id: string;
  youtube_channel_id: string;
  title: string;
  relationship: string;
  priority: number;
  active: boolean;
  last_ingested_at: string | null;
  next_ingestion_at: string | null;
};

export type VideoIntelligenceMetrics = {
  live_videos: number;
  videos_with_snapshots: number;
  snapshot_coverage_percent: number;
  pending_jobs: number;
  due_jobs: number;
  failed_jobs: number;
  skipped_jobs: number;
  snapshot_lag_seconds: number;
  feature_count: number;
  baseline_count: number;
  latest_snapshot_at: string | null;
};

export type VideoIntelligenceItem = {
  video_id: string;
  youtube_video_id: string;
  title: string;
  channel: string;
  published_at: string;
  discovery_lag_seconds: number;
  snapshot_count: number;
  latest_snapshot_at: string | null;
  latest_views: number | null;
  view_velocity: number | null;
  velocity_acceleration: number | null;
  outlier_ratio: number | null;
  engagement_per_1000: number | null;
  next_snapshot_at: string | null;
  freshness: string;
};

export type VideoIntelligenceRun = {
  requested_jobs: number;
  requested_videos: number;
  completed_jobs: number;
  failed_jobs: number;
  snapshots_created: number;
  features_updated: number;
  baselines_updated: number;
};

export type TopicIntelligenceMetrics = {
  active_topics: number;
  active_signals: number;
  assigned_videos: number;
  embedding_count: number;
  stale_signals: number;
  latest_run_status: string | null;
  latest_run_at: string | null;
  source_video_count: number;
  eligible_video_count: number;
  clustering_lag_seconds: number;
  signal_generation_lag_seconds: number;
  llm_feature_enabled: boolean;
  llm_configured: boolean;
  llm_provider: string | null;
  llm_model: string | null;
  llm_auditor_model: string | null;
  llm_policy_version: string;
  llm_audit_required: boolean;
  llm_audit_run_count: number;
  llm_audit_acceptance_rate: number;
  llm_latest_trace_decisions: Record<string, number>;
  llm_circuit_open: boolean;
  llm_run_count: number;
  llm_successful_runs: number;
  llm_failed_or_rejected_runs: number;
  llm_latest_status: string | null;
  llm_latest_run_at: string | null;
};

export type TopicIntelligenceRun = {
  run_id: string;
  reused: boolean;
  source_videos: number;
  eligible_videos: number;
  topics: number;
  signals: number;
  assigned_videos: number;
};

export type DemandIntelligenceMetrics = {
  sampled_videos: number;
  comment_count: number;
  classified_count: number;
  cluster_count: number;
  internal_cluster_count: number;
  topics_with_demand: number;
  relevance_evaluated_count: number;
  relevance_accepted_count: number;
  relevance_rejected_count: number;
  demand_evidence_rejection_rate: number;
  demand_relevance_median: number | null;
  relevance_model_version: string | null;
  failed_fetches: number;
  comments_disabled_videos: number;
  latest_run_status: string | null;
  latest_run_at: string | null;
  processing_lag_seconds: number;
};

export type DemandIntelligenceRun = {
  run_id: string;
  reused: boolean;
  candidate_videos: number;
  fetched_videos: number;
  comments: number;
  classified: number;
  relevance_evaluated: number;
  relevance_accepted: number;
  relevance_rejected: number;
  clusters: number;
  provider_failures: number;
};

export type TranscriptIntelligenceMetrics = {
  eligible_videos: number;
  transcript_count: number;
  coverage_percent: number;
  native_count: number;
  auto_caption_count: number;
  generated_count: number;
  segment_count: number;
  evidence_segment_count: number;
  topics_with_transcript: number;
  unavailable_videos: number;
  failed_fetches: number;
  latest_run_status: string | null;
  latest_run_at: string | null;
  processing_lag_seconds: number;
};

export type TranscriptIntelligenceRun = {
  run_id: string;
  reused: boolean;
  candidates: number;
  fetched: number;
  unavailable: number;
  failed: number;
  segments: number;
};
