"""Access layer for the raw/derived storage boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from apps.api.models import DerivedMetricPoint, RawApiSnapshot

RAW_SNAPSHOT_TTL = timedelta(days=30)


def compute_input_fingerprint(*parts: str) -> str:
    """Return an order-independent fingerprint of a derived value's inputs."""

    joined = "|".join(sorted(str(part) for part in parts))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def record_raw_api_snapshot(
    session: Session,
    *,
    video_id: str,
    provider: str,
    payload: Mapping[str, object],
    fetched_at: datetime,
    provenance: Mapping[str, object] | None = None,
) -> RawApiSnapshot:
    """Mirror one official-API response with a 30-day expiry."""

    if provider != "youtube_official":
        raise ValueError("raw API snapshots only accept youtube_official data")
    snapshot = RawApiSnapshot(
        id=str(uuid4()),
        video_id=video_id,
        provider=provider,
        fetched_at=fetched_at,
        expires_at=fetched_at + RAW_SNAPSHOT_TTL,
        payload=dict(payload),
        provenance=dict(provenance or {}),
    )
    session.add(snapshot)
    return snapshot


def project_raw_to_derived(
    session: Session,
    *,
    subject_type: str,
    subject_id: str,
    window: str,
    metrics: Mapping[str, float],
    scoring_version: str,
    input_fingerprint: str,
    computed_at: datetime | None = None,
) -> list[DerivedMetricPoint]:
    """Publish computed metrics into the append-only derived ledger."""

    moment = computed_at or datetime.now(tz=UTC)
    points = [
        DerivedMetricPoint(
            id=str(uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            metric_name=metric_name,
            value=float(value),
            window=window,
            computed_at=moment,
            scoring_version=scoring_version,
            input_fingerprint=input_fingerprint,
        )
        for metric_name, value in metrics.items()
    ]
    for point in points:
        session.add(point)
    return points
