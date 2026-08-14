"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArchiveRestore,
  CheckCircle2,
  Clock3,
  RefreshCw,
  ServerCog,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ErrorState, PageLoading, StatusDot } from "@/components/ui";
import { getOperationsReadiness } from "@/lib/api";
import { relativeTime, titleCase } from "@/lib/format";

function statusTone(status: string): "healthy" | "warning" | "risk" {
  if (status === "ready" || status === "completed" || status === "success") {
    return "healthy";
  }
  return status === "critical" || status === "failed" ? "risk" : "warning";
}

export default function OperationsPage() {
  const query = useQuery({
    queryKey: ["operations-readiness"],
    queryFn: getOperationsReadiness,
    refetchInterval: 30_000,
  });

  if (query.isLoading) return <PageLoading label="Checking operations" />;
  if (query.isError) {
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  }
  if (!query.data) return null;

  const readiness = query.data;
  const pipelines = Object.entries(readiness.pipeline);

  return (
    <div className="mx-auto max-w-[1220px] px-5 py-8 sm:px-8">
      <PageHeader
        aside={
          <button
            className="flex items-center gap-2 border border-[var(--line-strong)] px-3 py-2 text-[11px] transition-colors hover:bg-white"
            onClick={() => query.refetch()}
            type="button"
          >
            <RefreshCw size={12} />
            Recheck
          </button>
        }
        description="Production readiness, pipeline freshness, failed jobs, and backup evidence in one place."
        title="Operations"
      />

      <section className="grid border-y border-[var(--line-strong)] lg:grid-cols-[280px_1fr]">
        <div className="border-b border-[var(--line)] py-6 pr-8 lg:border-r lg:border-b-0">
          <div className="flex items-center gap-3">
            <StatusDot tone={statusTone(readiness.status)} />
            <p className="editorial text-[34px]">
              {titleCase(readiness.status)}
            </p>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-[var(--muted)]">
            Last checked {relativeTime(readiness.checked_at)}. This screen
            refreshes every 30 seconds.
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4">
          {pipelines.map(([name, pipeline]) => (
            <div
              className="border-l border-[var(--line)] px-5 py-6 first:border-l-0"
              key={name}
            >
              <p className="text-[8px] tracking-[0.08em] text-[var(--muted)] uppercase">
                {name}
              </p>
              <div className="mt-4 flex items-center gap-2 text-[11px]">
                <StatusDot tone={statusTone(pipeline.status)} />
                {titleCase(pipeline.status)}
              </div>
              <p className="mt-3 text-[8px] text-[var(--faint)]">
                {pipeline.last_completed_at
                  ? `Completed ${relativeTime(pipeline.last_completed_at)}`
                  : "No completed run"}
              </p>
              <p className="mt-1 text-[8px] text-[var(--faint)]">
                {pipeline.failed_runs} failed
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid border-b border-[var(--line-strong)] lg:grid-cols-[1fr_360px]">
        <div className="py-7 lg:border-r lg:border-[var(--line)] lg:pr-8">
          <div className="mb-5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ServerCog size={16} strokeWidth={1.5} />
              <h2 className="editorial text-[22px]">Active alerts</h2>
            </div>
            <span className="text-[8px] text-[var(--muted)]">
              {readiness.alerts.length} open
            </span>
          </div>
          {readiness.alerts.length ? (
            <div className="divide-y divide-[var(--line)]">
              {readiness.alerts.map((alert) => (
                <div
                  className="grid grid-cols-[20px_120px_1fr] gap-3 py-3 text-[11px]"
                  key={alert.code}
                >
                  <AlertTriangle
                    className={
                      alert.severity === "critical"
                        ? "text-[var(--coral)]"
                        : "text-[var(--amber)]"
                    }
                    size={14}
                  />
                  <span className="mono text-[8px]">{alert.code}</span>
                  <span className="text-[var(--muted)]">{alert.message}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-3 border border-[var(--line)] bg-white p-5 text-[10px]">
              <CheckCircle2 className="lime" size={16} />
              No active operational alerts.
            </div>
          )}
        </div>

        <div className="py-7 lg:pl-8">
          <div className="flex items-center gap-2">
            <ArchiveRestore size={16} strokeWidth={1.5} />
            <h2 className="editorial text-[22px]">Recovery point</h2>
          </div>
          <div className="mt-5 border border-[var(--line)] bg-white p-5">
            <div className="flex items-center gap-2 text-[10px]">
              <StatusDot
                tone={readiness.backup.healthy ? "healthy" : "warning"}
              />
              {readiness.backup.healthy ? "Fresh backup" : "Backup overdue"}
            </div>
            <p className="mono mt-4 truncate text-[8px] text-[var(--muted)]">
              {readiness.backup.latest_file ?? "No backup found"}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-4 border-t border-[var(--line)] pt-4 text-[8px]">
              <div>
                <p className="text-[var(--faint)]">Age</p>
                <p className="mt-1">
                  {readiness.backup.age_hours === null
                    ? "—"
                    : `${readiness.backup.age_hours}h`}
                </p>
              </div>
              <div>
                <p className="text-[var(--faint)]">Checksum</p>
                <p className="mt-1">
                  {readiness.backup.checksum_present ? "Present" : "Missing"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-7">
        <div className="mb-5 flex items-center gap-2">
          <Clock3 size={16} strokeWidth={1.5} />
          <h2 className="editorial text-[22px]">Dead-letter queue</h2>
          <span className="text-[8px] text-[var(--muted)]">
            Latest {readiness.dead_letters.length}
          </span>
        </div>
        {readiness.dead_letters.length ? (
          <div className="overflow-x-auto border-t border-[var(--line-strong)]">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--line)] text-[8px] text-[var(--muted)]">
                  <th className="py-2 font-medium">Job</th>
                  <th className="py-2 font-medium">Failed</th>
                  <th className="py-2 font-medium">Code</th>
                  <th className="py-2 font-medium">Attempts</th>
                  <th className="py-2 font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {readiness.dead_letters.map((item) => (
                  <tr
                    className="border-b border-[var(--line)] text-[11px]"
                    key={`${item.job_type}:${item.id}`}
                  >
                    <td className="py-3 pr-5">
                      <span className="mr-2">{titleCase(item.job_type)}</span>
                      <span className="mono text-[7px] text-[var(--faint)]">
                        {item.id.slice(0, 8)}
                      </span>
                    </td>
                    <td className="py-3 pr-5 text-[var(--muted)]">
                      {relativeTime(item.failed_at)}
                    </td>
                    <td className="mono py-3 pr-5 text-[8px]">
                      {item.error_code ?? "unknown"}
                    </td>
                    <td className="py-3 pr-5">{item.attempt_count ?? "—"}</td>
                    <td className="max-w-[420px] py-3 text-[var(--muted)]">
                      {item.error_message ?? "No error detail captured"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex items-center gap-3 border-y border-[var(--line)] py-6 text-[10px] text-[var(--muted)]">
            <CheckCircle2 className="lime" size={16} />
            No failed jobs are waiting for review.
          </div>
        )}
      </section>
    </div>
  );
}
