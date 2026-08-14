from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    FieldProvenance,
    ProviderFetch,
    Signal,
    Topic,
    TopicVideoMembership,
    TranscriptFetchRun,
    TranscriptPipelineRun,
    TranscriptSegment,
    VideoFeature,
    VideoTranscript,
    YoutubeVideo,
)
from apps.api.provider_operations import (
    SqlAlchemyProviderFetchRecorder,
    SqlAlchemyProviderRoutingPolicy,
)
from apps.worker.video_intelligence import FEATURE_VERSION
from packages.domain import TranscriptResult
from packages.provider_sdk.base.interfaces import TranscriptProvider
from packages.provider_sdk.router import ProviderRouter, ProviderUnavailableError
from packages.provider_sdk.youtube_transcript import YoutubeTranscriptProvider
from packages.transcripts import PROCESSING_VERSION, process_transcript

PIPELINE_INTERVAL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class TranscriptRunResult:
    run_id: str
    reused: bool
    candidates: int
    fetched: int
    unavailable: int
    failed: int
    segments: int


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _fetch_id(raw_ref: str) -> str:
    if not raw_ref.startswith("fetch://"):
        raise ValueError(f"Unsupported provider evidence reference: {raw_ref}")
    return raw_ref.removeprefix("fetch://")


class TranscriptIntelligenceService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        recorder = SqlAlchemyProviderFetchRecorder(session, settings)
        providers: dict[str, TranscriptProvider] = {
            "youtube_transcript": YoutubeTranscriptProvider(recorder=recorder),
        }
        priority = [
            name.strip()
            for name in settings.transcript_provider_priority.split(",")
            if name.strip() in providers
        ]
        if not priority:
            priority = ["youtube_transcript"]
        self._router = ProviderRouter(
            discovery=[],
            metadata=[],
            channels=[],
            comments=[],
            transcripts=[providers[name] for name in priority],
            policy=SqlAlchemyProviderRoutingPolicy(session, settings),
            retry_attempts=settings.provider_retry_attempts,
            retry_base_seconds=settings.provider_retry_base_seconds,
        )
        self._languages = tuple(
            item.strip()
            for item in settings.transcript_preferred_languages.split(",")
            if item.strip()
        ) or ("en",)

    async def run(
        self,
        *,
        force: bool = False,
        limit: int | None = None,
    ) -> TranscriptRunResult:
        started_at = datetime.now(tz=UTC)
        bucket = int(started_at.timestamp()) // PIPELINE_INTERVAL_SECONDS
        suffix = f":manual:{uuid4()}" if force else ""
        key = f"transcripts:{PROCESSING_VERSION}:{bucket}{suffix}"
        existing = self._session.scalar(
            select(TranscriptPipelineRun).where(TranscriptPipelineRun.idempotency_key == key)
        )
        if existing is not None:
            return self._result(existing, reused=True)
        run = TranscriptPipelineRun(
            id=str(uuid4()),
            idempotency_key=key,
            started_at=started_at,
            completed_at=None,
            status="running",
            processing_version=PROCESSING_VERSION,
            candidate_count=0,
            fetched_count=0,
            unavailable_count=0,
            failed_count=0,
            segment_count=0,
            processing_lag_seconds=0,
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            candidates = self.select_candidates(
                limit=limit or self._settings.transcript_candidate_limit,
            )
            run.candidate_count = len(candidates)
            fetched = 0
            unavailable = 0
            failed = 0
            segments = 0
            for video in candidates:
                status, segment_count = await self._fetch_video(
                    video,
                    force=force,
                )
                fetched += int(status == "success")
                unavailable += int(status == "unavailable")
                failed += int(status == "failed")
                segments += segment_count
            completed_at = datetime.now(tz=UTC)
            newest = max(
                (_aware(video.first_discovered_at) for video in candidates),
                default=completed_at,
            )
            run.completed_at = completed_at
            run.status = "success"
            run.fetched_count = fetched
            run.unavailable_count = unavailable
            run.failed_count = failed
            run.segment_count = segments
            run.processing_lag_seconds = max(
                0,
                round((completed_at - newest).total_seconds()),
            )
            self._session.commit()
            return self._result(run, reused=False)
        except Exception as error:
            run.completed_at = datetime.now(tz=UTC)
            run.status = "failed"
            run.error_code = type(error).__name__
            run.error_message = str(error)[:1000]
            self._session.commit()
            raise

    def select_candidates(self, *, limit: int) -> list[YoutubeVideo]:
        rows = self._session.execute(
            select(YoutubeVideo, TopicVideoMembership, Signal, VideoFeature)
            .join(
                TopicVideoMembership,
                TopicVideoMembership.video_id == YoutubeVideo.id,
            )
            .join(Topic, Topic.id == TopicVideoMembership.topic_id)
            .join(Signal, Signal.topic_id == Topic.id)
            .join(
                VideoFeature,
                (VideoFeature.video_id == YoutubeVideo.id)
                & (VideoFeature.feature_version == FEATURE_VERSION),
            )
            .where(
                Topic.source_kind == "live",
                Topic.status == "active",
                Signal.status == "active",
                YoutubeVideo.published_at >= datetime.now(tz=UTC) - timedelta(days=30),
                YoutubeVideo.is_short.is_(False),
                YoutubeVideo.is_live.is_(False),
                YoutubeVideo.duration_seconds.between(60, 7200),
            )
            .order_by(
                desc(Signal.score),
                desc(VideoFeature.outlier_ratio),
                desc(YoutubeVideo.published_at),
            )
        ).all()
        selected: list[YoutubeVideo] = []
        topic_counts: defaultdict[str, int] = defaultdict(int)
        seen: set[str] = set()
        for video, membership, _signal, _feature in rows:
            if video.id in seen or topic_counts[membership.topic_id] >= 2:
                continue
            selected.append(video)
            seen.add(video.id)
            topic_counts[membership.topic_id] += 1
            if len(selected) >= max(1, limit):
                break
        return selected

    async def _fetch_video(
        self,
        video: YoutubeVideo,
        *,
        force: bool,
    ) -> tuple[str, int]:
        suffix = f":manual:{uuid4()}" if force else ""
        key = f"transcript:auto:{video.id}:{','.join(self._languages)}:{PROCESSING_VERSION}{suffix}"
        existing = self._session.scalar(
            select(TranscriptFetchRun).where(TranscriptFetchRun.idempotency_key == key)
        )
        if existing is not None:
            segment_count = (
                int(
                    self._session.scalar(
                        select(func.count(TranscriptSegment.id)).where(
                            TranscriptSegment.transcript_id == existing.transcript_id
                        )
                    )
                    or 0
                )
                if existing.transcript_id
                else 0
            )
            return existing.status, segment_count
        fetch_run = TranscriptFetchRun(
            id=str(uuid4()),
            video_id=video.id,
            provider="auto",
            idempotency_key=key,
            started_at=datetime.now(tz=UTC),
            completed_at=None,
            status="running",
            transcript_id=None,
            provider_fetch_id=None,
            language_policy=",".join(self._languages),
            allow_generated=False,
            error_code=None,
            error_message=None,
        )
        self._session.add(fetch_run)
        self._session.commit()
        try:
            result = await self._router.transcript(
                video.youtube_video_id,
                preferred_languages=self._languages,
                allow_generated=False,
            )
            transcript, segment_count = self._persist(video, result)
            fetch_id = _fetch_id(result.raw_ref)
            provider = self._session.scalar(
                select(ProviderFetch.provider).where(ProviderFetch.id == fetch_id)
            )
            fetch_run.provider = provider or "unknown"
            fetch_run.provider_fetch_id = fetch_id
            fetch_run.transcript_id = transcript.id
            fetch_run.status = "success"
            fetch_run.completed_at = datetime.now(tz=UTC)
            self._session.commit()
            return "success", segment_count
        except ProviderUnavailableError as error:
            message = str(error)
            unavailable = "unavailable" in message.lower()
            fetch_run.status = "unavailable" if unavailable else "failed"
            fetch_run.error_code = "transcript_unavailable" if unavailable else "providers_failed"
            fetch_run.error_message = message[:1000]
            fetch_run.completed_at = datetime.now(tz=UTC)
            self._session.commit()
            return fetch_run.status, 0
        except Exception as error:
            fetch_run.status = "failed"
            fetch_run.error_code = type(error).__name__
            fetch_run.error_message = str(error)[:1000]
            fetch_run.completed_at = datetime.now(tz=UTC)
            self._session.commit()
            return "failed", 0

    def _persist(
        self,
        video: YoutubeVideo,
        result: TranscriptResult,
    ) -> tuple[VideoTranscript, int]:
        content_hash = sha256(result.text.encode()).hexdigest()
        processed = process_transcript(
            title=video.title,
            full_text=result.text,
            segments=result.segments,
        )
        transcript = self._session.scalar(
            select(VideoTranscript).where(VideoTranscript.video_id == video.id)
        )
        fetch_id = _fetch_id(result.raw_ref)
        now = datetime.now(tz=UTC)
        if transcript is None:
            transcript = VideoTranscript(
                id=str(uuid4()),
                video_id=video.id,
                language=result.language,
                transcript_type=result.transcript_type,
                provider="youtube_transcript",
                provider_fetch_id=fetch_id,
                full_text=result.text,
                content_hash=content_hash,
                quality_score=result.quality_score,
                generated_cost=result.generated_cost,
                fetched_at=now,
                model_name=result.model_name,
                summary_json=processed.summary,
                entities_json=processed.entities,
                key_claims_json=processed.key_claims,
                use_cases_json=processed.use_cases,
                comparisons_json=processed.comparisons,
                unanswered_questions_json=processed.unanswered_questions,
                narrative_angle=processed.narrative_angle,
                content_format=processed.content_format,
                processing_version=PROCESSING_VERSION,
                created_at=now,
            )
            self._session.add(transcript)
            self._session.flush()
        else:
            transcript.language = result.language
            transcript.transcript_type = result.transcript_type
            transcript.provider = "youtube_transcript"
            transcript.provider_fetch_id = fetch_id
            transcript.full_text = result.text
            transcript.content_hash = content_hash
            transcript.quality_score = result.quality_score
            transcript.generated_cost = result.generated_cost
            transcript.fetched_at = now
            transcript.model_name = result.model_name
            transcript.summary_json = processed.summary
            transcript.entities_json = processed.entities
            transcript.key_claims_json = processed.key_claims
            transcript.use_cases_json = processed.use_cases
            transcript.comparisons_json = processed.comparisons
            transcript.unanswered_questions_json = processed.unanswered_questions
            transcript.narrative_angle = processed.narrative_angle
            transcript.content_format = processed.content_format
            transcript.processing_version = PROCESSING_VERSION
            self._session.execute(
                delete(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id)
            )
            self._session.flush()
        for segment in processed.segments:
            self._session.add(
                TranscriptSegment(
                    id=str(uuid4()),
                    transcript_id=transcript.id,
                    position=segment.position,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    text=segment.text,
                    embedding_json=segment.embedding,
                    is_evidence=segment.is_evidence,
                    segment_hash=segment.content_hash,
                )
            )
        self._record_provenance(transcript, fetch_id, now)
        self._session.commit()
        return transcript, len(processed.segments)

    def _record_provenance(
        self,
        transcript: VideoTranscript,
        fetch_id: str,
        observed_at: datetime,
    ) -> None:
        fields = {
            "language": transcript.language,
            "transcript_type": transcript.transcript_type,
            "full_text": transcript.content_hash,
            "quality_score": transcript.quality_score,
        }
        for field_name, value in fields.items():
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            self._session.add(
                FieldProvenance(
                    id=str(uuid4()),
                    entity_type="transcript",
                    entity_id=transcript.id,
                    field_name=field_name,
                    provider_fetch_id=fetch_id,
                    observed_at=observed_at,
                    confidence=transcript.quality_score,
                    value_hash=sha256(encoded.encode()).hexdigest(),
                )
            )

    def operational_metrics(self) -> dict[str, int | float | str | None]:
        latest = self._session.scalar(
            select(TranscriptPipelineRun).order_by(desc(TranscriptPipelineRun.started_at))
        )
        live_video_count = int(
            self._session.scalar(
                select(func.count(func.distinct(TopicVideoMembership.video_id)))
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        transcript_count = int(
            self._session.scalar(
                select(func.count(func.distinct(VideoTranscript.video_id)))
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == VideoTranscript.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        topics_with_transcript = int(
            self._session.scalar(
                select(func.count(func.distinct(TopicVideoMembership.topic_id)))
                .join(
                    VideoTranscript,
                    VideoTranscript.video_id == TopicVideoMembership.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        segment_count = int(
            self._session.scalar(
                select(func.count(func.distinct(TranscriptSegment.id)))
                .join(
                    VideoTranscript,
                    VideoTranscript.id == TranscriptSegment.transcript_id,
                )
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == VideoTranscript.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
            )
            or 0
        )
        evidence_count = int(
            self._session.scalar(
                select(func.count(func.distinct(TranscriptSegment.id)))
                .join(
                    VideoTranscript,
                    VideoTranscript.id == TranscriptSegment.transcript_id,
                )
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == VideoTranscript.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(
                    Topic.source_kind == "live",
                    TranscriptSegment.is_evidence.is_(True),
                )
            )
            or 0
        )
        type_counts: dict[str, int] = {
            transcript_type: int(count)
            for transcript_type, count in self._session.execute(
                select(
                    VideoTranscript.transcript_type,
                    func.count(func.distinct(VideoTranscript.id)),
                )
                .join(
                    TopicVideoMembership,
                    TopicVideoMembership.video_id == VideoTranscript.video_id,
                )
                .join(Topic, Topic.id == TopicVideoMembership.topic_id)
                .where(Topic.source_kind == "live")
                .group_by(VideoTranscript.transcript_type)
            ).all()
        }
        return {
            "eligible_videos": live_video_count,
            "transcript_count": transcript_count,
            "coverage_percent": round(
                transcript_count / live_video_count * 100,
                1,
            )
            if live_video_count
            else 0,
            "native_count": int(type_counts.get("native", 0)),
            "auto_caption_count": int(type_counts.get("auto-caption", 0)),
            "generated_count": int(type_counts.get("generated", 0)),
            "segment_count": segment_count,
            "evidence_segment_count": evidence_count,
            "topics_with_transcript": topics_with_transcript,
            "unavailable_videos": int(
                self._session.scalar(
                    select(func.count(func.distinct(TranscriptFetchRun.video_id))).where(
                        TranscriptFetchRun.status == "unavailable"
                    )
                )
                or 0
            ),
            "failed_fetches": int(
                self._session.scalar(
                    select(func.count(TranscriptFetchRun.id)).where(
                        TranscriptFetchRun.status == "failed"
                    )
                )
                or 0
            ),
            "latest_run_status": latest.status if latest is not None else None,
            "latest_run_at": (
                _aware(latest.completed_at or latest.started_at).isoformat()
                if latest is not None
                else None
            ),
            "processing_lag_seconds": (latest.processing_lag_seconds if latest is not None else 0),
        }

    @staticmethod
    def _result(
        run: TranscriptPipelineRun,
        *,
        reused: bool,
    ) -> TranscriptRunResult:
        return TranscriptRunResult(
            run_id=run.id,
            reused=reused,
            candidates=run.candidate_count,
            fetched=run.fetched_count,
            unavailable=run.unavailable_count,
            failed=run.failed_count,
            segments=run.segment_count,
        )
