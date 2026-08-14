from __future__ import annotations

import math
from dataclasses import dataclass

from packages.scoring.early_signal import (
    ScoreComponents,
    calculate_early_signal_score,
)


def _bounded(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


@dataclass(frozen=True)
class TopicMeasurements:
    video_count: int
    video_count_24h: int
    video_count_72h: int
    previous_video_count_24h: int
    distinct_channels: int
    distinct_channels_72h: int
    channel_size_bucket_count: int
    large_channel_count: int
    aggregate_view_velocity: float
    top_velocity_share: float
    top_channel_share: float
    median_outlier_ratio: float
    top_outlier_ratio: float
    search_appearances_24h: int
    previous_search_appearances_24h: int
    provider_coverage_count: int
    snapshot_coverage: float
    entity_count: int
    audience_demand: float = 0
    baseline_coverage: float = 0
    transcript_coverage: float = 0
    specificity_score: float = 0
    topic_age_days: float = 30


@dataclass(frozen=True)
class TopicScore:
    score: float
    components: ScoreComponents
    lifecycle_stage: str
    confidence: str


def score_topic(measurements: TopicMeasurements) -> TopicScore:
    current_rate = measurements.video_count_24h
    previous_rate = measurements.previous_video_count_24h
    acceleration = (current_rate - previous_rate) / max(previous_rate, 1)
    momentum = _bounded(
        current_rate * 13
        + measurements.video_count_72h * 4
        + math.log10(measurements.aggregate_view_velocity + 1) * 11
        + max(-10, min(20, acceleration * 18))
    )
    creator_diversity = _bounded(
        measurements.distinct_channels / max(measurements.video_count, 1) * 45
        + min(measurements.distinct_channels * 6, 35)
        + min(measurements.channel_size_bucket_count * 7, 20)
    )
    outlier_strength = _bounded(
        20
        + max(0, math.log2(max(measurements.median_outlier_ratio, 1))) * 32
        + max(0, math.log2(max(measurements.top_outlier_ratio, 1))) * 12
    )
    recent_video_share = measurements.video_count_72h / max(measurements.video_count, 1)
    recent_channel_share = measurements.distinct_channels_72h / max(
        measurements.distinct_channels,
        1,
    )
    age_freshness = 100 * math.exp(-max(0.0, measurements.topic_age_days) / 21)
    acceleration_freshness = _bounded(50 + acceleration * 25)
    novelty = _bounded(
        age_freshness * 0.45
        + min(100.0, recent_video_share * 100) * 0.25
        + min(100.0, recent_channel_share * 100) * 0.15
        + acceleration_freshness * 0.15
    )
    cross_community_spread = _bounded(
        measurements.distinct_channels_72h * 9 + measurements.channel_size_bucket_count * 12
    )
    if measurements.previous_search_appearances_24h:
        search_growth = (
            measurements.search_appearances_24h / measurements.previous_search_appearances_24h - 1
        )
        search_visibility = _bounded(50 + search_growth * 35)
    else:
        search_visibility = _bounded(25 + measurements.search_appearances_24h * 8)
    large_share = measurements.large_channel_count / max(
        measurements.distinct_channels,
        1,
    )
    saturation = _bounded(
        measurements.video_count_72h * 4 + measurements.large_channel_count * 9 + large_share * 30
    )
    fragility = _bounded(
        measurements.top_velocity_share * 48
        + measurements.top_channel_share * 34
        + (30 if measurements.video_count == 1 else 15 if measurements.video_count == 2 else 0)
        + (10 if measurements.provider_coverage_count < 2 else 0)
        + (1 - measurements.snapshot_coverage) * 25
        + (1 - measurements.baseline_coverage) * 30
        + (1 - measurements.transcript_coverage) * 6
        + max(0, 70 - measurements.specificity_score) * 0.35
    )
    components = ScoreComponents(
        momentum=momentum,
        creator_diversity=creator_diversity,
        outlier_strength=outlier_strength,
        audience_demand=_bounded(measurements.audience_demand),
        novelty=novelty,
        cross_community_spread=cross_community_spread,
        search_visibility_growth=search_visibility,
        saturation_penalty=saturation,
        fragility_penalty=fragility,
    )
    score = calculate_early_signal_score(components)
    if saturation >= 78:
        lifecycle = "Saturated"
    elif current_rate == 0 and measurements.video_count_72h == 0:
        lifecycle = "Declining"
    elif measurements.large_channel_count >= 3 and measurements.distinct_channels >= 7:
        lifecycle = "Mass Market"
    elif momentum >= 72 and measurements.distinct_channels >= 5:
        lifecycle = "Breakout"
    elif measurements.distinct_channels >= 3 and (current_rate >= 2 or momentum >= 46):
        lifecycle = "Emerging"
    else:
        lifecycle = "Seed"
    confidence = (
        "High"
        if measurements.video_count >= 6
        and measurements.distinct_channels >= 5
        and measurements.snapshot_coverage >= 0.9
        and measurements.baseline_coverage >= 0.7
        and measurements.specificity_score >= 70
        else "Medium"
        if measurements.video_count >= 3
        and measurements.distinct_channels >= 3
        and measurements.snapshot_coverage >= 0.7
        and measurements.baseline_coverage >= 0.5
        and measurements.specificity_score >= 65
        else "Low"
    )
    return TopicScore(
        score=score,
        components=components,
        lifecycle_stage=lifecycle,
        confidence=confidence,
    )
