from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import Base, TopicPipelineRun
from apps.worker.topic_intelligence import TopicIntelligenceService


def test_stale_topic_pipeline_runs_are_failed_and_recoverable() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            TopicPipelineRun(
                id="stale-run",
                idempotency_key="topic:stale",
                started_at=now - timedelta(hours=2),
                completed_at=None,
                status="running",
                clustering_version="test",
                embedding_version="test",
                source_video_count=0,
                eligible_video_count=0,
                topic_count=0,
                signal_count=0,
                clustering_lag_seconds=0,
                signal_generation_lag_seconds=0,
                llm_policy_version="test",
                llm_trace_json={},
                error_code=None,
                error_message=None,
            )
        )
        session.commit()
        service = object.__new__(TopicIntelligenceService)
        service._session = session
        service._settings = Settings(
            _env_file=None,
            topic_pipeline_stale_minutes=30,
        )

        recovered = service.reconcile_stale_runs(now=now)

        assert recovered == 1
        row = session.scalar(select(TopicPipelineRun))
        assert row is not None
        assert row.status == "failed"
        assert row.completed_at.replace(tzinfo=UTC) == now
        assert row.error_code == "stale_run_recovered"
