from types import SimpleNamespace

from apps.api.config import Settings
from apps.worker.topic_intelligence import TopicIntelligenceService


def _service() -> TopicIntelligenceService:
    service = object.__new__(TopicIntelligenceService)
    service._settings = Settings(feature_microtopic_content_gap=True)
    return service


def test_cross_channel_seed_can_be_published_as_watch_candidate() -> None:
    definition = SimpleNamespace(specificity_score=82, thesis_support_ratio=0.9)
    measurements = SimpleNamespace(
        video_count=6,
        video_count_72h=1,
        distinct_channels=5,
        distinct_channels_72h=1,
        baseline_coverage=0.8,
        median_outlier_ratio=1.3,
        top_outlier_ratio=2.1,
        top_velocity_share=0.5,
    )
    score = SimpleNamespace(score=26, lifecycle_stage="Seed")

    assert _service()._is_actionable(  # type: ignore[arg-type]
        definition,
        measurements,
        score,
    )


def test_three_channel_seed_can_be_published_as_early_watch() -> None:
    definition = SimpleNamespace(specificity_score=82, thesis_support_ratio=0.9)
    measurements = SimpleNamespace(
        video_count=3,
        video_count_72h=1,
        distinct_channels=3,
        distinct_channels_72h=1,
        baseline_coverage=0.8,
        median_outlier_ratio=1.3,
        top_outlier_ratio=2.1,
        top_velocity_share=0.5,
    )
    score = SimpleNamespace(score=38, lifecycle_stage="Seed")

    assert _service()._is_actionable(  # type: ignore[arg-type]
        definition,
        measurements,
        score,
    )


def test_two_channel_seed_evidence_stays_internal() -> None:
    definition = SimpleNamespace(specificity_score=82, thesis_support_ratio=0.9)
    measurements = SimpleNamespace(
        video_count=2,
        video_count_72h=1,
        distinct_channels=2,
        distinct_channels_72h=1,
        baseline_coverage=0.8,
        median_outlier_ratio=1.3,
        top_outlier_ratio=2.1,
        top_velocity_share=0.5,
    )
    score = SimpleNamespace(score=38, lifecycle_stage="Seed")

    assert not _service()._is_actionable(  # type: ignore[arg-type]
        definition,
        measurements,
        score,
    )


def test_personal_lane_uses_cross_channel_freshness_when_baselines_are_new() -> None:
    definition = SimpleNamespace(
        specificity_score=86,
        thesis_support_ratio=1.0,
        facet="workspace_discovery",
    )
    measurements = SimpleNamespace(
        video_count=12,
        video_count_72h=8,
        distinct_channels=12,
        distinct_channels_72h=8,
        baseline_coverage=0.16,
        median_outlier_ratio=1.0,
        top_outlier_ratio=1.0,
        top_velocity_share=0.78,
    )
    score = SimpleNamespace(score=53, lifecycle_stage="Breakout")

    assert _service()._is_actionable(  # type: ignore[arg-type]
        definition,
        measurements,
        score,
    )
