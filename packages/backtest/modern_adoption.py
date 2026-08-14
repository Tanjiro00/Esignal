from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from packages.backtest.probability_replay import ProbabilityEpisode, build_probability_episodes
from packages.backtest.youniverse import StructuralVideo
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
)

MODERN_ADOPTION_REPLAY_VERSION = "modern-youtube-adoption-replay-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return _aware(datetime.fromisoformat(text))


def load_structural_cohort(path: Path) -> tuple[StructuralVideo, ...]:
    """Load public metadata only; no outcome engagement fields are accepted."""

    opener = gzip.open if path.suffix == ".gz" else open
    videos: list[StructuralVideo] = []
    with opener(path, "rt", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            forbidden = {
                "view_count",
                "final_view_count",
                "like_count",
                "comment_count",
                "views_per_hour",
            }.intersection(payload)
            if forbidden:
                raise ValueError(
                    f"candidate cohort line {line_number} contains outcome fields: "
                    f"{', '.join(sorted(forbidden))}"
                )
            videos.append(
                StructuralVideo(
                    video_id=str(payload["video_id"]),
                    channel_id=str(payload["channel_id"]),
                    title=str(payload.get("title") or ""),
                    description=str(payload.get("description") or ""),
                    tags=tuple(str(item) for item in payload.get("tags") or ()),
                    category=str(payload.get("category") or ""),
                    upload_date=_timestamp(payload["upload_date"]),
                )
            )
    return tuple(
        sorted(
            videos,
            key=lambda video: (_aware(video.upload_date), video.video_id),
        )
    )


def weekly_checkpoints(start: datetime, end: datetime) -> tuple[datetime, ...]:
    current = _aware(start)
    upper = _aware(end)
    checkpoints: list[datetime] = []
    while current <= upper:
        checkpoints.append(current)
        current += timedelta(days=7)
    return tuple(checkpoints)


def build_temporal_adoption_episodes(
    candidate_index: StructuralCandidateIndex,
    outcome_evaluator: StructuralOutcomeEvaluator,
    *,
    train_start: datetime,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
) -> tuple[tuple[ProbabilityEpisode, ...], tuple[ProbabilityEpisode, ...]]:
    if _aware(train_end) >= _aware(test_start):
        raise ValueError("train_end must be earlier than test_start")
    checkpoints = weekly_checkpoints(train_start, train_end) + weekly_checkpoints(
        test_start,
        test_end,
    )
    episodes = build_probability_episodes(candidate_index, outcome_evaluator, checkpoints)
    train = tuple(
        episode
        for episode in episodes
        if _aware(train_start) <= episode.checkpoint_at <= _aware(train_end)
    )
    test = tuple(
        episode
        for episode in episodes
        if _aware(test_start) <= episode.checkpoint_at <= _aware(test_end)
    )
    return train, test


def temporal_fit_calibration_split(
    episodes: Sequence[ProbabilityEpisode],
    *,
    fitting_fraction: float = 0.75,
) -> tuple[tuple[ProbabilityEpisode, ...], tuple[ProbabilityEpisode, ...], datetime]:
    if not 0 < fitting_fraction < 1:
        raise ValueError("fitting_fraction must be between zero and one")
    checkpoints = sorted({episode.checkpoint_at for episode in episodes})
    if len(checkpoints) < 4:
        raise ValueError("at least four training checkpoints are required")
    boundary_index = min(
        len(checkpoints) - 1,
        max(1, int(len(checkpoints) * fitting_fraction)),
    )
    boundary = checkpoints[boundary_index]
    fitting = tuple(episode for episode in episodes if episode.checkpoint_at < boundary)
    calibration = tuple(episode for episode in episodes if episode.checkpoint_at >= boundary)
    return fitting, calibration, boundary


def maximum_complete_checkpoint(
    videos: Iterable[StructuralVideo],
    *,
    outcome_horizon_days: int,
) -> datetime:
    latest = max(_aware(video.upload_date) for video in videos)
    return latest - timedelta(days=outcome_horizon_days)


__all__ = [
    "MODERN_ADOPTION_REPLAY_VERSION",
    "build_temporal_adoption_episodes",
    "load_structural_cohort",
    "maximum_complete_checkpoint",
    "temporal_fit_calibration_split",
    "weekly_checkpoints",
]
