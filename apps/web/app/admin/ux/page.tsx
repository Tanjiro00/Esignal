"use client";

import { useQuery } from "@tanstack/react-query";

import { ErrorState, PageLoading } from "@/components/ui";
import { getAnalyticsSummary, getDemoContext } from "@/lib/api";
import type { AnalyticsSummary, DemoContext } from "@/lib/types";

type UxData = { context: DemoContext; analytics: AnalyticsSummary };

const labels: Record<string, string> = {
  today_opened: "Today opened",
  opportunity_card_viewed: "Opportunity cards viewed",
  opportunity_opened: "Opportunities opened",
  why_recommended_opened: "Why recommended opened",
  evidence_opened: "Evidence opened",
  technical_details_opened: "Technical details opened",
  act_clicked: "Act clicked",
  watch_clicked: "Watch clicked",
  skip_clicked: "Skip clicked",
  decision_reason_selected: "Decision reason selected",
  brief_created: "Briefs created",
  brief_shared: "Briefs shared",
  production_started: "Production started",
  result_opened: "Results opened",
  onboarding_started: "Onboarding started",
  onboarding_step_completed: "Onboarding steps completed",
  onboarding_completed: "Onboarding completed",
};

export default function UxAnalyticsPage() {
  const query = useQuery<UxData>({
    queryKey: ["admin-ux-analytics"],
    queryFn: async () => {
      const context = await getDemoContext();
      const analytics = await getAnalyticsSummary(context.workspace_id);
      return { context, analytics };
    },
  });

  if (query.isLoading) return <PageLoading label="Loading UX analytics" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;
  if (!query.data.context.is_admin) {
    return (
      <div className="mx-auto max-w-[720px] px-6 py-24">
        <h1 className="editorial text-[36px]">Admin access required</h1>
        <p className="mt-3 text-[13px] text-[var(--muted)]">
          UX analytics is visible only to workspace owners and admins.
        </p>
      </div>
    );
  }

  const events = query.data.analytics.ux?.events ?? {};
  return (
    <div className="mx-auto max-w-[1100px] px-5 py-8 sm:px-8 sm:py-12">
      <header className="border-b border-[var(--ink)] pb-7">
        <p className="text-[10px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          Private beta
        </p>
        <h1 className="editorial mt-2 text-[46px]">UX analytics</h1>
        <p className="mt-3 max-w-[650px] text-[12px] leading-6 text-[var(--muted)]">
          Decision and onboarding behavior for beta analysis. This dashboard
          measures comprehension and completion, not engagement for its own
          sake.
        </p>
      </header>

      <section className="grid gap-px border-x border-b border-[var(--line)] bg-[var(--line)] sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(events).map(([key, value]) => (
          <div className="bg-white p-5" key={key}>
            <p className="text-[10px] leading-5 text-[var(--muted)]">
              {labels[key] ?? key.replaceAll("_", " ")}
            </p>
            <p className="editorial mt-2 text-[32px]">{value}</p>
          </div>
        ))}
      </section>

      <section className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h2 className="editorial text-[28px]">Decision funnel</h2>
          <div className="mt-4 divide-y divide-[var(--line)] border-y border-[var(--line)]">
            {(query.data.analytics.ux?.decision_funnel ?? []).map(
              (item, index) => (
                <div
                  className="grid grid-cols-[28px_1fr_auto] gap-3 py-4 text-[12px]"
                  key={item.key}
                >
                  <span className="text-[var(--muted)]">{index + 1}</span>
                  <span className="capitalize">
                    {item.key.replaceAll("_", " ")}
                  </span>
                  <strong>{item.value}</strong>
                </div>
              ),
            )}
          </div>
        </div>
        <div>
          <h2 className="editorial text-[28px]">Onboarding funnel</h2>
          <div className="mt-4 divide-y divide-[var(--line)] border-y border-[var(--line)]">
            {(query.data.analytics.ux?.onboarding_funnel ?? []).map(
              (item, index) => (
                <div
                  className="grid grid-cols-[28px_1fr_auto] gap-3 py-4 text-[12px]"
                  key={item.key}
                >
                  <span className="text-[var(--muted)]">{index + 1}</span>
                  <span className="capitalize">
                    {item.key.replaceAll("_", " ")}
                  </span>
                  <strong>{item.value}</strong>
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      <section className="mt-8 border-t border-[var(--line-strong)] pt-6">
        <h2 className="editorial text-[28px]">Observed timing</h2>
        <div className="mt-4 grid gap-px border border-[var(--line)] bg-[var(--line)] sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(query.data.analytics.ux?.timing ?? {}).map(
            ([key, value]) => (
              <div className="bg-white p-4" key={key}>
                <p className="text-[10px] text-[var(--muted)]">
                  {key.replaceAll("_", " ")}
                </p>
                <p className="mt-2 text-[15px] font-semibold">
                  {value === null
                    ? "Collecting"
                    : `${Math.max(Math.round(value / 1000), 1)} sec`}
                </p>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="mt-8 border-t border-[var(--line-strong)] pt-6">
        <h2 className="editorial text-[28px]">Beta targets</h2>
        <div className="mt-4 grid gap-4 text-[11px] sm:grid-cols-2 lg:grid-cols-4">
          <p>First card understood in under 30 seconds</p>
          <p>Act / Watch / Skip in under 2 minutes</p>
          <p>Brief created in under 5 minutes</p>
          <p>Onboarding completion above 70%</p>
        </div>
      </section>
    </div>
  );
}
