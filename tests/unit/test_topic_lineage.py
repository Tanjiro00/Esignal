from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.models import Base, Topic, TopicLineageEdge, TopicSnapshot
from packages.topic_lineage import (
    collect_lineage_followups,
    match_topic_identities,
    persist_topic_lineage_edges,
    topic_identity_payload,
)

CUTOFF = datetime(2026, 8, 8, 12, tzinfo=UTC)


def _raw_identity(*, claim: str = "replace a manual reporting step") -> dict[str, str]:
    return {
        "audience": "small business teams",
        "core_claim": claim,
        "domain": "productivity",
        "facet": "workflow",
        "primary_entity": "ai automation",
        "user_problem": "manual reporting",
        "workflow_context": "weekly operations",
    }


def _topic(topic_id: str, identity: dict[str, object]) -> Topic:
    return Topic(
        id=topic_id,
        canonical_label=f"mutable label {topic_id}",
        aliases_json=[],
        entities_json=[],
        centroid_embedding=[],
        embedding_model="test",
        embedding_version="test",
        first_observed_at=CUTOFF - timedelta(days=2),
        first_confirmed_at=CUTOFF - timedelta(days=1),
        lifecycle_stage="Seed",
        status="active",
        source_kind="live",
        merged_into_topic_id=None,
        clustering_version="test",
        identity_json=identity,
        specificity_score=80,
        thesis_support_ratio=1,
        visibility_reason_codes_json=[],
    )


def _snapshot(
    snapshot_id: str,
    *,
    topic_id: str,
    observed_at: datetime,
    identity: dict[str, object] | None,
) -> TopicSnapshot:
    component_json: dict[str, object] = {"score": 60}
    if identity is not None:
        component_json["topic_identity"] = identity
    return TopicSnapshot(
        id=snapshot_id,
        topic_id=topic_id,
        observed_at=observed_at,
        video_count_24h=2,
        video_count_72h=4,
        distinct_channels_72h=3,
        aggregate_view_velocity=100,
        median_outlier_ratio=2,
        large_channel_count=0,
        demand_score=20,
        saturation_score=10,
        fragility_score=5,
        component_json=component_json,
    )


def test_identity_fingerprint_is_label_free_and_normalized() -> None:
    left = topic_identity_payload(_raw_identity(), definition_key="cluster-A")
    right = topic_identity_payload(
        {key: f"  {value.upper()}  " for key, value in _raw_identity().items()},
        definition_key="cluster-B",
    )

    assert left["semantic_fingerprint"] == right["semantic_fingerprint"]
    assert left["definition_key"] != right["definition_key"]
    match = match_topic_identities(left, right)
    assert match is not None
    assert match.reason_code == "exact_semantic_identity"


def test_workspace_discovery_identity_uses_workspace_and_query_ids() -> None:
    identity = topic_identity_payload(
        {
            "query": "mutable display query",
            "query_id": "query-1",
            "source": "workspace_discovery_query",
            "workspace_id": "workspace-1",
        },
        definition_key="workspace-query-cluster",
    )

    assert identity["semantic_fingerprint"]
    assert identity["semantic"] == {
        "query_id": "query-1",
        "source": "workspace_discovery_query",
        "workspace_id": "workspace-1",
    }


def test_lineage_edges_are_idempotent_and_preserve_a_unique_successor() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source_identity = topic_identity_payload(_raw_identity(), definition_key="old-cluster")
    target_identity = topic_identity_payload(_raw_identity(), definition_key="new-cluster")
    with Session(engine, expire_on_commit=False) as session:
        old = _topic("old-topic", {**_raw_identity(), "lineage": source_identity})
        new = _topic("new-topic", {**_raw_identity(), "lineage": target_identity})
        session.add_all((old, new))
        session.flush()

        first = persist_topic_lineage_edges(
            session,
            previous_topics=[old],
            current_identities={new.id: target_identity},
            detected_at=CUTOFF,
        )
        second = persist_topic_lineage_edges(
            session,
            previous_topics=[old],
            current_identities={new.id: target_identity},
            detected_at=CUTOFF + timedelta(days=1),
        )
        session.commit()

        assert len(first) == len(second) == 1
        assert session.scalar(select(func.count(TopicLineageEdge.id))) == 1
        assert old.merged_into_topic_id == new.id
        assert first[0].reason_codes_json == ["exact_semantic_identity"]
        assert first[0].detected_at.replace(tzinfo=UTC) == CUTOFF


def test_followup_resolution_uses_frozen_snapshot_identity_not_mutable_topic_copy() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    frozen_identity = topic_identity_payload(_raw_identity(), definition_key="old-cluster")
    unrelated_identity = topic_identity_payload(
        _raw_identity(claim="generate synthetic voiceovers"),
        definition_key="other-cluster",
    )
    with Session(engine) as session:
        # Current topic copies intentionally disagree with the historical snapshot.
        session.add_all(
            (
                _topic("old-topic", {"mutable": "changed later"}),
                _topic("new-topic", {"mutable": "also changed later"}),
                _topic("other-topic", {"mutable": "irrelevant"}),
            )
        )
        session.flush()
        baseline = _snapshot(
            "baseline",
            topic_id="old-topic",
            observed_at=CUTOFF - timedelta(hours=1),
            identity=frozen_identity,
        )
        successor = _snapshot(
            "successor",
            topic_id="new-topic",
            observed_at=CUTOFF + timedelta(days=2),
            identity=frozen_identity,
        )
        unrelated = _snapshot(
            "unrelated",
            topic_id="other-topic",
            observed_at=CUTOFF + timedelta(days=2),
            identity=unrelated_identity,
        )
        session.add_all((baseline, successor, unrelated))
        session.commit()

        grouped = collect_lineage_followups(
            session,
            baselines={baseline.topic_id: baseline},
            checkpoint_at=CUTOFF,
            evaluation_as_of=CUTOFF + timedelta(days=5),
            horizon_days=5,
        )

        assert [row.id for row in grouped[baseline.topic_id]] == [successor.id]
