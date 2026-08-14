"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Check, Clock3, ExternalLink, Link2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ResultComparator } from "@/components/results/result-comparator";
import { Button, ErrorState, PageLoading } from "@/components/ui";
import {
  confirmOutcomeSuggestion,
  getDemoContext,
  getOutcomes,
  getOutcomeSuggestions,
  rejectOutcomeSuggestion,
  trackProductEvent,
} from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import { relativeTime } from "@/lib/format";
import { outcomeMetric, resultComparator } from "@/lib/result-comparator";
import type { DemoContext, Outcome, OutcomeSuggestion } from "@/lib/types";

type ResultsData = {
  context: DemoContext;
  outcomes: Outcome[];
  suggestions: OutcomeSuggestion[];
};

export default function ResultsPage() {
  const client = useQueryClient();
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const query = useQuery<ResultsData>({
    queryKey: ["results-v2"],
    queryFn: async () => {
      const context = await getDemoContext();
      const [outcomes, suggestions] = await Promise.all([
        getOutcomes(context.workspace_id),
        getOutcomeSuggestions(context.workspace_id),
      ]);
      return { context, outcomes, suggestions };
    },
  });
  const suggestionMutation = useMutation({
    mutationFn: ({
      suggestion,
      action,
    }: {
      suggestion: OutcomeSuggestion;
      action: "confirm" | "reject";
    }) =>
      action === "confirm"
        ? confirmOutcomeSuggestion(
            query.data!.context.workspace_id,
            suggestion.id,
            suggestion.suggested_brief_id,
          )
        : rejectOutcomeSuggestion(
            query.data!.context.workspace_id,
            suggestion.id,
          ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["results-v2"] }),
  });

  if (query.isLoading)
    return <PageLoading label="Loading channel performance" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const outcomesWithComparators = query.data.outcomes.map((outcome) => ({
    outcome,
    comparator: resultComparator(outcome.performance_json),
  }));
  const stableComparators = outcomesWithComparators.filter(
    ({ comparator }) => comparator.stable,
  ).length;

  return (
    <div className="mx-auto max-w-[1080px] px-5 py-8 sm:px-8 sm:py-12">
      <header className="border-b border-[var(--ink)] pb-8">
        <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          Step 3 · learn from the published video
        </p>
        <h1 className="editorial mt-3 text-[46px] leading-none sm:text-[62px]">
          Performance
        </h1>
        <p className="mt-4 max-w-[680px] text-[14px] leading-7 text-[var(--muted)]">
          After a planned video is published, EarlySignal links it to the idea
          and compares its early performance with your channel baseline.
        </p>
        {query.data.outcomes.length ? (
          <div className="mt-6 flex flex-wrap gap-x-7 gap-y-2 text-[11px] text-[var(--muted)]">
            <span>
              {query.data.outcomes.length} linked{" "}
              {query.data.outcomes.length === 1 ? "video" : "videos"}
            </span>
            <span>{stableComparators} with a stable comparator</span>
            <span>
              {query.data.suggestions.length}{" "}
              {query.data.suggestions.length === 1 ? "item" : "items"} awaiting
              confirmation
            </span>
          </div>
        ) : null}
      </header>

      {query.data.suggestions.length ? (
        <section className="my-8 border border-[var(--lime-strong)] bg-[var(--lime-soft)] p-5 sm:p-7">
          <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
            Automatic video match
          </p>
          <h2 className="editorial mt-2 text-[30px]">
            We found a likely published video
          </h2>
          <p className="mt-3 max-w-[680px] text-[12px] leading-6 text-[var(--muted)]">
            Confirm which video plan this upload belongs to, or mark it
            unrelated. EarlySignal never claims the source idea caused the
            performance.
          </p>
          <div className="mt-5 divide-y divide-[var(--line-strong)] border-t border-[var(--line-strong)]">
            {query.data.suggestions.map((suggestion) => (
              <article
                className="grid gap-4 py-5 lg:grid-cols-[1fr_1fr_auto]"
                key={suggestion.id}
              >
                <div>
                  <a
                    className="inline-flex items-start gap-2 text-[13px] font-semibold hover:underline"
                    href={suggestion.video_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {suggestion.video_title}
                    <ExternalLink className="mt-0.5" size={12} />
                  </a>
                  <p className="mt-2 text-[10px] text-[var(--muted)]">
                    Published {relativeTime(suggestion.published_at)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--muted)]">
                    Likely related video plan
                  </p>
                  <p className="mt-1 text-[12px] font-medium">
                    {suggestion.brief_title}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    aria-label="Mark suggestion unrelated"
                    disabled={suggestionMutation.isPending}
                    onClick={() =>
                      suggestionMutation.mutate({
                        suggestion,
                        action: "reject",
                      })
                    }
                  >
                    <X size={13} /> Not related
                  </Button>
                  <Button
                    disabled={suggestionMutation.isPending}
                    onClick={() =>
                      suggestionMutation.mutate({
                        suggestion,
                        action: "confirm",
                      })
                    }
                    variant="primary"
                  >
                    <Link2 size={13} /> Confirm
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {query.data.outcomes.length ? (
        <main className="divide-y divide-[var(--line-strong)] border-b border-[var(--line-strong)]">
          {outcomesWithComparators.map(({ outcome, comparator }) => {
            const avd = outcomeMetric(
              outcome.performance_json,
              "average_view_duration_seconds",
              "average_view_duration",
            );
            const isOpen = opened[outcome.id] ?? false;
            const displayStatus = comparator.stable
              ? outcome.success_status
              : "early";
            return (
              <article
                className="py-7 sm:py-9"
                data-testid={`outcome-result-${outcome.id}`}
                key={outcome.id}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={`inline-flex min-h-8 items-center gap-2 px-3 text-[10px] font-semibold uppercase ${
                      displayStatus === "successful"
                        ? "bg-[var(--lime-soft)] text-[var(--lime-ink)]"
                        : "bg-[var(--surface-subtle)] text-[var(--muted)]"
                    }`}
                  >
                    {displayStatus === "successful" ? (
                      <Check size={13} />
                    ) : (
                      <Clock3 size={13} />
                    )}
                    {displayStatus}
                  </span>
                  <span className="text-[10px] text-[var(--muted)]">
                    Published {relativeTime(outcome.published_at)}
                  </span>
                </div>
                <div className="mt-4 grid gap-5 md:grid-cols-[1fr_auto] md:items-end">
                  <div>
                    <h2 className="editorial text-[30px] leading-tight sm:text-[34px]">
                      Video {outcome.youtube_video_id}
                    </h2>
                    <p className="mt-3 max-w-[680px] text-[12px] leading-6 text-[var(--muted)]">
                      {outcome.user_notes ||
                        "Performance is waiting for the next owned-channel analytics snapshot."}
                    </p>
                  </div>
                  <Link
                    className="inline-flex min-h-11 items-center gap-2 text-[12px] font-medium hover:underline"
                    href={`/opportunities/${outcome.signal_id}`}
                  >
                    Source idea <ExternalLink size={13} />
                  </Link>
                </div>

                <ResultComparator comparator={comparator} />

                <button
                  aria-expanded={isOpen}
                  className="mt-5 min-h-11 text-[11px] font-medium underline-offset-4 hover:underline"
                  onClick={() => {
                    setOpened((current) => ({
                      ...current,
                      [outcome.id]: !isOpen,
                    }));
                    if (!isOpen) {
                      void trackProductEvent(query.data.context.workspace_id, {
                        event_type: "result_opened",
                        event_key: `result-opened:${createClientEventId()}:${outcome.id}`,
                        signal_id: outcome.signal_id,
                        metadata: { outcome_id: outcome.id },
                      }).catch(() => undefined);
                    }
                  }}
                  type="button"
                >
                  {isOpen
                    ? "Hide performance details"
                    : "View performance details"}
                </button>
                {isOpen ? (
                  <div
                    className="grid gap-5 border-t border-[var(--line)] pt-5 text-[11px] leading-6 md:grid-cols-3"
                    data-testid="result-details"
                  >
                    <div>
                      <strong className="block">Baseline definition</strong>
                      <p className="mt-1 text-[var(--muted)]">
                        {outcome.baseline_definition}
                      </p>
                    </div>
                    <div>
                      <strong className="block">Average view duration</strong>
                      <p className="mt-1 text-[var(--muted)]">
                        {avd === null
                          ? "Pending"
                          : `${Math.round(avd)} seconds`}
                      </p>
                    </div>
                    <div>
                      <strong className="block">Association status</strong>
                      <p className="mt-1 text-[var(--muted)] capitalize">
                        {outcome.link_status.replaceAll("_", " ")}
                      </p>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </main>
      ) : (
        <main className="grid min-h-[460px] place-items-center text-center">
          <div className="max-w-[520px]">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-[var(--surface-subtle)]">
              <BarChart3 size={20} />
            </span>
            <h2 className="editorial mt-5 text-[32px]">
              No published plan to measure yet
            </h2>
            <p className="mt-3 text-[13px] leading-6 text-[var(--muted)]">
              Move a video plan into production and publish the related video.
              EarlySignal will suggest the match automatically.
            </p>
            <Link
              className="mt-6 inline-flex min-h-11 items-center border border-[var(--ink)] bg-[var(--ink)] px-4 text-[12px] font-medium !text-white"
              href="/briefs"
            >
              Open video plans
            </Link>
          </div>
        </main>
      )}
    </div>
  );
}
