"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Captions,
  Clock3,
  Database,
  Eye,
  FlaskConical,
  Gauge,
  GitBranch,
  Layers3,
  MessageSquareText,
  Network,
  Plus,
  Play,
  RefreshCw,
  RotateCcw,
  X,
} from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import {
  Button,
  ErrorState,
  LinkButton,
  PageLoading,
  StatusDot,
} from "@/components/ui";
import {
  addMonitoredChannel,
  createDiscoveryQuery,
  getDemandIntelligenceMetrics,
  getDemoContext,
  getDiscoveryQueries,
  getDiscoveryRuns,
  getMonitoredChannels,
  getLatestProviderBenchmark,
  getProviderFetch,
  getProviderFetches,
  getProviderRoutingDecisions,
  getProviderRoutingMetrics,
  getProviders,
  getTopicIntelligenceMetrics,
  getTranscriptIntelligenceMetrics,
  getVideoIntelligenceMetrics,
  getVideoIntelligenceVideos,
  replayProviderFetch,
  resetProviderCircuit,
  runProviderBenchmark,
  runDiscoveryQuery,
  runDemandIntelligence,
  runMonitoredChannel,
  runProviderHealthCheck,
  runTopicIntelligence,
  runTranscriptIntelligence,
  runVideoIntelligence,
  updateProvider,
} from "@/lib/api";
import { compactNumber, relativeTime } from "@/lib/format";
import type {
  DemandIntelligenceMetrics,
  DemoContext,
  DiscoveryQuery,
  IngestionRun,
  MonitoredChannel,
  ProviderFetch,
  ProviderFetchDetail,
  ProviderHealth,
  ProviderBenchmark,
  ProviderRoutingDecision,
  ProviderRoutingMetrics,
  TopicIntelligenceMetrics,
  TranscriptIntelligenceMetrics,
  VideoIntelligenceItem,
  VideoIntelligenceMetrics,
} from "@/lib/types";

type ProvidersData = {
  context: DemoContext;
  discoveryQueries: DiscoveryQuery[];
  discoveryRuns: IngestionRun[];
  monitoredChannels: MonitoredChannel[];
  providers: ProviderHealth[];
  fetches: ProviderFetch[];
  intelligenceMetrics: VideoIntelligenceMetrics;
  intelligenceVideos: VideoIntelligenceItem[];
  topicMetrics: TopicIntelligenceMetrics;
  demandMetrics: DemandIntelligenceMetrics;
  transcriptMetrics: TranscriptIntelligenceMetrics;
  routingMetrics: ProviderRoutingMetrics;
  routingDecisions: ProviderRoutingDecision[];
  benchmark: ProviderBenchmark | null;
};

function Toggle({
  checked,
  label,
  onChange,
  disabled,
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
  disabled: boolean;
}) {
  return (
    <button
      aria-checked={checked}
      aria-label={label}
      className={`relative h-5 w-9 rounded-full transition-colors ${
        checked ? "bg-[var(--lime-strong)]" : "bg-[var(--line-strong)]"
      }`}
      disabled={disabled}
      onClick={onChange}
      role="switch"
      type="button"
    >
      <span
        className={`absolute top-[2px] h-4 w-4 rounded-full bg-white transition-transform ${
          checked ? "translate-x-[18px]" : "translate-x-[2px]"
        }`}
      />
    </button>
  );
}

function RawPayloadDrawer({
  fetch,
  onClose,
  onReplay,
  replaying,
}: {
  fetch: ProviderFetchDetail;
  onClose: () => void;
  onReplay: () => void;
  replaying: boolean;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 max-h-[58vh] overflow-auto border-t border-[var(--line-strong)] bg-white shadow-[0_-10px_35px_rgba(0,0,0,0.08)] lg:left-[var(--sidebar)]">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--line)] bg-white px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Database size={15} />
          <span className="mono truncate text-[10px]">{fetch.id}</span>
          <span className="text-[var(--muted)]">·</span>
          <span className="text-[10px]">{fetch.provider}</span>
          <span className="text-[var(--muted)]">·</span>
          <span className="mono text-[11px]">{fetch.endpoint}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button disabled={replaying} onClick={onReplay}>
            <RotateCcw size={13} />
            {replaying ? "Replaying…" : "Replay"}
          </Button>
          <button
            aria-label="Close raw payload"
            className="grid h-8 w-8 place-items-center"
            onClick={onClose}
            type="button"
          >
            <X size={16} />
          </button>
        </div>
      </div>
      <div className="grid lg:grid-cols-[370px_1fr]">
        <dl className="border-r border-[var(--line)] p-5">
          {[
            ["Immutable content hash", fetch.raw_payload_hash],
            ["Request fingerprint", fetch.request_fingerprint],
            ["Parser version", fetch.parser_version],
            ["Raw fixture", fetch.raw_payload_uri],
            ["Attempt", String(fetch.attempt_number)],
          ].map(([label, value]) => (
            <div
              className="grid grid-cols-[128px_1fr] gap-3 border-b border-[var(--line)] py-3 last:border-b-0"
              key={label}
            >
              <dt className="text-[8px] text-[var(--muted)]">{label}</dt>
              <dd className="mono text-[8px] break-all">{value}</dd>
            </div>
          ))}
          <div className="mt-4">
            <p className="mb-2 text-[8px] text-[var(--muted)]">
              Linked entity IDs
            </p>
            {fetch.linked_entity_ids.map((id) => (
              <span
                className="mono mr-1 mb-1 inline-block border border-[var(--line)] px-2 py-1 text-[8px]"
                key={id}
              >
                {id}
              </span>
            ))}
          </div>
        </dl>
        <div>
          <div className="flex h-10 items-center gap-5 border-b border-[var(--line)] px-5 text-[11px]">
            <span className="border-b-2 border-[var(--lime-strong)] py-3">
              Raw JSON
            </span>
            <span className="text-[var(--muted)]">Normalized entities</span>
            <span className="text-[var(--muted)]">Replay notes</span>
          </div>
          <pre className="mono overflow-auto p-5 text-[11px] leading-[1.7]">
            {JSON.stringify(fetch.raw_payload, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

function formatLag(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function scheduledTime(value: string | null): string {
  if (!value) return "Schedule complete";
  const date = new Date(value);
  const minutes = Math.round((date.getTime() - Date.now()) / 60_000);
  if (minutes <= 0) return "Due now";
  if (minutes < 60) return `in ${minutes}m`;
  if (minutes < 2880) return `in ${Math.round(minutes / 60)}h`;
  return `in ${Math.round(minutes / 1440)}d`;
}

function VideoIntelligencePanel({
  metrics,
  videos,
  pending,
  refreshing,
  onRun,
}: {
  metrics: VideoIntelligenceMetrics;
  videos: VideoIntelligenceItem[];
  pending: boolean;
  refreshing: boolean;
  onRun: (forceRefresh: boolean) => void;
}) {
  const rankedVideos = videos
    .slice()
    .sort((a, b) => (b.outlier_ratio ?? 0) - (a.outlier_ratio ?? 0))
    .slice(0, 10);
  const cards = [
    {
      label: "Snapshot coverage",
      value: `${metrics.snapshot_coverage_percent}%`,
      detail: `${metrics.videos_with_snapshots}/${metrics.live_videos} live videos`,
      icon: Activity,
    },
    {
      label: "Queue",
      value: String(metrics.due_jobs),
      detail: `${metrics.pending_jobs} pending · ${metrics.skipped_jobs} impossible skipped`,
      icon: Clock3,
    },
    {
      label: "Processing lag",
      value: formatLag(metrics.snapshot_lag_seconds),
      detail:
        metrics.snapshot_lag_seconds === 0
          ? "All scheduled work is on time"
          : "Oldest overdue snapshot",
      icon: Gauge,
    },
    {
      label: "Computed models",
      value: String(metrics.feature_count),
      detail: `${metrics.baseline_count} channel baseline rows`,
      icon: Layers3,
    },
  ];

  return (
    <section className="mb-8 border border-[var(--line)] bg-white">
      <div className="flex flex-col gap-4 border-b border-[var(--line)] p-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="editorial text-[24px]">Video intelligence</h2>
            <span className="inline-flex items-center gap-1.5 border border-[var(--line)] bg-[var(--surface-subtle)] px-2 py-1 text-[8px] font-semibold tracking-[0.08em] uppercase">
              <StatusDot tone="healthy" /> Live measurements
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted)]">
            Historical snapshots → channel baselines → velocity and outlier
            scoring
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            disabled={pending}
            onClick={() => onRun(false)}
            variant="secondary"
          >
            <Play size={12} />
            {pending && !refreshing ? "Running due…" : "Run due snapshots"}
          </Button>
          <Button
            disabled={pending}
            onClick={() => onRun(true)}
            variant="primary"
          >
            <RefreshCw size={12} />
            {pending && refreshing ? "Refreshing…" : "Refresh live stats"}
          </Button>
        </div>
      </div>

      <div className="grid gap-px border-b border-[var(--line)] bg-[var(--line)] sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div className="bg-white p-4" key={card.label}>
              <div className="flex items-center justify-between">
                <p className="text-[8px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
                  {card.label}
                </p>
                <Icon className="text-[var(--muted)]" size={14} />
              </div>
              <p className="mono mt-4 text-[24px] leading-none">{card.value}</p>
              <p className="mt-2 text-[8px] text-[var(--muted)]">
                {card.detail}
              </p>
            </div>
          );
        })}
      </div>

      <div className="flex flex-col gap-1 border-b border-[var(--line)] bg-[var(--surface-subtle)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[11px]">
          Strongest measured outliers across the live discovery set
        </p>
        <p className="mono text-[8px] text-[var(--muted)]">
          Latest snapshot{" "}
          {metrics.latest_snapshot_at
            ? relativeTime(metrics.latest_snapshot_at)
            : "not available"}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left">
          <thead>
            <tr className="border-b border-[var(--line-strong)] text-[8px] tracking-[0.08em] text-[var(--muted)] uppercase">
              {[
                "Video",
                "Freshness",
                "Views",
                "Velocity",
                "Acceleration",
                "Outlier",
                "Engagement / 1k",
                "Next snapshot",
              ].map((label) => (
                <th className="px-3 py-3 font-medium" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="[content-visibility:auto]">
            {rankedVideos.map((video) => (
              <tr
                className="border-b border-[var(--line)] last:border-b-0"
                key={video.video_id}
              >
                <td className="max-w-[290px] px-3 py-3">
                  <a
                    className="block truncate text-[10px] font-medium hover:underline"
                    href={`https://www.youtube.com/watch?v=${video.youtube_video_id}`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {video.title}
                  </a>
                  <p className="mt-1 truncate text-[8px] text-[var(--muted)]">
                    {video.channel} · {video.snapshot_count} snapshots
                  </p>
                </td>
                <td className="px-3 py-3">
                  <span className="flex items-center gap-2 text-[8px]">
                    <StatusDot
                      tone={video.freshness === "Stale" ? "warning" : "healthy"}
                    />
                    {video.latest_snapshot_at
                      ? relativeTime(video.latest_snapshot_at)
                      : video.freshness}
                  </span>
                </td>
                <td className="mono px-3 py-3 text-[10px]">
                  {video.latest_views === null
                    ? "—"
                    : compactNumber(video.latest_views)}
                </td>
                <td className="mono px-3 py-3 text-[10px]">
                  {video.view_velocity === null
                    ? "—"
                    : `${compactNumber(video.view_velocity)}/h`}
                </td>
                <td className="mono px-3 py-3 text-[11px]">
                  {video.velocity_acceleration === null
                    ? "—"
                    : `${video.velocity_acceleration > 0 ? "+" : ""}${video.velocity_acceleration.toFixed(0)}%`}
                </td>
                <td className="px-3 py-3">
                  <span
                    className={`mono inline-flex min-w-12 justify-center border px-2 py-1 text-[10px] ${
                      (video.outlier_ratio ?? 0) >= 2
                        ? "border-[var(--lime-strong)] bg-[#f2ffd1]"
                        : "border-[var(--line)]"
                    }`}
                  >
                    {video.outlier_ratio === null
                      ? "—"
                      : `${video.outlier_ratio.toFixed(2)}×`}
                  </span>
                </td>
                <td className="mono px-3 py-3 text-[11px]">
                  {video.engagement_per_1000 === null
                    ? "—"
                    : video.engagement_per_1000.toFixed(1)}
                </td>
                <td className="px-3 py-3 text-[8px] text-[var(--muted)]">
                  {scheduledTime(video.next_snapshot_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rankedVideos.length === 0 ? (
          <p className="px-4 py-8 text-center text-[11px] text-[var(--muted)]">
            Run live ingestion to create the first measurement set.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function TopicIntelligencePanel({
  metrics,
  pending,
  onRun,
}: {
  metrics: TopicIntelligenceMetrics;
  pending: boolean;
  onRun: () => void;
}) {
  return (
    <section className="mb-8 grid border border-[var(--line)] bg-white lg:grid-cols-[1.2fr_.8fr]">
      <div className="border-b border-[var(--line)] p-5 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-3">
          <Network size={18} strokeWidth={1.5} />
          <div>
            <h2 className="editorial text-[24px]">Topic intelligence</h2>
            <p className="mt-1 text-[11px] text-[var(--muted)]">
              Entity normalization + local embeddings + transparent scoring
            </p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          {[
            ["Live topics", metrics.active_topics],
            ["Live signals", metrics.active_signals],
            ["Assigned videos", metrics.assigned_videos],
            ["Embeddings", metrics.embedding_count],
          ].map(([label, value]) => (
            <div className="border-l border-[var(--line)] pl-3" key={label}>
              <p className="mono text-[21px]">{value}</p>
              <p className="mt-1 text-[8px] text-[var(--muted)]">{label}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col justify-between p-5">
        <div className="grid grid-cols-2 gap-5 text-[11px]">
          <div>
            <p className="text-[var(--muted)]">Eligible / discovered</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.eligible_video_count} / {metrics.source_video_count}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Stale signals</p>
            <p className="mono mt-2 text-[14px]">{metrics.stale_signals}</p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Clustering lag</p>
            <p className="mono mt-2 text-[14px]">
              {formatLag(metrics.clustering_lag_seconds)}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Last run</p>
            <p className="mt-2 text-[10px]">
              {metrics.latest_run_at
                ? relativeTime(metrics.latest_run_at)
                : "Never"}
            </p>
          </div>
        </div>
        <div className="mt-5 border-t border-[var(--line)] pt-4 text-[11px]">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[var(--muted)]">Evidence decision graph</span>
            <span className="mono">
              {!metrics.llm_feature_enabled
                ? "OFF"
                : !metrics.llm_configured
                  ? "NO KEY"
                  : metrics.llm_circuit_open
                    ? "CIRCUIT OPEN"
                    : "ACTIVE"}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-[var(--muted)]">
              Grounding audit · {metrics.llm_audit_run_count} runs
            </span>
            <span className="mono">
              {metrics.llm_audit_required
                ? `${Math.round(metrics.llm_audit_acceptance_rate * 100)}% accepted`
                : "OPTIONAL"}
            </span>
          </div>
        </div>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <Button
            className="flex-1"
            disabled={pending}
            onClick={onRun}
            variant="primary"
          >
            <RefreshCw size={12} />
            {pending ? "Rebuilding…" : "Rebuild live signals"}
          </Button>
          <LinkButton className="flex-1" href="/signals">
            Open signals
          </LinkButton>
        </div>
      </div>
    </section>
  );
}

function DemandIntelligencePanel({
  metrics,
  pending,
  onRun,
}: {
  metrics: DemandIntelligenceMetrics;
  pending: boolean;
  onRun: () => void;
}) {
  return (
    <section className="mb-8 grid border border-[var(--line)] bg-white lg:grid-cols-[1.2fr_.8fr]">
      <div className="border-b border-[var(--line)] p-5 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-3">
          <MessageSquareText size={18} strokeWidth={1.5} />
          <div>
            <h2 className="editorial text-[24px]">Audience demand</h2>
            <p className="mt-1 text-[11px] text-[var(--muted)]">
              Top + newest comments, semantic relevance gate, evidence clusters
            </p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          {[
            ["Sampled videos", metrics.sampled_videos],
            ["Stored comments", metrics.comment_count],
            ["Classified", metrics.classified_count],
            ["Demand clusters", metrics.cluster_count],
          ].map(([label, value]) => (
            <div className="border-l border-[var(--line)] pl-3" key={label}>
              <p className="mono text-[21px]">{value}</p>
              <p className="mt-1 text-[8px] text-[var(--muted)]">{label}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col justify-between p-5">
        <div className="grid grid-cols-2 gap-5 text-[11px]">
          <div>
            <p className="text-[var(--muted)]">Topics with demand</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.topics_with_demand}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Failed / disabled</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.failed_fetches} / {metrics.comments_disabled_videos}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Rejected by relevance</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.demand_evidence_rejection_rate}%
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Median relevance</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.demand_relevance_median === null
                ? "Pending"
                : `${Math.round(metrics.demand_relevance_median * 100)}%`}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Processing lag</p>
            <p className="mono mt-2 text-[14px]">
              {formatLag(metrics.processing_lag_seconds)}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Last run</p>
            <p className="mt-2 text-[10px]">
              {metrics.latest_run_at
                ? relativeTime(metrics.latest_run_at)
                : "Never"}
            </p>
          </div>
        </div>
        <Button
          className="mt-6 w-full"
          disabled={pending}
          onClick={onRun}
          variant="primary"
        >
          <RefreshCw size={12} />
          {pending ? "Sampling comments…" : "Refresh comments + demand"}
        </Button>
      </div>
    </section>
  );
}

function TranscriptIntelligencePanel({
  metrics,
  pending,
  onRun,
}: {
  metrics: TranscriptIntelligenceMetrics;
  pending: boolean;
  onRun: () => void;
}) {
  return (
    <section className="mb-8 grid border border-[var(--line)] bg-white lg:grid-cols-[1.2fr_.8fr]">
      <div className="border-b border-[var(--line)] p-5 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-3">
          <Captions size={18} strokeWidth={1.5} />
          <div>
            <h2 className="editorial text-[24px]">Transcript intelligence</h2>
            <p className="mt-1 text-[11px] text-[var(--muted)]">
              Public captions → timed evidence → transcript-aware topic context
            </p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          {[
            ["Coverage", `${metrics.coverage_percent}%`],
            ["Transcripts", metrics.transcript_count],
            ["Timed segments", metrics.segment_count],
            ["Evidence excerpts", metrics.evidence_segment_count],
          ].map(([label, value]) => (
            <div className="border-l border-[var(--line)] pl-3" key={label}>
              <p className="mono text-[21px]">{value}</p>
              <p className="mt-1 text-[8px] text-[var(--muted)]">{label}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col justify-between p-5">
        <div className="grid grid-cols-2 gap-5 text-[11px]">
          <div>
            <p className="text-[var(--muted)]">Native / auto-caption</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.native_count} / {metrics.auto_caption_count}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Topics covered</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.topics_with_transcript}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Unavailable / failed</p>
            <p className="mono mt-2 text-[14px]">
              {metrics.unavailable_videos} / {metrics.failed_fetches}
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">Last run</p>
            <p className="mt-2 text-[10px]">
              {metrics.latest_run_at
                ? relativeTime(metrics.latest_run_at)
                : "Never"}
            </p>
          </div>
        </div>
        <Button
          className="mt-6 w-full"
          disabled={pending}
          onClick={onRun}
          variant="primary"
        >
          <RefreshCw size={12} />
          {pending ? "Fetching captions…" : "Refresh transcript evidence"}
        </Button>
      </div>
    </section>
  );
}

function ProviderRoutingPanel({
  metrics,
  decisions,
  benchmark,
  pending,
  onBenchmark,
}: {
  metrics: ProviderRoutingMetrics;
  decisions: ProviderRoutingDecision[];
  benchmark: ProviderBenchmark | null;
  pending: boolean;
  onBenchmark: (live: boolean) => void;
}) {
  const recommendations = Object.entries(
    benchmark?.recommended_priorities ?? {},
  );
  const cards = [
    {
      label: "Routing decisions",
      value: metrics.decisions,
      detail: `${metrics.successful} completed in the last 24h`,
    },
    {
      label: "Fallback rate",
      value: `${metrics.fallback_rate}%`,
      detail: `${metrics.fallback_count} successful fallbacks`,
    },
    {
      label: "Hard failures",
      value: metrics.failed,
      detail: "All eligible providers exhausted",
    },
    {
      label: "Circuit / controls",
      value: `${metrics.open_circuits} / ${metrics.disabled_capabilities}`,
      detail: `${metrics.budget_skips} budget skips`,
    },
  ];

  return (
    <section className="mb-8 border border-[var(--line)] bg-white">
      <div className="flex flex-col gap-4 border-b border-[var(--line)] p-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <GitBranch size={17} strokeWidth={1.5} />
            <h2 className="editorial text-[24px]">Resilient routing</h2>
          </div>
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            Preferred provider → bounded retry → circuit-aware fallback
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            disabled={pending}
            onClick={() => onBenchmark(false)}
            variant="secondary"
          >
            <FlaskConical size={12} />
            {pending ? "Building…" : "Refresh report"}
          </Button>
          <Button
            disabled={pending}
            onClick={() => onBenchmark(true)}
            variant="primary"
          >
            <Play size={12} />
            {pending ? "Probing…" : "Run live comparison"}
          </Button>
        </div>
      </div>

      <div className="grid gap-px border-b border-[var(--line)] bg-[var(--line)] sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div className="bg-white p-4" key={card.label}>
            <p className="text-[8px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
              {card.label}
            </p>
            <p className="mono mt-4 text-[24px] leading-none">{card.value}</p>
            <p className="mt-2 text-[8px] text-[var(--muted)]">{card.detail}</p>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1.25fr_.75fr]">
        <div className="border-b border-[var(--line)] lg:border-r lg:border-b-0">
          <div className="border-b border-[var(--line)] bg-[var(--surface-subtle)] px-4 py-3">
            <p className="text-[11px] font-medium">Recent routing decisions</p>
          </div>
          <div className="divide-y divide-[var(--line)]">
            {decisions.slice(0, 7).map((decision) => {
              const providers = [
                ...new Set(
                  decision.attempted_providers.map((item) => item.provider),
                ),
              ];
              return (
                <div
                  className="grid gap-2 px-4 py-3 sm:grid-cols-[110px_1fr_100px]"
                  key={decision.id}
                >
                  <div>
                    <p className="text-[11px] font-medium">
                      {decision.capability}
                    </p>
                    <p className="mt-1 text-[8px] text-[var(--muted)]">
                      {relativeTime(decision.created_at)}
                    </p>
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center gap-2 text-[8px]">
                    {providers.length ? (
                      providers.map((provider, index) => (
                        <span
                          className="contents"
                          key={`${decision.id}:${provider}`}
                        >
                          {index > 0 ? (
                            <ArrowRight
                              className="text-[var(--muted)]"
                              size={11}
                            />
                          ) : null}
                          <span
                            className={`mono border px-2 py-1 ${
                              provider === decision.selected_provider
                                ? "border-[var(--lime-strong)] bg-[#f2ffd1]"
                                : "border-[var(--line)]"
                            }`}
                          >
                            {provider}
                          </span>
                        </span>
                      ))
                    ) : (
                      <span className="text-[var(--muted)]">
                        Skipped before request
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-end gap-2 text-[8px]">
                    <StatusDot
                      tone={
                        decision.status === "success" ? "healthy" : "warning"
                      }
                    />
                    {decision.fallback_used
                      ? "Fallback"
                      : decision.status === "success"
                        ? "Preferred"
                        : decision.reason}
                  </div>
                </div>
              );
            })}
            {decisions.length === 0 ? (
              <p className="px-4 py-8 text-center text-[11px] text-[var(--muted)]">
                Routing decisions appear after the next live ingestion run.
              </p>
            ) : null}
          </div>
        </div>

        <div>
          <div className="border-b border-[var(--line)] bg-[var(--surface-subtle)] px-4 py-3">
            <p className="text-[11px] font-medium">Benchmark recommendation</p>
          </div>
          <div className="p-4">
            {recommendations.length ? (
              <div className="space-y-4">
                {recommendations.map(([capability, providers]) => (
                  <div key={capability}>
                    <p className="mb-2 text-[8px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
                      {capability}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 text-[8px]">
                      {providers.map((provider, index) => (
                        <span
                          className="contents"
                          key={`${capability}:${provider}`}
                        >
                          {index > 0 ? <ArrowRight size={10} /> : null}
                          <span className="mono">{provider}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] leading-relaxed text-[var(--muted)]">
                Build the first report from stored observations. Live comparison
                adds bounded discovery, comment, and caption probes.
              </p>
            )}
            <div className="mt-5 border-t border-[var(--line)] pt-4 text-[8px] text-[var(--muted)]">
              {benchmark ? (
                <>
                  <p>
                    {benchmark.result.mode ?? "stored_observations"} ·{" "}
                    {benchmark.result.fixture?.query_count ?? 100} query corpus
                    · {benchmark.live_case_count} live cases
                  </p>
                  <p className="mono mt-2 break-all">
                    {benchmark.markdown_path ?? benchmark.id}
                  </p>
                </>
              ) : (
                <p>No benchmark report yet.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function ProvidersPage() {
  const client = useQueryClient();
  const [selectedFetchId, setSelectedFetchId] = useState<string | null>(null);
  const [newQuery, setNewQuery] = useState("");
  const [channelId, setChannelId] = useState("");
  const query = useQuery<ProvidersData>({
    queryKey: ["provider-admin"],
    queryFn: async () => {
      const [
        context,
        discoveryQueries,
        discoveryRuns,
        monitoredChannels,
        providers,
        fetches,
        intelligenceMetrics,
        intelligenceVideos,
        topicMetrics,
        demandMetrics,
        transcriptMetrics,
        routingMetrics,
        routingDecisions,
        benchmark,
      ] = await Promise.all([
        getDemoContext(),
        getDiscoveryQueries(),
        getDiscoveryRuns(),
        getMonitoredChannels(),
        getProviders(),
        getProviderFetches(),
        getVideoIntelligenceMetrics(),
        getVideoIntelligenceVideos(),
        getTopicIntelligenceMetrics(),
        getDemandIntelligenceMetrics(),
        getTranscriptIntelligenceMetrics(),
        getProviderRoutingMetrics(),
        getProviderRoutingDecisions(),
        getLatestProviderBenchmark().catch(() => null),
      ]);
      return {
        context,
        discoveryQueries,
        discoveryRuns,
        monitoredChannels,
        providers,
        fetches,
        intelligenceMetrics,
        intelligenceVideos,
        topicMetrics,
        demandMetrics,
        transcriptMetrics,
        routingMetrics,
        routingDecisions,
        benchmark,
      };
    },
  });
  const fetchDetail = useQuery({
    queryKey: ["provider-fetch", selectedFetchId],
    queryFn: () => getProviderFetch(selectedFetchId!),
    enabled: Boolean(selectedFetchId),
  });
  const toggleMutation = useMutation({
    mutationFn: (provider: ProviderHealth) =>
      updateProvider(provider.provider, provider.capability, {
        enabled: !provider.enabled,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const priorityMutation = useMutation({
    mutationFn: ({
      provider,
      priority,
    }: {
      provider: ProviderHealth;
      priority: number;
    }) =>
      updateProvider(provider.provider, provider.capability, {
        priority,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const circuitMutation = useMutation({
    mutationFn: (provider: ProviderHealth) =>
      resetProviderCircuit(provider.provider, provider.capability),
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const healthMutation = useMutation({
    mutationFn: runProviderHealthCheck,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const replayMutation = useMutation({
    mutationFn: (id: string) => replayProviderFetch(id),
    onSuccess: (result) => {
      client.setQueryData(["provider-fetch", result.id], result);
      setSelectedFetchId(result.id);
      client.invalidateQueries({ queryKey: ["provider-admin"] });
    },
  });
  const createQueryMutation = useMutation({
    mutationFn: (value: string) => createDiscoveryQuery(value),
    onSuccess: () => {
      setNewQuery("");
      client.invalidateQueries({ queryKey: ["provider-admin"] });
    },
  });
  const runQueryMutation = useMutation({
    mutationFn: (id: string) => runDiscoveryQuery(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const monitorMutation = useMutation({
    mutationFn: (value: string) =>
      addMonitoredChannel(query.data!.context.workspace_id, value),
    onSuccess: (channel) => {
      setChannelId("");
      return runMonitoredChannel(channel.channel_id).finally(() =>
        client.invalidateQueries({ queryKey: ["provider-admin"] }),
      );
    },
  });
  const runChannelMutation = useMutation({
    mutationFn: runMonitoredChannel,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const intelligenceMutation = useMutation({
    mutationFn: runVideoIntelligence,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const topicMutation = useMutation({
    mutationFn: runTopicIntelligence,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const demandMutation = useMutation({
    mutationFn: runDemandIntelligence,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const transcriptMutation = useMutation({
    mutationFn: runTranscriptIntelligence,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });
  const benchmarkMutation = useMutation({
    mutationFn: runProviderBenchmark,
    onSuccess: () => client.invalidateQueries({ queryKey: ["provider-admin"] }),
  });

  if (query.isLoading) return <PageLoading label="Loading provider health" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const providersByCapability = Object.entries(
    query.data.providers.reduce<Record<string, ProviderHealth[]>>(
      (groups, provider) => {
        const rows = groups[provider.capability] ?? [];
        rows.push(provider);
        groups[provider.capability] = rows;
        return groups;
      },
      {},
    ),
  ).map(([capability, providers]) => [
    capability,
    providers.toSorted((a, b) => a.priority - b.priority),
  ]) as Array<[string, ProviderHealth[]]>;
  const spentToday = query.data.providers.reduce(
    (total, provider) => total + provider.spent_today_usd,
    0,
  );
  const dailyLimit = query.data.providers.reduce(
    (total, provider) => total + provider.daily_limit_usd,
    0,
  );

  return (
    <div className="flex min-h-[calc(100vh-var(--topbar))]">
      <div className="min-w-0 flex-1 px-5 py-8 sm:px-7">
        <div className="mx-auto max-w-[1170px]">
          <PageHeader
            aside={
              <div className="flex w-full gap-2 sm:w-auto">
                <Button
                  className="flex-1 sm:flex-none"
                  disabled={healthMutation.isPending}
                  onClick={() => healthMutation.mutate()}
                  variant="primary"
                >
                  <Play size={13} />
                  {healthMutation.isPending ? "Checking…" : "Run health check"}
                </Button>
                <Button
                  className="flex-1 sm:flex-none"
                  onClick={() => query.refetch()}
                >
                  <RefreshCw size={13} /> Refresh
                </Button>
              </div>
            }
            description="Live ingestion, raw evidence, provenance and provider operations"
            title="Ingestion control"
          />

          <section className="mb-8 grid gap-4 2xl:grid-cols-[1.35fr_.65fr]">
            <div className="border border-[var(--line)] bg-white">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--line)] p-4">
                <div>
                  <h2 className="editorial text-[22px]">
                    Discovery operations
                  </h2>
                  <p className="mt-1 text-[11px] text-[var(--muted)]">
                    Public YouTube discovery → official metadata → normalized
                    videos
                  </p>
                </div>
                <form
                  className="flex min-w-[280px] flex-1 gap-2 sm:max-w-[430px]"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = newQuery.trim();
                    if (value) createQueryMutation.mutate(value);
                  }}
                >
                  <input
                    aria-label="New discovery query"
                    className="h-9 min-w-0 flex-1 border border-[var(--line-strong)] bg-white px-3 text-[10px] outline-none focus:border-black"
                    onChange={(event) => setNewQuery(event.target.value)}
                    placeholder="Add an AI / tech query"
                    value={newQuery}
                  />
                  <Button
                    disabled={
                      createQueryMutation.isPending ||
                      newQuery.trim().length < 2
                    }
                    type="submit"
                  >
                    <Plus size={13} /> Add
                  </Button>
                </form>
              </div>
              <div className="divide-y divide-[var(--line)]">
                {query.data.discoveryQueries.map((item) => {
                  const latest = query.data.discoveryRuns.find(
                    (run) => run.query_id === item.id,
                  );
                  return (
                    <div
                      className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                      key={item.id}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-[11px] font-medium">{item.query}</p>
                        <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1 text-[8px] text-[var(--muted)]">
                          <span>
                            {item.category} · P{item.priority} · every{" "}
                            {Math.round(item.minimum_interval_seconds / 3600)}h
                          </span>
                          <span>
                            Yield{" "}
                            <strong className="mono font-medium text-[var(--ink)]">
                              {latest
                                ? `${latest.retained_video_count}/${latest.result_count}`
                                : "—"}
                            </strong>
                          </span>
                          <span>
                            Last run{" "}
                            <strong className="font-medium text-[var(--ink)]">
                              {latest
                                ? relativeTime(latest.started_at)
                                : "Never"}
                            </strong>
                          </span>
                        </div>
                      </div>
                      <Button
                        aria-label={`Run discovery query ${item.query}`}
                        className="h-8 justify-center"
                        disabled={runQueryMutation.isPending}
                        onClick={() => runQueryMutation.mutate(item.id)}
                        variant="primary"
                      >
                        <Play size={12} />
                        {runQueryMutation.isPending ? "Running…" : "Run"}
                      </Button>
                    </div>
                  );
                })}
              </div>
              {runQueryMutation.isError ? (
                <p className="border-t border-[var(--line)] px-4 py-3 text-[11px] text-red-700">
                  {runQueryMutation.error.message}
                </p>
              ) : null}
            </div>

            <div className="border border-[var(--line)] bg-white p-4">
              <h2 className="editorial text-[22px]">Monitored channels</h2>
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted)]">
                RSS discovery runs independently from search. Add a canonical
                YouTube channel ID.
              </p>
              <form
                className="mt-4 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  const value = channelId.trim();
                  if (value) monitorMutation.mutate(value);
                }}
              >
                <input
                  aria-label="YouTube channel ID"
                  className="h-9 min-w-0 flex-1 border border-[var(--line-strong)] px-3 text-[10px] outline-none focus:border-black"
                  onChange={(event) => setChannelId(event.target.value)}
                  placeholder="UC…"
                  value={channelId}
                />
                <Button
                  disabled={
                    monitorMutation.isPending || channelId.trim().length < 12
                  }
                  type="submit"
                >
                  <Plus size={13} /> Monitor
                </Button>
              </form>
              <div className="mt-4 divide-y divide-[var(--line)] border-t border-[var(--line)]">
                {query.data.monitoredChannels.length ? (
                  query.data.monitoredChannels.map((channel) => (
                    <div
                      className="flex items-center justify-between gap-3 py-3"
                      key={`${channel.workspace_id}:${channel.channel_id}`}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[10px] font-medium">
                          {channel.title}
                        </p>
                        <p className="mono mt-1 truncate text-[8px] text-[var(--muted)]">
                          {channel.youtube_channel_id}
                        </p>
                      </div>
                      <Button
                        aria-label={`Run monitored channel ${channel.title}`}
                        className="h-7 shrink-0"
                        disabled={runChannelMutation.isPending}
                        onClick={() =>
                          runChannelMutation.mutate(channel.channel_id)
                        }
                      >
                        <Play size={11} /> Run
                      </Button>
                    </div>
                  ))
                ) : (
                  <p className="py-4 text-[11px] text-[var(--muted)]">
                    No real channels monitored yet.
                  </p>
                )}
              </div>
              {monitorMutation.isError ? (
                <p className="mt-3 text-[11px] text-red-700">
                  {monitorMutation.error.message}
                </p>
              ) : null}
            </div>
          </section>

          <VideoIntelligencePanel
            metrics={query.data.intelligenceMetrics}
            onRun={(forceRefresh) => intelligenceMutation.mutate(forceRefresh)}
            pending={intelligenceMutation.isPending}
            refreshing={intelligenceMutation.variables === true}
            videos={query.data.intelligenceVideos}
          />
          {intelligenceMutation.isError ? (
            <p className="-mt-5 mb-8 border border-red-200 bg-red-50 px-4 py-3 text-[11px] text-red-700">
              {intelligenceMutation.error.message}
            </p>
          ) : null}

          <TopicIntelligencePanel
            metrics={query.data.topicMetrics}
            onRun={() => topicMutation.mutate()}
            pending={topicMutation.isPending}
          />
          {topicMutation.isError ? (
            <p className="-mt-5 mb-8 border border-red-200 bg-red-50 px-4 py-3 text-[11px] text-red-700">
              {topicMutation.error.message}
            </p>
          ) : null}

          <DemandIntelligencePanel
            metrics={query.data.demandMetrics}
            onRun={() => demandMutation.mutate()}
            pending={demandMutation.isPending}
          />
          {demandMutation.isError ? (
            <p className="-mt-5 mb-8 border border-red-200 bg-red-50 px-4 py-3 text-[11px] text-red-700">
              {demandMutation.error.message}
            </p>
          ) : null}

          <TranscriptIntelligencePanel
            metrics={query.data.transcriptMetrics}
            onRun={() => transcriptMutation.mutate()}
            pending={transcriptMutation.isPending}
          />
          {transcriptMutation.isError ? (
            <p className="-mt-5 mb-8 border border-red-200 bg-red-50 px-4 py-3 text-[11px] text-red-700">
              {transcriptMutation.error.message}
            </p>
          ) : null}

          <ProviderRoutingPanel
            benchmark={query.data.benchmark}
            decisions={query.data.routingDecisions}
            metrics={query.data.routingMetrics}
            onBenchmark={(live) => benchmarkMutation.mutate(live)}
            pending={benchmarkMutation.isPending}
          />
          {benchmarkMutation.isError ? (
            <p className="-mt-5 mb-8 border border-red-200 bg-red-50 px-4 py-3 text-[11px] text-red-700">
              {benchmarkMutation.error.message}
            </p>
          ) : null}

          <div className="mb-3 flex items-end justify-between">
            <div>
              <h2 className="editorial text-[24px]">Provider health</h2>
              <p className="mt-1 text-[11px] text-[var(--muted)]">
                Real and deterministic demo capabilities stay isolated.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto border border-[var(--line)] bg-white">
            <table className="w-full min-w-[1180px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--line-strong)] bg-[var(--surface-subtle)] text-[8px] font-semibold tracking-[0.08em] text-[var(--muted)] uppercase">
                  {[
                    "Provider",
                    "Capability",
                    "Status",
                    "Circuit",
                    "Requests h / d",
                    "Success / fallback",
                    "p50 / p95",
                    "Spend day / month",
                    "Priority",
                    "Last issue",
                    "Control",
                  ].map((label) => (
                    <th className="px-3 py-3 font-medium" key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {query.data.providers.map((provider) => (
                  <tr
                    className="border-b border-[var(--line)] last:border-b-0"
                    key={`${provider.provider}:${provider.capability}`}
                  >
                    <td className="px-3 py-4">
                      <p className="mono text-[10px]">{provider.provider}</p>
                      <p className="mt-1 text-[8px] text-[var(--muted)]">
                        {provider.demo ? "Demo" : "Live"}
                      </p>
                    </td>
                    <td className="px-3 py-4 text-[10px]">
                      {provider.capability}
                    </td>
                    <td className="px-3 py-4">
                      <span className="flex items-center gap-2 text-[11px]">
                        <StatusDot
                          tone={
                            !provider.enabled
                              ? "neutral"
                              : provider.status === "Healthy"
                                ? "healthy"
                                : "warning"
                          }
                        />
                        {provider.status}
                      </span>
                    </td>
                    <td className="px-3 py-4 text-[11px] capitalize">
                      <p>{provider.circuit_state}</p>
                      <p className="mono mt-1 text-[8px] text-[var(--muted)]">
                        {provider.consecutive_failures} consecutive failures
                      </p>
                    </td>
                    <td className="mono px-3 py-4 text-[11px]">
                      {provider.request_count_hour} /{" "}
                      {provider.request_count_day}
                      <span className="mt-1 block text-[8px] text-[var(--muted)]">
                        {provider.request_count} lifetime
                      </span>
                    </td>
                    <td className="px-3 py-4">
                      <p className="mono text-[10px]">
                        {provider.success_rate}% / {provider.fallback_rate}%
                      </p>
                      <p className="mt-1 text-[8px] text-[var(--muted)]">
                        success / fallback
                      </p>
                    </td>
                    <td className="mono px-3 py-4 text-[11px]">
                      {provider.p50_latency_ms} / {provider.p95_latency_ms} ms
                    </td>
                    <td className="px-3 py-4 text-[11px]">
                      ${provider.spent_today_usd.toFixed(4)} / $
                      {provider.spent_month_usd.toFixed(4)}
                      <span className="block text-[8px] text-[var(--muted)]">
                        ${provider.daily_limit_usd.toFixed(0)} daily cap
                      </span>
                    </td>
                    <td className="px-3 py-4">
                      <div className="flex items-center gap-1">
                        <Button
                          aria-label={`Raise priority for ${provider.provider} ${provider.capability}`}
                          className="h-7 w-7 justify-center px-0"
                          disabled={
                            priorityMutation.isPending || provider.priority <= 1
                          }
                          onClick={() =>
                            priorityMutation.mutate({
                              provider,
                              priority: provider.priority - 1,
                            })
                          }
                        >
                          −
                        </Button>
                        <span className="mono min-w-5 text-center text-[10px]">
                          {provider.priority}
                        </span>
                        <Button
                          aria-label={`Lower priority for ${provider.provider} ${provider.capability}`}
                          className="h-7 w-7 justify-center px-0"
                          disabled={
                            priorityMutation.isPending ||
                            provider.priority >= 20
                          }
                          onClick={() =>
                            priorityMutation.mutate({
                              provider,
                              priority: provider.priority + 1,
                            })
                          }
                        >
                          +
                        </Button>
                      </div>
                    </td>
                    <td className="max-w-[150px] px-3 py-4 text-[8px] leading-relaxed text-[var(--muted)]">
                      {provider.disabled_reason ?? provider.last_error ?? "—"}
                    </td>
                    <td className="px-3 py-4">
                      <div className="flex items-center gap-2">
                        <Toggle
                          checked={provider.enabled}
                          disabled={toggleMutation.isPending}
                          label={`${provider.enabled ? "Disable" : "Enable"} ${provider.provider} ${provider.capability}`}
                          onChange={() => toggleMutation.mutate(provider)}
                        />
                        {provider.circuit_state !== "closed" ? (
                          <Button
                            className="h-7"
                            disabled={circuitMutation.isPending}
                            onClick={() => circuitMutation.mutate(provider)}
                          >
                            <RotateCcw size={11} /> Reset
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="mt-8">
            <div className="mb-3 flex items-end justify-between">
              <div>
                <h2 className="editorial text-[24px]">
                  Recent provider fetches
                </h2>
                <p className="mt-1 text-[11px] text-[var(--muted)]">
                  Immutable raw fixtures are inspectable and replayable.
                </p>
              </div>
              <p className="mono text-[11px] text-[var(--muted)]">
                {query.data.fetches.length} fetches
              </p>
            </div>
            <div className="overflow-x-auto border border-[var(--line)] bg-white">
              <table className="w-full min-w-[780px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-[var(--line-strong)] bg-[var(--surface-subtle)] text-[8px] tracking-[0.08em] text-[var(--muted)] uppercase">
                    {[
                      "Request ID",
                      "Provider",
                      "Endpoint",
                      "Started",
                      "Latency",
                      "Status",
                      "Raw payload",
                      "",
                    ].map((label, index) => (
                      <th
                        className="px-3 py-3 font-medium"
                        key={`${label}-${index}`}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {query.data.fetches.map((fetch) => (
                    <tr
                      className="border-b border-[var(--line)] last:border-b-0"
                      key={fetch.id}
                    >
                      <td className="mono px-3 py-3 text-[8px]">
                        {fetch.id.slice(0, 13)}
                      </td>
                      <td className="px-3 py-3 text-[11px]">
                        {fetch.provider}
                      </td>
                      <td className="mono px-3 py-3 text-[8px]">
                        {fetch.endpoint}
                      </td>
                      <td className="px-3 py-3 text-[8px]">
                        {relativeTime(fetch.started_at)}
                      </td>
                      <td className="mono px-3 py-3 text-[8px]">
                        {fetch.latency_ms} ms
                      </td>
                      <td className="px-3 py-3">
                        <span className="flex items-center gap-2 text-[8px]">
                          <StatusDot
                            tone={
                              fetch.status === "success" ? "healthy" : "warning"
                            }
                          />
                          {fetch.http_status} {fetch.status}
                        </span>
                      </td>
                      <td className="mono max-w-[140px] truncate px-3 py-3 text-[8px]">
                        {fetch.raw_payload_hash.slice(0, 14)}…
                      </td>
                      <td className="px-3 py-3 text-right">
                        <Button
                          aria-label={`View payload ${fetch.id}`}
                          className="h-7 text-[11px]"
                          onClick={() => setSelectedFetchId(fetch.id)}
                        >
                          <Eye size={12} /> View payload
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>

      <aside className="hidden w-[260px] shrink-0 border-l border-[var(--line)] bg-white p-5 xl:block">
        <p className="text-[12px] font-semibold">Routing policy</p>
        <p className="mt-2 text-[11px] text-[var(--muted)]">
          Fallback order by capability
        </p>
        <div className="mt-5 divide-y divide-[var(--line)]">
          {providersByCapability.map(([capability, providers]) => (
            <div className="py-4" key={capability}>
              <p className="mb-3 text-[11px] font-medium">{capability}</p>
              <div className="space-y-2">
                {providers.map((provider) => (
                  <div
                    className="grid grid-cols-[18px_8px_1fr] items-center gap-2 text-[8px]"
                    key={`${provider.provider}:${provider.capability}`}
                  >
                    <span className="mono text-[var(--muted)]">
                      {provider.priority}
                    </span>
                    <StatusDot
                      tone={provider.enabled ? "healthy" : "neutral"}
                    />
                    <span
                      className={`mono truncate ${
                        provider.enabled
                          ? "text-[var(--ink)]"
                          : "text-[var(--muted)] line-through"
                      }`}
                    >
                      {provider.provider}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-5 border-t border-[var(--line)] pt-5">
          <p className="text-[12px] font-semibold">Provider budget</p>
          <div className="mt-5 flex justify-between text-[11px]">
            <span className="text-[var(--muted)]">Daily limit</span>
            <span>${dailyLimit.toFixed(2)}</span>
          </div>
          <div className="mt-3 flex justify-between text-[11px]">
            <span className="text-[var(--muted)]">Spent today</span>
            <span>${spentToday.toFixed(4)}</span>
          </div>
          <div className="mt-3 h-1 bg-[var(--line)]">
            <div
              className="h-full bg-[var(--lime-strong)]"
              style={{
                width: `${Math.min(100, dailyLimit ? (spentToday / dailyLimit) * 100 : 0)}%`,
              }}
            />
          </div>
          <p className="mt-3 text-[8px] leading-relaxed text-[var(--muted)]">
            Zero-dollar calls still record quota-independent cost evidence.
          </p>
        </div>
      </aside>

      {fetchDetail.data && selectedFetchId && (
        <RawPayloadDrawer
          fetch={fetchDetail.data}
          onClose={() => setSelectedFetchId(null)}
          onReplay={() => replayMutation.mutate(selectedFetchId)}
          replaying={replayMutation.isPending}
        />
      )}
    </div>
  );
}
