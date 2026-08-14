from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median

CHANNEL_PROFILE_VERSION = "channel-profile-v4-quality"

URL_PATTERN = re.compile(
    r"(?:https?://|www\.)\S+|(?:[a-z0-9-]+\.)+[a-z]{2,24}\b\S*",
    re.IGNORECASE,
)
HANDLE_PATTERN = re.compile(r"(?<!\w)@[a-z0-9_.-]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9+#-]{2,}")
SPONSOR_PATTERN = re.compile(
    r"(?:sponsored by|thanks to .{0,60} for sponsoring|use code|affiliate link|"
    r"business inquiries|follow me on|join my newsletter).*$",
    re.IGNORECASE,
)
STOPWORDS = {
    "all",
    "and",
    "are",
    "about",
    "after",
    "again",
    "also",
    "any",
    "another",
    "because",
    "before",
    "best",
    "build",
    "but",
    "can",
    "channel",
    "check",
    "cdn",
    "complete",
    "cookies",
    "could",
    "did",
    "does",
    "doing",
    "description",
    "each",
    "even",
    "every",
    "everything",
    "erid",
    "first",
    "for",
    "from",
    "get",
    "got",
    "had",
    "has",
    "have",
    "how",
    "here",
    "its",
    "into",
    "just",
    "latest",
    "like",
    "links",
    "make",
    "many",
    "may",
    "might",
    "more",
    "most",
    "new",
    "news",
    "not",
    "now",
    "one",
    "only",
    "official",
    "our",
    "out",
    "over",
    "really",
    "review",
    "same",
    "should",
    "shorts",
    "show",
    "some",
    "sponsor",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "through",
    "today",
    "tools",
    "under",
    "use",
    "used",
    "using",
    "video",
    "was",
    "watch",
    "way",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    "youtube",
    "youtu",
    "unionconf",
    "castello",
    "composite",
    "itzy",
}


@dataclass(frozen=True)
class ChannelVideoSample:
    id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int
    is_short: bool
    is_live: bool
    outlier_ratio: float | None = None


@dataclass(frozen=True)
class ChannelProfileInference:
    core_topics: tuple[str, ...]
    adjacent_topics: tuple[str, ...]
    legacy_topics: tuple[str, ...]
    preferred_formats: tuple[str, ...]
    successful_formats: tuple[str, ...]
    typical_duration_min_seconds: int
    typical_duration_max_seconds: int
    upload_cadence: dict[str, float | int | str]
    audience_sophistication: str
    creator_authority: str
    title_style: dict[str, object]
    cleaned_channel_description: str
    version: str = CHANNEL_PROFILE_VERSION


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def sanitize_channel_text(value: str) -> str:
    lines: list[str] = []
    for raw_line in value.splitlines() or [value]:
        line = SPONSOR_PATTERN.sub("", raw_line)
        line = URL_PATTERN.sub(" ", line)
        line = HANDLE_PATTERN.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip(" -–—|")
        if line:
            lines.append(line)
    return " ".join(lines)


def _tokens(value: str) -> list[str]:
    return [
        token
        for token in TOKEN_PATTERN.findall(sanitize_channel_text(value).lower())
        if token not in STOPWORDS
        and not token.isdigit()
        and not (any(character.isdigit() for character in token) and len(token) >= 6)
        and not (
            len(token) >= 8 and not any(vowel in token for vowel in ("a", "e", "i", "o", "u", "y"))
        )
    ]


def _format(sample: ChannelVideoSample) -> str:
    title = sample.title.lower()
    if sample.is_live:
        return "Live"
    if sample.is_short or sample.duration_seconds <= 90:
        return "Shorts"
    if any(value in title for value in (" vs ", "compare", "comparison", "best ")):
        return "Structured comparison"
    if any(value in title for value in ("how to", "tutorial", "guide", "course", "build ")):
        return "Tutorial"
    if any(value in title for value in ("tested", "benchmark", "stress test", "experiment")):
        return "Hands-on test"
    return "Evidence-led explainer"


def _topic_counts(
    samples: list[ChannelVideoSample],
    *,
    captured_at: datetime,
    current: bool,
) -> dict[str, float]:
    counts: dict[str, float] = {}
    for sample in samples:
        age = _aware(captured_at) - _aware(sample.published_at)
        is_current = age <= timedelta(days=180)
        if is_current != current:
            continue
        weight = max(0.08, 0.5 ** (max(0, age.days) / (45 if current else 365)))
        title_tokens = _tokens(sample.title)
        description_tokens = _tokens(sample.description)[:20]
        for token in title_tokens:
            counts[token] = counts.get(token, 0) + weight * 2.5
        for token in description_tokens:
            counts[token] = counts.get(token, 0) + weight * 0.4
        for first, second in zip(title_tokens, title_tokens[1:], strict=False):
            if first != second:
                key = f"{first} {second}"
                counts[key] = counts.get(key, 0) + weight * 2.2
    return counts


def _top(
    counter: Mapping[str, float],
    *,
    limit: int,
    excluded: set[str] | None = None,
) -> tuple[str, ...]:
    excluded = excluded or set()
    ranked = sorted(
        counter.items(),
        key=lambda item: (
            -(item[1] * (1.15 if " " in item[0] else 1.0)),
            item[0],
        ),
    )
    selected: list[str] = []
    for value, _score in ranked:
        if value in excluded:
            continue
        value_tokens = set(value.split())
        if any(
            value_tokens < set(existing.split()) or set(existing.split()) < value_tokens
            for existing in selected
        ):
            continue
        selected.append(value)
        if len(selected) >= limit:
            break
    return tuple(selected)


def extract_channel_profile_v2(
    *,
    channel_title: str,
    channel_description: str,
    samples: list[ChannelVideoSample],
    captured_at: datetime,
) -> ChannelProfileInference:
    ordered = sorted(samples, key=lambda sample: _aware(sample.published_at), reverse=True)
    current_counts = _topic_counts(ordered, captured_at=captured_at, current=True)
    channel_counts: Counter[str] = Counter()
    channel_counts.update(_tokens(channel_title))
    channel_counts.update(_tokens(channel_description))
    for token, score in channel_counts.items():
        current_counts[token] = current_counts.get(token, 0) + score * 0.7
    legacy_counts = _topic_counts(ordered, captured_at=captured_at, current=False)
    core = _top(current_counts, limit=8)
    adjacent = _top(current_counts, limit=8, excluded=set(core))
    legacy = _top(legacy_counts, limit=10, excluded=set((*core, *adjacent)))

    format_weights: defaultdict[str, float] = defaultdict(float)
    successful_weights: defaultdict[str, float] = defaultdict(float)
    for index, sample in enumerate(ordered):
        content_format = _format(sample)
        recency_weight = 0.5 ** (index / 12)
        format_weights[content_format] += recency_weight
        if sample.outlier_ratio is not None and sample.outlier_ratio >= 1.2:
            successful_weights[content_format] += recency_weight * sample.outlier_ratio
    preferred_formats = tuple(
        key
        for key, _value in sorted(
            format_weights.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )[:4]
    successful_formats = tuple(
        key
        for key, _value in sorted(
            successful_weights.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )[:3]

    long_form_durations = sorted(
        sample.duration_seconds
        for sample in ordered
        if not sample.is_short and not sample.is_live and sample.duration_seconds > 90
    )
    if long_form_durations:
        low_index = max(0, round((len(long_form_durations) - 1) * 0.2))
        high_index = min(
            len(long_form_durations) - 1,
            round((len(long_form_durations) - 1) * 0.8),
        )
        duration_low = long_form_durations[low_index]
        duration_high = long_form_durations[high_index]
    else:
        duration_low, duration_high = 480, 1_800

    dates = sorted((_aware(sample.published_at) for sample in ordered), reverse=True)
    gaps = [
        max(0.0, (first - second).total_seconds() / 86_400)
        for first, second in zip(dates, dates[1:], strict=False)
    ]
    median_gap = median(gaps) if gaps else 7.0
    uploads_per_month = round(30 / max(median_gap, 0.5), 1)

    all_titles = " ".join(sample.title.lower() for sample in ordered[:30])
    beginner = sum(
        all_titles.count(value)
        for value in ("beginner", "no code", "no-code", "explained", "basics")
    )
    advanced = sum(
        all_titles.count(value)
        for value in ("production", "benchmark", "architecture", "api", "advanced")
    )
    audience_sophistication = (
        "advanced"
        if advanced > beginner + 1
        else "beginner"
        if beginner > advanced + 1
        else "intermediate"
    )
    authority = (
        "expert"
        if sum(
            all_titles.count(value)
            for value in ("tested", "benchmark", "case study", "production", "built")
        )
        >= 5
        else "practitioner"
    )
    return ChannelProfileInference(
        core_topics=core,
        adjacent_topics=adjacent,
        legacy_topics=legacy,
        preferred_formats=preferred_formats or ("Evidence-led explainer",),
        successful_formats=successful_formats,
        typical_duration_min_seconds=max(60, duration_low),
        typical_duration_max_seconds=max(duration_low, duration_high),
        upload_cadence={
            "median_days_between_uploads": round(median_gap, 2),
            "uploads_per_month": uploads_per_month,
            "sample_size": len(gaps),
            "method": "weighted-history-v2",
        },
        audience_sophistication=audience_sophistication,
        creator_authority=authority,
        title_style={
            "voice": "specific and evidence-led",
            "observed_formats": list(preferred_formats),
            "history_sample_size": len(ordered),
        },
        cleaned_channel_description=sanitize_channel_text(channel_description)[:1_000],
    )
