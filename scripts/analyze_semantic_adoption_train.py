from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from packages.backtest.modern_adoption import load_structural_cohort, weekly_checkpoints
from packages.backtest.semantic_adoption import (
    SemanticCandidateBuilder,
    SemanticReplayPolicy,
    build_semantic_episodes,
    load_embedding_map,
)


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
    base = SemanticReplayPolicy()
    results: list[dict[str, object]] = []
    for minimum_cluster_size, minimum_samples, method in (
        (2, 1, "leaf"),
        (2, 2, "leaf"),
        (3, 2, "leaf"),
        (3, 3, "leaf"),
        (3, 2, "eom"),
    ):
        policy = replace(
            base,
            minimum_cluster_size=minimum_cluster_size,
            minimum_samples=minimum_samples,
            cluster_selection_method=method,
        )
        builder = SemanticCandidateBuilder(videos, embeddings, policy=policy)
        episodes = build_semantic_episodes(builder, checkpoints)
        result = {
            "policy": asdict(policy),
            "episodes": len(episodes),
            "positives": sum(episode.adoption_label for episode in episodes),
            "base_rate": round(
                sum(episode.adoption_label for episode in episodes) / max(len(episodes), 1),
                6,
            ),
            "distinct_channels_median": sorted(
                episode.state.distinct_channel_count for episode in episodes
            )[len(episodes) // 2]
            if episodes
            else None,
            "examples": [
                {
                    "checkpoint": episode.checkpoint_at.isoformat(),
                    "label": episode.state.label,
                    "evidence_titles": episode.state.evidence_titles,
                    "videos": episode.state.active_video_count,
                    "channels": episode.state.distinct_channel_count,
                    "mean_similarity": episode.state.mean_similarity,
                    "outcome": episode.adoption_label,
                    "future_videos": episode.outcome.future_video_count,
                }
                for episode in sorted(
                    episodes,
                    key=lambda item: (
                        -item.state.active_video_count,
                        item.checkpoint_at,
                        item.state.label,
                    ),
                )[:20]
            ],
        }
        results.append(result)
        print(json.dumps({key: value for key, value in result.items() if key != "examples"}))
    args.output.write_text(json.dumps({"results": results}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
