"use client";

import { Captions, ChevronDown, ExternalLink, PlaySquare } from "lucide-react";
import Image from "next/image";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui";
import {
  EVIDENCE_GROUPS,
  evidenceGroup,
  groupEvidence,
  selectKeyEvidence,
  transcriptByVideo,
  type EvidenceGroupKey,
} from "@/lib/evidence-selection";
import { compactNumber } from "@/lib/format";
import type {
  EvidenceVideo,
  SignalDetail,
  TranscriptEvidence,
} from "@/lib/types";

const ROLE_LABELS: Record<EvidenceGroupKey, string> = {
  driver: "Driver",
  amplifier: "Amplifier",
  supporting: "Supporting",
};

function Thumbnail({ video }: { video: EvidenceVideo }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className="relative aspect-video overflow-hidden rounded-xl bg-[var(--surface-subtle)]">
      {failed || !video.thumbnail_url ? (
        <span className="grid h-full place-items-center text-[var(--muted)]">
          <PlaySquare aria-hidden="true" size={24} />
        </span>
      ) : (
        <Image
          alt=""
          className="h-full w-full object-cover"
          height={99}
          onError={() => setFailed(true)}
          sizes="(max-width: 767px) 112px, 176px"
          src={video.thumbnail_url}
          unoptimized
          width={176}
        />
      )}
      {!failed && video.thumbnail_url ? (
        <span className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-black/65 text-white">
            <PlaySquare aria-hidden="true" size={14} />
          </span>
        </span>
      ) : null}
    </div>
  );
}

function outlierLabel(value: number) {
  return `${value.toFixed(1).replace(/\.0$/, "")}× channel baseline`;
}

function EvidenceSource({
  video,
  transcript,
}: {
  video: EvidenceVideo;
  transcript?: TranscriptEvidence;
}) {
  const role = ROLE_LABELS[evidenceGroup(video.role)];

  return (
    <article
      className="grid grid-cols-[112px_minmax(0,1fr)] gap-4 rounded-xl border border-transparent px-2 py-2.5 transition-[transform,background-color,border-color] duration-200 hover:-translate-y-px hover:border-[var(--line)] hover:bg-[var(--surface-subtle)] md:grid-cols-[160px_minmax(0,1fr)_180px] md:gap-4 md:px-3 md:py-4"
      data-testid="evidence-source"
    >
      <Thumbnail video={video} />
      <div className="min-w-0">
        <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--lime-ink)] uppercase">
          {role}
        </p>
        <a
          className="mt-1 inline-flex items-start gap-2 text-[14px] leading-5 font-semibold hover:underline"
          href={video.canonical_url}
          rel="noreferrer"
          target="_blank"
        >
          {video.title}
          <ExternalLink
            aria-hidden="true"
            className="mt-1 shrink-0"
            size={12}
          />
        </a>
        <p className="mt-1.5 text-[12px] text-[var(--muted)]">
          {video.channel} · {compactNumber(video.channel_subscribers)}{" "}
          subscribers
        </p>
        <div className="mt-2.5 border-l-2 border-[var(--lime-strong)] pl-3">
          <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
            Angle contribution
          </p>
          <p className="mt-1 text-[12px] leading-5">
            {transcript?.narrative_angle ||
              "No transcript-grounded angle contribution is stored."}
          </p>
        </div>
      </div>
      <dl className="col-span-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[12px] md:col-span-1 md:block md:space-y-2.5">
        <div>
          <dt className="text-[var(--muted)]">Published</dt>
          <dd className="mt-1 font-semibold">{video.age_label} ago</dd>
        </div>
        <div>
          <dt className="text-[var(--muted)]">Outlier</dt>
          <dd className="mt-1 font-semibold">
            {outlierLabel(video.outlier_ratio)}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--muted)]">Transcript</dt>
          <dd className="mt-1 flex items-center gap-1.5 font-semibold">
            <Captions aria-hidden="true" size={12} />
            {video.transcript_status}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--muted)]">Views</dt>
          <dd className="mt-1 font-medium text-[var(--muted)]">
            {compactNumber(video.views)}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function OpportunityEvidenceList({ signal }: { signal: SignalDetail }) {
  const [showAll, setShowAll] = useState(false);
  const keyEvidence = useMemo(
    () => selectKeyEvidence(signal.evidence_videos, signal.transcript_evidence),
    [signal.evidence_videos, signal.transcript_evidence],
  );
  const visibleEvidence = showAll ? signal.evidence_videos : keyEvidence;
  const groupedEvidence = useMemo(
    () => groupEvidence(visibleEvidence),
    [visibleEvidence],
  );
  const transcripts = useMemo(
    () => transcriptByVideo(signal.transcript_evidence),
    [signal.transcript_evidence],
  );

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
            {showAll ? "All stored evidence" : "Key evidence only"}
          </p>
          <h2 className="editorial mt-2 max-w-[720px] text-[30px] leading-[1.08] sm:text-[32px]">
            Evidence behind the recommendation
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <p className="text-[12px] text-[var(--muted)]">
            {visibleEvidence.length} of {signal.evidence_videos.length} sources
          </p>
          {signal.evidence_videos.length > keyEvidence.length ? (
            <Button
              aria-expanded={showAll}
              className="min-h-9"
              onClick={() => setShowAll((current) => !current)}
            >
              {showAll ? "Show key evidence" : "Show all"}
              <ChevronDown
                aria-hidden="true"
                className={`transition-transform ${
                  showAll ? "rotate-180" : ""
                }`}
                size={14}
              />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="motion-list mt-4 space-y-5">
        {EVIDENCE_GROUPS.map((group) => {
          const videos = groupedEvidence[group.key];
          if (!videos.length) return null;
          return (
            <section
              aria-labelledby={`evidence-${group.key}`}
              data-testid={`evidence-group-${group.key}`}
              key={group.key}
            >
              <div className="flex items-baseline justify-between gap-3 border-b border-[var(--line-strong)] pb-2.5">
                <div>
                  <h3
                    className="text-[13px] font-semibold"
                    id={`evidence-${group.key}`}
                  >
                    {group.label}
                  </h3>
                  <p className="mt-1 text-[12px] text-[var(--muted)]">
                    {group.description}
                  </p>
                </div>
                <span className="text-[12px] text-[var(--muted)]">
                  {videos.length}
                </span>
              </div>
              <div>
                {videos.map((video) => (
                  <EvidenceSource
                    key={video.id}
                    transcript={transcripts.get(video.id)}
                    video={video}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}
