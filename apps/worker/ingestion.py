from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    ChannelBaseline,
    DiscoveryQueryRecord,
    DiscoveryRun,
    FieldProvenance,
    ProviderFetch,
    VideoDiscoveryOccurrence,
    WorkspaceChannel,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.provider_operations import (
    SqlAlchemyProviderFetchRecorder,
    SqlAlchemyProviderRoutingPolicy,
)
from apps.worker.video_intelligence import VideoIntelligenceService
from packages.domain import (
    ChannelMetadata,
    DiscoveredVideo,
    DiscoveryQuery,
    VideoMetadata,
)
from packages.provider_sdk.base.interfaces import DiscoveryProvider, RecentUploadProvider
from packages.provider_sdk.router import ProviderRouter
from packages.provider_sdk.youtube_official import YoutubeOfficialProvider
from packages.provider_sdk.youtube_web import YoutubeWebDiscoveryProvider

DEFAULT_QUERIES: tuple[tuple[str, str, int], ...] = (
    ("AI agent recurring task real workflow", "Applied agents", 1),
    ("AI agent beginner no code", "Beginner agents", 1),
    ("new open source AI model release", "Model releases", 1),
    ("free local unlimited AI video generator", "Local AI video", 1),
    ("coding agent production deployment", "Production coding", 2),
    ("AI tool benchmark independent test", "Tool evaluation", 2),
    ("AI model security failure", "AI safety", 2),
    ("humanoid robotics real world demo", "Robotics", 3),
)

SUPERSEDED_BROAD_QUERIES = {
    "AI coding agents",
    "new AI models",
    "AI agent automation",
    "local AI video generation",
    "AI creator tools",
    "AI developer tools",
    "AI productivity workflow",
    "AI robotics demo",
}


@dataclass(frozen=True)
class IngestionResult:
    run_id: str
    source: str
    result_count: int
    unique_video_count: int
    retained_video_count: int
    estimated_cost: float
    status: str


@dataclass(frozen=True)
class NormalizedBatch:
    unique_video_count: int
    retained_video_count: int
    fetch_ids: tuple[str, ...]


@dataclass(frozen=True)
class HistoryBackfillResult:
    channels_attempted: int
    channels_completed: int
    videos_retained: int


def _fetch_id(raw_ref: str) -> str:
    prefix = "fetch://"
    if not raw_ref.startswith(prefix):
        raise ValueError(f"Provider result has an unsupported raw reference: {raw_ref}")
    return raw_ref[len(prefix) :]


def _value_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(encoded.encode()).hexdigest()


def _interval_for_priority(priority: int) -> int:
    return {0: 900, 1: 3600, 2: 14_400, 3: 86_400}.get(priority, 14_400)


class IngestionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._recorder = SqlAlchemyProviderFetchRecorder(session, settings)
        self._discovery = YoutubeWebDiscoveryProvider(recorder=self._recorder)
        self._metadata = YoutubeOfficialProvider(
            api_key=settings.youtube_api_key,
            recorder=self._recorder,
        )
        providers: dict[str, DiscoveryProvider] = {
            "youtube_web": self._discovery,
            "youtube_official": self._metadata,
        }
        discovery_priority: list[DiscoveryProvider] = [
            providers[name.strip()]
            for name in settings.discovery_provider_priority.split(",")
            if name.strip() in providers
            and (name.strip() != "youtube_official" or settings.youtube_api_key)
        ]
        if not discovery_priority:
            discovery_priority = [self._discovery]
        policy = SqlAlchemyProviderRoutingPolicy(session, settings)
        self._router = ProviderRouter(
            discovery=discovery_priority,
            metadata=[self._metadata],
            channels=[self._metadata],
            comments=[],
            transcripts=[],
            policy=policy,
            retry_attempts=settings.provider_retry_attempts,
            retry_base_seconds=settings.provider_retry_base_seconds,
        )
        self._official_discovery_top_up = bool(
            settings.youtube_api_key
            and discovery_priority
            and discovery_priority[0].name != "youtube_official"
        )
        recent_providers: list[RecentUploadProvider] = [self._discovery]
        if settings.youtube_api_key:
            recent_providers.append(self._metadata)
        self._recent_router = ProviderRouter(
            discovery=[],
            metadata=[],
            channels=[],
            recent_uploads=recent_providers,
            comments=[],
            transcripts=[],
            policy=policy,
            retry_attempts=settings.provider_retry_attempts,
            retry_base_seconds=settings.provider_retry_base_seconds,
        )

    def seed_default_queries(self) -> list[DiscoveryQueryRecord]:
        now = datetime.now(tz=UTC)
        existing = {
            row.query: row for row in self._session.scalars(select(DiscoveryQueryRecord)).all()
        }
        for query in SUPERSEDED_BROAD_QUERIES:
            row = existing.get(query)
            if row is not None:
                row.active = False
                row.updated_at = now
        rows: list[DiscoveryQueryRecord] = []
        for query, category, priority in DEFAULT_QUERIES:
            row = existing.get(query)
            if row is None:
                row = DiscoveryQueryRecord(
                    id=str(uuid4()),
                    query=query,
                    category=category,
                    priority=priority,
                    country="US",
                    language="en",
                    active=True,
                    source="manual",
                    minimum_interval_seconds=_interval_for_priority(priority),
                    expires_at=None,
                    last_run_at=None,
                    next_run_at=now,
                    historical_yield=0,
                    cost_per_retained_video=0,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(row)
            else:
                row.active = True
                row.priority = priority
                row.minimum_interval_seconds = _interval_for_priority(priority)
                row.next_run_at = min(row.next_run_at, now)
                row.updated_at = now
            rows.append(row)
        self._session.commit()
        return rows

    def create_query(
        self,
        *,
        query: str,
        category: str,
        priority: int,
        country: str = "US",
        language: str = "en",
    ) -> DiscoveryQueryRecord:
        normalized = " ".join(query.split())
        existing = self._session.scalar(
            select(DiscoveryQueryRecord).where(DiscoveryQueryRecord.query == normalized)
        )
        if existing is not None:
            return existing
        now = datetime.now(tz=UTC)
        row = DiscoveryQueryRecord(
            id=str(uuid4()),
            query=normalized,
            category=category,
            priority=priority,
            country=country,
            language=language,
            active=True,
            source="manual",
            minimum_interval_seconds=_interval_for_priority(priority),
            expires_at=None,
            last_run_at=None,
            next_run_at=now,
            historical_yield=0,
            cost_per_retained_video=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.commit()
        return row

    async def _discover_for_query(
        self,
        query: DiscoveryQueryRecord,
        request: DiscoveryQuery,
    ) -> list[DiscoveredVideo]:
        discovered = list(await self._router.discover(request))
        if (
            not self._official_discovery_top_up
            or query.last_run_at is not None
            or len(discovered) >= request.max_results
        ):
            return discovered
        try:
            official = list(await self._metadata.search(replace(request, sort="date")))
        except Exception:
            return discovered
        return list(
            {
                item.video_id: item
                for item in (
                    *discovered,
                    *official,
                )
            }.values()
        )[: request.max_results]

    async def run_query(
        self,
        query: DiscoveryQueryRecord,
        *,
        force: bool = False,
        max_results: int | None = None,
    ) -> IngestionResult:
        now = datetime.now(tz=UTC)
        interval = max(query.minimum_interval_seconds, 60)
        bucket = int(now.timestamp()) // interval
        suffix = f":manual:{uuid4()}" if force else ""
        idempotency_key = f"discovery:auto:{query.id}:{bucket}{suffix}"
        existing = self._session.scalar(
            select(DiscoveryRun).where(DiscoveryRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return self._result(existing, query.query)
        run = DiscoveryRun(
            id=str(uuid4()),
            query_id=query.id,
            channel_id=None,
            provider="auto",
            idempotency_key=idempotency_key,
            started_at=now,
            completed_at=None,
            status="running",
            result_count=0,
            unique_video_count=0,
            retained_video_count=0,
            estimated_cost=0,
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            request = DiscoveryQuery(
                query=query.query,
                country=query.country,
                language=query.language,
                published_after=now - timedelta(days=14),
                max_results=max_results or self._settings.ingestion_default_query_limit,
                sort="relevance",
            )
            discovered = await self._discover_for_query(query, request)
            normalized = await self._enrich_and_normalize(
                discovered,
                query=query,
                country=query.country,
                language=query.language,
            )
            self._complete_run(run, discovered=discovered, normalized=normalized)
            self._schedule_next(query, now=now, retained=normalized.retained_video_count)
            self._session.commit()
            return self._result(run, query.query)
        except Exception as error:
            self._session.rollback()
            failed_run = self._session.get(DiscoveryRun, run.id)
            if failed_run is None:
                raise
            failed_run.status = "failed"
            failed_run.completed_at = datetime.now(tz=UTC)
            failed_run.error_code = type(error).__name__
            failed_run.error_message = str(error)[:1000]
            self._session.commit()
            raise

    async def monitor_channel(
        self,
        *,
        workspace_id: str,
        youtube_channel_id: str,
        relationship: str = "competitor",
        priority: int = 1,
    ) -> YoutubeChannel:
        metadata = list(await self._router.enrich_channels([youtube_channel_id]))
        if not metadata:
            raise ValueError("YouTube channel was not found")
        channel = self._upsert_channel(metadata[0], observed_at=datetime.now(tz=UTC))
        workspace_row = self._session.get(WorkspaceChannel, (workspace_id, channel.id))
        if workspace_row is None:
            workspace_row = WorkspaceChannel(
                workspace_id=workspace_id,
                channel_id=channel.id,
                relationship=relationship,
                priority=priority,
                active=True,
                last_ingested_at=None,
                next_ingestion_at=datetime.now(tz=UTC),
            )
            self._session.add(workspace_row)
        else:
            workspace_row.relationship = relationship
            workspace_row.priority = priority
            workspace_row.active = True
            workspace_row.next_ingestion_at = datetime.now(tz=UTC)
        if relationship == "owned":
            for existing_owned in self._session.scalars(
                select(WorkspaceChannel).where(
                    WorkspaceChannel.workspace_id == workspace_id,
                    WorkspaceChannel.relationship == "owned",
                    WorkspaceChannel.channel_id != channel.id,
                    WorkspaceChannel.active.is_(True),
                )
            ):
                existing_owned.active = False
        self._session.commit()
        self._record_channel_provenance(channel, metadata[0])
        self._session.commit()
        return channel

    async def backfill_channel_histories(
        self,
        *,
        limit_channels: int = 3,
        uploads_per_channel: int = 15,
    ) -> HistoryBackfillResult:
        channels = list(
            self._session.scalars(
                select(YoutubeChannel)
                .where(~YoutubeChannel.youtube_channel_id.startswith("UCESDEMO"))
                .order_by(YoutubeChannel.last_observed_at.desc())
            )
        )
        pending: list[YoutubeChannel] = []
        for channel in channels:
            marker = self._session.scalar(
                select(ChannelBaseline.id).where(
                    ChannelBaseline.channel_id == channel.id,
                    ChannelBaseline.metric_name == "history_backfill_marker",
                    ChannelBaseline.version == "channel-baseline-v1",
                )
            )
            if marker is None:
                pending.append(channel)
            if len(pending) >= max(1, limit_channels):
                break
        completed = 0
        retained = 0
        for channel in pending:
            discovered = list(
                await self._recent_router.recent_uploads(
                    channel.youtube_channel_id,
                    published_after=datetime.now(tz=UTC) - timedelta(days=180),
                    limit=max(5, min(uploads_per_channel, 15)),
                )
            )
            normalized = await self._enrich_and_normalize(
                discovered,
                query=None,
                country=channel.country,
                language=channel.default_language,
            )
            self._session.add(
                ChannelBaseline(
                    id=str(uuid4()),
                    channel_id=channel.id,
                    window="history",
                    metric_name="history_backfill_marker",
                    metric_value=float(normalized.retained_video_count),
                    sample_size=normalized.retained_video_count,
                    calculated_at=datetime.now(tz=UTC),
                    version="channel-baseline-v1",
                )
            )
            self._session.commit()
            completed += 1
            retained += normalized.retained_video_count
        return HistoryBackfillResult(
            channels_attempted=len(pending),
            channels_completed=completed,
            videos_retained=retained,
        )

    async def ingest_monitored_channel(
        self,
        workspace_channel: WorkspaceChannel,
        *,
        force: bool = False,
        max_results: int = 15,
    ) -> IngestionResult:
        channel = self._session.get(YoutubeChannel, workspace_channel.channel_id)
        if channel is None:
            raise ValueError("Monitored channel does not exist")
        now = datetime.now(tz=UTC)
        interval = _interval_for_priority(workspace_channel.priority)
        bucket = int(now.timestamp()) // interval
        suffix = f":manual:{uuid4()}" if force else ""
        idempotency_key = f"channel:auto:{channel.youtube_channel_id}:{bucket}{suffix}"
        existing = self._session.scalar(
            select(DiscoveryRun).where(DiscoveryRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return self._result(existing, f"uploads:{channel.youtube_channel_id}")
        run = DiscoveryRun(
            id=str(uuid4()),
            query_id=None,
            channel_id=channel.id,
            provider="auto",
            idempotency_key=idempotency_key,
            started_at=now,
            completed_at=None,
            status="running",
            result_count=0,
            unique_video_count=0,
            retained_video_count=0,
            estimated_cost=0,
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            discovered = list(
                await self._recent_router.recent_uploads(
                    channel.youtube_channel_id,
                    published_after=now - timedelta(days=30),
                    limit=max_results,
                )
            )
            normalized = await self._enrich_and_normalize(
                discovered,
                query=None,
                country=channel.country,
                language=channel.default_language,
            )
            self._complete_run(run, discovered=discovered, normalized=normalized)
            workspace_channel.last_ingested_at = now
            workspace_channel.next_ingestion_at = now + timedelta(seconds=interval)
            self._session.commit()
            return self._result(run, f"uploads:{channel.youtube_channel_id}")
        except Exception as error:
            self._session.rollback()
            failed_run = self._session.get(DiscoveryRun, run.id)
            if failed_run is None:
                raise
            failed_run.status = "failed"
            failed_run.completed_at = datetime.now(tz=UTC)
            failed_run.error_code = type(error).__name__
            failed_run.error_message = str(error)[:1000]
            self._session.commit()
            raise

    async def run_due(self, *, limit: int = 5) -> list[IngestionResult]:
        now = datetime.now(tz=UTC)
        queries = list(
            self._session.scalars(
                select(DiscoveryQueryRecord)
                .where(
                    DiscoveryQueryRecord.active.is_(True),
                    DiscoveryQueryRecord.next_run_at <= now,
                    or_(
                        DiscoveryQueryRecord.expires_at.is_(None),
                        DiscoveryQueryRecord.expires_at > now,
                    ),
                )
                .order_by(DiscoveryQueryRecord.priority, DiscoveryQueryRecord.next_run_at)
                .limit(limit)
            )
        )
        results = [await self.run_query(row) for row in queries]
        remaining = max(0, limit - len(results))
        if remaining:
            monitored = list(
                self._session.scalars(
                    select(WorkspaceChannel)
                    .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
                    .where(
                        WorkspaceChannel.active.is_(True),
                        or_(
                            WorkspaceChannel.next_ingestion_at.is_(None),
                            WorkspaceChannel.next_ingestion_at <= now,
                        ),
                        ~YoutubeChannel.youtube_channel_id.startswith("UCESDEMO"),
                    )
                    .order_by(WorkspaceChannel.priority)
                    .limit(remaining)
                )
            )
            results.extend([await self.ingest_monitored_channel(row) for row in monitored])
        return results

    async def replay_fetch(self, fetch: ProviderFetch) -> IngestionResult | None:
        if fetch.capability != "discovery":
            return None
        query = self._session.scalar(
            select(DiscoveryQueryRecord)
            .join(DiscoveryRun, DiscoveryRun.query_id == DiscoveryQueryRecord.id)
            .where(DiscoveryRun.provider == fetch.provider)
            .order_by(DiscoveryRun.started_at.desc())
        )
        if query is None:
            return None
        return await self.run_query(query, force=True)

    async def _enrich_and_normalize(
        self,
        discovered: list[DiscoveredVideo],
        *,
        query: DiscoveryQueryRecord | None,
        country: str,
        language: str,
    ) -> NormalizedBatch:
        unique_hits = list({item.video_id: item for item in discovered}.values())
        if not unique_hits:
            fetch_ids = tuple({_fetch_id(item.raw_ref) for item in discovered})
            return NormalizedBatch(0, 0, fetch_ids)
        metadata = list(await self._router.enrich_videos([item.video_id for item in unique_hits]))
        channel_ids = list(dict.fromkeys(item.channel_id for item in metadata))
        channels = list(await self._router.enrich_channels(channel_ids))
        channel_metadata = {item.channel_id: item for item in channels}
        hit_by_id = {item.video_id: item for item in unique_hits}
        observed_at = datetime.now(tz=UTC)
        intelligence = VideoIntelligenceService(
            self._session,
            self._settings,
            metadata_provider=self._metadata,
        )
        internal_links: dict[str, list[str]] = {}
        touched_video_ids: list[str] = []
        touched_channel_ids: set[str] = set()
        retained = 0
        for item in metadata:
            channel_evidence = channel_metadata.get(item.channel_id)
            if channel_evidence is None:
                channel_evidence = ChannelMetadata(
                    channel_id=item.channel_id,
                    title=item.channel_title or item.channel_id,
                    subscriber_count=0,
                    country=country,
                    language=language,
                    raw_ref=item.raw_ref,
                    published_at=item.published_at,
                )
            channel = self._upsert_channel(channel_evidence, observed_at=observed_at)
            video = self._upsert_video(item, channel=channel, observed_at=observed_at)
            intelligence.record_snapshot_from_metadata(
                video,
                item,
                observed_at=observed_at,
            )
            intelligence.schedule_video(video, now=observed_at)
            self._record_video_provenance(video, item)
            self._record_channel_provenance(channel, channel_evidence)
            hit = hit_by_id[item.video_id]
            discovery_fetch_id = _fetch_id(hit.raw_ref)
            self._session.add(
                VideoDiscoveryOccurrence(
                    id=str(uuid4()),
                    video_id=video.id,
                    query_id=query.id if query else None,
                    provider_fetch_id=discovery_fetch_id,
                    position=hit.position,
                    country=country,
                    language=language,
                    discovered_at=observed_at,
                )
            )
            internal_links.setdefault(discovery_fetch_id, []).append(video.id)
            internal_links.setdefault(_fetch_id(item.raw_ref), []).append(video.id)
            internal_links.setdefault(_fetch_id(channel_evidence.raw_ref), []).append(channel.id)
            touched_video_ids.append(video.id)
            touched_channel_ids.add(channel.id)
            retained += 1
        self._session.commit()
        for fetch_id, entity_ids in internal_links.items():
            self._recorder.link_entities(
                fetch_id,
                entity_type="normalized_entity",
                entity_ids=entity_ids,
            )
        intelligence.recalculate_channel_baselines(touched_channel_ids)
        intelligence.calculate_video_features(touched_video_ids)
        self._session.commit()
        all_fetch_ids = tuple(
            {
                *(_fetch_id(item.raw_ref) for item in discovered),
                *(_fetch_id(item.raw_ref) for item in metadata),
                *(_fetch_id(item.raw_ref) for item in channels),
            }
        )
        return NormalizedBatch(
            unique_video_count=len(unique_hits),
            retained_video_count=retained,
            fetch_ids=all_fetch_ids,
        )

    def _upsert_channel(
        self,
        item: ChannelMetadata,
        *,
        observed_at: datetime,
    ) -> YoutubeChannel:
        row = self._session.scalar(
            select(YoutubeChannel).where(YoutubeChannel.youtube_channel_id == item.channel_id)
        )
        if row is None:
            row = YoutubeChannel(
                id=str(uuid4()),
                youtube_channel_id=item.channel_id,
                canonical_url=f"https://www.youtube.com/channel/{item.channel_id}",
                title=item.title,
                description=item.description,
                country=item.country or "US",
                default_language=item.language or "en",
                subscriber_count=item.subscriber_count,
                video_count=item.video_count,
                view_count=item.view_count,
                published_at=item.published_at or observed_at,
                last_observed_at=observed_at,
                created_at=observed_at,
                updated_at=observed_at,
            )
            self._session.add(row)
            self._session.flush()
        else:
            row.title = item.title or row.title
            row.description = item.description or row.description
            row.country = item.country or row.country
            row.default_language = item.language or row.default_language
            row.subscriber_count = item.subscriber_count
            row.video_count = item.video_count
            row.view_count = item.view_count
            row.last_observed_at = observed_at
            row.updated_at = observed_at
        return row

    def _upsert_video(
        self,
        item: VideoMetadata,
        *,
        channel: YoutubeChannel,
        observed_at: datetime,
    ) -> YoutubeVideo:
        row = self._session.scalar(
            select(YoutubeVideo).where(YoutubeVideo.youtube_video_id == item.video_id)
        )
        if row is None:
            row = YoutubeVideo(
                id=str(uuid4()),
                youtube_video_id=item.video_id,
                channel_id=channel.id,
                canonical_url=f"https://www.youtube.com/watch?v={item.video_id}",
                title=item.title,
                description=item.description,
                published_at=item.published_at,
                duration_seconds=item.duration_seconds,
                default_language=item.default_language,
                category_id=item.category_id,
                is_short=item.duration_seconds <= 60,
                is_live=item.is_live,
                thumbnail_url=item.thumbnail_url,
                first_discovered_at=observed_at,
                discovery_lag_seconds=max(
                    0,
                    round((observed_at - item.published_at).total_seconds()),
                ),
                last_observed_at=observed_at,
                created_at=observed_at,
                updated_at=observed_at,
            )
            self._session.add(row)
            self._session.flush()
        else:
            row.channel_id = channel.id
            row.title = item.title
            row.description = item.description
            row.published_at = item.published_at
            row.duration_seconds = item.duration_seconds
            row.default_language = item.default_language
            row.category_id = item.category_id
            row.is_short = item.duration_seconds <= 60
            row.is_live = item.is_live
            row.thumbnail_url = item.thumbnail_url
            row.last_observed_at = observed_at
            row.updated_at = observed_at
        return row

    def _record_video_provenance(
        self,
        video: YoutubeVideo,
        metadata: VideoMetadata,
    ) -> None:
        fetch_id = _fetch_id(metadata.raw_ref)
        fields = {
            "channel_id": metadata.channel_id,
            "title": metadata.title,
            "description": metadata.description,
            "published_at": metadata.published_at,
            "duration_seconds": metadata.duration_seconds,
            "view_count": metadata.view_count,
            "like_count": metadata.like_count,
            "comment_count": metadata.comment_count,
            "thumbnail_url": metadata.thumbnail_url,
            "default_language": metadata.default_language,
            "category_id": metadata.category_id,
            "is_live": metadata.is_live,
        }
        for field_name, value in fields.items():
            self._session.add(
                FieldProvenance(
                    id=str(uuid4()),
                    entity_type="video",
                    entity_id=f"youtube:{video.youtube_video_id}",
                    field_name=field_name,
                    provider_fetch_id=fetch_id,
                    observed_at=datetime.now(tz=UTC),
                    confidence=1.0,
                    value_hash=_value_hash(value),
                )
            )

    def _record_channel_provenance(
        self,
        channel: YoutubeChannel,
        metadata: ChannelMetadata,
    ) -> None:
        fetch_id = _fetch_id(metadata.raw_ref)
        fields = {
            "title": metadata.title,
            "description": metadata.description,
            "subscriber_count": metadata.subscriber_count,
            "video_count": metadata.video_count,
            "view_count": metadata.view_count,
            "country": metadata.country,
            "default_language": metadata.language,
        }
        for field_name, value in fields.items():
            self._session.add(
                FieldProvenance(
                    id=str(uuid4()),
                    entity_type="channel",
                    entity_id=f"youtube:{channel.youtube_channel_id}",
                    field_name=field_name,
                    provider_fetch_id=fetch_id,
                    observed_at=datetime.now(tz=UTC),
                    confidence=1.0,
                    value_hash=_value_hash(value),
                )
            )

    def _complete_run(
        self,
        run: DiscoveryRun,
        *,
        discovered: list[DiscoveredVideo],
        normalized: NormalizedBatch,
    ) -> None:
        costs = list(
            self._session.scalars(
                select(ProviderFetch.estimated_cost).where(
                    ProviderFetch.id.in_(normalized.fetch_ids)
                )
            )
        )
        run.completed_at = datetime.now(tz=UTC)
        run.status = "success"
        if discovered:
            discovery_fetch_id = _fetch_id(discovered[0].raw_ref)
            run.provider = (
                self._session.scalar(
                    select(ProviderFetch.provider).where(ProviderFetch.id == discovery_fetch_id)
                )
                or run.provider
            )
        run.result_count = len(discovered)
        run.unique_video_count = normalized.unique_video_count
        run.retained_video_count = normalized.retained_video_count
        run.estimated_cost = sum(costs)

    def _schedule_next(
        self,
        query: DiscoveryQueryRecord,
        *,
        now: datetime,
        retained: int,
    ) -> None:
        digest = int(sha256(query.id.encode()).hexdigest()[:8], 16)
        jitter_limit = max(1, min(900, query.minimum_interval_seconds // 10))
        jitter = digest % jitter_limit
        query.last_run_at = now
        query.next_run_at = now + timedelta(seconds=query.minimum_interval_seconds + jitter)
        query.historical_yield = round(
            retained
            if query.historical_yield == 0
            else query.historical_yield * 0.75 + retained * 0.25,
            2,
        )
        query.cost_per_retained_video = 0 if retained == 0 else query.cost_per_retained_video
        query.updated_at = now

    @staticmethod
    def _result(run: DiscoveryRun, source: str) -> IngestionResult:
        return IngestionResult(
            run_id=run.id,
            source=source,
            result_count=run.result_count,
            unique_video_count=run.unique_video_count,
            retained_video_count=run.retained_video_count,
            estimated_cost=run.estimated_cost,
            status=run.status,
        )
