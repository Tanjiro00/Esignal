import "@testing-library/jest-dom/vitest";

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DecisionFeedback } from "@/components/signals/decision-feedback";

afterEach(cleanup);

describe("DecisionFeedback", () => {
  it("saves a meaningful tracking condition and optional note", () => {
    const onSubmit = vi.fn();
    render(
      <DecisionFeedback
        busy={false}
        currentAction={null}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Track changes" }));
    expect(screen.getByTestId("decision-feedback")).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "More independent evidence" }),
    );
    fireEvent.change(screen.getByLabelText("Optional note"), {
      target: { value: "Wait for an independent benchmark." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Track changes" }));

    expect(onSubmit).toHaveBeenCalledWith(
      "watch",
      "need_more_evidence",
      "Wait for an independent benchmark.",
      undefined,
    );
    expect(screen.queryByTestId("decision-feedback")).not.toBeInTheDocument();
  });

  it("confirms production time and target date before creating a video plan", () => {
    const onSubmit = vi.fn();
    render(
      <DecisionFeedback
        busy={false}
        onSubmit={onSubmit}
        productionDaysMax={6}
        productionDaysMin={3}
        recommendedPublishBy="2026-08-03T12:00:00Z"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Create video plan" }));
    fireEvent.change(screen.getByLabelText(/Production time/), {
      target: { value: "4" },
    });
    fireEvent.change(screen.getByLabelText(/Target publish date/), {
      target: { value: "2026-08-02" },
    });
    fireEvent.click(
      within(screen.getByTestId("decision-feedback")).getByRole("button", {
        name: "Create video plan",
      }),
    );

    expect(onSubmit).toHaveBeenCalledWith(
      "act",
      undefined,
      undefined,
      expect.objectContaining({
        production_days: 4,
        target_publish_date: expect.stringContaining("2026-08-02"),
      }),
    );
  });

  it("keeps every compact mobile action visibly named", () => {
    render(<DecisionFeedback busy={false} compact onSubmit={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: "Create video plan" }),
    ).toHaveTextContent("Video plan");
    expect(
      screen.getByRole("button", { name: "Track changes" }),
    ).toHaveTextContent("Track");
    expect(
      screen.getByRole("button", { name: "Dismiss idea" }),
    ).toHaveTextContent("Dismiss");
  });

  it("does not offer a video plan for an unreleased research candidate", () => {
    render(
      <DecisionFeedback allowAct={false} busy={false} onSubmit={vi.fn()} />,
    );

    expect(
      screen.queryByRole("button", { name: "Create video plan" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Track changes" })).toBeVisible();
    expect(screen.getByText(/still a research candidate/i)).toBeVisible();
  });
});
