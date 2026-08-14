from packages.decision_experience import (
    assess_decision,
    score_to_user_bucket_v1,
)


def test_score_bucket_preserves_supported_raw_band() -> None:
    bucket = score_to_user_bucket_v1(
        88,
        fragility_penalty=20,
        baseline_coverage_percent=92,
        specificity_score=86,
    )

    assert bucket.label == "Very high"
    assert bucket.reason_codes == ("evidence_supports_raw_band",)


def test_weak_baseline_downgrades_a_high_score() -> None:
    bucket = score_to_user_bucket_v1(
        82,
        fragility_penalty=30,
        baseline_coverage_percent=52,
        specificity_score=82,
    )

    assert bucket.label == "Moderate"
    assert "weak_baseline_coverage" in bucket.reason_codes


def test_multiple_fragility_signals_never_inflate_a_bucket() -> None:
    bucket = score_to_user_bucket_v1(
        91,
        fragility_penalty=80,
        baseline_coverage_percent=25,
        specificity_score=48,
    )

    assert bucket.label == "Moderate"
    assert {
        "very_high_fragility",
        "very_weak_baseline_coverage",
        "weak_topic_specificity",
    }.issubset(bucket.reason_codes)


def test_decision_requires_signal_fit_and_evidence() -> None:
    assert (
        assess_decision(
            signal_bucket="High",
            fit_bucket="High",
            evidence_bucket="Moderate",
            lifecycle_stage="Emerging",
            saturation_penalty=32,
        ).decision
        == "Act"
    )
    assert (
        assess_decision(
            signal_bucket="High",
            fit_bucket="Moderate",
            evidence_bucket="Moderate",
            lifecycle_stage="Emerging",
            saturation_penalty=32,
        ).decision
        == "Watch"
    )
    assert (
        assess_decision(
            signal_bucket="Very high",
            fit_bucket="Very high",
            evidence_bucket="High",
            lifecycle_stage="Saturated",
            saturation_penalty=92,
        ).decision
        == "Skip"
    )


def test_seed_signal_is_never_promoted_beyond_watch() -> None:
    assessment = assess_decision(
        signal_bucket="Very high",
        fit_bucket="Very high",
        evidence_bucket="High",
        lifecycle_stage="Seed",
        saturation_penalty=12,
    )

    assert assessment.decision == "Watch"
    assert assessment.reason_codes == ("early_evidence_watch",)


def test_trend_without_a_non_obvious_insight_is_not_released_for_action() -> None:
    assessment = assess_decision(
        signal_bucket="Very high",
        fit_bucket="Very high",
        evidence_bucket="High",
        lifecycle_stage="Emerging",
        saturation_penalty=12,
        insight_ready=False,
    )

    assert assessment.decision == "Skip"
    assert assessment.reason_codes == ("no_evidence_backed_insight",)
