import type { ContentAngle, EvidenceVideo, SignalDetail } from "@/lib/types";

export type StoredContentGap = NonNullable<
  SignalDetail["content_gap_map"]
>["gaps"][number];

export type ContentGapItem = {
  gap: StoredContentGap;
  angle?: ContentAngle;
};

function normalized(value: unknown) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

export function contentGapFingerprint(gap: StoredContentGap) {
  return ["claim", "proof_type", "context", "audience"]
    .map((key) => normalized(gap.open_gap[key]))
    .join("|");
}

export function selectDistinctContentGaps(
  gaps: StoredContentGap[],
  angles: ContentAngle[],
  limit = 3,
) {
  const angleByKey = new Map(
    angles
      .filter((angle) => angle.gap_key)
      .map((angle) => [angle.gap_key as string, angle]),
  );
  const sorted = [...gaps].sort(
    (a, b) => a.rank - b.rank || a.gap_key.localeCompare(b.gap_key),
  );
  const selected: ContentGapItem[] = [];
  const fingerprints = new Set<string>();

  for (const gap of sorted) {
    const fingerprint = contentGapFingerprint(gap);
    if (fingerprint && fingerprints.has(fingerprint)) continue;
    selected.push({ gap, angle: angleByKey.get(gap.gap_key) });
    if (fingerprint) fingerprints.add(fingerprint);
    if (selected.length >= limit) break;
  }
  return selected;
}

export function evidenceVideosForGap(
  item: ContentGapItem,
  videos: EvidenceVideo[],
) {
  const videoById = new Map<string, EvidenceVideo>();
  for (const video of videos) {
    videoById.set(video.id, video);
    videoById.set(video.youtube_video_id, video);
  }

  const matched: EvidenceVideo[] = [];
  const matchedIds = new Set<string>();
  for (const reference of item.gap.evidence) {
    if (!reference.startsWith("video:")) continue;
    const video = videoById.get(reference.slice("video:".length));
    if (!video || matchedIds.has(video.id)) continue;
    matched.push(video);
    matchedIds.add(video.id);
  }
  return matched;
}
