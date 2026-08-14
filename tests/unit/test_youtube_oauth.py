import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.config import Settings
from apps.api.demo import DEMO_OWNED_CHANNEL_ID, DEMO_WORKSPACE_ID
from apps.api.models import (
    Base,
    ChannelProfile,
    Signal,
    Topic,
    WorkspaceSignalScore,
    YoutubeOAuthAuditEvent,
    YoutubeOAuthConnection,
    YoutubeOAuthState,
    YoutubeOwnedAnalytics,
    YoutubeVideo,
)
from apps.api.seed import seed_demo
from apps.api.youtube_oauth import YoutubeOAuthService, YoutubeOwnedAnalyticsService
from apps.worker.channel_fit import ChannelFitService
from packages.youtube_oauth import (
    OAuthTokenPayload,
    OwnedChannelPayload,
    OwnedVideoMetricPayload,
    TokenCipher,
    build_pkce_pair,
)


class FakeOAuthTransport:
    def __init__(self) -> None:
        self.fail_refresh = False
        self.revoked_tokens: list[str] = []

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> OAuthTokenPayload:
        assert (client_id, client_secret, code) == (
            "client-id",
            "client-secret",
            "authorization-code",
        )
        assert len(code_verifier) > 40
        return OAuthTokenPayload(
            access_token="access-token-sensitive",
            refresh_token="refresh-token-sensitive",
            expires_in=3600,
            scopes=(
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
            ),
        )

    async def refresh_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> OAuthTokenPayload:
        assert refresh_token == "refresh-token-sensitive"
        if self.fail_refresh:
            raise RuntimeError("sensitive remote response must not be stored")
        return OAuthTokenPayload(
            access_token="refreshed-access-token-sensitive",
            refresh_token="",
            expires_in=3600,
            scopes=(),
        )

    async def owned_channel(self, access_token: str) -> OwnedChannelPayload:
        assert access_token == "access-token-sensitive"
        return OwnedChannelPayload(
            youtube_channel_id="UCESDEMO0000000000000000",
            title="Atlas Labs",
        )

    async def owned_video_metrics(
        self,
        access_token: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[OwnedVideoMetricPayload]:
        assert access_token in {
            "access-token-sensitive",
            "refreshed-access-token-sensitive",
        }
        return [
            OwnedVideoMetricPayload(
                youtube_video_id="esdemo000000",
                views=210_000,
                watch_time_minutes=890_000,
                average_view_duration_seconds=254,
                average_percentage_viewed=48.4,
                subscribers_gained=1_820,
                revenue=None,
                traffic_source_groups={"YT_SEARCH": 88_000},
                geography={"US": 104_000},
            )
        ]

    async def revoke(self, token: str) -> None:
        self.revoked_tokens.append(token)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        feature_youtube_oauth_analytics=True,
        youtube_oauth_client_id="client-id",
        youtube_oauth_client_secret="client-secret",
        youtube_oauth_redirect_uri="http://test/api/v1/oauth/youtube/callback",
        token_encryption_key=Fernet.generate_key().decode(),
    )


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_demo(session)
    return factory


def _authorize(
    session: Session,
    settings: Settings,
    transport: FakeOAuthTransport,
) -> YoutubeOAuthConnection:
    service = YoutubeOAuthService(session, settings, transport)
    authorization_url = service.begin_authorization(DEMO_WORKSPACE_ID)
    query = parse_qs(urlparse(authorization_url).query)
    assert "client-secret" not in authorization_url
    assert query["code_challenge_method"] == ["S256"]
    state_row = session.scalar(select(YoutubeOAuthState))
    assert state_row is not None
    assert "access-token" not in state_row.encrypted_code_verifier
    connection, redirect_after = asyncio.run(
        service.complete_authorization(
            state=query["state"][0],
            code="authorization-code",
        )
    )
    assert redirect_after == "/settings"
    return connection


def test_token_cipher_and_pkce_do_not_store_plaintext() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("refresh-token")
    verifier, challenge = build_pkce_pair()

    assert encrypted != "refresh-token"
    assert cipher.decrypt(encrypted) == "refresh-token"
    assert verifier != challenge
    assert "=" not in challenge


def test_oauth_tokens_are_encrypted_and_refresh_failure_degrades_safely() -> None:
    factory = _session_factory()
    settings = _settings()
    transport = FakeOAuthTransport()
    with factory() as session:
        connection = _authorize(session, settings, transport)
        assert connection.status == "active"
        assert connection.encrypted_access_token != "access-token-sensitive"
        assert connection.encrypted_refresh_token != "refresh-token-sensitive"
        audit_text = str(
            [
                (event.event_type, event.metadata_json)
                for event in session.scalars(select(YoutubeOAuthAuditEvent))
            ]
        )
        assert "access-token-sensitive" not in audit_text
        assert "refresh-token-sensitive" not in audit_text

        connection.token_expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)
        session.commit()
        transport.fail_refresh = True
        token = asyncio.run(
            YoutubeOAuthService(session, settings, transport).access_token(DEMO_WORKSPACE_ID)
        )
        assert token is None
        session.refresh(connection)
        assert connection.status == "degraded"
        assert connection.last_refresh_error == "RuntimeError"

        asyncio.run(YoutubeOAuthService(session, settings, transport).disconnect(DEMO_WORKSPACE_ID))
        session.refresh(connection)
        assert connection.status == "revoked"
        assert connection.encrypted_access_token == ""
        assert connection.encrypted_refresh_token == ""
        assert transport.revoked_tokens == ["refresh-token-sensitive"]


def test_owned_analytics_produces_verified_channel_fit() -> None:
    factory = _session_factory()
    settings = _settings()
    transport = FakeOAuthTransport()
    with factory() as session:
        _authorize(session, settings, transport)
        updated = asyncio.run(
            YoutubeOwnedAnalyticsService(session, settings, transport).sync(DEMO_WORKSPACE_ID)
        )
        assert updated == 1
        analytics = session.scalar(select(YoutubeOwnedAnalytics))
        assert analytics is not None
        assert analytics.watch_time_minutes == 890_000
        assert analytics.traffic_source_groups_json["YT_SEARCH"] == 88_000
        assert analytics.geography_json["US"] == 104_000

        profile = session.get(
            ChannelProfile,
            (DEMO_WORKSPACE_ID, DEMO_OWNED_CHANNEL_ID),
        )
        signal = session.scalar(select(Signal).order_by(Signal.generated_at))
        assert profile is not None and signal is not None
        topic = session.get(Topic, signal.topic_id)
        workspace_score = session.get(
            WorkspaceSignalScore,
            (DEMO_WORKSPACE_ID, signal.id),
        )
        evidence = list(
            session.scalars(
                select(YoutubeVideo)
                .where(YoutubeVideo.channel_id == DEMO_OWNED_CHANNEL_ID)
                .limit(3)
            )
        )
        assert topic is not None and workspace_score is not None and evidence
        result = ChannelFitService(
            session,
            verified_analytics_enabled=True,
        ).score(
            profile=profile,
            signal=signal,
            topic_values=[topic.canonical_label, *topic.entities_json],
            evidence_videos=evidence,
            vertical_relevance=[1.0 for _ in evidence],
            provisional_angles=workspace_score.recommended_angle_json,
            observed_at=datetime(2026, 7, 26, 18, tzinfo=UTC),
        )
        assert result.components["fit_verification"] == "verified"
        assert result.components["verified_analytics_sample_size"] == 1
