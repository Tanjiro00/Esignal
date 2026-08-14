from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

ASSOCIATION_MODEL_VERSION = "outcome-association-v1"
METRICS_MODEL_VERSION = "outcome-metrics-v2"
MINIMUM_STABLE_COMPARABLE_SAMPLE = 5
COMPARABLE_PERIOD_DAYS = 180
SNAPSHOT_HORIZONS_HOURS = (24, 72, 168, 720)
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+-]{1,}")
STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "before",
    "best",
    "build",
    "channel",
    "could",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "only",
    "real",
    "that",
    "their",
    "this",
    "video",
    "what",
    "when",
    "with",
    "your",
}
SPONSOR_MARKERS = (
    "sponsored",
    "paid partnership",
    "thanks to our sponsor",
    "#ad",
)


@dataclass(frozen=True)
class BriefCandidate:
    brief_id: str
    signal_id: str
    title: str
    evidence_text: str
    created_at: datetime


@dataclass(frozen=True)
class MatchResult:
    brief_id: str
    signal_id: str
    confidence: float
    reason_codes: tuple[str, ...]
    features: dict[str, float | int | str]


@dataclass(frozen=True)
class SnapshotPoint:
    age_hours: float
    views: int
    watch_time_minutes: float | None = None
    average_view_duration_seconds: float | None = None
    average_percentage_viewed: float | None = None
    subscribers_gained: int | None = None
    revenue: float | None = None


@dataclass(frozen=True)
class BaselineCandidate:
    video_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int
    is_short: bool
    is_live: bool
    snapshots: tuple[SnapshotPoint, ...]


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if token not in STOPWORDS and len(token) >= 3
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _coverage(query: set[str], evidence: set[str]) -> float:
    return len(query & evidence) / len(query) if query else 0.0


def _is_sponsored(value: str) -> bool:
    normalized = value.lower()
    return any(marker in normalized for marker in SPONSOR_MARKERS)


def match_upload_to_brief(
    *,
    upload_title: str,
    upload_description: str,
    published_at: datetime,
    candidates: Sequence[BriefCandidate],
    minimum_confidence: float = 0.18,
) -> MatchResult | None:
    """Return the best auditable brief association for an owned upload."""

    upload_title_tokens = _tokens(upload_title)
    upload_all_tokens = upload_title_tokens | _tokens(upload_description)
    best: MatchResult | None = None
    for candidate in candidates:
        title_tokens = _tokens(candidate.title)
        evidence_tokens = _tokens(candidate.evidence_text)
        title_similarity = _jaccard(upload_title_tokens, title_tokens)
        evidence_coverage = _coverage(upload_title_tokens, evidence_tokens | title_tokens)
        reverse_coverage = _coverage(title_tokens, upload_all_tokens)
        days_from_brief = max(
            0.0,
            (published_at - candidate.created_at).total_seconds() / 86_400,
        )
        recency = math.exp(-days_from_brief / 45)
        confidence = round(
            min(
                0.99,
                title_similarity * 0.42
                + evidence_coverage * 0.25
                + reverse_coverage * 0.23
                + recency * 0.10,
            ),
            4,
        )
        if confidence < minimum_confidence:
            continue
        reason_codes: list[str] = []
        if title_similarity >= 0.2:
            reason_codes.append("title_overlap")
        if evidence_coverage >= 0.3:
            reason_codes.append("description_or_topic_overlap")
        if days_from_brief <= 30:
            reason_codes.append("published_after_active_brief")
        result = MatchResult(
            brief_id=candidate.brief_id,
            signal_id=candidate.signal_id,
            confidence=confidence,
            reason_codes=tuple(reason_codes or ("semantic_match",)),
            features={
                "title_similarity": round(title_similarity, 4),
                "evidence_coverage": round(evidence_coverage, 4),
                "brief_title_coverage": round(reverse_coverage, 4),
                "days_from_brief": round(days_from_brief, 2),
            },
        )
        if best is None or result.confidence > best.confidence:
            best = result
    return best


def _snapshot_at(
    snapshots: Sequence[SnapshotPoint],
    horizon_hours: int,
) -> SnapshotPoint | None:
    if not snapshots:
        return None
    eligible = [point for point in snapshots if point.age_hours <= horizon_hours * 1.2]
    if eligible:
        return min(eligible, key=lambda point: abs(point.age_hours - horizon_hours))
    return None


def build_comparable_baseline(
    *,
    target: BaselineCandidate,
    history: Sequence[BaselineCandidate],
    max_samples: int = 20,
) -> dict[str, object]:
    """Build a robust baseline from format-, duration-, topic-, and period peers."""

    target_tokens = _tokens(target.title)
    target_sponsored = _is_sponsored(f"{target.title} {target.description}")
    candidates: list[tuple[float, BaselineCandidate]] = []
    for item in history:
        if item.video_id == target.video_id or item.published_at >= target.published_at:
            continue
        if item.is_short != target.is_short or item.is_live != target.is_live:
            continue
        if (target.published_at - item.published_at).days > COMPARABLE_PERIOD_DAYS:
            continue
        duration_ratio = item.duration_seconds / max(target.duration_seconds, 1)
        if not 0.6 <= duration_ratio <= 1.6:
            continue
        if _is_sponsored(f"{item.title} {item.description}") != target_sponsored:
            continue
        topic_similarity = _jaccard(target_tokens, _tokens(item.title))
        candidates.append((topic_similarity, item))

    candidates.sort(
        key=lambda pair: (pair[0], pair[1].published_at),
        reverse=True,
    )
    selected = [item for _similarity, item in candidates[:max_samples]]

    horizon_values: dict[str, object] = {}
    for horizon in SNAPSHOT_HORIZONS_HOURS:
        horizon_key = _horizon_key(horizon)
        values = [
            point.views
            for item in selected
            if (point := _snapshot_at(item.snapshots, horizon)) is not None
        ]
        sample_size = len(values)
        horizon_values[f"views_{horizon_key}"] = int(median(values)) if values else None
        horizon_values[f"sample_size_{horizon_key}"] = sample_size
        horizon_values[f"stability_{horizon_key}"] = (
            "stable" if sample_size >= MINIMUM_STABLE_COMPARABLE_SAMPLE else "early"
        )
    return {
        "version": METRICS_MODEL_VERSION,
        "sample_size": len(selected),
        "minimum_stable_sample_size": MINIMUM_STABLE_COMPARABLE_SAMPLE,
        "stability": ("stable" if len(selected) >= MINIMUM_STABLE_COMPARABLE_SAMPLE else "early"),
        "video_ids": [item.video_id for item in selected],
        "filters": {
            "content_type": "short" if target.is_short else "live" if target.is_live else "long",
            "duration_ratio": "0.6–1.6x",
            "topic_family": "title-token similarity ranked",
            "upload_period_days": COMPARABLE_PERIOD_DAYS,
            "sponsored": target_sponsored,
        },
        **horizon_values,
    }


def _horizon_key(hours: int) -> str:
    return {24: "24h", 72: "72h", 168: "7d", 720: "30d"}[hours]


def _median_optional(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(float(median(present)), 4) if present else None


def build_associated_metrics(
    *,
    target_snapshots: Sequence[SnapshotPoint],
    baseline: dict[str, object],
    signal_detected_at: datetime,
    brief_created_at: datetime,
    published_at: datetime,
) -> dict[str, object]:
    metrics: dict[str, object] = {
        "version": METRICS_MODEL_VERSION,
        "interpretation": "associated_uplift_not_causal",
        "comparator": baseline,
        "publish_delay_from_signal_hours": round(
            max(0.0, (published_at - signal_detected_at).total_seconds() / 3600),
            2,
        ),
        "publish_delay_from_brief_hours": round(
            max(0.0, (published_at - brief_created_at).total_seconds() / 3600),
            2,
        ),
    }
    for horizon in SNAPSHOT_HORIZONS_HOURS:
        key = _horizon_key(horizon)
        point = _snapshot_at(target_snapshots, horizon)
        views = point.views if point else None
        baseline_views = baseline.get(f"views_{key}")
        metrics[f"views_{key}"] = views
        metrics[f"baseline_views_{key}"] = baseline_views
        metrics[f"channel_relative_uplift_{key}"] = (
            round(views / float(baseline_views), 3)
            if views is not None and isinstance(baseline_views, (float, int)) and baseline_views > 0
            else None
        )
    latest = max(target_snapshots, key=lambda point: point.age_hours, default=None)
    metrics["watch_time_minutes"] = latest.watch_time_minutes if latest else None
    metrics["average_view_duration_seconds"] = (
        latest.average_view_duration_seconds if latest else None
    )
    metrics["average_percentage_viewed"] = latest.average_percentage_viewed if latest else None
    metrics["subscribers_gained"] = latest.subscribers_gained if latest else None
    metrics["revenue"] = latest.revenue if latest else None
    metrics["watch_time_uplift"] = _median_optional(())
    metrics["retention_uplift"] = _median_optional(())
    metrics["subscriber_uplift"] = _median_optional(())
    metrics["revenue_uplift"] = _median_optional(())
    return metrics
