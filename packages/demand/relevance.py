from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import blake2b, sha256

from packages.clustering.semantic import PRODUCT_ENTITIES, normalize_entities

RELEVANCE_MODEL_VERSION = "comment-topic-relevance-v1"
RELEVANCE_EMBEDDING_VERSION = "comment-topic-hashing-v1"
RELEVANCE_THRESHOLD = 0.70
EMBEDDING_DIMENSIONS = 96

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}")
STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "just",
    "like",
    "more",
    "that",
    "the",
    "this",
    "video",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "you",
    "your",
}
CONCEPT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cost", ("free", "price", "pricing", "cost", "subscription", "credits", "paywall")),
    ("local", ("local", "on your pc", "self hosted", "self-hosted", "offline")),
    ("unlimited", ("unlimited", "no limit", "without limits", "no paywall")),
    ("setup", ("setup", "install", "installation", "configure", "configuration", "running")),
    ("tutorial", ("tutorial", "step by step", "walkthrough", "guide", "show how")),
    ("comparison", ("compare", "comparison", "versus", " vs ", "difference")),
    ("proof", ("test", "benchmark", "proof", "failure case", "real world")),
    ("beginner", ("beginner", "no code", "no-code", "without coding")),
    ("privacy", ("privacy", "private data", "security", "safe", "permission")),
    ("workflow", ("workflow", "use case", "production", "for work", "real project")),
    ("release", ("release", "new version", "update", "latest version")),
    ("agent", ("agent", "agents", "agentic")),
    (
        "video_generation",
        ("ai video", "video generation", "video generator", "text-to-video", "image-to-video"),
    ),
)
HIGH_ACTIONABILITY = {
    "request_for_tutorial",
    "comparison_request",
    "test_or_proof_request",
    "missing_use_case",
    "pricing_request",
    "privacy_safety_concern",
}
MEDIUM_ACTIONABILITY = {
    "request_for_explanation",
    "skepticism",
    "objection",
    "correction",
    "regional_request",
    "request_for_update",
    "explicit_question",
}


@dataclass(frozen=True)
class CommentTopicRelevanceInput:
    comment_text: str
    intent: str
    demand_probability: float
    spam_probability: float
    topic_label: str
    topic_entities: tuple[str, ...]
    video_title: str
    video_description: str
    video_entities: tuple[str, ...]
    duplicate_count: int = 1


@dataclass(frozen=True)
class CommentTopicRelevanceResult:
    is_relevant: bool
    relevance_score: float
    intent: str
    actionability: str
    comment_topic_semantic_similarity: float
    comment_video_semantic_similarity: float
    entity_overlap_score: float
    claim_support_score: float
    intent_actionability_score: float
    duplicate_or_echo_probability: float
    spam_probability: float
    supported_entities: tuple[str, ...]
    supported_claims: tuple[str, ...]
    reason_codes: tuple[str, ...]
    model_version: str = RELEVANCE_MODEL_VERSION


def _normalized(value: str) -> str:
    return " ".join(value.lower().replace("’", "'").split())


def normalized_comment_fingerprint(value: str) -> str:
    normalized = " ".join(TOKEN_PATTERN.findall(_normalized(value)))
    return sha256(normalized.encode()).hexdigest()


def _stem(token: str) -> str:
    for suffix in ("ing", "tion", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _concepts(value: str) -> set[str]:
    normalized = f" {_normalized(value)} "
    concepts = {
        concept
        for concept, aliases in CONCEPT_ALIASES
        if any(alias in normalized for alias in aliases)
    }
    concepts.update(
        _stem(token) for token in TOKEN_PATTERN.findall(normalized) if token not in STOP_WORDS
    )
    return concepts


def _embedding(value: str) -> list[float]:
    concepts = sorted(_concepts(value))
    features: list[tuple[str, float]] = [(concept, 1.0) for concept in concepts]
    features.extend(
        (f"{left}_{right}", 1.35) for left, right in zip(concepts, concepts[1:], strict=False)
    )
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature, weight in features:
        digest = blake2b(feature.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine(first: list[float], second: list[float]) -> float:
    return max(
        0.0,
        min(
            1.0,
            sum(left * right for left, right in zip(first, second, strict=True)),
        ),
    )


def _semantic_similarity(first: str, second: str) -> float:
    first_concepts = _concepts(first)
    second_concepts = _concepts(second)
    if not first_concepts or not second_concepts:
        return 0.0
    lexical = len(first_concepts & second_concepts) / math.sqrt(
        len(first_concepts) * len(second_concepts)
    )
    hashed = _cosine(_embedding(first), _embedding(second))
    return round(min(1.0, lexical * 0.72 + hashed * 0.28), 4)


def _actionability(intent: str, demand_probability: float) -> tuple[str, float]:
    if intent in HIGH_ACTIONABILITY and demand_probability >= 0.7:
        return "high", 1.0
    if intent in MEDIUM_ACTIONABILITY and demand_probability >= 0.5:
        return "medium", 0.72
    return "low", round(min(0.35, demand_probability * 0.35), 4)


def _duplicate_probability(count: int) -> float:
    if count <= 1:
        return 0.0
    return round(min(0.85, 0.18 + (count - 2) * 0.17), 4)


def _entity_support(
    *,
    comment_text: str,
    topic_entities: tuple[str, ...],
    video_entities: tuple[str, ...],
) -> tuple[float, tuple[str, ...], str | None]:
    comment_entities = set(normalize_entities(comment_text, ""))
    topic = set(topic_entities)
    video = set(video_entities)
    product_anchors = topic & PRODUCT_ENTITIES
    comment_products = comment_entities & PRODUCT_ENTITIES
    video_products = video & PRODUCT_ENTITIES

    if product_anchors:
        if comment_products and not comment_products & product_anchors:
            return 0.0, (), "entity_conflict"
        direct = comment_entities & topic
        if direct:
            return 1.0, tuple(sorted(direct)), "entity_match"
        bridged = video_products & product_anchors
        if bridged:
            return 0.85, tuple(sorted(bridged)), "source_video_entity_bridge"
        return 0.0, (), "missing_product_anchor"

    direct = comment_entities & topic
    if direct:
        return 1.0, tuple(sorted(direct)), "entity_match"
    bridged = video & topic
    if bridged:
        return 0.82, tuple(sorted(bridged)), "source_video_entity_bridge"
    if topic and video:
        return 0.0, (), "entity_mismatch"
    return 0.55, (), "topic_has_no_entity_anchor"


def classify_comment_topic_relevance(
    value: CommentTopicRelevanceInput,
) -> CommentTopicRelevanceResult:
    topic_text = " ".join((value.topic_label, *value.topic_entities))
    video_text = " ".join((value.video_title, value.video_description[:800], *value.video_entities))
    topic_similarity = _semantic_similarity(value.comment_text, topic_text)
    video_similarity = _semantic_similarity(value.comment_text, video_text)
    entity_score, supported_entities, entity_reason = _entity_support(
        comment_text=value.comment_text,
        topic_entities=value.topic_entities,
        video_entities=value.video_entities,
    )
    actionability, actionability_score = _actionability(
        value.intent,
        value.demand_probability,
    )
    comment_concepts = _concepts(value.comment_text)
    topic_concepts = _concepts(topic_text)
    video_concepts = _concepts(video_text)
    direct_claims = comment_concepts & topic_concepts
    source_claims = comment_concepts & video_concepts & topic_concepts
    supported_claims = tuple(sorted(direct_claims | source_claims))[:10]
    if supported_claims:
        claim_score = min(1.0, 0.62 + len(supported_claims) * 0.12)
    elif video_concepts & topic_concepts and actionability_score >= 0.7:
        claim_score = 0.42
    else:
        claim_score = 0.0
    duplicate_probability = _duplicate_probability(value.duplicate_count)
    evidence_chain_bonus = (
        0.18
        if entity_score >= 0.8 and actionability_score >= 0.9 and claim_score >= 0.6
        else 0.08
        if entity_score >= 0.8 and actionability_score >= 0.7 and claim_score >= 0.6
        else 0.0
    )
    relevance_score = round(
        max(
            0.0,
            min(
                1.0,
                topic_similarity * 0.22
                + video_similarity * 0.18
                + entity_score * 0.20
                + claim_score * 0.20
                + actionability_score * 0.20
                + evidence_chain_bonus
                - duplicate_probability * 0.12
                - value.spam_probability * 0.18,
            ),
        ),
        4,
    )
    reason_codes: list[str] = []
    if entity_reason:
        reason_codes.append(entity_reason)
    if topic_similarity >= 0.25:
        reason_codes.append("topic_claim_match")
    if video_similarity >= 0.25:
        reason_codes.append("video_claim_match")
    if supported_claims:
        reason_codes.append("claim_support")
    if actionability == "high":
        reason_codes.append("high_actionability")
    elif actionability == "medium":
        reason_codes.append("actionable_intent")
    if duplicate_probability > 0:
        reason_codes.append("possible_echo")
    if value.spam_probability >= 0.5:
        reason_codes.append("spam_risk")

    product_anchors = set(value.topic_entities) & PRODUCT_ENTITIES
    has_anchor_coverage = not product_anchors or entity_score >= 0.8
    blocked_reason = entity_reason in {
        "entity_conflict",
        "missing_product_anchor",
        "entity_mismatch",
    }
    is_relevant = bool(
        relevance_score >= RELEVANCE_THRESHOLD
        and value.demand_probability >= 0.5
        and value.spam_probability < 0.5
        and actionability_score >= 0.7
        and has_anchor_coverage
        and not blocked_reason
    )
    reason_codes.append("accepted" if is_relevant else "below_relevance_gate")
    return CommentTopicRelevanceResult(
        is_relevant=is_relevant,
        relevance_score=relevance_score,
        intent=value.intent,
        actionability=actionability,
        comment_topic_semantic_similarity=topic_similarity,
        comment_video_semantic_similarity=video_similarity,
        entity_overlap_score=round(entity_score, 4),
        claim_support_score=round(claim_score, 4),
        intent_actionability_score=round(actionability_score, 4),
        duplicate_or_echo_probability=duplicate_probability,
        spam_probability=round(value.spam_probability, 4),
        supported_entities=supported_entities,
        supported_claims=supported_claims,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )
