"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Captions,
  ChevronDown,
  Clock3,
  MessageCircleQuestion,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { OpportunityDecisionCard } from "@/components/opportunities/opportunity-decision-card";
import { OpportunityContentGap } from "@/components/opportunities/opportunity-content-gap";
import { OpportunityEvidenceList } from "@/components/opportunities/opportunity-evidence-list";
import { ErrorState, PageLoading } from "@/components/ui";
import { getDemoContext, getSignal, trackProductEvent } from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import { decisionCardFromSignal } from "@/lib/decision-card";
import { relativeTime } from "@/lib/format";
import type { OpportunityGroupKey } from "@/lib/opportunity-library";
import type { DemoContext, SignalDetail } from "@/lib/types";

type DetailData = { context: DemoContext; signal: SignalDetail };
type DetailTab = "Overview" | "Sources" | "Timing";

const tabs: DetailTab[] = ["Overview", "Sources", "Timing"];

function Evidence({ signal }: { signal: SignalDetail }) {
  return (
    <div className="space-y-6">
      <OpportunityEvidenceList signal={signal} />

      <section className="grid gap-5 lg:grid-cols-2">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
            <Captions size={14} /> What creators are saying
          </p>
          <div className="mt-3 space-y-3">
            {signal.transcript_evidence.length ? (
              signal.transcript_evidence.slice(0, 4).map((item) => (
                <article
                  className="border-l border-[var(--lime-strong)] pl-4"
                  key={item.video_id}
                >
                  <p className="text-[13px] font-semibold">
                    {item.video_title}
                  </p>
                  <p className="mt-1.5 text-[13px] leading-5 text-[var(--muted)]">
                    {item.summary}
                  </p>
                </article>
              ))
            ) : (
              <p className="text-[13px] text-[var(--muted)]">
                No public transcript is stored yet.
              </p>
            )}
          </div>
        </div>
        <div>
          <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
            <MessageCircleQuestion size={14} /> What viewers still need
          </p>
          <div className="mt-3 space-y-3">
            {signal.demand_clusters.length ? (
              signal.demand_clusters.map((cluster) => (
                <article key={cluster.id}>
                  <p className="text-[13px] font-semibold">{cluster.label}</p>
                  <p className="mt-1.5 text-[13px] leading-5 text-[var(--muted)]">
                    {cluster.summary}
                  </p>
                </article>
              ))
            ) : (
              <p className="text-[13px] text-[var(--muted)]">
                Audience demand stays unclaimed until comments repeat across
                independent videos and channels.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function Lifecycle({ signal }: { signal: SignalDetail }) {
  const milestones = signal.earlyness?.milestones ?? [];
  return (
    <section>
      <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
        Topic lifecycle
      </p>
      <h2 className="editorial mt-1.5 text-[30px]">
        How this opportunity reached today
      </h2>
      <ol className="relative mt-5 max-w-[760px] border-l border-[var(--line-strong)] pl-7">
        {milestones.length ? (
          milestones.map((milestone) => (
            <li className="relative pb-5 last:pb-0" key={milestone.key}>
              <span
                className={`absolute top-1 -left-[33px] h-3 w-3 rounded-full border-2 border-white ${
                  milestone.status === "current"
                    ? "bg-[var(--lime-strong)]"
                    : milestone.status === "reached"
                      ? "bg-[var(--ink)]"
                      : "bg-[var(--line-strong)]"
                }`}
              />
              <p className="text-[13px] font-semibold">{milestone.label}</p>
              <p className="mt-1 text-[12px] text-[var(--muted)]">
                {milestone.occurred_at
                  ? relativeTime(milestone.occurred_at)
                  : "Not observed yet"}
              </p>
            </li>
          ))
        ) : (
          <li className="relative">
            <Clock3 className="absolute -left-[38px] bg-white" size={20} />
            <p className="text-[13px] font-semibold">{signal.topic.stage}</p>
            <p className="mt-2 text-[12px] leading-5 text-[var(--muted)]">
              The recommendation uses stored historical snapshots. A richer
              lifecycle appears as new milestones are observed.
            </p>
          </li>
        )}
      </ol>
    </section>
  );
}

export function OpportunityDetail({
  signalId,
  initialTab = "Overview",
  initialAnalysisOpen = false,
  returnGroup = null,
}: {
  signalId: string;
  initialTab?: DetailTab;
  initialAnalysisOpen?: boolean;
  returnGroup?: OpportunityGroupKey | null;
}) {
  const opened = useRef(false);
  const query = useQuery<DetailData>({
    queryKey: ["opportunity-detail", signalId],
    queryFn: async () => {
      const context = await getDemoContext();
      const signal = await getSignal(context.workspace_id, signalId);
      return { context, signal };
    },
  });

  useEffect(() => {
    if (!query.data || opened.current) return;
    opened.current = true;
    const journeyStarted = Number(
      window.sessionStorage.getItem("earlysignal_today_started_at") ?? 0,
    );
    void trackProductEvent(query.data.context.workspace_id, {
      event_type: "opportunity_opened",
      event_key: `opportunity-opened:${createClientEventId()}:${signalId}`,
      signal_id: signalId,
      metadata: {
        surface: "opportunity_detail",
        time_from_today_ms: journeyStarted
          ? Math.max(Date.now() - journeyStarted, 0)
          : 0,
      },
    }).catch(() => undefined);
  }, [query.data, signalId]);

  if (query.isLoading) return <PageLoading label="Loading idea" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const { context, signal } = query.data;
  const card = decisionCardFromSignal(signal);
  const angle = signal.content_angles[0];
  const tab = initialTab;
  const returnHref = returnGroup
    ? `/opportunities?group=${returnGroup}`
    : "/opportunities";

  function tabHref(item: DetailTab) {
    const params = new URLSearchParams();
    if (returnGroup) params.set("from", returnGroup);
    if (item === "Sources") params.set("section", "evidence");
    if (item === "Timing") params.set("section", "lifecycle");
    const queryString = params.toString();
    return `/opportunities/${signalId}${queryString ? `?${queryString}` : ""}`;
  }

  return (
    <div className="motion-page mx-auto max-w-[1180px] px-5 py-3 pb-28 sm:px-8 sm:py-5 sm:pb-8">
      <Link
        className="inline-flex min-h-9 items-center gap-2 text-[13px] text-[var(--muted)] hover:text-[var(--ink)]"
        href={returnHref}
      >
        <ArrowLeft size={14} /> All ideas
      </Link>

      <header className="mt-1">
        <p className="hidden text-[11px] font-semibold tracking-[0.1em] text-[var(--lime-ink)] uppercase sm:block">
          Understand the idea, then choose what happens next
        </p>
        <nav
          aria-label="Opportunity detail sections"
          className="mt-2 flex w-fit gap-1 overflow-x-auto rounded-xl bg-[var(--surface-subtle)] p-1"
        >
          {tabs.map((item) => (
            <Link
              aria-selected={tab === item}
              className={`min-h-9 shrink-0 rounded-lg px-4 text-[13px] font-medium transition-[background-color,box-shadow,color] duration-200 ${
                tab === item
                  ? "bg-white text-[var(--ink)] shadow-sm"
                  : "text-[var(--muted)] hover:bg-white/70 hover:text-[var(--ink)]"
              }`}
              href={tabHref(item)}
              key={item}
              onClick={() => {
                if (item === "Sources") {
                  void trackProductEvent(context.workspace_id, {
                    event_type: "evidence_opened",
                    event_key: `evidence-opened:${createClientEventId()}:${signalId}`,
                    signal_id: signalId,
                    metadata: { surface: "opportunity_detail" },
                  }).catch(() => undefined);
                }
              }}
              role="tab"
              scroll={false}
            >
              {item}
            </Link>
          ))}
        </nav>
      </header>

      <main className="py-4" role="tabpanel">
        {tab === "Overview" ? (
          <>
            <OpportunityDecisionCard
              card={card}
              context={context}
              currentAction={signal.current_action}
              evidenceCount={signal.evidence_videos.length}
              evidenceLinks={signal.evidence_videos}
              headingLevel={1}
              opportunityId={angle?.opportunity_id}
              showDetailLink={false}
              signalId={signalId}
              stickyMobile
            />
            <details
              className="soft-disclosure group mt-4 rounded-xl border border-[var(--line)] bg-white px-4 shadow-[var(--shadow-soft)]"
              data-testid="gap-analysis"
              key={`gap-analysis-${initialAnalysisOpen ? "open" : "closed"}`}
              open={initialAnalysisOpen ? true : undefined}
            >
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-[13px] font-semibold">
                <span>
                  See how this differs from existing coverage
                  <span className="ml-2 font-normal text-[var(--muted)]">
                    optional analysis
                  </span>
                </span>
                <ChevronDown
                  className="shrink-0 transition-transform group-open:rotate-180"
                  size={16}
                />
              </summary>
              <div className="pt-2 pb-5">
                <OpportunityContentGap signal={signal} />
              </div>
            </details>
          </>
        ) : null}
        {tab === "Sources" ? <Evidence signal={signal} /> : null}
        {tab === "Timing" ? <Lifecycle signal={signal} /> : null}
      </main>

      <details
        className="soft-disclosure group rounded-xl border border-[var(--line)] bg-white px-4 shadow-[var(--shadow-soft)]"
        onToggle={(event) => {
          if (!event.currentTarget.open) return;
          void trackProductEvent(context.workspace_id, {
            event_type: "technical_details_opened",
            event_key: `technical-details:${createClientEventId()}:${signalId}`,
            signal_id: signalId,
            metadata: { surface: "opportunity_detail" },
          }).catch(() => undefined);
        }}
      >
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-[13px] font-semibold">
          Technical details
          <ChevronDown
            className="transition-transform group-open:rotate-180"
            size={16}
          />
        </summary>
        <div className="grid gap-5 pt-2 pb-6 text-[12px] leading-5 text-[var(--muted)] md:grid-cols-3">
          <div>
            <strong className="block text-[var(--ink)]">
              Score components
            </strong>
            {Object.entries(signal.score_components).map(([key, value]) => (
              <p key={key}>
                {key.replaceAll("_", " ")}: {Math.round(value)}
              </p>
            ))}
          </div>
          <div>
            <strong className="block text-[var(--ink)]">Coverage</strong>
            <p>
              Baseline:{" "}
              {Math.round(signal.evidence_quality.baseline_coverage_percent)}%
            </p>
            <p>
              Transcripts:{" "}
              {Math.round(signal.evidence_quality.transcript_coverage_percent)}%
            </p>
            <p>Evidence mode: {signal.data_mode}</p>
          </div>
          <div>
            <strong className="block text-[var(--ink)]">Provenance</strong>
            <p>{signal.provenance.length} stored provenance records</p>
            <p>
              Freshness:{" "}
              {signal.data_freshness.signal
                ? relativeTime(signal.data_freshness.signal)
                : "Not available"}
            </p>
            <p>Decision version: {card.decision_version}</p>
          </div>
        </div>
      </details>
    </div>
  );
}
