from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.backtest.cross_market import (
    CrossMarketCheckpoint,
    CrossMarketPolicy,
    CrossMarketReplay,
    deduplicate_cross_market_episodes,
    summarize_cross_market,
)
from packages.backtest.global_trending import (
    GlobalTrendingObservation,
    iter_filtered_observations,
)
from packages.clustering import MicrotopicDocument, cluster_microtopics_v6, normalize_entities
from scripts.run_global_cross_market_backtest import _checkpoints, _file_hash

SENSITIVITY_CONFIGS = (
    ("primary_21d_country5", 21, 5),
    ("horizon_14d", 14, 5),
    ("horizon_30d", 30, 5),
    ("new_country_floor_3", 21, 3),
    ("new_country_floor_10", 21, 10),
)
_FORMAT_MARKERS = re.compile(
    r"(?i)(?<![\w])(?:how to|tutorial|review|hands-on|explained|demo|livestream|"
    r"podcast|shorts?|reaction)(?![\w])"
)


def _format_invariance(
    observations: tuple[GlobalTrendingObservation, ...],
) -> dict[str, Any]:
    first_by_video: dict[str, GlobalTrendingObservation] = {}
    for row in observations:
        first_by_video.setdefault(row.video_id, row)
    checked = 0
    unchanged = 0
    examples: list[dict[str, str]] = []
    for row in first_by_video.values():
        stripped_title = " ".join(_FORMAT_MARKERS.sub(" ", row.title).split())
        if stripped_title == row.title:
            continue
        checked += 1
        original = MicrotopicDocument(
            id=row.video_id,
            title=row.title,
            description=row.description,
            entities=tuple(normalize_entities(row.title, row.description)),
        )
        stripped = MicrotopicDocument(
            id=row.video_id,
            title=stripped_title,
            description=row.description,
            entities=tuple(normalize_entities(stripped_title, row.description)),
        )
        original_clusters = cluster_microtopics_v6([original])
        stripped_clusters = cluster_microtopics_v6([stripped])
        original_key = original_clusters[0].key if original_clusters else None
        stripped_key = stripped_clusters[0].key if stripped_clusters else None
        if original_key == stripped_key:
            unchanged += 1
        elif len(examples) < 20:
            examples.append(
                {
                    "video_id": row.video_id,
                    "title": row.title,
                    "stripped_title": stripped_title,
                    "original_key": original_key or "unmapped",
                    "stripped_key": stripped_key or "unmapped",
                }
            )
    return {
        "checked_videos": checked,
        "unchanged_topic_identity": unchanged,
        "unchanged_percent": round(unchanged / checked * 100, 1) if checked else None,
        "changed_examples": examples,
    }


def _diagnostics(checkpoints: tuple[Any, ...]) -> dict[str, Any]:
    false_positive_labels: Counter[str] = Counter()
    duplicate_breadth_without_new_supply = 0
    selected = 0
    false_positive_examples: list[dict[str, Any]] = []
    for checkpoint in checkpoints:
        outcomes = {outcome.topic_key: outcome for outcome in checkpoint.outcomes}
        for prediction in checkpoint.predictions:
            selected += 1
            outcome = outcomes[prediction.topic_key]
            if not outcome.fired:
                false_positive_labels[prediction.label] += 1
                if len(false_positive_examples) < 20:
                    false_positive_examples.append(
                        {
                            "checkpoint_at": checkpoint.checkpoint_at.isoformat(),
                            "topic_key": prediction.topic_key,
                            "label": prediction.label,
                            "evidence_urls": [
                                f"https://www.youtube.com/watch?v={video_id}"
                                for video_id in prediction.member_video_ids
                            ],
                        }
                    )
            breadth_met = outcome.max_new_countries >= 5 and outcome.max_country_count >= 8
            new_supply_met = (
                outcome.max_supply_growth >= 3
                and outcome.max_new_channels >= 3
                and outcome.max_new_video_share >= 0.5
            )
            if breadth_met and not new_supply_met:
                duplicate_breadth_without_new_supply += 1
    return {
        "selected_predictions": selected,
        "duplicate_or_existing_video_breadth_without_new_supply": (
            duplicate_breadth_without_new_supply
        ),
        "largest_false_positive_contributors": [
            {"label": label, "count": count}
            for label, count in false_positive_labels.most_common(20)
        ],
        "false_positive_examples": false_positive_examples,
    }


def _markdown(payload: dict[str, Any]) -> str:
    primary = payload["primary_holdout"]
    rows = [
        "# EarlySignal: global cross-market robustness report",
        "",
        f"**Primary verdict:** `{primary['gate']['verdict']}`  ",
        f"**Primary reproduction:** "
        f"`{'MATCH' if payload['primary_reproduction_matches'] else 'MISMATCH'}`",
        "",
        "## Sensitivity (descriptive only)",
        "",
        "| Configuration | Checkpoints | Candidates | Positives | Method precision | Lead |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["sensitivity"].items():
        metrics = result["metrics"]
        method = metrics["rankings"]["method"]
        precision = method["precision_at_10_percent"]
        lead = method["median_lead_days"]
        rows.append(
            f"| {name} | {metrics['checkpoint_count']} | {metrics['candidate_topics']} | "
            f"{metrics['fired_candidate_topics']} | "
            f"{f'{precision}%' if precision is not None else 'N/A'} | "
            f"{lead if lead is not None else 'N/A'} |"
        )
    format_check = payload["format_invariance"]
    diagnostics = payload["primary_diagnostics"]
    unchanged_percent = format_check["unchanged_percent"]
    rows.extend(
        [
            "",
            "## Diagnostics",
            "",
            f"- Format-marker identity check: {format_check['unchanged_topic_identity']}/"
            f"{format_check['checked_videos']} unchanged "
            f"({unchanged_percent if unchanged_percent is not None else 'N/A'}%).",
            "- Method predictions with country breadth but without enough new-video/new-channel "
            f"supply: {diagnostics['duplicate_or_existing_video_breadth_without_new_supply']}.",
            "",
            "## Reproducibility",
            "",
            f"- Filtered evidence SHA-256: `{payload['filtered_sha256']}`",
            f"- Primary code/protocol SHA-256: `{primary['code_sha256']}`",
            "- Primary verdict is never changed by these sensitivity checks.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--primary-train", required=True, type=Path)
    parser.add_argument("--primary-holdout", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    train = json.loads(args.primary_train.read_text(encoding="utf-8"))
    holdout = json.loads(args.primary_holdout.read_text(encoding="utf-8"))
    with gzip.open(args.dataset, "rt", encoding="utf-8", newline="") as source:
        observations = tuple(iter_filtered_observations(source))
    last_observed_at = max(row.observed_at.astimezone(UTC) for row in observations)
    sensitivity: dict[str, Any] = {}
    primary_checkpoints: tuple[CrossMarketCheckpoint, ...] = ()
    for name, horizon_days, minimum_new_countries in SENSITIVITY_CONFIGS:
        policy = CrossMarketPolicy(
            outcome_horizon_days=horizon_days,
            minimum_new_countries=minimum_new_countries,
        )
        replay = CrossMarketReplay(observations, policy=policy)
        checkpoints = tuple(
            checkpoint
            for checkpoint in _checkpoints("holdout")
            if checkpoint + timedelta(days=horizon_days) <= last_observed_at
        )
        evaluated = deduplicate_cross_market_episodes(
            (replay.checkpoint(checkpoint) for checkpoint in checkpoints),
            cooldown_days=horizon_days,
            top_k=policy.top_k,
        )
        metrics = summarize_cross_market(evaluated, split="holdout")
        sensitivity[name] = {
            "horizon_days": horizon_days,
            "minimum_new_countries": minimum_new_countries,
            "metrics": metrics,
        }
        if name == "primary_21d_country5":
            primary_checkpoints = evaluated
    primary_reproduction_matches = (
        sensitivity["primary_21d_country5"]["metrics"] == holdout["metrics"]
    )
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "filtered_sha256": _file_hash(args.dataset),
        "primary_train": {"gate": train["gate"], "metrics": train["metrics"]},
        "primary_holdout": {
            "gate": holdout["gate"],
            "metrics": holdout["metrics"],
            "code_sha256": holdout["code_sha256"],
        },
        "primary_reproduction_matches": primary_reproduction_matches,
        "sensitivity": sensitivity,
        "primary_diagnostics": _diagnostics(primary_checkpoints),
        "format_invariance": _format_invariance(observations),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "primary_reproduction_matches": primary_reproduction_matches,
                "primary_verdict": holdout["gate"]["verdict"],
                "sensitivity": {name: result["metrics"] for name, result in sensitivity.items()},
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
