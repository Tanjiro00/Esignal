from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import Topic, TopicLineageEdge, TopicSnapshot

TOPIC_IDENTITY_VERSION = "topic-identity-v1"
TOPIC_LINEAGE_VERSION = "topic-lineage-v1"

SEMANTIC_IDENTITY_FIELDS = (
    "domain",
    "facet",
    "primary_entity",
    "audience",
    "user_problem",
    "core_claim",
    "workflow_context",
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).casefold()


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


def topic_identity_payload(
    identity_json: Mapping[str, Any] | None,
    *,
    definition_key: str | None = None,
) -> dict[str, Any]:
    """Build the immutable identity fragment stored in every topic snapshot.

    Labels are deliberately excluded. They are presentation and can change after
    synthesis; lineage requires the deterministic semantic tuple or deterministic
    constituent cluster keys that existed when the snapshot was captured.
    """

    identity = dict(identity_json or {})
    if identity.get("source") in {"workspace_discovery", "workspace_discovery_query"}:
        semantic = {
            "query_id": _normalize(identity.get("query_id")),
            "source": "workspace_discovery_query",
            "workspace_id": _normalize(identity.get("workspace_id")),
        }
        complete = bool(semantic["query_id"] and semantic["workspace_id"])
    else:
        semantic = {field: _normalize(identity.get(field)) for field in SEMANTIC_IDENTITY_FIELDS}
        complete = bool(
            semantic["domain"]
            and semantic["primary_entity"]
            and (semantic["user_problem"] or semantic["core_claim"])
        )

    reconciliation = identity.get("llm_reconciliation")
    raw_member_keys = (
        reconciliation.get("member_keys", []) if isinstance(reconciliation, Mapping) else []
    )
    source_keys = sorted(
        {
            value
            for value in (
                *(
                    _normalize(item)
                    for item in raw_member_keys
                    if isinstance(item, str) and item.strip()
                ),
                _normalize(definition_key),
            )
            if value
        }
    )
    fingerprint = (
        _hash(
            {
                "identity_version": TOPIC_IDENTITY_VERSION,
                "semantic": semantic,
            }
        )
        if complete
        else None
    )
    return {
        "definition_key": _normalize(definition_key) or None,
        "semantic": semantic,
        "semantic_fingerprint": fingerprint,
        "source_keys": source_keys,
        "version": TOPIC_IDENTITY_VERSION,
    }


def snapshot_topic_identity(snapshot: TopicSnapshot) -> dict[str, Any] | None:
    value = snapshot.component_json.get("topic_identity")
    if not isinstance(value, dict) or value.get("version") != TOPIC_IDENTITY_VERSION:
        return None
    return value


@dataclass(frozen=True)
class LineageMatch:
    confidence: float
    reason_code: str


def match_topic_identities(
    source: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
) -> LineageMatch | None:
    if not source or not target:
        return None
    source_fingerprint = source.get("semantic_fingerprint")
    target_fingerprint = target.get("semantic_fingerprint")
    if source_fingerprint and source_fingerprint == target_fingerprint:
        return LineageMatch(confidence=1.0, reason_code="exact_semantic_identity")

    source_keys = set(source.get("source_keys") or [])
    target_keys = set(target.get("source_keys") or [])
    if not source_keys or not target_keys:
        return None
    overlap = source_keys & target_keys
    confidence = len(overlap) / max(1, min(len(source_keys), len(target_keys)))
    if confidence < 0.5:
        return None
    return LineageMatch(
        confidence=round(confidence, 4),
        reason_code="deterministic_source_key_overlap",
    )


def persist_topic_lineage_edges(
    session: Session,
    *,
    previous_topics: Sequence[Topic],
    current_identities: Mapping[str, Mapping[str, Any]],
    detected_at: datetime,
) -> list[TopicLineageEdge]:
    """Persist auditable many-to-many successor edges for disappeared topics."""

    current_ids = set(current_identities)
    created: list[TopicLineageEdge] = []
    for source_topic in previous_topics:
        if source_topic.id in current_ids:
            continue
        source_identity = source_topic.identity_json.get("lineage")
        if not isinstance(source_identity, dict):
            source_identity = topic_identity_payload(source_topic.identity_json)

        matches: list[tuple[str, LineageMatch]] = []
        for target_topic_id, target_identity in current_identities.items():
            match = match_topic_identities(source_identity, target_identity)
            if match is not None:
                matches.append((target_topic_id, match))
        if not matches:
            source_topic.merged_into_topic_id = None
            continue

        best_confidence = max(match.confidence for _, match in matches)
        best = [item for item in matches if item[1].confidence == best_confidence]
        relationship = "split_successor" if len(best) > 1 else "successor"
        source_topic.merged_into_topic_id = best[0][0] if len(best) == 1 else None
        for target_topic_id, match in best:
            fingerprint = str(
                source_identity.get("semantic_fingerprint")
                or current_identities[target_topic_id].get("semantic_fingerprint")
                or ""
            )
            edge_id = str(
                uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        (
                            "earlysignal-topic-lineage",
                            TOPIC_LINEAGE_VERSION,
                            source_topic.id,
                            target_topic_id,
                        )
                    ),
                )
            )
            edge = session.get(TopicLineageEdge, edge_id)
            if edge is None:
                edge = TopicLineageEdge(
                    id=edge_id,
                    source_topic_id=source_topic.id,
                    target_topic_id=target_topic_id,
                    relationship=relationship,
                    confidence=match.confidence,
                    identity_fingerprint=fingerprint or None,
                    reason_codes_json=[match.reason_code],
                    evidence_json={
                        "source_identity": dict(source_identity),
                        "target_identity": dict(current_identities[target_topic_id]),
                    },
                    lineage_version=TOPIC_LINEAGE_VERSION,
                    detected_at=detected_at,
                    created_at=detected_at,
                )
                session.add(edge)
            else:
                edge.relationship = relationship
                edge.confidence = match.confidence
                edge.identity_fingerprint = fingerprint or None
                edge.reason_codes_json = [match.reason_code]
                edge.evidence_json = {
                    "source_identity": dict(source_identity),
                    "target_identity": dict(current_identities[target_topic_id]),
                }
            created.append(edge)
    return created


def collect_lineage_followups(
    session: Session,
    *,
    baselines: Mapping[str, TopicSnapshot],
    checkpoint_at: datetime,
    evaluation_as_of: datetime,
    horizon_days: int,
) -> dict[str, list[TopicSnapshot]]:
    """Resolve direct and immutable-identity follow-up without mutable Topic rows."""

    if not baselines:
        return {}
    checkpoint = _aware(checkpoint_at)
    end = min(checkpoint + timedelta(days=horizon_days), _aware(evaluation_as_of))
    source_ids = list(baselines)
    edges = list(
        session.scalars(
            select(TopicLineageEdge).where(
                TopicLineageEdge.source_topic_id.in_(source_ids),
                TopicLineageEdge.detected_at <= end,
            )
        )
    )
    edge_targets: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        edge_targets[edge.source_topic_id].add(edge.target_topic_id)

    rows = list(
        session.scalars(
            select(TopicSnapshot)
            .where(
                TopicSnapshot.observed_at > checkpoint,
                TopicSnapshot.observed_at <= end,
            )
            .order_by(TopicSnapshot.observed_at, TopicSnapshot.id)
        )
    )
    future_by_fingerprint: dict[str, list[TopicSnapshot]] = defaultdict(list)
    future_by_topic: dict[str, list[TopicSnapshot]] = defaultdict(list)
    for snapshot in rows:
        future_by_topic[snapshot.topic_id].append(snapshot)
        identity = snapshot_topic_identity(snapshot)
        fingerprint = identity.get("semantic_fingerprint") if identity else None
        if isinstance(fingerprint, str) and fingerprint:
            future_by_fingerprint[fingerprint].append(snapshot)

    grouped: dict[str, list[TopicSnapshot]] = {}
    for topic_id, baseline in baselines.items():
        selected = list(future_by_topic.get(topic_id, []))
        identity = snapshot_topic_identity(baseline)
        fingerprint = identity.get("semantic_fingerprint") if identity else None
        if isinstance(fingerprint, str) and fingerprint:
            selected.extend(future_by_fingerprint.get(fingerprint, []))
        for target_topic_id in edge_targets.get(topic_id, set()):
            selected.extend(future_by_topic.get(target_topic_id, []))
        grouped[topic_id] = sorted(
            {snapshot.id: snapshot for snapshot in selected}.values(),
            key=lambda snapshot: (_aware(snapshot.observed_at), snapshot.id),
        )
    return grouped


def followup_topic_ids(snapshots: Iterable[TopicSnapshot]) -> list[str]:
    return sorted({snapshot.topic_id for snapshot in snapshots})


__all__ = [
    "TOPIC_IDENTITY_VERSION",
    "TOPIC_LINEAGE_VERSION",
    "LineageMatch",
    "collect_lineage_followups",
    "followup_topic_ids",
    "match_topic_identities",
    "persist_topic_lineage_edges",
    "snapshot_topic_identity",
    "topic_identity_payload",
]
