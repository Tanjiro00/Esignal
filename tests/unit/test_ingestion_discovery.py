import asyncio
from datetime import UTC, datetime

from apps.api.models import DiscoveryQueryRecord
from apps.worker.ingestion import IngestionService
from packages.domain import DiscoveredVideo, DiscoveryQuery


def _video(video_id: str, *, raw_ref: str) -> DiscoveredVideo:
    return DiscoveredVideo(
        video_id=video_id,
        title=f"Video {video_id}",
        channel_id=f"channel-{video_id}",
        channel_title=f"Channel {video_id}",
        published_at=datetime.now(tz=UTC),
        position=1,
        query="developer hiring with AI",
        raw_ref=raw_ref,
    )


class _DiscoverySource:
    def __init__(self, items: list[DiscoveredVideo]) -> None:
        self.items = items
        self.calls = 0

    async def discover(self, request: DiscoveryQuery) -> list[DiscoveredVideo]:
        self.calls += 1
        return self.items


class _OfficialSource:
    def __init__(
        self,
        items: list[DiscoveredVideo],
        *,
        error: Exception | None = None,
    ) -> None:
        self.items = items
        self.error = error
        self.calls = 0
        self.last_request: DiscoveryQuery | None = None

    async def search(self, request: DiscoveryQuery) -> list[DiscoveredVideo]:
        self.calls += 1
        self.last_request = request
        if self.error is not None:
            raise self.error
        return self.items


def test_first_run_tops_up_sparse_web_discovery_and_deduplicates() -> None:
    async def run() -> None:
        service = object.__new__(IngestionService)
        web = _DiscoverySource([_video("shared", raw_ref="web://fetch")])
        official = _OfficialSource(
            [
                _video("shared", raw_ref="official://fetch"),
                _video("official-only", raw_ref="official://fetch"),
            ]
        )
        service._router = web  # type: ignore[assignment]
        service._metadata = official  # type: ignore[assignment]
        service._official_discovery_top_up = True
        query = DiscoveryQueryRecord(last_run_at=None)

        result = await service._discover_for_query(
            query,
            DiscoveryQuery(query="developer hiring with AI", max_results=10),
        )

        assert [item.video_id for item in result] == ["shared", "official-only"]
        assert official.calls == 1
        assert official.last_request is not None
        assert official.last_request.sort == "date"

    asyncio.run(run())


def test_top_up_is_one_time_and_degrades_to_web_results() -> None:
    async def run() -> None:
        service = object.__new__(IngestionService)
        web = _DiscoverySource([_video("web-only", raw_ref="web://fetch")])
        official = _OfficialSource([], error=RuntimeError("quota exhausted"))
        service._router = web  # type: ignore[assignment]
        service._metadata = official  # type: ignore[assignment]
        service._official_discovery_top_up = True
        request = DiscoveryQuery(query="developer hiring with AI", max_results=10)

        first = await service._discover_for_query(
            DiscoveryQueryRecord(last_run_at=None),
            request,
        )
        repeat = await service._discover_for_query(
            DiscoveryQueryRecord(last_run_at=datetime.now(tz=UTC)),
            request,
        )

        assert [item.video_id for item in first] == ["web-only"]
        assert [item.video_id for item in repeat] == ["web-only"]
        assert official.calls == 1

    asyncio.run(run())
