import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReviewPage from "./page";

const apiMocks = vi.hoisted(() => ({
  getDemoContext: vi.fn(),
  getSignalReview: vi.fn(),
  getSignalReviewQueue: vi.fn(),
  overrideCommentRelevance: vi.fn(),
  reclassifyCommentDemand: vi.fn(),
  reviewSignal: vi.fn(),
}));

vi.mock("@/lib/api", () => apiMocks);

const submittedAt = "2026-07-28T08:00:00Z";
const review = {
  id: "review-1",
  workspace_id: "workspace-1",
  signal_id: "signal-1",
  topic_label: "Concrete AI agent workflow",
  lifecycle_stage: "Emerging",
  signal_score: 82,
  channel_fit: 89,
  status: "needs_review",
  reviewer_id: null,
  reviewer_name: null,
  primary_reason: null,
  reason_codes: [],
  submitted_at: submittedAt,
  first_reviewed_at: null,
  decided_at: null,
  updated_at: submittedAt,
  source_kind: "live",
};

describe("human signal review workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getDemoContext.mockResolvedValue({ workspace_id: "workspace-1" });
    apiMocks.getSignalReviewQueue.mockResolvedValue({
      items: [review],
      total: 1,
      metrics: {
        total: 1,
        status_counts: { needs_review: 1 },
        approval_rate: 0,
        rejection_reasons: {},
        average_review_time_hours: null,
        stage_distribution: {},
      },
      filters: {
        statuses: ["needs_review", "approved", "rejected"],
        reasons: ["insufficient_evidence"],
        sources: ["live"],
      },
    });
    apiMocks.getSignalReview.mockResolvedValue({
      review,
      signal: {
        id: "signal-1",
        topic: { label: review.topic_label, stage: "Emerging" },
        score: 82,
        channel_fit: 89,
        thesis: "A specific stored-evidence thesis for this workflow.",
        content_angles: [{ title: "Test the exact workflow" }],
        evidence_videos: [
          {
            id: "video-1",
            title: "One exact workflow",
            channel: "Builder Lab",
            views: 42_000,
            outlier_ratio: 2.4,
            published_at: submittedAt,
          },
        ],
        evidence_quality: { transcript_coverage_percent: 80 },
        demand_clusters: [],
        earlyness: null,
        opportunity_window: { label: "3–5 days" },
        saturation: { score: 20 },
      },
      false_positive_risks: [
        {
          reason_code: "single_video_dependency",
          severity: "high",
          explanation: "Only one evidence video is stored.",
          evidence_refs: ["video-1"],
        },
      ],
      decision_card_preview: {},
      thesis_override: null,
      opportunity_override: {},
      evidence_selection: [],
      comment_relevance: [
        {
          id: "relevance-1",
          comment_id: "comment-1",
          comment_text: "Can you test this exact workflow on a real project?",
          video_id: "video-1",
          video_title: "One exact workflow",
          video_url: "https://youtube.com/watch?v=evidence-1",
          channel: "Builder Lab",
          intent: "test_or_proof_request",
          actionability: "high",
          is_relevant: true,
          effective_relevant: true,
          relevance_score: 0.88,
          comment_topic_semantic_similarity: 0.81,
          comment_video_semantic_similarity: 0.84,
          entity_overlap_score: 1,
          claim_support_score: 0.9,
          duplicate_or_echo_probability: 0,
          supported_entities: ["Concrete workflow"],
          supported_claims: ["real project"],
          reason_codes: ["entity_match", "video_claim_match", "accepted"],
          override_decision: null,
          override_reason: null,
          reviewer_id: null,
          reviewed_at: null,
          model_version: "comment-topic-relevance-v1",
        },
      ],
      audit_history: [
        {
          id: "event-1",
          event_type: "queued_for_review",
          from_status: null,
          to_status: "needs_review",
          reviewer_name: null,
          note: null,
          created_at: submittedAt,
        },
      ],
    });
    apiMocks.reviewSignal.mockResolvedValue({
      id: "event-approve",
      to_status: "approved",
    });
    apiMocks.overrideCommentRelevance.mockResolvedValue({
      id: "relevance-1",
      effective_relevant: false,
    });
    apiMocks.reclassifyCommentDemand.mockResolvedValue({
      evaluated: 1,
      accepted: 1,
      rejected: 0,
      changed: 0,
      clusters: 1,
      model_version: "comment-topic-relevance-v1",
    });
  });

  it("shows stored evidence, false-positive risks, audit, and explicit approval", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ReviewPage />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Signal review" }),
    ).toBeVisible();
    expect(screen.getByText(/no bulk approval/)).toBeVisible();
    expect(await screen.findByText("One exact workflow")).toBeVisible();
    expect(
      screen.getByText("Only one evidence video is stored."),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Audit history" }),
    ).toBeVisible();
    expect(
      screen.getByText(/Comment → source video → topic claim/),
    ).toBeVisible();
    expect(
      screen.getByText(/Can you test this exact workflow on a real project/),
    ).toBeVisible();

    fireEvent.click(screen.getAllByRole("button", { name: /^Reject$/ })[1]);
    await waitFor(() =>
      expect(apiMocks.overrideCommentRelevance).toHaveBeenCalledWith(
        "workspace-1",
        "relevance-1",
        expect.objectContaining({ decision: false }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /^Approve$/ }));
    await waitFor(() =>
      expect(apiMocks.reviewSignal).toHaveBeenCalledWith(
        "workspace-1",
        "signal-1",
        expect.objectContaining({
          action: "approve",
          reason_codes: ["other"],
        }),
      ),
    );
  });
});
