from packages.channel_fit import (
    FIT_VERSION,
    ChannelFitComponents,
    calculate_channel_fit,
    token_overlap_score,
)


def test_channel_fit_uses_all_positive_components_and_penalties() -> None:
    strong = ChannelFitComponents(
        topical_relevance=100,
        audience_overlap=100,
        format_compatibility=100,
        authority_or_credibility=100,
        production_feasibility=100,
        historical_performance_similarity=100,
        timing_feasibility=100,
        cannibalization_penalty=0,
        brand_risk_penalty=0,
    )
    penalized = ChannelFitComponents(
        **{
            **strong.__dict__,
            "cannibalization_penalty": 100,
            "brand_risk_penalty": 100,
        }
    )

    assert FIT_VERSION == "channel-fit-v1"
    assert calculate_channel_fit(strong) == 100
    assert calculate_channel_fit(penalized) == 70


def test_channel_fit_inputs_are_bounded() -> None:
    components = ChannelFitComponents(
        topical_relevance=130,
        audience_overlap=130,
        format_compatibility=130,
        authority_or_credibility=130,
        production_feasibility=130,
        historical_performance_similarity=130,
        timing_feasibility=130,
        cannibalization_penalty=-20,
        brand_risk_penalty=-20,
    )

    assert calculate_channel_fit(components) == 100
    assert all(0 <= value <= 100 for value in components.normalized().__dict__.values())


def test_token_overlap_is_deterministic_and_keeps_an_explicit_floor() -> None:
    matching = token_overlap_score(
        ["local AI video generation", "consumer GPUs"],
        ["Practical local AI video tests on consumer GPUs"],
        floor=20,
    )
    unrelated = token_overlap_score(
        ["local AI video generation"],
        ["mechanical keyboard reviews"],
        floor=20,
    )

    assert matching > unrelated
    assert unrelated == 20
