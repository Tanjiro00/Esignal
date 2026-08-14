"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Bookmark,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Ellipsis,
  FilePlus2,
  Info,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Sparkline } from "@/components/sparkline";
import { Button, ErrorState, PageLoading } from "@/components/ui";
import {
  actOnSignal,
  createBrief,
  getDemoContext,
  getSignals,
  trackProductEvent,
} from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import { relativeTime, scoreTone } from "@/lib/format";
import type {
  DemoContext,
  SignalFeedResponse,
  SignalListItem,
} from "@/lib/types";

type FeedData = {
  context: DemoContext;
  feed: SignalFeedResponse;
};

const stageTone: Record<string, string> = {
  Seed: "text-[var(--lime-ink)]",
  Emerging: "text-[var(--lime-strong)]",
  Breakout: "text-[var(--lime-strong)]",
  "Mass Market": "text-[var(--amber)]",
  Saturated: "text-[var(--coral)]",
};

function scoreLabel(score: number) {
  const tone = scoreTone(score);
  if (tone === "strong") return "Strong";
  if (tone === "risk") return "Weak";
  return "Watch";
}

function fitLabel(score: number) {
  if (score >= 85) return "High";
  if (score >= 65) return "Good";
  return "Low";
}

function whyNow(signal: SignalListItem) {
  if (signal.topic_label === "Claude Code autonomous workflows") {
    return [
      "Claude Code can now handle longer multi-file changes and tests autonomously.",
      "Independent builder channels are publishing complete workflow demonstrations.",
      "Audience discussion centers on safety, permissions, and protecting private code.",
    ];
  }

  return [
    `${signal.evidence_videos} recent videos show the topic moving beyond isolated experiments.`,
    `Coverage is spreading across ${signal.independent_channels} independent creator channels.`,
    signal.strongest_demand.available
      ? `Audience questions are converging on “${signal.strongest_demand.label.toLowerCase()}”.`
      : "Audience demand stays excluded until a sampled cluster spans multiple videos and channels.",
  ];
}

function SignalListRow({
  signal,
  selected,
  onSelect,
}: {
  signal: SignalListItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      aria-label={`Review ${signal.topic_label}`}
      aria-pressed={selected}
      className={`relative grid w-full grid-cols-[minmax(0,1fr)_76px_76px_62px] gap-4 border-b border-[var(--line)] px-5 py-5 text-left transition-colors last:border-b-0 hover:bg-[var(--surface-subtle)] focus-visible:z-10 max-sm:grid-cols-3 max-sm:gap-x-3 xl:py-7 ${
        selected ? "bg-[#fbfdf5]" : "bg-white"
      }`}
      data-testid="signal-row"
      onClick={onSelect}
      type="button"
    >
      {selected && (
        <span className="absolute inset-y-0 left-0 w-[3px] bg-[var(--lime)]" />
      )}

      <span className="min-w-0 max-sm:col-span-3">
        <span className="flex items-start gap-3">
          <span
            className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
              signal.lifecycle_stage === "Saturated"
                ? "bg-[var(--coral)]"
                : "bg-[var(--lime)]"
            }`}
          />
          <span className="min-w-0">
            <strong className="block text-[14px] leading-[1.35] font-semibold tracking-[-0.015em]">
              {signal.topic_label}
            </strong>
            <span
              className={`mt-2 block text-[12px] font-medium ${stageTone[signal.lifecycle_stage] ?? "text-[var(--muted)]"}`}
            >
              {signal.lifecycle_stage}
            </span>
            {signal.earlyness ? (
              <span className="mt-2 flex items-start gap-1.5 text-[10px] leading-snug font-medium text-[var(--ink)]">
                <Clock3
                  aria-hidden="true"
                  className="mt-px shrink-0"
                  size={11}
                />
                {signal.earlyness.headline}
              </span>
            ) : null}
            <span className="mt-2 block text-[10px] tracking-[0.06em] text-[var(--muted)] uppercase">
              {signal.decision_card
                ? `${signal.decision_card.evidence_strength.label} evidence`
                : signal.evidence_quality.calibrated
                  ? "Calibrated evidence"
                  : "Evidence still calibrating"}
            </span>
            <span className="mt-2 hidden items-center gap-1 text-[11px] font-medium text-[var(--ink)] max-sm:inline-flex">
              Review details
              <ArrowRight aria-hidden="true" className="rotate-90" size={13} />
            </span>
          </span>
        </span>
      </span>

      <span className="max-sm:mt-4">
        <span className="mb-2 hidden text-[10px] tracking-[0.08em] text-[var(--muted)] uppercase max-sm:block">
          Decision
        </span>
        <span
          className={`block text-[11px] leading-tight font-semibold tracking-[0.08em] ${
            signal.decision_card?.decision === "Skip"
              ? "text-[var(--coral)]"
              : "text-[var(--lime-ink)]"
          }`}
        >
          {signal.decision_card?.decision_label ??
            scoreLabel(signal.score).toUpperCase()}
        </span>
        <span className="mt-1.5 block text-[10px] text-[var(--muted)]">
          {signal.decision_card?.signal_strength.label ??
            scoreLabel(signal.score)}
        </span>
      </span>

      <span className="max-sm:mt-4">
        <span className="mb-2 hidden text-[10px] tracking-[0.08em] text-[var(--muted)] uppercase max-sm:block">
          Window
        </span>
        <span className="block text-[13px] font-medium">
          {signal.opportunity_window.label}
        </span>
        <span className="mt-1.5 block text-[11px] text-[var(--muted)]">
          {signal.lifecycle_stage === "Saturated" ? "Crowded" : "Actionable"}
        </span>
      </span>

      <span className="text-right max-sm:mt-4">
        <span className="mb-2 hidden text-[10px] tracking-[0.08em] text-[var(--muted)] uppercase max-sm:block">
          Evidence
        </span>
        <span className="mono block text-[18px] leading-none">
          {signal.evidence_videos}
        </span>
        <span className="mt-1.5 block text-[10px] leading-relaxed text-[var(--muted)]">
          videos
          <br />
          {signal.independent_channels} ch.
        </span>
      </span>
    </button>
  );
}

function DecisionMetric({
  label,
  value,
  qualifier,
  description,
  accent = false,
  compact = false,
}: {
  label: string;
  value: string;
  qualifier: string;
  description: string;
  accent?: boolean;
  compact?: boolean;
}) {
  return (
    <div className="min-w-0 border-r border-[var(--line)] pr-5 last:border-r-0 max-sm:nth-[2n]:border-r-0 max-sm:nth-[2n]:pr-0">
      <p className="flex items-center gap-1.5 text-[12px] font-medium">
        {label}
        <Info aria-hidden="true" size={13} strokeWidth={1.5} />
      </p>
      <p
        className={`editorial mt-4 leading-none ${
          compact ? "text-[29px]" : "text-[36px]"
        }`}
      >
        {value}
        {accent && (
          <span className="ml-2 align-middle font-sans text-[12px] tracking-normal text-[var(--lime-strong)]">
            {qualifier}
          </span>
        )}
      </p>
      {!accent && (
        <p className="mt-2 text-[11px] text-[var(--lime-strong)]">
          {qualifier}
        </p>
      )}
      <p className="mt-4 text-[10px] leading-relaxed text-[var(--muted)]">
        {description}
      </p>
    </div>
  );
}

function SelectedSignal({
  signal,
  busy,
  freshness,
  onSave,
  onDismiss,
  onBrief,
}: {
  signal: SignalListItem;
  busy: boolean;
  freshness: string;
  onSave: () => void;
  onDismiss: () => void;
  onBrief: () => void;
}) {
  const reasons = whyNow(signal);
  const negative = signal.momentum.change_72h < 0;

  return (
    <section
      aria-label={`Selected signal: ${signal.topic_label}`}
      className="flex min-w-0 scroll-mt-[calc(var(--topbar)+16px)] flex-col bg-white lg:scroll-mt-4"
      id="selected-signal"
    >
      <div className="flex items-start justify-between gap-6 border-b border-[var(--line)] px-7 py-7 max-sm:px-5">
        <div className="min-w-0">
          <p className="mb-2 text-[11px] font-semibold tracking-[0.12em] text-[var(--muted)] uppercase xl:hidden">
            Selected signal
          </p>
          <h2 className="editorial text-[30px] leading-[1.08] tracking-[-0.035em] sm:text-[34px]">
            {signal.topic_label}
          </h2>
        </div>

        <details className="group relative shrink-0">
          <summary
            aria-label="More signal actions"
            className="grid h-10 w-10 cursor-pointer list-none place-items-center border border-transparent hover:border-[var(--line-strong)]"
          >
            <Ellipsis aria-hidden="true" size={20} />
          </summary>
          <div className="absolute top-11 right-0 z-20 w-44 border border-[var(--line-strong)] bg-white p-1 shadow-sm">
            <button
              className="flex h-10 w-full items-center gap-2 px-3 text-left text-[13px] hover:bg-[var(--surface-subtle)]"
              disabled={busy}
              onClick={onSave}
              type="button"
            >
              {signal.current_action === "save" ? (
                <Check size={15} />
              ) : (
                <Bookmark size={15} />
              )}
              {signal.current_action === "save" ? "Saved" : "Save signal"}
            </button>
            <button
              className="flex h-10 w-full items-center gap-2 px-3 text-left text-[13px] hover:bg-[var(--surface-subtle)]"
              disabled={busy}
              onClick={onDismiss}
              type="button"
            >
              <X size={15} />
              Dismiss
            </button>
          </div>
        </details>
      </div>

      {signal.earlyness ? (
        <div
          className="mx-7 mt-6 border-l-2 border-[var(--lime-strong)] bg-[#f8fce9] px-4 py-3 max-sm:mx-5"
          data-testid="selected-signal-earlyness"
        >
          <p className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.08em] uppercase">
            <Clock3 aria-hidden="true" size={13} />
            {signal.earlyness.headline}
          </p>
          <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--muted)]">
            {signal.earlyness.supporting_text}
          </p>
        </div>
      ) : null}

      <div className="px-7 pt-6 max-sm:px-5">
        <h3 className="text-[15px] font-semibold">
          Why this is worth reviewing now
        </h3>
        <ul className="mt-4 space-y-3">
          {reasons.map((reason) => (
            <li
              className="flex items-start gap-3 text-[13px] leading-relaxed text-[var(--muted)]"
              key={reason}
            >
              <CheckCircle2
                aria-hidden="true"
                className="mt-0.5 shrink-0 text-[var(--lime-strong)]"
                size={16}
              />
              {reason}
            </li>
          ))}
        </ul>
      </div>

      <div className="mx-7 mt-6 grid grid-cols-2 gap-x-5 gap-y-7 border-y border-[var(--line)] py-6 max-sm:mx-5 lg:grid-cols-4">
        <DecisionMetric
          accent
          description="A conservative band derived from stored video, channel, snapshot, and discovery evidence."
          label="Signal strength"
          qualifier={
            signal.decision_card?.confidence.label ?? signal.confidence
          }
          value={
            signal.decision_card?.signal_strength.label ??
            scoreLabel(signal.score)
          }
        />
        <DecisionMetric
          accent
          description={
            signal.data_mode === "live"
              ? "Fit is personalized against the owned channel and conservatively downgraded when evidence is fragile."
              : "Very relevant to your audience and recent performance."
          }
          label="Channel fit"
          qualifier="Personalized"
          value={
            signal.decision_card?.channel_fit.label ??
            fitLabel(signal.channel_fit)
          }
        />
        <DecisionMetric
          compact
          description="Timely opportunity before the broader peak."
          label="Publishing window"
          qualifier="Actionable"
          value={signal.opportunity_window.label}
        />
        <DecisionMetric
          description="Across independent sources and creators."
          label="Evidence"
          qualifier="Independent sources"
          value={`${signal.evidence_videos} / ${signal.independent_channels}`}
        />
      </div>

      <div className="grid flex-1 gap-0 px-7 py-6 max-sm:px-5 lg:grid-cols-[1fr_1.1fr]">
        <div className="border-r border-[var(--line)] pr-7 max-lg:border-r-0 max-lg:border-b max-lg:pr-0 max-lg:pb-6">
          <p className="text-[13px] font-semibold">
            {signal.strongest_demand.available
              ? "Strongest audience question"
              : "Audience demand"}
          </p>
          {signal.strongest_demand.available ? (
            <>
              <blockquote className="editorial mt-4 text-[23px] leading-[1.25] italic">
                “{signal.strongest_demand.question}”
              </blockquote>
              <p className="mt-5 text-[12px] text-[var(--muted)]">
                {signal.strongest_demand.comment_count} relevant comments ·{" "}
                repeated across {signal.strongest_demand.distinct_channels}{" "}
                channels · {signal.strongest_demand.distinct_commenters}{" "}
                commenters · {signal.strongest_demand.evidence_strength}{" "}
                evidence
              </p>
            </>
          ) : (
            <div className="mt-4 border-l-2 border-[var(--line-strong)] pl-4">
              <p className="text-[13px] leading-relaxed text-[var(--muted)]">
                {signal.strongest_demand.question}
              </p>
              <p className="mt-2 text-[10px] text-[var(--faint)]">
                Demand score remains zero until the stored sample meets the
                semantic relevance and cross-video evidence floor.
              </p>
            </div>
          )}
        </div>

        <div className="pl-7 max-lg:pt-6 max-lg:pl-0">
          <div className="flex items-center justify-between gap-4">
            <p className="text-[13px] font-semibold">Momentum</p>
            <p className="text-[11px] text-[var(--muted)]">Last 7 days</p>
          </div>
          <div className="mt-5 grid grid-cols-[42px_1fr] items-stretch gap-4">
            <div className="flex flex-col justify-between py-1 text-[10px] text-[var(--muted)]">
              <span>High</span>
              <span>Medium</span>
              <span>Low</span>
            </div>
            <div className="flex min-w-0 flex-col justify-between">
              <Sparkline
                className="h-[100px] w-full"
                negative={negative}
                values={signal.momentum.sparkline}
              />
              <div className="mt-2 flex justify-between text-[10px] text-[var(--muted)]">
                <span>7d ago</span>
                <span>5d</span>
                <span>3d</span>
                <span>Today</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-[var(--line)] px-7 py-5 max-sm:px-5">
        <Link
          className="inline-flex h-11 items-center gap-2 text-[13px] font-medium hover:underline"
          href={`/signals/${signal.id}`}
        >
          Open evidence <ArrowRight aria-hidden="true" size={16} />
        </Link>
        <p className="ml-auto text-[11px] text-[var(--muted)] max-sm:order-3 max-sm:ml-0 max-sm:w-full">
          Source:{" "}
          {signal.data_mode === "live"
            ? "Live YouTube evidence"
            : "Deterministic demo"}{" "}
          · Updated {relativeTime(freshness)}
        </p>
        <Button
          className="h-12 min-w-[210px] !border-[var(--lime)] !bg-[var(--lime)] px-6 text-[14px] !text-[var(--ink)] hover:!bg-[#a9df11] max-sm:w-full"
          disabled={busy}
          onClick={onBrief}
        >
          <FilePlus2 aria-hidden="true" size={17} />
          Build brief
          <ArrowRight aria-hidden="true" size={17} />
        </Button>
      </div>
    </section>
  );
}

export function SignalFeed() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("All stages");
  const [range, setRange] = useState("7");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [sourceMode, setSourceMode] = useState("auto");
  const trackedImpressions = useRef(new Set<string>());

  const query = useQuery<FeedData>({
    queryKey: ["signal-feed", sourceMode],
    queryFn: async () => {
      const context = await getDemoContext();
      const feed = await getSignals(context.workspace_id, {
        source: sourceMode,
      });
      return { context, feed };
    },
  });

  useEffect(() => {
    if (!query.data) return;
    const { context, feed } = query.data;
    for (const signal of feed.items) {
      const key = `${feed.data_mode}:${signal.id}`;
      if (trackedImpressions.current.has(key)) continue;
      trackedImpressions.current.add(key);
      void trackProductEvent(context.workspace_id, {
        event_type: "signal_impression",
        event_key: `feed:${createClientEventId()}:${signal.id}`,
        signal_id: signal.id,
        metadata: { surface: "signal_feed", data_mode: feed.data_mode },
      }).catch(() => undefined);
    }
  }, [query.data]);

  const actionMutation = useMutation({
    mutationFn: ({
      signalId,
      nextAction,
      reason,
    }: {
      signalId: string;
      nextAction: "save" | "dismiss";
      reason: string;
    }) =>
      actOnSignal(
        query.data!.context.workspace_id,
        signalId,
        nextAction,
        reason,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["signal-feed"] }),
  });

  const briefMutation = useMutation({
    mutationFn: (signalId: string) =>
      createBrief(query.data!.context.workspace_id, signalId),
    onSuccess: (brief) => router.push(`/briefs?created=${brief.id}`),
  });

  const visible = useMemo(() => {
    if (!query.data) return [];
    const anchor = new Date(query.data.feed.data_freshness).getTime();
    return query.data.feed.items.filter((item) => {
      const matchesSearch =
        !search ||
        `${item.topic_label} ${item.thesis} ${item.category}`
          .toLowerCase()
          .includes(search.toLowerCase());
      const matchesStage =
        stage === "All stages" || item.lifecycle_stage === stage;
      const ageDays =
        (anchor - new Date(item.generated_at).getTime()) /
        (1000 * 60 * 60 * 24);
      const matchesRange = range === "all" || ageDays <= Number(range);
      return matchesSearch && matchesStage && matchesRange;
    });
  }, [query.data, range, search, stage]);

  const selected =
    visible.find((item) => item.id === selectedId) ?? visible[0] ?? null;
  const displayed = showAll ? visible : visible.slice(0, 4);

  if (query.isLoading) return <PageLoading label="Loading signals" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const busy = actionMutation.isPending || briefMutation.isPending;

  return (
    <div className="min-h-screen px-5 py-8 sm:px-8 lg:px-9 lg:py-9">
      <div className="mx-auto max-w-[1220px]">
        <header>
          <div className="flex items-end justify-between gap-6">
            <div>
              <h1 className="editorial text-[48px] leading-none tracking-[-0.04em] sm:text-[54px]">
                Signals
              </h1>
              <p className="mt-3 text-[15px] text-[var(--muted)]">
                Find the next video worth making
              </p>
            </div>
            <div className="hidden text-right sm:block">
              <div className="mb-2 flex justify-end gap-1">
                {query.data.feed.available_modes.map((mode) => (
                  <button
                    aria-pressed={query.data.feed.data_mode === mode}
                    className={`border px-2.5 py-1 text-[10px] font-medium capitalize ${
                      query.data.feed.data_mode === mode
                        ? "border-[var(--ink)] bg-[var(--ink)] text-white"
                        : "border-[var(--line-strong)] bg-white"
                    }`}
                    key={mode}
                    onClick={() => setSourceMode(mode)}
                    type="button"
                  >
                    {mode === "live" ? "Live evidence" : "Demo dataset"}
                  </button>
                ))}
              </div>
              <p className="text-[12px] text-[var(--muted)]">
                Updated {relativeTime(query.data.feed.data_freshness)}
              </p>
            </div>
          </div>

          <div className="mt-7 flex flex-wrap gap-3">
            <label className="relative min-w-[260px] flex-1 sm:max-w-[430px]">
              <Search
                aria-hidden="true"
                className="absolute top-1/2 left-4 -translate-y-1/2 text-[var(--muted)]"
                size={18}
                strokeWidth={1.5}
              />
              <span className="sr-only">Search signals</span>
              <input
                className="h-12 w-full border border-[var(--line-strong)] bg-white pr-4 pl-12 text-[14px] placeholder:text-[var(--faint)]"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search signals"
                type="search"
                value={search}
              />
            </label>

            <div className="ml-auto flex flex-wrap gap-3 max-sm:ml-0 max-sm:w-full">
              <label className="relative max-sm:flex-1">
                <span className="sr-only">Lifecycle stage</span>
                <select
                  aria-label="Lifecycle stage"
                  className="h-12 min-w-[180px] appearance-none border border-[var(--line-strong)] bg-white pr-11 pl-4 text-[14px] max-sm:w-full max-sm:min-w-0"
                  onChange={(event) => setStage(event.target.value)}
                  value={stage}
                >
                  {[
                    "All stages",
                    "Seed",
                    "Emerging",
                    "Breakout",
                    "Mass Market",
                    "Saturated",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
                <ChevronDown
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2"
                  size={16}
                />
              </label>

              <label className="relative max-sm:flex-1">
                <span className="sr-only">Evidence date range</span>
                <select
                  aria-label="Evidence date range"
                  className="h-12 min-w-[180px] appearance-none border border-[var(--line-strong)] bg-white pr-11 pl-4 text-[14px] max-sm:w-full max-sm:min-w-0"
                  onChange={(event) => setRange(event.target.value)}
                  value={range}
                >
                  <option value="7">Last 7 days</option>
                  <option value="30">Last 30 days</option>
                  <option value="all">All time</option>
                </select>
                <ChevronDown
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2"
                  size={16}
                />
              </label>
            </div>
          </div>
        </header>

        <div className="mt-6 grid overflow-hidden border border-[var(--line)] bg-white xl:min-h-[calc(100vh-225px)] xl:grid-cols-[minmax(370px,0.38fr)_minmax(0,0.62fr)]">
          <section
            aria-label="Ranked signals"
            className="min-w-0 border-r border-[var(--line)] max-xl:border-r-0 max-xl:border-b"
          >
            <div className="grid grid-cols-[minmax(0,1fr)_76px_76px_62px] gap-4 border-b border-[var(--line)] px-5 py-3 text-[11px] text-[var(--muted)] max-sm:hidden">
              <span>
                {showAll ? `All ${visible.length}` : `Top ${displayed.length}`}{" "}
                signals
              </span>
              <span>Decision</span>
              <span>Window</span>
              <span className="text-right">Evidence</span>
            </div>

            {displayed.length ? (
              displayed.map((signal) => (
                <SignalListRow
                  key={signal.id}
                  onSelect={() => {
                    setSelectedId(signal.id);
                    if (window.innerWidth < 1280) {
                      window.requestAnimationFrame(() =>
                        document
                          .getElementById("selected-signal")
                          ?.scrollIntoView({
                            behavior: "smooth",
                            block: "start",
                          }),
                      );
                    }
                  }}
                  selected={selected?.id === signal.id}
                  signal={signal}
                />
              ))
            ) : (
              <div className="px-6 py-16 text-center">
                <p className="editorial text-2xl">No evidence matches.</p>
                <p className="mt-2 text-[13px] text-[var(--muted)]">
                  Adjust the lifecycle, date range, or search.
                </p>
              </div>
            )}

            {visible.length > 4 && (
              <button
                className="flex h-14 w-full items-center justify-center gap-2 text-[13px] font-medium hover:bg-[var(--surface-subtle)]"
                onClick={() => setShowAll((value) => !value)}
                type="button"
              >
                {showAll ? "Show top signals" : "View all signals"}
                <ArrowRight
                  aria-hidden="true"
                  className={showAll ? "rotate-180" : ""}
                  size={16}
                />
              </button>
            )}
          </section>

          {selected && (
            <SelectedSignal
              busy={busy}
              freshness={query.data.feed.data_freshness}
              onBrief={() => briefMutation.mutate(selected.id)}
              onDismiss={() =>
                actionMutation.mutate({
                  signalId: selected.id,
                  nextAction: "dismiss",
                  reason: "irrelevant",
                })
              }
              onSave={() =>
                actionMutation.mutate({
                  signalId: selected.id,
                  nextAction: "save",
                  reason: "strong_fit",
                })
              }
              signal={selected}
            />
          )}
        </div>
      </div>
    </div>
  );
}
