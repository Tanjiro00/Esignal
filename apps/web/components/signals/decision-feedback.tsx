"use client";

import { Check, Eye, FilePlus2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui";

export type DecisionAction = "act" | "watch" | "skip";
export type DecisionPlan = {
  production_days?: number;
  target_publish_date?: string;
};

const REASONS: Record<DecisionAction, Array<[string, string]>> = {
  act: [
    ["strong_fit", "Strong channel fit"],
    ["great_timing", "Timing is right"],
    ["clear_angle", "Clear open angle"],
    ["already_planned", "Already planned"],
  ],
  watch: [
    ["need_more_evidence", "More independent evidence"],
    ["larger_channels_enter", "Larger channels enter"],
    ["clearer_demand", "Audience demand gets clearer"],
    ["waiting_for_product_release", "The product releases"],
    ["production_capacity", "Production capacity opens"],
  ],
  skip: [
    ["not_relevant", "Not relevant"],
    ["too_late", "Too late"],
    ["weak_evidence", "Evidence is too weak"],
    ["brand_mismatch", "Brand mismatch"],
    ["already_covered", "Already covered"],
    ["production_too_expensive", "Too expensive"],
  ],
};

const LABELS: Record<DecisionAction, string> = {
  act: "Create video plan",
  watch: "Track changes",
  skip: "Dismiss idea",
};

export function DecisionFeedback({
  busy,
  currentAction,
  onSubmit,
  allowAct = true,
  compact = false,
  productionDaysMin = 2,
  productionDaysMax = 5,
  recommendedPublishBy,
}: {
  busy: boolean;
  currentAction?: string | null;
  onSubmit: (
    action: DecisionAction,
    reason?: string,
    comment?: string,
    plan?: DecisionPlan,
  ) => void;
  allowAct?: boolean;
  compact?: boolean;
  productionDaysMin?: number;
  productionDaysMax?: number;
  recommendedPublishBy?: string;
}) {
  const [selected, setSelected] = useState<DecisionAction | null>(null);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [productionDays, setProductionDays] = useState(productionDaysMin);
  const defaultDate = useMemo(() => {
    if (recommendedPublishBy) return recommendedPublishBy.slice(0, 10);
    const target = new Date();
    target.setDate(target.getDate() + productionDaysMax);
    return target.toISOString().slice(0, 10);
  }, [productionDaysMax, recommendedPublishBy]);
  const [targetDate, setTargetDate] = useState(defaultDate);

  function close() {
    setSelected(null);
    setReason("");
    setComment("");
  }

  function submit() {
    if (!selected) return;
    onSubmit(
      selected,
      reason || undefined,
      comment || undefined,
      selected === "act"
        ? {
            production_days: productionDays,
            target_publish_date: targetDate
              ? new Date(`${targetDate}T12:00:00Z`).toISOString()
              : undefined,
          }
        : undefined,
    );
    close();
  }

  return (
    <>
      <div
        className={
          compact
            ? allowAct
              ? "grid grid-cols-[1fr_auto_auto] gap-2"
              : "grid grid-cols-2 gap-2"
            : "grid gap-2"
        }
        data-testid="decision-actions"
      >
        {allowAct ? (
          <Button
            aria-label="Create video plan"
            className="min-h-12"
            disabled={busy}
            onClick={() => setSelected("act")}
            variant="primary"
          >
            <FilePlus2 size={15} />{" "}
            {compact ? "Video plan" : "Create video plan"}
          </Button>
        ) : null}
        <div className={compact ? "contents" : "grid grid-cols-2 gap-2"}>
          <Button
            aria-label="Track changes"
            className="min-h-11"
            disabled={busy}
            onClick={() => setSelected("watch")}
          >
            {currentAction === "watch" ? (
              <Check size={14} />
            ) : (
              <Eye size={14} />
            )}
            <span>{compact ? "Track" : "Track changes"}</span>
          </Button>
          <Button
            aria-label="Dismiss idea"
            className="min-h-11"
            disabled={busy}
            onClick={() => setSelected("skip")}
          >
            <span>Dismiss</span>
            {compact ? <X size={14} /> : null}
          </Button>
        </div>
        {!compact ? (
          <p className="mt-1 text-[10px] leading-5 text-[var(--muted)]">
            {allowAct
              ? "Make it now, save it while the evidence develops, or remove it from your active library."
              : "This is still a research candidate. Track new evidence or remove it from your library."}
          </p>
        ) : null}
      </div>

      {selected ? (
        <div
          aria-label={`${LABELS[selected]} opportunity`}
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/30 p-4 backdrop-blur-sm"
          data-testid="decision-feedback"
          role="dialog"
        >
          <div className="motion-dialog w-full max-w-[540px] rounded-2xl border border-[var(--line-strong)] bg-white p-5 shadow-2xl sm:p-7">
            <div className="flex items-start justify-between gap-5">
              <div>
                <p className="text-[10px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
                  {selected === "act"
                    ? "Next step · plan the video"
                    : selected === "watch"
                      ? "Save in Tracking"
                      : "Remove from the active library"}
                </p>
                <h2 className="editorial mt-2 text-[30px]">
                  {selected === "act"
                    ? "Create a video plan"
                    : selected === "watch"
                      ? "What are you waiting for?"
                      : "Why should we dismiss this idea?"}
                </h2>
              </div>
              <button
                aria-label="Close decision dialog"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[var(--line)] transition-[transform,background-color] duration-200 hover:rotate-3 hover:bg-[var(--surface-subtle)]"
                onClick={close}
                type="button"
              >
                <X size={16} />
              </button>
            </div>

            {selected === "act" ? (
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <label className="text-[12px] font-medium">
                  Production time
                  <span className="mt-1 block text-[10px] font-normal text-[var(--muted)]">
                    Recommended {productionDaysMin}–{productionDaysMax} days
                  </span>
                  <input
                    className="mt-2 h-11 w-full rounded-xl border border-[var(--line-strong)] px-3"
                    max={60}
                    min={1}
                    onChange={(event) =>
                      setProductionDays(Number(event.target.value))
                    }
                    type="number"
                    value={productionDays}
                  />
                </label>
                <label className="text-[12px] font-medium">
                  Target publish date
                  <span className="mt-1 block text-[10px] font-normal text-[var(--muted)]">
                    Keep it inside the opportunity window
                  </span>
                  <input
                    className="mt-2 h-11 w-full rounded-xl border border-[var(--line-strong)] px-3"
                    onChange={(event) => setTargetDate(event.target.value)}
                    type="date"
                    value={targetDate}
                  />
                </label>
              </div>
            ) : (
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {REASONS[selected].map(([value, label]) => (
                  <button
                    aria-pressed={reason === value}
                    className={`min-h-11 rounded-xl border px-3 text-left text-[11px] font-medium transition-[background-color,border-color,box-shadow] duration-200 ${
                      reason === value
                        ? "border-[var(--lime-strong)] bg-[var(--lime-soft)]"
                        : "border-[var(--line-strong)] bg-white hover:border-[var(--ink)] hover:shadow-sm"
                    }`}
                    key={value}
                    onClick={() => setReason(value)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            <label className="mt-5 block text-[11px] text-[var(--muted)]">
              Optional note
              <textarea
                className="mt-2 min-h-20 w-full resize-y rounded-xl border border-[var(--line-strong)] bg-white p-3 text-[12px] text-[var(--ink)] outline-none focus:border-[var(--ink)]"
                maxLength={300}
                onChange={(event) => setComment(event.target.value)}
                placeholder={
                  selected === "act"
                    ? "Producer, proof or access notes"
                    : "Add context for the team"
                }
                value={comment}
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <Button onClick={close}>Cancel</Button>
              <Button
                disabled={busy || (selected !== "act" && !reason)}
                onClick={submit}
                variant="primary"
              >
                {selected === "act"
                  ? "Create video plan"
                  : `Save ${LABELS[selected]}`}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
