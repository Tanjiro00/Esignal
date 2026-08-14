import { ArrowRight, CalendarClock } from "lucide-react";
import Link from "next/link";

import { decisionCardFromSignal } from "@/lib/decision-card";
import {
  opportunityStatusLabel,
  type OpportunityGroupKey,
} from "@/lib/opportunity-library";
import type { Brief, SignalListItem } from "@/lib/types";

function DecisionChip({ decision }: { decision: "Act" | "Watch" | "Skip" }) {
  const label =
    decision === "Act"
      ? "Make now"
      : decision === "Watch"
        ? "Wait"
        : "Not recommended";
  return (
    <span
      className={`inline-flex min-h-7 w-fit max-w-full items-center justify-center rounded-full border px-2.5 text-center text-[11px] leading-tight font-semibold tracking-[0.06em] whitespace-normal uppercase ${
        decision === "Act"
          ? "border-[var(--lime-strong)] bg-[var(--lime-soft)] text-[var(--lime-ink)]"
          : decision === "Watch"
            ? "border-[var(--amber)] bg-[var(--amber-soft)] text-[var(--ink)]"
            : "border-[var(--line-strong)] bg-white text-[var(--muted)]"
      }`}
    >
      {label}
    </span>
  );
}

function CellLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase xl:hidden">
      {children}
    </span>
  );
}

export function OpportunityLibraryRow({
  signal,
  brief,
  group,
}: {
  signal: SignalListItem;
  brief?: Brief;
  group: OpportunityGroupKey;
}) {
  const card = decisionCardFromSignal(signal);
  const status =
    !card.release_ready && group === "watching"
      ? "Insight pending"
      : opportunityStatusLabel(group, brief);

  return (
    <li>
      <Link
        aria-label={`Open idea: ${card.recommended_video}`}
        className="group grid grid-cols-3 gap-x-3 gap-y-3 border-b border-[var(--line)] px-4 py-3.5 transition-[transform,background-color] duration-200 ease-out last:border-b-0 hover:translate-x-0.5 hover:bg-[var(--surface-subtle)] focus-visible:bg-[var(--surface-subtle)] xl:grid-cols-[minmax(320px,1fr)_86px_92px_110px_78px_104px_24px] xl:items-center xl:gap-3 xl:px-5 xl:py-3"
        data-testid="opportunity-library-row"
        href={`/opportunities/${signal.id}?from=${group}`}
      >
        <div className="col-span-3 min-w-0 xl:col-span-1">
          <p className="line-clamp-2 text-[14px] leading-5 font-semibold break-words">
            {card.recommended_video}
          </p>
          <p className="mt-1 truncate text-[12px] text-[var(--muted)]">
            {card.topic} · {signal.evidence_videos} sources
          </p>
        </div>
        <div>
          <CellLabel>Next step</CellLabel>
          <DecisionChip decision={card.decision} />
        </div>
        <div className="text-[12px]">
          <CellLabel>Stage</CellLabel>
          <span className="font-medium">{signal.lifecycle_stage}</span>
        </div>
        <div className="text-[12px]">
          <CellLabel>Publish by</CellLabel>
          <span className="flex items-center gap-1.5 font-medium">
            <CalendarClock
              aria-hidden="true"
              className="text-[var(--muted)]"
              size={13}
            />
            {card.recommended_publish_by_label ?? card.publishing_window.label}
          </span>
        </div>
        <div className="text-[12px]">
          <CellLabel>Fit</CellLabel>
          <span className="font-medium">{card.channel_fit.label}</span>
        </div>
        <div className="text-[12px]">
          <CellLabel>Status</CellLabel>
          <span className="font-medium">{status}</span>
        </div>
        <ArrowRight
          aria-hidden="true"
          className="hidden text-[var(--muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--ink)] xl:block"
          size={16}
        />
      </Link>
    </li>
  );
}
