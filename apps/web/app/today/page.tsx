"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, RefreshCw, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { OpportunityDecisionCard } from "@/components/opportunities/opportunity-decision-card";
import { Button, ErrorState } from "@/components/ui";
import {
  generateDigest,
  getBriefs,
  getDemoContext,
  getLatestDigest,
  getSignals,
  trackProductEvent,
} from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import { decisionCardFromDigest } from "@/lib/decision-card";
import { relativeTime } from "@/lib/format";
import {
  latestBriefBySignal,
  opportunityGroup,
} from "@/lib/opportunity-library";
import { todayRefetchInterval } from "@/lib/today-refresh";
import type {
  Brief,
  DemoContext,
  DigestItem,
  DigestRun,
  SignalFeedResponse,
} from "@/lib/types";

type TodayData = {
  context: DemoContext;
  digest: DigestRun;
  feed: SignalFeedResponse;
  briefs: Brief[];
};

function TodayLoading() {
  return (
    <div
      aria-label="Loading today’s opportunities"
      className="mx-auto max-w-[1160px] px-5 py-8 sm:px-8 sm:py-12"
      role="status"
    >
      <div className="skeleton h-4 w-40" />
      <div className="skeleton mt-5 h-14 w-2/3 max-w-[620px]" />
      <div className="skeleton mt-4 h-5 w-1/2 max-w-[480px]" />
      <div className="skeleton mt-10 h-[580px] w-full" />
    </div>
  );
}

export default function TodayPage() {
  const client = useQueryClient();
  const opened = useRef(false);
  const query = useQuery<TodayData>({
    queryKey: ["today"],
    queryFn: async () => {
      const context = await getDemoContext();
      const [digest, feed, briefs] = await Promise.all([
        getLatestDigest(context.workspace_id),
        getSignals(context.workspace_id),
        getBriefs(context.workspace_id),
      ]);
      return { context, digest, feed, briefs };
    },
    refetchInterval: (currentQuery) =>
      todayRefetchInterval(currentQuery.state.data),
  });
  const refresh = useMutation({
    mutationFn: () => generateDigest(query.data!.context.workspace_id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["today"] }),
  });

  useEffect(() => {
    if (!query.data || opened.current) return;
    opened.current = true;
    window.sessionStorage.setItem(
      "earlysignal_today_started_at",
      String(Date.now()),
    );
    void trackProductEvent(query.data.context.workspace_id, {
      event_type: "today_opened",
      event_key: `today-opened:${createClientEventId()}`,
      metadata: { surface: "today" },
    }).catch(() => undefined);
  }, [query.data]);

  if (query.isLoading) return <TodayLoading />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const bySignal = new Map(
    query.data.feed.items.map((signal) => [signal.id, signal]),
  );
  const latestBriefs = latestBriefBySignal(query.data.briefs);
  const groups = new Map(
    query.data.feed.items.map((signal) => [
      signal.id,
      opportunityGroup(signal, latestBriefs.get(signal.id)),
    ]),
  );
  const ranked = [...query.data.digest.content.items].sort((a, b) => {
    const priority = { Act: 0, Watch: 1, Skip: 2 };
    return (
      priority[decisionCardFromDigest(a).decision] -
      priority[decisionCardFromDigest(b).decision]
    );
  });
  const visible = ranked
    .filter((item) => {
      const signal = bySignal.get(item.signal_id);
      const card = decisionCardFromDigest(item);
      return (
        signal !== undefined &&
        groups.get(signal.id) === "needs_decision" &&
        card.release_ready &&
        card.decision !== "Skip"
      );
    })
    .slice(0, 3);
  const researchCandidates = query.data.feed.items
    .filter(
      (signal) =>
        signal.decision_card !== null &&
        !signal.decision_card.release_ready &&
        !signal.current_action,
    )
    .sort(
      (a, b) =>
        b.channel_fit * 0.6 +
        b.score * 0.4 -
        (a.channel_fit * 0.6 + a.score * 0.4),
    );
  const decisions = visible.map((item) => decisionCardFromDigest(item));
  const actCount = decisions.filter((card) => card.decision === "Act").length;
  const watchCount = decisions.filter(
    (card) => card.decision === "Watch",
  ).length;
  const trackingCount = query.data.feed.items.filter(
    (signal) => signal.current_action === "watch",
  ).length;
  const candidateCount = researchCandidates.length;
  const isInitialAnalysis = query.data.feed.total === 0;
  const filteredCount = Math.max(
    query.data.feed.total - visible.length - trackingCount - candidateCount,
    0,
  );

  return (
    <div className="mx-auto max-w-[1160px] px-5 pt-6 pb-[calc(8rem+env(safe-area-inset-bottom))] sm:px-8 sm:py-10">
      <header className="border-b border-[var(--ink)] pb-5 sm:pb-7">
        <p className="text-[10px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          What needs your decision?
        </p>
        <h1 className="editorial mt-2 text-[42px] leading-none sm:text-[54px]">
          Today
        </h1>
        <p className="mt-3 max-w-[680px] text-[13px] leading-6 text-[var(--muted)]">
          {actCount
            ? `${actCount} ${actCount === 1 ? "idea is" : "ideas are"} ready to make for ${query.data.context.owned_channel_name}.`
            : watchCount
              ? `${watchCount} specific ${watchCount === 1 ? "idea is" : "ideas are"} worth tracking. Nothing needs production today.`
              : candidateCount
                ? `${candidateCount} relevant ${candidateCount === 1 ? "topic is" : "topics are"} being validated for ${query.data.context.owned_channel_name}.`
                : isInitialAnalysis
                  ? `We are building the first evidence-backed signal set for ${query.data.context.owned_channel_name}.`
                  : "Nothing needs your attention right now. We are still monitoring your niche."}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-[var(--muted)]">
          <span className="flex shrink-0 items-center gap-2">
            <BellRing size={13} /> {actCount} ready now · {watchCount} released
            watch alerts · {candidateCount} research candidates ·{" "}
            {trackingCount} saved
          </span>
          <span className="shrink-0 max-sm:hidden">
            {filteredCount} weak, closed or already-decided topics filtered out
          </span>
          <span className="flex shrink-0 items-center gap-1">
            Updated {relativeTime(query.data.digest.generated_at)}
            <span aria-hidden="true">·</span>
            <Button
              className="min-h-8 px-1 text-[11px]"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
              variant="ghost"
            >
              <RefreshCw size={12} />
              {refresh.isPending ? "Checking…" : "Refresh"}
            </Button>
          </span>
        </div>
      </header>

      {visible.length ? (
        <main className="space-y-6 py-5 sm:py-7">
          {visible.map((item: DigestItem, index) => {
            const signal = bySignal.get(item.signal_id);
            return (
              <OpportunityDecisionCard
                card={decisionCardFromDigest(item)}
                context={query.data.context}
                currentAction={signal?.current_action}
                evidenceCount={signal?.evidence_videos}
                evidenceLinks={item.evidence_videos}
                key={item.signal_id}
                opportunityId={item.recommended_angle.opportunity_id}
                rank={index + 1}
                signalId={item.signal_id}
                stickyMobile={index === 0}
                surface="today"
                topicStage={item.lifecycle_stage}
              />
            );
          })}
        </main>
      ) : researchCandidates.length ? (
        <main className="space-y-5 py-5 sm:py-7">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--line)] pb-4">
            <div>
              <p className="text-[10px] font-semibold tracking-[0.12em] text-[var(--amber)] uppercase">
                Relevant, not released yet
              </p>
              <h2 className="editorial mt-1 text-[28px]">
                Signals we found for your channel
              </h2>
              <p className="mt-2 max-w-[720px] text-[13px] leading-5 text-[var(--muted)]">
                These topics passed channel relevance and source coverage. They
                remain candidates until the evidence supports a genuinely
                non-obvious insight. You can open the sources or track a topic
                now.
              </p>
            </div>
            <Link
              className="inline-flex min-h-10 items-center text-[12px] font-semibold hover:underline"
              href="/opportunities"
            >
              Open full library
            </Link>
          </div>
          {researchCandidates.slice(0, 3).map((signal, index) => (
            <OpportunityDecisionCard
              card={signal.decision_card!}
              context={query.data.context}
              currentAction={signal.current_action}
              evidenceCount={signal.evidence_videos}
              evidenceLinks={signal.evidence_preview}
              key={signal.id}
              rank={index + 1}
              signalId={signal.id}
              stickyMobile={index === 0}
              surface="default"
              topicStage={signal.lifecycle_stage}
            />
          ))}
        </main>
      ) : (
        <main className="grid min-h-[440px] place-items-center border-b border-[var(--line)] text-center">
          <div className="max-w-[560px] py-16">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-[var(--surface-subtle)]">
              <SlidersHorizontal size={20} />
            </span>
            <h2 className="editorial mt-5 text-[32px]">
              {isInitialAnalysis
                ? "Building your first signal set"
                : "No decision needed today"}
            </h2>
            <p className="mt-3 text-[13px] leading-6 text-[var(--muted)]">
              {isInitialAnalysis ? (
                <>
                  Your focused searches are collecting and comparing channel
                  evidence now. The first relevant candidates will appear here
                  automatically; this page checks again every 15 seconds.
                </>
              ) : (
                <>
                  We filtered out weak, generic, saturated and already-decided
                  topics. {trackingCount} research{" "}
                  {trackingCount === 1
                    ? "candidate remains"
                    : "candidates remain"}{" "}
                  in Tracking. A card appears here only after stored evidence
                  supports a non-obvious audience question or audited content
                  insight.
                </>
              )}
            </p>
            <Link
              className="mt-6 inline-flex min-h-11 items-center border border-[var(--line-strong)] px-4 text-[12px] font-medium hover:border-[var(--ink)]"
              href="/opportunities"
            >
              Browse all opportunities
            </Link>
          </div>
        </main>
      )}

      <footer className="flex flex-wrap items-center justify-between gap-4 py-6 text-[11px] text-[var(--muted)]">
        <span>
          Digest notifications are limited to meaningful updates, two or three
          times per week.
        </span>
        <Link
          className="font-medium text-[var(--ink)] hover:underline"
          href="/settings#notifications"
        >
          Notification settings
        </Link>
      </footer>
    </div>
  );
}
