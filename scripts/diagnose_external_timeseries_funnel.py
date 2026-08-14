from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from packages.backtest.external_timeseries import ExternalTimeseriesReplay, _latest_snapshots
from packages.clustering import cluster_microtopics_v6
from scripts.run_external_timeseries_backtest import CHECKPOINTS, _load_dataset


def _raw_states(
    replay: ExternalTimeseriesReplay,
    observed_at: datetime,
) -> dict[str, dict[str, Any]]:
    cutoff = observed_at.astimezone(UTC)
    grouped: defaultdict[str, list[Any]] = defaultdict(list)
    for video_id, key in replay._topic_key_by_video.items():
        video = replay._by_id[video_id]
        if cutoff - timedelta(days=30) <= video.published_at <= cutoff and _latest_snapshots(
            video, cutoff
        ):
            grouped[key].append(video)
    states = {}
    for key, videos in grouped.items():
        cluster = cluster_microtopics_v6([replay._documents[video.video_id] for video in videos])[0]
        features = [replay._video_feature(video, cutoff) for video in videos]
        outliers = [feature[1] for feature in features if feature is not None]
        recent = [video for video in videos if video.published_at >= cutoff - timedelta(hours=72)]
        states[key] = {
            "key": key,
            "label": cluster.label,
            "visible": cluster.visible,
            "reason_codes": list(cluster.reason_codes),
            "specificity": cluster.specificity_score,
            "video_count": len(videos),
            "supply_72h": len(recent),
            "distinct_channels": len({video.channel_id for video in videos}),
            "median_outlier": median(outliers) if outliers else 0,
            "titles": [video.title for video in videos[:5]],
        }
    return states


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    replay = ExternalTimeseriesReplay(_load_dataset(args.dataset))
    state_cache: dict[datetime, dict[str, dict[str, Any]]] = {}

    def states(at: datetime) -> dict[str, dict[str, Any]]:
        if at not in state_cache:
            state_cache[at] = _raw_states(replay, at)
        return state_cache[at]

    checkpoints: list[dict[str, Any]] = []
    for raw_checkpoint, split in CHECKPOINTS:
        checkpoint = datetime.fromisoformat(raw_checkpoint).astimezone(UTC)
        baseline = states(checkpoint)
        futures = [states(checkpoint + timedelta(days=day)) for day in range(1, 31)]
        topics: list[dict[str, Any]] = []
        for key, row in baseline.items():
            baseline_supply = max(int(row["supply_72h"]), 1)
            max_supply = 0.0
            peak_lift = 0.0
            fired_at = None
            for offset, future_states in enumerate(futures, start=1):
                future = future_states.get(key)
                if future is None:
                    continue
                supply_growth = float(future["supply_72h"]) / baseline_supply
                lift = float(future["median_outlier"])
                max_supply = max(max_supply, supply_growth)
                peak_lift = max(peak_lift, lift)
                if fired_at is None and supply_growth >= 3 and lift >= 3:
                    fired_at = offset
            topics.append(
                {
                    **row,
                    "fired": fired_at is not None,
                    "lead_days": fired_at,
                    "max_supply_growth": round(max_supply, 4),
                    "peak_lift": round(peak_lift, 4),
                }
            )
        checkpoints.append(
            {
                "checkpoint_at": checkpoint.isoformat(),
                "split": split,
                "raw_topic_count": len(topics),
                "visible_topic_count": sum(bool(row["visible"]) for row in topics),
                "fired_topic_count": sum(bool(row["fired"]) for row in topics),
                "reason_counts": dict(
                    Counter(reason for row in topics for reason in row["reason_codes"])
                ),
                "topics": topics,
            }
        )
    payload = {
        "diagnostic_version": "external-topic-funnel-diagnostic-v1",
        "not_a_registered_quality_gate": True,
        "checkpoints": checkpoints,
        "totals": {
            "raw_topics": sum(int(row["raw_topic_count"]) for row in checkpoints),
            "visible_topics": sum(int(row["visible_topic_count"]) for row in checkpoints),
            "fired_topics": sum(int(row["fired_topic_count"]) for row in checkpoints),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
