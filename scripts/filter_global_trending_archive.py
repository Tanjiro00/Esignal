from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from packages.backtest.global_trending import filter_global_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--train-output", required=True, type=Path)
    parser.add_argument("--train-max-collection-at", required=True)
    parser.add_argument("--stats-output", required=True, type=Path)
    parser.add_argument(
        "--input",
        type=Path,
        help="Uncompressed source CSV. Omit to read the CSV stream from stdin.",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.train_output.parent.mkdir(parents=True, exist_ok=True)
    args.stats_output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(f"{args.output.suffix}.partial")
    train_partial = args.train_output.with_suffix(f"{args.train_output.suffix}.partial")
    train_cutoff = datetime.fromisoformat(
        args.train_max_collection_at.replace("Z", "+00:00")
    ).astimezone(UTC)
    source = (
        args.input.open("r", encoding="utf-8", newline="") if args.input is not None else sys.stdin
    )
    try:
        with ExitStack() as stack:
            target = stack.enter_context(
                gzip.open(partial, "wt", encoding="utf-8", newline="", compresslevel=3)
            )
            train_target = stack.enter_context(
                gzip.open(
                    train_partial,
                    "wt",
                    encoding="utf-8",
                    newline="",
                    compresslevel=3,
                )
            )
            stats = filter_global_rows(
                source,
                target,
                train_destination=train_target,
                train_max_collection_at=train_cutoff,
            )
    finally:
        if args.input is not None:
            source.close()
    os.replace(partial, args.output)
    os.replace(train_partial, args.train_output)
    args.stats_output.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
