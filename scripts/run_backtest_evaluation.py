from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import BacktestCheckpoint
from packages.backtest import (
    BacktestReportService,
    BlindOutcomeLabeler,
    OutcomeLabelPolicy,
    QualityGatePolicy,
    ReplayPolicy,
    TemporalReplayService,
)
from scripts.export_backtest_checkpoint import parse_timestamp


def _checkpoint_ids(value: str) -> list[str]:
    values = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not values:
        raise argparse.ArgumentTypeError("at least one checkpoint id is required")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Replay point-in-time predictions, label future outcomes blindly, "
            "and render a quality report."
        )
    )
    parser.add_argument("--checkpoint-ids", required=True, type=_checkpoint_ids)
    parser.add_argument(
        "--evaluation-as-of",
        type=parse_timestamp,
        default=datetime.now(tz=UTC),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--name", default="temporal backtest")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--horizon-days", type=int, default=42)
    parser.add_argument("--max-snapshot-age-days", type=int, default=7)
    parser.add_argument("--minimum-checkpoints", type=int, default=6)
    args = parser.parse_args()

    settings = Settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        checkpoints_by_id = {
            row.id: row
            for row in session.scalars(
                select(BacktestCheckpoint).where(BacktestCheckpoint.id.in_(args.checkpoint_ids))
            )
        }
        missing = [
            checkpoint_id
            for checkpoint_id in args.checkpoint_ids
            if checkpoint_id not in checkpoints_by_id
        ]
        if missing:
            parser.error(f"checkpoint ids not found: {', '.join(missing)}")
        checkpoints = [checkpoints_by_id[item] for item in args.checkpoint_ids]
        replay = TemporalReplayService(session)
        labeler = BlindOutcomeLabeler(session)
        replay_policy = ReplayPolicy(
            top_k=args.top_k,
            max_snapshot_age_days=args.max_snapshot_age_days,
        )
        label_policy = OutcomeLabelPolicy(horizon_days=args.horizon_days)
        replay_counts: dict[str, dict[str, int]] = {}
        for checkpoint in checkpoints:
            predictions, universe = replay.replay_checkpoint(
                checkpoint,
                policy=replay_policy,
                persist=True,
            )
            outcomes = labeler.label_checkpoint(
                checkpoint,
                evaluation_as_of=args.evaluation_as_of,
                policy=label_policy,
                persist=True,
            )
            replay_counts[checkpoint.id] = {
                "candidate_universe": len(universe),
                "outcomes": len(outcomes),
                "predictions": len(predictions),
            }
        report = BacktestReportService(session).build_and_persist(
            name=args.name,
            checkpoints=checkpoints,
            gate_policy=QualityGatePolicy(
                top_k=args.top_k,
                minimum_checkpoints=args.minimum_checkpoints,
            ),
        )
        report_content_hash = report.content_hash
        report_gate_passed = bool(report.gate_json["passed"])
        report_markdown = report.markdown_report
        report_metrics = report.metrics_json
        report_id = report.id
        report_status = report.status

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_markdown + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "content_hash": report_content_hash,
                "gate_passed": report_gate_passed,
                "metrics": report_metrics,
                "output": str(args.output),
                "report_id": report_id,
                "replay_counts": replay_counts,
                "status": report_status,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
