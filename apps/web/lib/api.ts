import type {
  AnalyticsSummary,
  DemandFeedResponse,
  AuthSession,
  Brief,
  BriefDocument,
  ChannelProfile,
  CommentTopicRelevance,
  DemoContext,
  DigestRun,
  DigestSubscription,
  DiscoveryQuery,
  EvaluationCandidateList,
  EvaluationLabel,
  EvaluationReport,
  IngestionRun,
  MonitoredChannel,
  OnboardingStatus,
  OperationsReadiness,
  Outcome,
  OutcomePerformance,
  OutcomeSuggestion,
  ProviderBenchmark,
  ProviderFetch,
  ProviderFetchDetail,
  ProviderHealth,
  ProviderRoutingDecision,
  ProviderRoutingMetrics,
  QuerySuggestion,
  SignalPackaging,
  SignalDetail,
  SignalEarlyness,
  SignalFeedResponse,
  SignalReviewAction,
  SignalReviewDetail,
  SignalReviewEvent,
  SignalReviewQueue,
  SignalReviewReason,
  TopicIntelligenceMetrics,
  TopicIntelligenceRun,
  DemandIntelligenceMetrics,
  DemandIntelligenceRun,
  TranscriptIntelligenceMetrics,
  TranscriptIntelligenceRun,
  VideoIntelligenceItem,
  VideoIntelligenceMetrics,
  VideoIntelligenceRun,
  YoutubeOAuthStatus,
} from "@/lib/types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    let message = detail || `Request failed with ${response.status}`;
    try {
      const parsed = JSON.parse(detail) as { detail?: string };
      message = parsed.detail ?? message;
    } catch {
      // Keep the server response text when it is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getAuthSession(): Promise<AuthSession> {
  return request("/auth/me");
}

export function registerAccount(payload: {
  name: string;
  email: string;
  password: string;
  workspace_name: string;
  timezone: string;
}): Promise<AuthSession> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginAccount(payload: {
  email: string;
  password: string;
}): Promise<AuthSession> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logoutAccount(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}

export function changeAccountPassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<{ detail: string }> {
  return request("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getDemoContext(): Promise<DemoContext> {
  return request("/context");
}

export function getAnalyticsSummary(
  workspaceId: string,
): Promise<AnalyticsSummary> {
  return request(`/workspaces/${workspaceId}/analytics/summary`);
}

export function trackProductEvent(
  workspaceId: string,
  payload: {
    event_type:
      | "signal_impression"
      | "signal_open"
      | "evidence_interaction"
      | "today_opened"
      | "opportunity_card_viewed"
      | "opportunity_opened"
      | "why_recommended_opened"
      | "evidence_opened"
      | "technical_details_opened"
      | "act_clicked"
      | "watch_clicked"
      | "skip_clicked"
      | "decision_reason_selected"
      | "brief_shared"
      | "production_started"
      | "result_opened"
      | "onboarding_started"
      | "onboarding_step_completed";
    event_key: string;
    signal_id?: string;
    metadata?: Record<string, string | number>;
  },
): Promise<{ id: string; event_type: string; occurred_at: string }> {
  return request(`/workspaces/${workspaceId}/analytics/events`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getDigestSubscription(
  workspaceId: string,
): Promise<DigestSubscription> {
  return request(`/workspaces/${workspaceId}/digest/subscription`);
}

export function updateDigestSubscription(
  workspaceId: string,
  payload: Omit<
    DigestSubscription,
    "workspace_id" | "next_run_at" | "last_generated_at"
  >,
): Promise<DigestSubscription> {
  return request(`/workspaces/${workspaceId}/digest/subscription`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getLatestDigest(workspaceId: string): Promise<DigestRun> {
  return request(`/workspaces/${workspaceId}/digest/latest`);
}

export function generateDigest(workspaceId: string): Promise<DigestRun> {
  return request(`/workspaces/${workspaceId}/digest/generate`, {
    method: "POST",
  });
}

export function getOnboardingStatus(
  workspaceId: string,
): Promise<OnboardingStatus> {
  return request(`/workspaces/${workspaceId}/onboarding`);
}

export function updateOnboardingWorkspace(
  workspaceId: string,
  payload: { name: string; timezone: string },
): Promise<OnboardingStatus> {
  return request(`/workspaces/${workspaceId}/onboarding/workspace`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function autoSetupOnboarding(
  workspaceId: string,
  youtubeChannel: string,
): Promise<OnboardingStatus> {
  return request(`/workspaces/${workspaceId}/onboarding/auto-setup`, {
    method: "POST",
    body: JSON.stringify({ youtube_channel: youtubeChannel }),
  });
}

export function prepareOnboardingDigest(
  workspaceId: string,
): Promise<OnboardingStatus> {
  return request(`/workspaces/${workspaceId}/onboarding/prepare-digest`, {
    method: "POST",
  });
}

export function completeOnboarding(
  workspaceId: string,
): Promise<OnboardingStatus> {
  return request(`/workspaces/${workspaceId}/onboarding/complete`, {
    method: "POST",
  });
}

export async function finishOnboarding(
  workspaceId: string,
): Promise<OnboardingStatus> {
  try {
    await prepareOnboardingDigest(workspaceId);
    return await completeOnboarding(workspaceId);
  } catch (error) {
    // A proxy or browser can lose the response after the server commits. Check
    // the authoritative state before telling the creator that setup failed.
    const status = await getOnboardingStatus(workspaceId).catch(() => null);
    if (status?.status === "completed") return status;
    throw error;
  }
}

export function getChannelProfile(
  workspaceId: string,
): Promise<ChannelProfile> {
  return request(`/workspaces/${workspaceId}/channel-profile`);
}

export function updateChannelProfile(
  workspaceId: string,
  payload: Omit<
    ChannelProfile,
    | "workspace_id"
    | "channel_id"
    | "channel_title"
    | "youtube_channel_id"
    | "profile_source"
    | "title_style"
    | "legacy_topics"
    | "successful_formats"
    | "upload_cadence"
    | "inference"
    | "explicit_overrides"
    | "profile_version"
    | "updated_at"
  >,
): Promise<ChannelProfile> {
  return request(`/workspaces/${workspaceId}/channel-profile`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getYoutubeOAuthStatus(
  workspaceId: string,
): Promise<YoutubeOAuthStatus> {
  return request(`/workspaces/${workspaceId}/oauth/youtube`);
}

export function startYoutubeOAuth(
  workspaceId: string,
): Promise<{ authorization_url: string }> {
  return request(`/workspaces/${workspaceId}/oauth/youtube/start`, {
    method: "POST",
    body: JSON.stringify({ redirect_after: "/settings" }),
  });
}

export function syncYoutubeAnalytics(
  workspaceId: string,
): Promise<{ updated_videos: number; status: string }> {
  return request(`/workspaces/${workspaceId}/oauth/youtube/sync`, {
    method: "POST",
  });
}

export function disconnectYoutubeOAuth(
  workspaceId: string,
): Promise<YoutubeOAuthStatus> {
  return request(`/workspaces/${workspaceId}/oauth/youtube/disconnect`, {
    method: "POST",
  });
}

export function getSignals(
  workspaceId: string,
  filters?: { stage?: string; action?: string; source?: string },
): Promise<SignalFeedResponse> {
  const params = new URLSearchParams();
  if (filters?.stage) params.set("stage", filters.stage);
  if (filters?.action) params.set("action", filters.action);
  if (filters?.source) params.set("source", filters.source);
  const suffix = params.size ? `?${params.toString()}` : "";
  return request(`/workspaces/${workspaceId}/signals${suffix}`);
}

export function getSignal(
  workspaceId: string,
  signalId: string,
): Promise<SignalDetail> {
  return request(`/workspaces/${workspaceId}/signals/${signalId}`);
}

export function getOpportunityDecisionCard(
  workspaceId: string,
  signalId: string,
): Promise<SignalDetail["decision_card"]> {
  return request(
    `/workspaces/${workspaceId}/opportunities/${signalId}/decision-card`,
  );
}

export function getSignalEarlyness(
  workspaceId: string,
  signalId: string,
): Promise<SignalEarlyness> {
  return request(`/workspaces/${workspaceId}/signals/${signalId}/earlyness`);
}

export function getSignalReviewQueue(
  workspaceId: string,
  filters?: { status?: string; source?: string },
): Promise<SignalReviewQueue> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (filters?.status) params.set("status", filters.status);
  if (filters?.source) params.set("source", filters.source);
  return request(`/admin/review/signals?${params.toString()}`);
}

export function getSignalReview(
  workspaceId: string,
  signalId: string,
): Promise<SignalReviewDetail> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return request(`/admin/review/signals/${signalId}?${params.toString()}`);
}

export function reviewSignal(
  workspaceId: string,
  signalId: string,
  payload: {
    action: SignalReviewAction;
    reason_codes?: SignalReviewReason[];
    note?: string;
    idempotency_key: string;
    thesis?: string;
    opportunity?: Record<string, unknown>;
    evidence_video_ids?: string[];
    merge_target_signal_id?: string;
  },
): Promise<SignalReviewEvent> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return request(
    `/admin/review/signals/${signalId}/actions?${params.toString()}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function overrideCommentRelevance(
  workspaceId: string,
  relevanceId: string,
  payload: {
    decision: boolean | null;
    reason: string;
    idempotency_key: string;
  },
): Promise<CommentTopicRelevance> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return request(
    `/admin/demand/relevance/${relevanceId}/override?${params.toString()}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function reclassifyCommentDemand(topicId?: string): Promise<{
  evaluated: number;
  accepted: number;
  rejected: number;
  changed: number;
  clusters: number;
  model_version: string;
}> {
  return request("/admin/demand/reclassify", {
    method: "POST",
    body: JSON.stringify({ topic_id: topicId }),
  });
}

export function actOnSignal(
  workspaceId: string,
  signalId: string,
  action: "act" | "watch" | "skip" | "save" | "dismiss",
  reason?: string,
  comment?: string,
  opportunityId?: string,
  plan?: { production_days?: number; target_publish_date?: string },
): Promise<{ action: string }> {
  return request(`/workspaces/${workspaceId}/signals/${signalId}/actions`, {
    method: "POST",
    body: JSON.stringify({
      action,
      reason: reason || undefined,
      comment: comment?.trim() || undefined,
      opportunity_id: opportunityId,
      production_days: plan?.production_days,
      target_publish_date: plan?.target_publish_date,
    }),
  });
}

export function createBrief(
  workspaceId: string,
  signalId: string,
  angleIndex = 0,
  opportunityId?: string,
): Promise<Brief> {
  return request(`/workspaces/${workspaceId}/signals/${signalId}/briefs`, {
    method: "POST",
    body: JSON.stringify({
      angle_index: angleIndex,
      opportunity_id: opportunityId,
    }),
  });
}

export function getBriefs(workspaceId: string): Promise<Brief[]> {
  return request(`/workspaces/${workspaceId}/briefs`);
}

export function updateBrief(
  workspaceId: string,
  briefId: string,
  payload: {
    title?: string;
    status?: "draft" | "approved" | "in_production" | "published" | "archived";
    brief_json?: BriefDocument;
  },
): Promise<Brief> {
  return request(`/workspaces/${workspaceId}/briefs/${briefId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getSignalPackaging(
  workspaceId: string,
  signalId: string,
  opportunityId: string,
): Promise<SignalPackaging> {
  const params = new URLSearchParams({ opportunity_id: opportunityId });
  return request(
    `/workspaces/${workspaceId}/signals/${signalId}/packaging?${params.toString()}`,
  );
}

export function regenerateSignalPackaging(
  workspaceId: string,
  signalId: string,
  opportunityId: string,
  section: string,
): Promise<SignalPackaging> {
  const params = new URLSearchParams({ opportunity_id: opportunityId });
  return request(
    `/workspaces/${workspaceId}/signals/${signalId}/packaging/regenerate?${params.toString()}`,
    {
      method: "POST",
      body: JSON.stringify({ section }),
    },
  );
}

export async function recordPackagingCopy(
  workspaceId: string,
  signalId: string,
  opportunityId: string,
  section: string,
  itemIndex?: number,
): Promise<void> {
  const params = new URLSearchParams({ opportunity_id: opportunityId });
  await request(
    `/workspaces/${workspaceId}/signals/${signalId}/packaging/copy?${params.toString()}`,
    {
      method: "POST",
      body: JSON.stringify({
        section,
        item_index: itemIndex,
      }),
    },
  );
}

export function getOutcomes(workspaceId: string): Promise<Outcome[]> {
  return request(`/workspaces/${workspaceId}/outcomes`);
}

export function getOutcomeSuggestions(
  workspaceId: string,
  status = "suggested",
): Promise<OutcomeSuggestion[]> {
  return request(
    `/workspaces/${workspaceId}/outcomes/suggestions?status=${encodeURIComponent(status)}`,
  );
}

export function confirmOutcomeSuggestion(
  workspaceId: string,
  suggestionId: string,
  contentBriefId?: string,
): Promise<OutcomeSuggestion> {
  return request(
    `/workspaces/${workspaceId}/outcomes/suggestions/${suggestionId}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ content_brief_id: contentBriefId }),
    },
  );
}

export function rejectOutcomeSuggestion(
  workspaceId: string,
  suggestionId: string,
): Promise<OutcomeSuggestion> {
  return request(
    `/workspaces/${workspaceId}/outcomes/suggestions/${suggestionId}/reject`,
    { method: "POST" },
  );
}

export function unlinkOutcome(
  workspaceId: string,
  outcomeId: string,
): Promise<Outcome> {
  return request(`/workspaces/${workspaceId}/outcomes/${outcomeId}/unlink`, {
    method: "POST",
  });
}

export function createOutcome(
  workspaceId: string,
  payload: {
    signal_id: string;
    content_brief_id: string;
    youtube_video_id: string;
    published_at: string;
    baseline_definition: string;
    performance_json: OutcomePerformance;
    success_status: string;
    user_notes: string;
  },
): Promise<Outcome> {
  return request(`/workspaces/${workspaceId}/outcomes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getEvaluationCandidates(
  source?: "live" | "demo",
): Promise<EvaluationCandidateList> {
  const params = new URLSearchParams({ limit: "100" });
  if (source) params.set("source", source);
  return request(`/admin/evaluation/candidates?${params.toString()}`);
}

export function labelEvaluationTopic(
  topicId: string,
  payload: {
    workspace_id?: string;
    label: string;
    additional_labels: string[];
    notes: string;
  },
): Promise<EvaluationLabel> {
  return request(`/admin/evaluation/topics/${topicId}/label`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getEvaluationReport(
  workspaceId?: string,
): Promise<EvaluationReport> {
  const suffix = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  return request(`/admin/evaluation/report${suffix}`);
}

export function evaluationExportUrl(
  kind: "labels" | "feedback",
  format: "jsonl" | "csv",
): string {
  const path =
    kind === "labels"
      ? `/admin/evaluation/export?format=${format}`
      : `/admin/evaluation/feedback/export?format=${format}`;
  return `${API_URL}${path}`;
}

export function getProviders(): Promise<ProviderHealth[]> {
  return request("/admin/providers");
}

export function updateProvider(
  provider: string,
  capability: string,
  payload: { enabled?: boolean; priority?: number },
): Promise<ProviderHealth> {
  return request(`/admin/providers/${provider}/${capability}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function resetProviderCircuit(
  provider: string,
  capability: string,
): Promise<ProviderHealth> {
  return request(`/admin/providers/${provider}/${capability}/reset-circuit`, {
    method: "POST",
  });
}

export function runProviderHealthCheck(): Promise<ProviderHealth[]> {
  return request("/admin/providers/health-check", { method: "POST" });
}

export function getOperationsReadiness(): Promise<OperationsReadiness> {
  return request("/admin/operations/readiness");
}

export function getProviderRoutingMetrics(): Promise<ProviderRoutingMetrics> {
  return request("/admin/provider-routing/metrics");
}

export function getProviderRoutingDecisions(): Promise<
  ProviderRoutingDecision[]
> {
  return request("/admin/provider-routing/decisions?limit=30");
}

export function getLatestProviderBenchmark(): Promise<ProviderBenchmark> {
  return request("/admin/providers/benchmark/latest");
}

export function runProviderBenchmark(
  live: boolean,
): Promise<ProviderBenchmark> {
  return request(`/admin/providers/benchmark?live=${live}&limit=3`, {
    method: "POST",
  });
}

export function getProviderFetches(): Promise<ProviderFetch[]> {
  return request("/admin/provider-fetches");
}

export function getProviderFetch(id: string): Promise<ProviderFetchDetail> {
  return request(`/admin/provider-fetches/${id}`);
}

export function replayProviderFetch(id: string): Promise<ProviderFetchDetail> {
  return request(`/admin/provider-fetches/${id}/replay`, { method: "POST" });
}

export function getDiscoveryQueries(): Promise<DiscoveryQuery[]> {
  return request("/admin/discovery-queries");
}

export function getQuerySuggestions(
  status = "all",
): Promise<QuerySuggestion[]> {
  return request(
    `/admin/query-suggestions?status=${encodeURIComponent(status)}`,
  );
}

export function runQueryExpansion(): Promise<{
  candidates_evaluated: number;
  suggestions_created: number;
  duplicates_skipped: number;
  low_value_queries_demoted: number;
  pending_suggestions: number;
  capped: boolean;
}> {
  return request("/admin/query-expansion/run", { method: "POST" });
}

export function transitionQuerySuggestion(
  suggestionId: string,
  action: "approve" | "activate" | "pause" | "retire",
): Promise<QuerySuggestion> {
  return request(`/admin/query-suggestions/${suggestionId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function createDiscoveryQuery(
  query: string,
  category = "AI / tech",
  priority = 2,
): Promise<DiscoveryQuery> {
  return request("/admin/discovery-queries", {
    method: "POST",
    body: JSON.stringify({ query, category, priority }),
  });
}

export function runDiscoveryQuery(
  id: string,
  force = true,
): Promise<IngestionRun> {
  return request(`/admin/discovery-queries/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ force, max_results: 20 }),
  });
}

export function getDiscoveryRuns(): Promise<IngestionRun[]> {
  return request("/admin/discovery-runs");
}

export function getMonitoredChannels(): Promise<MonitoredChannel[]> {
  return request("/admin/monitored-channels");
}

export function getWorkspaceChannels(
  workspaceId: string,
): Promise<MonitoredChannel[]> {
  return request(`/workspaces/${workspaceId}/channels`);
}

export function addMonitoredChannel(
  workspaceId: string,
  youtubeChannelId: string,
  relationship: "owned" | "competitor" | "reference" = "competitor",
): Promise<MonitoredChannel> {
  return request(`/workspaces/${workspaceId}/channels`, {
    method: "POST",
    body: JSON.stringify({
      youtube_channel_id: youtubeChannelId,
      relationship,
      priority: 1,
    }),
  });
}

export function updateMonitoredChannel(
  workspaceId: string,
  channelId: string,
  active: boolean,
): Promise<MonitoredChannel> {
  return request(`/workspaces/${workspaceId}/channels/${channelId}`, {
    method: "PATCH",
    body: JSON.stringify({ active }),
  });
}

export function runMonitoredChannel(id: string): Promise<IngestionRun> {
  return request(`/admin/monitored-channels/${id}/run`, {
    method: "POST",
    body: JSON.stringify({ force: true, max_results: 15 }),
  });
}

export function getVideoIntelligenceMetrics(): Promise<VideoIntelligenceMetrics> {
  return request("/admin/video-intelligence/metrics");
}

export function getVideoIntelligenceVideos(): Promise<VideoIntelligenceItem[]> {
  return request("/admin/video-intelligence/videos");
}

export function runVideoIntelligence(
  forceRefresh: boolean,
): Promise<VideoIntelligenceRun> {
  return request("/admin/video-intelligence/run", {
    method: "POST",
    body: JSON.stringify({ force_refresh: forceRefresh, limit: 50 }),
  });
}

export function getTopicIntelligenceMetrics(): Promise<TopicIntelligenceMetrics> {
  return request("/admin/topic-intelligence/metrics");
}

export function runTopicIntelligence(): Promise<TopicIntelligenceRun> {
  return request("/admin/topic-intelligence/run", { method: "POST" });
}

export function getDemandIntelligenceMetrics(): Promise<DemandIntelligenceMetrics> {
  return request("/admin/demand-intelligence/metrics");
}

export function runDemandIntelligence(): Promise<DemandIntelligenceRun> {
  return request("/admin/demand-intelligence/run?limit=12", { method: "POST" });
}

export function getTranscriptIntelligenceMetrics(): Promise<TranscriptIntelligenceMetrics> {
  return request("/admin/transcript-intelligence/metrics");
}

export function runTranscriptIntelligence(): Promise<TranscriptIntelligenceRun> {
  return request("/admin/transcript-intelligence/run?limit=8", {
    method: "POST",
  });
}

export function getDemandFeed(limit = 20): Promise<DemandFeedResponse> {
  return request<DemandFeedResponse>(`/demand/feed?limit=${limit}`);
}
