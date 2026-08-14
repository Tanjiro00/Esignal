from packages.scoring import (
    ScoreComponents,
    TopicMeasurements,
    calculate_early_signal_score,
    score_topic,
)


def test_score_uses_transparent_specification_weights() -> None:
    components = ScoreComponents(
        momentum=100,
        creator_diversity=100,
        outlier_strength=100,
        audience_demand=100,
        novelty=100,
        cross_community_spread=100,
        search_visibility_growth=100,
        saturation_penalty=0,
        fragility_penalty=0,
    )
    assert calculate_early_signal_score(components) == 100


def test_penalties_and_bounds_are_applied() -> None:
    components = ScoreComponents(
        momentum=20,
        creator_diversity=20,
        outlier_strength=20,
        audience_demand=20,
        novelty=20,
        cross_community_spread=20,
        search_visibility_growth=20,
        saturation_penalty=100,
        fragility_penalty=100,
    )
    assert calculate_early_signal_score(components) == 0


def test_inputs_are_bounded_before_scoring() -> None:
    components = ScoreComponents(120, 120, 120, 120, 120, 120, 120, -20, -20)
    assert calculate_early_signal_score(components) == 100


def _topic_measurements(**overrides: int | float) -> TopicMeasurements:
    values: dict[str, int | float] = {
        "video_count": 6,
        "video_count_24h": 3,
        "video_count_72h": 6,
        "previous_video_count_24h": 1,
        "distinct_channels": 6,
        "distinct_channels_72h": 6,
        "channel_size_bucket_count": 3,
        "large_channel_count": 1,
        "aggregate_view_velocity": 4000,
        "top_velocity_share": 0.25,
        "top_channel_share": 1 / 6,
        "median_outlier_ratio": 1.8,
        "top_outlier_ratio": 3.2,
        "search_appearances_24h": 8,
        "previous_search_appearances_24h": 2,
        "provider_coverage_count": 2,
        "snapshot_coverage": 1,
        "entity_count": 4,
        "audience_demand": 0,
        "baseline_coverage": 1,
        "transcript_coverage": 0.5,
        "specificity_score": 80,
        "topic_age_days": 7,
    }
    values.update(overrides)
    return TopicMeasurements(**values)  # type: ignore[arg-type]


def test_one_video_topic_receives_fragility_penalty() -> None:
    result = score_topic(
        _topic_measurements(
            video_count=1,
            distinct_channels=1,
            distinct_channels_72h=1,
            top_velocity_share=1,
            top_channel_share=1,
            provider_coverage_count=1,
        )
    )
    assert result.components.fragility_penalty >= 90
    assert result.confidence == "Low"


def test_saturated_topic_cannot_remain_seed() -> None:
    result = score_topic(
        _topic_measurements(
            video_count=18,
            video_count_72h=18,
            distinct_channels=12,
            distinct_channels_72h=12,
            large_channel_count=8,
        )
    )
    assert result.components.saturation_penalty >= 78
    assert result.lifecycle_stage == "Saturated"


def test_topic_components_are_bounded_and_lifecycle_is_deterministic() -> None:
    first = score_topic(_topic_measurements())
    second = score_topic(_topic_measurements())
    assert first == second
    assert all(0 <= value <= 100 for value in first.components.normalized().__dict__.values())


def test_confirmed_audience_demand_increases_score_transparently() -> None:
    without_demand = score_topic(_topic_measurements(audience_demand=0))
    with_demand = score_topic(_topic_measurements(audience_demand=80))

    assert with_demand.components.audience_demand == 80
    assert with_demand.score == without_demand.score + 12


def test_novelty_uses_temporal_change_not_entity_count() -> None:
    sparse_entities = score_topic(_topic_measurements(entity_count=1))
    many_entities = score_topic(_topic_measurements(entity_count=20))

    assert sparse_entities.components.novelty == many_entities.components.novelty


def test_old_topic_is_less_novel_than_a_recent_topic_with_the_same_activity() -> None:
    recent = score_topic(_topic_measurements(topic_age_days=2))
    old = score_topic(_topic_measurements(topic_age_days=120))

    assert recent.components.novelty > old.components.novelty
    assert recent.score > old.score
