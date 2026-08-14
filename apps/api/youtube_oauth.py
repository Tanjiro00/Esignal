from __future__ import annotations

import secrets
from datetime import UTC, datetime, time, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    WorkspaceChannel,
    YoutubeChannel,
    YoutubeOAuthAuditEvent,
    YoutubeOAuthConnection,
    YoutubeOAuthState,
    YoutubeOwnedAnalytics,
    YoutubeVideo,
)
from packages.youtube_oauth import (
    GOOGLE_AUTHORIZATION_URL,
    REQUIRED_SCOPES,
    TOKEN_ENCRYPTION_VERSION,
    GoogleYouTubeOAuthTransport,
    TokenCipher,
    YouTubeOAuthTransport,
    build_pkce_pair,
    hash_oauth_state,
)

OWNED_ANALYTICS_VERSION = "youtube-owned-analytics-v1"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class YoutubeOAuthService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        transport: YouTubeOAuthTransport | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._transport = transport or GoogleYouTubeOAuthTransport()

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.feature_youtube_oauth_analytics
            and self._settings.youtube_oauth_client_id
            and self._settings.youtube_oauth_client_secret.get_secret_value()
            and self._settings.token_encryption_key.get_secret_value()
        )

    def _cipher(self) -> TokenCipher:
        return TokenCipher(self._settings.token_encryption_key.get_secret_value())

    def _audit(
        self,
        workspace_id: str,
        event_type: str,
        result: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            YoutubeOAuthAuditEvent(
                id=str(uuid4()),
                workspace_id=workspace_id,
                event_type=event_type,
                result=result,
                metadata_json=metadata or {},
                created_at=datetime.now(tz=UTC),
            )
        )

    def status(self, workspace_id: str) -> dict[str, object]:
        connection = self._session.get(YoutubeOAuthConnection, workspace_id)
        recent_audit = list(
            self._session.scalars(
                select(YoutubeOAuthAuditEvent)
                .where(YoutubeOAuthAuditEvent.workspace_id == workspace_id)
                .order_by(desc(YoutubeOAuthAuditEvent.created_at))
                .limit(10)
            )
        )
        analytics_count = len(
            list(
                self._session.scalars(
                    select(YoutubeOwnedAnalytics.id).where(
                        YoutubeOwnedAnalytics.workspace_id == workspace_id
                    )
                )
            )
        )
        return {
            "feature_enabled": self._settings.feature_youtube_oauth_analytics,
            "configured": self.configured,
            "connected": bool(connection and connection.status == "active"),
            "status": connection.status if connection else "not_connected",
            "verified": bool(connection and connection.verified_at),
            "scopes": connection.scopes_json if connection else [],
            "token_expires_at": connection.token_expires_at if connection else None,
            "verified_at": connection.verified_at if connection else None,
            "last_synced_at": connection.last_synced_at if connection else None,
            "last_refresh_error": connection.last_refresh_error if connection else None,
            "analytics_video_count": analytics_count,
            "audit_events": [
                {
                    "event_type": item.event_type,
                    "result": item.result,
                    "metadata": item.metadata_json,
                    "created_at": item.created_at,
                }
                for item in recent_audit
            ],
        }

    def begin_authorization(
        self,
        workspace_id: str,
        *,
        redirect_after: str = "/settings",
    ) -> str:
        if not self.configured:
            raise ValueError("YouTube OAuth is not configured")
        if not redirect_after.startswith("/") or redirect_after.startswith("//"):
            raise ValueError("redirect_after must be a local application path")
        owned = self._session.scalar(
            select(WorkspaceChannel.channel_id).where(
                WorkspaceChannel.workspace_id == workspace_id,
                WorkspaceChannel.relationship == "owned",
                WorkspaceChannel.active.is_(True),
            )
        )
        if owned is None:
            raise LookupError("Configure an owned channel first")
        state = secrets.token_urlsafe(32)
        verifier, challenge = build_pkce_pair()
        now = datetime.now(tz=UTC)
        self._session.add(
            YoutubeOAuthState(
                id=str(uuid4()),
                workspace_id=workspace_id,
                state_hash=hash_oauth_state(state),
                encrypted_code_verifier=self._cipher().encrypt(verifier),
                redirect_after=redirect_after,
                expires_at=now + timedelta(minutes=10),
                used_at=None,
                created_at=now,
            )
        )
        self._audit(
            workspace_id,
            "authorization_started",
            "success",
            {"scopes": list(REQUIRED_SCOPES)},
        )
        self._session.commit()
        return f"{GOOGLE_AUTHORIZATION_URL}?{
            urlencode(
                {
                    'client_id': self._settings.youtube_oauth_client_id,
                    'redirect_uri': self._settings.youtube_oauth_redirect_uri,
                    'response_type': 'code',
                    'scope': ' '.join(REQUIRED_SCOPES),
                    'access_type': 'offline',
                    'include_granted_scopes': 'true',
                    'prompt': 'consent',
                    'state': state,
                    'code_challenge': challenge,
                    'code_challenge_method': 'S256',
                }
            )
        }"

    async def complete_authorization(
        self,
        *,
        state: str,
        code: str,
    ) -> tuple[YoutubeOAuthConnection, str]:
        if not self.configured:
            raise ValueError("YouTube OAuth is not configured")
        state_row = self._session.scalar(
            select(YoutubeOAuthState).where(YoutubeOAuthState.state_hash == hash_oauth_state(state))
        )
        now = datetime.now(tz=UTC)
        if state_row is None or state_row.used_at is not None or _aware(state_row.expires_at) < now:
            raise ValueError("OAuth state is invalid or expired")
        state_row.used_at = now
        verifier = self._cipher().decrypt(state_row.encrypted_code_verifier)
        token = await self._transport.exchange_code(
            client_id=self._settings.youtube_oauth_client_id,
            client_secret=self._settings.youtube_oauth_client_secret.get_secret_value(),
            redirect_uri=self._settings.youtube_oauth_redirect_uri,
            code=code,
            code_verifier=verifier,
        )
        granted_scopes = token.scopes or REQUIRED_SCOPES
        if not set(REQUIRED_SCOPES).issubset(granted_scopes):
            self._audit(
                state_row.workspace_id,
                "authorization_completed",
                "rejected",
                {"reason": "required_scope_missing"},
            )
            self._session.commit()
            raise ValueError("Required read-only YouTube scopes were not granted")
        authorized_channel = await self._transport.owned_channel(token.access_token)
        owned = self._session.execute(
            select(WorkspaceChannel, YoutubeChannel)
            .join(YoutubeChannel, YoutubeChannel.id == WorkspaceChannel.channel_id)
            .where(
                WorkspaceChannel.workspace_id == state_row.workspace_id,
                WorkspaceChannel.relationship == "owned",
                WorkspaceChannel.active.is_(True),
            )
            .limit(1)
        ).first()
        if owned is None:
            raise LookupError("Configure an owned channel first")
        if owned[1].youtube_channel_id != authorized_channel.youtube_channel_id:
            self._audit(
                state_row.workspace_id,
                "authorization_completed",
                "rejected",
                {
                    "reason": "owned_channel_mismatch",
                    "authorized_channel_id": authorized_channel.youtube_channel_id,
                },
            )
            self._session.commit()
            raise ValueError("Authorized YouTube channel does not match the owned channel")
        cipher = self._cipher()
        connection = self._session.get(
            YoutubeOAuthConnection,
            state_row.workspace_id,
        )
        refresh_token = token.refresh_token
        if connection is not None and not refresh_token:
            refresh_token = cipher.decrypt(connection.encrypted_refresh_token)
        if not refresh_token:
            raise ValueError("Google did not return a refresh token")
        if connection is None:
            connection = YoutubeOAuthConnection(
                workspace_id=state_row.workspace_id,
                channel_id=owned[1].id,
                created_at=now,
                updated_at=now,
            )
            self._session.add(connection)
        connection.channel_id = owned[1].id
        connection.status = "active"
        connection.scopes_json = list(granted_scopes)
        connection.encrypted_access_token = cipher.encrypt(token.access_token)
        connection.encrypted_refresh_token = cipher.encrypt(refresh_token)
        connection.token_expires_at = now + timedelta(seconds=token.expires_in)
        connection.token_encryption_version = TOKEN_ENCRYPTION_VERSION
        connection.verified_at = now
        connection.last_refresh_error = None
        connection.updated_at = now
        self._audit(
            state_row.workspace_id,
            "authorization_completed",
            "success",
            {
                "channel_id": authorized_channel.youtube_channel_id,
                "scopes": list(granted_scopes),
            },
        )
        self._session.commit()
        return connection, state_row.redirect_after

    async def access_token(self, workspace_id: str) -> str | None:
        connection = self._session.get(YoutubeOAuthConnection, workspace_id)
        if connection is None or connection.status != "active":
            return None
        cipher = self._cipher()
        now = datetime.now(tz=UTC)
        if connection.token_expires_at is not None and _aware(
            connection.token_expires_at
        ) > now + timedelta(minutes=5):
            return cipher.decrypt(connection.encrypted_access_token)
        try:
            refresh_token = cipher.decrypt(connection.encrypted_refresh_token)
            token = await self._transport.refresh_token(
                client_id=self._settings.youtube_oauth_client_id,
                client_secret=self._settings.youtube_oauth_client_secret.get_secret_value(),
                refresh_token=refresh_token,
            )
            connection.encrypted_access_token = cipher.encrypt(token.access_token)
            connection.token_expires_at = now + timedelta(seconds=token.expires_in)
            connection.status = "active"
            connection.last_refresh_error = None
            connection.updated_at = now
            self._audit(workspace_id, "token_refreshed", "success")
            self._session.commit()
            return token.access_token
        except Exception as error:
            connection.status = "degraded"
            connection.last_refresh_error = type(error).__name__[:240]
            connection.updated_at = now
            self._audit(
                workspace_id,
                "token_refresh_failed",
                "error",
                {"error_type": type(error).__name__},
            )
            self._session.commit()
            return None

    async def disconnect(self, workspace_id: str) -> None:
        connection = self._session.get(YoutubeOAuthConnection, workspace_id)
        if connection is None:
            return
        remote_result = "not_attempted"
        try:
            token = self._cipher().decrypt(
                connection.encrypted_refresh_token or connection.encrypted_access_token
            )
            if token:
                await self._transport.revoke(token)
                remote_result = "revoked"
        except Exception as error:
            remote_result = f"failed:{type(error).__name__}"
        connection.status = "revoked"
        connection.encrypted_access_token = ""
        connection.encrypted_refresh_token = ""
        connection.token_expires_at = None
        connection.updated_at = datetime.now(tz=UTC)
        self._audit(
            workspace_id,
            "disconnected",
            "success",
            {"remote_revoke": remote_result},
        )
        self._session.commit()


class YoutubeOwnedAnalyticsService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        transport: YouTubeOAuthTransport | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._transport = transport or GoogleYouTubeOAuthTransport()
        self._oauth = YoutubeOAuthService(session, settings, self._transport)

    async def sync_due(self, *, limit: int = 10) -> dict[str, int]:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=6)
        connections = list(
            self._session.scalars(
                select(YoutubeOAuthConnection)
                .where(
                    YoutubeOAuthConnection.status == "active",
                    (
                        YoutubeOAuthConnection.last_synced_at.is_(None)
                        | (YoutubeOAuthConnection.last_synced_at <= cutoff)
                    ),
                )
                .order_by(YoutubeOAuthConnection.last_synced_at)
                .limit(limit)
            )
        )
        updated = 0
        for connection in connections:
            updated += await self.sync(connection.workspace_id)
        return {
            "workspaces_synced": len(connections),
            "videos_updated": updated,
        }

    async def sync(self, workspace_id: str, *, days: int = 90) -> int:
        access_token = await self._oauth.access_token(workspace_id)
        if access_token is None:
            return 0
        connection = self._session.get(YoutubeOAuthConnection, workspace_id)
        if connection is None:
            return 0
        observed_at = datetime.now(tz=UTC)
        end = datetime.combine(observed_at.date(), time.min, tzinfo=UTC)
        start = end - timedelta(days=days)
        try:
            metrics = await self._transport.owned_video_metrics(
                access_token,
                start_date=start.date(),
                end_date=end.date(),
            )
        except Exception as error:
            connection.last_refresh_error = f"analytics:{type(error).__name__}"[:240]
            connection.updated_at = observed_at
            self._oauth._audit(  # noqa: SLF001 - same domain service
                workspace_id,
                "analytics_sync_failed",
                "error",
                {"error_type": type(error).__name__},
            )
            self._session.commit()
            return 0
        videos = {
            video.youtube_video_id: video
            for video in self._session.scalars(
                select(YoutubeVideo).where(YoutubeVideo.channel_id == connection.channel_id)
            )
        }
        updated = 0
        for item in metrics:
            video = videos.get(item.youtube_video_id)
            existing = self._session.scalar(
                select(YoutubeOwnedAnalytics).where(
                    YoutubeOwnedAnalytics.workspace_id == workspace_id,
                    YoutubeOwnedAnalytics.youtube_video_id == item.youtube_video_id,
                    YoutubeOwnedAnalytics.period_start == start,
                    YoutubeOwnedAnalytics.period_end == end,
                    YoutubeOwnedAnalytics.analytics_version == OWNED_ANALYTICS_VERSION,
                )
            )
            row = existing or YoutubeOwnedAnalytics(
                id=str(uuid4()),
                workspace_id=workspace_id,
                channel_id=connection.channel_id,
                video_id=video.id if video else None,
                youtube_video_id=item.youtube_video_id,
                period_start=start,
                period_end=end,
                analytics_version=OWNED_ANALYTICS_VERSION,
                observed_at=observed_at,
            )
            row.video_id = video.id if video else None
            row.views = item.views
            row.watch_time_minutes = item.watch_time_minutes
            row.average_view_duration_seconds = item.average_view_duration_seconds
            row.average_percentage_viewed = item.average_percentage_viewed
            row.subscribers_gained = item.subscribers_gained
            row.revenue = item.revenue
            row.traffic_source_groups_json = item.traffic_source_groups
            row.geography_json = item.geography
            row.content_type = (
                "short"
                if video and video.is_short
                else "live"
                if video and video.is_live
                else "long"
            )
            row.published_at = video.published_at if video else start
            row.duration_seconds = video.duration_seconds if video else 0
            row.observed_at = observed_at
            if existing is None:
                self._session.add(row)
            updated += 1
        connection.last_synced_at = observed_at
        connection.last_refresh_error = None
        connection.updated_at = observed_at
        self._oauth._audit(  # noqa: SLF001 - same domain service
            workspace_id,
            "analytics_synced",
            "success",
            {"video_count": updated, "analytics_version": OWNED_ANALYTICS_VERSION},
        )
        self._session.commit()
        return updated
