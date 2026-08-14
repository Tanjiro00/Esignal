"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  CircleX,
  Eye,
  ExternalLink,
  ListVideo,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  DecisionFeedback,
  type DecisionAction,
  type DecisionPlan,
} from "@/components/signals/decision-feedback";
import { actOnSignal, createBrief, trackProductEvent } from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import type { DemoContext, SignalDecisionCard } from "@/lib/types";

export type OpportunityEvidenceLink = {
  id: string;
  title: string;
  canonical_url: string;
  channel: string;
};

function savedDecisionLabel(action?: DecisionAction) {
  if (action === "watch") return "Tracking changes for this idea.";
  if (action === "skip") return "Idea removed from the active library.";
  return "Video plan created.";
}

function DecisionBadge({
  decision,
  releaseReady,
}: {
  decision: SignalDecisionCard["decision"];
  releaseReady: boolean;
}) {
  if (!releaseReady) {
    return (
      <span className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[var(--amber)] bg-[var(--amber-soft)] px-3 text-[11px] font-semibold tracking-[0.1em] text-[var(--ink)]">
        <Eye size={14} />
        TRACKING — NEEDS EVIDENCE
      </span>
    );
  }
  const Icon =
    decision === "Act" ? CheckCircle2 : decision === "Watch" ? Eye : CircleX;
  return (
    <span
      className={`inline-flex min-h-8 items-center gap-2 rounded-full border px-3 text-[11px] font-semibold tracking-[0.1em] ${
        decision === "Act"
          ? "border-[var(--lime-strong)] bg-[var(--lime-soft)] text-[var(--lime-ink)]"
          : decision === "Watch"
            ? "border-[var(--amber)] bg-[var(--amber-soft)] text-[var(--ink)]"
            : "border-[var(--line-strong)] bg-[var(--surface-subtle)] text-[var(--muted)]"
      }`}
    >
      <Icon size={14} />
      {decision === "Act"
        ? "GOOD TIME TO MAKE"
        : decision === "Watch"
          ? "WAIT FOR A STRONGER SIGNAL"
          : "NOT RECOMMENDED"}
    </span>
  );
}

export function OpportunityDecisionCard({
  context,
  signalId,
  card,
  opportunityId,
  currentAction,
  evidenceCount,
  evidenceLinks = [],
  rank,
  onDecision,
  showDetailLink = true,
  stickyMobile = false,
  surface = "default",
  topicStage,
  headingLevel = 2,
}: {
  context: DemoContext;
  signalId: string;
  card: SignalDecisionCard;
  opportunityId?: string;
  currentAction?: string | null;
  evidenceCount?: number;
  evidenceLinks?: OpportunityEvidenceLink[];
  rank?: number;
  onDecision?: () => void;
  showDetailLink?: boolean;
  stickyMobile?: boolean;
  surface?: "default" | "today";
  topicStage?: string;
  headingLevel?: 1 | 2;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const tracked = useRef(false);
  const isToday = surface === "today";
  const TitleHeading = headingLevel === 1 ? "h1" : "h2";

  useEffect(() => {
    if (tracked.current) return;
    tracked.current = true;
    void trackProductEvent(context.workspace_id, {
      event_type: "opportunity_card_viewed",
      event_key: `opportunity-card:${createClientEventId()}:${signalId}`,
      signal_id: signalId,
      metadata: { surface: "decision_card", decision: card.decision },
    }).catch(() => undefined);
  }, [card.decision, context.workspace_id, signalId]);

  const mutation = useMutation({
    mutationFn: async ({
      action,
      reason,
      comment,
      plan,
    }: {
      action: DecisionAction;
      reason?: string;
      comment?: string;
      plan?: DecisionPlan;
    }) => {
      const journeyStarted = Number(
        window.sessionStorage.getItem("earlysignal_today_started_at") ?? 0,
      );
      void trackProductEvent(context.workspace_id, {
        event_type: `${action}_clicked` as
          "act_clicked" | "watch_clicked" | "skip_clicked",
        event_key: `decision-click:${createClientEventId()}:${signalId}`,
        signal_id: signalId,
        metadata: {
          surface: "decision_card",
          decision_elapsed_ms: journeyStarted
            ? Math.max(Date.now() - journeyStarted, 0)
            : 0,
        },
      }).catch(() => undefined);
      if (reason) {
        void trackProductEvent(context.workspace_id, {
          event_type: "decision_reason_selected",
          event_key: `decision-reason:${createClientEventId()}:${signalId}`,
          signal_id: signalId,
          metadata: { action, reason },
        }).catch(() => undefined);
      }
      await actOnSignal(
        context.workspace_id,
        signalId,
        action,
        reason,
        comment,
        opportunityId,
        plan,
      );
      if (action === "act") {
        return createBrief(context.workspace_id, signalId, 0, opportunityId);
      }
      return null;
    },
    onSuccess: (brief) => {
      onDecision?.();
      void queryClient.invalidateQueries({ queryKey: ["today"] });
      void queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      void queryClient.invalidateQueries({
        queryKey: ["opportunity-detail", signalId],
      });
      if (brief) router.push(`/briefs?brief=${brief.id}`);
    },
  });
  const savedDecision = savedDecisionLabel(mutation.variables?.action);

  return (
    <article
      className="motion-surface overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-soft)]"
      data-testid="opportunity-card"
    >
      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="p-4 sm:p-5 lg:p-5">
          <div className="flex flex-wrap items-center gap-2.5">
            <DecisionBadge
              decision={card.decision}
              releaseReady={card.release_ready}
            />
            {rank ? (
              <span className="text-[12px] text-[var(--muted)]">
                Priority {rank}
              </span>
            ) : null}
            {currentAction &&
            ["act", "watch", "skip"].includes(currentAction) ? (
              <span className="text-[12px] text-[var(--muted)]">
                {currentAction === "act"
                  ? "Video plan created"
                  : currentAction === "watch"
                    ? "Tracking changes"
                    : "Dismissed"}
              </span>
            ) : null}
            <span
              className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-[0.06em] uppercase ${
                card.release_ready
                  ? "border-[var(--lime-strong)] bg-[var(--lime-soft)] text-[var(--lime-ink)]"
                  : "border-[var(--line-strong)] text-[var(--muted)]"
              }`}
              data-testid="insight-status"
            >
              {card.release_ready
                ? "Evidence-backed insight"
                : "Candidate only"}
            </span>
          </div>

          {isToday ? (
            <>
              <section aria-labelledby={`recommendation-${signalId}`}>
                <p className="mt-4 text-[11px] font-semibold tracking-[0.1em] text-[var(--lime-ink)] uppercase">
                  Evidence-backed video opportunity
                </p>
                <TitleHeading
                  className="editorial mt-2 max-w-[780px] text-[31px] leading-[1.08] break-words sm:text-[40px]"
                  data-testid="recommended-video"
                  id={`recommendation-${signalId}`}
                >
                  {card.recommended_video}
                </TitleHeading>
                <div className="mt-3 border-l-2 border-[var(--line-strong)] pl-3">
                  <p className="text-[10px] font-semibold tracking-[0.1em] text-[var(--muted)] uppercase">
                    {topicStage ? `${topicStage} topic` : "Detected topic"}
                  </p>
                  <p
                    className="mt-1 text-[15px] leading-5 font-medium"
                    data-testid="trend-topic"
                  >
                    {card.topic}
                  </p>
                </div>
              </section>

              <section
                aria-label="Why this is not obvious"
                className="mt-4 rounded-xl border border-[#dce9a8] bg-[linear-gradient(135deg,var(--lime-soft),white)] px-4 py-3.5"
                data-testid="insight-statement"
              >
                <p className="text-[10px] font-semibold tracking-[0.1em] text-[var(--lime-ink)] uppercase">
                  What the evidence adds
                </p>
                <p className="mt-1.5 text-[14px] leading-5">
                  {card.insight_statement}
                </p>
              </section>

              <div className="mt-4 grid gap-4 border-t border-[var(--line)] pt-4 md:grid-cols-2 md:gap-5">
                <section aria-label="Why now">
                  <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
                    <Sparkles size={13} /> Why now
                  </p>
                  <p className="mt-1.5 text-[13px] leading-5">{card.why_now}</p>
                </section>
                <section aria-label="Why this channel">
                  <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
                    Why this channel
                  </p>
                  <p className="mt-1.5 text-[13px] leading-5">
                    {card.why_this_channel}
                  </p>
                </section>
              </div>

              {evidenceLinks.length ? (
                <details
                  className="soft-disclosure group mt-4"
                  data-testid="opportunity-evidence-preview"
                >
                  <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between gap-3 text-[12px] font-semibold">
                    <span className="flex items-center gap-2">
                      <ListVideo size={14} />
                      Evidence sources · {evidenceCount ?? evidenceLinks.length}
                    </span>
                    <ChevronDown
                      className="shrink-0 transition-transform group-open:rotate-180"
                      size={16}
                    />
                  </summary>
                  <div className="grid gap-1 pb-3">
                    {evidenceLinks.slice(0, 2).map((video) => (
                      <a
                        className="group/source grid min-h-10 grid-cols-[1fr_auto] items-center gap-3 border-b border-[var(--line)] py-2 text-[12px]"
                        href={video.canonical_url}
                        key={video.id}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <span className="min-w-0 truncate">
                          <strong className="font-medium group-hover/source:underline">
                            {video.channel}
                          </strong>
                          <span className="text-[var(--muted)]"> · </span>
                          <span className="text-[var(--muted)]">
                            {video.title}
                          </span>
                        </span>
                        <ExternalLink
                          aria-hidden="true"
                          className="text-[var(--muted)] group-hover/source:text-[var(--ink)]"
                          size={13}
                        />
                      </a>
                    ))}
                    {showDetailLink ? (
                      <Link
                        className="mt-2 inline-flex min-h-9 items-center gap-2 text-[12px] font-semibold hover:underline"
                        href={`/opportunities/${signalId}?section=evidence`}
                      >
                        Open all evidence
                        {evidenceCount ? ` (${evidenceCount})` : ""}{" "}
                        <ArrowRight size={13} />
                      </Link>
                    ) : null}
                  </div>
                </details>
              ) : null}
            </>
          ) : (
            <>
              <TitleHeading className="editorial mt-3 max-w-[760px] text-[28px] leading-[1.05] break-words sm:text-[34px]">
                {card.topic}
              </TitleHeading>
              <p className="mt-2 max-w-[760px] text-[14px] leading-6 text-[var(--muted)]">
                {card.thesis}
              </p>

              <section
                aria-label="What to cover"
                className="mt-4 rounded-xl border border-[var(--line)] bg-[linear-gradient(135deg,var(--surface-subtle),white)] px-4 py-3.5 shadow-sm sm:px-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
                    What to cover
                  </p>
                  <span className="rounded-full border border-[var(--line-strong)] bg-white px-2.5 py-1 text-[10px] tracking-[0.06em] text-[var(--muted)]">
                    Format-neutral
                  </span>
                </div>
                <p className="editorial mt-2 text-[21px] leading-tight break-words sm:text-[24px]">
                  {card.open_angle}
                </p>
                {!card.release_ready ? (
                  <p
                    className="mt-2.5 text-[12px] leading-5 text-[var(--muted)]"
                    data-testid="candidate-insight-warning"
                  >
                    The trend can be monitored, but it is not released as a
                    recommendation until a non-obvious claim is supported by
                    audience, performance, or audited evidence.
                  </p>
                ) : null}
              </section>

              <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)] md:gap-5">
                <section aria-label="Why now">
                  <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
                    <Sparkles size={13} /> Why now
                  </p>
                  <p className="mt-1.5 text-[13px] leading-5">{card.why_now}</p>
                </section>

                {evidenceLinks.length ? (
                  <section
                    aria-label="Sources used for this trend"
                    data-testid="opportunity-evidence-preview"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
                        <ListVideo size={14} /> Sources used for this trend
                      </p>
                      <span className="text-[11px] text-[var(--muted)]">
                        {evidenceCount ?? evidenceLinks.length} YouTube{" "}
                        {(evidenceCount ?? evidenceLinks.length) === 1
                          ? "source"
                          : "sources"}
                      </span>
                    </div>
                    <div className="mt-2 grid gap-1">
                      {evidenceLinks.slice(0, 2).map((video) => (
                        <a
                          className="group grid min-h-10 grid-cols-[1fr_auto] items-center gap-3 border-b border-[var(--line)] py-2 text-[12px]"
                          href={video.canonical_url}
                          key={video.id}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <span className="min-w-0 truncate">
                            <strong className="font-medium group-hover:underline">
                              {video.channel}
                            </strong>
                            <span className="text-[var(--muted)]"> · </span>
                            <span className="text-[var(--muted)]">
                              {video.title}
                            </span>
                          </span>
                          <ExternalLink
                            aria-hidden="true"
                            className="text-[var(--muted)] group-hover:text-[var(--ink)]"
                            size={13}
                          />
                        </a>
                      ))}
                    </div>
                    {showDetailLink ? (
                      <Link
                        className="mt-2 inline-flex min-h-9 items-center gap-2 text-[12px] font-semibold hover:underline"
                        href={`/opportunities/${signalId}?section=evidence`}
                      >
                        Open all evidence
                        {evidenceCount ? ` (${evidenceCount})` : ""}{" "}
                        <ArrowRight size={13} />
                      </Link>
                    ) : null}
                  </section>
                ) : null}
              </div>

              <details
                className="soft-disclosure group mt-3"
                onToggle={(event) => {
                  if (event.currentTarget.open) {
                    void trackProductEvent(context.workspace_id, {
                      event_type: "why_recommended_opened",
                      event_key: `why-recommended:${createClientEventId()}:${signalId}`,
                      signal_id: signalId,
                      metadata: { surface: "decision_card" },
                    }).catch(() => undefined);
                  }
                }}
              >
                <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between text-[12px] font-semibold">
                  Why this fits your channel · risks
                  <ChevronDown
                    className="transition-transform group-open:rotate-180"
                    size={16}
                  />
                </summary>
                <div className="grid gap-4 pb-4 text-[12px] leading-5 text-[var(--muted)] sm:grid-cols-2">
                  <p>{card.why_this_channel}</p>
                  <div className="border-l-2 border-[var(--coral)] pl-3">
                    <p className="flex items-center gap-2 font-semibold tracking-[0.08em] text-[var(--ink)] uppercase">
                      <ShieldAlert size={12} /> Main risk
                    </p>
                    <p className="mt-1">{card.main_risk}</p>
                  </div>
                </div>
              </details>
            </>
          )}
        </div>

        <aside className="border-t border-[var(--line)] bg-[linear-gradient(180deg,var(--lime-soft)_0%,var(--surface-subtle)_38%,white_100%)] p-4 sm:p-5 lg:border-t-0 lg:border-l">
          <div className="mb-4 border-l-2 border-[var(--lime-strong)] pl-3">
            <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
              Recommended next step
            </p>
            <p className="mt-1 text-[14px] font-semibold">
              {!card.release_ready
                ? "Track until evidence supports a decision"
                : card.decision === "Act"
                  ? "Create a video plan now"
                  : card.decision === "Watch"
                    ? "Track until the signal strengthens"
                    : "Dismiss this idea"}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[12px]">
            <div className="col-span-2 border-b border-[var(--line)] pb-3">
              <dt className="flex items-center gap-2 text-[var(--muted)]">
                <CalendarClock size={15} /> Publish by
              </dt>
              <dd className="mt-1 text-[20px] font-semibold">
                {card.recommended_publish_by_label ??
                  card.publishing_window.label}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Production</dt>
              <dd className="mt-1 font-semibold">
                {card.production_days_min}–{card.production_days_max} days
              </dd>
            </div>
            {isToday ? (
              <div>
                <dt className="text-[var(--muted)]">Evidence strength</dt>
                <dd className="mt-1 font-semibold">
                  {card.evidence_strength.label}
                </dd>
              </div>
            ) : (
              <>
                <div>
                  <dt className="text-[var(--muted)]">Channel fit</dt>
                  <dd className="mt-1 font-semibold">
                    {card.channel_fit.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Evidence quality</dt>
                  <dd className="mt-1 font-semibold">
                    {card.evidence_strength.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Window risk</dt>
                  <dd className="mt-1 font-semibold">
                    {card.decision === "Act"
                      ? "Low"
                      : card.decision === "Watch"
                        ? "Moderate"
                        : "High"}
                  </dd>
                </div>
              </>
            )}
            {isToday ? (
              <div className="col-span-2 border-t border-[var(--line)] pt-3">
                <dt className="flex items-center gap-2 font-semibold tracking-[0.08em] uppercase">
                  <ShieldAlert size={12} /> Main risk
                </dt>
                <dd className="mt-2 leading-5 text-[var(--muted)]">
                  {card.main_risk}
                </dd>
              </div>
            ) : null}
          </dl>
          {!isToday ? (
            <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">
              Fit is the match with your channel history. Window risk is the
              chance the useful moment closes before you can publish.
            </p>
          ) : null}

          <div
            className={`mt-4 border-t border-[var(--line)] pt-4 ${
              stickyMobile ? "max-sm:hidden" : ""
            }`}
          >
            <DecisionFeedback
              allowAct={card.release_ready}
              busy={mutation.isPending}
              currentAction={currentAction}
              onSubmit={(action, reason, comment, plan) =>
                mutation.mutate({ action, reason, comment, plan })
              }
              productionDaysMax={card.production_days_max}
              productionDaysMin={card.production_days_min}
              recommendedPublishBy={card.recommended_publish_by}
            />
            {mutation.isSuccess ? (
              <p
                className="mt-3 border-l-2 border-[var(--lime-strong)] pl-3 text-[12px] font-medium"
                role="status"
              >
                {savedDecision}
              </p>
            ) : null}
          </div>
        </aside>
      </div>
      {stickyMobile ? (
        <div
          className="fixed inset-x-0 bottom-[calc(68px+env(safe-area-inset-bottom))] z-30 rounded-t-2xl border-t border-[var(--line)] bg-white/95 p-3 shadow-[0_-10px_28px_rgb(31_36_34_/_10%)] backdrop-blur-xl sm:hidden"
          data-testid="mobile-sticky-actions"
        >
          <DecisionFeedback
            allowAct={card.release_ready}
            busy={mutation.isPending}
            compact
            currentAction={currentAction}
            onSubmit={(action, reason, comment, plan) =>
              mutation.mutate({ action, reason, comment, plan })
            }
            productionDaysMax={card.production_days_max}
            productionDaysMin={card.production_days_min}
            recommendedPublishBy={card.recommended_publish_by}
          />
          {mutation.isSuccess ? (
            <p className="mt-2 text-[12px] font-medium" role="status">
              {savedDecision}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
