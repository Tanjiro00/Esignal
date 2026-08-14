import { describe, expect, it } from "vitest";

import {
  EMPTY_TODAY_REFETCH_INTERVAL_MS,
  todayRefetchInterval,
} from "./today-refresh";

describe("todayRefetchInterval", () => {
  it("keeps checking while the first signal set is still empty", () => {
    expect(todayRefetchInterval({ feed: { total: 0 } })).toBe(
      EMPTY_TODAY_REFETCH_INTERVAL_MS,
    );
  });

  it("stops polling after signals become available", () => {
    expect(todayRefetchInterval({ feed: { total: 1 } })).toBe(false);
  });

  it("does not poll before the initial request resolves", () => {
    expect(todayRefetchInterval(undefined)).toBe(false);
  });
});
