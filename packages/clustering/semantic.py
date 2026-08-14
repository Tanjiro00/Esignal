from __future__ import annotations

import math
import re
from hashlib import blake2b, sha256

EMBEDDING_DIMENSIONS = 64
EMBEDDING_MODEL = "local-hashing-title-entity-transcript-v2"
EMBEDDING_VERSION = "video-embedding-v2-transcript"

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}")
STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "best",
    "for",
    "from",
    "full",
    "guide",
    "how",
    "into",
    "its",
    "just",
    "more",
    "new",
    "now",
    "that",
    "the",
    "this",
    "tutorial",
    "using",
    "what",
    "with",
    "you",
    "your",
}

PRODUCT_ENTITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NVIDIA", ("nvidia",)),
    ("OpenAI", ("openai",)),
    ("Claude Code", ("claude code",)),
    ("Claude", ("claude",)),
    ("ChatGPT", ("chatgpt",)),
    ("Grok", ("grok",)),
    ("Gemini", ("gemini",)),
    ("Kimi", ("kimi",)),
    ("DeepSeek", ("deepseek",)),
    ("Qwen", ("qwen",)),
    ("Cursor", ("cursor",)),
    ("Windsurf", ("windsurf",)),
    ("Lovable", ("lovable",)),
    ("OpenClaw", ("openclaw",)),
    ("Hermes", ("hermes",)),
    ("Higgsfield", ("higgsfield",)),
    ("Sora", ("sora",)),
    ("Veo", ("veo",)),
    ("Runway", ("runway",)),
    ("Kling", ("kling",)),
    ("Luma", ("luma",)),
    ("Pika", ("pika",)),
    ("Wan", ("wan 2", "wan2")),
    ("ComfyUI", ("comfyui",)),
    ("Ollama", ("ollama",)),
)

PRODUCT_ENTITIES = frozenset(canonical for canonical, _ in PRODUCT_ENTITY_PATTERNS)

DOMAIN_ENTITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Coding agents", ("coding agent", "multi agent coding", "ai assisted development")),
    ("AI agents", ("ai agent", "ai agents", "agentic")),
    (
        "AI video generation",
        (
            "ai video",
            "video generation",
            "video generator",
            "text-to-video",
            "image-to-video",
        ),
    ),
    ("AI models", ("ai model", "ai models", "model release", "new models")),
    ("AI productivity", ("ai productivity", "productivity tool")),
    ("AI robotics", ("ai robot", "robotics", "humanoid")),
    ("Chinese AI models", ("chinese ai", "china ai", "china's new ai")),
    ("Open-source AI", ("open source ai", "open-source ai")),
    ("Developer tools", ("coding", "developer", "typescript", "python", "react")),
    ("Productivity", ("productivity", "workflow", "work less")),
)

ENTITY_PATTERNS = (*PRODUCT_ENTITY_PATTERNS, *DOMAIN_ENTITY_PATTERNS)


def _normalized_text(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.lower()))


def normalize_entities(title: str, description: str) -> list[str]:
    title_text = _normalized_text(title)
    context_text = _normalized_text(description[:800])
    products = [
        canonical
        for canonical, patterns in PRODUCT_ENTITY_PATTERNS
        if any(_normalized_text(pattern) in title_text for pattern in patterns)
    ]
    domains = [
        canonical
        for canonical, patterns in DOMAIN_ENTITY_PATTERNS
        if any(
            _normalized_text(pattern) in title_text or _normalized_text(pattern) in context_text
            for pattern in patterns
        )
    ]
    return [*products, *domains]


def source_hash(title: str, description: str, entities: list[str]) -> str:
    value = "\n".join((title.strip(), description.strip(), *entities))
    return sha256(value.encode()).hexdigest()


def _features(title: str, description: str, entities: list[str]) -> list[tuple[str, float]]:
    title_tokens = [
        token for token in TOKEN_PATTERN.findall(title.lower()) if token not in STOP_WORDS
    ]
    description_tokens = [
        token
        for token in TOKEN_PATTERN.findall(description.lower())[:180]
        if token not in STOP_WORDS
    ]
    features: list[tuple[str, float]] = [
        *((token, 3.0) for token in title_tokens),
        *((token, 1.0) for token in description_tokens),
        *((f"entity:{entity.lower()}", 5.0) for entity in entities),
    ]
    features.extend(
        (f"{left}_{right}", 2.5)
        for left, right in zip(title_tokens, title_tokens[1:], strict=False)
    )
    return features


def embed_video_text(
    title: str,
    description: str,
    entities: list[str],
) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature, weight in _features(title, description, entities):
        digest = blake2b(feature.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or len(first) != len(second):
        return 0
    return sum(left * right for left, right in zip(first, second, strict=True))


def mean_embedding(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return [0.0] * EMBEDDING_DIMENSIONS
    result = [
        sum(vector[index] for vector in vectors) / len(vectors)
        for index in range(EMBEDDING_DIMENSIONS)
    ]
    norm = math.sqrt(sum(value * value for value in result))
    if norm == 0:
        return result
    return [round(value / norm, 8) for value in result]
