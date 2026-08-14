import type { EvidenceVideo, TranscriptEvidence } from "@/lib/types";

export const EVIDENCE_GROUPS = [
  {
    key: "driver",
    label: "Drivers",
    description: "Primary sources that moved the signal.",
  },
  {
    key: "amplifier",
    label: "Amplifiers",
    description: "Independent sources that confirmed or accelerated it.",
  },
  {
    key: "supporting",
    label: "Supporting evidence",
    description: "Additional corroboration behind the recommendation.",
  },
] as const;

export type EvidenceGroupKey = (typeof EVIDENCE_GROUPS)[number]["key"];

export function evidenceGroup(role: string): EvidenceGroupKey {
  if (role.toLowerCase() === "driver") return "driver";
  if (role.toLowerCase() === "amplifier") return "amplifier";
  return "supporting";
}

function compareEvidence(
  a: EvidenceVideo,
  b: EvidenceVideo,
  transcriptIds: Set<string>,
) {
  const transcriptDelta =
    Number(transcriptIds.has(b.id)) - Number(transcriptIds.has(a.id));
  if (transcriptDelta !== 0) return transcriptDelta;
  if (b.outlier_ratio !== a.outlier_ratio) {
    return b.outlier_ratio - a.outlier_ratio;
  }
  if (b.view_velocity !== a.view_velocity) {
    return b.view_velocity - a.view_velocity;
  }
  return (
    new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
  );
}

export function selectKeyEvidence(
  videos: EvidenceVideo[],
  transcriptEvidence: TranscriptEvidence[],
  limit = 5,
) {
  if (videos.length <= limit) return [...videos];

  const transcriptIds = new Set(
    transcriptEvidence.map((transcript) => transcript.video_id),
  );
  const grouped: Record<EvidenceGroupKey, EvidenceVideo[]> = {
    driver: [],
    amplifier: [],
    supporting: [],
  };
  for (const video of videos) {
    grouped[evidenceGroup(video.role)].push(video);
  }
  for (const group of EVIDENCE_GROUPS) {
    grouped[group.key].sort((a, b) => compareEvidence(a, b, transcriptIds));
  }

  const selected: EvidenceVideo[] = [];
  const selectedIds = new Set<string>();
  const quotas: Record<EvidenceGroupKey, number> = {
    driver: 2,
    amplifier: 2,
    supporting: 1,
  };
  for (const group of EVIDENCE_GROUPS) {
    for (const video of grouped[group.key].slice(0, quotas[group.key])) {
      if (selected.length >= limit) break;
      selected.push(video);
      selectedIds.add(video.id);
    }
  }

  if (selected.length < limit) {
    const remaining = [...videos]
      .filter((video) => !selectedIds.has(video.id))
      .sort((a, b) => compareEvidence(a, b, transcriptIds));
    selected.push(...remaining.slice(0, limit - selected.length));
  }
  return selected;
}

export function groupEvidence(videos: EvidenceVideo[]) {
  const grouped: Record<EvidenceGroupKey, EvidenceVideo[]> = {
    driver: [],
    amplifier: [],
    supporting: [],
  };
  for (const video of videos) {
    grouped[evidenceGroup(video.role)].push(video);
  }
  return grouped;
}

export function transcriptByVideo(transcripts: TranscriptEvidence[]) {
  return new Map(
    transcripts.map((transcript) => [transcript.video_id, transcript]),
  );
}
