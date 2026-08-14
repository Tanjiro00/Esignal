import { describe, expect, it } from "vitest";

import {
  DEFAULT_MINIMUM_STABLE_SAMPLE,
  resultComparator,
} from "@/lib/result-comparator";
import type { OutcomePerformance } from "@/lib/types";

const stablePerformance: OutcomePerformance = {
  views_24h: 284_000,
  baseline_views_24h: 142_000,
  channel_relative_uplift_24h: 2,
  comparator: {
    sample_size: 8,
    sample_size_24h: 8,
    minimum_stable_sample_size: 5,
    stability_24h: "stable",
    views_24h: 142_000,
    filters: {
      content_type: "long",
      duration_ratio: "0.6–1.6x",
      topic_family: "title-token similarity ranked",
      upload_period_days: 180,
    },
  },
};

describe("result comparator", () => {
  it("exposes a stable 24h comparator and its methodology", () => {
    const comparator = resultComparator(stablePerformance);

    expect(comparator.horizonLabel).toBe("24h");
    expect(comparator.actualViews).toBe(284_000);
    expect(comparator.medianViews).toBe(142_000);
    expect(comparator.upliftPercent).toBe(100);
    expect(comparator.stable).toBe(true);
    expect(comparator.sampleDescription).toBe("8 similar long-form videos");
    expect(comparator.periodDescription).toBe(
      "Published during the last 6 months",
    );
    expect(comparator.matchingDescription).toBe(
      "Similar duration and topic family",
    );
  });

  it("suppresses the percentage when the horizon sample is too small", () => {
    const comparator = resultComparator({
      ...stablePerformance,
      comparator: {
        ...stablePerformance.comparator,
        sample_size: 3,
        sample_size_24h: 3,
        stability_24h: "early",
      },
    });

    expect(comparator.stable).toBe(false);
    expect(comparator.upliftPercent).toBeNull();
    expect(comparator.actualViews).toBe(284_000);
    expect(comparator.medianViews).toBe(142_000);
    expect(comparator.minimumStableSample).toBe(5);
  });

  it("fails closed for legacy ratios without a stored sample", () => {
    const comparator = resultComparator({
      views_48h: 200_000,
      baseline_views_48h: 100_000,
      performance_ratio: 2,
    });

    expect(comparator.horizonLabel).toBe("48h");
    expect(comparator.sampleSize).toBe(0);
    expect(comparator.minimumStableSample).toBe(DEFAULT_MINIMUM_STABLE_SAMPLE);
    expect(comparator.stable).toBe(false);
    expect(comparator.upliftPercent).toBeNull();
  });
});
