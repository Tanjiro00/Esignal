from __future__ import annotations

import math
import re
from dataclasses import dataclass
from hashlib import blake2b

CLASSIFIER_VERSION = "comment-demand-rules-v2"
COMMENT_EMBEDDING_VERSION = "comment-demand-hashing-v1"
EMBEDDING_DIMENSIONS = 64

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}")
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
QUESTION_START = re.compile(
    r"^(how|what|why|when|where|which|who|can|could|would|will|does|do|is|are|has|have)\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "about",
    "after",
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

TAXONOMY_LABELS = {
    "explicit_question": "Recurring audience questions",
    "request_for_explanation": "Requests for a clearer explanation",
    "request_for_tutorial": "Requests for a practical tutorial",
    "comparison_request": "Requests for a direct comparison",
    "test_or_proof_request": "Requests for independent tests or proof",
    "skepticism": "Recurring skepticism",
    "objection": "Recurring objections",
    "correction": "Corrections and factual challenges",
    "missing_use_case": "Missing real-world use cases",
    "regional_request": "Regional or audience-specific requests",
    "pricing_request": "Pricing and cost questions",
    "privacy_safety_concern": "Privacy and safety concerns",
    "request_for_update": "Requests for an updated follow-up",
    "emotional_reaction": "Emotional reactions",
    "generic_praise": "Generic praise",
    "generic_criticism": "Generic criticism",
    "spam_irrelevant": "Spam or irrelevant comments",
}


@dataclass(frozen=True)
class CommentAnalysis:
    taxonomy: str
    demand_probability: float
    spam_probability: float
    sentiment: str
    embedding: list[float]


def _contains(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_request_intent(text: str) -> bool:
    return bool(
        "?" in text
        or QUESTION_START.search(text)
        or _contains(
            text,
            (
                "please",
                "can you",
                "could you",
                "would you",
                "show us",
                "i want to know",
                "i'd like to know",
                "we need",
            ),
        )
    )


def _taxonomy(text: str) -> str:
    if _contains(
        text,
        (
            "here's quick summary",
            "here is a quick summary",
            "if you want keypoints",
            "if you want key points",
            "just like the comment",
            "check my channel",
            "visit my channel",
            "dm me",
            "contact me",
        ),
    ):
        return "spam_irrelevant"
    if URL_PATTERN.search(text) and _contains(
        text,
        ("subscribe", "my channel", "telegram", "whatsapp", "crypto", "giveaway"),
    ):
        return "spam_irrelevant"
    if _has_request_intent(text) and _contains(
        text,
        ("privacy", "private data", "personal data", "safe to", "security", "permission"),
    ):
        return "privacy_safety_concern"
    if _has_request_intent(text) and _contains(
        text,
        ("price", "pricing", "cost", "subscription", "free tier", "how much", "credits"),
    ):
        return "pricing_request"
    if _has_request_intent(text) and _contains(
        text,
        ("compare", "comparison", "versus", " vs ", "better than", "difference between"),
    ):
        return "comparison_request"
    if _has_request_intent(text) and _contains(
        text,
        (
            "tutorial",
            "step by step",
            "walkthrough",
            "show us how",
            "show how",
            "setup guide",
            "please make a guide",
        ),
    ):
        return "request_for_tutorial"
    if _has_request_intent(text) and _contains(
        text,
        (
            "test this",
            "real test",
            "benchmark",
            "prove",
            "proof",
            "failure case",
        ),
    ):
        return "test_or_proof_request"
    if _has_request_intent(text) and _contains(
        text,
        ("explain", "what does", "why does", "i don't understand", "clarify", "break down"),
    ):
        return "request_for_explanation"
    if _contains(
        text,
        ("actually,", "correction", "incorrect", "not true", "wrong about", "misleading"),
    ):
        return "correction"
    if _contains(
        text,
        ("i doubt", "skeptical", "hype", "too good to be true", "not convinced"),
    ):
        return "skepticism"
    if _contains(
        text,
        ("but this", "the problem is", "doesn't work", "does not work", "deal breaker"),
    ):
        return "objection"
    if _has_request_intent(text) and _contains(
        text,
        ("use case", "real use", "for teams", "for work", "in production", "practical example"),
    ):
        return "missing_use_case"
    if _has_request_intent(text) and _contains(
        text,
        ("in europe", "in india", "in my country", "non-english", "for beginners", "for students"),
    ):
        return "regional_request"
    if _contains(
        text,
        ("update this", "follow up", "new version", "latest version", "part 2", "revisit"),
    ):
        return "request_for_update"
    if _contains(
        text,
        ("who edits", "your editor", "editing style", "what camera", "background music"),
    ):
        return "emotional_reaction"
    if "?" in text or QUESTION_START.search(text):
        return "explicit_question"
    if _contains(
        text,
        ("great video", "awesome", "amazing", "love this", "thank you", "thanks for"),
    ):
        return "generic_praise"
    if _contains(text, ("terrible", "awful", "waste of time", "bad video", "useless")):
        return "generic_criticism"
    if len(TOKEN_PATTERN.findall(text)) < 3:
        return "spam_irrelevant"
    return "emotional_reaction"


def _spam_probability(text: str, taxonomy: str) -> float:
    score = 0.02
    score += min(0.55, len(URL_PATTERN.findall(text)) * 0.28)
    if _contains(text, ("subscribe", "telegram", "whatsapp", "giveaway", "promo code")):
        score += 0.4
    if re.search(r"(.)\1{7,}", text):
        score += 0.25
    if taxonomy == "spam_irrelevant":
        score = max(score, 0.82)
    return round(min(1.0, score), 4)


def _demand_probability(text: str, taxonomy: str, spam: float) -> float:
    base = {
        "explicit_question": 0.78,
        "request_for_explanation": 0.86,
        "request_for_tutorial": 0.92,
        "comparison_request": 0.9,
        "test_or_proof_request": 0.91,
        "skepticism": 0.72,
        "objection": 0.7,
        "correction": 0.58,
        "missing_use_case": 0.82,
        "regional_request": 0.8,
        "pricing_request": 0.88,
        "privacy_safety_concern": 0.88,
        "request_for_update": 0.76,
        "emotional_reaction": 0.12,
        "generic_praise": 0.05,
        "generic_criticism": 0.18,
        "spam_irrelevant": 0.0,
    }[taxonomy]
    if "?" in text:
        base += 0.05
    return round(max(0.0, min(1.0, base * (1 - spam))), 4)


def _sentiment(text: str, taxonomy: str) -> str:
    if taxonomy in {
        "skepticism",
        "objection",
        "correction",
        "generic_criticism",
        "privacy_safety_concern",
    }:
        return "negative"
    if taxonomy == "generic_praise":
        return "positive"
    if _contains(text, ("love", "great", "awesome", "amazing", "thanks")):
        return "positive"
    return "neutral"


def _stem(token: str) -> str:
    for suffix in ("ing", "tion", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _embedding(text: str, taxonomy: str) -> list[float]:
    tokens = [_stem(token) for token in TOKEN_PATTERN.findall(text) if token not in STOP_WORDS]
    features = [(token, 1.0) for token in tokens]
    features.extend(
        (f"{left}_{right}", 1.4) for left, right in zip(tokens, tokens[1:], strict=False)
    )
    features.append((f"taxonomy:{taxonomy}", 3.0))
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature, weight in features:
        digest = blake2b(feature.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def taxonomy_label(taxonomy: str) -> str:
    return TAXONOMY_LABELS.get(taxonomy, taxonomy.replace("_", " ").title())


def classify_comment(text: str) -> CommentAnalysis:
    normalized = " ".join(text.lower().split())
    taxonomy = _taxonomy(normalized)
    spam = _spam_probability(normalized, taxonomy)
    return CommentAnalysis(
        taxonomy=taxonomy,
        demand_probability=_demand_probability(normalized, taxonomy, spam),
        spam_probability=spam,
        sentiment=_sentiment(normalized, taxonomy),
        embedding=_embedding(normalized, taxonomy),
    )
