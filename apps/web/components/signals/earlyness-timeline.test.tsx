import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  EarlynessTimeline,
  formatLifecycleDate,
} from "@/components/signals/earlyness-timeline";
import type { SignalEarlyness } from "@/lib/types";

const earlyness: SignalEarlyness = {
  claim_kind: "pending",
  headline: "Currently Emerging",
  supporting_text:
    "Breakout not detected yet. Large-channel adoption not detected.",
  current_stage: "Emerging",
  lead_time_to_breakout_hours: null,
  lead_time_to_large_channel_hours: null,
  topic_id: "topic-1",
  signal_id: "signal-1",
  first_video_published_at: "2026-07-16T12:00:00Z",
  first_discovered_at: "2026-07-17T12:00:00Z",
  first_topic_formed_at: "2026-07-18T12:00:00Z",
  first_seed_at: "2026-07-18T12:00:00Z",
  first_emerging_at: "2026-07-20T12:00:00Z",
  first_signal_visible_at: "2026-07-20T12:00:00Z",
  first_breakout_at: null,
  first_mass_market_at: null,
  first_saturated_at: null,
  first_declining_at: null,
  first_large_channel_adoption_at: null,
  latest_measurement_at: "2026-07-26T12:00:00Z",
  visible_age_hours: 144,
  time_in_current_stage_hours: 144,
  large_channel_threshold_subscribers: 100_000,
  backfill_version: "topic-lifecycle-backfill-v1",
  milestones: [
    {
      key: "first_detected",
      label: "First detected",
      occurred_at: "2026-07-17T12:00:00Z",
      status: "reached",
      evidence_id: "video-1",
    },
    {
      key: "breakout",
      label: "Breakout",
      occurred_at: null,
      status: "pending",
      evidence_id: null,
    },
  ],
  transitions: [],
  data_mode: "demo",
};

describe("EarlynessTimeline", () => {
  it("opens stored lifecycle evidence and keeps pending events explicit", () => {
    render(<EarlynessTimeline earlyness={earlyness} currentStage="Emerging" />);

    expect(screen.getByText("Currently Emerging")).toBeVisible();
    fireEvent.click(screen.getByText("View lifecycle evidence"));
    expect(screen.getByText("First detected")).toBeVisible();
    expect(screen.getByText("Jul 17, 2026")).toBeVisible();
    expect(screen.getByText("Breakout")).toBeVisible();
    expect(screen.getByText("Not yet")).toBeVisible();
    expect(screen.getByText(/Missing events are not estimated/)).toBeVisible();
  });

  it("uses an honest fallback instead of invented dates", () => {
    render(<EarlynessTimeline earlyness={null} currentStage="Emerging" />);
    expect(screen.getByText("Current")).toBeVisible();
    expect(screen.queryByText(/Day \d/)).not.toBeInTheDocument();
  });
});

describe("formatLifecycleDate", () => {
  it("formats UTC dates and distinguishes pending from unobserved", () => {
    expect(formatLifecycleDate("2026-07-20T23:30:00Z", false)).toBe(
      "Jul 20, 2026",
    );
    expect(formatLifecycleDate(null, true)).toBe("Not yet");
    expect(formatLifecycleDate(null, false)).toBe("Not observed");
  });
});
