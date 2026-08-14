"""Upstream mention sources.

YouTube supply is a lagging indicator. By the time two creators have filmed a
tool, the tool has usually already been on Hacker News and accumulated GitHub
stars. The earliest evidence therefore lives upstream of the platform we are
predicting, and adding it is a change in *information*, not in modelling.

Every adapter returns the same value type, so a new source is a new file rather
than a change to the pipeline.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

USER_AGENT = "earlysignal-research/2.0 (+upstream signal evaluation)"


@dataclass(frozen=True, slots=True)
class UpstreamMention:
    """One dated piece of evidence that a term exists outside YouTube."""

    source: str
    term: str
    at: datetime
    weight: float
    title: str
    url: str
    position: str = "body"
    """Where the term matched: "title" and "name" are structural positions.

    A term appearing in a story title or a repository name is being *named*.
    The same term inside a comment body may be an incidental mention — "26b"
    occurs in a sentence about model sizes without the discussion being about
    anything called 26b. Only structural positions promote a term to an entity.
    """


class UpstreamSource(Protocol):
    name: str

    def mentions(self, term: str, *, limit: int = 50) -> tuple[UpstreamMention, ...]: ...


class HttpCache:
    """Disk cache keyed by URL.

    Upstream APIs are rate limited and the same term is queried repeatedly
    across checkpoints, so caching is what makes the evaluation affordable.
    """

    def __init__(self, directory: Path, *, min_interval_seconds: float = 0.0) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._min_interval = min_interval_seconds
        self._last_request = 0.0

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        key = sha256(url.encode()).hexdigest()[:24]
        path = self.directory / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        wait = self._min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            payload = {"__error__": str(error)}
        finally:
            self._last_request = time.monotonic()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


def quote(term: str) -> str:
    return urllib.parse.quote(f'"{term}"')


def to_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def earliest(mentions: Sequence[UpstreamMention]) -> datetime | None:
    return min((mention.at for mention in mentions), default=None)


__all__ = [
    "HttpCache",
    "UpstreamMention",
    "UpstreamSource",
    "earliest",
    "quote",
    "to_datetime",
]
