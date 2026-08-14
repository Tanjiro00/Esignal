from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from packages.domain import DiscoveredVideo, DiscoveryQuery, ProviderRequest
from packages.provider_sdk.base.observability import ProviderFetchRecorder

SEARCH_URL = "https://www.youtube.com/results"
FEED_URL = "https://www.youtube.com/feeds/videos.xml"
PARSER_VERSION = "youtube-web-v1.0.0"


class YoutubeWebProviderError(RuntimeError):
    def __init__(self, message: str, *, reason: str = "provider_error") -> None:
        super().__init__(message)
        self.reason = reason


def _text(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    simple = value.get("simpleText")
    if isinstance(simple, str):
        return simple
    runs = value.get("runs")
    if isinstance(runs, list):
        return (
            "".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)).strip()
            or None
        )
    return None


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _extract_initial_data(html: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for marker in ("var ytInitialData = ", "ytInitialData = "):
        start = html.find(marker)
        if start < 0:
            continue
        start += len(marker)
        try:
            payload, _ = decoder.raw_decode(html[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise YoutubeWebProviderError(
        "YouTube search payload did not contain ytInitialData",
        reason="invalid_payload",
    )


def _relative_published_at(label: str | None, *, now: datetime) -> datetime | None:
    if not label:
        return None
    value = label.lower()
    units = (
        ("minute", "minutes"),
        ("hour", "hours"),
        ("day", "days"),
        ("week", "weeks"),
        ("month", "days"),
        ("year", "days"),
    )
    amount = next((int(token) for token in value.split() if token.isdigit()), None)
    if amount is None:
        return None
    for singular, delta_name in units:
        if singular not in value:
            continue
        if singular == "month":
            amount *= 30
        elif singular == "year":
            amount *= 365
        return now - timedelta(**{delta_name: amount})
    return None


class YoutubeWebDiscoveryProvider:
    name = "youtube_web"

    def __init__(
        self,
        *,
        recorder: ProviderFetchRecorder,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._recorder = recorder
        self._client = client

    async def search(self, query: DiscoveryQuery) -> Sequence[DiscoveredVideo]:
        parameters = {
            "search_query": query.query,
            "hl": query.language,
            "gl": query.country,
        }
        request = ProviderRequest(
            provider=self.name,
            capability="discovery",
            endpoint="youtube.results",
            parameters={
                **parameters,
                "published_after": query.published_after,
                "max_results": query.max_results,
                "sort": query.sort,
            },
            parser_version=PARSER_VERSION,
        )
        started_at = datetime.now(tz=UTC)
        client = self._client or httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={
                "Accept-Language": f"{query.language},en;q=0.8",
                "User-Agent": "Mozilla/5.0 (compatible; EarlySignal/0.2)",
            },
        )
        owns_client = self._client is None
        try:
            response = await client.get(SEARCH_URL, params=parameters)
            completed_at = datetime.now(tz=UTC)
            if response.status_code >= 400:
                self._recorder.record_failure(
                    request,
                    payload={"response_text": response.text},
                    started_at=started_at,
                    completed_at=completed_at,
                    http_status=response.status_code,
                    error_code="http_error",
                    error_message=f"YouTube web returned HTTP {response.status_code}",
                )
                reason = (
                    f"http_{response.status_code}"
                    if response.status_code == 429 or response.status_code >= 500
                    else "http_error"
                )
                raise YoutubeWebProviderError(
                    f"YouTube web returned HTTP {response.status_code}",
                    reason=reason,
                )
            try:
                payload = _extract_initial_data(response.text)
            except YoutubeWebProviderError as error:
                self._recorder.record_failure(
                    request,
                    payload={"response_text": response.text},
                    started_at=started_at,
                    completed_at=completed_at,
                    http_status=response.status_code,
                    error_code="invalid_payload",
                    error_message=str(error),
                )
                raise
            recorded = self._recorder.record_success(
                request,
                payload=payload,
                started_at=started_at,
                completed_at=completed_at,
                http_status=response.status_code,
            )
            try:
                results = self._parse_search(
                    payload,
                    query=query,
                    raw_ref=recorded.raw_ref,
                    observed_at=completed_at,
                )
            except Exception as error:
                self._recorder.mark_parse_failure(
                    recorded.fetch_id,
                    error_code="parser_error",
                    error_message=str(error),
                )
                raise
            self._recorder.link_entities(
                recorded.fetch_id,
                entity_type="youtube_video",
                entity_ids=[item.video_id for item in results],
            )
            return results
        except httpx.HTTPError as error:
            completed_at = datetime.now(tz=UTC)
            self._recorder.record_failure(
                request,
                payload={"network_error": type(error).__name__},
                started_at=started_at,
                completed_at=completed_at,
                http_status=0,
                error_code="network_error",
                error_message=f"YouTube web network error: {type(error).__name__}",
            )
            raise YoutubeWebProviderError(
                "YouTube web discovery is unavailable",
                reason="network_error",
            ) from error
        finally:
            if owns_client:
                await client.aclose()

    def _parse_search(
        self,
        payload: dict[str, Any],
        *,
        query: DiscoveryQuery,
        raw_ref: str,
        observed_at: datetime,
    ) -> list[DiscoveredVideo]:
        results: list[DiscoveredVideo] = []
        seen: set[str] = set()
        for node in _walk(payload):
            renderer = node.get("videoRenderer")
            if not isinstance(renderer, dict):
                continue
            video_id = renderer.get("videoId")
            if not isinstance(video_id, str) or video_id in seen:
                continue
            owner = renderer.get("ownerText")
            owner_run = (
                owner.get("runs", [{}])[0]
                if isinstance(owner, dict) and isinstance(owner.get("runs"), list)
                else {}
            )
            browse = (
                owner_run.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId")
                if isinstance(owner_run, dict)
                else None
            )
            published_at = _relative_published_at(
                _text(renderer.get("publishedTimeText")),
                now=observed_at,
            )
            if query.published_after and published_at and published_at < query.published_after:
                continue
            seen.add(video_id)
            results.append(
                DiscoveredVideo(
                    video_id=video_id,
                    title=_text(renderer.get("title")),
                    channel_id=browse if isinstance(browse, str) else None,
                    channel_title=_text(owner),
                    published_at=published_at,
                    position=len(results) + 1,
                    query=query.query,
                    raw_ref=raw_ref,
                )
            )
            if len(results) >= query.max_results:
                break
        return results

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]:
        request = ProviderRequest(
            provider=self.name,
            capability="channels",
            endpoint="youtube.channel_feed",
            parameters={
                "channel_id": channel_id,
                "published_after": published_after,
                "limit": limit,
            },
            parser_version=PARSER_VERSION,
        )
        started_at = datetime.now(tz=UTC)
        client = self._client or httpx.AsyncClient(timeout=20, follow_redirects=True)
        owns_client = self._client is None
        try:
            response = await client.get(FEED_URL, params={"channel_id": channel_id})
            completed_at = datetime.now(tz=UTC)
            if response.status_code >= 400:
                self._recorder.record_failure(
                    request,
                    payload={"response_text": response.text},
                    started_at=started_at,
                    completed_at=completed_at,
                    http_status=response.status_code,
                    error_code="http_error",
                    error_message=f"YouTube feed returned HTTP {response.status_code}",
                )
                raise YoutubeWebProviderError(f"YouTube feed returned HTTP {response.status_code}")
            recorded = self._recorder.record_success(
                request,
                payload={"xml": response.text},
                started_at=started_at,
                completed_at=completed_at,
                http_status=response.status_code,
            )
            results = self._parse_feed(
                response.text,
                channel_id=channel_id,
                published_after=published_after,
                limit=limit,
                raw_ref=recorded.raw_ref,
            )
            self._recorder.link_entities(
                recorded.fetch_id,
                entity_type="youtube_video",
                entity_ids=[item.video_id for item in results],
            )
            return results
        except ET.ParseError as error:
            raise YoutubeWebProviderError("YouTube channel feed is invalid") from error
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _parse_feed(
        xml: str,
        *,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
        raw_ref: str,
    ) -> list[DiscoveredVideo]:
        root = ET.fromstring(xml)
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        results: list[DiscoveredVideo] = []
        for entry in root.findall("atom:entry", namespaces):
            video_id = entry.findtext("yt:videoId", namespaces=namespaces)
            published_text = entry.findtext("atom:published", namespaces=namespaces)
            if not video_id or not published_text:
                continue
            published_at = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
            if published_after and published_at < published_after:
                continue
            results.append(
                DiscoveredVideo(
                    video_id=video_id,
                    title=entry.findtext("atom:title", namespaces=namespaces),
                    channel_id=channel_id,
                    channel_title=root.findtext("atom:title", namespaces=namespaces),
                    published_at=published_at,
                    position=len(results) + 1,
                    query=f"uploads:{channel_id}",
                    raw_ref=raw_ref,
                )
            )
            if len(results) >= limit:
                break
        return results
