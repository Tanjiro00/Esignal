"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ProducerBrief } from "@/components/briefs/producer-brief";
import { ErrorState, PageLoading } from "@/components/ui";
import { getBriefs, getDemoContext, getSignalPackaging } from "@/lib/api";
import type { Brief, DemoContext, SignalPackaging } from "@/lib/types";

type BriefsData = {
  context: DemoContext;
  briefs: Brief[];
  packaging: Record<string, SignalPackaging>;
};

export default function BriefsPage() {
  const query = useQuery<BriefsData>({
    queryKey: ["briefs-v2"],
    queryFn: async () => {
      const context = await getDemoContext();
      const briefs = await getBriefs(context.workspace_id);
      const packagingRows = await Promise.all(
        briefs.map(async (brief) => {
          if (!brief.opportunity_id) return null;
          return getSignalPackaging(
            context.workspace_id,
            brief.signal_id,
            brief.opportunity_id,
          ).catch(() => null);
        }),
      );
      return {
        context,
        briefs,
        packaging: Object.fromEntries(
          packagingRows
            .filter((row): row is SignalPackaging => row !== null)
            .map((row) => [row.content_brief_id, row]),
        ),
      };
    },
  });

  if (query.isLoading) return <PageLoading label="Loading video plans" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  return (
    <div className="mx-auto max-w-[1060px] px-5 py-8 sm:px-8 sm:py-12">
      <header className="border-b border-[var(--ink)] pb-8">
        <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          Step 2 · prepare the video
        </p>
        <h1 className="editorial mt-3 text-[46px] leading-none sm:text-[62px]">
          Video plans
        </h1>
        <p className="mt-4 max-w-[660px] text-[14px] leading-7 text-[var(--muted)]">
          Every idea you choose to make becomes an editable production plan with
          the angle, evidence, proof checklist and target publish date.
        </p>
      </header>

      {query.data.briefs.length ? (
        <main className="divide-y divide-[var(--ink)]">
          {query.data.briefs.map((brief, index) => (
            <ProducerBrief
              brief={brief}
              context={query.data.context}
              index={index}
              key={brief.id}
              packaging={query.data.packaging[brief.id]}
            />
          ))}
        </main>
      ) : (
        <main className="grid min-h-[460px] place-items-center text-center">
          <div className="max-w-[520px]">
            <h2 className="editorial text-[32px]">No video plans yet</h2>
            <p className="mt-3 text-[13px] leading-6 text-[var(--muted)]">
              Open an idea and choose Create video plan. It will appear here
              ready for editing and production.
            </p>
            <Link
              className="mt-6 inline-flex min-h-11 items-center border border-[var(--ink)] bg-[var(--ink)] px-4 text-[12px] font-medium !text-white"
              href="/opportunities"
            >
              Open idea library
            </Link>
          </div>
        </main>
      )}
    </div>
  );
}
