from __future__ import annotations

from dataclasses import dataclass

from packages.channel_fit.scoring import tokens

_GENERIC_TOKENS = {
    "2025",
    "2026",
    "about",
    "best",
    "build",
    "building",
    "guide",
    "latest",
    "new",
    "practical",
    "real",
    "the",
    "using",
}


def relevance_tokens(values: list[str] | tuple[str, ...] | str) -> set[str]:
    normalized: set[str] = set()
    for token in tokens(values):
        if token in _GENERIC_TOKENS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = f"{token[:-3]}y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            token = token[:-1]
        normalized.add(token)
    return normalized


def relevance_overlap(
    candidate_values: list[str] | tuple[str, ...] | str,
    reference_values: list[str] | tuple[str, ...] | str,
) -> float:
    candidate = relevance_tokens(candidate_values)
    reference = relevance_tokens(reference_values)
    if not candidate or not reference:
        return 0.0
    denominator = max(1, min(len(candidate), len(reference), 10))
    return round(min(100.0, len(candidate & reference) / denominator * 100), 1)


@dataclass(frozen=True)
class DiscoveryOccurrenceEvidence:
    video_id: str
    query_id: str
    query: str


def assess_workspace_relevance(
    *,
    topic_values: list[str],
    core_topic_values: list[str],
    evidence_video_ids: list[str],
    plan_query_count: int,
    occurrences: list[DiscoveryOccurrenceEvidence],
) -> dict[str, object]:
    has_personal_plan = plan_query_count > 0
    core_overlap = relevance_overlap(topic_values, core_topic_values)
    matching_occurrences = [
        item for item in occurrences if relevance_overlap(topic_values, item.query) >= 20
    ]
    matching_video_ids = sorted({item.video_id for item in matching_occurrences})
    matching_query_ids = sorted({item.query_id for item in matching_occurrences})
    evidence_count = len(set(evidence_video_ids))
    coverage = len(matching_video_ids) / max(1, evidence_count)
    personal_evidence_confirmed = len(matching_video_ids) >= 2 and coverage >= 0.25

    if not has_personal_plan:
        eligible = True
        reason_codes = ["no_personal_discovery_plan"]
    else:
        reason_codes = []
        if core_overlap < 20 and not personal_evidence_confirmed:
            reason_codes.append("core_topic_mismatch")
        if len(matching_video_ids) < 2:
            reason_codes.append("insufficient_personal_query_videos")
        if coverage < 0.25:
            reason_codes.append("low_personal_query_coverage")
        eligible = not reason_codes
        if eligible:
            reason_codes.append(
                "core_and_personal_evidence_confirmed"
                if core_overlap >= 20
                else "personal_query_evidence_confirmed"
            )

    return {
        "eligible": eligible,
        "version": "workspace-relevance-v2",
        "has_personal_discovery_plan": has_personal_plan,
        "plan_query_count": plan_query_count,
        "core_topic_overlap": core_overlap,
        "matching_video_count": len(matching_video_ids),
        "matching_query_count": len(matching_query_ids),
        "evidence_video_count": evidence_count,
        "personal_evidence_coverage": round(coverage, 3),
        "matching_video_refs": [f"video:{video_id}" for video_id in matching_video_ids],
        "matching_query_refs": [f"query:{query_id}" for query_id in matching_query_ids],
        "reason_codes": reason_codes,
    }
