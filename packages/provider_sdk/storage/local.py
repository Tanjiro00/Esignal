from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoredRawPayload:
    uri: str
    content_hash: str


class LocalRawPayloadStore:
    """Content-addressed gzip store for immutable provider payloads."""

    def __init__(self, *, repository_root: Path, storage_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._storage_root = storage_root.resolve()
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        payload: dict[str, Any],
        *,
        provider: str,
        capability: str,
        observed_at: datetime,
    ) -> StoredRawPayload:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        content_hash = sha256(canonical).hexdigest()
        destination = (
            self._storage_root
            / observed_at.strftime("%Y/%m/%d")
            / provider
            / capability
            / f"{content_hash}.json.gz"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            compressed = gzip.compress(canonical, compresslevel=6, mtime=0)
            destination.write_bytes(compressed)
        return StoredRawPayload(
            uri=str(destination.relative_to(self._repository_root)),
            content_hash=content_hash,
        )
