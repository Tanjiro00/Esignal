from scripts.run_youniverse_structural_evaluation import (
    FALLBACK_LADDER,
    PRIMARY_VARIANT,
    is_train_feasible,
    robustness_variants,
    select_train_variant,
    train_feasibility,
)


def _payload(*, candidates: int, predictions: int, coverage: float | None) -> dict:
    return {
        "metrics": {
            "candidate_topics": candidates,
            "rankings": {
                "method": {
                    "predictions": predictions,
                    "prediction_outcome_baseline_coverage_percent": coverage,
                    "future_video_baseline_coverage_percent": coverage,
                }
            },
        }
    }


def test_feasibility_is_independent_of_precision_and_fired_labels() -> None:
    payload = _payload(candidates=50, predictions=50, coverage=80)
    payload["metrics"]["fired_candidate_topics"] = 0
    payload["metrics"]["rankings"]["method"]["precision_at_10_percent"] = 0

    assert is_train_feasible(payload)
    assert all(train_feasibility(payload).values())


def test_selection_uses_first_feasible_ladder_row() -> None:
    evaluated = [
        (PRIMARY_VARIANT, _payload(candidates=49, predictions=100, coverage=100)),
        (FALLBACK_LADDER[0], _payload(candidates=80, predictions=49, coverage=100)),
        (FALLBACK_LADDER[1], _payload(candidates=80, predictions=80, coverage=80)),
        (FALLBACK_LADDER[2], _payload(candidates=100, predictions=100, coverage=100)),
    ]

    assert select_train_variant(evaluated) == FALLBACK_LADDER[1]


def test_selection_retains_primary_when_no_variant_is_feasible() -> None:
    evaluated = [
        (PRIMARY_VARIANT, _payload(candidates=0, predictions=0, coverage=None)),
        (FALLBACK_LADDER[0], _payload(candidates=2, predictions=2, coverage=0)),
    ]

    assert select_train_variant(evaluated) == PRIMARY_VARIANT


def test_robustness_changes_one_candidate_policy_dimension_at_a_time() -> None:
    variants = robustness_variants(PRIMARY_VARIANT)

    assert variants
    assert len(variants) == len(
        {
            (
                variant.minimum_channels,
                variant.recent_window_days,
                variant.maximum_active_videos,
                variant.episode_cooldown_days,
            )
            for variant in variants
        }
    )
    for variant in variants:
        differences = sum(
            left != right
            for left, right in zip(
                (
                    variant.minimum_channels,
                    variant.recent_window_days,
                    variant.maximum_active_videos,
                    variant.episode_cooldown_days,
                ),
                (
                    PRIMARY_VARIANT.minimum_channels,
                    PRIMARY_VARIANT.recent_window_days,
                    PRIMARY_VARIANT.maximum_active_videos,
                    PRIMARY_VARIANT.episode_cooldown_days,
                ),
                strict=True,
            )
        )
        assert differences == 1
