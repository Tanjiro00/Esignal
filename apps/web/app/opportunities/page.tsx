"use client";

import { useQuery } from "@tanstack/react-query";
import { SearchX } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { OpportunityLibraryRow } from "@/components/opportunities/opportunity-library-row";
import { ErrorState, PageLoading } from "@/components/ui";
import { getBriefs, getDemoContext, getSignals } from "@/lib/api";
import { decisionCardFromSignal } from "@/lib/decision-card";
import {
  latestBriefBySignal,
  opportunityGroup,
  opportunityGroupFromParam,
  OPPORTUNITY_GROUPS,
  type OpportunityGroupKey,
} from "@/lib/opportunity-library";
import type {
  Brief,
  DemoContext,
  SignalFeedResponse,
  SignalListItem,
} from "@/lib/types";

type OpportunitiesData = {
  context: DemoContext;
  feed: SignalFeedResponse;
  briefs: Brief[];
};

function opportunitySort(a: SignalListItem, b: SignalListItem) {
  const priority = { Act: 0, Watch: 1, Skip: 2 };
  const decisionDelta =
    priority[decisionCardFromSignal(a).decision] -
    priority[decisionCardFromSignal(b).decision];
  if (decisionDelta !== 0) return decisionDelta;
  return (
    new Date(a.opportunity_window.end).getTime() -
    new Date(b.opportunity_window.end).getTime()
  );
}

const mobileGroupLabels: Record<OpportunityGroupKey, string> = {
  needs_decision: "Inbox",
  watching: "Tracking",
  in_production: "Plans",
  skipped: "Dismissed",
  expired: "Closed",
};

function OpportunitiesContent() {
  const searchParams = useSearchParams();
  const query = useQuery<OpportunitiesData>({
    queryKey: ["opportunities"],
    queryFn: async () => {
      const context = await getDemoContext();
      const [feed, briefs] = await Promise.all([
        getSignals(context.workspace_id),
        getBriefs(context.workspace_id),
      ]);
      return { context, feed, briefs };
    },
  });

  const briefsBySignal = useMemo(
    () => latestBriefBySignal(query.data?.briefs ?? []),
    [query.data?.briefs],
  );
  const grouped = useMemo(() => {
    const result: Record<OpportunityGroupKey, SignalListItem[]> = {
      needs_decision: [],
      watching: [],
      in_production: [],
      skipped: [],
      expired: [],
    };
    const now = new Date();
    for (const signal of query.data?.feed.items ?? []) {
      result[opportunityGroup(signal, briefsBySignal.get(signal.id), now)].push(
        signal,
      );
    }
    for (const group of OPPORTUNITY_GROUPS) {
      result[group.key].sort(opportunitySort);
    }
    return result;
  }, [briefsBySignal, query.data?.feed.items]);
  const firstNonEmptyGroup =
    OPPORTUNITY_GROUPS.find((group) => grouped[group.key].length > 0)?.key ??
    "needs_decision";
  const activeGroup =
    opportunityGroupFromParam(searchParams.get("group")) ?? firstNonEmptyGroup;
  const activeDefinition =
    OPPORTUNITY_GROUPS.find((group) => group.key === activeGroup) ??
    OPPORTUNITY_GROUPS[0];
  const visible = grouped[activeGroup];

  if (query.isLoading) return <PageLoading label="Loading opportunities" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  return (
    <div className="motion-page mx-auto max-w-[1160px] px-5 py-5 sm:px-8 sm:py-7">
      <header className="pb-3 sm:pb-4">
        <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          Step 1 · choose what to do
        </p>
        <h1 className="editorial mt-2 text-[42px] leading-none sm:text-[52px]">
          Idea library
        </h1>
        <p className="mt-1.5 max-w-[720px] text-[14px] leading-5 text-[var(--muted)] sm:mt-2 sm:leading-6">
          <span className="sm:hidden">
            Choose an idea, make a plan, track it, or dismiss it.
          </span>
          <span className="hidden sm:inline">
            New ideas start in Inbox. Create a video plan, save an idea in
            Tracking while new evidence arrives, or dismiss it.
          </span>
        </p>
        <nav
          aria-label="Opportunity status groups"
          className="mt-3 grid grid-cols-5 gap-1 rounded-xl bg-[var(--surface-subtle)] p-1 sm:mt-4 sm:flex"
        >
          {OPPORTUNITY_GROUPS.map((group) => {
            const active = activeGroup === group.key;
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`relative flex min-h-9 min-w-0 items-center justify-center gap-1 rounded-lg px-0 text-[11px] font-medium transition-[transform,box-shadow,background-color,color] duration-200 sm:shrink-0 sm:gap-2 sm:px-3 sm:text-[13px] ${
                  active
                    ? "bg-white text-[var(--ink)] shadow-sm"
                    : "text-[var(--muted)] hover:bg-white/70 hover:text-[var(--ink)]"
                }`}
                href={`/opportunities?group=${group.key}`}
                key={group.key}
                scroll={false}
              >
                <span className="min-w-0 truncate sm:hidden">
                  {mobileGroupLabels[group.key]}
                </span>
                <span className="hidden sm:inline">{group.label}</span>
                <span
                  className={`shrink-0 text-center text-[10px] sm:min-w-5 sm:text-[11px] ${
                    active ? "font-semibold" : ""
                  }`}
                >
                  {grouped[group.key].length}
                </span>
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="py-4 sm:py-5">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h2 className="editorial text-[28px] sm:text-[32px]">
              {activeDefinition.label}
            </h2>
            <p className="mt-1 max-w-[620px] text-[12px] leading-5 text-[var(--muted)]">
              {activeDefinition.description}
            </p>
          </div>
          <p className="text-[12px] text-[var(--muted)]">
            {visible.length} {visible.length === 1 ? "idea" : "ideas"}
          </p>
        </div>

        {visible.length ? (
          <section
            aria-label={`${activeDefinition.label} opportunities`}
            className="motion-card mt-4 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-soft)]"
            data-testid={`opportunity-group-${activeGroup}`}
          >
            <div
              aria-hidden="true"
              className="hidden grid-cols-[minmax(320px,1fr)_86px_92px_110px_78px_104px_24px] gap-3 border-b border-[var(--line-strong)] bg-[var(--surface-subtle)] px-5 py-2.5 text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase xl:grid"
              data-testid="opportunity-library-columns"
            >
              <span>Idea</span>
              <span>Next step</span>
              <span>Stage</span>
              <span>Publish by</span>
              <span>Fit</span>
              <span>Status</span>
              <span />
            </div>
            <ul className="motion-list">
              {visible.map((signal) => (
                <OpportunityLibraryRow
                  brief={briefsBySignal.get(signal.id)}
                  group={activeGroup}
                  key={signal.id}
                  signal={signal}
                />
              ))}
            </ul>
          </section>
        ) : (
          <section className="motion-card mt-4 grid min-h-[220px] place-items-center rounded-2xl border border-[var(--line)] bg-[var(--surface-subtle)] text-center shadow-[var(--shadow-soft)]">
            <div>
              <SearchX className="mx-auto text-[var(--muted)]" size={26} />
              <h2 className="editorial mt-4 text-[28px]">
                Nothing in {activeDefinition.label.toLowerCase()}
              </h2>
              <p className="mt-3 max-w-[460px] text-[13px] leading-6 text-[var(--muted)]">
                {activeDefinition.description}
              </p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<PageLoading label="Loading opportunities" />}>
      <OpportunitiesContent />
    </Suspense>
  );
}
