import { describe, expect, it } from "vitest";

import {
  latestBriefBySignal,
  opportunityGroup,
  opportunityGroupFromParam,
  opportunityStatusLabel,
} from "@/lib/opportunity-library";
import type { Brief, SignalListItem } from "@/lib/types";

function signal(overrides: Partial<SignalListItem> = {}): SignalListItem {
  return {
    id: "signal-1",
    topic_label: "Specific AI topic",
    category: "AI",
    lifecycle_stage: "Emerging",
    score: 72,
    confidence: "High",
    channel_fit: 81,
    opportunity_window: {
      start: "2026-08-01T00:00:00Z",
      end: "2026-08-05T00:00:00Z",
      label: "August 1–5",
    },
    momentum: { change_24h: 12, change_72h: 30, sparkline: [] },
    independent_channels: 4,
    evidence_videos: 6,
    evidence_preview: [],
    evidence_quality: {
      baseline_coverage_percent: 80,
      transcript_coverage_percent: 70,
      specificity_score: 0.9,
      calibrated: true,
    },
    strongest_demand: {
      available: false,
      label: "Unavailable",
      question: "",
      comment_count: 0,
      distinct_channels: 0,
      distinct_videos: 0,
      distinct_commenters: 0,
      evidence_strength: "Low",
    },
    thesis: "Evidence-backed thesis",
    current_action: null,
    generated_at: "2026-07-29T00:00:00Z",
    data_mode: "demo",
    ...overrides,
    earlyness: overrides.earlyness ?? null,
    decision_card: overrides.decision_card ?? null,
  };
}

function brief(overrides: Partial<Brief> = {}): Brief {
  return {
    id: "brief-1",
    workspace_id: "workspace-1",
    signal_id: "signal-1",
    channel_id: "channel-1",
    opportunity_id: null,
    evidence_version: "v1",
    status: "draft",
    title: "Brief",
    brief_json: {
      title: "Brief",
      audience_promise: "Promise",
      why_now: "Why now",
      evidence: [],
      unanswered_question: "Question",
      format: "Format neutral",
      effort: "Medium",
      timing_risk: "Low",
      title_directions: [],
      avoid: "",
    },
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
    ...overrides,
  };
}

describe("opportunity library grouping", () => {
  it("accepts only stable library group route values", () => {
    expect(opportunityGroupFromParam("watching")).toBe("watching");
    expect(opportunityGroupFromParam("needs_decision")).toBe("needs_decision");
    expect(opportunityGroupFromParam("unknown")).toBeNull();
    expect(opportunityGroupFromParam(null)).toBeNull();
  });

  it("keeps active work ahead of action and expiry groups", () => {
    const activeBrief = brief({ status: "in_production" });
    expect(
      opportunityGroup(
        signal({
          current_action: "watch",
          opportunity_window: {
            start: "2026-07-01T00:00:00Z",
            end: "2026-07-02T00:00:00Z",
            label: "Closed",
          },
        }),
        activeBrief,
        new Date("2026-07-29T00:00:00Z"),
      ),
    ).toBe("in_production");
    expect(opportunityStatusLabel("in_production", activeBrief)).toBe(
      "In production",
    );
  });

  it("separates tracked, dismissed, closed and open ideas", () => {
    const now = new Date("2026-07-29T00:00:00Z");
    expect(
      opportunityGroup(signal({ current_action: "watch" }), undefined, now),
    ).toBe("watching");
    expect(
      opportunityGroup(signal({ current_action: "skip" }), undefined, now),
    ).toBe("skipped");
    expect(
      opportunityGroup(
        signal({
          opportunity_window: {
            start: "2026-07-01T00:00:00Z",
            end: "2026-07-02T00:00:00Z",
            label: "Closed",
          },
        }),
        undefined,
        now,
      ),
    ).toBe("expired");
    expect(opportunityGroup(signal(), undefined, now)).toBe("needs_decision");
  });

  it("keeps unverified content-gap hypotheses out of the Inbox", () => {
    const candidate = signal({
      decision_card: {
        release_ready: false,
      } as SignalListItem["decision_card"],
    });

    expect(
      opportunityGroup(candidate, undefined, new Date("2026-07-29T00:00:00Z")),
    ).toBe("watching");
  });

  it("uses the latest non-archived brief per signal", () => {
    const result = latestBriefBySignal([
      brief({ id: "old", updated_at: "2026-07-20T00:00:00Z" }),
      brief({
        id: "archived",
        status: "archived",
        updated_at: "2026-07-30T00:00:00Z",
      }),
      brief({
        id: "latest",
        status: "approved",
        updated_at: "2026-07-29T00:00:00Z",
      }),
    ]);

    expect(result.get("signal-1")?.id).toBe("latest");
  });
});
