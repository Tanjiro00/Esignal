"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Captions,
  ChevronDown,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { EarlynessTimeline } from "@/components/signals/earlyness-timeline";
import {
  DecisionFeedback,
  type DecisionAction,
} from "@/components/signals/decision-feedback";
import { Sparkline } from "@/components/sparkline";
import { ErrorState, PageLoading } from "@/components/ui";
import {
  actOnSignal,
  createBrief,
  getDemoContext,
  getSignal,
  trackProductEvent,
} from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import { compactNumber, titleCase } from "@/lib/format";
import type {
  DemoContext,
  SignalDecisionCard,
  SignalDetail,
} from "@/lib/types";

type DetailData = {
  context: DemoContext;
  signal: SignalDetail;
};

function evidenceLink(signal: SignalDetail, reference: string) {
  const [kind, id] = reference.split(":", 2);
  if (kind === "video") {
    const video = signal.evidence_videos.find((item) => item.id === id);
    return video
      ? { href: video.canonical_url, label: video.channel }
      : { href: null, label: "Video evidence" };
  }
  if (kind === "transcript-segment") {
    const segment = signal.transcript_evidence
      .flatMap((item) => item.segments)
      .find((item) => item.id === id);
    return segment
      ? { href: segment.video_url, label: "Transcript" }
      : { href: null, label: "Transcript evidence" };
  }
  if (kind === "comment") {
    const snippet = signal.demand_clusters
      .flatMap((item) => item.snippets)
      .find((item) => item.comment_id === id);
    return snippet
      ? { href: snippet.video_url, label: "Audience comment" }
      : { href: null, label: "Comment evidence" };
  }
  if (kind === "video-snapshot") {
    return { href: null, label: "Stored metric" };
  }
  return { href: null, label: "Stored evidence" };
}

function fallbackCard(signal: SignalDetail): SignalDecisionCard {
  const decision = "Skip";
  const angle = signal.content_angles[0];
  return {
    decision,
    decision_label: "SKIP",
    decision_reason_codes: ["legacy_signal"],
    decision_version: "legacy-signal",
    topic: signal.topic.label,
    thesis: signal.thesis,
    why_now:
      signal.why_emerging[0] ??
      "Recent independent evidence makes this topic worth reviewing.",
    why_this_channel:
      typeof signal.channel_fit_detail.explanation === "string"
        ? signal.channel_fit_detail.explanation
        : "The recommendation uses the saved channel profile.",
    open_angle: "No evidence-backed video angle yet.",
    recommended_video: "No evidence-backed video angle yet.",
    release_ready: false,
    insight_status: "candidate",
    insight_type: "legacy_fallback",
    insight_statement:
      "The stored evidence supports a trend, but not a non-obvious video insight yet.",
    insight_reason_codes: ["missing_insight_provenance"],
    publishing_window: signal.opportunity_window,
    production_effort: angle?.effort ?? "Medium",
    production_days_min: angle?.production_time_days?.min ?? 3,
    production_days_max: angle?.production_time_days?.max ?? 7,
    signal_strength: {
      label: signal.score >= 70 ? "High" : "Moderate",
      reason_codes: ["legacy_signal"],
      version: "legacy-signal",
    },
    channel_fit: {
      label: signal.channel_fit >= 70 ? "High" : "Moderate",
      reason_codes: ["legacy_signal"],
      version: "legacy-signal",
    },
    confidence: {
      label: signal.confidence === "High" ? "High" : "Moderate",
      reason_codes: ["legacy_signal"],
      version: "legacy-signal",
    },
    evidence_strength: {
      label: signal.evidence_videos.length >= 3 ? "High" : "Moderate",
      reason_codes: ["legacy_signal"],
      version: "legacy-signal",
    },
    main_risk: signal.saturation.analysis,
  };
}

function DecisionPill({
  decision,
}: {
  decision: SignalDecisionCard["decision"];
}) {
  const tone =
    decision === "Act"
      ? "bg-[var(--lime)] text-[var(--ink)]"
      : decision === "Skip"
        ? "bg-[#fff0ee] text-[var(--coral)]"
        : "bg-[var(--surface-subtle)] text-[var(--ink)]";
  return (
    <span
      className={`inline-flex min-h-8 items-center px-3 text-[11px] font-semibold tracking-[0.12em] ${tone}`}
      data-testid="signal-decision"
    >
      {decision === "Act" ? "ACT NOW" : decision.toUpperCase()}
    </span>
  );
}

function EvidenceTable({ signal }: { signal: SignalDetail }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left">
        <thead>
          <tr className="border-b border-[var(--line-strong)] text-[11px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
            <th className="pb-3 font-medium">Video</th>
            <th className="pb-3 font-medium">Channel</th>
            <th className="pb-3 font-medium">Age</th>
            <th className="pb-3 font-medium">Views</th>
            <th className="pb-3 font-medium">Velocity</th>
            <th className="pb-3 font-medium">Outlier</th>
            <th className="pb-3 text-right font-medium">Evidence role</th>
          </tr>
        </thead>
        <tbody>
          {signal.evidence_videos.slice(0, 8).map((video) => (
            <tr
              className="border-b border-[var(--line)] last:border-b-0"
              key={video.id}
            >
              <td className="max-w-[320px] py-4 pr-5">
                <a
                  className="inline-flex items-start gap-2 text-[12px] leading-snug font-medium hover:underline"
                  href={video.canonical_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  {video.title}
                  <ExternalLink className="mt-0.5 shrink-0" size={12} />
                </a>
                <p className="mt-1 text-[11px] text-[var(--muted)]">
                  Transcript {video.transcript_status} · comments{" "}
                  {video.comment_sample_status}
                </p>
              </td>
              <td className="py-4 pr-5 text-[11px]">
                {video.channel}
                <span className="mt-1 block text-[11px] text-[var(--muted)]">
                  {compactNumber(video.channel_subscribers)} subscribers
                </span>
              </td>
              <td className="py-4 pr-5 text-[11px]">{video.age_label}</td>
              <td className="py-4 pr-5 text-[11px]">
                {compactNumber(video.views)}
              </td>
              <td className="py-4 pr-5">
                <Sparkline className="h-7 w-20" values={video.sparkline} />
              </td>
              <td className="py-4 pr-5 text-[11px] font-semibold text-[var(--lime-ink)]">
                {video.outlier_ratio.toFixed(1)}×
              </td>
              <td className="py-4 text-right text-[10px] capitalize">
                {video.role}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TranscriptEvidence({ signal }: { signal: SignalDetail }) {
  if (!signal.transcript_evidence.length) {
    return (
      <p className="border-l-2 border-[var(--line-strong)] pl-4 text-[12px] leading-6 text-[var(--muted)]">
        No public transcript is stored yet. The recommendation still resolves to
        video metadata, snapshots, and sampled comments.
      </p>
    );
  }
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {signal.transcript_evidence.slice(0, 4).map((transcript) => (
        <article
          className="border-t border-[var(--line)] pt-4"
          key={transcript.video_id}
        >
          <p className="flex items-center gap-2 text-[12px] font-semibold">
            <Captions size={15} />
            {transcript.video_title}
          </p>
          <p className="mt-3 text-[11px] leading-6 text-[var(--muted)]">
            {transcript.summary}
          </p>
          <div className="mt-4 space-y-3">
            {transcript.segments.slice(0, 2).map((segment) => (
              <a
                className="block border-l border-[var(--lime-strong)] pl-3 text-[10px] leading-5 text-[var(--muted)] hover:text-[var(--ink)]"
                href={segment.video_url}
                key={segment.id}
                rel="noreferrer"
                target="_blank"
              >
                {segment.text} ↗
              </a>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function Disclosure({
  title,
  subtitle,
  children,
  testId,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <details
      className="border-t border-[var(--line-strong)]"
      data-testid={testId}
    >
      <summary className="flex min-h-16 cursor-pointer list-none items-center justify-between gap-6 py-4">
        <span>
          <strong className="block text-[13px]">{title}</strong>
          <span className="mt-1 block text-[11px] text-[var(--muted)]">
            {subtitle}
          </span>
        </span>
        <ChevronDown className="shrink-0" size={16} />
      </summary>
      <div className="pt-2 pb-9">{children}</div>
    </details>
  );
}

export function SignalDetailView({ signalId }: { signalId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const trackedOpen = useRef(false);
  const query = useQuery<DetailData>({
    queryKey: ["signal-detail", signalId],
    queryFn: async () => {
      const context = await getDemoContext();
      const signal = await getSignal(context.workspace_id, signalId);
      return { context, signal };
    },
  });

  useEffect(() => {
    if (!query.data || trackedOpen.current) return;
    trackedOpen.current = true;
    void trackProductEvent(query.data.context.workspace_id, {
      event_type: "signal_open",
      event_key: `signal-open:${createClientEventId()}:${signalId}`,
      signal_id: signalId,
      metadata: {
        surface: "signal_detail",
        data_mode: query.data.signal.data_mode,
      },
    }).catch(() => undefined);
  }, [query.data, signalId]);

  const actionMutation = useMutation({
    mutationFn: async ({
      action,
      reason,
      comment,
    }: {
      action: DecisionAction;
      reason?: string;
      comment?: string;
    }) => {
      const angle = query.data!.signal.content_angles[0];
      await actOnSignal(
        query.data!.context.workspace_id,
        signalId,
        action,
        reason,
        comment,
        angle?.opportunity_id,
      );
      if (action === "act") {
        return createBrief(
          query.data!.context.workspace_id,
          signalId,
          0,
          angle?.opportunity_id,
        );
      }
      return null;
    },
    onSuccess: (brief) => {
      queryClient.invalidateQueries({ queryKey: ["signal-detail", signalId] });
      queryClient.invalidateQueries({ queryKey: ["signal-feed"] });
      if (brief) router.push(`/briefs?created=${brief.id}`);
    },
  });

  if (query.isLoading) return <PageLoading label="Loading decision evidence" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const { context, signal } = query.data;
  const card = signal.decision_card ?? fallbackCard(signal);
  const busy = actionMutation.isPending;

  return (
    <div className="mx-auto max-w-[1240px] px-5 py-6 sm:px-8 sm:py-9">
      <Link
        className="inline-flex min-h-11 items-center gap-2 text-[11px] text-[var(--muted)] hover:text-[var(--ink)]"
        href="/digest"
      >
        <ArrowLeft size={14} /> Back to Digest
      </Link>

      <section className="border-y border-[var(--ink)] py-7 sm:py-9">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,.8fr)]">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <DecisionPill decision={card.decision} />
              <span className="text-[11px] text-[var(--muted)]">
                {signal.topic.stage} · {signal.data_mode} evidence
              </span>
            </div>
            <h1 className="editorial mt-5 max-w-[820px] text-[40px] leading-[1.02] sm:text-[56px]">
              {card.topic}
            </h1>
            <p className="mt-5 max-w-[760px] text-[15px] leading-7 text-[var(--muted)]">
              {card.thesis}
            </p>

            <div className="mt-7 grid gap-6 border-t border-[var(--line)] pt-6 sm:grid-cols-2">
              <div>
                <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                  Why now
                </p>
                <p className="mt-2 text-[13px] leading-6 text-[var(--muted)]">
                  {card.why_now}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                  Why {context.owned_channel_name}
                </p>
                <p className="mt-2 text-[13px] leading-6 text-[var(--muted)]">
                  {card.why_this_channel}
                </p>
              </div>
            </div>
          </div>

          <aside className="border-l border-[var(--line)] pl-8 max-lg:border-t max-lg:border-l-0 max-lg:pt-7 max-lg:pl-0">
            <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
              What to cover · format-neutral
            </p>
            <p className="editorial mt-3 text-[27px] leading-[1.15]">
              {card.open_angle}
            </p>
            <p className="mt-4 text-[12px] leading-6 text-[var(--muted)]">
              EarlySignal defines the subject and unresolved question. You
              choose the format that fits your channel.
            </p>
            {signal.content_angles[0]?.differentiation ? (
              <p className="mt-3 border-l border-[var(--lime-strong)] pl-3 text-[11px] leading-5 text-[var(--muted)]">
                Coverage gap: {signal.content_angles[0].differentiation}
              </p>
            ) : null}

            <dl className="mt-6 grid grid-cols-2 gap-5 border-y border-[var(--line)] py-5 text-[11px]">
              <div>
                <dt className="text-[var(--muted)]">Publish</dt>
                <dd className="mt-1 font-semibold">
                  {card.publishing_window.label}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Production</dt>
                <dd className="mt-1 font-semibold">
                  {card.production_effort} · {card.production_days_min}–
                  {card.production_days_max} days
                </dd>
                {card.feasibility ? (
                  <dd
                    className={`mt-1 text-[10px] ${
                      card.feasibility === "Infeasible"
                        ? "text-[var(--coral)]"
                        : "text-[var(--lime-ink)]"
                    }`}
                  >
                    {card.feasibility} feasibility
                  </dd>
                ) : null}
              </div>
              <div>
                <dt className="text-[var(--muted)]">Channel fit</dt>
                <dd className="mt-1 font-semibold">{card.channel_fit.label}</dd>
                <dd className="mt-1 text-[11px] text-[var(--muted)]">
                  {card.fit_verification === "verified"
                    ? "✓ Verified analytics"
                    : "Estimated from public history"}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Evidence</dt>
                <dd className="mt-1 font-semibold">
                  {card.evidence_strength.label}
                </dd>
              </div>
            </dl>

            <div className="mt-5 border-l-2 border-[var(--coral)] pl-4">
              <p className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.1em] uppercase">
                <ShieldAlert size={13} /> Main risk
              </p>
              <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">
                {card.main_risk}
              </p>
            </div>

            <div className="mt-6 max-sm:hidden">
              <DecisionFeedback
                allowAct={card.release_ready}
                busy={busy}
                currentAction={signal.current_action}
                onSubmit={(action, reason, comment) =>
                  actionMutation.mutate({ action, reason, comment })
                }
              />
            </div>
          </aside>
        </div>
      </section>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--line-strong)] bg-white p-3 sm:hidden">
        <DecisionFeedback
          allowAct={card.release_ready}
          busy={busy}
          compact
          currentAction={signal.current_action}
          onSubmit={(action, reason, comment) =>
            actionMutation.mutate({ action, reason, comment })
          }
        />
      </div>

      <section className="mt-8">
        <Disclosure
          subtitle={`${signal.evidence_videos.length} videos, ${signal.transcript_evidence.length} transcripts, ${signal.demand_clusters.length} demand clusters`}
          testId="signal-evidence-disclosure"
          title="View evidence"
        >
          <EvidenceTable signal={signal} />
          <div className="mt-10 border-t border-[var(--line)] pt-8">
            <h2 className="editorial text-[26px]">Transcript evidence</h2>
            <div className="mt-5">
              <TranscriptEvidence signal={signal} />
            </div>
          </div>
          <div className="mt-10 grid gap-8 border-t border-[var(--line)] pt-8 lg:grid-cols-2">
            <div>
              <h2 className="editorial text-[26px]">Audience demand</h2>
              <div className="mt-5 divide-y divide-[var(--line)]">
                {signal.demand_clusters.length ? (
                  signal.demand_clusters.map((cluster) => (
                    <article className="py-4 first:pt-0" key={cluster.id}>
                      <p className="text-[12px] font-semibold">
                        {cluster.label} · {cluster.evidence_strength}
                      </p>
                      <p className="mt-2 text-[11px] leading-6 text-[var(--muted)]">
                        {cluster.summary}
                      </p>
                      {cluster.snippets.slice(0, 2).map((snippet) => (
                        <blockquote
                          className="mt-3 border-l border-[var(--lime-strong)] pl-3 text-[10px] leading-5 text-[var(--muted)]"
                          key={snippet.comment_id}
                        >
                          “{snippet.text}”{" "}
                          <a
                            className="text-[var(--ink)] hover:underline"
                            href={snippet.video_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            Source ↗
                          </a>
                        </blockquote>
                      ))}
                    </article>
                  ))
                ) : (
                  <p className="text-[12px] text-[var(--muted)]">
                    No audience-demand cluster currently passes the evidence
                    floor.
                  </p>
                )}
              </div>
            </div>
            <div>
              <h2 className="editorial text-[26px]">Lifecycle timeline</h2>
              <EarlynessTimeline
                currentStage={signal.topic.stage}
                earlyness={signal.earlyness}
              />
            </div>
          </div>
        </Disclosure>

        <Disclosure
          subtitle="The evidence and channel logic behind the recommendation"
          title="Why this recommendation"
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <div>
              <h2 className="editorial text-[26px]">Why it is emerging</h2>
              <ol className="mt-5 space-y-4">
                {(signal.why_emerging_evidence.length
                  ? signal.why_emerging_evidence
                  : signal.why_emerging.map((text) => ({
                      text,
                      evidence_refs: [],
                    }))
                ).map((claim, index) => (
                  <li
                    className="grid grid-cols-[28px_1fr] gap-3 text-[12px] leading-6 text-[var(--muted)]"
                    key={`${claim.text}-${index}`}
                  >
                    <span className="editorial text-[20px] text-[var(--ink)]">
                      {index + 1}
                    </span>
                    <span>
                      {claim.text}
                      {claim.evidence_refs.length ? (
                        <span className="mt-2 flex flex-wrap gap-2">
                          {claim.evidence_refs.slice(0, 4).map((reference) => {
                            const source = evidenceLink(signal, reference);
                            return source.href ? (
                              <a
                                className="text-[11px] font-semibold tracking-[0.12em] text-[var(--ink)] uppercase underline decoration-[var(--faint)] underline-offset-4"
                                href={source.href}
                                key={reference}
                                rel="noreferrer"
                                target="_blank"
                              >
                                {source.label} ↗
                              </a>
                            ) : (
                              <span
                                className="text-[11px] font-semibold tracking-[0.12em] text-[var(--muted)] uppercase"
                                key={reference}
                              >
                                {source.label}
                              </span>
                            );
                          })}
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ol>
              {signal.intelligence_provenance.model ? (
                <p className="mt-5 text-[11px] tracking-[0.12em] text-[var(--muted)] uppercase">
                  Evidence synthesis · {signal.intelligence_provenance.model}
                </p>
              ) : null}
            </div>
            <div className="lg:border-l lg:border-[var(--line)] lg:pl-8">
              <h2 className="editorial text-[26px]">Channel fit</h2>
              <p className="mt-5 text-[13px] leading-7 text-[var(--muted)]">
                {card.why_this_channel}
              </p>
              <dl className="mt-6 grid grid-cols-2 gap-5 text-[11px]">
                <div>
                  <dt className="text-[var(--muted)]">Signal strength</dt>
                  <dd className="mt-1 font-semibold">
                    {card.signal_strength.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Confidence</dt>
                  <dd className="mt-1 font-semibold">
                    {card.confidence.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Saturation</dt>
                  <dd className="mt-1 font-semibold">
                    {signal.saturation.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Evidence</dt>
                  <dd className="mt-1 font-semibold">
                    {card.evidence_strength.label}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </Disclosure>

        <Disclosure
          subtitle="Internal values are shown here for auditability, not decision-making"
          title="How the score was formed"
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <div>
              <h2 className="editorial text-[24px]">Signal components</h2>
              <div className="mt-5 space-y-3">
                {Object.entries(signal.score_components).map(
                  ([name, value]) => (
                    <div
                      className="grid grid-cols-[1fr_120px_36px] items-center gap-3"
                      key={name}
                    >
                      <span className="text-[10px] text-[var(--muted)]">
                        {titleCase(name)}
                      </span>
                      <span className="h-1 bg-[var(--line)]">
                        <span
                          className={`block h-full ${
                            name.includes("penalty")
                              ? "bg-[var(--coral)]"
                              : "bg-[var(--lime-strong)]"
                          }`}
                          style={{ width: `${Math.min(100, value)}%` }}
                        />
                      </span>
                      <span className="text-right text-[10px]">
                        {value.toFixed(1)}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </div>
            <div className="lg:border-l lg:border-[var(--line)] lg:pl-8">
              <h2 className="editorial text-[24px]">Fit components</h2>
              <div className="mt-5 space-y-3">
                {Object.entries(signal.channel_fit_detail)
                  .filter(([, value]) => typeof value === "number")
                  .map(([name, value]) => (
                    <div
                      className="grid grid-cols-[1fr_120px_36px] items-center gap-3"
                      key={name}
                    >
                      <span className="text-[10px] text-[var(--muted)]">
                        {titleCase(name)}
                      </span>
                      <span className="h-1 bg-[var(--line)]">
                        <span
                          className="block h-full bg-[var(--lime-strong)]"
                          style={{ width: `${Math.min(100, Number(value))}%` }}
                        />
                      </span>
                      <span className="text-right text-[10px]">
                        {Number(value).toFixed(1)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </Disclosure>

        <Disclosure
          subtitle="The primary angle plus up to two alternatives"
          title="Alternative opportunities"
        >
          <div className="grid gap-6 md:grid-cols-3">
            {signal.content_angles.map((angle, index) => (
              <article
                className="border-t border-[var(--line-strong)] pt-5"
                key={angle.opportunity_id ?? angle.title}
              >
                <p className="text-[11px] tracking-[0.12em] text-[var(--muted)] uppercase">
                  {index === 0 ? "Primary" : `Alternative ${index}`}
                </p>
                <h3 className="mt-3 text-[14px] font-semibold">
                  {angle.title}
                </h3>
                <p className="mt-3 text-[11px] leading-6 text-[var(--muted)]">
                  {angle.audience_promise}
                </p>
                {angle.differentiation ? (
                  <p className="mt-3 text-[10px] leading-5 text-[var(--muted)]">
                    <strong className="text-[var(--ink)]">
                      Different from current coverage:
                    </strong>{" "}
                    {angle.differentiation}
                  </p>
                ) : null}
                {angle.open_gap ? (
                  <dl className="mt-4 grid grid-cols-2 gap-3 border-y border-[var(--line)] py-3 text-[11px]">
                    <div>
                      <dt className="text-[var(--muted)]">Open format</dt>
                      <dd className="mt-1 font-semibold">
                        {String(angle.open_gap.format)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[var(--muted)]">Proof</dt>
                      <dd className="mt-1 font-semibold">
                        {String(angle.open_gap.proof_type)}
                      </dd>
                    </div>
                  </dl>
                ) : null}
                {angle.recommended_publish_by_label ? (
                  <p
                    className={`mt-3 text-[10px] font-medium ${
                      angle.feasible_for_act === false
                        ? "text-[var(--coral)]"
                        : "text-[var(--lime-ink)]"
                    }`}
                  >
                    Publish by {angle.recommended_publish_by_label} ·{" "}
                    {angle.feasibility}
                  </p>
                ) : null}
                {index === 0 && angle.why_primary ? (
                  <p className="mt-3 text-[10px] leading-5 text-[var(--lime-ink)]">
                    {angle.why_primary}
                  </p>
                ) : null}
                <button
                  className="mt-5 inline-flex min-h-11 items-center gap-2 text-[11px] font-semibold hover:underline"
                  disabled={busy}
                  onClick={async () => {
                    const brief = await createBrief(
                      context.workspace_id,
                      signalId,
                      index,
                      angle.opportunity_id,
                    );
                    router.push(`/briefs?created=${brief.id}`);
                  }}
                  type="button"
                >
                  Create this brief <ArrowUpRight size={13} />
                </button>
              </article>
            ))}
          </div>
        </Disclosure>
      </section>

      <Link
        className="mt-7 inline-flex min-h-11 items-center gap-2 text-[11px] text-[var(--muted)] hover:text-[var(--ink)]"
        href="/signals"
      >
        Browse all signals <ArrowRight size={14} />
      </Link>
    </div>
  );
}
