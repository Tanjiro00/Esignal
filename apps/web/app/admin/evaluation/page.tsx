"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Save } from "lucide-react";
import { useMemo, useState } from "react";

import { Button, ErrorState, PageLoading } from "@/components/ui";
import {
  evaluationExportUrl,
  getDemoContext,
  getEvaluationCandidates,
  getEvaluationReport,
  labelEvaluationTopic,
} from "@/lib/api";
import { titleCase } from "@/lib/format";
import type {
  DemoContext,
  EvaluationCandidate,
  EvaluationCandidateList,
  EvaluationReport,
} from "@/lib/types";

type EvaluationData = {
  context: DemoContext;
  candidates: EvaluationCandidateList;
  report: EvaluationReport;
};

function metricLabel(key: string) {
  return titleCase(
    key.replace("reviewed_candidate_universe", "reviewed universe"),
  );
}

export default function EvaluationPage() {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [label, setLabel] = useState("true_early_signal");
  const [additional, setAdditional] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const query = useQuery<EvaluationData>({
    queryKey: ["evaluation"],
    queryFn: async () => {
      const context = await getDemoContext();
      const [candidates, report] = await Promise.all([
        getEvaluationCandidates(context.demo ? "demo" : "live"),
        getEvaluationReport(context.workspace_id),
      ]);
      return { context, candidates, report };
    },
  });
  const selected = useMemo(
    () =>
      query.data?.candidates.items.find(
        (item) => item.topic_id === selectedId,
      ) ?? query.data?.candidates.items[0],
    [query.data, selectedId],
  );

  const mutation = useMutation({
    mutationFn: ({
      candidate,
      nextLabel,
      nextAdditional,
      nextNotes,
    }: {
      candidate: EvaluationCandidate;
      nextLabel: string;
      nextAdditional: string[];
      nextNotes: string;
    }) =>
      labelEvaluationTopic(candidate.topic_id, {
        workspace_id: query.data!.context.workspace_id,
        label: nextLabel,
        additional_labels: nextAdditional,
        notes: nextNotes,
      }),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ["evaluation"],
      }),
  });

  if (query.isLoading)
    return <PageLoading label="Loading evaluation dataset" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data || !selected) return null;
  const { candidates, report } = query.data;
  const hasSelectedDraft = selectedId === selected.topic_id;
  const currentLabel = hasSelectedDraft
    ? label
    : (selected.evaluation?.label ?? "true_early_signal");
  const currentAdditional = hasSelectedDraft
    ? additional
    : (selected.evaluation?.additional_labels ?? []);
  const currentNotes = hasSelectedDraft
    ? notes
    : (selected.evaluation?.notes ?? "");

  function chooseCandidate(candidate: EvaluationCandidate) {
    setSelectedId(candidate.topic_id);
    setLabel(candidate.evaluation?.label ?? "true_early_signal");
    setAdditional(candidate.evaluation?.additional_labels ?? []);
    setNotes(candidate.evaluation?.notes ?? "");
  }

  return (
    <div className="mx-auto max-w-[1380px] px-5 py-7 sm:px-8 sm:py-10">
      <header className="border-b border-[var(--ink)] pb-7">
        <div className="flex items-end justify-between gap-6 max-lg:flex-col max-lg:items-start">
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] text-[var(--lime-ink)] uppercase">
              Point-in-time quality control
            </p>
            <h1 className="editorial mt-3 text-[48px] leading-none sm:text-[62px]">
              Evaluation
            </h1>
            <p className="mt-4 max-w-[680px] text-[13px] leading-6 text-[var(--muted)]">
              Review up to 100 topic candidates per page. Every label freezes
              the evidence and model versions available at review time.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              className="inline-flex min-h-10 items-center gap-2 border border-[var(--line-strong)] bg-white px-3 text-[11px] font-medium"
              href={evaluationExportUrl("labels", "jsonl")}
            >
              <Download size={13} /> Labels JSONL
            </a>
            <a
              className="inline-flex min-h-10 items-center gap-2 border border-[var(--line-strong)] bg-white px-3 text-[11px] font-medium"
              href={evaluationExportUrl("feedback", "csv")}
            >
              <Download size={13} /> Feedback CSV
            </a>
          </div>
        </div>
      </header>

      <section className="grid border-b border-[var(--line-strong)] sm:grid-cols-2 xl:grid-cols-4">
        <div className="border-r border-[var(--line)] py-5 pr-5">
          <p className="text-[10px] tracking-[0.12em] text-[var(--muted)] uppercase">
            Reviewed
          </p>
          <p className="editorial mt-2 text-[34px]">
            {candidates.reviewed}/{candidates.total}
          </p>
        </div>
        {Object.entries(report.metrics)
          .slice(0, 3)
          .map(([key, value]) => (
            <div
              className="border-r border-[var(--line)] px-5 py-5 last:border-r-0"
              key={key}
            >
              <p className="text-[10px] tracking-[0.12em] text-[var(--muted)] uppercase">
                {metricLabel(key)}
              </p>
              <p className="editorial mt-2 text-[34px]">{value}%</p>
            </div>
          ))}
      </section>

      <div className="grid gap-8 py-8 lg:grid-cols-[minmax(330px,.72fr)_minmax(0,1.28fr)]">
        <section>
          <div className="mb-3 flex items-center justify-between text-[11px]">
            <h2 className="font-semibold">Candidate universe</h2>
            <span className="text-[var(--muted)]">
              {candidates.items.length} loaded
            </span>
          </div>
          <div className="max-h-[720px] overflow-y-auto border-y border-[var(--line-strong)]">
            {candidates.items.map((candidate, index) => (
              <button
                className={`flex w-full items-start gap-3 border-b border-[var(--line)] px-3 py-4 text-left last:border-b-0 ${
                  candidate.topic_id === selected.topic_id
                    ? "bg-[var(--surface-subtle)]"
                    : "bg-white hover:bg-[var(--surface-subtle)]"
                }`}
                key={candidate.topic_id}
                onClick={() => chooseCandidate(candidate)}
                type="button"
              >
                <span className="mt-0.5 w-7 shrink-0 text-[10px] text-[var(--muted)]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="min-w-0 flex-1">
                  <strong className="block text-[12px] leading-5">
                    {candidate.topic_label}
                  </strong>
                  <span className="mt-1 block text-[10px] text-[var(--muted)]">
                    {candidate.lifecycle_stage} · {candidate.evidence_videos}{" "}
                    videos
                  </span>
                </span>
                {candidate.reviewed ? (
                  <Check className="mt-0.5 text-[var(--lime-ink)]" size={14} />
                ) : null}
              </button>
            ))}
          </div>
        </section>

        <section
          className="border-t border-[var(--ink)] pt-5"
          data-testid="evaluation-form"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[10px] tracking-[0.12em] text-[var(--muted)] uppercase">
                {selected.source_kind} candidate · specificity{" "}
                {Math.round(selected.specificity_score)}
              </p>
              <h2 className="editorial mt-2 text-[30px] leading-tight">
                {selected.topic_label}
              </h2>
            </div>
            <span className="border border-[var(--line)] px-3 py-2 text-[10px]">
              {selected.signal_score === null
                ? "No visible signal"
                : `Signal ${Math.round(selected.signal_score)}`}
            </span>
          </div>

          <label className="mt-7 block text-[11px]">
            Primary label
            <select
              aria-label="Primary evaluation label"
              className="mt-2 h-11 w-full border border-[var(--line-strong)] bg-white px-3"
              onChange={(event) => {
                setSelectedId(selected.topic_id);
                setLabel(event.target.value);
              }}
              value={currentLabel}
            >
              {candidates.primary_labels.map((item) => (
                <option key={item} value={item}>
                  {titleCase(item)}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="mt-6">
            <legend className="text-[11px]">Additional labels</legend>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {candidates.additional_labels.map((item) => (
                <label
                  className="flex min-h-11 items-center gap-3 border border-[var(--line)] px-3 text-[11px]"
                  key={item}
                >
                  <input
                    checked={currentAdditional.includes(item)}
                    className="accent-[var(--lime-strong)]"
                    onChange={(event) => {
                      setSelectedId(selected.topic_id);
                      setAdditional(
                        event.target.checked
                          ? [...currentAdditional, item]
                          : currentAdditional.filter((value) => value !== item),
                      );
                    }}
                    type="checkbox"
                  />
                  {titleCase(item)}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="mt-6 block text-[11px]">
            Reviewer notes
            <textarea
              className="mt-2 min-h-28 w-full border border-[var(--line-strong)] bg-white p-3 text-[12px]"
              maxLength={2000}
              onChange={(event) => {
                setSelectedId(selected.topic_id);
                setNotes(event.target.value);
              }}
              placeholder="Why this label is supported by the frozen evidence."
              value={currentNotes}
            />
          </label>
          <div className="mt-5 flex items-center gap-4">
            <Button
              className="min-h-11"
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  candidate: selected,
                  nextLabel: currentLabel,
                  nextAdditional: currentAdditional,
                  nextNotes: currentNotes,
                })
              }
              variant="primary"
            >
              <Save size={14} />
              {mutation.isPending ? "Saving…" : "Save point-in-time label"}
            </Button>
            {mutation.isSuccess ? (
              <span className="text-[11px] text-[var(--lime-ink)]">
                Evidence frozen
              </span>
            ) : null}
          </div>
          <p className="mt-5 border-l-2 border-[var(--line-strong)] pl-3 text-[10px] leading-5 text-[var(--muted)]">
            Evaluation is read-only with respect to production scoring. Small
            samples never update model weights automatically.
          </p>
        </section>
      </div>
    </div>
  );
}
