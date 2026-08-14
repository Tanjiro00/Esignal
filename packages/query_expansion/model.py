from __future__ import annotations

import re
from dataclasses import dataclass

QUERY_EXPANSION_VERSION = "query-expansion-v1"
MAX_NEW_SUGGESTIONS_PER_RUN = 10
MAX_PENDING_SUGGESTIONS = 50
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+-]{1,}")
BROAD_TERMS = {
    "ai",
    "agents",
    "automation",
    "coding",
    "models",
    "release",
    "tech",
    "tools",
    "video",
}


@dataclass(frozen=True)
class QueryCandidate:
    query: str
    source_type: str
    source_entity: str
    source_topic_id: str | None
    source_evidence_ids: tuple[str, ...]
    rationale: str
    product_anchors: tuple[str, ...]
    problem_anchors: tuple[str, ...]
    workspace_id: str | None = None


@dataclass(frozen=True)
class QueryQuality:
    accepted: bool
    normalized_query: str
    broadness_score: float
    anchor_terms: tuple[str, ...]
    reason_codes: tuple[str, ...]


def normalize_query(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.lower()))[:300]


def evaluate_query_candidate(candidate: QueryCandidate) -> QueryQuality:
    normalized = normalize_query(candidate.query)
    tokens = normalized.split()
    unique = set(tokens)
    product_tokens = {
        token for value in candidate.product_anchors for token in normalize_query(value).split()
    }
    problem_tokens = {
        token for value in candidate.problem_anchors for token in normalize_query(value).split()
    }
    product_overlap = unique & product_tokens
    problem_overlap = unique & problem_tokens
    broad_terms = unique & BROAD_TERMS
    broadness = round(
        min(
            100.0,
            (100 if len(unique) < 2 else 55 if len(unique) < 3 else 20)
            + (len(broad_terms) / max(len(unique), 1) * 45),
        ),
        2,
    )
    reasons: list[str] = []
    if len(unique) < 3:
        reasons.append("too_broad")
    if not product_overlap:
        reasons.append("missing_product_anchor")
    if not problem_overlap:
        reasons.append("missing_problem_anchor")
    if len(normalized) < 6:
        reasons.append("too_short")
    return QueryQuality(
        accepted=not reasons and broadness < 70,
        normalized_query=normalized,
        broadness_score=broadness,
        anchor_terms=tuple(sorted(product_overlap | problem_overlap)),
        reason_codes=tuple(reasons or ("anchored_candidate",)),
    )


def query_precision(*, retained_results: int, total_results: int) -> float:
    if total_results <= 0:
        return 0.0
    return round(min(100.0, max(0.0, retained_results / total_results * 100)), 2)


def should_demote_query(*, precision: float, sample_size: int) -> bool:
    return sample_size >= 20 and precision < 15
