import { ArrowUpRight } from "lucide-react";

import {
  evidenceVideosForGap,
  selectDistinctContentGaps,
  type ContentGapItem,
} from "@/lib/content-gap";
import type { SignalDetail } from "@/lib/types";

function textValue(value: unknown, fallback = "Not stored") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function sentence(value: unknown, fallback?: string) {
  const text = textValue(value, fallback);
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function occupiedSummary(item: ContentGapItem) {
  const pattern = item.gap.occupied_pattern;
  const claim = sentence(pattern.claim?.value);
  const format = textValue(pattern.format?.value);
  const context = textValue(pattern.context?.value);
  return `${claim}. Most often: ${format} in ${context}.`;
}

function evidenceStrength(item: ContentGapItem) {
  const score = item.gap.score_components.evidence_strength;
  return typeof score === "number" ? `${Math.round(score)}/100` : "Not scored";
}

function PrimaryGap({
  item,
  signal,
}: {
  item: ContentGapItem;
  signal: SignalDetail;
}) {
  const angle = item.angle;
  const open = item.gap.open_gap;
  const demand = signal.demand_clusters[0];
  const sources = evidenceVideosForGap(item, signal.evidence_videos);
  const title =
    demand?.label ||
    angle?.unanswered_question ||
    textValue(open.claim, "Stored open audience need");
  const question = angle?.unanswered_question || demand?.summary;
  const effort =
    angle?.effort || textValue(open.production_complexity, "Not estimated");

  return (
    <section
      aria-labelledby="primary-gap-title"
      data-testid="primary-content-gap"
    >
      <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
        Evidence-backed content gap
      </p>
      <div className="mt-2 grid gap-4 border-b border-[var(--line-strong)] pb-4 lg:grid-cols-[minmax(0,1fr)_270px] lg:items-end">
        <div>
          <h2
            className="editorial max-w-[760px] text-[34px] leading-[1.08] sm:text-[40px]"
            id="primary-gap-title"
          >
            {title}
          </h2>
          {question ? (
            <p className="mt-3 max-w-[760px] text-[14px] leading-6 text-[var(--muted)]">
              {question}
            </p>
          ) : null}
          {angle?.insight_statement ? (
            <div
              className="mt-3 border-l-2 border-[var(--lime-strong)] pl-3"
              data-testid="content-gap-insight"
            >
              <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--lime-ink)] uppercase">
                What the evidence adds
              </p>
              <p className="mt-1 text-[12px] leading-5">
                {angle.insight_statement}
              </p>
            </div>
          ) : null}
        </div>
        <div className="border-l-2 border-[var(--lime-strong)] pl-4">
          <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--lime-ink)] uppercase">
            Why it is open
          </p>
          <p className="mt-1.5 text-[12px] leading-5">
            {angle?.differentiation ||
              angle?.why_now ||
              "The stored occupied-content map does not contain this evidence cell."}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-2 border-b border-[var(--line)] lg:grid-cols-4">
        {[
          ["Audience", textValue(open.audience)],
          ["Promise", angle?.audience_promise || textValue(open.claim)],
          ["Required proof", textValue(open.proof_type)],
          ["Production effort", effort],
        ].map(([label, value]) => (
          <div
            className="border-b border-[var(--line)] py-3 nth-[2n]:pl-4 nth-[2n+1]:pr-4 lg:border-r lg:border-b-0 lg:px-4 lg:first:pl-0 lg:last:border-r-0 lg:last:pr-0"
            key={label}
          >
            <dt className="text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
              {label}
            </dt>
            <dd className="mt-1.5 text-[12px] leading-5">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-4 border-b border-[var(--line-strong)] py-4 lg:grid-cols-2">
        <div>
          <p className="text-[12px] font-semibold">What current videos cover</p>
          <p className="mt-1.5 text-[12px] leading-5 text-[var(--muted)]">
            {occupiedSummary(item)}
          </p>
        </div>
        <div>
          <p className="text-[12px] font-semibold">What current videos miss</p>
          <p className="mt-1.5 text-[12px] leading-5 text-[var(--muted)]">
            {sentence(open.claim)}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
            Evidence strength
          </p>
          <p className="mt-1 text-[12px] font-semibold">
            {evidenceStrength(item)} · {item.gap.evidence.length} stored refs
          </p>
        </div>
        {sources.length ? (
          <div className="min-w-0 sm:max-w-[620px]">
            <p className="text-[10px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase sm:text-right">
              Source links
            </p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 sm:justify-end">
              {sources.map((source) => (
                <a
                  className="inline-flex items-start gap-1.5 text-[12px] font-medium hover:underline"
                  href={source.canonical_url}
                  key={source.id}
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="max-w-[220px] truncate">{source.title}</span>
                  <ArrowUpRight
                    aria-hidden="true"
                    className="mt-0.5 shrink-0"
                    size={12}
                  />
                </a>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function CoverageMap({
  item,
  signal,
}: {
  item: ContentGapItem;
  signal: SignalDetail;
}) {
  const open = item.gap.open_gap;
  const demand = signal.demand_clusters[0];
  const steps = [
    {
      label: "Well covered",
      value: occupiedSummary(item),
    },
    {
      label: "Under-covered",
      value: `${sentence(open.proof_type)} in ${textValue(open.context)}.`,
    },
    {
      label: "Unanswered audience demand",
      value:
        demand?.summary ||
        item.angle?.unanswered_question ||
        "No released demand cluster is stored.",
    },
    {
      label: "Recommended open angle",
      value: item.angle?.title || sentence(open.claim),
    },
  ];

  return (
    <section
      aria-labelledby="coverage-map-title"
      className="mt-5"
      data-testid="coverage-map"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="text-[13px] font-semibold" id="coverage-map-title">
          Coverage map
        </h3>
        <p className="text-[12px] text-[var(--muted)]">
          From occupied coverage to the open angle
        </p>
      </div>
      <ol className="mt-3 grid border-t border-[var(--line-strong)] md:grid-cols-4">
        {steps.map((step, index) => (
          <li
            className="border-b border-[var(--line)] py-3 md:border-r md:border-b-0 md:px-3 md:first:pl-0 md:last:border-r-0 md:last:pr-0"
            key={step.label}
          >
            <div className="flex items-center gap-2">
              <span className="mono text-[10px] text-[var(--lime-ink)]">
                0{index + 1}
              </span>
              <p className="text-[11px] font-semibold">{step.label}</p>
            </div>
            <p className="mt-1.5 text-[12px] leading-5 text-[var(--muted)]">
              {step.value}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AlternativeGaps({ items }: { items: ContentGapItem[] }) {
  if (!items.length) return null;
  return (
    <section className="mt-6" aria-labelledby="alternative-gaps-title">
      <div className="border-b border-[var(--line-strong)] pb-3">
        <h3 className="text-[13px] font-semibold" id="alternative-gaps-title">
          Two distinct alternatives
        </h3>
        <p className="mt-1 text-[12px] text-[var(--muted)]">
          Lower-ranked directions with a different claim or proof requirement.
        </p>
      </div>
      <div className="grid gap-x-8 md:grid-cols-2">
        {items.map((item) => {
          const angle = item.angle;
          const open = item.gap.open_gap;
          return (
            <article
              className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 border-b border-[var(--line)] py-4"
              data-testid="alternative-gap"
              key={item.gap.gap_key}
            >
              <span className="mono text-[10px] text-[var(--lime-ink)]">
                0{item.gap.rank}
              </span>
              <div>
                <h4 className="text-[13px] leading-5 font-semibold">
                  {angle?.title || sentence(open.claim)}
                </h4>
                <span className="mt-2 inline-flex border border-[var(--line-strong)] px-2 py-1 text-[10px] font-semibold tracking-[0.06em] text-[var(--muted)] uppercase">
                  {angle?.release_ready
                    ? "Evidence-backed"
                    : "Hypothesis · not released"}
                </span>
                <p className="mt-2 text-[12px] leading-5 text-[var(--muted)]">
                  {angle?.differentiation || sentence(open.claim)}
                </p>
                <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[12px]">
                  <div>
                    <dt className="text-[var(--muted)]">Required proof</dt>
                    <dd className="mt-1 font-semibold">
                      {textValue(open.proof_type)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[var(--muted)]">Effort</dt>
                    <dd className="mt-1 font-semibold">
                      {angle?.effort || textValue(open.production_complexity)}
                    </dd>
                  </div>
                </dl>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function OpportunityContentGap({ signal }: { signal: SignalDetail }) {
  const items = selectDistinctContentGaps(
    signal.content_gap_map?.gaps ?? [],
    signal.content_angles,
  );
  const primary = items.find((item) => item.angle?.release_ready);

  if (!primary) {
    return (
      <section
        className="max-w-[760px]"
        data-testid="no-released-content-insight"
      >
        <p className="text-[11px] font-semibold tracking-[0.1em] uppercase">
          Trend detected · insight pending
        </p>
        <h2 className="editorial mt-2 text-[32px] leading-tight">
          No non-obvious angle is supported yet
        </h2>
        <p className="mt-3 text-[14px] leading-6 text-[var(--muted)]">
          We can see movement in this topic, but the stored audience,
          performance, and audited evidence do not yet establish an insight
          worth turning into a video recommendation.
        </p>
      </section>
    );
  }
  const alternatives = items.filter((item) => item !== primary);

  return (
    <div>
      <PrimaryGap item={primary} signal={signal} />
      <CoverageMap item={primary} signal={signal} />
      <AlternativeGaps items={alternatives.slice(0, 2)} />
    </div>
  );
}
