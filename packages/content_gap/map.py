from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from statistics import median

from packages.clustering import MicrotopicDocument, infer_microtopic_identity_v6

CONTENT_PATTERN_VERSION = "topic-content-pattern-v1"
CONTENT_GAP_VERSION = "content-gap-v4"
OPPORTUNITY_RANKING_VERSION = "opportunity-ranking-v5"
MINIMUM_INSIGHT_PATTERN_SAMPLE = 6
MINIMUM_PERFORMANCE_GROUP_SIZE = 3
MINIMUM_PERFORMANCE_LIFT = 1.5
MINIMUM_PERFORMANCE_MEDIAN = 1.25
INSIGHT_DIMENSIONS = ("claim", "context", "product_anchor")
GENERIC_INSIGHT_VALUES = {
    "",
    "unknown",
    "ai practitioners",
    "developer tools",
    "deliver a measurable practical outcome",
    "practical day-to-day use",
}

AUDIENCE_MARKERS = {
    "audience",
    "beginner",
    "builder",
    "business",
    "creator",
    "developer",
    "engineer",
    "entrepreneur",
    "founder",
    "leader",
    "marketer",
    "operator",
    "owner",
    "people",
    "practitioner",
    "professional",
    "student",
    "team",
}


@dataclass(frozen=True)
class ContentPattern:
    video_id: str
    audience: str
    claim: str
    format: str
    context: str
    emotion: str
    product_anchor: str
    proof_type: str
    production_complexity: str
    pattern_key: str
    evidence_refs: tuple[str, ...]
    channel_id: str = ""
    outlier_ratio: float = 1.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PerformanceInsight:
    dimension: str
    value: str
    group_size: int
    comparison_size: int
    group_median: float
    comparison_median: float
    lift: float
    winning_evidence_refs: tuple[str, ...]
    comparison_evidence_refs: tuple[str, ...]


def _matches(text: str, *patterns: str) -> bool:
    lowered = f" {text.lower()} "
    return any(pattern in lowered for pattern in patterns)


def _emotion(text: str) -> str:
    if _matches(text, " fail", " risk", " unsafe", " cost", " mistake", " warning"):
        return "risk"
    if _matches(text, " best ", " vs ", " compare", " benchmark", " worth"):
        return "evaluation"
    if _matches(text, " wow", " amazing", " insane", " changed everything", " breakthrough"):
        return "excitement"
    return "curiosity"


def _proof_type(text: str, content_format: str) -> str:
    if _matches(text, " benchmark", " tested", " stress test", " experiment"):
        return "original test"
    if content_format == "structured comparison":
        return "comparative proof"
    if content_format == "tutorial":
        return "demonstration"
    if _matches(text, " case study", " for 7 days", " real project"):
        return "case evidence"
    return "commentary"


def _complexity(text: str, content_format: str) -> str:
    if _matches(text, " production", " deploy", " local ", " gpu", " build ", " case study"):
        return "high"
    if content_format in {"hands-on test", "tutorial", "structured comparison"}:
        return "medium"
    return "low"


def extract_content_pattern(
    *,
    video_id: str,
    title: str,
    description: str,
    entities: tuple[str, ...],
    transcript_format: str | None = None,
    narrative_angle: str | None = None,
    channel_id: str = "",
    outlier_ratio: float = 1.0,
) -> ContentPattern:
    identity = infer_microtopic_identity_v6(
        MicrotopicDocument(
            id=video_id,
            title=title,
            description=description,
            entities=entities,
        )
    )
    text = " ".join((title, description[:1_200], narrative_angle or ""))
    content_format = (
        transcript_format
        if transcript_format and transcript_format != "unknown"
        else identity.content_format
        if identity is not None
        else "evidence-led explainer"
    )
    audience = identity.audience if identity is not None else "AI practitioners"
    claim = (
        identity.core_claim if identity is not None else "deliver a measurable practical outcome"
    )
    context = identity.workflow_context if identity is not None else "practical day-to-day use"
    product_anchor = (
        identity.primary_entity
        if identity is not None
        else (entities[0] if entities else "unknown")
    )
    proof_type = _proof_type(text, content_format)
    complexity = _complexity(text, content_format)
    values = (
        audience,
        claim,
        content_format,
        context,
        _emotion(text),
        product_anchor,
        proof_type,
        complexity,
    )
    key = sha256("|".join(values).encode()).hexdigest()[:24]
    return ContentPattern(
        video_id=video_id,
        audience=audience,
        claim=claim,
        format=content_format,
        context=context,
        emotion=_emotion(text),
        product_anchor=product_anchor,
        proof_type=proof_type,
        production_complexity=complexity,
        pattern_key=key,
        evidence_refs=(f"video:{video_id}",),
        channel_id=channel_id,
        outlier_ratio=round(max(0.0, float(outlier_ratio)), 3),
    )


def _dominant(patterns: list[ContentPattern], field: str) -> tuple[str, float]:
    counts = Counter(str(getattr(pattern, field)) for pattern in patterns)
    if not counts:
        return "unknown", 0
    value, count = counts.most_common(1)[0]
    return value, round(count / len(patterns), 3)


def _bounded(value: float) -> float:
    return min(100.0, max(0.0, float(value)))


def _audience_label(profile_audience: str, fallback: str) -> str:
    candidate = " ".join(profile_audience.strip().split()).split(".")[0].strip(" -–—|")
    tokens = {
        token.strip(".,:;!?()[]{}").lower()
        for token in candidate.split()
        if token.strip(".,:;!?()[]{}")
    }
    if (
        not candidate
        or len(candidate) > 72
        or not any(
            token in AUDIENCE_MARKERS
            or any(
                token.startswith(f"{marker}s") or token.startswith(f"{marker}ers")
                for marker in AUDIENCE_MARKERS
            )
            for token in tokens
        )
    ):
        return fallback
    return candidate


def _candidate_score(components: dict[str, float]) -> float:
    return round(
        _bounded(
            components["unmet_demand_strength"] * 0.18
            + components["content_gap_strength"] * 0.20
            + components["channel_fit"] * 0.18
            + components["production_feasibility"] * 0.10
            + components["timing"] * 0.10
            + components["evidence_strength"] * 0.10
            + components["novelty"] * 0.10
            - components["brand_risk"] * 0.06
        ),
        1,
    )


def _performance_insight(patterns: list[ContentPattern]) -> PerformanceInsight | None:
    """Find a repeated, channel-relative performance split in stored evidence.

    A missing content cell is not an insight by itself. This only returns a
    pattern when both the winning group and the comparison group have repeated
    evidence and the median channel-relative lift clears a conservative floor.
    """

    if len(patterns) < MINIMUM_INSIGHT_PATTERN_SAMPLE:
        return None

    candidates: list[PerformanceInsight] = []
    # Performance by presentation style is not a content insight. Keep the
    # release gate limited to what the coverage is substantively about.
    for dimension in INSIGHT_DIMENSIONS:
        values = sorted({str(getattr(pattern, dimension)) for pattern in patterns})
        for value in values:
            if value.strip().lower() in GENERIC_INSIGHT_VALUES:
                continue
            group = [pattern for pattern in patterns if str(getattr(pattern, dimension)) == value]
            comparison = [
                pattern for pattern in patterns if str(getattr(pattern, dimension)) != value
            ]
            if (
                len(group) < MINIMUM_PERFORMANCE_GROUP_SIZE
                or len(comparison) < MINIMUM_PERFORMANCE_GROUP_SIZE
            ):
                continue
            group_channels = {pattern.channel_id or pattern.video_id for pattern in group}
            comparison_channels = {pattern.channel_id or pattern.video_id for pattern in comparison}
            if (
                len(group_channels) < MINIMUM_PERFORMANCE_GROUP_SIZE
                or len(comparison_channels) < MINIMUM_PERFORMANCE_GROUP_SIZE
            ):
                continue
            group_median = float(median(pattern.outlier_ratio for pattern in group))
            comparison_median = float(median(pattern.outlier_ratio for pattern in comparison))
            lift = group_median / max(comparison_median, 0.1)
            if group_median < MINIMUM_PERFORMANCE_MEDIAN or lift < MINIMUM_PERFORMANCE_LIFT:
                continue
            candidates.append(
                PerformanceInsight(
                    dimension=dimension,
                    value=value,
                    group_size=len(group),
                    comparison_size=len(comparison),
                    group_median=round(group_median, 2),
                    comparison_median=round(comparison_median, 2),
                    lift=round(lift, 2),
                    winning_evidence_refs=tuple(
                        reference for pattern in group for reference in pattern.evidence_refs
                    ),
                    comparison_evidence_refs=tuple(
                        reference for pattern in comparison for reference in pattern.evidence_refs
                    ),
                )
            )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.lift,
            item.group_size,
            item.dimension,
            item.value,
        ),
    )


def _coverage_novelty(
    *,
    pattern_count: int,
    dominant_share: float,
    is_open: bool,
) -> float:
    """Estimate how credible a coverage-gap hypothesis is without overstating it."""

    sample_score = min(100.0, pattern_count / MINIMUM_INSIGHT_PATTERN_SAMPLE * 100)
    separation_score = dominant_share * 100 if is_open else 0.0
    return round(min(44.0, sample_score * 0.55 + separation_score * 0.45), 1)


def build_content_gap_map(
    *,
    topic_label: str,
    patterns: list[ContentPattern],
    profile_audience: str,
    preferred_formats: list[str],
    demand_question: str,
    evidence_refs: list[str],
    channel_fit: float,
    production_feasibility: float,
    timing: float,
    brand_risk: float,
    demand_supported: bool = False,
) -> dict[str, object]:
    dimensions = (
        "audience",
        "claim",
        "format",
        "context",
        "emotion",
        "product_anchor",
        "proof_type",
        "production_complexity",
    )
    occupied = {
        dimension: {
            "value": _dominant(patterns, dimension)[0],
            "share": _dominant(patterns, dimension)[1],
        }
        for dimension in dimensions
    }
    dominant_context = str(occupied["context"]["value"])
    dominant_claim = str(occupied["claim"]["value"])
    audience = _audience_label(
        profile_audience,
        str(occupied["audience"]["value"]),
    )
    preferred_format = (
        preferred_formats[0].lower() if preferred_formats else "evidence-led explainer"
    )
    evidence_strength = min(100.0, len(patterns) * 14.0)
    confirmed_demand = demand_supported and bool(demand_question.strip())
    demand_strength = 90.0 if confirmed_demand else 0.0
    performance_insight = _performance_insight(patterns)
    neutral_primary_title = (
        demand_question
        if confirmed_demand
        else (
            f"{topic_label}: {performance_insight.value}"
            if performance_insight is not None
            else topic_label
        )
    )

    specs = [
        {
            "key": "evidence-led-question",
            "title": neutral_primary_title,
            "promise": (
                "Resolve the specific evidence-backed question or observed subject "
                "difference without prescribing a video format or editorial stance."
            ),
            "format": preferred_format.title(),
            "effort": "Medium",
            "proof_type": "stored evidence",
            "context": dominant_context,
            "claim": (
                performance_insight.value if performance_insight is not None else dominant_claim
            ),
            "gap_strength": 96.0,
            "complexity": "medium",
            "title_directions": [
                neutral_primary_title,
                (
                    demand_question
                    if confirmed_demand
                    else f"What distinguishes {performance_insight.value} within {topic_label}?"
                    if performance_insight is not None
                    else f"{topic_label}: the unresolved evidence"
                ),
            ],
        },
        {
            "key": "failure-boundary",
            "title": f"{topic_label}: limits and failure boundaries for {audience}",
            "promise": (
                "Clarify the stored limits, trade-offs, and affected audience without "
                "assuming a tutorial, test, review, or other treatment."
            ),
            "format": preferred_format.title(),
            "effort": "Low–medium",
            "proof_type": "failure evidence",
            "context": dominant_context,
            "claim": "show where the dominant promise fails",
            "gap_strength": 92.0,
            "complexity": "low",
            "title_directions": [
                f"{topic_label}: documented limits and unresolved risks",
                f"{topic_label}: who is affected and under which conditions?",
            ],
        },
        {
            "key": "adoption-conditions",
            "title": f"{topic_label}: adoption conditions for {audience}",
            "promise": (
                "Identify the concrete conditions under which the observed change "
                "matters to this channel's audience."
            ),
            "format": preferred_format.title(),
            "effort": "High",
            "proof_type": "stored evidence",
            "context": dominant_context,
            "claim": "identify the conditions that change the audience decision",
            "gap_strength": 86.0,
            "complexity": "high",
            "title_directions": [
                f"{topic_label}: when the change becomes material",
                f"{topic_label}: affected users, constraints, and open questions",
            ],
        },
    ]

    occupied_cells = {
        (
            pattern.audience,
            pattern.claim,
            pattern.format,
            pattern.context,
            pattern.proof_type,
        )
        for pattern in patterns
    }
    opportunities: list[dict[str, object]] = []
    for spec_index, spec in enumerate(specs):
        candidate_cell = (
            audience,
            str(spec["claim"]),
            str(spec["format"]),
            str(spec["context"]),
            str(spec["proof_type"]),
        )
        is_open = candidate_cell not in occupied_cells
        performance_candidate = performance_insight is not None and spec_index == 0
        demand_ready = confirmed_demand and spec_index == 0
        # Heuristic subject labels are useful analyst input, but production
        # review showed that even claim/context labels can collapse into vague
        # phrases such as "creator production". Only confirmed demand or a
        # separately audited Evidence Analyst result may cross the release gate.
        release_ready = demand_ready
        insight_type = (
            "audience_demand"
            if demand_ready
            else "performance_pattern_candidate"
            if performance_candidate
            else "coverage_gap_candidate"
        )
        novelty = _coverage_novelty(
            pattern_count=len(patterns),
            dominant_share=float(str(occupied["format"]["share"])),
            is_open=is_open,
        )
        insight_statement = (
            demand_question
            if demand_ready
            else (
                "A channel-relative performance split was detected, but its "
                "subject label has not passed semantic evidence audit."
            )
            if performance_candidate
            else (
                "The stored evidence does not yet establish a non-obvious insight "
                "for this coverage-gap hypothesis."
            )
        )
        insight_reason_codes = (
            ["confirmed_cross_video_audience_demand"]
            if demand_ready
            else [
                "performance_split_requires_semantic_audit",
                "minimum_pattern_sample_met",
            ]
            if performance_candidate
            else [
                "coverage_gap_only",
                "no_confirmed_demand_or_audited_insight",
            ]
        )
        insight_evidence = (
            [
                reference
                for reference in evidence_refs
                if reference.startswith(("comment:", "demand:"))
            ]
            if demand_ready
            else [
                *performance_insight.winning_evidence_refs,
                *performance_insight.comparison_evidence_refs,
            ]
            if performance_candidate and performance_insight is not None
            else list(dict.fromkeys(evidence_refs))
        )
        components = {
            "unmet_demand_strength": demand_strength,
            "content_gap_strength": (float(str(spec["gap_strength"])) if is_open else 45.0),
            "channel_fit": _bounded(channel_fit),
            "production_feasibility": _bounded(production_feasibility),
            "timing": _bounded(timing),
            "evidence_strength": evidence_strength,
            "novelty": (70.0 if demand_ready else novelty),
            "brand_risk": _bounded(brand_risk),
        }
        opportunities.append(
            {
                "gap_key": spec["key"],
                "title": spec["title"],
                "audience_promise": spec["promise"],
                "why_now": (
                    insight_statement
                    if release_ready
                    else (
                        "This is a coverage-gap hypothesis, not a released insight. "
                        "More demand or performance evidence is required."
                    )
                ),
                "evidence": list(dict.fromkeys(evidence_refs)),
                "unanswered_question": (
                    demand_question
                    if confirmed_demand
                    else (
                        f"What distinguishes the {performance_insight.value} cases "
                        f"within {topic_label} from the rest of the stored sample?"
                    )
                    if performance_candidate and performance_insight is not None
                    else "No evidence-backed audience question is available yet."
                ),
                "format": spec["format"],
                "effort": spec["effort"],
                "timing_risk": (
                    "The differentiated proof must stay small enough to publish "
                    "inside the current opportunity window."
                ),
                "title_directions": spec["title_directions"],
                "avoid": (
                    "Do not repeat the dominant occupied pattern or claim results "
                    "that are absent from stored evidence."
                ),
                "occupied_pattern": occupied,
                "open_gap": {
                    "audience": audience,
                    "claim": spec["claim"],
                    "format": spec["format"],
                    "context": spec["context"],
                    "proof_type": spec["proof_type"],
                    "production_complexity": spec["complexity"],
                    "is_open": is_open,
                },
                "differentiation": (
                    f"The candidate focuses on {spec['claim']} in {spec['context']}; "
                    "the creator remains free to choose the video format."
                ),
                "release_ready": release_ready,
                "insight_status": ("evidence_backed" if release_ready else "candidate"),
                "insight_type": insight_type,
                "insight_statement": insight_statement,
                "insight_reason_codes": insight_reason_codes,
                "insight_evidence": list(dict.fromkeys(insight_evidence)),
                "insight_metrics": {
                    "pattern_sample_size": len(patterns),
                    "demand_supported": confirmed_demand,
                    "performance_pattern": (
                        asdict(performance_insight) if performance_insight is not None else {}
                    ),
                },
                "ranking_score": _candidate_score(components),
                "score_components": components,
                "content_gap_version": CONTENT_GAP_VERSION,
                "opportunity_ranking_version": OPPORTUNITY_RANKING_VERSION,
            }
        )
    opportunities.sort(
        key=lambda opportunity: (
            not bool(opportunity["release_ready"]),
            -float(str(opportunity["ranking_score"])),
            str(opportunity["gap_key"]),
        )
    )
    for rank, opportunity in enumerate(opportunities[:3], start=1):
        opportunity["rank"] = rank
        if rank == 1:
            runner_up = float(str(opportunities[1]["ranking_score"]))
            opportunity["why_primary"] = (
                f"Ranks "
                f"{float(str(opportunity['ranking_score'])) - runner_up:.1f} points "
                "above the next option because it combines the strongest open gap, "
                "channel fit, and publishability."
            )
        else:
            opportunity["why_ranked_below_primary"] = (
                "Useful alternative, but its combined gap, production, or timing "
                "score is lower than the primary opportunity."
            )
    return {
        "pattern_version": CONTENT_PATTERN_VERSION,
        "gap_version": CONTENT_GAP_VERSION,
        "ranking_version": OPPORTUNITY_RANKING_VERSION,
        "patterns": [pattern.as_dict() for pattern in patterns],
        "occupied_pattern": occupied,
        "opportunities": opportunities[:3],
    }
