from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.backtest.modern_adoption import load_structural_cohort, weekly_checkpoints
from packages.backtest.semantic_adoption import (
    QualityGatedSemanticCandidateBuilder,
    SemanticCandidateBuilder,
    SemanticEpisode,
    SemanticReplayPolicy,
    build_semantic_episodes,
    load_embedding_map,
)
from packages.clustering.evidence_quality import (
    COPY_RESISTANT_EVIDENCE_POLICY,
    EvidenceQualityPolicy,
)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _summary(episodes: tuple[SemanticEpisode, ...]) -> dict[str, Any]:
    positives = sum(episode.adoption_label for episode in episodes)
    return {
        "episodes": len(episodes),
        "positives": positives,
        "base_rate": round(positives / max(len(episodes), 1), 6),
        "examples": [
            {
                "checkpoint_at": episode.checkpoint_at.isoformat(),
                "label": episode.state.label,
                "evidence_video_ids": episode.state.evidence_video_ids,
                "evidence_titles": episode.state.evidence_titles,
                "active_videos": episode.state.active_video_count,
                "channels": episode.state.distinct_channel_count,
                "outcome": episode.adoption_label,
                "future_videos": episode.outcome.future_video_count,
                "new_future_channels": episode.outcome.new_future_channel_count,
            }
            for episode in sorted(
                episodes,
                key=lambda item: (
                    -item.state.active_video_count,
                    item.checkpoint_at,
                    item.state.topic_key,
                ),
            )[:25]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    videos = load_structural_cohort(args.cohort)
    embeddings = load_embedding_map(args.embeddings)
    checkpoints = weekly_checkpoints(
        datetime(2026, 3, 1, 23, 59, 59, tzinfo=UTC),
        datetime(2026, 5, 25, 23, 59, 59, tzinfo=UTC),
    )
    replay_policy = SemanticReplayPolicy()
    copy_resistant_policy = COPY_RESISTANT_EVIDENCE_POLICY
    strict_anchor_policy = EvidenceQualityPolicy()
    baseline = build_semantic_episodes(
        SemanticCandidateBuilder(videos, embeddings, policy=replay_policy),
        checkpoints,
    )
    copy_resistant = build_semantic_episodes(
        QualityGatedSemanticCandidateBuilder(
            videos,
            embeddings,
            policy=replay_policy,
            quality_policy=copy_resistant_policy,
        ),
        checkpoints,
    )
    strict_anchor = build_semantic_episodes(
        QualityGatedSemanticCandidateBuilder(
            videos,
            embeddings,
            policy=replay_policy,
            quality_policy=strict_anchor_policy,
        ),
        checkpoints,
    )
    payload: dict[str, Any] = {
        "analysis_boundary": (
            "March-May training checkpoints only. June was already consumed by v1 and is "
            "not a holdout for this challenger."
        ),
        "cohort_sha256": _hash(args.cohort),
        "embeddings_sha256": _hash(args.embeddings),
        "checkpoints": [checkpoints[0].isoformat(), checkpoints[-1].isoformat()],
        "replay_policy": asdict(replay_policy),
        "copy_resistant_policy": asdict(copy_resistant_policy),
        "strict_anchor_policy": asdict(strict_anchor_policy),
        "baseline": _summary(baseline),
        "copy_resistant": _summary(copy_resistant),
        "strict_anchor": _summary(strict_anchor),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "baseline": {
                    key: value for key, value in payload["baseline"].items() if key != "examples"
                },
                "copy_resistant": {
                    key: value
                    for key, value in payload["copy_resistant"].items()
                    if key != "examples"
                },
                "strict_anchor": {
                    key: value
                    for key, value in payload["strict_anchor"].items()
                    if key != "examples"
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
