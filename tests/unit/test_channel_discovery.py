from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    Base,
    ChannelProfile,
    DiscoveryQueryRecord,
    Workspace,
    WorkspaceChannel,
    WorkspaceDiscoveryQuery,
    YoutubeChannel,
)
from apps.worker.channel_discovery import ChannelDiscoveryService


def test_channel_discovery_builds_diverse_idempotent_fallback_portfolio() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="workspace-1",
                name="Creator",
                slug="creator",
                timezone="UTC",
                created_at=now,
            )
        )
        session.add(
            YoutubeChannel(
                id="channel-1",
                youtube_channel_id="UCCHANNEL1",
                canonical_url="https://youtube.com/channel/UCCHANNEL1",
                title="Software creator",
                description="Software engineering, careers, SaaS and AI.",
                country="RU",
                default_language="ru",
                subscriber_count=1_000,
                video_count=25,
                view_count=10_000,
                published_at=now,
                last_observed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WorkspaceChannel(
                workspace_id="workspace-1",
                channel_id="channel-1",
                relationship="owned",
                priority=0,
                active=True,
                last_ingested_at=None,
                next_ingestion_at=now,
            )
        )
        session.commit()
        session.add(
            ChannelProfile(
                workspace_id="workspace-1",
                channel_id="channel-1",
                profile_source="user",
                audience_description="Software professionals navigating careers and AI.",
                language="en",
                topic_keywords_json=[
                    "AI impact on software careers",
                    "developer hiring",
                    "technical interviews",
                    "engineering culture",
                    "IT labor market",
                ],
                creator_expertise_json=["software engineering careers"],
                core_topics_json=["shorts", "youtube", "ghqabza1zi8"],
                adjacent_topics_json=["cdn", "cookies", "vfnxwvjksq"],
                inference_json={"version": "test"},
                explicit_overrides_json={},
                profile_version="channel-profile-v4-quality",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        service = ChannelDiscoveryService(session, Settings())
        first = service.build("workspace-1")
        second = service.build("workspace-1")

        assert len(first.queries) >= 14
        assert len({item.query.lower() for item in first.queries}) == len(first.queries)
        assert all(3 <= len(item.query.split()) <= 10 for item in first.queries)
        assert not any(
            "agent" in item.query.lower() or "workflow" in item.query.lower()
            for item in first.queries
        )
        assert any("software" in item.query.lower() for item in first.queries)
        assert any("careers" in item.query.lower() for item in first.queries)
        assert not any(
            noise in item.query.lower()
            for item in first.queries
            for noise in ("youtube", "shorts", "ghqabza1zi8", "cookies")
        )
        assert [item.query for item in second.queries] == [item.query for item in first.queries]
        assert session.scalar(
            select(func.count(WorkspaceDiscoveryQuery.query_id)).where(
                WorkspaceDiscoveryQuery.workspace_id == "workspace-1",
                WorkspaceDiscoveryQuery.active.is_(True),
            )
        ) == len(first.queries)
        assert session.scalar(select(func.count(DiscoveryQueryRecord.id))) == len(first.queries)
