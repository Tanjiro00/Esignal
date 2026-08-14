from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    Base,
    ChannelProfile,
    Workspace,
    WorkspaceChannel,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.onboarding import OnboardingService


def _channel(
    *,
    channel_id: str,
    title: str,
    description: str,
    subscribers: int,
) -> YoutubeChannel:
    now = datetime.now(tz=UTC)
    return YoutubeChannel(
        id=channel_id,
        youtube_channel_id=f"UC-{channel_id}",
        canonical_url=f"https://youtube.com/channel/UC-{channel_id}",
        title=title,
        description=description,
        country="US",
        default_language="en",
        subscriber_count=subscribers,
        video_count=100,
        view_count=1_000_000,
        published_at=now - timedelta(days=1_000),
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def _video(channel_id: str, index: int, title: str) -> YoutubeVideo:
    now = datetime.now(tz=UTC)
    return YoutubeVideo(
        id=f"{channel_id}-video-{index}",
        youtube_video_id=f"yt-{channel_id}-{index}",
        channel_id=channel_id,
        canonical_url=f"https://youtube.com/watch?v=yt-{channel_id}-{index}",
        title=title,
        description="",
        published_at=now - timedelta(days=index),
        duration_seconds=600,
        is_short=False,
        is_live=False,
        thumbnail_url=f"https://img.youtube.com/vi/yt-{channel_id}-{index}/hqdefault.jpg",
        first_discovered_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def _seed_workspace(session: Session) -> str:
    now = datetime.now(tz=UTC)
    workspace_id = "workspace"
    owned = _channel(
        channel_id="owned",
        title="Software careers",
        description="Engineering careers, SaaS and AI",
        subscribers=10_000,
    )
    session.add(
        Workspace(
            id=workspace_id,
            name="Workspace",
            slug="workspace",
            created_at=now,
        )
    )
    session.add(owned)
    session.add(
        WorkspaceChannel(
            workspace_id=workspace_id,
            channel_id=owned.id,
            relationship="owned",
            priority=0,
            active=True,
        )
    )
    session.add(
        ChannelProfile(
            workspace_id=workspace_id,
            channel_id=owned.id,
            profile_source="user",
            core_topics_json=["software engineering", "SaaS", "AI"],
            topic_keywords_json=["developer careers", "AI"],
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return workspace_id


def test_reference_seeding_prefers_ai_creator_over_larger_broadcaster() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workspace_id = _seed_workspace(session)
        creator = _channel(
            channel_id="creator",
            title="Practical AI Engineer",
            description="Build software with AI agents and coding workflows",
            subscribers=200_000,
        )
        broadcaster = _channel(
            channel_id="broadcaster",
            title="World News Network",
            description="Breaking news, politics, finance and technology",
            subscribers=10_000_000,
        )
        session.add_all((creator, broadcaster))
        for index in range(10):
            session.add(
                _video(
                    creator.id,
                    index,
                    f"Build a Claude AI coding agent workflow {index}",
                )
            )
            session.add(
                _video(
                    broadcaster.id,
                    index,
                    (
                        f"OpenAI market update {index}"
                        if index < 3
                        else f"World politics bulletin {index}"
                    ),
                )
            )
        session.commit()

        created = OnboardingService(session, Settings()).seed_reference_channels(
            workspace_id,
            limit=5,
        )

        references = list(
            session.scalars(
                select(WorkspaceChannel.channel_id).where(
                    WorkspaceChannel.workspace_id == workspace_id,
                    WorkspaceChannel.relationship == "reference",
                )
            )
        )
        assert created == 1
        assert references == [creator.id]


def test_reference_seeding_does_not_fill_with_unrelated_popular_channels() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workspace_id = _seed_workspace(session)
        unrelated = _channel(
            channel_id="unrelated",
            title="Celebrity News",
            description="Entertainment and sports headlines",
            subscribers=20_000_000,
        )
        session.add(unrelated)
        for index in range(10):
            session.add(_video(unrelated.id, index, f"Celebrity interview {index}"))
        session.commit()

        created = OnboardingService(session, Settings()).seed_reference_channels(
            workspace_id,
            limit=5,
        )

        assert created == 0
