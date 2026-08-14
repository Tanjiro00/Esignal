import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { compactNumber } from "@/lib/format";
import type { ResultComparatorModel } from "@/lib/result-comparator";

function differenceCopy(value: number): string {
  if (value === 0) return "the same number of views as";
  return `${Math.abs(value)}% ${value > 0 ? "more" : "fewer"} views than`;
}

export function ResultComparator({
  comparator,
}: {
  comparator: ResultComparatorModel;
}) {
  const DifferenceIcon =
    comparator.upliftPercent === null || comparator.upliftPercent === 0
      ? Minus
      : comparator.upliftPercent > 0
        ? TrendingUp
        : TrendingDown;

  return (
    <section
      aria-label="Comparable performance"
      className="mt-7 border-y border-[var(--line-strong)]"
      data-testid="result-comparator"
    >
      <div className="grid md:grid-cols-[minmax(0,0.72fr)_minmax(0,0.72fr)_minmax(280px,1.4fr)]">
        <div className="border-b border-[var(--line)] py-6 md:border-r md:border-b-0 md:pr-6">
          <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
            {comparator.horizonLabel} views
          </p>
          <p className="editorial mt-3 text-[38px] leading-none sm:text-[44px]">
            {comparator.actualViews === null
              ? "Pending"
              : compactNumber(comparator.actualViews)}
          </p>
          <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">
            Observed performance for this published video.
          </p>
        </div>

        <div className="border-b border-[var(--line)] py-6 md:border-r md:border-b-0 md:px-6">
          <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
            Comparable median
          </p>
          <p className="editorial mt-3 text-[38px] leading-none sm:text-[44px]">
            {comparator.medianViews === null
              ? "Pending"
              : compactNumber(comparator.medianViews)}
          </p>
          <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">
            Median at the same {comparator.horizonLabel} measurement window.
          </p>
        </div>

        <div className="py-6 md:pl-7">
          {comparator.stable && comparator.upliftPercent !== null ? (
            <div data-testid="stable-comparator">
              <p className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-[var(--lime-ink)] uppercase">
                <DifferenceIcon size={14} strokeWidth={1.6} />
                Stable comparator
              </p>
              <p
                className={`editorial mt-3 text-[38px] leading-none sm:text-[44px] ${
                  comparator.upliftPercent >= 0
                    ? "text-[var(--lime-ink)]"
                    : "text-[var(--coral)]"
                }`}
                data-testid="associated-difference"
              >
                {comparator.upliftPercent > 0 ? "+" : ""}
                {comparator.upliftPercent}% associated difference
              </p>
              <p className="mt-3 max-w-[500px] text-[11px] leading-5 text-[var(--muted)]">
                This video reached {differenceCopy(comparator.upliftPercent)}{" "}
                the comparable median. Association does not prove causation.
              </p>
            </div>
          ) : (
            <div data-testid="early-comparator">
              <p className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-[var(--muted)] uppercase">
                <DifferenceIcon size={14} strokeWidth={1.6} />
                Early result
              </p>
              <p className="editorial mt-3 max-w-[520px] text-[28px] leading-tight">
                Not enough comparable videos for a stable uplift estimate
              </p>
              <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">
                {comparator.sampleSize} available; at least{" "}
                {comparator.minimumStableSample} are required before showing a
                percentage.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="grid border-t border-[var(--line-strong)] py-5 md:grid-cols-[160px_1fr] md:items-start">
        <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
          Compared with
        </p>
        <ul className="mt-4 grid gap-3 text-[11px] leading-5 md:mt-0 md:grid-cols-3 md:gap-0">
          {[
            comparator.sampleDescription,
            comparator.periodDescription,
            comparator.matchingDescription,
          ].map((item) => (
            <li
              className="border-l border-[var(--line)] pl-4 first:border-l-0 first:pl-0 md:first:border-l md:first:pl-4"
              key={item}
            >
              {item}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
