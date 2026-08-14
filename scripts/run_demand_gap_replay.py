"""Does anything we can see at a checkpoint predict future demand?

The outcome here is the creator-relevant one: videos published on the topic
after the checkpoint outperforming their own channels' usual results. Adoption
by other creators is reported alongside, so the two targets can be compared on
identical candidates.

Only observations recorded at or before each checkpoint are used, so this runs
on the genuinely observed window (from 2026-07-05) rather than on backfill.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from es_core.demand import DemandModel, DemandPolicy, ViewObservation
from es_core.identity import TopicRegistry
from es_core.outcome import DemandGapPolicy, evaluate_demand_gap
from es_core.pipeline import build_candidates
from es_eval import dataset as dataset_module
from es_eval import replay as replay_module


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def load_observations(path: Path) -> list[ViewObservation]:
    observations: list[ViewObservation] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 4 or not row[3]:
                continue
            observations.append(
                ViewObservation(
                    video_id=row[0],
                    observed_at=datetime.fromisoformat(row[1].replace("Z", "+00:00")),
                    age_days=int(row[2]) / 86_400,
                    view_count=int(row[3]),
                )
            )
    return observations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--horizon", type=int, default=21)
    parser.add_argument("--observation", choices=("real", "naive"), default="real")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = dataset_module.load(
        cohort=args.data / "cohort.jsonl.gz",
        embeddings=args.data / "embeddings-v1.jsonl",
        discovery=args.data / "discovery.csv",
        treat_publication_as_observation=args.observation == "naive",
    )
    observations = load_observations(args.data / "snapshots.csv.gz")
    channel_of = {video.video_id: video.channel_id for video in data.videos}
    print(f"videos={len(data.videos)} embedded={len(data.embedded)} snapshots={len(observations)}")

    demand_policy = DemandGapPolicy(horizon_days=args.horizon)
    checkpoints = replay_module.weekly_checkpoints(args.start, args.end)
    registry = TopicRegistry()
    rows: list[dict[str, float | str | bool | None]] = []

    for checkpoint in checkpoints:
        # The outcome window must be fully observed, otherwise the label is not
        # a label but a partial reading.
        outcome_end = checkpoint + timedelta(days=args.horizon)
        model_at_outcome = DemandModel.build(
            data.videos,
            observations,
            as_of=outcome_end,
            policy=DemandPolicy(),
        )
        candidates = build_candidates(
            data.videos,
            data.embeddings,
            as_of=checkpoint,
            registry=registry,
        )
        publishable = [
            candidate
            for candidate in candidates
            if candidate.evidence.status == "accepted" and candidate.anchors
        ]
        future = [video for video in data.videos if checkpoint < video.published_at <= outcome_end]
        fired = 0
        for candidate in publishable:
            topic_future = replay_module._topic_future(candidate, future, data)
            outcome = evaluate_demand_gap(
                as_of=checkpoint,
                future_videos=topic_future,
                lift_of=lambda video: model_at_outcome.normalized_lift(
                    video.video_id, channel_id=channel_of.get(video.video_id, "")
                ),
                policy=demand_policy,
            )
            if outcome.supported_videos == 0:
                continue
            fired += int(outcome.fired)
            rows.append(
                {
                    "checkpoint": checkpoint.date().isoformat(),
                    "topic_id": candidate.topic_id,
                    "anchor": candidate.anchors[0].term if candidate.anchors else "",
                    "label": outcome.fired,
                    "median_lift": outcome.median_lift,
                    "supported": outcome.supported_videos,
                    "saturating": outcome.saturating,
                    **{name: value for name, value in candidate.features.items()},
                }
            )
        print(
            f"{checkpoint.date()}: candidates={len(candidates)} publishable={len(publishable)} "
            f"labelled={sum(1 for row in rows if row['checkpoint'] == checkpoint.date().isoformat())} "
            f"fired={fired} baseline_channels={model_at_outcome.covered_channels}"
        )

    labels = [bool(row["label"]) for row in rows]
    if not rows or not any(labels):
        print(f"episodes={len(rows)} positives={sum(labels)} — insufficient support")
        return
    base_rate = sum(labels) / len(labels)
    print(f"\nepisodes={len(rows)} positives={sum(labels)} base_rate={base_rate:.4f}")
    print(f"{'feature':28} {'prec@Q':>8} {'lift':>7} {'AP':>7}  95% CI")
    scored = []
    for feature in sorted(
        set(replay_module.BASELINES.values())
        | {
            "anchor_score_max",
            "anchor_novelty_max",
            "angle_diversity",
            "new_creator_share",
            "creator_diversity",
            "channel_entropy",
            "log_topic_age_days",
        }
    ):
        values = [float(row.get(feature, 0.0) or 0.0) for row in rows]
        precision, _ = replay_module.top_quintile_precision(values, labels)
        lower, _, upper = replay_module.bootstrap_lift(values, labels)
        average = replay_module.average_precision(values, labels)
        scored.append((precision / base_rate, feature, precision, average, lower, upper))
    for lift, feature, precision, average, lower, upper in sorted(scored, reverse=True):
        print(f"{feature:28} {precision:8.4f} {lift:7.3f} {average:7.4f}  {lower:.2f}-{upper:.2f}")

    if args.output:
        args.output.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
