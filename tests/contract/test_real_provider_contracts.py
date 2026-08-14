import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from packages.domain import DiscoveryQuery, ProviderRequest, RecordedPayload
from packages.provider_sdk.youtube_official import YoutubeOfficialProvider
from packages.provider_sdk.youtube_transcript import YoutubeTranscriptProvider
from packages.provider_sdk.youtube_web import YoutubeWebDiscoveryProvider

ROOT = Path(__file__).resolve().parents[2]


class MemoryRecorder:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.links: list[tuple[str, str, tuple[str, ...]]] = []

    def record_success(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
    ) -> RecordedPayload:
        del request, started_at, completed_at, http_status
        self.payloads.append(payload)
        fetch_id = f"fixture-fetch-{len(self.payloads)}"
        return RecordedPayload(
            fetch_id=fetch_id,
            raw_ref=f"fetch://{fetch_id}",
            payload_hash=f"hash-{len(self.payloads)}",
        )

    def record_failure(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
        error_code: str,
        error_message: str,
    ) -> RecordedPayload:
        del error_code, error_message
        return self.record_success(
            request,
            payload=payload,
            started_at=started_at,
            completed_at=completed_at,
            http_status=http_status,
        )

    def link_entities(
        self,
        fetch_id: str,
        *,
        entity_type: str,
        entity_ids: list[str],
    ) -> None:
        self.links.append((fetch_id, entity_type, tuple(entity_ids)))

    def mark_parse_failure(
        self,
        fetch_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        raise AssertionError(f"Unexpected parse failure {fetch_id}: {error_code}: {error_message}")


def _fixture(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text())


def test_youtube_web_search_fixture_normalizes_stable_ids() -> None:
    recorder = MemoryRecorder()
    provider = YoutubeWebDiscoveryProvider(recorder=recorder)
    payload = _fixture("fixtures/providers/youtube_web/search.json")

    results = provider._parse_search(
        payload,
        query=DiscoveryQuery(query="AI coding agents", max_results=10),
        raw_ref="fetch://fixture-web",
        observed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
    )

    assert len(results) == 1
    assert results[0].video_id == "abc123xyz89"
    assert results[0].channel_id == "UCFIXTURE00000000000001"
    assert results[0].position == 1
    assert results[0].raw_ref == "fetch://fixture-web"


def test_youtube_official_fixtures_match_metadata_contract() -> None:
    videos_payload = _fixture("fixtures/providers/youtube_official/videos.json")
    channels_payload = _fixture("fixtures/providers/youtube_official/channels.json")
    recorder = MemoryRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = videos_payload if request.url.path.endswith("/videos") else channels_payload
        return httpx.Response(200, json=payload)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YoutubeOfficialProvider(
                api_key="sanitized-fixture-key",
                recorder=recorder,
                client=client,
            )
            videos = list(await provider.fetch_videos(["abc123xyz89"]))
            channels = list(await provider.fetch_channels(["UCFIXTURE00000000000001"]))
        assert videos[0].duration_seconds == 754
        assert videos[0].view_count == 184_300
        assert videos[0].raw_ref == "fetch://fixture-fetch-1"
        assert channels[0].subscriber_count == 120_000
        assert channels[0].raw_ref == "fetch://fixture-fetch-2"

    asyncio.run(run())
    assert len(recorder.payloads) == 2


def test_youtube_official_resolves_channel_handle_urls() -> None:
    channels_payload = _fixture("fixtures/providers/youtube_official/channels.json")
    recorder = MemoryRecorder()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/channels")
        assert request.url.params["forHandle"] == "om_nazarov"
        assert "id" not in request.url.params
        return httpx.Response(200, json=channels_payload)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YoutubeOfficialProvider(
                api_key="sanitized-fixture-key",
                recorder=recorder,
                client=client,
            )
            channels = list(
                await provider.fetch_channels(
                    [
                        "https://www.youtube.com/@om_nazarov",
                        "@om_nazarov",
                    ]
                )
            )
        assert len(channels) == 1
        assert channels[0].channel_id == "UCFIXTURE00000000000001"

    asyncio.run(run())
    assert len(requests) == 1
    assert len(recorder.payloads) == 1


def test_youtube_official_search_matches_discovery_contract() -> None:
    payload = _fixture("fixtures/providers/youtube_official/search.json")
    recorder = MemoryRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        assert request.url.params["type"] == "video"
        assert request.url.params["q"] == "AI coding agents"
        return httpx.Response(200, json=payload)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YoutubeOfficialProvider(
                api_key="sanitized-fixture-key",
                recorder=recorder,
                client=client,
            )
            results = list(
                await provider.search(DiscoveryQuery(query="AI coding agents", max_results=10))
            )
        assert len(results) == 1
        assert results[0].video_id == "abc123xyz89"
        assert results[0].channel_id == "UCFIXTURE00000000000001"
        assert results[0].position == 1
        assert results[0].raw_ref == "fetch://fixture-fetch-1"

    asyncio.run(run())
    assert recorder.links == [("fixture-fetch-1", "youtube_video", ("abc123xyz89",))]


def test_youtube_official_comments_drop_profile_data_before_recording() -> None:
    comments_payload = _fixture("fixtures/providers/youtube_official/comments.json")
    recorder = MemoryRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/commentThreads")
        return httpx.Response(200, json=comments_payload)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YoutubeOfficialProvider(
                api_key="sanitized-fixture-key",
                recorder=recorder,
                client=client,
            )
            comments = list(
                await provider.fetch_comments(
                    "abc123xyz89",
                    order="relevance",
                    limit=10,
                    include_replies=False,
                )
            )
        assert len(comments) == 1
        assert comments[0].comment_id == "fixture-comment-1"
        assert comments[0].reply_count == 4
        assert comments[0].author_hash is not None
        assert comments[0].raw_ref == "fetch://fixture-fetch-1"

    asyncio.run(run())
    stored = json.dumps(recorder.payloads)
    assert "Fixture Author" not in stored
    assert "UC_FIXTURE_COMMENTER" not in stored
    assert "authorHash" in stored


def test_youtube_transcript_provider_normalizes_timed_public_captions() -> None:
    recorder = MemoryRecorder()

    class FakeFetched:
        @staticmethod
        def to_raw_data() -> list[dict[str, object]]:
            return [
                {"start": 0.0, "duration": 3.2, "text": "  Local AI workflow  "},
                {"start": 3.2, "duration": 4.0, "text": "costs less than hosted tools."},
            ]

    class FakeTranscript:
        language_code = "en"
        is_translatable = True

        @staticmethod
        def fetch() -> FakeFetched:
            return FakeFetched()

    class FakeTranscriptList:
        @staticmethod
        def find_manually_created_transcript(
            languages: tuple[str, ...],
        ) -> FakeTranscript:
            assert languages == ("en",)
            return FakeTranscript()

    class FakeApi:
        @staticmethod
        def list(video_id: str) -> FakeTranscriptList:
            assert video_id == "abc123xyz89"
            return FakeTranscriptList()

    async def run() -> None:
        result = await YoutubeTranscriptProvider(
            recorder=recorder,
            api=FakeApi(),
        ).fetch_transcript(
            "abc123xyz89",
            preferred_languages=("en",),
            allow_generated=False,
        )
        assert result.transcript_type == "native"
        assert result.segments == (
            (0.0, 3.2, "Local AI workflow"),
            (3.2, 7.2, "costs less than hosted tools."),
        )
        assert result.text == "Local AI workflow costs less than hosted tools."
        assert result.raw_ref == "fetch://fixture-fetch-1"

    asyncio.run(run())
    assert recorder.payloads[0]["segments"][0]["text"] == "Local AI workflow"
    assert recorder.links == [("fixture-fetch-1", "youtube_video", ("abc123xyz89",))]
