from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.config import Settings
from packages.backtest import AsOfContext, PointInTimeCheckpointService


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone, for example Z")
    return parsed.astimezone(UTC)


def _providers(value: str) -> tuple[str, ...]:
    return tuple(provider.strip() for provider in value.split(",") if provider.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export a deterministic point-in-time evidence manifest without replaying predictions."
        )
    )
    parser.add_argument("--as-of", required=True, type=parse_timestamp)
    parser.add_argument("--source-kind", choices=("live", "demo"), default="live")
    parser.add_argument("--source-environment", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--providers",
        default="",
        help="Optional comma-separated provider allowlist for sensitivity runs.",
    )
    parser.add_argument("--exclude-comments", action="store_true")
    parser.add_argument("--exclude-transcripts", action="store_true")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the verified manifest in backtest_runs/checkpoints.",
    )
    parser.add_argument("--name", default="point-in-time checkpoint")
    args = parser.parse_args()

    context = AsOfContext(
        as_of=args.as_of,
        source_kind=args.source_kind,
        allowed_providers=_providers(args.providers),
        include_comments=not args.exclude_comments,
        include_transcripts=not args.exclude_transcripts,
    )
    settings = Settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        service = PointInTimeCheckpointService(session)
        manifest = service.build_manifest(
            context,
            source_environment=args.source_environment,
        )
        persisted_ids: dict[str, str] | None = None
        if args.persist:
            run, checkpoint = service.persist_manifest(manifest, name=args.name)
            persisted_ids = {"checkpoint_id": checkpoint.id, "run_id": run.id}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = {
        "content_sha256": manifest["content_sha256"],
        "input_hash": manifest["input_hash"],
        "output": str(args.output),
        "persisted": persisted_ids,
        "snapshots": manifest["input_tables"]["video_snapshots"]["count"],
        "videos": manifest["input_tables"]["videos"]["count"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
