from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

YOUNIVERSE_DATASET_VERSION = "youniverse-v1.1-en"
YOUNIVERSE_REPLAY_VERSION = "youniverse-structural-replay-v1.1-filtered-schema"
YOUNIVERSE_OUTCOME_VERSION = "future-topic-supply-channel-outlier-42d-v1"


@dataclass(frozen=True)
class _Anchor:
    name: str
    pattern: re.Pattern[str]


_ANCHORS: tuple[_Anchor, ...] = (
    _Anchor("microsoft_365_copilot", re.compile(r"\bmicrosoft (?:365 )?copilot\b", re.I)),
    _Anchor("stable_diffusion", re.compile(r"\bstable diffusion\b", re.I)),
    _Anchor("google_duplex", re.compile(r"\bgoogle duplex\b", re.I)),
    _Anchor("reinforcement_learning", re.compile(r"\breinforcement learning\b", re.I)),
    _Anchor(
        "generative_adversarial_network",
        re.compile(r"\bgenerative adversarial networks?\b", re.I),
    ),
    _Anchor("natural_language_processing", re.compile(r"\bnatural language processing\b", re.I)),
    _Anchor("computer_vision", re.compile(r"\bcomputer vision\b", re.I)),
    _Anchor("neural_network", re.compile(r"\bneural networks?\b", re.I)),
    _Anchor("machine_learning", re.compile(r"\bmachine learning\b", re.I)),
    _Anchor("deep_learning", re.compile(r"\bdeep learning\b", re.I)),
    _Anchor("artificial_intelligence", re.compile(r"\bartificial intelligence\b", re.I)),
    _Anchor("tensorflow", re.compile(r"\btensorflow(?:\.?js)?\b", re.I)),
    _Anchor("pytorch", re.compile(r"\bpytorch\b", re.I)),
    _Anchor("keras", re.compile(r"\bkeras\b", re.I)),
    _Anchor("openai_gym", re.compile(r"\bopenai gym\b", re.I)),
    _Anchor("openai", re.compile(r"\bopenai\b", re.I)),
    _Anchor("deepmind", re.compile(r"\bdeepmind\b", re.I)),
    _Anchor("alphago", re.compile(r"\balphago\b", re.I)),
    _Anchor("ibm_watson", re.compile(r"\bibm watson\b", re.I)),
    _Anchor("gpt", re.compile(r"\bgpt[- ]?[234](?:\.5)?\b", re.I)),
    _Anchor("chatgpt", re.compile(r"\bchatgpt\b", re.I)),
    _Anchor("gemini", re.compile(r"\bgemini\b", re.I)),
    _Anchor("claude", re.compile(r"\bclaude(?: code)?\b", re.I)),
    _Anchor("deepseek", re.compile(r"\bdeepseek\b", re.I)),
    _Anchor("midjourney", re.compile(r"\bmidjourney\b", re.I)),
    _Anchor("bert", re.compile(r"\bBERT\b")),
    _Anchor("gan", re.compile(r"\bGANs?\b")),
    _Anchor("nlp", re.compile(r"\bNLP\b")),
    _Anchor("uppercase_ai", re.compile(r"(?<![A-Z0-9])A\.?I\.?(?![A-Z0-9])")),
)

_FAST_AI_HINT = re.compile(
    r"artificial intelligence|machine learning|deep learning|neural network|"
    r"natural language processing|computer vision|reinforcement learning|"
    r"generative adversarial|tensorflow|pytorch|keras|openai|deepmind|alphago|"
    r"ibm watson|google duplex|gpt[- ]?[234]|chatgpt|gemini|claude|deepseek|"
    r"midjourney|stable diffusion",
    re.IGNORECASE,
)
_FAST_UPPERCASE_HINT = re.compile(r"\b(?:BERT|GANs?|NLP|A\.?I\.?)\b")


def detect_historical_ai_anchor(title: str) -> str | None:
    """Return the first title-only, token-aware AI anchor."""

    normalized = " ".join(title.split())
    if not _FAST_AI_HINT.search(normalized) and not _FAST_UPPERCASE_HINT.search(normalized):
        return None
    for anchor in _ANCHORS:
        if anchor.pattern.search(normalized):
            return anchor.name
    return None


def is_historical_ai_title(title: str) -> bool:
    return detect_historical_ai_anchor(title) is not None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("missing datetime")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _integer(value: Any) -> int:
    if value in (None, "", "NA", "NaN", "nan"):
        return 0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(parsed):
        return 0
    return max(0, int(parsed))


def _tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if item)
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if item)
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _raw_or_filtered(payload: dict[str, Any], raw_key: str, filtered_key: str) -> Any:
    """Read a raw YouNiverse field or its provenance-preserving filtered name."""

    if raw_key in payload:
        return payload[raw_key]
    return payload.get(filtered_key)


@dataclass(frozen=True)
class YouniverseRawVideo:
    video_id: str
    channel_id: str
    title: str
    description: str
    tags: tuple[str, ...]
    category: str
    upload_date: datetime
    crawl_date: datetime
    final_view_count: int
    final_like_count: int
    final_dislike_count: int

    @property
    def anchor(self) -> str | None:
        return detect_historical_ai_anchor(self.title)

    def json_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["upload_date"] = self.upload_date.isoformat()
        payload["crawl_date"] = self.crawl_date.isoformat()
        payload["tags"] = list(self.tags)
        return payload


@dataclass(frozen=True)
class StructuralVideo:
    """Candidate-side fields. Final engagement is intentionally absent."""

    video_id: str
    channel_id: str
    title: str
    description: str
    tags: tuple[str, ...]
    category: str
    upload_date: datetime


@dataclass(frozen=True)
class OutcomeVideo:
    """Outcome-only fields, never passed into candidate ranking."""

    video_id: str
    channel_id: str
    upload_date: datetime
    crawl_date: datetime
    final_view_count: int

    @property
    def exposure_age_days(self) -> int:
        return max(0, (self.crawl_date.date() - self.upload_date.date()).days)


def parse_youniverse_payload(payload: dict[str, Any]) -> YouniverseRawVideo:
    return YouniverseRawVideo(
        video_id=str(payload.get("display_id") or payload.get("video_id") or "").strip(),
        channel_id=str(payload.get("channel_id") or "").strip(),
        title=str(payload.get("title") or "").strip(),
        description=str(payload.get("description") or "").strip(),
        tags=_tags(payload.get("tags")),
        category=str(payload.get("categories") or payload.get("category") or "").strip(),
        upload_date=_datetime(payload.get("upload_date")),
        crawl_date=_datetime(payload.get("crawl_date")),
        final_view_count=_integer(_raw_or_filtered(payload, "view_count", "final_view_count")),
        final_like_count=_integer(_raw_or_filtered(payload, "like_count", "final_like_count")),
        final_dislike_count=_integer(
            _raw_or_filtered(payload, "dislike_count", "final_dislike_count")
        ),
    )


def parse_youniverse_record(line: str) -> YouniverseRawVideo:
    return parse_youniverse_payload(json.loads(line))


def split_candidate_and_outcome(
    video: YouniverseRawVideo,
) -> tuple[StructuralVideo, OutcomeVideo]:
    return (
        StructuralVideo(
            video_id=video.video_id,
            channel_id=video.channel_id,
            title=video.title,
            description=video.description,
            tags=video.tags,
            category=video.category,
            upload_date=video.upload_date,
        ),
        OutcomeVideo(
            video_id=video.video_id,
            channel_id=video.channel_id,
            upload_date=video.upload_date,
            crawl_date=video.crawl_date,
            final_view_count=video.final_view_count,
        ),
    )


__all__ = [
    "OutcomeVideo",
    "StructuralVideo",
    "YOUNIVERSE_DATASET_VERSION",
    "YOUNIVERSE_OUTCOME_VERSION",
    "YOUNIVERSE_REPLAY_VERSION",
    "YouniverseRawVideo",
    "detect_historical_ai_anchor",
    "is_historical_ai_title",
    "parse_youniverse_record",
    "parse_youniverse_payload",
    "split_candidate_and_outcome",
]
