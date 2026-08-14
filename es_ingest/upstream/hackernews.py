"""Hacker News mentions via the public Algolia index.

Free, no key, and it covers exactly the audience that discovers developer tools
before they reach YouTube tutorials.
"""

from __future__ import annotations

from datetime import UTC, datetime

from es_ingest.upstream.base import HttpCache, UpstreamMention, quote, to_datetime

ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsSource:
    name = "hackernews"

    def __init__(self, cache: HttpCache) -> None:
        self._cache = cache

    def mentions(self, term: str, *, limit: int = 50) -> tuple[UpstreamMention, ...]:
        url = f"{ENDPOINT}?query={quote(term)}&tags=(story,comment)&hitsPerPage={min(limit, 100)}"
        payload = self._cache.get_json(url)
        if not isinstance(payload, dict) or "hits" not in payload:
            return ()
        needle = term.lower()
        mentions: list[UpstreamMention] = []
        for hit in payload["hits"]:
            at = to_datetime(str(hit.get("created_at") or ""))
            if at is None:
                continue
            # Algolia is typo-tolerant even for quoted phrases, so a returned
            # hit is only evidence once the term literally appears in it.
            headline = " ".join(
                str(hit.get(field) or "") for field in ("title", "story_title", "url")
            ).lower()
            body = str(hit.get("comment_text") or "").lower()
            if needle not in headline and needle not in body:
                continue
            position = "title" if needle in headline else "body"
            points = float(hit.get("points") or 0)
            comments = float(hit.get("num_comments") or 0)
            mentions.append(
                UpstreamMention(
                    source=self.name,
                    term=term,
                    at=at,
                    # A front-page story counts for more than a passing comment.
                    weight=1.0 + points / 100.0 + comments / 200.0,
                    title=str(hit.get("title") or hit.get("story_title") or "")[:200],
                    url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    position=position,
                )
            )
        return tuple(sorted(mentions, key=lambda mention: mention.at))


def observable(
    mentions: tuple[UpstreamMention, ...],
    *,
    as_of: datetime,
) -> tuple[UpstreamMention, ...]:
    cutoff = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    return tuple(mention for mention in mentions if mention.at <= cutoff)


__all__ = ["HackerNewsSource", "observable"]
