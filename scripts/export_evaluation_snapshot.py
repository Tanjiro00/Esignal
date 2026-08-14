from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.evaluation import build_evaluation_snapshot


def _captured_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a deterministic, evidence-safe topic/signal snapshot."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-kind", choices=("demo", "live"), required=True)
    parser.add_argument("--source-environment", required=True)
    parser.add_argument("--captured-at")
    parser.add_argument("--expected-topics", type=int)
    parser.add_argument("--expected-signals", type=int)
    args = parser.parse_args()

    settings = Settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        payload = build_evaluation_snapshot(
            session,
            captured_at=_captured_at(args.captured_at),
            source_kind=args.source_kind,
            source_environment=args.source_environment,
        )

    counts = payload["counts"]
    if args.expected_topics is not None and counts["topic_candidates"] != args.expected_topics:
        raise SystemExit(
            f"Expected {args.expected_topics} topics, found {counts['topic_candidates']}"
        )
    if args.expected_signals is not None and counts["visible_signals"] != args.expected_signals:
        raise SystemExit(
            f"Expected {args.expected_signals} signals, found {counts['visible_signals']}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {counts['topic_candidates']} topics and "
        f"{counts['visible_signals']} visible signals to {args.output}"
    )


if __name__ == "__main__":
    main()
