"""GitHub repository evidence.

For developer-tool topics the star curve typically precedes the first tutorial
video by weeks. Repository creation time is a hard, dated fact and needs no
authentication to read.

Unauthenticated search allows 10 requests per minute, so the client is rate
limited and every response is cached.
"""

from __future__ import annotations

import urllib.parse

from es_ingest.upstream.base import HttpCache, UpstreamMention, to_datetime

ENDPOINT = "https://api.github.com/search/repositories"


class GitHubSource:
    name = "github"

    def __init__(self, cache: HttpCache) -> None:
        self._cache = cache

    def mentions(self, term: str, *, limit: int = 10) -> tuple[UpstreamMention, ...]:
        query = urllib.parse.quote(f'"{term}" in:name,description')
        url = f"{ENDPOINT}?q={query}&sort=stars&order=desc&per_page={min(limit, 30)}"
        payload = self._cache.get_json(url, headers={"Accept": "application/vnd.github+json"})
        if not isinstance(payload, dict) or "items" not in payload:
            return ()
        needle = term.lower()
        mentions: list[UpstreamMention] = []
        for item in payload["items"]:
            at = to_datetime(str(item.get("created_at") or ""))
            if at is None:
                continue
            name = str(item.get("full_name") or "").lower()
            description = str(item.get("description") or "").lower()
            if needle not in name and needle not in description:
                continue
            position = "name" if needle in name else "body"
            stars = float(item.get("stargazers_count") or 0)
            mentions.append(
                UpstreamMention(
                    source=self.name,
                    term=term,
                    at=at,
                    weight=1.0 + stars / 1000.0,
                    title=str(item.get("full_name") or "")[:200],
                    url=str(item.get("html_url") or ""),
                    position=position,
                )
            )
        return tuple(sorted(mentions, key=lambda mention: mention.at))


__all__ = ["GitHubSource"]
