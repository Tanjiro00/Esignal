from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import httpx

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
YOUTUBE_API_ROOT = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS_ROOT = "https://youtubeanalytics.googleapis.com/v2"
REQUIRED_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
)


@dataclass(frozen=True)
class OAuthTokenPayload:
    access_token: str
    refresh_token: str
    expires_in: int
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class OwnedChannelPayload:
    youtube_channel_id: str
    title: str


@dataclass(frozen=True)
class OwnedVideoMetricPayload:
    youtube_video_id: str
    views: int
    watch_time_minutes: float
    average_view_duration_seconds: float
    average_percentage_viewed: float
    subscribers_gained: int
    revenue: float | None
    traffic_source_groups: dict[str, int]
    geography: dict[str, int]


class YouTubeOAuthTransport(Protocol):
    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> OAuthTokenPayload: ...

    async def refresh_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> OAuthTokenPayload: ...

    async def owned_channel(self, access_token: str) -> OwnedChannelPayload: ...

    async def owned_video_metrics(
        self,
        access_token: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[OwnedVideoMetricPayload]: ...

    async def revoke(self, token: str) -> None: ...


class GoogleYouTubeOAuthTransport:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        finally:
            if owns_client:
                await client.aclose()

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> OAuthTokenPayload:
        response = await self._request(
            "POST",
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        body = response.json()
        return OAuthTokenPayload(
            access_token=str(body["access_token"]),
            refresh_token=str(body.get("refresh_token", "")),
            expires_in=int(body.get("expires_in", 3600)),
            scopes=tuple(str(body.get("scope", "")).split()),
        )

    async def refresh_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> OAuthTokenPayload:
        response = await self._request(
            "POST",
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        body = response.json()
        return OAuthTokenPayload(
            access_token=str(body["access_token"]),
            refresh_token="",
            expires_in=int(body.get("expires_in", 3600)),
            scopes=tuple(str(body.get("scope", "")).split()),
        )

    async def owned_channel(self, access_token: str) -> OwnedChannelPayload:
        response = await self._request(
            "GET",
            f"{YOUTUBE_API_ROOT}/channels",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"part": "id,snippet", "mine": "true"},
        )
        items = response.json().get("items", [])
        if not items:
            raise ValueError("Authorized account has no YouTube channel")
        return OwnedChannelPayload(
            youtube_channel_id=str(items[0]["id"]),
            title=str(items[0].get("snippet", {}).get("title", "YouTube channel")),
        )

    async def owned_video_metrics(
        self,
        access_token: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[OwnedVideoMetricPayload]:
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "ids": "channel==MINE",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": "video",
            "metrics": (
                "views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,subscribersGained,estimatedRevenue"
            ),
            "maxResults": "200",
            "sort": "-views",
        }
        response = await self._request(
            "GET",
            f"{YOUTUBE_ANALYTICS_ROOT}/reports",
            headers=headers,
            params=params,
        )
        rows = response.json().get("rows", [])
        traffic_response = await self._request(
            "GET",
            f"{YOUTUBE_ANALYTICS_ROOT}/reports",
            headers=headers,
            params={
                **params,
                "dimensions": "video,insightTrafficSourceType",
                "metrics": "views",
                "sort": "-views",
            },
        )
        geography_response = await self._request(
            "GET",
            f"{YOUTUBE_ANALYTICS_ROOT}/reports",
            headers=headers,
            params={
                **params,
                "dimensions": "video,country",
                "metrics": "views",
                "sort": "-views",
            },
        )
        traffic_by_video: dict[str, dict[str, int]] = {}
        for row in traffic_response.json().get("rows", []):
            traffic_by_video.setdefault(str(row[0]), {})[str(row[1])] = int(row[2] or 0)
        geography_by_video: dict[str, dict[str, int]] = {}
        for row in geography_response.json().get("rows", []):
            geography_by_video.setdefault(str(row[0]), {})[str(row[1])] = int(row[2] or 0)
        metrics = [
            OwnedVideoMetricPayload(
                youtube_video_id=str(row[0]),
                views=int(row[1] or 0),
                watch_time_minutes=float(row[2] or 0),
                average_view_duration_seconds=float(row[3] or 0),
                average_percentage_viewed=float(row[4] or 0),
                subscribers_gained=int(row[5] or 0),
                revenue=float(row[6]) if row[6] is not None else None,
                traffic_source_groups=traffic_by_video.get(str(row[0]), {}),
                geography=geography_by_video.get(str(row[0]), {}),
            )
            for row in rows
        ]
        return metrics

    async def revoke(self, token: str) -> None:
        await self._request(
            "POST",
            GOOGLE_REVOKE_URL,
            data={"token": token},
        )
