import { describe, expect, it } from "vitest";

import {
  evidenceGroup,
  groupEvidence,
  selectKeyEvidence,
} from "@/lib/evidence-selection";
import type { EvidenceVideo, TranscriptEvidence } from "@/lib/types";

function video(id: string, role: string, outlierRatio: number): EvidenceVideo {
  return {
    id,
    youtube_video_id: id,
    title: `Video ${id}`,
    canonical_url: `https://youtube.com/watch?v=${id}`,
    thumbnail_url: `https://i.ytimg.com/vi/${id}/hqdefault.jpg`,
    channel: `Channel ${id}`,
    channel_subscribers: 12_000,
    published_at: "2026-07-29T00:00:00Z",
    age_label: "12h ago",
    views: 42_000,
    view_velocity: 100,
    outlier_ratio: outlierRatio,
    role,
    freshness: "Fresh",
    transcript_status: "Manual",
    comment_sample_status: "Sampled",
    sparkline: [],
  };
}

function transcript(videoId: string): TranscriptEvidence {
  return {
    video_id: videoId,
    youtube_video_id: videoId,
    video_title: `Video ${videoId}`,
    language: "en",
    transcript_type: "manual",
    quality_score: 0.9,
    summary: "Stored transcript summary",
    entities: [],
    content_format: "demo",
    narrative_angle: "Private repository safety",
    fetched_at: "2026-07-29T00:00:00Z",
    segments: [],
  };
}

describe("key evidence selection", () => {
  it("keeps role diversity and caps the default list at five", () => {
    const videos = [
      video("d1", "driver", 2),
      video("d2", "driver", 3),
      video("d3", "driver", 8),
      video("a1", "amplifier", 2),
      video("a2", "amplifier", 3),
      video("a3", "amplifier", 8),
      video("s1", "supporting", 2),
      video("s2", "supporting", 9),
    ];

    const selected = selectKeyEvidence(videos, [transcript("d1")]);
    const groups = groupEvidence(selected);

    expect(selected).toHaveLength(5);
    expect(groups.driver).toHaveLength(2);
    expect(groups.amplifier).toHaveLength(2);
    expect(groups.supporting).toHaveLength(1);
    expect(selected.map((item) => item.id)).toContain("d1");
  });

  it("uses stored transcript availability before outlier within a role", () => {
    const selected = selectKeyEvidence(
      [
        video("d-with-transcript", "driver", 1.5),
        video("d-outlier", "driver", 8),
        video("d-third", "driver", 7),
        video("a1", "amplifier", 2),
        video("a2", "amplifier", 2),
        video("s1", "supporting", 2),
      ],
      [transcript("d-with-transcript")],
    );

    expect(selected.map((item) => item.id)).toContain("d-with-transcript");
    expect(selected.map((item) => item.id)).toContain("d-outlier");
    expect(selected.map((item) => item.id)).not.toContain("d-third");
  });

  it("normalizes unknown provider roles to supporting evidence", () => {
    expect(evidenceGroup("corroborating")).toBe("supporting");
  });
});
