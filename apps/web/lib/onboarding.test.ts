import { afterEach, describe, expect, it, vi } from "vitest";

import { finishOnboarding } from "@/lib/api";

function jsonResponse(body: object) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("finishOnboarding", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("accepts an authoritative completed state after a lost response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: "in_progress" }))
      .mockRejectedValueOnce(new TypeError("connection lost"))
      .mockResolvedValueOnce(jsonResponse({ status: "completed" }));
    vi.stubGlobal("fetch", fetchMock);

    const status = await finishOnboarding("workspace-1");

    expect(status.status).toBe("completed");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("keeps a real final-step failure visible when setup is incomplete", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: "in_progress" }))
      .mockRejectedValueOnce(new TypeError("connection lost"))
      .mockResolvedValueOnce(jsonResponse({ status: "in_progress" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(finishOnboarding("workspace-1")).rejects.toThrow(
      "connection lost",
    );
  });
});
