import asyncio

from packages.domain import DiscoveryQuery
from packages.provider_sdk import MockProvider, ProviderRouter


def test_mock_provider_implements_all_slice_one_capabilities() -> None:
    async def exercise() -> None:
        provider = MockProvider()
        results = await provider.search(DiscoveryQuery(query="AI coding agents", max_results=3))
        assert len(results) == 3
        assert len({item.video_id for item in results}) == 3
        assert all(item.raw_ref.startswith("fixture://") for item in results)

        metadata = await provider.fetch_videos([item.video_id for item in results])
        channels = await provider.fetch_channels([item.channel_id or "" for item in results])
        comments = await provider.fetch_comments(
            results[0].video_id,
            order="relevance",
            limit=2,
            include_replies=False,
        )
        transcript = await provider.fetch_transcript(
            results[0].video_id,
            preferred_languages=("en",),
            allow_generated=False,
        )

        assert len(metadata) == 3
        assert len(channels) == 3
        assert len(comments) == 2
        assert transcript.transcript_type == "native"
        assert transcript.quality_score > 0.9

    asyncio.run(exercise())


def test_router_returns_normalized_domain_objects() -> None:
    async def exercise() -> None:
        provider = MockProvider()
        router = ProviderRouter(
            discovery=[provider],
            metadata=[provider],
            comments=[provider],
            transcripts=[provider],
        )
        discovered = await router.discover(DiscoveryQuery(query="local AI video", max_results=2))
        assert [item.position for item in discovered] == [1, 2]
        assert len(await router.comments(discovered[0].video_id, limit=1)) == 1
        assert (await router.transcript(discovered[0].video_id)).language == "en"

    asyncio.run(exercise())
