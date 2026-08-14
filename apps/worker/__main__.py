from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.database import SessionLocal
from apps.api.demo import DEMO_WORKSPACE_ID
from apps.api.lifecycle import backfill_lifecycle_history
from apps.api.models import DiscoveryQueryRecord, WorkspaceChannel, YoutubeChannel
from apps.api.snapshot_buckets import backfill_snapshot_buckets
from apps.api.youtube_oauth import YoutubeOwnedAnalyticsService
from apps.worker.demand_intelligence import DemandIntelligenceService
from apps.worker.digests import DigestService
from apps.worker.ingestion import IngestionService
from apps.worker.outcome_tracking import OutcomeAutomationService
from apps.worker.query_expansion import QueryExpansionService
from apps.worker.topic_intelligence import TopicIntelligenceService
from apps.worker.transcript_intelligence import TranscriptIntelligenceService
from apps.worker.video_intelligence import VideoIntelligenceService
from packages.provider_benchmark import ProviderBenchmarkService


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    settings.validate_runtime()
    with SessionLocal() as session:
        service = IngestionService(session, settings)
        intelligence = VideoIntelligenceService(session, settings)
        topics = TopicIntelligenceService(session, settings)
        demand = DemandIntelligenceService(session, settings)
        transcripts = TranscriptIntelligenceService(session, settings)
        benchmark = ProviderBenchmarkService(session, settings)
        digests = DigestService(session)
        outcomes = OutcomeAutomationService(session)
        owned_analytics = YoutubeOwnedAnalyticsService(session, settings)
        query_expansion = QueryExpansionService(session)
        if args.command == "seed-queries":
            rows = service.seed_default_queries()
            print(json.dumps({"queries": len(rows)}))
            return
        if args.command == "run-query":
            row = service.create_query(
                query=args.query,
                category=args.category,
                priority=args.priority,
            )
            result = await service.run_query(
                row,
                force=args.force,
                max_results=args.limit,
            )
            topics.run(force=True)
            print(json.dumps(asdict(result), default=str))
            return
        if args.command == "run-due":
            service.seed_default_queries()
            results = await service.run_due(limit=args.limit)
            print(json.dumps([asdict(item) for item in results], default=str))
            return
        if args.command == "schedule-snapshots":
            created = intelligence.schedule_all(limit=args.limit)
            print(json.dumps({"snapshot_jobs_created": created}))
            return
        if args.command == "run-snapshots":
            snapshot_result = await intelligence.run_due(limit=args.limit)
            print(json.dumps(asdict(snapshot_result), default=str))
            return
        if args.command == "refresh-video-intelligence":
            refresh_result = await intelligence.refresh_recent(limit=args.limit)
            print(json.dumps(asdict(refresh_result), default=str))
            return
        if args.command == "backfill-channel-history":
            backfill_result = await service.backfill_channel_histories(
                limit_channels=args.limit,
                uploads_per_channel=args.uploads,
            )
            print(json.dumps(asdict(backfill_result), default=str))
            return
        if args.command == "rebuild-video-intelligence":
            baselines = intelligence.recalculate_channel_baselines()
            features = intelligence.calculate_video_features()
            session.commit()
            print(
                json.dumps(
                    {
                        "features_updated": features,
                        "baselines_updated": baselines,
                    }
                )
            )
            return
        if args.command == "video-intelligence-metrics":
            print(json.dumps(intelligence.operational_metrics(), default=str))
            return
        if args.command == "build-signals":
            build_result = topics.run(force=args.force)
            print(json.dumps(asdict(build_result), default=str))
            return
        if args.command == "enrich-workspace":
            enrichment_result = topics.enrich_workspace(
                args.workspace_id,
                limit=args.limit,
            )
            print(json.dumps(asdict(enrichment_result), default=str))
            return
        if args.command == "backfill-lifecycle-history":
            lifecycle_backfill_result = backfill_lifecycle_history(
                session,
                source_kind=args.source,
            )
            session.commit()
            print(json.dumps(asdict(lifecycle_backfill_result), default=str))
            return
        if args.command == "backfill-snapshot-buckets":
            bucket_result = backfill_snapshot_buckets(
                session,
                captured_at=datetime.now(tz=UTC),
                source_kind=args.source,
            )
            session.commit()
            print(json.dumps(bucket_result, default=str))
            return
        if args.command == "topic-intelligence-metrics":
            print(json.dumps(topics.operational_metrics(), default=str))
            return
        if args.command == "run-demand":
            demand_result = await demand.run(
                force=args.force,
                limit=args.limit,
            )
            if not demand_result.reused:
                topics.run(force=True)
            print(json.dumps(asdict(demand_result), default=str))
            return
        if args.command == "demand-intelligence-metrics":
            print(json.dumps(demand.operational_metrics(), default=str))
            return
        if args.command == "run-transcripts":
            transcript_result = await transcripts.run(
                force=args.force,
                limit=args.limit,
            )
            if transcript_result.fetched:
                topics.run(force=True)
            print(json.dumps(asdict(transcript_result), default=str))
            return
        if args.command == "transcript-intelligence-metrics":
            print(json.dumps(transcripts.operational_metrics(), default=str))
            return
        if args.command == "benchmark-providers":
            benchmark_run = await benchmark.run(
                live=args.live,
                limit=args.limit,
            )
            print(
                json.dumps(
                    {
                        "id": benchmark_run.id,
                        "status": benchmark_run.status,
                        "live_case_count": benchmark_run.live_case_count,
                        "recommended_priorities": (benchmark_run.recommended_priorities_json),
                        "json_path": benchmark_run.json_path,
                        "csv_path": benchmark_run.csv_path,
                        "markdown_path": benchmark_run.markdown_path,
                    },
                    default=str,
                )
            )
            return
        if args.command == "generate-digest":
            workspace_id = args.workspace_id
            digest = digests.generate(workspace_id)
            print(
                json.dumps(
                    {
                        "id": digest.id,
                        "workspace_id": digest.workspace_id,
                        "status": digest.status,
                        "signal_count": len(digest.content_json.get("items", [])),
                        "generated_at": digest.generated_at,
                    },
                    default=str,
                )
            )
            return
        if args.command == "refresh-outcomes":
            outcome_result = outcomes.run(args.workspace_id)
            print(json.dumps(asdict(outcome_result), default=str))
            return
        if args.command == "sync-owned-analytics":
            analytics_result = (
                {
                    "workspaces_synced": 1,
                    "videos_updated": await owned_analytics.sync(args.workspace_id),
                }
                if args.workspace_id
                else await owned_analytics.sync_due(limit=args.limit)
            )
            print(json.dumps(analytics_result, default=str))
            return
        if args.command == "expand-queries":
            expansion_result = query_expansion.run()
            print(json.dumps(asdict(expansion_result), default=str))
            return
        if args.command == "serve":
            service.seed_default_queries()
            await service.backfill_channel_histories(limit_channels=3)
            intelligence.schedule_all()
            topics.reconcile_stale_runs()
            startup_topic_result = topics.run()
            startup_demand = await demand.run()
            startup_transcripts = await transcripts.run()
            if not startup_demand.reused or startup_transcripts.fetched:
                startup_topic_result = topics.run(force=True)
            if not startup_topic_result.reused:
                topics.enrich_active_workspaces()
            digests.generate_due()
            if settings.feature_outcome_suggestions:
                outcomes.run()
            if settings.feature_youtube_oauth_analytics:
                await owned_analytics.sync_due()
            if settings.feature_query_expansion:
                query_expansion.run()
            while True:
                try:
                    results = await service.run_due(limit=args.limit)
                    history_backfill = await service.backfill_channel_histories(limit_channels=3)
                    snapshot_result = await intelligence.run_due(limit=args.snapshot_limit)
                    demand_result = await demand.run()
                    transcript_result = await transcripts.run()
                    topic_dirty = bool(
                        results
                        or history_backfill.channels_completed
                        or snapshot_result.snapshots_created
                        or not demand_result.reused
                        or transcript_result.fetched
                    )
                    topic_result = topics.run() if topic_dirty else None
                    workspace_enrichment_results = (
                        topics.enrich_active_workspaces()
                        if topic_result is not None and not topic_result.reused
                        else []
                    )
                    digest_runs = digests.generate_due()
                    scheduler_outcome_result = (
                        outcomes.run() if settings.feature_outcome_suggestions else None
                    )
                    owned_analytics_result = (
                        await owned_analytics.sync_due()
                        if settings.feature_youtube_oauth_analytics
                        else None
                    )
                    query_expansion_result = (
                        query_expansion.run() if settings.feature_query_expansion else None
                    )
                    if (
                        results
                        or history_backfill.channels_completed
                        or snapshot_result.requested_jobs
                        or not demand_result.reused
                        or not transcript_result.reused
                        or digest_runs
                        or (
                            scheduler_outcome_result is not None
                            and (
                                scheduler_outcome_result.suggestions_created
                                or scheduler_outcome_result.outcomes_updated
                            )
                        )
                        or (
                            owned_analytics_result is not None
                            and owned_analytics_result["videos_updated"]
                        )
                        or (
                            query_expansion_result is not None
                            and (
                                query_expansion_result.suggestions_created
                                or query_expansion_result.low_value_queries_demoted
                            )
                        )
                    ):
                        print(
                            json.dumps(
                                {
                                    "ingestion_runs": [asdict(item) for item in results],
                                    "history_backfill": asdict(history_backfill),
                                    "snapshot_run": asdict(snapshot_result),
                                    "topic_run": (
                                        asdict(topic_result) if topic_result is not None else None
                                    ),
                                    "workspace_enrichment_runs": [
                                        asdict(item) for item in workspace_enrichment_results
                                    ],
                                    "demand_run": asdict(demand_result),
                                    "transcript_run": asdict(transcript_result),
                                    "digest_runs": [
                                        {
                                            "id": item.id,
                                            "workspace_id": item.workspace_id,
                                            "status": item.status,
                                        }
                                        for item in digest_runs
                                    ],
                                    "outcome_run": (
                                        asdict(scheduler_outcome_result)
                                        if scheduler_outcome_result is not None
                                        else None
                                    ),
                                    "owned_analytics_run": owned_analytics_result,
                                    "query_expansion_run": (
                                        asdict(query_expansion_result)
                                        if query_expansion_result is not None
                                        else None
                                    ),
                                },
                                default=str,
                            ),
                            flush=True,
                        )
                except Exception as error:
                    print(
                        json.dumps(
                            {
                                "status": "scheduler_error",
                                "error": type(error).__name__,
                                "message": str(error)[:500],
                            }
                        ),
                        flush=True,
                    )
                await asyncio.sleep(args.poll_seconds)
        if args.command == "monitor-channel":
            channel = await service.monitor_channel(
                workspace_id=args.workspace_id,
                youtube_channel_id=args.channel_id,
                relationship=args.relationship,
                priority=args.priority,
            )
            workspace_channel = session.get(
                WorkspaceChannel,
                (args.workspace_id, channel.id),
            )
            if workspace_channel is None:
                raise RuntimeError("Monitored channel was not persisted")
            result = await service.ingest_monitored_channel(
                workspace_channel,
                force=True,
                max_results=args.limit,
            )
            print(json.dumps(asdict(result), default=str))
            return
        if args.command == "ingest-channel":
            monitored_channel = session.scalar(
                select(YoutubeChannel).where(YoutubeChannel.youtube_channel_id == args.channel_id)
            )
            if monitored_channel is None:
                raise RuntimeError("Channel is not monitored; use `monitor-channel` first")
            workspace_channel = session.scalar(
                select(WorkspaceChannel).where(
                    WorkspaceChannel.channel_id == monitored_channel.id,
                    WorkspaceChannel.active.is_(True),
                )
            )
            if workspace_channel is None:
                raise RuntimeError("Channel monitoring is disabled")
            result = await service.ingest_monitored_channel(
                workspace_channel,
                force=args.force,
                max_results=args.limit,
            )
            print(json.dumps(asdict(result), default=str))
            return
        if args.command == "list-queries":
            rows = list(
                session.scalars(
                    select(DiscoveryQueryRecord).order_by(
                        DiscoveryQueryRecord.priority,
                        DiscoveryQueryRecord.query,
                    )
                )
            )
            print(
                json.dumps(
                    [
                        {
                            "id": row.id,
                            "query": row.query,
                            "priority": row.priority,
                            "active": row.active,
                            "next_run_at": row.next_run_at,
                        }
                        for row in rows
                    ],
                    default=str,
                )
            )
            return
        raise RuntimeError(f"Unsupported command: {args.command}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EarlySignal ingestion worker")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("seed-queries")
    commands.add_parser("list-queries")

    run_query = commands.add_parser("run-query")
    run_query.add_argument("query")
    run_query.add_argument("--category", default="AI / tech")
    run_query.add_argument("--priority", type=int, default=1, choices=range(4))
    run_query.add_argument("--limit", type=int, default=20)
    run_query.add_argument("--force", action="store_true")

    run_due = commands.add_parser("run-due")
    run_due.add_argument("--limit", type=int, default=5)

    schedule_snapshots = commands.add_parser("schedule-snapshots")
    schedule_snapshots.add_argument("--limit", type=int, default=500)

    run_snapshots = commands.add_parser("run-snapshots")
    run_snapshots.add_argument("--limit", type=int, default=50)

    refresh_intelligence = commands.add_parser("refresh-video-intelligence")
    refresh_intelligence.add_argument("--limit", type=int, default=50)

    backfill_history = commands.add_parser("backfill-channel-history")
    backfill_history.add_argument("--limit", type=int, default=20)
    backfill_history.add_argument("--uploads", type=int, default=15)

    commands.add_parser("rebuild-video-intelligence")
    commands.add_parser("video-intelligence-metrics")
    build_signals = commands.add_parser("build-signals")
    build_signals.add_argument("--force", action="store_true")
    enrich_workspace = commands.add_parser("enrich-workspace")
    enrich_workspace.add_argument("--workspace-id", required=True)
    enrich_workspace.add_argument("--limit", type=int, default=12)
    lifecycle_history = commands.add_parser("backfill-lifecycle-history")
    lifecycle_history.add_argument("--source", choices=("live", "demo"), default="live")
    snapshot_buckets = commands.add_parser("backfill-snapshot-buckets")
    snapshot_buckets.add_argument("--source", choices=("live", "demo"), default="live")
    commands.add_parser("topic-intelligence-metrics")
    run_demand = commands.add_parser("run-demand")
    run_demand.add_argument("--limit", type=int, default=12)
    run_demand.add_argument("--force", action="store_true")
    commands.add_parser("demand-intelligence-metrics")
    run_transcripts = commands.add_parser("run-transcripts")
    run_transcripts.add_argument("--limit", type=int, default=8)
    run_transcripts.add_argument("--force", action="store_true")
    commands.add_parser("transcript-intelligence-metrics")
    benchmark = commands.add_parser("benchmark-providers")
    benchmark.add_argument("--live", action="store_true")
    benchmark.add_argument("--limit", type=int, default=3)
    digest = commands.add_parser("generate-digest")
    digest.add_argument("--workspace-id", default=DEMO_WORKSPACE_ID)
    refresh_outcomes = commands.add_parser("refresh-outcomes")
    refresh_outcomes.add_argument("--workspace-id")
    owned_analytics = commands.add_parser("sync-owned-analytics")
    owned_analytics.add_argument("--workspace-id")
    owned_analytics.add_argument("--limit", type=int, default=10)
    commands.add_parser("expand-queries")

    serve = commands.add_parser("serve")
    serve.add_argument("--limit", type=int, default=5)
    serve.add_argument("--snapshot-limit", type=int, default=50)
    serve.add_argument("--poll-seconds", type=int, default=60)

    monitor = commands.add_parser("monitor-channel")
    monitor.add_argument("channel_id")
    monitor.add_argument("--workspace-id", default=DEMO_WORKSPACE_ID)
    monitor.add_argument(
        "--relationship",
        default="competitor",
        choices=("owned", "competitor", "reference"),
    )
    monitor.add_argument("--priority", type=int, default=1, choices=range(4))
    monitor.add_argument("--limit", type=int, default=15)

    ingest_channel = commands.add_parser("ingest-channel")
    ingest_channel.add_argument("channel_id")
    ingest_channel.add_argument("--limit", type=int, default=15)
    ingest_channel.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
