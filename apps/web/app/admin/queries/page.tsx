"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CirclePause,
  Gauge,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button, ErrorState, PageLoading, StatusDot } from "@/components/ui";
import {
  getDiscoveryQueries,
  getQuerySuggestions,
  runQueryExpansion,
  transitionQuerySuggestion,
} from "@/lib/api";
import type { DiscoveryQuery, QuerySuggestion } from "@/lib/types";

type QueryAdminData = {
  suggestions: QuerySuggestion[];
  queries: DiscoveryQuery[];
};

export default function QueryExpansionPage() {
  const client = useQueryClient();
  const query = useQuery<QueryAdminData>({
    queryKey: ["query-expansion-admin"],
    queryFn: async () => {
      const [suggestions, queries] = await Promise.all([
        getQuerySuggestions(),
        getDiscoveryQueries(),
      ]);
      return { suggestions, queries };
    },
  });
  const runMutation = useMutation({
    mutationFn: runQueryExpansion,
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["query-expansion-admin"] }),
  });
  const actionMutation = useMutation({
    mutationFn: ({
      suggestion,
      action,
    }: {
      suggestion: QuerySuggestion;
      action: "approve" | "activate" | "pause" | "retire";
    }) => transitionQuerySuggestion(suggestion.id, action),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["query-expansion-admin"] }),
  });

  if (query.isLoading) return <PageLoading label="Loading query expansion" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const pending = query.data.suggestions.filter(
    (item) => item.status === "suggested",
  );

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8">
      <PageHeader
        aside={
          <Button
            disabled={runMutation.isPending}
            onClick={() => runMutation.mutate()}
            variant="primary"
          >
            <RefreshCw size={13} />
            {runMutation.isPending ? "Evaluating…" : "Find query candidates"}
          </Button>
        }
        description="Evidence-anchored query candidates stay inactive until an admin reviews and activates them"
        title="Query expansion"
      />

      <section className="grid gap-3 border-y border-[var(--line-strong)] py-5 sm:grid-cols-4">
        {[
          ["Pending review", pending.length],
          [
            "Active expanded",
            query.data.suggestions.filter((item) => item.status === "active")
              .length,
          ],
          [
            "Low value",
            query.data.suggestions.filter((item) => item.status === "low_value")
              .length,
          ],
          ["Total discovery queries", query.data.queries.length],
        ].map(([label, value]) => (
          <div
            className="border-l border-[var(--line)] pl-4"
            key={String(label)}
          >
            <p className="text-[8px] text-[var(--muted)] uppercase">{label}</p>
            <p className="editorial mt-2 text-[28px]">{value}</p>
          </div>
        ))}
      </section>

      <section className="mt-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="editorial text-[28px]">Suggestions</h2>
            <p className="mt-1 text-[11px] text-[var(--muted)]">
              Approval creates a paused query. Activation is a separate explicit
              step.
            </p>
          </div>
          <span className="text-[8px] text-[var(--muted)]">
            Hard cap: 50 pending · 10 new per run
          </span>
        </div>
        <div className="mt-4 border-t border-[var(--line-strong)]">
          {query.data.suggestions.map((suggestion) => (
            <article
              className="grid gap-5 border-b border-[var(--line)] bg-white px-5 py-5 lg:grid-cols-[1fr_210px_230px]"
              key={suggestion.id}
            >
              <div>
                <div className="flex flex-wrap items-center gap-2 text-[8px] uppercase">
                  <StatusDot
                    tone={
                      suggestion.status === "active"
                        ? "healthy"
                        : suggestion.status === "low_value"
                          ? "risk"
                          : "warning"
                    }
                  />
                  <span>{suggestion.status.replaceAll("_", " ")}</span>
                  <span className="text-[var(--muted)]">
                    · {suggestion.source_type.replaceAll("_", " ")}
                  </span>
                </div>
                <h3 className="mt-3 text-[14px] font-semibold">
                  {suggestion.query}
                </h3>
                <p className="mt-2 max-w-[620px] text-[11px] leading-relaxed text-[var(--muted)]">
                  {suggestion.rationale}
                </p>
                <p className="mono mt-3 text-[8px] text-[var(--faint)]">
                  Evidence {suggestion.source_evidence_ids.join(" · ")}
                </p>
              </div>
              <dl className="border-l border-[var(--line)] pl-5 text-[11px] max-lg:border-l-0 max-lg:pl-0">
                <div className="flex justify-between gap-3 py-1">
                  <dt className="text-[var(--muted)]">Source entity</dt>
                  <dd className="text-right">{suggestion.source_entity}</dd>
                </div>
                <div className="flex justify-between gap-3 py-1">
                  <dt className="text-[var(--muted)]">Anchors</dt>
                  <dd className="text-right">
                    {suggestion.anchor_terms.join(", ")}
                  </dd>
                </div>
                <div className="flex justify-between gap-3 py-1">
                  <dt className="text-[var(--muted)]">Broadness</dt>
                  <dd>{suggestion.broadness_score.toFixed(0)}</dd>
                </div>
                <div className="flex justify-between gap-3 py-1">
                  <dt className="text-[var(--muted)]">Precision</dt>
                  <dd>
                    {suggestion.precision_sample_size
                      ? `${suggestion.precision_score.toFixed(0)}%`
                      : "Unmeasured"}
                  </dd>
                </div>
              </dl>
              <div className="flex flex-wrap content-center justify-end gap-2">
                {suggestion.status === "suggested" ? (
                  <Button
                    disabled={actionMutation.isPending}
                    onClick={() =>
                      actionMutation.mutate({
                        suggestion,
                        action: "approve",
                      })
                    }
                  >
                    <Check size={12} /> Approve
                  </Button>
                ) : null}
                {suggestion.status === "approved" ? (
                  <Button
                    disabled={actionMutation.isPending}
                    onClick={() =>
                      actionMutation.mutate({
                        suggestion,
                        action: "activate",
                      })
                    }
                    variant="primary"
                  >
                    <Play size={12} /> Activate
                  </Button>
                ) : null}
                {suggestion.status === "active" ? (
                  <Button
                    disabled={actionMutation.isPending}
                    onClick={() =>
                      actionMutation.mutate({ suggestion, action: "pause" })
                    }
                  >
                    <CirclePause size={12} /> Pause
                  </Button>
                ) : null}
                {suggestion.status !== "retired" ? (
                  <Button
                    disabled={actionMutation.isPending}
                    onClick={() =>
                      actionMutation.mutate({ suggestion, action: "retire" })
                    }
                    variant="ghost"
                  >
                    <Trash2 size={12} /> Retire
                  </Button>
                ) : null}
              </div>
            </article>
          ))}
          {!query.data.suggestions.length ? (
            <p className="py-10 text-center text-[10px] text-[var(--muted)]">
              No candidates yet. Run evidence evaluation to create a bounded
              review queue.
            </p>
          ) : null}
        </div>
      </section>

      <section className="mt-10">
        <div className="flex items-center gap-2">
          <Gauge size={16} />
          <h2 className="editorial text-[28px]">Query precision</h2>
        </div>
        <div className="mt-4 overflow-x-auto border-t border-[var(--line-strong)]">
          <table className="w-full min-w-[760px] text-left text-[11px]">
            <thead className="text-[8px] text-[var(--muted)] uppercase">
              <tr>
                <th className="py-3 font-medium">Query</th>
                <th className="py-3 font-medium">Source</th>
                <th className="py-3 font-medium">Status</th>
                <th className="py-3 text-right font-medium">Sample</th>
                <th className="py-3 text-right font-medium">Precision</th>
              </tr>
            </thead>
            <tbody>
              {query.data.queries.map((item) => (
                <tr className="border-t border-[var(--line)]" key={item.id}>
                  <td className="py-3 font-medium">{item.query}</td>
                  <td className="py-3">{item.source}</td>
                  <td className="py-3">{item.quality_status}</td>
                  <td className="py-3 text-right">
                    {item.precision_sample_size}
                  </td>
                  <td className="py-3 text-right">
                    {item.precision_sample_size
                      ? `${item.precision_score.toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {runMutation.isError ? (
        <p className="mt-5 text-[11px] text-[var(--coral)]">
          {runMutation.error.message}
        </p>
      ) : null}
    </div>
  );
}
