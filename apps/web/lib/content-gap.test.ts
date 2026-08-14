import { describe, expect, it } from "vitest";

import {
  evidenceVideosForGap,
  selectDistinctContentGaps,
  type StoredContentGap,
} from "@/lib/content-gap";
import type { ContentAngle, EvidenceVideo } from "@/lib/types";

function gap(
  key: string,
  rank: number,
  claim: string,
  proofType: string,
): StoredContentGap {
  return {
    gap_key: key,
    rank,
    occupied_pattern: {},
    open_gap: {
      audience: "AI builders",
      claim,
      context: "private repository",
      proof_type: proofType,
      is_open: true,
    },
    score_components: { evidence_strength: 88 },
    evidence: ["video:video-1"],
  };
}

function angle(key: string, title: string): ContentAngle {
  return {
    gap_key: key,
    title,
    audience_promise: "A stored audience promise",
    why_now: "A stored timing explanation",
    evidence: ["video:video-1"],
    unanswered_question: "A stored audience question?",
    format: "Creator choice",
    effort: "Medium",
    timing_risk: "A stored timing risk",
    title_directions: [],
    avoid: "Avoid unsupported claims",
  };
}

function video(): EvidenceVideo {
  return {
    id: "video-1",
    youtube_video_id: "youtube-1",
    title: "Stored evidence video",
    canonical_url: "https://youtube.com/watch?v=youtube-1",
    thumbnail_url: "https://i.ytimg.com/vi/youtube-1/hqdefault.jpg",
    channel: "Stored channel",
    channel_subscribers: 12_000,
    published_at: "2026-07-29T00:00:00Z",
    age_label: "1d",
    views: 42_000,
    view_velocity: 100,
    outlier_ratio: 2,
    role: "driver",
    freshness: "Fresh",
    transcript_status: "Native",
    comment_sample_status: "Sampled",
    sparkline: [],
  };
}

describe("content gap presentation", () => {
  it("keeps rank order and joins angles by stable gap key", () => {
    const selected = selectDistinctContentGaps(
      [
        gap("runner-up", 2, "show failure modes", "failure evidence"),
        gap("primary", 1, "run a real test", "original test"),
      ],
      [angle("runner-up", "Failure modes"), angle("primary", "Real test")],
    );

    expect(selected.map((item) => item.gap.gap_key)).toEqual([
      "primary",
      "runner-up",
    ]);
    expect(selected[0]?.angle?.title).toBe("Real test");
  });

  it("drops alternatives that repeat the same substantive gap", () => {
    const selected = selectDistinctContentGaps(
      [
        gap("primary", 1, "run a real test", "original test"),
        gap("reworded", 2, "run a real test", "original test"),
        gap("distinct", 3, "show failure modes", "failure evidence"),
      ],
      [],
    );

    expect(selected.map((item) => item.gap.gap_key)).toEqual([
      "primary",
      "distinct",
    ]);
  });

  it("resolves only stored video references to source links", () => {
    const item = {
      gap: {
        ...gap("primary", 1, "run a real test", "original test"),
        evidence: ["video:video-1", "demand:demand-1", "video:missing"],
      },
    };

    expect(evidenceVideosForGap(item, [video()])).toEqual([video()]);
  });
});
