from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.backtest import (
    CohortPolicy,
    HistoricalCohortService,
    InsufficientCohortData,
)
from scripts.export_backtest_checkpoint import parse_timestamp


def _checkpoint_times(value: str) -> list[datetime]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("checkpoint timestamps must not be empty")
    return [parse_timestamp(item) for item in values]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect direct point-in-time coverage and optionally freeze a chronological "
            "train/holdout backtest cohort before outcome evaluation."
        )
    )
    parser.add_argument("--as-of", type=parse_timestamp, default=datetime.now(tz=UTC))
    parser.add_argument("--source-kind", choices=("live", "demo"), default="live")
    parser.add_argument("--source-environment", default="local")
    parser.add_argument("--name", default="historical baseline cohort")
    parser.add_argument("--checkpoint-count", type=int, default=8)
    parser.add_argument("--holdout-count", type=int, default=2)
    parser.add_argument("--horizon-days", type=int, default=42)
    parser.add_argument("--candidate-days", type=int, default=120)
    parser.add_argument("--minimum-eligible-videos", type=int, default=1)
    parser.add_argument("--minimum-direct-snapshots", type=int, default=1)
    parser.add_argument("--minimum-prediction-candidates", type=int, default=1)
    parser.add_argument(
        "--checkpoint-times",
        type=_checkpoint_times,
        help="Optional comma-separated UTC timestamps; otherwise daily cutoffs are discovered.",
    )
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()

    policy = CohortPolicy(
        checkpoint_count=args.checkpoint_count,
        holdout_count=args.holdout_count,
        horizon_days=args.horizon_days,
        candidate_days=args.candidate_days,
        minimum_eligible_videos=args.minimum_eligible_videos,
        minimum_direct_snapshots=args.minimum_direct_snapshots,
        minimum_prediction_candidates=args.minimum_prediction_candidates,
    )
    settings = Settings()
    engine = create_engine(settings.database_url)
    exit_code = 0
    with Session(engine) as session:
        service = HistoricalCohortService(session)
        coverage = service.inspect(
            freeze_at=args.as_of,
            source_kind=args.source_kind,
            policy=policy,
            checkpoint_times=args.checkpoint_times,
        )
        eligible = [row for row in coverage if row.eligible]
        payload: dict[str, object] = {
            "as_of": args.as_of.isoformat(),
            "coverage": [row.as_dict() for row in coverage],
            "eligible_checkpoint_count": len(eligible),
            "frozen": None,
            "policy": asdict(policy),
            "source_kind": args.source_kind,
            "status": "ready_to_freeze"
            if len(eligible) >= policy.checkpoint_count
            else "insufficient_checkpoint_coverage",
        }
        markdown: str | None = None
        if args.freeze:
            try:
                frozen = service.freeze(
                    name=args.name,
                    freeze_at=args.as_of,
                    source_environment=args.source_environment,
                    source_kind=args.source_kind,
                    policy=policy,
                    checkpoint_times=args.checkpoint_times,
                )
                payload["frozen"] = {
                    "checkpoint_ids": list(frozen.checkpoint_ids),
                    "cohort_id": frozen.cohort_id,
                    "dataset_hash": frozen.dataset_hash,
                    "holdout_checkpoint_ids": list(frozen.holdout_checkpoint_ids),
                    "train_checkpoint_ids": list(frozen.train_checkpoint_ids),
                }
                payload["status"] = "frozen"
                markdown = frozen.markdown_report
            except InsufficientCohortData as error:
                payload["error"] = str(error)
                exit_code = 2

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.output_markdown and markdown is not None:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
