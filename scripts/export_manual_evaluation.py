from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import EvaluationLabel, SignalAction
from packages.evaluation import (
    evaluation_export_records,
    feedback_export_records,
    records_as_csv,
    records_as_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export point-in-time manual evaluation labels or decision feedback."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("labels", "feedback"), default="labels")
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    parser.add_argument("--workspace-id")
    args = parser.parse_args()

    settings = Settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        if args.kind == "labels":
            query = select(EvaluationLabel)
            if args.workspace_id:
                query = query.where(EvaluationLabel.workspace_id == args.workspace_id)
            records = evaluation_export_records(list(session.scalars(query)))
        else:
            action_query = select(SignalAction)
            if args.workspace_id:
                action_query = action_query.where(SignalAction.workspace_id == args.workspace_id)
            records = feedback_export_records(list(session.scalars(action_query)))

    content = records_as_jsonl(records) if args.format == "jsonl" else records_as_csv(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {len(records)} {args.kind} records to {args.output}")


if __name__ == "__main__":
    main()
