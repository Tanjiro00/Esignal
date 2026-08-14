import { Clock3 } from "lucide-react";

import type { SignalEarlyness } from "@/lib/types";

const LEGACY_STAGES = [
  "Seed",
  "Emerging",
  "Breakout",
  "Mass Market",
  "Saturated",
];

export function formatLifecycleDate(value: string | null, pending: boolean) {
  if (!value) return pending ? "Not yet" : "Not observed";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

function LegacyLifecycleRail({ currentStage }: { currentStage: string }) {
  return (
    <div className="relative mt-7 grid grid-cols-5 gap-2">
      <span className="absolute top-1.5 right-[8%] left-[8%] h-px bg-[var(--line-strong)]" />
      {LEGACY_STAGES.map((stage) => {
        const current = stage === currentStage;
        return (
          <div className="relative z-10 min-w-0 text-center" key={stage}>
            <span
              className={`mx-auto block h-3 w-3 rounded-full border bg-white ${
                current
                  ? "border-2 border-[var(--lime-strong)]"
                  : "border-[var(--faint)]"
              }`}
            />
            <span className="mt-2 block text-[11px] text-[var(--muted)]">
              {stage}
            </span>
            <span className="mt-1 block text-[8px] text-[var(--faint)]">
              {current ? "Current" : "History pending"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function EarlynessTimeline({
  earlyness,
  currentStage,
}: {
  earlyness: SignalEarlyness | null;
  currentStage: string;
}) {
  if (!earlyness) {
    return (
      <div data-testid="lifecycle-history-disabled">
        <LegacyLifecycleRail currentStage={currentStage} />
        <p className="mt-5 text-[11px] leading-relaxed text-[var(--muted)]">
          Historical transition dates are hidden until the verified lifecycle
          backfill is enabled.
        </p>
      </div>
    );
  }

  const claimTone =
    earlyness.claim_kind === "early"
      ? "border-[var(--lime-strong)] bg-[#f8fce9]"
      : earlyness.claim_kind === "late"
        ? "border-[var(--coral)] bg-[#fff7f3]"
        : "border-[var(--line-strong)] bg-[var(--surface-subtle)]";

  return (
    <div className="mt-5" data-testid="earlyness-timeline">
      <div className={`border-l-2 px-4 py-3 ${claimTone}`}>
        <p className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.1em] uppercase">
          <Clock3 aria-hidden="true" size={13} />
          Earlyness
        </p>
        <p className="mt-2 text-[14px] font-semibold">{earlyness.headline}</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--muted)]">
          {earlyness.supporting_text}
        </p>
      </div>

      <details className="group mt-4 border-t border-[var(--line)] pt-3">
        <summary className="cursor-pointer list-none text-[10px] font-semibold underline decoration-[var(--faint)] underline-offset-4">
          View lifecycle evidence
        </summary>
        <div className="relative mt-6 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-4">
          <span className="absolute top-1.5 right-[6%] left-[6%] hidden h-px bg-[var(--line-strong)] sm:block" />
          {earlyness.milestones.map((milestone) => {
            const pending = milestone.status === "pending";
            const reached =
              milestone.status === "reached" || milestone.status === "current";
            return (
              <div className="relative z-10 min-w-0" key={milestone.key}>
                <span
                  className={`block h-3 w-3 rounded-full border bg-white ${
                    milestone.status === "current"
                      ? "border-2 border-[var(--lime-strong)]"
                      : reached
                        ? "border-[var(--ink)]"
                        : "border-[var(--faint)]"
                  }`}
                />
                <p className="mt-2 text-[11px] font-medium">
                  {milestone.label}
                </p>
                <p className="mt-1 text-[8px] text-[var(--muted)]">
                  {formatLifecycleDate(milestone.occurred_at, pending)}
                </p>
                {milestone.evidence_id ? (
                  <p className="mt-1 text-[7px] tracking-[0.05em] text-[var(--faint)] uppercase">
                    Stored evidence
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
        <p className="mt-5 text-[8px] leading-relaxed text-[var(--muted)]">
          Large-channel entry means the first stored topic measurement with a
          participating channel at or above{" "}
          {earlyness.large_channel_threshold_subscribers.toLocaleString(
            "en-US",
          )}{" "}
          subscribers. Missing events are not estimated.
        </p>
      </details>
    </div>
  );
}
