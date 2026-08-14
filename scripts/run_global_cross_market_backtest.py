from __future__ import annotations

import argparse
import gzip
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from packages.backtest.cross_market import (
    CROSS_MARKET_OUTCOME_VERSION,
    CROSS_MARKET_REPLAY_VERSION,
    CrossMarketCheckpoint,
    CrossMarketReplay,
    deduplicate_cross_market_episodes,
    summarize_cross_market,
)
from packages.backtest.global_trending import (
    GLOBAL_TRENDING_DATASET_VERSION,
    GlobalTrendingObservation,
    iter_filtered_observations,
)
from packages.clustering import MICROTOPIC_V6_VERSION

PREREGISTRATION = "GLOBAL_CROSS_MARKET_BACKTEST_PREREGISTRATION_2026-08-09.md"
SPLIT_RANGES = {
    "train": (
        datetime(2022, 8, 7, 23, 59, 59, tzinfo=UTC),
        datetime(2024, 6, 9, 23, 59, 59, tzinfo=UTC),
    ),
    "holdout": (
        datetime(2024, 7, 7, 23, 59, 59, tzinfo=UTC),
        datetime(2025, 6, 8, 23, 59, 59, tzinfo=UTC),
    ),
}


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_hash(root: Path) -> str:
    digest = sha256()
    for relative in (
        "packages/clustering/__init__.py",
        "packages/clustering/microtopics.py",
        "packages/clustering/microtopics_v6.py",
        "packages/clustering/semantic.py",
        "packages/scoring/__init__.py",
        "packages/scoring/early_signal.py",
        "packages/scoring/topic.py",
        "packages/backtest/external_timeseries.py",
        "packages/backtest/global_trending.py",
        "packages/backtest/cross_market.py",
        "scripts/filter_global_trending_archive.py",
        "scripts/stream_tar_member.py",
        "scripts/run_global_archive_filter.sh",
        "scripts/run_global_cross_market_backtest.py",
        "scripts/run_global_cross_market_sequence.sh",
        f"docs/evaluation/{PREREGISTRATION}",
    ):
        path = root / relative
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _checkpoints(
    split: Literal["train", "holdout"],
) -> tuple[datetime, ...]:
    start, end = SPLIT_RANGES[split]
    rows = []
    current = start
    while current <= end:
        rows.append(current)
        current += timedelta(days=7)
    return tuple(rows)


def _bounded_observations(
    observations: Iterable[GlobalTrendingObservation],
    *,
    maximum_observed_at: datetime,
) -> Iterator[GlobalTrendingObservation]:
    """Stop reading the chronological archive at the split's mature boundary.

    The train process must not even deserialize holdout rows before its report and
    code hash have been persisted. The source archive is chronological; asserting
    that invariant makes an accidental out-of-order future row a hard failure.
    """

    previous: datetime | None = None
    for row in observations:
        observed_at = row.observed_at.astimezone(UTC)
        if previous is not None and observed_at < previous:
            raise ValueError("filtered global archive is not chronological")
        previous = observed_at
        if observed_at > maximum_observed_at:
            return
        yield row


def _checkpoint_payload(row: CrossMarketCheckpoint) -> dict[str, Any]:
    outcomes = {outcome.topic_key: outcome for outcome in row.outcomes}
    candidates = {candidate.topic_key: candidate for candidate in row.candidates}
    predictions = []
    for rank, prediction in enumerate(row.predictions, start=1):
        outcome = outcomes[prediction.topic_key]
        predictions.append(
            {
                "rank": rank,
                "topic_key": prediction.topic_key,
                "label": prediction.label,
                "score": prediction.score,
                "video_count_7d": prediction.video_count_7d,
                "distinct_channels_30d": prediction.distinct_channels_30d,
                "country_count_30d": prediction.country_count_30d,
                "evidence_video_ids": list(prediction.member_video_ids),
                "evidence_urls": [
                    f"https://www.youtube.com/watch?v={video_id}"
                    for video_id in prediction.member_video_ids
                ],
                "evidence_titles": list(prediction.evidence_titles),
                "fired": outcome.fired,
                "fired_at": outcome.fired_at.isoformat() if outcome.fired_at else None,
                "lead_days": outcome.lead_days,
                "max_supply_growth": outcome.max_supply_growth,
                "max_new_channels": outcome.max_new_channels,
                "max_new_countries": outcome.max_new_countries,
                "max_country_count": outcome.max_country_count,
                "max_new_video_share": outcome.max_new_video_share,
            }
        )
    return {
        "checkpoint_at": row.checkpoint_at.isoformat(),
        "candidate_count": row.candidate_count,
        "predictions": predictions,
        "positive_candidate_count": sum(outcome.fired for outcome in row.outcomes),
        "positive_candidates": [
            {
                "topic_key": outcome.topic_key,
                "label": candidates[outcome.topic_key].label,
                "fired_at": outcome.fired_at.isoformat() if outcome.fired_at else None,
                "lead_days": outcome.lead_days,
                "evidence_video_ids": list(candidates[outcome.topic_key].member_video_ids),
                "evidence_urls": [
                    f"https://www.youtube.com/watch?v={video_id}"
                    for video_id in candidates[outcome.topic_key].member_video_ids
                ],
                "evidence_titles": list(candidates[outcome.topic_key].evidence_titles),
                "selected_by_method": any(
                    prediction.topic_key == outcome.topic_key for prediction in row.predictions
                ),
            }
            for outcome in row.outcomes
            if outcome.fired
        ],
    }


def _gate(metrics: dict[str, Any], *, split: str) -> dict[str, Any]:
    method = metrics["rankings"]["method"]
    precision = method["precision_at_10_percent"]
    baseline_precisions = [
        metrics["rankings"][name]["precision_at_10_percent"]
        for name in ("supply", "countries", "velocity", "view_growth", "random")
        if metrics["rankings"][name]["precision_at_10_percent"] is not None
    ]
    checks = {
        "holdout_split": split == "holdout",
        "positive_outcome_support": metrics["fired_candidate_topics"] >= 20,
        "precision_at_10": precision is not None and precision >= 40,
        "median_lead": (method["median_lead_days"] is not None and method["median_lead_days"] >= 7),
        "beats_base_rate": (
            precision is not None
            and metrics["candidate_base_rate_percent"] is not None
            and precision > metrics["candidate_base_rate_percent"]
        ),
        "not_worse_than_each_simple_baseline": (
            precision is not None
            and bool(baseline_precisions)
            and precision >= max(baseline_precisions)
        ),
        "complete_followup": True,
    }
    if split != "holdout":
        verdict = "TRAIN_DIAGNOSTIC"
    elif not checks["positive_outcome_support"]:
        verdict = "INSUFFICIENT_OUTCOME_SUPPORT"
    else:
        verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks}


def _markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    gate = payload["gate"]
    base_rate = metrics["candidate_base_rate_percent"]
    rows = [
        "# EarlySignal global cross-market historical replay",
        "",
        f"**Split:** `{payload['split']}`  ",
        f"**Verdict:** `{gate['verdict']}`  ",
        f"**Protocol:** `{payload['replay_version']}`  ",
        f"**Outcome:** `{payload['outcome_version']}`  ",
        f"**Taxonomy:** `{payload['taxonomy_version']}`",
        "",
        f"- Filtered evidence videos: {payload['video_count']}",
        f"- Stable topic identities: {payload['topic_identity_count']}",
        f"- Weekly checkpoints: {metrics['checkpoint_count']}",
        f"- Eligible topic-checkpoints: {metrics['candidate_topics']}",
        f"- Positive future topic outcomes: {metrics['fired_candidate_topics']}",
        f"- Candidate base rate: {base_rate if base_rate is not None else 'N/A'}%",
        "",
        "## Ranking comparison",
        "",
        "| Ranking | Predictions | Fired | Precision@10 | Recall | Median lead |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("method", "supply", "countries", "velocity", "view_growth", "random"):
        item = metrics["rankings"][name]
        precision = item["precision_at_10_percent"]
        recall = item["recall_percent"]
        lead = item["median_lead_days"]
        rows.append(
            f"| {name} | {item['predictions']} | {item['fired']} | "
            f"{f'{precision}%' if precision is not None else 'N/A'} | "
            f"{f'{recall}%' if recall is not None else 'N/A'} | "
            f"{lead if lead is not None else 'N/A'} |"
        )
    rows.extend(
        [
            "",
            "## Frozen gate",
            "",
            "| Check | Result |",
            "|---|---|",
            *[
                f"| {name} | {'PASS' if passed else 'FAIL'} |"
                for name, passed in gate["checks"].items()
            ],
            "",
            "## Historical method predictions",
            "",
        ]
    )
    for checkpoint in payload["checkpoints"]:
        rows.extend(
            [
                f"### {checkpoint['checkpoint_at']}",
                "",
                f"Eligible candidates: {checkpoint['candidate_count']}; "
                f"future positives: {checkpoint['positive_candidate_count']}",
                "",
                "| Rank | Topic | Score | Evidence | Countries | Fired | Lead |",
                "|---:|---|---:|---:|---:|---|---:|",
            ]
        )
        if not checkpoint["predictions"]:
            rows.append("| — | No eligible prediction | — | — | — | — | — |")
        for prediction in checkpoint["predictions"]:
            label = str(prediction["label"]).replace("|", "\\|")
            rows.append(
                f"| {prediction['rank']} | {label} | {prediction['score']} | "
                f"{prediction['distinct_channels_30d']} channels | "
                f"{prediction['country_count_30d']} | "
                f"{'yes' if prediction['fired'] else 'no'} | "
                f"{prediction['lead_days'] if prediction['lead_days'] is not None else 'N/A'} |"
            )
        rows.append("")
    rows.extend(
        [
            "## Reproducibility",
            "",
            f"- Source SHA-256: `{payload['source_sha256']}`",
            f"- Filtered slice SHA-256: `{payload['filtered_sha256']}`",
            f"- Code/protocol SHA-256: `{payload['code_sha256']}`",
            f"- Dataset adapter: `{payload['dataset_version']}`",
            f"- Preregistration: `{PREREGISTRATION}`",
            "- Source: https://doi.org/10.13012/B2IDB-9307654_V1",
            "",
            "## Interpretation boundary",
            "",
            "This replay tests diffusion after a first public Trending appearance. The source "
            "does not contain the complete pre-Trending YouTube upload universe, so the result "
            "must not be described as prediction before all platform confirmation.",
            "",
            "The archive has no complete non-Trending upload universe, subscriber baseline, "
            "search demand, comments or transcripts. Those production inputs are held at "
            "neutral/zero values, so this test evaluates the observable cross-market ranking "
            "slice rather than the entire product stack.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=("train", "holdout"), required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    split: Literal["train", "holdout"] = args.split
    checkpoints = _checkpoints(split)
    maximum_observed_at = checkpoints[-1] + timedelta(days=21)
    with gzip.open(args.dataset, "rt", encoding="utf-8", newline="") as source:
        replay = CrossMarketReplay(
            _bounded_observations(
                iter_filtered_observations(source),
                maximum_observed_at=maximum_observed_at,
            )
        )
    checkpoint_rows = deduplicate_cross_market_episodes(
        (replay.checkpoint(row) for row in checkpoints),
        cooldown_days=replay.policy.outcome_horizon_days,
        top_k=replay.policy.top_k,
    )
    metrics = summarize_cross_market(checkpoint_rows, split=split)
    root = Path(__file__).resolve().parents[1]
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "split": split,
        "dataset_version": GLOBAL_TRENDING_DATASET_VERSION,
        "replay_version": CROSS_MARKET_REPLAY_VERSION,
        "outcome_version": CROSS_MARKET_OUTCOME_VERSION,
        "taxonomy_version": MICROTOPIC_V6_VERSION,
        "source_sha256": args.source_sha256,
        "filtered_sha256": _file_hash(args.dataset),
        "code_sha256": _code_hash(root),
        "video_count": replay.video_count,
        "topic_identity_count": replay.topic_identity_count,
        "first_observed_at": (
            replay.first_observed_at.isoformat() if replay.first_observed_at else None
        ),
        "last_observed_at": (
            replay.last_observed_at.isoformat() if replay.last_observed_at else None
        ),
        "policy": replay.policy.__dict__,
        "feature_limitations": [
            "No non-Trending upload universe or channel subscriber baseline.",
            "No unbiased per-channel outlier ratio, search demand, comments, or transcripts.",
            "Unavailable production features are fixed at neutral or zero values.",
            "The replay validates cross-market diffusion ranking, not the complete "
            "production stack.",
        ],
        "metrics": metrics,
        "gate": _gate(metrics, split=split),
        "checkpoints": [_checkpoint_payload(row) for row in checkpoint_rows],
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps({"gate": payload["gate"], "metrics": metrics}, sort_keys=True))


if __name__ == "__main__":
    main()
