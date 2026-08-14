import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OnboardingPage from "./page";

const apiMocks = vi.hoisted(() => ({
  autoSetupOnboarding: vi.fn(),
  getDemoContext: vi.fn(),
  getOnboardingStatus: vi.fn(),
  trackProductEvent: vi.fn(),
}));

vi.mock("@/lib/api", () => apiMocks);

const context = {
  workspace_id: "workspace-stephen",
  workspace_name: "Stephen Samuelsen",
  owned_channel_id: "channel-stephen",
  owned_channel_name: "Stephen Samuelsen",
  user_id: "user-1",
  user_name: "Creator",
  user_email: "creator@example.com",
  role: "owner",
  is_admin: false,
  onboarding_status: "completed",
  demo: false,
  features: {},
  fresh_at: "2026-07-30T18:00:00Z",
};

const onboarding = {
  workspace_id: "workspace-stephen",
  status: "completed",
  current_step: 3,
  completed_steps: [1, 2, 3],
  completed_at: "2026-07-30T18:00:00Z",
  owned_channel: {
    id: "channel-stephen",
    title: "Stephen Samuelsen",
    youtube_channel_id: "UClTPTPse8np7oK5CPfjk7tA",
    canonical_url: "https://www.youtube.com/@StephenSamuelsen",
  },
  active_query_count: 20,
  reference_channel_count: 5,
};

describe("zero-configuration onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getDemoContext.mockResolvedValue(context);
    apiMocks.getOnboardingStatus.mockResolvedValue(onboarding);
    apiMocks.trackProductEvent.mockResolvedValue(undefined);
  });

  it("reconciles a stale workspace context after onboarding completes", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(["workspace-context"], {
      ...context,
      onboarding_status: "in_progress",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <OnboardingPage />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("link", { name: "Open Today" }),
    ).toHaveAttribute("href", "/today");
    await waitFor(() =>
      expect(
        queryClient.getQueryData<{ onboarding_status: string }>([
          "workspace-context",
        ])?.onboarding_status,
      ).toBe("completed"),
    );
  });
});
