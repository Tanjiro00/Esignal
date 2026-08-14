from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestOutcome,
    BacktestPrediction,
    BacktestRun,
    Base,
    Topic,
    TopicSnapshot,
)
from packages.backtest import (
    BlindOutcomeLabeler,
    OutcomeLabelPolicy,
    QualityGatePolicy,
    ReplayPolicy,
    TemporalReplayService,
    calculate_backtest_metrics,
    render_markdown_report,
)
from packages.topic_lineage import topic_identity_payload

CUTOFF = datetime(2026, 5, 1, 12, tzinfo=UTC)


def _topic(topic_id: str) -> Topic:
    return Topic(
        id=topic_id,
        canonical_label=f"mutable current label {topic_id}",
        aliases_json=[],
        entities_json=[],
        centroid_embedding=[],
        embedding_model="test",
        embedding_version="test",
        first_observed_at=CUTOFF - timedelta(days=10),
        first_confirmed_at=CUTOFF - timedelta(days=9),
        lifecycle_stage="Mass Market",
        status="active",
        source_kind="live",
        merged_into_topic_id=None,
        clustering_version="test",
        identity_json={"mutable": "future copy must not be read"},
        specificity_score=99,
        thesis_support_ratio=1,
        visibility_reason_codes_json=[],
    )


def _snapshot(
    snapshot_id: str,
    *,
    topic_id: str,
    observed_at: datetime,
    score: float,
    supply: int,
    lift: float,
    identity_key: str | None = None,
) -> TopicSnapshot:
    topic_identity = topic_identity_payload(
        {
            "audience": "test audience",
            "core_claim": "test claim",
            "domain": "test domain",
            "facet": "test facet",
            "primary_entity": identity_key or topic_id,
            "user_problem": "test problem",
            "workflow_context": "test context",
        },
        definition_key=identity_key or topic_id,
    )
    return TopicSnapshot(
        id=snapshot_id,
        topic_id=topic_id,
        observed_at=observed_at,
        video_count_24h=max(2, supply // 2),
        video_count_72h=supply,
        distinct_channels_72h=3,
        aggregate_view_velocity=500,
        median_outlier_ratio=lift,
        large_channel_count=0,
        demand_score=65,
        saturation_score=20,
        fragility_score=15,
        component_json={
            "baseline_coverage": 0.9,
            "distinct_channels": 5,
            "previous_video_count_24h": 1,
            "score": score,
            "snapshot_coverage": 1,
            "specificity_score": 82,
            "top_channel_share": 0.3,
            "top_outlier_ratio": max(2, lift),
            "top_velocity_share": 0.4,
            "topic_identity": topic_identity,
            "transcript_coverage": 0.5,
            "video_count": max(6, supply),
        },
    )


def _seed(session: Session) -> BacktestCheckpoint:
    run = BacktestRun(
        id="run-1",
        idempotency_key="run-1",
        name="test",
        status="success",
        source_kind="live",
        dataset_version="test",
        code_revision="test",
        code_dirty=False,
        migration_revision="test",
        config_json={},
        model_versions_json={},
        started_at=CUTOFF,
        completed_at=CUTOFF,
        error_code=None,
        error_message=None,
        created_at=CUTOFF,
    )
    checkpoint = BacktestCheckpoint(
        id="checkpoint-1",
        run_id=run.id,
        checkpoint_at=CUTOFF,
        status="success",
        manifest_version="test",
        manifest_json={},
        input_hash="input",
        eligible_video_count=3,
        snapshot_count=3,
        prediction_count=0,
        completed_at=CUTOFF,
        created_at=CUTOFF,
    )
    session.add(run)
    session.flush()
    session.add(checkpoint)
    session.add_all((_topic("topic-a"), _topic("topic-b"), _topic("topic-c")))
    session.flush()
    session.add_all(
        (
            _snapshot(
                "a-baseline",
                topic_id="topic-a",
                observed_at=CUTOFF - timedelta(hours=1),
                score=90,
                supply=2,
                lift=1.2,
            ),
            _snapshot(
                "b-baseline",
                topic_id="topic-b",
                observed_at=CUTOFF - timedelta(hours=1),
                score=70,
                supply=3,
                lift=1.2,
            ),
            _snapshot(
                "c-baseline",
                topic_id="topic-c",
                observed_at=CUTOFF - timedelta(hours=1),
                score=60,
                supply=2,
                lift=1.2,
            ),
            _snapshot(
                "a-fired",
                topic_id="topic-a",
                observed_at=CUTOFF + timedelta(days=25),
                score=5,
                supply=7,
                lift=3.4,
            ),
            _snapshot(
                "b-future-high-score",
                topic_id="topic-b",
                observed_at=CUTOFF + timedelta(days=20),
                score=100,
                supply=4,
                lift=1.5,
            ),
            _snapshot(
                "b-negative-followup",
                topic_id="topic-b",
                observed_at=CUTOFF + timedelta(days=41),
                score=100,
                supply=4,
                lift=1.5,
            ),
            _snapshot(
                "c-fired",
                topic_id="topic-c",
                observed_at=CUTOFF + timedelta(days=30),
                score=95,
                supply=6,
                lift=3.2,
            ),
            _snapshot(
                "c-followup",
                topic_id="topic-c",
                observed_at=CUTOFF + timedelta(days=41),
                score=95,
                supply=7,
                lift=3.1,
            ),
        )
    )
    session.commit()
    return checkpoint


def _session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(engine)


def test_replay_ignores_future_scores_and_is_idempotent() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        service = TemporalReplayService(session)
        policy = ReplayPolicy(top_k=2)

        predictions, universe = service.replay_checkpoint(checkpoint, policy=policy)
        repeated, _ = service.replay_checkpoint(checkpoint, policy=policy)

        assert [row.candidate_key for row in predictions] == ["topic-a", "topic-b"]
        assert [row.score for row in predictions] == [90, 70]
        assert [row.candidate_key for row in repeated] == ["topic-a", "topic-b"]
        assert len(universe) == 3
        assert session.scalar(select(func.count(BacktestPrediction.id))) == 2
        assert all(row.evidence_json["mutable_topic_copy_excluded"] for row in predictions)
        assert all(row.evidence_json["topic_lineage_snapshot_bound"] for row in predictions)


def test_blind_labeler_follows_frozen_identity_across_topic_id_change() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        session.add_all((_topic("topic-old"), _topic("topic-successor")))
        session.flush()
        session.add_all(
            (
                _snapshot(
                    "lineage-baseline",
                    topic_id="topic-old",
                    observed_at=CUTOFF - timedelta(hours=1),
                    score=80,
                    supply=2,
                    lift=1.1,
                    identity_key="shared-lineage",
                ),
                _snapshot(
                    "lineage-fired",
                    topic_id="topic-successor",
                    observed_at=CUTOFF + timedelta(days=20),
                    score=10,
                    supply=7,
                    lift=3.4,
                    identity_key="shared-lineage",
                ),
            )
        )
        session.commit()

        outcomes = BlindOutcomeLabeler(session).label_checkpoint(
            checkpoint,
            evaluation_as_of=CUTOFF + timedelta(days=43),
        )
        by_key = {row.candidate_key: row for row in outcomes}

        assert by_key["topic-old"].fired is True
        assert by_key["topic-old"].evidence_json["lineage_resolution"] == {
            "snapshot_identity_available": True,
            "successor_topic_used": True,
            "version": "snapshot-identity-and-stored-edge-v1",
        }
        assert by_key["topic-old"].evidence_json["followup_topic_ids"] == ["topic-successor"]


def test_blind_labeler_requires_joint_supply_and_lift_and_complete_followup() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        outcomes = BlindOutcomeLabeler(session).label_checkpoint(
            checkpoint,
            evaluation_as_of=CUTOFF + timedelta(days=43),
            policy=OutcomeLabelPolicy(horizon_days=42),
        )
        by_key = {row.candidate_key: row for row in outcomes}

        assert by_key["topic-a"].fired is True
        assert by_key["topic-a"].fired_at.replace(tzinfo=UTC) == CUTOFF + timedelta(days=25)
        assert by_key["topic-b"].status == "evaluated"
        assert by_key["topic-b"].fired is False
        assert by_key["topic-c"].fired is True
        assert all(row.evidence_json["prediction_fields_read"] is False for row in outcomes)
        assert session.scalar(select(func.count(BacktestOutcome.id))) == 3


def test_incomplete_followup_is_not_counted_as_a_false_positive() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        outcomes = BlindOutcomeLabeler(session).label_checkpoint(
            checkpoint,
            evaluation_as_of=CUTOFF + timedelta(days=10),
        )

        assert {row.status for row in outcomes} == {"insufficient_followup"}
        assert all(not row.fired for row in outcomes)


def test_precision_lead_time_and_recall_are_computed_from_evaluated_rows_only() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        predictions, _ = TemporalReplayService(session).replay_checkpoint(
            checkpoint,
            policy=ReplayPolicy(top_k=1),
        )
        outcomes = BlindOutcomeLabeler(session).label_checkpoint(
            checkpoint,
            evaluation_as_of=CUTOFF + timedelta(days=43),
        )
        metrics, gate = calculate_backtest_metrics(
            checkpoints=[checkpoint],
            predictions=predictions,
            outcomes=outcomes,
            gate_policy=QualityGatePolicy(
                top_k=1,
                minimum_checkpoints=1,
                minimum_precision_percent=40,
                minimum_median_lead_days=21,
                minimum_evaluation_coverage_percent=80,
            ),
        )

        assert metrics["precision_at_k_percent"] == 100
        assert metrics["lead_time_days"]["median"] == 25
        assert metrics["recall_percent"] == 50
        assert gate["passed"] is True


def test_report_does_not_present_missing_followup_as_zero_quality() -> None:
    with _session() as session:
        checkpoint = _seed(session)
        predictions, _ = TemporalReplayService(session).replay_checkpoint(
            checkpoint,
            policy=ReplayPolicy(top_k=1),
        )
        outcomes = BlindOutcomeLabeler(session).label_checkpoint(
            checkpoint,
            evaluation_as_of=CUTOFF + timedelta(days=10),
        )
        metrics, gate = calculate_backtest_metrics(
            checkpoints=[checkpoint],
            predictions=predictions,
            outcomes=outcomes,
        )

        report = render_markdown_report(
            name="incomplete",
            checkpoint_ids=[checkpoint.id],
            metrics=metrics,
            gate=gate,
        )

        assert "**Quality gate:** INSUFFICIENT DATA" in report
        assert "Precision@10:** N/A" in report
        assert "Median lead time:** N/A" in report
        assert "| checkpoint_count | N/A | 6 | PENDING |" in report
        assert "| precision_at_k_percent | N/A | 40 | PENDING |" in report
        assert "| precision_at_k_percent | 0.0 | 40 | FAIL |" not in report
