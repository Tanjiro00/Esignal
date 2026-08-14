from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApiException,
)

from packages.domain import ProviderRequest, TranscriptResult
from packages.provider_sdk.base.observability import ProviderFetchRecorder

PARSER_VERSION = "youtube-transcript-api-v1"
SPACE_PATTERN = re.compile(r"\s+")
NOISE_MARKER_PATTERN = re.compile(
    r"\[(?:music|applause|laughter|silence)\]",
    re.IGNORECASE,
)
SPEAKER_MARKER_PATTERN = re.compile(r"(?:^|\s)>>\s*")


class YoutubeTranscriptProviderError(RuntimeError):
    def __init__(self, message: str, *, reason: str = "provider_error") -> None:
        super().__init__(message)
        self.reason = reason


def _normalized(value: str) -> str:
    without_noise = NOISE_MARKER_PATTERN.sub(" ", value.replace("\u200b", " "))
    without_markers = SPEAKER_MARKER_PATTERN.sub(" ", without_noise)
    return SPACE_PATTERN.sub(" ", without_markers).strip()


def _quality_score(
    segments: list[dict[str, object]],
    *,
    transcript_type: str,
) -> float:
    texts = [_normalized(str(item.get("text", ""))) for item in segments]
    words = " ".join(texts).split()
    nonempty = [text for text in texts if text]
    if not words or not nonempty:
        return 0
    unique_ratio = len(set(nonempty)) / len(nonempty)
    base = 0.95 if transcript_type == "native" else 0.84
    if len(words) < 80:
        base -= 0.15
    if unique_ratio < 0.55:
        base -= 0.12
    noisy = sum(1 for word in words if not any(character.isalnum() for character in word))
    if noisy / len(words) > 0.08:
        base -= 0.08
    return round(min(0.99, max(0.2, base)), 3)


class YoutubeTranscriptProvider:
    """Fetch public YouTube captions without needing a Data API credential."""

    name = "youtube_transcript"

    def __init__(
        self,
        *,
        recorder: ProviderFetchRecorder,
        api: Any | None = None,
    ) -> None:
        self._recorder = recorder
        self._api = api or YouTubeTranscriptApi()

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: Sequence[str],
        allow_generated: bool,
    ) -> TranscriptResult:
        languages = tuple(preferred_languages) or ("en",)
        request = ProviderRequest(
            provider=self.name,
            capability="transcripts",
            endpoint="youtube_transcript_api.fetch",
            parameters={
                "video_id": video_id,
                "preferred_languages": languages,
                # This adapter can read auto-captions, but never generates audio transcripts.
                "allow_external_generation": allow_generated,
            },
            parser_version=PARSER_VERSION,
            estimated_cost=0,
        )
        started_at = datetime.now(tz=UTC)
        try:
            transcript, transcript_type = await asyncio.to_thread(
                self._select_transcript,
                video_id,
                languages,
            )
            fetched = await asyncio.to_thread(transcript.fetch)
            raw_segments = list(fetched.to_raw_data())
            segments: list[dict[str, object]] = []
            normalized_segments: list[tuple[float, float, str]] = []
            for item in raw_segments:
                text = _normalized(str(item.get("text", "")))
                if not text:
                    continue
                start = max(0.0, float(item.get("start", 0)))
                duration = max(0.0, float(item.get("duration", 0)))
                end = start + duration
                segments.append(
                    {
                        "start": round(start, 3),
                        "duration": round(duration, 3),
                        "text": text,
                    }
                )
                normalized_segments.append((round(start, 3), round(end, 3), text))
            full_text = _normalized(" ".join(item[2] for item in normalized_segments))
            if not full_text:
                raise YoutubeTranscriptProviderError(
                    "Transcript contained no usable text",
                    reason="unavailable",
                )
            language = str(getattr(transcript, "language_code", languages[0]))
            completed_at = datetime.now(tz=UTC)
            recorded = self._recorder.record_success(
                request,
                payload={
                    "video_id": video_id,
                    "language": language,
                    "transcript_type": transcript_type,
                    "is_translatable": bool(getattr(transcript, "is_translatable", False)),
                    "segments": segments,
                },
                started_at=started_at,
                completed_at=completed_at,
                http_status=200,
            )
            self._recorder.link_entities(
                recorded.fetch_id,
                entity_type="youtube_video",
                entity_ids=[video_id],
            )
            return TranscriptResult(
                video_id=video_id,
                language=language,
                transcript_type=transcript_type,
                text=full_text,
                segments=tuple(normalized_segments),
                raw_ref=recorded.raw_ref,
                quality_score=_quality_score(
                    segments,
                    transcript_type=transcript_type,
                ),
            )
        except YoutubeTranscriptProviderError:
            raise
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as error:
            self._record_failure(request, started_at, video_id, error, "unavailable")
            raise YoutubeTranscriptProviderError(
                "Public captions are unavailable for this video",
                reason="unavailable",
            ) from error
        except YouTubeTranscriptApiException as error:
            self._record_failure(request, started_at, video_id, error, "provider_error")
            raise YoutubeTranscriptProviderError(
                "YouTube transcript service is temporarily unavailable",
                reason="provider_error",
            ) from error
        except Exception as error:
            self._record_failure(request, started_at, video_id, error, "provider_error")
            raise YoutubeTranscriptProviderError(
                "Transcript provider failed",
                reason="provider_error",
            ) from error

    def _select_transcript(
        self,
        video_id: str,
        languages: tuple[str, ...],
    ) -> tuple[Any, str]:
        available = self._api.list(video_id)
        try:
            return available.find_manually_created_transcript(languages), "native"
        except NoTranscriptFound:
            return available.find_generated_transcript(languages), "auto-caption"

    def _record_failure(
        self,
        request: ProviderRequest,
        started_at: datetime,
        video_id: str,
        error: Exception,
        code: str,
    ) -> None:
        self._recorder.record_failure(
            request,
            payload={"video_id": video_id, "error": type(error).__name__},
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
            http_status=0,
            error_code=code,
            error_message=f"Transcript fetch failed: {type(error).__name__}",
        )
