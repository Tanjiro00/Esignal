from dataclasses import dataclass


def _bounded(value: float) -> float:
    return min(100.0, max(0.0, value))


@dataclass(frozen=True)
class ScoreComponents:
    momentum: float
    creator_diversity: float
    outlier_strength: float
    audience_demand: float
    novelty: float
    cross_community_spread: float
    search_visibility_growth: float
    saturation_penalty: float
    fragility_penalty: float

    def normalized(self) -> "ScoreComponents":
        return ScoreComponents(**{key: _bounded(value) for key, value in self.__dict__.items()})


def calculate_early_signal_score(components: ScoreComponents) -> float:
    """Apply the transparent heuristic from the MVP specification.

    The positive weights sum to one. Penalties are additional deductions and
    the customer-facing score is always kept within 0–100.
    """

    c = components.normalized()
    score = (
        0.22 * c.momentum
        + 0.16 * c.creator_diversity
        + 0.16 * c.outlier_strength
        + 0.15 * c.audience_demand
        + 0.12 * c.novelty
        + 0.10 * c.cross_community_spread
        + 0.09 * c.search_visibility_growth
        - 0.14 * c.saturation_penalty
        - 0.10 * c.fragility_penalty
    )
    return round(_bounded(score), 1)
