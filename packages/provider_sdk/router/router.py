from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from hashlib import sha256
from time import monotonic
from typing import Any, TypeVar

from packages.domain import (
    ChannelMetadata,
    CommentRecord,
    DiscoveredVideo,
    DiscoveryQuery,
    TranscriptResult,
    VideoMetadata,
)
from packages.provider_sdk.base.interfaces import (
    ChannelProvider,
    CommentProvider,
    DiscoveryProvider,
    RecentUploadProvider,
    TranscriptProvider,
    VideoMetadataProvider,
)
from packages.provider_sdk.router.policy import (
    OrderedProviderRoutingPolicy,
    ProviderRoutingPolicy,
    RouteAttempt,
    SkippedProvider,
)

T = TypeVar("T")


class ProviderUnavailableError(RuntimeError):
    pass


class ProviderRouter:
    """Capability router with bounded retries, circuit-aware ordering, and fallback."""

    def __init__(
        self,
        *,
        discovery: Sequence[DiscoveryProvider],
        metadata: Sequence[VideoMetadataProvider],
        comments: Sequence[CommentProvider],
        transcripts: Sequence[TranscriptProvider],
        channels: Sequence[ChannelProvider] = (),
        recent_uploads: Sequence[RecentUploadProvider] | None = None,
        policy: ProviderRoutingPolicy | None = None,
        retry_attempts: int = 3,
        retry_base_seconds: float = 0.15,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._discovery = list(discovery)
        self._metadata = list(metadata)
        self._channels = list(channels)
        self._recent_uploads = (
            list(recent_uploads) if recent_uploads is not None else list(channels)
        )
        self._comments = list(comments)
        self._transcripts = list(transcripts)
        self._policy = policy or OrderedProviderRoutingPolicy()
        self._retry_attempts = max(1, retry_attempts)
        self._retry_base_seconds = max(0, retry_base_seconds)
        self._sleep = sleep
        self._jitter = jitter

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredVideo]:
        return list(
            await self._execute(
                capability="discovery",
                operation_key=self._operation_key(
                    "search",
                    query.query,
                    query.country,
                    query.language,
                    query.published_after,
                    query.max_results,
                    query.sort,
                ),
                providers=self._discovery,
                call=lambda provider: provider.search(query),
            )
        )

    async def enrich_videos(self, video_ids: list[str]) -> list[VideoMetadata]:
        return list(
            await self._execute(
                capability="metadata",
                operation_key=self._operation_key("videos", *video_ids),
                providers=self._metadata,
                call=lambda provider: provider.fetch_videos(video_ids),
            )
        )

    async def enrich_channels(self, channel_ids: list[str]) -> list[ChannelMetadata]:
        return list(
            await self._execute(
                capability="channels",
                operation_key=self._operation_key("channels", *channel_ids),
                providers=self._channels,
                call=lambda provider: provider.fetch_channels(channel_ids),
            )
        )

    async def recent_uploads(
        self,
        channel_id: str,
        *,
        published_after: datetime | None = None,
        limit: int = 50,
    ) -> list[DiscoveredVideo]:
        return list(
            await self._execute(
                capability="channels",
                operation_key=self._operation_key(
                    "recent_uploads",
                    channel_id,
                    published_after,
                    limit,
                ),
                providers=self._recent_uploads,
                call=lambda provider: provider.list_recent_uploads(
                    channel_id,
                    published_after,
                    limit,
                ),
            )
        )

    async def comments(
        self,
        video_id: str,
        *,
        order: str = "relevance",
        limit: int = 100,
        include_replies: bool = False,
    ) -> list[CommentRecord]:
        return list(
            await self._execute(
                capability="comments",
                operation_key=self._operation_key(
                    "comments",
                    video_id,
                    order,
                    limit,
                    include_replies,
                ),
                providers=self._comments,
                call=lambda provider: provider.fetch_comments(
                    video_id,
                    order=order,
                    limit=limit,
                    include_replies=include_replies,
                ),
                terminal_reasons={"commentsDisabled"},
            )
        )

    async def transcript(
        self,
        video_id: str,
        *,
        preferred_languages: Sequence[str] = ("en",),
        allow_generated: bool = False,
    ) -> TranscriptResult:
        return await self._execute(
            capability="transcripts",
            operation_key=self._operation_key(
                "transcript",
                video_id,
                *preferred_languages,
                allow_generated,
            ),
            providers=self._transcripts,
            call=lambda provider: provider.fetch_transcript(
                video_id,
                preferred_languages=preferred_languages,
                allow_generated=allow_generated,
            ),
        )

    async def _execute(
        self,
        *,
        capability: str,
        operation_key: str,
        providers: Sequence[Any],
        call: Callable[[Any], Awaitable[T]],
        terminal_reasons: set[str] | None = None,
    ) -> T:
        if not providers:
            raise ProviderUnavailableError(f"No {capability} provider is configured")
        by_name = {provider.name: provider for provider in providers}
        plan = self._policy.rank(capability, tuple(by_name))
        attempts: list[RouteAttempt] = []
        skipped = list(plan.skipped)
        errors: list[str] = []
        terminal_reasons = terminal_reasons or set()

        for provider_name in plan.providers:
            provider = by_name.get(provider_name)
            if provider is None:
                skipped.append(SkippedProvider(provider_name, "not_configured"))
                continue
            for attempt_number in range(1, self._retry_attempts + 1):
                started = monotonic()
                try:
                    result = await call(provider)
                    attempts.append(
                        RouteAttempt(
                            provider=provider_name,
                            attempt=attempt_number,
                            status="success",
                            reason="ok",
                            latency_ms=round((monotonic() - started) * 1000),
                        )
                    )
                    self._policy.record_decision(
                        capability=capability,
                        operation_key=operation_key,
                        selected_provider=provider_name,
                        attempts=attempts,
                        skipped=skipped,
                        status="success",
                        reason="fallback_success"
                        if len({a.provider for a in attempts}) > 1 or skipped
                        else "ok",
                    )
                    return result
                except Exception as error:
                    reason = self._error_reason(error)
                    attempts.append(
                        RouteAttempt(
                            provider=provider_name,
                            attempt=attempt_number,
                            status="failed",
                            reason=reason,
                            latency_ms=round((monotonic() - started) * 1000),
                        )
                    )
                    errors.append(f"{provider_name}:{reason}")
                    if reason in terminal_reasons:
                        self._policy.record_decision(
                            capability=capability,
                            operation_key=operation_key,
                            selected_provider=None,
                            attempts=attempts,
                            skipped=skipped,
                            status="terminal",
                            reason=reason,
                        )
                        message = (
                            "Comments are disabled for this video"
                            if reason == "commentsDisabled"
                            else f"{capability} request is terminal: {reason}"
                        )
                        raise ProviderUnavailableError(message) from error
                    if not self._is_transient(reason) or attempt_number >= self._retry_attempts:
                        break
                    delay = self._retry_base_seconds * (2 ** (attempt_number - 1))
                    await self._sleep(delay + delay * self._jitter())

        reason = "all_providers_failed" if attempts else "all_providers_skipped"
        self._policy.record_decision(
            capability=capability,
            operation_key=operation_key,
            selected_provider=None,
            attempts=attempts,
            skipped=skipped,
            status="failed",
            reason=reason,
        )
        details = ", ".join(errors) or ", ".join(
            f"{item.provider}:{item.reason}" for item in skipped
        )
        raise ProviderUnavailableError(f"All {capability} providers failed ({details})")

    @staticmethod
    def _operation_key(*parts: object) -> str:
        value = "|".join(str(part) for part in parts)
        digest = sha256(value.encode()).hexdigest()[:20]
        return f"{str(parts[0])[:48]}:{digest}"

    @staticmethod
    def _error_reason(error: Exception) -> str:
        reason = getattr(error, "reason", None)
        if isinstance(reason, str) and reason:
            return reason
        cause = error.__cause__
        if cause is not None and cause.__class__.__module__.startswith("httpx"):
            return "network_error"
        return type(error).__name__

    @staticmethod
    def _is_transient(reason: str) -> bool:
        normalized = reason.lower()
        return normalized in {
            "network_error",
            "timeout",
            "ratelimitexceeded",
            "backenderror",
            "internalerror",
            "serviceunavailable",
            "toomanyrequests",
            "provider_error",
            "http_429",
            "http_500",
            "http_502",
            "http_503",
            "http_504",
        }
