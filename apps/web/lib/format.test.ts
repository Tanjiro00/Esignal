import { describe, expect, it } from "vitest";

import {
  compactNumber,
  relativeTime,
  scoreTone,
  titleCase,
} from "@/lib/format";

describe("format helpers", () => {
  it("keeps dashboard values compact", () => {
    expect(compactNumber(214_000)).toBe("214K");
  });

  it("maps score ranges to stable semantic tones", () => {
    expect(scoreTone(86)).toBe("strong");
    expect(scoreTone(61)).toBe("watch");
    expect(scoreTone(41)).toBe("risk");
  });

  it("formats deterministic component labels", () => {
    expect(titleCase("creator_diversity")).toBe("Creator Diversity");
  });

  it("treats timezone-less API timestamps as UTC", () => {
    expect(
      relativeTime("2026-07-27T09:45:00", new Date("2026-07-27T09:50:00Z")),
    ).toBe("5m ago");
  });
});
