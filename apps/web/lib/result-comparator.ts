import type { OutcomeComparator, OutcomePerformance } from "@/lib/types";

export const DEFAULT_MINIMUM_STABLE_SAMPLE = 5;

type HorizonDefinition = {
  key: "24h" | "48h" | "72h" | "7d" | "30d";
  label: string;
  actualKeys: string[];
  baselineKeys: string[];
};

const HORIZONS: HorizonDefinition[] = [
  {
    key: "24h",
    label: "24h",
    actualKeys: ["views_24h"],
    baselineKeys: ["baseline_views_24h"],
  },
  {
    key: "48h",
    label: "48h",
    actualKeys: ["views_48h"],
    baselineKeys: ["baseline_views_48h"],
  },
  {
    key: "72h",
    label: "72h",
    actualKeys: ["views_72h"],
    baselineKeys: ["baseline_views_72h"],
  },
  {
    key: "7d",
    label: "7d",
    actualKeys: ["views_7d", "views_168h"],
    baselineKeys: ["baseline_views_7d", "baseline_views_168h"],
  },
  {
    key: "30d",
    label: "30d",
    actualKeys: ["views_30d"],
    baselineKeys: ["baseline_views_30d"],
  },
];

function finiteNumber(
  source: Record<string, unknown> | undefined,
  ...keys: string[]
): number | null {
  if (!source) return null;
  for (const key of keys) {
    const value = Number(source[key]);
    if (Number.isFinite(value) && value >= 0) return value;
  }
  return null;
}

function comparatorRecord(
  performance: OutcomePerformance,
): OutcomeComparator | undefined {
  const comparator = performance.comparator;
  return comparator &&
    typeof comparator === "object" &&
    !Array.isArray(comparator)
    ? comparator
    : undefined;
}

function contentTypeDescription(contentType: string | undefined): string {
  if (contentType === "short") return "similar Shorts";
  if (contentType === "live") return "similar live streams";
  if (contentType === "long") return "similar long-form videos";
  return "comparable channel videos";
}

function periodDescription(days: number | undefined): string {
  if (!days) return "Published before this video";
  if (days === 180) return "Published during the last 6 months";
  if (days === 365) return "Published during the last 12 months";
  return `Published during the previous ${days} days`;
}

export type ResultComparatorModel = {
  horizonKey: HorizonDefinition["key"];
  horizonLabel: string;
  actualViews: number | null;
  medianViews: number | null;
  sampleSize: number;
  minimumStableSample: number;
  stable: boolean;
  upliftPercent: number | null;
  sampleDescription: string;
  periodDescription: string;
  matchingDescription: string;
};

export function resultComparator(
  performance: OutcomePerformance,
): ResultComparatorModel {
  const comparator = comparatorRecord(performance);
  const horizon =
    HORIZONS.find((candidate) => {
      const actual = finiteNumber(performance, ...candidate.actualKeys);
      const baseline =
        finiteNumber(performance, ...candidate.baselineKeys) ??
        finiteNumber(comparator, `views_${candidate.key}`);
      return actual !== null || baseline !== null;
    }) ?? HORIZONS[0];

  const actualViews = finiteNumber(performance, ...horizon.actualKeys);
  const medianViews =
    finiteNumber(performance, ...horizon.baselineKeys) ??
    finiteNumber(comparator, `views_${horizon.key}`);
  const sampleSize =
    finiteNumber(comparator, `sample_size_${horizon.key}`, "sample_size") ?? 0;
  const minimumStableSample =
    finiteNumber(comparator, "minimum_stable_sample_size") ??
    DEFAULT_MINIMUM_STABLE_SAMPLE;
  const declaredStability = comparator?.[`stability_${horizon.key}`];
  const stable =
    actualViews !== null &&
    medianViews !== null &&
    medianViews > 0 &&
    sampleSize >= minimumStableSample &&
    declaredStability !== "early";
  const upliftPercent = stable
    ? Math.round((actualViews / medianViews - 1) * 100)
    : null;
  const filters = comparator?.filters;

  return {
    horizonKey: horizon.key,
    horizonLabel: horizon.label,
    actualViews,
    medianViews,
    sampleSize,
    minimumStableSample,
    stable,
    upliftPercent,
    sampleDescription: `${sampleSize} ${contentTypeDescription(filters?.content_type)}`,
    periodDescription: periodDescription(filters?.upload_period_days),
    matchingDescription:
      filters?.duration_ratio && filters?.topic_family
        ? "Similar duration and topic family"
        : filters?.duration_ratio
          ? "Similar duration and content type"
          : "Ranked by format and topic proximity",
  };
}

export function outcomeMetric(
  performance: OutcomePerformance,
  ...keys: string[]
): number | null {
  return finiteNumber(performance, ...keys);
}
