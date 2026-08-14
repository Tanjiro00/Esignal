"""Development replay of the v2 core on the production cohort.

Two modes, and the difference between them is the point:

* ``--observation real``   uses ``first_discovered_at`` as observation time.
  Honest, but this database only started observing on 2026-07-05.
* ``--observation naive``  pretends publication time is observation time, which
  is what the v1 runs did. Included only so both algorithms can be compared on
  identical inputs; its numbers are not evidence of predictive power.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from es_core.anchors import AnchorPolicy
from es_core.clustering import ClusterPolicy
from es_core.outcome import AdoptionPolicy
from es_core.pipeline import PipelinePolicy
from es_eval import dataset as dataset_module
from es_eval import replay as replay_module


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--horizon", type=int, default=42)
    parser.add_argument("--observation", choices=("real", "naive"), default="real")
    parser.add_argument("--niche-strength", type=float, default=0.30)
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
        treat_publication_as_observation=args.observation == "naive",
    )
    print(f"videos={len(data.videos)} embedded={len(data.embedded)} observation={args.observation}")

    checkpoints = replay_module.weekly_checkpoints(args.start, args.end)
    result = replay_module.run(
        data,
        checkpoints,
        pipeline_policy=PipelinePolicy(
            anchors=AnchorPolicy(),
            clustering=ClusterPolicy(niche_centroid_strength=args.niche_strength),
        ),
        adoption_policy=AdoptionPolicy(horizon_days=args.horizon),
        publishable_only=not args.all_candidates,
    )

    episodes = result.episodes
    labels = [episode.label for episode in episodes]
    print(
        f"checkpoints={len(checkpoints)} episodes={len(episodes)} "
        f"positives={sum(labels)} base_rate={result.base_rate:.4f} "
        f"rejected_evidence={result.rejected_by_evidence} "
        f"rejected_anchor={result.rejected_by_anchor}"
    )
    if not episodes or not any(labels):
        print("insufficient positive support for ranking metrics")
        return

    rows = []
    for name, feature in replay_module.BASELINES.items():
        scores = [episode.candidate.features.get(feature, 0.0) for episode in episodes]
        precision, count = replay_module.top_quintile_precision(scores, labels)
        lower, median, upper = replay_module.bootstrap_lift(scores, labels)
        rows.append(
            {
                "ranking": name,
                "precision_at_quintile": round(precision, 6),
                "selected": count,
                "lift": round(precision / result.base_rate, 6) if result.base_rate else 0.0,
                "lift_ci": [round(lower, 4), round(median, 4), round(upper, 4)],
                "average_precision": round(replay_module.average_precision(scores, labels), 6),
            }
        )
    print(f"{'ranking':20} {'prec@Q':>8} {'lift':>7} {'AP':>7}  lift 95% CI")
    for row in rows:
        print(
            f"{row['ranking']:20} {row['precision_at_quintile']:8.4f} "
            f"{row['lift']:7.3f} {row['average_precision']:7.4f}  "
            f"{row['lift_ci'][0]:.2f}-{row['lift_ci'][2]:.2f}"
        )
    print(f"median lead days: {replay_module.median_lead_days(episodes):.2f}")

    if args.output:
        args.output.write_text(
            json.dumps(
                {
                    "observation_mode": args.observation,
                    "observation_floor": (
                        result.observation_floor.isoformat() if result.observation_floor else None
                    ),
                    "checkpoints": [point.isoformat() for point in checkpoints],
                    "horizon_days": args.horizon,
                    "episodes": len(episodes),
                    "positives": sum(labels),
                    "base_rate": result.base_rate,
                    "rejected_by_evidence": result.rejected_by_evidence,
                    "rejected_by_anchor": result.rejected_by_anchor,
                    "rankings": rows,
                    "median_lead_days": replay_module.median_lead_days(episodes),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
