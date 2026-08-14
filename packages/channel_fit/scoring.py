from __future__ import annotations

import re
from dataclasses import asdict, dataclass

FIT_VERSION = "channel-fit-v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}")
WEIGHTS = {
    "topical_relevance": 0.24,
    "audience_overlap": 0.12,
    "format_compatibility": 0.12,
    "authority_or_credibility": 0.12,
    "production_feasibility": 0.12,
    "historical_performance_similarity": 0.14,
    "timing_feasibility": 0.14,
}


def bounded(value: float) -> float:
    return min(100.0, max(0.0, value))


def tokens(values: list[str] | tuple[str, ...] | str) -> set[str]:
    if isinstance(values, str):
        values = [values]
    return {
        token
        for value in values
        for token in TOKEN_PATTERN.findall(value.lower())
        if len(token) >= 3
    }


def token_overlap_score(
    topic_values: list[str] | tuple[str, ...],
    profile_values: list[str] | tuple[str, ...],
    *,
    floor: float = 20,
) -> float:
    topic = tokens(topic_values)
    profile = tokens(profile_values)
    if not topic or not profile:
        return floor
    coverage = len(topic & profile) / max(1, min(len(topic), 12))
    return round(bounded(floor + coverage * (100 - floor)), 1)


@dataclass(frozen=True)
class ChannelFitComponents:
    topical_relevance: float
    audience_overlap: float
    format_compatibility: float
    authority_or_credibility: float
    production_feasibility: float
    historical_performance_similarity: float
    timing_feasibility: float
    cannibalization_penalty: float
    brand_risk_penalty: float

    def normalized(self) -> ChannelFitComponents:
        return ChannelFitComponents(
            **{key: round(bounded(float(value)), 1) for key, value in asdict(self).items()}
        )


def calculate_channel_fit(components: ChannelFitComponents) -> float:
    values = components.normalized()
    positive = sum(
        float(getattr(values, component)) * weight for component, weight in WEIGHTS.items()
    )
    penalties = values.cannibalization_penalty * 0.1 + values.brand_risk_penalty * 0.2
    return round(bounded(positive - penalties), 1)
