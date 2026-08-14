"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Clock3,
  GitMerge,
  GitPullRequest,
  MessageSquareText,
  PencilLine,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { EarlynessTimeline } from "@/components/signals/earlyness-timeline";
import { Button, ErrorState, PageLoading, StatusDot } from "@/components/ui";
import {
  getDemoContext,
  getSignalReview,
  getSignalReviewQueue,
  overrideCommentRelevance,
  reclassifyCommentDemand,
  reviewSignal,
} from "@/lib/api";
import { compactNumber, relativeTime } from "@/lib/format";
import type {
  SignalReviewAction,
  SignalReviewDetail,
  SignalReviewReason,
} from "@/lib/types";

const REASONS: Array<{ value: SignalReviewReason; label: string }> = [
  { value: "false_topic_merge", label: "False topic merge" },
  { value: "too_broad", label: "Too broad" },
  { value: "too_narrow", label: "Too narrow" },
  { value: "late_signal", label: "Late signal" },
  { value: "single_channel_dependency", label: "Single-channel dependency" },
  { value: "single_video_dependency", label: "Single-video dependency" },
  { value: "weak_outlier", label: "Weak outlier evidence" },
  { value: "weak_demand", label: "Weak demand" },
  { value: "irrelevant_comments", label: "Irrelevant comments" },
  { value: "low_channel_fit", label: "Low channel fit" },
  { value: "saturated", label: "Saturated" },
  { value: "insufficient_evidence", label: "Insufficient evidence" },
  { value: "duplicate_signal", label: "Duplicate signal" },
  { value: "other", label: "Other" },
];

function statusTone(
  status: string,
): "healthy" | "warning" | "risk" | "neutral" {
  if (status === "approved" || status === "published") return "healthy";
  if (status === "rejected" || status === "expired") return "risk";
  if (status === "needs_review" || status === "needs_changes") return "warning";
  return "neutral";
}

function ReviewMetrics({
  queue,
}: {
  queue: Awaited<ReturnType<typeof getSignalReviewQueue>>;
}) {
  const cards = [
    {
      label: "Needs review",
      value: queue.metrics.status_counts.needs_review ?? 0,
      detail: `${queue.metrics.total} total candidates`,
    },
    {
      label: "Approval rate",
      value: `${queue.metrics.approval_rate}%`,
      detail: "Approved vs decided",
    },
    {
      label: "Average review",
      value:
        queue.metrics.average_review_time_hours === null
          ? "Pending"
          : `${queue.metrics.average_review_time_hours}h`,
      detail: "Submitted → decision",
    },
    {
      label: "Rejected",
      value: queue.metrics.status_counts.rejected ?? 0,
      detail: `${Object.keys(queue.metrics.rejection_reasons).length} reason types`,
    },
  ];
  return (
    <div className="mb-6 grid border border-[var(--line)] bg-white sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <div
          className="border-b border-[var(--line)] p-4 last:border-b-0 sm:border-r sm:last:border-r-0 xl:border-b-0"
          key={card.label}
        >
          <p className="text-[11px] text-[var(--muted)]">{card.label}</p>
          <p className="editorial mt-2 text-[28px]">{card.value}</p>
          <p className="mt-1 text-[8px] text-[var(--faint)]">{card.detail}</p>
        </div>
      ))}
    </div>
  );
}

function ReviewWorkspace({
  detail,
  pending,
  onAction,
  onRelevanceOverride,
  onReplayRelevance,
  relevancePending,
}: {
  detail: SignalReviewDetail;
  pending: boolean;
  onAction: (
    action: SignalReviewAction,
    options?: {
      reasons?: SignalReviewReason[];
      note?: string;
      thesis?: string;
      opportunity?: Record<string, unknown>;
      evidenceVideoIds?: string[];
      mergeTargetSignalId?: string;
    },
  ) => void;
  onRelevanceOverride: (relevanceId: string, decision: boolean | null) => void;
  onReplayRelevance: () => void;
  relevancePending: boolean;
}) {
  const { review, signal } = detail;
  const [reason, setReason] = useState<SignalReviewReason>(
    (review.primary_reason as SignalReviewReason | null) ??
      "insufficient_evidence",
  );
  const [note, setNote] = useState(review.reason_codes.join(", "));
  const [thesis, setThesis] = useState(detail.thesis_override ?? signal.thesis);
  const [opportunityTitle, setOpportunityTitle] = useState(
    signal.content_angles[0]?.title ?? "",
  );
  const [mergeTarget, setMergeTarget] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>(
    detail.evidence_selection.length
      ? detail.evidence_selection
      : signal.evidence_videos.map((video) => video.id),
  );

  return (
    <div className="min-w-0">
      <section className="border border-[var(--line)] bg-white">
        <div className="flex flex-col gap-4 border-b border-[var(--line)] p-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 border border-[var(--line)] px-2 py-1 text-[8px] font-semibold tracking-[0.08em] uppercase">
                <StatusDot tone={statusTone(review.status)} />
                {review.status.replaceAll("_", " ")}
              </span>
              <span className="text-[11px] text-[var(--muted)]">
                Submitted {relativeTime(review.submitted_at)}
              </span>
            </div>
            <h2 className="editorial text-[30px] leading-tight">
              {review.topic_label}
            </h2>
            <p className="mt-2 max-w-3xl text-[10px] leading-relaxed text-[var(--muted)]">
              {signal.thesis}
            </p>
          </div>
          <div
            className="flex shrink-0 flex-wrap gap-2"
            data-testid="signal-review-actions"
          >
            <Button
              disabled={pending}
              onClick={() =>
                onAction("approve", {
                  reasons: ["other"],
                  note: note || "Evidence reviewed.",
                })
              }
              variant="primary"
            >
              <Check size={13} /> Approve
            </Button>
            <Button
              disabled={pending}
              onClick={() => onAction("reject", { reasons: [reason], note })}
              variant="danger"
            >
              <X size={13} /> Reject
            </Button>
          </div>
        </div>

        <div className="grid border-b border-[var(--line)] sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["Lifecycle", signal.topic.stage],
            ["Signal score", Math.round(signal.score)],
            ["Channel fit", Math.round(signal.channel_fit)],
            ["Evidence", signal.evidence_videos.length],
            [
              "Transcript coverage",
              `${signal.evidence_quality.transcript_coverage_percent}%`,
            ],
          ].map(([label, value]) => (
            <div
              className="border-b border-[var(--line)] p-4 sm:border-r xl:border-b-0"
              key={label}
            >
              <p className="text-[8px] text-[var(--muted)]">{label}</p>
              <p className="mt-2 text-[16px] font-medium">{value}</p>
            </div>
          ))}
        </div>

        <div className="grid xl:grid-cols-[minmax(0,1fr)_440px]">
          <div className="min-w-0 border-b border-[var(--line)] p-5 xl:border-r xl:border-b-0">
            <h3 className="editorial text-[22px]">Review evidence</h3>
            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-[8px] font-semibold tracking-[0.08em] uppercase">
                  Why this may be false
                </p>
                {detail.false_positive_risks.length ? (
                  <div className="space-y-2">
                    {detail.false_positive_risks.map((risk) => (
                      <div
                        className="border-l-2 border-[var(--coral)] bg-[#fff8f5] px-3 py-2"
                        key={risk.reason_code}
                      >
                        <p className="text-[11px] font-semibold">
                          {risk.reason_code.replaceAll("_", " ")}
                        </p>
                        <p className="mt-1 text-[8px] leading-relaxed text-[var(--muted)]">
                          {risk.explanation}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="border-l-2 border-[var(--lime-strong)] bg-[#f8fce9] px-3 py-2 text-[11px]">
                    No deterministic risk gate is currently triggered.
                  </p>
                )}
              </div>
              <div>
                <p className="mb-2 text-[8px] font-semibold tracking-[0.08em] uppercase">
                  Demand and saturation
                </p>
                <div className="border border-[var(--line)] p-3">
                  <p className="text-[10px] font-medium">
                    {signal.demand_clusters[0]?.label ?? "No confirmed demand"}
                  </p>
                  <p className="mt-2 text-[11px] leading-relaxed text-[var(--muted)]">
                    {signal.demand_clusters[0]?.summary ??
                      "No stored comment cluster meets the current evidence floor."}
                  </p>
                  <p className="mt-3 text-[8px] text-[var(--faint)]">
                    Saturation: {signal.saturation.label} ·{" "}
                    {signal.saturation.large_channel_count} large channels
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-6 border-t border-[var(--line)] pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[8px] font-semibold tracking-[0.08em] uppercase">
                    Comment relevance
                  </p>
                  <p className="mt-1 text-[8px] text-[var(--muted)]">
                    Comment → source video → topic claim. Manual decisions are
                    audited and survive replay.
                  </p>
                </div>
                <Button disabled={relevancePending} onClick={onReplayRelevance}>
                  <RotateCcw size={12} /> Replay relevance
                </Button>
              </div>
              {detail.comment_relevance.length ? (
                <div className="mt-4 space-y-2">
                  {detail.comment_relevance.slice(0, 12).map((item) => (
                    <div
                      className="border border-[var(--line)] p-3"
                      key={item.id}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2 text-[8px]">
                            <span
                              className={`font-semibold ${
                                item.effective_relevant
                                  ? "text-[#477000]"
                                  : "text-[var(--coral)]"
                              }`}
                            >
                              {item.effective_relevant
                                ? "Accepted evidence"
                                : "Rejected evidence"}
                            </span>
                            <span className="text-[var(--muted)]">
                              {item.actionability} actionability ·{" "}
                              {Math.round(item.relevance_score * 100)} relevance
                            </span>
                            {item.override_decision !== null ? (
                              <span className="border border-[var(--line-strong)] px-1.5 py-0.5">
                                Manual override
                              </span>
                            ) : null}
                          </div>
                          <blockquote className="mt-2 text-[10px] leading-relaxed">
                            “{item.comment_text}”
                          </blockquote>
                          <a
                            className="mt-2 block truncate text-[8px] text-[var(--muted)] hover:underline"
                            href={item.video_url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {item.video_title} · {item.channel} ↗
                          </a>
                          <p className="mt-2 text-[8px] text-[var(--faint)]">
                            {item.reason_codes.join(" · ")}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-wrap gap-1.5">
                          <Button
                            disabled={relevancePending}
                            onClick={() => onRelevanceOverride(item.id, true)}
                          >
                            Accept
                          </Button>
                          <Button
                            disabled={relevancePending}
                            onClick={() => onRelevanceOverride(item.id, false)}
                            variant="danger"
                          >
                            Reject
                          </Button>
                          {item.override_decision !== null ? (
                            <Button
                              disabled={relevancePending}
                              onClick={() => onRelevanceOverride(item.id, null)}
                            >
                              Use model
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 border-l-2 border-[var(--line-strong)] pl-3 text-[11px] text-[var(--muted)]">
                  No comment-to-topic relevance records are stored for this
                  candidate yet.
                </p>
              )}
            </div>

            <div className="mt-6">
              <p className="mb-3 text-[8px] font-semibold tracking-[0.08em] uppercase">
                Evidence selection
              </p>
              <div className="space-y-2">
                {signal.evidence_videos.map((video) => (
                  <label
                    className="grid cursor-pointer grid-cols-[20px_minmax(0,1fr)_90px] items-start gap-2 border-b border-[var(--line)] py-2"
                    key={video.id}
                  >
                    <input
                      checked={selectedEvidence.includes(video.id)}
                      className="mt-0.5"
                      onChange={(event) =>
                        setSelectedEvidence((current) =>
                          event.target.checked
                            ? [...current, video.id]
                            : current.filter((id) => id !== video.id),
                        )
                      }
                      type="checkbox"
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-[11px] font-medium">
                        {video.title}
                      </span>
                      <span className="mt-1 block text-[8px] text-[var(--muted)]">
                        {video.channel} · {compactNumber(video.views)} views
                      </span>
                    </span>
                    <span className="text-right text-[8px] text-[var(--muted)]">
                      {video.outlier_ratio.toFixed(1)}× outlier
                    </span>
                  </label>
                ))}
              </div>
              <Button
                className="mt-3"
                disabled={pending || selectedEvidence.length === 0}
                onClick={() =>
                  onAction("edit_evidence_selection", {
                    evidenceVideoIds: selectedEvidence,
                    note: "Reviewer updated the evidence selection.",
                  })
                }
              >
                Save evidence selection
              </Button>
            </div>
          </div>

          <div className="min-w-0 p-5">
            <h3 className="editorial text-[22px]">Lifecycle timeline</h3>
            <EarlynessTimeline
              currentStage={signal.topic.stage}
              earlyness={signal.earlyness}
            />
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-2">
        <div className="border border-[var(--line)] bg-white p-5">
          <div className="flex items-center gap-2">
            <PencilLine size={15} />
            <h3 className="editorial text-[22px]">Editorial overrides</h3>
          </div>
          <label className="mt-5 block text-[8px] font-semibold tracking-[0.08em] uppercase">
            Topic thesis
          </label>
          <textarea
            className="mt-2 min-h-28 w-full border border-[var(--line-strong)] p-3 text-[10px] leading-relaxed outline-none focus:border-[var(--ink)]"
            onChange={(event) => setThesis(event.target.value)}
            value={thesis}
          />
          <Button
            className="mt-2"
            disabled={pending || thesis.trim().length < 12}
            onClick={() =>
              onAction("edit_thesis", {
                thesis,
                note: "Reviewer edited the user-facing thesis.",
              })
            }
          >
            Save thesis
          </Button>

          <label className="mt-6 block text-[8px] font-semibold tracking-[0.08em] uppercase">
            Primary opportunity
          </label>
          <input
            className="mt-2 h-10 w-full border border-[var(--line-strong)] px-3 text-[10px] outline-none focus:border-[var(--ink)]"
            onChange={(event) => setOpportunityTitle(event.target.value)}
            value={opportunityTitle}
          />
          <Button
            className="mt-2"
            disabled={pending || opportunityTitle.trim().length < 3}
            onClick={() =>
              onAction("edit_opportunity", {
                opportunity: { title: opportunityTitle },
                note: "Reviewer edited the primary opportunity.",
              })
            }
          >
            Save opportunity
          </Button>
        </div>

        <div className="border border-[var(--line)] bg-white p-5">
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} />
            <h3 className="editorial text-[22px]">Review actions</h3>
          </div>
          <label className="mt-5 block text-[8px] font-semibold tracking-[0.08em] uppercase">
            Decision reason
          </label>
          <select
            className="mt-2 h-10 w-full border border-[var(--line-strong)] bg-white px-3 text-[10px]"
            onChange={(event) =>
              setReason(event.target.value as SignalReviewReason)
            }
            value={reason}
          >
            {REASONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <textarea
            aria-label="Review note"
            className="mt-3 min-h-20 w-full border border-[var(--line-strong)] p-3 text-[10px] outline-none focus:border-[var(--ink)]"
            onChange={(event) => setNote(event.target.value)}
            placeholder="Evidence-backed review note"
            value={note}
          />
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Button
              disabled={pending}
              onClick={() =>
                onAction("request_split", {
                  reasons: [reason],
                  note,
                })
              }
            >
              <GitPullRequest size={13} /> Request topic split
            </Button>
            <Button
              disabled={pending}
              onClick={() =>
                onAction("mark_late", {
                  reasons: ["late_signal"],
                  note,
                })
              }
            >
              <Clock3 size={13} /> Mark as late
            </Button>
            <Button
              disabled={pending}
              onClick={() =>
                onAction("mark_weak_evidence", {
                  reasons: ["weak_outlier"],
                  note,
                })
              }
            >
              <AlertTriangle size={13} /> Mark weak evidence
            </Button>
            <Button
              disabled={pending}
              onClick={() =>
                onAction("mark_irrelevant_demand", {
                  reasons: ["irrelevant_comments"],
                  note,
                })
              }
            >
              <MessageSquareText size={13} /> Irrelevant demand
            </Button>
          </div>
          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <label className="block text-[8px] font-semibold tracking-[0.08em] uppercase">
              Merge target signal ID
            </label>
            <div className="mt-2 flex gap-2">
              <input
                className="h-10 min-w-0 flex-1 border border-[var(--line-strong)] px-3 text-[11px] outline-none focus:border-[var(--ink)]"
                onChange={(event) => setMergeTarget(event.target.value)}
                placeholder="UUID"
                value={mergeTarget}
              />
              <Button
                disabled={pending || mergeTarget.length !== 36}
                onClick={() =>
                  onAction("request_merge", {
                    reasons: ["false_topic_merge"],
                    note,
                    mergeTargetSignalId: mergeTarget,
                  })
                }
              >
                <GitMerge size={13} /> Request merge
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-2">
        <div className="border border-[var(--line)] bg-white p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck size={15} />
            <h3 className="editorial text-[22px]">Decision card preview</h3>
          </div>
          <div className="mt-4 border-l-2 border-[var(--lime-strong)] bg-[#f8fce9] p-4">
            <p className="text-[11px] font-semibold tracking-[0.08em] uppercase">
              {signal.topic.stage} · {Math.round(signal.score)} signal score
            </p>
            <p className="editorial mt-3 text-[24px] leading-tight">
              {detail.thesis_override ?? signal.thesis}
            </p>
            <p className="mt-3 text-[11px] text-[var(--muted)]">
              {signal.evidence_videos.length} stored videos ·{" "}
              {
                new Set(signal.evidence_videos.map((video) => video.channel))
                  .size
              }{" "}
              independent channels · {signal.opportunity_window.label}
            </p>
          </div>
        </div>

        <div className="border border-[var(--line)] bg-white p-5">
          <h3 className="editorial text-[22px]">Audit history</h3>
          <div className="mt-4 space-y-3">
            {detail.audit_history.map((event) => (
              <div
                className="grid grid-cols-[82px_minmax(0,1fr)] gap-3 border-b border-[var(--line)] pb-3 last:border-b-0"
                key={event.id}
              >
                <p className="text-[8px] text-[var(--faint)]">
                  {relativeTime(event.created_at)}
                </p>
                <div>
                  <p className="text-[11px] font-semibold">
                    {event.event_type.replaceAll("_", " ")}
                  </p>
                  <p className="mt-1 text-[8px] text-[var(--muted)]">
                    {event.reviewer_name ?? "System"} ·{" "}
                    {event.from_status ?? "created"} → {event.to_status}
                  </p>
                  {event.note ? (
                    <p className="mt-1 text-[8px] leading-relaxed">
                      {event.note}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function ReviewPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("needs_review");
  const [source, setSource] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const contextQuery = useQuery({
    queryKey: ["workspace-context"],
    queryFn: getDemoContext,
  });
  const workspaceId = contextQuery.data?.workspace_id;
  const queueQuery = useQuery({
    queryKey: ["signal-review-queue", workspaceId, status, source],
    queryFn: () =>
      getSignalReviewQueue(workspaceId!, {
        status: status || undefined,
        source: source || undefined,
      }),
    enabled: Boolean(workspaceId),
  });
  const queue = queueQuery.data;
  const effectiveSelectedId = useMemo(() => {
    if (
      selectedId &&
      queue?.items.some((item) => item.signal_id === selectedId)
    ) {
      return selectedId;
    }
    return queue?.items[0]?.signal_id ?? null;
  }, [queue, selectedId]);
  const detailQuery = useQuery({
    queryKey: ["signal-review", workspaceId, effectiveSelectedId],
    queryFn: () => getSignalReview(workspaceId!, effectiveSelectedId!),
    enabled: Boolean(workspaceId && effectiveSelectedId),
  });
  const mutation = useMutation({
    mutationFn: ({
      action,
      options,
    }: {
      action: SignalReviewAction;
      options?: {
        reasons?: SignalReviewReason[];
        note?: string;
        thesis?: string;
        opportunity?: Record<string, unknown>;
        evidenceVideoIds?: string[];
        mergeTargetSignalId?: string;
      };
    }) =>
      reviewSignal(workspaceId!, effectiveSelectedId!, {
        action,
        reason_codes: options?.reasons,
        note: options?.note,
        thesis: options?.thesis,
        opportunity: options?.opportunity,
        evidence_video_ids: options?.evidenceVideoIds,
        merge_target_signal_id: options?.mergeTargetSignalId,
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["signal-review-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["signal-review"] }),
        queryClient.invalidateQueries({ queryKey: ["signals"] }),
      ]);
    },
  });
  const relevanceMutation = useMutation({
    mutationFn: ({
      relevanceId,
      decision,
    }: {
      relevanceId: string;
      decision: boolean | null;
    }) =>
      overrideCommentRelevance(workspaceId!, relevanceId, {
        decision,
        reason:
          decision === null
            ? "Reviewer cleared the manual override."
            : decision
              ? "Reviewer confirmed this comment supports the topic."
              : "Reviewer rejected this comment as topic evidence.",
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["signal-review"] }),
        queryClient.invalidateQueries({ queryKey: ["signals"] }),
        queryClient.invalidateQueries({ queryKey: ["demand-intelligence"] }),
      ]);
    },
  });
  const replayMutation = useMutation({
    mutationFn: () =>
      reclassifyCommentDemand(detailQuery.data?.signal.topic.id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["signal-review"] }),
        queryClient.invalidateQueries({ queryKey: ["signals"] }),
        queryClient.invalidateQueries({ queryKey: ["demand-intelligence"] }),
      ]);
    },
  });

  if (contextQuery.isLoading || queueQuery.isLoading) {
    return <PageLoading label="Loading human review queue" />;
  }
  if (contextQuery.error || queueQuery.error) {
    const error = contextQuery.error ?? queueQuery.error;
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : "Review queue unavailable"
        }
        retry={() => queueQuery.refetch()}
      />
    );
  }

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-7 sm:px-6 lg:px-8 lg:py-10">
      <PageHeader
        aside={
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              aria-label="Review status"
              className="h-10 border border-[var(--line-strong)] bg-white px-3 text-[10px]"
              onChange={(event) => setStatus(event.target.value)}
              value={status}
            >
              <option value="">All statuses</option>
              {(queue?.filters.statuses ?? []).map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            <select
              aria-label="Review source"
              className="h-10 border border-[var(--line-strong)] bg-white px-3 text-[10px]"
              onChange={(event) => setSource(event.target.value)}
              value={source}
            >
              <option value="">All sources</option>
              {(queue?.filters.sources ?? []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        }
        description="Approve every user-visible signal and retain an immutable evidence-backed audit trail."
        title="Signal review"
      />

      {queue ? <ReviewMetrics queue={queue} /> : null}

      <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="h-fit border border-[var(--line)] bg-white xl:sticky xl:top-6">
          <div className="border-b border-[var(--line)] px-4 py-3 text-[11px] text-[var(--muted)]">
            {queue?.total ?? 0} matching candidates · no bulk approval
          </div>
          {queue?.items.length ? (
            queue.items.map((item) => (
              <button
                aria-pressed={item.signal_id === effectiveSelectedId}
                className={`w-full border-b border-[var(--line)] p-4 text-left last:border-b-0 ${
                  item.signal_id === effectiveSelectedId
                    ? "border-l-2 border-l-[var(--lime-strong)] bg-[#fbfdf3]"
                    : "hover:bg-[var(--surface-subtle)]"
                }`}
                key={item.id}
                onClick={() => setSelectedId(item.signal_id)}
                type="button"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[8px] font-semibold tracking-[0.06em] uppercase">
                    <StatusDot tone={statusTone(item.status)} />
                    {item.status.replaceAll("_", " ")}
                  </span>
                  <span className="text-[8px] text-[var(--faint)]">
                    {relativeTime(item.submitted_at)}
                  </span>
                </div>
                <p className="mt-3 text-[12px] leading-snug font-semibold">
                  {item.topic_label}
                </p>
                <p className="mt-2 text-[8px] text-[var(--muted)]">
                  {item.lifecycle_stage} · score {Math.round(item.signal_score)}{" "}
                  · fit {Math.round(item.channel_fit)}
                </p>
              </button>
            ))
          ) : (
            <div className="p-8 text-center">
              <ShieldCheck
                className="mx-auto text-[var(--lime-strong)]"
                size={22}
              />
              <p className="mt-3 text-[10px] font-medium">Queue is clear</p>
              <p className="mt-1 text-[8px] text-[var(--muted)]">
                No signals match this filter.
              </p>
            </div>
          )}
        </aside>

        {effectiveSelectedId && detailQuery.isLoading ? (
          <div className="skeleton h-[760px]" />
        ) : detailQuery.error ? (
          <ErrorState
            message={
              detailQuery.error instanceof Error
                ? detailQuery.error.message
                : "Review detail unavailable"
            }
            retry={() => detailQuery.refetch()}
          />
        ) : detailQuery.data ? (
          <ReviewWorkspace
            detail={detailQuery.data}
            key={`${detailQuery.data.review.id}:${detailQuery.data.review.updated_at}`}
            onAction={(action, options) => mutation.mutate({ action, options })}
            onRelevanceOverride={(relevanceId, decision) =>
              relevanceMutation.mutate({ relevanceId, decision })
            }
            onReplayRelevance={() => replayMutation.mutate()}
            pending={mutation.isPending}
            relevancePending={
              relevanceMutation.isPending || replayMutation.isPending
            }
          />
        ) : (
          <div className="grid min-h-80 place-items-center border border-[var(--line)] bg-white">
            <p className="text-[10px] text-[var(--muted)]">
              Select a signal to review its stored evidence.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
