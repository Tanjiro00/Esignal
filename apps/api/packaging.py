from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import ContentBrief, SignalPackaging
from packages.packaging import (
    PACKAGING_VERSION,
    build_signal_packaging,
    regenerate_packaging_section,
)


def _evidence_ids(brief: ContentBrief) -> list[str]:
    raw = brief.brief_json.get("evidence", [])
    return [str(value) for value in raw if str(value).strip()]


def ensure_signal_packaging(
    session: Session,
    brief: ContentBrief,
) -> SignalPackaging:
    if brief.opportunity_id is None:
        raise ValueError("Packaging requires a selected opportunity")
    existing = session.scalar(
        select(SignalPackaging).where(
            SignalPackaging.workspace_id == brief.workspace_id,
            SignalPackaging.signal_id == brief.signal_id,
            SignalPackaging.opportunity_id == brief.opportunity_id,
        )
    )
    if existing is not None:
        return existing
    now = datetime.now(tz=UTC)
    evidence_ids = _evidence_ids(brief)
    row = SignalPackaging(
        id=str(uuid4()),
        workspace_id=brief.workspace_id,
        signal_id=brief.signal_id,
        opportunity_id=brief.opportunity_id,
        content_brief_id=brief.id,
        packaging_json=build_signal_packaging(
            angle=brief.brief_json,
            evidence_ids=evidence_ids,
        ),
        evidence_ids_json=evidence_ids,
        regeneration_counts_json={},
        packaging_version=PACKAGING_VERSION,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def regenerate_signal_packaging(
    session: Session,
    row: SignalPackaging,
    section: str,
) -> SignalPackaging:
    brief = session.get(ContentBrief, row.content_brief_id)
    if brief is None:
        raise LookupError("Packaging brief not found")
    counts = dict(row.regeneration_counts_json)
    revision = counts.get(section, 0) + 1
    row.packaging_json = regenerate_packaging_section(
        current=row.packaging_json,
        section=section,
        angle=brief.brief_json,
        evidence_ids=row.evidence_ids_json,
        revision=revision,
    )
    counts[section] = revision
    row.regeneration_counts_json = counts
    row.packaging_version = PACKAGING_VERSION
    row.updated_at = datetime.now(tz=UTC)
    session.flush()
    return row
